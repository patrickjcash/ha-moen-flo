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

from .api import MoenFloNABClient, MoenFloNABApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
SCAN_INTERVAL = timedelta(minutes=5)


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
        hass.data[DOMAIN].pop(entry.entry_id)

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

                # Trigger device to take fresh sensor readings and update shadow
                try:
                    await self.client.update_shadow(client_id, "sens_on")
                    # Wait for device to respond with fresh readings
                    await asyncio.sleep(3)
                except Exception as err:
                    _LOGGER.warning(
                        "Failed to trigger shadow update for device %s: %s",
                        device_duid,
                        err,
                    )

                # Get live telemetry from device shadow
                try:
                    shadow_data = await self.client.get_shadow(client_id)
                    # Extract state.reported which contains live sensor data
                    if isinstance(shadow_data, dict) and "state" in shadow_data:
                        reported = shadow_data.get("state", {}).get("reported", {})
                        if reported:
                            # Merge shadow data into device info
                            # Shadow data takes precedence for these fields
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
                                "Updated device %s with live shadow data (water level: %s mm)",
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

                # Get pump cycle history using numeric ID (NEW!)
                try:
                    cycles = await self.client.get_pump_cycles(client_id, limit=10)
                    device_data["pump_cycles"] = cycles
                except Exception as err:
                    _LOGGER.warning(
                        "Failed to get pump cycles for device %s: %s", device_duid, err
                    )
                    device_data["pump_cycles"] = []

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

            return data

        except MoenFloNABApiError as err:
            raise UpdateFailed(f"Error communicating with API: {err}")
