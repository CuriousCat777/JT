"""Tests for Google Calendar sync integration."""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from guardian_one.core.audit import AuditLog
from guardian_one.core.config import AgentConfig
from guardian_one.agents.chronos import CalendarEvent, Chronos
from guardian_one.integrations.calendar_sync import (
    CalendarEntry,
    CalendarSync,
    GoogleCalendarProvider,
    EpicScheduleProvider,
    _load_json,
    _save_json,
)


def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


# ---------------------------------------------------------------------------
# CalendarEntry dataclass
# ---------------------------------------------------------------------------

class TestCalendarEntry:
    def test_defaults(self):
        now = datetime.now(timezone.utc)
        entry = CalendarEntry(title="Test", start=now, end=now + timedelta(hours=1))
        assert entry.title == "Test"
        assert entry.location == ""
        assert entry.source == ""
        assert entry.event_id == ""
        assert entry.calendar_id == "primary"
        assert entry.description == ""
        assert entry.raw is None

    def test_all_fields(self):
        now = datetime.now(timezone.utc)
        entry = CalendarEntry(
            title="Meeting",
            start=now,
            end=now + timedelta(hours=1),
            location="Room 101",
            source="google_calendar",
            event_id="abc123",
            calendar_id="work",
            description="Weekly standup",
            raw={"id": "abc123"},
        )
        assert entry.location == "Room 101"
        assert entry.event_id == "abc123"
        assert entry.raw == {"id": "abc123"}


# ---------------------------------------------------------------------------
# GoogleCalendarProvider — credential & token handling
# ---------------------------------------------------------------------------

class TestGoogleCalendarProviderCredentials:
    def test_no_credentials_file(self, tmp_path):
        provider = GoogleCalendarProvider(
            credentials_path=str(tmp_path / "nonexistent.json"),
        )
        assert provider.has_credentials is False
        assert provider.provider_name == "google_calendar"

    def test_has_credentials_with_file(self, tmp_path):
        cred_file = tmp_path / "creds.json"
        cred_file.write_text('{"installed": {"client_id": "x", "client_secret": "y"}}')
        provider = GoogleCalendarProvider(credentials_path=str(cred_file))
        assert provider.has_credentials is True

    def test_no_token(self, tmp_path):
        provider = GoogleCalendarProvider(
            credentials_path=str(tmp_path / "creds.json"),
            token_path=str(tmp_path / "token.json"),
        )
        assert provider.has_token is False

    def test_has_token_with_file(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text('{"refresh_token": "rt", "access_token": "at"}')
        provider = GoogleCalendarProvider(
            credentials_path=str(tmp_path / "creds.json"),
            token_path=str(token_file),
        )
        assert provider.has_token is True

    def test_authenticate_no_credentials(self, tmp_path):
        provider = GoogleCalendarProvider(
            credentials_path=str(tmp_path / "nonexistent.json"),
        )
        assert provider.authenticate() is False
        assert "not found" in provider.last_error.lower()

    def test_authenticate_bad_json(self, tmp_path):
        cred_file = tmp_path / "creds.json"
        cred_file.write_text("not json")
        provider = GoogleCalendarProvider(credentials_path=str(cred_file))
        assert provider.authenticate() is False
        assert "Failed to load" in provider.last_error

    def test_authenticate_no_token(self, tmp_path):
        cred_file = tmp_path / "creds.json"
        cred_file.write_text('{"installed": {"client_id": "x", "client_secret": "y"}}')
        provider = GoogleCalendarProvider(
            credentials_path=str(cred_file),
            token_path=str(tmp_path / "token.json"),
        )
        assert provider.authenticate() is False
        assert "No saved token" in provider.last_error

    def test_load_client_secrets(self, tmp_path):
        cred_file = tmp_path / "creds.json"
        cred_file.write_text(json.dumps({
            "installed": {
                "client_id": "test_id",
                "client_secret": "test_secret",
            }
        }))
        provider = GoogleCalendarProvider(credentials_path=str(cred_file))
        assert provider._load_client_secrets() is True
        assert provider._client_id == "test_id"
        assert provider._client_secret == "test_secret"

    def test_load_client_secrets_web_format(self, tmp_path):
        cred_file = tmp_path / "creds.json"
        cred_file.write_text(json.dumps({
            "web": {
                "client_id": "web_id",
                "client_secret": "web_secret",
            }
        }))
        provider = GoogleCalendarProvider(credentials_path=str(cred_file))
        assert provider._load_client_secrets() is True
        assert provider._client_id == "web_id"

    def test_env_var_credentials_path(self, tmp_path):
        cred_file = tmp_path / "env_creds.json"
        cred_file.write_text('{"installed": {"client_id": "x", "client_secret": "y"}}')
        with patch.dict(os.environ, {"GOOGLE_CALENDAR_CREDENTIALS": str(cred_file)}):
            provider = GoogleCalendarProvider()
            assert provider.has_credentials is True

    def test_env_var_token_path(self, tmp_path):
        token_file = tmp_path / "env_token.json"
        token_file.write_text('{"refresh_token": "rt"}')
        with patch.dict(os.environ, {"GOOGLE_CALENDAR_TOKEN": str(token_file)}):
            provider = GoogleCalendarProvider(credentials_path=str(tmp_path / "c.json"))
            assert provider.has_token is True


# ---------------------------------------------------------------------------
# GoogleCalendarProvider — token management
# ---------------------------------------------------------------------------

class TestGoogleCalendarProviderTokens:
    def test_load_saved_token(self, tmp_path):
        token_file = tmp_path / "token.json"
        expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        token_file.write_text(json.dumps({
            "refresh_token": "rt_123",
            "access_token": "at_456",
            "expiry": expiry,
        }))
        provider = GoogleCalendarProvider(
            credentials_path=str(tmp_path / "c.json"),
            token_path=str(token_file),
        )
        assert provider._load_saved_token() is True
        assert provider._refresh_token == "rt_123"
        assert provider._access_token == "at_456"
        assert provider._token_expiry is not None

    def test_load_saved_token_no_expiry(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({
            "refresh_token": "rt_123",
            "access_token": "at_456",
        }))
        provider = GoogleCalendarProvider(
            credentials_path=str(tmp_path / "c.json"),
            token_path=str(token_file),
        )
        assert provider._load_saved_token() is True
        assert provider._token_expiry is None

    def test_save_token(self, tmp_path):
        token_path = str(tmp_path / "new_token.json")
        provider = GoogleCalendarProvider(
            credentials_path=str(tmp_path / "c.json"),
            token_path=token_path,
        )
        provider._access_token = "at_saved"
        provider._refresh_token = "rt_saved"
        provider._token_expiry = datetime(2026, 3, 1, tzinfo=timezone.utc)
        provider._save_token()

        data = json.loads(Path(token_path).read_text())
        assert data["access_token"] == "at_saved"
        assert data["refresh_token"] == "rt_saved"
        assert "2026-03-01" in data["expiry"]

    def test_ensure_valid_token_fresh(self, tmp_path):
        provider = GoogleCalendarProvider(
            credentials_path=str(tmp_path / "c.json"),
            token_path=str(tmp_path / "t.json"),
        )
        provider._access_token = "fresh"
        provider._token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        # No refresh needed
        assert provider._ensure_valid_token() is True

    def test_ensure_valid_token_expired(self, tmp_path):
        provider = GoogleCalendarProvider(
            credentials_path=str(tmp_path / "c.json"),
            token_path=str(tmp_path / "t.json"),
        )
        provider._access_token = "expired"
        provider._token_expiry = datetime.now(timezone.utc) - timedelta(hours=1)
        provider._refresh_token = ""
        # No refresh token → can't refresh
        assert provider._ensure_valid_token() is False

    def test_authenticate_with_valid_saved_token(self, tmp_path):
        cred_file = tmp_path / "creds.json"
        cred_file.write_text(json.dumps({
            "installed": {"client_id": "x", "client_secret": "y"}
        }))
        token_file = tmp_path / "token.json"
        expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        token_file.write_text(json.dumps({
            "refresh_token": "rt",
            "access_token": "at",
            "expiry": expiry,
        }))
        provider = GoogleCalendarProvider(
            credentials_path=str(cred_file),
            token_path=str(token_file),
        )
        assert provider.authenticate() is True
        assert provider._authenticated is True
        assert provider.last_error == ""


# ---------------------------------------------------------------------------
# GoogleCalendarProvider — API methods (mocked)
# ---------------------------------------------------------------------------

class TestGoogleCalendarProviderAPI:
    def _make_authenticated_provider(self, tmp_path):
        cred_file = tmp_path / "c.json"
        cred_file.write_text('{"installed": {"client_id": "x", "client_secret": "y"}}')
        provider = GoogleCalendarProvider(
            credentials_path=str(cred_file),
            token_path=str(tmp_path / "t.json"),
        )
        provider._authenticated = True
        provider._access_token = "test_token"
        provider._token_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        provider._client_id = "x"
        provider._client_secret = "y"
        return provider

    def test_fetch_events_not_authenticated(self, tmp_path):
        provider = GoogleCalendarProvider(
            credentials_path=str(tmp_path / "c.json"),
        )
        now = datetime.now(timezone.utc)
        events = provider.fetch_events(now, now + timedelta(days=1))
        assert events == []

    def test_fetch_events_parses_response(self, tmp_path):
        provider = self._make_authenticated_provider(tmp_path)
        now = datetime.now(timezone.utc)
        mock_response = {
            "items": [
                {
                    "id": "evt1",
                    "summary": "Team Standup",
                    "start": {"dateTime": now.isoformat()},
                    "end": {"dateTime": (now + timedelta(hours=1)).isoformat()},
                    "location": "Room A",
                    "description": "Daily sync",
                },
                {
                    "id": "evt2",
                    "summary": "Lunch",
                    "start": {"dateTime": (now + timedelta(hours=4)).isoformat()},
                    "end": {"dateTime": (now + timedelta(hours=5)).isoformat()},
                },
            ]
        }
        with patch.object(provider, "_api_request", return_value=mock_response):
            events = provider.fetch_events(now, now + timedelta(days=1))
        assert len(events) == 2
        assert events[0].title == "Team Standup"
        assert events[0].event_id == "evt1"
        assert events[0].location == "Room A"
        assert events[0].source == "google_calendar"
        assert events[1].title == "Lunch"

    def test_fetch_events_handles_date_only(self, tmp_path):
        provider = self._make_authenticated_provider(tmp_path)
        now = datetime.now(timezone.utc)
        mock_response = {
            "items": [
                {
                    "id": "all_day",
                    "summary": "Holiday",
                    "start": {"date": "2026-03-01"},
                    "end": {"date": "2026-03-02"},
                },
            ]
        }
        with patch.object(provider, "_api_request", return_value=mock_response):
            events = provider.fetch_events(now, now + timedelta(days=30))
        assert len(events) == 1
        assert events[0].title == "Holiday"

    def test_fetch_events_skips_bad_dates(self, tmp_path):
        provider = self._make_authenticated_provider(tmp_path)
        now = datetime.now(timezone.utc)
        mock_response = {
            "items": [
                {
                    "id": "bad",
                    "summary": "Bad Event",
                    "start": {},
                    "end": {},
                },
            ]
        }
        with patch.object(provider, "_api_request", return_value=mock_response):
            events = provider.fetch_events(now, now + timedelta(days=1))
        assert len(events) == 0

    def test_fetch_events_api_failure(self, tmp_path):
        provider = self._make_authenticated_provider(tmp_path)
        now = datetime.now(timezone.utc)
        with patch.object(provider, "_api_request", return_value=None):
            events = provider.fetch_events(now, now + timedelta(days=1))
        assert events == []

    def test_create_event_not_authenticated(self, tmp_path):
        provider = GoogleCalendarProvider(credentials_path=str(tmp_path / "c.json"))
        entry = CalendarEntry(
            title="Test",
            start=datetime.now(timezone.utc),
            end=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert provider.create_event(entry) == ""

    def test_create_event_success(self, tmp_path):
        provider = self._make_authenticated_provider(tmp_path)
        entry = CalendarEntry(
            title="New Event",
            start=datetime.now(timezone.utc),
            end=datetime.now(timezone.utc) + timedelta(hours=1),
            location="Office",
            description="Important meeting",
        )
        with patch.object(provider, "_api_request", return_value={"id": "new_evt_1"}):
            event_id = provider.create_event(entry)
        assert event_id == "new_evt_1"

    def test_create_event_failure(self, tmp_path):
        provider = self._make_authenticated_provider(tmp_path)
        entry = CalendarEntry(
            title="Fail",
            start=datetime.now(timezone.utc),
            end=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        with patch.object(provider, "_api_request", return_value=None):
            event_id = provider.create_event(entry)
        assert event_id == ""

    def test_update_event_success(self, tmp_path):
        provider = self._make_authenticated_provider(tmp_path)
        entry = CalendarEntry(
            title="Updated",
            start=datetime.now(timezone.utc),
            end=datetime.now(timezone.utc) + timedelta(hours=1),
            event_id="evt1",
            calendar_id="primary",
        )
        with patch.object(provider, "_api_request", return_value={"id": "evt1"}):
            assert provider.update_event(entry) is True

    def test_update_event_no_id(self, tmp_path):
        provider = self._make_authenticated_provider(tmp_path)
        entry = CalendarEntry(
            title="No ID",
            start=datetime.now(timezone.utc),
            end=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert provider.update_event(entry) is False

    def test_delete_event_success(self, tmp_path):
        provider = self._make_authenticated_provider(tmp_path)
        with patch.object(provider, "_api_request", return_value={}):
            assert provider.delete_event("evt1") is True

    def test_delete_event_empty_id(self, tmp_path):
        provider = self._make_authenticated_provider(tmp_path)
        assert provider.delete_event("") is False

    def test_delete_event_not_authenticated(self, tmp_path):
        provider = GoogleCalendarProvider(credentials_path=str(tmp_path / "c.json"))
        assert provider.delete_event("evt1") is False

    def test_status(self, tmp_path):
        provider = self._make_authenticated_provider(tmp_path)
        status = provider.status()
        assert status["provider"] == "google_calendar"
        assert status["authenticated"] is True
        assert "credentials_path" in status
        assert "token_path" in status

    def test_start_oauth_flow_no_creds(self, tmp_path):
        provider = GoogleCalendarProvider(
            credentials_path=str(tmp_path / "nonexistent.json"),
        )
        assert provider.start_oauth_flow() == ""

    def test_start_oauth_flow_returns_url(self, tmp_path):
        cred_file = tmp_path / "creds.json"
        cred_file.write_text(json.dumps({
            "installed": {"client_id": "my_id", "client_secret": "my_secret"}
        }))
        provider = GoogleCalendarProvider(credentials_path=str(cred_file))
        url = provider.start_oauth_flow()
        assert "accounts.google.com" in url
        assert "my_id" in url
        assert "calendar" in url


# ---------------------------------------------------------------------------
# CalendarSync — high-level engine
# ---------------------------------------------------------------------------

class TestCalendarSync:
    def _make_sync(self, authenticated=False):
        provider = MagicMock(spec=GoogleCalendarProvider)
        provider._authenticated = authenticated
        provider.last_error = "" if authenticated else "Not connected"
        sync = CalendarSync(provider=provider)
        return sync, provider

    def test_is_connected(self):
        sync, provider = self._make_sync(authenticated=True)
        assert sync.is_connected is True

    def test_not_connected(self):
        sync, provider = self._make_sync(authenticated=False)
        assert sync.is_connected is False

    def test_connect_delegates(self):
        sync, provider = self._make_sync()
        provider.authenticate.return_value = True
        assert sync.connect() is True
        provider.authenticate.assert_called_once()

    def test_pull_events_not_connected(self):
        sync, _ = self._make_sync(authenticated=False)
        assert sync.pull_events() == []

    def test_pull_events_success(self):
        sync, provider = self._make_sync(authenticated=True)
        now = datetime.now(timezone.utc)
        events = [
            CalendarEntry(title="A", start=now, end=now + timedelta(hours=1), event_id="e1"),
            CalendarEntry(title="B", start=now + timedelta(hours=2), end=now + timedelta(hours=3), event_id="e2"),
        ]
        provider.fetch_events.return_value = events
        result = sync.pull_events()
        assert len(result) == 2
        assert sync._synced_event_ids == {"e1", "e2"}

    def test_push_bill_to_calendar_not_connected(self):
        sync, _ = self._make_sync(authenticated=False)
        assert sync.push_bill_to_calendar("Rent", 1500, "2026-03-01") == ""

    def test_push_bill_to_calendar_bad_date(self):
        sync, _ = self._make_sync(authenticated=True)
        assert sync.push_bill_to_calendar("Rent", 1500, "bad-date") == ""

    def test_push_bill_to_calendar_success(self):
        sync, provider = self._make_sync(authenticated=True)
        provider.create_event.return_value = "bill_evt_1"
        result = sync.push_bill_to_calendar("Rent", 1500.00, "2026-03-01")
        assert result == "bill_evt_1"
        # Verify the event was created with correct title
        call_args = provider.create_event.call_args
        entry = call_args[0][0]
        assert entry.title == "[Bill Due] Rent"
        assert "$1,500.00" in entry.description
        assert entry.start.hour == 9  # Default time for midnight dates

    def test_push_bill_with_auto_pay(self):
        sync, provider = self._make_sync(authenticated=True)
        provider.create_event.return_value = "bill_evt_2"
        sync.push_bill_to_calendar("Insurance", 200, "2026-03-15", auto_pay=True)
        call_args = provider.create_event.call_args
        entry = call_args[0][0]
        assert "(auto-pay)" in entry.description

    def test_sync_bills_not_connected(self):
        sync, _ = self._make_sync(authenticated=False)
        result = sync.sync_bills_to_calendar([{"name": "Rent", "amount": 1500, "due_date": "2026-03-01"}])
        assert result["error"] == "Not connected"

    def test_sync_bills_skips_paid(self):
        sync, provider = self._make_sync(authenticated=True)
        provider.fetch_events.return_value = []  # No existing events
        provider.create_event.return_value = "new_id"
        bills = [
            {"name": "Rent", "amount": 1500, "due_date": "2026-03-01", "paid": True},
            {"name": "Electric", "amount": 80, "due_date": "2026-03-05", "paid": False},
        ]
        result = sync.sync_bills_to_calendar(bills)
        assert result["synced"] == 1
        assert result["skipped"] == 1

    def test_sync_bills_avoids_duplicates(self):
        sync, provider = self._make_sync(authenticated=True)
        now = datetime.now(timezone.utc)
        provider.fetch_events.return_value = [
            CalendarEntry(title="[Bill Due] Rent", start=now, end=now + timedelta(hours=1)),
        ]
        provider.create_event.return_value = "new_id"
        bills = [
            {"name": "Rent", "amount": 1500, "due_date": "2026-03-01", "paid": False},
            {"name": "Electric", "amount": 80, "due_date": "2026-03-05", "paid": False},
        ]
        result = sync.sync_bills_to_calendar(bills)
        assert result["synced"] == 1  # Only Electric
        assert result["skipped"] == 1  # Rent already exists

    def test_find_conflicts_none(self):
        sync, _ = self._make_sync()
        now = datetime.now(timezone.utc)
        events = [
            CalendarEntry(title="A", start=now, end=now + timedelta(hours=1)),
            CalendarEntry(title="B", start=now + timedelta(hours=2), end=now + timedelta(hours=3)),
        ]
        assert sync.find_conflicts(events) == []

    def test_find_conflicts_overlap(self):
        sync, _ = self._make_sync()
        now = datetime.now(timezone.utc)
        events = [
            CalendarEntry(title="A", start=now, end=now + timedelta(hours=2)),
            CalendarEntry(title="B", start=now + timedelta(hours=1), end=now + timedelta(hours=3)),
        ]
        conflicts = sync.find_conflicts(events)
        assert len(conflicts) == 1
        assert conflicts[0][0].title == "A"
        assert conflicts[0][1].title == "B"

    def test_today_schedule_not_connected(self):
        sync, _ = self._make_sync(authenticated=False)
        assert sync.today_schedule() == []

    def test_week_schedule_not_connected(self):
        sync, _ = self._make_sync(authenticated=False)
        assert sync.week_schedule() == []

    def test_today_schedule_connected(self):
        sync, provider = self._make_sync(authenticated=True)
        now = datetime.now(timezone.utc)
        provider.fetch_events.return_value = [
            CalendarEntry(title="Meeting", start=now, end=now + timedelta(hours=1)),
        ]
        result = sync.today_schedule()
        assert len(result) == 1
        assert result[0].title == "Meeting"

    def test_status(self):
        sync, provider = self._make_sync(authenticated=True)
        provider.status.return_value = {
            "provider": "google_calendar",
            "authenticated": True,
        }
        status = sync.status()
        assert status["provider"] == "google_calendar"
        assert status["synced_events"] == 0
        assert status["timezone"] == "America/Chicago"


# ---------------------------------------------------------------------------
# Chronos agent — calendar sync integration
# ---------------------------------------------------------------------------

class TestChronosCalendarSync:
    def test_chronos_initializes_calendar_sync(self):
        """Chronos should try to init CalendarSync (will be offline without creds)."""
        agent = Chronos(AgentConfig(name="chronos"), _make_audit())
        agent.initialize()
        assert agent._calendar_sync is not None
        assert agent._calendar_sync.is_connected is False

    def test_calendar_status_offline(self):
        agent = Chronos(AgentConfig(name="chronos"), _make_audit())
        agent.initialize()
        status = agent.calendar_status()
        assert status.get("authenticated") is False or status.get("connected") is False

    def test_sync_google_calendar_not_connected(self):
        agent = Chronos(AgentConfig(name="chronos"), _make_audit())
        agent.initialize()
        result = agent.sync_google_calendar()
        assert result["synced"] is False
        assert "not connected" in result["reason"].lower()

    def test_sync_google_calendar_with_mock(self):
        agent = Chronos(AgentConfig(name="chronos"), _make_audit())
        agent.initialize()
        # Mock the calendar sync
        mock_sync = MagicMock(spec=CalendarSync)
        mock_sync.is_connected = True
        now = datetime.now(timezone.utc)
        mock_sync.pull_events.return_value = [
            CalendarEntry(
                title="Standup",
                start=now + timedelta(hours=1),
                end=now + timedelta(hours=2),
                event_id="e1",
                calendar_id="primary",
            ),
            CalendarEntry(
                title="Lunch",
                start=now + timedelta(hours=4),
                end=now + timedelta(hours=5),
                event_id="e2",
                calendar_id="primary",
            ),
        ]
        agent._calendar_sync = mock_sync

        result = agent.sync_google_calendar()
        assert result["synced"] is True
        assert result["events_pulled"] == 2
        assert result["new_added"] == 2
        # Events should be in Chronos internal list (3 default routines + 2 new)
        google_events = [e for e in agent._events if e.source == "google"]
        assert len(google_events) == 2

    def test_sync_google_calendar_deduplicates(self):
        agent = Chronos(AgentConfig(name="chronos"), _make_audit())
        agent.initialize()
        mock_sync = MagicMock(spec=CalendarSync)
        mock_sync.is_connected = True
        now = datetime.now(timezone.utc)
        event = CalendarEntry(
            title="Standup",
            start=now + timedelta(hours=1),
            end=now + timedelta(hours=2),
            event_id="e1",
            calendar_id="primary",
        )
        mock_sync.pull_events.return_value = [event]
        agent._calendar_sync = mock_sync

        # First sync
        result1 = agent.sync_google_calendar()
        assert result1["new_added"] == 1

        # Second sync — same event should not be added again
        result2 = agent.sync_google_calendar()
        assert result2["new_added"] == 0
        google_events = [e for e in agent._events if e.source == "google"]
        assert len(google_events) == 1

    def test_sync_bills_to_calendar_not_connected(self):
        agent = Chronos(AgentConfig(name="chronos"), _make_audit())
        agent.initialize()
        result = agent.sync_bills_to_calendar([{"name": "Rent", "amount": 1500, "due_date": "2026-03-01"}])
        assert "error" in result

    def test_sync_bills_to_calendar_delegates(self):
        agent = Chronos(AgentConfig(name="chronos"), _make_audit())
        agent.initialize()
        mock_sync = MagicMock(spec=CalendarSync)
        mock_sync.is_connected = True
        mock_sync.sync_bills_to_calendar.return_value = {"synced": 2, "skipped": 1}
        agent._calendar_sync = mock_sync

        bills = [
            {"name": "Rent", "amount": 1500, "due_date": "2026-03-01"},
            {"name": "Electric", "amount": 80, "due_date": "2026-03-05"},
        ]
        result = agent.sync_bills_to_calendar(bills)
        assert result["synced"] == 2
        mock_sync.sync_bills_to_calendar.assert_called_once_with(bills)

    def test_today_schedule_offline_fallback(self):
        agent = Chronos(AgentConfig(name="chronos"), _make_audit())
        agent.initialize()
        now = datetime.now(timezone.utc)
        agent.add_event(CalendarEvent(
            title="Local Event",
            start=now,
            end=now + timedelta(hours=1),
        ))
        result = agent.today_schedule()
        assert len(result) == 1
        assert result[0]["title"] == "Local Event"

    def test_week_schedule_offline_fallback(self):
        agent = Chronos(AgentConfig(name="chronos"), _make_audit())
        agent.initialize()
        now = datetime.now(timezone.utc)
        agent.add_event(CalendarEvent(
            title="This Week",
            start=now + timedelta(days=1),
            end=now + timedelta(days=1, hours=1),
        ))
        result = agent.week_schedule()
        assert len(result) == 1
        assert result[0]["title"] == "This Week"

    def test_run_includes_calendar_status(self):
        agent = Chronos(AgentConfig(name="chronos"), _make_audit())
        agent.initialize()
        report = agent.run()
        assert "calendar_connected" in report.data
        assert report.data["calendar_connected"] is False

    def test_report_includes_calendar_info(self):
        agent = Chronos(AgentConfig(name="chronos"), _make_audit())
        agent.initialize()
        report = agent.report()
        assert "calendar_connected" in report.data
        assert "last_sync" in report.data


# ---------------------------------------------------------------------------
# EpicScheduleProvider (stub tests)
# ---------------------------------------------------------------------------

class TestEpicScheduleProvider:
    def test_no_credentials(self):
        provider = EpicScheduleProvider()
        assert provider.has_credentials is False
        assert provider.provider_name == "epic_fhir"

    def test_with_credentials(self):
        provider = EpicScheduleProvider(base_url="https://epic.test", client_id="cid")
        assert provider.has_credentials is True

    def test_authenticate_no_creds(self):
        provider = EpicScheduleProvider()
        assert provider.authenticate() is False

    def test_authenticate_stub(self):
        provider = EpicScheduleProvider(base_url="https://epic.test", client_id="cid")
        assert provider.authenticate() is False  # Stub — not yet implemented

    def test_fetch_events_unauthenticated(self):
        provider = EpicScheduleProvider()
        now = datetime.now(timezone.utc)
        assert provider.fetch_events(now, now + timedelta(days=1)) == []

    def test_create_event_unauthenticated(self):
        provider = EpicScheduleProvider()
        entry = CalendarEntry(title="Test", start=datetime.now(timezone.utc), end=datetime.now(timezone.utc))
        assert provider.create_event(entry) == ""

    def test_update_event_unauthenticated(self):
        provider = EpicScheduleProvider()
        entry = CalendarEntry(title="Test", start=datetime.now(timezone.utc), end=datetime.now(timezone.utc))
        assert provider.update_event(entry) is False

    def test_delete_event_unauthenticated(self):
        provider = EpicScheduleProvider()
        assert provider.delete_event("id") is False

    def test_status(self):
        provider = EpicScheduleProvider(base_url="https://epic.test", client_id="cid")
        status = provider.status()
        assert status["provider"] == "epic_fhir"
        assert status["has_credentials"] is True
        assert status["authenticated"] is False

    def test_env_vars(self):
        with patch.dict(os.environ, {
            "EPIC_FHIR_BASE_URL": "https://env.epic",
            "EPIC_CLIENT_ID": "env_cid",
        }):
            provider = EpicScheduleProvider()
            assert provider.has_credentials is True


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

class TestUtilityFunctions:
    def test_load_json(self, tmp_path):
        f = tmp_path / "test.json"
        f.write_text('{"key": "value"}')
        assert _load_json(str(f)) == {"key": "value"}

    def test_save_json(self, tmp_path):
        path = str(tmp_path / "out.json")
        _save_json(path, {"hello": "world"})
        assert json.loads(Path(path).read_text()) == {"hello": "world"}

    def test_save_json_creates_dirs(self, tmp_path):
        path = str(tmp_path / "sub" / "dir" / "out.json")
        _save_json(path, {"nested": True})
        assert json.loads(Path(path).read_text()) == {"nested": True}
