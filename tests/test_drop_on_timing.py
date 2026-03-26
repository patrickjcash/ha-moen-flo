"""
Test drop_on timing: does it reliably trigger backend session processing,
and how long does it take for get_last_usage and get_pump_cycles to reflect fresh data?

Polls both endpoints repeatedly after drop_on to find the actual latency.

USAGE:
    python tests/test_drop_on_timing.py

Requires .env file with MOEN_USERNAME and MOEN_PASSWORD
"""

import requests
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

OAUTH_BASE = "https://4j1gkf0vji.execute-api.us-east-2.amazonaws.com/prod/v1"
INVOKER_BASE = "https://exo9f857n8.execute-api.us-east-2.amazonaws.com/prod/v1/invoker"
CLIENT_ID = "6qn9pep31dglq6ed4fvlq6rp5t"
USER_AGENT = "Smartwater-iOS-prod-3.39.0"
POLL_SECONDS = [0, 3, 10, 20, 30, 45, 60]


def authenticate(username, password):
    resp = requests.post(
        f"{OAUTH_BASE}/oauth2/token",
        data=json.dumps({"client_id": CLIENT_ID, "username": username, "password": password}),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["token"]["access_token"]


def invoke_lambda(token, fn, body=None, parse=True, escape=True):
    resp = requests.post(
        INVOKER_BASE,
        json={"parse": parse, "escape": escape, "fn": fn, "body": body or {}},
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
        "cognitoIdentityId": "", "duid": str(client_id), "locale": "en_US",
    })


def get_cognito_id(token, client_id, devices_resp):
    for d in (devices_resp if isinstance(devices_resp, list) else []):
        if d.get("clientId") == client_id:
            return d.get("federatedIdentity", "")
    return ""


def get_pump_cycles(token, client_id, cognito_id, limit=5):
    result = invoke_lambda(token, "fbgpg_usage_v1_get_my_usage_device_history_prod", {
        "cognitoIdentityId": cognito_id, "duid": str(client_id),
        "type": "session", "limit": limit, "locale": "en_US",
    })
    if isinstance(result, dict) and "usage" in result:
        return result["usage"]
    return result if isinstance(result, list) else []


def shadow_cmd(token, client_id, cmd):
    return invoke_lambda(token, "smartwater-app-shadow-api-prod-update", {
        "clientId": str(client_id), "payload": {"crockCommand": cmd},
    })


def snapshot(token, client_id, cognito_id):
    lu = get_last_usage(token, client_id)
    sessions = get_pump_cycles(token, client_id, cognito_id)
    latest_cycle = sessions[0].get("date", "N/A") if sessions else "N/A"
    return {
        "lastOutgoTime": lu.get("lastOutgoTime", "N/A"),
        "estimatedNextRun": lu.get("estimatedNextRun", "N/A"),
        "estimatedMinsUntil": round(lu.get("estimatedTimeUntilNextRunMS", 0) / 60000, 1),
        "latestCycle": latest_cycle,
        "cycleCount": len(sessions),
    }


def main():
    username = os.environ["MOEN_USERNAME"]
    password = os.environ["MOEN_PASSWORD"]

    print("Authenticating...")
    token = authenticate(username, password)

    devices_resp = invoke_lambda(token, "smartwater-app-device-api-prod-list", {})
    devices = [d for d in (devices_resp if isinstance(devices_resp, list) else []) if d.get("deviceType") == "NAB"]
    if not devices:
        print("No NAB devices found")
        return

    for device in devices:
        name = device.get("nickname", "Unknown")
        client_id = device.get("clientId")
        cognito_id = device.get("federatedIdentity", "")
        print(f"\n{'='*60}")
        print(f"Device: {name}  (clientId: {client_id})")
        print(f"{'='*60}")

        # Baseline before drop_on
        print("\n[BASELINE] Before drop_on:")
        base = snapshot(token, client_id, cognito_id)
        for k, v in base.items():
            print(f"  {k}: {v}")

        # Send drop_on
        print(f"\n[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Sending drop_on...")
        shadow_cmd(token, client_id, "drop_on")
        t0 = time.time()

        prev = base.copy()
        changed_at = {}

        for wait in POLL_SECONDS:
            elapsed = time.time() - t0
            sleep_for = max(0, wait - elapsed)
            if sleep_for > 0:
                time.sleep(sleep_for)

            now_str = datetime.now(timezone.utc).strftime('%H:%M:%S')
            actual_elapsed = round(time.time() - t0, 1)
            s = snapshot(token, client_id, cognito_id)
            changes = [k for k in s if s[k] != prev[k]]

            print(f"\n[+{actual_elapsed}s / {now_str}]")
            for k, v in s.items():
                marker = " ← CHANGED" if k in changes else ""
                print(f"  {k}: {v}{marker}")

            for k in changes:
                if k not in changed_at:
                    changed_at[k] = actual_elapsed

            prev = s.copy()

        # Send updates_off
        shadow_cmd(token, client_id, "updates_off")
        print(f"\n[updates_off sent]")

        print("\n--- Summary ---")
        if changed_at:
            for k, t in changed_at.items():
                print(f"  {k} first changed at +{t}s after drop_on")
        else:
            print("  No fields changed during the observation window.")
            print("  → drop_on is NOT triggering backend processing within 60s")


if __name__ == "__main__":
    main()
