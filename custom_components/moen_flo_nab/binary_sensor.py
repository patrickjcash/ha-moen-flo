"""Binary sensor platform for Moen Flo NAB."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
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
    """Set up Moen Flo NAB binary sensors."""
    coordinator: MoenFloNABDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []

    for device_duid, device_data in coordinator.data.items():
        device_info = device_data.get("info", {})
        device_name = device_info.get("nickname", f"Sump Pump {device_duid[:8]}")

        # Connectivity Sensor
        entities.append(
            MoenFloNABConnectivitySensor(coordinator, device_duid, device_name)
        )

        # Flood Risk Sensor
        entities.append(MoenFloNABFloodRiskSensor(coordinator, device_duid, device_name))

        # Power Status Sensor
        entities.append(MoenFloNABPowerSensor(coordinator, device_duid, device_name))

    async_add_entities(entities)


class MoenFloNABBinarySensorBase(CoordinatorEntity, BinarySensorEntity):
    """Base class for Moen Flo NAB binary sensors."""

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the binary sensor."""
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
        # Try both firmware version field names from API
        fw_version = info.get("fwVersion") or info.get("firmwareVersion") or info.get("deviceFirmware")
        return {
            "identifiers": {(DOMAIN, self.device_duid)},
            "name": self.device_name,
            "manufacturer": "Moen",
            "model": "Flo NAB Sump Pump Monitor",
            "sw_version": fw_version if fw_version else None,
        }


class MoenFloNABConnectivitySensor(MoenFloNABBinarySensorBase):
    """Device connectivity binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_connectivity"
        self._attr_name = f"{device_name} Connectivity"

    @property
    def is_on(self) -> bool:
        """Return true if device is connected."""
        info = self.device_data.get("info", {})
        # Device is connected based on "connected" field
        return info.get("connected", False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        info = self.device_data.get("info", {})
        return {
            "wifi_rssi": info.get("wifiRssi"),
            "wifi_network": info.get("wifiNetwork"),
            "last_connect": info.get("lastConnect"),
            "firmware_version": info.get("firmwareVersion"),
        }


class MoenFloNABFloodRiskSensor(MoenFloNABBinarySensorBase):
    """Flood risk binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_flood_risk"
        self._attr_name = f"{device_name} Flood Risk"

    @property
    def is_on(self) -> bool:
        """Return true if there is a flood risk."""
        info = self.device_data.get("info", {})
        droplet = info.get("droplet", {})
        
        # Check droplet flood risk status
        flood_risk = droplet.get("floodRisk")
        if flood_risk and flood_risk != "unknown":
            return True
        
        # Check for active flood-related alerts
        alerts = info.get("alerts", {})
        for alert_id, alert_data in alerts.items():
            state = alert_data.get("state", "")
            if "active" in state:
                # Alert IDs: 254=Critical Flood, 256=High Flood, 258=Flood Risk
                if alert_id in ["254", "256", "258"]:
                    return True
        
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        info = self.device_data.get("info", {})
        droplet = info.get("droplet", {})
        
        attrs = {
            "water_level_mm": info.get("crockTofDistance"),
            "water_trend": droplet.get("trend"),  # rising/stable/receding
            "flood_risk_level": droplet.get("floodRisk"),
            "primary_pump_state": droplet.get("primaryState"),
            "backup_pump_state": droplet.get("backupState"),
        }
        
        # Add active alert IDs
        alerts = info.get("alerts", {})
        active_alert_ids = [aid for aid, alert in alerts.items() if "active" in alert.get("state", "")]
        if active_alert_ids:
            attrs["active_alert_ids"] = active_alert_ids
        
        return {k: v for k, v in attrs.items() if v is not None}


class MoenFloNABPowerSensor(MoenFloNABBinarySensorBase):
    """Power status binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.POWER
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_power"
        self._attr_name = f"{device_name} AC Power"

    @property
    def is_on(self) -> bool:
        """Return true if AC power is available."""
        info = self.device_data.get("info", {})
        # Device is on AC power if powerSource is "ac"
        return info.get("powerSource") == "ac"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        info = self.device_data.get("info", {})
        return {
            "power_source": info.get("powerSource"),
            "battery_percentage": info.get("batteryPercentage"),
            "battery_life_remaining": info.get("batteryLifeRemaining"),
        }
