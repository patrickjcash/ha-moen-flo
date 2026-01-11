"""
Test alert dismissal functionality

USAGE:
    python tests/test_dismiss_alerts.py

Requires .env file with MOEN_USERNAME and MOEN_PASSWORD
"""

import requests
import json
import sys
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# API Configuration
OAUTH_BASE = "https://4j1gkf0vji.execute-api.us-east-2.amazonaws.com/prod/v1"
INVOKER_BASE = "https://exo9f857n8.execute-api.us-east-2.amazonaws.com/prod/v1/invoker"
CLIENT_ID = "6qn9pep31dglq6ed4fvlq6rp5t"
USER_AGENT = "Smartwater-iOS-prod-3.39.0"

ALERT_CODES = {
    "218": "Backup Test Scheduled",
    "224": "Unknown Alert",
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
    "298": "Main Pump Not Stopping",
    "299": "High Water Level",
}


class AlertDismissalTester:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.access_token = None
        self.device_uuid = None
        self.client_id_numeric = None

    def authenticate(self):
        """Authenticate with Moen API"""
        print("Authenticating...")
        url = f"{OAUTH_BASE}/oauth2/token"
        headers = {
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        payload = {
            "client_id": CLIENT_ID,
            "username": self.username,
            "password": self.password
        }

        try:
            resp = requests.post(url, data=json.dumps(payload), headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if "token" in data:
                self.access_token = data["token"].get("access_token")
                print("✓ Authenticated\n")
                return True
        except Exception as e:
            print(f"✗ Auth failed: {e}")
        return False

    def invoke_lambda(self, function_name, body):
        """Call Lambda function via invoker endpoint"""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json"
        }
        payload = {
            "parse": False,
            "body": body,
            "fn": function_name,
            "escape": False
        }

        try:
            resp = requests.post(INVOKER_BASE, json=payload, headers=headers, timeout=30)
            data = resp.json()

            if data.get("StatusCode") == 200:
                payload_val = data.get("Payload")

                # Handle double-encoded JSON
                if isinstance(payload_val, str):
                    try:
                        payload_val = json.loads(payload_val)
                    except:
                        pass

                # Handle nested body structure
                if isinstance(payload_val, dict) and "body" in payload_val:
                    inner_body = payload_val["body"]
                    if isinstance(inner_body, str):
                        try:
                            return json.loads(inner_body)
                        except:
                            return inner_body
                    return inner_body

                return payload_val
        except Exception as e:
            return {"error": str(e)}
        return None

    def get_device_ids(self):
        """Get device IDs"""
        result = self.invoke_lambda(
            "smartwater-app-device-api-prod-list",
            {"locale": "en_US"}
        )

        devices = result if isinstance(result, list) else []

        if devices and isinstance(devices, list):
            for device in devices:
                if device.get('deviceType') == 'NAB':
                    self.device_uuid = device['duid']
                    self.client_id_numeric = device.get('clientId')
                    return True
        return False

    def get_current_alerts(self):
        """Get current alerts from shadow"""
        print("="*70)
        print("GETTING CURRENT ALERTS")
        print("="*70)

        shadow_result = self.invoke_lambda(
            "smartwater-app-shadow-api-prod-get",
            {"clientId": self.client_id_numeric}
        )

        if shadow_result and isinstance(shadow_result, dict):
            reported = shadow_result.get("state", {}).get("reported", {})
            alerts = reported.get("alerts", {})

            print(f"\nFound {len(alerts)} alert(s):")

            active_alerts = []
            inactive_alerts = []

            for alert_id, alert_data in alerts.items():
                state = alert_data.get("state", "")
                timestamp = alert_data.get("timestamp", "")
                description = ALERT_CODES.get(alert_id, f"Alert {alert_id}")

                alert_info = {
                    "id": alert_id,
                    "description": description,
                    "state": state,
                    "timestamp": timestamp,
                }

                if "active" in state and "inactive" not in state:
                    active_alerts.append(alert_info)
                else:
                    inactive_alerts.append(alert_info)

            print(f"\nActive alerts: {len(active_alerts)}")
            for alert in active_alerts:
                print(f"  [{alert['id']}] {alert['description']}")
                print(f"       State: {alert['state']}")
                print(f"       Since: {alert['timestamp']}")

            print(f"\nInactive alerts: {len(inactive_alerts)}")
            for alert in inactive_alerts:
                print(f"  [{alert['id']}] {alert['description']}")
                print(f"       State: {alert['state']}")

            return active_alerts, inactive_alerts

        return [], []

    def test_dismiss_methods(self, alert_id):
        """Test different methods to dismiss an alert"""
        print(f"\n{'='*70}")
        print(f"TESTING ALERT DISMISSAL METHODS FOR ALERT {alert_id}")
        print(f"{'='*70}\n")

        # Test 1: Try alertAck parameter in shadow update
        print("Test 1: Shadow update with alertAck parameter")
        result = self.invoke_lambda(
            "smartwater-app-shadow-api-prod-update",
            {"clientId": self.client_id_numeric, "alertAck": alert_id}
        )
        print(f"  Result: {json.dumps(result, indent=2) if result else 'No response'}\n")

        # Test 2: Try alertDismiss parameter
        print("Test 2: Shadow update with alertDismiss parameter")
        result = self.invoke_lambda(
            "smartwater-app-shadow-api-prod-update",
            {"clientId": self.client_id_numeric, "alertDismiss": alert_id}
        )
        print(f"  Result: {json.dumps(result, indent=2) if result else 'No response'}\n")

        # Test 3: Try setting alert state to suppressed
        print("Test 3: Shadow update with alert state suppressed")
        result = self.invoke_lambda(
            "smartwater-app-shadow-api-prod-update",
            {
                "clientId": self.client_id_numeric,
                "alerts": {alert_id: {"state": "suppressed"}}
            }
        )
        print(f"  Result: {json.dumps(result, indent=2) if result else 'No response'}\n")

        # Test 4: Try dedicated dismiss alert function
        print("Test 4: Dedicated dismiss alert function")
        result = self.invoke_lambda(
            "smartwater-app-alert-api-prod-dismiss",
            {"clientId": self.client_id_numeric, "alertId": alert_id}
        )
        print(f"  Result: {json.dumps(result, indent=2) if result else 'No response'}\n")

        # Test 5: Try logs-based dismiss
        print("Test 5: Logs-based dismiss")
        result = self.invoke_lambda(
            "fbgpg_logs_v1_dismiss_alert_prod",
            {"duid": self.device_uuid, "alertId": alert_id, "locale": "en_US"}
        )
        print(f"  Result: {json.dumps(result, indent=2) if result else 'No response'}\n")

    def run_test(self, dry_run=True):
        """Run dismissal test"""
        if not self.authenticate():
            return

        if not self.get_device_ids():
            print("✗ Could not get device IDs")
            return

        print(f"Device UUID: {self.device_uuid}")
        print(f"Numeric ID: {self.client_id_numeric}\n")

        # Get current alerts
        active_alerts, inactive_alerts = self.get_current_alerts()

        if not active_alerts:
            print("\n✓ No active alerts to test dismissal")
            return

        if dry_run:
            print(f"\n{'='*70}")
            print("DRY RUN MODE - Not actually dismissing alerts")
            print("Set dry_run=False to test actual dismissal")
            print(f"{'='*70}")
            print(f"\nWould test dismissal on {len(active_alerts)} active alert(s)")
        else:
            # Test dismissal on first active alert
            test_alert = active_alerts[0]
            self.test_dismiss_methods(test_alert['id'])

            # Check if alert was dismissed
            print(f"\n{'='*70}")
            print("CHECKING ALERT STATE AFTER DISMISSAL ATTEMPTS")
            print(f"{'='*70}")
            active_after, inactive_after = self.get_current_alerts()


if __name__ == "__main__":
    username = os.getenv("MOEN_USERNAME")
    password = os.getenv("MOEN_PASSWORD")

    if not username or not password:
        print("Error: MOEN_USERNAME and MOEN_PASSWORD must be set in .env file")
        sys.exit(1)

    # Set dry_run=False to actually test dismissal
    tester = AlertDismissalTester(username, password)
    tester.run_test(dry_run=True)
