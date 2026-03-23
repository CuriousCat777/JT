"""Zapier integration — webhook-based calendar bridge.

When Google Calendar OAuth isn't available, Chronos can pull/push events
through Zapier webhooks.  The flow:

**Inbound (Google Calendar → Guardian One):**
1. Zapier trigger: "New event in Google Calendar"
2. Zapier action: POST to a local webhook (or write to a JSON cache file)
3. ZapierCalendarProvider reads the cached events

**Outbound (Guardian One → Google Calendar):**
1. Guardian calls ZapierCalendarProvider.create_event()
2. Provider POSTs event data to a Zapier Catch Hook URL
3. Zapier action: "Create detailed event in Google Calendar"

Configuration:
    Set these env vars (or put them in .env):
        ZAPIER_WEBHOOK_CALENDAR_IN   — Zapier webhook URL that *receives* new events
                                       (Guardian pushes events here → Zapier → GCal)
        ZAPIER_WEBHOOK_CALENDAR_OUT  — Zapier webhook URL that *sends* events
                                       (Zapier pushes GCal events here → local cache)
        ZAPIER_CALENDAR_CACHE        — Path to local JSON cache file
                                       (default: data/zapier_calendar_cache.json)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from guardian_one.integrations.calendar_sync import (
    CalendarEntry,
    CalendarProvider,
)


# ---------------------------------------------------------------------------
# Cache — local JSON file that Zapier webhook writes to
# ---------------------------------------------------------------------------

_DEFAULT_CACHE_PATH = "data/zapier_calendar_cache.json"


def _load_cache(path: str) -> list[dict[str, Any]]:
    """Load the event cache from disk."""
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_cache(path: str, events: list[dict[str, Any]]) -> None:
    """Persist the event cache to disk."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(events, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# ZapierCalendarProvider
# ---------------------------------------------------------------------------

class ZapierCalendarProvider(CalendarProvider):
    """Calendar provider that bridges Google Calendar via Zapier webhooks.

    Two modes of operation:

    1. **Webhook mode** (preferred): Zapier pushes events to a local cache
       file via a webhook, and Guardian reads from that cache.  Outbound
       events are POSTed to a Zapier Catch Hook that creates GCal events.

    2. **Cache-only mode**: Events are manually placed in the cache file
       (useful for testing or offline work).

    Env vars:
        ZAPIER_WEBHOOK_CALENDAR_IN  — POST here to create a GCal event via Zapier
        ZAPIER_WEBHOOK_CALENDAR_OUT — Zapier posts GCal events here (writes to cache)
        ZAPIER_CALENDAR_CACHE       — Local cache file path
    """

    def __init__(
        self,
        webhook_in: str | None = None,
        webhook_out: str | None = None,
        cache_path: str | None = None,
    ) -> None:
        self._webhook_in = (
            webhook_in
            or os.environ.get("ZAPIER_WEBHOOK_CALENDAR_IN", "")
        )
        self._webhook_out = (
            webhook_out
            or os.environ.get("ZAPIER_WEBHOOK_CALENDAR_OUT", "")
        )
        self._cache_path = (
            cache_path
            or os.environ.get("ZAPIER_CALENDAR_CACHE", _DEFAULT_CACHE_PATH)
        )
        self._authenticated = False
        self._last_error = ""

    @property
    def provider_name(self) -> str:
        return "zapier_calendar"

    @property
    def has_credentials(self) -> bool:
        """True if at least one webhook URL is configured, or a cache file exists."""
        return bool(self._webhook_in) or os.path.isfile(self._cache_path)

    @property
    def has_webhook_in(self) -> bool:
        """True if outbound webhook (Guardian → Zapier → GCal) is configured."""
        return bool(self._webhook_in)

    @property
    def has_webhook_out(self) -> bool:
        """True if inbound webhook (Zapier → cache) is configured."""
        return bool(self._webhook_out)

    @property
    def last_error(self) -> str:
        return self._last_error

    def authenticate(self) -> bool:
        """Validate that at least one integration path is available."""
        if not self.has_credentials:
            self._last_error = (
                "No Zapier calendar webhooks configured. "
                "Set ZAPIER_WEBHOOK_CALENDAR_IN in .env to push events to Google Calendar, "
                "or set ZAPIER_WEBHOOK_CALENDAR_OUT for Zapier to push events to Guardian."
            )
            self._authenticated = False
            return False

        # If we have a webhook-in, verify it looks like a valid URL
        if self._webhook_in and not self._webhook_in.startswith("http"):
            self._last_error = f"Invalid webhook URL: {self._webhook_in}"
            self._authenticated = False
            return False

        self._authenticated = True
        self._last_error = ""
        return True

    # ---- Read events from cache ----

    def fetch_events(
        self,
        start: datetime,
        end: datetime,
        calendar_id: str = "primary",
    ) -> list[CalendarEntry]:
        """Read events from the local Zapier cache, filtered by time range."""
        if not self._authenticated:
            return []

        raw_events = _load_cache(self._cache_path)
        entries: list[CalendarEntry] = []

        for ev in raw_events:
            try:
                ev_start = datetime.fromisoformat(ev["start"])
                ev_end = datetime.fromisoformat(ev["end"])
            except (KeyError, ValueError, TypeError):
                continue

            # Make timezone-aware if naive
            if ev_start.tzinfo is None:
                ev_start = ev_start.replace(tzinfo=timezone.utc)
            if ev_end.tzinfo is None:
                ev_end = ev_end.replace(tzinfo=timezone.utc)

            # Normalize filter bounds
            filter_start = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
            filter_end = end if end.tzinfo else end.replace(tzinfo=timezone.utc)

            if ev_start >= filter_end or ev_end <= filter_start:
                continue

            entries.append(CalendarEntry(
                title=ev.get("title", ev.get("summary", "(no title)")),
                start=ev_start,
                end=ev_end,
                location=ev.get("location", ""),
                source="zapier_calendar",
                event_id=ev.get("event_id", ev.get("id", "")),
                calendar_id=ev.get("calendar_id", "primary"),
                description=ev.get("description", ""),
            ))

        return sorted(entries, key=lambda e: e.start)

    # ---- Write events via webhook ----

    def create_event(
        self,
        entry: CalendarEntry,
        calendar_id: str = "primary",
    ) -> str:
        """POST event to Zapier webhook, which creates it in Google Calendar."""
        if not self._authenticated:
            return ""

        if not self._webhook_in:
            # No outbound webhook — write to cache only
            return self._create_event_cache_only(entry)

        payload = {
            "title": entry.title,
            "start": entry.start.isoformat(),
            "end": entry.end.isoformat(),
            "location": entry.location,
            "description": entry.description,
            "calendar_id": calendar_id,
            "source": "guardian_one",
        }

        try:
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                self._webhook_in,
                data=data,
                method="POST",
            )
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = resp.read().decode()
            # Zapier returns a JSON response with status
            try:
                resp_data = json.loads(result)
                event_id = resp_data.get("id", f"zapier-{entry.title[:20]}")
            except (json.JSONDecodeError, ValueError):
                event_id = f"zapier-{entry.title[:20]}"

            # Also cache locally
            self._append_to_cache(entry, event_id)
            return event_id

        except Exception as exc:
            self._last_error = f"Zapier webhook POST failed: {exc}"
            # Fall back to cache-only
            return self._create_event_cache_only(entry)

    def _create_event_cache_only(self, entry: CalendarEntry) -> str:
        """Write event to local cache without hitting webhook."""
        event_id = f"local-{entry.title[:20]}-{entry.start.isoformat()[:10]}"
        self._append_to_cache(entry, event_id)
        return event_id

    def _append_to_cache(self, entry: CalendarEntry, event_id: str) -> None:
        """Add an event to the local cache file."""
        events = _load_cache(self._cache_path)
        events.append({
            "title": entry.title,
            "start": entry.start.isoformat(),
            "end": entry.end.isoformat(),
            "location": entry.location,
            "description": entry.description,
            "event_id": event_id,
            "calendar_id": entry.calendar_id,
            "source": "guardian_one",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        _save_cache(self._cache_path, events)

    def update_event(self, entry: CalendarEntry) -> bool:
        """Update an event in the cache (and optionally via webhook)."""
        if not self._authenticated or not entry.event_id:
            return False

        # Update in local cache
        events = _load_cache(self._cache_path)
        updated = False
        for ev in events:
            if ev.get("event_id") == entry.event_id:
                ev["title"] = entry.title
                ev["start"] = entry.start.isoformat()
                ev["end"] = entry.end.isoformat()
                ev["location"] = entry.location
                ev["description"] = entry.description
                ev["updated_at"] = datetime.now(timezone.utc).isoformat()
                updated = True
                break

        if updated:
            _save_cache(self._cache_path, events)

        # If webhook is configured, also push the update
        if updated and self._webhook_in:
            try:
                payload = {
                    "action": "update",
                    "event_id": entry.event_id,
                    "title": entry.title,
                    "start": entry.start.isoformat(),
                    "end": entry.end.isoformat(),
                    "location": entry.location,
                    "description": entry.description,
                    "source": "guardian_one",
                }
                data = json.dumps(payload).encode()
                req = urllib.request.Request(self._webhook_in, data=data, method="POST")
                req.add_header("Content-Type", "application/json")
                urllib.request.urlopen(req, timeout=30)
            except Exception as exc:
                self._last_error = f"Zapier update webhook failed: {exc}"

        return updated

    def delete_event(self, event_id: str, calendar_id: str = "primary") -> bool:
        """Remove an event from the cache (and optionally notify Zapier)."""
        if not self._authenticated or not event_id:
            return False

        events = _load_cache(self._cache_path)
        original_count = len(events)
        events = [ev for ev in events if ev.get("event_id") != event_id]
        deleted = len(events) < original_count

        if deleted:
            _save_cache(self._cache_path, events)

        # Notify webhook about deletion
        if deleted and self._webhook_in:
            try:
                payload = {
                    "action": "delete",
                    "event_id": event_id,
                    "calendar_id": calendar_id,
                    "source": "guardian_one",
                }
                data = json.dumps(payload).encode()
                req = urllib.request.Request(self._webhook_in, data=data, method="POST")
                req.add_header("Content-Type", "application/json")
                urllib.request.urlopen(req, timeout=30)
            except Exception as exc:
                self._last_error = f"Zapier delete webhook failed: {exc}"

        return deleted

    # ---- Zapier webhook receiver ----

    def receive_webhook_event(self, payload: dict[str, Any]) -> str:
        """Process an inbound event from Zapier (GCal → Guardian).

        Call this from a Flask/FastAPI route that Zapier POSTs to.
        Returns the event_id of the cached event.
        """
        event_id = payload.get("event_id", payload.get("id", ""))
        title = payload.get("title", payload.get("summary", "(no title)"))
        start = payload.get("start", payload.get("start_time", ""))
        end = payload.get("end", payload.get("end_time", ""))

        if not start or not end:
            return ""

        events = _load_cache(self._cache_path)

        # Deduplicate by event_id
        if event_id:
            events = [ev for ev in events if ev.get("event_id") != event_id]

        events.append({
            "title": title,
            "start": start,
            "end": end,
            "location": payload.get("location", ""),
            "description": payload.get("description", ""),
            "event_id": event_id,
            "calendar_id": payload.get("calendar_id", "primary"),
            "source": "zapier_inbound",
            "received_at": datetime.now(timezone.utc).isoformat(),
        })
        _save_cache(self._cache_path, events)
        return event_id or f"zapier-{title[:20]}"

    # ---- Status ----

    def status(self) -> dict[str, Any]:
        cached_events = _load_cache(self._cache_path)
        return {
            "provider": self.provider_name,
            "authenticated": self._authenticated,
            "has_webhook_in": self.has_webhook_in,
            "has_webhook_out": self.has_webhook_out,
            "cache_path": self._cache_path,
            "cached_events": len(cached_events),
            "last_error": self._last_error,
        }

    def cache_stats(self) -> dict[str, Any]:
        """Return stats about the local event cache."""
        events = _load_cache(self._cache_path)
        now = datetime.now(timezone.utc)
        upcoming = 0
        past = 0
        for ev in events:
            try:
                ev_start = datetime.fromisoformat(ev["start"])
                if ev_start.tzinfo is None:
                    ev_start = ev_start.replace(tzinfo=timezone.utc)
                if ev_start >= now:
                    upcoming += 1
                else:
                    past += 1
            except (KeyError, ValueError):
                pass
        return {
            "total": len(events),
            "upcoming": upcoming,
            "past": past,
            "cache_path": self._cache_path,
        }

    def clear_cache(self) -> int:
        """Clear all events from the local cache. Returns count of removed events."""
        events = _load_cache(self._cache_path)
        count = len(events)
        _save_cache(self._cache_path, [])
        return count

    def purge_past_events(self) -> int:
        """Remove past events from the cache. Returns count of removed events."""
        events = _load_cache(self._cache_path)
        now = datetime.now(timezone.utc)
        future_events = []
        removed = 0
        for ev in events:
            try:
                ev_end = datetime.fromisoformat(ev.get("end", ev.get("start", "")))
                if ev_end.tzinfo is None:
                    ev_end = ev_end.replace(tzinfo=timezone.utc)
                if ev_end >= now:
                    future_events.append(ev)
                else:
                    removed += 1
            except (KeyError, ValueError):
                future_events.append(ev)  # Keep events we can't parse
        _save_cache(self._cache_path, future_events)
        return removed
