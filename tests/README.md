# Moen Flo NAB Integration Tests

This directory contains test and diagnostic scripts for the Moen Smart Sump Pump Monitor integration.

## Active Test Scripts

### monitor_mqtt.py
Real-time MQTT monitor for observing device shadow updates and streaming behavior.

**Usage:**
```bash
. .venv/bin/activate
python tests/monitor_mqtt.py
```

**Features:**
- Connects to AWS IoT Core and subscribes to all shadow topics
- Displays real-time MQTT messages with timestamps
- Shows sensor streaming behavior (sens_on, updates_off commands)
- Monitors water level changes in real-time

**Purpose:** Essential tool for monitoring MQTT traffic and verifying integration behavior.

---

### debug_pump_cycles_sensor.py
Validates pump cycles API and sensor data.

**Usage:**
```bash
. .venv/bin/activate
python tests/debug_pump_cycles_sensor.py
```

**Features:**
- Fetches last 50 pump cycles from API
- Analyzes cycles in last 15 minutes
- Verifies timestamp parsing and timezone handling
- Shows volume and duration data for each cycle

**Purpose:** Validate pump cycles API is working and data is being returned correctly.

---

### debug_pump_thresholds.py
Analyzes pump cycle data structure for threshold calculation.

**Usage:**
```bash
. .venv/bin/activate
python tests/debug_pump_thresholds.py
```

**Features:**
- Examines pump cycle API response structure
- Searches for water level/distance data in cycles
- Proves that cycle data doesn't contain water sensor readings
- Documents why Option D (extract from API) isn't viable for basin fullness

**Purpose:** Research script that proves pump cycle API doesn't contain water distance data, leading to event-based detection approach in v2.4.0.

---

### test_correct_acknowledge.py
Working example of alert acknowledgment via API (v1 endpoint).

**Usage:**
```bash
. .venv/bin/activate
python tests/test_correct_acknowledge.py
```

**Features:**
- Demonstrates proper alert acknowledgment workflow using v1 API
- Uses `fbgpg_alerts_v1_silence_alert_prod` endpoint with pathParameters format
- Uses numeric client ID (not UUID) as required by v1 API
- Shows alert state before/after acknowledgment
- Working reference implementation

**Purpose:** Reference implementation for alert dismissal functionality. This script validates that the v1 silence/acknowledge endpoint successfully removes dismissible alerts from the active alerts list.

**Note:** The v1 `silence_alert` and `acknowledge_alert` endpoints are functionally identical.

---

## Requirements

```bash
# Create virtual environment (if not already created)
python3 -m venv .venv

# Activate it
. .venv/bin/activate

# Install dependencies
pip install aiohttp python-dotenv boto3 awsiotsdk requests
```

## Environment Variables

Create a `.env` file in the project root:

```bash
MOEN_USERNAME=your_email@example.com
MOEN_PASSWORD=your_password
```

**Note:** The `.env` file is gitignored and will never be committed.

## Key Findings

### MQTT Discovery
1. **Device requires MQTT connection** - ToF sensor only updates when MQTT connection is active
2. **REST API limitation** - Cannot trigger device, only retrieves cached shadow data
3. **Continuous streaming** - Single sens_on command streams readings indefinitely until updates_off
4. **Battery preservation** - Integration sends updates_off after data collection to prevent battery drain

### Integration Behavior
- **Normal operation**: Send sens_on → wait 2s → collect data → send updates_off
- **Update frequency**: Adaptive polling (10s to 300s based on pump activity and alerts)
- **MQTT connection**: Persistent connection with automatic credential refresh (v2.3.2)
- **Fallback**: Uses REST API if MQTT unavailable

### v2.4.0 Changes
- **Basin Fullness**: Event-based threshold detection (detects pump ON/OFF from distance changes)
- **Error Handling**: Improved coordinator error handling prevents multi-hour update gaps
- **Alert Sensors**: New Critical/Warning binary sensors, Active Alerts count sensor

### v2.4.1 Changes (Alert Dismissal Fix)
- **Alert Dismissal**: Fixed "Dismiss Alerts" button using correct v1 acknowledge endpoint
- **Alert Source**: Integration now uses v2 ACTIVE alerts API (matches mobile app behavior)
- **API Discovery**: Identified that `fbgpg_alerts_v1_acknowledge_alert_prod` with pathParameters is the correct dismissal method
- **Endpoint Behavior**: ACTIVE endpoint returns all unacknowledged alerts, CURRENT endpoint returns only dismissible inactive alerts

## Test Output Files

Test scripts may generate JSON files containing API responses. These are automatically gitignored to prevent committing sensitive data.

**Gitignored patterns:**
- `tests/*.json`
- `tests/*_test_*.json`
- `tests/archive/` (entire folder with historical test scripts)

## Troubleshooting

### Authentication Errors
- Verify credentials in `.env` file
- Check if account requires 2FA (not currently supported)
- Ensure Moen account has access to NAB devices

### MQTT Connection Errors
- Verify `boto3` and `awsiotsdk` are installed
- Check internet connectivity to AWS IoT endpoint
- Ensure ID token is valid (re-authenticate if expired)

### Missing Data
- Not all devices support all features (temperature/humidity sensors)
- ToF readings only available via MQTT, not REST API
- Check device firmware version in Moen app

## Contributing

When creating new test scripts:
1. Use `.venv` virtual environment
2. Load credentials from `.env` file (never hardcode)
3. Add clear docstrings and comments
4. Update this README with script purpose and usage
5. Ensure output files are in gitignore patterns
