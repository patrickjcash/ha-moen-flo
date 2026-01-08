"""Statistics import for pump volume tracking."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


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

    Args:
        hass: Home Assistant instance
        device_duid: Device UUID
        device_name: Friendly device name
        cycles: List of pump cycle dictionaries from API

    Returns:
        Number of statistics imported
    """
    if not cycles:
        _LOGGER.debug("No pump cycles to import for device %s", device_duid)
        return 0

    # Statistics ID format: domain:object_id (no special chars in object_id)
    # Replace hyphens in UUID with underscores for valid statistic_id
    safe_duid = device_duid.replace("-", "_")
    statistic_id = f"{DOMAIN}:{safe_duid}_pump_volume"

    # Define metadata
    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=f"{device_name} Water Volume",
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=UnitOfVolume.GALLONS,
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
        last_timestamp = datetime.fromisoformat(last_stat["end"]).replace(
            tzinfo=timezone.utc
        )
        last_sum = last_stat.get("sum", 0.0)
        _LOGGER.debug(
            "Last imported statistic for %s: %s (sum: %.1f gal)",
            device_duid,
            last_timestamp,
            last_sum,
        )

    # Build statistics from cycles (API returns newest first, we process oldest first)
    statistics = []
    cumulative_sum = last_sum

    for cycle in reversed(cycles):
        try:
            # Parse cycle timestamp
            date_str = cycle.get("date", "")
            if not date_str:
                continue

            # Parse ISO timestamp and ensure UTC
            cycle_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if cycle_time.tzinfo is None:
                cycle_time = cycle_time.replace(tzinfo=timezone.utc)

            # Normalize to top of hour (minutes and seconds = 0) as required by HA statistics
            cycle_time = cycle_time.replace(minute=0, second=0, microsecond=0)

            # Skip if already imported
            if last_timestamp and cycle_time <= last_timestamp:
                continue

            # Get volume for this cycle
            volume = cycle.get("emptyVolume", 0)
            if volume <= 0:
                continue

            cumulative_sum += volume

            statistics.append(
                StatisticData(
                    start=cycle_time,
                    state=volume,  # This cycle's volume
                    sum=cumulative_sum,  # Cumulative total
                )
            )

        except (ValueError, TypeError) as err:
            _LOGGER.warning(
                "Failed to parse pump cycle for device %s: %s", device_duid, err
            )
            continue

    # Import statistics if we have new data
    if statistics:
        async_add_external_statistics(hass, metadata, statistics)
        _LOGGER.info(
            "Imported %d pump cycle statistics for %s (total: %.1f gallons)",
            len(statistics),
            device_name,
            cumulative_sum,
        )
        return len(statistics)
    else:
        _LOGGER.debug("No new pump cycle statistics to import for %s", device_name)
        return 0
