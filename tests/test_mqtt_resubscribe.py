#!/usr/bin/env python3
"""
Live test: after AWS IoT drops the MQTT connection, does calling
resubscribe_existing_topics() from on_connection_resumed bring shadow/get
answers back?

With clean_session=True the broker forgets subscriptions when the connection
drops. The CRT client reconnects on its own (session_present=False), but
without a resubscribe, shadow/get responses never arrive.

The drop is caused the same way it happens in production: a publish to
shadow/update, which the app credentials are not allowed to make. The payload
is updates_off, so nothing changes on the device even if it were accepted.

USAGE:
    .venv/bin/python tests/test_mqtt_resubscribe.py "<nickname>"

Requires .env file with MOEN_USERNAME and MOEN_PASSWORD
"""
import json
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from awscrt import auth, io, mqtt  # noqa: E402
from awsiot import mqtt_connection_builder  # noqa: E402

from test_rest_shadow_command import (  # noqa: E402
    FUTURE_TIMEOUT, IOT_ENDPOINT, IOT_REGION, authenticate, get_aws_credentials,
    get_nab_devices, log,
)


def run(bootstrap, creds, client_id, resubscribe):
    label = "resubscribe" if resubscribe else "control"
    print(f"\n--- {label}: resubscribe_existing_topics on resume = {resubscribe}")
    got_get = threading.Event()
    resumed = threading.Event()
    state = {}

    def on_message(topic, payload, **kwargs):
        got_get.set()

    def on_interrupted(connection, error, **kwargs):
        log(f"  [{label}] interrupted: {error}")

    def on_resumed(connection, return_code, session_present, **kwargs):
        log(f"  [{label}] resumed: session_present={session_present}")
        state["session_present"] = session_present
        if resubscribe and not session_present:
            future, _ = connection.resubscribe_existing_topics()

            def done(f):
                try:
                    log(f"  [{label}] resubscribed: {f.result()}")
                except Exception as err:
                    log(f"  [{label}] resubscribe failed: {err}")
                resumed.set()

            future.add_done_callback(done)
        else:
            resumed.set()

    conn = mqtt_connection_builder.websockets_with_default_aws_signing(
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
        on_connection_interrupted=on_interrupted,
        on_connection_resumed=on_resumed,
    )
    conn.connect().result(FUTURE_TIMEOUT)
    conn.subscribe(
        topic=f"$aws/things/{client_id}/shadow/get/accepted",
        qos=mqtt.QoS.AT_LEAST_ONCE,
        callback=on_message,
    )[0].result(FUTURE_TIMEOUT)

    def ask():
        got_get.clear()
        conn.publish(topic=f"$aws/things/{client_id}/shadow/get", payload="",
                     qos=mqtt.QoS.AT_LEAST_ONCE)[0].result(FUTURE_TIMEOUT)
        return got_get.wait(5)

    baseline = ask()
    log(f"  [{label}] shadow/get answered before drop: {baseline}")

    future, _ = conn.publish(
        topic=f"$aws/things/{client_id}/shadow/update",
        payload=json.dumps({"state": {"desired": {"crockCommand": "updates_off"}}}),
        qos=mqtt.QoS.AT_LEAST_ONCE,
    )
    try:
        future.result(FUTURE_TIMEOUT)
        log(f"  [{label}] shadow/update publish was ACCEPTED (no drop to test)")
    except Exception as err:
        log(f"  [{label}] shadow/update publish failed: {err}")

    resumed.wait(20)
    time.sleep(1)
    after = ask()
    log(f"  [{label}] shadow/get answered after drop: {after}")
    try:
        conn.disconnect().result(FUTURE_TIMEOUT)
    except Exception as err:
        log(f"  [{label}] disconnect error: {err}")
    return {"before": baseline, "session_present": state.get("session_present"), "after": after}


def main():
    if len(sys.argv) < 2:
        raise SystemExit('usage: test_mqtt_resubscribe.py "<nickname>"')
    access_token, id_token = authenticate()
    device = next((d for d in get_nab_devices(access_token) if d.get("nickname") == sys.argv[1]), None)
    if not device:
        raise SystemExit(f"No device named {sys.argv[1]!r}")
    log(f"Device: {device['nickname']} (clientId {device['clientId']})")

    creds = get_aws_credentials(id_token)
    elg = io.EventLoopGroup(1)
    bootstrap = io.ClientBootstrap(elg, io.DefaultHostResolver(elg))

    results = {
        "control": run(bootstrap, creds, device["clientId"], resubscribe=False),
        "resubscribe": run(bootstrap, creds, device["clientId"], resubscribe=True),
    }
    print("\n=== RESULTS ===")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
