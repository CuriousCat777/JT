"""Tests for all three subordinate agents."""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from guardian_one.core.audit import AuditLog
from guardian_one.core.base_agent import AgentStatus
from guardian_one.core.config import AgentConfig
from guardian_one.agents.chronos import CalendarEvent, Chronos, SleepRecord
from guardian_one.agents.archivist import Archivist, FileRecord, RetentionPolicy
from guardian_one.agents.cfo import (
    Account,
    AccountType,
    Bill,
    CFO,
    Transaction,
    TransactionCategory,
)


def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


# ---- Chronos ----

def test_chronos_initialize():
    agent = Chronos(AgentConfig(name="chronos"), _make_audit())
    agent.initialize()
    assert agent.status == AgentStatus.IDLE


def test_chronos_add_event_and_upcoming():
    agent = Chronos(AgentConfig(name="chronos"), _make_audit())
    agent.initialize()

    now = datetime.now(timezone.utc)
    agent.add_event(CalendarEvent(
        title="Team standup",
        start=now + timedelta(hours=1),
        end=now + timedelta(hours=2),
    ))
    agent.add_event(CalendarEvent(
        title="Far future event",
        start=now + timedelta(days=30),
        end=now + timedelta(days=30, hours=1),
    ))

    upcoming = agent.upcoming_events(hours=12)
    assert len(upcoming) == 1
    assert upcoming[0].title == "Team standup"


def test_chronos_conflict_detection():
    agent = Chronos(AgentConfig(name="chronos"), _make_audit())
    agent.initialize()

    now = datetime.now(timezone.utc)
    agent.add_event(CalendarEvent(title="A", start=now, end=now + timedelta(hours=2)))
    agent.add_event(CalendarEvent(title="B", start=now + timedelta(hours=1), end=now + timedelta(hours=3)))

    conflicts = agent.check_conflicts()
    assert len(conflicts) == 1


def test_chronos_sleep_analysis():
    agent = Chronos(AgentConfig(name="chronos"), _make_audit())
    agent.initialize()

    for i in range(7):
        agent.record_sleep(SleepRecord(
            date=f"2026-02-{10+i}",
            bedtime="23:00",
            waketime="06:30",
            duration_hours=7.5,
            quality_score=0.8,
        ))

    analysis = agent.sleep_analysis()
    assert analysis["avg_duration_hours"] == 7.5
    assert "healthy" in analysis["recommendation"].lower()


def test_chronos_workflow_index():
    agent = Chronos(AgentConfig(name="chronos"), _make_audit())
    agent.initialize()
    agent.index_workflow("pre_chart", ["review problems", "check labs", "review meds"])
    assert agent.get_workflow("pre_chart") == ["review problems", "check labs", "review meds"]
    assert "pre_chart" in agent.list_workflows()


def test_chronos_run():
    agent = Chronos(AgentConfig(name="chronos"), _make_audit())
    agent.initialize()
    report = agent.run()
    assert report.agent_name == "chronos"
    assert report.status == AgentStatus.IDLE.value


# ---- Archivist ----

def test_archivist_initialize():
    agent = Archivist(AgentConfig(name="archivist"), _make_audit())
    agent.initialize()
    assert agent.status == AgentStatus.IDLE


def test_archivist_file_management():
    agent = Archivist(AgentConfig(name="archivist"), _make_audit())
    agent.initialize()

    agent.register_file(FileRecord(path="/docs/tax_2025.pdf", category="financial", tags=["tax", "2025"]))
    agent.register_file(FileRecord(path="/docs/resume.pdf", category="professional", tags=["resume"]))

    results = agent.search_files(category="financial")
    assert len(results) == 1
    assert results[0].path == "/docs/tax_2025.pdf"

    results = agent.search_files(tags=["resume"])
    assert len(results) == 1


def test_archivist_master_profile():
    agent = Archivist(AgentConfig(name="archivist"), _make_audit())
    agent.initialize()

    agent.set_profile_field("name", "Jeremy Paulo Salvino Tabernero")
    agent.set_profile_field("email", "jeremy@example.com")
    profile = agent.get_profile()
    assert profile["name"] == "Jeremy Paulo Salvino Tabernero"


def test_archivist_privacy_audit():
    agent = Archivist(AgentConfig(name="archivist"), _make_audit())
    agent.initialize()

    audit_result = agent.privacy_audit()
    assert "issues" in audit_result
    assert "recommendations" in audit_result


def test_archivist_run():
    agent = Archivist(AgentConfig(name="archivist"), _make_audit())
    agent.initialize()
    report = agent.run()
    assert report.agent_name == "archivist"


# ---- CFO ----

def test_cfo_initialize():
    agent = CFO(AgentConfig(name="cfo"), _make_audit())
    agent.initialize()
    assert agent.status == AgentStatus.IDLE


def test_cfo_accounts_and_net_worth():
    agent = CFO(AgentConfig(name="cfo"), _make_audit())
    agent.initialize()

    agent.add_account(Account(name="Checking", account_type=AccountType.CHECKING, balance=5000))
    agent.add_account(Account(name="Savings", account_type=AccountType.SAVINGS, balance=15000))
    agent.add_account(Account(name="Student Loan", account_type=AccountType.LOAN, balance=-30000))

    assert agent.net_worth() == -10000
    balances = agent.balances_by_type()
    assert balances["checking"] == 5000
    assert balances["savings"] == 15000


def test_cfo_spending_summary():
    agent = CFO(AgentConfig(name="cfo"), _make_audit())
    agent.initialize()

    agent.record_transaction(Transaction(date="2026-02-01", description="Rent", amount=-1500, category=TransactionCategory.HOUSING))
    agent.record_transaction(Transaction(date="2026-02-05", description="Groceries", amount=-200, category=TransactionCategory.FOOD))
    agent.record_transaction(Transaction(date="2026-02-01", description="Salary", amount=8000, category=TransactionCategory.INCOME))

    spending = agent.spending_summary("2026-02")
    assert spending["housing"] == 1500
    assert spending["food"] == 200
    assert agent.income_summary("2026-02") == 8000


def test_cfo_bill_management():
    agent = CFO(AgentConfig(name="cfo"), _make_audit())
    agent.initialize()

    agent.add_bill(Bill(name="Electric", amount=120, due_date="2020-01-01"))  # Past due
    agent.add_bill(Bill(name="Internet", amount=80, due_date="2030-12-31"))   # Far future

    overdue = agent.overdue_bills()
    assert len(overdue) == 1
    assert overdue[0].name == "Electric"


def test_cfo_home_purchase_scenario():
    agent = CFO(AgentConfig(name="cfo"), _make_audit())
    agent.initialize()
    agent.add_account(Account(name="Savings", account_type=AccountType.SAVINGS, balance=50000))

    result = agent.home_purchase_scenario(target_price=350000)
    assert result["down_payment"] == 70000
    assert result["down_payment_gap"] == 20000  # 70k needed, 50k have
    assert result["monthly_payment"] > 0


def test_cfo_tax_recommendations():
    agent = CFO(AgentConfig(name="cfo"), _make_audit())
    agent.initialize()

    recs = agent.tax_recommendations()
    assert len(recs) > 0
    assert any("retirement" in r.lower() for r in recs)


def test_cfo_run():
    agent = CFO(AgentConfig(name="cfo"), _make_audit())
    agent.initialize()
    report = agent.run()
    assert report.agent_name == "cfo"
    assert report.status == AgentStatus.IDLE.value
