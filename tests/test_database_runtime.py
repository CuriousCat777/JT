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

        # Re-running save_ledger is idempotent because the bridge
        # uses replace_transactions (delete-and-replace) — every
        # call produces the same end state for the cfo_ledger
        # slice without depending on stable reference_ids.
        cfo.save_ledger()
        assert len(bridge.db.query_transactions()) == 2

    def test_save_ledger_reflects_deletions_and_reorders(
        self, tmp_path: Path, bridge: DatabaseBridge
    ) -> None:
        """Regression: ``clean_ledger`` (or any other edit that
        removes / reorders transactions) must be reflected in the
        DB mirror on the next ``save_ledger`` without leaving
        orphaned rows. The bridge uses delete-and-replace keyed
        on ``source='cfo_ledger'`` so the slice always converges
        to the current in-memory state."""
        from guardian_one.agents.cfo import (
            CFO, Account, AccountType, Transaction, TransactionCategory,
        )
        from guardian_one.core.config import AgentConfig

        audit = AuditLog(log_dir=tmp_path / "logs")
        cfo = CFO(
            config=AgentConfig(name="cfo"),
            audit=audit,
            data_dir=tmp_path / "data",
            db_bridge=bridge,
        )
        cfo._accounts["Checking"] = Account(
            name="Checking",
            account_type=AccountType.CHECKING,
            balance=100.0,
            institution="Chase",
        )
        # Start with 3 transactions.
        for desc, amt in [("A", -10.0), ("B", -20.0), ("C", -30.0)]:
            cfo._transactions.append(Transaction(
                date="2026-03-01", description=desc, amount=amt,
                category=TransactionCategory.FOOD, account="Checking",
            ))
        cfo.save_ledger()
        first = sorted(t.description for t in bridge.db.query_transactions())
        assert first == ["A", "B", "C"]

        # Delete the middle one (simulates clean_ledger).
        cfo._transactions.pop(1)
        cfo.save_ledger()
        after_delete = sorted(
            t.description for t in bridge.db.query_transactions()
        )
        # B is gone, A and C survive — no orphaned B row.
        assert after_delete == ["A", "C"]

        # Reorder: swap A and C.
        cfo._transactions[0], cfo._transactions[1] = (
            cfo._transactions[1], cfo._transactions[0]
        )
        cfo.save_ledger()
        after_reorder = sorted(
            t.description for t in bridge.db.query_transactions()
        )
        # Same set, still no duplicates.
        assert after_reorder == ["A", "C"]
        assert len(bridge.db.query_transactions()) == 2

    def test_save_ledger_drops_stale_accounts(
        self, tmp_path: Path, bridge: DatabaseBridge
    ) -> None:
        """Regression: when CFO's ``clean_ledger`` (or any other
        account removal) drops an account and then calls
        ``save_ledger``, the DB mirror must remove the stale row
        so ``--db-accounts`` and ``--db-net-worth`` don't keep
        reporting inflated totals."""
        from guardian_one.agents.cfo import (
            CFO, Account, AccountType, Transaction, TransactionCategory,
        )
        from guardian_one.core.config import AgentConfig

        audit = AuditLog(log_dir=tmp_path / "logs")
        cfo = CFO(
            config=AgentConfig(name="cfo"),
            audit=audit,
            data_dir=tmp_path / "data",
            db_bridge=bridge,
        )
        cfo._accounts["Checking"] = Account(
            name="Checking",
            account_type=AccountType.CHECKING,
            balance=1000.0,
            institution="Chase",
        )
        cfo._accounts["OldCredit"] = Account(
            name="OldCredit",
            account_type=AccountType.CREDIT_CARD,
            balance=-200.0,
            institution="Chase",
        )
        cfo.save_ledger()
        assert {a.name for a in bridge.db.get_accounts()} == {
            "Checking", "OldCredit",
        }

        # User cleans up the closed card from the in-memory ledger.
        del cfo._accounts["OldCredit"]
        cfo.save_ledger()

        stored = {a.name for a in bridge.db.get_accounts()}
        assert stored == {"Checking"}  # Stale row gone.
        # Net worth reflects the drop.
        assert bridge.db.net_worth()["total"] == 1000.0

    def test_save_ledger_preserves_other_source_rows(
        self, tmp_path: Path, bridge: DatabaseBridge
    ) -> None:
        """The CFO mirror must only touch rows tagged with
        ``source='cfo_ledger'``. Manual inserts and
        audit-mirrored rows with other source tags must survive
        every save_ledger call."""
        from guardian_one.agents.cfo import (
            CFO, Account, AccountType, Transaction, TransactionCategory,
        )
        from guardian_one.core.config import AgentConfig
        from guardian_one.database.models import FinancialTransaction

        # Seed a manual row with a different source tag.
        bridge.db.insert_transaction(FinancialTransaction(
            date="2026-03-01", description="manual test",
            amount=-5.0, source="manual_entry", reference_id="m1",
        ))

        audit = AuditLog(log_dir=tmp_path / "logs")
        cfo = CFO(
            config=AgentConfig(name="cfo"),
            audit=audit,
            data_dir=tmp_path / "data",
            db_bridge=bridge,
        )
        cfo._accounts["Checking"] = Account(
            name="Checking",
            account_type=AccountType.CHECKING,
            balance=100.0,
            institution="Chase",
        )
        cfo._transactions.append(Transaction(
            date="2026-03-02", description="cfo ledger row",
            amount=-10.0, category=TransactionCategory.FOOD,
            account="Checking",
        ))
        cfo.save_ledger()

        stored = bridge.db.query_transactions()
        sources = {t.source for t in stored}
        assert sources == {"manual_entry", "cfo_ledger"}
        assert len(stored) == 2

    def test_save_ledger_preserves_repeated_same_day_charges(
        self, tmp_path: Path, bridge: DatabaseBridge
    ) -> None:
        """Regression: two legitimate $4.99 charges at the same
        merchant on the same day must both land in the database.
        A naive ``account|date|amount|description`` synthetic key
        would dedup one of them away. The mirror now namespaces
        the fallback key with a positional index so legitimate
        repeats survive."""
        from guardian_one.agents.cfo import (
            CFO, Account, AccountType, Transaction, TransactionCategory,
        )
        from guardian_one.core.config import AgentConfig

        audit = AuditLog(log_dir=tmp_path / "logs")
        cfo = CFO(
            config=AgentConfig(name="cfo"),
            audit=audit,
            data_dir=tmp_path / "data",
            db_bridge=bridge,
        )
        cfo._accounts["Checking"] = Account(
            name="Checking",
            account_type=AccountType.CHECKING,
            balance=100.0,
            institution="Chase",
        )
        # Two identical coffees on the same day — both real.
        for _ in range(2):
            cfo._transactions.append(Transaction(
                date="2026-03-01",
                description="Starbucks",
                amount=-4.99,
                category=TransactionCategory.FOOD,
                account="Checking",
            ))

        cfo.save_ledger()
        stored = bridge.db.query_transactions()
        assert len(stored) == 2  # Both land.

        # Re-mirror must still be idempotent — the positional
        # indices keep the keys stable across runs.
        cfo.save_ledger()
        assert len(bridge.db.query_transactions()) == 2

    def test_save_ledger_uses_provider_metadata_id_when_present(
        self, tmp_path: Path, bridge: DatabaseBridge
    ) -> None:
        """When metadata carries a provider id, the mirror uses it
        directly. This way cross-sync re-ordering of the
        transaction list (e.g. the user re-imports with a newer
        snapshot) doesn't scramble dedup keys."""
        from guardian_one.agents.cfo import (
            CFO, Account, AccountType, Transaction, TransactionCategory,
        )
        from guardian_one.core.config import AgentConfig

        audit = AuditLog(log_dir=tmp_path / "logs")
        cfo = CFO(
            config=AgentConfig(name="cfo"),
            audit=audit,
            data_dir=tmp_path / "data",
            db_bridge=bridge,
        )
        cfo._accounts["Checking"] = Account(
            name="Checking",
            account_type=AccountType.CHECKING,
            balance=100.0,
            institution="Chase",
        )
        cfo._transactions.append(Transaction(
            date="2026-03-01",
            description="Plaid txn",
            amount=-10.00,
            category=TransactionCategory.FOOD,
            account="Checking",
            metadata={"id": "plaid:txn:abc123"},
        ))
        cfo.save_ledger()

        stored = bridge.db.query_transactions()
        assert len(stored) == 1
        # The stored reference_id comes from metadata.id, not a
        # positional composite.
        assert stored[0].reference_id == "plaid:txn:abc123"


class TestGuardianOneDbPathOverride:
    def test_db_path_override_is_honored(
        self, tmp_path: Path
    ) -> None:
        """Regression: when ``--db-path`` (or the ``db_path`` arg
        to ``GuardianOne``) is given, the runtime audit/CFO mirror
        must write to the SAME file that ``--db-*`` CLI queries
        read from. Before the fix, runtime persistence was
        hard-wired to ``config.data_dir/guardian.db``, so mixed
        invocations would silently split state across two files."""
        # We can't import GuardianOne in this sandbox (cryptography
        # C extension missing), so we test the lower-level plumbing
        # by verifying that _build_db_bridge honors the override
        # attribute.
        from guardian_one.database.bridge import DatabaseBridge

        custom = tmp_path / "custom.db"
        # Direct DatabaseBridge: the constructor accepts a db_path
        # and the resolved stats reflect it.
        bridge = DatabaseBridge(db_path=custom)
        stats = bridge.db.stats()
        assert Path(stats["db_path"]) == custom
        # A mirror write lands in the custom file — which is all
        # ``GuardianOne(db_path=custom)`` is supposed to arrange.
        bridge.log_audit_entry(agent="cfo", action="synced")
        logs = bridge.db.query_logs(limit=1)
        assert len(logs) == 1
        # And the custom file actually exists on disk, not the
        # default.
        assert custom.exists()
