"""
Test whether drop_on affects freshness of get_last_usage (estimatedNextRun).

Calls get_last_usage BEFORE and AFTER drop_on + 3s wait to see if the value
changes, confirming whether the drop_on flush is needed for this endpoint too.

USAGE:
    python tests/test_last_usage_staleness.py

Requires .env file with MOEN_USERNAME and MOEN_PASSWORD
"""

import requests
import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

OAUTH_BASE = "https://4j1gkf0vji.execute-api.us-east-2.amazonaws.com/prod/v1"
INVOKER_BASE = "https://exo9f857n8.execute-api.us-east-2.amazonaws.com/prod/v1/invoker"
CLIENT_ID = "6qn9pep31dglq6ed4fvlq6rp5t"
USER_AGENT = "Smartwater-iOS-prod-3.39.0"


def authenticate(username, password):
    resp = requests.post(
        f"{OAUTH_BASE}/oauth2/token",
        data=json.dumps({"client_id": CLIENT_ID, "username": username, "password": password}),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["token"]["access_token"]


def invoke_lambda(token, function_name, body=None, parse=True, escape=True):
    resp = requests.post(
        INVOKER_BASE,
        json={"parse": parse, "escape": escape, "fn": function_name, "body": body or {}},
        headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT, "Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        return data
    if "body" in data:
        inner = data["body"]
        return json.loads(inner) if isinstance(inner, str) else inner
    return data


def get_last_usage(token, client_id):
    return invoke_lambda(token, "fbgpg_usage_v1_get_last_usage_prod", {
        "cognitoIdentityId": "",
        "duid": str(client_id),
        "locale": "en_US",
    })


def drop_on(token, client_id):
    return invoke_lambda(token, "smartwater-app-shadow-api-prod-update", {
        "clientId": str(client_id),
        "payload": {"crockCommand": "drop_on"},
    })


def drop_off(token, client_id):
    return invoke_lambda(token, "smartwater-app-shadow-api-prod-update", {
        "clientId": str(client_id),
        "payload": {"crockCommand": "updates_off"},
    })


def main():
    username = os.environ["MOEN_USERNAME"]
    password = os.environ["MOEN_PASSWORD"]

    print("Authenticating...")
    token = authenticate(username, password)

    # Get device list
    devices_resp = invoke_lambda(token, "smartwater-app-device-api-prod-list", {})
    devices = [d for d in (devices_resp if isinstance(devices_resp, list) else []) if d.get("deviceType") == "NAB"]
    if not devices:
        print("No NAB devices found")
        return

    for device in devices:
        name = device.get("nickname", "Unknown")
        client_id = device.get("clientId")
        print(f"\n{'='*60}")
        print(f"Device: {name}  (clientId: {client_id})")
        print(f"{'='*60}")

        # Step 1: get_last_usage BEFORE drop_on
        print("\n[1] get_last_usage BEFORE drop_on:")
        before = get_last_usage(token, client_id)
        before_next = before.get("estimatedNextRun", "N/A")
        before_ms = before.get("estimatedTimeUntilNextRunMS", "N/A")
        before_last = before.get("lastOutgoTime", "N/A")
        print(f"  estimatedNextRun:           {before_next}")
        print(f"  estimatedTimeUntilNextRunMS: {before_ms}")
        print(f"  lastOutgoTime:              {before_last}")

        # Step 2: drop_on
        print("\n[2] Sending drop_on...")
        result = drop_on(token, client_id)
        print(f"  Response: {result}")

        # Step 3: wait 3s
        print("\n[3] Waiting 3 seconds...")
        time.sleep(3)

        # Step 4: get_last_usage AFTER drop_on
        print("\n[4] get_last_usage AFTER drop_on + 3s:")
        after = get_last_usage(token, client_id)
        after_next = after.get("estimatedNextRun", "N/A")
        after_ms = after.get("estimatedTimeUntilNextRunMS", "N/A")
        after_last = after.get("lastOutgoTime", "N/A")
        print(f"  estimatedNextRun:           {after_next}")
        print(f"  estimatedTimeUntilNextRunMS: {after_ms}")
        print(f"  lastOutgoTime:              {after_last}")

        # Step 5: drop_off
        print("\n[5] Sending updates_off...")
        drop_off(token, client_id)

        # Summary
        print("\n--- Summary ---")
        changed = before_next != after_next or before_last != after_last
        print(f"  estimatedNextRun changed:  {'YES' if before_next != after_next else 'no'}")
        print(f"  lastOutgoTime changed:     {'YES' if before_last != after_last else 'no'}")
        if changed:
            print("  → drop_on DOES affect get_last_usage freshness")
        else:
            print("  → drop_on does NOT change get_last_usage output (already fresh or different trigger needed)")


if __name__ == "__main__":
    main()
