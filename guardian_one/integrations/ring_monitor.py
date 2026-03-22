"""Ring Doorbell Monitor — event polling and audit logging.

Polls Ring cloud API for motion, doorbell, and ding events.
Logs all events to Guardian One's audit trail. Supports priority
monitoring for specific devices (e.g., parents' Manteca property).

Ring is 100% cloud-dependent (Amazon). No local API exists.
This integration uses the ring_doorbell library which authenticates
via Ring's OAuth2 flow.

Usage:
    monitor = RingMonitor(audit_log, vault)
    monitor.start_polling(interval_seconds=60)
    # or one-shot:
    events = monitor.check_events()
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from guardian_one.core.audit import AuditLog, Severity
    from guardian_one.homelink.vault import Vault


@dataclass
class RingEvent:
    """A single Ring event (motion, ding, doorbell press)."""
    device_id: str
    device_name: str
    event_type: str       # motion, ding, on_demand (live view)
    timestamp: str
    answered: bool = False
    duration_seconds: int = 0
    location: str = ""
    priority: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "answered": self.answered,
            "duration_seconds": self.duration_seconds,
            "location": self.location,
            "priority": self.priority,
        }


# Devices flagged for priority monitoring get CRITICAL severity
PRIORITY_DEVICES = {
    "ring-doorbell-manteca",
}


class RingMonitor:
    """Polls Ring API for events and logs them to the audit trail.

    Parameters
    ----------
    audit : AuditLog
        Guardian One's audit log for recording events.
    vault : Vault
        Encrypted credential store (RING_REFRESH_TOKEN).
    poll_interval : int
        Seconds between polls (default 60).
    priority_devices : set[str] | None
        Device IDs that get CRITICAL severity logging.
    """

    def __init__(
        self,
        audit: AuditLog,
        vault: Vault,
        poll_interval: int = 60,
        priority_devices: set[str] | None = None,
    ) -> None:
        self._audit = audit
        self._vault = vault
        self._poll_interval = poll_interval
        self._priority = priority_devices or PRIORITY_DEVICES
        self._seen_event_ids: set[str] = set()
        self._polling = False
        self._thread: threading.Thread | None = None
        self._events: list[RingEvent] = []
        self._last_check: str = ""
        self._ring = None  # ring_doorbell.Ring instance (lazy init)

    # ------------------------------------------------------------------
    # Ring API connection
    # ------------------------------------------------------------------

    def _get_ring(self) -> Any:
        """Lazy-init Ring API connection using token from Vault."""
        if self._ring is not None:
            return self._ring
        try:
            from ring_doorbell import Auth, Ring
        except ImportError:
            self._audit_log("ring_monitor", "ring_import_failed",
                            "WARNING",
                            {"error": "ring_doorbell package not installed. "
                             "Install with: pip install ring-doorbell"})
            return None

        token = self._vault.get("RING_REFRESH_TOKEN")
        if not token:
            self._audit_log("ring_monitor", "ring_no_credentials",
                            "WARNING",
                            {"error": "No RING_REFRESH_TOKEN in Vault. "
                             "Run ring-doorbell auth flow first."})
            return None

        try:
            auth = Auth("GuardianOne/1.0", token=token)
            self._ring = Ring(auth)
            self._ring.update_data()
            self._audit_log("ring_monitor", "ring_connected", "INFO",
                            {"devices": len(self._ring.devices())})
            return self._ring
        except Exception as e:
            self._audit_log("ring_monitor", "ring_auth_failed", "ERROR",
                            {"error": str(e)})
            return None

    # ------------------------------------------------------------------
    # Event checking
    # ------------------------------------------------------------------

    def check_events(self) -> list[RingEvent]:
        """Poll Ring API for new events. Returns newly seen events."""
        self._last_check = datetime.now(timezone.utc).isoformat()
        ring = self._get_ring()
        if ring is None:
            return []

        new_events: list[RingEvent] = []
        try:
            ring.update_dings()
            ring.update_data()

            for doorbell in ring.devices().get("doorbots", []):
                for event in doorbell.history(limit=20):
                    event_id = str(event.get("id", ""))
                    if event_id in self._seen_event_ids:
                        continue
                    self._seen_event_ids.add(event_id)

                    device_id = self._match_device_id(doorbell.name)
                    is_priority = device_id in self._priority

                    ring_event = RingEvent(
                        device_id=device_id,
                        device_name=doorbell.name,
                        event_type=event.get("kind", "unknown"),
                        timestamp=str(event.get("created_at", "")),
                        answered=event.get("answered", False),
                        duration_seconds=event.get("duration", 0),
                        location="manteca" if "manteca" in doorbell.name.lower() else "duluth",
                        priority=is_priority,
                    )
                    new_events.append(ring_event)
                    self._events.append(ring_event)

                    severity = "CRITICAL" if is_priority else "INFO"
                    self._audit_log(
                        "ring_monitor",
                        f"ring_event_{ring_event.event_type}",
                        severity,
                        ring_event.to_dict(),
                    )

        except Exception as e:
            self._audit_log("ring_monitor", "ring_poll_error", "ERROR",
                            {"error": str(e)})

        return new_events

    def _match_device_id(self, ring_name: str) -> str:
        """Map Ring device name to our device_id."""
        name_lower = ring_name.lower()
        if "manteca" in name_lower:
            return "ring-doorbell-manteca"
        if "304" in name_lower:
            return "cam-01"
        return "ring-doorbell-duluth-2"

    # ------------------------------------------------------------------
    # Continuous polling
    # ------------------------------------------------------------------

    def start_polling(self, interval: int | None = None) -> None:
        """Start background polling thread."""
        if self._polling:
            return
        self._polling = True
        self._poll_interval = interval or self._poll_interval
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="ring-monitor"
        )
        self._thread.start()
        self._audit_log("ring_monitor", "polling_started", "INFO",
                        {"interval_seconds": self._poll_interval,
                         "priority_devices": list(self._priority)})

    def stop_polling(self) -> None:
        """Stop background polling."""
        self._polling = False
        if self._thread:
            self._thread.join(timeout=self._poll_interval + 5)
            self._thread = None
        self._audit_log("ring_monitor", "polling_stopped", "INFO", {})

    def _poll_loop(self) -> None:
        """Background polling loop."""
        while self._polling:
            try:
                new = self.check_events()
                if new:
                    priority_events = [e for e in new if e.priority]
                    if priority_events:
                        self._send_alert(priority_events)
            except Exception as e:
                self._audit_log("ring_monitor", "poll_loop_error", "ERROR",
                                {"error": str(e)})
            time.sleep(self._poll_interval)

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------

    def _send_alert(self, events: list[RingEvent]) -> None:
        """Send alert for priority events (Manteca)."""
        for event in events:
            self._audit_log(
                "ring_monitor",
                "PRIORITY_ALERT",
                "CRITICAL",
                {
                    "message": f"Activity at parents' home: {event.event_type} "
                               f"on {event.device_name}",
                    "event": event.to_dict(),
                    "action_required": True,
                },
            )

    # ------------------------------------------------------------------
    # Status / reporting
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Current monitor status."""
        return {
            "polling": self._polling,
            "poll_interval_seconds": self._poll_interval,
            "last_check": self._last_check,
            "total_events_seen": len(self._events),
            "priority_devices": list(self._priority),
            "recent_events": [e.to_dict() for e in self._events[-10:]],
        }

    def manteca_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent events from Manteca property only."""
        manteca = [e for e in self._events if e.location == "manteca"]
        return [e.to_dict() for e in manteca[-limit:]]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _audit_log(
        self, agent: str, action: str, severity: str, details: dict[str, Any]
    ) -> None:
        """Write to Guardian One audit log."""
        from guardian_one.core.audit import Severity as Sev
        sev_map = {
            "INFO": Sev.INFO,
            "WARNING": Sev.WARNING,
            "ERROR": Sev.ERROR,
            "CRITICAL": Sev.CRITICAL,
        }
        self._audit.record(
            agent=agent,
            action=action,
            severity=sev_map.get(severity, Sev.INFO),
            details=details,
            requires_review=(severity == "CRITICAL"),
        )
