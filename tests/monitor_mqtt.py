#!/usr/bin/env python3
"""
Monitor MQTT shadow updates in real-time.
Run this and keep it open while you test.
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

# API Constants
AUTH_URL = "https://4j1gkf0vji.execute-api.us-east-2.amazonaws.com/prod/v1/oauth2/token"
INVOKER_URL = "https://exo9f857n8.execute-api.us-east-2.amazonaws.com/prod/v1/invoker"
CLIENT_ID = "6qn9pep31dglq6ed4fvlq6rp5t"
USER_AGENT = "Smartwater-iOS-prod-3.39.0"

# AWS Constants
IOT_ENDPOINT = "a1r2q5ic87novc-ats.iot.us-east-2.amazonaws.com"
IOT_REGION = "us-east-2"
IDENTITY_POOL_ID = "us-east-2:7880fbef-a3a8-4ffc-a0d1-74e686e79c80"
USER_POOL_ID = "us-east-2_9puIPVyv1"


async def authenticate(session, username, password):
    """Authenticate."""
    auth_data = {
        "client_id": CLIENT_ID,
        "username": username,
        "password": password
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    async with session.post(AUTH_URL, data=json.dumps(auth_data), headers=headers) as response:
        data = await response.json()
        return data["token"]["access_token"], data["token"]["id_token"]


async def invoke_lambda(session, access_token, function_name, payload):
    """Invoke Lambda."""
    request_payload = {
        "parse": False,
        "body": payload,
        "fn": function_name,
        "escape": False
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    async with session.post(INVOKER_URL, json=request_payload, headers=headers) as response:
        data = await response.json()
        if data.get("StatusCode") == 200:
            payload_val = data.get("Payload")
            if isinstance(payload_val, str):
                try:
                    payload_val = json.loads(payload_val)
                except:
                    pass
            if isinstance(payload_val, dict) and "body" in payload_val:
                body = payload_val["body"]
                if isinstance(body, str):
                    try:
                        return json.loads(body)
                    except:
                        return body
                return body
            return payload_val
        return data


async def get_devices(session, access_token):
    """Get devices."""
    response = await invoke_lambda(session, access_token, "smartwater-app-device-api-prod-list", {"locale": "en_US"})
    if isinstance(response, list):
        return response
    return []


def get_aws_credentials(id_token):
    """Get AWS credentials from Cognito using ID token."""
    cognito_identity = boto3.client('cognito-identity', region_name=IOT_REGION)

    provider_name = f"cognito-idp.{IOT_REGION}.amazonaws.com/{USER_POOL_ID}"
    identity_response = cognito_identity.get_id(
        IdentityPoolId=IDENTITY_POOL_ID,
        Logins={provider_name: id_token}
    )

    credentials_response = cognito_identity.get_credentials_for_identity(
        IdentityId=identity_response['IdentityId'],
        Logins={provider_name: id_token}
    )

    credentials = credentials_response['Credentials']
    return {
        'access_key': credentials['AccessKeyId'],
        'secret_key': credentials['SecretKey'],
        'session_token': credentials['SessionToken']
    }


async def main():
    username = os.getenv('MOEN_USERNAME')
    password = os.getenv('MOEN_PASSWORD')

    if not username or not password:
        print("ERROR: Set MOEN_USERNAME and MOEN_PASSWORD")
        return

    print("=" * 80)
    print("MQTT Shadow Monitor - Press Ctrl+C to exit")
    print("=" * 80)

    async with aiohttp.ClientSession() as session:
        # Auth
        print("\nAuthenticating...")
        access_token, id_token = await authenticate(session, username, password)
        print("✓ Authenticated")

        # Get device
        print("\nGetting device...")
        devices = await get_devices(session, access_token)
        device = devices[0]
        client_id = device.get('clientId')
        device_name = device.get('nickname', 'Unknown')
        print(f"✓ Device: {device_name} (ID: {client_id})")

        # Get AWS credentials
        print("\nGetting AWS credentials...")
        aws_creds = get_aws_credentials(id_token)
        print("✓ Got credentials")

        # Connect to AWS IoT
        print("\nConnecting to AWS IoT MQTT...")
        event_loop_group = io.EventLoopGroup(1)
        host_resolver = io.DefaultHostResolver(event_loop_group)
        client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

        mqtt_connection = mqtt_connection_builder.websockets_with_default_aws_signing(
            endpoint=IOT_ENDPOINT,
            client_bootstrap=client_bootstrap,
            region=IOT_REGION,
            credentials_provider=auth.AwsCredentialsProvider.new_static(
                access_key_id=aws_creds['access_key'],
                secret_access_key=aws_creds['secret_key'],
                session_token=aws_creds['session_token']
            ),
            client_id=f"moen-monitor-{uuid.uuid4()}",
            clean_session=True,
            keep_alive_secs=30
        )

        connect_future = mqtt_connection.connect()
        connect_future.result()
        print("✓ Connected to MQTT!")

        # Subscribe to all shadow topics
        shadow_topic = f"$aws/things/{client_id}/shadow/#"

        def on_message(topic, payload, dup, qos, retain, **kwargs):
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"\n[{timestamp}] Message on: {topic}")
            try:
                data = json.loads(payload)
                if "state" in data:
                    reported = data.get("state", {}).get("reported", {})
                    tof = reported.get("crockTofDistance")
                    if tof:
                        print(f"  Water Level: {tof} mm")
                    droplet = reported.get("droplet", {})
                    if droplet:
                        print(f"  Flood Risk: {droplet.get('floodRisk')}")
                        print(f"  Trend: {droplet.get('trend')}")
                print(f"  Raw: {json.dumps(data, indent=2)[:500]}...")
            except Exception as e:
                print(f"  Error: {e}")
                print(f"  Raw payload: {payload[:200]}")

        print(f"\nSubscribing to: {shadow_topic}")
        subscribe_future, _ = mqtt_connection.subscribe(
            topic=shadow_topic,
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_message
        )
        subscribe_future.result()
        print("✓ Subscribed!")

        print("\n" + "=" * 80)
        print("Monitoring shadow updates... (Press Ctrl+C to exit)")
        print("=" * 80)
        print("\nTip: Publish sens_on command to trigger fresh reading:")
        print(f"  Topic: $aws/things/{client_id}/shadow/update")
        print('  Payload: {"state": {"desired": {"crockCommand": "sens_on"}}}')
        print()

        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n\nDisconnecting...")
            disconnect_future = mqtt_connection.disconnect()
            disconnect_future.result()
            print("✓ Disconnected")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
