"""Calendar integration — Google Calendar and Epic scheduling.

Providers auto-detect credentials from environment variables and report
their connection status.  When credentials are absent the providers
operate in offline mode (returning empty results, never crashing).
"""

from __future__ import annotations

import abc
import os
from dataclasses import dataclass, field
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

    @property
    @abc.abstractmethod
    def has_credentials(self) -> bool: ...

    @property
    @abc.abstractmethod
    def provider_name(self) -> str: ...


class GoogleCalendarProvider(CalendarProvider):
    """Google Calendar integration.

    Credentials lookup order:
    1. ``credentials_path`` constructor arg
    2. ``GOOGLE_CALENDAR_CREDENTIALS`` env var
    3. ``config/google_credentials.json`` (default fallback)

    To activate:
    1. Create a Google Cloud project with Calendar API enabled
    2. Download OAuth credentials JSON
    3. Set GOOGLE_CALENDAR_CREDENTIALS env var to the file path
    """

    DEFAULT_CRED_PATH = "config/google_credentials.json"

    def __init__(self, credentials_path: str | None = None) -> None:
        self._credentials_path = (
            credentials_path
            or os.environ.get("GOOGLE_CALENDAR_CREDENTIALS")
            or self.DEFAULT_CRED_PATH
        )
        self._authenticated = False
        self._last_error: str = ""

    @property
    def provider_name(self) -> str:
        return "google_calendar"

    @property
    def has_credentials(self) -> bool:
        return os.path.isfile(self._credentials_path)

    @property
    def last_error(self) -> str:
        return self._last_error

    def authenticate(self) -> bool:
        if not self.has_credentials:
            self._last_error = (
                f"Credentials file not found: {self._credentials_path}. "
                "Set GOOGLE_CALENDAR_CREDENTIALS env var."
            )
            self._authenticated = False
            return False

        try:
            # Real implementation would use google-auth-oauthlib here.
            # For now, presence of credentials file = ready to connect.
            self._authenticated = False  # Will be True once OAuth is wired
            self._last_error = "OAuth flow not yet implemented — credentials detected but not activated"
            return self._authenticated
        except Exception as exc:
            self._last_error = f"Authentication failed: {exc}"
            self._authenticated = False
            return False

    def fetch_events(self, start: datetime, end: datetime) -> list[CalendarEntry]:
        if not self._authenticated:
            return []
        # Real implementation: googleapiclient.discovery → Calendar API v3
        return []

    def create_event(self, entry: CalendarEntry) -> str:
        if not self._authenticated:
            return ""
        # Real implementation: insert event via Calendar API
        return ""

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "has_credentials": self.has_credentials,
            "authenticated": self._authenticated,
            "credentials_path": self._credentials_path,
            "last_error": self._last_error,
        }


class EpicScheduleProvider(CalendarProvider):
    """Epic hospital scheduling integration (FHIR R4).

    Credentials lookup:
    1. Constructor args
    2. ``EPIC_FHIR_BASE_URL`` and ``EPIC_CLIENT_ID`` env vars

    To activate:
    1. Obtain FHIR API credentials from your Epic instance
    2. Set EPIC_FHIR_BASE_URL and EPIC_CLIENT_ID env vars
    """

    def __init__(
        self,
        base_url: str | None = None,
        client_id: str | None = None,
    ) -> None:
        self._base_url = base_url or os.environ.get("EPIC_FHIR_BASE_URL", "")
        self._client_id = client_id or os.environ.get("EPIC_CLIENT_ID", "")
        self._authenticated = False
        self._last_error: str = ""

    @property
    def provider_name(self) -> str:
        return "epic_fhir"

    @property
    def has_credentials(self) -> bool:
        return bool(self._base_url and self._client_id)

    @property
    def last_error(self) -> str:
        return self._last_error

    def authenticate(self) -> bool:
        if not self.has_credentials:
            self._last_error = (
                "Missing EPIC_FHIR_BASE_URL or EPIC_CLIENT_ID env vars."
            )
            self._authenticated = False
            return False

        try:
            self._authenticated = False
            self._last_error = "SMART on FHIR auth not yet implemented — credentials detected"
            return self._authenticated
        except Exception as exc:
            self._last_error = f"Epic authentication failed: {exc}"
            self._authenticated = False
            return False

    def fetch_events(self, start: datetime, end: datetime) -> list[CalendarEntry]:
        if not self._authenticated:
            return []
        # Real: FHIR /Schedule and /Slot resources
        return []

    def create_event(self, entry: CalendarEntry) -> str:
        if not self._authenticated:
            return ""
        # Real: FHIR Appointment resource
        return ""

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "has_credentials": self.has_credentials,
            "authenticated": self._authenticated,
            "base_url": self._base_url or "(not set)",
            "last_error": self._last_error,
        }
