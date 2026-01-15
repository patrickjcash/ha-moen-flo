"""The Moen Flo NAB Sump Pump Monitor integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MoenFloNABClient, MoenFloNABApiError, MoenFloNABMqttClient
from .const import DOMAIN
from .statistics import async_import_pump_statistics

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]

# Adaptive polling constants
MIN_POLL_INTERVAL = 10  # Minimum polling interval in seconds
MAX_POLL_INTERVAL = 300  # Maximum polling interval in seconds (5 minutes)
ALERT_MAX_INTERVAL = 60  # Maximum interval when non-info alerts are active
CYCLE_WINDOW_MINUTES = 15  # Look back window for counting recent cycles


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Moen Flo NAB from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    session = async_get_clientsession(hass)
    client = MoenFloNABClient(username, password, session)

    # Authenticate
    try:
        await client.authenticate()
    except MoenFloNABApiError as err:
        _LOGGER.error("Failed to authenticate: %s", err)
        return False

    # Create coordinator
    coordinator = MoenFloNABDataUpdateCoordinator(hass, client)

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Forward to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        # Disconnect MQTT clients
        await coordinator.disconnect_mqtt()

    return unload_ok


class MoenFloNABDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Moen Flo NAB data."""

    def __init__(self, hass: HomeAssistant, client: MoenFloNABClient) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=MAX_POLL_INTERVAL),
        )
        self.client = client
        self.devices = {}
        self.mqtt_clients = {}  # Store MQTT clients per device
        self._last_alert_state = {}  # Track alert states for adaptive polling
        self._first_refresh = True  # Track if this is the first data fetch
        self._water_distance_history = {}  # Track water distance readings per device
        self._notification_metadata = {}  # Cache notification ID to title mappings per device
        self._pump_thresholds = {}  # Persistent pump on/off thresholds per device
        self._previous_distance = {}  # Track previous water distance for event detection
        self._last_distance_time = {}  # Track timestamp of last distance reading

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            # Get list of locations (houses)
            try:
                locations = await self.client.get_locations()
                _LOGGER.debug(f"Found {len(locations)} location(s)")
            except Exception as err:
                _LOGGER.warning(f"Failed to get locations: {err}")
                locations = []

            # Get list of all devices
            devices_list = await self.client.get_devices()

            # Filter to only NAB (sump pump monitor) devices
            nab_devices = [d for d in devices_list if d.get("deviceType") == "NAB"]

            if not nab_devices:
                _LOGGER.warning("No NAB (sump pump monitor) devices found")
                return {}

            _LOGGER.debug(f"Found {len(nab_devices)} NAB device(s) out of {len(devices_list)} total devices")

            data = {}

            for device in nab_devices:
                device_duid = device.get("duid")
                client_id = device.get("clientId")
                location_id = device.get("locationId")
                federated_identity = device.get("federatedIdentity")

                if not device_duid or not client_id:
                    _LOGGER.warning("Device missing duid or clientId: %s", device)
                    continue

                # Set cognito identity ID for API calls that require it
                # (pump cycles, environment data, pump health)
                if federated_identity:
                    self.client._cognito_identity_id = federated_identity
                else:
                    _LOGGER.warning("Device %s missing federatedIdentity, some API calls may fail", device_duid)

                # Find the location name for this device
                location_name = None
                if location_id and locations:
                    for loc in locations:
                        if loc.get("locationId") == location_id:
                            location_name = loc.get("nickname")
                            break

                # Store both IDs and location info for future use
                device_data = {
                    "duid": device_duid,
                    "clientId": client_id,
                    "locationId": location_id,
                    "locationName": location_name,
                    "info": device,
                }

                # Get/create MQTT client for this device
                mqtt_client = self.mqtt_clients.get(device_duid)
                if mqtt_client is None:
                    mqtt_client = self.client.create_mqtt_client(client_id)
                    if mqtt_client:
                        # Connect to MQTT
                        connected = await mqtt_client.connect()
                        if connected:
                            self.mqtt_clients[device_duid] = mqtt_client
                            _LOGGER.info("Established MQTT connection for device %s", device_duid)
                        else:
                            _LOGGER.warning("Failed to connect MQTT for device %s, using REST fallback", device_duid)
                            mqtt_client = None
                elif mqtt_client.needs_reconnect():
                    # Credentials expired, need to reconnect with fresh ID token
                    _LOGGER.info("MQTT credentials expired for device %s, reconnecting", device_duid)
                    try:
                        # Ensure we have fresh tokens
                        await self.client.authenticate()
                        # Reconnect with new ID token
                        reconnected = await mqtt_client.reconnect_with_new_token(self.client._id_token)
                        if not reconnected:
                            _LOGGER.warning("Failed to reconnect MQTT for device %s, using REST fallback", device_duid)
                            mqtt_client = None
                            # Remove from cache so we can try fresh connection next time
                            self.mqtt_clients.pop(device_duid, None)
                    except Exception as err:
                        _LOGGER.error("Failed to reauthenticate during MQTT reconnect for device %s: %s. Using REST fallback", device_duid, err)
                        mqtt_client = None
                        # Remove from cache so we can try fresh connection next time
                        self.mqtt_clients.pop(device_duid, None)

                # Get live telemetry via MQTT
                try:
                    if mqtt_client and mqtt_client.is_connected:
                        # Trigger fresh sensor reading via MQTT
                        await mqtt_client.trigger_sensor_update("sens_on")
                        # Wait for device to take reading and update shadow (~2 seconds)
                        await asyncio.sleep(2)
                        # Request shadow via MQTT to get the fresh reading
                        await mqtt_client.request_shadow()
                        # Wait for shadow response
                        await asyncio.sleep(1)

                        # Stop streaming to preserve battery
                        await mqtt_client.trigger_sensor_update("updates_off")

                        # Get shadow data from MQTT client
                        reported = mqtt_client.last_shadow_data
                        if reported:
                            # Merge shadow data into device info
                            device_data["info"]["crockTofDistance"] = reported.get(
                                "crockTofDistance", device_data["info"].get("crockTofDistance")
                            )
                            device_data["info"]["droplet"] = reported.get(
                                "droplet", device_data["info"].get("droplet")
                            )
                            device_data["info"]["connected"] = reported.get(
                                "connected", device_data["info"].get("connected")
                            )
                            device_data["info"]["wifiRssi"] = reported.get(
                                "wifiRssi", device_data["info"].get("wifiRssi")
                            )
                            device_data["info"]["batteryPercentage"] = reported.get(
                                "batteryPercentage", device_data["info"].get("batteryPercentage")
                            )
                            device_data["info"]["powerSource"] = reported.get(
                                "powerSource", device_data["info"].get("powerSource")
                            )
                            device_data["info"]["alerts"] = reported.get(
                                "alerts", device_data["info"].get("alerts")
                            )

                            # Track water distance for threshold calculation
                            distance = reported.get("crockTofDistance")
                            if distance is not None:
                                # Detect pump events for threshold learning
                                self._detect_pump_events(device_duid, distance)

                                if device_duid not in self._water_distance_history:
                                    self._water_distance_history[device_duid] = []
                                self._water_distance_history[device_duid].append(distance)
                                # Keep last 100 readings
                                if len(self._water_distance_history[device_duid]) > 100:
                                    self._water_distance_history[device_duid].pop(0)

                            _LOGGER.debug(
                                "Updated device %s with MQTT shadow data (water level: %s mm)",
                                device_duid,
                                reported.get("crockTofDistance"),
                            )
                        else:
                            _LOGGER.warning("No shadow data received from MQTT for device %s", device_duid)
                    else:
                        _LOGGER.warning("MQTT not connected for device %s, using cached telemetry data", device_duid)

                except Exception as err:
                    _LOGGER.warning(
                        "Failed to get shadow data for device %s: %s", device_duid, err
                    )

                # Calculate pump thresholds from water distance history (updated by MQTT above)
                device_data["pump_thresholds"] = self._calculate_pump_thresholds(device_duid)

                # Get environment data (temp/humidity) using numeric ID
                try:
                    env_data = await self.client.get_device_environment(client_id)
                    device_data["environment"] = env_data
                except Exception as err:
                    _LOGGER.warning(
                        "Failed to get environment data for device %s: %s",
                        device_duid,
                        err,
                    )
                    device_data["environment"] = {}

                # Get pump health data using numeric ID
                try:
                    health_data = await self.client.get_pump_health(client_id)
                    device_data["pump_health"] = health_data
                except Exception as err:
                    _LOGGER.warning(
                        "Failed to get pump health for device %s: %s", device_duid, err
                    )
                    device_data["pump_health"] = {}

                # Get pump cycle history using numeric ID
                try:
                    # On first refresh, fetch all available cycles for statistics import
                    # On subsequent updates, fetch last 50 cycles for incremental updates
                    limit = 1000 if self._first_refresh else 50
                    cycles = await self.client.get_pump_cycles(client_id, limit=limit)
                    device_data["pump_cycles"] = cycles

                    # Import statistics on first refresh or when we have new cycles
                    if cycles and (self._first_refresh or len(cycles) > 0):
                        device_name = device.get("nickname", f"Sump Pump {device_duid[:8]}")
                        await async_import_pump_statistics(
                            self.hass,
                            device_duid,
                            device_name,
                            cycles,
                        )

                except Exception as err:
                    _LOGGER.warning(
                        "Failed to get pump cycles for device %s: %s", device_duid, err
                    )
                    device_data["pump_cycles"] = []

                # Get event logs for water detection using UUID
                # NOTE: Event logs are also used to build notification metadata
                try:
                    events = await self.client.get_device_logs(device_duid, limit=50)
                    device_data["event_logs"] = {"events": events}
                except Exception as err:
                    _LOGGER.warning(
                        "Failed to get event logs for device %s: %s", device_duid, err
                    )
                    device_data["event_logs"] = {"events": []}

                # Build notification metadata map (only once per device)
                if device_duid not in self._notification_metadata:
                    try:
                        notification_map = await self.client.get_notification_metadata(device_duid)
                        self._notification_metadata[device_duid] = notification_map
                        _LOGGER.info(
                            "Built notification metadata for device %s: %d types",
                            device_duid[:8],
                            len(notification_map)
                        )
                    except Exception as err:
                        _LOGGER.warning(
                            "Failed to build notification metadata for device %s: %s",
                            device_duid,
                            err
                        )
                        self._notification_metadata[device_duid] = {}

                # Store notification metadata in device data for sensors to access
                device_data["notification_metadata"] = self._notification_metadata.get(device_duid, {})

                # Get active alerts from v2 API (replaces shadow alerts)
                # This provides the same alert list as the mobile app
                try:
                    active_alerts_list = await self.client.get_active_alerts()

                    # Filter to this device's alerts
                    device_alerts = [
                        alert for alert in active_alerts_list
                        if str(alert.get("duid")) == str(client_id)
                    ]

                    # Convert list to dictionary format for sensor compatibility
                    # Shadow format: {"262": {...}, "218": {...}}
                    # ACTIVE format: [{...}, {...}] with severity included
                    alerts_dict = {}
                    for alert in device_alerts:
                        alert_id = alert.get("id")
                        if alert_id:
                            # Store alert with additional fields from v2 API
                            alerts_dict[alert_id] = {
                                "state": alert.get("state"),
                                "timestamp": alert.get("time"),
                                "severity": alert.get("severity"),  # Now directly available
                                "dismiss": alert.get("dismiss"),
                                "title": alert.get("title"),
                            }

                    # Override shadow alerts with ACTIVE alerts
                    device_data["info"]["alerts"] = alerts_dict

                    _LOGGER.debug(
                        "Updated device %s with %d active alert(s) from v2 API",
                        device_duid[:8],
                        len(alerts_dict)
                    )
                except Exception as err:
                    _LOGGER.warning(
                        "Failed to get active alerts for device %s: %s. Using shadow alerts.",
                        device_duid,
                        err
                    )
                    # Keep shadow alerts as fallback (already set above)

                data[device_duid] = device_data

                # Implement adaptive polling based on alert state
                self._update_poll_interval(device_duid, device_data)

            # Mark first refresh as complete
            if self._first_refresh:
                self._first_refresh = False
                _LOGGER.info("Initial data fetch and statistics import complete")

            return data

        except MoenFloNABApiError as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    def _update_poll_interval(self, device_duid: str, device_data: dict):
        """Update polling interval based on pump activity and active alerts.

        Adaptive polling formula: interval = 180 / cycles_in_last_15_min
        - Minimum: 10 seconds
        - Maximum: 300 seconds (5 minutes)
        - Alert override: 60 second maximum when non-info alerts are active
        """
        from datetime import datetime, timezone

        # Count cycles in last 15 minutes
        pump_cycles = device_data.get("pump_cycles", [])
        now = datetime.now(timezone.utc)
        recent_cycles = 0

        for cycle in pump_cycles:
            try:
                cycle_time_str = cycle.get("date", "")
                if cycle_time_str:
                    cycle_time = datetime.fromisoformat(cycle_time_str.replace("Z", "+00:00"))
                    minutes_ago = (now - cycle_time).total_seconds() / 60
                    if minutes_ago <= CYCLE_WINDOW_MINUTES:
                        recent_cycles += 1
            except (ValueError, AttributeError):
                continue

        # Calculate base interval: 180 / cycles (with divide-by-zero protection)
        if recent_cycles == 0:
            calculated_interval = MAX_POLL_INTERVAL
        else:
            calculated_interval = 180 / recent_cycles

        # Apply hard limits
        calculated_interval = max(MIN_POLL_INTERVAL, min(calculated_interval, MAX_POLL_INTERVAL))

        # Check for unacknowledged critical or warning alerts
        alerts = device_data.get("info", {}).get("alerts")
        if not isinstance(alerts, dict):
            alerts = {}

        notification_metadata = device_data.get("notification_metadata", {})
        has_non_info_alert = False

        for alert_id, alert_data in alerts.items():
            state = alert_data.get("state", "")
            # Only check unacknowledged alerts (matches mobile app behavior)
            if "unlack" in state:
                # Get severity from alert data (v2 API) or metadata
                severity = alert_data.get("severity", "").lower()
                if not severity and alert_id in notification_metadata:
                    severity = notification_metadata[alert_id].get("severity", "").lower()

                # Only cap polling for critical or warning severity
                if severity in ["critical", "warning"]:
                    has_non_info_alert = True
                    break

        # Apply alert override
        if has_non_info_alert:
            final_interval = min(calculated_interval, ALERT_MAX_INTERVAL)
        else:
            final_interval = calculated_interval

        # Create timedelta
        new_interval = timedelta(seconds=final_interval)

        # Get previous interval for comparison
        previous_interval = self.update_interval.total_seconds() if self.update_interval else MAX_POLL_INTERVAL

        # Only update and log if interval changed significantly (>5 seconds difference)
        if abs(final_interval - previous_interval) > 5:
            self.update_interval = new_interval
            alert_note = f" (capped by alerts)" if has_non_info_alert and final_interval == ALERT_MAX_INTERVAL else ""
            _LOGGER.info(
                "Device %s: %d cycles in last %d min → polling every %.0fs%s",
                device_duid,
                recent_cycles,
                CYCLE_WINDOW_MINUTES,
                final_interval,
                alert_note
            )

    def _detect_pump_events(self, device_duid: str, current_distance: float) -> None:
        """Detect pump ON/OFF events from water distance changes.

        Uses persistent thresholds that adapt over time based on detected pump events.
        This approach works across long time periods (days/weeks) between pump cycles.

        Args:
            device_duid: Device UUID
            current_distance: Current water distance in mm
        """
        import time

        previous_distance = self._previous_distance.get(device_duid)
        last_time = self._last_distance_time.get(device_duid, 0)
        current_time = time.time()

        # Store current reading for next iteration
        self._previous_distance[device_duid] = current_distance
        self._last_distance_time[device_duid] = current_time

        # Need previous reading to detect changes
        if previous_distance is None:
            return

        # Calculate change
        distance_change = current_distance - previous_distance
        time_delta = current_time - last_time

        # Time-based filtering moved to event detection conditions below
        # This allows us to always update previous_distance for the next comparison

        # Initialize thresholds if not present
        if device_duid not in self._pump_thresholds:
            self._pump_thresholds[device_duid] = {
                "pump_on_distance": None,
                "pump_off_distance": None,
                "on_event_count": 0,
                "off_event_count": 0,
                "last_on_event": None,
                "last_off_event": None,
            }

        thresholds = self._pump_thresholds[device_duid]

        # Detect PUMP ON event: water distance drops significantly (basin filling)
        # Water gets closer to sensor = distance decreases
        # Use 100mm (4 inch) threshold - real pump events show 5+ inch changes
        # IMPORTANT: Only detect rapid changes to avoid slow drift over long polling intervals
        # Real pump events happen quickly (basin fills in seconds/minutes, not hours)
        if distance_change < -100 and 5 <= time_delta <= 600:  # 100mm drop in 5s-10min window
            old_on = thresholds.get("pump_on_distance")
            if old_on is None:
                new_on = int(current_distance)
                _LOGGER.info("Device %s: Detected first pump ON event at %d mm (dropped %d mm)",
                            device_duid, new_on, int(abs(distance_change)))
            else:
                # Weighted average: 80% old, 20% new
                new_on = int(0.8 * old_on + 0.2 * current_distance)
                _LOGGER.info("Device %s: Pump ON event detected (dropped %d mm), updating threshold %d → %d mm",
                            device_duid, int(abs(distance_change)), old_on, new_on)

            thresholds["pump_on_distance"] = new_on
            thresholds["on_event_count"] = thresholds.get("on_event_count", 0) + 1
            thresholds["last_on_event"] = current_time

        # Detect PUMP OFF event: water distance jumps significantly (pump drained basin)
        # Water gets farther from sensor = distance increases
        # Use 100mm (4 inch) threshold - real pump events show 5+ inch changes
        # IMPORTANT: Only detect rapid changes to avoid slow drift over long polling intervals
        # Real pump events happen quickly (pump drains basin in seconds/minutes, not hours)
        elif distance_change > 100 and 5 <= time_delta <= 600:  # 100mm jump in 5s-10min window
            old_off = thresholds.get("pump_off_distance")
            if old_off is None:
                new_off = int(current_distance)
                _LOGGER.info("Device %s: Detected first pump OFF event at %d mm (jumped %d mm)",
                            device_duid, new_off, int(distance_change))
            else:
                # Weighted average: 80% old, 20% new
                new_off = int(0.8 * old_off + 0.2 * current_distance)
                _LOGGER.info("Device %s: Pump OFF event detected (jumped %d mm), updating threshold %d → %d mm",
                            device_duid, int(distance_change), old_off, new_off)

            thresholds["pump_off_distance"] = new_off
            thresholds["off_event_count"] = thresholds.get("off_event_count", 0) + 1
            thresholds["last_off_event"] = current_time

    def _calculate_pump_thresholds(self, device_duid: str) -> dict:
        """Return pump on/off distance thresholds from persistent event detection.

        PERSISTENT APPROACH:
        Uses event-based detection to learn pump thresholds over time:
        - Detects significant water distance drops (pump ON) and jumps (pump OFF)
        - Stores thresholds persistently with weighted averaging
        - Works across days/weeks between pump cycles
        - Falls back to simple min/max if no events detected yet

        Args:
            device_duid: Device UUID

        Returns:
            Dictionary with pump_on_distance, pump_off_distance, and observation count
        """
        # Try persistent thresholds first
        if device_duid in self._pump_thresholds:
            thresholds = self._pump_thresholds[device_duid]
            pump_on = thresholds.get("pump_on_distance")
            pump_off = thresholds.get("pump_off_distance")

            if pump_on is not None and pump_off is not None and pump_off > pump_on:
                return {
                    "pump_on_distance": pump_on,
                    "pump_off_distance": pump_off,
                    "observation_count": thresholds.get("on_event_count", 0) + thresholds.get("off_event_count", 0),
                    "on_event_count": thresholds.get("on_event_count", 0),
                    "off_event_count": thresholds.get("off_event_count", 0),
                }

        # Fallback: use simple min/max from recent history
        history = self._water_distance_history.get(device_duid, [])

        if not history or len(history) < 5:
            return {}

        pump_on_distance = min(history)
        pump_off_distance = max(history)

        # Need meaningful difference
        if pump_off_distance - pump_on_distance < 10:
            return {}

        return {
            "pump_on_distance": int(pump_on_distance),
            "pump_off_distance": int(pump_off_distance),
            "observation_count": len(history),
            "on_event_count": 0,
            "off_event_count": 0,
        }

    async def disconnect_mqtt(self):
        """Disconnect all MQTT clients."""
        for device_duid, mqtt_client in self.mqtt_clients.items():
            try:
                await mqtt_client.disconnect()
                _LOGGER.info("Disconnected MQTT for device %s", device_duid)
            except Exception as err:
                _LOGGER.error("Error disconnecting MQTT for device %s: %s", device_duid, err)
        self.mqtt_clients.clear()
