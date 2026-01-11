# Bug Report - 2026-01-11

## Issues Found

### 1. Dismiss All Notifications Button Doesn't Work

**Symptom:** Button press appears to succeed but alerts remain active.

**Root Cause:** The shadow API `alertAck` parameter returns `{"status": true}` but doesn't actually dismiss certain alert types.

**Evidence:** Alert 218 ("Backup Test Scheduled") remains in `active_unlack_unrack_unsuppressed` state after dismissal attempt.

**Test Results:**
```
Method 1: alertAck parameter
  Response: {"status": true}
  Alert state before: active_unlack_unrack_unsuppressed
  Alert state after:  active_unlack_unrack_unsuppressed
  ✗ State did not change
```

**Proposed Fix:**
- Some alerts cannot be dismissed via API (same limitation as in Moen app)
- Button should remain but with updated description explaining limitation
- Consider adding success/failure feedback to user
- Alternative: Use `fbgpg_logs_v1_dismiss_alert_prod` endpoint (exists in test_dismiss_alerts.py but untested)

---

### 2. Last Pump Cycle Sensor Shows Wrong Time

**Symptom:** App shows last pump cycle at 12:05PM, HA shows different time (actual: 6:33 PM)

**Root Cause:** The sensor uses `get_last_pump_cycle()` which returns the most recent EVENT from logs, not the most recent PUMP CYCLE.

**Evidence from debug script:**
```
Most recent pump cycle: 06:33:50 PM (from session data)
Most recent event: 05:10:28 PM - "Flood Risk Cleared" (NOT a pump cycle!)
Discrepancy: 83.4 minutes

⚠ Event log is NOT a pump cycle event
HA 'Last Pump Cycle' sensor uses event log, NOT pump cycle data!
```

**Current Implementation:**
```python
# sensor.py lines 440-454
last_event = self.device_data.get("last_cycle")  # This is from event logs!
if last_event:
    time_str = last_event.get("time", "")
    # ... parse and return
```

**Problem:** `get_last_pump_cycle()` in api.py just returns `logs[0]` which is the most recent event of ANY type.

**Proposed Fix:**
```python
# In sensor.py MoenFloNABLastCycleSensor.native_value
# Remove event log logic entirely, use ONLY pump_cycles data
cycles = self.device_data.get("pump_cycles", [])
if cycles and len(cycles) > 0:
    latest = cycles[0]
    date_str = latest.get("date", "")
    if date_str:
        # Parse timestamp properly
        if date_str.endswith('Z'):
            date_str = date_str.replace('Z', '+00:00')
        dt = datetime.fromisoformat(date_str)
        return dt
return None
```

**Additional Fix Needed:** Remove `get_last_pump_cycle()` API method entirely as it's misleading (it doesn't get pump cycles, it gets events).

---

### 3. Pump Cycles Last 15 Minutes Showing 0 (NOT A BUG)

**Symptom:** Sensor shows 0 even though there was a run at 12:05PM

**Actual Cause:** User timezone confusion or stale HA data. The debug script shows:
- Most recent cycle: 6:33 PM (30 minutes ago at time of test)
- No cycles in last 15 minutes: CORRECT

**Evidence:**
```
Cycles found in last 15 minutes: 0
Most recent cycle was 30.3 minutes ago
✓ This explains why sensor shows 0
```

**Conclusion:** Sensor is working correctly. If user sees it showing 0 when there was a recent cycle, it's likely:
1. HA hasn't updated yet (check polling interval)
2. Timezone display issue
3. User looking at old HA state

**No fix needed** for this sensor.

---

## Test Scripts Created

1. **tests/debug_alert_dismissal.py** - Tests alert dismissal API methods
2. **tests/debug_pump_cycle_timing.py** - Analyzes pump cycle timing and event log discrepancies

## Files to Modify

### Priority 1: Last Pump Cycle Sensor Fix
- `custom_components/moen_sump_pump/sensor.py` (lines 432-474)
- `custom_components/moen_sump_pump/api.py` (remove get_last_pump_cycle method)
- `custom_components/moen_sump_pump/__init__.py` (remove last_cycle fetching logic)

### Priority 2: Dismiss Button Documentation
- `custom_components/moen_sump_pump/button.py` (add better logging/feedback)
- Consider testing `fbgpg_logs_v1_dismiss_alert_prod` endpoint as alternative

## Next Steps

1. Fix Last Pump Cycle sensor to use pump_cycles data only
2. Test dismiss button with alternative API endpoint
3. Add logging to button to show which alerts were successfully dismissed
4. Update CHANGELOG for v2.3.1 patch release
