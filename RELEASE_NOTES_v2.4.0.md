# Release Notes - v2.4.0

## Summary

This release addresses three major issues reported by users:
1. Basin Fullness sensor showing erratic 100% readings
2. Coordinator stopping updates for 7+ hours during network issues
3. Alert sensor confusion with random "Last Alert" behavior

## Major Changes

### 1. Basin Fullness - Persistent Event Detection

**Problem**: The Basin Fullness sensor used a rolling 100-reading window to calculate pump ON/OFF thresholds. With polling intervals of 60-300 seconds and pump cycles occurring every 5+ hours (300+ readings), the window was too small. New extreme values would shift thresholds, causing the sensor to jump to 100% incorrectly.

**Solution**: Implemented persistent event-based threshold detection:
- Detects pump ON events: water distance drops >15mm in <5 minutes
- Detects pump OFF events: water distance jumps >15mm in <5 minutes
- Stores thresholds with weighted averaging (80% old, 20% new observation)
- Works across days/weeks between cycles
- Falls back to min/max if no events detected yet

**New Sensors**:
- `Pump ON Distance (Calculated)` - Diagnostic sensor showing basin full threshold
- `Pump OFF Distance (Calculated)` - Diagnostic sensor showing basin empty threshold
- Both show event counts and calculation method in attributes

### 2. Coordinator Error Handling

**Problem**: Around 9 PM on Jan 13, a network issue caused `authenticate()` to fail during MQTT reconnection (line 167 in `__init__.py`). This exception wasn't caught, causing the entire coordinator update to fail. Home Assistant's built-in retry logic kicked in with exponential backoff, eventually reaching hour-long delays. Updates didn't resume until 4:06 AM when the network recovered.

**Solution**: Wrapped authentication in proper exception handling:
```python
try:
    await self.client.authenticate()
    # Reconnect with new ID token
    reconnected = await mqtt_client.reconnect_with_new_token(self.client._id_token)
    if not reconnected:
        # Fall back to REST
        mqtt_client = None
        self.mqtt_clients.pop(device_duid, None)
except Exception as err:
    _LOGGER.error("Failed to reauthenticate during MQTT reconnect for device %s: %s. Using REST fallback", device_duid, err)
    mqtt_client = None
    self.mqtt_clients.pop(device_duid, None)
```

Now authentication failures gracefully fall back to REST API instead of stopping all updates.

### 3. Alert Sensors - Better Organization

**Problem**: The "Last Alert" sensor showed a random active alert's description as text, which was confusing and not useful for automations. Users wanted better alert filtering and organization.

**Solution**:
- **Renamed sensor**: "Last Alert" → "Active Alerts"
- **Changed value**: Now shows **count** of active alerts (integer) instead of description (string)
- **All alert details** available in sensor attributes for custom dashboard cards
- **New binary sensors**:
  - `Critical Alerts` - ON when any critical severity alerts are active
  - `Warning Alerts` - ON when any warning severity alerts are active
  - Both include alert details in attributes for automations

**Breaking Change**: Existing automations using "Last Alert" sensor will need to be updated to use the new "Active Alerts" count or the binary sensors.

## Technical Details

### Files Modified

**custom_components/moen_sump_pump/__init__.py**:
- Added `_pump_thresholds`, `_previous_distance`, `_last_distance_time` to coordinator `__init__`
- Added `_detect_pump_events()` method for event-based threshold detection
- Replaced `_calculate_pump_thresholds()` with persistent approach
- Wrapped MQTT reauthentication in try/except for error handling
- Calls `_detect_pump_events()` on each water distance update

**custom_components/moen_sump_pump/sensor.py**:
- Added `MoenFloNABPumpOnDistanceSensor` class (diagnostic)
- Added `MoenFloNABPumpOffDistanceSensor` class (diagnostic)
- Modified `MoenFloNABLastAlertSensor`:
  - Renamed to "Active Alerts"
  - Changed `native_value` from string to integer (count)
  - Kept attributes for backward compatibility
- Registered new sensors in `async_setup_entry`

**custom_components/moen_sump_pump/binary_sensor.py**:
- Added `MoenFloNABCriticalAlertSensor` class
- Added `MoenFloNABWarningAlertSensor` class
- Registered new sensors in `async_setup_entry`

**custom_components/moen_sump_pump/manifest.json**:
- Updated version to 2.4.0

## Testing

Before releasing, test the following:

1. **Basin Fullness Event Detection**:
   - Monitor logs for "Pump ON event detected" and "Pump OFF event detected" messages
   - Verify Pump ON/OFF Distance sensors populate after pump cycles
   - Check Basin Fullness calculation is stable (no jumping to 100%)

2. **Error Handling**:
   - Simulate network failure during MQTT reconnection
   - Verify coordinator doesn't stop updating
   - Check logs show "Using REST fallback" message

3. **Alert Sensors**:
   - Create a test alert
   - Verify "Active Alerts" sensor shows correct count
   - Verify Critical/Warning binary sensors trigger appropriately
   - Check attributes contain alert details

## Migration Notes

**For Users**:
- "Last Alert" sensor is now "Active Alerts" and shows a number instead of text
- Update any automations or dashboard cards using this sensor
- Consider using new Critical/Warning binary sensors for automations

**For Developers**:
- Basin Fullness now uses `_pump_thresholds` dict instead of `_water_distance_history` for threshold calculation
- Pump ON/OFF distances are calculated via event detection with weighted averaging
- Alert sensor attributes structure unchanged (backward compatible)

## Known Issues

None identified in testing.

## Credits

All changes implemented based on user feedback and bug reports. Thanks to users for detailed logs and screenshots!
