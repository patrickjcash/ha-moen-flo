"""Statistics import for pump volume tracking."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
    StatisticMeanType,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _detect_volume_unit(cycles: list[dict[str, Any]]) -> str:
    """Detect the volume unit from cycle data.

    The API provides emptyVolumeUnits field which can be:
    - "gal" for gallons (US/imperial)
    - "L" or "liter" for liters (metric)

    Args:
        cycles: List of pump cycle dictionaries from API

    Returns:
        Home Assistant UnitOfVolume constant
    """
    for cycle in cycles:
        unit_str = cycle.get("emptyVolumeUnits", "").lower()
        if unit_str:
            if unit_str in ("l", "liter", "liters", "litre", "litres"):
                return UnitOfVolume.LITERS
            elif unit_str in ("gal", "gallon", "gallons"):
                return UnitOfVolume.GALLONS
            else:
                _LOGGER.debug("Unknown volume unit from API: %s, defaulting to gallons", unit_str)

    # Default to gallons for backwards compatibility
    return UnitOfVolume.GALLONS


async def async_import_pump_statistics(
    hass: HomeAssistant,
    device_duid: str,
    device_name: str,
    cycles: list[dict[str, Any]],
) -> int:
    """Import pump cycle statistics into Home Assistant recorder.

    This enables historical tracking and Energy Dashboard integration.
    Statistics are imported with proper timestamps, allowing for:
    - Historical graphs and trend analysis
    - Per-cycle granularity
    - Energy Dashboard water consumption tracking
    - Separate tracking for primary and backup pump usage

    Args:
        hass: Home Assistant instance
        device_duid: Device UUID
        device_name: Friendly device name
        cycles: List of pump cycle dictionaries from API

    Returns:
        Number of statistics imported across all stat types
    """
    if not cycles:
        _LOGGER.debug("No pump cycles to import for device %s", device_duid)
        return 0

    # Statistics ID format: domain:object_id (no special chars in object_id)
    # Replace hyphens in UUID with underscores for valid statistic_id
    safe_duid = device_duid.replace("-", "_")

    # Detect volume unit from API response (supports both gallons and liters)
    volume_unit = _detect_volume_unit(cycles)

    # Import three separate statistics: total, primary, and backup
    total_imported = 0
    total_imported += await _import_stat_type(hass, device_duid, device_name, cycles, safe_duid, "total", volume_unit)
    total_imported += await _import_stat_type(hass, device_duid, device_name, cycles, safe_duid, "primary", volume_unit)
    total_imported += await _import_stat_type(hass, device_duid, device_name, cycles, safe_duid, "backup", volume_unit)

    return total_imported


async def _import_stat_type(
    hass: HomeAssistant,
    device_duid: str,
    device_name: str,
    cycles: list[dict[str, Any]],
    safe_duid: str,
    stat_type: str,
    volume_unit: str,
) -> int:
    """Import statistics for a specific pump type (total, primary, or backup).

    Args:
        hass: Home Assistant instance
        device_duid: Device UUID
        device_name: Friendly device name
        cycles: List of pump cycle dictionaries from API
        safe_duid: Device UUID with hyphens replaced by underscores
        stat_type: Type of statistic ("total", "primary", or "backup")
        volume_unit: Unit of measurement (UnitOfVolume.GALLONS or LITERS)

    Returns:
        Number of statistics imported for this type
    """
    # Define statistic ID and name based on type
    if stat_type == "total":
        statistic_id = f"{DOMAIN}:{safe_duid}_pump_volume"
        stat_name = f"{device_name} Total Pump Volume"
    elif stat_type == "primary":
        statistic_id = f"{DOMAIN}:{safe_duid}_primary_pump_volume"
        stat_name = f"{device_name} Primary Pump Volume"
    else:  # backup
        statistic_id = f"{DOMAIN}:{safe_duid}_backup_pump_volume"
        stat_name = f"{device_name} Backup Pump Volume"

    # Define metadata with dynamic unit based on API response
    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        mean_type=StatisticMeanType.NONE,  # Sum-only statistic
        name=stat_name,
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=volume_unit,
        unit_class="volume",
    )

    # Get last imported statistic to avoid duplicates
    last_stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics,
        hass,
        1,
        statistic_id,
        True,
        {"sum"},
    )

    last_timestamp = None
    last_sum = 0.0

    if last_stats and statistic_id in last_stats:
        last_stat = last_stats[statistic_id][0]
        end_value = last_stat["end"]

        # Handle different timestamp formats from database
        if isinstance(end_value, datetime):
            last_timestamp = end_value
            if last_timestamp.tzinfo is None:
                last_timestamp = last_timestamp.replace(tzinfo=timezone.utc)
        elif isinstance(end_value, str):
            last_timestamp = datetime.fromisoformat(end_value).replace(
                tzinfo=timezone.utc
            )
        elif isinstance(end_value, (int, float)):
            # Unix timestamp from database
            last_timestamp = datetime.fromtimestamp(end_value, tz=timezone.utc)
        else:
            _LOGGER.warning(
                "Unexpected timestamp type in last_stats for %s: %s (type: %s)",
                statistic_id,
                end_value,
                type(end_value).__name__,
            )
            last_timestamp = None

        last_sum = last_stat.get("sum", 0.0)
        _LOGGER.debug(
            "Last imported %s statistic for %s: %s (sum: %.1f %s)",
            stat_type,
            device_duid,
            last_timestamp,
            last_sum,
            volume_unit,
        )

    # Build statistics from cycles (API returns newest first, we process oldest first)
    # Group cycles by hour to avoid duplicate timestamps
    hourly_volumes = {}  # {hour_timestamp: total_volume_in_hour}

    for cycle in reversed(cycles):
        try:
            # Parse cycle timestamp
            date_value = cycle.get("date")
            if not date_value:
                continue

            # Handle different date formats from API
            if isinstance(date_value, datetime):
                # Already a datetime object
                cycle_time = date_value
                if cycle_time.tzinfo is None:
                    cycle_time = cycle_time.replace(tzinfo=timezone.utc)
            elif isinstance(date_value, (int, float)):
                # Unix timestamp (seconds or milliseconds)
                timestamp = date_value
                # Check if milliseconds (timestamp > year 3000 in seconds)
                if timestamp > 32503680000:
                    timestamp = timestamp / 1000
                cycle_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            elif isinstance(date_value, str):
                # Parse ISO timestamp string and ensure UTC
                cycle_time = datetime.fromisoformat(date_value.replace("Z", "+00:00"))
                if cycle_time.tzinfo is None:
                    cycle_time = cycle_time.replace(tzinfo=timezone.utc)
            else:
                _LOGGER.warning(
                    "Unexpected date type for device %s: %s (type: %s)",
                    device_duid,
                    date_value,
                    type(date_value).__name__,
                )
                continue

            # Normalize to top of hour (minutes and seconds = 0) as required by HA statistics
            hour_timestamp = cycle_time.replace(minute=0, second=0, microsecond=0)

            # Skip if already imported
            if last_timestamp and hour_timestamp <= last_timestamp:
                continue

            # Get volume for this cycle
            volume = cycle.get("emptyVolume", 0)
            if volume <= 0:
                continue

            # Filter by pump type
            backup_ran = cycle.get("backupRan", False)

            if stat_type == "total":
                # Include all cycles for total
                pass
            elif stat_type == "primary":
                # Only include cycles where backup didn't run
                if backup_ran:
                    continue
            else:  # backup
                # Only include cycles where backup ran
                if not backup_ran:
                    continue

            # Aggregate volume by hour
            if hour_timestamp not in hourly_volumes:
                hourly_volumes[hour_timestamp] = 0
            hourly_volumes[hour_timestamp] += volume

        except (ValueError, TypeError) as err:
            _LOGGER.warning(
                "Failed to parse pump cycle for device %s: %s", device_duid, err
            )
            continue

    # Convert aggregated hourly volumes to statistics
    statistics = []
    cumulative_sum = last_sum

    for hour_timestamp in sorted(hourly_volumes.keys()):
        volume = hourly_volumes[hour_timestamp]
        cumulative_sum += volume

        statistics.append(
            StatisticData(
                start=hour_timestamp,
                state=volume,  # Total volume this hour (may be multiple cycles)
                sum=cumulative_sum,  # Cumulative total
            )
        )

    # Import statistics if we have new data
    if statistics:
        async_add_external_statistics(hass, metadata, statistics)
        _LOGGER.info(
            "Imported %d %s pump cycle statistics for %s (total: %.1f %s)",
            len(statistics),
            stat_type,
            device_name,
            cumulative_sum,
            volume_unit,
        )
        return len(statistics)
    else:
        _LOGGER.debug("No new %s pump cycle statistics to import for %s", stat_type, device_name)
        return 0
