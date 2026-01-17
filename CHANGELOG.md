# Changelog

All notable changes to the Moen Flo NAB Home Assistant Integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.4.8] - 2026-01-17

### Fixed
- **Distance History Not Persisting Across Restarts** - Critical bug preventing event detection after restarts:
  - Root cause: `_distance_history` was only stored in memory, not persisted to storage
  - Impact: After any Home Assistant restart, history would reset to empty `{}`
  - Detection requires at least 2 readings in history, so first reading after restart would be skipped
  - If HA restarted between pump cycles, detection would never accumulate enough history
  - Fix: Added `_distance_history` to persistent storage alongside `_pump_thresholds`
  - History now saved after each MQTT update to ensure survival across restarts
  - Storage schema updated to: `{"thresholds": {...}, "distance_history": {...}}`

### Technical Details
- Updated `async_load_thresholds()` to load both thresholds and distance history
- Updated `async_save_thresholds()` to save both thresholds and distance history
- Added save call after every distance reading update (line 522)
- Distance history now properly accumulates across multiple HA restart cycles

## [2.4.7] - 2026-01-16

### Fixed
- **Pump Event Detection Not Triggering** - Rewrote event detection to be more reliable:
  - Root cause: Consecutive-only comparison could miss pump events in certain scenarios
  - Old approach: Compared only against the immediately previous reading stored in `_previous_distance`
  - New approach: Maintains history of last 24 readings and compares current reading against ALL previous readings
  - This makes detection robust to edge cases where consecutive comparison fails
  - Removed time window constraints (was 5s-600s) - now works regardless of polling interval
  - Still uses 50mm threshold for detecting significant water level changes
  - Example: Now successfully detects 218mm → 357mm (139mm jump) that was missed before

### Added
- **Persistent Storage for Pump Thresholds** - Thresholds now survive Home Assistant restarts:
  - Pump ON/OFF distance thresholds are now saved to persistent storage
  - Automatically loads saved thresholds on startup
  - Saves thresholds whenever pump events are detected
  - Storage uses Home Assistant's Store with key `moen_sump_pump_thresholds`
  - Prevents having to re-learn thresholds after HA restarts

### Technical Details
- Replaced `_previous_distance` dict with `_distance_history` that stores last 24 readings per device
- Event detection now loops through all historical readings to find 50mm+ changes
- Added `async_load_thresholds()` and `async_save_thresholds()` methods
- Storage version 1 with schema: `{"thresholds": {device_duid: {...}}}`
- Thresholds are saved asynchronously using `hass.async_create_task()` from sync context

## [2.4.6] - 2026-01-15

### Fixed
- **Pump Threshold Sensors Updating Incorrectly** - Removed fallback logic causing false updates:
  - Root cause: Min/max fallback logic was updating thresholds based on slow drift in water level history
  - Fallback used `min(history)` and `max(history)` from last 100 readings, which changed as water slowly drifted over hours
  - This caused thresholds to update at random times when there was NO actual pump event
  - Removed fallback logic entirely - sensors now show "Unknown" until first real pump event detected
  - Thresholds only update when actual pump events are detected (50mm+ change in 5s-10min)
  - Prevents spurious threshold updates from gradual drift over hours/days

### Technical Details
- Removed min/max fallback logic from `_calculate_pump_thresholds()` (lines 594-613)
- Removed `_water_distance_history` tracking (no longer needed without fallback logic)
- Removed arbitrary 100-reading history limit that couldn't handle weeks between pump cycles
- Sensors now return empty dict (Unknown) if no pump events detected yet
- Event detection uses 50mm threshold with 5s-10min time window
- Once learned, thresholds persist indefinitely using weighted averaging (80% old, 20% new)
- Event detection compares consecutive readings only - works regardless of time between pump cycles

## [2.4.5] - 2026-01-15

### Fixed
- **Pump Event Detection Too Sensitive** - Increased threshold to reduce false triggers from noise:
  - Root cause: 15mm threshold was catching noise/oscillations as pump events
  - Increased threshold from ±15mm to ±50mm for pump event detection
  - Only real pump cycles (significant water level changes) trigger threshold updates
  - Prevents spurious updates from local minima/maxima in noisy readings
  - Improved logging to show actual distance change magnitude

### Technical Details
- Updated event detection thresholds in `_detect_pump_events()` (lines 523, 542)
- Pump ON: now requires >50mm drop (was 15mm)
- Pump OFF: now requires >50mm jump (was 15mm)
- Added distance change magnitude to log messages for debugging
- Changed debug logs to info level for event detection visibility

## [2.4.4] - 2026-01-14

### Fixed
- **Pump ON/OFF Distance Sensors Showing Unknown** - Fixed sensors displaying "Unknown" instead of threshold values:
  - Root cause: `continue` statements in MQTT telemetry section skipped entire device update loop
  - Device update loop now continues even if MQTT is not connected
  - Pump threshold calculations and other API calls now execute regardless of MQTT status
  - MQTT connection still required for real-time water distance readings and event detection

- **Adaptive Polling Not Reaching Maximum Interval** - Fixed polling staying capped at 60 seconds:
  - Root cause: Alert checking logic was treating ALL alerts as non-info, capping interval at ALERT_MAX_INTERVAL (60s)
  - Now correctly checks for unacknowledged critical/warning severity alerts only
  - Info-severity alerts no longer prevent polling from reaching MAX_POLL_INTERVAL (300s)
  - Polling will now scale up to 5 minutes when there are no pump cycles and no critical/warning alerts

### Changed
- **MQTT Telemetry Handling** - More graceful degradation when MQTT unavailable:
  - Integration continues to fetch pump cycles, environment data, and other API endpoints
  - MQTT failures no longer block the entire device update
  - Cached telemetry data is used when MQTT is unavailable
  - Clear warnings logged when MQTT is not connected

### Technical Details
- Removed `continue` statements from MQTT telemetry section (lines 187-252 in __init__.py)
- Changed MQTT logic to use nested if/else instead of early exit
- **Moved pump threshold calculation to immediately after MQTT section** (line 255)
- Thresholds now correctly sourced from MQTT water distance readings only
- Removed incorrect dependency on pump_cycles API for threshold calculation
- Updated `_update_poll_interval()` to check alert severity (lines 448-468)
- Checks for `"unlack" in state` to match mobile app behavior
- Only critical/warning alerts cap polling at 60s; info alerts allow full 10s-300s range

## [2.4.3] - 2026-01-14

### Fixed
- **Pump ON/OFF Distance Sensors Not Updating** - Fixed calculated pump threshold sensors remaining flat:
  - Root cause: Event detection (`_detect_pump_events`) was only called in MQTT path but integration was falling back to REST API
  - Removed REST API fallback entirely - integration now requires MQTT for telemetry
  - Simplified telemetry logic to be MQTT-only, ensuring event detection always runs
  - Pump ON/OFF distance sensors will now update properly as water distance changes are detected via MQTT
  - Basin Fullness sensor will now calculate correctly using updated thresholds

### Changed
- **MQTT-Only Telemetry** - Removed REST API fallback for shadow data:
  - Integration now skips device updates if MQTT is not connected (with warning)
  - More reliable behavior - either MQTT works or you get clear warnings
  - Simplifies code and prevents silent failures where thresholds never update
  - MQTT connection is now effectively required for the integration to function

### Technical Details
- Removed REST fallback path from telemetry update cycle (lines 246-267 in __init__.py)
- Changed logic to check `if not mqtt_client` at start and skip with `continue`
- Event detection now always runs when MQTT data is received
- Pump thresholds update on ±15mm water distance changes within 5 minutes
- Added clear warning logs when MQTT is not connected

## [2.4.2] - 2026-01-14

### Fixed
- **Alert Sensor Logic** - Fixed alert sensors not matching mobile app behavior:
  - Active Alerts sensor now correctly counts ALL unacknowledged alerts (was only counting alerts with active conditions)
  - Warning Alerts binary sensor now triggers on unacknowledged warning-severity alerts (was incorrectly OFF)
  - Critical Alerts binary sensor now triggers on unacknowledged critical-severity alerts
  - Root cause: Integration was checking for `"active" in state` but should check for `"unlack" in state`
  - Mobile app shows all `unlack` (unacknowledged) alerts regardless of whether condition is currently active or inactive
  - Example: "High Water Level" alert with state `inactive_unlack` now correctly shows as active (condition resolved but not yet dismissed)

### Changed
- **Flood Risk Sensor** - Simplified to match mobile app logic:
  - Now ONLY checks `droplet.floodRisk` field from device (previously also checked for any active alerts)
  - Removed confusing behavior where any alert would trigger flood risk sensor
  - Sensor now purely reflects device's flood risk assessment: unknown, low, medium, high, critical
  - More predictable behavior that matches what users see in mobile app

### Technical Details
- Changed alert state check from `"active" in state and "inactive" not in state` to `"unlack" in state`
- Updated Active Alerts sensor (sensor.py) count logic and attributes categorization
- Updated Warning Alerts binary sensor (binary_sensor.py) is_on and extra_state_attributes methods
- Updated Critical Alerts binary sensor (binary_sensor.py) is_on and extra_state_attributes methods
- Simplified Flood Risk binary sensor (binary_sensor.py) to remove alert-checking logic
- Alert state semantics: `active`/`inactive` = condition occurring, `unlack`/`lack` = acknowledged status

## [2.4.1] - 2026-01-14

### Fixed
- **Alert Dismissal** - Fixed "Dismiss Alerts" button that was not working:
  - Now uses correct v1 acknowledge endpoint (`fbgpg_alerts_v1_acknowledge_alert_prod`) with pathParameters format
  - Previous implementation used shadow update endpoint which did not actually dismiss alerts
  - Alerts now correctly disappear from both integration and mobile app after dismissal
  - Only attempts to dismiss alerts with `dismiss: true` flag
  - Non-dismissible alerts (e.g., "Backup Test Scheduled") are correctly skipped

### Changed
- **Alert Data Source** - Integration now uses v2 ACTIVE alerts API instead of shadow alerts:
  - Matches mobile app behavior exactly (shows all unacknowledged alerts)
  - Provides severity and title directly without requiring metadata lookup
  - More efficient and reliable than shadow-based approach
  - Falls back to shadow alerts if ACTIVE API fails
- **Button Naming** - Renamed "Dismiss All Notifications" to "Dismiss Alerts" for consistency

### Technical Details
- Added `_invoke_lambda_with_path_params()` method for v1 API endpoints
- Added `get_active_alerts()` method to fetch unacknowledged alerts
- Coordinator converts ACTIVE API list format to dictionary for sensor compatibility
- Binary sensors (Critical/Warning) now read severity directly from alert data with fallback to notification_metadata
- Improved error handling and logging for alert operations

## [2.4.0] - 2026-01-14

### Added
- **Persistent Pump Threshold Detection** - Basin Fullness sensor now uses event-based threshold learning:
  - Detects pump ON/OFF events from water distance changes (±15mm in <5 min)
  - Stores thresholds persistently with weighted averaging (80% old, 20% new)
  - Works across days/weeks between pump cycles, not limited to recent readings
  - Replaces unreliable 100-reading rolling window approach
- **New Diagnostic Sensors** - Added calculated pump threshold sensors:
  - `Pump ON Distance (Calculated)` - Water distance when basin is full (pump starts)
  - `Pump OFF Distance (Calculated)` - Water distance when basin is empty (pump stops)
  - Shows calculation method (event_detection vs min_max_fallback) in attributes
  - Displays event count and last event timestamp for transparency
- **Improved Alert Sensors** - Enhanced alert monitoring and filtering:
  - Renamed "Last Alert" to "Active Alerts" - now shows count instead of description
  - All active alerts with details available as sensor attributes
  - New `Critical Alerts` binary sensor - triggers on critical severity alerts
  - New `Warning Alerts` binary sensor - triggers on warning severity alerts
  - Better for automations and dashboard organization

### Fixed
- **Critical: Coordinator Update Failures** - Fixed unhandled authentication errors causing 7+ hour update gaps:
  - MQTT reconnection authentication failures now properly caught and handled
  - Falls back to REST API if reauthentication fails instead of stopping updates
  - Prevents exponential backoff lockup when network issues occur
  - Adds detailed error logging for troubleshooting
- **Basin Fullness Calculation** - Fixed erratic behavior where sensor would jump to 100%:
  - Old approach used min/max from 100 readings, causing threshold shifts with new extremes
  - New event-based detection provides stable, long-term threshold learning
  - Thresholds now adapt gradually over time instead of shifting with each new reading

### Changed
- Basin Fullness calculation method changed from rolling window to persistent event detection
- Active Alerts sensor now returns integer count instead of text description (breaking change for existing automations)

## [2.3.3] - 2026-01-13

### Fixed
- **Critical Bug: Pump Cycles Data Not Loading** - Fixed issue where pump cycle history was never fetched:
  - API client's `_cognito_identity_id` was never set, causing pump cycles API to fail silently
  - Affected sensors: Pump Cycles Last 15 Minutes (always showed 0), Last Pump Cycle (missing data)
  - Affected statistics: Pump volume statistics were not being imported
  - Now properly extracts `federatedIdentity` from device data and sets it before API calls
  - This was a regression introduced in v2.3.0 when multi-device support was added

### Technical Details
- Coordinator now sets `client._cognito_identity_id` from device's `federatedIdentity` field
- Added warning log if `federatedIdentity` is missing from device data
- Fixes pump cycles, environment data, and pump health API calls

## [2.3.2] - 2026-01-13

### Fixed
- **MQTT Connection Stability** - Fixed issue where MQTT updates would stop after ~1 hour:
  - AWS Cognito temporary credentials expire after 1 hour but were never refreshed
  - Added credential expiration tracking to MQTT client
  - MQTT connection now automatically reconnects with fresh credentials before expiration
  - Prevents "MQTT stops working after half a day" issue reported by users
  - Falls back to REST API if reconnection fails

### Technical Details
- `MoenFloNABMqttClient` now tracks `_credentials_expiry` timestamp
- Added `needs_reconnect()` method to check credential expiration
- Added `reconnect_with_new_token()` method to refresh connection
- Coordinator checks credential expiration on each update cycle
- Credentials refreshed 5 minutes before actual expiration to prevent gaps

## [2.3.1] - 2026-01-11

### Fixed
- **Last Pump Cycle Sensor** - Critical fix for incorrect timestamps:
  - Sensor was showing time of most recent event (any type) instead of actual pump cycle time
  - Could display times from non-pump events like "Flood Risk Cleared", causing discrepancies of 60+ minutes
  - Now uses pump session data exclusively, matching Moen app behavior
  - Improved timestamp parsing to handle ISO format with 'Z' suffix correctly
- **API Client** - Removed misleading `get_last_pump_cycle()` method that returned event logs, not pump cycles

### Removed
- Event log data from Last Pump Cycle sensor attributes (was misleading)
- Coordinator call to fetch "last_cycle" from event logs (no longer used)

### Technical Details
- Last Pump Cycle sensor now sources data from `pump_cycles` array only
- Event logs still fetched for notification metadata and water detection
- Timestamp parsing changed from manual string manipulation to proper ISO format handling

## [2.3.0] - 2026-01-11

### Added
- **Multiple Device Support** - Full support for multiple sump pump monitors:
  - Each device gets its own complete set of sensors and binary sensors
  - Automatic filtering to only show sump pump monitors
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
- Sump pump monitor device filtering in coordinator update cycle
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
