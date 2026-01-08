# Moen Flo NAB Integration Tests

## Active Test Scripts

### monitor_mqtt.py
Real-time MQTT monitor for observing device shadow updates and streaming behavior.

**Usage:**
```bash
python tests/monitor_mqtt.py
```

**Features:**
- Connects to AWS IoT Core and subscribes to all shadow topics
- Displays real-time MQTT messages with timestamps
- Shows sensor streaming behavior (sens_on, updates_off commands)
- Useful for debugging and understanding device behavior

**Purpose:** Essential tool for monitoring MQTT traffic and verifying integration behavior.

---

### test_updates_off_integration.py
Tests the v1.7.0 battery preservation feature.

**Usage:**
```bash
python tests/test_updates_off_integration.py
```

**Features:**
- Simulates the coordinator update cycle
- Sends sens_on → collects data → sends updates_off
- Verifies crockCommand is cleared after data collection
- Confirms battery preservation implementation

**Purpose:** Validate that the integration properly stops sensor streaming after data collection.

---

### test_alert_sensor.py
Test script for validating alert processing logic.

**Usage:**
```bash
python tests/test_alert_sensor.py
```

**Features:**
- Displays all mapped alert codes with descriptions
- Processes example alert data to show sensor behavior
- Demonstrates how Last Alert sensor determines state
- Shows whether Flood Risk binary sensor would trigger

**Purpose:** Verify alert code mappings and sensor logic without requiring API access.

---

## Archived Test Scripts

The `archive/` folder contains diagnostic and development scripts that were useful during integration development but are not needed for regular use.

### v1.7.0 Battery Preservation Research (in archive/)
- `test_shadow_commands.py` - Tests REST API vs MQTT for triggering device
- `get_mqtt_credentials.py` - Helper to extract MQTT credentials
- `get_mqtt_credentials_standalone.py` - Standalone credential helper
- `mqtt_explorer_setup.py` - Setup guide for MQTT Explorer GUI
- `test_mqtt_boto3.py` - MQTT connection testing with boto3

### MQTT Development Scripts (in archive/)
- `test_mqtt_connection.py` - Initial MQTT exploration
- `test_mqtt_live.py` - Live MQTT testing with sens_on command
- `test_mqtt_continuous.py` - Continuous streaming duration test
- `test_sens_on_mqtt_trigger.py` - Testing sens_on via MQTT
- `test_continuous_streaming.py` - Measuring stream duration after sens_on
- `test_drop_on_command.py` - Testing drop_on command
- `test_drop_on_with_mqtt.py` - Combined drop_on + MQTT test

### Shadow API Development Scripts (in archive/)
- `test_auth_response.py` - Check authentication response structure
- `test_cached_vs_shadow.py` - Compare shadow vs cached endpoints
- `test_check_cached_value.py` - Quick cached value check
- `test_shadow_after_mqtt.py` - Verify shadow persistence after MQTT
- `test_sens_on_quick.py` - Quick sens_on command test
- `test_tof_trigger.py` - ToF sensor trigger testing
- `moen_nab_api_explorer.py` - Interactive API endpoint testing
- `compare_all_shadow_data.py` - Complete shadow vs cached data comparison
- `compare_shadow_vs_cached.py` - Water level data comparison
- `test_shadow_api_live.py` - Real-time shadow API monitoring
- `check_water_level_simple.py` - Quick water level diagnostic
- `debug_shadow_structure.py` - Shadow data structure analysis
- `test_shadow_workflow.py` - Shadow trigger/retrieve workflow test
- `test_live_shadow_integration.py` - Live integration testing

**Purpose:** These scripts were used during development to:
- Reverse-engineer the Moen API and AWS IoT integration
- Discover that device only responds when MQTT connection is active
- Prove that MQTT sen_on triggers fresh readings
- Measure continuous streaming behavior (~90 readings/minute for 2+ minutes)
- Validate shadow data persistence

---

## Requirements

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies for MQTT tests
pip install aiohttp python-dotenv boto3 awsiotsdk
```

## Environment Variables

Create a `.env` file in the project root:

```bash
MOEN_USERNAME=your_email@example.com
MOEN_PASSWORD=your_password
```

**Note:** The `.env` file is gitignored and will never be committed.

## Key Findings from Testing

### MQTT Discovery
1. **Device requires MQTT connection** - ToF sensor only updates when MQTT connection is active
2. **REST API shadow endpoint** - Cannot trigger device, only updates cloud shadow metadata
3. **MQTT shadow endpoint** - Returns fresh ToF data when sens_on command sent via MQTT
4. **Continuous streaming** - Single sens_on command streams ~1 reading/second indefinitely
5. **Battery preservation** - Must send updates_off to stop streaming (discovered in v1.7.0)
6. **Shadow persistence** - Fresh readings persist in shadow even after disconnect

### Integration Implementation (v1.7.0)
- **Normal operation**: Send sens_on → wait → collect data → send updates_off (every 5 minutes)
- **Alert mode**: Same sequence every 30 seconds when pump failures detected
- **Critical mode**: Same sequence every 10 seconds during high flood risk
- **Connection**: Persistent MQTT maintained throughout, reconnects if dropped
- **Fallback**: Uses REST API if MQTT unavailable (though triggering doesn't work via REST)
- **Battery preservation**: Always pairs sens_on with updates_off to stop streaming

## Test Output Files

Test scripts may generate JSON files containing API responses. These files are automatically gitignored to prevent committing sensitive data.

**Gitignored patterns:**
- `tests/*.json`
- `tests/*_test_*.json`
- `tests/*_exploration_*.json`
- `tests/output_*.json`
- `tests/archive/` (entire folder)

## Testing Best Practices

1. **Never commit sensitive data** - All JSON output files and archive folder are gitignored
2. **Use .env for credentials** - Never hardcode credentials in test scripts
3. **Check API responses** - Verify data structure hasn't changed
4. **Test authentication first** - Ensure credentials work before testing endpoints
5. **Respect rate limits** - Add delays between API calls if testing multiple endpoints

## Troubleshooting

### Authentication Errors
- Verify credentials in `.env` file
- Check if account requires 2FA (not currently supported)
- Ensure Moen account has access to NAB devices

### MQTT Connection Errors
- Verify `boto3` and `awsiotsdk` are installed
- Check internet connectivity to AWS IoT endpoint
- Ensure ID token is valid (re-authenticate if expired)

### API Endpoint Changes
- Moen may update their API without notice
- Check the latest API responses for structural changes
- Update integration code if endpoints change

### Missing Data
- Not all devices support all features (temperature/humidity sensors)
- Some fields may be null if device doesn't report them
- ToF readings only available via MQTT, not REST API
- Check device firmware version in Moen app
