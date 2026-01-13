"""API client for Moen Flo NAB devices."""
import aiohttp
import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List, Callable

try:
    import boto3
    from awsiot import mqtt_connection_builder
    from awscrt import mqtt, io, auth
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    _LOGGER.warning("MQTT libraries not available, using REST API only")

_LOGGER = logging.getLogger(__name__)

# API Constants
AUTH_URL = "https://4j1gkf0vji.execute-api.us-east-2.amazonaws.com/prod/v1/oauth2/token"
INVOKER_URL = "https://exo9f857n8.execute-api.us-east-2.amazonaws.com/prod/v1/invoker"

# NOTE: This CLIENT_ID is extracted from the Moen mobile app.
# It is app-specific (not user-specific) but may change with app updates.
CLIENT_ID = "6qn9pep31dglq6ed4fvlq6rp5t"

USER_AGENT = "Smartwater-iOS-prod-3.39.0"

# AWS IoT Constants (extracted from Moen mobile app)
IOT_ENDPOINT = "a1r2q5ic87novc-ats.iot.us-east-2.amazonaws.com"
IOT_REGION = "us-east-2"
IDENTITY_POOL_ID = "us-east-2:7880fbef-a3a8-4ffc-a0d1-74e686e79c80"
USER_POOL_ID = "us-east-2_9puIPVyv1"


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
        self._id_token: Optional[str] = None
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
                self._id_token = result.get("id_token")  # Store for MQTT

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

    async def get_locations(self) -> List[Dict[str, Any]]:
        """Get list of all locations/houses for the account.

        Returns list of locations with:
        - locationId: Unique location identifier
        - nickname: User-defined name for the location
        - federatedIdentity: User's cognito identity
        """
        payload = {}
        response = await self._invoke_lambda(
            "smartwater-app-location-api-prod-list", payload
        )

        # Response is a direct list
        if isinstance(response, list):
            return response

        return []

    async def get_devices(self, location_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of devices with both UUID and numeric ID.

        Args:
            location_id: Optional location ID to filter devices

        Returns:
            List of devices. Each device includes:
            - duid: Device UUID
            - clientId: Numeric client ID
            - nickname: User-defined device name
            - locationId: Location the device belongs to
            - roomId: Room the device is in
            - deviceType: Device type (NAB for sump pump monitors)
        """
        payload = {"locale": "en_US"}
        response = await self._invoke_lambda(
            "smartwater-app-device-api-prod-list", payload
        )

        # Response can be direct list or nested in body
        devices = []
        if isinstance(response, list):
            devices = response
        elif isinstance(response, dict):
            if "data" in response:
                devices = response["data"]
            elif "body" in response:
                body = response["body"]
                if isinstance(body, str):
                    body = json.loads(body)
                if isinstance(body, list):
                    devices = body
                elif isinstance(body, dict) and "data" in body:
                    devices = body["data"]

        # Filter by location if specified
        if location_id and devices:
            devices = [d for d in devices if d.get("locationId") == location_id]

        return devices

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

    async def get_notification_metadata(self, device_duid: str) -> Dict[str, Dict[str, str]]:
        """Build notification ID to description mapping from event logs.

        This extracts notification metadata (ID, title, severity) from device
        event logs. Since the API doesn't provide a dedicated notification
        metadata endpoint, we mine the event logs to build the mapping.

        Args:
            device_duid: Device UUID

        Returns:
            Dictionary mapping notification ID to metadata:
            {
                "218": {"title": "Backup Test Scheduled", "severity": "info"},
                "224": {"title": "High Water Level", "severity": "warning"},
                ...
            }
        """
        # Get a large sample of events to capture all notification types
        events = await self.get_device_logs(device_duid, limit=200)

        notification_map = {}

        for event in events:
            event_id = str(event.get("id", ""))
            title = event.get("title", "")
            severity = event.get("severity", "")

            if event_id and title and event_id not in notification_map:
                notification_map[event_id] = {
                    "title": title,
                    "severity": severity,
                }

        _LOGGER.debug(
            f"Built notification metadata map with {len(notification_map)} types from event logs"
        )

        return notification_map

    async def update_shadow(self, client_id: int, command: str = "sens_on") -> bool:
        """Trigger device to update its shadow with fresh sensor readings.

        CRITICAL: Must use numeric clientId, NOT UUID!

        This sends a command to the device to take fresh sensor readings
        and report them to the AWS IoT Shadow. Common commands:
        - "sens_on": Turn sensors on and take fresh readings (default)
        - "updates_off": Turn updates off

        Args:
            client_id: Numeric client ID
            command: Shadow command to send (default: "sens_on")

        Returns:
            True if command was sent successfully
        """
        payload = {
            "clientId": client_id,
            "crockCommand": command
        }

        try:
            await self._invoke_lambda(
                "smartwater-app-shadow-api-prod-update", payload
            )
            return True
        except Exception as err:
            _LOGGER.error(f"Failed to update shadow: {err}")
            return False

    async def get_shadow(self, client_id: int) -> Dict[str, Any]:
        """Get device shadow (live telemetry) using numeric client_id.

        CRITICAL: Must use numeric clientId, NOT UUID!

        This returns the AWS IoT Device Shadow with live telemetry data.
        The shadow contains real-time sensor readings including:
        - crockTofDistance: Water level
        - droplet: Flood risk analysis
        - connected: Connection status
        - wifiRssi: WiFi signal strength
        - batteryPercentage: Battery level
        - powerSource: AC/battery status
        - alerts: Active device alerts

        Returns: Device shadow with state.reported containing live data
        """
        payload = {
            "clientId": client_id
        }

        response = await self._invoke_lambda(
            "smartwater-app-shadow-api-prod-get", payload
        )

        return response if isinstance(response, dict) else {}

    async def acknowledge_alert(self, client_id: int, alert_id: str) -> bool:
        """Acknowledge/dismiss a specific alert.

        Args:
            client_id: Numeric device client ID
            alert_id: Alert ID to acknowledge (e.g., "218", "266")

        Returns:
            True if acknowledgement was successful, False otherwise
        """
        # Try to update the shadow to acknowledge the alert
        # This may set the alert to "acked" or "suppressed" state
        payload = {
            "clientId": client_id,
            "alertAck": alert_id
        }

        try:
            response = await self._invoke_lambda(
                "smartwater-app-shadow-api-prod-update", payload
            )
            _LOGGER.debug(f"Acknowledged alert {alert_id}: {response}")
            return True
        except Exception as err:
            _LOGGER.error(f"Failed to acknowledge alert {alert_id}: {err}")
            return False

    async def dismiss_all_alerts(self, client_id: int) -> Dict[str, bool]:
        """Dismiss all active alerts for a device.

        Args:
            client_id: Numeric device client ID

        Returns:
            Dictionary mapping alert IDs to success status
        """
        # First, get current alerts
        shadow = await self.get_shadow(client_id)
        if not shadow or "state" not in shadow:
            _LOGGER.warning(f"No shadow data for device {client_id}")
            return {}

        reported = shadow.get("state", {}).get("reported", {})
        alerts = reported.get("alerts", {})

        if not alerts:
            _LOGGER.info(f"No alerts to dismiss for device {client_id}")
            return {}

        # Attempt to acknowledge each active alert
        results = {}
        for alert_id, alert_data in alerts.items():
            state = alert_data.get("state", "")
            # Only dismiss active alerts
            if "active" in state and "inactive" not in state:
                success = await self.acknowledge_alert(client_id, alert_id)
                results[alert_id] = success
                _LOGGER.info(f"Alert {alert_id} dismiss: {'success' if success else 'failed'}")

        return results

    def create_mqtt_client(self, client_id: int) -> Optional['MoenFloNABMqttClient']:
        """Create an MQTT client for real-time device data.

        Args:
            client_id: Numeric device client ID

        Returns:
            MoenFloNABMqttClient instance or None if ID token not available
        """
        if not self._id_token:
            _LOGGER.error("No ID token available, authenticate first")
            return None

        if not MQTT_AVAILABLE:
            _LOGGER.warning("MQTT libraries not available")
            return None

        return MoenFloNABMqttClient(client_id, self._id_token)


class MoenFloNABMqttClient:
    """MQTT client for real-time Moen Flo NAB device data.

    This client maintains a persistent MQTT connection to AWS IoT Core
    and provides real-time sensor data updates. It uses adaptive polling:
    - Normal: Update every 5 minutes
    - Alert: Update every 30-60 seconds
    - Critical: Continuous streaming (~90 readings/minute)
    """

    def __init__(self, client_id: int, id_token: str):
        """Initialize MQTT client.

        Args:
            client_id: Numeric device client ID
            id_token: Cognito ID token from authentication
        """
        self.client_id = client_id
        self.id_token = id_token
        self.mqtt_connection = None
        self.event_loop_group = None
        self.host_resolver = None
        self.client_bootstrap = None
        self._shadow_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._connected = False
        self._last_shadow_data: Optional[Dict[str, Any]] = None
        self._credentials_expiry: Optional[datetime] = None

    def _get_aws_credentials(self) -> Dict[str, str]:
        """Get temporary AWS credentials from Cognito using ID token."""
        if not MQTT_AVAILABLE:
            raise MoenFloNABApiError("MQTT libraries not available")

        cognito_identity = boto3.client('cognito-identity', region_name=IOT_REGION)
        provider_name = f"cognito-idp.{IOT_REGION}.amazonaws.com/{USER_POOL_ID}"

        # Exchange ID token for Cognito identity
        identity_response = cognito_identity.get_id(
            IdentityPoolId=IDENTITY_POOL_ID,
            Logins={provider_name: self.id_token}
        )

        # Get temporary AWS credentials
        credentials_response = cognito_identity.get_credentials_for_identity(
            IdentityId=identity_response['IdentityId'],
            Logins={provider_name: self.id_token}
        )

        credentials = credentials_response['Credentials']

        # Track credential expiration (AWS credentials typically valid for 1 hour)
        # Set expiry to 5 minutes before actual expiration to ensure smooth refresh
        expiration = credentials.get('Expiration')
        if expiration:
            # AWS returns timezone-aware datetime, convert to naive local time
            if expiration.tzinfo is not None:
                expiration = expiration.replace(tzinfo=None)
            self._credentials_expiry = expiration - timedelta(minutes=5)
            _LOGGER.debug(f"AWS credentials expire at {expiration}, will refresh at {self._credentials_expiry}")
        else:
            # Fallback if no expiration provided (default 1 hour minus 5 min buffer)
            self._credentials_expiry = datetime.now() + timedelta(minutes=55)
            _LOGGER.debug(f"No expiration in credentials, using default refresh at {self._credentials_expiry}")

        return {
            'access_key': credentials['AccessKeyId'],
            'secret_key': credentials['SecretKey'],
            'session_token': credentials['SessionToken']
        }

    def _setup_mqtt_connection(self, aws_creds: Dict[str, str]):
        """Set up MQTT connection (blocking operation)."""
        # Set up AWS IoT connection
        self.event_loop_group = io.EventLoopGroup(1)
        self.host_resolver = io.DefaultHostResolver(self.event_loop_group)
        self.client_bootstrap = io.ClientBootstrap(
            self.event_loop_group, self.host_resolver
        )

        # Create MQTT connection
        self.mqtt_connection = mqtt_connection_builder.websockets_with_default_aws_signing(
            endpoint=IOT_ENDPOINT,
            client_bootstrap=self.client_bootstrap,
            region=IOT_REGION,
            credentials_provider=auth.AwsCredentialsProvider.new_static(
                access_key_id=aws_creds['access_key'],
                secret_access_key=aws_creds['secret_key'],
                session_token=aws_creds['session_token']
            ),
            client_id=f"moen-ha-{uuid.uuid4()}",
            clean_session=True,
            keep_alive_secs=30
        )

    async def connect(self) -> bool:
        """Establish MQTT connection to AWS IoT Core.

        Returns:
            True if connection successful
        """
        if not MQTT_AVAILABLE:
            _LOGGER.warning("MQTT not available, cannot connect")
            return False

        try:
            _LOGGER.info(f"Connecting to AWS IoT MQTT for device {self.client_id}")

            # Get AWS credentials in executor to avoid blocking
            loop = asyncio.get_event_loop()
            aws_creds = await loop.run_in_executor(None, self._get_aws_credentials)

            # Set up MQTT connection in executor to avoid blocking
            await loop.run_in_executor(None, self._setup_mqtt_connection, aws_creds)

            # Connect (run blocking operations in executor)
            connect_future = self.mqtt_connection.connect()
            await loop.run_in_executor(None, connect_future.result)

            # Subscribe to shadow topics
            get_accepted_topic = f"$aws/things/{self.client_id}/shadow/get/accepted"
            update_accepted_topic = f"$aws/things/{self.client_id}/shadow/update/accepted"

            subscribe_future, _ = self.mqtt_connection.subscribe(
                topic=get_accepted_topic,
                qos=mqtt.QoS.AT_LEAST_ONCE,
                callback=self._on_shadow_message
            )
            await loop.run_in_executor(None, subscribe_future.result)

            subscribe_future2, _ = self.mqtt_connection.subscribe(
                topic=update_accepted_topic,
                qos=mqtt.QoS.AT_LEAST_ONCE,
                callback=self._on_shadow_message
            )
            await loop.run_in_executor(None, subscribe_future2.result)

            self._connected = True
            _LOGGER.info(f"Successfully connected to AWS IoT MQTT for device {self.client_id}")
            return True

        except Exception as err:
            _LOGGER.error(f"Failed to connect to MQTT: {err}")
            self._connected = False
            return False

    def _on_shadow_message(self, topic, payload, dup, qos, retain, **kwargs):
        """Handle incoming MQTT shadow messages."""
        try:
            data = json.loads(payload)
            if "state" in data:
                reported = data.get("state", {}).get("reported", {})
                self._last_shadow_data = reported

                # Call all registered callbacks
                for callback in self._shadow_callbacks:
                    try:
                        callback(reported)
                    except Exception as err:
                        _LOGGER.error(f"Error in shadow callback: {err}")

        except Exception as err:
            _LOGGER.error(f"Error parsing shadow message: {err}")

    def register_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Register a callback to be called when shadow data is received.

        Args:
            callback: Function to call with shadow data dict
        """
        if callback not in self._shadow_callbacks:
            self._shadow_callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Unregister a shadow data callback."""
        if callback in self._shadow_callbacks:
            self._shadow_callbacks.remove(callback)

    async def trigger_sensor_update(self, command: str = "sens_on") -> bool:
        """Trigger device to take fresh sensor readings via MQTT.

        Sends a shadow update command to tell the device to take measurements.
        The device will then push updated readings via the subscribed topics.

        Args:
            command: Shadow command (default: "sens_on")

        Returns:
            True if command sent successfully
        """
        if not self._connected or not self.mqtt_connection:
            _LOGGER.warning("MQTT not connected, cannot trigger sensor update")
            return False

        try:
            update_topic = f"$aws/things/{self.client_id}/shadow/update"
            payload = {
                "state": {
                    "desired": {
                        "crockCommand": command
                    }
                }
            }

            publish_future, _ = self.mqtt_connection.publish(
                topic=update_topic,
                payload=json.dumps(payload),
                qos=mqtt.QoS.AT_LEAST_ONCE
            )
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, publish_future.result)

            _LOGGER.debug(f"Triggered sensor update with command: {command}")
            return True

        except Exception as err:
            _LOGGER.error(f"Failed to trigger sensor update: {err}")
            return False

    async def request_shadow(self) -> bool:
        """Request current shadow state via MQTT.

        Returns:
            True if request sent successfully
        """
        if not self._connected or not self.mqtt_connection:
            return False

        try:
            get_topic = f"$aws/things/{self.client_id}/shadow/get"
            publish_future, _ = self.mqtt_connection.publish(
                topic=get_topic,
                payload="",
                qos=mqtt.QoS.AT_LEAST_ONCE
            )
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, publish_future.result)
            return True

        except Exception as err:
            _LOGGER.error(f"Failed to request shadow: {err}")
            return False

    @property
    def last_shadow_data(self) -> Optional[Dict[str, Any]]:
        """Get the last received shadow data."""
        return self._last_shadow_data

    @property
    def is_connected(self) -> bool:
        """Check if MQTT connection is active."""
        return self._connected

    async def disconnect(self):
        """Disconnect from MQTT."""
        if self.mqtt_connection and self._connected:
            try:
                disconnect_future = self.mqtt_connection.disconnect()
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, disconnect_future.result)
                _LOGGER.info(f"Disconnected from MQTT for device {self.client_id}")
            except Exception as err:
                _LOGGER.error(f"Error disconnecting from MQTT: {err}")
            finally:
                self._connected = False

    def needs_reconnect(self) -> bool:
        """Check if MQTT connection needs to be refreshed due to credential expiration.

        Returns:
            True if credentials are expired or about to expire
        """
        if not self._connected:
            return True

        if not self._credentials_expiry:
            # No expiry tracked, assume we need to reconnect after 50 minutes
            return True

        # Check if credentials have expired or will expire soon
        now = datetime.now()
        needs_refresh = now >= self._credentials_expiry
        if needs_refresh:
            _LOGGER.info(f"AWS credentials expired for device {self.client_id}, reconnection needed")
        return needs_refresh

    async def reconnect_with_new_token(self, new_id_token: str) -> bool:
        """Reconnect MQTT with a new ID token.

        Args:
            new_id_token: Fresh Cognito ID token

        Returns:
            True if reconnection successful
        """
        _LOGGER.info(f"Reconnecting MQTT for device {self.client_id} with fresh credentials")

        # Disconnect existing connection
        await self.disconnect()

        # Update ID token
        self.id_token = new_id_token

        # Reconnect with fresh credentials
        return await self.connect()
