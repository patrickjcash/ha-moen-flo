"""Sensor platform for Moen Flo NAB."""
from __future__ import annotations

from datetime import datetime, timezone
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
from .const import DOMAIN

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
        device_name = device_info.get("nickname", f"Sump Pump {device_duid[:8]}")

        # Water Level Sensor
        entities.append(
            MoenFloNABWaterLevelSensor(coordinator, device_duid, device_name)
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

        # Pump History Sensor
        entities.append(
            MoenFloNABPumpVolumeSensor(coordinator, device_duid, device_name)
        )

        # Diagnostic Sensors
        entities.append(MoenFloNABBatterySensor(coordinator, device_duid, device_name))
        entities.append(MoenFloNABWiFiSignalSensor(coordinator, device_duid, device_name))

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
            "model": "Flo NAB Sump Pump Monitor",
            "sw_version": info.get("firmwareVersion"),
        }


class MoenFloNABWaterLevelSensor(MoenFloNABSensorBase):
    """Water level sensor - distance from sensor to water surface."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfLength.MILLIMETERS
    _attr_icon = "mdi:waves"

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_water_level"
        self._attr_name = f"{device_name} Water Level"

    @property
    def native_value(self) -> float | None:
        """Return the water level distance in mm.
        
        crockTofDistance is in millimeters (282mm = 28.2cm).
        Lower value = higher water level (water closer to sensor).
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
        
        attrs = {
            "distance_cm": round(float(info.get("crockTofDistance", 0)) / 10, 1) if info.get("crockTofDistance") else None,
            "water_trend": droplet.get("trend"),  # rising/stable/receding
            "flood_risk": droplet.get("floodRisk"),
            "basin_diameter_inches": main_pump.get("crockDiameter"),
            "basin_diameter_mm": info.get("crockDiameterMM"),
        }
        
        return {k: v for k, v in attrs.items() if v is not None}


class MoenFloNABTemperatureSensor(MoenFloNABSensorBase):
    """Temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT

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
            "unit": temp_data.get("unitOfMeasure"),
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
        """Return the last cycle time from pump cycles data."""
        cycles = self.device_data.get("pump_cycles", [])

        if cycles and len(cycles) > 0:
            latest = cycles[0]
            try:
                # Parse ISO timestamp
                date_str = latest.get("date", "")
                if date_str:
                    # Remove microseconds and Z if present
                    date_str = date_str.split('.')[0].replace('Z', '')
                    dt = datetime.fromisoformat(date_str)
                    # Ensure timezone-aware datetime (assume UTC if not specified)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
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
            
            # Add most recent event from logs for context
            last_event = self.device_data.get("last_cycle")
            if last_event:
                attrs["last_event_id"] = last_event.get("id")
                attrs["last_event_title"] = last_event.get("title")
                attrs["last_event_severity"] = last_event.get("severity")
            
            return {k: v for k, v in attrs.items() if v is not None}

        return {}


class MoenFloNABPumpVolumeSensor(MoenFloNABSensorBase):
    """Total pump volume sensor with primary/backup breakdown."""

    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfVolume.GALLONS
    _attr_icon = "mdi:pump"

    def __init__(
        self,
        coordinator: MoenFloNABDataUpdateCoordinator,
        device_duid: str,
        device_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, device_duid, device_name)
        self._attr_unique_id = f"{device_duid}_total_volume"
        self._attr_name = f"{device_name} Total Volume"

    @property
    def native_value(self) -> float | None:
        """Return the total volume pumped across all cycles."""
        cycles = self.device_data.get("pump_cycles", [])

        if cycles:
            total_volume = sum(c.get("emptyVolume", 0) for c in cycles)
            return round(total_volume, 1)

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return primary/backup volume breakdown and cycle history."""
        cycles = self.device_data.get("pump_cycles", [])

        if not cycles:
            return {}

        # Calculate primary pump volume (cycles where backup didn't run)
        primary_cycles = [c for c in cycles if not c.get("backupRan")]
        primary_volume = sum(c.get("emptyVolume", 0) for c in primary_cycles)

        # Calculate backup pump volume (cycles where backup ran)
        backup_cycles = [c for c in cycles if c.get("backupRan")]
        backup_volume = sum(c.get("emptyVolume", 0) for c in backup_cycles)

        # Build cycle history (last 10 cycles)
        cycle_history = []
        for cycle in cycles[:10]:
            try:
                date_str = cycle.get("date", "")
                if date_str:
                    # Parse timestamp
                    date_str = date_str.split(".")[0].replace("Z", "")
                    dt = datetime.fromisoformat(date_str)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)

                    cycle_history.append(
                        {
                            "date": dt.isoformat(),
                            "volume": round(cycle.get("emptyVolume", 0), 1),
                            "backup_ran": cycle.get("backupRan", False),
                        }
                    )
            except (ValueError, TypeError):
                pass

        # Get oldest and newest cycle dates
        oldest_date = None
        newest_date = None
        if cycles:
            try:
                # Newest is first
                newest_str = cycles[0].get("date", "").split(".")[0].replace("Z", "")
                newest_dt = datetime.fromisoformat(newest_str)
                if newest_dt.tzinfo is None:
                    newest_dt = newest_dt.replace(tzinfo=timezone.utc)
                newest_date = newest_dt.isoformat()

                # Oldest is last
                oldest_str = cycles[-1].get("date", "").split(".")[0].replace("Z", "")
                oldest_dt = datetime.fromisoformat(oldest_str)
                if oldest_dt.tzinfo is None:
                    oldest_dt = oldest_dt.replace(tzinfo=timezone.utc)
                oldest_date = oldest_dt.isoformat()
            except (ValueError, TypeError, IndexError):
                pass

        attrs = {
            "primary_volume": round(primary_volume, 1),
            "backup_volume": round(backup_volume, 1),
            "total_cycles": len(cycles),
            "primary_cycles": len(primary_cycles),
            "backup_cycles": len(backup_cycles),
            "cycle_history": cycle_history,
            "oldest_cycle_date": oldest_date,
            "newest_cycle_date": newest_date,
        }

        return {k: v for k, v in attrs.items() if v is not None}


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
