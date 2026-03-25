"""
Test whether sending crockCommand: drop_on triggers backend session processing.

Procedure:
  1. Fetch session history (baseline)
  2. Send drop_on shadow command
  3. Wait a few seconds
  4. Fetch session history again
  5. Compare — new sessions or updated timestamps indicate the trigger works

USAGE:
    python tests/test_drop_on_trigger.py

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
WAIT_SECONDS = 10


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


def get_sessions(token, cognito, client_id, label):
    # Try parse=False first (known-working per debug_pump_cycles_sensor.py)
    result = invoke_lambda(
        token,
        "fbgpg_usage_v1_get_my_usage_device_history_prod",
        {"cognitoIdentityId": cognito, "duid": str(client_id), "locale": "en_US", "limit": 5, "type": "session"},
        parse=False,
        escape=False,
    )
    if isinstance(result, dict) and "usage" in result:
        sessions = result["usage"]
    elif isinstance(result, list):
        sessions = result
    else:
        print(f"  [{label}] unexpected response type {type(result).__name__}: {str(result)[:200]}")
        sessions = []
    print(f"  [{label}] {len(sessions)} session(s) returned:")
    for i, s in enumerate(sessions[:5]):
        ts = s.get("date") or s.get("timestamp") or s.get("startTime") or "?"
        print(f"    [{i+1}] {ts}")
    return [s.get("date") or s.get("timestamp") or s.get("startTime") for s in sessions]


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

        # Step 1: baseline session history
        before = get_sessions(token, cognito, client_id, "BEFORE drop_on")

        # Step 2: send drop_on
        print(f"\n  Sending crockCommand: drop_on ...")
        result = invoke_lambda(
            token,
            "smartwater-app-shadow-api-prod-update",
            {"clientId": str(client_id), "payload": {"crockCommand": "drop_on"}},
            parse=True,
            escape=True,
        )
        # {"error": {"status": True}} means the invoker returned {"status": True} directly
        # (no StatusCode wrapper) — this is the expected success response
        status = result.get("status") if isinstance(result, dict) else (result.get("error", {}).get("status") if isinstance(result, dict) else None)
        ok = status is True or (isinstance(result, dict) and result.get("error", {}).get("status") is True)
        print(f"  drop_on response: {result}  →  {'✓ accepted' if ok else '✗ unexpected'}")

        # Step 3: wait
        print(f"\n  Waiting {WAIT_SECONDS}s for backend to process...")
        time.sleep(WAIT_SECONDS)

        # Step 4: fetch history again
        after = get_sessions(token, cognito, client_id, "AFTER drop_on")

        # Step 5: send updates_off (mirrors app pausing the overview screen)
        print(f"\n  Sending crockCommand: updates_off ...")
        invoke_lambda(
            token,
            "smartwater-app-shadow-api-prod-update",
            {"clientId": str(client_id), "payload": {"crockCommand": "updates_off"}},
            parse=True,
            escape=True,
        )
        print(f"  updates_off sent")

        # Step 6: compare
        new_sessions = [ts for ts in after if ts not in before]
        if new_sessions:
            print(f"\n  ✓ {len(new_sessions)} NEW session(s) appeared after drop_on:")
            for ts in new_sessions:
                print(f"    {ts}")
        elif after != before:
            print(f"\n  ~ Session list changed (different order or timestamps)")
        else:
            print(f"\n  ✗ No change in session history after {WAIT_SECONDS}s")
            print(f"    (drop_on is accepted; inconclusive if no unprocessed cycles exist at test time)")

        print()


if __name__ == "__main__":
    main()
