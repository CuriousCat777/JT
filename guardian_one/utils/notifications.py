"""Notification system — alerts and reminders for Jeremy.

Channels:
    - ConsoleChannel   — print to stdout (always on)
    - EmailChannel     — Gmail SMTP with App Password
    - SMSChannel       — Twilio REST API (optional, no extra pip deps)
    - iMessageChannel  — macOS iMessage via osascript (optional)
    - PushChannel      — Generic push notification (webhook-based)

Features:
    - Quiet hours (no LOW/MEDIUM alerts between 10pm–7am unless CRITICAL)
    - Rate limiting — configurable cap per rolling window (default: 3 per 2 hours)
    - AlertRouter — turns CFO events into notifications automatically
    - DailyDigest — formats the CFO daily review into a clean HTML email
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
import subprocess
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from typing import Any, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)


# -----------------------------------------------------------------------
# Data types
# -----------------------------------------------------------------------

class Urgency(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_URGENCY_RANK = {Urgency.LOW: 0, Urgency.MEDIUM: 1, Urgency.HIGH: 2, Urgency.CRITICAL: 3}


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


# -----------------------------------------------------------------------
# Console channel (unchanged from original)
# -----------------------------------------------------------------------

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


# -----------------------------------------------------------------------
# Email channel — Gmail SMTP
# -----------------------------------------------------------------------

class EmailChannel:
    """Send notifications via Gmail SMTP.

    Requires:
        - GMAIL_APP_PASSWORD env var (16-char Google App Password)
        - GMAIL_FROM env var (your Gmail address, defaults to NOTIFY_EMAIL)
        - NOTIFY_EMAIL env var (recipient, defaults to GMAIL_FROM)

    Generate an App Password at: https://myaccount.google.com/apppasswords
    """

    def __init__(
        self,
        from_email: str | None = None,
        to_email: str | None = None,
        app_password: str | None = None,
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 587,
    ) -> None:
        self.from_email = from_email or os.getenv("GMAIL_FROM") or os.getenv("NOTIFY_EMAIL", "")
        self.to_email = to_email or os.getenv("NOTIFY_EMAIL") or self.from_email
        self.app_password = app_password or os.getenv("GMAIL_APP_PASSWORD", "")
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port

    @property
    def configured(self) -> bool:
        return bool(self.from_email and self.to_email and self.app_password)

    def send(self, notification: Notification) -> bool:
        if not self.configured:
            log.debug("EmailChannel: not configured, skipping")
            return False

        subject = f"[Guardian] {notification.title}"
        html = _notification_to_html(notification)

        msg = MIMEMultipart("alternative")
        msg["From"] = self.from_email
        msg["To"] = self.to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(notification.body, "plain"))
        msg.attach(MIMEText(html, "html"))

        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                server.starttls(context=ctx)
                server.login(self.from_email, self.app_password)
                server.sendmail(self.from_email, self.to_email, msg.as_string())
            log.info("Email sent: %s → %s", subject, self.to_email)
            return True
        except Exception:
            log.exception("EmailChannel: failed to send")
            return False


# -----------------------------------------------------------------------
# SMS channel — Twilio REST API (no extra pip dependency)
# -----------------------------------------------------------------------

class SMSChannel:
    """Send notifications via Twilio SMS.

    Requires:
        - TWILIO_ACCOUNT_SID env var
        - TWILIO_AUTH_TOKEN env var
        - TWILIO_FROM_NUMBER env var (your Twilio phone number, e.g. +1234567890)
        - NOTIFY_PHONE env var (recipient phone number, e.g. +1234567890)

    Uses urllib so no extra pip install needed.
    """

    API_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

    def __init__(
        self,
        account_sid: str | None = None,
        auth_token: str | None = None,
        from_number: str | None = None,
        to_number: str | None = None,
    ) -> None:
        self.account_sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token = auth_token or os.getenv("TWILIO_AUTH_TOKEN", "")
        self.from_number = from_number or os.getenv("TWILIO_FROM_NUMBER", "")
        self.to_number = to_number or os.getenv("NOTIFY_PHONE", "")

    @property
    def configured(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.from_number and self.to_number)

    def send(self, notification: Notification) -> bool:
        if not self.configured:
            log.debug("SMSChannel: not configured, skipping")
            return False

        body = f"[{notification.urgency.value.upper()}] {notification.title}\n{notification.body}"
        # Twilio SMS limit is 1600 chars
        if len(body) > 1600:
            body = body[:1597] + "..."

        url = self.API_URL.format(sid=self.account_sid)
        data = (
            f"To={self.to_number}"
            f"&From={self.from_number}"
            f"&Body={body}"
        ).encode()

        import base64
        creds = base64.b64encode(
            f"{self.account_sid}:{self.auth_token}".encode()
        ).decode()

        req = Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Basic {creds}")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
                log.info("SMS sent: SID=%s", result.get("sid", "unknown"))
                return True
        except (URLError, Exception):
            log.exception("SMSChannel: failed to send")
            return False


# -----------------------------------------------------------------------
# iMessage channel — macOS osascript (or placeholder on Linux)
# -----------------------------------------------------------------------

class iMessageChannel:
    """Send notifications via iMessage (macOS only).

    Requires:
        - IMESSAGE_RECIPIENT env var (phone number or Apple ID email)
        - macOS with Messages.app configured

    On non-macOS, this silently skips.
    """

    def __init__(self, recipient: str | None = None) -> None:
        self.recipient = recipient or os.getenv("IMESSAGE_RECIPIENT", "")

    @property
    def configured(self) -> bool:
        import platform
        return bool(self.recipient) and platform.system() == "Darwin"

    def send(self, notification: Notification) -> bool:
        if not self.configured:
            log.debug("iMessageChannel: not configured or not macOS, skipping")
            return False

        body = f"[{notification.urgency.value.upper()}] {notification.title}\n{notification.body}"
        if len(body) > 2000:
            body = body[:1997] + "..."

        safe_recipient = self.recipient.replace("\\", "\\\\").replace('"', '\\"')
        safe_body = body.replace("\\", "\\\\").replace('"', '\\"')
        script = (
            f'tell application "Messages"\n'
            f'  set targetService to 1st account whose service type = iMessage\n'
            f'  set targetBuddy to participant "{safe_recipient}" of targetService\n'
            f'  send "{safe_body}" to targetBuddy\n'
            f'end tell'
        )

        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, timeout=10, check=True,
            )
            log.info("iMessage sent to %s", self.recipient)
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            log.exception("iMessageChannel: failed to send")
            return False


# -----------------------------------------------------------------------
# Push notification channel — generic webhook
# -----------------------------------------------------------------------

class PushChannel:
    """Send push notifications via a webhook endpoint.

    Supports services like Pushover, ntfy.sh, or custom webhooks.

    Requires:
        - PUSH_WEBHOOK_URL env var (endpoint URL)
        - PUSH_API_KEY env var (optional auth token)
    """

    def __init__(
        self,
        webhook_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.webhook_url = webhook_url or os.getenv("PUSH_WEBHOOK_URL", "")
        self.api_key = api_key or os.getenv("PUSH_API_KEY", "")

    @property
    def configured(self) -> bool:
        return bool(self.webhook_url)

    def send(self, notification: Notification) -> bool:
        if not self.configured:
            log.debug("PushChannel: not configured, skipping")
            return False

        payload = json.dumps({
            "title": notification.title,
            "body": notification.body,
            "priority": notification.urgency.value,
            "source": notification.source,
            "timestamp": notification.timestamp,
        }).encode()

        req = Request(self.webhook_url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")

        try:
            with urlopen(req, timeout=10) as resp:
                log.info("Push notification sent: %s", resp.status)
                return True
        except (URLError, Exception):
            log.exception("PushChannel: failed to send")
            return False


# -----------------------------------------------------------------------
# Rate limiter — rolling window enforcement
# -----------------------------------------------------------------------

class NotificationRateLimiter:
    """Enforces a maximum number of notifications per rolling time window.

    Default: 3 notifications per 2-hour window.
    CRITICAL notifications always bypass the rate limit.
    """

    def __init__(
        self,
        max_count: int = 3,
        window: timedelta = timedelta(hours=2),
    ) -> None:
        self.max_count = max_count
        self.window = window
        self._timestamps: deque[datetime] = deque()
        self._suppressed: list[Notification] = []

    def _prune(self, now: datetime) -> None:
        cutoff = now - self.window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    def allow(self, notification: Notification) -> bool:
        """Check if notification is allowed under rate limit.

        CRITICAL notifications always pass through.
        """
        if notification.urgency == Urgency.CRITICAL:
            return True

        now = datetime.now(timezone.utc)
        self._prune(now)

        if len(self._timestamps) >= self.max_count:
            self._suppressed.append(notification)
            log.info(
                "Rate limit reached (%d/%d in %s) — suppressing: %s",
                len(self._timestamps), self.max_count, self.window, notification.title,
            )
            return False

        self._timestamps.append(now)
        return True

    def record(self) -> None:
        """Record a sent notification timestamp (called after send)."""
        pass  # Timestamps are recorded in allow()

    @property
    def suppressed_count(self) -> int:
        return len(self._suppressed)

    @property
    def remaining(self) -> int:
        self._prune(datetime.now(timezone.utc))
        return max(0, self.max_count - len(self._timestamps))

    def flush_suppressed(self) -> list[Notification]:
        """Return and clear suppressed notifications."""
        flushed = list(self._suppressed)
        self._suppressed.clear()
        return flushed

    def status(self) -> dict[str, Any]:
        """Current rate limiter status."""
        self._prune(datetime.now(timezone.utc))
        return {
            "max_per_window": self.max_count,
            "window_hours": self.window.total_seconds() / 3600,
            "sent_in_window": len(self._timestamps),
            "remaining": self.remaining,
            "suppressed": self.suppressed_count,
        }


# -----------------------------------------------------------------------
# Notification manager (extended with quiet hours + rate limiting)
# -----------------------------------------------------------------------

class NotificationManager:
    """Dispatches notifications through registered channels.

    Features:
        - Quiet hours: LOW and MEDIUM alerts held between quiet_start and quiet_end
        - Rate limiting: max notifications per rolling window (default 3 per 2 hours)
        - CRITICAL notifications always bypass both quiet hours and rate limits
    """

    def __init__(
        self,
        quiet_start: time = time(22, 0),   # 10:00 PM
        quiet_end: time = time(7, 0),      # 7:00 AM
        timezone_name: str = "America/Chicago",
        rate_limit_max: int = 3,
        rate_limit_window: timedelta = timedelta(hours=2),
    ) -> None:
        self._channels: list[NotificationChannel] = [ConsoleChannel()]
        self._history: list[Notification] = []
        self._held: list[Notification] = []
        self.quiet_start = quiet_start
        self.quiet_end = quiet_end
        self.timezone_name = timezone_name
        self.rate_limiter = NotificationRateLimiter(
            max_count=rate_limit_max,
            window=rate_limit_window,
        )

    def add_channel(self, channel: NotificationChannel) -> None:
        self._channels.append(channel)

    def _is_quiet_hours(self) -> bool:
        """Check if we're currently in quiet hours."""
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo(self.timezone_name)).time()
        except (ImportError, KeyError):
            now = datetime.now(timezone.utc).time()

        if self.quiet_start <= self.quiet_end:
            return self.quiet_start <= now <= self.quiet_end
        # Wraps midnight (e.g. 22:00 → 07:00)
        return now >= self.quiet_start or now <= self.quiet_end

    def notify(
        self,
        source: str,
        title: str,
        body: str,
        urgency: Urgency = Urgency.MEDIUM,
        metadata: dict[str, Any] | None = None,
    ) -> Notification:
        notification = Notification(
            source=source, title=title, body=body, urgency=urgency,
            metadata=metadata or {},
        )

        # Quiet hours: hold low/medium, let high/critical through
        if self._is_quiet_hours() and _URGENCY_RANK[urgency] < _URGENCY_RANK[Urgency.HIGH]:
            self._held.append(notification)
            self._history.append(notification)
            return notification

        # Rate limiting: suppress if over limit (CRITICAL always passes)
        if not self.rate_limiter.allow(notification):
            self._history.append(notification)
            return notification

        for channel in self._channels:
            try:
                channel.send(notification)
            except Exception:
                log.exception("Channel %s failed", type(channel).__name__)
        self._history.append(notification)
        return notification

    def flush_held(self) -> list[Notification]:
        """Send all held (quiet-hours) notifications now. Returns what was sent."""
        flushed = list(self._held)
        for notification in flushed:
            if not self.rate_limiter.allow(notification):
                continue
            for channel in self._channels:
                try:
                    channel.send(notification)
                except Exception:
                    log.exception("Channel %s failed during flush", type(channel).__name__)
        self._held.clear()
        return flushed

    def recent(self, limit: int = 10) -> list[Notification]:
        return self._history[-limit:]

    @property
    def held_count(self) -> int:
        return len(self._held)

    def rate_limit_status(self) -> dict[str, Any]:
        """Get current rate limiter status."""
        return self.rate_limiter.status()


# -----------------------------------------------------------------------
# HTML formatter
# -----------------------------------------------------------------------

_URGENCY_COLOR = {
    Urgency.LOW: "#3498DB",
    Urgency.MEDIUM: "#F39C12",
    Urgency.HIGH: "#E74C3C",
    Urgency.CRITICAL: "#C0392B",
}

_URGENCY_LABEL = {
    Urgency.LOW: "Info",
    Urgency.MEDIUM: "Alert",
    Urgency.HIGH: "Urgent",
    Urgency.CRITICAL: "CRITICAL",
}


def _notification_to_html(notification: Notification) -> str:
    color = _URGENCY_COLOR[notification.urgency]
    label = _URGENCY_LABEL[notification.urgency]
    body_html = notification.body.replace("\n", "<br>")
    return f"""\
<div style="font-family:Calibri,Arial,sans-serif;max-width:600px;margin:0 auto;">
  <div style="background:{color};color:#fff;padding:12px 16px;border-radius:6px 6px 0 0;">
    <span style="font-size:12px;opacity:0.8;">{label}</span>
    <h2 style="margin:4px 0 0;font-size:18px;">{notification.title}</h2>
  </div>
  <div style="background:#f8f9fa;padding:16px;border:1px solid #ddd;border-top:none;border-radius:0 0 6px 6px;">
    <p style="font-size:14px;color:#333;line-height:1.5;">{body_html}</p>
    <p style="font-size:11px;color:#888;margin-top:12px;">
      Source: {notification.source} &bull; {notification.timestamp[:19]}
    </p>
  </div>
</div>"""


# -----------------------------------------------------------------------
# Daily Digest — formats CFO daily_review into a clean email
# -----------------------------------------------------------------------

def format_daily_digest(review: dict[str, Any], net_worth: float = 0.0) -> tuple[str, str]:
    """Turn a CFO daily_review() dict into (subject, html_body).

    Returns a tuple of (subject_line, html_string) ready for email.
    """
    date = review.get("date", "today")
    status = review.get("overall_status", "unknown")
    message = review.get("overall_message", "")

    status_emoji = {"all_clear": "All Clear", "review": "Review", "needs_attention": "Action Needed"}.get(status, status)
    subject = f"Guardian Daily — {status_emoji} — {date}"

    # Build sections
    sections: list[str] = []

    # Net worth
    if net_worth:
        sections.append(f"""
    <div style="background:#D6E4F0;padding:12px 16px;border-radius:6px;margin-bottom:12px;">
      <span style="font-size:12px;color:#5B6770;">Net Worth</span><br>
      <span style="font-size:22px;font-weight:bold;color:#1F4E79;">${net_worth:,.2f}</span>
    </div>""")

    # Overall status
    status_color = {"all_clear": "#27AE60", "review": "#F39C12", "needs_attention": "#E74C3C"}.get(status, "#333")
    sections.append(f"""
    <div style="background:#fff;border-left:4px solid {status_color};padding:12px 16px;margin-bottom:12px;">
      <strong style="color:{status_color};">{status_emoji}</strong>
      <p style="margin:4px 0 0;color:#333;">{message}</p>
    </div>""")

    # Bills
    bills = review.get("bills", {})
    if bills.get("overdue", 0) > 0:
        sections.append(f"""
    <div style="background:#FCD5D5;padding:12px 16px;border-radius:6px;margin-bottom:12px;">
      <strong style="color:#C0392B;">Bills Overdue: {bills['overdue']}</strong>
      <span style="color:#666;"> &bull; Paid: {bills.get('paid', 0)} &bull; Pending: {bills.get('pending', 0)}</span>
    </div>""")
    elif bills:
        sections.append(f"""
    <div style="background:#D5F5E3;padding:12px 16px;border-radius:6px;margin-bottom:12px;">
      <strong style="color:#27AE60;">Bills: All on track</strong>
      <span style="color:#666;"> &bull; Paid: {bills.get('paid', 0)} &bull; Pending: {bills.get('pending', 0)}</span>
    </div>""")

    # Budget
    budget = review.get("budget", {})
    over = budget.get("over_budget", 0)
    warnings = budget.get("warnings", 0)
    on_track = budget.get("on_track", 0)
    if over > 0:
        sections.append(f"""
    <div style="background:#FCD5D5;padding:12px 16px;border-radius:6px;margin-bottom:12px;">
      <strong style="color:#C0392B;">Budget: {over} over limit</strong>
      <span style="color:#666;"> &bull; Warnings: {warnings} &bull; On track: {on_track}</span>
    </div>""")
    elif warnings > 0:
        sections.append(f"""
    <div style="background:#FEF9E7;padding:12px 16px;border-radius:6px;margin-bottom:12px;">
      <strong style="color:#E67E22;">Budget: {warnings} approaching limit</strong>
      <span style="color:#666;"> &bull; On track: {on_track}</span>
    </div>""")
    elif budget.get("results"):
        sections.append(f"""
    <div style="background:#D5F5E3;padding:12px 16px;border-radius:6px;margin-bottom:12px;">
      <strong style="color:#27AE60;">Budget: All on track ({on_track} categories)</strong>
    </div>""")

    # Budget detail table
    budget_results = budget.get("results", [])
    if budget_results:
        rows = ""
        for b in budget_results:
            pct = b.get("percent_used", 0)
            color = "#C0392B" if pct > 100 else "#E67E22" if pct >= 80 else "#27AE60"
            rows += f"""
        <tr>
          <td style="padding:6px 10px;border-bottom:1px solid #eee;">{b['label']}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;">${b['limit']:,.0f}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;">${b['spent']:,.0f}</td>
          <td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;color:{color};font-weight:bold;">{pct:.0f}%</td>
        </tr>"""
        sections.append(f"""
    <table style="width:100%;border-collapse:collapse;margin-bottom:12px;font-size:13px;">
      <tr style="background:#1F4E79;color:#fff;">
        <th style="padding:8px 10px;text-align:left;">Category</th>
        <th style="padding:8px 10px;text-align:right;">Budget</th>
        <th style="padding:8px 10px;text-align:right;">Spent</th>
        <th style="padding:8px 10px;text-align:right;">% Used</th>
      </tr>{rows}
    </table>""")

    # Transaction flags
    tx = review.get("transactions", {})
    tx_warnings = tx.get("warnings", 0)
    if tx_warnings > 0:
        flags = tx.get("flags", [])
        flag_items = "".join(f"<li style='margin-bottom:4px;'>{f.get('reason', '')} — {f.get('description', '')}: ${abs(f.get('amount', 0)):,.2f}</li>" for f in flags[:5])
        sections.append(f"""
    <div style="background:#FEF9E7;padding:12px 16px;border-radius:6px;margin-bottom:12px;">
      <strong style="color:#E67E22;">Transaction Flags: {tx_warnings}</strong>
      <ul style="margin:8px 0 0;padding-left:20px;color:#333;font-size:13px;">
        {flag_items}
      </ul>
    </div>""")

    body_sections = "\n".join(sections)
    html = f"""\
<div style="font-family:Calibri,Arial,sans-serif;max-width:600px;margin:0 auto;">
  <div style="background:#1F4E79;color:#fff;padding:16px 20px;border-radius:8px 8px 0 0;">
    <h1 style="margin:0;font-size:20px;">Guardian One — Daily Review</h1>
    <p style="margin:4px 0 0;font-size:13px;opacity:0.8;">{date}</p>
  </div>
  <div style="background:#f8f9fa;padding:16px;border:1px solid #ddd;border-top:none;border-radius:0 0 8px 8px;">
    {body_sections}
    <p style="font-size:11px;color:#999;margin-top:16px;text-align:center;">
      Sent by Guardian One &bull; {review.get('generated_at', '')[:19]}
    </p>
  </div>
</div>"""

    return subject, html


# -----------------------------------------------------------------------
# AlertRouter — turns CFO data into notifications
# -----------------------------------------------------------------------

class AlertRouter:
    """Routes CFO financial events to the notification manager.

    Call route_daily_review() after running cfo.daily_review() to
    automatically fire off the right alerts.
    """

    def __init__(self, manager: NotificationManager) -> None:
        self.manager = manager

    def route_daily_review(
        self,
        review: dict[str, Any],
        net_worth: float = 0.0,
        send_digest: bool = True,
    ) -> list[Notification]:
        """Process a CFO daily_review dict and fire appropriate alerts.

        Returns the list of notifications that were created.
        """
        fired: list[Notification] = []

        # 1. Overdue bills → HIGH
        bills = review.get("bills", {})
        overdue = bills.get("overdue", 0)
        if overdue > 0:
            bill_results = bills.get("results", [])
            overdue_names = [
                b["bill"] for b in bill_results if b.get("status") == "overdue_unverified"
            ]
            body = f"{overdue} bill(s) overdue"
            if overdue_names:
                body += ": " + ", ".join(overdue_names[:5])
            n = self.manager.notify("CFO", "Bills Overdue", body, Urgency.HIGH)
            fired.append(n)

        # 2. Over-budget categories → HIGH
        budget = review.get("budget", {})
        over_count = budget.get("over_budget", 0)
        if over_count > 0:
            over_items = [
                b for b in budget.get("results", []) if b.get("status") == "over"
            ]
            lines = [
                f"  {b['label']}: ${b['spent']:,.0f} / ${b['limit']:,.0f} ({b['percent_used']:.0f}%)"
                for b in over_items[:5]
            ]
            body = f"{over_count} category(s) over budget:\n" + "\n".join(lines)
            n = self.manager.notify("CFO", "Over Budget", body, Urgency.HIGH)
            fired.append(n)

        # 3. Budget warnings (80–100%) → MEDIUM
        warn_count = budget.get("warnings", 0)
        if warn_count > 0:
            warn_items = [
                b for b in budget.get("results", []) if b.get("status") == "warning"
            ]
            lines = [
                f"  {b['label']}: {b['percent_used']:.0f}% used (${b['remaining']:,.0f} left)"
                for b in warn_items[:5]
            ]
            body = f"{warn_count} budget(s) approaching limit:\n" + "\n".join(lines)
            n = self.manager.notify("CFO", "Budget Warning", body, Urgency.MEDIUM)
            fired.append(n)

        # 4. Transaction flags → MEDIUM
        tx = review.get("transactions", {})
        if tx.get("warnings", 0) > 0:
            flags = tx.get("flags", [])
            lines = [
                f"  {f.get('reason', 'unknown')}: {f.get('description', '?')} (${abs(f.get('amount', 0)):,.2f})"
                for f in flags[:5]
            ]
            body = f"{tx['warnings']} flagged transaction(s):\n" + "\n".join(lines)
            n = self.manager.notify("CFO", "Transaction Flags", body, Urgency.MEDIUM)
            fired.append(n)

        # 5. Daily digest email → LOW
        if send_digest:
            subject, html = format_daily_digest(review, net_worth)
            n = self.manager.notify(
                "CFO", subject, html,
                Urgency.LOW,
                metadata={"type": "daily_digest", "html": html},
            )
            fired.append(n)

        return fired

    def route_budget_alerts(self, alerts: list[str]) -> list[Notification]:
        """Fire notifications for plain-text budget alerts from cfo.budget_alerts()."""
        fired: list[Notification] = []
        for alert in alerts:
            urgency = Urgency.HIGH if alert.startswith("OVER BUDGET") else Urgency.MEDIUM
            n = self.manager.notify("CFO", "Budget Alert", alert, urgency)
            fired.append(n)
        return fired

    def route_bill_reminder(self, bill_name: str, amount: float, due_date: str, overdue: bool = False) -> Notification:
        """Fire a single bill reminder."""
        urgency = Urgency.HIGH if overdue else Urgency.MEDIUM
        title = "Bill Overdue" if overdue else "Bill Due Soon"
        body = f"{bill_name}: ${amount:,.2f} — due {due_date}"
        return self.manager.notify("CFO", title, body, urgency)


# -----------------------------------------------------------------------
# Factory — build a fully-configured notification stack from env vars
# -----------------------------------------------------------------------

def build_notification_stack(
    enable_email: bool = True,
    enable_sms: bool = True,
    enable_imessage: bool = True,
    enable_push: bool = True,
    quiet_start: time = time(22, 0),
    quiet_end: time = time(7, 0),
    timezone_name: str = "America/Chicago",
    rate_limit_max: int = 3,
    rate_limit_window_hours: float = 2.0,
) -> tuple[NotificationManager, AlertRouter]:
    """Create a NotificationManager + AlertRouter wired to all configured channels.

    Channels are added only if their credentials are present in env vars.
    Console is always active.

    Rate limiting defaults to 3 notifications per 2-hour rolling window.
    CRITICAL notifications always bypass the rate limit.

    Returns (manager, router).
    """
    mgr = NotificationManager(
        quiet_start=quiet_start,
        quiet_end=quiet_end,
        timezone_name=timezone_name,
        rate_limit_max=rate_limit_max,
        rate_limit_window=timedelta(hours=rate_limit_window_hours),
    )

    if enable_email:
        email = EmailChannel()
        if email.configured:
            mgr.add_channel(email)
            log.info("EmailChannel configured → %s", email.to_email)

    if enable_sms:
        sms = SMSChannel()
        if sms.configured:
            mgr.add_channel(sms)
            log.info("SMSChannel configured → %s", sms.to_number)

    if enable_imessage:
        imsg = iMessageChannel()
        if imsg.configured:
            mgr.add_channel(imsg)
            log.info("iMessageChannel configured → %s", imsg.recipient)

    if enable_push:
        push = PushChannel()
        if push.configured:
            mgr.add_channel(push)
            log.info("PushChannel configured → %s", push.webhook_url)

    router = AlertRouter(mgr)
    return mgr, router
