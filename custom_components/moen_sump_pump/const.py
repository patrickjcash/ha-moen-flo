"""Constants for the Moen Smart Sump Pump Monitor integration."""

DOMAIN = "moen_sump_pump"

# Sensor Types
SENSOR_WATER_LEVEL = "water_level"
SENSOR_TEMPERATURE = "temperature"
SENSOR_HUMIDITY = "humidity"
SENSOR_PUMP_CAPACITY = "pump_capacity"
SENSOR_LAST_CYCLE = "last_cycle"

# Binary Sensor Types
BINARY_SENSOR_CONNECTIVITY = "connectivity"
BINARY_SENSOR_FLOOD_RISK = "flood_risk"
BINARY_SENSOR_POWER = "power"

# Device Classes
DEVICE_CLASS_WATER_LEVEL = "distance"

# Alert Code Mappings (from decompiled Moen app strings.xml and API exploration)
# These are the common NAB (Sump Pump Monitor) alert codes
ALERT_CODES = {
    "218": "Backup Test Scheduled",  # Backup pump test scheduled
    "224": "Unknown Alert",  # Found in API but not in app strings - appears with args
    "250": "Water Detected",  # Critical - Remote sensing cable detected water
    "252": "Water Was Detected",  # Warning - Water no longer detected
    "254": "Critical Flood Risk",  # Critical flood level
    "256": "High Flood Risk",  # High water level
    "258": "Primary Pump Failed",  # Primary pump failed to engage
    "260": "Backup Pump Failed",  # Backup pump failed to engage
    "262": "Primary Pump Lagging",  # Primary pump can't keep up
    "264": "Backup Pump Lagging",  # Backup pump can't keep up
    "266": "Backup Pump Test Failed",  # Backup pump test failed
    "268": "Power Outage",  # Device on battery power
    "298": "Main Pump Not Stopping",  # Main pump continues running (from alert 224 args)
    "299": "High Water Level",  # High water level (from alert 224 args)
}
