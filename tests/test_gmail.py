"""Tests for the Gmail agent and Rocket Money CSV checker."""

import csv
import io
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from guardian_one.core.audit import AuditLog
from guardian_one.core.base_agent import AgentReport, AgentStatus
from guardian_one.core.config import AgentConfig
from guardian_one.agents.gmail_agent import GmailAgent
from guardian_one.integrations.gmail_sync import (
    EmailMessage,
    GmailProvider,
    RocketMoneyCSVChecker,
)


def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


# ========================================================================
# GmailProvider tests
# ========================================================================

def test_gmail_provider_init():
    provider = GmailProvider()
    assert provider.is_authenticated is False
    assert provider._user == "me"


def test_gmail_provider_has_credentials_false():
    provider = GmailProvider(credentials_path="/nonexistent/path.json")
    assert provider.has_credentials is False


def test_gmail_provider_has_token_false():
    provider = GmailProvider(token_path="/nonexistent/token.json")
    assert provider.has_token is False


def test_gmail_provider_env_token():
    with patch.dict("os.environ", {"GMAIL_ACCESS_TOKEN": "test-token-123"}):
        provider = GmailProvider(
            credentials_path="/nonexistent/cred.json",
            token_path="/nonexistent/token.json",
        )
        result = provider.authenticate()
        assert result is True
        assert provider.is_authenticated is True
        assert provider._access_token == "test-token-123"


def test_gmail_provider_no_auth():
    provider = GmailProvider(
        credentials_path="/nonexistent/cred.json",
        token_path="/nonexistent/token.json",
    )
    result = provider.authenticate()
    assert result is False


def test_gmail_provider_list_messages_unauthenticated():
    provider = GmailProvider()
    msgs = provider.list_messages(query="is:unread")
    assert msgs == []


def test_gmail_provider_search_messages_unauthenticated():
    provider = GmailProvider()
    msgs = provider.search_messages("from:test@test.com")
    assert msgs == []


def test_gmail_provider_parse_message():
    raw = {
        "id": "msg123",
        "threadId": "thread456",
        "snippet": "Test snippet",
        "labelIds": ["INBOX", "UNREAD"],
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Test Subject"},
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "jeremytabernero@gmail.com"},
                {"name": "Date", "value": "Thu, 20 Feb 2026 10:00:00 +0000"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": "SGVsbG8gV29ybGQ=", "size": 11},
                },
                {
                    "filename": "transactions.csv",
                    "mimeType": "text/csv",
                    "body": {
                        "attachmentId": "att789",
                        "size": 1024,
                    },
                },
            ],
        },
    }
    msg = GmailProvider._parse_message(raw)
    assert msg.message_id == "msg123"
    assert msg.subject == "Test Subject"
    assert msg.sender == "sender@example.com"
    assert msg.recipient == "jeremytabernero@gmail.com"
    assert len(msg.attachments) == 1
    assert msg.attachments[0]["filename"] == "transactions.csv"
    assert msg.attachments[0]["attachment_id"] == "att789"
    assert "Hello World" in msg.body_text


def test_gmail_provider_parse_message_nested_parts():
    raw = {
        "id": "msg-nested",
        "threadId": "thread-nested",
        "snippet": "",
        "labelIds": [],
        "payload": {
            "headers": [{"name": "Subject", "value": "Nested"}],
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {
                            "filename": "data.csv",
                            "mimeType": "text/csv",
                            "body": {"attachmentId": "nested-att", "size": 512},
                        },
                    ],
                },
            ],
        },
    }
    msg = GmailProvider._parse_message(raw)
    assert len(msg.attachments) == 1
    assert msg.attachments[0]["filename"] == "data.csv"


# ========================================================================
# RocketMoneyCSVChecker tests
# ========================================================================

def test_csv_checker_build_query():
    gmail = GmailProvider()
    checker = RocketMoneyCSVChecker(gmail)
    query = checker.build_search_query()
    assert "rocketmoney.com" in query
    assert "jeremytabernero@gmail.com" in query
    assert "filename:csv" in query


def test_csv_checker_build_query_with_days():
    gmail = GmailProvider()
    checker = RocketMoneyCSVChecker(gmail)
    query = checker.build_search_query(days_back=7)
    assert "newer_than:7d" in query


def test_csv_checker_build_query_custom_recipient():
    gmail = GmailProvider()
    checker = RocketMoneyCSVChecker(gmail)
    query = checker.build_search_query(recipient="other@example.com")
    assert "other@example.com" in query
    assert "jeremytabernero@gmail.com" not in query


def test_csv_checker_unauthenticated():
    gmail = GmailProvider()
    checker = RocketMoneyCSVChecker(gmail)
    result = checker.check()
    assert result["found"] is False
    assert "not authenticated" in result.get("error", "").lower()


def test_csv_checker_download_unauthenticated():
    gmail = GmailProvider()
    checker = RocketMoneyCSVChecker(gmail)
    result = checker.download_latest_csv()
    assert result["success"] is False


# ========================================================================
# GmailAgent tests
# ========================================================================

def test_gmail_agent_init():
    config = AgentConfig(name="gmail")
    agent = GmailAgent(config=config, audit=_make_audit())
    assert agent.name == "gmail"
    assert agent.TARGET_EMAIL == "jeremytabernero@gmail.com"


def test_gmail_agent_initialize():
    config = AgentConfig(name="gmail")
    agent = GmailAgent(config=config, audit=_make_audit())
    agent.initialize()
    assert agent.status == AgentStatus.IDLE


def test_gmail_agent_run_unauthenticated():
    config = AgentConfig(name="gmail")
    agent = GmailAgent(config=config, audit=_make_audit())
    agent.initialize()
    report = agent.run()
    assert report.agent_name == "gmail"
    assert report.status == AgentStatus.IDLE.value
    assert any("OAuth2" in a or "not authenticated" in a.lower() for a in report.alerts)


def test_gmail_agent_report():
    config = AgentConfig(name="gmail")
    agent = GmailAgent(config=config, audit=_make_audit())
    agent.initialize()
    report = agent.report()
    assert report.agent_name == "gmail"
    assert "jeremytabernero@gmail.com" in report.summary


def test_gmail_agent_check_inbox_unauthenticated():
    config = AgentConfig(name="gmail")
    agent = GmailAgent(config=config, audit=_make_audit())
    agent.initialize()
    result = agent.check_inbox()
    assert result.get("authenticated") is False


def test_gmail_agent_check_rocket_money_unauthenticated():
    config = AgentConfig(name="gmail")
    agent = GmailAgent(config=config, audit=_make_audit())
    agent.initialize()
    result = agent.check_rocket_money_csv()
    assert result["found"] is False


# ========================================================================
# CSV parsing tests (local file processing)
# ========================================================================

def _write_sample_csv(tmpdir: str) -> Path:
    """Create a sample Rocket Money CSV for testing."""
    path = Path(tmpdir) / "test_transactions.csv"
    rows = [
        {
            "Date": "2026-02-01",
            "Original Date": "2026-02-01",
            "Account Type": "Cash",
            "Account Name": "Adv Plus Banking",
            "Account Number": "5411",
            "Institution Name": "Bank of America",
            "Name": "ALTRU HEALTH SYS",
            "Custom Name": "",
            "Amount": "-1677.55",
            "Description": "ALTRU HEALTH SYS DES:PAYMENT",
            "Category": "Income",
            "Note": "",
            "Ignored From": "",
            "Tax Deductible": "",
            "Transaction Tags": "",
        },
        {
            "Date": "2026-02-05",
            "Original Date": "2026-02-05",
            "Account Type": "Cash",
            "Account Name": "Adv Plus Banking",
            "Account Number": "5411",
            "Institution Name": "Bank of America",
            "Name": "HEB Grocery",
            "Custom Name": "",
            "Amount": "120.00",
            "Description": "CHECKCARD HEB",
            "Category": "Groceries",
            "Note": "",
            "Ignored From": "",
            "Tax Deductible": "",
            "Transaction Tags": "",
        },
        {
            "Date": "2026-02-10",
            "Original Date": "2026-02-10",
            "Account Type": "Credit Card",
            "Account Name": "VentureOne",
            "Account Number": "0675",
            "Institution Name": "Capital One",
            "Name": "DoorDash",
            "Custom Name": "",
            "Amount": "32.00",
            "Description": "DOORDASH DINNER",
            "Category": "Dining & Drinks",
            "Note": "",
            "Ignored From": "",
            "Tax Deductible": "",
            "Transaction Tags": "",
        },
        {
            "Date": "2026-02-15",
            "Original Date": "2026-02-15",
            "Account Type": "Cash",
            "Account Name": "Adv Plus Banking",
            "Account Number": "5411",
            "Institution Name": "Bank of America",
            "Name": "ALTRU HEALTH SYS",
            "Custom Name": "",
            "Amount": "-1677.55",
            "Description": "ALTRU HEALTH SYS DES:PAYMENT",
            "Category": "Income",
            "Note": "",
            "Ignored From": "",
            "Tax Deductible": "",
            "Transaction Tags": "",
        },
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_parse_rocket_money_csv():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = _write_sample_csv(tmpdir)
        transactions = GmailAgent.parse_rocket_money_csv(csv_path)
        assert len(transactions) == 4
        assert transactions[0]["Name"] == "ALTRU HEALTH SYS"
        assert transactions[1]["Category"] == "Groceries"


def test_parse_rocket_money_csv_nonexistent():
    transactions = GmailAgent.parse_rocket_money_csv("/nonexistent/file.csv")
    assert transactions == []


def test_summarize_csv_transactions():
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = _write_sample_csv(tmpdir)
        transactions = GmailAgent.parse_rocket_money_csv(csv_path)
        summary = GmailAgent.summarize_csv_transactions(transactions)

        assert summary["total_transactions"] == 4
        # Income: 1677.55 * 2 = 3355.10
        assert summary["total_income"] == 3355.10
        # Expenses: 120.00 + 32.00 = 152.00
        assert summary["total_expenses"] == 152.00
        assert summary["net"] == 3355.10 - 152.00
        assert "Groceries" in summary["categories"]
        assert "Dining & Drinks" in summary["categories"]
        assert "Income" in summary["categories"]
        assert "Adv Plus Banking" in summary["accounts"]
        assert "VentureOne" in summary["accounts"]
        assert "Bank of America" in summary["institutions"]
        assert "Capital One" in summary["institutions"]
        assert summary["date_range"]["earliest"] == "2026-02-01"
        assert summary["date_range"]["latest"] == "2026-02-15"


def test_summarize_csv_empty():
    summary = GmailAgent.summarize_csv_transactions([])
    assert summary["total_transactions"] == 0


def test_parse_real_csv_if_available():
    """Test parsing the actual Rocket Money CSV if it exists."""
    csv_path = Path("data/rocket_money_transactions.csv")
    if not csv_path.exists():
        return  # Skip if file not present

    transactions = GmailAgent.parse_rocket_money_csv(csv_path)
    assert len(transactions) > 0

    summary = GmailAgent.summarize_csv_transactions(transactions)
    assert summary["total_transactions"] > 100
    assert summary["total_income"] > 0
    assert summary["total_expenses"] > 0
    assert len(summary["categories"]) > 1
    assert summary["date_range"]["earliest"] <= "2023-01-01"


# ========================================================================
# Registry integration test
# ========================================================================

def test_gmail_in_registry():
    from guardian_one.homelink.registry import IntegrationRegistry, GMAIL_INTEGRATION

    reg = IntegrationRegistry()
    reg.load_defaults()
    assert "gmail_api" in reg.list_all()
    assert GMAIL_INTEGRATION.owner_agent == "gmail"
    assert GMAIL_INTEGRATION.auth_method == "oauth2"
    assert len(GMAIL_INTEGRATION.threat_model) == 5
