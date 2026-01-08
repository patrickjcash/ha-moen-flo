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

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
SCAN_INTERVAL = timedelta(minutes=5)
SCAN_INTERVAL_ALERT = timedelta(seconds=30)  # Fast polling during alerts
SCAN_INTERVAL_CRITICAL = timedelta(seconds=10)  # Very fast during critical alerts


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
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        self.devices = {}
        self.mqtt_clients = {}  # Store MQTT clients per device
        self._last_alert_state = {}  # Track alert states for adaptive polling
        self._first_refresh = True  # Track if this is the first data fetch

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            # Get list of devices
            devices_list = await self.client.get_devices()

            data = {}

            for device in devices_list:
                device_duid = device.get("duid")
                client_id = device.get("clientId")

                if not device_duid or not client_id:
                    _LOGGER.warning("Device missing duid or clientId: %s", device)
                    continue

                # Store both IDs for future use
                device_data = {
                    "duid": device_duid,
                    "clientId": client_id,
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

                # Get live telemetry via MQTT or REST fallback
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
                            _LOGGER.debug(
                                "Updated device %s with MQTT shadow data (water level: %s mm)",
                                device_duid,
                                reported.get("crockTofDistance"),
                            )
                        else:
                            _LOGGER.warning("No shadow data received from MQTT for device %s", device_duid)
                    else:
                        # REST fallback
                        _LOGGER.debug("Using REST API fallback for device %s", device_duid)
                        await self.client.update_shadow(client_id, "sens_on")
                        await asyncio.sleep(0.5)
                        shadow_data = await self.client.get_shadow(client_id)
                        # Stop streaming to preserve battery
                        await self.client.update_shadow(client_id, "updates_off")
                        if isinstance(shadow_data, dict) and "state" in shadow_data:
                            reported = shadow_data.get("state", {}).get("reported", {})
                            if reported:
                                device_data["info"]["crockTofDistance"] = reported.get("crockTofDistance")
                                device_data["info"]["droplet"] = reported.get("droplet")
                                device_data["info"]["connected"] = reported.get("connected")
                                device_data["info"]["wifiRssi"] = reported.get("wifiRssi")
                                device_data["info"]["batteryPercentage"] = reported.get("batteryPercentage")
                                device_data["info"]["powerSource"] = reported.get("powerSource")
                                device_data["info"]["alerts"] = reported.get("alerts")
                                _LOGGER.debug(
                                    "Updated device %s with REST shadow data (water level: %s mm)",
                                    device_duid,
                                    reported.get("crockTofDistance"),
                                )
                except Exception as err:
                    _LOGGER.warning(
                        "Failed to get shadow data for device %s: %s", device_duid, err
                    )

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

                    # Calculate pump thresholds from cycle history
                    device_data["pump_thresholds"] = self._calculate_pump_thresholds(cycles)

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
                    device_data["pump_thresholds"] = {}

                # Get last pump cycle from logs using UUID
                try:
                    last_cycle = await self.client.get_last_pump_cycle(device_duid)
                    device_data["last_cycle"] = last_cycle
                except Exception as err:
                    _LOGGER.warning(
                        "Failed to get last cycle for device %s: %s", device_duid, err
                    )
                    device_data["last_cycle"] = None

                # Get event logs for water detection using UUID
                try:
                    events = await self.client.get_device_logs(device_duid, limit=50)
                    device_data["event_logs"] = {"events": events}
                except Exception as err:
                    _LOGGER.warning(
                        "Failed to get event logs for device %s: %s", device_duid, err
                    )
                    device_data["event_logs"] = {"events": []}

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
        """Update polling interval based on device alert state.

        Normal: 5 minutes
        Alert (pump failures): 30 seconds
        Critical (high flood risk): 10 seconds
        """
        alerts = device_data.get("info", {}).get("alerts", [])
        droplet = device_data.get("info", {}).get("droplet", {})
        flood_risk = droplet.get("floodRisk") if droplet else None

        # Determine alert level
        has_critical_alert = flood_risk in ["high", "moderate"]
        has_alert = len(alerts) > 0 or flood_risk in ["caution"]

        current_state = "critical" if has_critical_alert else ("alert" if has_alert else "normal")
        previous_state = self._last_alert_state.get(device_duid, "normal")

        # Only update if state changed
        if current_state != previous_state:
            if current_state == "critical":
                self.update_interval = SCAN_INTERVAL_CRITICAL
                _LOGGER.info("Device %s in CRITICAL state, polling every %s seconds", device_duid, SCAN_INTERVAL_CRITICAL.seconds)
            elif current_state == "alert":
                self.update_interval = SCAN_INTERVAL_ALERT
                _LOGGER.info("Device %s has alerts, polling every %s seconds", device_duid, SCAN_INTERVAL_ALERT.seconds)
            else:
                self.update_interval = SCAN_INTERVAL
                _LOGGER.info("Device %s normal, polling every %s minutes", device_duid, SCAN_INTERVAL.seconds / 60)

            self._last_alert_state[device_duid] = current_state

    def _calculate_pump_thresholds(self, pump_cycles: list) -> dict:
        """Calculate pump on/off distance thresholds from pump cycle history.

        Analyzes recent pump cycles to determine:
        - pump_on_distance: Distance when pump starts (basin full) - estimated from basin diameter
        - pump_off_distance: Distance when pump stops (basin empty) - estimated from basin diameter + volume

        SIMPLE HEURISTIC APPROACH:
        Since pump cycle data doesn't include ToF distance readings, we use a simple geometric
        calculation based on basin diameter and pump volumes:

        1. Typical sump basin is 18" (457mm) diameter cylinder
        2. pump_on_distance: When basin is nearly full (estimated at ~50mm from sensor)
        3. pump_off_distance: Calculated from volume pumped out + basin geometry

        Formula: height_change (mm) = volume (gallons) * 3785.41 / (π * (diameter/2)^2)

        Args:
            pump_cycles: List of pump cycle dictionaries from API

        Returns:
            Dictionary with pump_on_distance, pump_off_distance, and calibration_cycles
        """
        if not pump_cycles or len(pump_cycles) == 0:
            return {}

        # Get average pump volume from recent cycles
        recent_cycles = pump_cycles[:10]  # Last 10 cycles
        volumes = [c.get("emptyVolume", 0) for c in recent_cycles if c.get("emptyVolume", 0) > 0]

        if not volumes:
            _LOGGER.debug("No valid pump volumes found in cycle data")
            return {}

        avg_volume_gallons = sum(volumes) / len(volumes)

        # Typical sump basin diameter: 18 inches = 457mm
        # This is a reasonable assumption for most residential sump pits
        basin_diameter_mm = 457
        basin_radius_mm = basin_diameter_mm / 2

        # Calculate basin cross-sectional area in mm²
        import math
        basin_area_mm2 = math.pi * (basin_radius_mm ** 2)

        # Convert volume from gallons to mm³
        volume_mm3 = avg_volume_gallons * 3785410  # 1 gallon = 3,785,410 mm³

        # Calculate height change in mm
        height_change_mm = volume_mm3 / basin_area_mm2

        # Assume pump starts when water is ~50mm from sensor (basin nearly full)
        # This is a typical distance for sump pumps to activate
        pump_on_distance = 50

        # pump_off_distance is when basin is empty after pumping out water
        pump_off_distance = pump_on_distance + height_change_mm

        _LOGGER.debug(
            "Calculated pump thresholds: ON=%d mm, OFF=%d mm (avg volume=%.1f gal, height change=%.1f mm)",
            pump_on_distance,
            pump_off_distance,
            avg_volume_gallons,
            height_change_mm,
        )

        return {
            "pump_on_distance": int(pump_on_distance),
            "pump_off_distance": int(pump_off_distance),
            "calibration_cycles": len(recent_cycles),
            "avg_cycle_volume_gallons": round(avg_volume_gallons, 1),
            "calculated_height_change_mm": round(height_change_mm, 1),
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
