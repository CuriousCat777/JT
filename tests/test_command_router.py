"""Tests for the CFO Command Router."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from guardian_one.core.command_router import CommandRouter, CommandResult, Intent


# ── Fake CFO scaffolding ──────────────────────────────────────────


class FakeAccountType(Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    INVESTMENT = "investment"


class FakeTransactionCategory(Enum):
    FOOD = "food"
    HOUSING = "housing"
    INCOME = "income"
    OTHER = "other"


@dataclass
class FakeAccount:
    name: str
    account_type: FakeAccountType
    balance: float
    institution: str = ""
    last_synced: str = "2026-01-01"


@dataclass
class FakeTransaction:
    date: str
    description: str
    amount: float
    category: FakeTransactionCategory = FakeTransactionCategory.OTHER
    account: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class FakeBill:
    name: str
    amount: float
    due_date: str
    recurring: bool = True
    frequency: str = "monthly"
    auto_pay: bool = False
    paid: bool = False


@dataclass
class FakeBudget:
    category: str
    limit: float
    label: str = ""


def _make_fake_cfo():
    """Build a mock CFO with realistic return values."""
    cfo = MagicMock()
    cfo.name = "cfo"

    cfo._accounts = {
        "Chase Checking": FakeAccount("Chase Checking", FakeAccountType.CHECKING, 5000.0, "Chase"),
        "Ally Savings": FakeAccount("Ally Savings", FakeAccountType.SAVINGS, 20000.0, "Ally"),
    }

    cfo.net_worth.return_value = 25000.0
    cfo.balances_by_type.return_value = {"checking": 5000.0, "savings": 20000.0}
    cfo.upcoming_bills.return_value = [
        FakeBill("Rent", 1500.0, "2026-03-25"),
        FakeBill("Electric", 120.0, "2026-03-28", auto_pay=True),
    ]
    cfo.overdue_bills.return_value = []
    cfo.spending_summary.return_value = {"food": 450.0, "housing": 1500.0}
    cfo.income_summary.return_value = 6500.0
    cfo.budget_check.return_value = [
        {"category": "food", "label": "Food & Groceries", "limit": 600.0,
         "spent": 450.0, "remaining": 150.0, "percent_used": 75.0, "status": "ok"},
    ]
    cfo.budget_alerts.return_value = []
    cfo._transactions = [
        FakeTransaction("2026-03-18", "Whole Foods", -85.50, FakeTransactionCategory.FOOD),
        FakeTransaction("2026-03-19", "Paycheck", 3250.0, FakeTransactionCategory.INCOME),
    ]
    cfo.verify_transactions.return_value = {
        "checked": 15, "issues": 0, "summary": "All clear", "status": "clean",
    }
    cfo.verify_bills_paid.return_value = [
        {"name": "Rent", "paid": True},
        {"name": "Electric", "paid": False},
    ]
    cfo.daily_review.return_value = {
        "transactions": "2 today",
        "bills": "1 due this week",
        "budget": "on track",
        "overall_status": "healthy",
    }
    cfo.dashboard.return_value = {"net_worth": 25000.0, "bills_due": 2}
    cfo.tax_recommendations.return_value = [
        "Max out 401k contributions",
        "Consider Roth IRA conversion",
    ]
    cfo.home_purchase_scenario.return_value = {
        "target_price": 350000, "down_payment": 70000,
        "monthly_payment": 1800.0, "affordable": True,
    }
    cfo.sync_all.return_value = {"plaid": {"status": "synced"}, "empower": {"status": "synced"}}
    cfo.generate_excel.return_value = "/tmp/dashboard.xlsx"
    cfo.validation_report.return_value = {"accounts": "valid", "transactions": "valid"}
    cfo.net_worth_trend.return_value = [
        {"date": "2026-02", "net_worth": 23000.0},
        {"date": "2026-03", "net_worth": 25000.0},
    ]
    cfo.plaid_status.return_value = {"connected": True, "institutions": 2}
    cfo.empower_status.return_value = {"connected": True, "balance": 45000.0}
    cfo.rocket_money_status.return_value = {"connected": True, "subscriptions": 8}
    cfo.set_budget.return_value = FakeBudget("food", 500.0, "Food & Groceries")

    return cfo


def _make_router(cfo=None, ai_engine=None):
    """Build a CommandRouter with a mocked guardian."""
    if cfo is None:
        cfo = _make_fake_cfo()

    guardian = MagicMock()
    guardian.get_agent.return_value = cfo
    guardian.ai_engine = ai_engine
    return CommandRouter(guardian)


# ── Intent Detection Tests ────────────────────────────────────────


class TestIntentDetection:
    def test_detect_net_worth_intent(self):
        router = _make_router()
        intent = router.detect_intent("what's my net worth?")
        assert intent.name == "net_worth"

    def test_detect_net_worth_variant(self):
        router = _make_router()
        intent = router.detect_intent("how much do i have in total?")
        assert intent.name == "net_worth"

    def test_detect_bills_upcoming(self):
        router = _make_router()
        intent = router.detect_intent("any bills due this week?")
        assert intent.name == "bills_upcoming"

    def test_detect_bills_overdue(self):
        router = _make_router()
        intent = router.detect_intent("do i have any overdue bills?")
        assert intent.name == "bills_overdue"

    def test_detect_spending(self):
        router = _make_router()
        intent = router.detect_intent("where's my money going?")
        assert intent.name == "spending"

    def test_detect_budget(self):
        router = _make_router()
        intent = router.detect_intent("how's my budget looking?")
        assert intent.name == "budget"

    def test_detect_income(self):
        router = _make_router()
        intent = router.detect_intent("how much did i make this month?")
        assert intent.name == "income"

    def test_detect_transactions(self):
        router = _make_router()
        intent = router.detect_intent("show me recent transactions")
        assert intent.name == "transactions"

    def test_detect_sync(self):
        router = _make_router()
        intent = router.detect_intent("sync my data")
        assert intent.name == "sync"

    def test_detect_dashboard(self):
        router = _make_router()
        intent = router.detect_intent("give me a dashboard")
        assert intent.name == "dashboard"

    def test_detect_daily_review(self):
        router = _make_router()
        intent = router.detect_intent("run a daily review")
        assert intent.name == "daily_review"

    def test_detect_tax(self):
        router = _make_router()
        intent = router.detect_intent("any tax recommendations?")
        assert intent.name == "tax"

    def test_detect_home_purchase(self):
        router = _make_router()
        intent = router.detect_intent("can i afford a house?")
        assert intent.name == "scenario_home"

    def test_detect_verify_transactions(self):
        router = _make_router()
        intent = router.detect_intent("check transactions for fraud")
        assert intent.name == "verify_transactions"

    def test_detect_verify_bills(self):
        router = _make_router()
        intent = router.detect_intent("verify bills have been paid")
        assert intent.name == "verify_bills"

    def test_detect_excel(self):
        router = _make_router()
        intent = router.detect_intent("generate an excel spreadsheet")
        assert intent.name == "excel"

    def test_detect_validate(self):
        router = _make_router()
        intent = router.detect_intent("run a validation report")
        assert intent.name == "validate"

    def test_detect_trend(self):
        router = _make_router()
        intent = router.detect_intent("show me the trend over time")
        assert intent.name == "net_worth_trend"

    def test_detect_plaid_status(self):
        router = _make_router()
        intent = router.detect_intent("what's my plaid status?")
        assert intent.name == "plaid_status"

    def test_detect_empower_status(self):
        router = _make_router()
        intent = router.detect_intent("how's empower doing?")
        assert intent.name == "empower_status"

    def test_detect_rocket_money(self):
        router = _make_router()
        intent = router.detect_intent("check rocket money")
        assert intent.name == "rocket_money_status"

    def test_detect_set_budget(self):
        router = _make_router()
        intent = router.detect_intent("set budget for food to 500")
        assert intent.name == "set_budget"

    def test_detect_help(self):
        router = _make_router()
        intent = router.detect_intent("what can you do?")
        assert intent.name == "help"

    def test_detect_unknown_falls_back_to_help(self):
        router = _make_router()
        intent = router.detect_intent("blah blah gibberish xyz")
        assert intent.name == "help"

    def test_detect_accounts(self):
        router = _make_router()
        intent = router.detect_intent("show me my accounts and balances")
        assert intent.name == "accounts"

    def test_longest_keyword_wins(self):
        """'verify transactions' should beat plain 'transactions'."""
        router = _make_router()
        intent = router.detect_intent("verify transactions please")
        assert intent.name == "verify_transactions"


# ── Parameter Extraction Tests ────────────────────────────────────


class TestParameterExtraction:
    def test_extract_month(self):
        router = _make_router()
        intent = router.detect_intent("spending in march")
        assert intent.params.get("month") == "2026-03"

    def test_extract_month_with_year(self):
        router = _make_router()
        intent = router.detect_intent("spending in january 2025")
        assert intent.params.get("month") == "2025-01"

    def test_extract_days(self):
        router = _make_router()
        intent = router.detect_intent("bills due in 14 days")
        assert intent.params.get("days") == 14

    def test_extract_price_with_k(self):
        router = _make_router()
        intent = router.detect_intent("can I afford a $350k house?")
        assert intent.params.get("price") == 350000

    def test_extract_price_full_number(self):
        router = _make_router()
        intent = router.detect_intent("home purchase $400,000")
        assert intent.params.get("price") == 400000

    def test_extract_count(self):
        router = _make_router()
        intent = router.detect_intent("last 20 transactions")
        assert intent.params.get("count") == 20

    def test_extract_category_and_limit(self):
        router = _make_router()
        intent = router.detect_intent("set food budget to 500")
        assert intent.params.get("category") == "food"
        assert intent.params.get("limit") == 500.0


# ── Execution Tests ───────────────────────────────────────────────


class TestExecution:
    def test_execute_net_worth(self):
        router = _make_router()
        result = router.handle("what's my net worth?")
        assert result.data["net_worth"] == 25000.0
        assert "by_type" in result.data

    def test_execute_accounts(self):
        router = _make_router()
        result = router.handle("show me my accounts")
        assert len(result.data["accounts"]) == 2

    def test_execute_bills_upcoming(self):
        router = _make_router()
        result = router.handle("any bills due?")
        assert len(result.data["bills"]) == 2

    def test_execute_bills_overdue(self):
        router = _make_router()
        result = router.handle("any overdue bills?")
        assert result.data["bills"] == []

    def test_execute_spending(self):
        router = _make_router()
        result = router.handle("where's my money going?")
        assert "food" in result.data["spending"]

    def test_execute_income(self):
        router = _make_router()
        result = router.handle("how much did i make?")
        assert result.data["income"] == 6500.0

    def test_execute_budget(self):
        router = _make_router()
        result = router.handle("how's my budget?")
        assert len(result.data["budget"]) == 1

    def test_execute_transactions(self):
        router = _make_router()
        result = router.handle("recent transactions")
        assert len(result.data["transactions"]) == 2

    def test_execute_verify_transactions(self):
        router = _make_router()
        result = router.handle("verify transactions")
        assert result.data["status"] == "clean"

    def test_execute_verify_bills(self):
        router = _make_router()
        result = router.handle("verify bills")
        assert len(result.data["results"]) == 2

    def test_execute_daily_review(self):
        router = _make_router()
        result = router.handle("daily review")
        assert result.data["overall_status"] == "healthy"

    def test_execute_dashboard(self):
        router = _make_router()
        result = router.handle("give me a dashboard")
        assert result.data["net_worth"] == 25000.0

    def test_execute_tax(self):
        router = _make_router()
        result = router.handle("tax recommendations")
        assert len(result.data["recommendations"]) == 2

    def test_execute_home_scenario(self):
        router = _make_router()
        result = router.handle("can I afford a $350k house?")
        assert result.data["affordable"] is True

    def test_execute_sync(self):
        router = _make_router()
        result = router.handle("sync my data")
        assert "plaid" in result.data

    def test_execute_excel(self):
        router = _make_router()
        result = router.handle("generate excel report")
        assert "path" in result.data

    def test_execute_validate(self):
        router = _make_router()
        result = router.handle("validation report")
        assert result.data["accounts"] == "valid"

    def test_execute_trend(self):
        router = _make_router()
        result = router.handle("show net worth trend")
        assert len(result.data["trend"]) == 2

    def test_execute_set_budget(self):
        router = _make_router()
        result = router.handle("set food budget to 500")
        assert result.data["category"] == "food"
        assert result.data["limit"] == 500.0

    def test_execute_set_budget_missing_params(self):
        router = _make_router()
        result = router.handle("set budget")
        assert "error" in result.data

    def test_execute_help(self):
        router = _make_router()
        result = router.handle("help")
        assert "commands" in result.data

    def test_execute_no_cfo(self):
        """When CFO agent is not available."""
        guardian = MagicMock()
        guardian.get_agent.return_value = None
        guardian.ai_engine = None
        router = CommandRouter(guardian)
        result = router.handle("net worth")
        assert "error" in result.data


# ── Formatting Tests ──────────────────────────────────────────────


class TestFormatting:
    def test_format_net_worth(self):
        router = _make_router()
        result = router.handle("what's my net worth?")
        assert "$25,000.00" in result.text
        assert "Checking" in result.text

    def test_format_bills_empty(self):
        cfo = _make_fake_cfo()
        cfo.upcoming_bills.return_value = []
        router = _make_router(cfo=cfo)
        result = router.handle("any bills due?")
        assert "No upcoming bills" in result.text

    def test_format_bills_with_data(self):
        router = _make_router()
        result = router.handle("any bills due?")
        assert "Rent" in result.text
        assert "1,500.00" in result.text

    def test_format_overdue_empty(self):
        router = _make_router()
        result = router.handle("any overdue bills?")
        assert "No overdue bills" in result.text

    def test_format_budget_with_alerts(self):
        cfo = _make_fake_cfo()
        cfo.budget_alerts.return_value = ["Food is at 90% of limit!"]
        router = _make_router(cfo=cfo)
        result = router.handle("how's my budget?")
        assert "[!]" in result.text

    def test_format_spending(self):
        router = _make_router()
        result = router.handle("where's my money going?")
        assert "Housing" in result.text
        assert "1,500.00" in result.text

    def test_format_income(self):
        router = _make_router()
        result = router.handle("how much did i make?")
        assert "$6,500.00" in result.text

    def test_format_transactions(self):
        router = _make_router()
        result = router.handle("recent transactions")
        assert "Whole Foods" in result.text
        assert "Paycheck" in result.text

    def test_format_help(self):
        router = _make_router()
        result = router.handle("help")
        assert "net worth" in result.text
        assert "Available commands" in result.text

    def test_format_error(self):
        guardian = MagicMock()
        guardian.get_agent.return_value = None
        guardian.ai_engine = None
        router = CommandRouter(guardian)
        result = router.handle("anything")
        assert "Error" in result.text


# ── AI Enhancement Tests ──────────────────────────────────────────


class TestAIEnhancement:
    def test_ai_enhance_when_available(self):
        ai = MagicMock()
        response = MagicMock()
        response.text = "Your net worth looks healthy at $25,000."
        ai.reason.return_value = response
        router = _make_router(ai_engine=ai)
        result = router.handle("what's my net worth?")
        assert result.ai_summary == "Your net worth looks healthy at $25,000."

    def test_ai_enhance_when_offline(self):
        router = _make_router(ai_engine=None)
        result = router.handle("what's my net worth?")
        assert result.ai_summary is None

    def test_ai_enhance_exception_handled(self):
        ai = MagicMock()
        ai.reason.side_effect = Exception("AI offline")
        router = _make_router(ai_engine=ai)
        result = router.handle("what's my net worth?")
        assert result.ai_summary is None


# ── Integration Tests ─────────────────────────────────────────────


class TestIntegration:
    def test_full_handle_pipeline(self):
        router = _make_router()
        result = router.handle("what's my net worth?")
        assert isinstance(result, CommandResult)
        assert result.intent.name == "net_worth"
        assert result.data["net_worth"] == 25000.0
        assert "$25,000.00" in result.text
        assert result.ai_summary is None

    def test_chat_help_command(self):
        router = _make_router()
        result = router.handle("what can you do?")
        assert "commands" in result.data
        assert len(result.data["commands"]) > 10

    def test_unknown_input_falls_back(self):
        router = _make_router()
        result = router.handle("asdfghjkl random gibberish")
        assert result.intent.name == "help"
        assert "commands" in result.data

    def test_handle_returns_command_result(self):
        router = _make_router()
        result = router.handle("net worth")
        assert hasattr(result, "intent")
        assert hasattr(result, "data")
        assert hasattr(result, "text")
        assert hasattr(result, "ai_summary")

    def test_multiple_queries_same_router(self):
        router = _make_router()
        r1 = router.handle("net worth")
        r2 = router.handle("any bills due?")
        r3 = router.handle("help")
        assert r1.intent.name == "net_worth"
        assert r2.intent.name == "bills_upcoming"
        assert r3.intent.name == "help"
