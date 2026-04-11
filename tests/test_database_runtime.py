"""Integration tests for the DatabaseBridge wiring into runtime flows.

These tests live in JT only (Ryzen does not ship ``AuditLog`` or
``CFO``). They verify that:

* ``AuditLog.record()`` mirrors every entry into ``system_logs``
  when a bridge is provided, without blocking on DB failures.
* The CFO agent mirrors ``save_ledger()`` into the database on
  every sync tail, so ``--db-accounts`` / ``--db-transactions``
  return live data rather than the stale ``--db-init`` snapshot.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.database.bridge import DatabaseBridge
from guardian_one.database.manager import GuardianDatabase


@pytest.fixture
def bridge(tmp_path: Path) -> DatabaseBridge:
    return DatabaseBridge(db_path=tmp_path / "runtime.db")


class TestAuditLogBridgeMirror:
    def test_record_mirrors_to_database(
        self, tmp_path: Path, bridge: DatabaseBridge
    ) -> None:
        """Every call to ``AuditLog.record()`` must also land in
        ``system_logs`` so ``--db-logs`` reflects live activity."""
        audit = AuditLog(log_dir=tmp_path / "logs", db_bridge=bridge)
        audit.record(
            agent="cfo", action="sync_plaid",
            severity=Severity.INFO,
            details={"accounts": 3, "transactions": 17},
        )
        audit.record(
            agent="chronos", action="schedule",
            severity=Severity.WARNING,
        )
        # JSONL write still happened.
        assert (tmp_path / "logs" / "audit.jsonl").exists()
        # DB mirror fired.
        logs = bridge.db.query_logs(limit=10)
        assert len(logs) == 2
        actions = {log.action for log in logs}
        assert actions == {"sync_plaid", "schedule"}
        # Source tag is set so --db-init's delete-and-replace
        # (keyed on source='audit.jsonl') leaves live mirror rows
        # alone.
        sources = {log.source for log in logs}
        assert sources == {"audit_runtime"}

    def test_record_without_bridge_still_works(
        self, tmp_path: Path
    ) -> None:
        """Sanity: AuditLog must still work when no bridge is passed."""
        audit = AuditLog(log_dir=tmp_path / "logs")
        entry = audit.record(agent="x", action="y")
        assert entry.action == "y"

    def test_bridge_failure_does_not_break_record(
        self, tmp_path: Path
    ) -> None:
        """Regression: a broken DB bridge must never block the
        canonical JSONL write."""
        class BrokenBridge:
            def log_audit_entry(self, **kwargs):  # noqa: ANN001
                raise RuntimeError("simulated DB failure")

        audit = AuditLog(log_dir=tmp_path / "logs", db_bridge=BrokenBridge())
        # Must not raise.
        audit.record(agent="x", action="y")
        assert (tmp_path / "logs" / "audit.jsonl").exists()


class TestCFOSaveLedgerBridgeMirror:
    def test_save_ledger_mirrors_accounts_and_transactions(
        self, tmp_path: Path, bridge: DatabaseBridge
    ) -> None:
        """Regression: ``CFO.save_ledger()`` must mirror accounts
        and transactions into the database so ``--db-accounts`` /
        ``--db-transactions`` show live data, not the
        ``--db-init`` snapshot."""
        from guardian_one.agents.cfo import (
            CFO, Account, AccountType, Transaction, TransactionCategory,
        )
        from guardian_one.core.config import AgentConfig

        # Stand up a minimal CFO wired to a sandbox audit + bridge.
        audit = AuditLog(log_dir=tmp_path / "logs")
        cfo = CFO(
            config=AgentConfig(name="cfo"),
            audit=audit,
            data_dir=tmp_path / "data",
            db_bridge=bridge,
        )
        # Inject a couple of accounts + transactions directly so we
        # don't need a real Plaid/Rocket Money provider.
        cfo._accounts["Checking"] = Account(
            name="Checking",
            account_type=AccountType.CHECKING,
            balance=1500.0,
            institution="Chase",
            last_synced="2026-03-01T00:00:00.000Z",
        )
        cfo._transactions.append(Transaction(
            date="2026-03-01",
            description="Amazon order",
            amount=-45.99,
            category=TransactionCategory.OTHER,
            account="Checking",
        ))
        cfo._transactions.append(Transaction(
            date="2026-03-02",
            description="Paycheck",
            amount=2500.00,
            category=TransactionCategory.INCOME,
            account="Checking",
        ))

        cfo.save_ledger()

        # Database now reflects the live ledger.
        accounts = bridge.db.get_accounts()
        assert len(accounts) == 1
        assert accounts[0].name == "Checking"
        assert accounts[0].balance == 1500.0

        txns = bridge.db.query_transactions()
        assert len(txns) == 2
        descs = {t.description for t in txns}
        assert descs == {"Amazon order", "Paycheck"}

        # Re-running save_ledger must be idempotent on the dedup
        # path: the transactions carry a deterministic reference_id
        # built from (account, date, amount, description), so a
        # second mirror does not duplicate rows.
        cfo.save_ledger()
        assert len(bridge.db.query_transactions()) == 2
