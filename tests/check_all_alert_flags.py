"""
Check dismiss/silence flags for ALL alerts

BREAKTHROUGH: v2 endpoints return 'dismiss' and 'silence' boolean fields!
Let's check all alerts to see if different alerts have different flag values.
"""

import urllib.request
import json
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
    data = json.loads(resp_body)
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
    return {"error": data}


def main():
    username = os.getenv("MOEN_USERNAME")
    password = os.getenv("MOEN_PASSWORD")
    if not username or not password:
        print("ERROR: Set credentials")
        return

    print("=== CHECKING ALL ALERT FLAGS ===\n")
    access_token = authenticate(username, password)

    # Use v2 active endpoint to get ALL alerts with dismiss/silence fields
    result = invoke_lambda(access_token, "fbgpg_alerts_v2_get_alerts_active_by_user_prod", {})

    if isinstance(result, dict) and "alerts" in result:
        alerts = result["alerts"]
        print(f"Found {len(alerts)} active alerts\n")
        print("=" * 80)

        for alert in alerts:
            alert_id = alert.get('id')
            title = alert.get('title', 'N/A')
            state = alert.get('state', 'N/A')
            dismiss = alert.get('dismiss', 'MISSING')
            silence = alert.get('silence', 'MISSING')

            print(f"\nAlert {alert_id}: {title}")
            print(f"  State:   {state}")
            print(f"  Dismiss: {dismiss}")
            print(f"  Silence: {silence}")

            # Show full object for analysis
            print(f"  Full data: {json.dumps(alert, indent=4)}")
            print("-" * 80)

        # Summary
        print("\n\n=== SUMMARY ===")
        print(f"Total alerts: {len(alerts)}")
        dismissible = [a for a in alerts if a.get('dismiss') is True]
        silenceable = [a for a in alerts if a.get('silence') is True]
        print(f"Dismissible (dismiss=True): {len(dismissible)}")
        print(f"Silenceable (silence=True): {len(silenceable)}")

        if dismissible:
            print("\nDismissible alerts:")
            for a in dismissible:
                print(f"  - {a.get('id')}: {a.get('title')}")

        if silenceable:
            print("\nSilenceable alerts:")
            for a in silenceable:
                print(f"  - {a.get('id')}: {a.get('title')}")

        # Check for alert 218 specifically
        print("\n\n=== TARGET ALERT 218 'Main Pump Not Stopping' ===")
        alert_218 = next((a for a in alerts if a.get('id') == '218'), None)
        if alert_218:
            print("FOUND!")
            print(f"  Dismiss: {alert_218.get('dismiss')}")
            print(f"  Silence: {alert_218.get('silence')}")
            print(f"  State: {alert_218.get('state')}")
            if alert_218.get('dismiss') is True:
                print("\n✓✓✓ ALERT 218 IS DISMISSIBLE! ✓✓✓")
            else:
                print("\n✗✗✗ ALERT 218 IS NOT DISMISSIBLE ✗✗✗")
        else:
            print("NOT FOUND in active alerts")

    else:
        print(f"Unexpected response: {result}")


if __name__ == "__main__":
    main()
