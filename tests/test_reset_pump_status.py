"""
Test fbgpg_usage_v1_put_usage_reset_device_capacity_prod endpoint.

This is the Lambda function called by the Moen app when the user presses
"Reset Primary Pump Status" under View Device --> Primary Pump.

Parameters: cognitoIdentityId (from device.federatedIdentity) + duid

USAGE:
    python tests/test_reset_pump_status.py

Requires .env file with MOEN_USERNAME and MOEN_PASSWORD
"""
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

OAUTH_BASE = "https://4j1gkf0vji.execute-api.us-east-2.amazonaws.com/prod/v1"
INVOKER_BASE = "https://exo9f857n8.execute-api.us-east-2.amazonaws.com/prod/v1/invoker"
CLIENT_ID = "6qn9pep31dglq6ed4fvlq6rp5t"
USER_AGENT = "Smartwater-iOS-prod-3.39.0"

TARGET_DEVICE = "North Sump Pump"


def authenticate(username, password):
    resp = requests.post(
        f"{OAUTH_BASE}/oauth2/token",
        data=json.dumps({"client_id": CLIENT_ID, "username": username, "password": password}),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["token"]["access_token"]


def invoke_lambda(access_token, function_name, body, parse=False, escape=False):
    """Call Lambda via invoker endpoint."""
    resp = requests.post(
        INVOKER_BASE,
        json={"parse": parse, "escape": escape, "fn": function_name, "body": body},
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT, "Content-Type": "application/json"},
        timeout=30,
    )
    data = resp.json()
    # Some endpoints return a raw value (bool, list) rather than a StatusCode envelope
    if not isinstance(data, dict):
        return data
    if data.get("StatusCode") == 200:
        payload = data.get("Payload")
        if isinstance(payload, str):
            payload = json.loads(payload)
        if isinstance(payload, dict) and "body" in payload:
            body_val = payload["body"]
            return json.loads(body_val) if isinstance(body_val, str) else body_val
        return payload
    return {"error": data}


def get_shadow(access_token, client_id):
    return invoke_lambda(access_token, "smartwater-app-shadow-api-prod-get", {"clientId": client_id})


def print_shadow_alerts(shadow, label):
    alerts = shadow.get("state", {}).get("reported", {}).get("alerts", {})
    print(f"\n--- Shadow alerts ({label}) ---")
    if alerts:
        for aid, adata in alerts.items():
            print(f"  Alert {aid}: {adata.get('state')}")
    else:
        print("  (no alerts)")


def main():
    username = os.getenv("MOEN_USERNAME")
    password = os.getenv("MOEN_PASSWORD")
    if not username or not password:
        print("ERROR: Set MOEN_USERNAME and MOEN_PASSWORD in .env")
        return

    print("Authenticating...")
    token = authenticate(username, password)
    print("✓ Authenticated\n")

    devices = invoke_lambda(token, "smartwater-app-device-api-prod-list", {"locale": "en_US"})
    devices = devices if isinstance(devices, list) else []
    device = next((d for d in devices if d.get("nickname") == TARGET_DEVICE), None)
    if not device:
        print(f"ERROR: Could not find device '{TARGET_DEVICE}'")
        print(f"Available: {[d.get('nickname') for d in devices]}")
        return

    duid = device.get("duid")
    client_id = device.get("clientId")
    cognito_identity_id = device.get("federatedIdentity")

    print(f"Device:             {device['nickname']}")
    print(f"duid:               {duid}")
    print(f"clientId:           {client_id}")
    print(f"cognitoIdentityId:  {cognito_identity_id}")

    # Capture state before
    shadow_before = get_shadow(token, client_id)
    print_shadow_alerts(shadow_before, "BEFORE")

    # Call the shadow update Lambda with the correct body structure.
    # The Android app sends ShadowRequest(clientId, {"crockCommand": "rst_primary"})
    # which serializes as {"clientId": "<id>", "payload": {"crockCommand": "rst_primary"}}
    # with parse=True, escape=True.
    print(f"\nCalling smartwater-app-shadow-api-prod-update with rst_primary ...")
    result = invoke_lambda(
        token,
        "smartwater-app-shadow-api-prod-update",
        {"clientId": str(client_id), "payload": {"crockCommand": "rst_primary"}},
        parse=True,
        escape=True,
    )
    print(f"Response: {json.dumps(result, indent=2)}")

    print("\nWaiting 10s for shadow to update...")
    time.sleep(10)

    # Capture state after
    shadow_after = get_shadow(token, client_id)
    print_shadow_alerts(shadow_after, "AFTER")

    # Compare
    alerts_before = shadow_before.get("state", {}).get("reported", {}).get("alerts", {})
    alerts_after = shadow_after.get("state", {}).get("reported", {}).get("alerts", {})
    changed = {
        aid: (alerts_before.get(aid, {}).get("state"), alerts_after.get(aid, {}).get("state"))
        for aid in set(list(alerts_before) + list(alerts_after))
        if alerts_before.get(aid, {}).get("state") != alerts_after.get(aid, {}).get("state")
    }
    removed = set(alerts_before) - set(alerts_after)

    if changed or removed:
        print("\n✓ Alert state changes detected:")
        for aid, (before, after) in changed.items():
            print(f"  Alert {aid}: {before} → {after}")
        for aid in removed:
            print(f"  Alert {aid}: REMOVED from shadow")
    else:
        print("\n⚠ No alert state changes detected")


if __name__ == "__main__":
    main()
