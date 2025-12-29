# Project File Structure

## Directory Layout

```
moen_flo_nab_integration/
├── custom_components/
│   └── moen_flo_nab/           # Main integration directory
│       ├── __init__.py          # Integration setup & coordinator
│       ├── api.py               # API client for Moen Flo
│       ├── binary_sensor.py     # Binary sensor platform
│       ├── config_flow.py       # UI configuration flow
│       ├── const.py             # Constants and configuration
│       ├── manifest.json        # Integration metadata
│       ├── sensor.py            # Sensor platform
│       └── strings.json         # UI translations
├── API_DOCUMENTATION.md         # Complete API reverse engineering docs
├── CHANGELOG.md                 # Version history and changes
├── INSTALLATION.md              # Detailed installation guide
├── LICENSE                      # MIT License with disclaimers
├── PROJECT_SUMMARY.md           # Project overview and summary
├── QUICK_START.md               # 5-minute setup guide
└── README.md                    # Main user documentation
```

## File Descriptions

### Core Integration Files

#### `__init__.py` (130 lines)
**Purpose:** Integration initialization and data coordination  
**Key Components:**
- `async_setup_entry()` - Sets up the integration
- `async_unload_entry()` - Cleans up on removal
- `MoenFloNABDataUpdateCoordinator` - Manages data updates every 5 minutes

**Dependencies:**
- Home Assistant core
- `api.py` for API communication
- `const.py` for configuration

#### `api.py` (220 lines)
**Purpose:** API client for Moen Flo NAB communication  
**Key Components:**
- `MoenFloNABClient` - Main API client class
- AWS Cognito authentication
- Lambda function invocation
- Token management and refresh

**Key Methods:**
- `authenticate()` - Login with credentials
- `get_devices()` - Retrieve device list
- `get_device_environment()` - Get temp/humidity
- `get_pump_health()` - Get pump capacity data
- `get_device_logs()` - Get event history
- `get_last_pump_cycle()` - Find last pump operation

#### `config_flow.py` (65 lines)
**Purpose:** UI-based configuration interface  
**Key Components:**
- `MoenFloNABConfigFlow` - Handles user setup
- Credential validation
- Duplicate detection
- Error handling

#### `sensor.py` (280 lines)
**Purpose:** Sensor platform implementation  
**Sensors Created:**
1. Water Level - Distance measurement with thresholds
2. Temperature - Fahrenheit temperature reading
3. Humidity - Percentage humidity reading
4. Pump Capacity - Daily usage percentage
5. Last Cycle - Timestamp of last pump cycle

**Base Class:**
- `MoenFloNABSensorBase` - Common functionality for all sensors

#### `binary_sensor.py` (160 lines)
**Purpose:** Binary sensor platform implementation  
**Sensors Created:**
1. Connectivity - Online/offline status
2. Flood Risk - High water level detection
3. AC Power - Power/battery status

**Base Class:**
- `MoenFloNABBinarySensorBase` - Common functionality for binary sensors

#### `const.py` (20 lines)
**Purpose:** Constants and configuration values  
**Contents:**
- Domain name
- Sensor type identifiers
- Binary sensor identifiers
- Device class constants

#### `manifest.json` (10 lines)
**Purpose:** Integration metadata for Home Assistant  
**Contents:**
- Integration domain
- Display name
- Version number
- Documentation URL
- Requirements
- IoT class (cloud_polling)

#### `strings.json` (20 lines)
**Purpose:** UI text translations  
**Contents:**
- Setup flow text
- Error messages
- Configuration labels

### Documentation Files

#### `README.md` (400 lines)
**Audience:** End users  
**Contents:**
- Feature overview
- Installation instructions
- Usage examples
- Automation examples
- Troubleshooting guide
- FAQ

#### `QUICK_START.md` (150 lines)
**Audience:** New users  
**Contents:**
- 5-minute setup guide
- First automation examples
- Quick dashboard configuration
- Common troubleshooting

#### `INSTALLATION.md` (350 lines)
**Audience:** Users installing the integration  
**Contents:**
- Detailed HACS installation
- Manual installation steps
- Configuration walkthrough
- Verification procedures
- Troubleshooting installation issues

#### `API_DOCUMENTATION.md` (650 lines)
**Audience:** Developers and contributors  
**Contents:**
- Complete API reverse engineering details
- Authentication flow
- Lambda function documentation
- Dual ID system explanation
- Request/response examples
- Testing procedures
- Integration architecture

#### `PROJECT_SUMMARY.md` (300 lines)
**Audience:** Contributors and maintainers  
**Contents:**
- Project overview
- Technical achievements
- Feature list
- Architecture details
- Future enhancements
- Development roadmap

#### `CHANGELOG.md` (100 lines)
**Audience:** Users and developers  
**Contents:**
- Version history
- Feature additions
- Bug fixes
- Breaking changes
- Upgrade notes

#### `LICENSE` (100 lines)
**Audience:** Legal/compliance  
**Contents:**
- MIT License text
- Additional disclaimers
- Usage warnings
- Liability limitations

## File Relationships

### Data Flow
```
config_flow.py
    ↓ (credentials)
api.py
    ↓ (authentication)
__init__.py (coordinator)
    ↓ (device data)
    ├─ sensor.py (5 entities)
    └─ binary_sensor.py (3 entities)
```

### Import Dependencies
```
config_flow.py  → api.py, const.py
__init__.py     → api.py, const.py
sensor.py       → __init__.py, const.py
binary_sensor.py → __init__.py, const.py
```

## Installation Paths

### HACS Installation
```
/config/
└── custom_components/
    └── moen_flo_nab/
        └── [all integration files]
```

### Manual Installation
```
/config/
└── custom_components/
    └── moen_flo_nab/
        └── [copy all files here]
```

## File Sizes (Approximate)

| File | Lines | Size | Purpose |
|------|-------|------|---------|
| `__init__.py` | 130 | 4.5 KB | Coordinator |
| `api.py` | 220 | 8.0 KB | API client |
| `sensor.py` | 280 | 10.0 KB | Sensors |
| `binary_sensor.py` | 160 | 6.0 KB | Binary sensors |
| `config_flow.py` | 65 | 2.5 KB | Config UI |
| `const.py` | 20 | 0.5 KB | Constants |
| `manifest.json` | 10 | 0.3 KB | Metadata |
| `strings.json` | 20 | 0.5 KB | Translations |
| **Total Code** | **905** | **32 KB** | |
| | | | |
| `README.md` | 400 | 20 KB | User guide |
| `API_DOCUMENTATION.md` | 650 | 35 KB | API docs |
| `INSTALLATION.md` | 350 | 18 KB | Install guide |
| `QUICK_START.md` | 150 | 8 KB | Quick start |
| `PROJECT_SUMMARY.md` | 300 | 15 KB | Overview |
| `CHANGELOG.md` | 100 | 5 KB | Changes |
| `LICENSE` | 100 | 5 KB | License |
| **Total Docs** | **2,050** | **106 KB** | |
| | | | |
| **Grand Total** | **2,955** | **138 KB** | Complete project |

## Code Statistics

### Python Files
- Total lines: 875
- Code lines: ~650
- Comments/docstrings: ~150
- Blank lines: ~75

### Documentation
- Total words: ~25,000
- Total characters: ~160,000
- Estimated reading time: 2 hours

## Maintenance

### Files to Update on Version Change
1. `manifest.json` - Version number
2. `CHANGELOG.md` - New entry
3. `PROJECT_SUMMARY.md` - Version status

### Files to Update for API Changes
1. `api.py` - Endpoints and payloads
2. `API_DOCUMENTATION.md` - New discoveries
3. `CHANGELOG.md` - Breaking changes

### Files to Update for Features
1. Relevant platform file (`sensor.py` or `binary_sensor.py`)
2. `README.md` - Feature documentation
3. `CHANGELOG.md` - Feature addition
4. `const.py` - New constants if needed

## Testing Files

### Recommended Test Structure (Future)
```
tests/
├── test_api.py              # API client tests
├── test_config_flow.py      # Config flow tests
├── test_sensor.py           # Sensor tests
├── test_binary_sensor.py    # Binary sensor tests
├── fixtures/                # Test data
│   ├── device_list.json
│   ├── environment.json
│   └── logs.json
└── conftest.py              # Pytest configuration
```

## Git Repository Structure

### Recommended `.gitignore`
```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python

# Virtual environments
venv/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Testing
.pytest_cache/
.coverage
htmlcov/

# Distribution
dist/
build/
*.egg-info/
```

### Recommended Repository Layout
```
ha-moen-flo-nab/
├── custom_components/
│   └── moen_flo_nab/
│       └── [all integration files]
├── docs/
│   ├── API_DOCUMENTATION.md
│   ├── INSTALLATION.md
│   └── images/
├── .github/
│   ├── workflows/
│   │   ├── validate.yaml
│   │   └── release.yaml
│   └── ISSUE_TEMPLATE/
├── README.md
├── CHANGELOG.md
├── LICENSE
└── .gitignore
```

## Deployment Checklist

Before releasing:
- [ ] All Python files have proper headers
- [ ] All functions have docstrings
- [ ] Version numbers match across files
- [ ] CHANGELOG.md updated
- [ ] README.md examples tested
- [ ] No hardcoded credentials
- [ ] Error handling complete
- [ ] Logging appropriate
- [ ] Documentation reviewed
- [ ] License file present

## Support Files

For community support, consider adding:
- `CONTRIBUTING.md` - Contribution guidelines
- `CODE_OF_CONDUCT.md` - Community standards
- `.github/ISSUE_TEMPLATE/` - Issue templates
- `.github/PULL_REQUEST_TEMPLATE.md` - PR template

---

**Total Project Size:** ~138 KB  
**Total Files:** 15 files  
**Total Lines:** ~3,000 lines  
**Estimated Development Time:** 40+ hours of reverse engineering and development
