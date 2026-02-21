"""Tests for Rocket Money + Empower integration and CFO sync pipeline."""

import tempfile
from pathlib import Path
from typing import Any

from guardian_one.core.audit import AuditLog
from guardian_one.core.base_agent import AgentStatus
from guardian_one.core.config import AgentConfig
from guardian_one.agents.cfo import (
    Account,
    AccountType,
    CFO,
    Transaction,
    TransactionCategory,
)
from guardian_one.integrations.financial_sync import (
    EmpowerProvider,
    RocketMoneyProvider,
    SyncedAccount,
    SyncedTransaction,
    map_rocket_money_account_type,
    map_rocket_money_category,
    parse_rocket_money_csv,
)


def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


def _make_data_dir() -> Path:
    return Path(tempfile.mkdtemp())


# ---------------------------------------------------------------------------
# Category mapping
# ---------------------------------------------------------------------------

def test_map_category_exact():
    assert map_rocket_money_category("Income") == "income"
    assert map_rocket_money_category("Rent") == "housing"
    assert map_rocket_money_category("Groceries") == "food"
    assert map_rocket_money_category("Utilities") == "utilities"


def test_map_category_case_insensitive():
    assert map_rocket_money_category("income") == "income"
    assert map_rocket_money_category("GROCERIES") == "food"
    assert map_rocket_money_category("rent") == "housing"


def test_map_category_partial():
    assert map_rocket_money_category("Food & Drink") == "food"
    assert map_rocket_money_category("Auto & Transport") == "transport"
    assert map_rocket_money_category("Health & Wellness") == "medical"


def test_map_category_unknown():
    assert map_rocket_money_category("SomethingRandom") == "other"
    assert map_rocket_money_category("") == "other"


def test_map_account_type():
    assert map_rocket_money_account_type("checking") == "checking"
    assert map_rocket_money_account_type("Credit Card") == "credit_card"
    assert map_rocket_money_account_type("401(k)") == "retirement"
    assert map_rocket_money_account_type("Roth IRA") == "retirement"
    assert map_rocket_money_account_type("Student Loan") == "loan"
    assert map_rocket_money_account_type("brokerage") == "investment"
    assert map_rocket_money_account_type("unknown_type") == "checking"


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

def test_parse_csv_basic():
    data_dir = _make_data_dir()
    csv_path = data_dir / "test.csv"
    csv_path.write_text(
        "Date,Account Type,Account Name,Institution Name,Name,Amount,Category\n"
        "2026-02-01,Checking,Primary Checking,Chase,Salary,-4200.00,Income\n"
        "2026-02-03,Credit Card,Chase Sapphire,Chase,Groceries,120.50,Groceries\n"
        "2026-02-05,Checking,Primary Checking,Chase,Rent,1800.00,Rent\n"
    )

    accounts, transactions = parse_rocket_money_csv(csv_path)

    assert len(accounts) == 2  # Primary Checking + Chase Sapphire
    assert len(transactions) == 3

    # First account
    checking = [a for a in accounts if a.name == "Primary Checking"][0]
    assert checking.account_type == "checking"
    assert checking.institution == "Chase"

    # Salary: RM negative (income) → CFO positive (inflow)
    salary_tx = [t for t in transactions if t.description == "Salary"][0]
    assert salary_tx.amount == 4200.00  # Flipped from -4200
    assert salary_tx.category == "income"

    # Groceries: RM positive (expense) → CFO negative (outflow)
    groceries_tx = [t for t in transactions if t.description == "Groceries"][0]
    assert groceries_tx.amount == -120.50
    assert groceries_tx.category == "food"


def test_parse_csv_nonexistent():
    accounts, transactions = parse_rocket_money_csv("/tmp/does_not_exist.csv")
    assert accounts == []
    assert transactions == []


def test_parse_csv_empty():
    data_dir = _make_data_dir()
    csv_path = data_dir / "empty.csv"
    csv_path.write_text("Date,Account Type,Account Name,Amount,Category\n")

    accounts, transactions = parse_rocket_money_csv(csv_path)
    assert accounts == []
    assert transactions == []


def test_parse_csv_custom_name_preferred():
    """Custom Name should be used over Name if present."""
    data_dir = _make_data_dir()
    csv_path = data_dir / "custom.csv"
    csv_path.write_text(
        "Date,Account Name,Name,Custom Name,Amount,Category\n"
        "2026-02-01,Checking,PAYMENT FROM EMPLOYER,My Paycheck,-3000,Income\n"
    )

    _, transactions = parse_rocket_money_csv(csv_path)
    assert transactions[0].description == "My Paycheck"


# ---------------------------------------------------------------------------
# RocketMoneyProvider — offline / no credentials
# ---------------------------------------------------------------------------

def test_rm_provider_no_credentials():
    provider = RocketMoneyProvider(api_key="")
    assert not provider.has_credentials
    assert not provider.authenticate()
    assert "Missing" in provider.last_error


def test_rm_provider_has_credentials():
    provider = RocketMoneyProvider(api_key="test-key")
    assert provider.has_credentials


def test_rm_provider_csv_sync():
    data_dir = _make_data_dir()
    csv_path = data_dir / "rm_export.csv"
    csv_path.write_text(
        "Date,Account Type,Account Name,Institution Name,Name,Amount,Category\n"
        "2026-02-01,Checking,My Checking,Chase,Groceries,85.00,Groceries\n"
        "2026-02-02,Credit Card,My Visa,Citi,Gas,45.00,Gas\n"
    )

    provider = RocketMoneyProvider()
    result = provider.sync_from_csv(csv_path)
    assert result["accounts"] == 2
    assert result["transactions"] == 2
    assert result["source"] == "csv"

    # CSV accounts available via fetch_accounts()
    accounts = provider.fetch_accounts()
    assert len(accounts) == 2

    # CSV transactions available via fetch_transactions()
    transactions = provider.fetch_transactions("2026-02-01", "2026-02-28")
    assert len(transactions) == 2


def test_rm_provider_csv_transaction_date_filter():
    data_dir = _make_data_dir()
    csv_path = data_dir / "dates.csv"
    csv_path.write_text(
        "Date,Account Name,Name,Amount,Category\n"
        "2026-01-15,Checking,Old Transaction,50.00,Food\n"
        "2026-02-01,Checking,New Transaction,30.00,Food\n"
    )

    provider = RocketMoneyProvider()
    provider.sync_from_csv(csv_path)

    # Only Feb
    feb_tx = provider.fetch_transactions("2026-02-01", "2026-02-28")
    assert len(feb_tx) == 1
    assert feb_tx[0].description == "New Transaction"


def test_rm_provider_status():
    provider = RocketMoneyProvider()
    status = provider.status()
    assert status["provider"] == "rocket_money"
    assert status["authenticated"] is False
    assert status["csv_accounts"] == 0


# ---------------------------------------------------------------------------
# EmpowerProvider — no credentials
# ---------------------------------------------------------------------------

def test_empower_no_credentials():
    provider = EmpowerProvider(api_key="", username="", password="")
    assert not provider.has_credentials
    assert not provider.authenticate()
    assert "Missing" in provider.last_error


def test_empower_has_api_key():
    provider = EmpowerProvider(api_key="test-key")
    assert provider.has_credentials


def test_empower_has_username_password():
    provider = EmpowerProvider(username="user", password="pass")
    assert provider.has_credentials


def test_empower_status():
    provider = EmpowerProvider()
    status = provider.status()
    assert status["provider"] == "empower"
    assert status["authenticated"] is False


def test_empower_fetch_accounts_unauthenticated():
    provider = EmpowerProvider()
    assert provider.fetch_accounts() == []


def test_empower_fetch_transactions_unauthenticated():
    provider = EmpowerProvider()
    assert provider.fetch_transactions("2026-01-01", "2026-02-28") == []


def test_empower_fetch_holdings_unauthenticated():
    provider = EmpowerProvider()
    assert provider.fetch_holdings() == []


def test_empower_fetch_net_worth_unauthenticated():
    provider = EmpowerProvider()
    assert provider.fetch_net_worth_history() == []


# ---------------------------------------------------------------------------
# CFO + Rocket Money sync
# ---------------------------------------------------------------------------

def test_cfo_has_rocket_money_provider():
    data_dir = _make_data_dir()
    cfo = CFO(AgentConfig(name="cfo"), _make_audit(), data_dir=data_dir)
    cfo.initialize()
    assert cfo.rocket_money is not None


def test_cfo_rocket_money_status():
    data_dir = _make_data_dir()
    cfo = CFO(AgentConfig(name="cfo"), _make_audit(), data_dir=data_dir)
    cfo.initialize()
    status = cfo.rocket_money_status()
    assert status["provider"] == "rocket_money"
    assert status["sync_mode"] == "offline"


def test_cfo_sync_from_csv():
    data_dir = _make_data_dir()
    csv_path = data_dir / "rocket_money_export.csv"
    csv_path.write_text(
        "Date,Account Type,Account Name,Institution Name,Name,Amount,Category\n"
        "2026-02-01,Checking,CSV Checking,Chase,Salary,-4200.00,Income\n"
        "2026-02-03,Credit Card,CSV Card,Citi,Groceries,120.50,Groceries\n"
    )

    cfo = CFO(AgentConfig(name="cfo"), _make_audit(), data_dir=data_dir)
    cfo.initialize()

    result = cfo.sync_from_csv(csv_path)
    assert result["source"] == "csv"
    assert result["accounts_added"] == 2
    assert result["transactions_added"] == 2

    # Verify accounts were added
    assert cfo.get_account("CSV Checking") is not None
    assert cfo.get_account("CSV Card") is not None

    # Verify transactions
    assert len(cfo._transactions) == 2


def test_cfo_csv_sync_deduplicates():
    """Syncing the same CSV twice should not duplicate transactions."""
    data_dir = _make_data_dir()
    csv_path = data_dir / "rocket_money_dedup.csv"
    csv_path.write_text(
        "Date,Account Name,Name,Amount,Category\n"
        "2026-02-01,Checking,Groceries,50.00,Food\n"
    )

    cfo = CFO(AgentConfig(name="cfo"), _make_audit(), data_dir=data_dir)
    cfo.initialize()

    first = cfo.sync_from_csv(csv_path)
    assert first["transactions_added"] == 1

    second = cfo.sync_from_csv(csv_path)
    assert second["transactions_added"] == 0  # No duplicates
    assert len(cfo._transactions) == 1


def test_cfo_run_includes_rocket_money_recommendation():
    """When no RM credentials and no CSV, run() should recommend setup."""
    data_dir = _make_data_dir()
    cfo = CFO(AgentConfig(name="cfo"), _make_audit(), data_dir=data_dir)
    cfo.initialize()

    report = cfo.run()
    # Should have a recommendation about setting up Rocket Money
    all_text = " ".join(report.recommendations)
    assert "ROCKET_MONEY_API_KEY" in all_text or "Rocket Money" in all_text


def test_cfo_run_with_csv_file():
    """When a Rocket Money CSV exists in data dir, run() should sync it."""
    data_dir = _make_data_dir()
    csv_path = data_dir / "rocket_money_transactions.csv"
    csv_path.write_text(
        "Date,Account Name,Name,Amount,Category\n"
        "2026-02-10,Auto Checking,Coffee,5.50,Coffee Shops\n"
    )

    cfo = CFO(AgentConfig(name="cfo"), _make_audit(), data_dir=data_dir)
    cfo.initialize()

    report = cfo.run()
    # Should have synced the CSV
    assert any("CSV sync" in a for a in report.actions_taken)


def test_cfo_dashboard_includes_rocket_money():
    data_dir = _make_data_dir()
    cfo = CFO(AgentConfig(name="cfo"), _make_audit(), data_dir=data_dir)
    cfo.initialize()
    dashboard = cfo.dashboard()
    assert "rocket_money" in dashboard


# ---------------------------------------------------------------------------
# CFO + Empower
# ---------------------------------------------------------------------------

def test_cfo_has_empower_provider():
    data_dir = _make_data_dir()
    cfo = CFO(AgentConfig(name="cfo"), _make_audit(), data_dir=data_dir)
    cfo.initialize()
    assert cfo.empower is not None


def test_cfo_empower_status():
    data_dir = _make_data_dir()
    cfo = CFO(AgentConfig(name="cfo"), _make_audit(), data_dir=data_dir)
    cfo.initialize()
    status = cfo.empower_status()
    assert status["provider"] == "empower"
    assert status["connected"] is False


def test_cfo_run_includes_empower_recommendation():
    """When no Empower credentials, run() should recommend setup."""
    data_dir = _make_data_dir()
    cfo = CFO(AgentConfig(name="cfo"), _make_audit(), data_dir=data_dir)
    cfo.initialize()

    report = cfo.run()
    all_text = " ".join(report.recommendations)
    assert "EMPOWER_API_KEY" in all_text or "Empower" in all_text


def test_cfo_empower_sync_not_connected():
    data_dir = _make_data_dir()
    cfo = CFO(AgentConfig(name="cfo"), _make_audit(), data_dir=data_dir)
    cfo.initialize()

    result = cfo.sync_empower()
    assert result["connected"] is False


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

def test_empower_in_registry():
    from guardian_one.homelink.registry import IntegrationRegistry
    reg = IntegrationRegistry()
    reg.load_defaults()
    assert "empower" in reg.list_all()

    empower = reg.get("empower")
    assert empower is not None
    assert empower.owner_agent == "cfo"
    assert empower.auth_method == "api_key"
    assert len(empower.threat_model) == 5
    assert any("critical" == t.severity for t in empower.threat_model)


def test_cfo_registry_integrations():
    from guardian_one.homelink.registry import IntegrationRegistry
    reg = IntegrationRegistry()
    reg.load_defaults()
    cfo_integrations = reg.by_agent("cfo")
    names = [r.name for r in cfo_integrations]
    assert "rocket_money" in names
    assert "empower" in names
