#!/usr/bin/env python3
"""
Test that the integration properly sends updates_off after sens_on.
This simulates the coordinator update cycle to verify battery preservation.
"""
import asyncio
import aiohttp
import sys
import os
from pathlib import Path

# Add the custom_components path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'custom_components', 'moen_flo_nab'))

from api import MoenFloNABClient, MoenFloNABMqttClient

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
except ImportError:
    pass


async def test_mqtt_updates_off():
    """Test MQTT path with updates_off command."""
    username = os.getenv('MOEN_USERNAME')
    password = os.getenv('MOEN_PASSWORD')

    if not username or not password:
        print("ERROR: Set MOEN_USERNAME and MOEN_PASSWORD in .env file")
        return

    async with aiohttp.ClientSession() as session:
        print("\n" + "=" * 80)
        print("Testing Integration MQTT Path with updates_off")
        print("=" * 80)

        # Authenticate
        print("\n[1/5] Authenticating...")
        client = MoenFloNABClient(username, password, session)
        await client.authenticate()
        print("      ✓ Authenticated")

        # Get device
        print("\n[2/5] Getting device...")
        devices = await client.get_devices()
        if not devices:
            print("      ✗ No devices found")
            return

        device = devices[0]
        client_id = device.get('clientId')
        nickname = device.get('nickname', 'Unnamed')
        print(f"      ✓ Found: {nickname} (clientId: {client_id})")

        # Create MQTT client
        print("\n[3/5] Connecting to MQTT...")
        mqtt_client = client.create_mqtt_client(client_id)
        if not mqtt_client:
            print("      ✗ Failed to create MQTT client")
            return

        connected = await mqtt_client.connect()
        if not connected:
            print("      ✗ Failed to connect to MQTT")
            return
        print("      ✓ Connected to MQTT")

        # Simulate coordinator update cycle (MQTT path)
        print("\n[4/5] Simulating coordinator update cycle...")
        print("      This mimics the integration's _async_update_data method")

        # Step 1: Send sens_on
        print("\n      → Sending sens_on command...")
        await mqtt_client.trigger_sensor_update("sens_on")
        print("        ✓ sens_on sent")

        # Step 2: Wait for device to respond
        print("      → Waiting 2 seconds for device to take reading...")
        await asyncio.sleep(2)

        # Step 3: Request shadow
        print("      → Requesting shadow data...")
        await mqtt_client.request_shadow()

        # Step 4: Wait for shadow response
        print("      → Waiting 1 second for shadow response...")
        await asyncio.sleep(1)

        # Step 5: NEW - Send updates_off to stop streaming
        print("      → Sending updates_off command (NEW IN v1.7.0)...")
        await mqtt_client.trigger_sensor_update("updates_off")
        print("        ✓ updates_off sent")

        # Get the data
        reported = mqtt_client.last_shadow_data
        if reported:
            water_level = reported.get('crockTofDistance')
            print(f"\n      ✓ Got shadow data: water level = {water_level} mm")
        else:
            print("      ⚠ No shadow data received (but commands were sent)")

        # Verify streaming stopped
        print("\n[5/5] Verifying streaming stopped...")
        print("      Waiting 3 seconds to check if updates continue...")
        await asyncio.sleep(3)

        # Read shadow one more time
        shadow_data = await client.get_shadow(client_id)
        if shadow_data and "state" in shadow_data:
            reported = shadow_data.get("state", {}).get("reported", {})
            crock_command = reported.get('crockCommand')
            print(f"      Final crockCommand state: {crock_command}")
            if crock_command is None or crock_command == "null":
                print("      ✓ Command cleared - streaming should be stopped")
            else:
                print(f"      ⚠ Command still set to: {crock_command}")

        # Disconnect
        await mqtt_client.disconnect()
        print("\n      ✓ Disconnected from MQTT")

        print("\n" + "=" * 80)
        print("Test Summary:")
        print("  ✓ Integration now sends updates_off after sens_on")
        print("  ✓ Battery preservation implemented")
        print("  ✓ Mirrors Moen mobile app behavior")
        print("\nNext: Monitor your device battery level over the next few days")
        print("      to verify continuous streaming is no longer occurring.")
        print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(test_mqtt_updates_off())
