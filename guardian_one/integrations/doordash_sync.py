"""DoorDash API integration stub.

Provides the interface for connecting to DoorDash's Drive API
(merchant/delivery) or scraping order status from the consumer app.

To activate:
1. Apply for DoorDash Drive API access at https://developer.doordash.com
2. Set DOORDASH_DEVELOPER_ID, DOORDASH_KEY_ID, DOORDASH_SIGNING_SECRET env vars
3. Or use session-based auth for consumer account access
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


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
    """Live order status from DoorDash."""
    order_id: str
    status: str
    driver_name: str | None = None
    driver_location: dict[str, float] | None = None  # lat/lng
    estimated_arrival: str | None = None
    raw: dict[str, Any] | None = None


class DoorDashProvider(abc.ABC):
    """Abstract interface for DoorDash data access."""

    @abc.abstractmethod
    def authenticate(self) -> bool: ...

    @abc.abstractmethod
    def search_restaurants(
        self, query: str, lat: float, lng: float
    ) -> list[DoorDashRestaurant]: ...

    @abc.abstractmethod
    def get_order_status(self, order_id: str) -> DoorDashOrderStatus | None: ...

    @abc.abstractmethod
    def get_order_history(self, limit: int = 20) -> list[dict[str, Any]]: ...


class DoorDashDriveProvider(DoorDashProvider):
    """DoorDash Drive API integration.

    Uses JWT-signed requests per the DoorDash developer docs.
    Set env vars:
        DOORDASH_DEVELOPER_ID
        DOORDASH_KEY_ID
        DOORDASH_SIGNING_SECRET
    """

    def __init__(
        self,
        developer_id: str | None = None,
        key_id: str | None = None,
        signing_secret: str | None = None,
    ) -> None:
        self._developer_id = developer_id
        self._key_id = key_id
        self._signing_secret = signing_secret
        self._authenticated = False

    def authenticate(self) -> bool:
        # TODO: Generate JWT with header {"alg": "HS256", "dd-ver": "DD-JWT-V1"}
        # and payload with developer_id. Sign with signing_secret.
        self._authenticated = bool(
            self._developer_id and self._key_id and self._signing_secret
        )
        return self._authenticated

    def search_restaurants(
        self, query: str, lat: float, lng: float
    ) -> list[DoorDashRestaurant]:
        if not self._authenticated:
            return []
        # TODO: POST to /drive/v2/deliveries or use search endpoint
        return []

    def get_order_status(self, order_id: str) -> DoorDashOrderStatus | None:
        if not self._authenticated:
            return None
        # TODO: GET /drive/v2/deliveries/{order_id}
        return None

    def get_order_history(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self._authenticated:
            return []
        # TODO: List recent deliveries
        return []
