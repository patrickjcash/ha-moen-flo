# Changelog

All notable changes to the Moen Flo NAB Home Assistant Integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.7.0] - 2026-01-08

### Added
- **Battery Preservation** - Automatic streaming shutdown after data collection:
  - Sends `updates_off` command after each `sens_on` trigger
  - Prevents continuous sensor streaming which drains battery
  - Mirrors Moen mobile app behavior (stops streaming when exiting Fine Tuning screen)
  - Applied to both MQTT and REST API fallback paths

### Changed
- **Integration Classification** - Changed `iot_class` from `cloud_push` to `cloud_polling`:
  - More accurately reflects polling-based architecture
  - Integration triggers updates every 5 minutes (normal operation)
  - Adaptive polling during alerts (30s for alerts, 10s for critical)
  - MQTT connection used for triggering only, not push notifications
- **Water Level Sensor Display** - Added `suggested_display_precision = 1`:
  - Water level sensor now displays with 1 decimal place (e.g., "26.0 cm")
  - Improves readability while maintaining millimeter precision in state

### Fixed
- **Battery Drain Issue** - Resolved continuous streaming after sensor updates:
  - Previous versions left device streaming indefinitely after `sens_on` command
  - Device was streaming ~1 update/second continuously, draining battery
  - Now properly stops streaming after collecting required data sample

### Technical Details
- Added `updates_off` command in [__init__.py:134](custom_components/moen_flo_nab/__init__.py#L134) (MQTT path)
- Added `updates_off` command in [__init__.py:175](custom_components/moen_flo_nab/__init__.py#L175) (REST fallback path)
- Verified REST API cannot trigger device (MQTT required) - see [MQTT_STREAMING_BEHAVIOR.md](docs/MQTT_STREAMING_BEHAVIOR.md#L144)
- Command sequence: `sens_on` → wait 2-3s → collect data → `updates_off`

### Background
Through MQTT monitoring, we discovered:
- `sens_on` triggers continuous ToF sensor streaming at ~1 Hz
- Streaming continues indefinitely until `updates_off` is sent
- Moen mobile app always sends `updates_off` when closing Fine Tuning page
- Continuous streaming significantly impacts battery life during power outages
- See detailed analysis in [docs/MQTT_STREAMING_BEHAVIOR.md](docs/MQTT_STREAMING_BEHAVIOR.md)

## [1.6.0] - 2026-01-07

### Added
- **Last Alert Sensor** - New diagnostic sensor showing the most recent active alert:
  - Displays human-readable alert description (e.g., "Primary Pump Failed")
  - Shows "No active alerts" when system is healthy
  - Attributes include all active alerts with timestamps and details
  - Includes up to 5 recent inactive alerts for historical context
  - Alert codes mapped from decompiled Moen app strings

### Changed
- **Flood Risk Binary Sensor** - Enhanced to properly detect all alert conditions:
  - Now triggers on ANY active alert (pump failures, water detection, etc.)
  - Improved alert state detection logic (checks for "active" without "inactive")
  - More accurate flood risk detection based on actual device state
  - Added documentation of common alert codes in sensor

### Fixed
- **Alert Code Mappings** - Corrected alert ID interpretations:
  - Alert 258 = Primary Pump Failed (not "Flood Risk")
  - Alert 260 = Backup Pump Failed
  - Alert 250 = Water Detected (remote sensing cable)
  - Alert 266 = Backup Pump Test Failed
  - Alert 268 = Power Outage (device on battery)

### Technical Details
- Added `ALERT_CODES` constant mapping common NAB alert IDs to descriptions
- Alert mappings extracted from decompiled Moen mobile app `strings.xml`
- Alert sensor processes both active and inactive alerts from shadow/device data
- Flood risk sensor no longer relies on incorrect alert ID filtering

## [1.5.0] - 2026-01-07

### Added
- **Live Sensor Readings via AWS IoT Shadow** - MAJOR UPDATE:
  - Integration now triggers device to take fresh sensor readings every update cycle
  - Implemented shadow API (`update_shadow` and `get_shadow`) for live telemetry
  - Water level sensor now receives real-time readings instead of stale cached data
  - All telemetry sensors updated with live data from device shadow

### Changed
- **Update Strategy** - Each coordinator update now:
  1. Sends `sens_on` command to trigger fresh sensor readings
  2. Waits 3 seconds for device to respond
  3. Retrieves live data from AWS IoT Device Shadow
  4. Merges fresh telemetry into device info
- **Live Data Fields** - The following sensors now use real-time shadow data:
  - Water level (`crockTofDistance`)
  - Flood risk analysis (`droplet`)
  - Connection status (`connected`)
  - WiFi signal strength (`wifiRssi`)
  - Battery level (`batteryPercentage`)
  - Power source (`powerSource`)
  - Device alerts (`alerts`)

### Technical Details
- Added `update_shadow()` API method to send device commands
- Added `get_shadow()` API method to retrieve AWS IoT Shadow state
- Coordinator triggers `sens_on` command via shadow update endpoint
- Shadow data structure: `state.reported` contains live sensor readings
- Implemented fallback to cached data if shadow update fails
- Added debug logging for shadow data updates

### Background
Through reverse engineering the Moen mobile app, we discovered that:
- Water level readings were only updating when "Fine Tune Device" page was opened in app
- The app sends a shadow update command (`crockCommand: "sens_on"`) to trigger fresh readings
- Both device list API and shadow API return cached data until device is triggered
- The solution requires actively requesting fresh readings, then retrieving them from shadow

## [1.2.0] - 2025-12-29

### Added
- **Diagnostic Sensors** - Following Home Assistant best practices:
  - Battery level sensor with power source and remaining life attributes
  - WiFi signal strength sensor (RSSI in dBm) with network name and MAC address
  - Connectivity sensor now marked as diagnostic (auto-hidden in UI)
- **HACS Metadata** - Added standard HACS configuration:
  - Minimum Home Assistant version requirement (2024.1.0)
  - Proper HACS.json configuration
- **Enhanced Documentation**:
  - Diagnostic sensors section with access instructions
  - New automation examples for battery and WiFi monitoring
  - Updated feature list with diagnostic sensor category

### Fixed
- **DateTime Timezone Issue** - Fixed "Invalid datetime: missing timezone information" error
  - Last Pump Cycle sensor now properly provides timezone-aware datetime (UTC)
  - Added timezone import and handling to ensure Home Assistant compatibility

### Changed
- Connectivity sensor moved from main binary sensors to diagnostic category
- Improved README structure with dedicated diagnostic sensors section

### Technical Details
- Added `EntityCategory.DIAGNOSTIC` to appropriate sensors
- Imported `SIGNAL_STRENGTH_DECIBELS_MILLIWATT` constant for WiFi sensor
- Ensured all datetime objects include timezone information using `datetime.timezone.utc`

## [1.1.0] - 2024-12-29

### Added
- Pump cycle history tracking with detailed water in/out data

## [1.0.0] - 2024-12-29

### Added
- Initial release of Moen Flo NAB integration
- AWS Cognito authentication support
- Lambda function invoker client
- Config flow for UI-based setup
- Water level sensor with critical thresholds (millimeters)
- Temperature sensor (Fahrenheit)
- Humidity sensor (percentage)
- Daily pump capacity sensor
- **Enhanced last pump cycle sensor with comprehensive cycle data:**
  - Water inflow rate (gallons per minute)
  - Water inflow duration (milliseconds)
  - Water pumped out volume (gallons)
  - Pump run duration (milliseconds)
  - Backup pump engagement status
- Connectivity binary sensor
- Flood risk binary sensor with detailed attributes
- AC power/battery status binary sensor
- Automatic device discovery
- 5-minute polling interval
- Comprehensive error handling
- Token refresh management
- Support for multiple devices
- Complete API documentation
- Installation guides (HACS and manual)
- User documentation with automation examples

### Technical Details
- Implemented dual ID system (UUID and numeric clientId)
- **BREAKTHROUGH: Discovered pump cycle endpoint using `type: "session"` parameter**
- Water level sensor uses millimeters with cm conversion in attributes
- Enhanced sensor attributes with water trend, flood risk levels, and basin diameter
- Proper async/await architecture
- Home Assistant 2023.1+ compatibility
- Type hints and docstrings
- Comprehensive logging

### Major API Discoveries
- **Gallons per cycle** - NOW AVAILABLE via pump cycles endpoint
- **Cycle durations** - NOW AVAILABLE (fill time and pump run time)
- **Water inflow rate** - NOW AVAILABLE (gallons per minute)
- **Backup pump status** - NOW AVAILABLE per cycle

### Known Limitations
- Historical water level data not available (only current level)
- 2FA not currently supported
- Real-time streaming not available (poll-based only)

## [Unreleased]

### Planned Features
- Integration diagnostics
- Configurable polling interval via options flow
- Historical data storage and graphing for pump cycles
- Additional Lambda function exploration
- Real-time push notifications (if API supports)
- Separate sensors for water in/out metrics (currently in attributes)

### Under Consideration
- Manual pump control services (if API permits)
- Advanced analytics and predictions
- Multi-language support
- Custom card for Lovelace UI

---

## Version History Notes

### Version Numbering
- **Major version** (X.0.0): Breaking changes, significant new features
- **Minor version** (1.X.0): New features, backward compatible
- **Patch version** (1.0.X): Bug fixes, minor improvements

### Upgrade Notes

#### From Nothing to 1.0.0
This is the initial release. Follow the installation guide in INSTALLATION.md.

---

## Contributing

We welcome contributions! Please see our contributing guidelines for:
- Bug reports
- Feature requests
- Pull requests
- Documentation improvements

Report issues at: https://github.com/yourusername/ha-moen-flo-nab/issues

---

[1.0.0]: https://github.com/yourusername/ha-moen-flo-nab/releases/tag/v1.0.0
[Unreleased]: https://github.com/yourusername/ha-moen-flo-nab/compare/v1.0.0...HEAD
