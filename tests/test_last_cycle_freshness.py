"""
Check freshness of Last Cycle data from all relevant endpoints.

Compares:
  - lastOutgoTime from fbgpg_usage_v1_get_last_usage_prod
  - Most recent session from fbgpg_usage_v1_get_my_usage_device_history_prod

USAGE:
    python tests/test_last_cycle_freshness.py

Requires .env file with MOEN_USERNAME and MOEN_PASSWORD
"""
import json
import os
from pathlib import Path

import requests
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


def invoke_lambda(access_token, function_name, body, parse=False, escape=False):
    resp = requests.post(
        INVOKER_BASE,
        json={"parse": parse, "escape": escape, "fn": function_name, "body": body},
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT, "Content-Type": "application/json"},
        timeout=30,
    )
    data = resp.json()
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
    nab_devices = [d for d in devices if isinstance(d, dict) and d.get("deviceType") == "NAB"]

    for device in nab_devices:
        name = device.get("nickname", "Unknown")
        client_id = device.get("clientId")
        cognito = device.get("federatedIdentity")

        print(f"{'='*60}")
        print(f"Device: {name}  (clientId: {client_id})")
        print(f"{'='*60}")

        # get_last_usage
        last_usage = invoke_lambda(
            token,
            "fbgpg_usage_v1_get_last_usage_prod",
            {"cognitoIdentityId": cognito, "duid": str(client_id), "locale": "en_US"},
        )
        if isinstance(last_usage, dict):
            print(f"  lastOutgoTime:       {last_usage.get('lastOutgoTime', 'N/A')}")
            print(f"  estimatedNextRun:    {last_usage.get('estimatedNextRun', 'N/A')}")
            ms = last_usage.get("estimatedTimeUntilNextRunMS")
            if ms is not None:
                minutes = int(ms / 60000)
                h, m = divmod(minutes, 60)
                print(f"  timeUntilNextRun:    {h}h {m}m")
        else:
            print(f"  get_last_usage response: {last_usage}")

        # Session history via standard endpoint (parse=False, escape=False matches debug_pump_cycles_sensor.py)
        cycles = invoke_lambda(
            token,
            "fbgpg_usage_v1_get_my_usage_device_history_prod",
            {"cognitoIdentityId": cognito, "duid": str(client_id), "locale": "en_US", "limit": 5, "type": "session"},
        )
        sessions = cycles.get("usage", []) if isinstance(cycles, dict) else (cycles if isinstance(cycles, list) else [])
        print(f"\n  Session history (standard endpoint, {len(sessions)} returned):")
        for i, s in enumerate(sessions[:5]):
            ts = s.get("date") or s.get("timestamp") or s.get("startTime") or "?"
            print(f"    [{i+1}] {ts}")

        # Top-10 endpoint used by the app's overview/pump capacity screen
        # Hypothesis: this may be what triggers backend session processing
        top10 = invoke_lambda(
            token,
            "fbgpg_usage_v1_get_my_usage_device_history_top10_prod",
            {"cognitoIdentityId": cognito, "duid": str(client_id), "type": "session"},
            parse=True,
            escape=True,
        )
        top10_sessions = top10.get("usage", []) if isinstance(top10, dict) else (top10 if isinstance(top10, list) else [])
        print(f"\n  Session history (top10 endpoint, {len(top10_sessions)} returned):")
        for i, s in enumerate(top10_sessions[:5]):
            ts = s.get("date") or s.get("timestamp") or s.get("startTime") or "?"
            print(f"    [{i+1}] {ts}")

        print()


if __name__ == "__main__":
    main()
