#!/usr/bin/env python3
"""Debug script to analyze pump cycle data for threshold calculation."""
import requests
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from statistics import median

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

    print("=" * 80)
    print("Pump Threshold Calculation Test")
    print("=" * 80)

    # Authenticate
    print("\nAuthenticating...")
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
    print("=" * 80)

    # Get pump cycles
    print("\nFetching pump cycles (last 20)...")
    pump_cycles = invoke_lambda(
        access_token,
        "fbgpg_usage_v1_get_my_usage_device_history_prod",
        {
            "cognitoIdentityId": cognito_id,
            "duid": str(client_id),
            "type": "session",
            "limit": 20,
            "locale": "en_US"
        }
    )

    # Handle response structure
    if isinstance(pump_cycles, dict) and "usage" in pump_cycles:
        pump_cycles = pump_cycles["usage"]
    elif not isinstance(pump_cycles, list):
        print(f"⚠ Unexpected response type: {type(pump_cycles)}")
        print(f"Response: {pump_cycles}")
        return

    print(f"Total cycles returned: {len(pump_cycles)}\n")

    if not pump_cycles:
        print("⚠ No pump cycles data returned!")
        return

    # Show structure of first cycle
    print("=" * 80)
    print("FIRST CYCLE DATA STRUCTURE")
    print("=" * 80)
    print(json.dumps(pump_cycles[0], indent=2))
    print("\n")

    # Analyze all cycles for water level data
    print("=" * 80)
    print("ANALYZING CYCLES FOR WATER LEVEL DATA")
    print("=" * 80)

    on_distances = []
    off_distances = []

    for i, cycle in enumerate(pump_cycles[:20]):
        print(f"\nCycle {i+1}:")
        print(f"  Date: {cycle.get('date')}")

        # Check all possible fields for water level data
        water_out = cycle.get("waterOut", {})
        water_in = cycle.get("waterIn", {})

        print(f"  waterOut: {water_out}")
        print(f"  waterIn: {water_in}")

        # Look for distance/level fields
        for key, value in cycle.items():
            if 'distance' in key.lower() or 'level' in key.lower() or 'tof' in key.lower():
                print(f"  {key}: {value}")

        # Try to extract meaningful data
        # waterOut typically has the pump cycle data
        if isinstance(water_out, dict):
            # Check for start/end level fields
            if "startLevel" in water_out:
                on_distances.append(water_out["startLevel"])
                print(f"  → Pump ON distance: {water_out['startLevel']} mm")
            if "endLevel" in water_out:
                off_distances.append(water_out["endLevel"])
                print(f"  → Pump OFF distance: {water_out['endLevel']} mm")

    print("\n" + "=" * 80)
    print("THRESHOLD CALCULATION RESULTS")
    print("=" * 80)

    if on_distances and off_distances:
        pump_on = int(median(on_distances))
        pump_off = int(median(off_distances))

        print(f"\n✓ Successfully extracted thresholds from {len(on_distances)} cycles")
        print(f"\nPump ON distances (basin full): {on_distances}")
        print(f"  → Median: {pump_on} mm")
        print(f"\nPump OFF distances (basin empty): {off_distances}")
        print(f"  → Median: {pump_off} mm")
        print(f"\nRange: {pump_off - pump_on} mm")

        # Test calculation with example current distance
        if pump_cycles:
            print("\n" + "-" * 80)
            print("EXAMPLE BASIN FULLNESS CALCULATIONS")
            print("-" * 80)

            test_distances = [pump_on, pump_on + 10, (pump_on + pump_off) // 2, pump_off - 10, pump_off]
            for dist in test_distances:
                fullness = 100 - ((dist - pump_on) / (pump_off - pump_on) * 100)
                fullness = max(0, min(100, round(fullness, 0)))
                print(f"  Distance {dist}mm → Basin {fullness}% full")
    else:
        print("\n✗ Could not extract water level data from cycles")
        print("\nAvailable fields in first cycle:")
        if pump_cycles:
            for key in pump_cycles[0].keys():
                print(f"  - {key}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
