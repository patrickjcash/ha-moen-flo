"""
Dump raw active alerts from v2 API to inspect severity, dismiss, and other fields.

USAGE:
    python tests/dump_active_alerts.py

Requires .env file with MOEN_USERNAME and MOEN_PASSWORD
"""

import requests
import json
import os
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


def invoke_lambda(token, function_name, body=None):
    resp = requests.post(
        INVOKER_BASE,
        json={"parse": True, "escape": True, "fn": function_name, "body": body or {}},
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


def main():
    username = os.environ["MOEN_USERNAME"]
    password = os.environ["MOEN_PASSWORD"]

    print("Authenticating...")
    token = authenticate(username, password)

    print("\n=== fbgpg_alerts_v2_get_alerts_active_by_user_prod (raw) ===\n")
    result = invoke_lambda(token, "fbgpg_alerts_v2_get_alerts_active_by_user_prod")
    alerts = result.get("alerts", []) if isinstance(result, dict) else []

    print(f"Total alerts returned: {len(alerts)}\n")
    for alert in alerts:
        print(json.dumps(alert, indent=2))
        print()


if __name__ == "__main__":
    main()
