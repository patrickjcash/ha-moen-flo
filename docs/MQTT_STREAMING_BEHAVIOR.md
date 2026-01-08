# MQTT Streaming Behavior - Moen Flo NAB Device

## Discovery Summary

**Date**: January 8, 2026
**Device**: Moen Smart Sump Pump Monitor (Flo NAB)
**Firmware**: v1.0.8w

## Key Finding

The Moen Flo NAB device responds to two MQTT shadow commands that control Time-of-Flight (ToF) sensor streaming:

1. **`sens_on`** - Initiates continuous streaming of water level measurements (~1 update per second)
2. **`updates_off`** - Stops the continuous streaming and clears the command from device shadow

## Device Behavior

### Starting Streaming with `sens_on`

When `sens_on` command is sent to the device shadow:

```json
{
  "state": {
    "desired": {
      "crockCommand": "sens_on"
    }
  }
}
```

**Device Response**:
- Acknowledges the command immediately
- Begins streaming water level updates at approximately 1 Hz (1 update per second)
- **Continues streaming indefinitely** until explicitly stopped with `updates_off`
- Each update includes `crockTofDistance` (water level in millimeters)

### Stopping Streaming with `updates_off`

When `updates_off` command is sent:

```json
{
  "state": {
    "desired": {
      "crockCommand": "updates_off"
    }
  }
}
```

**Device Response**:
- Acknowledges the command
- Stops continuous streaming
- Clears `crockCommand` to `null` in the shadow
- Returns to idle state

## MQTT Message Sequence

### Opening Moen App "Fine Tuning" Page

```
[10:20:00] shadow/update/accepted - crockCommand: "sens_on"
[10:20:00] shadow/update/delta - crockCommand: "sens_on"
[10:20:01] shadow/update - crockTofDistance: 262 mm (device clears command to null)
[10:20:01] shadow/update - crockTofDistance: 261 mm
[10:20:02] shadow/update - crockTofDistance: 261 mm
[10:20:02] shadow/update - crockTofDistance: 262 mm
[10:20:03] shadow/update - crockTofDistance: 260 mm
```

### Closing Moen App "Fine Tuning" Page

```
[10:20:03] shadow/update/accepted - crockCommand: "updates_off"
[10:20:03] shadow/update/delta - crockCommand: "updates_off"
[10:20:04] shadow/update - crockCommand: null (device clears command)
[Streaming stops]
```

## Implications for Home Assistant Integration

### Battery Concerns

**Problem**: Continuous streaming at 1 Hz will drain the device battery much faster than normal operation.

**Solution**: Always send `updates_off` after collecting the needed data sample.

### Current Implementation (v1.6.0)

The integration sends `sens_on` but **never sends `updates_off`**, which could leave the device streaming continuously if:
- The integration polls frequently during alert states
- Multiple updates occur before the device times out
- Previous commands don't properly clear

### Required Changes for v1.7.0

Add `updates_off` command after data collection in two locations:

#### 1. MQTT Path (custom_components/moen_flo_nab/__init__.py:119)

```python
# Trigger fresh sensor reading via MQTT
await mqtt_client.trigger_sensor_update("sens_on")
# Wait for device to take reading and update shadow (~2 seconds)
await asyncio.sleep(2)
# Request shadow via MQTT to get the fresh reading
await mqtt_client.request_shadow()
# Wait for shadow response
await asyncio.sleep(1)

# STOP STREAMING to preserve battery
await mqtt_client.trigger_sensor_update("updates_off")
```

#### 2. REST Fallback Path (custom_components/moen_flo_nab/__init__.py:153)

```python
# REST fallback
_LOGGER.debug("Using REST API fallback for device %s", device_duid)
await self.client.update_shadow(client_id, "sens_on")
await asyncio.sleep(0.5)
shadow_data = await self.client.get_shadow(client_id)

# STOP STREAMING to preserve battery
await self.client.update_shadow(client_id, "updates_off")
```

## Testing Evidence

### Test Setup
- **Tool**: Python MQTT monitor script (tests/monitor_mqtt.py)
- **Connection**: AWS IoT Core WebSocket with temporary Cognito credentials
- **Subscribed Topics**: `$aws/things/{clientId}/shadow/#`
- **Duration**: 10+ minutes of observation

### Observations

1. **Without `updates_off`**: Device continued streaming for 12+ hours (observed on production HA instance)
2. **With `updates_off`**: Streaming stopped immediately after command acknowledged
3. **Moen App Behavior**: Always sends `updates_off` when exiting Fine Tuning screen
4. **Streaming Rate**: Approximately 1 update per second (varies 0.5-1.5 seconds)

### REST API vs MQTT Testing (January 8, 2026)

**Question**: Can we trigger `sens_on` via REST API Shadow endpoint instead of MQTT?

**Test Script**: `tests/test_shadow_commands.py`

**Result**: **NO** - REST API does not trigger device streaming

**Evidence**:
```
# Sent via REST API:
POST smartwater-app-shadow-api-prod-update
{
  "clientId": 12345678,
  "crockCommand": "sens_on"
}

# MQTT Monitor received:
$aws/things/12345678/shadow/update/accepted
{
  "state": {},           # ← Empty state!
  "metadata": {},
  "version": 70631,
  "timestamp": 1767886294
}

# Result: No streaming started, device did not respond
```

**Conclusion**: The REST API `update_shadow()` endpoint updates the AWS cloud shadow but **does NOT publish the command to the device** via MQTT. Only direct MQTT publishing to `$aws/things/{clientId}/shadow/update` triggers the actual device. Therefore, **MQTT connection is required** - we cannot simplify to REST-only.

## Additional Commands

From MQTT observation, other supported `crockCommand` values:

- `sens_on` - Start continuous ToF streaming
- `updates_off` - Stop streaming
- `sens_off` - Unknown behavior (not tested)
- `crockBckTst` - Backup test command (different shadow field)

## AWS IoT Topics

The device uses standard AWS IoT Shadow topics:

- `$aws/things/{clientId}/shadow/update` - Publish commands
- `$aws/things/{clientId}/shadow/update/accepted` - Receive command acknowledgments
- `$aws/things/{clientId}/shadow/update/delta` - Receive desired vs reported deltas
- `$aws/things/{clientId}/shadow/get` - Request full shadow
- `$aws/things/{clientId}/shadow/get/accepted` - Receive full shadow state

## References

- **Integration Code**: custom_components/moen_flo_nab/
- **Test Scripts**: tests/monitor_mqtt.py, tests/test_mqtt_boto3.py
- **AWS Documentation**: https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-mqtt.html

## Recommended Best Practices

1. **Always pair `sens_on` with `updates_off`** - Never leave streaming active
2. **Minimal delay between commands** - Don't wait longer than necessary for data
3. **Respect device battery** - Especially important for battery-powered operation during power outages
4. **Monitor shadow state** - Ensure `crockCommand` is cleared to `null` after operations

## Version History

- **v1.6.0 and earlier**: Missing `updates_off` - potential battery drain issue
- **v1.7.0 (planned)**: Adds `updates_off` after data collection to preserve battery
