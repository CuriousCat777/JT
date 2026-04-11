"""Tests for the Guardian One database module."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from guardian_one.database.manager import GuardianDatabase
from guardian_one.database.models import (
    CrawlRecord,
    FinancialAccount,
    FinancialTransaction,
    SystemCode,
    SystemLog,
)
from guardian_one.database.bridge import DatabaseBridge


@pytest.fixture
def db(tmp_path: Path) -> GuardianDatabase:
    """Create a fresh database in a temp directory."""
    return GuardianDatabase(tmp_path / "test.db")


@pytest.fixture
def bridge(tmp_path: Path) -> DatabaseBridge:
    return DatabaseBridge(tmp_path / "bridge_test.db")


# -----------------------------------------------------------------------
# Schema initialization
# -----------------------------------------------------------------------

class TestSchemaInit:
    def test_creates_database_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "init_test.db"
        GuardianDatabase(db_path)
        assert db_path.exists()

    def test_stats_returns_zero_counts(self, db: GuardianDatabase) -> None:
        stats = db.stats()
        assert stats["system_logs"] == 0
        assert stats["system_codes"] == 0
        assert stats["crawl_records"] == 0
        assert stats["financial_transactions"] == 0
        assert stats["financial_accounts"] == 0

    def test_double_init_is_safe(self, tmp_path: Path) -> None:
        db_path = tmp_path / "double.db"
        db1 = GuardianDatabase(db_path)
        db1.insert_log(SystemLog(agent="test", action="first"))
        db2 = GuardianDatabase(db_path)
        assert db2.count_logs() == 1


# -----------------------------------------------------------------------
# System Logs
# -----------------------------------------------------------------------

class TestSystemLogs:
    def test_insert_and_query(self, db: GuardianDatabase) -> None:
        db.insert_log(SystemLog(agent="cfo", action="sync", severity="info"))
        db.insert_log(SystemLog(agent="chronos", action="schedule", severity="warning"))
        logs = db.query_logs()
        assert len(logs) == 2

    def test_filter_by_agent(self, db: GuardianDatabase) -> None:
        db.insert_log(SystemLog(agent="cfo", action="sync"))
        db.insert_log(SystemLog(agent="chronos", action="schedule"))
        logs = db.query_logs(agent="cfo")
        assert len(logs) == 1
        assert logs[0].agent == "cfo"

    def test_filter_by_severity(self, db: GuardianDatabase) -> None:
        db.insert_log(SystemLog(agent="cfo", action="ok", severity="info"))
        db.insert_log(SystemLog(agent="cfo", action="fail", severity="error"))
        logs = db.query_logs(severity="error")
        assert len(logs) == 1
        assert logs[0].severity == "error"

    def test_search_logs(self, db: GuardianDatabase) -> None:
        db.insert_log(SystemLog(agent="cfo", action="sync", message="fetched 5 accounts"))
        db.insert_log(SystemLog(agent="cfo", action="report", message="generated report"))
        logs = db.query_logs(search="accounts")
        assert len(logs) == 1

    def test_count_logs(self, db: GuardianDatabase) -> None:
        for i in range(5):
            db.insert_log(SystemLog(agent="test", action=f"action_{i}"))
        assert db.count_logs() == 5

    def test_count_by_severity(self, db: GuardianDatabase) -> None:
        db.insert_log(SystemLog(severity="info"))
        db.insert_log(SystemLog(severity="info"))
        db.insert_log(SystemLog(severity="error"))
        assert db.count_logs(severity="info") == 2
        assert db.count_logs(severity="error") == 1

    def test_limit_and_offset(self, db: GuardianDatabase) -> None:
        for i in range(10):
            db.insert_log(SystemLog(agent="test", action=f"action_{i}"))
        logs = db.query_logs(limit=3)
        assert len(logs) == 3
        logs2 = db.query_logs(limit=3, offset=3)
        assert len(logs2) == 3
        assert logs[0].id != logs2[0].id

    def test_insert_logs_batch(self, db: GuardianDatabase) -> None:
        batch = [SystemLog(agent="bulk", action=f"a_{i}") for i in range(50)]
        count = db.insert_logs_batch(batch)
        assert count == 50
        assert db.count_logs() == 50

    def test_insert_logs_batch_empty(self, db: GuardianDatabase) -> None:
        assert db.insert_logs_batch([]) == 0

    def test_timestamps_use_z_suffix(self, db: GuardianDatabase) -> None:
        """Python-generated and DB-generated timestamps must both end in 'Z'."""
        from guardian_one.database.models import _now_iso

        # Python-generated
        assert _now_iso().endswith("Z")
        assert "+00:00" not in _now_iso()

        # Round-trip through the DB: inserted row has a Python timestamp,
        # and a row with schema default has a DB-generated timestamp. Both
        # must be lexicographically comparable.
        db.insert_log(SystemLog(agent="a", action="x"))
        rows = db.execute_raw("SELECT timestamp FROM system_logs")
        for row in rows:
            assert row["timestamp"].endswith("Z"), row["timestamp"]

    def test_timestamps_millisecond_precision(self) -> None:
        """Python timestamps must match the schema's millisecond precision.

        Regression: if ``_now_iso()`` uses microseconds but schema defaults
        use milliseconds, lexicographic TEXT ordering on the ``timestamp``
        column is wrong, breaking ``since=`` / ``until=`` filters.
        """
        import re
        from guardian_one.database.models import _now_iso

        ts = _now_iso()
        # Exactly 3 fractional digits followed by Z
        assert re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", ts
        ), ts
        # Total length must match the schema default: 23 chars + Z = 24
        assert len(ts) == 24, (len(ts), ts)


# -----------------------------------------------------------------------
# System Codes
# -----------------------------------------------------------------------

class TestSystemCodes:
    def test_insert_and_query(self, db: GuardianDatabase) -> None:
        db.insert_code(SystemCode(code_id="DEV-001", code_type="device", description="Test device"))
        codes = db.query_codes()
        assert len(codes) == 1
        assert codes[0].code_id == "DEV-001"

    def test_filter_by_type(self, db: GuardianDatabase) -> None:
        db.insert_code(SystemCode(code_id="DEV-001", code_type="device"))
        db.insert_code(SystemCode(code_id="CFG-001", code_type="config"))
        codes = db.query_codes(code_type="device")
        assert len(codes) == 1
        assert codes[0].code_type == "device"

    def test_update_status(self, db: GuardianDatabase) -> None:
        db.insert_code(SystemCode(code_id="KEY-001", status="active"))
        assert db.update_code_status("KEY-001", "expired")
        codes = db.query_codes()
        assert codes[0].status == "expired"

    def test_update_nonexistent_returns_false(self, db: GuardianDatabase) -> None:
        assert not db.update_code_status("NOPE", "expired")

    def test_unique_code_id(self, db: GuardianDatabase) -> None:
        db.insert_code(SystemCode(code_id="UNQ-001"))
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_code(SystemCode(code_id="UNQ-001"))


# -----------------------------------------------------------------------
# Crawl Records
# -----------------------------------------------------------------------

class TestCrawlRecords:
    def test_insert_and_query(self, db: GuardianDatabase) -> None:
        db.insert_crawl(CrawlRecord(
            bot_name="query_bot_1",
            target_url="https://example.com",
            status_code=200,
            title="Example",
        ))
        crawls = db.query_crawls()
        assert len(crawls) == 1
        assert crawls[0].bot_name == "query_bot_1"

    def test_batch_insert(self, db: GuardianDatabase) -> None:
        records = [
            CrawlRecord(bot_name="bot1", target_url=f"https://example.com/{i}")
            for i in range(5)
        ]
        count = db.insert_crawls_batch(records)
        assert count == 5
        assert len(db.query_crawls()) == 5

    def test_filter_by_bot(self, db: GuardianDatabase) -> None:
        db.insert_crawl(CrawlRecord(bot_name="bot_a", target_url="https://a.com"))
        db.insert_crawl(CrawlRecord(bot_name="bot_b", target_url="https://b.com"))
        crawls = db.query_crawls(bot_name="bot_a")
        assert len(crawls) == 1

    def test_filter_by_url(self, db: GuardianDatabase) -> None:
        db.insert_crawl(CrawlRecord(bot_name="bot", target_url="https://example.com/page"))
        db.insert_crawl(CrawlRecord(bot_name="bot", target_url="https://other.com/page"))
        crawls = db.query_crawls(url_contains="example")
        assert len(crawls) == 1

    def test_filter_by_tag(self, db: GuardianDatabase) -> None:
        db.insert_crawl(CrawlRecord(bot_name="bot", tags="finance,important"))
        db.insert_crawl(CrawlRecord(bot_name="bot", tags="health"))
        crawls = db.query_crawls(tag="finance")
        assert len(crawls) == 1


# -----------------------------------------------------------------------
# Financial Transactions
# -----------------------------------------------------------------------

class TestFinancialTransactions:
    def test_insert_and_query(self, db: GuardianDatabase) -> None:
        db.insert_transaction(FinancialTransaction(
            date="2026-03-01", description="Amazon", amount=-45.99,
            category="shopping", account="Chase Checking",
        ))
        txns = db.query_transactions()
        assert len(txns) == 1
        assert txns[0].amount == -45.99

    def test_deduplication_by_reference(self, db: GuardianDatabase) -> None:
        txn = FinancialTransaction(
            date="2026-03-01", description="Amazon", amount=-45.99,
            reference_id="TXN-001",
        )
        db.insert_transaction(txn)
        db.insert_transaction(txn)  # duplicate
        txns = db.query_transactions()
        assert len(txns) == 1

    def test_batch_insert(self, db: GuardianDatabase) -> None:
        txns = [
            FinancialTransaction(date=f"2026-03-{i:02d}", description=f"txn_{i}",
                                 amount=-10.0 * i, reference_id=f"REF-{i}")
            for i in range(1, 6)
        ]
        count = db.insert_transactions_batch(txns)
        assert count == 5

    def test_batch_dedupes_existing_refs_but_keeps_new_ones(
        self, db: GuardianDatabase
    ) -> None:
        """Regression: dedup must drop only the reference_id collisions,
        not the whole batch or unrelated rows."""
        db.insert_transaction(FinancialTransaction(
            date="2026-03-01", description="seed", amount=-1.0,
            reference_id="R-1",
        ))
        batch = [
            FinancialTransaction(date="2026-03-02", description="dup",
                                 amount=-2.0, reference_id="R-1"),  # dup
            FinancialTransaction(date="2026-03-03", description="new",
                                 amount=-3.0, reference_id="R-2"),  # new
            FinancialTransaction(date="2026-03-04", description="no-ref",
                                 amount=-4.0, reference_id=""),  # no key
        ]
        # Only the two non-duplicate rows should be inserted.
        assert db.insert_transactions_batch(batch) == 2
        assert len(db.query_transactions()) == 3

    def test_batch_dedupes_within_batch(self, db: GuardianDatabase) -> None:
        """Regression: the same reference_id appearing twice in one
        batch must only be inserted once."""
        batch = [
            FinancialTransaction(date="2026-03-01", amount=-1.0, reference_id="SAME"),
            FinancialTransaction(date="2026-03-02", amount=-2.0, reference_id="SAME"),
            FinancialTransaction(date="2026-03-03", amount=-3.0, reference_id="SAME"),
        ]
        assert db.insert_transactions_batch(batch) == 1
        assert len(db.query_transactions()) == 1

    def test_batch_surfaces_real_constraint_violations(
        self, db: GuardianDatabase
    ) -> None:
        """Regression: non-dedup constraint violations (like passing
        ``None`` for a ``NOT NULL`` column) must surface as
        ``sqlite3.IntegrityError``, not be silently swallowed.

        We construct the bad row with ``object.__setattr__`` to bypass
        the dataclass default, simulating what would happen if upstream
        code bypassed the bridge normalization and passed raw ``None``.
        """
        bad = FinancialTransaction(
            date="2026-03-01", description="x", amount=-1.0,
            reference_id="BAD-1",
        )
        # Force a NULL into the amount column (REAL NOT NULL DEFAULT 0.0)
        object.__setattr__(bad, "amount", None)
        # The single-row path must raise — not silently skip.
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_transaction(bad)

    def test_filter_by_category(self, db: GuardianDatabase) -> None:
        db.insert_transaction(FinancialTransaction(
            date="2026-03-01", category="food", amount=-20.0, reference_id="a"))
        db.insert_transaction(FinancialTransaction(
            date="2026-03-01", category="shopping", amount=-50.0, reference_id="b"))
        txns = db.query_transactions(category="food")
        assert len(txns) == 1

    def test_amount_range(self, db: GuardianDatabase) -> None:
        for i in range(1, 6):
            db.insert_transaction(FinancialTransaction(
                amount=-10.0 * i, reference_id=f"range-{i}"))
        txns = db.query_transactions(min_amount=-30.0, max_amount=-10.0)
        assert len(txns) == 3

    def test_spending_summary(self, db: GuardianDatabase) -> None:
        db.insert_transaction(FinancialTransaction(
            date="2026-03-01", category="food", amount=-50.0, reference_id="s1"))
        db.insert_transaction(FinancialTransaction(
            date="2026-03-02", category="food", amount=-25.0, reference_id="s2"))
        db.insert_transaction(FinancialTransaction(
            date="2026-03-01", category="shopping", amount=-100.0, reference_id="s3"))
        summary = db.spending_summary()
        assert summary["food"] == -75.0
        assert summary["shopping"] == -100.0


# -----------------------------------------------------------------------
# Financial Accounts
# -----------------------------------------------------------------------

class TestFinancialAccounts:
    def test_upsert_new(self, db: GuardianDatabase) -> None:
        db.upsert_account(FinancialAccount(
            name="Chase Checking", account_type="checking",
            balance=1500.0, institution="Chase",
        ))
        accounts = db.get_accounts()
        assert len(accounts) == 1
        assert accounts[0].balance == 1500.0

    def test_upsert_updates_existing(self, db: GuardianDatabase) -> None:
        db.upsert_account(FinancialAccount(
            name="Chase Checking", institution="Chase", balance=1500.0))
        db.upsert_account(FinancialAccount(
            name="Chase Checking", institution="Chase", balance=2000.0))
        accounts = db.get_accounts()
        assert len(accounts) == 1
        assert accounts[0].balance == 2000.0

    def test_filter_by_institution(self, db: GuardianDatabase) -> None:
        db.upsert_account(FinancialAccount(name="A", institution="Chase"))
        db.upsert_account(FinancialAccount(name="B", institution="BofA"))
        accounts = db.get_accounts(institution="Chase")
        assert len(accounts) == 1

    def test_net_worth(self, db: GuardianDatabase) -> None:
        db.upsert_account(FinancialAccount(
            name="Checking", account_type="checking", balance=5000.0, institution="Chase"))
        db.upsert_account(FinancialAccount(
            name="Credit Card", account_type="credit_card", balance=-1000.0, institution="Chase"))
        nw = db.net_worth()
        assert nw["total"] == 4000.0
        assert nw["by_type"]["checking"] == 5000.0
        assert nw["by_type"]["credit_card"] == -1000.0


# -----------------------------------------------------------------------
# Import helpers
# -----------------------------------------------------------------------

class TestImport:
    def test_import_audit_jsonl(self, db: GuardianDatabase, tmp_path: Path) -> None:
        jsonl_path = tmp_path / "audit.jsonl"
        entries = [
            {"timestamp": "2026-03-01T00:00:00Z", "agent": "cfo",
             "action": "sync", "severity": "info", "details": {}},
            {"timestamp": "2026-03-01T01:00:00Z", "agent": "chronos",
             "action": "schedule", "severity": "warning", "details": {"note": "conflict"}},
        ]
        with open(jsonl_path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        count = db.import_audit_jsonl(jsonl_path)
        assert count == 2
        logs = db.query_logs()
        assert len(logs) == 2

    def test_import_cfo_ledger(self, db: GuardianDatabase, tmp_path: Path) -> None:
        ledger_path = tmp_path / "cfo_ledger.json"
        data = {
            "saved_at": "2026-03-22T00:00:00Z",
            "accounts": [
                {"name": "Checking (5411)", "account_type": "checking",
                 "balance": 1238.93, "institution": "Bank of America",
                 "last_synced": "2026-03-19T00:00:00Z"},
                {"name": "Savings (5320)", "account_type": "savings",
                 "balance": 364.93, "institution": "Bank of America",
                 "last_synced": "2026-03-19T00:00:00Z"},
            ],
        }
        with open(ledger_path, "w") as f:
            json.dump(data, f)
        count = db.import_cfo_ledger(ledger_path)
        assert count == 2
        accounts = db.get_accounts()
        assert len(accounts) == 2

    def test_import_audit_jsonl_coerces_null_fields(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """Regression: a JSONL line with explicit ``null`` values for
        NOT NULL columns must not abort the whole import.  The row
        should land with default values instead."""
        jsonl_path = tmp_path / "audit.jsonl"
        entries = [
            {"timestamp": "2026-03-01T00:00:00Z", "agent": "cfo",
             "action": "sync", "severity": "info", "details": {}},
            # All fields that the schema marks NOT NULL are explicitly
            # null here. Pre-fix this would abort the whole batch.
            {"timestamp": None, "agent": None, "action": None,
             "severity": None, "details": None},
            {"timestamp": "2026-03-01T01:00:00Z", "agent": "chronos",
             "action": "schedule", "severity": "warning",
             "details": {"note": "conflict"}},
        ]
        with open(jsonl_path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        count = db.import_audit_jsonl(jsonl_path)
        assert count == 3
        logs = db.query_logs(limit=10)
        assert len(logs) == 3
        # The null row should have coerced defaults, not None.
        severities = {log.severity for log in logs}
        assert None not in severities

    def test_import_cfo_ledger_coerces_null_fields(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """Regression: a ledger account with explicit ``null`` fields
        must not abort the whole ledger import."""
        ledger_path = tmp_path / "cfo_ledger.json"
        data = {
            "saved_at": "2026-03-22T00:00:00Z",
            "accounts": [
                {"name": "Real Account", "account_type": "checking",
                 "balance": 1000.0, "institution": "Chase",
                 "last_synced": "2026-03-19T00:00:00Z"},
                # All NOT NULL fields explicitly null. Pre-fix this
                # would raise IntegrityError and abort the import.
                {"name": None, "account_type": None, "balance": None,
                 "institution": None, "last_synced": None},
                {"name": "Second Real", "account_type": "savings",
                 "balance": 500.0, "institution": "BofA"},
            ],
        }
        with open(ledger_path, "w") as f:
            json.dump(data, f)
        count = db.import_cfo_ledger(ledger_path)
        assert count == 3
        accounts = db.get_accounts()
        assert len(accounts) == 3
        for a in accounts:
            assert a.name is not None
            assert a.institution is not None
            assert a.balance is not None

    def test_import_cfo_ledger_parses_string_balances(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """Regression: ledger files may contain ``balance`` as a string
        (``"1238.93"``) or as garbage (``"N/A"``). The parser must
        convert parseable strings to floats and fall back to 0.0 for
        garbage — not let non-numeric values reach REAL columns."""
        ledger_path = tmp_path / "cfo_ledger.json"
        data = {
            "saved_at": "2026-03-22T00:00:00Z",
            "accounts": [
                {"name": "Parseable", "account_type": "checking",
                 "balance": "1238.93", "institution": "Chase"},
                {"name": "Already Float", "account_type": "savings",
                 "balance": 500.50, "institution": "BofA"},
                {"name": "Garbage", "account_type": "checking",
                 "balance": "N/A", "institution": "Other"},
                {"name": "With Suffix", "account_type": "credit_card",
                 "balance": "-99.99 USD", "institution": "Amex"},
            ],
        }
        with open(ledger_path, "w") as f:
            json.dump(data, f)
        count = db.import_cfo_ledger(ledger_path)
        assert count == 4
        accounts = {a.name: a for a in db.get_accounts()}
        assert isinstance(accounts["Parseable"].balance, float)
        assert accounts["Parseable"].balance == 1238.93
        assert accounts["Already Float"].balance == 500.50
        # Unparseable strings fall back to 0.0 (safer than a wrong
        # number, and won't crash downstream numeric logic).
        assert accounts["Garbage"].balance == 0.0
        assert accounts["With Suffix"].balance == 0.0

    def test_import_nonexistent_file(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        missing = tmp_path / "definitely-not-here.json"
        assert not missing.exists()
        assert db.import_audit_jsonl(missing) == 0
        assert db.import_cfo_ledger(missing) == 0


# -----------------------------------------------------------------------
# Database Bridge
# -----------------------------------------------------------------------

class TestDatabaseBridge:
    def test_log_audit_entry(self, bridge: DatabaseBridge) -> None:
        bridge.log_audit_entry(agent="cfo", action="sync", severity="info")
        logs = bridge.db.query_logs()
        assert len(logs) == 1

    def test_sync_accounts(self, bridge: DatabaseBridge) -> None:
        accounts = [
            {"name": "Checking", "account_type": "checking",
             "balance": 5000.0, "institution": "Chase"},
        ]
        count = bridge.sync_accounts(accounts, source="test")
        assert count == 1

    def test_sync_accounts_coerces_null_to_defaults(
        self, bridge: DatabaseBridge
    ) -> None:
        """Regression: upstream providers often send JSON ``null`` for
        optional fields. The bridge must coerce those to defaults so
        the sync doesn't abort on NOT NULL constraint violations."""
        accounts = [
            {"name": None, "account_type": None, "balance": None,
             "institution": None, "last_synced": None},
            {"name": "Real", "institution": "Bank"},  # mixed: missing + None
        ]
        count = bridge.sync_accounts(accounts, source="test")
        assert count == 2
        stored = bridge.db.get_accounts()
        assert len(stored) == 2
        # No None values made it into the table.
        for a in stored:
            assert a.name is not None
            assert a.institution is not None
            assert a.balance == 0.0 or a.balance == pytest.approx(a.balance)

    def test_sync_transactions(self, bridge: DatabaseBridge) -> None:
        txns = [
            {"date": "2026-03-01", "description": "Amazon",
             "amount": -45.99, "category": "shopping", "reference_id": "T1"},
            {"date": "2026-03-02", "description": "Starbucks",
             "amount": -5.50, "category": "food", "reference_id": "T2"},
        ]
        count = bridge.sync_transactions(txns, source="test")
        assert count == 2

    def test_sync_transactions_coerces_null_to_defaults(
        self, bridge: DatabaseBridge
    ) -> None:
        """Regression: JSON ``null`` fields in upstream transaction
        payloads must be coerced, not passed through as Python None."""
        txns = [
            {"date": None, "description": None, "amount": None,
             "category": None, "reference_id": "NULL-1"},
            {"date": "2026-03-02", "description": "ok",
             "amount": -5.50, "reference_id": "NULL-2"},
        ]
        count = bridge.sync_transactions(txns, source="test")
        assert count == 2
        stored = bridge.db.query_transactions()
        assert len(stored) == 2

    def test_sync_transactions_parses_string_amounts(
        self, bridge: DatabaseBridge
    ) -> None:
        """Regression: upstream providers sometimes return amounts as
        strings like ``"-20.50"``. The bridge must parse them into
        real floats so downstream numeric logic (amount < 0 filters,
        :,.2f formatting, spending_summary) keeps working."""
        txns = [
            {"date": "2026-03-01", "description": "parsable",
             "amount": "-20.50", "category": "food",
             "reference_id": "STR-1"},
            {"date": "2026-03-02", "description": "garbage",
             "amount": "N/A", "category": "shopping",
             "reference_id": "STR-2"},
            {"date": "2026-03-03", "description": "with suffix",
             "amount": "-99.99 USD", "category": "other",
             "reference_id": "STR-3"},
            {"date": "2026-03-04", "description": "already float",
             "amount": -5.25, "category": "food",
             "reference_id": "STR-4"},
        ]
        count = bridge.sync_transactions(txns, source="test")
        assert count == 4
        stored = bridge.db.query_transactions()
        assert len(stored) == 4

        # Every stored amount must be a real float so formatting and
        # arithmetic work downstream.
        by_ref = {t.reference_id: t for t in stored}
        assert isinstance(by_ref["STR-1"].amount, float)
        assert by_ref["STR-1"].amount == -20.50
        assert by_ref["STR-2"].amount == 0.0  # unparseable → default
        assert by_ref["STR-3"].amount == 0.0  # non-numeric suffix → default
        assert by_ref["STR-4"].amount == -5.25

        # spending_summary must find only the parseable negative rows.
        summary = bridge.db.spending_summary()
        assert summary.get("food") == -25.75  # -20.50 + -5.25
        # The garbage rows default to 0.0, so they don't pollute the
        # "shopping" / "other" buckets.
        assert "shopping" not in summary or summary["shopping"] == 0.0
        assert "other" not in summary or summary["other"] == 0.0

    def test_store_crawl(self, bridge: DatabaseBridge) -> None:
        row_id = bridge.store_crawl(
            bot_name="query_bot",
            target_url="https://example.com",
            status_code=200,
            title="Example Page",
            tags=["finance", "important"],
        )
        assert row_id > 0
        crawls = bridge.db.query_crawls()
        assert len(crawls) == 1
        assert crawls[0].tags == "finance,important"

    def test_store_code(self, bridge: DatabaseBridge) -> None:
        row_id = bridge.store_code(
            code_id="DEV-001",
            code_type="device",
            description="Test device code",
            associated_entity="camera_1",
        )
        assert row_id > 0
        codes = bridge.db.query_codes()
        assert len(codes) == 1


# -----------------------------------------------------------------------
# Raw SQL and maintenance
# -----------------------------------------------------------------------

class TestMaintenance:
    def test_execute_raw(self, db: GuardianDatabase) -> None:
        db.insert_log(SystemLog(agent="test", action="hello"))
        rows = db.execute_raw("SELECT COUNT(*) as cnt FROM system_logs")
        assert rows[0]["cnt"] == 1

    def test_execute_raw_accepts_with_cte(self, db: GuardianDatabase) -> None:
        db.insert_log(SystemLog(agent="a", action="x"))
        rows = db.execute_raw(
            "WITH agg AS (SELECT agent FROM system_logs) SELECT COUNT(*) AS n FROM agg"
        )
        assert rows[0]["n"] == 1

    def test_execute_raw_rejects_mutations(self, db: GuardianDatabase) -> None:
        db.insert_log(SystemLog(agent="target", action="keep"))
        for stmt in (
            "DELETE FROM system_logs",
            "UPDATE system_logs SET agent='x'",
            "DROP TABLE system_logs",
            "INSERT INTO system_logs(agent) VALUES ('x')",
            "-- comment\nDELETE FROM system_logs",
        ):
            with pytest.raises(ValueError):
                db.execute_raw(stmt)
        # Data was not touched.
        rows = db.execute_raw("SELECT COUNT(*) AS n FROM system_logs")
        assert rows[0]["n"] == 1

    def test_execute_raw_rejects_with_cte_mutation(
        self, db: GuardianDatabase
    ) -> None:
        """Regression: ``WITH x AS (SELECT 1) DELETE FROM ...`` must not
        slip past the prefix check — the read-only SQLite connection
        should refuse it at the engine level."""
        db.insert_log(SystemLog(agent="target", action="keep"))
        for stmt in (
            "WITH x AS (SELECT 1) DELETE FROM system_logs",
            "WITH x AS (SELECT 1) UPDATE system_logs SET agent='x'",
            "WITH x AS (SELECT 1) INSERT INTO system_logs(agent) VALUES ('x')",
        ):
            with pytest.raises(ValueError):
                db.execute_raw(stmt)
        # Data was not touched.
        rows = db.execute_raw("SELECT COUNT(*) AS n FROM system_logs")
        assert rows[0]["n"] == 1

    def test_execute_raw_propagates_real_query_errors(
        self, db: GuardianDatabase
    ) -> None:
        """Regression: a SELECT against a missing table must raise
        ``sqlite3.OperationalError`` — not be silently remapped as a
        "refused mutating statement"."""
        with pytest.raises(sqlite3.OperationalError) as exc_info:
            db.execute_raw("SELECT * FROM definitely_not_a_table")
        assert "no such table" in str(exc_info.value).lower()
        # Also check that a syntax error is not remapped either. The
        # prefix check lets "SELECT garbage syntax" through, then the
        # engine returns OperationalError which must propagate.
        with pytest.raises(sqlite3.OperationalError):
            db.execute_raw("SELECT FROM WHERE broken")

    def test_vacuum(self, db: GuardianDatabase) -> None:
        db.insert_log(SystemLog(agent="test", action="hello"))
        db.vacuum()  # should not raise

    def test_stats_includes_db_info(self, db: GuardianDatabase) -> None:
        stats = db.stats()
        assert "db_path" in stats
        assert "db_size_bytes" in stats
        assert stats["db_size_bytes"] > 0
