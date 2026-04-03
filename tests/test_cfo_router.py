"""Tests for the CFO conversational command router."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from guardian_one.core.audit import AuditLog
from guardian_one.core.config import AgentConfig
from guardian_one.agents.cfo import (
    Account,
    AccountType,
    Bill,
    Budget,
    CFO,
    Transaction,
    TransactionCategory,
)
from guardian_one.core.cfo_router import CFORouter, RouteResult


def _make_cfo() -> CFO:
    """Create a CFO agent with sample data for testing."""
    audit = AuditLog(log_dir=Path(tempfile.mkdtemp()))
    cfo = CFO(
        config=AgentConfig(name="cfo"),
        audit=audit,
        data_dir=tempfile.mkdtemp(),
    )
    cfo.initialize()

    # Add accounts
    cfo.add_account(Account("Chase Checking", AccountType.CHECKING, 5_000.00, "Chase"), persist=False)
    cfo.add_account(Account("Ally Savings", AccountType.SAVINGS, 15_000.00, "Ally"), persist=False)
    cfo.add_account(Account("Amex Gold", AccountType.CREDIT_CARD, -2_500.00, "Amex"), persist=False)

    # Add transactions
    now = datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    cfo.record_transaction(Transaction(
        date=f"{month}-01", description="Paycheck", amount=4_000.00,
        category=TransactionCategory.INCOME, account="Chase Checking",
    ), persist=False)
    cfo.record_transaction(Transaction(
        date=f"{month}-05", description="Rent", amount=-1_500.00,
        category=TransactionCategory.HOUSING, account="Chase Checking",
    ), persist=False)
    cfo.record_transaction(Transaction(
        date=f"{month}-08", description="Groceries", amount=-250.00,
        category=TransactionCategory.FOOD, account="Amex Gold",
    ), persist=False)

    # Add bills
    future = (now + timedelta(days=5)).strftime("%Y-%m-%d")
    past = (now - timedelta(days=3)).strftime("%Y-%m-%d")
    cfo.add_bill(Bill("Rent", 1_500.00, future, auto_pay=True), persist=False)
    cfo.add_bill(Bill("Electric", 120.00, past, auto_pay=False), persist=False)

    # Add a budget
    cfo.set_budget("food", 500.0, persist=False)
    cfo.set_budget("housing", 1_600.0, persist=False)

    return cfo


def _router() -> CFORouter:
    return CFORouter(_make_cfo())


# --- Basic routing ---

def test_help():
    r = _router()
    result = r.handle("help")
    assert result.intent == "help"
    assert result.success
    assert "net_worth" in result.text


def test_empty_input():
    r = _router()
    result = r.handle("")
    assert result.intent == "empty"
    assert not result.success


def test_unknown_input():
    r = _router()
    result = r.handle("xyzzy foobar gibberish")
    assert result.intent == "unknown"
    assert not result.success


def test_exit():
    r = _router()
    result = r.handle("exit")
    assert result.intent == "exit"
    assert result.data.get("exit") is True


# --- Financial queries ---

def test_net_worth():
    r = _router()
    result = r.handle("what's my net worth?")
    assert result.intent == "net_worth"
    assert result.success
    assert result.data["net_worth"] == 17_500.00  # 5000 + 15000 - 2500


def test_net_worth_regex():
    r = _router()
    result = r.handle("net worth")
    assert result.intent == "net_worth"


def test_dashboard():
    r = _router()
    result = r.handle("give me an overview")
    assert result.intent == "dashboard"
    assert result.success
    assert "Net Worth" in result.text


def test_accounts():
    r = _router()
    result = r.handle("show my accounts")
    assert result.intent == "accounts"
    assert result.data["count"] == 3


def test_spending():
    r = _router()
    result = r.handle("how much did I spend this month?")
    assert result.intent == "spending"
    assert result.success


def test_income():
    r = _router()
    result = r.handle("how much did I earn?")
    assert result.intent == "income"
    assert result.data["income"] == 4_000.00


def test_bills():
    r = _router()
    result = r.handle("what bills are due?")
    assert result.intent == "bills"
    assert result.data["total"] == 2


def test_budget():
    r = _router()
    result = r.handle("budget check")
    assert result.intent == "budget"
    assert result.success
    assert "Food" in result.text or "food" in result.text.lower()


def test_daily_review():
    r = _router()
    result = r.handle("daily review")
    assert result.intent == "daily_review"
    assert "overall_status" in result.data


def test_tax():
    r = _router()
    result = r.handle("tax recommendations")
    assert result.intent == "tax"
    assert result.success


def test_home_scenario_default():
    r = _router()
    result = r.handle("can I afford a house?")
    assert result.intent == "home_scenario"
    assert "monthly_payment" in result.data


def test_home_scenario_with_price():
    r = _router()
    result = r.handle("home purchase scenario for $450,000")
    assert result.intent == "home_scenario"
    assert result.data["target_price"] == 450_000.0


def test_trend():
    r = _router()
    result = r.handle("net worth trend")
    assert result.intent == "trend"
    # No history yet, should still succeed
    assert result.success


def test_sync_status():
    r = _router()
    result = r.handle("sync status")
    assert result.intent == "sync_status"
    assert "Plaid" in result.text


def test_transactions():
    r = _router()
    result = r.handle("show recent transactions")
    assert result.intent == "transactions"
    assert result.data["total"] == 3


def test_validate():
    r = _router()
    result = r.handle("validation report")
    assert result.intent == "validate"
    assert result.success


def test_excel():
    pytest.importorskip("openpyxl", reason="openpyxl not installed")
    r = _router()
    result = r.handle("generate excel dashboard")
    assert result.intent == "excel"
    assert result.success
    assert "xlsx" in result.text.lower() or "saved" in result.text.lower()


# --- Scoring ---

def test_net_worth_beats_dashboard():
    """'net worth' should match net_worth, not dashboard."""
    r = _router()
    result = r.handle("net worth")
    assert result.intent == "net_worth"


def test_spending_beats_budget():
    """'spending breakdown' should match spending, not budget."""
    r = _router()
    result = r.handle("spending breakdown")
    assert result.intent == "spending"


# --- Month extraction ---

def test_spending_with_month_name():
    r = _router()
    result = r.handle("spending in January")
    assert result.intent == "spending"
    assert result.data["month"].endswith("-01")


def test_spending_with_iso_month():
    r = _router()
    result = r.handle("spending for 2026-02")
    assert result.intent == "spending"
    assert result.data["month"] == "2026-02"


# --- Intent listing ---

def test_list_intents():
    r = _router()
    intents = r.list_intents()
    names = [i["intent"] for i in intents]
    assert "net_worth" in names
    assert "dashboard" in names
    assert "bills" in names
    assert len(intents) >= 10
