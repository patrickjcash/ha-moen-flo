# Quick Start Guide

Get up and running with the Moen Flo NAB integration in 5 minutes!

## Prerequisites

✅ Home Assistant 2023.1 or newer  
✅ Moen Flo NAB device connected to your account  
✅ Moen account email and password  

## Installation (Choose One Method)

### Option A: HACS (Easiest)

1. Open **HACS** → **Integrations**
2. Click **⋮** → **Custom repositories**
3. Add: `https://github.com/yourusername/ha-moen-flo-nab`
4. Category: **Integration**
5. Search for "Moen Flo NAB" and install
6. **Restart Home Assistant**

### Option B: Manual

1. Download/clone this repository
2. Copy `custom_components/moen_flo_nab/` to `/config/custom_components/`
3. **Restart Home Assistant**

## Setup

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Moen Flo NAB"
4. Enter your Moen email and password
5. Click **Submit**

Done! Your device and sensors are now available.

## What You Get

### 🌊 Sensors (5)
- **Water Level** - Current water level distance
- **Temperature** - Basement/pit temperature
- **Humidity** - Relative humidity
- **Pump Capacity** - Daily usage percentage
- **Last Cycle** - When pump last ran

### ⚡ Binary Sensors (3)
- **Connectivity** - Device online status
- **Flood Risk** - High water alert
- **AC Power** - Power/battery status

## First Automation (Copy & Paste)

### Flood Risk Alert
```yaml
automation:
  - alias: "Flood Risk Alert"
    trigger:
      platform: state
      entity_id: binary_sensor.sump_pump_flood_risk
      to: "on"
    action:
      service: notify.mobile_app
      data:
        title: "⚠️ Flood Risk!"
        message: "Water level critically high"
```

### Power Loss Alert  
```yaml
automation:
  - alias: "Power Loss"
    trigger:
      platform: state
      entity_id: binary_sensor.sump_pump_ac_power
      to: "off"
    action:
      service: notify.mobile_app
      data:
        title: "⚡ Power Out"
        message: "Sump pump on battery"
```

## Quick Dashboard

Add this to Lovelace for a simple dashboard:

```yaml
type: entities
title: Sump Pump Monitor
entities:
  - entity: sensor.sump_pump_water_level
    name: Water Level
  - entity: sensor.sump_pump_temperature
    name: Temperature
  - entity: sensor.sump_pump_humidity
    name: Humidity
  - entity: sensor.sump_pump_daily_pump_capacity
    name: Pump Usage
  - entity: sensor.sump_pump_last_pump_cycle
    name: Last Cycle
  - entity: binary_sensor.sump_pump_connectivity
    name: Online
  - entity: binary_sensor.sump_pump_flood_risk
    name: Flood Risk
  - entity: binary_sensor.sump_pump_ac_power
    name: AC Power
```

## Troubleshooting

### Problem: "Invalid Authentication"
**Solution:** Double-check email/password. Try logging into Moen app.

### Problem: Sensors show "Unknown"
**Solution:** Wait 5 minutes for first update. Check device is online in Moen app.

### Problem: Integration not found
**Solution:** 
1. Verify files in `/config/custom_components/moen_flo_nab/`
2. Restart Home Assistant
3. Check logs: **Settings** → **System** → **Logs**

## Next Steps

- 📖 Read [README.md](README.md) for detailed features
- 🔧 See [INSTALLATION.md](INSTALLATION.md) for advanced setup
- 📊 Check [API_DOCUMENTATION.md](API_DOCUMENTATION.md) for technical details
- 🤖 Create more automations based on your needs
- 📈 Add history graphs for water level tracking

## Need Help?

- Check logs: **Settings** → **System** → **Logs**
- Review [README.md](README.md) troubleshooting section
- Open issue on GitHub with error messages

## Pro Tips

💡 **Set up notifications** for flood risk and power loss immediately  
💡 **Monitor pump capacity** - if consistently high, may indicate a problem  
💡 **Track temperature** in winter to prevent freezing  
💡 **Check connectivity** sensor to ensure device stays online  
💡 **Use history graphs** to identify patterns in water level  

---

**That's it! You're ready to monitor your sump pump with Home Assistant.**

For more advanced features and customization, explore the full documentation.
