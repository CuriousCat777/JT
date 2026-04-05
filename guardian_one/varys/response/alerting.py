"""Alert dispatcher — sends security alerts to configured channels."""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from guardian_one.varys.agent import SecurityAlert

log = logging.getLogger(__name__)


class AlertDispatcher:
    """Dispatches alerts to console, email, and webhook channels."""

    def __init__(self) -> None:
        self._sent: list[dict[str, Any]] = []

    @property
    def sent_count(self) -> int:
        return len(self._sent)

    def send_alert(
        self,
        alert: Any,
        channels: list[str] | None = None,
    ) -> None:
        """Send an alert to the specified channels."""
        channels = channels or ["console"]

        for channel in channels:
            self._dispatch(channel, alert)

        self._sent.append({
            "alert_id": alert.id,
            "severity": alert.severity.value,
            "channels": channels,
            "title": alert.title,
        })

    def _dispatch(self, channel: str, alert: Any) -> None:
        """Route to the correct channel handler."""
        if channel == "console":
            self._send_console(alert)
        elif channel == "email":
            self._send_email(alert)
        elif channel == "slack":
            self._send_slack(alert)
        else:
            log.warning("Unknown alert channel: %s", channel)

    def _send_console(self, alert: Any) -> None:
        severity = alert.severity.value.upper()
        log.warning(
            "[VARYS %s] %s — %s",
            severity,
            alert.title,
            alert.description,
        )

    def _send_email(self, alert: Any) -> None:
        # Integration point: use guardian_one.utils.notifications.EmailChannel
        log.info("Email alert queued: %s", alert.title)

    def _send_slack(self, alert: Any) -> None:
        # Integration point: webhook to Slack
        log.info("Slack alert queued: %s", alert.title)
