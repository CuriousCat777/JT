"""Gmail integration — OAuth2-based Gmail API provider.

Provides:
    - OAuth2 authentication via google-auth-oauthlib
    - Inbox monitoring (unread message listing)
    - Email search by query (from, subject, has:attachment, etc.)
    - Attachment downloading (for CSV processing)
    - Message detail retrieval

Setup:
    1. Create a Google Cloud project with Gmail API enabled
    2. Download OAuth credentials to config/google_credentials.json
    3. Run once interactively to complete the OAuth consent flow
    4. Token is cached in config/gmail_token.json for subsequent use
"""

from __future__ import annotations

import abc
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Gmail IDs are alphanumeric (hex or base64url-safe characters)
_SAFE_GMAIL_ID = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


@dataclass
class EmailMessage:
    """Represents a parsed Gmail message."""
    message_id: str
    thread_id: str
    subject: str
    sender: str
    recipient: str
    date: str
    snippet: str
    labels: list[str] = field(default_factory=list)
    body_text: str = ""
    attachments: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Attachment:
    """An email attachment."""
    filename: str
    mime_type: str
    size: int
    attachment_id: str
    message_id: str
    data: bytes = b""


class GmailProvider:
    """Gmail API integration using OAuth2.

    Authentication flow:
        1. On first use, opens browser for Google consent
        2. Stores refresh token in config/gmail_token.json
        3. Auto-refreshes access token on subsequent calls

    This provider uses the google-auth-oauthlib and google-api-python-client
    libraries when available, falling back to direct HTTP for environments
    where those aren't installed.
    """

    def __init__(
        self,
        credentials_path: str | Path | None = None,
        token_path: str | Path | None = None,
        user_email: str = "me",
    ) -> None:
        self._credentials_path = Path(credentials_path) if credentials_path else Path("config/google_credentials.json")
        self._token_path = Path(token_path) if token_path else Path("config/gmail_token.json")
        self._user = user_email
        self._access_token: str | None = None
        self._authenticated = False

    @property
    def has_credentials(self) -> bool:
        """Check if OAuth credentials file exists."""
        return self._credentials_path.exists()

    @property
    def has_token(self) -> bool:
        """Check if a cached token exists."""
        return self._token_path.exists()

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    def authenticate(self) -> bool:
        """Authenticate with Gmail API.

        Attempts to load a cached token first. If unavailable,
        checks for google-auth-oauthlib to run the interactive flow.
        Returns True if authentication succeeds.
        """
        # Try loading cached token
        if self._load_cached_token():
            self._authenticated = True
            return True

        # Try google-auth-oauthlib interactive flow
        if self._credentials_path.exists():
            try:
                return self._oauth2_interactive_flow()
            except ImportError:
                pass
            except Exception:
                pass

        # Check environment variable for token
        token = os.environ.get("GMAIL_ACCESS_TOKEN")
        if token:
            self._access_token = token
            self._authenticated = True
            return True

        return False

    def _load_cached_token(self) -> bool:
        """Load and refresh a cached OAuth token."""
        if not self._token_path.exists():
            return False
        try:
            token_data = json.loads(self._token_path.read_text())
            # Try using google.oauth2.credentials if available
            try:
                from google.oauth2.credentials import Credentials
                creds = Credentials.from_authorized_user_info(token_data, GMAIL_SCOPES)
                if creds.valid:
                    self._access_token = creds.token
                    return True
                if creds.expired and creds.refresh_token:
                    from google.auth.transport.requests import Request
                    creds.refresh(Request())
                    self._access_token = creds.token
                    self._save_token(creds)
                    return True
            except ImportError:
                # Fall back to manual refresh
                if "access_token" in token_data:
                    self._access_token = token_data["access_token"]
                    return True
                if "refresh_token" in token_data and "client_id" in token_data:
                    return self._manual_refresh(token_data)
        except (json.JSONDecodeError, KeyError):
            pass
        return False

    def _manual_refresh(self, token_data: dict[str, Any]) -> bool:
        """Manually refresh an OAuth2 token using urllib."""
        try:
            data = urllib.parse.urlencode({
                "client_id": token_data["client_id"],
                "client_secret": token_data["client_secret"],
                "refresh_token": token_data["refresh_token"],
                "grant_type": "refresh_token",
            }).encode()
            req = urllib.request.Request(
                "https://oauth2.googleapis.com/token",
                data=data,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                self._access_token = result["access_token"]
                token_data["access_token"] = result["access_token"]
                self._token_path.write_text(json.dumps(token_data, indent=2))
                return True
        except Exception:
            return False

    def _oauth2_interactive_flow(self) -> bool:
        """Run the interactive OAuth2 consent flow."""
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(
            str(self._credentials_path), GMAIL_SCOPES
        )
        creds = flow.run_local_server(port=0)
        self._access_token = creds.token
        self._save_token(creds)
        self._authenticated = True
        return True

    def _save_token(self, creds: Any) -> None:
        """Persist OAuth2 credentials to disk."""
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(creds.to_json())

    # ------------------------------------------------------------------
    # Gmail API operations
    # ------------------------------------------------------------------

    def _api_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Make an authenticated Gmail API request."""
        if not self._access_token:
            return None

        url = f"{GMAIL_API_BASE}/users/{self._user}/{endpoint}"
        if params:
            url += "?" + urllib.parse.urlencode(params)

        req = urllib.request.Request(
            url,
            method=method,
            headers={
                "Authorization": f"Bearer {self._access_token}",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            error_body = ""
            if e.fp:
                try:
                    error_body = e.read().decode()
                except Exception:
                    pass
            return {"error": True, "status": e.code, "details": error_body}
        except urllib.error.URLError as e:
            return {"error": True, "status": 0, "details": str(e.reason)}

    def list_messages(
        self,
        query: str = "",
        max_results: int = 10,
        label_ids: list[str] | None = None,
    ) -> list[dict[str, str]]:
        """List messages matching a query.

        Args:
            query: Gmail search query (same syntax as Gmail search bar).
            max_results: Maximum messages to return.
            label_ids: Filter by label IDs (e.g., ["INBOX", "UNREAD"]).

        Returns:
            List of dicts with 'id' and 'threadId' keys.
        """
        params: dict[str, str] = {"maxResults": str(max_results)}
        if query:
            params["q"] = query
        if label_ids:
            params["labelIds"] = ",".join(label_ids)

        result = self._api_request("messages", params=params)
        if result is None or result.get("error"):
            return []
        return result.get("messages", [])

    def get_message(self, message_id: str, format: str = "full") -> EmailMessage | None:
        """Fetch a full message by ID.

        Args:
            message_id: The Gmail message ID.
            format: 'full', 'metadata', or 'minimal'.

        Returns:
            Parsed EmailMessage or None.
        """
        if not _SAFE_GMAIL_ID.match(message_id):
            return None
        result = self._api_request(
            f"messages/{message_id}",
            params={"format": format},
        )
        if result is None or result.get("error"):
            return None
        return self._parse_message(result)

    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Download an attachment by ID.

        Returns:
            Raw bytes of the attachment data.
        """
        if not _SAFE_GMAIL_ID.match(message_id) or not _SAFE_GMAIL_ID.match(attachment_id):
            return b""
        result = self._api_request(
            f"messages/{message_id}/attachments/{attachment_id}"
        )
        if result is None or result.get("error"):
            return b""
        data_b64 = result.get("data", "")
        # Gmail uses URL-safe base64
        return base64.urlsafe_b64decode(data_b64 + "==")

    def search_messages(self, query: str, max_results: int = 20) -> list[EmailMessage]:
        """Search for messages and return fully parsed results.

        This is a convenience method that combines list_messages + get_message.
        """
        message_refs = self.list_messages(query=query, max_results=max_results)
        messages: list[EmailMessage] = []
        for ref in message_refs:
            msg = self.get_message(ref["id"])
            if msg:
                messages.append(msg)
        return messages

    def get_unread_count(self) -> int:
        """Get the count of unread messages in INBOX."""
        result = self._api_request("labels/UNREAD")
        if result and not result.get("error"):
            return result.get("messagesUnread", result.get("threadsUnread", 0))
        # Fallback: list unread messages
        msgs = self.list_messages(query="is:unread", max_results=100)
        return len(msgs)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_message(raw: dict[str, Any]) -> EmailMessage:
        """Parse a raw Gmail API message response into an EmailMessage."""
        headers = {}
        payload = raw.get("payload", {})
        for header in payload.get("headers", []):
            headers[header["name"].lower()] = header["value"]

        # Extract attachments info
        attachments = []
        for part in payload.get("parts", []):
            if part.get("filename"):
                attachments.append({
                    "filename": part["filename"],
                    "mime_type": part.get("mimeType", ""),
                    "size": part.get("body", {}).get("size", 0),
                    "attachment_id": part.get("body", {}).get("attachmentId", ""),
                })
            # Check nested parts (multipart messages)
            for sub_part in part.get("parts", []):
                if sub_part.get("filename"):
                    attachments.append({
                        "filename": sub_part["filename"],
                        "mime_type": sub_part.get("mimeType", ""),
                        "size": sub_part.get("body", {}).get("size", 0),
                        "attachment_id": sub_part.get("body", {}).get("attachmentId", ""),
                    })

        # Extract body text
        body_text = ""
        if payload.get("body", {}).get("data"):
            body_text = base64.urlsafe_b64decode(
                payload["body"]["data"] + "=="
            ).decode(errors="replace")
        else:
            for part in payload.get("parts", []):
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body_text = base64.urlsafe_b64decode(
                        part["body"]["data"] + "=="
                    ).decode(errors="replace")
                    break

        return EmailMessage(
            message_id=raw.get("id", ""),
            thread_id=raw.get("threadId", ""),
            subject=headers.get("subject", ""),
            sender=headers.get("from", ""),
            recipient=headers.get("to", ""),
            date=headers.get("date", ""),
            snippet=raw.get("snippet", ""),
            labels=raw.get("labelIds", []),
            body_text=body_text,
            attachments=attachments,
            raw=raw,
        )


class RocketMoneyCSVChecker:
    """Checks Gmail for Rocket Money CSV export emails.

    Searches for emails from Rocket Money that contain CSV attachments,
    targeting jeremytabernero@gmail.com.
    """

    # Known Rocket Money sender addresses
    ROCKET_MONEY_SENDERS = [
        "noreply@rocketmoney.com",
        "support@rocketmoney.com",
        "export@rocketmoney.com",
        "no-reply@rocketmoney.com",
        "notifications@rocketmoney.com",
        "hello@rocketmoney.com",
    ]

    def __init__(self, gmail: GmailProvider) -> None:
        self._gmail = gmail

    def build_search_query(
        self,
        recipient: str = "jeremytabernero@gmail.com",
        days_back: int | None = None,
    ) -> str:
        """Build a Gmail search query for Rocket Money CSV emails.

        Args:
            recipient: Target email address.
            days_back: Limit search to recent N days (None = all time).

        Returns:
            Gmail search query string.
        """
        parts = [
            "(from:rocketmoney.com OR from:rocket-money.com OR from:truebill.com)",
            f"to:{recipient}",
            "(filename:csv OR filename:CSV)",
        ]
        if days_back:
            parts.append(f"newer_than:{days_back}d")
        return " ".join(parts)

    def check(
        self,
        recipient: str = "jeremytabernero@gmail.com",
        days_back: int | None = 30,
        max_results: int = 20,
    ) -> dict[str, Any]:
        """Check if Rocket Money CSV has been sent to the specified email.

        Returns a dict with:
            - found: bool — whether any matching emails were found
            - count: int — number of matching emails
            - emails: list — details of matching emails
            - query: str — the Gmail query used
            - checked_at: str — timestamp
        """
        if not self._gmail.is_authenticated:
            return {
                "found": False,
                "count": 0,
                "emails": [],
                "query": "",
                "error": "Gmail not authenticated. Run OAuth2 setup first.",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

        query = self.build_search_query(recipient=recipient, days_back=days_back)
        messages = self._gmail.search_messages(query=query, max_results=max_results)

        email_details = []
        for msg in messages:
            csv_attachments = [
                att for att in msg.attachments
                if att.get("filename", "").lower().endswith(".csv")
            ]
            email_details.append({
                "message_id": msg.message_id,
                "subject": msg.subject,
                "sender": msg.sender,
                "date": msg.date,
                "snippet": msg.snippet,
                "csv_attachments": [
                    {"filename": a["filename"], "size": a["size"]}
                    for a in csv_attachments
                ],
            })

        return {
            "found": len(messages) > 0,
            "count": len(messages),
            "emails": email_details,
            "query": query,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def download_latest_csv(
        self,
        recipient: str = "jeremytabernero@gmail.com",
        save_dir: str | Path = "data",
    ) -> dict[str, Any]:
        """Download the most recent Rocket Money CSV attachment.

        Returns:
            Dict with 'success', 'path' (if saved), and details.
        """
        if not self._gmail.is_authenticated:
            return {"success": False, "error": "Gmail not authenticated."}

        query = self.build_search_query(recipient=recipient, days_back=90)
        messages = self._gmail.search_messages(query=query, max_results=5)

        for msg in messages:
            for att in msg.attachments:
                if att.get("filename", "").lower().endswith(".csv") and att.get("attachment_id"):
                    data = self._gmail.get_attachment(msg.message_id, att["attachment_id"])
                    if data:
                        save_path = Path(save_dir)
                        save_path.mkdir(parents=True, exist_ok=True)
                        filepath = save_path / att["filename"]
                        filepath.write_bytes(data)
                        return {
                            "success": True,
                            "path": str(filepath),
                            "filename": att["filename"],
                            "size": len(data),
                            "from_email": msg.sender,
                            "date": msg.date,
                            "subject": msg.subject,
                        }

        return {
            "success": False,
            "error": "No CSV attachments found from Rocket Money.",
        }
