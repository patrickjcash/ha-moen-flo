# Changelog

All notable changes to the Moen Flo NAB Home Assistant Integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
