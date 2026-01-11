"""
Debug pump cycle timing issues

Investigates:
1. Last pump cycle time discrepancy (app vs HA)
2. Pump cycles last 15 minutes calculation

USAGE:
    python tests/debug_pump_cycle_timing.py

Requires .env file with MOEN_USERNAME and MOEN_PASSWORD
"""

import requests
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
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
    print("=== AUTHENTICATING ===")
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

    access_token = data["token"]["access_token"]
    print("✓ Authenticated\n")
    return access_token


def invoke_lambda(access_token, function_name, body):
    """Call Lambda function via invoker endpoint"""
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

        # Handle double-encoded JSON
        if isinstance(payload_val, str):
            try:
                payload_val = json.loads(payload_val)
            except:
                pass

        # Handle nested body structure
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
        raise Exception(f"Lambda error: {data}")


def parse_timestamp(ts_str):
    """Parse ISO timestamp to datetime"""
    if ts_str.endswith('Z'):
        ts_str = ts_str.replace('Z', '+00:00')
    return datetime.fromisoformat(ts_str)


def main():
    import os
    username = os.getenv("MOEN_USERNAME")
    password = os.getenv("MOEN_PASSWORD")

    if not username or not password:
        print("ERROR: Set MOEN_USERNAME and MOEN_PASSWORD in .env file")
        return

    # Authenticate
    access_token = authenticate(username, password)

    # Get devices
    print("=== GETTING DEVICES ===")
    devices_resp = invoke_lambda(access_token, "smartwater-app-device-api-prod-list", {"locale": "en_US"})
    devices = devices_resp if isinstance(devices_resp, list) else []

    print(f"Total devices: {len(devices)}")
    for d in devices:
        print(f"  - {d.get('nickname', 'Unknown')} (Type: {d.get('deviceType', 'Unknown')})")

    nab_devices = [d for d in devices if d.get("deviceType") == "NAB"]

    if not nab_devices:
        print("\nNo NAB devices found (filtering by deviceType=='NAB')")
        print("Trying first device regardless of type...")
        if devices:
            nab_devices = [devices[0]]
        else:
            print("No devices at all!")
            return

    device = nab_devices[0]
    device_uuid = device.get("duid")
    nickname = device.get("nickname", "Unknown")

    print(f"✓ Found device: {nickname}")
    print(f"  UUID: {device_uuid}\n")

    # Get pump cycles
    print("=== GETTING PUMP CYCLES ===")
    client_id = device.get("clientId")
    cycles_resp = invoke_lambda(access_token, "fbgpg_usage_v1_get_my_usage_device_history_prod", {
        "duid": client_id,
        "type": "session",
        "limit": 50,
        "locale": "en_US"
    })
    # Extract usage array from response (same as API client does)
    if isinstance(cycles_resp, dict) and "usage" in cycles_resp:
        pump_cycles = cycles_resp["usage"]
    elif isinstance(cycles_resp, list):
        pump_cycles = cycles_resp
    else:
        pump_cycles = []

    print(f"Total pump cycles: {len(pump_cycles)}\n")

    if not pump_cycles:
        print("No pump cycles found")
        return

    # Get event logs (what HA uses for "last_cycle")
    print("=== GETTING EVENT LOGS ===")
    events_resp = invoke_lambda(access_token, "fbgpg_logs_v1_get_device_logs_user_prod", {
        "cognitoIdentityId": None,  # Will be filled by API
        "duid": device_uuid,
        "limit": 50,
        "locale": "en_US"
    })

    # Extract events array from response (same as API client does)
    if isinstance(events_resp, dict) and "events" in events_resp:
        events = events_resp["events"]
    elif isinstance(events_resp, list):
        events = events_resp
    else:
        events = []

    print(f"Total events: {len(events)}\n")

    # Current time
    now = datetime.now(timezone.utc)
    now_local = datetime.now()
    print(f"Current time (UTC): {now.isoformat()}")
    print(f"Current time (local): {now_local.strftime('%Y-%m-%d %I:%M:%S %p')}\n")

    # Analyze most recent pump cycles
    print("=== MOST RECENT PUMP CYCLES (from session data) ===")
    for i, cycle in enumerate(pump_cycles[:10]):
        cycle_time_str = cycle.get("date", "")
        if not cycle_time_str:
            continue

        cycle_time = parse_timestamp(cycle_time_str)
        minutes_ago = (now - cycle_time).total_seconds() / 60

        # Get cycle details
        fill_volume = cycle.get("fillVolume", 0)
        empty_volume = cycle.get("emptyVolume", 0)
        fill_time_ms = cycle.get("fillTimeMS", 0)
        empty_time_ms = cycle.get("emptyTimeMS", 0)

        print(f"\nCycle {i+1}:")
        print(f"  Timestamp (raw): {cycle_time_str}")
        print(f"  Timestamp (UTC): {cycle_time.strftime('%Y-%m-%d %I:%M:%S %p %Z')}")
        print(f"  Time ago: {minutes_ago:.1f} minutes")
        print(f"  Fill: {fill_volume} gal in {fill_time_ms}ms")
        print(f"  Empty: {empty_volume} gal in {empty_time_ms}ms")

    # Check what "last_cycle" event log returns
    print("\n=== MOST RECENT EVENT (what HA uses for last_cycle) ===")
    if events:
        last_event = events[0]
        event_time_str = last_event.get("time", "")
        event_id = last_event.get("id", "")
        event_title = last_event.get("title", "")

        print(f"Event ID: {event_id}")
        print(f"Event Title: {event_title}")
        print(f"Timestamp (raw): {event_time_str}")

        if event_time_str:
            # This is how HA parses it
            time_str_parsed = event_time_str.split('.')[0].replace('Z', '')
            event_time = datetime.fromisoformat(time_str_parsed)
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)

            print(f"Timestamp (parsed): {event_time.isoformat()}")
            print(f"Timestamp (display): {event_time.strftime('%Y-%m-%d %I:%M:%S %p %Z')}")

            minutes_ago = (now - event_time).total_seconds() / 60
            print(f"Time ago: {minutes_ago:.1f} minutes")

            # Compare with most recent pump cycle
            if pump_cycles:
                cycle_time = parse_timestamp(pump_cycles[0].get("date", ""))
                time_diff = (event_time - cycle_time).total_seconds() / 60
                print(f"\n⚠ DISCREPANCY CHECK:")
                print(f"  Event log time:  {event_time.strftime('%I:%M:%S %p')}")
                print(f"  Pump cycle time: {cycle_time.strftime('%I:%M:%S %p')}")
                print(f"  Difference: {abs(time_diff):.1f} minutes")

                if abs(time_diff) > 1:
                    print(f"  ✗ MISMATCH DETECTED!")
                    print(f"  Event log is NOT a pump cycle event")
                    print(f"  HA 'Last Pump Cycle' sensor uses event log, NOT pump cycle data!")
                else:
                    print(f"  ✓ Times match")

    # Analyze 15-minute window
    print("\n=== CYCLES IN LAST 15 MINUTES ===")
    cutoff_time = now - timedelta(minutes=15)
    print(f"Cutoff time (15 min ago): {cutoff_time.strftime('%Y-%m-%d %I:%M:%S %p %Z')}\n")

    cycles_in_window = []
    for cycle in pump_cycles:
        cycle_time_str = cycle.get("date", "")
        if not cycle_time_str:
            continue

        cycle_time = parse_timestamp(cycle_time_str)

        # This is the EXACT calculation HA uses
        minutes_ago = (now - cycle_time).total_seconds() / 60

        if minutes_ago <= 15:
            cycles_in_window.append({
                "time": cycle_time,
                "time_str": cycle_time_str,
                "minutes_ago": minutes_ago
            })

    print(f"Cycles found in last 15 minutes: {len(cycles_in_window)}")
    if cycles_in_window:
        for i, cycle in enumerate(cycles_in_window, 1):
            print(f"  {i}. {cycle['time'].strftime('%I:%M:%S %p')} ({cycle['minutes_ago']:.1f} min ago)")
    else:
        print("  None found")

        # Show how long ago the most recent cycle was
        if pump_cycles:
            most_recent = parse_timestamp(pump_cycles[0].get("date", ""))
            minutes_ago = (now - most_recent).total_seconds() / 60
            print(f"\n  Most recent cycle was {minutes_ago:.1f} minutes ago")
            if minutes_ago > 15:
                print(f"  ✓ This explains why sensor shows 0")

    # Simulate HA sensor calculation
    print("\n=== SIMULATING HA SENSOR CALCULATION ===")
    print("Code: MoenFloNABPumpCyclesLast15MinSensor.native_value")
    print(f"now = datetime.now(timezone.utc)  # {now.isoformat()}")
    print(f"pump_cycles = {len(pump_cycles)} cycles")
    print("recent_cycles = 0")
    print("for cycle in pump_cycles:")

    simulated_count = 0
    for i, cycle in enumerate(pump_cycles[:20]):
        cycle_time_str = cycle.get("date", "")
        if not cycle_time_str:
            continue

        cycle_time = parse_timestamp(cycle_time_str)
        minutes_ago = (now - cycle_time).total_seconds() / 60

        is_in_window = minutes_ago <= 15
        if is_in_window:
            simulated_count += 1

        if i < 5 or is_in_window:  # Show first 5 and all in window
            print(f"  cycle_time = {cycle_time.strftime('%I:%M:%S %p')}")
            print(f"  minutes_ago = {minutes_ago:.2f}")
            print(f"  if minutes_ago <= 15: recent_cycles += 1  # {'YES' if is_in_window else 'NO'}")

        if minutes_ago > 15 and i >= 5:
            print(f"  ... (remaining {len(pump_cycles) - i} cycles are older)")
            break

    print(f"\nSimulated sensor value: {simulated_count}")
    print(f"Expected value: {len(cycles_in_window)}")
    print(f"Match: {'✓' if simulated_count == len(cycles_in_window) else '✗'}")

    # Save detailed output
    output_file = Path(__file__).parent / f"pump_cycle_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_data = {
        "current_time_utc": now.isoformat(),
        "current_time_local": now_local.isoformat(),
        "device": {
            "uuid": device_uuid,
            "nickname": nickname
        },
        "pump_cycles": {
            "total": len(pump_cycles),
            "in_last_15_min": len(cycles_in_window),
            "simulated_sensor_value": simulated_count,
            "most_recent": pump_cycles[0].get("date") if pump_cycles else None
        },
        "event_log": {
            "most_recent_event_id": events[0].get("id") if events else None,
            "most_recent_event_title": events[0].get("title") if events else None,
            "most_recent_event_time": events[0].get("time") if events else None,
        },
        "cycles_in_window": [
            {
                "timestamp": c["time_str"],
                "minutes_ago": round(c["minutes_ago"], 2)
            }
            for c in cycles_in_window
        ],
        "recent_cycles": [
            {
                "timestamp": cycle.get("date"),
                "fill_volume": cycle.get("fillVolume"),
                "empty_volume": cycle.get("emptyVolume"),
                "fill_time_ms": cycle.get("fillTimeMS"),
                "empty_time_ms": cycle.get("emptyTimeMS"),
            }
            for cycle in pump_cycles[:20]
        ]
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\n✓ Detailed output saved to: {output_file.name}")


if __name__ == "__main__":
    main()
