"""Sensor platform for Moen Flo NAB."""
from __future__ import annotations

from datetime import datetime, timezone, date
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfLength,
    UnitOfTemperature,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MoenFloNABDataUpdateCoordinator
from .const import ALERT_CODES, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Moen Flo NAB sensors."""
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

        # Water Distance Sensor
        entities.append(
            MoenFloNABWaterDistanceSensor(coordinator, device_duid, device_name)
        )

        # Basin Fullness Sensor
        entities.append(
            MoenFloNABBasinFullnessSensor(coordinator, device_duid, device_name)
        )

        # Pump ON Distance Sensor (calculated)
        entities.append(
            MoenFloNABPumpOnDistanceSensor(coordinator, device_duid, device_name)
        )

        # Pump OFF Distance Sensor (calculated)
        entities.append(
            MoenFloNABPumpOffDistanceSensor(coordinator, device_duid, device_name)
        )

        # Temperature Sensor
        entities.append(
            MoenFloNABTemperatureSensor(coordinator, device_duid, device_name)
        )

        # Humidity Sensor
        entities.append(MoenFloNABHumiditySensor(coordinator, device_duid, device_name))

        # Pump Capacity Sensor
        entities.append(
            MoenFloNABPumpCapacitySensor(coordinator, device_duid, device_name)
        )

        # Last Cycle Sensor
        entities.append(MoenFloNABLastCycleSensor(coordinator, device_duid, device_name))

        # Diagnostic Sensors
        entities.append(MoenFloNABBatterySensor(coordinator, device_duid, device_name))
        entities.append(MoenFloNABWiFiSignalSensor(coordinator, device_duid, device_name))
        entities.append(MoenFloNABPollingPeriodSensor(coordinator, device_duid, device_name))
        entities.append(MoenFloNABPumpCyclesLast15MinSensor(coordinator, device_duid, device_name))

        # Alert Sensor
        entities.append(MoenFloNABLastAlertSensor(coordinator, device_duid, device_name))

        # Pump Configuration Diagnostic Sensors
        entities.append(MoenFloNABPrimaryPumpManufacturerSensor(coordinator, device_duid, device_name))
        entities.append(MoenFloNABPrimaryPumpModelSensor(coordinator, device_duid, device_name))
        entities.append(MoenFloNABPrimaryPumpInstallDateSensor(coordinator, device_duid, device_name))
        entities.append(MoenFloNABBasinDiameterSensor(coordinator, device_duid, device_name))
        entities.append(MoenFloNABBackupPumpManufacturerSensor(coordinator, device_duid, device_name))
        entities.append(MoenFloNABBackupPumpModelSensor(coordinator, device_duid, device_name))
        entities.append(MoenFloNABBackupPumpInstallDateSensor(coordinator, device_duid, device_name))
        entities.append(MoenFloNABBackupPumpTestFrequencySensor(coordinator, device_duid, device_name))
        entities.append(MoenFloNABBackupPumpBatteryWaterSensor(coordinator, device_duid, device_name))
        entities.append(MoenFloNABBackupPumpInstalledSensor(coordinator, device_duid, device_name))

    async_add_entities(entities)


class MoenFloNABSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Moen Flo NAB sensors."""

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
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


class MoenFloNABWaterDistanceSensor(MoenFloNABSensorBase):
    """Water distance sensor - distance from sensor to water surface."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfLength.MILLIMETERS
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:arrow-expand-vertical"

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_water_distance"
        self._attr_name = f"{device_name} Water Distance"

    @property
    def native_value(self) -> float | None:
        """Return the water distance in mm.

        crockTofDistance is in millimeters (282mm = 28.2cm).
        Lower value = water closer to sensor (basin fuller).
        Higher value = water farther from sensor (basin emptier).
        """
        info = self.device_data.get("info", {})
        distance = info.get("crockTofDistance")
        if distance is not None:
            try:
                return round(float(distance), 1)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        info = self.device_data.get("info", {})
        droplet = info.get("droplet", {})
        pump_info = info.get("pumpInfo", {})
        main_pump = pump_info.get("main", {})

        # Get pump thresholds from coordinator
        pump_thresholds = self.device_data.get("pump_thresholds", {})

        attrs = {
            "distance_cm": round(float(info.get("crockTofDistance", 0)) / 10, 1) if info.get("crockTofDistance") else None,
            "water_trend": droplet.get("trend"),  # rising/stable/receding
            "flood_risk": droplet.get("floodRisk"),
            "basin_diameter_inches": main_pump.get("crockDiameter"),
            "basin_diameter_mm": info.get("crockDiameterMM"),
            "pump_on_distance": pump_thresholds.get("pump_on_distance"),
            "pump_off_distance": pump_thresholds.get("pump_off_distance"),
        }

        return {k: v for k, v in attrs.items() if v is not None}


class MoenFloNABBasinFullnessSensor(MoenFloNABSensorBase):
    """Basin fullness sensor - percentage full based on pump cycle thresholds."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:hydraulic-oil-level"

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_basin_fullness"
        self._attr_name = f"{device_name} Basin Fullness"

    @property
    def native_value(self) -> float | None:
        """Return the basin fullness percentage.

        100% = pump on distance (basin full, pump about to start)
        0% = pump off distance (basin empty, pump just finished)

        Formula: 100 - ((current - pump_on) / (pump_off - pump_on) * 100)
        """
        info = self.device_data.get("info", {})
        pump_thresholds = self.device_data.get("pump_thresholds", {})

        current_distance = info.get("crockTofDistance")
        pump_on_distance = pump_thresholds.get("pump_on_distance")
        pump_off_distance = pump_thresholds.get("pump_off_distance")

        # Need all three values to calculate
        if current_distance is None or pump_on_distance is None or pump_off_distance is None:
            return None

        # Avoid division by zero
        if pump_off_distance == pump_on_distance:
            return None

        try:
            # Calculate fullness percentage
            # Inverted because lower distance = fuller basin
            fullness = 100 - ((float(current_distance) - float(pump_on_distance)) /
                             (float(pump_off_distance) - float(pump_on_distance)) * 100)

            # Clamp to 0-100 range
            return max(0, min(100, round(fullness, 0)))
        except (ValueError, TypeError, ZeroDivisionError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        info = self.device_data.get("info", {})
        pump_thresholds = self.device_data.get("pump_thresholds", {})

        attrs = {
            "current_distance_mm": info.get("crockTofDistance"),
            "pump_on_distance_mm": pump_thresholds.get("pump_on_distance"),
            "pump_off_distance_mm": pump_thresholds.get("pump_off_distance"),
            "observation_count": pump_thresholds.get("observation_count", 0),
        }

        return {k: v for k, v in attrs.items() if v is not None}


class MoenFloNABPumpOnDistanceSensor(MoenFloNABSensorBase):
    """Pump ON distance sensor - calculated from detected pump events."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfLength.MILLIMETERS
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:gauge-full"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_pump_on_distance"
        self._attr_name = f"{device_name} Pump ON Distance (Calculated)"

    @property
    def native_value(self) -> int | None:
        """Return the pump ON distance threshold in mm.

        This is the water distance when the basin is full and pump starts.
        Lower distance = closer to sensor = fuller basin.
        """
        pump_thresholds = self.device_data.get("pump_thresholds", {})
        return pump_thresholds.get("pump_on_distance")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        from datetime import datetime

        pump_thresholds = self.device_data.get("pump_thresholds", {})

        attrs = {
            "event_count": pump_thresholds.get("cycle_count", 0),
            "calculation_method": "event_detection" if pump_thresholds.get("cycle_count", 0) > 0 else "min_max_fallback",
        }

        # Add last event timestamp if available
        last_event = pump_thresholds.get("last_cycle")
        if last_event:
            attrs["last_event"] = datetime.fromtimestamp(last_event).isoformat()

        return {k: v for k, v in attrs.items() if v is not None}


class MoenFloNABPumpOffDistanceSensor(MoenFloNABSensorBase):
    """Pump OFF distance sensor - calculated from detected pump events."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfLength.MILLIMETERS
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:gauge-empty"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_pump_off_distance"
        self._attr_name = f"{device_name} Pump OFF Distance (Calculated)"

    @property
    def native_value(self) -> int | None:
        """Return the pump OFF distance threshold in mm.

        This is the water distance when the basin is empty and pump stops.
        Higher distance = farther from sensor = emptier basin.
        """
        pump_thresholds = self.device_data.get("pump_thresholds", {})
        return pump_thresholds.get("pump_off_distance")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        from datetime import datetime

        pump_thresholds = self.device_data.get("pump_thresholds", {})

        attrs = {
            "event_count": pump_thresholds.get("cycle_count", 0),
            "calculation_method": "event_detection" if pump_thresholds.get("cycle_count", 0) > 0 else "min_max_fallback",
        }

        # Add last event timestamp if available
        last_event = pump_thresholds.get("last_cycle")
        if last_event:
            attrs["last_event"] = datetime.fromtimestamp(last_event).isoformat()

        return {k: v for k, v in attrs.items() if v is not None}


class MoenFloNABTemperatureSensor(MoenFloNABSensorBase):
    """Temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_temperature"
        self._attr_name = f"{device_name} Temperature"

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement based on API response.

        The API returns unitOfMeasure as "F" or "C" based on user's
        Moen app settings. We use this to report the correct unit to HA.
        """
        env_data = self.device_data.get("environment", {})
        temp_data = env_data.get("tempData", {})
        unit = temp_data.get("unitOfMeasure", "F")

        if unit == "C":
            return UnitOfTemperature.CELSIUS
        # Default to Fahrenheit for backwards compatibility
        return UnitOfTemperature.FAHRENHEIT

    @property
    def native_value(self) -> float | None:
        """Return the temperature from environment data."""
        env_data = self.device_data.get("environment", {})
        temp_data = env_data.get("tempData", {})
        temp = temp_data.get("current")
        if temp is not None:
            try:
                return round(float(temp), 1)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        env_data = self.device_data.get("environment", {})
        temp_data = env_data.get("tempData", {})

        return {
            "low_threshold": temp_data.get("tempLowThreshold"),
            "high_threshold": temp_data.get("tempHighThreshold"),
            "api_unit": temp_data.get("unitOfMeasure"),
        }


class MoenFloNABHumiditySensor(MoenFloNABSensorBase):
    """Humidity sensor."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_humidity"
        self._attr_name = f"{device_name} Humidity"

    @property
    def native_value(self) -> float | None:
        """Return the humidity from environment data."""
        env_data = self.device_data.get("environment", {})
        humid_data = env_data.get("humidData", {})
        humidity = humid_data.get("current")
        if humidity is not None:
            try:
                return round(float(humidity), 1)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        env_data = self.device_data.get("environment", {})
        humid_data = env_data.get("humidData", {})
        
        return {
            "low_threshold": humid_data.get("humidLowThreshold"),
            "high_threshold": humid_data.get("humidHighThreshold"),
            "unit": humid_data.get("unitOfMeasure"),
        }


class MoenFloNABPumpCapacitySensor(MoenFloNABSensorBase):
    """Pump daily capacity sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:pump"

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_pump_capacity"
        self._attr_name = f"{device_name} Daily Pump Capacity"

    @property
    def native_value(self) -> float | None:
        """Return the pump capacity percentage from TopTen data."""
        health_data = self.device_data.get("pump_health", {})
        
        # TopTen contains recent daily capacity usage
        if isinstance(health_data, dict) and "TopTen" in health_data:
            top_ten = health_data["TopTen"]
            if top_ten and len(top_ten) > 0:
                # Get the most recent day
                latest = top_ten[0]
                capacity = latest.get("capacity")
                if capacity is not None:
                    try:
                        return round(float(capacity), 1)
                    except (ValueError, TypeError):
                        return None
        
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        health_data = self.device_data.get("pump_health", {})
        
        attrs = {
            "capacity_sufficient": health_data.get("pumpCapacitySufficient"),
            "pump_indicator": health_data.get("pumpIndicator"),
            "pump_size": health_data.get("pumpSize"),
        }
        
        # Add latest day info if available
        if isinstance(health_data, dict) and "TopTen" in health_data:
            top_ten = health_data["TopTen"]
            if top_ten and len(top_ten) > 0:
                latest = top_ten[0]
                attrs["date"] = latest.get("day")
                attrs["warn_color"] = latest.get("warnColor")
        
        return {k: v for k, v in attrs.items() if v is not None}


class MoenFloNABLastCycleSensor(MoenFloNABSensorBase):
    """Last pump cycle sensor with detailed Water In/Out data."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:pump-off"

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_last_cycle"
        self._attr_name = f"{device_name} Last Pump Cycle"

    @property
    def native_value(self) -> datetime | None:
        """Return the last pump cycle time from pump session data.

        Uses pump_cycles data which contains actual pump run timestamps.
        Previously used event logs which could return any event type (not necessarily pump cycles).
        """
        cycles = self.device_data.get("pump_cycles", [])
        if cycles and len(cycles) > 0:
            latest = cycles[0]
            try:
                # Parse ISO timestamp
                date_str = latest.get("date", "")
                if date_str:
                    # Handle ISO format with Z suffix
                    if date_str.endswith('Z'):
                        date_str = date_str.replace('Z', '+00:00')
                    dt = datetime.fromisoformat(date_str)
                    return dt
            except (ValueError, TypeError):
                pass

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return comprehensive pump cycle data."""
        cycles = self.device_data.get("pump_cycles", [])
        
        if cycles and len(cycles) > 0:
            latest = cycles[0]
            
            # Calculate durations in human-readable format
            fill_time_sec = latest.get("fillTimeMS", 0) / 1000
            empty_time_sec = latest.get("emptyTimeMS", 0) / 1000
            
            fill_time_display = f"{int(fill_time_sec // 60)}min {int(fill_time_sec % 60)}sec" if fill_time_sec >= 60 else f"{int(fill_time_sec)}sec"
            empty_time_display = f"{int(empty_time_sec // 60)}min {int(empty_time_sec % 60)}sec" if empty_time_sec >= 60 else f"{int(empty_time_sec)}sec"
            
            attrs = {
                "water_in_rate": latest.get("fillVolume"),
                "water_in_units": latest.get("fillVolumeUnits"),
                "water_in_duration": fill_time_display,
                "water_out_volume": latest.get("emptyVolume"),
                "water_out_units": latest.get("emptyVolumeUnits"),
                "water_out_duration": empty_time_display,
                "backup_pump_ran": latest.get("backupRan"),
            }

            return {k: v for k, v in attrs.items() if v is not None}

        return {}


class MoenFloNABBatterySensor(MoenFloNABSensorBase):
    """Battery level diagnostic sensor."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_battery"
        self._attr_name = f"{device_name} Battery"

    @property
    def native_value(self) -> float | None:
        """Return the battery percentage."""
        info = self.device_data.get("info", {})
        battery = info.get("batteryPercentage")
        if battery is not None:
            try:
                return round(float(battery), 0)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        info = self.device_data.get("info", {})

        attrs = {
            "power_source": info.get("powerSource"),
            "battery_life_remaining": info.get("batteryLifeRemaining"),
        }

        return {k: v for k, v in attrs.items() if v is not None}


class MoenFloNABWiFiSignalSensor(MoenFloNABSensorBase):
    """WiFi signal strength diagnostic sensor."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:wifi"

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_wifi_signal"
        self._attr_name = f"{device_name} WiFi Signal"

    @property
    def native_value(self) -> int | None:
        """Return the WiFi RSSI in dBm."""
        info = self.device_data.get("info", {})
        rssi = info.get("wifiRssi")
        if rssi is not None:
            try:
                return int(rssi)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        info = self.device_data.get("info", {})

        attrs = {
            "wifi_network": info.get("wifiNetwork"),
            "mac_address": info.get("macAddress"),
        }

        return {k: v for k, v in attrs.items() if v is not None}


class MoenFloNABLastAlertSensor(MoenFloNABSensorBase):
    """Active alerts count sensor with all alert details in attributes."""

    _attr_icon = "mdi:alert-circle"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_last_alert"
        self._attr_name = f"{device_name} Active Alerts"

    @property
    def native_value(self) -> int:
        """Return the count of active alerts."""
        info = self.device_data.get("info", {})
        alerts = info.get("alerts", {})

        if not alerts:
            return 0

        # Count unacknowledged alerts (matches mobile app behavior)
        active_count = 0
        for alert_id, alert_data in alerts.items():
            state = alert_data.get("state", "")
            # Check if alert is unacknowledged (unlack) regardless of active/inactive
            if "unlack" in state:
                active_count += 1

        return active_count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return all active and recent alerts with timestamps."""
        info = self.device_data.get("info", {})
        alerts = info.get("alerts", {})

        if not alerts:
            return {}

        active_alerts = []
        inactive_alerts = []

        # Get dynamic notification metadata
        notification_metadata = self.device_data.get("notification_metadata", {})

        for alert_id, alert_data in alerts.items():
            state = alert_data.get("state", "")
            timestamp_str = alert_data.get("timestamp", "")

            # Use dynamic metadata if available, fallback to hardcoded
            if alert_id in notification_metadata:
                description = notification_metadata[alert_id].get("title", f"Alert {alert_id}")
                severity = notification_metadata[alert_id].get("severity", "unknown")
            else:
                description = ALERT_CODES.get(alert_id, f"Alert {alert_id}")
                severity = "unknown"

            alert_info = {
                "id": alert_id,
                "description": description,
                "severity": severity,
                "timestamp": timestamp_str,
                "state": state,
            }

            # Add args if present (some alerts have additional data)
            if "args" in alert_data:
                alert_info["args"] = alert_data["args"]

            # Categorize by acknowledged status (matches mobile app)
            # "unlack" = unacknowledged (shows in app notification list)
            # "lack" = acknowledged (dismissed, shows in history only)
            if "unlack" in state:
                active_alerts.append(alert_info)
            else:
                inactive_alerts.append(alert_info)

        # Sort by timestamp (most recent first)
        def get_timestamp(alert):
            try:
                return datetime.fromisoformat(
                    alert["timestamp"].replace("Z", "+00:00")
                )
            except (ValueError, KeyError):
                return datetime.min.replace(tzinfo=timezone.utc)

        active_alerts.sort(key=get_timestamp, reverse=True)
        inactive_alerts.sort(key=get_timestamp, reverse=True)

        attrs = {
            "active_alert_count": len(active_alerts),
            "total_alert_count": len(alerts),
        }

        if active_alerts:
            attrs["active_alerts"] = active_alerts

        # Include up to 5 most recent inactive alerts for context
        if inactive_alerts:
            attrs["recent_inactive_alerts"] = inactive_alerts[:5]

        return attrs


class MoenFloNABPrimaryPumpManufacturerSensor(MoenFloNABSensorBase):
    """Primary pump manufacturer diagnostic sensor."""

    _attr_icon = "mdi:factory"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_primary_pump_manufacturer"
        self._attr_name = f"{device_name} Primary Pump Manufacturer"

    @property
    def native_value(self) -> str | None:
        """Return the primary pump manufacturer."""
        info = self.device_data.get("info", {})
        pump_info = info.get("pumpInfo", {})
        main_pump = pump_info.get("main", {})
        manufacturer = main_pump.get("manufacturer")
        return manufacturer if manufacturer else None


class MoenFloNABPrimaryPumpModelSensor(MoenFloNABSensorBase):
    """Primary pump model number diagnostic sensor."""

    _attr_icon = "mdi:pump"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_primary_pump_model"
        self._attr_name = f"{device_name} Primary Pump Model"

    @property
    def native_value(self) -> str | None:
        """Return the primary pump model number."""
        info = self.device_data.get("info", {})
        pump_info = info.get("pumpInfo", {})
        main_pump = pump_info.get("main", {})
        model = main_pump.get("model")
        return model if model else None


class MoenFloNABPrimaryPumpInstallDateSensor(MoenFloNABSensorBase):
    """Primary pump install date diagnostic sensor."""

    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:calendar-check"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_primary_pump_install_date"
        self._attr_name = f"{device_name} Primary Pump Install Date"

    @property
    def native_value(self) -> date | None:
        """Return the primary pump install date."""
        info = self.device_data.get("info", {})
        pump_info = info.get("pumpInfo", {})
        main_pump = pump_info.get("main", {})
        install_date_str = main_pump.get("installDate")
        if install_date_str:
            try:
                # Parse ISO timestamp and extract date
                # Format: "2010-12-31T08:54:53.000Z" → date(2010, 12, 31)
                dt = datetime.fromisoformat(install_date_str.replace("Z", "+00:00"))
                return dt.date()
            except (ValueError, AttributeError):
                pass
        return None


class MoenFloNABBasinDiameterSensor(MoenFloNABSensorBase):
    """Basin diameter diagnostic sensor."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_icon = "mdi:diameter"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = UnitOfLength.MILLIMETERS

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_basin_diameter"
        self._attr_name = f"{device_name} Basin Diameter"

    @property
    def native_value(self) -> float | None:
        """Return the basin diameter in millimeters.

        Using mm as native unit allows Home Assistant to automatically
        convert to the user's preferred unit system (inches for imperial).
        """
        info = self.device_data.get("info", {})
        diameter_mm = info.get("crockDiameterMM")
        if diameter_mm is not None:
            try:
                return float(diameter_mm)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        info = self.device_data.get("info", {})
        pump_info = info.get("pumpInfo", {})
        main_pump = pump_info.get("main", {})
        return {
            "basin_diameter_inches": main_pump.get("crockDiameter"),
        }


class MoenFloNABBackupPumpManufacturerSensor(MoenFloNABSensorBase):
    """Backup pump manufacturer diagnostic sensor."""

    _attr_icon = "mdi:factory"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_backup_pump_manufacturer"
        self._attr_name = f"{device_name} Backup Pump Manufacturer"

    @property
    def native_value(self) -> str | None:
        """Return the backup pump manufacturer."""
        info = self.device_data.get("info", {})
        pump_info = info.get("pumpInfo", {})
        backup_pump = pump_info.get("backup", {})
        manufacturer = backup_pump.get("manufacturer")
        return manufacturer if manufacturer else None


class MoenFloNABBackupPumpModelSensor(MoenFloNABSensorBase):
    """Backup pump model number diagnostic sensor."""

    _attr_icon = "mdi:pump"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_backup_pump_model"
        self._attr_name = f"{device_name} Backup Pump Model"

    @property
    def native_value(self) -> str | None:
        """Return the backup pump model number."""
        info = self.device_data.get("info", {})
        pump_info = info.get("pumpInfo", {})
        backup_pump = pump_info.get("backup", {})
        model = backup_pump.get("model")
        return model if model else None


class MoenFloNABBackupPumpInstallDateSensor(MoenFloNABSensorBase):
    """Backup pump install date diagnostic sensor."""

    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:calendar-check"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_backup_pump_install_date"
        self._attr_name = f"{device_name} Backup Pump Install Date"

    @property
    def native_value(self) -> date | None:
        """Return the backup pump install date."""
        info = self.device_data.get("info", {})
        pump_info = info.get("pumpInfo", {})
        backup_pump = pump_info.get("backup", {})
        install_date_str = backup_pump.get("installDate")
        if install_date_str:
            try:
                # Parse ISO timestamp and extract date
                dt = datetime.fromisoformat(install_date_str.replace("Z", "+00:00"))
                return dt.date()
            except (ValueError, AttributeError):
                pass
        return None


class MoenFloNABBackupPumpTestFrequencySensor(MoenFloNABSensorBase):
    """Backup pump test frequency diagnostic sensor."""

    _attr_icon = "mdi:calendar-clock"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_backup_pump_test_frequency"
        self._attr_name = f"{device_name} Backup Pump Test Frequency"

    @property
    def native_value(self) -> str | None:
        """Return the backup pump test frequency."""
        info = self.device_data.get("info", {})
        pump_info = info.get("pumpInfo", {})
        backup_pump = pump_info.get("backup", {})
        frequency = backup_pump.get("pumpTestFrequency")
        return frequency if frequency else None


class MoenFloNABBackupPumpBatteryWaterSensor(MoenFloNABSensorBase):
    """Backup pump battery requires water diagnostic sensor."""

    _attr_icon = "mdi:battery-plus"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_backup_pump_battery_water"
        self._attr_name = f"{device_name} Backup Pump Battery Requires Water"

    @property
    def native_value(self) -> str | None:
        """Return whether backup pump battery requires water."""
        info = self.device_data.get("info", {})
        pump_info = info.get("pumpInfo", {})
        backup_pump = pump_info.get("backup", {})
        requires_water = backup_pump.get("batteryNeedsWater")
        if requires_water is not None:
            return "Yes" if requires_water else "No"
        return None


class MoenFloNABBackupPumpInstalledSensor(MoenFloNABSensorBase):
    """Backup pump installed diagnostic sensor."""

    _attr_icon = "mdi:pump"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_backup_pump_installed"
        self._attr_name = f"{device_name} Backup Pump Installed"

    @property
    def native_value(self) -> str | None:
        """Return whether backup pump is installed."""
        info = self.device_data.get("info", {})
        pump_info = info.get("pumpInfo", {})
        installed = pump_info.get("hasBackupPump")
        if installed is not None:
            return "Yes" if installed else "No"
        return None


class MoenFloNABPollingPeriodSensor(MoenFloNABSensorBase):
    """Polling period diagnostic sensor showing current update interval."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = "s"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:timer-outline"

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_polling_period"
        self._attr_name = f"{device_name} Polling Period"

    @property
    def native_value(self) -> int | None:
        """Return the current polling interval in seconds."""
        if self.coordinator.update_interval:
            return int(self.coordinator.update_interval.total_seconds())
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        from datetime import datetime, timezone

        # Count recent pump cycles for context
        pump_cycles = self.device_data.get("pump_cycles", [])
        now = datetime.now(timezone.utc)
        recent_cycles = 0

        for cycle in pump_cycles:
            try:
                cycle_time_str = cycle.get("date", "")
                if cycle_time_str:
                    cycle_time = datetime.fromisoformat(cycle_time_str.replace("Z", "+00:00"))
                    minutes_ago = (now - cycle_time).total_seconds() / 60
                    if minutes_ago <= 15:
                        recent_cycles += 1
            except (ValueError, AttributeError):
                continue

        # Check for active alerts
        info = self.device_data.get("info", {})
        alerts = info.get("alerts", {})
        active_alerts = sum(
            1 for alert_data in alerts.values()
            if isinstance(alert_data, dict)
            and "active" in alert_data.get("state", "")
            and "inactive" not in alert_data.get("state", "")
        )

        return {
            "cycles_last_15_min": recent_cycles,
            "active_alerts": active_alerts,
            "adaptive_polling": "enabled",
        }


class MoenFloNABPumpCyclesLast15MinSensor(MoenFloNABSensorBase):
    """Pump cycles in last 15 minutes diagnostic sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "cycles"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:counter"

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_pump_cycles_last_15_min"
        self._attr_name = f"{device_name} Pump Cycles Last 15 Minutes"

    @property
    def native_value(self) -> int | None:
        """Return the number of pump cycles in the last 15 minutes."""
        from datetime import datetime, timezone

        pump_cycles = self.device_data.get("pump_cycles", [])
        now = datetime.now(timezone.utc)
        recent_cycles = 0

        for cycle in pump_cycles:
            try:
                cycle_time_str = cycle.get("date", "")
                if cycle_time_str:
                    cycle_time = datetime.fromisoformat(cycle_time_str.replace("Z", "+00:00"))
                    minutes_ago = (now - cycle_time).total_seconds() / 60
                    if minutes_ago <= 15:
                        recent_cycles += 1
            except (ValueError, AttributeError):
                continue

        return recent_cycles

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        from datetime import datetime, timezone

        pump_cycles = self.device_data.get("pump_cycles", [])
        now = datetime.now(timezone.utc)

        # Get timestamps of recent cycles
        recent_cycle_times = []
        for cycle in pump_cycles:
            try:
                cycle_time_str = cycle.get("date", "")
                if cycle_time_str:
                    cycle_time = datetime.fromisoformat(cycle_time_str.replace("Z", "+00:00"))
                    minutes_ago = (now - cycle_time).total_seconds() / 60
                    if minutes_ago <= 15:
                        recent_cycle_times.append(cycle_time_str)
            except (ValueError, AttributeError):
                continue

        attrs = {}
        if recent_cycle_times:
            attrs["recent_cycle_times"] = recent_cycle_times
            attrs["most_recent_cycle"] = recent_cycle_times[0] if recent_cycle_times else None

        return attrs
