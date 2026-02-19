"""Notification system — alerts and reminders for Jeremy.

Currently supports console output.  Designed for easy extension to
push notifications, email, SMS, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol


class Urgency(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Notification:
    source: str
    title: str
    body: str
    urgency: Urgency = Urgency.MEDIUM
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class NotificationChannel(Protocol):
    """Protocol for notification delivery backends."""
    def send(self, notification: Notification) -> bool: ...


class ConsoleChannel:
    """Print notifications to stdout (default for MVP)."""

    def send(self, notification: Notification) -> bool:
        icon = {
            Urgency.LOW: "[i]",
            Urgency.MEDIUM: "[!]",
            Urgency.HIGH: "[!!]",
            Urgency.CRITICAL: "[!!!]",
        }[notification.urgency]
        print(
            f"{icon} [{notification.source}] {notification.title}: {notification.body}"
        )
        return True


class NotificationManager:
    """Dispatches notifications through registered channels."""

    def __init__(self) -> None:
        self._channels: list[NotificationChannel] = [ConsoleChannel()]
        self._history: list[Notification] = []

    def add_channel(self, channel: NotificationChannel) -> None:
        self._channels.append(channel)

    def notify(
        self,
        source: str,
        title: str,
        body: str,
        urgency: Urgency = Urgency.MEDIUM,
    ) -> Notification:
        notification = Notification(
            source=source, title=title, body=body, urgency=urgency
        )
        for channel in self._channels:
            channel.send(notification)
        self._history.append(notification)
        return notification

    def recent(self, limit: int = 10) -> list[Notification]:
        return self._history[-limit:]
