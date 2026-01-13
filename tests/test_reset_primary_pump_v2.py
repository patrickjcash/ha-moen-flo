"""
Test resetting primary pump status - Version 2

Fixed to properly get device UUID and handle response format
"""

import urllib.request
import json
import time
from pathlib import Path
import os

env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip().strip('"').strip("'")

OAUTH_BASE = "https://4j1gkf0vji.execute-api.us-east-2.amazonaws.com/prod/v1"
INVOKER_BASE = "https://exo9f857n8.execute-api.us-east-2.amazonaws.com/prod/v1/invoker"
USER_AGENT = "Smartwater-iOS-prod-3.39.0"
CLIENT_ID = "6qn9pep31dglq6ed4fvlq6rp5t"


def http_request(url, method="GET", data=None, headers=None):
    if headers is None:
        headers = {}
    if data is not None:
        data = json.dumps(data).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read().decode('utf-8')
            return response.status, body if body else None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8') if e.fp else None


def authenticate(username, password):
    url = f"{OAUTH_BASE}/oauth2/token"
    headers = {"User-Agent": USER_AGENT}
    payload = {"client_id": CLIENT_ID, "username": username, "password": password}
    status, body = http_request(url, "POST", payload, headers)
    if status != 200:
        raise Exception(f"Auth failed: {status}")
    return json.loads(body)["token"]["access_token"]


def invoke_lambda(access_token, function_name, body):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": USER_AGENT,
    }
    payload = {"parse": False, "body": body, "fn": function_name, "escape": False}
    status, resp_body = http_request(INVOKER_BASE, "POST", payload, headers)
    data = json.loads(resp_body) if resp_body else {}
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
    return {"error": data, "status": status}


def main():
    username = os.getenv("MOEN_USERNAME")
    password = os.getenv("MOEN_PASSWORD")
    if not username or not password:
        print("ERROR: Set credentials")
        return

    print("=== RESET PRIMARY PUMP STATUS ===\n")
    access_token = authenticate(username, password)

    # Get device with full details
    devices = invoke_lambda(access_token, "smartwater-app-device-api-prod-list", {"locale": "en_US"})
    device = [d for d in (devices if isinstance(devices, list) else []) if d.get("deviceType") == "NAB"][0]

    client_id = device.get("clientId")
    duid = device.get("clientId")  # Try clientId as duid first
    device_id = device.get("deviceId")  # Might be different field

    print(f"Device: {device.get('nickname')}")
    print(f"Full device data: {json.dumps(device, indent=2)}")
    print(f"\nClient ID: {client_id}")
    print(f"Device ID: {device_id}\n")

    # Check current shadow alerts
    print("=== BEFORE RESET ===")
    shadow = invoke_lambda(access_token, "smartwater-app-shadow-api-prod-get", {"clientId": client_id})
    alerts_before = shadow.get("state", {}).get("reported", {}).get("alerts", {})
    print(f"Alerts in shadow: {list(alerts_before.keys())}")
    for aid in ["218", "266"]:
        if aid in alerts_before:
            print(f"  Alert {aid}: {alerts_before[aid].get('state')}")

    # Send reset primary pump command
    print("\n=== SENDING RESET PRIMARY PUMP COMMAND ===")

    shadow_request = {
        "clientId": str(client_id),
        "crockCommand": "rst_primary"
    }

    payload = {
        "parse": True,
        "escape": True,
        "fn": "smartwater-app-shadow-api-prod-update",
        "body": shadow_request
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json"
    }

    req = urllib.request.Request(
        INVOKER_BASE,
        data=json.dumps(payload).encode(),
        headers=headers
    )

    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
        print(f"Response: {json.dumps(result, indent=2)}")

        # Wait for shadow update
        print("\nWaiting 5 seconds for shadow update...")
        time.sleep(5)

        # Check shadow
        shadow_after = invoke_lambda(access_token, "smartwater-app-shadow-api-prod-get", {"clientId": client_id})
        alerts_after = shadow_after.get("state", {}).get("reported", {}).get("alerts", {})

        print(f"\n=== AFTER RESET ===")
        print(f"Alerts in shadow: {list(alerts_after.keys())}")

        for aid in ["218", "266"]:
            if aid in alerts_after:
                state_after = alerts_after[aid].get('state')
                state_before = alerts_before.get(aid, {}).get('state')
                if state_after != state_before:
                    print(f"  Alert {aid}: {state_before} → {state_after} ✓ CHANGED")
                else:
                    print(f"  Alert {aid}: {state_after} (no change)")
            elif aid in alerts_before:
                print(f"  Alert {aid}: REMOVED FROM SHADOW ✓✓✓")

        # Check if alert 266 was dismissed
        if '266' not in alerts_after and '266' in alerts_before:
            print("\n✓✓✓ SUCCESS! ALERT 266 REMOVED FROM SHADOW! ✓✓✓")
            print("✓✓✓ THIS IS THE SOLUTION FOR PATHWAY 2 ALERTS! ✓✓✓")
        elif '266' in alerts_after:
            print(f"\n✗ Alert 266 still in shadow")


if __name__ == "__main__":
    main()
