#!/usr/bin/env python3
"""Test the alert sensor processing logic."""

# Alert code mappings from const.py
ALERT_CODES = {
    "250": "Water Detected",
    "252": "Water Was Detected",
    "254": "Critical Flood Risk",
    "256": "High Flood Risk",
    "258": "Primary Pump Failed",
    "260": "Backup Pump Failed",
    "262": "Primary Pump Lagging",
    "264": "Backup Pump Lagging",
    "266": "Backup Pump Test Failed",
    "268": "Power Outage",
}


def test_alert_mappings():
    """Test that our alert code mappings match the known alerts."""
    print("=" * 80)
    print("Alert Code Mappings")
    print("=" * 80)

    for code, description in sorted(ALERT_CODES.items()):
        print(f"Alert {code}: {description}")

    print(f"\nTotal mapped alerts: {len(ALERT_CODES)}")


def test_current_alerts():
    """Test processing the current alert data from the device."""
    # This is the actual alert data from the debug output
    current_alerts = {
        "224": {
            "timestamp": "2026-01-03T18:46:55.772Z",
            "state": "inactive_unlack_unrack_unsuppressed",
            "args": ["280", "283"]
        },
        "258": {
            "timestamp": "2026-01-07T23:46:24.101Z",
            "state": "active_unlack_unrack_unsuppressed"
        },
        "260": {
            "timestamp": "2026-01-07T23:41:26.820Z",
            "state": "active_unlack_unrack_unsuppressed"
        },
        "262": {
            "timestamp": "2026-01-07T10:29:28.398Z",
            "state": "inactive_unlack_unrack_unsuppressed"
        },
        "266": {
            "timestamp": "2026-01-06T21:08:18.315Z",
            "state": "inactive_unlack_unrack_unsuppressed"
        },
        "268": {
            "timestamp": "2026-01-03T18:46:57.338Z",
            "state": "active_unlack_unrack_unsuppressed"
        }
    }

    print("\n" + "=" * 80)
    print("Processing Current Device Alerts")
    print("=" * 80)

    active_alerts = []
    inactive_alerts = []

    for alert_id, alert_data in current_alerts.items():
        state = alert_data.get("state", "")
        timestamp = alert_data.get("timestamp", "")
        description = ALERT_CODES.get(alert_id, f"Alert {alert_id}")

        is_active = "active" in state and "inactive" not in state

        if is_active:
            active_alerts.append({
                "id": alert_id,
                "description": description,
                "timestamp": timestamp
            })
        else:
            inactive_alerts.append({
                "id": alert_id,
                "description": description,
                "timestamp": timestamp
            })

    print(f"\nActive Alerts: {len(active_alerts)}")
    for alert in active_alerts:
        print(f"  [{alert['id']}] {alert['description']}")
        print(f"       Since: {alert['timestamp']}")

    print(f"\nInactive Alerts: {len(inactive_alerts)}")
    for alert in inactive_alerts:
        print(f"  [{alert['id']}] {alert['description']}")
        print(f"       Last: {alert['timestamp']}")

    # Determine what the Last Alert sensor would show
    if active_alerts:
        # Find most recent
        most_recent = max(active_alerts, key=lambda a: a['timestamp'])
        print(f"\n" + "=" * 80)
        print(f"Last Alert Sensor Value: {most_recent['description']}")
        print("=" * 80)
    else:
        print(f"\n" + "=" * 80)
        print("Last Alert Sensor Value: No active alerts")
        print("=" * 80)

    # Determine if Flood Risk sensor would be ON
    flood_risk_on = len(active_alerts) > 0
    print(f"\nFlood Risk Binary Sensor: {'ON (Problem detected)' if flood_risk_on else 'OFF (No problems)'}")
    print("=" * 80)


if __name__ == "__main__":
    test_alert_mappings()
    test_current_alerts()
