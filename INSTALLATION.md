# Installation Guide - Moen Flo NAB Integration

## Prerequisites

- Home Assistant 2023.1 or newer
- A Moen Flo NAB device registered to your Moen account
- Your Moen account email and password

## Installation Methods

### Method 1: HACS (Recommended)

HACS (Home Assistant Community Store) makes installation and updates easy.

#### Step 1: Install HACS (if not already installed)
1. Follow the official HACS installation guide: https://hacs.xyz/docs/setup/download
2. Restart Home Assistant after HACS installation

#### Step 2: Add Custom Repository
1. Open HACS in Home Assistant
2. Click the three dots menu in the top right
3. Select "Custom repositories"
4. Add this repository URL: `https://github.com/yourusername/ha-moen-flo-nab`
5. Select category: "Integration"
6. Click "Add"

#### Step 3: Install Integration
1. In HACS, search for "Moen Flo NAB"
2. Click on the integration
3. Click "Download"
4. Restart Home Assistant

### Method 2: Manual Installation

#### Step 1: Download Files
Download the latest release from GitHub or clone the repository:
```bash
cd /config
git clone https://github.com/yourusername/ha-moen-flo-nab.git
```

#### Step 2: Copy Files
Copy the `custom_components/moen_flo_nab` directory to your Home Assistant configuration directory:

```bash
# Using command line
cp -r ha-moen-flo-nab/custom_components/moen_flo_nab /config/custom_components/

# Or using Samba/SSH
# Copy the moen_flo_nab folder to /config/custom_components/
```

Your directory structure should look like:
```
config/
├── custom_components/
│   └── moen_flo_nab/
│       ├── __init__.py
│       ├── manifest.json
│       ├── api.py
│       ├── config_flow.py
│       ├── sensor.py
│       ├── binary_sensor.py
│       ├── const.py
│       └── strings.json
```

#### Step 3: Restart Home Assistant
Restart Home Assistant to load the new integration.

## Configuration

### Step 1: Add Integration
1. Navigate to **Settings** → **Devices & Services**
2. Click the **+ Add Integration** button
3. Search for "Moen Flo NAB"
4. Click on "Moen Flo NAB Sump Pump Monitor"

### Step 2: Enter Credentials
1. Enter your Moen account email
2. Enter your Moen account password
3. Click **Submit**

### Step 3: Verify Installation
1. The integration should now appear in your Devices & Services
2. Click on "Moen Flo NAB" to see your devices
3. Click on your device to see all sensors

## Verification

### Check Entities
All entities should be automatically created. Expected entities:

**Sensors:**
- `sensor.sump_pump_water_level`
- `sensor.sump_pump_temperature`
- `sensor.sump_pump_humidity`
- `sensor.sump_pump_daily_pump_capacity`
- `sensor.sump_pump_last_pump_cycle`

**Binary Sensors:**
- `binary_sensor.sump_pump_connectivity`
- `binary_sensor.sump_pump_flood_risk`
- `binary_sensor.sump_pump_ac_power`

### Test Data Flow
1. Check that sensors show current values (not "Unknown")
2. Wait 5 minutes for the first update cycle to complete
3. Verify sensor values match what you see in the Moen mobile app

## Troubleshooting Installation

### Integration Not Appearing in Add Integration Menu
**Cause:** Files not properly copied or Home Assistant not restarted

**Solution:**
1. Verify files are in `/config/custom_components/moen_flo_nab/`
2. Check that `manifest.json` exists
3. Restart Home Assistant
4. Check logs for errors: **Settings** → **System** → **Logs**

### "Invalid Authentication" Error
**Cause:** Incorrect credentials

**Solution:**
1. Verify credentials by logging into the Moen mobile app
2. Ensure you're using the email address (not username)
3. Check for typos in password
4. Try resetting your Moen password if needed

### "Unknown Error" During Setup
**Cause:** Network issues or API problems

**Solution:**
1. Check Home Assistant logs: **Settings** → **System** → **Logs**
2. Verify your Home Assistant has internet access
3. Try setup again after a few minutes
4. Check Moen service status

### Entities Created But Show "Unavailable"
**Cause:** Device not responding or API issues

**Solution:**
1. Verify device is online in Moen mobile app
2. Wait 5-10 minutes for first data poll
3. Check coordinator logs for errors
4. Reload integration: **Devices & Services** → **Moen Flo NAB** → **⋮** → **Reload**

## Updating the Integration

### Via HACS
1. HACS will notify you of updates
2. Click "Update" in HACS
3. Restart Home Assistant

### Manual Update
1. Download the latest release
2. Replace files in `/config/custom_components/moen_flo_nab/`
3. Restart Home Assistant

## Uninstalling

### Step 1: Remove Integration
1. Go to **Settings** → **Devices & Services**
2. Find "Moen Flo NAB"
3. Click the three dots menu
4. Select "Delete"
5. Confirm deletion

### Step 2: Remove Files (Optional)
If you want to completely remove the integration:
1. Delete `/config/custom_components/moen_flo_nab/` directory
2. Restart Home Assistant

## Next Steps

After successful installation:
1. Read the [Usage Guide](README.md#usage) for automation examples
2. Set up notifications for flood risk and power loss
3. Create dashboards to monitor your sump pump
4. Consider adding historical graphs for water levels

## Getting Help

If you encounter issues:
1. Check the [Troubleshooting](README.md#troubleshooting) section
2. Review Home Assistant logs for error messages
3. Open an issue on GitHub with:
   - Home Assistant version
   - Integration version
   - Error messages from logs
   - Steps to reproduce the issue
