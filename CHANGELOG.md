# Changelog

All notable changes to the Moen Flo NAB Home Assistant Integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.3.0] - 2026-01-11

### Added
- **Multiple Device Support** - Full support for multiple sump pump monitors:
  - Each NAB device gets its own complete set of sensors and binary sensors
  - Automatic filtering to only show NAB (sump pump monitor) devices
  - Ignores other Moen device types (e.g., water shutoff valves)
- **Multiple House/Location Support** - Devices linked to their houses:
  - Fetches house/location information from API
  - Device names prefixed with location (e.g., "My Home Sump Pump Monitor")
  - Proper device organization for multi-location setups
- **Dynamic Notification Descriptions** - Notification names fetched from API:
  - No longer hardcoded - pulls notification titles from event logs
  - Always matches current Moen app notification names
  - Automatically updates when Moen adds new notification types
  - Includes severity levels (critical, warning, info)
  - Falls back gracefully to hardcoded mappings if needed
- **Polling Period Diagnostic Sensor** - Shows current update interval:
  - Displays adaptive polling interval in seconds
  - Attributes show recent pump cycles and active alerts
  - Helps users understand integration's adaptive polling behavior
- **Pump Cycles Last 15 Minutes Diagnostic Sensor** - Tracks recent activity:
  - Counts pump cycles in the last 15 minutes
  - Attributes include timestamps of recent cycles
  - Useful for monitoring high-frequency pump activity
- **Dismiss All Notifications Button** - New button entity:
  - Allows dismissing all active alerts from Home Assistant
  - Attempts to acknowledge each active notification
  - Refreshes coordinator data after dismissal
  - Some notifications may not be dismissable by API

### Changed
- **Device Nicknames** - Now pulled from API `nickname` field instead of defaults
- **Entity Naming** - Devices now named as `{Location} {Nickname}` when location available
- **Notification Metadata** - Built dynamically from event logs, cached per device

### Fixed
- **Alert Code Mappings** - Updated with newly discovered notification IDs:
  - Alert 224: High Water Level (was "Unknown Alert")
  - Alert 225: Normal Water Level (new)
  - Alert 236: Sensor Too Close (new)
  - Alert 259: Flood Risk Cleared (new)
  - Alert 261: Main Pump Reset (new)
  - Alert 262: Main Pump Overwhelmed (was "Primary Pump Lagging")
  - Alert 263: Main Pump Recovered (new)
  - Alert 266: Main Pump Not Stopping (was from args)
  - Alert 267: Main Pump Stops Normally (new)
  - Alert 269: Backup Pump Reset (new)

### Technical Details
- Added `get_locations()` API method to fetch houses
- Added `get_notification_metadata()` to build ID-to-title mapping from event logs
- Coordinator caches notification metadata to avoid repeated API calls
- Button platform added to manifest and __init__.py
- NAB device filtering in coordinator update cycle
- Location linking via `locationId` field in device data
- Event log mining for notification titles (fetches 200 events)
- Dynamic descriptions with fallback to `ALERT_CODES` constant

### Documentation
- Added [NOTIFICATION_DISCOVERY.md](NOTIFICATION_DISCOVERY.md) - Details notification system implementation
- Added test scripts in tests/archive/ for API exploration
- Updated .gitignore to exclude deployment-specific files

## [1.8.2] - 2026-01-08

### Fixed
- **Last Alert Sensor Category** - Moved from Diagnostic to regular Sensors
  - Alert status is important user-facing information, not just diagnostic data
  - Sensor now appears in main sensors list instead of hidden diagnostic section
- **Integration Setup Naming** - Changed setup title from "Moen Flo NAB Setup" to "Moen Smart Sump Pump Monitor Setup"
  - Removes internal codename from user-facing configuration flow
  - Matches manifest name and product branding
- **Statistics Timestamp Format** - Normalized timestamps to top of hour
  - Home Assistant requires statistics timestamps with minutes and seconds = 0
  - Added automatic normalization: `cycle_time.replace(minute=0, second=0, microsecond=0)`
  - Fixes "Invalid timestamp: timestamps must be from the top of the hour" error
- **MQTT Connection Builder Blocking** - Additional blocking call fix
  - `mqtt_connection_builder.websockets_with_default_aws_signing()` performs blocking module imports
  - Created `_setup_mqtt_connection()` helper method
  - All MQTT connection setup now runs in executor thread
  - Fixes "Detected blocking call to listdir" warnings

## [1.8.1] - 2026-01-08

### Fixed
- **Hassfest Validation** - Added `recorder` to manifest dependencies
  - Required for long-term statistics functionality
  - Fixes integration validation error
- **Statistics ID Bug** - Fixed invalid statistic_id format
  - Device UUIDs with hyphens caused "Invalid statistic_id" error
  - Now converts hyphens to underscores in statistic IDs
  - Statistics will now import correctly on integration reload
- **MQTT Blocking Calls** - Fixed "blocking call to putrequest" errors
  - boto3 and AWS IoT SDK calls now run in executor threads
  - Prevents blocking Home Assistant's event loop
  - MQTT connections should now succeed reliably
  - Enables live water level readings from device ToF sensor

### Removed
- **Recent Volume Sensor** - Removed deprecated sensor entirely
  - Long-term statistics provide proper historical tracking
  - Use statistics entity or History/Statistics Graph cards for pump volume data
  - Sensor was replaced by statistics in v1.8.0

## [1.8.0] - 2026-01-08

### Added
- **Long-Term Statistics for Pump Volume** - Proper historical tracking with Energy Dashboard support:
  - Imports all available pump cycles (up to ~1000) on first load
  - Creates timestamped statistics for each pump cycle
  - Works with Home Assistant Energy Dashboard
  - Enables custom period graphs (daily, weekly, monthly, yearly)
  - Incremental updates - only imports new cycles after initial load
  - Automatically backfills historical data going back weeks
- **Basin Fullness Sensor** - New sensor showing how full the sump basin is (0-100%)
  - 100% = basin full (pump about to start)
  - 0% = basin empty (pump just finished)
  - Currently shows as unavailable until threshold learning is implemented (future enhancement)
  - Includes attributes: current_distance_mm, pump_on/off_distance_mm, calibration_cycles

### Changed
- **Water Level → Water Distance** - Renamed for clarity:
  - Sensor now called "Water Distance" instead of "Water Level"
  - More accurately describes measurement (distance from sensor to water)
  - Lower value = water closer to sensor (basin fuller)
  - Higher value = water farther from sensor (basin emptier)
  - Changed icon from `mdi:waves` to `mdi:arrow-expand-vertical`
  - Unique ID changed from `_water_level` to `_water_distance` (may show as new entity)
  - Added pump threshold attributes: pump_on_distance, pump_off_distance
- **Total Volume → Recent Volume** - Sensor behavior improved:
  - Renamed to "Recent Volume" to reflect actual behavior
  - Changed from `TOTAL_INCREASING` to `MEASUREMENT` state class
  - Now correctly shows volume from last 50 cycles only
  - Marked as diagnostic sensor (hidden by default)
  - No longer fluctuates incorrectly - for true cumulative totals, use statistics/Energy Dashboard

### Fixed
- **MQTT Client Import Error** - Restored missing MQTT client code in api.py:
  - Previous version accidentally reverted api.py to older version without MQTT support
  - Caused ImportError on Home Assistant startup
  - All MQTT functionality now properly restored

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
- **Water Distance Sensor Display** - Added `suggested_display_precision = 1`:
  - Water distance sensor now displays with 1 decimal place (e.g., "26.0 cm")
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
