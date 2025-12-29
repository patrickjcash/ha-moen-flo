"""
Moen NAB API - Test Script
Tests all available data endpoints for Home Assistant integration planning.

USAGE:
    python nab_test.py <moen_username> <moen_password>

    Example:
    python nab_test.py user@example.com mypassword

    Output: Creates a JSON file with timestamp containing all API responses

KEY FINDINGS:
- Event IDs (like 267) ARE event types, not sequential numbers
- Event 267 = "Main Pump Stops Normally" - indicates successful pump cycle completion
- Must use numeric clientId for telemetry endpoints (temp/humidity, daily stats)
- Must use UUID (duid) for log endpoints
- CLIENT_ID is from Moen app decompilation and may need updating
"""

import requests
import json
import sys
from datetime import datetime, timezone

# API Configuration
OAUTH_BASE = "https://4j1gkf0vji.execute-api.us-east-2.amazonaws.com/prod/v1"
INVOKER_BASE = "https://exo9f857n8.execute-api.us-east-2.amazonaws.com/prod/v1"

# NOTE: This CLIENT_ID is extracted from the Moen mobile app.
# It's not user-specific but is app-specific and may change with app updates.
# For production use, consider making this configurable.
CLIENT_ID = "6qn9pep31dglq6ed4fvlq6rp5t"

USER_AGENT = "Smartwater-iOS-prod-3.39.0"


class MoenNABTester:
    """Test all available Moen NAB API endpoints"""
    
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.access_token = None
        self.device_uuid = None  # UUID used for logs
        self.client_id_numeric = None  # Numeric ID used for telemetry
        self.cognito_identity_id = None
        
    def authenticate(self):
        """Authenticate with Moen API"""
        print("Authenticating...")
        url = f"{OAUTH_BASE}/oauth2/token"
        headers = {
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        payload = {
            "client_id": CLIENT_ID,
            "username": self.username,
            "password": self.password
        }
        
        try:
            resp = requests.post(url, data=json.dumps(payload), headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            if "token" in data:
                self.access_token = data["token"].get("access_token")
                print("✓ Authentication successful")
                return True
        except Exception as e:
            print(f"✗ Authentication failed: {e}")
        return False
    
    def invoke_lambda(self, function_name, body):
        """Call Lambda function via invoker endpoint"""
        url = f"{INVOKER_BASE}/invoker"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json"
        }
        payload = {
            "parse": False,
            "body": body,
            "fn": function_name,
            "escape": False
        }
        
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
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
        except Exception as e:
            print(f"  Lambda call failed: {e}")
        return None

    def get_device_info(self):
        """Get device information and IDs"""
        print("\n=== Getting Device Info ===")
        result = self.invoke_lambda(
            "smartwater-app-device-api-prod-list",
            {"locale": "en_US"}
        )
        
        devices = result if isinstance(result, list) else result.get("body") if isinstance(result, dict) else None
             
        if devices and isinstance(devices, list):
            for device in devices:
                if device.get('deviceType') == 'NAB':
                    self.device_uuid = device['duid']
                    self.client_id_numeric = device.get('clientId')
                    self.cognito_identity_id = device.get('federatedIdentity')
                    
                    print(f"✓ Found NAB device")
                    print(f"  UUID (duid): {self.device_uuid}")
                    print(f"  Numeric ID (clientId): {self.client_id_numeric}")
                    print(f"  Cognito Identity: {self.cognito_identity_id}")
                    
                    # Display water level data - NOW CORRECTLY INTERPRETED
                    droplet = device.get('droplet', {})
                    tof_distance_mm = device.get('crockTofDistance')
                    tof_distance_cm = tof_distance_mm / 10 if tof_distance_mm else None
                    
                    print(f"\n  Water Level Data:")
                    print(f"    Distance to water: {tof_distance_mm}mm ({tof_distance_cm}cm)")
                    print(f"    Water trend: {droplet.get('trend')} (rising/stable/receding)")
                    print(f"    Flood risk: {droplet.get('floodRisk')}")
                    print(f"    Droplet level value: {droplet.get('level')} (meaning unclear)")
                    
                    # Pump information
                    pump_info = device.get('pumpInfo', {})
                    main_pump = pump_info.get('main', {})
                    backup_pump = pump_info.get('backup', {})
                    
                    print(f"\n  Pump Configuration:")
                    print(f"    Basin diameter: {main_pump.get('crockDiameter')}\" ({device.get('crockDiameterMM')}mm)")
                    print(f"    Main pump: {main_pump.get('manufacturer')} {main_pump.get('model')}")
                    print(f"    Backup pump: {backup_pump.get('manufacturer')} {backup_pump.get('model')}")
                    print(f"    Has backup: {pump_info.get('hasBackupPump')}")
                    
                    print(f"\n  Pump States:")
                    print(f"    Primary pump (droplet): {droplet.get('primaryState')}")
                    print(f"    Backup pump (droplet): {droplet.get('backupState')}")
                    print(f"    System state: {device.get('systemState')}")
                    
                    print(f"\n  System Status:")
                    print(f"    Connected: {device.get('connected')}")
                    print(f"    WiFi RSSI: {device.get('wifiRssi')} dBm")
                    print(f"    Power source: {device.get('powerSource')}")
                    print(f"    Battery: {device.get('batteryPercentage')}%")
                    print(f"    Firmware: {device.get('firmwareVersion')}")
                    
                    # Show alert details - this is how the app determines pump status!
                    alerts = device.get('alerts', {})
                    active_alerts = {aid: alert for aid, alert in alerts.items() if 'active' in alert.get('state', '')}
                    
                    if active_alerts:
                        print(f"\n  Active Alerts ({len(active_alerts)}):")
                        for alert_id, alert_data in active_alerts.items():
                            timestamp = alert_data.get('timestamp', 'unknown')
                            state = alert_data.get('state', 'unknown')
                            print(f"    Alert {alert_id}: {state} - {timestamp}")
                    else:
                        print(f"\n  Active Alerts: None")
                    
                    return device
        
        print("✗ No NAB device found")
        return None

    def test_environment_data(self):
        """Test temperature and humidity endpoint"""
        print("\n=== Testing Environment Data (Temp/Humidity) ===")
        
        # KEY: Must use numeric clientId in pathParameters
        body = {
            "cognitoIdentityId": self.cognito_identity_id,
            "pathParameters": {
                "duid": self.client_id_numeric,  # Numeric ID, NOT UUID
                "deviceType": "NAB"
            }
        }
        
        result = self.invoke_lambda(
            "fbgpg_usage_v1_get_device_environment_latest_prod",
            body
        )
        
        if result:
            temp = result.get('tempData', {}).get('current')
            humid = result.get('humidData', {}).get('current')
            print(f"✓ Environment data retrieved")
            print(f"  Temperature: {temp}°F")
            print(f"  Humidity: {humid}%")
            return result
        else:
            print("✗ No environment data available")
        return None

    def test_daily_stats(self):
        """Test daily pump capacity statistics"""
        print("\n=== Testing Daily Pump Stats ===")
        
        # KEY: Must use numeric clientId at root level
        body = {
            "cognitoIdentityId": self.cognito_identity_id,
            "duid": self.client_id_numeric  # Numeric ID, NOT UUID
        }
        
        result = self.invoke_lambda(
            "fbgpg_usage_v1_get_my_usage_device_history_top10_prod",
            body
        )
        
        if result:
            health = result.get('pumpCapacitySufficient')
            indicator = result.get('pumpIndicator')
            print(f"✓ Daily stats retrieved")
            print(f"  Capacity Sufficient: {health}")
            print(f"  Pump Indicator: {indicator}")
            
            if "TopTen" in result and len(result["TopTen"]) > 0:
                print(f"  Recent usage data: {len(result['TopTen'])} days")
                latest = result["TopTen"][0]
                print(f"    Latest - Day: {latest.get('day')}, Capacity: {latest.get('capacity')}%")
            
            return result
        else:
            print("✗ No daily stats available")
        return None

    def test_event_logs(self):
        """Test event logs - all events are pump-related"""
        print("\n=== Testing Event Logs ===")
        
        # KEY: Uses UUID, not numeric ID
        body = {
            "cognitoIdentityId": self.cognito_identity_id,
            "duid": self.device_uuid,  # UUID for logs
            "limit": 50,
            "locale": "en_US"
        }
        
        result = self.invoke_lambda(
            "fbgpg_logs_v1_get_device_logs_user_prod",
            body
        )
        
        if result and "events" in result:
            events = result["events"]
            print(f"✓ Retrieved {len(events)} events")
            
            # All events are pump-related
            # Show the most recent event (most important)
            if events:
                most_recent = events[0]
                print(f"\n  Most Recent Event:")
                print(f"    Event ID: {most_recent.get('id')}")
                print(f"    Title: {most_recent.get('title')}")
                print(f"    Severity: {most_recent.get('severity')}")
                print(f"    Time: {most_recent.get('time')}")
                print(f"    Details: {most_recent.get('text')}")
                
                try:
                    ts = most_recent.get('time').split('.')[0]
                    event_time = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    diff = now - event_time
                    hours = diff.total_seconds() / 3600
                    print(f"    Time ago: {hours:.1f} hours")
                except Exception as e:
                    pass
                
                # Show a few more recent events for context
                if len(events) > 1:
                    print(f"\n  Recent Event History (last 5):")
                    for i, event in enumerate(events[:5], 1):
                        print(f"    {i}. [{event.get('severity')}] ID {event.get('id')}: {event.get('title')}")
            
            return result
        else:
            print("✗ No event logs available")
        return None

    def test_pump_cycles(self):
        """Test pump cycle history - the detailed Water In/Out data"""
        print("\n=== Testing Pump Cycle History ===")
        
        # KEY: Must use numeric clientId and type='session'
        body = {
            "cognitoIdentityId": self.cognito_identity_id,
            "duid": self.client_id_numeric,  # Numeric ID, NOT UUID
            "type": "session",  # This is the magic parameter!
            "limit": 10,
            "locale": "en_US"
        }
        
        result = self.invoke_lambda(
            "fbgpg_usage_v1_get_my_usage_device_history_prod",
            body
        )
        
        if result and "usage" in result and len(result["usage"]) > 0:
            cycles = result["usage"]
            print(f"✓ Retrieved {len(cycles)} pump cycles")
            
            # Show the most recent cycle
            latest = cycles[0]
            print(f"\n  Most Recent Cycle:")
            print(f"    Time: {latest.get('date')}")
            print(f"    Water In: {latest.get('fillVolume')} {latest.get('fillVolumeUnits')} for {latest.get('fillTimeMS')/1000:.0f} sec")
            print(f"    Water Out: {latest.get('emptyVolume')} {latest.get('emptyVolumeUnits')} in {latest.get('emptyTimeMS')/1000:.0f} sec")
            print(f"    Backup Ran: {latest.get('backupRan')}")
            
            # Calculate time since last cycle
            try:
                ts = latest.get('date').split('.')[0]
                cycle_time = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                diff = now - cycle_time
                minutes = diff.total_seconds() / 60
                if minutes < 60:
                    print(f"    Time ago: {minutes:.0f} min")
                else:
                    print(f"    Time ago: {minutes/60:.1f} hours")
            except:
                pass
            
            # Show summary of recent cycles
            if len(cycles) > 1:
                print(f"\n  Recent Cycles Summary:")
                total_gallons = sum(c.get('emptyVolume', 0) for c in cycles)
                backup_count = sum(1 for c in cycles if c.get('backupRan'))
                print(f"    Total gallons (last {len(cycles)} cycles): {total_gallons:.1f} gal")
                print(f"    Backup pump engaged: {backup_count}/{len(cycles)} times")
            
            return result
        else:
            print("✗ No pump cycle history available")
        return None

    def run_full_test(self):
        """Run complete test of all endpoints"""
        print("=" * 70)
        print("MOEN NAB API - COMPLETE TEST")
        print("=" * 70)
        
        if not self.authenticate():
            print("\n✗ Cannot proceed without authentication")
            return None
        
        device = self.get_device_info()
        if not device:
            print("\n✗ Cannot proceed without device info")
            return None
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "device_uuid": self.device_uuid,
            "client_id_numeric": self.client_id_numeric,
            "data": {}
        }
        
        # Test all endpoints
        env = self.test_environment_data()
        if env:
            results["data"]["environment"] = env
        
        stats = self.test_daily_stats()
        if stats:
            results["data"]["daily_stats"] = stats
        
        cycles = self.test_pump_cycles()
        if cycles:
            results["data"]["pump_cycles"] = cycles
        
        logs = self.test_event_logs()
        if logs:
            results["data"]["event_logs"] = logs
        
        # Save results
        filename = f"moen_nab_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n{'=' * 70}")
        print(f"✓ Test complete!")
        print(f"✓ Results saved to: {filename}")
        print(f"{'=' * 70}")
        
        return results


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python moen_nab_test_corrected.py <username> <password>")
        sys.exit(1)
    
    tester = MoenNABTester(sys.argv[1], sys.argv[2])
    tester.run_full_test()