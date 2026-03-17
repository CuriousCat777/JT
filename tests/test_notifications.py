"""Tests for the notification system."""

from datetime import time
from unittest.mock import MagicMock, patch

from guardian_one.utils.notifications import (
    AlertRouter,
    ConsoleChannel,
    EmailChannel,
    Notification,
    NotificationManager,
    SMSChannel,
    Urgency,
    _notification_to_html,
    build_notification_stack,
    format_daily_digest,
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


def test_notify_with_metadata_kwarg():
    mgr = NotificationManager()
    note = mgr.notify("src", "T", "B", metadata={"x": 1})
    assert note.metadata == {"x": 1}


# ------------------------------------------------------------------
# EmailChannel tests
# ------------------------------------------------------------------


def test_email_channel_not_configured(monkeypatch):
    monkeypatch.delenv("GMAIL_FROM", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    monkeypatch.delenv("NOTIFY_EMAIL", raising=False)
    ch = EmailChannel(from_email="", to_email="", app_password="")
    assert ch.configured is False
    assert ch.send(Notification(source="t", title="T", body="B")) is False


def test_email_channel_configured_check():
    ch = EmailChannel(from_email="a@b.com", to_email="c@d.com", app_password="secret123")
    assert ch.configured is True


def test_email_channel_send_calls_smtp():
    ch = EmailChannel(from_email="a@b.com", to_email="c@d.com", app_password="secret")
    note = Notification(source="test", title="Title", body="Body")

    with patch("guardian_one.utils.notifications.smtplib.SMTP") as mock_smtp:
        server = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=server)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        result = ch.send(note)

    assert result is True
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("a@b.com", "secret")
    server.sendmail.assert_called_once()


def test_email_channel_handles_smtp_error():
    ch = EmailChannel(from_email="a@b.com", to_email="c@d.com", app_password="secret")
    note = Notification(source="test", title="Title", body="Body")

    with patch("guardian_one.utils.notifications.smtplib.SMTP") as mock_smtp:
        mock_smtp.side_effect = ConnectionRefusedError("Connection refused")
        result = ch.send(note)

    assert result is False


def test_email_channel_env_fallback():
    with patch.dict("os.environ", {
        "GMAIL_FROM": "env@test.com",
        "NOTIFY_EMAIL": "notify@test.com",
        "GMAIL_APP_PASSWORD": "envpass",
    }):
        ch = EmailChannel()
        assert ch.from_email == "env@test.com"
        assert ch.to_email == "notify@test.com"
        assert ch.app_password == "envpass"
        assert ch.configured is True


# ------------------------------------------------------------------
# SMSChannel tests
# ------------------------------------------------------------------


def test_sms_channel_not_configured():
    ch = SMSChannel(account_sid="", auth_token="", from_number="", to_number="")
    assert ch.configured is False
    assert ch.send(Notification(source="t", title="T", body="B")) is False


def test_sms_channel_configured_check():
    ch = SMSChannel(
        account_sid="AC123",
        auth_token="tok123",
        from_number="+15551234567",
        to_number="+15559876543",
    )
    assert ch.configured is True


def test_sms_channel_send_calls_api():
    ch = SMSChannel(
        account_sid="AC123",
        auth_token="tok123",
        from_number="+15551234567",
        to_number="+15559876543",
    )
    note = Notification(source="test", title="Title", body="Body")

    mock_response = MagicMock()
    mock_response.read.return_value = b'{"sid": "SM123"}'
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("guardian_one.utils.notifications.urlopen", return_value=mock_response):
        result = ch.send(note)

    assert result is True


def test_sms_channel_handles_api_error():
    ch = SMSChannel(
        account_sid="AC123",
        auth_token="tok123",
        from_number="+15551234567",
        to_number="+15559876543",
    )
    note = Notification(source="test", title="Title", body="Body")

    with patch("guardian_one.utils.notifications.urlopen", side_effect=Exception("API error")):
        result = ch.send(note)

    assert result is False


def test_sms_truncates_long_messages():
    ch = SMSChannel(
        account_sid="AC123",
        auth_token="tok123",
        from_number="+15551234567",
        to_number="+15559876543",
    )
    # Create a very long notification
    note = Notification(source="test", title="Title", body="X" * 2000)

    mock_response = MagicMock()
    mock_response.read.return_value = b'{"sid": "SM123"}'
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("guardian_one.utils.notifications.urlopen", return_value=mock_response) as mock_open:
        ch.send(note)

    # Verify the body was truncated
    call_args = mock_open.call_args
    req = call_args[0][0]
    assert len(req.data) <= 1700  # URL-encoded body + metadata


# ------------------------------------------------------------------
# Quiet hours tests
# ------------------------------------------------------------------


def test_quiet_hours_holds_low_urgency():
    """During quiet hours, LOW urgency notifications are held."""
    mgr = NotificationManager(quiet_start=time(0, 0), quiet_end=time(23, 59))
    # Always quiet hours with this range

    mock = MagicMock()
    mgr.add_channel(mock)

    mgr.notify("test", "Low", "body", Urgency.LOW)

    # ConsoleChannel always exists, but mock should NOT have been called
    # because it's quiet hours and urgency is LOW
    mock.send.assert_not_called()
    assert mgr.held_count == 1


def test_quiet_hours_holds_medium_urgency():
    """During quiet hours, MEDIUM urgency notifications are held."""
    mgr = NotificationManager(quiet_start=time(0, 0), quiet_end=time(23, 59))

    mock = MagicMock()
    mgr.add_channel(mock)

    mgr.notify("test", "Medium", "body", Urgency.MEDIUM)
    mock.send.assert_not_called()
    assert mgr.held_count == 1


def test_quiet_hours_allows_high_urgency():
    """During quiet hours, HIGH urgency notifications go through."""
    mgr = NotificationManager(quiet_start=time(0, 0), quiet_end=time(23, 59))

    mock = MagicMock()
    mgr.add_channel(mock)

    mgr.notify("test", "High", "body", Urgency.HIGH)
    mock.send.assert_called_once()
    assert mgr.held_count == 0


def test_quiet_hours_allows_critical():
    """During quiet hours, CRITICAL urgency notifications go through."""
    mgr = NotificationManager(quiet_start=time(0, 0), quiet_end=time(23, 59))

    mock = MagicMock()
    mgr.add_channel(mock)

    mgr.notify("test", "Critical", "body", Urgency.CRITICAL)
    mock.send.assert_called_once()
    assert mgr.held_count == 0


def test_flush_held_sends_all():
    """flush_held() sends all held notifications."""
    mgr = NotificationManager(quiet_start=time(0, 0), quiet_end=time(23, 59))

    mock = MagicMock()
    mgr.add_channel(mock)

    mgr.notify("a", "T1", "B1", Urgency.LOW)
    mgr.notify("b", "T2", "B2", Urgency.MEDIUM)
    assert mgr.held_count == 2

    flushed = mgr.flush_held()
    assert len(flushed) == 2
    assert mgr.held_count == 0
    # Each held notification sent to each non-Console channel
    assert mock.send.call_count == 2


def test_held_still_in_history():
    """Held notifications are still tracked in history."""
    mgr = NotificationManager(quiet_start=time(0, 0), quiet_end=time(23, 59))
    mgr.notify("a", "T", "B", Urgency.LOW)
    assert len(mgr._history) == 1
    assert mgr.held_count == 1


# ------------------------------------------------------------------
# HTML formatter tests
# ------------------------------------------------------------------


def test_notification_to_html_contains_title():
    note = Notification(source="CFO", title="Budget Alert", body="Over budget!")
    html = _notification_to_html(note)
    assert "Budget Alert" in html
    assert "Over budget!" in html
    assert "CFO" in html


def test_notification_to_html_urgency_colors():
    for urgency in Urgency:
        note = Notification(source="test", title="T", body="B", urgency=urgency)
        html = _notification_to_html(note)
        assert "font-family" in html  # Has styling


def test_notification_to_html_newlines():
    note = Notification(source="test", title="T", body="Line 1\nLine 2")
    html = _notification_to_html(note)
    assert "<br>" in html


# ------------------------------------------------------------------
# Daily Digest tests
# ------------------------------------------------------------------


def _sample_review():
    return {
        "date": "2026-02-23",
        "generated_at": "2026-02-23T12:00:00+00:00",
        "overall_status": "needs_attention",
        "overall_message": "3 item(s) need your attention today.",
        "transactions": {"status": "needs_attention", "warnings": 2, "flags": [
            {"reason": "duplicate", "description": "Starbucks", "amount": -5.50},
            {"reason": "unusual_amount", "description": "Amazon", "amount": -450.00},
        ]},
        "bills": {
            "results": [
                {"bill": "Rent", "status": "overdue_unverified"},
                {"bill": "Netflix", "status": "confirmed_paid"},
            ],
            "paid": 1,
            "pending": 0,
            "overdue": 1,
        },
        "budget": {
            "results": [
                {"label": "Food", "limit": 500, "spent": 600, "remaining": -100,
                 "percent_used": 120, "status": "over"},
                {"label": "Transport", "limit": 200, "spent": 170, "remaining": 30,
                 "percent_used": 85, "status": "warning"},
            ],
            "over_budget": 1,
            "warnings": 1,
            "on_track": 0,
        },
    }


def test_daily_digest_subject():
    review = _sample_review()
    subject, html = format_daily_digest(review, net_worth=135000)
    assert "Action Needed" in subject
    assert "2026-02-23" in subject


def test_daily_digest_html_has_net_worth():
    review = _sample_review()
    subject, html = format_daily_digest(review, net_worth=135000)
    assert "$135,000.00" in html


def test_daily_digest_html_has_overdue_bills():
    review = _sample_review()
    _, html = format_daily_digest(review)
    assert "Bills Overdue" in html


def test_daily_digest_html_has_budget_table():
    review = _sample_review()
    _, html = format_daily_digest(review)
    assert "Food" in html
    assert "120%" in html


def test_daily_digest_html_has_tx_flags():
    review = _sample_review()
    _, html = format_daily_digest(review)
    assert "Transaction Flags" in html
    assert "Starbucks" in html


def test_daily_digest_all_clear():
    review = {
        "date": "2026-02-23",
        "generated_at": "2026-02-23T12:00:00+00:00",
        "overall_status": "all_clear",
        "overall_message": "Everything looks good today.",
        "transactions": {"status": "clean", "warnings": 0},
        "bills": {"results": [], "paid": 2, "pending": 0, "overdue": 0},
        "budget": {"results": [], "over_budget": 0, "warnings": 0, "on_track": 3},
    }
    subject, html = format_daily_digest(review)
    assert "All Clear" in subject
    assert "Everything looks good" in html


# ------------------------------------------------------------------
# AlertRouter tests
# ------------------------------------------------------------------


def test_alert_router_fires_on_overdue_bills():
    mgr = NotificationManager()
    router = AlertRouter(mgr)

    review = _sample_review()
    fired = router.route_daily_review(review, send_digest=False)

    # Should fire: overdue bills (HIGH), over budget (HIGH), budget warning (MEDIUM), tx flags (MEDIUM)
    assert len(fired) == 4
    titles = [n.title for n in fired]
    assert "Bills Overdue" in titles
    assert "Over Budget" in titles
    assert "Budget Warning" in titles
    assert "Transaction Flags" in titles


def test_alert_router_fires_digest():
    mgr = NotificationManager()
    router = AlertRouter(mgr)

    review = _sample_review()
    fired = router.route_daily_review(review, net_worth=135000, send_digest=True)

    # Should include the digest as the last notification
    digest = [n for n in fired if n.metadata.get("type") == "daily_digest"]
    assert len(digest) == 1
    assert "Guardian Daily" in digest[0].title


def test_alert_router_no_alerts_when_clean():
    mgr = NotificationManager()
    router = AlertRouter(mgr)

    review = {
        "date": "2026-02-23",
        "generated_at": "2026-02-23T12:00:00+00:00",
        "overall_status": "all_clear",
        "overall_message": "Everything looks good.",
        "transactions": {"status": "clean", "warnings": 0},
        "bills": {"results": [], "paid": 0, "pending": 0, "overdue": 0},
        "budget": {"results": [], "over_budget": 0, "warnings": 0, "on_track": 0},
    }
    fired = router.route_daily_review(review, send_digest=False)
    assert len(fired) == 0  # No issues → no alerts (digest disabled)


def test_alert_router_budget_alerts_text():
    mgr = NotificationManager()
    router = AlertRouter(mgr)

    alerts = [
        "OVER BUDGET: Food — spent $600 of $500 limit ($100 over)",
        "Heads up: Transport — $170 of $200 (85% used)",
    ]
    fired = router.route_budget_alerts(alerts)
    assert len(fired) == 2
    assert fired[0].urgency == Urgency.HIGH
    assert fired[1].urgency == Urgency.MEDIUM


def test_alert_router_bill_reminder():
    mgr = NotificationManager()
    router = AlertRouter(mgr)

    n = router.route_bill_reminder("Rent", 1500, "2026-02-25", overdue=False)
    assert n.urgency == Urgency.MEDIUM
    assert "Rent" in n.body
    assert "$1,500.00" in n.body

    n2 = router.route_bill_reminder("Netflix", 15.99, "2026-02-20", overdue=True)
    assert n2.urgency == Urgency.HIGH
    assert "Overdue" in n2.title


def test_alert_router_urgency_levels():
    """Verify correct urgency mapping for different alert types."""
    mgr = NotificationManager()
    router = AlertRouter(mgr)

    review = _sample_review()
    fired = router.route_daily_review(review, send_digest=False)

    urgencies = {n.title: n.urgency for n in fired}
    assert urgencies["Bills Overdue"] == Urgency.HIGH
    assert urgencies["Over Budget"] == Urgency.HIGH
    assert urgencies["Budget Warning"] == Urgency.MEDIUM
    assert urgencies["Transaction Flags"] == Urgency.MEDIUM


# ------------------------------------------------------------------
# build_notification_stack tests
# ------------------------------------------------------------------


def test_build_stack_console_only():
    """Without env vars, only ConsoleChannel is active."""
    with patch.dict("os.environ", {}, clear=True):
        mgr, router = build_notification_stack(enable_email=True, enable_sms=True)
    assert len(mgr._channels) == 1  # Just Console
    assert isinstance(mgr._channels[0], ConsoleChannel)
    assert isinstance(router, AlertRouter)


def test_build_stack_with_email():
    """With email env vars, EmailChannel is added."""
    env = {
        "GMAIL_FROM": "a@b.com",
        "NOTIFY_EMAIL": "c@d.com",
        "GMAIL_APP_PASSWORD": "secret",
    }
    with patch.dict("os.environ", env, clear=True):
        mgr, _ = build_notification_stack()
    assert len(mgr._channels) == 2  # Console + Email
    assert isinstance(mgr._channels[1], EmailChannel)


def test_build_stack_with_sms():
    """With Twilio env vars, SMSChannel is added."""
    env = {
        "TWILIO_ACCOUNT_SID": "AC123",
        "TWILIO_AUTH_TOKEN": "tok123",
        "TWILIO_FROM_NUMBER": "+15551234567",
        "NOTIFY_PHONE": "+15559876543",
    }
    with patch.dict("os.environ", env, clear=True):
        mgr, _ = build_notification_stack(enable_email=False)
    assert len(mgr._channels) == 2  # Console + SMS
    assert isinstance(mgr._channels[1], SMSChannel)


def test_build_stack_disabled_channels():
    """Channels can be disabled even if credentials exist."""
    env = {
        "GMAIL_FROM": "a@b.com",
        "NOTIFY_EMAIL": "c@d.com",
        "GMAIL_APP_PASSWORD": "secret",
    }
    with patch.dict("os.environ", env, clear=True):
        mgr, _ = build_notification_stack(enable_email=False, enable_sms=False)
    assert len(mgr._channels) == 1  # Just Console


def test_build_stack_quiet_hours():
    """build_notification_stack passes quiet hour config through."""
    mgr, _ = build_notification_stack(
        quiet_start=time(21, 0),
        quiet_end=time(8, 0),
        timezone_name="America/New_York",
    )
    assert mgr.quiet_start == time(21, 0)
    assert mgr.quiet_end == time(8, 0)
    assert mgr.timezone_name == "America/New_York"


# ------------------------------------------------------------------
# Channel error resilience
# ------------------------------------------------------------------


def test_manager_survives_channel_exception():
    """If a channel raises, manager continues to other channels."""
    class BrokenChannel:
        def send(self, notification):
            raise RuntimeError("boom")

    class GoodChannel:
        def __init__(self):
            self.sent = []
        def send(self, notification):
            self.sent.append(notification)
            return True

    mgr = NotificationManager()
    mgr.add_channel(BrokenChannel())
    good = GoodChannel()
    mgr.add_channel(good)

    mgr.notify("test", "T", "B", Urgency.HIGH)
    assert len(good.sent) == 1  # Good channel still got it
    assert len(mgr._history) == 1
