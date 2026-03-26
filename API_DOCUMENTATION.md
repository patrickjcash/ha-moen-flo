# Moen Smart Sump Pump (NAB) API Documentation

This document consolidates all reverse-engineered findings for the Moen Flo NAB (Smart Sump Pump Monitor) API. It is the single source of truth — `API_ENDPOINTS_REFERENCE.md` is superseded by this file.

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Lambda Invoker Pattern](#lambda-invoker-pattern)
4. [Device Identification: Dual ID System](#device-identification-dual-id-system)
5. [Endpoints](#endpoints)
   - [Device List](#1-device-list)
   - [Device Get (Single)](#2-device-get-single)
   - [Shadow Get (REST)](#3-shadow-get-rest)
   - [Shadow Update (REST)](#4-shadow-update-rest)
   - [Environment (Temp/Humidity)](#5-environment-temphumidity)
   - [Usage History Top-10](#6-usage-history-top-10)
   - [Pump Cycle Session History](#7-pump-cycle-session-history)
   - [Event Logs](#8-event-logs)
   - [Alert Settings by Device](#9-alert-settings-by-device)
   - [Get Current Alerts V2](#10-get-current-alerts-v2)
   - [Get Active Alerts V2](#11-get-active-alerts-v2)
   - [Get Current Alerts V1](#12-get-current-alerts-v1)
   - [Acknowledge Alert](#13-acknowledge-alert)
   - [Silence Alert](#14-silence-alert)
6. [MQTT Connection](#mqtt-connection)
7. [Data Reference](#data-reference)
   - [Device Response Fields](#device-response-fields)
   - [Droplet Object](#droplet-object)
   - [Alert State Format](#alert-state-format)
   - [Alert ID Reference](#alert-id-reference)
8. [Known Limitations](#known-limitations)
9. [Confirmed Non-Existent Endpoints](#confirmed-non-existent-endpoints)
10. [Endpoint Naming Patterns](#endpoint-naming-patterns)

---

## Overview

The Moen Flo NAB uses a serverless AWS architecture. All REST API calls are dispatched through a single Lambda invoker endpoint. Real-time device control requires MQTT over AWS IoT.

**Key infrastructure:**
- Auth: AWS Cognito User Pool (custom token endpoint)
- API: API Gateway → Lambda invoker → individual Lambda functions
- Real-time: AWS IoT MQTT (requires Cognito Identity Pool credentials)

---

## Authentication

### Endpoint
```
POST https://4j1gkf0vji.execute-api.us-east-2.amazonaws.com/prod/v1/oauth2/token
```

### Headers
```
User-Agent: Smartwater-iOS-prod-3.39.0
Content-Type: application/json
```

### Request Body
```json
{
  "client_id": "6qn9pep31dglq6ed4fvlq6rp5t",
  "username": "user@example.com",
  "password": "password"
}
```

### Response
```json
{
  "token": {
    "access_token": "eyJ...",
    "id_token": "eyJ...",
    "refresh_token": "eyJ...",
    "expires_in": 3600
  }
}
```

### Notes
- Use `access_token` in `Authorization: Bearer` headers for Lambda invoker calls
- Use `id_token` for AWS Cognito Identity Pool credential exchange (MQTT)
- Tokens expire after 1 hour (3600 seconds)
- No client secret required (public client)

---

## Lambda Invoker Pattern

All REST API calls POST to a single invoker endpoint that dispatches to specific Lambda functions.

### Endpoint
```
POST https://exo9f857n8.execute-api.us-east-2.amazonaws.com/prod/v1/invoker
```

### Headers
```
Authorization: Bearer {access_token}
User-Agent: Smartwater-iOS-prod-3.39.0
Content-Type: application/json
```

### Request Structure
```json
{
  "fn": "lambda-function-name",
  "parse": false,
  "escape": false,
  "body": {
    "key": "value"
  }
}
```

- `parse`: When `true`, the invoker JSON-parses the Lambda response body for you
- `escape`: When `true`, enables JSON escaping of the body

### Response Structure
```json
{
  "StatusCode": 200,
  "Payload": {
    "statusCode": 200,
    "body": { ... }
  }
}
```

Response parsing pattern:
```python
data = await resp.json()
if data.get("StatusCode") == 200:
    payload = data.get("Payload")
    if isinstance(payload, str):
        payload = json.loads(payload)       # First parse: sometimes double-encoded
    if isinstance(payload, dict) and "body" in payload:
        body = payload["body"]
        if isinstance(body, str):
            body = json.loads(body)         # Second parse: body may be a JSON string
        # body is now the actual data
```

---

## Device Identification: Dual ID System

NAB devices have **two distinct identifiers**. Using the wrong one returns null/404.

| Identifier | Format | Used For |
|------------|--------|----------|
| `duid` | UUID string (`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`) | Device list, event logs, alert endpoints |
| `clientId` | Integer (e.g., `123456789`) | Shadow API, environment, usage history |

Both IDs are returned by the device list endpoint:
```python
devices = invoke_lambda("smartwater-app-device-api-prod-list", {"locale": "en_US"})
device = [d for d in devices if d.get("deviceType") == "NAB"][0]
duid      = device["duid"]       # UUID
client_id = device["clientId"]   # Integer (pass as string to some endpoints)
```

**Alert endpoints** use the numeric `clientId` (NOT UUID), passed as a string in `pathParameters.duid`. This naming is confusing but confirmed by testing.

---

## Endpoints

### 1. Device List

**Function:** `smartwater-app-device-api-prod-list`

**Purpose:** List all devices on the account. Primary source for both device IDs.

**Payload:**
```json
{"locale": "en_US"}
```

**Response:** Array of device objects (see [Device Response Fields](#device-response-fields))

---

### 2. Device Get (Single)

**Function:** `smartwater-app-device-api-prod-get`

**Purpose:** Get a single device by `clientId`.

**ID Type:** Numeric `clientId`

**Payload:**
```json
{"clientId": 123456789}
```

**Response:** Same flat structure as a single item from device list. Does NOT wrap the device in a `device.state` envelope. Returns no additional fields beyond what the list endpoint provides.

---

### 3. Shadow Get (REST)

**Function:** `smartwater-app-shadow-api-prod-get`

**Purpose:** Get the AWS IoT device shadow (cached device state).

**ID Type:** Numeric `clientId`

**Payload:**
```json
{"clientId": 123456789}
```

**Response:**
```json
{
  "state": {
    "reported": {
      "sens_on": true,
      "droplet": {
        "level": 14.2,
        "trend": -0.5,
        "floodRisk": 15,
        "primaryState": "normal",
        "backupState": "not_running"
      },
      "alerts": {
        "266": {
          "state": "active_unlack_unrack_unsuppressed",
          "timestamp": 1736640106624
        }
      }
    },
    "desired": {}
  }
}
```

**Notes:**
- Returns cached state; device is NOT contacted
- `sens_on` controls whether distance sensor is active (must be `true` for readings)
- To trigger a live reading, MQTT is required (see [MQTT Connection](#mqtt-connection))

---

### 4. Shadow Update (REST)

**Function:** `smartwater-app-shadow-api-prod-update`

**Purpose:** Update the device shadow desired/reported state.

**ID Type:** Numeric `clientId`

**Payload:**
```json
{
  "clientId": 123456789,
  "state": {
    "reported": {
      "sens_on": true
    }
  }
}
```

**Notes:**
- REST shadow updates do NOT trigger device actions (device doesn't poll REST)
- For device commands (e.g., activate sensor), use MQTT

---

### 5. Environment (Temp/Humidity)

**Function:** `fbgpg_usage_v1_get_device_environment_latest_prod`

**Purpose:** Get current temperature and humidity readings.

**ID Type:** Numeric `clientId` (as string)

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
  "ts": 1736640106624
}
```

- Temperature: Fahrenheit
- Humidity: Percentage (0–100)
- Timestamp: Unix milliseconds

---

### 6. Usage History Top-10

**Function:** `fbgpg_usage_v1_get_usage_device_history_top10_prod`

**Purpose:** Daily pump usage statistics (capacity, cycle counts).

**ID Type:** Numeric `clientId`

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
      "ts": 1736640106624,
      "pumpCapacityPercentage": 23.5,
      "pumpCycles": 15,
      "date": "2024-01-15"
    }
  ]
}
```

---

### 7. Pump Cycle Session History

**Function:** `fbgpg_usage_v1_get_my_usage_device_history_prod`

**Purpose:** Detailed per-cycle data including fill/empty volumes and durations.

**ID Type:** Numeric `clientId` (passed as `duid`)

**Critical:** Must include `"type": "session"` or you get daily aggregates, not per-cycle data.

**Payload:**
```json
{
  "cognitoIdentityId": "us-east-2:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
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

- `fillVolume` — Water inflow rate (gallons per minute)
- `fillTimeMS` — Duration water was filling the basin (ms)
- `emptyVolume` — Volume pumped out per cycle (gallons)
- `emptyTimeMS` — How long pump ran (ms)
- `backupRan` — Whether backup pump engaged

---

### 8. Event Logs

**Function:** `fbgpg_logs_v1_get_device_logs_user_prod`

**Purpose:** Historical event log with notification IDs and titles.

**ID Type:** UUID `duid`

**Payload:**
```json
{
  "cognitoIdentityId": "us-east-2:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "duid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "limit": 200,
  "locale": "en_US"
}
```

**Response:**
```json
{
  "events": [
    {
      "id": "267",
      "title": "Main Pump Stops Normally",
      "text": "The main pump has stopped running.",
      "time": 1736640106624,
      "severity": "info"
    }
  ]
}
```

**Note:** This endpoint is the only source of notification title metadata. There is no dedicated `/notification-types` endpoint — titles must be mined from event logs.

---

### 9. Alert Settings by Device

**Function:** `fbgpg_user_v1_alert_settings_by_device_get_prod`

**Purpose:** Get per-alert notification channel preferences (push, email, voice, text).

**ID Type:** Numeric `clientId` (as string, in `pathParameters.duid`)

**Payload:**
```json
{
  "pathParameters": {
    "duid": "123456789"
  }
}
```

**Response:** Array of alert setting objects:
```json
[
  {
    "alertTypeId": 224,
    "push": true,
    "email": true,
    "voice": false,
    "text": false,
    "args": ["223", "225"]
  }
]
```

- Returns ~20 alert type IDs per device
- The `args` field on some alerts contains related alert IDs (e.g., alert 224 "High Water Level" has args referencing the low/normal threshold alert IDs)
- Passing the UUID `duid` returns empty results; numeric `clientId` is required

---

### 10. Get Current Alerts V2

**Function:** `fbgpg_alerts_v2_get_alerts_current_by_user_prod`

**Purpose:** Get only unacknowledged alerts. **Recommended for HA integration.**

**Payload:**
```json
{}
```

**Response:**
```json
{
  "alerts": [
    {
      "id": "266",
      "duid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "time": "2026-01-12T00:21:46.624Z",
      "state": "active_unlack_unrack_unsuppressed",
      "severity": "warning",
      "title": "Main Pump Not Stopping",
      "text": "The main pump will not stop running...",
      "detailsObject": {
        "flags": ["allow_active_rem_ack", "notify", "push", "email"],
        "priority": 80
      },
      "dismiss": true,
      "silence": false
    }
  ]
}
```

- `dismiss: true` → Alert can be dismissed via the acknowledge endpoint
- `dismiss: false` → Alert cannot be manually dismissed (resolves when condition clears)
- Acknowledged alerts are automatically excluded from this endpoint's results

---

### 11. Get Active Alerts V2

**Function:** `fbgpg_alerts_v2_get_alerts_active_by_user_prod`

**Purpose:** Get ALL active alerts including acknowledged ones.

**Payload:** `{}`

**Response:** Same structure as V2 current endpoint.

**Note:** Do not use for display — includes acknowledged alerts that should be hidden from users.

---

### 12. Get Current Alerts V1

**Function:** `fbgpg_alerts_v1_get_alerts_current_by_user_prod`

**Purpose:** V1 alert retrieval. Returns different structure; lacks `dismiss`/`silence` fields.

**Payload:** `{}`

**Response includes:** `active`, `localAck`, `remoteAck`, `suppressed`, `actions` fields (different schema from V2).

---

### 13. Acknowledge Alert

**Function:** `fbgpg_alerts_v1_acknowledge_alert_prod`

**Purpose:** Mark an alert as acknowledged (changes `unlack` → `lack` in shadow state).

**ID Type:** Numeric `clientId` AS STRING, in `pathParameters.duid`

**Payload:**
```json
{
  "pathParameters": {
    "duid": "123456789",
    "alertEventId": "266"
  }
}
```

**Invoker format** (use `parse: true, escape: true`):
```json
{
  "fn": "fbgpg_alerts_v1_acknowledge_alert_prod",
  "parse": true,
  "escape": true,
  "body": {
    "pathParameters": {
      "duid": "123456789",
      "alertEventId": "266"
    }
  }
}
```

**Response:** HTTP 204 No Content

**Effect:**
- Alert state: `active_unlack_unrack_unsuppressed` → `active_lack_unrack_unsuppressed`
- Alert's `dismiss` field changes from `true` to `false`
- Alert is removed from `fbgpg_alerts_v2_get_alerts_current_by_user_prod` results
- Alert remains visible in device shadow and Moen app (does NOT fully dismiss)

---

### 14. Silence Alert

**Function:** `fbgpg_alerts_v1_silence_alert_prod`

**Purpose:** Silence/suppress an alert. Functionally identical to acknowledge.

**Payload:** Same as acknowledge alert.

**Response:** HTTP 204 No Content

**Effect:** Identical to `fbgpg_alerts_v1_acknowledge_alert_prod`.

---

## MQTT Connection

Real-time device reading triggers (e.g., activating `sens_on`) require MQTT over AWS IoT. REST shadow updates do not command the device.

### Setup

1. **Exchange Cognito tokens for Identity credentials:**
```python
import boto3

cognito_client = boto3.client("cognito-identity", region_name="us-east-2")
identity_pool_id = "us-east-2:7880fbef-a3a8-4ffc-a0d1-74e686e79c80"
user_pool_provider = "cognito-idp.us-east-2.amazonaws.com/us-east-2_Cqk5OcQJh"

# Get identity ID
identity_resp = cognito_client.get_id(
    IdentityPoolId=identity_pool_id,
    Logins={user_pool_provider: id_token}
)
identity_id = identity_resp["IdentityId"]

# Get credentials
creds_resp = cognito_client.get_credentials_for_identity(
    IdentityId=identity_id,
    Logins={user_pool_provider: id_token}
)
credentials = creds_resp["Credentials"]
# credentials["AccessKeyId"], credentials["SecretKey"], credentials["SessionToken"]
```

2. **Connect via MQTT:**
```python
import aiomqtt

MQTT_ENDPOINT = "a1p3vgpxlnkaa2-ats.iot.us-east-2.amazonaws.com"
MQTT_PORT = 443
SHADOW_TOPIC = f"$aws/things/{client_id}/shadow/update"

async with aiomqtt.Client(
    hostname=MQTT_ENDPOINT,
    port=MQTT_PORT,
    transport="websockets",
    websocket_path="/mqtt",
    # ... SigV4 auth headers using credentials
) as client:
    await client.publish(
        SHADOW_TOPIC,
        json.dumps({"state": {"desired": {"sens_on": True}}})
    )
```

### Shadow Topics
```
$aws/things/{clientId}/shadow/update           # Publish desired state
$aws/things/{clientId}/shadow/update/accepted  # Subscribe for confirmation
$aws/things/{clientId}/shadow/get              # Request current shadow
$aws/things/{clientId}/shadow/get/accepted     # Subscribe for shadow response
```

---

## Data Reference

### Device Response Fields

Fields returned by `smartwater-app-device-api-prod-list` and `smartwater-app-device-api-prod-get`:

| Field | Type | Description |
|-------|------|-------------|
| `duid` | string | UUID device identifier |
| `clientId` | integer | Numeric device identifier |
| `nickname` | string | User-assigned device name |
| `location` | string | Location description |
| `deviceType` | string | `"NAB"` for sump pump monitors |
| `connected` | boolean | Device online status |
| `batteryPercentage` | integer | Battery charge (0–100) |
| `powerSource` | string | Power source description |
| `wifiRssi` | integer | WiFi signal strength (dBm, negative) |
| `fwVersion` | string | Firmware version string |
| `crockTofDistance` | float | Distance from sensor to water surface (inches). Lower = higher water level. |
| `crockDiameter` | float | Sump pit diameter (inches) |
| `droplet` | object | Computed flood risk state (see below) |
| `federatedIdentity` | string | Cognito Identity ID (used for MQTT auth and some Lambda calls) |
| `lastHeardFromTime` | integer | Timestamp of last device communication (Unix ms) |
| `alerts` | array | Active alert summaries |

**Fields that do NOT exist** (do not use these):
- ~~`waterLevelCritical`~~ — Does not exist in any API endpoint
- ~~`waterLevelWarning`~~ — Does not exist in any API endpoint
- ~~`isConnected`~~ — Use `connected`
- ~~`batteryLevel`~~ — Use `batteryPercentage`
- ~~`isOnBattery`~~ — Use `powerSource`
- ~~`signalStrength`~~ — Use `wifiRssi`

---

### Droplet Object

The `droplet` object appears in both the device list and device shadow. It represents the Moen backend's computed flood risk assessment:

```json
{
  "level": 14.2,
  "trend": -0.5,
  "floodRisk": 15,
  "primaryState": "normal",
  "backupState": "not_running"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `level` | float | Current water level (inches from floor, not sensor) |
| `trend` | float | Rate of change (inches/hour, negative = falling) |
| `floodRisk` | integer | Risk score (0–100) |
| `primaryState` | string | Main pump state (`"normal"`, `"running"`, etc.) |
| `backupState` | string | Backup pump state (`"not_running"`, `"running"`, etc.) |

Water level thresholds (critical/warning) are computed server-side and published only as part of `floodRisk`. They are not configurable via API and not exposed as raw values.

---

### Alert State Format

Alert states follow the pattern: `{activity}_{ack}_{rack}_{suppressed}`

| Component | Values | Meaning |
|-----------|--------|---------|
| activity | `active` / `inactive` | Whether the condition is currently occurring |
| ack | `unlack` / `lack` | Whether user has acknowledged (`lack` = acknowledged) |
| rack | `unrack` / `rack` | Unknown purpose (possibly "re-acknowledged") |
| suppressed | `unsuppressed` / `suppressed` | Whether alert is suppressed/muted |

**Examples:**
- `active_unlack_unrack_unsuppressed` — New unacknowledged active alert (shown in app)
- `active_lack_unrack_unsuppressed` — Active but acknowledged (API acknowledge result)
- `inactive_unlack_unrack_unsuppressed` — Condition resolved, not yet acknowledged

---

### Alert ID Reference

Alert IDs from three sources:
1. **`fbgpg_user_v1_alert_settings_by_device_get_prod`** — Comprehensive list of IDs configured on device
2. **`fbgpg_logs_v1_get_device_logs_user_prod`** — Titles and severities from event history
3. **Decompiled Android APK** — Enum names, dismiss behavior, and shadow commands

**Dismiss behavior:**
- `dismiss: true` — Can be acknowledged via `fbgpg_alerts_v1_acknowledge_alert_prod`
- `dismiss: false` — Cannot be dismissed via normal flow; resolves when condition clears or via shadow command

| ID | Title | Severity | dismiss | Notes | Source |
|----|-------|----------|---------|-------|--------|
| 213 | (unknown) | — | — | | Alert settings |
| 218 | Backup Test Scheduled | info | false | Pathway notification; not shown in app when actionable alerts present; excluded from HA active count | Event logs |
| 222 | (unknown) | — | — | | Alert settings |
| 224 | High Water Level | warning | true | | Event logs + alert settings |
| 225 | Normal Water Level | info | — | | Event logs |
| 230 | (unknown) | — | — | | Alert settings |
| 232 | (unknown) | — | — | | Alert settings |
| 236 | Sensor Too Close | critical | — | | Event logs |
| 250 | (unknown) | — | — | | Alert settings |
| 254 | Critical Flood Risk | critical | — | | Event logs + alert settings |
| 256 | High Flood Risk | critical | — | | Event logs + alert settings |
| 258 | Flood Risk | warning | — | | Event logs + alert settings |
| 259 | Flood Risk Cleared | info | — | | Event logs |
| 260 | Main Pump Failed | critical | — | | Event logs + alert settings |
| 261 | Main Pump Reset | info | — | | Event logs |
| 262 | Main Pump Overwhelmed | critical | — | | Event logs + alert settings |
| 263 | Main Pump Recovered | info | — | | Event logs |
| 266 | Main Pump Not Stopping | warning | false | Pathway 2 alert; cleared by shadow command `crockCommand: rst_primary` (from `RESET_PRIMARY_STATE` enum in APK). Cannot be dismissed via normal acknowledge flow. | Event logs + alert settings + APK |
| 267 | Main Pump Stops Normally | info | — | | Event logs |
| 268 | Backup Pump Not Stopping *(inferred)* | warning *(inferred)* | false *(inferred)* | Likely backup pump equivalent of 266; probably cleared by `crockCommand: rst_backup` (`RESET_BACKUP_STATE` in APK) | Alert settings + APK |
| 269 | Backup Pump Reset | info | — | | Event logs |
| 270 | Backup Pump Stops Normally *(inferred)* | info *(inferred)* | — | Likely backup pump equivalent of 267 | Alert settings |
| 301 | (unknown) | — | — | Seen in alert settings args on North pump | Alert settings |
| 1716 | (unknown) | — | — | | Alert settings |
| 1718 | (unknown) | — | — | | Alert settings |
| 1720 | (unknown) | — | — | | Alert settings |
| 1722 | (unknown) | — | — | | Alert settings |
| 2802 | (unknown) | — | — | | Alert settings |
| 2803 | (unknown) | — | — | | Alert settings |

**Notification types seen in the Moen app UI, not yet mapped to IDs:**
- Dead Battery (critical)
- Backup Test Failed (critical)
- Overflow Water Level (critical)
- Water Detected (critical)
- Backup Pump Failed (critical)
- Backup Pump Overwhelmed (warning)
- Device Lost (warning)
- Water Level Sensor Communication Lost (warning)
- Main Power Lost (warning)
- Low Battery (warning)
- Possible Drain Backflow (warning)
- Main Power Restored (info)
- Check Battery Water Level (info)
- Network Connected (info)

---

## Known Limitations

1. **No water level threshold API**: `waterLevelCritical` and `waterLevelWarning` do **not** exist in any API endpoint. They were incorrectly documented in an earlier version of this file. Water level risk is expressed only through the `droplet.floodRisk` score (0–100), computed server-side.

2. **No dedicated notification metadata endpoint**: No `/notification-types` or equivalent Lambda function exists. Notification titles must be mined from event logs. See `NOTIFICATION_DISCOVERY.md`.

3. **Alert dismissal is partial**: API acknowledge/silence (`lack`) does not fully dismiss alerts. Manual dismissal in the Moen app removes alerts from shadow entirely; API acknowledge only changes the `unlack`→`lack` component while the alert remains in shadow.

4. **No historical water level data**: Only current sensor distance (`crockTofDistance`) is available. The API does not store or return historical water level readings.

5. **REST shadow updates don't command device**: To trigger a live sensor reading (`sens_on`), MQTT is required. REST shadow writes are ignored by the device.

6. **`fbgpg_alerts_v1_get_alert_types_prod` does not exist**: Confirmed Lambda `ResourceNotFoundException`.

7. **`type: "session"` required for per-cycle data**: Without this parameter, `fbgpg_usage_v1_get_my_usage_device_history_prod` returns daily aggregates instead of per-cycle records.

---

## Confirmed Non-Existent Endpoints

These Lambda function names were tested and returned `ResourceNotFoundException` or equivalent errors:

- `fbgpg_alerts_v1_get_alert_types_prod`
- `smartwater-app-location-api-prod-list`
- `smartwater-app-house-api-prod-list`
- `fbgpg_location_v1_get_locations_prod`
- `fbgpg_house_v1_get_houses_prod`
- `smartwater-app-user-api-prod-locations`
- `smartwater-app-user-api-prod-houses`

---

## Endpoint Naming Patterns

Two generations of naming exist:

| Pattern | Example | Era |
|---------|---------|-----|
| `smartwater-app-{service}-api-prod-{action}` | `smartwater-app-device-api-prod-list` | Legacy |
| `fbgpg_{service}_v{ver}_{action}_prod` | `fbgpg_usage_v1_get_my_usage_device_history_prod` | Current |

**Service codes (fbgpg):**
- `alerts` — Alert management and retrieval
- `device` — Device control and attributes
- `usage` — Statistics and session history
- `logs` — Event logging
- `user` — User settings and preferences

---

## Reverse Engineering Methods

1. **Decompiled Android APK** (jadx) — Primary source for Lambda function names and payload structures. Key files:
   - `com/moen/smartwater/base/utils/ConstantsKt.java` — All endpoint name constants
   - `com/moen/smartwater/base/data/repositories/AlertRepository.java` — Alert payload structures
2. **HTTPS traffic interception** (mitmproxy with SSL pinning bypass via Frida)
3. **Exhaustive endpoint testing** — Permuting known patterns against all discovered function names

---

## Disclaimer

This documentation is provided for educational and Home Assistant integration purposes only. The Moen Flo API is not officially public. This integration is not endorsed by Moen or Fortune Brands. Use at your own risk.
