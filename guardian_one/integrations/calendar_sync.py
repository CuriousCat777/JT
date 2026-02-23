"""Calendar integration — Google Calendar and Epic scheduling.

Providers auto-detect credentials from environment variables and report
their connection status.  When credentials are absent the providers
operate in offline mode (returning empty results, never crashing).

Google Calendar flow:
1. Place OAuth client-secret JSON at config/google_credentials.json
   (or set GOOGLE_CALENDAR_CREDENTIALS env var)
2. Run ``python main.py --calendar-auth`` to complete the OAuth consent
   flow — a browser window opens, you approve, and the refresh token is
   saved to config/google_token.json.
3. All subsequent calls use the saved token (no browser needed).
"""

from __future__ import annotations

import abc
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any


# ---------------------------------------------------------------------------
# Shared data model
# ---------------------------------------------------------------------------

@dataclass
class CalendarEntry:
    title: str
    start: datetime
    end: datetime
    location: str = ""
    source: str = ""
    event_id: str = ""
    calendar_id: str = "primary"
    description: str = ""
    raw: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------

class CalendarProvider(abc.ABC):
    """Abstract interface for calendar data sources."""

    @abc.abstractmethod
    def authenticate(self) -> bool: ...

    @abc.abstractmethod
    def fetch_events(self, start: datetime, end: datetime) -> list[CalendarEntry]: ...

    @abc.abstractmethod
    def create_event(self, entry: CalendarEntry) -> str: ...

    @abc.abstractmethod
    def update_event(self, entry: CalendarEntry) -> bool: ...

    @abc.abstractmethod
    def delete_event(self, event_id: str, calendar_id: str = "primary") -> bool: ...

    @property
    @abc.abstractmethod
    def has_credentials(self) -> bool: ...

    @property
    @abc.abstractmethod
    def provider_name(self) -> str: ...


# ---------------------------------------------------------------------------
# Google Calendar provider — real OAuth2 + Calendar API v3
# ---------------------------------------------------------------------------

# Google OAuth endpoints
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
_SCOPES = "https://www.googleapis.com/auth/calendar"


def _load_json(path: str) -> dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)


def _save_json(path: str, data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Tiny HTTP handler that captures the OAuth redirect code."""

    auth_code: str | None = None

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        _OAuthCallbackHandler.auth_code = code
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        if code:
            self.wfile.write(b"<h2>Authorization successful!</h2>"
                             b"<p>You can close this tab and return to the terminal.</p>")
        else:
            error = params.get("error", ["unknown"])[0]
            self.wfile.write(f"<h2>Authorization failed: {error}</h2>".encode())

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Suppress noisy HTTP logs


class GoogleCalendarProvider(CalendarProvider):
    """Google Calendar integration via OAuth2 + Calendar API v3.

    Credentials lookup order:
    1. ``credentials_path`` constructor arg
    2. ``GOOGLE_CALENDAR_CREDENTIALS`` env var
    3. ``config/google_credentials.json`` (default fallback)

    Token storage: ``config/google_token.json`` (auto-created after first auth).
    """

    DEFAULT_CRED_PATH = "config/google_credentials.json"
    DEFAULT_TOKEN_PATH = "config/google_token.json"
    REDIRECT_PORT = 8235

    def __init__(
        self,
        credentials_path: str | None = None,
        token_path: str | None = None,
    ) -> None:
        self._credentials_path = (
            credentials_path
            or os.environ.get("GOOGLE_CALENDAR_CREDENTIALS")
            or self.DEFAULT_CRED_PATH
        )
        self._token_path = (
            token_path
            or os.environ.get("GOOGLE_CALENDAR_TOKEN")
            or self.DEFAULT_TOKEN_PATH
        )
        self._authenticated = False
        self._last_error: str = ""
        self._access_token: str = ""
        self._refresh_token: str = ""
        self._token_expiry: datetime | None = None
        self._client_id: str = ""
        self._client_secret: str = ""

    @property
    def provider_name(self) -> str:
        return "google_calendar"

    @property
    def has_credentials(self) -> bool:
        return os.path.isfile(self._credentials_path)

    @property
    def has_token(self) -> bool:
        return os.path.isfile(self._token_path)

    @property
    def last_error(self) -> str:
        return self._last_error

    # ---- OAuth helpers ----

    def _load_client_secrets(self) -> bool:
        """Load client_id and client_secret from the credentials JSON."""
        try:
            data = _load_json(self._credentials_path)
            # Google credentials JSON has either "installed" or "web" key
            info = data.get("installed") or data.get("web") or {}
            self._client_id = info.get("client_id", "")
            self._client_secret = info.get("client_secret", "")
            return bool(self._client_id and self._client_secret)
        except Exception as exc:
            self._last_error = f"Failed to load client secrets: {exc}"
            return False

    def _load_saved_token(self) -> bool:
        """Load a previously-saved refresh token."""
        if not self.has_token:
            return False
        try:
            data = _load_json(self._token_path)
            self._refresh_token = data.get("refresh_token", "")
            self._access_token = data.get("access_token", "")
            expiry = data.get("expiry")
            if expiry:
                self._token_expiry = datetime.fromisoformat(expiry)
            return bool(self._refresh_token)
        except Exception:
            return False

    def _save_token(self) -> None:
        """Persist token data to disk."""
        _save_json(self._token_path, {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
            "expiry": self._token_expiry.isoformat() if self._token_expiry else "",
        })

    def _exchange_code(self, code: str) -> bool:
        """Exchange an authorization code for access + refresh tokens."""
        redirect_uri = f"http://localhost:{self.REDIRECT_PORT}"
        body = urllib.parse.urlencode({
            "code": code,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }).encode()
        req = urllib.request.Request(_GOOGLE_TOKEN_URL, data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            self._access_token = data["access_token"]
            self._refresh_token = data.get("refresh_token", self._refresh_token)
            expires_in = data.get("expires_in", 3600)
            self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            self._save_token()
            return True
        except Exception as exc:
            self._last_error = f"Token exchange failed: {exc}"
            return False

    def _refresh_access_token(self) -> bool:
        """Use the refresh token to get a new access token."""
        if not self._refresh_token:
            return False
        body = urllib.parse.urlencode({
            "refresh_token": self._refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "refresh_token",
        }).encode()
        req = urllib.request.Request(_GOOGLE_TOKEN_URL, data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            self._access_token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            self._save_token()
            return True
        except Exception as exc:
            self._last_error = f"Token refresh failed: {exc}"
            return False

    def _ensure_valid_token(self) -> bool:
        """Refresh the access token if it's expired or about to expire."""
        if not self._access_token:
            return self._refresh_access_token()
        if self._token_expiry and datetime.now(timezone.utc) >= self._token_expiry - timedelta(minutes=5):
            return self._refresh_access_token()
        return True

    def _api_request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Make an authenticated request to the Calendar API."""
        if not self._ensure_valid_token():
            return None
        url = f"{_CALENDAR_API}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._access_token}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            self._last_error = f"API {method} {path}: HTTP {exc.code}"
            return None
        except Exception as exc:
            self._last_error = f"API {method} {path}: {exc}"
            return None

    # ---- Public interface ----

    def start_oauth_flow(self) -> str:
        """Return the authorization URL for the user to visit."""
        if not self._load_client_secrets():
            return ""
        redirect_uri = f"http://localhost:{self.REDIRECT_PORT}"
        params = urllib.parse.urlencode({
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": _SCOPES,
            "access_type": "offline",
            "prompt": "consent",
        })
        return f"{_GOOGLE_AUTH_URL}?{params}"

    def complete_oauth_flow(self, open_browser: bool = True) -> bool:
        """Run the full OAuth consent flow (opens browser, starts local server).

        Returns True if authentication succeeds.
        """
        auth_url = self.start_oauth_flow()
        if not auth_url:
            return False

        print(f"\n  Opening browser for Google Calendar authorization...")
        print(f"  If the browser doesn't open, visit this URL:\n")
        print(f"  {auth_url}\n")

        if open_browser:
            try:
                import webbrowser
                webbrowser.open(auth_url)
            except Exception:
                pass  # User can copy the URL manually

        # Start a tiny HTTP server to catch the redirect
        _OAuthCallbackHandler.auth_code = None
        server = HTTPServer(("localhost", self.REDIRECT_PORT), _OAuthCallbackHandler)
        server.timeout = 120  # Wait up to 2 minutes
        server.handle_request()
        server.server_close()

        code = _OAuthCallbackHandler.auth_code
        if not code:
            self._last_error = "No authorization code received."
            return False

        if not self._exchange_code(code):
            return False

        self._authenticated = True
        self._last_error = ""
        return True

    def authenticate(self) -> bool:
        """Authenticate using saved token, or report that auth is needed."""
        if not self.has_credentials:
            self._last_error = (
                f"Credentials file not found: {self._credentials_path}. "
                "Download OAuth client JSON from Google Cloud Console "
                "and set GOOGLE_CALENDAR_CREDENTIALS env var."
            )
            self._authenticated = False
            return False

        if not self._load_client_secrets():
            self._authenticated = False
            return False

        # Try saved token first
        if self._load_saved_token():
            if self._ensure_valid_token():
                self._authenticated = True
                self._last_error = ""
                return True

        # No valid token — user needs to run --calendar-auth
        self._last_error = (
            "No saved token found. Run `python main.py --calendar-auth` "
            "to complete the Google Calendar authorization."
        )
        self._authenticated = False
        return False

    def fetch_events(
        self,
        start: datetime,
        end: datetime,
        calendar_id: str = "primary",
    ) -> list[CalendarEntry]:
        """Fetch events from Google Calendar in the given time range."""
        if not self._authenticated:
            return []
        params = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": "250",
        }
        result = self._api_request("GET", f"/calendars/{calendar_id}/events", params=params)
        if not result:
            return []
        entries: list[CalendarEntry] = []
        for item in result.get("items", []):
            s = item.get("start", {})
            e = item.get("end", {})
            start_str = s.get("dateTime") or s.get("date", "")
            end_str = e.get("dateTime") or e.get("date", "")
            try:
                start_dt = datetime.fromisoformat(start_str)
                end_dt = datetime.fromisoformat(end_str)
            except (ValueError, TypeError):
                continue
            entries.append(CalendarEntry(
                title=item.get("summary", "(no title)"),
                start=start_dt,
                end=end_dt,
                location=item.get("location", ""),
                source="google_calendar",
                event_id=item.get("id", ""),
                calendar_id=calendar_id,
                description=item.get("description", ""),
                raw=item,
            ))
        return entries

    def create_event(
        self,
        entry: CalendarEntry,
        calendar_id: str = "primary",
    ) -> str:
        """Create a new event. Returns the event ID or empty string on failure."""
        if not self._authenticated:
            return ""
        body: dict[str, Any] = {
            "summary": entry.title,
            "start": {"dateTime": entry.start.isoformat()},
            "end": {"dateTime": entry.end.isoformat()},
        }
        if entry.location:
            body["location"] = entry.location
        if entry.description:
            body["description"] = entry.description
        result = self._api_request("POST", f"/calendars/{calendar_id}/events", body=body)
        if result:
            return result.get("id", "")
        return ""

    def update_event(self, entry: CalendarEntry) -> bool:
        """Update an existing event by its event_id."""
        if not self._authenticated or not entry.event_id:
            return False
        cal = entry.calendar_id or "primary"
        body: dict[str, Any] = {
            "summary": entry.title,
            "start": {"dateTime": entry.start.isoformat()},
            "end": {"dateTime": entry.end.isoformat()},
        }
        if entry.location:
            body["location"] = entry.location
        if entry.description:
            body["description"] = entry.description
        result = self._api_request("PUT", f"/calendars/{cal}/events/{entry.event_id}", body=body)
        return result is not None

    def delete_event(self, event_id: str, calendar_id: str = "primary") -> bool:
        """Delete an event by ID."""
        if not self._authenticated or not event_id:
            return False
        result = self._api_request("DELETE", f"/calendars/{calendar_id}/events/{event_id}")
        return result is not None

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "has_credentials": self.has_credentials,
            "has_token": self.has_token,
            "authenticated": self._authenticated,
            "credentials_path": self._credentials_path,
            "token_path": self._token_path,
            "last_error": self._last_error,
        }


# ---------------------------------------------------------------------------
# CalendarSync — high-level sync engine
# ---------------------------------------------------------------------------

class CalendarSync:
    """Pulls events from Google Calendar and merges them into Chronos.

    Also pushes bill due dates from CFO → calendar as reminder events.
    """

    BILL_EVENT_PREFIX = "[Bill Due] "

    def __init__(
        self,
        provider: GoogleCalendarProvider | None = None,
        timezone_name: str = "America/Chicago",
    ) -> None:
        self._provider = provider or GoogleCalendarProvider()
        self._timezone_name = timezone_name
        self._synced_event_ids: set[str] = set()

    @property
    def provider(self) -> GoogleCalendarProvider:
        return self._provider

    @property
    def is_connected(self) -> bool:
        return self._provider._authenticated

    def connect(self) -> bool:
        """Authenticate the provider using saved tokens."""
        return self._provider.authenticate()

    def pull_events(
        self,
        days_ahead: int = 14,
        days_behind: int = 1,
    ) -> list[CalendarEntry]:
        """Fetch upcoming events from Google Calendar."""
        if not self.is_connected:
            return []
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days_behind)
        end = now + timedelta(days=days_ahead)
        events = self._provider.fetch_events(start, end)
        self._synced_event_ids = {e.event_id for e in events if e.event_id}
        return events

    def push_bill_to_calendar(
        self,
        bill_name: str,
        amount: float,
        due_date: str,
        auto_pay: bool = False,
    ) -> str:
        """Create a calendar event for a bill due date.

        Returns the Google Calendar event ID or empty string on failure.
        """
        if not self.is_connected:
            return ""
        try:
            due_dt = datetime.fromisoformat(due_date)
        except ValueError:
            return ""
        # Make it a 30-minute reminder event at 9 AM on the due date
        if due_dt.hour == 0 and due_dt.minute == 0:
            due_dt = due_dt.replace(hour=9, minute=0)
        end_dt = due_dt + timedelta(minutes=30)
        auto_tag = " (auto-pay)" if auto_pay else ""
        entry = CalendarEntry(
            title=f"{self.BILL_EVENT_PREFIX}{bill_name}",
            start=due_dt,
            end=end_dt,
            description=f"Bill: {bill_name}\nAmount: ${amount:,.2f}{auto_tag}\n\nCreated by Guardian One CFO",
            source="guardian_cfo",
        )
        return self._provider.create_event(entry)

    def sync_bills_to_calendar(
        self,
        bills: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Push all unpaid bills to Google Calendar.

        Args:
            bills: List of dicts with keys: name, amount, due_date, auto_pay, paid

        Returns summary of what was synced.
        """
        if not self.is_connected:
            return {"synced": 0, "skipped": 0, "error": "Not connected"}

        # First, fetch existing bill events to avoid duplicates
        now = datetime.now(timezone.utc)
        existing = self._provider.fetch_events(
            now - timedelta(days=7),
            now + timedelta(days=60),
        )
        existing_bill_titles = {
            e.title for e in existing
            if e.title.startswith(self.BILL_EVENT_PREFIX)
        }

        synced = 0
        skipped = 0
        for bill in bills:
            if bill.get("paid", False):
                skipped += 1
                continue
            title = f"{self.BILL_EVENT_PREFIX}{bill['name']}"
            if title in existing_bill_titles:
                skipped += 1
                continue
            event_id = self.push_bill_to_calendar(
                bill["name"],
                bill["amount"],
                bill["due_date"],
                bill.get("auto_pay", False),
            )
            if event_id:
                synced += 1
            else:
                skipped += 1

        return {"synced": synced, "skipped": skipped}

    def find_conflicts(self, events: list[CalendarEntry]) -> list[tuple[CalendarEntry, CalendarEntry]]:
        """Detect overlapping event pairs."""
        conflicts = []
        for i, a in enumerate(events):
            for b in events[i + 1:]:
                if a.start < b.end and b.start < a.end:
                    conflicts.append((a, b))
        return conflicts

    def today_schedule(self) -> list[CalendarEntry]:
        """Get today's events sorted by start time."""
        if not self.is_connected:
            return []
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        events = self._provider.fetch_events(start_of_day, end_of_day)
        return sorted(events, key=lambda e: e.start)

    def week_schedule(self) -> list[CalendarEntry]:
        """Get this week's events sorted by start time."""
        if not self.is_connected:
            return []
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_week = start_of_day + timedelta(days=7)
        events = self._provider.fetch_events(start_of_day, end_of_week)
        return sorted(events, key=lambda e: e.start)

    def status(self) -> dict[str, Any]:
        return {
            **self._provider.status(),
            "synced_events": len(self._synced_event_ids),
            "timezone": self._timezone_name,
        }


# ---------------------------------------------------------------------------
# Epic FHIR provider (stub — kept for future use)
# ---------------------------------------------------------------------------

class EpicScheduleProvider(CalendarProvider):
    """Epic hospital scheduling integration (FHIR R4).

    Credentials lookup:
    1. Constructor args
    2. ``EPIC_FHIR_BASE_URL`` and ``EPIC_CLIENT_ID`` env vars
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
        return []

    def create_event(self, entry: CalendarEntry) -> str:
        if not self._authenticated:
            return ""
        return ""

    def update_event(self, entry: CalendarEntry) -> bool:
        if not self._authenticated:
            return False
        return False

    def delete_event(self, event_id: str, calendar_id: str = "primary") -> bool:
        if not self._authenticated:
            return False
        return False

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "has_credentials": self.has_credentials,
            "authenticated": self._authenticated,
            "base_url": self._base_url or "(not set)",
            "last_error": self._last_error,
        }
