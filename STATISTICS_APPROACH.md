# Statistics-Based Pump Volume Tracking

## Problem
The current "Total Volume" sensor sums the last 10 cycles, causing the value to fluctuate up and down as cycles enter/leave the 10-cycle window. This doesn't work with Home Assistant's energy dashboard and can't show historical trends.

## Solution: Long-Term Statistics
Use Home Assistant's statistics system to store historical pump cycle data, enabling:
- Historical graphs and trend analysis
- Energy Dashboard integration
- Proper cumulative totals that never decrease
- Per-cycle granularity with timestamps

## Implementation Approach

### Similar to: Opower/Utility Integrations
This follows the same pattern as electricity/gas utility integrations:
- Fetch historical data from API
- Insert statistics with proper timestamps
- Only add new data on subsequent updates
- Works with Energy Dashboard out of the box

### Code Structure

```python
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)

async def async_import_pump_statistics(hass, device_duid, cycles):
    """Import pump cycle statistics into HA recorder."""

    # Define metadata
    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name="Sump Pump Water Volume",
        source=DOMAIN,
        statistic_id=f"{DOMAIN}:{device_duid}_pump_volume",
        unit_of_measurement=UnitOfVolume.GALLONS,
    )

    # Get last imported statistic to avoid duplicates
    last_stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, f"{DOMAIN}:{device_duid}_pump_volume", True, set()
    )

    last_timestamp = None
    if last_stats:
        last_timestamp = datetime.fromisoformat(
            last_stats[f"{DOMAIN}:{device_duid}_pump_volume"][0]["end"]
        )

    # Build statistics from cycles
    cumulative_sum = 0
    statistics = []

    for cycle in reversed(cycles):  # Process oldest first
        cycle_time = datetime.fromisoformat(cycle["date"].replace("Z", "+00:00"))

        # Skip if already imported
        if last_timestamp and cycle_time <= last_timestamp:
            continue

        cumulative_sum += cycle.get("emptyVolume", 0)

        statistics.append(
            StatisticData(
                start=cycle_time,
                state=cycle.get("emptyVolume", 0),  # This cycle's volume
                sum=cumulative_sum,  # Cumulative total
            )
        )

    if statistics:
        async_add_external_statistics(hass, metadata, statistics)
        _LOGGER.info(
            "Imported %d pump cycle statistics for %s",
            len(statistics),
            device_duid
        )
```

### Sensor Changes

**Remove the current Total Volume sensor** and replace with a coordinator method that imports statistics:

```python
# In __init__.py coordinator's async_setup_entry or first refresh:

async def async_first_refresh(self):
    """First refresh - import all historical statistics."""
    await super().async_config_entry_first_refresh()

    # Import statistics for all devices
    for device_duid, device_data in self.data.items():
        cycles = device_data.get("pump_cycles", [])
        if cycles:
            await async_import_pump_statistics(
                self.hass,
                device_duid,
                cycles
            )
```

### Update Strategy

**First Load:** Fetch all available cycles (limit=1000) and import them
**Subsequent Updates:** Fetch last 50 cycles, only import new ones

This minimizes API calls while keeping data up-to-date.

## Benefits

1. **Proper Historical Tracking**: Statistics are immutable and timestamped
2. **Energy Dashboard Compatible**: Works with HA's energy dashboard out of the box
3. **Efficient**: Only imports new data after initial load
4. **Accurate**: One statistic entry per pump cycle with exact timestamp
5. **Persistent**: Survives HA restarts and integration reloads

## UI Result

Users can:
- View pump volume in Energy Dashboard
- Create custom graphs with history_stats
- See daily/weekly/monthly totals
- Compare periods (this month vs last month)
- Set up automations based on volume trends

## Statistics vs Regular Sensor

| Feature | Regular Sensor | Statistics |
|---------|---------------|------------|
| Historical Data | Limited by recorder | Full history imported |
| Energy Dashboard | ❌ (if fluctuating) | ✅ |
| Granularity | Current state only | Per-cycle entries |
| API Efficiency | Frequent fetches | One-time import + incremental |
| Accuracy | Depends on polling | Exact cycle timestamps |

## Example: Similar Integrations

- **Opower**: Imports utility usage with timestamps
- **Tibber**: Imports electricity consumption
- **PVOutput**: Imports solar generation
- **Sense**: Imports energy monitor data

All use the same statistics pattern we're proposing here.

## Migration Path

1. **v1.7.2**: Deprecate Total Volume sensor (mark as diagnostic/hidden)
2. **v1.8.0**: Implement statistics import on first load
3. **v1.8.1**: Remove old sensor entirely
4. Document migration in CHANGELOG and README

## Questions?

- Should we import ALL cycles on first load or limit to last 90 days?
- Should we keep a "Recent Volume" sensor showing last 10 cycles separately?
- Should statistics update hourly, daily, or on every coordinator update?
