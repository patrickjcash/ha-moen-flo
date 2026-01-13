#!/usr/bin/env python3
"""Debug script to check pump cycles sensor data."""
import requests
import json
import os
from pathlib import Path
from datetime import datetime, timezone
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


def invoke_lambda(access_token, function_name, body_params):
    """Call Lambda function"""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json"
    }
    payload = {
        "parse": False,
        "body": body_params,
        "fn": function_name,
        "escape": False
    }

    resp = requests.post(INVOKER_BASE, json=payload, headers=headers, timeout=30)
    if resp.status_code == 204:
        return {"success": True, "message": "204 No Content"}
    resp.raise_for_status()

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
    return data


def main():
    """Main function."""
    username = os.getenv('MOEN_USERNAME')
    password = os.getenv('MOEN_PASSWORD')

    if not username or not password:
        print("Error: MOEN_USERNAME and MOEN_PASSWORD must be set in .env file")
        return

    # Authenticate
    print("Authenticating...")
    access_token = authenticate(username, password)
    print("✓ Authenticated")

    # Get devices
    devices = invoke_lambda(access_token, "smartwater-app-device-api-prod-list", {})
    nab_devices = [d for d in devices if d.get("deviceType") == "NAB"]

    if not nab_devices:
        print("No NAB devices found")
        return

    device = nab_devices[0]
    client_id = device.get("clientId")
    device_name = device.get("nickname", "Unknown")
    cognito_id = device.get("federatedIdentity")

    print(f"\nDevice: {device_name} (clientId: {client_id})")
    print(f"Cognito ID: {cognito_id}")
    print("=" * 60)

    # Get pump cycles
    print("\nFetching pump cycles (last 50)...")
    pump_cycles = invoke_lambda(
        access_token,
        "fbgpg_usage_v1_get_my_usage_device_history_prod",
        {
            "cognitoIdentityId": cognito_id,
            "duid": str(client_id),
            "type": "session",
            "limit": 50,
            "locale": "en_US"
        }
    )

    # Handle response structure - may be dict with "usage" key or list
    if isinstance(pump_cycles, dict) and "usage" in pump_cycles:
        pump_cycles = pump_cycles["usage"]
    elif not isinstance(pump_cycles, list):
        print(f"⚠ Unexpected response type: {type(pump_cycles)}")
        print(f"Response: {pump_cycles}")
        return

    print(f"Total cycles returned: {len(pump_cycles)}")

    if not pump_cycles:
        print("⚠ No pump cycles data returned!")
        return

    # Check last 15 minutes
    now = datetime.now(timezone.utc)
    recent_cycles = []

    print(f"\nCurrent time: {now.strftime('%Y-%m-%d %I:%M:%S %p %Z')}")
    print("\nAnalyzing cycles for last 15 minutes...")

    for i, cycle in enumerate(pump_cycles[:10]):  # Check first 10
        cycle_time_str = cycle.get("date", "")
        if cycle_time_str:
            try:
                # Parse timestamp
                cycle_time = datetime.fromisoformat(cycle_time_str.replace("Z", "+00:00"))
                minutes_ago = (now - cycle_time).total_seconds() / 60

                print(f"\nCycle {i+1}:")
                print(f"  Timestamp: {cycle_time_str}")
                print(f"  Parsed: {cycle_time.strftime('%Y-%m-%d %I:%M:%S %p %Z')}")
                print(f"  Minutes ago: {minutes_ago:.1f}")

                if minutes_ago <= 15:
                    recent_cycles.append(cycle)
                    print(f"  ✓ Within 15 minutes")
                else:
                    print(f"  ✗ Too old (>{minutes_ago:.1f} min ago)")
            except Exception as e:
                print(f"  ✗ Error parsing: {e}")

    print("\n" + "=" * 60)
    print(f"RESULT: {len(recent_cycles)} cycles in last 15 minutes")

    if recent_cycles:
        print("\nRecent cycles:")
        for cycle in recent_cycles:
            water_out = cycle.get("waterOut", {})
            volume = water_out.get("value", 0)
            duration = water_out.get("duration", 0)
            print(f"  - {cycle.get('date')} | Volume: {volume:.1f} gal | Duration: {duration:.1f}s")
    else:
        print("\n⚠ No cycles found in last 15 minutes")
        if pump_cycles:
            latest = pump_cycles[0]
            latest_time = datetime.fromisoformat(latest.get("date", "").replace("Z", "+00:00"))
            minutes_ago = (now - latest_time).total_seconds() / 60
            print(f"\nMost recent cycle was {minutes_ago:.1f} minutes ago")
            print(f"Timestamp: {latest.get('date')}")


if __name__ == "__main__":
    main()
