"""Google Calendar sync API for Chronos."""

from datetime import datetime, timezone
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials

from chronos.auth import get_credentials

API_SERVICE_NAME = "calendar"
API_VERSION = "v3"


class CalendarSync:
    """Syncs events from Google Calendar."""

    def __init__(self, credentials: Optional[Credentials] = None):
        self._creds = credentials or get_credentials()
        self._service = build(
            API_SERVICE_NAME, API_VERSION, credentials=self._creds
        )

    def list_calendars(self) -> list[dict]:
        """List all calendars accessible by the authenticated user."""
        result = self._service.calendarList().list().execute()
        return result.get("items", [])

    def fetch_events(
        self,
        calendar_id: str = "primary",
        max_results: int = 50,
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
    ) -> list[dict]:
        """Fetch events from a Google Calendar.

        Args:
            calendar_id: Calendar ID to fetch from. Defaults to primary.
            max_results: Maximum number of events to return.
            time_min: Start of time range (inclusive). Defaults to now.
            time_max: End of time range (exclusive). Optional.

        Returns:
            List of event dicts from the Google Calendar API.
        """
        if time_min is None:
            time_min = datetime.now(timezone.utc)

        params = {
            "calendarId": calendar_id,
            "timeMin": time_min.isoformat(),
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }

        if time_max is not None:
            params["timeMax"] = time_max.isoformat()

        try:
            result = self._service.events().list(**params).execute()
            return result.get("items", [])
        except HttpError as e:
            raise SyncError(f"Failed to fetch events: {e}") from e

    def get_event(self, event_id: str, calendar_id: str = "primary") -> dict:
        """Fetch a single event by ID."""
        try:
            return (
                self._service.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute()
            )
        except HttpError as e:
            raise SyncError(f"Failed to get event {event_id}: {e}") from e

    def sync_incremental(
        self, calendar_id: str = "primary", sync_token: Optional[str] = None
    ) -> tuple[list[dict], str]:
        """Perform incremental sync using a sync token.

        On first call (no sync_token), does a full sync.
        Subsequent calls with the returned sync_token fetch only changes.

        Args:
            calendar_id: Calendar ID to sync.
            sync_token: Token from a previous sync call.

        Returns:
            Tuple of (events, next_sync_token).
        """
        all_events = []
        page_token = None

        try:
            while True:
                params = {
                    "calendarId": calendar_id,
                    "singleEvents": True,
                }

                if sync_token:
                    params["syncToken"] = sync_token
                else:
                    params["timeMin"] = datetime.now(timezone.utc).isoformat()

                if page_token:
                    params["pageToken"] = page_token

                result = self._service.events().list(**params).execute()
                all_events.extend(result.get("items", []))

                page_token = result.get("nextPageToken")
                if not page_token:
                    break

            next_sync_token = result.get("nextSyncToken", "")
            return all_events, next_sync_token

        except HttpError as e:
            if e.resp.status == 410:
                # Sync token expired — restart full sync
                return self.sync_incremental(calendar_id, sync_token=None)
            raise SyncError(f"Incremental sync failed: {e}") from e


class SyncError(Exception):
    """Raised when a calendar sync operation fails."""
