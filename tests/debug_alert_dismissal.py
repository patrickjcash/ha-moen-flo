"""
Debug alert dismissal functionality

USAGE:
    python tests/debug_alert_dismissal.py

Requires .env file with MOEN_USERNAME and MOEN_PASSWORD
"""

import requests
import json
import time
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

# API Configuration
OAUTH_BASE = "https://4j1gkf0vji.execute-api.us-east-2.amazonaws.com/prod/v1"
INVOKER_BASE = "https://exo9f857n8.execute-api.us-east-2.amazonaws.com/prod/v1/invoker"
CLIENT_ID = "6qn9pep31dglq6ed4fvlq6rp5t"
USER_AGENT = "Smartwater-iOS-prod-3.39.0"


def authenticate(username, password):
    """Authenticate with Moen API"""
    print("=== AUTHENTICATING ===")
    url = f"{OAUTH_BASE}/oauth2/token"
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    payload = {
        "client_id": CLIENT_ID,
        "username": username,
        "password": password
    }

    resp = requests.post(url, data=json.dumps(payload), headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    access_token = data["token"]["access_token"]
    print("✓ Authenticated\n")
    return access_token


def invoke_lambda(access_token, function_name, body):
    """Call Lambda function via invoker endpoint"""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json"
    }
    payload = {
        "parse": False,
        "body": body,
        "fn": function_name,
        "escape": False
    }

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
    else:
        raise Exception(f"Lambda error: {data}")


def main():
    import os
    username = os.getenv("MOEN_USERNAME")
    password = os.getenv("MOEN_PASSWORD")

    if not username or not password:
        print("ERROR: Set MOEN_USERNAME and MOEN_PASSWORD in .env file")
        return

    # Authenticate
    access_token = authenticate(username, password)

    # Get devices
    print("=== GETTING DEVICES ===")
    devices_resp = invoke_lambda(access_token, "smartwater-app-device-api-prod-list", {"locale": "en_US"})
    devices = devices_resp if isinstance(devices_resp, list) else []

    print(f"Total devices: {len(devices)}")
    for d in devices:
        print(f"  - {d.get('nickname', 'Unknown')} (Type: {d.get('deviceType', 'Unknown')})")

    nab_devices = [d for d in devices if d.get("deviceType") == "NAB"]

    if not nab_devices:
        print("\nNo NAB devices found (filtering by deviceType=='NAB')")
        print("Trying first device regardless of type...")
        if devices:
            nab_devices = [devices[0]]
        else:
            print("No devices at all!")
            return

    device = nab_devices[0]
    device_uuid = device.get("duid")
    client_id = device.get("clientId")
    nickname = device.get("nickname", "Unknown")

    print(f"✓ Found device: {nickname}")
    print(f"  UUID: {device_uuid}")
    print(f"  Client ID: {client_id}\n")

    # Get shadow to see active alerts
    print("=== GETTING DEVICE SHADOW ===")
    shadow_resp = invoke_lambda(access_token, "smartwater-app-shadow-api-prod-get", {
        "clientId": client_id
    })

    reported = shadow_resp.get("state", {}).get("reported", {})
    alerts = reported.get("alerts", {})

    print(f"Total alerts in shadow: {len(alerts)}\n")

    # Analyze alerts
    active_alerts = []
    inactive_alerts = []

    for alert_id, alert_data in alerts.items():
        state = alert_data.get("state", "")
        is_active = "active" in state and "inactive" not in state

        if is_active:
            active_alerts.append({
                "id": alert_id,
                "state": state,
                "timestamp": alert_data.get("timestamp", ""),
                "args": alert_data.get("args", [])
            })
        else:
            inactive_alerts.append({"id": alert_id, "state": state})

    print(f"--- Active Alerts: {len(active_alerts)} ---")
    for alert in active_alerts:
        print(f"  Alert {alert['id']}:")
        print(f"    State: {alert['state']}")
        print(f"    Timestamp: {alert['timestamp']}")
        if alert['args']:
            print(f"    Args: {alert['args']}")

    print(f"\n--- Inactive Alerts: {len(inactive_alerts)} ---")
    for alert in inactive_alerts[:5]:
        print(f"  Alert {alert['id']}: {alert['state']}")

    if not active_alerts:
        print("\n⚠ No active alerts to test dismissal with")
        return

    # Test dismissing first active alert
    print("\n=== TESTING SINGLE ALERT DISMISSAL ===")
    test_alert = active_alerts[0]
    print(f"Attempting to dismiss alert {test_alert['id']}...")

    # Try Method 1: alertAck in body
    print("\nMethod 1: alertAck parameter")
    try:
        response = invoke_lambda(access_token, "smartwater-app-shadow-api-prod-update", {
            "clientId": client_id,
            "alertAck": test_alert['id']
        })
        print(f"  Response: {json.dumps(response, indent=2)}")
    except Exception as e:
        print(f"  Error: {e}")

    # Wait for change to propagate
    print("\n  Waiting 2 seconds for change to propagate...")
    time.sleep(2)

    # Verify dismissal
    print("\n=== VERIFYING DISMISSAL ===")
    shadow_after = invoke_lambda(access_token, "smartwater-app-shadow-api-prod-get", {
        "clientId": client_id
    })
    alerts_after = shadow_after.get("state", {}).get("reported", {}).get("alerts", {})

    if test_alert['id'] in alerts_after:
        state_after = alerts_after[test_alert['id']].get("state", "")
        print(f"Alert {test_alert['id']} state:")
        print(f"  Before: {test_alert['state']}")
        print(f"  After:  {state_after}")

        if state_after != test_alert['state']:
            print("  ✓ State changed!")
            if "inactive" in state_after or "ack" in state_after:
                print("  ✓ Successfully dismissed/acknowledged!")
            else:
                print("  ⚠ State changed but not to inactive/ack")
        else:
            print("  ✗ State did not change")
    else:
        print(f"Alert {test_alert['id']} no longer in shadow (removed)")

    # Show all remaining active alerts
    active_after = [
        aid for aid, adata in alerts_after.items()
        if "active" in adata.get("state", "") and "inactive" not in adata.get("state", "")
    ]
    print(f"\nActive alerts remaining: {len(active_after)}")
    for aid in active_after:
        print(f"  - {aid}: {alerts_after[aid].get('state')}")

    # Try alternative methods if first didn't work
    if len(active_alerts) > 1 and test_alert['id'] in active_after:
        print("\n=== TESTING ALTERNATIVE METHODS ===")

        test_methods = [
            {
                "name": "Method 2: state.desired.alertAck",
                "payload": {
                    "clientId": client_id,
                    "state": {
                        "desired": {
                            "alertAck": test_alert['id']
                        }
                    }
                }
            },
            {
                "name": "Method 3: Direct alert state modification",
                "payload": {
                    "clientId": client_id,
                    "alerts": {
                        test_alert['id']: {
                            "state": "inactive_ack_unrack_unsuppressed"
                        }
                    }
                }
            },
            {
                "name": "Method 4: alertAck array",
                "payload": {
                    "clientId": client_id,
                    "alertAck": [test_alert['id']]
                }
            }
        ]

        for method in test_methods:
            print(f"\n{method['name']}:")
            print(f"  Payload: {json.dumps(method['payload'], indent=4)}")
            try:
                response = invoke_lambda(access_token, "smartwater-app-shadow-api-prod-update", method['payload'])
                print(f"  Response: {json.dumps(response, indent=2)[:200]}...")
                time.sleep(1)
            except Exception as e:
                print(f"  Error: {e}")

    print("\n=== SUMMARY ===")
    print(f"Device: {nickname}")
    print(f"Total alerts: {len(alerts)}")
    print(f"Active before test: {len(active_alerts)}")
    print(f"Active after test: {len(active_after)}")
    print("\nCheck output above for dismissal method results.")


if __name__ == "__main__":
    main()
