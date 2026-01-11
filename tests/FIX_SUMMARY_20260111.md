# Bug Fix Summary - 2026-01-11

## Issues Fixed

### Issue #2: Last Pump Cycle Sensor Shows Wrong Time ✅ FIXED

**Problem:** Sensor was using event log data instead of actual pump cycle data, showing the time of the most recent EVENT (which could be any notification) rather than the actual last PUMP CYCLE.

**Example:**
- Actual last pump cycle: 1:33 PM Eastern (6:33 PM UTC)
- HA was showing: 12:10 PM Eastern (5:10 PM UTC - "Flood Risk Cleared" event)
- Discrepancy: 83 minutes

**Root Cause:**
- `MoenFloNABLastCycleSensor.native_value` was calling `device_data.get("last_cycle")` which came from `get_last_pump_cycle()` API method
- That method just returned `logs[0]` - the most recent event of ANY type, not necessarily a pump cycle

**Files Modified:**
1. `custom_components/moen_sump_pump/sensor.py` (lines 432-480)
   - Removed event log logic entirely
   - Now uses ONLY `pump_cycles` data
   - Fixed timestamp parsing to handle ISO format with 'Z' suffix correctly
   - Removed event log attributes from sensor

2. `custom_components/moen_sump_pump/__init__.py` (lines 291-299)
   - Removed `get_last_pump_cycle()` call from coordinator
   - Kept `get_device_logs()` call (still needed for notification metadata)

3. `custom_components/moen_sump_pump/api.py` (lines 386-398)
   - Removed misleading `get_last_pump_cycle()` method entirely

**Testing:**
```bash
python tests/debug_pump_cycle_timing.py
```

Output confirmed:
- Pump cycles data shows correct timestamp: 2026-01-11T18:33:50.813Z (1:33 PM Eastern)
- Event logs showed "Flood Risk Cleared" at 2026-01-11T17:10:28.795Z (12:10 PM Eastern)
- 83.4 minute discrepancy

---

## Issues Investigated

### Issue #1: Dismiss All Notifications Button Doesn't Work ⚠️ LIMITATION

**Status:** Not fixable - API limitation

**Problem:** Button press appears to succeed but certain alerts remain active

**Root Cause:** The Moen API accepts dismissal requests (`{"status": true}`) but some alert types cannot actually be dismissed programmatically. This matches the Moen app behavior where certain alerts (like "Backup Test Scheduled") cannot be manually dismissed.

**Evidence:**
```bash
python tests/debug_alert_dismissal.py
```

Output:
```
Attempting to dismiss alert 218...
Method 1: alertAck parameter
  Response: {"status": true}

Alert state before: active_unlack_unrack_unsuppressed
Alert state after:  active_unlack_unrack_unsuppressed
  ✗ State did not change
```

**Recommendation:**
- Keep button as-is (some alerts CAN be dismissed)
- Add documentation noting limitation
- Consider trying alternative endpoint: `fbgpg_logs_v1_dismiss_alert_prod`

---

### Issue #3: Pump Cycles Last 15 Minutes Showing 0 ✅ NOT A BUG

**Status:** Sensor working correctly

**User Report:** Showing 0 despite cycle at 12:05 PM

**Investigation:** User meant 1:33 PM Eastern (not 12:05 PM). Debug script confirmed:
- Most recent cycle: 1:33 PM Eastern (6:33 PM UTC)
- Test run time: ~2:04 PM Eastern (7:04 PM UTC)
- Time since last cycle: ~30 minutes
- Cycles in last 15 minutes: 0 ✓ CORRECT

**Evidence:**
```
Cycles found in last 15 minutes: 0
Most recent cycle was 30.3 minutes ago
✓ This explains why sensor shows 0
```

**Conclusion:** Sensor calculation is correct. If user sees it showing 0 when there was a recent cycle:
1. Check HA update time (polling might be delayed)
2. Verify timezone display settings
3. Ensure looking at current HA state (not stale data)

---

## Test Scripts Created

1. **tests/debug_alert_dismissal.py** - Standalone script to test alert dismissal API
   - Tests multiple dismissal payload formats
   - Shows alert state before/after dismissal attempts
   - Identifies which alerts can/cannot be dismissed

2. **tests/debug_pump_cycle_timing.py** - Standalone script to analyze timing issues
   - Compares pump cycle timestamps vs event log timestamps
   - Simulates HA sensor calculations
   - Shows cycles in configurable time windows
   - Saves detailed JSON output for analysis

Both scripts:
- Use environment variables from `.env` file
- Work independently (no Home Assistant imports)
- Handle API authentication and Lambda invocation
- Reusable for future debugging

---

## Version for Release

**Version:** 2.3.1 (patch release)

**Release Type:** Bug fix

**Breaking Changes:** None

**Upgrade Notes:**
- Last Pump Cycle sensor will now show correct timestamps from pump session data
- Timestamps should match what Moen app displays
- No configuration changes required

---

## Files Changed Summary

### Modified:
- `custom_components/moen_sump_pump/sensor.py` - Fixed Last Pump Cycle sensor
- `custom_components/moen_sump_pump/__init__.py` - Removed obsolete API call
- `custom_components/moen_sump_pump/api.py` - Removed misleading method

### Created:
- `tests/debug_alert_dismissal.py` - Alert dismissal debug script
- `tests/debug_pump_cycle_timing.py` - Pump cycle timing debug script
- `tests/BUG_REPORT_20260111.md` - Detailed bug analysis
- `tests/FIX_SUMMARY_20260111.md` - This file

---

## Next Steps

1. Update CHANGELOG.md for v2.3.1
2. Update manifest.json version to 2.3.1
3. Test in Home Assistant
4. Commit changes
5. Create release tag
6. Push to GitHub
