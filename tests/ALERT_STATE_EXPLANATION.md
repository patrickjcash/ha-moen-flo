# Alert State Behavior - Explained

## Discovery

Through testing with manual dismissal in the Moen app, we discovered how alert states work:

### Alert State Format

Alerts have a compound state string: `{active/inactive}_{ack}_{rack}_{suppressed}`

Example states:
- `active_unlack_unrack_unsuppressed` - Active condition, unacknowledged
- `inactive_unlack_unrack_unsuppressed` - Inactive condition, but unacknowledged (still shows in app!)

### State Components

1. **active/inactive** - Whether the alert condition is currently happening
   - `active` = Problem is ongoing (e.g., pump is currently failed)
   - `inactive` = Problem has resolved (e.g., pump recovered)

2. **unlack/ack** - Whether user has acknowledged/dismissed the alert
   - `unlack` = Unacknowledged (shows in app notifications)
   - `ack` = Acknowledged (dismissed by user)

3. **unrack/rack** - Unknown purpose
4. **unsuppressed/suppressed** - Whether alert is suppressed

### Key Finding: inactive ≠ dismissed!

**Before our test:**
- Alert 224 (High Water Level): `inactive_unlack_unrack_unsuppressed`
- Alert 262 (Main Pump Overwhelmed): `inactive_unlack_unrack_unsuppressed`
- Alert 266 (Main Pump Not Stopping): `inactive_unlack_unrack_unsuppressed`
- Alert 218 (Backup Test Scheduled): `active_unlack_unrack_unsuppressed`

**What app showed:** All 4 alerts (because all are `unlack`)

**What shadow showed:** All 4 alerts with states above

**After manually dismissing 224 in app:**
- Alert 224: **Removed from shadow entirely** ✓
- Other alerts unchanged

## App vs HA Behavior

### Moen App Logic:
Shows all alerts with `unlack` (unacknowledged), regardless of active/inactive status.

**Why?** To notify users of problems that occurred even if they've since resolved, until user acknowledges them.

### HA Integration Logic (Correct):
Flood Risk sensor only triggers on `active` alerts (line 171 of binary_sensor.py):
```python
if "active" in state and "inactive" not in state:
    return True
```

**Why?** HA should show current problems, not historical ones that have resolved.

## Example Scenario

1. **Water level gets high** → Alert 224 becomes `active_unlack_unrack_unsuppressed`
   - App shows: "High Water Level" ✓
   - HA flood risk: ON ✓

2. **Water level returns to normal** → Alert 224 becomes `inactive_unlack_unrack_unsuppressed`
   - App shows: "High Water Level" ✓ (still unacknowledged)
   - HA flood risk: OFF ✓ (problem resolved)

3. **User dismisses in app** → Alert 224 removed from shadow entirely
   - App shows: (nothing) ✓
   - HA flood risk: OFF ✓

## Dismissal Behavior

### What Works:
- `inactive_unlack` alerts can be dismissed (they disappear from shadow)
- Manual dismissal in app works perfectly

### What Doesn't Work:
- Some `active_unlack` alerts cannot be dismissed via API
- Example: Alert 218 (Backup Test Scheduled) - API returns `{"status": true}` but state doesn't change
- Likely because the condition is still active (test is still scheduled)

### API Dismissal Method:
```python
# Shadow API with alertAck parameter
await client.update_shadow({
    "clientId": client_id,
    "alertAck": alert_id
})
```

**Result:**
- For `inactive_unlack` alerts: Removes from shadow ✓
- For some `active_unlack` alerts: No effect (cannot dismiss active problems)

## Integration Implications

### Current Behavior (v2.3.1):
✅ **Flood Risk Sensor** - Correctly shows only `active` alerts
✅ **Last Alert Sensor** - Shows most recent active alert with proper descriptions
✅ **Dismiss Button** - Attempts dismissal but some alerts can't be dismissed programmatically

### Why Dismiss Button May Not Work:
1. Alert is still `active` (problem ongoing) - cannot be dismissed
2. Alert is `inactive_unlack` - should be dismissable, but API may have limitations
3. Some alert types (like scheduled tests) may be non-dismissable by design

### Recommendation:
Keep button as-is with documentation noting:
- Works for resolved (`inactive`) alerts
- May not work for ongoing (`active`) problems
- Some alert types cannot be dismissed programmatically

## Testing Results Summary

**Test Date:** 2026-01-11

**Alerts Before Manual Dismissal:**
- 218: `active_unlack_unrack_unsuppressed` (Backup Test Scheduled)
- 224: `inactive_unlack_unrack_unsuppressed` (High Water Level)
- 262: `inactive_unlack_unrack_unsuppressed` (Main Pump Overwhelmed)
- 266: `inactive_unlack_unrack_unsuppressed` (Main Pump Not Stopping)

**After Dismissing 224 in App:**
- 218: `active_unlack_unrack_unsuppressed` (unchanged)
- 224: **REMOVED FROM SHADOW** ✓
- 262: `inactive_unlack_unrack_unsuppressed` (unchanged)
- 266: `inactive_unlack_unrack_unsuppressed` (unchanged)

**Conclusion:** Dismissal works by removing the alert from the shadow entirely, not by changing its state to "ack".
