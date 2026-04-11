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

    def test_dedup_is_namespaced_by_source_single(
        self, db: GuardianDatabase
    ) -> None:
        """Regression: two different providers may independently emit
        the same reference_id value. The second insert must not be
        silently dropped as a "duplicate" of the first — dedup should
        be keyed on ``(source, reference_id)``."""
        db.insert_transaction(FinancialTransaction(
            date="2026-03-01", description="Plaid txn",
            amount=-10.0, source="plaid", reference_id="123",
        ))
        # Same reference_id, different source — must land.
        inserted = db.insert_transaction(FinancialTransaction(
            date="2026-03-01", description="Rocket Money txn",
            amount=-20.0, source="rocket_money", reference_id="123",
        ))
        assert inserted > 0
        stored = db.query_transactions()
        assert len(stored) == 2
        sources = {t.source for t in stored}
        assert sources == {"plaid", "rocket_money"}

        # Re-inserting the plaid row with the same source is still a
        # duplicate (skipped).
        again = db.insert_transaction(FinancialTransaction(
            date="2026-03-01", description="Plaid txn",
            amount=-10.0, source="plaid", reference_id="123",
        ))
        assert again == 0
        assert len(db.query_transactions()) == 2

    def test_dedup_is_namespaced_by_source_batch(
        self, db: GuardianDatabase
    ) -> None:
        """Regression: the batch path must apply the same
        source-namespaced dedup — two providers with reference_id=123
        in the same batch must both land."""
        batch = [
            FinancialTransaction(date="2026-03-01", amount=-10.0,
                                 source="plaid", reference_id="X"),
            FinancialTransaction(date="2026-03-01", amount=-20.0,
                                 source="rocket_money", reference_id="X"),
            # Within-batch dup for the SAME source → skipped.
            FinancialTransaction(date="2026-03-02", amount=-30.0,
                                 source="plaid", reference_id="X"),
        ]
        assert db.insert_transactions_batch(batch) == 2
        stored = db.query_transactions()
        assert len(stored) == 2
        pairs = {(t.source, t.reference_id) for t in stored}
        assert pairs == {("plaid", "X"), ("rocket_money", "X")}

    def test_replace_transactions_for_source_delete_and_replace(
        self, db: GuardianDatabase
    ) -> None:
        """``replace_transactions_for_source`` wipes the slice
        tagged with the caller's ``source`` and bulk-inserts the
        new snapshot atomically, leaving rows with other sources
        untouched."""
        db.insert_transaction(FinancialTransaction(
            date="2026-03-01", description="plaid A",
            amount=-10.0, source="plaid", reference_id="p1",
        ))
        db.insert_transaction(FinancialTransaction(
            date="2026-03-02", description="plaid B",
            amount=-20.0, source="plaid", reference_id="p2",
        ))
        db.insert_transaction(FinancialTransaction(
            date="2026-03-03", description="manual A",
            amount=-5.0, source="manual", reference_id="m1",
        ))

        snapshot = [
            FinancialTransaction(
                date="2026-03-04", description="plaid C",
                amount=-30.0, reference_id="p3",
            ),
            FinancialTransaction(
                date="2026-03-05", description="plaid D",
                amount=-40.0, reference_id="p4",
            ),
        ]
        assert db.replace_transactions_for_source("plaid", snapshot) == 2

        stored = db.query_transactions()
        descs = sorted(t.description for t in stored)
        # Old plaid rows gone, new plaid rows present, manual row
        # still present.
        assert descs == ["manual A", "plaid C", "plaid D"]

    def test_replace_transactions_empty_input_wipes_the_slice(
        self, db: GuardianDatabase
    ) -> None:
        """Legitimate empty-snapshot semantics: passing an empty
        ``txns`` list is treated as "the caller has zero rows for
        this source" and the slice is cleared. This is required
        for CFO's ``save_ledger`` to converge to an empty mirror
        after ``clean_ledger`` or a user-initiated truncation.
        Previous revisions short-circuited on empty input and
        left stale rows behind.

        Rows with other source tags are still untouched."""
        db.insert_transaction(FinancialTransaction(
            date="2026-03-01", source="plaid", reference_id="p1",
        ))
        db.insert_transaction(FinancialTransaction(
            date="2026-03-02", source="manual", reference_id="m1",
        ))
        assert db.replace_transactions_for_source("plaid", []) == 0
        remaining = db.query_transactions()
        assert len(remaining) == 1
        assert remaining[0].source == "manual"

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

    def test_import_cfo_ledger_imports_transactions(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """Regression: ``cfo_ledger.json`` contains both
        ``accounts`` and ``transactions`` sections. The importer
        must populate ``financial_transactions`` as well so
        --db-transactions / --db-search / --db-spending return
        pre-existing history after --db-init (before any runtime
        sync rewrites it)."""
        ledger_path = tmp_path / "cfo_ledger.json"
        data = {
            "saved_at": "2026-03-22T00:00:00Z",
            "accounts": [
                {"name": "Checking", "account_type": "checking",
                 "balance": 1000.0, "institution": "Chase"},
            ],
            "transactions": [
                {"date": "2026-03-01", "description": "Amazon",
                 "amount": -45.99, "category": "other",
                 "account": "Checking"},
                {"date": "2026-03-02", "description": "Paycheck",
                 "amount": 2500.00, "category": "income",
                 "account": "Checking"},
                # Two same-day, same-amount charges — both should
                # land thanks to the occurrence-counter in the
                # synthesized ref.
                {"date": "2026-03-03", "description": "Starbucks",
                 "amount": -4.99, "category": "food",
                 "account": "Checking"},
                {"date": "2026-03-03", "description": "Starbucks",
                 "amount": -4.99, "category": "food",
                 "account": "Checking"},
            ],
        }
        with open(ledger_path, "w") as f:
            json.dump(data, f)
        db.import_cfo_ledger(ledger_path)

        stored = db.query_transactions()
        assert len(stored) == 4
        descs = sorted(t.description for t in stored)
        assert descs == ["Amazon", "Paycheck", "Starbucks", "Starbucks"]
        # All tagged with the cfo_ledger source.
        assert {t.source for t in stored} == {"cfo_ledger"}

        # Re-importing the same ledger is idempotent: the
        # replace_transactions path deletes the cfo_ledger slice
        # and re-inserts, converging to the same 4 rows.
        db.import_cfo_ledger(ledger_path)
        assert len(db.query_transactions()) == 4

    def test_import_cfo_ledger_without_transactions_key_leaves_slice(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """An old-format ledger with only ``accounts`` (no
        ``transactions`` key) must NOT wipe the existing
        cfo_ledger transaction slice — we can't distinguish
        "old format" from "zero transactions" otherwise."""
        # Pre-seed a cfo_ledger row via the bridge path so we can
        # verify it survives.
        db.insert_transaction(FinancialTransaction(
            date="2026-03-01", description="existing",
            amount=-10.0, source="cfo_ledger", reference_id="x1",
        ))
        ledger_path = tmp_path / "cfo_ledger.json"
        with open(ledger_path, "w") as f:
            json.dump({
                "saved_at": "2026-03-22T00:00:00Z",
                "accounts": [{"name": "Checking"}],
                # Note: no "transactions" key at all.
            }, f)
        db.import_cfo_ledger(ledger_path)
        # Existing row still present.
        assert len(db.query_transactions()) == 1

    def test_import_cfo_ledger_empty_transactions_wipes_slice(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """An explicit ``"transactions": []`` IS a meaningful
        "the ledger has zero transactions" snapshot and must
        replace the slice accordingly."""
        db.insert_transaction(FinancialTransaction(
            date="2026-03-01", description="stale",
            amount=-10.0, source="cfo_ledger", reference_id="x1",
        ))
        ledger_path = tmp_path / "cfo_ledger.json"
        with open(ledger_path, "w") as f:
            json.dump({
                "saved_at": "2026-03-22T00:00:00Z",
                "accounts": [{"name": "Checking"}],
                "transactions": [],
            }, f)
        db.import_cfo_ledger(ledger_path)
        assert db.query_transactions() == []

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

    def test_import_cfo_ledger_tolerates_non_utf8_bytes(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """Regression: a ledger file exported with a non-UTF-8 codec
        (e.g. Windows-1252) must not raise ``UnicodeDecodeError`` and
        abort ``--db-init``. The import should either succeed with
        replacement chars in the text fields or skip gracefully."""
        ledger_path = tmp_path / "cfo_ledger.json"
        # Valid JSON skeleton with a non-UTF-8 byte (0xA9 = ©
        # in latin-1) in the institution string.
        raw = (
            b'{"accounts": [{"name": "Checking", "account_type": '
            b'"checking", "balance": 100.0, '
            b'"institution": "Bank \xa9 2026"}]}'
        )
        ledger_path.write_bytes(raw)
        # Must not raise, must not crash the process.
        count = db.import_cfo_ledger(ledger_path)
        # Import succeeded via errors="replace" — the one account
        # landed with the replacement char in place of the 0xA9 byte.
        assert count == 1
        accounts = db.get_accounts()
        assert len(accounts) == 1
        assert "Bank" in accounts[0].institution

    def test_import_audit_jsonl_tolerates_non_utf8_bytes(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """Regression: an audit log file with non-UTF-8 bytes must
        not raise ``UnicodeDecodeError`` during line iteration."""
        jsonl_path = tmp_path / "audit.jsonl"
        raw = (
            b'{"timestamp": "2026-03-01T00:00:00Z", "agent": "cfo", '
            b'"action": "sync", "severity": "info", '
            b'"details": {"note": "ok \xa9 2026"}}\n'
            b'{"timestamp": "2026-03-02T00:00:00Z", "agent": "chronos", '
            b'"action": "schedule", "severity": "info"}\n'
        )
        jsonl_path.write_bytes(raw)
        count = db.import_audit_jsonl(jsonl_path)
        assert count == 2
        logs = db.query_logs()
        assert len(logs) == 2

    def test_import_cfo_ledger_tolerates_malformed_json(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """Regression: a corrupt or truncated ledger file must not
        raise ``json.JSONDecodeError`` and abort ``--db-init``. The
        import should skip the file and return 0 the same way
        ``import_audit_jsonl`` tolerates bad JSONL lines."""
        ledger_path = tmp_path / "cfo_ledger.json"
        ledger_path.write_text('{"accounts": [not valid json')
        # Must not raise.
        count = db.import_cfo_ledger(ledger_path)
        assert count == 0
        # The database is still usable and the accounts table empty.
        assert db.get_accounts() == []

    def test_import_cfo_ledger_tolerates_non_utf8_bytes(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """Regression: a ledger file exported with a non-UTF-8 codec
        (e.g. Windows-1252) must not raise ``UnicodeDecodeError`` and
        abort ``--db-init``. The import should succeed (with
        replacement chars) thanks to ``errors="replace"``."""
        ledger_path = tmp_path / "cfo_ledger.json"
        # Valid JSON skeleton with a non-UTF-8 byte (0xA9 = © in
        # latin-1) in the institution string.
        raw = (
            b'{"accounts": [{"name": "Checking", "account_type": '
            b'"checking", "balance": 100.0, '
            b'"institution": "Bank \xa9 2026"}]}'
        )
        ledger_path.write_bytes(raw)
        # Must not raise.
        count = db.import_cfo_ledger(ledger_path)
        assert count == 1
        accounts = db.get_accounts()
        assert len(accounts) == 1
        assert "Bank" in accounts[0].institution

    def test_import_audit_jsonl_includes_rotated_files(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """Regression: the audit subsystem rotates audit.jsonl into
        audit.jsonl.1 … audit.jsonl.5 where *higher* suffix == *older*
        file. --db-init must import all rotated siblings plus the
        current file, in chronological order, so no history is lost."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        # Create one line per rotation level with a distinct action
        # we can later assert on.
        rotated_entries = {
            "audit.jsonl.3": ("oldest", "2026-03-01T00:00:00.000Z"),
            "audit.jsonl.2": ("middle_a", "2026-03-02T00:00:00.000Z"),
            "audit.jsonl.1": ("middle_b", "2026-03-03T00:00:00.000Z"),
            "audit.jsonl": ("current", "2026-03-04T00:00:00.000Z"),
        }
        for name, (action, ts) in rotated_entries.items():
            (log_dir / name).write_text(
                json.dumps({"timestamp": ts, "agent": "cfo",
                            "action": action, "severity": "info"}) + "\n"
            )
        # Also drop a non-digit sibling that must be ignored.
        (log_dir / "audit.jsonl.bak").write_text("garbage")

        count = db.import_audit_jsonl(log_dir / "audit.jsonl")
        assert count == 4
        logs = db.query_logs(limit=20)
        actions = {log.action for log in logs}
        assert actions == {"oldest", "middle_a", "middle_b", "current"}

    def test_import_audit_jsonl_canonicalizes_bad_timestamps(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """Regression: a JSONL line with an unparseable ``timestamp``
        must not land a garbage string in the canonical TEXT column,
        where it could lex-compare incorrectly with real timestamps.
        Bad rows are rewritten to the epoch sentinel so they cluster
        harmlessly at the beginning of time-window queries."""
        jsonl_path = tmp_path / "audit.jsonl"
        entries = [
            {"timestamp": "2026-03-01T00:00:00Z",
             "agent": "cfo", "action": "good", "severity": "info"},
            # Completely unparseable → must be epoch sentinel, not
            # persisted verbatim.
            {"timestamp": "not a real date",
             "agent": "cfo", "action": "bad", "severity": "info"},
            # Missing timestamp field → same treatment.
            {"agent": "cfo", "action": "missing", "severity": "info"},
        ]
        with open(jsonl_path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        assert db.import_audit_jsonl(jsonl_path) == 3

        # Verify that NO stored timestamp is the raw garbage string.
        rows = db.execute_raw("SELECT action, timestamp FROM system_logs")
        by_action = {r["action"]: r["timestamp"] for r in rows}
        assert by_action["good"] == "2026-03-01T00:00:00.000Z"
        # Bad rows land at epoch sentinel.
        assert by_action["bad"] == "1970-01-01T00:00:00.000Z"
        assert by_action["missing"] == "1970-01-01T00:00:00.000Z"

        # A ``since=`` filter for a real time window must not
        # accidentally include the garbage rows just because they
        # sort "after" the boundary as raw TEXT.
        filtered = db.query_logs(since="2026-01-01T00:00:00Z", limit=20)
        filtered_actions = sorted(log.action for log in filtered)
        assert filtered_actions == ["good"]

    def test_import_audit_jsonl_rejects_lookalike_bad_timestamps(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """Regression: a string that *looks* canonical
        (``len == 24``, ends in ``Z``, has a ``.`` at position 19)
        but represents an impossible datetime
        (``2026-13-40T25:61:61.999Z``) must still be rewritten
        to the epoch sentinel. The previous shape-only check
        happily accepted such lookalike garbage."""
        jsonl_path = tmp_path / "audit.jsonl"
        entries = [
            {"timestamp": "2026-03-01T00:00:00Z",
             "agent": "cfo", "action": "good", "severity": "info"},
            # Shape matches canonical but values are impossible.
            {"timestamp": "2026-13-40T25:61:61.999Z",
             "agent": "cfo", "action": "lookalike", "severity": "info"},
            # Month 00 is also invalid.
            {"timestamp": "2026-00-15T12:00:00.000Z",
             "agent": "cfo", "action": "zero_month", "severity": "info"},
        ]
        with open(jsonl_path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        assert db.import_audit_jsonl(jsonl_path) == 3

        rows = db.execute_raw("SELECT action, timestamp FROM system_logs")
        by_action = {r["action"]: r["timestamp"] for r in rows}
        assert by_action["good"] == "2026-03-01T00:00:00.000Z"
        assert by_action["lookalike"] == "1970-01-01T00:00:00.000Z"
        assert by_action["zero_month"] == "1970-01-01T00:00:00.000Z"

        # Lookalike/zero_month must not leak into a real ``since=``
        # time window — they sort to epoch-zero.
        filtered = db.query_logs(since="2026-01-01T00:00:00Z", limit=20)
        actions = sorted(log.action for log in filtered)
        assert actions == ["good"]

    def test_import_audit_jsonl_is_idempotent(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """Regression: re-running --db-init (after a partial init with
        the entrypoint sentinel recovery) must NOT duplicate audit
        rows. The import is delete-and-replace keyed on
        ``source = 'audit.jsonl'``."""
        jsonl_path = tmp_path / "audit.jsonl"
        jsonl_path.write_text(
            json.dumps({"timestamp": "2026-03-01T00:00:00Z",
                        "agent": "cfo", "action": "sync",
                        "severity": "info"}) + "\n"
            + json.dumps({"timestamp": "2026-03-02T00:00:00Z",
                          "agent": "chronos", "action": "schedule",
                          "severity": "warning"}) + "\n"
        )
        # Also add a manually-inserted log with a different source;
        # it should survive the delete-and-replace.
        db.insert_log(SystemLog(agent="manual", action="created",
                                source="manual_entry"))

        assert db.import_audit_jsonl(jsonl_path) == 2
        first = db.query_logs(limit=50)
        assert len(first) == 3  # 2 from file + 1 manual

        # Second call: same file, must still only have 3 rows total.
        assert db.import_audit_jsonl(jsonl_path) == 2
        second = db.query_logs(limit=50)
        assert len(second) == 3
        # The manual row is still present.
        assert any(log.source == "manual_entry" for log in second)

    def test_import_audit_jsonl_missing_file_does_not_wipe_existing(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """Regression: re-running ``import_audit_jsonl`` when the
        source file is missing (or empty) must NOT delete previously
        imported rows. This matters for --db-init retries in an
        environment where the logs directory is temporarily absent
        or mis-mounted — silently wiping prior history would be a
        data-loss bug."""
        # First: import a real file so system_logs has audit rows.
        jsonl_path = tmp_path / "audit.jsonl"
        jsonl_path.write_text(
            json.dumps({"timestamp": "2026-03-01T00:00:00Z",
                        "agent": "cfo", "action": "sync",
                        "severity": "info"}) + "\n"
        )
        assert db.import_audit_jsonl(jsonl_path) == 1
        # Manual row with different source — should survive both calls.
        db.insert_log(SystemLog(agent="manual", action="keep",
                                source="manual_entry"))
        assert len(db.query_logs()) == 2

        # Now delete the file and re-run the import. The method must
        # return 0 without touching the previously-imported audit row.
        jsonl_path.unlink()
        assert db.import_audit_jsonl(jsonl_path) == 0
        after = db.query_logs(limit=50)
        assert len(after) == 2
        sources = {log.source for log in after}
        assert sources == {"audit.jsonl", "manual_entry"}

    def test_import_audit_jsonl_empty_file_does_not_wipe_existing(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """Regression: same guard as above, but for the case where
        the file exists but contains no valid rows (empty, or all
        lines malformed). Stale audit rows must be preserved."""
        jsonl_path = tmp_path / "audit.jsonl"
        jsonl_path.write_text(
            json.dumps({"timestamp": "2026-03-01T00:00:00Z",
                        "agent": "cfo", "action": "first",
                        "severity": "info"}) + "\n"
        )
        assert db.import_audit_jsonl(jsonl_path) == 1
        assert len(db.query_logs()) == 1

        # Replace the file with one that parses to zero valid rows.
        jsonl_path.write_text("not json\n{\n")
        assert db.import_audit_jsonl(jsonl_path) == 0
        # Original row is still there.
        after = db.query_logs(limit=50)
        assert len(after) == 1
        assert after[0].action == "first"

    def test_import_audit_jsonl_partial_read_failure_preserves_history(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """Regression: if ONE rotated sibling exists but is
        unreadable while others parse successfully, the delete-
        and-replace must be aborted entirely rather than replacing
        full history with a partial subset."""
        import os

        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        # Populate rotated siblings with good rows first.
        (log_dir / "audit.jsonl.2").write_text(
            json.dumps({"timestamp": "2026-03-01T00:00:00Z",
                        "agent": "cfo", "action": "oldest",
                        "severity": "info"}) + "\n"
        )
        (log_dir / "audit.jsonl.1").write_text(
            json.dumps({"timestamp": "2026-03-02T00:00:00Z",
                        "agent": "cfo", "action": "middle",
                        "severity": "info"}) + "\n"
        )
        (log_dir / "audit.jsonl").write_text(
            json.dumps({"timestamp": "2026-03-03T00:00:00Z",
                        "agent": "cfo", "action": "newest",
                        "severity": "info"}) + "\n"
        )
        # First import: clean.
        assert db.import_audit_jsonl(log_dir / "audit.jsonl") == 3
        actions_before = {log.action for log in db.query_logs(limit=20)}
        assert actions_before == {"oldest", "middle", "newest"}

        # Now make audit.jsonl.1 unreadable (chmod 000). Root in
        # the test sandbox can still read 000 files, so simulate
        # the failure with a monkeypatch on ``open`` for that
        # specific path instead.
        import builtins
        real_open = builtins.open
        target = str(log_dir / "audit.jsonl.1")

        def _fake_open(path, *args, **kwargs):  # noqa: ANN001
            if str(path) == target:
                raise OSError("simulated read failure")
            return real_open(path, *args, **kwargs)

        builtins.open = _fake_open
        try:
            # Second import: one file fails → must NOT wipe anything.
            assert db.import_audit_jsonl(log_dir / "audit.jsonl") == 0
        finally:
            builtins.open = real_open

        # All three original rows must still be present.
        actions_after = {log.action for log in db.query_logs(limit=20)}
        assert actions_after == actions_before

    def test_import_audit_jsonl_finds_rotated_only(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """Regression: a log directory that contains ONLY rotated
        siblings (``audit.jsonl.1``) and no base ``audit.jsonl`` must
        still import cleanly. The caller (cli.py --db-init) doesn't
        pre-check file existence, so the method is the single point
        of truth."""
        base = tmp_path / "audit.jsonl"
        # No base file — only a rotated sibling.
        (tmp_path / "audit.jsonl.1").write_text(
            json.dumps({"timestamp": "2026-03-01T00:00:00Z",
                        "agent": "cfo", "action": "rotated_only",
                        "severity": "info"}) + "\n"
        )
        assert db.import_audit_jsonl(base) == 1
        logs = db.query_logs(limit=5)
        assert len(logs) == 1
        assert logs[0].action == "rotated_only"

    def test_query_logs_normalizes_since_until_bounds(
        self, db: GuardianDatabase
    ) -> None:
        """Regression: ``since`` / ``until`` must be normalized to the
        canonical ms-``Z`` format before being compared against
        stored timestamps. Otherwise a naive boundary like
        ``...00:00Z`` would lex-compare as GREATER than stored
        ``...00:00.100Z`` (because ``Z`` > ``.``), wrongly excluding
        rows from the boundary second."""
        # Seed rows with canonical millisecond timestamps.
        for ms, action in [("100", "a"), ("200", "b"), ("900", "c")]:
            db.insert_log(SystemLog(
                timestamp=f"2026-03-02T00:00:00.{ms}Z",
                agent="test", action=action, severity="info",
            ))
        # Filter with an un-normalized boundary (no fractional seconds).
        # Pre-fix, comparing TEXT ``'2026-03-02T00:00:00Z'`` against
        # ``'2026-03-02T00:00:00.100Z'`` puts the former AFTER the
        # latter, so the >= filter would return zero rows.
        logs = db.query_logs(since="2026-03-02T00:00:00Z", limit=10)
        actions = sorted(log.action for log in logs)
        assert actions == ["a", "b", "c"]

        # Until must also be normalized. A plain ``...00:01Z`` should
        # include everything stored in the 00:00 minute.
        logs = db.query_logs(until="2026-03-02T00:00:01Z", limit=10)
        assert sorted(log.action for log in logs) == ["a", "b", "c"]

    def test_import_audit_jsonl_normalizes_legacy_timestamps(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """Regression: timestamps in legacy audit logs come in several
        shapes (``...27+00:00``, ``...27.320955+00:00``, ``...27Z``),
        and all must be normalized to the schema's canonical
        millisecond-``Z`` format so lexicographic TEXT ordering holds
        across imported + DB-generated rows.
        """
        jsonl_path = tmp_path / "audit.jsonl"
        entries = [
            # datetime.isoformat() — microseconds + offset
            {"timestamp": "2026-03-01T00:00:00.123456+00:00",
             "agent": "cfo", "action": "a", "severity": "info"},
            # no fractional seconds, Z suffix
            {"timestamp": "2026-03-02T00:00:00Z",
             "agent": "cfo", "action": "b", "severity": "info"},
            # no fractional seconds, offset
            {"timestamp": "2026-03-03T00:00:00+00:00",
             "agent": "cfo", "action": "c", "severity": "info"},
            # already canonical
            {"timestamp": "2026-03-04T00:00:00.456Z",
             "agent": "cfo", "action": "d", "severity": "info"},
        ]
        with open(jsonl_path, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        assert db.import_audit_jsonl(jsonl_path) == 4

        # Every stored timestamp must match the canonical shape.
        import re
        rows = db.execute_raw("SELECT timestamp FROM system_logs")
        for row in rows:
            ts = row["timestamp"]
            assert ts.endswith("Z"), ts
            assert "+" not in ts, ts
            assert re.match(
                r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", ts
            ), ts

        # Lexicographic ORDER BY now produces chronological order.
        ordered = db.query_logs(limit=10)
        actions = [log.action for log in ordered]
        # query_logs returns DESC, so expected order is d, c, b, a.
        assert actions == ["d", "c", "b", "a"]

        # A ``since=`` boundary filter now respects the chronological
        # intent across mixed source formats.
        since = "2026-03-02T00:00:00.000Z"
        filtered = db.query_logs(since=since)
        filtered_actions = sorted(log.action for log in filtered)
        assert filtered_actions == ["b", "c", "d"]

    def test_normalize_iso_timestamp_leaves_garbage_alone(self) -> None:
        """Regression: unparseable timestamps pass through unchanged
        so ``_coerce_str`` can still apply its own defaults."""
        from guardian_one.database.models import normalize_iso_timestamp
        assert normalize_iso_timestamp("not a date") == "not a date"
        assert normalize_iso_timestamp("") == ""
        assert normalize_iso_timestamp(None) == ""

    def test_import_cfo_ledger_tolerates_non_dict_top_level(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """A JSON file whose top-level is a list or primitive is
        syntactically valid JSON but not a ledger. Importing it must
        not crash — it should just import zero accounts."""
        ledger_path = tmp_path / "cfo_ledger.json"
        ledger_path.write_text('[1, 2, 3]')
        assert db.import_cfo_ledger(ledger_path) == 0

    def test_import_cfo_ledger_parses_string_balances(
        self, db: GuardianDatabase, tmp_path: Path
    ) -> None:
        """Regression: ledger files contain ``balance`` in many shapes:
        plain strings, thousand-separated, currency-prefixed
        (``"$500.00"``, ``"-$99.99"``), currency-suffixed, or garbage.
        Special attention to ``"-$99.99"`` — the negative sign sits
        before the currency symbol, and a naive regex extract would
        drop the sign and flip a debit into a credit."""
        ledger_path = tmp_path / "cfo_ledger.json"
        data = {
            "saved_at": "2026-03-22T00:00:00Z",
            "accounts": [
                {"name": "Plain String", "account_type": "checking",
                 "balance": "1238.93", "institution": "Chase"},
                {"name": "Already Float", "account_type": "savings",
                 "balance": 500.50, "institution": "BofA"},
                {"name": "Thousand Separated", "account_type": "checking",
                 "balance": "1,238.93", "institution": "Wells"},
                {"name": "Negative Separated", "account_type": "credit_card",
                 "balance": "-1,234,567.89", "institution": "Cap One"},
                {"name": "With Suffix", "account_type": "credit_card",
                 "balance": "-99.99 USD", "institution": "Amex"},
                {"name": "Currency Prefix", "account_type": "savings",
                 "balance": "$500.00", "institution": "BofA"},
                {"name": "Neg Currency Prefix", "account_type": "credit_card",
                 "balance": "-$99.99", "institution": "Discover"},
                {"name": "Neg Currency Prefix Sep", "account_type": "credit_card",
                 "balance": "-$1,234.56", "institution": "Citi"},
                {"name": "Garbage", "account_type": "checking",
                 "balance": "N/A", "institution": "Other"},
            ],
        }
        with open(ledger_path, "w") as f:
            json.dump(data, f)
        count = db.import_cfo_ledger(ledger_path)
        assert count == 9
        accounts = {a.name: a for a in db.get_accounts()}
        assert isinstance(accounts["Plain String"].balance, float)
        assert accounts["Plain String"].balance == 1238.93
        assert accounts["Already Float"].balance == 500.50
        assert accounts["Thousand Separated"].balance == 1238.93
        assert accounts["Negative Separated"].balance == -1234567.89
        assert accounts["With Suffix"].balance == -99.99
        assert accounts["Currency Prefix"].balance == 500.00
        # Critical: the ``-`` sits before the ``$`` and must be
        # preserved so a debit doesn't become a credit.
        assert accounts["Neg Currency Prefix"].balance == -99.99
        assert accounts["Neg Currency Prefix Sep"].balance == -1234.56
        # Pure garbage with no numeric token still falls back to 0.0.
        assert accounts["Garbage"].balance == 0.0

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

    def test_sync_transactions_empty_reference_id_falls_back_to_id(
        self, bridge: DatabaseBridge
    ) -> None:
        """Regression: upstream payloads like
        ``{"reference_id": "", "id": "abc"}`` must use ``id`` as the
        dedup key. Before the fix, ``_s`` returned ``""`` unchanged
        and the row bypassed the partial unique index, so re-sync
        silently duplicated the row."""
        txns = [
            {"date": "2026-03-01", "description": "first",
             "amount": -10.0, "reference_id": "", "id": "A1"},
            {"date": "2026-03-02", "description": "second",
             "amount": -20.0, "reference_id": None, "id": "B2"},
        ]
        # First sync: both land.
        assert bridge.sync_transactions(txns) == 2
        stored = bridge.db.query_transactions()
        refs = {t.reference_id for t in stored}
        assert refs == {"A1", "B2"}
        # Re-sync: dedup must catch them via the fallback id.
        assert bridge.sync_transactions(txns) == 0
        assert len(bridge.db.query_transactions()) == 2

    def test_sync_transactions_both_empty_ids_are_missing_keys(
        self, bridge: DatabaseBridge
    ) -> None:
        """When both reference_id and id are empty/None/missing,
        the row gets an empty dedup key (same as before) and the
        caller accepts duplicate risk."""
        txns = [
            {"date": "2026-03-01", "description": "no key",
             "amount": -5.0, "reference_id": "", "id": None},
        ]
        assert bridge.sync_transactions(txns) == 1
        stored = bridge.db.query_transactions()
        assert stored[0].reference_id == ""

    def test_sync_transactions_numeric_reference_id_resyncs(
        self, bridge: DatabaseBridge
    ) -> None:
        """Regression: upstream providers sometimes send numeric
        ``reference_id`` values (e.g. ``123``). Both the first sync
        and every subsequent re-sync must succeed — the stored value
        must match the incoming value's str form so the dedup
        pre-check catches duplicates before they hit the UNIQUE index.
        """
        txns = [
            {"date": "2026-03-01", "description": "numeric id",
             "amount": -20.0, "reference_id": 123},
            {"date": "2026-03-02", "description": "still numeric",
             "amount": -30.0, "reference_id": 456},
        ]
        # First sync: both rows land.
        assert bridge.sync_transactions(txns) == 2
        stored = bridge.db.query_transactions()
        # reference_id must be stored as a string, not an int.
        for row in stored:
            assert isinstance(row.reference_id, str)
        # Re-sync must be idempotent (0 new rows, no IntegrityError).
        assert bridge.sync_transactions(txns) == 0
        assert len(bridge.db.query_transactions()) == 2

    def test_sync_accounts_numeric_fields_are_stringified(
        self, bridge: DatabaseBridge
    ) -> None:
        """Regression: a numeric ``name`` or ``institution`` from a
        quirky upstream payload should not break re-sync via the
        ``upsert_account`` unique-name check."""
        accounts = [
            {"name": 42, "account_type": "checking",
             "balance": 100.0, "institution": "Chase"},
        ]
        assert bridge.sync_accounts(accounts) == 1
        stored = bridge.db.get_accounts()
        assert len(stored) == 1
        assert stored[0].name == "42"
        assert isinstance(stored[0].name, str)

    def test_sync_accounts_skips_non_dict_entries(
        self, bridge: DatabaseBridge
    ) -> None:
        """Regression: a stray ``null`` / primitive in the provider's
        account list must not abort the sync via ``AttributeError``
        inside ``_s``. Bad entries are skipped; good ones land."""
        accounts = [
            {"name": "First", "institution": "Chase",
             "balance": 100.0, "account_type": "checking"},
            None,
            "unexpected string",
            42,
            {"name": "Second", "institution": "BofA",
             "balance": 200.0, "account_type": "savings"},
        ]
        assert bridge.sync_accounts(accounts) == 2
        stored = bridge.db.get_accounts()
        assert len(stored) == 2
        names = {a.name for a in stored}
        assert names == {"First", "Second"}

    def test_sync_transactions_skips_non_dict_entries(
        self, bridge: DatabaseBridge
    ) -> None:
        """Regression: a stray ``null`` / primitive in the provider's
        transaction list must not abort the batch via ``AttributeError``
        inside ``_s``. Bad entries are filtered out of the generator;
        good ones land."""
        txns = [
            {"date": "2026-03-01", "description": "Good A",
             "amount": -10.0, "reference_id": "A"},
            None,
            [],
            "broken",
            {"date": "2026-03-02", "description": "Good B",
             "amount": -20.0, "reference_id": "B"},
        ]
        assert bridge.sync_transactions(txns) == 2
        stored = bridge.db.query_transactions()
        assert len(stored) == 2
        refs = {t.reference_id for t in stored}
        assert refs == {"A", "B"}

    def test_sync_transactions_parses_string_amounts(
        self, bridge: DatabaseBridge
    ) -> None:
        """Regression: upstream providers return amounts in many
        shapes — plain strings, thousand-separated, currency
        suffixed/prefixed, and occasional garbage. The bridge must
        extract the numeric value where possible and only fall
        back to 0.0 when no numeric token is present."""
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
            {"date": "2026-03-05", "description": "thousand-separated",
             "amount": "-1,238.93", "category": "food",
             "reference_id": "STR-5"},
            {"date": "2026-03-06", "description": "currency prefix",
             "amount": "$500.00", "category": "income",
             "reference_id": "STR-6"},
        ]
        count = bridge.sync_transactions(txns, source="test")
        assert count == 6
        stored = bridge.db.query_transactions()
        assert len(stored) == 6

        # Every stored amount must be a real float so formatting and
        # arithmetic work downstream.
        by_ref = {t.reference_id: t for t in stored}
        assert isinstance(by_ref["STR-1"].amount, float)
        assert by_ref["STR-1"].amount == -20.50
        assert by_ref["STR-2"].amount == 0.0  # unparseable → default
        assert by_ref["STR-3"].amount == -99.99  # suffix stripped
        assert by_ref["STR-4"].amount == -5.25
        assert by_ref["STR-5"].amount == -1238.93  # thousand-sep stripped
        assert by_ref["STR-6"].amount == 500.00  # currency prefix stripped

        # spending_summary must find every parseable negative row,
        # including the thousand-separated one (pre-fix it was 0.0
        # and would have been lost from the "food" bucket).
        summary = bridge.db.spending_summary()
        # food: -20.50 + -5.25 + -1238.93 = -1264.68
        assert summary.get("food") == pytest.approx(-1264.68)
        assert summary.get("other") == pytest.approx(-99.99)

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
