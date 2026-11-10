#!/usr/bin/env python3
"""
Live check of the 2.4.16b1 integration code (api.py) against a real device.

Runs the coordinator's telemetry sequence with the integration's own client
classes, then forces an MQTT drop and checks that the client recovers:

  1. Two polls: REST sens_on -> 2s -> MQTT shadow/get -> 1s -> REST updates_off,
     then read last_shadow_data the way the coordinator does.
  2. Force a drop with a denied shadow/update publish (trigger_sensor_update),
     wait for the auto-reconnect, and confirm the client resubscribed and is
     marked connected again.
  3. One more poll after the drop.
  4. reconnect_with_new_token(): the old connection is closed and a new one works.

USAGE:
    .venv/bin/python tests/test_beta_poll.py "<nickname>"

Requires .env file with MOEN_USERNAME and MOEN_PASSWORD
"""
import asyncio
import importlib.util
import logging
import os
import sys
import time
from pathlib import Path

import aiohttp
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

# Load api.py directly: the package __init__ imports Home Assistant.
spec = importlib.util.spec_from_file_location(
    "moen_api", ROOT / "custom_components" / "moen_sump_pump" / "api.py"
)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("botocore").setLevel(logging.WARNING)
log = logging.getLogger("test").info

WATCHED = ["crockTofDistance", "droplet", "connected", "wifiRssi", "batteryPercentage", "powerSource", "alerts"]


async def poll(client, mqtt_client, client_id, label):
    sens_ok = await client.update_shadow(client_id, "sens_on")
    await asyncio.sleep(2)
    get_ok = await mqtt_client.request_shadow()
    await asyncio.sleep(1)
    off_ok = await client.update_shadow(client_id, "updates_off")
    reported = mqtt_client.last_shadow_data or {}
    present = [k for k in WATCHED if k in reported]
    log(f"[{label}] sens_on={sens_ok} shadow/get={get_ok} updates_off={off_ok} "
        f"fields={len(reported)} watched_present={len(present)}/{len(WATCHED)} "
        f"tof={reported.get('crockTofDistance')} floodRisk={(reported.get('droplet') or {}).get('floodRisk')}")
    return {"sens_on": sens_ok, "updates_off": off_ok, "fields": len(reported),
            "watched_present": len(present) == len(WATCHED)}


async def main():
    if len(sys.argv) < 2:
        raise SystemExit('usage: test_beta_poll.py "<nickname>"')
    async with aiohttp.ClientSession() as session:
        client = api.MoenFloNABClient(os.environ["MOEN_USERNAME"], os.environ["MOEN_PASSWORD"], session)
        await client.authenticate()
        device = next((d for d in await client.get_devices() if d.get("nickname") == sys.argv[1]), None)
        if not device:
            raise SystemExit(f"No device named {sys.argv[1]!r}")
        client_id = device["clientId"]
        log(f"Device: {device['nickname']} (clientId {client_id})")

        mqtt_client = client.create_mqtt_client(client_id)
        results = {}
        try:
            assert await mqtt_client.connect(), "initial connect failed"
            results["poll_1"] = await poll(client, mqtt_client, client_id, "poll 1")
            await asyncio.sleep(3)
            results["poll_2"] = await poll(client, mqtt_client, client_id, "poll 2")

            log("Forcing a drop with a denied shadow/update publish")
            await mqtt_client.trigger_sensor_update("updates_off")
            dropped_flag = mqtt_client.is_connected
            deadline = time.time() + 25
            while not mqtt_client.is_connected and time.time() < deadline:
                await asyncio.sleep(0.5)
            results["drop"] = {"connected_right_after_drop": dropped_flag,
                               "recovered_on_its_own": mqtt_client.is_connected}
            log(f"[drop] connected right after={dropped_flag} recovered={mqtt_client.is_connected}")

            mqtt_client._last_shadow_data = None  # make sure poll 3 needs a fresh shadow/get
            results["poll_3_after_drop"] = await poll(client, mqtt_client, client_id, "poll 3")

            old_conn = mqtt_client.mqtt_connection
            await client.authenticate()
            reconnected = await mqtt_client.reconnect_with_new_token(client._id_token)
            results["reconnect"] = {"ok": reconnected, "new_connection_object": mqtt_client.mqtt_connection is not old_conn}
            mqtt_client._last_shadow_data = None
            results["poll_4_after_reconnect"] = await poll(client, mqtt_client, client_id, "poll 4")
        finally:
            await mqtt_client.disconnect()
            log(f"Cleanup: updates_off accepted={await client.update_shadow(client_id, 'updates_off')}")

    print("\n=== RESULTS ===")
    for k, v in results.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
