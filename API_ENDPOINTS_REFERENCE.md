# Moen Smart Sump Pump API Endpoints Reference

## Alert Retrieval Endpoints

### Get Current Alerts (V2) - **RECOMMENDED FOR HA INTEGRATION**
```
Endpoint: fbgpg_alerts_v2_get_alerts_current_by_user_prod
Method: POST via Lambda Invoker
Body: {}
Returns: Only UNACKNOWLEDGED alerts

Response includes:
- dismiss (boolean) - Can be directly dismissed
- silence (boolean) - Can be silenced
- All standard alert fields
```

**Use this endpoint to show alerts in HA** - acknowledged alerts are automatically hidden.

### Get Active Alerts (V2)
```
Endpoint: fbgpg_alerts_v2_get_alerts_active_by_user_prod
Method: POST via Lambda Invoker
Body: {}
Returns: ALL active alerts (acknowledged and unacknowledged)

Response includes same fields as CURRENT endpoint
```

**Do not use for display** - shows acknowledged alerts that should be hidden.

### Get Current Alerts (V1)
```
Endpoint: fbgpg_alerts_v1_get_alerts_current_by_user_prod
Method: POST via Lambda Invoker
Body: {}
Returns: Alerts with different structure

Response includes:
- active, localAck, remoteAck, suppressed, actions
- Does NOT include dismiss/silence fields
```

## Alert Action Endpoints

### Acknowledge Alert
```
Endpoint: fbgpg_alerts_v1_acknowledge_alert_prod
Method: POST via Lambda Invoker
Parameters:
  pathParameters:
    duid: <numeric_client_id>  # e.g., "100215609"
    alertEventId: <alert_id>    # e.g., "266"

Returns: 204 No Content

Effect:
- Changes state from unlack_unrack to lack_rack
- Changes dismiss from true to false
- Removes from CURRENT endpoint
- For dismiss:true alerts: Dismisses successfully
- For dismiss:false alerts: No effect (requires device action)
```

**Example invocation:**
```python
payload = {
    "parse": True,
    "escape": True,
    "fn": "fbgpg_alerts_v1_acknowledge_alert_prod",
    "body": {
        "pathParameters": {
            "duid": "100215609",
            "alertEventId": "266"
        }
    }
}
```

### Silence Alert
```
Endpoint: fbgpg_alerts_v1_silence_alert_prod
Method: POST via Lambda Invoker
Parameters: Same as acknowledgeAlert

Returns: 204 No Content
Effect: Identical to acknowledgeAlert
```

## Lambda Invoker Pattern

All API calls go through the Lambda invoker:

```
Base URL: https://exo9f857n8.execute-api.us-east-2.amazonaws.com/prod/v1/invoker
Method: POST
Headers:
  Authorization: Bearer <access_token>
  User-Agent: Smartwater-iOS-prod-3.39.0
  Content-Type: application/json

Body structure:
{
  "parse": true/false,
  "escape": true/false,
  "fn": "<endpoint_name>",
  "body": {
    // Endpoint-specific parameters
  }
}
```

## Device Identification

NAB devices have two IDs:
1. **UUID (duid)**: `e0db37b4-1f27-4e70-8479-a0528774e7cd`
2. **Numeric Client ID**: `100215609`

**IMPORTANT**: Alert endpoints require the **numeric client ID**, not the UUID!

Get numeric client ID from device list:
```python
devices = invoke_lambda(token, "smartwater-app-device-api-prod-list", {"locale": "en_US"})
device = [d for d in devices if d.get("deviceType") == "NAB"][0]
client_id = device.get("clientId")  # This is the numeric ID
```

## Authentication

```
Endpoint: https://4j1gkf0vji.execute-api.us-east-2.amazonaws.com/prod/v1/oauth2/token
Method: POST
Headers:
  User-Agent: Smartwater-iOS-prod-3.39.0
  Content-Type: application/json

Body:
{
  "client_id": "6qn9pep31dglq6ed4fvlq6rp5t",
  "username": "<email>",
  "password": "<password>"
}

Response:
{
  "token": {
    "access_token": "eyJ..."
  }
}
```

## Complete Example: Dismiss Alert Workflow

```python
import urllib.request
import json

# 1. Authenticate
auth_url = "https://4j1gkf0vji.execute-api.us-east-2.amazonaws.com/prod/v1/oauth2/token"
auth_payload = {
    "client_id": "6qn9pep31dglq6ed4fvlq6rp5t",
    "username": "user@example.com",
    "password": "password"
}
auth_req = urllib.request.Request(
    auth_url,
    data=json.dumps(auth_payload).encode(),
    headers={"User-Agent": "Smartwater-iOS-prod-3.39.0", "Content-Type": "application/json"}
)
with urllib.request.urlopen(auth_req) as resp:
    token = json.loads(resp.read())["token"]["access_token"]

# 2. Get current alerts
invoker_url = "https://exo9f857n8.execute-api.us-east-2.amazonaws.com/prod/v1/invoker"
get_alerts_payload = {
    "parse": False,
    "escape": False,
    "fn": "fbgpg_alerts_v2_get_alerts_current_by_user_prod",
    "body": {}
}
alerts_req = urllib.request.Request(
    invoker_url,
    data=json.dumps(get_alerts_payload).encode(),
    headers={
        "Authorization": f"Bearer {token}",
        "User-Agent": "Smartwater-iOS-prod-3.39.0",
        "Content-Type": "application/json"
    }
)
with urllib.request.urlopen(alerts_req) as resp:
    result = json.loads(resp.read())
    # Parse response based on StatusCode

# 3. Dismiss dismissible alerts
for alert in alerts:
    if alert.get('dismiss') == True:
        dismiss_payload = {
            "parse": True,
            "escape": True,
            "fn": "fbgpg_alerts_v1_acknowledge_alert_prod",
            "body": {
                "pathParameters": {
                    "duid": client_id,
                    "alertEventId": alert['id']
                }
            }
        }
        dismiss_req = urllib.request.Request(
            invoker_url,
            data=json.dumps(dismiss_payload).encode(),
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "Smartwater-iOS-prod-3.39.0",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(dismiss_req) as resp:
            # Returns 204 No Content on success
            pass
```

## Alert Response Structure

```json
{
  "StatusCode": 200,
  "Payload": {
    "body": {
      "alerts": [
        {
          "id": "266",
          "location": "",
          "duid": "100215609",
          "time": "2026-01-12T00:21:46.624Z",
          "state": "active_unlack_unrack_unsuppressed",
          "severity": "warning",
          "detailsObject": {
            "flags": ["allow_active_rem_ack", "notify", "push", "email"],
            "priority": 80
          },
          "callToAction": {
            "text": "",
            "uri": ""
          },
          "text": "The main pump will not stop running...",
          "title": "Main Pump Not Stopping",
          "troubleshootingUri": "",
          "dismiss": true,
          "silence": false
        }
      ]
    }
  }
}
```

## Known Issues & Limitations

1. **Pathway 2 alerts** (dismiss: false with allow_active_rem_ack) require device reset endpoints which are not yet discovered
2. **Pathway 3 alerts** (dismiss: false with ack_on_clear) cannot be manually dismissed
3. Alert 266 remains in shadow after acknowledging despite dismiss flag changing
4. Manual dismissal in app removes alerts from shadow, but API acknowledge does not
