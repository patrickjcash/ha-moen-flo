"""
Test the CORRECT acknowledge endpoint with exact payload from Android app

USAGE:
    python tests/test_correct_acknowledge.py

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
    return data["token"]["access_token"]


def invoke_lambda_correct_format(access_token, function_name, path_params):
    """Call Lambda with Android app's exact format"""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json"
    }
    payload = {
        "parse": True,
        "escape": True,
        "fn": function_name,
        "body": {
            "pathParameters": path_params
        }
    }

    resp = requests.post(INVOKER_BASE, json=payload, headers=headers, timeout=30)

    # Debug: print raw response
    print(f"  Raw status code: {resp.status_code}")

    # Handle 204 No Content
    if resp.status_code == 204:
        return {"success": True, "message": "204 No Content - Request accepted"}

    if not resp.text:
        return {"error": f"Empty response with status {resp.status_code}"}

    print(f"  Raw response text: {resp.text[:500]}")
    data = resp.json()

    if data.get("StatusCode") == 200:
        payload_val = data.get("Payload")
        if isinstance(payload_val, str):
            try:
                payload_val = json.loads(payload_val)
            except:
                pass
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
        return {"error": data}


def invoke_lambda(access_token, function_name, body):
    """Call Lambda function via invoker endpoint (standard format)"""
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
        if isinstance(payload_val, str):
            try:
                payload_val = json.loads(payload_val)
            except:
                pass
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
        return {"error": data}


def main():
    import os
    username = os.getenv("MOEN_USERNAME")
    password = os.getenv("MOEN_PASSWORD")

    if not username or not password:
        print("ERROR: Set MOEN_USERNAME and MOEN_PASSWORD in .env file")
        return

    print("=== AUTHENTICATING ===")
    access_token = authenticate(username, password)
    print("✓ Authenticated\n")

    # Get device
    devices_resp = invoke_lambda(access_token, "smartwater-app-device-api-prod-list", {"locale": "en_US"})
    devices = devices_resp if isinstance(devices_resp, list) else []
    device = [d for d in devices if d.get("deviceType") == "NAB"][0]

    device_uuid = device.get("duid")
    client_id = device.get("clientId")

    print(f"Device: {device.get('nickname')}")
    print(f"UUID: {device_uuid}")
    print(f"Client ID: {client_id}\n")

    # Get current alerts
    shadow = invoke_lambda(access_token, "smartwater-app-shadow-api-prod-get", {"clientId": client_id})
    alerts = shadow.get("state", {}).get("reported", {}).get("alerts", {})

    # Find inactive alerts
    inactive_alerts = [aid for aid, adata in alerts.items()
                      if "inactive" in adata.get("state", "") and "unlack" in adata.get("state", "")]

    print(f"=== CURRENT ALERTS ===")
    for aid, adata in alerts.items():
        state = adata.get("state", "")
        print(f"  {aid}: {state}")

    if not inactive_alerts:
        print("\n⚠ No inactive alerts to test!")
        if not alerts:
            print("No alerts at all!")
            return
        test_alert = list(alerts.keys())[0]
    else:
        test_alert = "262" if "262" in inactive_alerts else inactive_alerts[0]

    print(f"\n=== TESTING ACKNOWLEDGE VS SILENCE ON ALERT {test_alert} ===\n")

    state_before = alerts.get(test_alert, {}).get("state", "")
    print(f"Alert {test_alert} state before: {state_before}\n")

    # TEST SILENCE ENDPOINT (for dismissal)
    print("Testing SILENCE endpoint with NUMERIC CLIENT ID:")
    print(f"  Function: fbgpg_alerts_v1_silence_alert_prod")
    print(f"  pathParameters: {{\"duid\": \"{client_id}\", \"alertEventId\": \"{test_alert}\"}}\n")

    try:
        result = invoke_lambda_correct_format(
            access_token,
            "fbgpg_alerts_v1_silence_alert_prod",
            {
                "duid": str(client_id),  # Use numeric client ID, not UUID!
                "alertEventId": test_alert
            }
        )
        print(f"Response: {json.dumps(result, indent=2)}")

        if "error" not in result and "errorType" not in result:
            print("\n✓ No error! Waiting 10 seconds for shadow to update...")
            time.sleep(10)
        else:
            print(f"\n✗ Got error response")
    except Exception as e:
        print(f"✗ Exception: {e}")

    # Verify results
    print("\n=== VERIFYING RESULTS ===")
    shadow_after = invoke_lambda(access_token, "smartwater-app-shadow-api-prod-get", {"clientId": client_id})
    alerts_after = shadow_after.get("state", {}).get("reported", {}).get("alerts", {})

    if test_alert in alerts_after:
        state_after = alerts_after[test_alert].get("state", "")
        print(f"Alert {test_alert}:")
        print(f"  Before: {state_before}")
        print(f"  After:  {state_after}")
        if state_before != state_after:
            print("  ✓✓✓ STATE CHANGED!")
            if "ack" in state_after or test_alert not in alerts_after:
                print("  ✓✓✓ SUCCESSFULLY ACKNOWLEDGED!")
        else:
            print("  ✗ No change")
    else:
        print(f"Alert {test_alert}: ✓✓✓ REMOVED FROM SHADOW!")
        print("  ✓✓✓ SUCCESSFULLY ACKNOWLEDGED!")

    print("\n=== ALL REMAINING ALERTS ===")
    for aid, adata in alerts_after.items():
        print(f"  {aid}: {adata.get('state')}")


if __name__ == "__main__":
    main()
