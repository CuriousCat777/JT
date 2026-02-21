"""Tests for the notification system."""

from guardian_one.utils.notifications import (
    ConsoleChannel,
    Notification,
    NotificationManager,
    Urgency,
)


# ------------------------------------------------------------------
# ConsoleChannel tests
# ------------------------------------------------------------------


def test_console_channel_send():
    channel = ConsoleChannel()
    note = Notification(source="test", title="Title", body="Body")
    result = channel.send(note)
    assert result is True


def test_console_channel_all_urgency_levels():
    channel = ConsoleChannel()
    for urgency in Urgency:
        note = Notification(source="test", title="Title", body="Body", urgency=urgency)
        result = channel.send(note)
        assert result is True


# ------------------------------------------------------------------
# NotificationManager tests
# ------------------------------------------------------------------


def test_notification_manager_init():
    mgr = NotificationManager()
    assert len(mgr._channels) == 1  # Default ConsoleChannel
    assert len(mgr._history) == 0


def test_notify_creates_notification():
    mgr = NotificationManager()
    note = mgr.notify("test_agent", "Alert", "Something happened")
    assert note.source == "test_agent"
    assert note.title == "Alert"
    assert note.body == "Something happened"
    assert note.urgency == Urgency.MEDIUM


def test_notify_with_urgency():
    mgr = NotificationManager()
    note = mgr.notify("cfo", "Budget Alert", "Over budget!", urgency=Urgency.HIGH)
    assert note.urgency == Urgency.HIGH


def test_notify_stores_history():
    mgr = NotificationManager()
    mgr.notify("a", "T1", "B1")
    mgr.notify("b", "T2", "B2")
    mgr.notify("c", "T3", "B3")
    assert len(mgr._history) == 3


def test_recent_returns_latest():
    mgr = NotificationManager()
    for i in range(15):
        mgr.notify("agent", f"Title {i}", f"Body {i}")

    recent = mgr.recent(limit=5)
    assert len(recent) == 5
    assert recent[-1].title == "Title 14"


def test_recent_with_fewer_than_limit():
    mgr = NotificationManager()
    mgr.notify("a", "T", "B")
    recent = mgr.recent(limit=10)
    assert len(recent) == 1


def test_recent_empty_history():
    mgr = NotificationManager()
    recent = mgr.recent()
    assert recent == []


def test_add_custom_channel():
    class MockChannel:
        def __init__(self):
            self.sent = []

        def send(self, notification):
            self.sent.append(notification)
            return True

    mgr = NotificationManager()
    mock = MockChannel()
    mgr.add_channel(mock)
    mgr.notify("test", "T", "B")

    assert len(mock.sent) == 1
    assert mock.sent[0].title == "T"


def test_notification_has_timestamp():
    mgr = NotificationManager()
    note = mgr.notify("test", "T", "B")
    assert note.timestamp  # Should have an ISO timestamp
    assert "T" in note.timestamp  # ISO format contains 'T'


def test_notification_metadata():
    note = Notification(
        source="test",
        title="T",
        body="B",
        metadata={"key": "value"},
    )
    assert note.metadata["key"] == "value"
