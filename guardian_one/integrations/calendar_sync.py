"""Calendar integration — stubs for Google Calendar and Epic scheduling.

These are interface definitions with placeholder implementations.
Connect real APIs by filling in the marked sections.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class CalendarEntry:
    title: str
    start: datetime
    end: datetime
    location: str = ""
    source: str = ""
    raw: dict[str, Any] | None = None


class CalendarProvider(abc.ABC):
    """Abstract interface for calendar data sources."""

    @abc.abstractmethod
    def authenticate(self) -> bool: ...

    @abc.abstractmethod
    def fetch_events(self, start: datetime, end: datetime) -> list[CalendarEntry]: ...

    @abc.abstractmethod
    def create_event(self, entry: CalendarEntry) -> str: ...


class GoogleCalendarProvider(CalendarProvider):
    """Google Calendar integration stub.

    To activate:
    1. Create a Google Cloud project with Calendar API enabled
    2. Download OAuth credentials to config/google_credentials.json
    3. Set GOOGLE_CALENDAR_CREDENTIALS env var
    """

    def __init__(self, credentials_path: str | None = None) -> None:
        self._credentials_path = credentials_path
        self._authenticated = False

    def authenticate(self) -> bool:
        # TODO: Implement OAuth2 flow with google-auth-oauthlib
        self._authenticated = False
        return self._authenticated

    def fetch_events(self, start: datetime, end: datetime) -> list[CalendarEntry]:
        if not self._authenticated:
            return []
        # TODO: Use googleapiclient.discovery to call Calendar API
        return []

    def create_event(self, entry: CalendarEntry) -> str:
        # TODO: Implement event creation via API
        return ""


class EpicScheduleProvider(CalendarProvider):
    """Epic hospital scheduling integration stub.

    To activate:
    1. Obtain FHIR API credentials from your Epic instance
    2. Set EPIC_FHIR_BASE_URL and EPIC_CLIENT_ID env vars
    """

    def __init__(self, base_url: str | None = None, client_id: str | None = None) -> None:
        self._base_url = base_url
        self._client_id = client_id
        self._authenticated = False

    def authenticate(self) -> bool:
        # TODO: Implement Epic FHIR SMART on FHIR auth
        self._authenticated = False
        return self._authenticated

    def fetch_events(self, start: datetime, end: datetime) -> list[CalendarEntry]:
        if not self._authenticated:
            return []
        # TODO: Query FHIR Schedule/Slot resources
        return []

    def create_event(self, entry: CalendarEntry) -> str:
        # TODO: Create appointment via FHIR API
        return ""
