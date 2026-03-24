#!/usr/bin/env python3
"""
Request and dump the full MQTT shadow state for all NAB devices.
Requests shadow/get for each device, prints complete JSON, then exits.
"""
import asyncio
import json
import os
import uuid
from pathlib import Path
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
except ImportError:
    pass

import aiohttp
import boto3
from awsiot import mqtt_connection_builder
from awscrt import mqtt, io, auth

# API Constants (from monitor_mqtt.py)
AUTH_URL = "https://4j1gkf0vji.execute-api.us-east-2.amazonaws.com/prod/v1/oauth2/token"
INVOKER_URL = "https://exo9f857n8.execute-api.us-east-2.amazonaws.com/prod/v1/invoker"
CLIENT_ID_OAUTH = "6qn9pep31dglq6ed4fvlq6rp5t"
USER_AGENT = "Smartwater-iOS-prod-3.39.0"

# AWS Constants (from monitor_mqtt.py)
IOT_ENDPOINT = "a1r2q5ic87novc-ats.iot.us-east-2.amazonaws.com"
IOT_REGION = "us-east-2"
IDENTITY_POOL_ID = "us-east-2:7880fbef-a3a8-4ffc-a0d1-74e686e79c80"
USER_POOL_ID = "us-east-2_9puIPVyv1"


async def authenticate(session):
    auth_data = {"client_id": CLIENT_ID_OAUTH, "username": os.getenv('MOEN_USERNAME'), "password": os.getenv('MOEN_PASSWORD')}
    async with session.post(AUTH_URL, data=json.dumps(auth_data), headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"}) as r:
        data = await r.json()
        return data["token"]["access_token"], data["token"]["id_token"]


async def get_nab_devices(session, access_token):
    payload = {"parse": False, "body": {"locale": "en_US"}, "fn": "smartwater-app-device-api-prod-list", "escape": False}
    async with session.post(INVOKER_URL, json=payload, headers={"Authorization": f"Bearer {access_token}", "User-Agent": USER_AGENT, "Content-Type": "application/json"}) as r:
        data = await r.json()
        devices = data.get("Payload", [])
        if isinstance(devices, str):
            devices = json.loads(devices)
        if isinstance(devices, dict) and "body" in devices:
            devices = devices["body"]
        if isinstance(devices, str):
            devices = json.loads(devices)
        return [d for d in devices if isinstance(d, dict) and d.get("deviceType") == "NAB"]


def get_aws_credentials(id_token):
    cognito = boto3.client('cognito-identity', region_name=IOT_REGION)
    provider = f"cognito-idp.{IOT_REGION}.amazonaws.com/{USER_POOL_ID}"
    identity = cognito.get_id(IdentityPoolId=IDENTITY_POOL_ID, Logins={provider: id_token})
    creds = cognito.get_credentials_for_identity(IdentityId=identity['IdentityId'], Logins={provider: id_token})['Credentials']
    return {'access_key': creds['AccessKeyId'], 'secret_key': creds['SecretKey'], 'session_token': creds['SessionToken']}


async def main():
    async with aiohttp.ClientSession() as session:
        print("Authenticating...")
        access_token, id_token = await authenticate(session)
        print("Getting devices...")
        devices = await get_nab_devices(session, access_token)
        print(f"Found {len(devices)} NAB device(s)\n")

    print("Getting AWS credentials...")
    aws_creds = get_aws_credentials(id_token)

    elg = io.EventLoopGroup(1)
    hr = io.DefaultHostResolver(elg)
    bootstrap = io.ClientBootstrap(elg, hr)

    for device in devices:
        client_id = device['clientId']
        name = device.get('nickname', 'Unknown')
        print(f"\n{'='*70}")
        print(f"Device: {name}  (clientId: {client_id})")
        print(f"{'='*70}")

        received = asyncio.Event()
        shadow_data = {}

        mqtt_conn = mqtt_connection_builder.websockets_with_default_aws_signing(
            endpoint=IOT_ENDPOINT,
            client_bootstrap=bootstrap,
            region=IOT_REGION,
            credentials_provider=auth.AwsCredentialsProvider.new_static(
                access_key_id=aws_creds['access_key'],
                secret_access_key=aws_creds['secret_key'],
                session_token=aws_creds['session_token']
            ),
            client_id=f"moen-dump-{uuid.uuid4()}",
            clean_session=True,
            keep_alive_secs=30
        )

        mqtt_conn.connect().result()
        print("Connected to MQTT")

        def on_message(topic, payload, **kwargs):
            if "shadow/get/accepted" in topic:
                shadow_data['full'] = json.loads(payload)
                received.set()

        mqtt_conn.subscribe(
            topic=f"$aws/things/{client_id}/shadow/get/accepted",
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_message
        )[0].result()

        # Request full shadow
        mqtt_conn.publish(
            topic=f"$aws/things/{client_id}/shadow/get",
            payload="{}",
            qos=mqtt.QoS.AT_LEAST_ONCE
        )[0].result()

        # Wait up to 10 seconds for response
        try:
            await asyncio.wait_for(received.wait(), timeout=10.0)
            print("\nFull shadow state (state.reported):")
            reported = shadow_data['full'].get('state', {}).get('reported', {})
            print(json.dumps(reported, indent=2))
        except asyncio.TimeoutError:
            print("Timed out waiting for shadow response")

        mqtt_conn.disconnect().result()


if __name__ == "__main__":
    asyncio.run(main())
