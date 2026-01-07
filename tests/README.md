# Moen Flo NAB Integration Tests

## Test Scripts

### nab_test.py
Main test script for validating the Moen Flo NAB API integration.

**Usage:**
```bash
# Create a .env file in the project root with your credentials:
# MOEN_USERNAME=your_email@example.com
# MOEN_PASSWORD=your_password

# Run the test
python tests/nab_test.py
```

**Features:**
- Tests authentication with Moen API
- Retrieves device list
- Fetches environment data (temperature/humidity)
- Gets pump health and cycle data
- Retrieves event logs
- Validates all API endpoints

### moen_nab_api_explorer.py
API exploration tool for discovering and testing Moen Flo NAB endpoints.

**Usage:**
```bash
python tests/moen_nab_api_explorer.py
```

**Features:**
- Interactive API endpoint testing
- Exports responses to JSON files (gitignored)
- Helpful for debugging and API discovery

## Test Output Files

Test scripts may generate JSON files containing API responses. These files are automatically gitignored to prevent committing sensitive data.

**Gitignored patterns:**
- `tests/*.json`
- `tests/*_test_*.json`
- `tests/*_exploration_*.json`
- `tests/output_*.json`

## Requirements

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install aiohttp python-dotenv
```

## Environment Variables

Create a `.env` file in the project root:

```bash
MOEN_USERNAME=your_email@example.com
MOEN_PASSWORD=your_password
```

**Note:** The `.env` file is gitignored and will never be committed.

## Testing Best Practices

1. **Never commit sensitive data** - All JSON output files are gitignored
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
