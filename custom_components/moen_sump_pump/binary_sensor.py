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
        location_name = device_data.get("locationName")

        # Build device name with location if available
        base_name = device_info.get("nickname", f"Sump Pump {device_duid[:8]}")
        if location_name:
            device_name = f"{location_name} {base_name}"
        else:
            device_name = base_name

        # Connectivity Sensor
        entities.append(
            MoenFloNABConnectivitySensor(coordinator, device_duid, device_name)
        )

        # Flood Risk Sensor
        entities.append(MoenFloNABFloodRiskSensor(coordinator, device_duid, device_name))

        # Power Status Sensor
        entities.append(MoenFloNABPowerSensor(coordinator, device_duid, device_name))

        # Water Detection Sensor (remote sensing cable)
        entities.append(MoenFloNABWaterDetectionSensor(coordinator, device_duid, device_name))

        # Critical Alerts Sensor
        entities.append(MoenFloNABCriticalAlertSensor(coordinator, device_duid, device_name))

        # Warning Alerts Sensor
        entities.append(MoenFloNABWarningAlertSensor(coordinator, device_duid, device_name))

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
        return {
            "identifiers": {(DOMAIN, self.device_duid)},
            "name": self.device_name,
            "manufacturer": "Moen",
            "model": "Moen Smart Sump Pump Monitor",
            "sw_version": info.get("firmwareVersion"),
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
        """Return true if there is a flood risk.

        This sensor triggers when:
        - droplet.floodRisk is set to a value other than "unknown"
        - ANY active alert exists (pump failures, water detection, etc.)

        Alert examples: 258=Primary Pump Failed, 260=Backup Pump Failed,
                       250=Water Detected, 254=Critical Flood
        """
        info = self.device_data.get("info", {})
        droplet = info.get("droplet", {})

        # Check droplet flood risk status
        flood_risk = droplet.get("floodRisk")
        if flood_risk and flood_risk != "unknown":
            return True

        # Check for ANY active alerts
        alerts = info.get("alerts")
        if isinstance(alerts, dict):
            for alert_id, alert_data in alerts.items():
                if isinstance(alert_data, dict):
                    state = alert_data.get("state", "")
                    # Alert is active if state contains "active" and NOT "inactive"
                    if "active" in state and "inactive" not in state:
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
        alerts = info.get("alerts")
        if isinstance(alerts, dict):
            active_alert_ids = [
                aid for aid, alert in alerts.items()
                if isinstance(alert, dict) and "active" in alert.get("state", "")
            ]
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


class MoenFloNABWaterDetectionSensor(MoenFloNABBinarySensorBase):
    """Water detection binary sensor (remote sensing cable)."""

    _attr_device_class = BinarySensorDeviceClass.MOISTURE

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_water_detection"
        self._attr_name = f"{device_name} Water Detection"

    @property
    def is_on(self) -> bool:
        """Return true if water is detected by remote sensing cable.

        Event ID 250 = Water Detected (critical)
        Event ID 252 = Water Was Detected (warning - no longer detected)
        """
        event_logs = self.device_data.get("event_logs", {})
        events = event_logs.get("events", [])

        if not events:
            return False

        # Check most recent water detection events
        for event in events:
            event_id = str(event.get("id", ""))

            # Event 250 = Water currently detected
            if event_id == "250":
                return True

            # Event 252 = Water was detected (cleared)
            # If we see this before 250, water is no longer detected
            if event_id == "252":
                return False

        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        event_logs = self.device_data.get("event_logs", {})
        events = event_logs.get("events", [])

        if not events:
            return {}

        # Find the most recent water detection event (250 or 252)
        for event in events:
            event_id = str(event.get("id", ""))
            if event_id in ["250", "252"]:
                return {
                    "event_id": event.get("id"),
                    "event_title": event.get("title"),
                    "event_severity": event.get("severity"),
                    "event_time": event.get("time"),
                    "event_details": event.get("text"),
                }

        return {}


class MoenFloNABCriticalAlertSensor(MoenFloNABBinarySensorBase):
    """Binary sensor for critical severity alerts."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_critical_alerts"
        self._attr_name = f"{device_name} Critical Alerts"

    @property
    def is_on(self) -> bool:
        """Return true if there are any active critical alerts."""
        info = self.device_data.get("info", {})
        alerts = info.get("alerts", {})

        if not alerts:
            return False

        for alert_id, alert_data in alerts.items():
            state = alert_data.get("state", "")
            # Check if alert is active (not inactive)
            if "active" in state and "inactive" not in state:
                # Get severity directly from alert (v2 API provides this)
                severity = alert_data.get("severity", "").lower()

                # Fallback to notification metadata if severity not in alert
                if not severity:
                    notification_metadata = self.device_data.get("notification_metadata", {})
                    if alert_id in notification_metadata:
                        severity = notification_metadata[alert_id].get("severity", "").lower()

                if severity == "critical":
                    return True

        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        info = self.device_data.get("info", {})
        alerts = info.get("alerts", {})
        notification_metadata = self.device_data.get("notification_metadata", {})

        critical_alerts = []

        for alert_id, alert_data in alerts.items():
            state = alert_data.get("state", "")
            if "active" in state and "inactive" not in state:
                # Get severity directly from alert (v2 API)
                severity = alert_data.get("severity", "").lower()
                title = alert_data.get("title")

                # Fallback to notification metadata
                if not severity and alert_id in notification_metadata:
                    severity = notification_metadata[alert_id].get("severity", "").lower()
                if not title and alert_id in notification_metadata:
                    title = notification_metadata[alert_id].get("title", f"Alert {alert_id}")

                if severity == "critical":
                    critical_alerts.append({
                        "id": alert_id,
                        "description": title or f"Alert {alert_id}",
                        "timestamp": alert_data.get("timestamp"),
                        "state": state,
                        "severity": severity,
                    })

        attrs = {
            "critical_alert_count": len(critical_alerts),
        }

        if critical_alerts:
            attrs["critical_alerts"] = critical_alerts

        return attrs


class MoenFloNABWarningAlertSensor(MoenFloNABBinarySensorBase):
    """Binary sensor for warning severity alerts."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_warning_alerts"
        self._attr_name = f"{device_name} Warning Alerts"

    @property
    def is_on(self) -> bool:
        """Return true if there are any active warning alerts."""
        info = self.device_data.get("info", {})
        alerts = info.get("alerts", {})

        if not alerts:
            return False

        for alert_id, alert_data in alerts.items():
            state = alert_data.get("state", "")
            # Check if alert is active (not inactive)
            if "active" in state and "inactive" not in state:
                # Get severity directly from alert (v2 API provides this)
                severity = alert_data.get("severity", "").lower()

                # Fallback to notification metadata if severity not in alert
                if not severity:
                    notification_metadata = self.device_data.get("notification_metadata", {})
                    if alert_id in notification_metadata:
                        severity = notification_metadata[alert_id].get("severity", "").lower()

                if severity == "warning":
                    return True

        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        info = self.device_data.get("info", {})
        alerts = info.get("alerts", {})
        notification_metadata = self.device_data.get("notification_metadata", {})

        warning_alerts = []

        for alert_id, alert_data in alerts.items():
            state = alert_data.get("state", "")
            if "active" in state and "inactive" not in state:
                # Get severity directly from alert (v2 API)
                severity = alert_data.get("severity", "").lower()
                title = alert_data.get("title")

                # Fallback to notification metadata
                if not severity and alert_id in notification_metadata:
                    severity = notification_metadata[alert_id].get("severity", "").lower()
                if not title and alert_id in notification_metadata:
                    title = notification_metadata[alert_id].get("title", f"Alert {alert_id}")

                if severity == "warning":
                    warning_alerts.append({
                        "id": alert_id,
                        "description": title or f"Alert {alert_id}",
                        "timestamp": alert_data.get("timestamp"),
                        "state": state,
                        "severity": severity,
                    })

        attrs = {
            "warning_alert_count": len(warning_alerts),
        }

        if warning_alerts:
            attrs["warning_alerts"] = warning_alerts

        return attrs
