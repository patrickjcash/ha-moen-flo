# Alert Implementation Summary

## Overview

Version 1.6.0 adds comprehensive alert handling to the Moen Smart Sump Pump Monitor integration based on analysis of the actual device shadow API data and reverse engineering of the Moen mobile app.

## Key Discovery

The initial implementation incorrectly assumed that the `droplet.floodRisk` field would contain meaningful data. However, testing revealed:

- **`droplet.floodRisk` returns "unknown"** in the API response
- **Alert data is stored in the `alerts` field** as a dictionary of alert codes
- **The Moen app decodes numeric alert IDs** to display human-readable messages
- **Alert states follow a specific pattern**: `active_unlack_unrack_unsuppressed` vs `inactive_unlack_unrack_unsuppressed`

## Implementation Changes

### 1. New "Last Alert" Sensor

**Entity ID**: `sensor.{device_name}_last_alert`

**Purpose**: Shows the most recent active alert in human-readable form

**States**:
- When alerts active: Shows description (e.g., "Primary Pump Failed")
- When no active alerts: Shows "No active alerts"
- When no alert data: Shows "No alerts"

**Attributes**:
```yaml
active_alert_count: 3
total_alert_count: 6
active_alerts:
  - id: "258"
    description: "Primary Pump Failed"
    timestamp: "2026-01-07T12:34:56.000Z"
    state: "active_unlack_unrack_unsuppressed"
  - id: "260"
    description: "Backup Pump Failed"
    timestamp: "2026-01-07T12:30:00.000Z"
    state: "active_unlack_unrack_unsuppressed"
recent_inactive_alerts:
  - id: "262"
    description: "Primary Pump Lagging"
    timestamp: "2026-01-06T08:00:00.000Z"
    state: "inactive_unlack_unrack_unsuppressed"
```

### 2. Enhanced Flood Risk Binary Sensor

**Entity ID**: `binary_sensor.{device_name}_flood_risk`

**Previous Behavior**: Checked for specific alert IDs (254, 256, 258)

**New Behavior**:
- Triggers on ANY active alert (not just specific codes)
- Properly distinguishes active vs inactive alerts
- More reliable indicator of system health

**Logic**:
```python
# Check if droplet.floodRisk is set (still checked for future API improvements)
if flood_risk and flood_risk != "unknown":
    return True

# Check for ANY active alerts
for alert_id, alert_data in alerts.items():
    state = alert_data.get("state", "")
    if "active" in state and "inactive" not in state:
        return True  # Problem detected!
```

### 3. Alert Code Mappings

Extracted from decompiled Moen app `strings.xml`:

| Code | Description | Source String |
|------|-------------|---------------|
| 250 | Water Detected | `backup_pump_status_failed` |
| 252 | Water Was Detected | (cleared state) |
| 254 | Critical Flood Risk | (inferred from context) |
| 256 | High Flood Risk | (inferred from context) |
| 258 | Primary Pump Failed | `primary_pump_status_failed` |
| 260 | Backup Pump Failed | `backup_pump_status_failed` |
| 262 | Primary Pump Lagging | `primary_pump_status_lagging` |
| 264 | Backup Pump Lagging | `backup_pump_status_lagging` |
| 266 | Backup Pump Test Failed | `backup_pump_test_status_failed` |
| 268 | Power Outage | (device on battery power) |

**Note**: Alert 224 appeared in test data but was not found in the app strings. It's displayed as "Alert 224" (unknown).

## Example Data from Real Device

### Example Alert State

**Active Alerts**:
- Alert 258: Primary Pump Failed
- Alert 260: Backup Pump Failed
- Alert 268: Power Outage

**Inactive Alerts**:
- Alert 224: Unknown alert
- Alert 262: Primary Pump Lagging
- Alert 266: Backup Pump Test Failed

### Shadow API Response Structure

```json
{
  "state": {
    "reported": {
      "alerts": {
        "258": {
          "timestamp": "2026-01-07T12:34:56.000Z",
          "state": "active_unlack_unrack_unsuppressed"
        },
        "260": {
          "timestamp": "2026-01-07T12:30:00.000Z",
          "state": "active_unlack_unrack_unsuppressed"
        }
      },
      "droplet": {
        "level": -1,
        "trend": "stable",
        "floodRisk": "unknown",
        "primaryState": "unknown",
        "backupState": "unknown"
      }
    }
  }
}
```

## User Experience

### Dashboard View

**When system is healthy**:
- Flood Risk: OFF (green)
- Last Alert: "No active alerts"

**When pumps fail** (current state):
- Flood Risk: ON (red/yellow - problem detected)
- Last Alert: "Primary Pump Failed"
- Attributes show all 3 active alerts with timestamps

### Automations

Users can now create automations based on:

```yaml
# Example: Notify on ANY alert
trigger:
  - platform: state
    entity_id: binary_sensor.sump_pump_monitor_flood_risk
    to: "on"
action:
  - service: notify.mobile_app
    data:
      title: "Sump Pump Alert"
      message: "{{ state_attr('sensor.sump_pump_monitor_last_alert', 'active_alerts') }}"

# Example: Notify on specific alert types
trigger:
  - platform: state
    entity_id: sensor.sump_pump_monitor_last_alert
action:
  - choose:
      - conditions:
          - condition: state
            entity_id: sensor.sump_pump_monitor_last_alert
            state: "Primary Pump Failed"
        sequence:
          - service: notify.critical
            data:
              message: "PRIMARY PUMP FAILURE - Check immediately!"
```

## Testing

Run the test script to verify alert processing:

```bash
python3 tests/test_alert_sensor.py
```

This simulates the alert processing logic using real device data and shows:
- All mapped alert codes
- Current active/inactive alerts
- What the Last Alert sensor would display
- Whether Flood Risk sensor would be ON/OFF

## Future Improvements

1. **Additional Alert Codes**: As more alert types are discovered, add them to `ALERT_CODES` in [const.py](custom_components/moen_flo_nab/const.py)

2. **Alert Severity**: Could add severity levels (Critical, Warning, Info) based on alert codes

3. **Alert History**: Could track alert history in Home Assistant recorder

4. **Droplet Data**: If future API updates populate `droplet.floodRisk` with real data, it will be used automatically

## Files Modified

- [binary_sensor.py](custom_components/moen_flo_nab/binary_sensor.py) - Fixed Flood Risk sensor logic
- [sensor.py](custom_components/moen_flo_nab/sensor.py) - Added Last Alert sensor
- [const.py](custom_components/moen_flo_nab/const.py) - Added ALERT_CODES mapping
- [manifest.json](custom_components/moen_flo_nab/manifest.json) - Version bump to 1.6.0
- [CHANGELOG.md](CHANGELOG.md) - Documented changes

## Files Added

- [tests/test_alert_sensor.py](tests/test_alert_sensor.py) - Alert processing test
- [ALERT_IMPLEMENTATION.md](ALERT_IMPLEMENTATION.md) - This document
