"""Update platform for Moen Flo NAB."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
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
    """Set up Moen Flo NAB update entities."""
    coordinator: MoenFloNABDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for device_duid, device_data in coordinator.data.items():
        device_info = device_data.get("info", {})
        location_name = device_data.get("locationName")
        base_name = device_info.get("nickname", f"Sump Pump {device_duid[:8]}")
        device_name = f"{location_name} {base_name}" if location_name else base_name
        entities.append(MoenFloNABFirmwareUpdate(coordinator, device_duid, device_name))

    async_add_entities(entities)


class MoenFloNABFirmwareUpdate(CoordinatorEntity, UpdateEntity):
    """Firmware update entity for Moen Flo NAB devices."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_supported_features = UpdateEntityFeature(0)
    _attr_title = "Moen Sump Pump Firmware"

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the update entity."""
        super().__init__(coordinator)
        self.device_duid = device_duid
        self.device_name = device_name
        self._attr_unique_id = f"{device_duid}_firmware_update"
        self._attr_name = f"{device_name} Firmware"

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

    @property
    def installed_version(self) -> str | None:
        """Return the currently installed firmware version."""
        info = self.device_data.get("info", {})
        return info.get("firmwareVersion")

    @property
    def latest_version(self) -> str | None:
        """Return the latest available firmware version."""
        firmware_info = self.device_data.get("firmware_info", {})
        return firmware_info.get("latest")

    @property
    def in_progress(self) -> bool:
        """Return whether an update is in progress."""
        return False
