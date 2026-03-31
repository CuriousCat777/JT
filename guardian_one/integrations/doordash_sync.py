"""DoorDash Drive API integration.

Connects to the DoorDash Drive API using JWT authentication.
The Drive API allows creating and tracking deliveries.

Setup:
1. Sign up at https://developer.doordash.com
2. Create an app to get developer_id, key_id, and signing_secret
3. Set these in your .env file:
       DOORDASH_DEVELOPER_ID=...
       DOORDASH_KEY_ID=...
       DOORDASH_SIGNING_SECRET=...
4. The agent will auto-connect on startup when credentials are present.

API reference: https://developer.doordash.com/en-US/api/drive
"""

from __future__ import annotations

import abc
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.request
import urllib.error
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# DoorDash delivery IDs: alphanumeric, hyphens, underscores only
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class DoorDashRestaurant:
    """Restaurant data from DoorDash."""
    id: str
    name: str
    cuisine: str
    rating: float
    delivery_fee: float
    estimated_minutes: int
    address: str = ""
    raw: dict[str, Any] | None = None


@dataclass
class DoorDashOrderStatus:
    """Live order/delivery status from DoorDash."""
    order_id: str
    status: str
    driver_name: str | None = None
    driver_phone: str | None = None
    driver_location: dict[str, float] | None = None  # lat/lng
    estimated_arrival: str | None = None
    tracking_url: str | None = None
    raw: dict[str, Any] | None = None


@dataclass
class DeliveryRequest:
    """Request to create a delivery via the Drive API."""
    external_delivery_id: str
    pickup_address: str
    pickup_business_name: str
    pickup_phone_number: str
    pickup_instructions: str = ""
    dropoff_address: str = ""
    dropoff_business_name: str = ""
    dropoff_phone_number: str = ""
    dropoff_instructions: str = ""
    order_value: int = 0  # cents
    tip: int = 0  # cents


@dataclass
class DeliveryResponse:
    """Response after creating or querying a delivery."""
    external_delivery_id: str
    delivery_status: str
    tracking_url: str = ""
    fee: int = 0  # cents
    pickup_time_estimated: str = ""
    dropoff_time_estimated: str = ""
    dasher_name: str = ""
    dasher_phone: str = ""
    raw: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------

class DoorDashProvider(abc.ABC):
    """Abstract interface for DoorDash data access."""

    @abc.abstractmethod
    def authenticate(self) -> bool: ...

    @abc.abstractmethod
    def create_delivery(self, request: DeliveryRequest) -> DeliveryResponse | None: ...

    @abc.abstractmethod
    def get_delivery_status(self, external_delivery_id: str) -> DeliveryResponse | None: ...

    @abc.abstractmethod
    def cancel_delivery(self, external_delivery_id: str) -> bool: ...

    @property
    @abc.abstractmethod
    def is_authenticated(self) -> bool: ...


# ---------------------------------------------------------------------------
# JWT helper (DoorDash uses a custom JWT scheme: DD-JWT-V1)
# ---------------------------------------------------------------------------

def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _create_doordash_jwt(
    developer_id: str,
    key_id: str,
    signing_secret: str,
) -> str:
    """Create a JWT token for DoorDash Drive API.

    DoorDash uses HS256 with a custom header version 'DD-JWT-V1'.
    The token is valid for 5 minutes (standard for their API).
    """
    header = {
        "alg": "HS256",
        "typ": "JWT",
        "dd-ver": "DD-JWT-V1",
    }
    now = int(time.time())
    payload = {
        "aud": "doordash",
        "iss": developer_id,
        "kid": key_id,
        "iat": now,
        "exp": now + 300,  # 5 minutes
    }

    segments = [
        _base64url_encode(json.dumps(header).encode()),
        _base64url_encode(json.dumps(payload).encode()),
    ]
    signing_input = ".".join(segments)

    # Decode the base64-encoded signing secret
    decoded_secret = base64.decodebytes(signing_secret.encode())

    signature = hmac.new(
        decoded_secret,
        signing_input.encode(),
        hashlib.sha256,
    ).digest()

    segments.append(_base64url_encode(signature))
    return ".".join(segments)


# ---------------------------------------------------------------------------
# Drive API provider
# ---------------------------------------------------------------------------

_DRIVE_API_BASE = "https://openapi.doordash.com"


class DoorDashDriveProvider(DoorDashProvider):
    """DoorDash Drive API v2 integration.

    Handles JWT creation, delivery CRUD, and status polling.
    Credentials are loaded from env vars if not passed directly.
    """

    def __init__(
        self,
        developer_id: str | None = None,
        key_id: str | None = None,
        signing_secret: str | None = None,
    ) -> None:
        self._developer_id = developer_id or os.getenv("DOORDASH_DEVELOPER_ID", "")
        self._key_id = key_id or os.getenv("DOORDASH_KEY_ID", "")
        self._signing_secret = signing_secret or os.getenv("DOORDASH_SIGNING_SECRET", "")
        self._authenticated = False
        self._token: str = ""
        self._token_created: float = 0

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    @property
    def has_credentials(self) -> bool:
        return bool(self._developer_id and self._key_id and self._signing_secret)

    def authenticate(self) -> bool:
        """Generate a JWT token for API access.

        Tokens are valid for 5 minutes. Call this before each API request
        or use _ensure_token() which refreshes automatically.
        """
        if not self.has_credentials:
            self._authenticated = False
            return False

        try:
            self._token = _create_doordash_jwt(
                self._developer_id,
                self._key_id,
                self._signing_secret,
            )
            self._token_created = time.time()
            self._authenticated = True
            return True
        except Exception:
            self._authenticated = False
            return False

    def _ensure_token(self) -> bool:
        """Refresh the JWT if it's expired or missing."""
        if not self._token or (time.time() - self._token_created) > 240:
            return self.authenticate()
        return self._authenticated

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Make an authenticated request to the Drive API."""
        if not self._ensure_token():
            return None

        url = f"{_DRIVE_API_BASE}{path}"
        data = json.dumps(body).encode() if body else None

        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            return {"error": True, "status": e.code, "detail": error_body}
        except urllib.error.URLError:
            return {"error": True, "detail": "Network error"}

    # ------------------------------------------------------------------
    # Delivery operations
    # ------------------------------------------------------------------

    def create_delivery(self, request: DeliveryRequest) -> DeliveryResponse | None:
        """Create a new delivery via POST /drive/v2/deliveries."""
        body = {
            "external_delivery_id": request.external_delivery_id,
            "pickup_address": request.pickup_address,
            "pickup_business_name": request.pickup_business_name,
            "pickup_phone_number": request.pickup_phone_number,
            "pickup_instructions": request.pickup_instructions,
            "dropoff_address": request.dropoff_address,
            "dropoff_business_name": request.dropoff_business_name,
            "dropoff_phone_number": request.dropoff_phone_number,
            "dropoff_instructions": request.dropoff_instructions,
            "order_value": request.order_value,
            "tip": request.tip,
        }

        result = self._request("POST", "/drive/v2/deliveries", body)
        if result is None or result.get("error"):
            return None

        return DeliveryResponse(
            external_delivery_id=result.get("external_delivery_id", request.external_delivery_id),
            delivery_status=result.get("delivery_status", "unknown"),
            tracking_url=result.get("tracking_url", ""),
            fee=result.get("fee", 0),
            pickup_time_estimated=result.get("pickup_time_estimated", ""),
            dropoff_time_estimated=result.get("dropoff_time_estimated", ""),
            dasher_name=result.get("dasher", {}).get("name", "") if isinstance(result.get("dasher"), dict) else "",
            dasher_phone=result.get("dasher", {}).get("phone_number", "") if isinstance(result.get("dasher"), dict) else "",
            raw=result,
        )

    def get_delivery_status(self, external_delivery_id: str) -> DeliveryResponse | None:
        """Get delivery status via GET /drive/v2/deliveries/{id}."""
        if not _SAFE_ID.match(external_delivery_id):
            return None
        result = self._request("GET", f"/drive/v2/deliveries/{external_delivery_id}")
        if result is None or result.get("error"):
            return None

        return DeliveryResponse(
            external_delivery_id=result.get("external_delivery_id", external_delivery_id),
            delivery_status=result.get("delivery_status", "unknown"),
            tracking_url=result.get("tracking_url", ""),
            fee=result.get("fee", 0),
            pickup_time_estimated=result.get("pickup_time_estimated", ""),
            dropoff_time_estimated=result.get("dropoff_time_estimated", ""),
            dasher_name=result.get("dasher", {}).get("name", "") if isinstance(result.get("dasher"), dict) else "",
            dasher_phone=result.get("dasher", {}).get("phone_number", "") if isinstance(result.get("dasher"), dict) else "",
            raw=result,
        )

    def cancel_delivery(self, external_delivery_id: str) -> bool:
        """Cancel a delivery via PUT /drive/v2/deliveries/{id}/cancel."""
        result = self._request("PUT", f"/drive/v2/deliveries/{external_delivery_id}/cancel")
        if result is None or result.get("error"):
            return False
        return True
