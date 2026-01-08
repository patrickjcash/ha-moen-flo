# Moen Flo NAB Integration Tests

## Active Test Scripts

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

The `archive/` folder contains diagnostic and development scripts that were useful during integration development but are not needed for regular use. **This folder is gitignored and not included in releases.**

### Development/Debugging Scripts (in archive/)
- `moen_nab_api_explorer.py` - Interactive API endpoint testing
- `compare_all_shadow_data.py` - Complete shadow vs cached data comparison
- `compare_shadow_vs_cached.py` - Water level data comparison
- `test_shadow_api_live.py` - Real-time shadow API monitoring
- `check_water_level_simple.py` - Quick water level diagnostic
- `debug_shadow_structure.py` - Shadow data structure analysis
- `test_shadow_workflow.py` - Shadow trigger/retrieve workflow test
- `test_live_shadow_integration.py` - Live integration testing

**Purpose:** These scripts were used during development to reverse-engineer the Moen API, discover shadow endpoints, and validate live telemetry. They contain development/debugging code and are not needed for production use.

---

## Requirements

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install aiohttp python-dotenv
```

## Environment Variables

Create a `.env` file in the project root (for archived test scripts that require API access):

```bash
MOEN_USERNAME=your_email@example.com
MOEN_PASSWORD=your_password
```

**Note:** The `.env` file is gitignored and will never be committed.

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

### API Endpoint Changes
- Moen may update their API without notice
- Check the latest API responses for structural changes
- Update integration code if endpoints change

### Missing Data
- Not all devices support all features (temperature/humidity sensors)
- Some fields may be null if device doesn't report them
- Check device firmware version in Moen app
