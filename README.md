# Moen Smart Sump Pump Monitor - Home Assistant Integration

A custom Home Assistant integration for the Moen Smart Sump Pump Monitor (model S2000ESUSA), providing real-time monitoring of water levels, temperature, humidity, pump health, and system status.

> **Note:** This device was previously branded as "Moen Flo Smart Sump Pump Monitor". The product line has been rebranded to simply "Moen Smart Sump Pump Monitor".

> **⚠️ IMPORTANT DISCLAIMER**
> This is an **unofficial integration** provided for **informational purposes only**. It may stop working at any time and should **NOT** be relied upon as a safety-critical monitoring system. See full [Disclaimer](#disclaimer) below. **Use at your own risk.**

## Features

### Sensors
- **Water Level** - Distance from sensor to water surface (millimeters)
- **Temperature** - Ambient temperature in the sump pit (°F)
- **Humidity** - Relative humidity in the sump pit (%)
- **Daily Pump Capacity** - Percentage of daily pump capacity used
- **Last Pump Cycle** - Timestamp of the last pump cycle with detailed water in/out data

### Binary Sensors
- **Flood Risk** - Alerts when water level reaches critical thresholds
- **Water Detection** - Detects water via the remote sensing cable (moisture sensor)

### Diagnostic Sensors
These sensors are hidden by default and provide technical device information:
- **Connectivity** - Device online/offline status with WiFi details
- **Battery Level** - Battery percentage and remaining life
- **WiFi Signal** - WiFi signal strength (RSSI in dBm)
- **AC Power** - Shows if device is on AC power or battery backup

## Installation

### HACS (Recommended)
1. Add this repository as a custom repository in HACS
2. Search for "Moen Smart Sump Pump Monitor" in HACS
3. Click "Install"
4. Restart Home Assistant

### Manual Installation
1. Copy the `custom_components/moen_flo_nab` directory to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

### Via UI (Recommended)
1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Moen Smart Sump Pump Monitor"
4. Enter your Moen account email and password
5. Click **Submit**

The integration will automatically discover your devices and create all sensors.

### Via YAML (Not Supported)
This integration only supports configuration through the UI.

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
- Active flood alerts are present on the device

### Water Detection
The Water Detection binary sensor monitors the optional remote sensing cable (moisture sensor). This is separate from the water level sensor in the sump pit. The sensing cable can detect water in areas away from the sump pit, such as:
- Floor drains
- Water heater pans
- Under washing machines
- Basement floors

When water contacts the sensing cable, the sensor will turn ON and remain ON until the water is cleared.

### Diagnostic Sensors
Diagnostic sensors are automatically hidden in the UI but can be accessed through:
1. **Device Page**: Go to Settings → Devices & Services → Moen Flo NAB → Select your device
2. **Enable in UI**: Click on a diagnostic entity and enable "Show in UI" if you want it visible

These sensors are useful for:
- Monitoring device connectivity and WiFi strength
- Tracking battery health and remaining backup power
- Troubleshooting connection issues

### Automations

#### Example: Flood Alert Notification
```yaml
automation:
  - alias: "Sump Pump Flood Risk Alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.sump_pump_flood_risk
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ Flood Risk Detected!"
          message: "Water level in sump pit is critically high"
          data:
            priority: high
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
- **Environment Data**: `fbgpg_usage_v1_get_device_environment_latest_prod` (Temperature/Humidity)
- **Pump Health**: `fbgpg_usage_v1_get_my_usage_device_history_top10_prod`
- **Pump Cycles**: `fbgpg_usage_v1_get_my_usage_device_history_prod` (Detailed cycle data)
- **Event Logs**: `fbgpg_logs_v1_get_device_logs_user_prod`

### Update Interval
The integration polls the API every 5 minutes by default. This balances data freshness with API rate limits.

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
