# API Reverse Engineering Documentation

This document details the reverse engineering process and findings for the Moen Flo NAB API.

## Overview

The Moen Flo NAB (Sump Pump Monitor) uses a serverless architecture with AWS Lambda functions accessed through an API Gateway invoker endpoint. Authentication is handled via AWS Cognito.

## Authentication

### Endpoint
```
POST https://4j1gkf0vji.execute-api.us-east-2.amazonaws.com/prod/v1/oauth2/token
```

### Headers
```
Content-Type: application/x-amz-json-1.1
X-Amz-Target: AWSCognitoIdentityProviderService.InitiateAuth
```

### Request Body
```json
{
  "AuthFlow": "USER_PASSWORD_AUTH",
  "ClientId": "6qn9pep31dglq6ed4fvlq6rp5t",
  "AuthParameters": {
    "USERNAME": "user@example.com",
    "PASSWORD": "password"
  }
}
```

### Response
```json
{
  "AuthenticationResult": {
    "AccessToken": "eyJraWQiOiJ...",
    "IdToken": "eyJraWQiOiJVc...",
    "RefreshToken": "eyJjdHkiOiJ...",
    "ExpiresIn": 3600,
    "TokenType": "Bearer"
  }
}
```

### Notes
- `IdToken` is used for API authorization
- Tokens expire after 1 hour (3600 seconds)
- No client secret is required (public client)

## Lambda Invoker Pattern

All API calls go through a central invoker endpoint that dispatches to specific Lambda functions.

### Invoker Endpoint
```
POST https://exo9f857n8.execute-api.us-east-2.amazonaws.com/prod/v1/invoker
```

### Headers
```
Authorization: Bearer {IdToken}
Content-Type: application/json
```

### Request Structure
```json
{
  "functionName": "lambda-function-name",
  "payload": "{\"key\":\"value\"}"
}
```

### Response Structure
```json
{
  "payload": "{\"body\":\"{...}\"}"
}
```

The response contains nested JSON that must be parsed multiple times.

## Critical Discovery: Dual ID System

**This was the key breakthrough in accessing all device data.**

The Moen Flo NAB API uses TWO different identifiers for the same device:

1. **`duid` (Device UUID)** - String UUID format
   - Example: `"2c6fa88a-1234-5678-9abc-def012345678"`
   - Used for: Device lists, event logs
   
2. **`clientId` (Numeric Client ID)** - Integer format
   - Example: `123456789`
   - Used for: Telemetry, environment data, usage statistics

**Why this matters:** Initially, we could only get device info and logs because we were using the UUID everywhere. Temperature, humidity, and pump health data were returning `null` or `404` because those endpoints require the numeric `clientId`, not the UUID.

### How to Get Both IDs

Call the device list endpoint - it returns BOTH IDs:

```python
response = await invoke_lambda("smartwater-app-device-api-prod-list", {})
# Response contains array of devices, each with:
{
  "duid": "2c6fa88a-1234-5678-9abc-def012345678",  # UUID
  "clientId": 123456789,                            # Numeric ID
  "nickname": "Sump Pump",
  ...
}
```

## Lambda Functions

### 1. Device List
**Function:** `smartwater-app-device-api-prod-list`

**Purpose:** Get all devices associated with the account

**Payload:**
```json
{}
```

**Response:**
```json
{
  "body": {
    "data": [
      {
        "duid": "uuid-here",
        "clientId": 123456789,
        "nickname": "Sump Pump",
        "location": "Basement",
        "deviceType": "nab",
        "isConnected": true,
        "online": true,
        "fwVersion": "1.2.3",
        "crockTofDistance": 18.5,
        "crockDiameter": 18.11,
        "waterLevelCritical": 6.0,
        "waterLevelWarning": 8.0,
        "batteryLevel": 100,
        "isOnBattery": false,
        "signalStrength": -65,
        "lastHeardFromTime": 1234567890,
        "alerts": []
      }
    ]
  }
}
```

**Key Fields:**
- `crockTofDistance` - Distance from sensor to water (inches), lower = higher water level
- `crockDiameter` - Sump pit diameter (inches)
- `waterLevelCritical` - Critical threshold (inches from sensor)
- `waterLevelWarning` - Warning threshold (inches from sensor)
- `isOnBattery` - Battery backup status
- `signalStrength` - WiFi signal strength (dBm)

### 2. Environment Data (Temperature/Humidity)
**Function:** `fbgpg_usage_v1_get_device_environment_latest_prod`

**Purpose:** Get current temperature and humidity readings

**Critical:** Must use numeric `clientId`, NOT UUID!

**Payload:**
```json
{
  "pathParameters": {
    "clientId": "123456789"
  }
}
```

**Response:**
```json
{
  "temperature": 64.0,
  "humidity": 48.0,
  "ts": 1234567890
}
```

**Units:**
- Temperature: Fahrenheit
- Humidity: Percentage (0-100)
- Timestamp: Unix milliseconds

### 3. Pump Health/Capacity
**Function:** `fbgpg_usage_v1_get_usage_device_history_top10_prod`

**Purpose:** Get pump usage statistics and health metrics

**Critical:** Must use numeric `clientId`, NOT UUID!

**Payload:**
```json
{
  "clientId": 123456789,
  "queryStringParameters": {
    "sortBy": "ts",
    "orderBy": "desc",
    "limit": "10"
  }
}
```

**Response:**
```json
{
  "data": [
    {
      "ts": 1234567890,
      "pumpCapacityPercentage": 23.5,
      "pumpCycles": 15,
      "date": "2024-01-15"
    }
  ]
}
```

**Key Fields:**
- `pumpCapacityPercentage` - Percentage of daily pump capacity used
- `pumpCycles` - Number of pump cycles in the period
- Returns up to 10 most recent daily records

### 4. Pump Cycle History (CRITICAL DISCOVERY!)
**Function:** `fbgpg_usage_v1_get_my_usage_device_history_prod`

**Purpose:** Get detailed pump cycle data including water volumes and durations

**Critical:** Must use numeric `clientId`, NOT UUID! Must include `type: "session"`!

**Payload:**
```json
{
  "cognitoIdentityId": "identity-id-here",
  "duid": 123456789,
  "type": "session",
  "limit": 10,
  "locale": "en_US"
}
```

**Response:**
```json
{
  "usage": [
    {
      "date": "2024-12-29T10:30:15.000Z",
      "fillVolume": 1.2,
      "fillVolumeUnits": "gpm",
      "fillTimeMS": 45000,
      "emptyVolume": 5.5,
      "emptyVolumeUnits": "gal",
      "emptyTimeMS": 12000,
      "backupRan": false
    }
  ]
}
```

**Key Fields:**
- `fillVolume` - Water inflow rate (gallons per minute)
- `fillTimeMS` - Duration water was filling the basin (milliseconds)
- `emptyVolume` - Amount of water pumped out (gallons)
- `emptyTimeMS` - Duration pump was running (milliseconds)
- `backupRan` - Whether backup pump engaged (boolean)

**BREAKTHROUGH:** Using `type: "session"` was the key to unlocking this data! Without this parameter, the endpoint returns empty or different data.

### 5. Device Event Logs
**Function:** `fbgpg_logs_v1_get_device_logs_user_prod`

**Purpose:** Get device event history

**Uses:** UUID `duid`, not numeric ID

**Payload:**
```json
{
  "cognitoIdentityId": "identity-id-here",
  "duid": "uuid-here",
  "limit": 100,
  "locale": "en_US"
}
```

**Response:**
```json
{
  "events": [
    {
      "id": 267,
      "title": "Main Pump Stops Normally",
      "text": "The main pump has stopped",
      "time": 1234567890,
      "severity": "info"
    }
  ]
}
```

**Key Event IDs:**
- `267` - Main Pump Stops Normally
- `254` - Critical Flood Alert
- `256` - High Flood Alert
- `258` - Flood Risk Alert
- Other event IDs represent various pump and system events

## Data Mapping

### What's Available

| Metric | Source | ID Type | API Endpoint | Status |
|--------|--------|---------|--------------|--------|
| Water Level | Device List | UUID | `device-api-prod-list` | ✅ Available |
| Temperature | Environment | Numeric | `get_device_environment_latest_prod` | ✅ Available |
| Humidity | Environment | Numeric | `get_device_environment_latest_prod` | ✅ Available |
| Pump Health | Usage History | Numeric | `usage_device_history_top10_prod` | ✅ Available |
| **Gallons Pumped** | **Pump Cycles** | **Numeric** | **`usage_device_history_prod`** | **✅ Available!** |
| **Water In Rate** | **Pump Cycles** | **Numeric** | **`usage_device_history_prod`** | **✅ Available!** |
| **Cycle Durations** | **Pump Cycles** | **Numeric** | **`usage_device_history_prod`** | **✅ Available!** |
| **Backup Pump Status** | **Pump Cycles** | **Numeric** | **`usage_device_history_prod`** | **✅ Available!** |
| Last Cycle Time | Pump Cycles | Numeric | `usage_device_history_prod` | ✅ Available |
| Connectivity | Device List | UUID | `device-api-prod-list` | ✅ Available |
| Power Status | Device List | UUID | `device-api-prod-list` | ✅ Available |
| Battery Level | Device List | UUID | `device-api-prod-list` | ✅ Available |
| Alerts | Device List | UUID | `device-api-prod-list` | ✅ Available |
| Event History | Event Logs | UUID | `get_device_logs_user_prod` | ✅ Available |

### What's NOT Available

| Metric | Reason |
|--------|--------|
| Historical water levels | Only current level available (not logged) |
| Real-time streaming | Poll-based API only |

**Major Discovery:** The pump cycle endpoint provides comprehensive data including:
- Exact gallons of water pumped per cycle
- Water inflow rate (gallons per minute)
- Fill duration (how long water was entering the basin)
- Pump run duration (how long pump was running)
- Backup pump engagement status

This data was previously thought unavailable, but was discovered by using the `type: "session"` parameter.

## API Limits and Best Practices

### Rate Limiting
- No explicit rate limits documented
- Recommended polling: Every 5 minutes
- Avoid excessive requests to prevent throttling

### Error Handling
- `401` - Token expired, re-authenticate
- `404` - Wrong endpoint or ID type
- `500` - Lambda error, retry with backoff

### Response Parsing
Many responses require multiple levels of JSON parsing:
```python
response = await invoke_lambda(...)
# First parse: API gateway response
if "payload" in response:
    payload = json.loads(response["payload"])
    # Second parse: Lambda response
    if "body" in payload:
        body = json.loads(payload["body"])
        # Now you have the actual data
        data = body.get("data")
```

## Testing and Validation

### Test Sequence
1. Authenticate and get tokens
2. Get device list (verify both IDs present)
3. Call environment endpoint with numeric ID
4. Call pump health endpoint with numeric ID
5. Call logs endpoint with UUID
6. Verify all data is present

### Expected Values
- Temperature: 40-80°F typical for basements
- Humidity: 30-60% typical
- Water Level: Varies, but should match app
- Pump Capacity: 0-100%

## Integration Architecture

### Update Cycle
```
Every 5 minutes:
1. Get device list (both IDs)
2. Get environment data (numeric ID) → Temp/Humidity
3. Get pump health (numeric ID) → Daily capacity
4. Get pump cycles (numeric ID) → Water volumes & durations
5. Get event logs (UUID) → Event history
6. Aggregate data in coordinator
7. Update all entities
```

### Data Flow
```
User Credentials
    ↓
Cognito Auth → Access Token + ID Token
    ↓
Lambda Invoker → Device List (UUID + Numeric ID)
    ↓
    ├→ Environment (Numeric ID) → Temp/Humidity
    ├→ Pump Health (Numeric ID) → Daily Capacity
    ├→ Pump Cycles (Numeric ID) → Gallons/Durations/Rates
    └→ Event Logs (UUID) → Event History
    ↓
Coordinator → Cache all data
    ↓
Entities (Sensors + Binary Sensors)
```

## Security Considerations

### Credentials
- Username and password stored in Home Assistant's encrypted storage
- Tokens stored in memory, not persisted
- No third-party servers involved

### API Communication
- All communication over HTTPS
- Tokens in Authorization headers
- Standard AWS Cognito security model

## Future Enhancements

### Potential Additions
1. **Historical Data**: Store and graph past water levels
2. **Cycle Analysis**: Calculate cycle duration from log events
3. **Gallons Tracking**: Implement local calculation using pit dimensions
4. **Predictive Alerts**: ML-based flood risk prediction
5. **Multi-Device Support**: Handle multiple sump pumps

### API Opportunities
- Explore other Lambda functions in the app
- Check for batch/bulk data endpoints
- Investigate websocket/push notification capabilities

## Additional Endpoints Discovered (2026-01-11)

### Alert Management

#### Acknowledge Alert
**Function:** `fbgpg_alerts_v1_acknowledge_alert_prod`
**Purpose:** Mark alert as acknowledged/seen
**Payload:**
```json
{
  "fn": "fbgpg_alerts_v1_acknowledge_alert_prod",
  "parse": true,
  "escape": true,
  "body": {
    "pathParameters": {
      "duid": "device-uuid",
      "alertEventId": "262"
    }
  }
}
```
**Response:** HTTP 204 No Content
**Status:** ⚠️ Returns success but effect unclear

#### Silence Alert
**Function:** `fbgpg_alerts_v1_silence_alert_prod`
**Purpose:** Silence/dismiss alert
**Payload:** Same as acknowledge
**Response:** HTTP 204 No Content
**Status:** ⚠️ Returns success but alert remains visible

#### Get Alerts Endpoints
- `fbgpg_alerts_v1_get_alerts_by_user_prod` - All alerts for user
- `fbgpg_alerts_v1_get_alerts_current_by_user_prod` - Current alerts
- `fbgpg_alerts_v2_get_alerts_active_by_user_prod` - Active alerts (V2)
- `fbgpg_v1_get_alerts_by_duid_prod` - Alerts by device UUID

#### Alert Settings
- `fbgpg_user_v1_alert_settings_by_device_get_prod` - Get alert settings
- `fbgpg_user_v1_alert_settings_update_prod` - Update alert settings

### Device Management

- `fbgpg_device_v1_get_device_prod` - Get device details (NAB)
- `fbgpg_device_v1_update_attribute_prod` - Update device attributes
- `fbgpg_device_v1_device_get_latest_firmware_prod` - Check firmware updates
- `fbgpg_device_v1_get_backup_test_status_prod` - Backup pump test status

### Usage & Environment

- `fbgpg_usage_v1_get_my_usage_device_history_top10_prod` - Top 10 usage periods
- `fbgpg_usage_v1_get_last_usage_prod` - Most recent usage
- `fbgpg_usage_v1_put_usage_reset_device_capacity_prod` - Reset capacity tracking
- `fbgpg_usage_v1_get_device_environment_latest_prod` - Environment data (temp/humidity)

### User Settings

- `fbgpg_user_v1_user_settings_get_prod` - Get user preferences
- `fbgpg_user_v1_user_settings_put_prod` - Update preferences

### Endpoint Naming Patterns

**Legacy:** `smartwater-app-{service}-api-prod-{action}`
**New (FBGPG):** `fbgpg_{service}_v{version}_{action}_{environment}`

**Service Codes:**
- `alerts` - Alert management
- `device` - Device control
- `usage` - Statistics/history
- `logs` - Event logging
- `user` - Settings/preferences

### Investigation Notes

All endpoints discovered via decompiled Android app analysis (`/Users/patrick/python/base/sources/com/moen/smartwater/base/utils/ConstantsKt.java`).

Alert dismissal endpoints (acknowledge/silence) return 204 success but don't visibly dismiss alerts - requires further investigation. See `tests/ALERT_DISMISSAL_INVESTIGATION.md` for detailed findings.

## Reverse Engineering Tools Used

1. **mitmproxy** - Intercept HTTPS traffic from mobile app
2. **jadx** - Decompile Android APK
3. **Frida** - Runtime inspection and SSL pinning bypass
4. **Postman** - Test API endpoints
5. **Python requests** - Validate findings

## Credits

This reverse engineering effort involved:
- Analysis of network traffic from the Moen mobile app
- Decompilation of the Android application
- Trial and error with various Lambda functions
- Collaboration between Claude and Gemini AI assistants

The critical breakthrough (dual ID system) was discovered by testing different ID formats across all endpoints.

## Disclaimer

This documentation is provided for educational and integration purposes only. The Moen Flo API is not officially public, and this integration is not endorsed by Moen or Fortune Brands. Use at your own risk.
