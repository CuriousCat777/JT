"""Comprehensive tests for guardian_one/integrations/gmail_sync.py.

Coverage targets:
    - EmailMessage and Attachment dataclasses
    - GmailProvider: properties, authenticate(), _load_cached_token(),
      _manual_refresh(), _api_request(), list_messages(), get_message(),
      get_attachment(), search_messages(), get_unread_count(), _parse_message()
    - RocketMoneyCSVChecker: build_search_query(), check(), download_latest_csv()

All external I/O (urllib.request.urlopen) is mocked. No real network calls.
"""

from __future__ import annotations

import base64
import io
import json
import os
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from guardian_one.integrations.gmail_sync import (
    GMAIL_API_BASE,
    GMAIL_SCOPES,
    Attachment,
    EmailMessage,
    GmailProvider,
    RocketMoneyCSVChecker,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_urlopen_response(payload: dict | bytes, status: int = 200) -> MagicMock:
    """Return a mock context manager that mimics urllib.request.urlopen."""
    if isinstance(payload, dict):
        body = json.dumps(payload).encode()
    else:
        body = payload

    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _b64(text: str) -> str:
    """Return URL-safe base64 encoding of text (no padding)."""
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _make_raw_message(
    msg_id: str = "msg1",
    thread_id: str = "thread1",
    subject: str = "Test Subject",
    sender: str = "sender@example.com",
    recipient: str = "me@example.com",
    date: str = "Mon, 01 Jan 2024 12:00:00 +0000",
    snippet: str = "A short snippet",
    labels: list[str] | None = None,
    body_data: str | None = None,
    parts: list[dict] | None = None,
) -> dict:
    """Build a minimal raw Gmail API message dict."""
    headers = [
        {"name": "Subject", "value": subject},
        {"name": "From", "value": sender},
        {"name": "To", "value": recipient},
        {"name": "Date", "value": date},
    ]
    payload: dict = {"headers": headers}
    if body_data is not None:
        payload["body"] = {"data": _b64(body_data)}
    if parts is not None:
        payload["parts"] = parts
    return {
        "id": msg_id,
        "threadId": thread_id,
        "snippet": snippet,
        "labelIds": labels or [],
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_api_base_url(self):
        assert GMAIL_API_BASE == "https://gmail.googleapis.com/gmail/v1"

    def test_scopes_contains_readonly(self):
        assert "https://www.googleapis.com/auth/gmail.readonly" in GMAIL_SCOPES

    def test_scopes_is_list(self):
        assert isinstance(GMAIL_SCOPES, list)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

class TestEmailMessage:
    def test_required_fields(self):
        msg = EmailMessage(
            message_id="1",
            thread_id="t1",
            subject="Hi",
            sender="a@b.com",
            recipient="c@d.com",
            date="2024-01-01",
            snippet="snip",
        )
        assert msg.message_id == "1"
        assert msg.thread_id == "t1"
        assert msg.subject == "Hi"

    def test_defaults(self):
        msg = EmailMessage(
            message_id="x",
            thread_id="y",
            subject="",
            sender="",
            recipient="",
            date="",
            snippet="",
        )
        assert msg.labels == []
        assert msg.body_text == ""
        assert msg.attachments == []
        assert msg.raw == {}

    def test_labels_are_independent_per_instance(self):
        m1 = EmailMessage("a", "b", "", "", "", "", "")
        m2 = EmailMessage("c", "d", "", "", "", "", "")
        m1.labels.append("INBOX")
        assert "INBOX" not in m2.labels


class TestAttachment:
    def test_fields(self):
        att = Attachment(
            filename="report.csv",
            mime_type="text/csv",
            size=1024,
            attachment_id="att1",
            message_id="msg1",
        )
        assert att.filename == "report.csv"
        assert att.data == b""

    def test_with_data(self):
        att = Attachment(
            filename="f.csv", mime_type="text/csv", size=5,
            attachment_id="a", message_id="m", data=b"hello",
        )
        assert att.data == b"hello"


# ---------------------------------------------------------------------------
# GmailProvider — properties
# ---------------------------------------------------------------------------

class TestGmailProviderProperties:
    def test_has_credentials_false_when_missing(self, tmp_path):
        gp = GmailProvider(
            credentials_path=tmp_path / "creds.json",
            token_path=tmp_path / "token.json",
        )
        assert gp.has_credentials is False

    def test_has_credentials_true_when_present(self, tmp_path):
        creds = tmp_path / "creds.json"
        creds.write_text("{}")
        gp = GmailProvider(credentials_path=creds, token_path=tmp_path / "token.json")
        assert gp.has_credentials is True

    def test_has_token_false_when_missing(self, tmp_path):
        gp = GmailProvider(
            credentials_path=tmp_path / "creds.json",
            token_path=tmp_path / "token.json",
        )
        assert gp.has_token is False

    def test_has_token_true_when_present(self, tmp_path):
        token = tmp_path / "token.json"
        token.write_text("{}")
        gp = GmailProvider(credentials_path=tmp_path / "creds.json", token_path=token)
        assert gp.has_token is True

    def test_is_authenticated_initially_false(self, tmp_path):
        gp = GmailProvider(
            credentials_path=tmp_path / "creds.json",
            token_path=tmp_path / "token.json",
        )
        assert gp.is_authenticated is False

    def test_default_paths_used_when_none(self):
        gp = GmailProvider()
        assert gp._credentials_path == Path("config/google_credentials.json")
        assert gp._token_path == Path("config/gmail_token.json")

    def test_custom_user_email(self, tmp_path):
        gp = GmailProvider(
            credentials_path=tmp_path / "c.json",
            token_path=tmp_path / "t.json",
            user_email="custom@example.com",
        )
        assert gp._user == "custom@example.com"


# ---------------------------------------------------------------------------
# GmailProvider — _load_cached_token (ImportError / manual path)
# ---------------------------------------------------------------------------

class TestLoadCachedToken:
    def test_returns_false_when_no_token_file(self, tmp_path):
        gp = GmailProvider(token_path=tmp_path / "token.json")
        assert gp._load_cached_token() is False

    def test_returns_false_on_invalid_json(self, tmp_path):
        token = tmp_path / "token.json"
        token.write_text("NOT_JSON")
        gp = GmailProvider(token_path=token)
        assert gp._load_cached_token() is False

    def test_uses_access_token_from_file_when_google_auth_unavailable(self, tmp_path):
        token = tmp_path / "token.json"
        token.write_text(json.dumps({"access_token": "tok123"}))
        gp = GmailProvider(token_path=token)

        # Force ImportError for google.oauth2.credentials
        with patch.dict("sys.modules", {"google.oauth2.credentials": None,
                                         "google.oauth2": None}):
            result = gp._load_cached_token()

        assert result is True
        assert gp._access_token == "tok123"

    def test_calls_manual_refresh_when_refresh_token_present(self, tmp_path):
        token_data = {
            "refresh_token": "rtoken",
            "client_id": "cid",
            "client_secret": "csec",
        }
        token = tmp_path / "token.json"
        token.write_text(json.dumps(token_data))
        gp = GmailProvider(token_path=token)

        with patch.dict("sys.modules", {"google.oauth2.credentials": None,
                                         "google.oauth2": None}):
            with patch.object(gp, "_manual_refresh", return_value=True) as mock_refresh:
                result = gp._load_cached_token()

        mock_refresh.assert_called_once_with(token_data)
        assert result is True


# ---------------------------------------------------------------------------
# GmailProvider — _manual_refresh
# ---------------------------------------------------------------------------

class TestManualRefresh:
    def test_successful_refresh_sets_access_token(self, tmp_path):
        token = tmp_path / "token.json"
        token_data = {
            "client_id": "cid",
            "client_secret": "csec",
            "refresh_token": "rtoken",
        }
        token.write_text(json.dumps(token_data))
        gp = GmailProvider(token_path=token)
        mock_resp = _make_urlopen_response({"access_token": "new_token_xyz"})

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = gp._manual_refresh(token_data)

        assert result is True
        assert gp._access_token == "new_token_xyz"

    def test_updates_token_file_after_refresh(self, tmp_path):
        token = tmp_path / "token.json"
        token_data = {
            "client_id": "cid",
            "client_secret": "csec",
            "refresh_token": "rtoken",
        }
        token.write_text(json.dumps(token_data))
        gp = GmailProvider(token_path=token)
        mock_resp = _make_urlopen_response({"access_token": "updated_token"})

        with patch("urllib.request.urlopen", return_value=mock_resp):
            gp._manual_refresh(token_data)

        saved = json.loads(token.read_text())
        assert saved["access_token"] == "updated_token"

    def test_returns_false_on_network_error(self, tmp_path):
        token = tmp_path / "token.json"
        gp = GmailProvider(token_path=token)

        with patch("urllib.request.urlopen", side_effect=Exception("network down")):
            result = gp._manual_refresh({
                "client_id": "x", "client_secret": "y", "refresh_token": "z",
            })

        assert result is False


# ---------------------------------------------------------------------------
# GmailProvider — authenticate()
# ---------------------------------------------------------------------------

class TestAuthenticate:
    def test_authenticate_via_cached_token(self, tmp_path):
        token = tmp_path / "token.json"
        token.write_text(json.dumps({"access_token": "cached_tok"}))
        gp = GmailProvider(token_path=token)

        with patch.dict("sys.modules", {"google.oauth2.credentials": None,
                                         "google.oauth2": None}):
            result = gp.authenticate()

        assert result is True
        assert gp.is_authenticated is True
        assert gp._access_token == "cached_tok"

    def test_authenticate_via_env_var_when_no_token_no_creds(self, tmp_path):
        gp = GmailProvider(
            credentials_path=tmp_path / "creds.json",
            token_path=tmp_path / "token.json",
        )
        with patch.dict(os.environ, {"GMAIL_ACCESS_TOKEN": "env_token_abc"}):
            result = gp.authenticate()

        assert result is True
        assert gp._access_token == "env_token_abc"
        assert gp.is_authenticated is True

    def test_authenticate_returns_false_when_nothing_available(self, tmp_path):
        gp = GmailProvider(
            credentials_path=tmp_path / "creds.json",
            token_path=tmp_path / "token.json",
        )
        env_without_token = {k: v for k, v in os.environ.items() if k != "GMAIL_ACCESS_TOKEN"}
        with patch.dict(os.environ, env_without_token, clear=True):
            result = gp.authenticate()

        assert result is False
        assert gp.is_authenticated is False

    def test_authenticate_env_var_not_used_when_token_already_loaded(self, tmp_path):
        token = tmp_path / "token.json"
        token.write_text(json.dumps({"access_token": "cached_tok"}))
        gp = GmailProvider(token_path=token)

        with patch.dict(os.environ, {"GMAIL_ACCESS_TOKEN": "env_token"}):
            with patch.dict("sys.modules", {"google.oauth2.credentials": None,
                                             "google.oauth2": None}):
                gp.authenticate()

        # Cached token takes priority
        assert gp._access_token == "cached_tok"


# ---------------------------------------------------------------------------
# GmailProvider — _api_request
# ---------------------------------------------------------------------------

class TestApiRequest:
    def _authenticated_provider(self, tmp_path) -> GmailProvider:
        gp = GmailProvider(
            credentials_path=tmp_path / "c.json",
            token_path=tmp_path / "t.json",
        )
        gp._access_token = "test_access_token"
        return gp

    def test_returns_none_when_no_access_token(self, tmp_path):
        gp = GmailProvider(credentials_path=tmp_path / "c.json",
                           token_path=tmp_path / "t.json")
        result = gp._api_request("messages")
        assert result is None

    def test_builds_correct_url_and_returns_json(self, tmp_path):
        gp = self._authenticated_provider(tmp_path)
        payload = {"messages": [{"id": "1", "threadId": "t1"}]}
        mock_resp = _make_urlopen_response(payload)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            result = gp._api_request("messages", params={"q": "is:unread"})

        assert result == payload
        called_url = mock_open.call_args[0][0].full_url
        assert "messages" in called_url
        assert "q=is%3Aunread" in called_url

    def test_includes_bearer_auth_header(self, tmp_path):
        gp = self._authenticated_provider(tmp_path)
        mock_resp = _make_urlopen_response({})

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            gp._api_request("labels/UNREAD")

        req = mock_open.call_args[0][0]
        assert req.get_header("Authorization") == "Bearer test_access_token"

    def test_handles_http_error(self, tmp_path):
        gp = self._authenticated_provider(tmp_path)
        http_err = urllib.error.HTTPError(
            url="http://x", code=401, msg="Unauthorized",
            hdrs={}, fp=io.BytesIO(b"auth failed"),  # type: ignore[arg-type]
        )

        with patch("urllib.request.urlopen", side_effect=http_err):
            result = gp._api_request("messages")

        assert result is not None
        assert result["error"] is True
        assert result["status"] == 401

    def test_handles_url_error(self, tmp_path):
        gp = self._authenticated_provider(tmp_path)
        url_err = urllib.error.URLError(reason="Name or service not known")

        with patch("urllib.request.urlopen", side_effect=url_err):
            result = gp._api_request("messages")

        assert result is not None
        assert result["error"] is True
        assert result["status"] == 0


# ---------------------------------------------------------------------------
# GmailProvider — list_messages
# ---------------------------------------------------------------------------

class TestListMessages:
    def _make_provider(self, tmp_path) -> GmailProvider:
        gp = GmailProvider(credentials_path=tmp_path / "c.json",
                           token_path=tmp_path / "t.json")
        gp._access_token = "tok"
        return gp

    def test_returns_messages_list(self, tmp_path):
        gp = self._make_provider(tmp_path)
        payload = {"messages": [{"id": "a", "threadId": "ta"}, {"id": "b", "threadId": "tb"}]}
        mock_resp = _make_urlopen_response(payload)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = gp.list_messages(query="is:unread")

        assert len(result) == 2
        assert result[0]["id"] == "a"

    def test_returns_empty_list_on_error(self, tmp_path):
        gp = self._make_provider(tmp_path)
        mock_resp = _make_urlopen_response({"error": True})

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = gp.list_messages()

        assert result == []

    def test_returns_empty_list_when_no_messages_key(self, tmp_path):
        gp = self._make_provider(tmp_path)
        mock_resp = _make_urlopen_response({"resultSizeEstimate": 0})

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = gp.list_messages()

        assert result == []

    def test_passes_label_ids_as_query_param(self, tmp_path):
        gp = self._make_provider(tmp_path)
        mock_resp = _make_urlopen_response({"messages": []})

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
            gp.list_messages(label_ids=["INBOX", "UNREAD"])

        url = mock_open.call_args[0][0].full_url
        assert "labelIds=INBOX%2CUNREAD" in url or "labelIds=INBOX,UNREAD" in url


# ---------------------------------------------------------------------------
# GmailProvider — get_message
# ---------------------------------------------------------------------------

class TestGetMessage:
    def _make_provider(self, tmp_path) -> GmailProvider:
        gp = GmailProvider(credentials_path=tmp_path / "c.json",
                           token_path=tmp_path / "t.json")
        gp._access_token = "tok"
        return gp

    def test_returns_email_message_on_success(self, tmp_path):
        gp = self._make_provider(tmp_path)
        raw = _make_raw_message(msg_id="msg42", subject="Hello")
        mock_resp = _make_urlopen_response(raw)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = gp.get_message("msg42")

        assert isinstance(result, EmailMessage)
        assert result.message_id == "msg42"
        assert result.subject == "Hello"

    def test_returns_none_on_error_response(self, tmp_path):
        gp = self._make_provider(tmp_path)
        mock_resp = _make_urlopen_response({"error": True, "status": 404})

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = gp.get_message("nonexistent")

        assert result is None

    def test_returns_none_when_no_access_token(self, tmp_path):
        gp = GmailProvider(credentials_path=tmp_path / "c.json",
                           token_path=tmp_path / "t.json")
        result = gp.get_message("msg1")
        assert result is None


# ---------------------------------------------------------------------------
# GmailProvider — get_attachment
# ---------------------------------------------------------------------------

class TestGetAttachment:
    def _make_provider(self, tmp_path) -> GmailProvider:
        gp = GmailProvider(credentials_path=tmp_path / "c.json",
                           token_path=tmp_path / "t.json")
        gp._access_token = "tok"
        return gp

    def test_returns_decoded_bytes(self, tmp_path):
        gp = self._make_provider(tmp_path)
        raw_content = b"col1,col2\nval1,val2\n"
        b64_content = base64.urlsafe_b64encode(raw_content).decode().rstrip("=")
        mock_resp = _make_urlopen_response({"data": b64_content})

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = gp.get_attachment("msg1", "att1")

        assert raw_content == result[:len(raw_content)]

    def test_returns_empty_bytes_on_error(self, tmp_path):
        gp = self._make_provider(tmp_path)
        mock_resp = _make_urlopen_response({"error": True})

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = gp.get_attachment("msg1", "att1")

        assert result == b""

    def test_returns_empty_bytes_when_no_token(self, tmp_path):
        gp = GmailProvider(credentials_path=tmp_path / "c.json",
                           token_path=tmp_path / "t.json")
        result = gp.get_attachment("msg1", "att1")
        assert result == b""


# ---------------------------------------------------------------------------
# GmailProvider — get_unread_count
# ---------------------------------------------------------------------------

class TestGetUnreadCount:
    def _make_provider(self, tmp_path) -> GmailProvider:
        gp = GmailProvider(credentials_path=tmp_path / "c.json",
                           token_path=tmp_path / "t.json")
        gp._access_token = "tok"
        return gp

    def test_uses_labels_endpoint_messagesunread(self, tmp_path):
        gp = self._make_provider(tmp_path)
        mock_resp = _make_urlopen_response({"messagesUnread": 7, "threadsUnread": 3})

        with patch("urllib.request.urlopen", return_value=mock_resp):
            count = gp.get_unread_count()

        assert count == 7

    def test_falls_back_to_threadsunread(self, tmp_path):
        gp = self._make_provider(tmp_path)
        mock_resp = _make_urlopen_response({"threadsUnread": 4})

        with patch("urllib.request.urlopen", return_value=mock_resp):
            count = gp.get_unread_count()

        assert count == 4

    def test_falls_back_to_list_messages_on_error(self, tmp_path):
        gp = self._make_provider(tmp_path)
        # First call (labels/UNREAD) returns error; second call (list_messages) returns 3 msgs
        labels_resp = _make_urlopen_response({"error": True, "status": 403})
        list_resp = _make_urlopen_response(
            {"messages": [{"id": "1"}, {"id": "2"}, {"id": "3"}]}
        )

        with patch("urllib.request.urlopen", side_effect=[labels_resp, list_resp]):
            count = gp.get_unread_count()

        assert count == 3


# ---------------------------------------------------------------------------
# GmailProvider — search_messages
# ---------------------------------------------------------------------------

class TestSearchMessages:
    def test_combines_list_and_get(self, tmp_path):
        gp = GmailProvider(credentials_path=tmp_path / "c.json",
                           token_path=tmp_path / "t.json")
        gp._access_token = "tok"

        list_resp = _make_urlopen_response({"messages": [{"id": "m1", "threadId": "t1"}]})
        msg_raw = _make_raw_message(msg_id="m1", subject="Found It")
        get_resp = _make_urlopen_response(msg_raw)

        with patch("urllib.request.urlopen", side_effect=[list_resp, get_resp]):
            results = gp.search_messages("subject:Found It", max_results=5)

        assert len(results) == 1
        assert results[0].subject == "Found It"

    def test_returns_empty_list_when_no_messages(self, tmp_path):
        gp = GmailProvider(credentials_path=tmp_path / "c.json",
                           token_path=tmp_path / "t.json")
        gp._access_token = "tok"
        mock_resp = _make_urlopen_response({"messages": []})

        with patch("urllib.request.urlopen", return_value=mock_resp):
            results = gp.search_messages("nothing")

        assert results == []


# ---------------------------------------------------------------------------
# GmailProvider — _parse_message (static method, thorough)
# ---------------------------------------------------------------------------

class TestParseMessage:
    def test_plain_body_direct(self):
        raw = _make_raw_message(
            msg_id="p1", thread_id="t1",
            subject="Direct Body", sender="s@x.com",
            recipient="r@x.com", body_data="Hello, world!",
        )
        msg = GmailProvider._parse_message(raw)

        assert msg.message_id == "p1"
        assert msg.thread_id == "t1"
        assert msg.subject == "Direct Body"
        assert msg.sender == "s@x.com"
        assert msg.recipient == "r@x.com"
        assert "Hello, world!" in msg.body_text
        assert msg.attachments == []

    def test_body_from_text_plain_part(self):
        parts = [
            {
                "mimeType": "text/plain",
                "body": {"data": _b64("Part body text")},
                "parts": [],
            }
        ]
        raw = _make_raw_message(msg_id="p2", parts=parts)
        msg = GmailProvider._parse_message(raw)
        assert "Part body text" in msg.body_text

    def test_attachment_in_top_level_parts(self):
        parts = [
            {
                "filename": "report.csv",
                "mimeType": "text/csv",
                "body": {"size": 512, "attachmentId": "att_id_1"},
                "parts": [],
            }
        ]
        raw = _make_raw_message(msg_id="p3", parts=parts)
        msg = GmailProvider._parse_message(raw)

        assert len(msg.attachments) == 1
        att = msg.attachments[0]
        assert att["filename"] == "report.csv"
        assert att["mime_type"] == "text/csv"
        assert att["size"] == 512
        assert att["attachment_id"] == "att_id_1"

    def test_nested_attachment_in_sub_parts(self):
        parts = [
            {
                "mimeType": "multipart/mixed",
                "body": {},
                "parts": [
                    {
                        "filename": "nested.csv",
                        "mimeType": "text/csv",
                        "body": {"size": 256, "attachmentId": "att_nested"},
                    }
                ],
            }
        ]
        raw = _make_raw_message(msg_id="p4", parts=parts)
        msg = GmailProvider._parse_message(raw)

        filenames = [a["filename"] for a in msg.attachments]
        assert "nested.csv" in filenames

    def test_labels_propagated(self):
        raw = _make_raw_message(msg_id="p5", labels=["INBOX", "UNREAD"])
        msg = GmailProvider._parse_message(raw)
        assert "INBOX" in msg.labels
        assert "UNREAD" in msg.labels

    def test_snippet_propagated(self):
        raw = _make_raw_message(msg_id="p6", snippet="Preview of email...")
        msg = GmailProvider._parse_message(raw)
        assert msg.snippet == "Preview of email..."

    def test_raw_preserved(self):
        raw = _make_raw_message(msg_id="p7")
        msg = GmailProvider._parse_message(raw)
        assert msg.raw is raw

    def test_missing_headers_default_to_empty_string(self):
        raw = {
            "id": "p8",
            "threadId": "t8",
            "snippet": "",
            "labelIds": [],
            "payload": {"headers": []},
        }
        msg = GmailProvider._parse_message(raw)
        assert msg.subject == ""
        assert msg.sender == ""
        assert msg.recipient == ""
        assert msg.date == ""

    def test_headers_are_case_insensitive(self):
        raw = {
            "id": "p9",
            "threadId": "t9",
            "snippet": "",
            "labelIds": [],
            "payload": {
                "headers": [
                    {"name": "SUBJECT", "value": "Upper Case"},
                    {"name": "FROM", "value": "upper@example.com"},
                    {"name": "TO", "value": "dest@example.com"},
                    {"name": "DATE", "value": "2024-06-01"},
                ]
            },
        }
        msg = GmailProvider._parse_message(raw)
        assert msg.subject == "Upper Case"
        assert msg.sender == "upper@example.com"

    def test_part_without_filename_is_not_an_attachment(self):
        parts = [
            {
                "mimeType": "text/plain",
                "body": {"data": _b64("plain text")},
                "parts": [],
            }
        ]
        raw = _make_raw_message(msg_id="p10", parts=parts)
        msg = GmailProvider._parse_message(raw)
        assert msg.attachments == []

    def test_multiple_attachments_all_captured(self):
        parts = [
            {
                "filename": "a.csv",
                "mimeType": "text/csv",
                "body": {"size": 100, "attachmentId": "id_a"},
                "parts": [],
            },
            {
                "filename": "b.pdf",
                "mimeType": "application/pdf",
                "body": {"size": 200, "attachmentId": "id_b"},
                "parts": [],
            },
        ]
        raw = _make_raw_message(msg_id="p11", parts=parts)
        msg = GmailProvider._parse_message(raw)
        assert len(msg.attachments) == 2
        filenames = {a["filename"] for a in msg.attachments}
        assert filenames == {"a.csv", "b.pdf"}


# ---------------------------------------------------------------------------
# _parse_message — parametrized header extraction
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("header_name,field_name,value", [
    ("Subject", "subject", "My Subject"),
    ("From", "sender", "from@example.com"),
    ("To", "recipient", "to@example.com"),
    ("Date", "date", "Tue, 01 Jan 2025 00:00:00 +0000"),
])
def test_parse_message_header_extraction(header_name, field_name, value):
    raw = {
        "id": "hx",
        "threadId": "tx",
        "snippet": "",
        "labelIds": [],
        "payload": {
            "headers": [{"name": header_name, "value": value}]
        },
    }
    msg = GmailProvider._parse_message(raw)
    assert getattr(msg, field_name) == value


# ---------------------------------------------------------------------------
# RocketMoneyCSVChecker — build_search_query
# ---------------------------------------------------------------------------

class TestBuildSearchQuery:
    def _checker(self, tmp_path) -> RocketMoneyCSVChecker:
        gp = GmailProvider(credentials_path=tmp_path / "c.json",
                           token_path=tmp_path / "t.json")
        return RocketMoneyCSVChecker(gp)

    def test_contains_rocket_money_domain(self, tmp_path):
        checker = self._checker(tmp_path)
        q = checker.build_search_query()
        assert "rocketmoney.com" in q

    def test_contains_recipient(self, tmp_path):
        checker = self._checker(tmp_path)
        q = checker.build_search_query(recipient="test@example.com")
        assert "to:test@example.com" in q

    def test_contains_csv_filename_filter(self, tmp_path):
        checker = self._checker(tmp_path)
        q = checker.build_search_query()
        assert "filename:csv" in q.lower()

    def test_no_newer_than_when_days_back_none(self, tmp_path):
        checker = self._checker(tmp_path)
        q = checker.build_search_query(days_back=None)
        assert "newer_than" not in q

    def test_newer_than_included_when_days_back_set(self, tmp_path):
        checker = self._checker(tmp_path)
        q = checker.build_search_query(days_back=30)
        assert "newer_than:30d" in q

    @pytest.mark.parametrize("days", [7, 14, 90])
    def test_days_back_parametrized(self, days, tmp_path):
        checker = self._checker(tmp_path)
        q = checker.build_search_query(days_back=days)
        assert f"newer_than:{days}d" in q


# ---------------------------------------------------------------------------
# RocketMoneyCSVChecker — check
# ---------------------------------------------------------------------------

class TestRocketMoneyCheck:
    def test_returns_error_when_not_authenticated(self, tmp_path):
        gp = GmailProvider(credentials_path=tmp_path / "c.json",
                           token_path=tmp_path / "t.json")
        checker = RocketMoneyCSVChecker(gp)
        result = checker.check()

        assert result["found"] is False
        assert result["count"] == 0
        assert "error" in result
        assert "authenticated" in result["error"].lower()

    def test_returns_found_false_when_no_messages(self, tmp_path):
        gp = GmailProvider(credentials_path=tmp_path / "c.json",
                           token_path=tmp_path / "t.json")
        gp._authenticated = True
        gp._access_token = "tok"
        checker = RocketMoneyCSVChecker(gp)

        with patch.object(gp, "search_messages", return_value=[]):
            result = checker.check()

        assert result["found"] is False
        assert result["count"] == 0
        assert result["emails"] == []

    def test_returns_found_true_when_messages_present(self, tmp_path):
        gp = GmailProvider(credentials_path=tmp_path / "c.json",
                           token_path=tmp_path / "t.json")
        gp._authenticated = True
        gp._access_token = "tok"
        checker = RocketMoneyCSVChecker(gp)

        msg = EmailMessage(
            message_id="m1", thread_id="t1",
            subject="Your CSV export", sender="noreply@rocketmoney.com",
            recipient="jeremytabernero@gmail.com", date="2024-01-01",
            snippet="CSV attached",
            attachments=[{
                "filename": "transactions.csv",
                "mime_type": "text/csv",
                "size": 1024,
                "attachment_id": "att1",
            }],
        )

        with patch.object(gp, "search_messages", return_value=[msg]):
            result = checker.check()

        assert result["found"] is True
        assert result["count"] == 1
        assert len(result["emails"]) == 1
        assert result["emails"][0]["subject"] == "Your CSV export"

    def test_result_contains_query_and_checked_at(self, tmp_path):
        gp = GmailProvider(credentials_path=tmp_path / "c.json",
                           token_path=tmp_path / "t.json")
        gp._authenticated = True
        gp._access_token = "tok"
        checker = RocketMoneyCSVChecker(gp)

        with patch.object(gp, "search_messages", return_value=[]):
            result = checker.check()

        assert "query" in result
        assert "checked_at" in result
        assert result["query"] != ""

    def test_csv_attachments_extracted_per_email(self, tmp_path):
        gp = GmailProvider(credentials_path=tmp_path / "c.json",
                           token_path=tmp_path / "t.json")
        gp._authenticated = True
        gp._access_token = "tok"
        checker = RocketMoneyCSVChecker(gp)

        msg = EmailMessage(
            message_id="m2", thread_id="t2",
            subject="Export", sender="export@rocketmoney.com",
            recipient="j@gmail.com", date="2024-02-01",
            snippet="",
            attachments=[
                {"filename": "data.csv", "mime_type": "text/csv", "size": 500, "attachment_id": "a1"},
                {"filename": "image.png", "mime_type": "image/png", "size": 200, "attachment_id": "a2"},
            ],
        )

        with patch.object(gp, "search_messages", return_value=[msg]):
            result = checker.check()

        csv_atts = result["emails"][0]["csv_attachments"]
        assert len(csv_atts) == 1
        assert csv_atts[0]["filename"] == "data.csv"


# ---------------------------------------------------------------------------
# RocketMoneyCSVChecker — download_latest_csv
# ---------------------------------------------------------------------------

class TestDownloadLatestCsv:
    def test_returns_error_when_not_authenticated(self, tmp_path):
        gp = GmailProvider(credentials_path=tmp_path / "c.json",
                           token_path=tmp_path / "t.json")
        checker = RocketMoneyCSVChecker(gp)
        result = checker.download_latest_csv(save_dir=tmp_path)
        assert result["success"] is False
        assert "authenticated" in result["error"].lower()

    def test_returns_error_when_no_csv_found(self, tmp_path):
        gp = GmailProvider(credentials_path=tmp_path / "c.json",
                           token_path=tmp_path / "t.json")
        gp._authenticated = True
        gp._access_token = "tok"
        checker = RocketMoneyCSVChecker(gp)

        with patch.object(gp, "search_messages", return_value=[]):
            result = checker.download_latest_csv(save_dir=tmp_path)

        assert result["success"] is False
        assert "No CSV" in result["error"]

    def test_downloads_and_saves_csv(self, tmp_path):
        gp = GmailProvider(credentials_path=tmp_path / "c.json",
                           token_path=tmp_path / "t.json")
        gp._authenticated = True
        gp._access_token = "tok"
        checker = RocketMoneyCSVChecker(gp)

        msg = EmailMessage(
            message_id="m3", thread_id="t3",
            subject="Your export", sender="export@rocketmoney.com",
            recipient="j@gmail.com", date="2024-03-01",
            snippet="",
            attachments=[{
                "filename": "transactions.csv",
                "mime_type": "text/csv",
                "size": 20,
                "attachment_id": "att_csv",
            }],
        )
        csv_bytes = b"col1,col2\nval1,val2\n"

        with patch.object(gp, "search_messages", return_value=[msg]):
            with patch.object(gp, "get_attachment", return_value=csv_bytes):
                result = checker.download_latest_csv(save_dir=tmp_path)

        assert result["success"] is True
        assert result["filename"] == "transactions.csv"
        assert result["size"] == len(csv_bytes)
        saved_path = Path(result["path"])
        assert saved_path.exists()
        assert saved_path.read_bytes() == csv_bytes


# ---------------------------------------------------------------------------
# RocketMoneyCSVChecker — ROCKET_MONEY_SENDERS constant
# ---------------------------------------------------------------------------

class TestRocketMoneySenders:
    def test_senders_list_is_not_empty(self):
        assert len(RocketMoneyCSVChecker.ROCKET_MONEY_SENDERS) > 0

    def test_noreply_present(self):
        assert "noreply@rocketmoney.com" in RocketMoneyCSVChecker.ROCKET_MONEY_SENDERS

    def test_all_senders_are_strings(self):
        for s in RocketMoneyCSVChecker.ROCKET_MONEY_SENDERS:
            assert isinstance(s, str)
            assert "@" in s
