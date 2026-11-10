#!/usr/bin/env python3
"""
Live test for PR #5: can sens_on go through the REST shadow update handler,
and is the MQTT publish to shadow/update really denied?

Each REST case sends sens_on with a different request shape, then watches
update/accepted and asks shadow/get whether the device produced a fresh reading
(metadata.reported.crockTofDistance.timestamp moved forward).

  case A: nested payload, parse=False, escape=False  (PR #5 as written)
  case B: nested payload, parse=True,  escape=True   (reset_pump_status shape)
  case C: flat body,      parse=False, escape=False  (main's update_shadow)
  case D: direct MQTT publish to shadow/update       (main's trigger_sensor_update)

Commands are the same ones the integration sends on every poll. updates_off is
always sent at the end so the device does not keep streaming.

USAGE:
    .venv/bin/python tests/test_rest_shadow_command.py              # list devices
    .venv/bin/python tests/test_rest_shadow_command.py "<nickname>"  # run on one

Requires .env file with MOEN_USERNAME and MOEN_PASSWORD
"""
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import boto3
import requests
from awscrt import auth, io, mqtt
from awsiot import mqtt_connection_builder
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

AUTH_URL = "https://4j1gkf0vji.execute-api.us-east-2.amazonaws.com/prod/v1/oauth2/token"
INVOKER_URL = "https://exo9f857n8.execute-api.us-east-2.amazonaws.com/prod/v1/invoker"
OAUTH_CLIENT_ID = "6qn9pep31dglq6ed4fvlq6rp5t"
USER_AGENT = "Smartwater-iOS-prod-3.39.0"
IOT_ENDPOINT = "a1r2q5ic87novc-ats.iot.us-east-2.amazonaws.com"
IOT_REGION = "us-east-2"
IDENTITY_POOL_ID = "us-east-2:7880fbef-a3a8-4ffc-a0d1-74e686e79c80"
USER_POOL_ID = "us-east-2_9puIPVyv1"
UPDATE_FN = "smartwater-app-shadow-api-prod-update"

WATCH_SECS = 12
SETTLE_SECS = 5
FUTURE_TIMEOUT = 10


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {msg}", flush=True)


def authenticate():
    resp = requests.post(
        AUTH_URL,
        data=json.dumps({
            "client_id": OAUTH_CLIENT_ID,
            "username": os.environ["MOEN_USERNAME"],
            "password": os.environ["MOEN_PASSWORD"],
        }),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json()["token"]
    return token["access_token"], token["id_token"]


def invoke(access_token, fn, body, parse=False, escape=False):
    """Call the invoker and return (http_status, json_or_text)."""
    resp = requests.post(
        INVOKER_URL,
        json={"parse": parse, "body": body, "fn": fn, "escape": escape},
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, resp.text


def newest_timestamp(metadata):
    """Newest timestamp anywhere in a shadow metadata tree (0 if none)."""
    if isinstance(metadata, dict):
        # A reported field can itself be called "timestamp", so check the value type.
        return max(
            (v if k == "timestamp" and isinstance(v, int) else newest_timestamp(v) for k, v in metadata.items()),
            default=0,
        )
    if isinstance(metadata, list):
        return max((newest_timestamp(v) for v in metadata), default=0)
    return 0


def get_nab_devices(access_token):
    _, data = invoke(access_token, "smartwater-app-device-api-prod-list", {"locale": "en_US"})
    devices = data.get("Payload", [])
    if isinstance(devices, str):
        devices = json.loads(devices)
    if isinstance(devices, dict) and "body" in devices:
        devices = devices["body"]
    if isinstance(devices, str):
        devices = json.loads(devices)
    nab = [d for d in devices if isinstance(d, dict) and d.get("deviceType") == "NAB"]
    if not nab:
        raise SystemExit("No NAB devices found")
    return nab


def get_aws_credentials(id_token):
    cognito = boto3.client("cognito-identity", region_name=IOT_REGION)
    provider = f"cognito-idp.{IOT_REGION}.amazonaws.com/{USER_POOL_ID}"
    identity = cognito.get_id(IdentityPoolId=IDENTITY_POOL_ID, Logins={provider: id_token})
    return cognito.get_credentials_for_identity(
        IdentityId=identity["IdentityId"], Logins={provider: id_token}
    )["Credentials"]


class Shadow:
    """MQTT connection that records shadow messages and connection drops."""

    def __init__(self, bootstrap, creds, client_id, label):
        self.client_id = client_id
        self.label = label
        self.commands = []        # desired.crockCommand values seen on update/accepted
        self.reported_count = 0   # update/accepted messages carrying reported data
        self.last_get = None      # most recent get/accepted document
        self.interruptions = []
        self.resumes = []
        self.conn = mqtt_connection_builder.websockets_with_default_aws_signing(
            endpoint=IOT_ENDPOINT,
            client_bootstrap=bootstrap,
            region=IOT_REGION,
            credentials_provider=auth.AwsCredentialsProvider.new_static(
                access_key_id=creds["AccessKeyId"],
                secret_access_key=creds["SecretKey"],
                session_token=creds["SessionToken"],
            ),
            client_id=f"moen-test-{uuid.uuid4()}",
            clean_session=True,
            keep_alive_secs=30,
            on_connection_interrupted=self._on_interrupted,
            on_connection_resumed=self._on_resumed,
        )

    def _on_interrupted(self, connection, error, **kwargs):
        self.interruptions.append(str(error))
        log(f"  [{self.label}] CONNECTION INTERRUPTED: {error}")

    def _on_resumed(self, connection, return_code, session_present, **kwargs):
        self.resumes.append(session_present)
        log(f"  [{self.label}] connection resumed (session_present={session_present})")

    def _on_message(self, topic, payload, **kwargs):
        doc = json.loads(payload)
        if topic.endswith("/get/accepted"):
            self.last_get = doc
            return
        state = doc.get("state", {})
        command = state.get("desired", {}).get("crockCommand")
        reported = state.get("reported")
        if command:
            self.commands.append(command)
        if reported:
            self.reported_count += 1
        log(
            f"  [{self.label}] update/accepted desired={state.get('desired')} "
            f"reported_fields={sorted(reported) if reported else []} "
            f"tof={reported.get('crockTofDistance') if reported else None}"
        )

    def connect(self):
        self.conn.connect().result(FUTURE_TIMEOUT)
        for suffix in ("get/accepted", "update/accepted"):
            future, _ = self.conn.subscribe(
                topic=f"$aws/things/{self.client_id}/shadow/{suffix}",
                qos=mqtt.QoS.AT_LEAST_ONCE,
                callback=self._on_message,
            )
            future.result(FUTURE_TIMEOUT)
        log(f"  [{self.label}] connected and subscribed")

    def reset(self):
        self.commands.clear()
        self.reported_count = 0

    def snapshot(self, wait=4):
        """Ask shadow/get. Returns (desired_command, tof, tof_ts, newest_reported_ts) or None."""
        self.last_get = None
        future, _ = self.conn.publish(
            topic=f"$aws/things/{self.client_id}/shadow/get",
            payload="",
            qos=mqtt.QoS.AT_LEAST_ONCE,
        )
        future.result(FUTURE_TIMEOUT)
        deadline = time.time() + wait
        while self.last_get is None and time.time() < deadline:
            time.sleep(0.1)
        if self.last_get is None:
            return None
        doc = self.last_get
        return (
            doc.get("state", {}).get("desired", {}).get("crockCommand"),
            doc.get("state", {}).get("reported", {}).get("crockTofDistance"),
            doc.get("metadata", {}).get("reported", {}).get("crockTofDistance", {}).get("timestamp"),
            newest_timestamp(doc.get("metadata", {}).get("reported", {})),
        )

    def disconnect(self):
        try:
            self.conn.disconnect().result(FUTURE_TIMEOUT)
        except Exception as err:
            log(f"  [{self.label}] disconnect error: {err}")


def updates_off(access_token, client_id):
    """Stop streaming, using the shape disable_droplet_updates sends in production."""
    status, _ = invoke(
        access_token, UPDATE_FN,
        {"clientId": str(client_id), "payload": {"crockCommand": "updates_off"}},
        parse=True, escape=True,
    )
    return status


def run_rest_case(name, description, shadow, access_token, client_id, body, parse, escape, results):
    print(f"\n--- Case {name}: {description}")
    updates_off(access_token, client_id)
    time.sleep(SETTLE_SECS)

    before = shadow.snapshot()
    log(f"  before: {before}")
    shadow.reset()
    sent_at = int(time.time())

    log(f"  POST body={json.dumps(body)} parse={parse} escape={escape}")
    status, response = invoke(access_token, UPDATE_FN, body, parse=parse, escape=escape)
    log(f"  response: HTTP {status} {json.dumps(response)[:300]}")

    time.sleep(WATCH_SECS)
    after = shadow.snapshot()
    log(f"  after:  {after}")
    if shadow.last_get:
        reported = shadow.last_get.get("state", {}).get("reported", {})
        log(f"  get/accepted: {len(reported)} reported fields, connected={reported.get('connected')}, "
            f"droplet={json.dumps(reported.get('droplet'))}")

    fresh = bool(after and after[2] and after[2] >= sent_at)
    results[name] = {
        "description": description,
        "http": status,
        "sens_on_on_update_accepted": "sens_on" in shadow.commands,
        "all_commands_seen": list(shadow.commands),
        "reported_messages": shadow.reported_count,
        "desired_after": after[0] if after else None,
        "tof_before": before[1] if before else None,
        "tof_after": after[1] if after else None,
        "fresh_reading": fresh,
        "any_reported_field_fresh": bool(after and after[3] >= sent_at),
    }


def run_mqtt_case(shadow, results):
    print("\n--- Case D: direct MQTT publish to shadow/update")
    outcome = "accepted"
    future, _ = shadow.conn.publish(
        topic=f"$aws/things/{shadow.client_id}/shadow/update",
        payload=json.dumps({"state": {"desired": {"crockCommand": "sens_on"}}}),
        qos=mqtt.QoS.AT_LEAST_ONCE,
    )
    started = time.time()
    try:
        future.result(FUTURE_TIMEOUT)
        log(f"  publish acknowledged after {time.time() - started:.3f}s")
    except Exception as err:
        outcome = f"{type(err).__name__}: {err}"
        log(f"  publish failed after {time.time() - started:.3f}s: {outcome}")

    # Give auto-reconnect time to finish, then see if subscriptions survived.
    time.sleep(8)
    try:
        after = shadow.snapshot()
    except Exception as err:
        after = None
        log(f"  shadow/get publish failed: {err}")
    log(f"  shadow/get after publish: {after}")

    results["D"] = {
        "description": "MQTT publish to shadow/update",
        "publish": outcome,
        "interruptions": shadow.interruptions,
        "resumes_session_present": shadow.resumes,
        "shadow_get_answered_afterwards": after is not None,
    }


def main():
    log("Authenticating")
    access_token, id_token = authenticate()
    devices = get_nab_devices(access_token)
    for d in devices:
        log(f"Found: {d.get('nickname')} (clientId {d.get('clientId')}) connected={d.get('connected')} "
            f"tof={d.get('crockTofDistance')}")
    if len(sys.argv) < 2:
        log("Pass a device nickname to run the test.")
        return
    matches = [d for d in devices if d.get("nickname") == sys.argv[1]]
    if not matches:
        raise SystemExit(f"No device named {sys.argv[1]!r}")
    device = matches[0]
    client_id = device["clientId"]
    log(f"Device under test: {device.get('nickname')} (clientId {client_id})")

    creds = get_aws_credentials(id_token)
    elg = io.EventLoopGroup(1)
    bootstrap = io.ClientBootstrap(elg, io.DefaultHostResolver(elg))

    results = {}
    shadow = Shadow(bootstrap, creds, client_id, "rest")
    denial = Shadow(bootstrap, creds, client_id, "mqtt")
    try:
        shadow.connect()
        nested = {"clientId": str(client_id), "payload": {"crockCommand": "sens_on"}}
        flat = {"clientId": client_id, "crockCommand": "sens_on"}

        run_rest_case("A", "nested, parse=False, escape=False (PR 5)",
                      shadow, access_token, client_id, nested, False, False, results)
        run_rest_case("B", "nested, parse=True, escape=True (reset_pump_status)",
                      shadow, access_token, client_id, nested, True, True, results)
        run_rest_case("C", "flat, parse=False, escape=False (main)",
                      shadow, access_token, client_id, flat, False, False, results)

        results["rest_connection_interruptions"] = shadow.interruptions

        updates_off(access_token, client_id)
        time.sleep(SETTLE_SECS)

        # Separate connection, so a drop here cannot affect the cases above.
        denial.connect()
        run_mqtt_case(denial, results)
    finally:
        print()
        log(f"Cleanup: updates_off -> HTTP {updates_off(access_token, client_id)}")
        denial.disconnect()
        shadow.disconnect()

    print("\n=== RESULTS ===")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
