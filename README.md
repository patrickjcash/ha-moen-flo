# Moen Smart Sump Pump Monitor - Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
![GitHub Release](https://img.shields.io/github/v/release/patrickjcash/ha-moen-flo?style=for-the-badge)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg?style=for-the-badge)
![License](https://img.shields.io/github/license/patrickjcash/ha-moen-flo?style=for-the-badge)
![IoT Class](https://img.shields.io/badge/IoT%20Class-Cloud%20Polling-blue.svg?style=for-the-badge)

A custom Home Assistant integration for the Moen Smart Sump Pump Monitor (model S2000ESUSA), providing real-time monitoring of water levels, temperature, humidity, pump health, and system status.

> **Note:** This device was previously branded as "Moen Flo Smart Sump Pump Monitor". The product line has been rebranded to simply "Moen Smart Sump Pump Monitor".

> **⚠️ IMPORTANT DISCLAIMER**
> This is an **unofficial integration** provided for **informational purposes only**. It may stop working at any time and should **NOT** be relied upon as a safety-critical monitoring system. See full [Disclaimer](#disclaimer) below. **Use at your own risk.**

## What's New in v2.4.0

🎯 **Intelligent Basin Fullness** - Persistent event-based threshold learning!

- Automatically detects pump ON/OFF events from water distance changes
- Learns thresholds over time with weighted averaging (adapts to seasonal changes)
- Works across days/weeks between pump cycles (not limited to recent readings)
- Two new diagnostic sensors show calculated pump ON/OFF distances

🛡️ **Improved Reliability** - Better error handling prevents update gaps!

- Authentication failures during MQTT reconnection no longer stop all updates
- Graceful fallback to REST API when MQTT issues occur
- Prevents multi-hour coordinator lockups from network hiccups

📊 **Enhanced Alert Organization** - Better filtering and automation!

- **Active Alerts** sensor shows count of all unacknowledged alerts (matches mobile app)
- **Critical Alerts** binary sensor triggers on unacknowledged critical-severity alerts
- **Warning Alerts** binary sensor triggers on unacknowledged warning-severity alerts
- **Flood Risk** sensor simplified to match device's flood risk assessment only
- Alert sensors now correctly count alerts that are resolved but not yet dismissed
- All alert details available as sensor attributes for custom dashboards

Plus all the features from v2.3.x:
- Multiple device & location support
- Dynamic notification descriptions from API
- MQTT connection stability with automatic credential refresh
- Pump cycles data with statistics integration
- Comprehensive monitoring and diagnostics

See the [CHANGELOG](CHANGELOG.md) for complete details.

## Features

### Sensors
- **Water Distance** - Distance from sensor to water surface (millimeters)
  - Lower value = water closer to sensor (basin fuller)
  - Higher value = water farther from sensor (basin emptier)
  - Includes attributes: distance_cm, water_trend, flood_risk, basin_diameter
- **Basin Fullness** - Percentage showing how full the sump basin is (0-100%)
  - 100% = basin full (pump about to start)
  - 0% = basin empty (pump just finished)
  - Automatically learns your basin's min/max distances from observed readings
  - Requires minimum 5 water distance readings to begin showing values
  - Attributes include current distance, pump on/off distances, and observation count
- **Temperature** - Ambient temperature in the sump pit (°F)
- **Humidity** - Relative humidity in the sump pit (%)
- **Daily Pump Capacity** - Percentage of daily pump capacity used
- **Last Pump Cycle** - Timestamp of the last pump cycle with detailed water in/out data

### Long-Term Statistics
- **Pump Volume Statistics** - Automatically imported for Energy Dashboard integration
  - **Three separate statistics**: Total Pump Volume, Primary Pump Volume, Backup Pump Volume
  - Track primary and backup pump usage independently
  - Historical pump volume with per-cycle granularity
  - Enables daily/weekly/monthly graphs
  - View in Energy Dashboard under "Water" category
  - Backfills weeks of historical data on first load
  - **See [Viewing Pump Volume Statistics](#viewing-pump-volume-statistics) below for access instructions**

### Binary Sensors
- **Flood Risk** - Reflects device's flood risk assessment (unknown, low, medium, high, critical)
- **Critical Alerts** - Triggers when critical-severity unacknowledged alerts are present
- **Warning Alerts** - Triggers when warning-severity unacknowledged alerts are present
- **Water Detection** - Detects water via the remote sensing cable (moisture sensor)

### Diagnostic Sensors
These sensors are hidden by default and provide technical device information:
- **Connectivity** - Device online/offline status with WiFi details
- **Battery Level** - Battery percentage and remaining life
- **WiFi Signal** - WiFi signal strength (RSSI in dBm)
- **AC Power** - Shows if device is on AC power or battery backup
- **Last Alert** - Most recent active alert with human-readable description

## Installation

### Prerequisites
- Home Assistant 2024.1 or newer
- A Moen Smart Sump Pump Monitor (S2000ESUSA) registered to your Moen account
- Your Moen account email and password

### Method 1: HACS (Recommended)

HACS (Home Assistant Community Store) makes installation and updates easy.

> **Note:** This integration is not yet published in the HACS default repository. You need to add it as a **custom repository** first.

1. **Install HACS** (if not already installed)
   - Follow the official HACS installation guide: https://hacs.xyz/docs/setup/download
   - Restart Home Assistant after HACS installation

2. **Add Custom Repository**

   [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=patrickjcash&repository=ha-moen-flo&category=integration)

   Click the badge above to add this repository to HACS directly, OR:
   - Open HACS in Home Assistant
   - Click the three dots menu (⋮) in the top right
   - Select "Custom repositories"
   - Add this repository URL: `https://github.com/patrickjcash/ha-moen-flo`
   - Select category: "Integration"
   - Click "Add"

3. **Install Integration**
   - In HACS, search for "Moen Smart Sump Pump Monitor"
   - Click on the integration
   - Click "Download"
   - Restart Home Assistant

### Method 2: Manual Installation

1. **Download Files**
   ```bash
   cd /config
   git clone https://github.com/patrickjcash/ha-moen-flo.git
   ```

2. **Copy Files**
   ```bash
   cp -r ha-moen-flo/custom_components/moen_sump_pump /config/custom_components/
   ```

   Your directory structure should look like:
   ```
   config/
   ├── custom_components/
   │   └── moen_sump_pump/
   │       ├── __init__.py
   │       ├── manifest.json
   │       ├── api.py
   │       ├── config_flow.py
   │       ├── sensor.py
   │       ├── binary_sensor.py
   │       ├── const.py
   │       └── strings.json
   ```

3. **Restart Home Assistant**

## Configuration

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=moen_sump_pump)

1. Click the badge above to add the integration directly, OR navigate to **Settings** → **Devices & Services**
2. Click the **+ Add Integration** button
3. Search for "Moen Smart Sump Pump Monitor"
4. Enter your Moen account email and password
5. Click **Submit**

The integration will automatically discover your devices and create all sensors.

### Verification

After setup, verify all entities are created:

**Sensors:**
- `sensor.sump_pump_water_distance`
- `sensor.sump_pump_basin_fullness`
- `sensor.sump_pump_temperature`
- `sensor.sump_pump_humidity`
- `sensor.sump_pump_daily_pump_capacity`
- `sensor.sump_pump_last_pump_cycle`

**Binary Sensors:**
- `binary_sensor.sump_pump_flood_risk`
- `binary_sensor.sump_pump_water_detection`

**Diagnostic Sensors (hidden by default):**
- `binary_sensor.sump_pump_connectivity`
- `binary_sensor.sump_pump_ac_power`
- `sensor.sump_pump_battery`
- `sensor.sump_pump_wifi_signal`
- `sensor.sump_pump_last_alert`

Wait 5 minutes for the first update cycle, then verify sensor values match what you see in the Moen mobile app.

## Usage

### Monitoring Water Levels
The water level sensor reports the distance from the sensor to the water surface in millimeters. A lower value means the water level is higher (closer to the sensor).

**Important Attributes:**
- `distance_cm` - Distance in centimeters for easier reading
- `water_trend` - rising/stable/receding
- `flood_risk` - Current flood risk level
- `basin_diameter_inches` - Diameter of the sump pit (inches)
- `basin_diameter_mm` - Diameter of the sump pit (millimeters)

### Pump Health Monitoring
The Daily Pump Capacity sensor shows what percentage of the pump's daily capacity has been used. This helps identify if your pump is being overworked.

### Detailed Cycle Data
The Last Pump Cycle sensor now includes comprehensive data about each pump operation:
- **Water In Rate** - How fast water is entering the basin (gallons per minute)
- **Water In Duration** - How long water was filling
- **Water Out Volume** - Exact gallons pumped out
- **Water Out Duration** - How long the pump ran
- **Backup Pump Status** - Whether backup pump was engaged

### Flood Risk Detection
The Flood Risk binary sensor activates when:
- Water level reaches the critical threshold
- **ANY active alert is present** on the device (pump failures, water detection, power outage, etc.)

The sensor uses live telemetry from the device's AWS IoT Shadow to detect issues in real-time. All active alerts are also exposed in the sensor's attributes for detailed troubleshooting.

### Water Detection
The Water Detection binary sensor monitors the optional remote sensing cable (moisture sensor). This is separate from the water level sensor in the sump pit. The sensing cable can detect water in areas away from the sump pit, such as:
- Floor drains
- Water heater pans
- Under washing machines
- Basement floors

When water contacts the sensing cable, the sensor will turn ON and remain ON until the water is cleared.

### Alert Monitoring
The **Last Alert** sensor shows the most recent active alert from your device in plain English:
- **"Primary Pump Failed"** - Primary pump has failed to engage
- **"Backup Pump Failed"** - Backup pump has failed to engage
- **"Water Detected"** - Remote sensing cable detected water
- **"Power Outage"** - Device is running on battery backup
- **"No active alerts"** - System is healthy

The sensor attributes provide detailed information about all active and recent inactive alerts, including:
- Alert timestamps
- Alert IDs and descriptions
- Full alert state information
- Up to 5 recent inactive alerts for historical context

**Supported Alert Codes:**
- 250: Water Detected
- 252: Water Was Detected (cleared)
- 254: Critical Flood Risk
- 256: High Flood Risk
- 258: Primary Pump Failed
- 260: Backup Pump Failed
- 262: Primary Pump Lagging
- 264: Backup Pump Lagging
- 266: Backup Pump Test Failed
- 268: Power Outage

Unknown alert codes are displayed as "Alert {code}" with full details preserved for troubleshooting.

### Diagnostic Sensors
Diagnostic sensors are automatically hidden in the UI but can be accessed through:
1. **Device Page**: Go to Settings → Devices & Services → Moen Flo NAB → Select your device
2. **Enable in UI**: Click on a diagnostic entity and enable "Show in UI" if you want it visible

These sensors are useful for:
- Monitoring device connectivity and WiFi strength
- Tracking battery health and remaining backup power
- Viewing active device alerts and system status
- Troubleshooting connection issues

### Viewing Pump Volume Statistics

The integration automatically imports pump volume history as **long-term statistics**, which enables historical tracking and graphing. Statistics are stored separately from sensors and accessed differently.

**Three separate statistics are available:**
- **Total Pump Volume** - All pump cycles combined
- **Primary Pump Volume** - Only cycles where primary pump ran alone
- **Backup Pump Volume** - Only cycles where backup pump engaged

#### Where to Find Statistics:

**Option 1: Energy Dashboard (Recommended)**
1. Navigate to **Settings** → **Dashboards** → **Energy**
2. Click **Add Consumption** in the Water section
3. Select the statistic(s) for your device (e.g., `Sump Pump Total Pump Volume`, `Sump Pump Primary Pump Volume`, `Sump Pump Backup Pump Volume`)
4. View daily, weekly, monthly, or yearly pump usage
5. Compare primary vs backup pump activity over time

**Option 2: History Panel**
1. Navigate to **History** (sidebar or `/history`)
2. Click the entity selection dropdown
3. Search for your device name (e.g., "Sump Pump")
4. Select the **statistic** (not sensor) - it will have a chart icon
5. Adjust time range to view historical data

**Option 3: Statistics Graph Card**
Add a Statistics Graph card to any dashboard:
```yaml
type: statistics-graph
entities:
  - sensor.sump_pump_water_volume
stat_types:
  - sum
period: day
```

**Option 4: Developer Tools**
1. Navigate to **Developer Tools** → **Statistics**
2. Search for your device name or "pump_volume"
3. View raw statistics data and metadata

#### Important Notes:
- **Statistics ≠ Sensors**: Statistics are stored in Home Assistant's long-term recorder database, separate from sensor entities
- **Search by Device Name**: Look for your device name (e.g., "Sump Pump Water Volume"), not "pump_volume"
- **Reload Integration**: After first installation, reload the integration to trigger statistics import
- **Historical Data**: The integration automatically backfills weeks of historical pump cycles on first load
- **Incremental Updates**: New pump cycles are automatically added to statistics during each update

### Automations

#### Example: Alert Notification (Any Issue)
```yaml
automation:
  - alias: "Sump Pump Alert Detected"
    trigger:
      - platform: state
        entity_id: binary_sensor.sump_pump_flood_risk
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ Sump Pump Alert!"
          message: "{{ states('sensor.sump_pump_last_alert') }}"
          data:
            priority: high
```

#### Example: Specific Alert Type (Pump Failure)
```yaml
automation:
  - alias: "Pump Failure Critical Alert"
    trigger:
      - platform: state
        entity_id: sensor.sump_pump_last_alert
    condition:
      - condition: or
        conditions:
          - condition: state
            entity_id: sensor.sump_pump_last_alert
            state: "Primary Pump Failed"
          - condition: state
            entity_id: sensor.sump_pump_last_alert
            state: "Backup Pump Failed"
    action:
      - service: notify.mobile_app
        data:
          title: "🚨 PUMP FAILURE!"
          message: "{{ states('sensor.sump_pump_last_alert') }} - Check immediately!"
          data:
            priority: high
            tag: "pump_failure"
```

#### Example: Water Detection Alert
```yaml
automation:
  - alias: "Water Detected by Sensing Cable"
    trigger:
      - platform: state
        entity_id: binary_sensor.sump_pump_water_detection
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "💧 Water Detected!"
          message: "Remote sensing cable has detected water"
          data:
            priority: high
```

#### Example: Pump Overwork Warning
```yaml
automation:
  - alias: "Sump Pump Overworked"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sump_pump_daily_pump_capacity
        above: 75
    action:
      - service: notify.mobile_app
        data:
          title: "Pump Running Frequently"
          message: "Sump pump has used {{ states('sensor.sump_pump_daily_pump_capacity') }}% of daily capacity"
```

#### Example: Power Loss Alert
```yaml
automation:
  - alias: "Sump Pump Power Loss"
    trigger:
      - platform: state
        entity_id: binary_sensor.sump_pump_ac_power
        to: "off"
    action:
      - service: notify.mobile_app
        data:
          title: "⚡ Sump Pump Power Loss"
          message: "Sump pump is running on battery backup"
```

#### Example: Temperature Monitoring
```yaml
automation:
  - alias: "Sump Pit Temperature Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sump_pump_temperature
        below: 40
    action:
      - service: notify.mobile_app
        data:
          title: "🥶 Low Temperature Alert"
          message: "Sump pit temperature is {{ states('sensor.sump_pump_temperature') }}°F - freeze risk"
```

#### Example: Low Battery Alert
```yaml
automation:
  - alias: "Sump Pump Low Battery"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sump_pump_battery
        below: 20
    action:
      - service: notify.mobile_app
        data:
          title: "🔋 Low Battery Alert"
          message: "Sump pump monitor battery is at {{ states('sensor.sump_pump_battery') }}%"
```

#### Example: WiFi Connection Issue
```yaml
automation:
  - alias: "Sump Pump WiFi Weak Signal"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sump_pump_wifi_signal
        below: -80
        for:
          minutes: 10
    action:
      - service: notify.mobile_app
        data:
          title: "📶 Weak WiFi Signal"
          message: "Sump pump monitor has weak WiFi signal ({{ states('sensor.sump_pump_wifi_signal') }} dBm)"
```

## API Details

This integration uses the Moen API with AWS Cognito authentication. The API backend is shared with the "Flo" branded devices but uses a different authentication pool.

> **Developer Note:** The API internally uses the term "NAB" (Network Attached Basin) for this device type in endpoint names and identifiers. This is not user-facing and is maintained in the code for clarity when working with the API.

### Dual ID System
The API uses two different IDs for the same device:
- **UUID (`duid`)** - Used for device lists and event logs
- **Numeric ID (`clientId`)** - Used for telemetry and usage statistics

### Endpoints
- **Authentication**: AWS Cognito User Pool
- **Device List**: `smartwater-app-device-api-prod-list`
- **Live Telemetry (Shadow API)**: `smartwater-app-shadow-api-prod-get` / `smartwater-app-shadow-api-prod-update`
- **Environment Data**: `fbgpg_usage_v1_get_device_environment_latest_prod` (Temperature/Humidity)
- **Pump Health**: `fbgpg_usage_v1_get_my_usage_device_history_top10_prod`
- **Pump Cycles**: `fbgpg_usage_v1_get_my_usage_device_history_prod` (Detailed cycle data)
- **Event Logs**: `fbgpg_logs_v1_get_device_logs_user_prod`

### Live Telemetry via AWS IoT Shadow
The integration uses the **AWS IoT Device Shadow** API to retrieve real-time sensor readings:

1. **Shadow Update Trigger**: Sends `sens_on` command to device via shadow update endpoint
2. **Wait Period**: Waits 3 seconds for device to take fresh sensor readings
3. **Shadow Retrieval**: Retrieves live telemetry from `state.reported` in device shadow
4. **Data Merge**: Merges fresh shadow data (water level, alerts, connectivity, etc.) with cached device data

This ensures water level readings and alert states are always current, not stale cached values. The shadow API was discovered through reverse engineering the Moen mobile app.

### Update Interval
The integration polls the API every 5 minutes by default. Each update:
- Triggers the device to take fresh sensor readings
- Retrieves live telemetry from AWS IoT Shadow
- Updates all sensor values with the latest data

This balances data freshness with API rate limits and device sensor lifespan.

## Troubleshooting

### Integration Not Loading
- Check Home Assistant logs for errors: **Settings** → **System** → **Logs**
- Verify your credentials are correct
- Ensure your Moen account has access to the device

### Sensors Showing "Unknown" or "Unavailable"
- Wait for the next update cycle (5 minutes)
- Check that your device is online in the Moen app
- Verify device is reporting data (some fields may not be available on all models)

### Authentication Errors
- Verify your email and password are correct
- Try logging into the Moen mobile app to confirm credentials
- Check if your account requires 2FA (not currently supported)

### Temperature/Humidity Not Updating
- Ensure your device model supports these sensors
- Check the device data in the coordinator debug logs
- Some devices may not report temperature/humidity if sensors are not present

## Supported Devices

This integration is designed for the **Moen Smart Sump Pump Monitor (model S2000ESUSA)**. It will not work with:
- Moen Smart Water Monitor (different API)
- Moen Smart Water Shutoff (different API)
- Other Flo-branded water devices (different API)

## Data Privacy

This integration:
- Stores your Moen credentials in Home Assistant's secure storage
- Communicates directly with Moen's API (no third-party servers)
- Does not collect or transmit any data outside your Home Assistant instance

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## Support

For issues, questions, or feature requests:
- Open an issue on GitHub
- Check existing issues for similar problems
- Provide Home Assistant logs when reporting bugs

## Credits

This integration was developed through reverse engineering of the Moen Flo mobile app API. Special thanks to the Home Assistant community for their support and guidance.

## License

This project is licensed under the MIT License - see LICENSE file for details.

## Disclaimer

**IMPORTANT: READ BEFORE USE**

This is an **unofficial, community-developed integration** and is:
- **NOT affiliated with, endorsed by, or supported by** Moen or Fortune Brands Home & Security, Inc.
- Provided "AS IS" without warranty of any kind, express or implied
- **FOR INFORMATIONAL PURPOSES ONLY** - not intended as a safety-critical system
- May stop working at any time due to API changes, device firmware updates, or service modifications

### Limitation of Liability

**THE AUTHORS AND CONTRIBUTORS OF THIS INTEGRATION SHALL NOT BE LIABLE FOR:**
- Any damages, losses, or injuries resulting from the use or inability to use this integration
- Failures to detect water levels, pump malfunctions, flooding, or any other hazardous conditions
- Data loss, property damage, or any consequential damages
- Any reliance placed on this integration for safety or critical monitoring

**YOU ASSUME ALL RISK** associated with the use of this integration. This software is provided for convenience and informational purposes only. **DO NOT rely solely on this integration for critical monitoring or safety applications.**

### No Warranty

This integration may:
- Stop functioning without notice due to API changes
- Provide inaccurate or delayed information
- Fail to alert you to critical conditions
- Experience bugs, errors, or unexpected behavior

**Always maintain proper physical monitoring and safety systems for your sump pump and water detection needs.**

### Use at Your Own Risk

By using this integration, you acknowledge and agree that:
1. You understand this is unofficial software reverse-engineered from the Moen API
2. The integration may break at any time without warning
3. You will not hold the authors liable for any damages or losses
4. You are responsible for implementing proper backup monitoring systems
5. This integration does not replace professional water detection or sump pump monitoring systems
