"""
Test whether (now + estimatedTimeUntilNextRunMS) gives a more accurate
"Estimated Next Pump Cycle" than the raw estimatedNextRun field.

Compare both values against the Moen app display.

USAGE:
    python tests/test_estimated_next_cycle.py

Requires .env file with MOEN_USERNAME and MOEN_PASSWORD
"""

import requests
import json
import os
from datetime import datetime, timezone, timedelta
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


def invoke_lambda(token, fn, body=None):
    resp = requests.post(
        INVOKER_BASE,
        json={"parse": True, "escape": True, "fn": fn, "body": body or {}},
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


def fmt_local(dt):
    """Format UTC datetime as local-ish string for easy comparison with app."""
    if dt is None:
        return "N/A"
    # Convert to ET (UTC-4 during EDT)
    et = dt - timedelta(hours=4)
    return et.strftime("%I:%M %p ET")


def app_display_text(ms_until):
    """Mirror the app's calculateNextRunEstimate threshold logic."""
    if ms_until is None:
        return "N/A (no field)"
    s = ms_until / 1000
    if s < -3600:
        return "Pump may run depending on weather"
    elif s < -60:
        return "Within an hour"
    elif s < 0:
        return "Soon"
    elif s < 60:
        return f"In {int(s)} seconds"
    elif s < 3600:
        return f"In {int(s/60)} minutes"
    elif s < 43200:
        return f"In {round(s/3600, 1)} hours"
    else:
        return "Pump may run depending on weather"


def ha_sensor_value(now_utc, ms_until, estimated_next_run):
    """Proposed HA sensor native_value with correct thresholds."""
    # App checks estimatedNextRun first
    if estimated_next_run is None or estimated_next_run == "-1":
        return None, "None (no estimatedNextRun)"
    if ms_until is None:
        dt = datetime.fromisoformat(estimated_next_run.replace("Z", "+00:00"))
        return dt, f"fallback to estimatedNextRun: {fmt_local(dt)}"
    s = ms_until / 1000
    if s < -3600 or s >= 43200:
        return None, "None (out of range)"
    raw = now_utc + timedelta(milliseconds=ms_until)
    if raw.second >= 30:
        rounded = raw.replace(second=0, microsecond=0) + timedelta(minutes=1)
    else:
        rounded = raw.replace(second=0, microsecond=0)
    return rounded, fmt_local(rounded)


def ha_sensor_value_current(now_utc, ms_until, estimated_next_run):
    """Current (b2) HA sensor logic for comparison."""
    if ms_until is not None:
        if ms_until <= 0:
            return None, "None (ms_until <= 0 — BUG)"
        raw = now_utc + timedelta(milliseconds=ms_until)
        if raw.second >= 30:
            rounded = raw.replace(second=0, microsecond=0) + timedelta(minutes=1)
        else:
            rounded = raw.replace(second=0, microsecond=0)
        return rounded, fmt_local(rounded)
    if estimated_next_run:
        dt = datetime.fromisoformat(estimated_next_run.replace("Z", "+00:00"))
        return dt, fmt_local(dt)
    return None, "None"


def main():
    username = os.environ["MOEN_USERNAME"]
    password = os.environ["MOEN_PASSWORD"]

    print("Authenticating...")
    token = authenticate(username, password)

    devices_resp = invoke_lambda(token, "smartwater-app-device-api-prod-list")
    devices = [d for d in (devices_resp if isinstance(devices_resp, list) else []) if d.get("deviceType") == "NAB"]

    now_utc = datetime.now(timezone.utc)
    print(f"\nCurrent time: {fmt_local(now_utc)} ({now_utc.strftime('%H:%M:%S')} UTC)\n")

    for device in devices:
        name = device.get("nickname", "Unknown")
        client_id = device.get("clientId")

        print(f"{'='*60}")
        print(f"Device: {name}")
        print(f"{'='*60}")

        lu = invoke_lambda(token, "fbgpg_usage_v1_get_last_usage_prod", {
            "cognitoIdentityId": "", "duid": str(client_id), "locale": "en_US",
        })

        raw_next = lu.get("estimatedNextRun")
        ms_until = lu.get("estimatedTimeUntilNextRunMS")
        last_outgo = lu.get("lastOutgoTime")

        s_until = ms_until / 1000 if ms_until is not None else None
        zone = app_display_text(ms_until)
        _, cur = ha_sensor_value_current(now_utc, ms_until, raw_next)
        _, prop = ha_sensor_value(now_utc, ms_until, raw_next)

        print(f"  lastOutgoTime:              {fmt_local(datetime.fromisoformat(last_outgo.replace('Z', '+00:00'))) if last_outgo else 'N/A'}")
        print(f"  estimatedTimeUntilNextRunMS: {ms_until} ({round(s_until/60, 1) if s_until is not None else '?'} min)")
        print()
        print(f"  App display text:  {zone}")
        print(f"  [CURRENT b2] HA:   {cur}")
        print(f"  [PROPOSED]   HA:   {prop}")
        print()
        print(f"  >>> Compare App display with what the Moen app shows for '{name}'")
        print()


if __name__ == "__main__":
    main()
