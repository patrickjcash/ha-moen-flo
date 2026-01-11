"""Button platform for Moen Flo NAB."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MoenFloNABDataUpdateCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Moen Flo NAB button entities."""
    coordinator: MoenFloNABDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    for device_duid, device_data in coordinator.data.items():
        device_info = device_data.get("info", {})
        location_name = device_data.get("locationName")

        # Build device name with location if available
        base_name = device_info.get("nickname", f"Sump Pump {device_duid[:8]}")
        if location_name:
            device_name = f"{location_name} {base_name}"
        else:
            device_name = base_name

        # Dismiss All Notifications Button
        entities.append(
            MoenFloNABDismissNotificationsButton(coordinator, device_duid, device_name)
        )

    async_add_entities(entities)


class MoenFloNABButtonBase(CoordinatorEntity, ButtonEntity):
    """Base class for Moen Flo NAB buttons."""

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.device_duid = device_duid
        self.device_name = device_name

    @property
    def device_data(self) -> dict[str, Any]:
        """Get device data from coordinator."""
        return self.coordinator.data.get(self.device_duid, {})

    @property
    def device_info(self):
        """Return device info."""
        info = self.device_data.get("info", {})
        return {
            "identifiers": {(DOMAIN, self.device_duid)},
            "name": self.device_name,
            "manufacturer": "Moen",
            "model": "Moen Smart Sump Pump Monitor",
            "sw_version": info.get("firmwareVersion"),
        }


class MoenFloNABDismissNotificationsButton(MoenFloNABButtonBase):
    """Button to dismiss all active notifications."""

    _attr_icon = "mdi:bell-cancel"

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_dismiss_notifications"
        self._attr_name = f"{device_name} Dismiss All Notifications"

    async def async_press(self) -> None:
        """Handle button press to dismiss all active notifications."""
        client_id = self.device_data.get("clientId")

        if not client_id:
            _LOGGER.error("No client ID found for device %s", self.device_duid)
            return

        _LOGGER.info("Dismissing all active notifications for device %s", self.device_duid)

        try:
            # Call the API to dismiss all alerts
            results = await self.coordinator.client.dismiss_all_alerts(client_id)

            if results:
                dismissed_count = sum(1 for success in results.values() if success)
                total_count = len(results)
                _LOGGER.info(
                    "Dismissed %d of %d active notifications for device %s",
                    dismissed_count,
                    total_count,
                    self.device_duid,
                )

                # Refresh coordinator data to update sensors
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.info("No active notifications to dismiss for device %s", self.device_duid)

        except Exception as err:
            _LOGGER.error("Failed to dismiss notifications: %s", err)
