"""Tests for the Zapier calendar integration."""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from guardian_one.integrations.zapier_sync import (
    ZapierCalendarProvider,
    _load_cache,
    _save_cache,
)
from guardian_one.integrations.calendar_sync import CalendarEntry, CalendarSync
from guardian_one.core.audit import AuditLog
from guardian_one.core.config import AgentConfig
from guardian_one.agents.chronos import Chronos


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_cache(tmp_path):
    """Return a path to a temporary cache file."""
    return str(tmp_path / "test_calendar_cache.json")


@pytest.fixture
def provider(tmp_cache):
    """ZapierCalendarProvider with no webhooks, cache-only mode."""
    return ZapierCalendarProvider(cache_path=tmp_cache)


@pytest.fixture
def sample_events():
    """A list of sample event dicts for the cache."""
    now = datetime.now(timezone.utc)
    return [
        {
            "title": "Team Standup",
            "start": now.isoformat(),
            "end": (now + timedelta(minutes=30)).isoformat(),
            "location": "Zoom",
            "event_id": "evt-001",
            "calendar_id": "primary",
            "description": "Daily standup",
        },
        {
            "title": "Lunch",
            "start": (now + timedelta(hours=3)).isoformat(),
            "end": (now + timedelta(hours=4)).isoformat(),
            "location": "",
            "event_id": "evt-002",
            "calendar_id": "primary",
            "description": "",
        },
        {
            "title": "Past Meeting",
            "start": (now - timedelta(days=2)).isoformat(),
            "end": (now - timedelta(days=2) + timedelta(hours=1)).isoformat(),
            "location": "Office",
            "event_id": "evt-003",
            "calendar_id": "primary",
            "description": "Already happened",
        },
    ]


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

class TestCacheHelpers:
    def test_load_empty_cache(self, tmp_cache):
        assert _load_cache(tmp_cache) == []

    def test_save_and_load(self, tmp_cache):
        events = [{"title": "Test", "start": "2026-01-01T09:00:00+00:00"}]
        _save_cache(tmp_cache, events)
        loaded = _load_cache(tmp_cache)
        assert len(loaded) == 1
        assert loaded[0]["title"] == "Test"

    def test_load_corrupt_json(self, tmp_cache):
        with open(tmp_cache, "w") as f:
            f.write("not json")
        assert _load_cache(tmp_cache) == []

    def test_load_non_list_json(self, tmp_cache):
        with open(tmp_cache, "w") as f:
            json.dump({"foo": "bar"}, f)
        assert _load_cache(tmp_cache) == []

    def test_save_creates_parent_dirs(self, tmp_path):
        nested = str(tmp_path / "deep" / "nested" / "cache.json")
        _save_cache(nested, [{"title": "Test"}])
        assert _load_cache(nested) == [{"title": "Test"}]


# ---------------------------------------------------------------------------
# Provider basics
# ---------------------------------------------------------------------------

class TestProviderBasics:
    def test_provider_name(self, provider):
        assert provider.provider_name == "zapier_calendar"

    def test_no_credentials_by_default(self, tmp_cache):
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        assert not p.has_credentials

    def test_has_credentials_with_webhook(self, tmp_cache):
        p = ZapierCalendarProvider(
            webhook_in="https://hooks.zapier.com/test",
            cache_path=tmp_cache,
        )
        assert p.has_credentials

    def test_has_credentials_with_cache_file(self, tmp_cache):
        _save_cache(tmp_cache, [])
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        assert p.has_credentials

    def test_authenticate_no_creds(self, provider):
        assert not provider.authenticate()
        assert "No Zapier" in provider.last_error

    def test_authenticate_with_webhook(self, tmp_cache):
        p = ZapierCalendarProvider(
            webhook_in="https://hooks.zapier.com/test",
            cache_path=tmp_cache,
        )
        assert p.authenticate()
        assert p._authenticated
        assert p.last_error == ""

    def test_authenticate_invalid_url(self, tmp_cache):
        p = ZapierCalendarProvider(
            webhook_in="not-a-url",
            cache_path=tmp_cache,
        )
        assert not p.authenticate()
        assert "Invalid" in p.last_error

    def test_authenticate_with_cache_only(self, tmp_cache):
        _save_cache(tmp_cache, [])
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        assert p.authenticate()

    def test_has_webhook_in(self, tmp_cache):
        p = ZapierCalendarProvider(webhook_in="https://hooks.zapier.com/x", cache_path=tmp_cache)
        assert p.has_webhook_in
        assert not p.has_webhook_out

    def test_has_webhook_out(self, tmp_cache):
        p = ZapierCalendarProvider(webhook_out="https://hooks.zapier.com/y", cache_path=tmp_cache)
        assert not p.has_webhook_in
        assert p.has_webhook_out

    def test_env_vars_loaded(self, tmp_cache):
        with patch.dict(os.environ, {
            "ZAPIER_WEBHOOK_CALENDAR_IN": "https://hooks.zapier.com/env-in",
            "ZAPIER_WEBHOOK_CALENDAR_OUT": "https://hooks.zapier.com/env-out",
        }):
            p = ZapierCalendarProvider(cache_path=tmp_cache)
            assert p._webhook_in == "https://hooks.zapier.com/env-in"
            assert p._webhook_out == "https://hooks.zapier.com/env-out"


# ---------------------------------------------------------------------------
# Fetch events
# ---------------------------------------------------------------------------

class TestFetchEvents:
    def test_fetch_not_authenticated(self, provider):
        now = datetime.now(timezone.utc)
        assert provider.fetch_events(now, now + timedelta(days=1)) == []

    def test_fetch_from_cache(self, tmp_cache, sample_events):
        _save_cache(tmp_cache, sample_events)
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        p.authenticate()

        now = datetime.now(timezone.utc)
        events = p.fetch_events(now - timedelta(hours=1), now + timedelta(days=1))
        # Should get the two future/current events, not the past one
        titles = [e.title for e in events]
        assert "Team Standup" in titles
        assert "Lunch" in titles
        assert "Past Meeting" not in titles

    def test_fetch_all_events(self, tmp_cache, sample_events):
        _save_cache(tmp_cache, sample_events)
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        p.authenticate()

        now = datetime.now(timezone.utc)
        events = p.fetch_events(now - timedelta(days=5), now + timedelta(days=5))
        assert len(events) == 3

    def test_fetch_sorted_by_start(self, tmp_cache, sample_events):
        _save_cache(tmp_cache, sample_events)
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        p.authenticate()

        now = datetime.now(timezone.utc)
        events = p.fetch_events(now - timedelta(days=5), now + timedelta(days=5))
        starts = [e.start for e in events]
        assert starts == sorted(starts)

    def test_fetch_empty_cache(self, tmp_cache):
        _save_cache(tmp_cache, [])
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        p.authenticate()
        now = datetime.now(timezone.utc)
        assert p.fetch_events(now, now + timedelta(days=1)) == []

    def test_fetch_skips_malformed_events(self, tmp_cache):
        _save_cache(tmp_cache, [
            {"title": "Good", "start": datetime.now(timezone.utc).isoformat(),
             "end": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()},
            {"title": "Bad", "start": "not-a-date", "end": "also-not"},
            {"title": "Missing"},
        ])
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        p.authenticate()
        now = datetime.now(timezone.utc)
        events = p.fetch_events(now - timedelta(hours=1), now + timedelta(days=1))
        assert len(events) == 1
        assert events[0].title == "Good"

    def test_fetch_handles_naive_datetimes(self, tmp_cache):
        naive_start = datetime(2026, 3, 23, 12, 0, 0)
        _save_cache(tmp_cache, [{
            "title": "Naive Event",
            "start": naive_start.isoformat(),
            "end": (naive_start + timedelta(hours=1)).isoformat(),
        }])
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        p.authenticate()
        events = p.fetch_events(
            datetime(2026, 3, 23, tzinfo=timezone.utc),
            datetime(2026, 3, 24, tzinfo=timezone.utc),
        )
        assert len(events) == 1

    def test_entry_fields_populated(self, tmp_cache, sample_events):
        _save_cache(tmp_cache, sample_events)
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        p.authenticate()
        now = datetime.now(timezone.utc)
        events = p.fetch_events(now - timedelta(days=5), now + timedelta(days=5))
        standup = [e for e in events if e.title == "Team Standup"][0]
        assert standup.source == "zapier_calendar"
        assert standup.location == "Zoom"
        assert standup.event_id == "evt-001"
        assert standup.description == "Daily standup"


# ---------------------------------------------------------------------------
# Create events
# ---------------------------------------------------------------------------

class TestCreateEvent:
    def test_create_not_authenticated(self, provider):
        entry = CalendarEntry(
            title="Test", start=datetime.now(timezone.utc),
            end=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert provider.create_event(entry) == ""

    def test_create_cache_only(self, tmp_cache):
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        _save_cache(tmp_cache, [])  # Create cache so has_credentials = True
        p.authenticate()

        entry = CalendarEntry(
            title="New Event",
            start=datetime.now(timezone.utc),
            end=datetime.now(timezone.utc) + timedelta(hours=1),
            location="Home",
        )
        event_id = p.create_event(entry)
        assert event_id
        assert "New Event" in event_id

        # Verify it's in cache
        cached = _load_cache(tmp_cache)
        assert len(cached) == 1
        assert cached[0]["title"] == "New Event"
        assert cached[0]["location"] == "Home"
        assert "created_at" in cached[0]

    def test_create_via_webhook_success(self, tmp_cache):
        p = ZapierCalendarProvider(
            webhook_in="https://hooks.zapier.com/test",
            cache_path=tmp_cache,
        )
        p.authenticate()

        entry = CalendarEntry(
            title="Webhook Event",
            start=datetime.now(timezone.utc),
            end=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"id": "gcal-123"}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            event_id = p.create_event(entry)
        assert event_id == "gcal-123"

        # Also cached locally
        cached = _load_cache(tmp_cache)
        assert len(cached) == 1

    def test_create_webhook_failure_falls_back_to_cache(self, tmp_cache):
        p = ZapierCalendarProvider(
            webhook_in="https://hooks.zapier.com/test",
            cache_path=tmp_cache,
        )
        p.authenticate()

        entry = CalendarEntry(
            title="Fallback Event",
            start=datetime.now(timezone.utc),
            end=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            event_id = p.create_event(entry)
        assert event_id  # Should still get a local ID
        assert "Fallback Event" in event_id

        cached = _load_cache(tmp_cache)
        assert len(cached) == 1


# ---------------------------------------------------------------------------
# Update & Delete
# ---------------------------------------------------------------------------

class TestUpdateDelete:
    def test_update_event_in_cache(self, tmp_cache, sample_events):
        _save_cache(tmp_cache, sample_events)
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        p.authenticate()

        updated_entry = CalendarEntry(
            title="Team Standup (Updated)",
            start=datetime.now(timezone.utc),
            end=datetime.now(timezone.utc) + timedelta(minutes=45),
            event_id="evt-001",
        )
        assert p.update_event(updated_entry)

        cached = _load_cache(tmp_cache)
        evt = [e for e in cached if e["event_id"] == "evt-001"][0]
        assert evt["title"] == "Team Standup (Updated)"
        assert "updated_at" in evt

    def test_update_nonexistent_event(self, tmp_cache):
        _save_cache(tmp_cache, [])
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        p.authenticate()

        entry = CalendarEntry(
            title="Ghost", start=datetime.now(timezone.utc),
            end=datetime.now(timezone.utc) + timedelta(hours=1),
            event_id="nonexistent",
        )
        assert not p.update_event(entry)

    def test_update_no_event_id(self, tmp_cache):
        _save_cache(tmp_cache, [])
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        p.authenticate()

        entry = CalendarEntry(
            title="No ID", start=datetime.now(timezone.utc),
            end=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert not p.update_event(entry)

    def test_delete_event(self, tmp_cache, sample_events):
        _save_cache(tmp_cache, sample_events)
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        p.authenticate()

        assert p.delete_event("evt-001")
        cached = _load_cache(tmp_cache)
        ids = [e["event_id"] for e in cached]
        assert "evt-001" not in ids
        assert len(cached) == 2

    def test_delete_nonexistent(self, tmp_cache, sample_events):
        _save_cache(tmp_cache, sample_events)
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        p.authenticate()

        assert not p.delete_event("nonexistent")
        assert len(_load_cache(tmp_cache)) == 3

    def test_delete_empty_id(self, tmp_cache):
        _save_cache(tmp_cache, [])
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        p.authenticate()
        assert not p.delete_event("")


# ---------------------------------------------------------------------------
# Webhook receiver
# ---------------------------------------------------------------------------

class TestWebhookReceiver:
    def test_receive_event(self, tmp_cache):
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        _save_cache(tmp_cache, [])

        event_id = p.receive_webhook_event({
            "event_id": "gcal-456",
            "title": "Meeting from Zapier",
            "start": "2026-03-25T10:00:00+00:00",
            "end": "2026-03-25T11:00:00+00:00",
            "location": "Conference Room",
        })
        assert event_id == "gcal-456"

        cached = _load_cache(tmp_cache)
        assert len(cached) == 1
        assert cached[0]["title"] == "Meeting from Zapier"
        assert cached[0]["source"] == "zapier_inbound"

    def test_receive_deduplicates(self, tmp_cache):
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        _save_cache(tmp_cache, [{
            "event_id": "gcal-456",
            "title": "Old Version",
            "start": "2026-03-25T10:00:00+00:00",
            "end": "2026-03-25T11:00:00+00:00",
        }])

        p.receive_webhook_event({
            "event_id": "gcal-456",
            "title": "Updated Version",
            "start": "2026-03-25T10:00:00+00:00",
            "end": "2026-03-25T11:30:00+00:00",
        })

        cached = _load_cache(tmp_cache)
        assert len(cached) == 1
        assert cached[0]["title"] == "Updated Version"

    def test_receive_missing_times(self, tmp_cache):
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        _save_cache(tmp_cache, [])
        result = p.receive_webhook_event({"title": "No times"})
        assert result == ""

    def test_receive_uses_summary_fallback(self, tmp_cache):
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        _save_cache(tmp_cache, [])
        p.receive_webhook_event({
            "summary": "GCal Summary Field",
            "start_time": "2026-03-25T10:00:00+00:00",
            "end_time": "2026-03-25T11:00:00+00:00",
        })
        cached = _load_cache(tmp_cache)
        assert cached[0]["title"] == "GCal Summary Field"


# ---------------------------------------------------------------------------
# Status & cache management
# ---------------------------------------------------------------------------

class TestStatusAndCache:
    def test_status(self, tmp_cache):
        p = ZapierCalendarProvider(
            webhook_in="https://hooks.zapier.com/in",
            cache_path=tmp_cache,
        )
        p.authenticate()
        status = p.status()
        assert status["provider"] == "zapier_calendar"
        assert status["authenticated"]
        assert status["has_webhook_in"]
        assert not status["has_webhook_out"]

    def test_cache_stats(self, tmp_cache, sample_events):
        _save_cache(tmp_cache, sample_events)
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        stats = p.cache_stats()
        assert stats["total"] == 3
        # At least 1 upcoming (Lunch is 3h out) and 1 past
        assert stats["upcoming"] >= 1
        assert stats["past"] >= 1

    def test_clear_cache(self, tmp_cache, sample_events):
        _save_cache(tmp_cache, sample_events)
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        removed = p.clear_cache()
        assert removed == 3
        assert _load_cache(tmp_cache) == []

    def test_purge_past_events(self, tmp_cache, sample_events):
        _save_cache(tmp_cache, sample_events)
        p = ZapierCalendarProvider(cache_path=tmp_cache)
        removed = p.purge_past_events()
        assert removed == 1
        remaining = _load_cache(tmp_cache)
        assert len(remaining) == 2
        titles = [e["title"] for e in remaining]
        assert "Past Meeting" not in titles


# ---------------------------------------------------------------------------
# CalendarSync integration
# ---------------------------------------------------------------------------

class TestCalendarSyncIntegration:
    def test_zapier_provider_in_calendar_sync(self, tmp_cache, sample_events):
        _save_cache(tmp_cache, sample_events)
        provider = ZapierCalendarProvider(cache_path=tmp_cache)
        provider.authenticate()

        sync = CalendarSync(provider=provider)
        assert sync.is_connected
        assert sync.provider.provider_name == "zapier_calendar"

    def test_pull_events_via_sync(self, tmp_cache, sample_events):
        _save_cache(tmp_cache, sample_events)
        provider = ZapierCalendarProvider(cache_path=tmp_cache)
        provider.authenticate()

        sync = CalendarSync(provider=provider)
        events = sync.pull_events(days_ahead=7, days_behind=7)
        assert len(events) == 3

    def test_today_schedule_via_sync(self, tmp_cache, sample_events):
        _save_cache(tmp_cache, sample_events)
        provider = ZapierCalendarProvider(cache_path=tmp_cache)
        provider.authenticate()

        sync = CalendarSync(provider=provider)
        today = sync.today_schedule()
        # Should get today's events only
        assert isinstance(today, list)

    def test_sync_status(self, tmp_cache):
        _save_cache(tmp_cache, [])
        provider = ZapierCalendarProvider(cache_path=tmp_cache)
        provider.authenticate()

        sync = CalendarSync(provider=provider)
        status = sync.status()
        assert status["provider"] == "zapier_calendar"
        assert status["authenticated"]


# ---------------------------------------------------------------------------
# Chronos integration — Zapier fallback
# ---------------------------------------------------------------------------

class TestChronosZapierFallback:
    def _make_chronos(self):
        cfg = AgentConfig(name="chronos", allowed_resources=["calendar", "zapier_calendar"])
        audit = AuditLog(log_dir=Path(tempfile.mkdtemp()))
        return Chronos(config=cfg, audit=audit)

    def test_chronos_reports_provider(self):
        chronos = self._make_chronos()
        chronos.initialize()
        # Without any credentials, should be "none"
        assert chronos.calendar_provider_name == "none"

    def test_chronos_zapier_fallback(self, tmp_cache):
        """When Google Calendar is unavailable but Zapier cache exists, Chronos uses Zapier."""
        _save_cache(tmp_cache, [])
        with patch.dict(os.environ, {"ZAPIER_CALENDAR_CACHE": tmp_cache}):
            chronos = self._make_chronos()
            chronos.initialize()
            assert chronos.calendar_provider_name == "zapier_calendar"
            assert chronos.calendar_sync is not None
            assert chronos.calendar_sync.is_connected

    def test_chronos_calendar_status_with_zapier(self, tmp_cache):
        _save_cache(tmp_cache, [])
        with patch.dict(os.environ, {"ZAPIER_CALENDAR_CACHE": tmp_cache}):
            chronos = self._make_chronos()
            chronos.initialize()
            status = chronos.calendar_status()
            assert status["active_provider"] == "zapier_calendar"
            assert status.get("authenticated")

    def test_chronos_run_with_zapier(self, tmp_cache, sample_events):
        _save_cache(tmp_cache, sample_events)
        with patch.dict(os.environ, {"ZAPIER_CALENDAR_CACHE": tmp_cache}):
            chronos = self._make_chronos()
            chronos.initialize()
            report = chronos.run()
            assert report.data["calendar_connected"]
            assert report.data["calendar_provider"] == "zapier_calendar"
