"""
Moen NAB API Explorer
Systematically test various endpoints to find pump cycle/run data

USAGE:
    python moen_nab_api_explorer.py <moen_username> <moen_password>

    Example:
    python moen_nab_api_explorer.py user@example.com mypassword

    Output: Creates a JSON file with timestamp containing exploration results
"""

import requests
import json
import sys
from datetime import datetime

# API Configuration
OAUTH_BASE = "https://4j1gkf0vji.execute-api.us-east-2.amazonaws.com/prod/v1"
INVOKER_BASE = "https://exo9f857n8.execute-api.us-east-2.amazonaws.com/prod/v1/invoker"
CLIENT_ID = "6qn9pep31dglq6ed4fvlq6rp5t"
USER_AGENT = "Smartwater-iOS-prod-3.39.0"


class MoenNABExplorer:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.access_token = None
        self.device_uuid = None
        self.client_id_numeric = None
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
                print("✓ Authenticated\n")
                return True
        except Exception as e:
            print(f"✗ Auth failed: {e}")
        return False
    
    def invoke_lambda(self, function_name, body):
        """Call Lambda function via invoker endpoint"""
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
            resp = requests.post(INVOKER_BASE, json=payload, headers=headers, timeout=30)
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
            return {"error": str(e)}
        return None

    def get_device_ids(self):
        """Get device IDs needed for API calls"""
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
                    return True
        return False

    def test_endpoint(self, function_name, body, description):
        """Test a single endpoint and report results"""
        print(f"Testing: {description}")
        print(f"  Function: {function_name}")
        print(f"  Body: {json.dumps(body, indent=4)}")
        
        result = self.invoke_lambda(function_name, body)
        
        if result:
            if isinstance(result, dict) and result.get("error"):
                print(f"  ✗ Error: {result['error']}\n")
            else:
                print(f"  ✓ Success!")
                print(f"  Response preview: {json.dumps(result, indent=4)[:500]}...\n")
                return result
        else:
            print(f"  ✗ No data returned\n")
        return None

    def explore_usage_endpoints(self):
        """Try various usage/history endpoints with different parameters"""
        print("=" * 70)
        print("EXPLORING USAGE/HISTORY ENDPOINTS")
        print("=" * 70 + "\n")
        
        results = {}
        
        # Test 1: Device history with different types
        for history_type in ["session", "cycle", "run", "pump", "event"]:
            result = self.test_endpoint(
                "fbgpg_usage_v1_get_my_usage_device_history_prod",
                {
                    "cognitoIdentityId": self.cognito_identity_id,
                    "duid": self.client_id_numeric,
                    "type": history_type,
                    "limit": 10,
                    "locale": "en_US"
                },
                f"Device history with type='{history_type}'"
            )
            if result:
                results[f"history_type_{history_type}"] = result
        
        # Test 2: Try with UUID instead of numeric ID
        result = self.test_endpoint(
            "fbgpg_usage_v1_get_my_usage_device_history_prod",
            {
                "cognitoIdentityId": self.cognito_identity_id,
                "duid": self.device_uuid,
                "type": "session",
                "limit": 10,
                "locale": "en_US"
            },
            "Device history with UUID (instead of numeric ID)"
        )
        if result:
            results["history_uuid"] = result
        
        # Test 3: Device sessions (if different from history)
        result = self.test_endpoint(
            "fbgpg_usage_v1_get_device_sessions_prod",
            {
                "cognitoIdentityId": self.cognito_identity_id,
                "duid": self.client_id_numeric,
                "limit": 10,
                "locale": "en_US"
            },
            "Device sessions endpoint"
        )
        if result:
            results["device_sessions"] = result
        
        # Test 4: Pump runs/cycles
        result = self.test_endpoint(
            "fbgpg_usage_v1_get_pump_cycles_prod",
            {
                "cognitoIdentityId": self.cognito_identity_id,
                "duid": self.client_id_numeric,
                "limit": 10,
                "locale": "en_US"
            },
            "Pump cycles endpoint"
        )
        if result:
            results["pump_cycles"] = result
        
        # Test 5: Usage summary
        result = self.test_endpoint(
            "fbgpg_usage_v1_get_usage_summary_prod",
            {
                "cognitoIdentityId": self.cognito_identity_id,
                "duid": self.client_id_numeric,
                "locale": "en_US"
            },
            "Usage summary endpoint"
        )
        if result:
            results["usage_summary"] = result
        
        # Test 6: Hourly usage (for the chart data)
        result = self.test_endpoint(
            "fbgpg_usage_v1_get_hourly_usage_prod",
            {
                "cognitoIdentityId": self.cognito_identity_id,
                "duid": self.client_id_numeric,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "locale": "en_US"
            },
            "Hourly usage endpoint (for chart)"
        )
        if result:
            results["hourly_usage"] = result
        
        # Test 7: Daily usage
        result = self.test_endpoint(
            "fbgpg_usage_v1_get_daily_usage_prod",
            {
                "cognitoIdentityId": self.cognito_identity_id,
                "duid": self.client_id_numeric,
                "locale": "en_US"
            },
            "Daily usage endpoint"
        )
        if result:
            results["daily_usage"] = result
        
        return results

    def explore_telemetry_endpoints(self):
        """Try various telemetry/sensor endpoints"""
        print("\n" + "=" * 70)
        print("EXPLORING TELEMETRY/SENSOR ENDPOINTS")
        print("=" * 70 + "\n")
        
        results = {}
        
        # Test 1: Device telemetry
        result = self.test_endpoint(
            "fbgpg_telemetry_v1_get_device_telemetry_prod",
            {
                "cognitoIdentityId": self.cognito_identity_id,
                "duid": self.client_id_numeric,
                "locale": "en_US"
            },
            "Device telemetry endpoint"
        )
        if result:
            results["telemetry"] = result
        
        # Test 2: Sensor readings
        result = self.test_endpoint(
            "fbgpg_telemetry_v1_get_sensor_readings_prod",
            {
                "cognitoIdentityId": self.cognito_identity_id,
                "duid": self.client_id_numeric,
                "locale": "en_US"
            },
            "Sensor readings endpoint"
        )
        if result:
            results["sensor_readings"] = result
        
        # Test 3: Current state
        result = self.test_endpoint(
            "fbgpg_device_v1_get_current_state_prod",
            {
                "cognitoIdentityId": self.cognito_identity_id,
                "duid": self.client_id_numeric,
                "locale": "en_US"
            },
            "Current state endpoint"
        )
        if result:
            results["current_state"] = result
        
        return results

    def run_exploration(self):
        """Run full exploration"""
        if not self.authenticate():
            return None
        
        if not self.get_device_ids():
            print("✗ Could not get device IDs")
            return None
        
        print(f"Device UUID: {self.device_uuid}")
        print(f"Numeric ID: {self.client_id_numeric}\n")
        
        all_results = {}
        
        # Explore usage endpoints
        usage_results = self.explore_usage_endpoints()
        all_results["usage_endpoints"] = usage_results
        
        # Explore telemetry endpoints
        telemetry_results = self.explore_telemetry_endpoints()
        all_results["telemetry_endpoints"] = telemetry_results
        
        # Save results
        filename = f"moen_api_exploration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(all_results, f, indent=2)
        
        print("\n" + "=" * 70)
        print(f"✓ Exploration complete! Results saved to: {filename}")
        print("=" * 70)
        
        return all_results


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python moen_nab_api_explorer.py <username> <password>")
        sys.exit(1)
    
    explorer = MoenNABExplorer(sys.argv[1], sys.argv[2])
    explorer.run_exploration()