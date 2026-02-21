import smtplib
from email.message import EmailMessage

from .config import settings


def send_email(subject: str, body: str):
    """Send an email notification. No-op if SMTP is not configured."""
    if not settings.smtp_host or not settings.smtp_from or not settings.smtp_to:
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = settings.smtp_to
    msg.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        if settings.smtp_user and settings.smtp_pass:
            server.login(settings.smtp_user, settings.smtp_pass)
        server.send_message(msg)
