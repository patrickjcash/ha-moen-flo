#!/usr/bin/env python3
"""
Investigate firmware update info available from the Moen API.

Checks:
1. Device list API - firmwareVersion and any update flags
2. Shadow state (reported) - fwVersion and any OTA fields
3. Known OTA/update Lambda endpoints

USAGE:
    python tests/test_firmware_update_info.py

Requires .env file with MOEN_USERNAME and MOEN_PASSWORD
"""
import asyncio
import json
import os
import uuid
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
except ImportError:
    pass

import aiohttp
import boto3

AUTH_URL = "https://4j1gkf0vji.execute-api.us-east-2.amazonaws.com/prod/v1/oauth2/token"
INVOKER_URL = "https://exo9f857n8.execute-api.us-east-2.amazonaws.com/prod/v1/invoker"
# APK ConstantsKt.MOEN_BASE_URL = "https://api.prod.iot.moen.com/v1/"
# LambdaNabLyhApiService uses @POST("invoker") with this base URL
MOEN_BASE_INVOKER_URL = "https://api.prod.iot.moen.com/v1/invoker"
CLIENT_ID_OAUTH = "6qn9pep31dglq6ed4fvlq6rp5t"
USER_AGENT = "Smartwater-iOS-prod-3.39.0"

IOT_REGION = "us-east-2"
IDENTITY_POOL_ID = "us-east-2:7880fbef-a3a8-4ffc-a0d1-74e686e79c80"
USER_POOL_ID = "us-east-2_9puIPVyv1"


async def authenticate(session):
    auth_data = {
        "client_id": CLIENT_ID_OAUTH,
        "username": os.getenv('MOEN_USERNAME'),
        "password": os.getenv('MOEN_PASSWORD'),
    }
    async with session.post(
        AUTH_URL,
        data=json.dumps(auth_data),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
    ) as r:
        data = await r.json()
        return data["token"]["access_token"], data["token"]["id_token"]


async def invoke(session, access_token, fn, body):
    payload = {"parse": False, "body": body, "fn": fn, "escape": False}
    async with session.post(
        INVOKER_URL,
        json=payload,
        headers={"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT, "Content-Type": "application/json"},
    ) as r:
        data = await r.json()
        raw = data.get("Payload", data)
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                pass
        return raw


async def get_shadow(session, access_token, client_id):
    return await invoke(session, access_token, "smartwater-app-shadow-api-prod-get", {"clientId": client_id})


def get_aws_credentials(id_token):
    cognito_idp = boto3.client("cognito-idp", region_name=IOT_REGION)
    cognito_identity = boto3.client("cognito-identity", region_name=IOT_REGION)

    logins = {f"cognito-idp.{IOT_REGION}.amazonaws.com/{USER_POOL_ID}": id_token}
    identity_response = cognito_identity.get_id(IdentityPoolId=IDENTITY_POOL_ID, Logins=logins)
    identity_id = identity_response["IdentityId"]
    creds_response = cognito_identity.get_credentials_for_identity(IdentityId=identity_id, Logins=logins)
    return creds_response["Credentials"], identity_id


async def main():
    async with aiohttp.ClientSession() as session:
        print("Authenticating...")
        access_token, id_token = await authenticate(session)
        print("OK\n")

        print("Fetching device list...")
        devices_raw = await invoke(session, access_token, "smartwater-app-device-api-prod-list", {"locale": "en_US"})
        # Unwrap nested payload (may be list, dict with "body", or double-encoded JSON)
        if isinstance(devices_raw, dict) and "body" in devices_raw:
            devices_raw = devices_raw["body"]
        if isinstance(devices_raw, str):
            try:
                devices_raw = json.loads(devices_raw)
            except Exception:
                pass
        nab_devices = [d for d in (devices_raw if isinstance(devices_raw, list) else []) if isinstance(d, dict) and d.get("deviceType") == "NAB"]
        print(f"Found {len(nab_devices)} NAB device(s)\n")

        for device in nab_devices:
            nickname = device.get("nickname", device.get("duid", "unknown"))
            client_id = device.get("clientId")
            duid = device.get("duid")
            print(f"{'='*60}")
            print(f"Device: {nickname}  (clientId={client_id})")
            print(f"{'='*60}")

            # 0. All available device identifiers
            mac = device.get("macAddress") or device.get("mac") or device.get("deviceMac")
            serial = device.get("serialNumber") or device.get("serial")
            federated_id = device.get("federatedIdentity")
            upgrade_uri = device.get("upgradeUri")
            print(f"\n[0] Device identifiers: duid={duid} clientId={client_id} mac={mac} serial={serial}")
            print(f"  federatedIdentity={federated_id}")
            print(f"  upgradeUri={upgrade_uri}  <-- firmware upgrade URI (None = up to date?)")
            print(f"  All keys: {list(device.keys())}")

            # 1. Firmware fields from device list
            print("\n[1] Device list firmware fields:")
            fw_fields = {k: v for k, v in device.items() if any(
                kw in k.lower() for kw in ["firmware", "fw", "version", "update", "ota", "software", "sw"]
            )}
            if fw_fields:
                for k, v in fw_fields.items():
                    print(f"  {k}: {v}")
            else:
                print("  (none found)")

            # 2. Shadow reported state firmware fields
            print("\n[2] Shadow reported firmware fields:")
            shadow = await get_shadow(session, access_token, client_id)
            reported = {}
            if isinstance(shadow, dict):
                reported = shadow.get("state", {}).get("reported", {})
            fw_shadow = {k: v for k, v in reported.items() if any(
                kw in k.lower() for kw in ["firmware", "fw", "version", "update", "ota", "software", "sw"]
            )}
            if fw_shadow:
                for k, v in fw_shadow.items():
                    print(f"  {k}: {v}")
            else:
                print("  (none found)")
            print(f"  [All shadow keys: {list(reported.keys())}]")

            # 3. Check latest firmware endpoint (discovered via APK analysis)
            # APK source (NabLyhRepository.java line 46) uses: escape=true, parse=true, body={"duid": duid}
            # LambdaRequest constructor order: (fn, escape, parse, clientContext, body)
            # escape=true means the body is JSON-stringified before passing to Lambda
            # parse=true means the invoker injects cognitoIdentityId from the JWT
            print("\n[3] fbgpg_device_v1_device_get_latest_firmware_prod (APK: escape=true, parse=true):")
            # APK NabLyhUpdateFirmwareFragment line 442-445: passes clientId (numeric), not UUID duid
            # getLatestFirmware(viewModel.f17242x, ...) where f17242x = getArgs().getClientId()
            fw_body_duid = {"duid": duid}           # UUID — what we've been trying
            fw_body_client = {"duid": str(client_id)}  # numeric clientId — what the app actually passes
            # APK: escape=true, parse=true, body=json.dumps({"duid": clientId})
            combos = [
                (MOEN_BASE_INVOKER_URL, "clientId escape=T parse=T", {"parse": True, "escape": True, "body": json.dumps(fw_body_client), "fn": "fbgpg_device_v1_device_get_latest_firmware_prod"}),
                (MOEN_BASE_INVOKER_URL, "clientId escape=T parse=F", {"parse": False, "escape": True, "body": json.dumps(fw_body_client), "fn": "fbgpg_device_v1_device_get_latest_firmware_prod"}),
                (MOEN_BASE_INVOKER_URL, "clientId escape=F parse=F", {"parse": False, "escape": False, "body": fw_body_client, "fn": "fbgpg_device_v1_device_get_latest_firmware_prod"}),
                (MOEN_BASE_INVOKER_URL, "uuid    escape=T parse=T", {"parse": True, "escape": True, "body": json.dumps(fw_body_duid), "fn": "fbgpg_device_v1_device_get_latest_firmware_prod"}),
            ]
            for url, label, payload in combos:
                async with session.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT, "Content-Type": "application/json"},
                ) as r:
                    text = await r.text()
                    try:
                        data = json.loads(text)
                        raw = data.get("Payload", data) if isinstance(data, dict) else data
                        if isinstance(raw, str):
                            try:
                                raw = json.loads(raw)
                            except Exception:
                                pass
                    except Exception:
                        raw = text
                    result_str = json.dumps(raw) if not isinstance(raw, str) else raw
                    print(f"  [{label}]: {result_str[:200]}")
                    if "upgrade" in result_str or "latest" in result_str:
                        print("  *** FIRMWARE RESPONSE FOUND ***")
                        print(f"  FULL: {result_str}")

            print()


if __name__ == "__main__":
    asyncio.run(main())
