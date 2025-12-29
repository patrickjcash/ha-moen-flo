"""API client for Moen Flo NAB devices."""
import aiohttp
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List

_LOGGER = logging.getLogger(__name__)

# API Constants
AUTH_URL = "https://4j1gkf0vji.execute-api.us-east-2.amazonaws.com/prod/v1/oauth2/token"
INVOKER_URL = "https://exo9f857n8.execute-api.us-east-2.amazonaws.com/prod/v1/invoker"

# NOTE: This CLIENT_ID is extracted from the Moen mobile app.
# It is app-specific (not user-specific) but may change with app updates.
CLIENT_ID = "6qn9pep31dglq6ed4fvlq6rp5t"

USER_AGENT = "Smartwater-iOS-prod-3.39.0"


class MoenFloNABApiError(Exception):
    """Base exception for Moen Flo NAB API errors."""
    pass


class MoenFloNABAuthError(MoenFloNABApiError):
    """Authentication error."""
    pass


class MoenFloNABClient:
    """Client for Moen Flo NAB API."""

    def __init__(self, username: str, password: str, session: aiohttp.ClientSession):
        """Initialize the client."""
        self.username = username
        self.password = password
        self.session = session
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        self._cognito_identity_id: Optional[str] = None

    async def authenticate(self) -> bool:
        """Authenticate with Moen Flo API."""
        try:
            # Simple authentication payload
            auth_data = {
                "client_id": CLIENT_ID,
                "username": self.username,
                "password": self.password
            }

            headers = {
                "User-Agent": USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded"
            }

            async with self.session.post(
                AUTH_URL, data=json.dumps(auth_data), headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    _LOGGER.error(f"Authentication failed: {error_text}")
                    raise MoenFloNABAuthError(f"Authentication failed: {error_text}")

                data = await response.json()
                
                if "token" not in data:
                    raise MoenFloNABAuthError("No token in response")

                result = data["token"]
                self._access_token = result.get("access_token")
                
                # Set token expiry (typically 1 hour)
                expires_in = result.get("expires_in", 3600)
                self._token_expiry = datetime.now() + timedelta(seconds=expires_in - 300)
                
                _LOGGER.info("Successfully authenticated with Moen Flo API")
                return True

        except aiohttp.ClientError as err:
            _LOGGER.error(f"Network error during authentication: {err}")
            raise MoenFloNABApiError(f"Network error: {err}")

    async def _ensure_authenticated(self):
        """Ensure we have a valid access token."""
        if not self._access_token or not self._token_expiry:
            await self.authenticate()
        elif datetime.now() >= self._token_expiry:
            _LOGGER.info("Token expired, re-authenticating")
            await self.authenticate()

    async def _invoke_lambda(
        self, function_name: str, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Invoke a Lambda function through the invoker API."""
        await self._ensure_authenticated()

        request_payload = {
            "parse": False,
            "body": payload or {},
            "fn": function_name,
            "escape": False
        }

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        }

        try:
            async with self.session.post(
                INVOKER_URL, json=request_payload, headers=headers
            ) as response:
                if response.status == 401:
                    _LOGGER.warning("Received 401, re-authenticating")
                    await self.authenticate()
                    return await self._invoke_lambda(function_name, payload)

                if response.status != 200:
                    error_text = await response.text()
                    _LOGGER.error(
                        f"Lambda invocation failed: {function_name} - {error_text}"
                    )
                    raise MoenFloNABApiError(
                        f"Lambda invocation failed: {error_text}"
                    )

                data = await response.json()
                
                # Parse nested payload structure
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
                
                return data

        except aiohttp.ClientError as err:
            _LOGGER.error(f"Network error invoking {function_name}: {err}")
            raise MoenFloNABApiError(f"Network error: {err}")

    async def get_devices(self) -> List[Dict[str, Any]]:
        """Get list of devices with both UUID and numeric ID."""
        payload = {"locale": "en_US"}
        response = await self._invoke_lambda(
            "smartwater-app-device-api-prod-list", payload
        )
        
        # Response can be direct list or nested in body
        if isinstance(response, list):
            return response
        
        if isinstance(response, dict):
            if "data" in response:
                return response["data"]
            if "body" in response:
                body = response["body"]
                if isinstance(body, str):
                    body = json.loads(body)
                if isinstance(body, list):
                    return body
                if isinstance(body, dict) and "data" in body:
                    return body["data"]
        
        return []

    async def get_device_data(self, device_duid: str) -> Dict[str, Any]:
        """Get detailed device data using UUID."""
        devices = await self.get_devices()
        for device in devices:
            if device.get("duid") == device_duid:
                # Store cognito ID for later use
                self._cognito_identity_id = device.get("federatedIdentity")
                return device
        return {}

    async def get_device_environment(self, client_id: int) -> Dict[str, Any]:
        """Get temperature and humidity data using numeric client_id.
        
        CRITICAL: Must use numeric clientId, NOT UUID!
        Returns: {"tempData": {...}, "humidData": {...}}
        """
        payload = {
            "cognitoIdentityId": self._cognito_identity_id,
            "pathParameters": {
                "duid": str(client_id),  # Despite name, this takes numeric ID
                "deviceType": "NAB"
            }
        }
        
        response = await self._invoke_lambda(
            "fbgpg_usage_v1_get_device_environment_latest_prod", payload
        )
        
        return response if isinstance(response, dict) else {}

    async def get_pump_health(self, client_id: int) -> Dict[str, Any]:
        """Get pump health/capacity data using numeric client_id.
        
        CRITICAL: Must use numeric clientId, NOT UUID!
        Returns: {"pumpCapacitySufficient": bool, "pumpIndicator": string, "TopTen": [...]}
        """
        payload = {
            "cognitoIdentityId": self._cognito_identity_id,
            "duid": client_id
        }
        
        response = await self._invoke_lambda(
            "fbgpg_usage_v1_get_my_usage_device_history_top10_prod", payload
        )
        
        return response if isinstance(response, dict) else {}

    async def get_pump_cycles(
        self, client_id: int, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get detailed pump cycle history using numeric client_id.
        
        CRITICAL DISCOVERY: Must use type="session" to get cycle data!
        
        Returns list of cycles with:
        - date: Timestamp of cycle
        - fillVolume: Water in rate (gpm)
        - fillTimeMS: Fill duration (milliseconds)
        - emptyVolume: Water pumped out (gallons)
        - emptyTimeMS: Pump run time (milliseconds)
        - backupRan: Whether backup pump engaged (boolean)
        """
        payload = {
            "cognitoIdentityId": self._cognito_identity_id,
            "duid": client_id,
            "type": "session",  # CRITICAL: Must be "session" for cycle data!
            "limit": limit,
            "locale": "en_US"
        }
        
        response = await self._invoke_lambda(
            "fbgpg_usage_v1_get_my_usage_device_history_prod", payload
        )
        
        # Extract usage array from response
        if isinstance(response, dict) and "usage" in response:
            return response["usage"]
        
        return []

    async def get_device_logs(
        self, device_duid: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get device event logs using UUID.
        
        CRITICAL: Uses UUID duid, NOT numeric clientId!
        Returns event log entries with id, title, time, severity, text.
        """
        payload = {
            "cognitoIdentityId": self._cognito_identity_id,
            "duid": device_duid,  # UUID for logs
            "limit": limit,
            "locale": "en_US"
        }
        
        response = await self._invoke_lambda(
            "fbgpg_logs_v1_get_device_logs_user_prod", payload
        )
        
        # Extract events array
        if isinstance(response, dict) and "events" in response:
            return response["events"]
        
        return []

    async def get_last_pump_cycle(self, device_duid: str) -> Optional[Dict[str, Any]]:
        """Get the most recent pump cycle event from logs.
        
        Note: Event IDs are event TYPES, not sequential numbers.
        Looking at recent events to find the most recent pump-related event.
        """
        logs = await self.get_device_logs(device_duid, limit=50)
        
        # Return the most recent event (they're sorted by time, newest first)
        if logs and len(logs) > 0:
            return logs[0]
        
        return None
