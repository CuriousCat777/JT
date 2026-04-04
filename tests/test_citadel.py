"""Tests for CITADEL ONE — SQLite backup database."""

import json
from pathlib import Path

import pytest

from guardian_one.core.citadel import CitadelOne, _TABLES


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Create a temporary project root with sample data files."""
    # logs/audit.jsonl
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    audit_entries = [
        {"timestamp": "2026-03-01T00:00:00Z", "agent": "chronos", "action": "sync",
         "severity": "info", "details": {"source": "calendar"}, "requires_review": False},
        {"timestamp": "2026-03-01T01:00:00Z", "agent": "cfo", "action": "bill_alert",
         "severity": "warning", "details": {"bill": "rent"}, "requires_review": True},
    ]
    with open(logs_dir / "audit.jsonl", "w") as f:
        for entry in audit_entries:
            f.write(json.dumps(entry) + "\n")

    # data/cfo_ledger.json
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    ledger = {
        "saved_at": "2026-03-22T00:00:00Z",
        "accounts": [
            {"name": "Checking", "account_type": "checking", "balance": 1500.00,
             "institution": "Test Bank", "last_synced": "2026-03-22T00:00:00Z"},
            {"name": "Savings", "account_type": "savings", "balance": 5000.00,
             "institution": "Test Bank", "last_synced": "2026-03-22T00:00:00Z"},
        ],
        "transactions": [
            {"date": "2026-03-20", "description": "Grocery Store", "amount": -85.50,
             "category": "food", "account": "Checking", "metadata": {"source": "plaid"}},
            {"date": "2026-03-21", "description": "Payroll Deposit", "amount": 3200.00,
             "category": "income", "account": "Checking", "metadata": {"source": "plaid"}},
        ],
        "bills": [
            {"name": "Electric", "amount": 120.00, "due_date": "2026-04-01",
             "recurring": True, "frequency": "monthly", "auto_pay": True, "paid": False},
        ],
        "budgets": [
            {"category": "food", "budget_limit": 500.00, "label": "Groceries & Dining"},
        ],
        "net_worth_history": [
            {"date": "2026-03-20", "net_worth": 6500.00,
             "by_type": {"checking": 1500.0, "savings": 5000.0}},
            {"date": "2026-03-21", "net_worth": 9700.00,
             "by_type": {"checking": 4700.0, "savings": 5000.0}},
        ],
    }
    with open(data_dir / "cfo_ledger.json", "w") as f:
        json.dump(ledger, f)

    # data/evaluations.jsonl
    eval_cycle = {
        "cycle": 1,
        "timestamp": "2026-03-20T12:00:00Z",
        "evaluations": [
            {
                "agent_name": "chronos",
                "timestamp": "2026-03-20T12:00:00Z",
                "overall_pct": 92.0,
                "overall_rating": 5,
                "rating_label": "Exceptional",
                "metrics": [
                    {"name": "Availability", "score_pct": 100.0, "rating": 5, "detail": "Online"},
                    {"name": "Task Completion", "score_pct": 100.0, "rating": 5, "detail": "All done"},
                ],
            }
        ],
        "system_overall_pct": 92.0,
        "system_overall_rating": 5,
    }
    with open(data_dir / "evaluations.jsonl", "w") as f:
        f.write(json.dumps(eval_cycle) + "\n")

    # config/guardian_config.yaml
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    with open(config_dir / "guardian_config.yaml", "w") as f:
        f.write("owner: Test Owner\ntimezone: America/Chicago\ndata_dir: data\n")

    # guardian_one_log.json
    op_log = {
        "log_version": "0.2.2",
        "owner": "Test Owner",
        "entries": [
            {
                "entry_id": 1,
                "timestamp": "2026-02-23T17:20:16Z",
                "category": "system",
                "intent": "decision",
                "summary": "Test entry one",
                "context": "Unit test",
                "outcome": "Passed",
                "confidence": "high",
                "tags": ["test"],
                "metadata": {"key": "value"},
                "prev_hash": "GENESIS",
                "entry_hash": "abc123",
            },
            {
                "entry_id": 2,
                "timestamp": "2026-02-24T10:00:00Z",
                "category": "financial",
                "intent": "record",
                "summary": "Test entry two",
                "context": "Unit test",
                "outcome": "Recorded",
                "confidence": "high",
                "tags": ["test", "finance"],
                "metadata": {},
                "prev_hash": "abc123",
                "entry_hash": "def456",
            },
        ],
    }
    with open(tmp_path / "guardian_one_log.json", "w") as f:
        json.dump(op_log, f)

    # guardian_errors.json
    errors = {
        "version": "0.1.0",
        "errors": [
            {
                "id": "err_0001",
                "timestamp": "2026-02-23T23:00:00Z",
                "type": "navigation",
                "what": "Wrong directory",
                "why": "Forgot to cd",
                "fix": "cd first",
                "context": "Testing",
                "related_skill": "CLI",
                "recurrence_count": 1,
                "resolved": True,
                "hash": "aaa111",
            },
        ],
    }
    with open(tmp_path / "guardian_errors.json", "w") as f:
        json.dump(errors, f)

    # guardian_skills.json
    skills = {
        "version": "0.1.0",
        "skills": [
            {
                "id": "skill_0001",
                "name": "Python Variables",
                "domain": "python-core",
                "description": "Variables and types",
                "level": 3,
                "level_label": "COMPETENT",
                "created": "2026-02-23T23:06:23Z",
                "last_assessed": "2026-02-23T23:06:23Z",
                "assessment_count": 1,
                "evidence": [{"date": "2026-02-23", "level_to": 3, "evidence": "Test"}],
                "hash": "bbb222",
            },
            {
                "id": "skill_0002",
                "name": "Python Dicts",
                "domain": "python-core",
                "description": "Dictionary usage",
                "level": 4,
                "level_label": "PROFICIENT",
                "created": "2026-02-23T23:06:23Z",
                "last_assessed": "2026-03-01T00:00:00Z",
                "assessment_count": 2,
                "evidence": [],
                "hash": "ccc333",
            },
        ],
    }
    with open(tmp_path / "guardian_skills.json", "w") as f:
        json.dump(skills, f)

    return tmp_path


@pytest.fixture
def citadel(project: Path) -> CitadelOne:
    """Create a CitadelOne instance pointed at the temp project."""
    db_path = project / "data" / "citadel_one.db"
    c = CitadelOne(db_path=db_path, project_root=project)
    yield c
    c.close()


# ------------------------------------------------------------------
# Table creation
# ------------------------------------------------------------------

class TestTableCreation:
    def test_all_tables_exist(self, citadel: CitadelOne) -> None:
        """Every table defined in _TABLES should exist in the database."""
        rows = citadel._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {row["name"] for row in rows}
        for expected in _TABLES:
            assert expected in table_names, f"Missing table: {expected}"

    def test_backup_manifest_exists(self, citadel: CitadelOne) -> None:
        assert "backup_manifest" in {
            row["name"]
            for row in citadel._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }


# ------------------------------------------------------------------
# Individual backup methods
# ------------------------------------------------------------------

class TestBackupAuditLog:
    def test_backup_ingests_entries(self, citadel: CitadelOne) -> None:
        count = citadel.backup_audit_log()
        assert count == 2

        rows = citadel._conn.execute("SELECT * FROM audit_log").fetchall()
        assert len(rows) == 2
        assert rows[0]["agent"] == "chronos"
        assert rows[1]["severity"] == "warning"

    def test_backup_is_idempotent(self, citadel: CitadelOne) -> None:
        citadel.backup_audit_log()
        citadel.backup_audit_log()
        rows = citadel._conn.execute("SELECT * FROM audit_log").fetchall()
        assert len(rows) == 2

    def test_backup_logs_manifest(self, citadel: CitadelOne) -> None:
        citadel.backup_audit_log()
        manifest = citadel._conn.execute(
            "SELECT * FROM backup_manifest WHERE table_name = 'audit_log'"
        ).fetchall()
        assert len(manifest) == 1
        assert manifest[0]["status"] == "success"
        assert manifest[0]["records_backed_up"] == 2


class TestBackupFinancialData:
    def test_accounts_backed_up(self, citadel: CitadelOne) -> None:
        citadel.backup_financial_data()
        rows = citadel._conn.execute("SELECT * FROM accounts").fetchall()
        assert len(rows) == 2
        names = {row["name"] for row in rows}
        assert "Checking" in names
        assert "Savings" in names

    def test_transactions_backed_up(self, citadel: CitadelOne) -> None:
        citadel.backup_financial_data()
        rows = citadel._conn.execute("SELECT * FROM transactions").fetchall()
        assert len(rows) == 2

    def test_bills_backed_up(self, citadel: CitadelOne) -> None:
        citadel.backup_financial_data()
        rows = citadel._conn.execute("SELECT * FROM bills").fetchall()
        assert len(rows) == 1
        assert rows[0]["name"] == "Electric"

    def test_budgets_backed_up(self, citadel: CitadelOne) -> None:
        citadel.backup_financial_data()
        rows = citadel._conn.execute("SELECT * FROM budgets").fetchall()
        assert len(rows) == 1
        assert rows[0]["category"] == "food"

    def test_net_worth_backed_up(self, citadel: CitadelOne) -> None:
        citadel.backup_financial_data()
        rows = citadel._conn.execute("SELECT * FROM net_worth_snapshots").fetchall()
        assert len(rows) == 2

    def test_financial_idempotent(self, citadel: CitadelOne) -> None:
        citadel.backup_financial_data()
        citadel.backup_financial_data()
        assert citadel._conn.execute("SELECT COUNT(*) as cnt FROM accounts").fetchone()["cnt"] == 2
        assert citadel._conn.execute("SELECT COUNT(*) as cnt FROM transactions").fetchone()["cnt"] == 2
        assert citadel._conn.execute("SELECT COUNT(*) as cnt FROM bills").fetchone()["cnt"] == 1
        assert citadel._conn.execute("SELECT COUNT(*) as cnt FROM net_worth_snapshots").fetchone()["cnt"] == 2

    def test_account_balance_updated(self, citadel: CitadelOne, project: Path) -> None:
        """Account balances should update on subsequent backups."""
        citadel.backup_financial_data()

        # Update balance in source
        ledger_path = project / "data" / "cfo_ledger.json"
        with open(ledger_path) as f:
            ledger = json.load(f)
        ledger["accounts"][0]["balance"] = 9999.99
        with open(ledger_path, "w") as f:
            json.dump(ledger, f)

        citadel.backup_financial_data()
        row = citadel._conn.execute(
            "SELECT balance FROM accounts WHERE name = 'Checking'"
        ).fetchone()
        assert row["balance"] == 9999.99


class TestBackupEvaluations:
    def test_evaluation_cycle_ingested(self, citadel: CitadelOne) -> None:
        count = citadel.backup_evaluations()
        assert count == 1

        cycles = citadel._conn.execute("SELECT * FROM evaluation_cycles").fetchall()
        assert len(cycles) == 1
        assert cycles[0]["system_overall_pct"] == 92.0

    def test_agent_evaluations_linked(self, citadel: CitadelOne) -> None:
        citadel.backup_evaluations()
        evals = citadel._conn.execute("SELECT * FROM agent_evaluations").fetchall()
        assert len(evals) == 1
        assert evals[0]["agent_name"] == "chronos"
        assert evals[0]["rating_label"] == "Exceptional"

    def test_metric_scores_linked(self, citadel: CitadelOne) -> None:
        citadel.backup_evaluations()
        metrics = citadel._conn.execute("SELECT * FROM metric_scores").fetchall()
        assert len(metrics) == 2
        names = {m["metric_name"] for m in metrics}
        assert "Availability" in names
        assert "Task Completion" in names

    def test_evaluations_idempotent(self, citadel: CitadelOne) -> None:
        citadel.backup_evaluations()
        citadel.backup_evaluations()
        assert citadel._conn.execute("SELECT COUNT(*) as cnt FROM evaluation_cycles").fetchone()["cnt"] == 1


class TestBackupConfig:
    def test_config_backed_up(self, citadel: CitadelOne) -> None:
        count = citadel.backup_config()
        assert count == 3  # owner, timezone, data_dir

        rows = citadel._conn.execute("SELECT * FROM system_config").fetchall()
        keys = {row["config_key"] for row in rows}
        assert "owner" in keys
        assert "timezone" in keys

    def test_config_upsert(self, citadel: CitadelOne, project: Path) -> None:
        """Running backup_config twice should update, not duplicate."""
        citadel.backup_config()

        # Change config
        with open(project / "config" / "guardian_config.yaml", "w") as f:
            f.write("owner: Updated Owner\ntimezone: UTC\n")

        citadel.backup_config()
        rows = citadel._conn.execute("SELECT * FROM system_config").fetchall()
        # Should have 2 keys now (owner, timezone) since data_dir was removed
        assert len(rows) == 3  # old data_dir stays, owner+timezone updated
        owner_row = citadel._conn.execute(
            "SELECT config_value FROM system_config WHERE config_key = 'owner'"
        ).fetchone()
        assert json.loads(owner_row["config_value"]) == "Updated Owner"


class TestBackupOperationLogs:
    def test_operation_logs_ingested(self, citadel: CitadelOne) -> None:
        count = citadel.backup_operation_logs()
        assert count == 2

        rows = citadel._conn.execute("SELECT * FROM operation_logs ORDER BY entry_id").fetchall()
        assert len(rows) == 2
        assert rows[0]["summary"] == "Test entry one"
        assert json.loads(rows[0]["tags"]) == ["test"]

    def test_operation_logs_idempotent(self, citadel: CitadelOne) -> None:
        citadel.backup_operation_logs()
        citadel.backup_operation_logs()
        assert citadel._conn.execute("SELECT COUNT(*) as cnt FROM operation_logs").fetchone()["cnt"] == 2


class TestBackupErrors:
    def test_errors_ingested(self, citadel: CitadelOne) -> None:
        count = citadel.backup_errors()
        assert count == 1

        rows = citadel._conn.execute("SELECT * FROM error_records").fetchall()
        assert len(rows) == 1
        assert rows[0]["error_id"] == "err_0001"
        assert rows[0]["resolved"] == 1

    def test_errors_upsert(self, citadel: CitadelOne, project: Path) -> None:
        citadel.backup_errors()

        # Update recurrence count
        with open(project / "guardian_errors.json") as f:
            data = json.load(f)
        data["errors"][0]["recurrence_count"] = 5
        with open(project / "guardian_errors.json", "w") as f:
            json.dump(data, f)

        citadel.backup_errors()
        row = citadel._conn.execute(
            "SELECT recurrence_count FROM error_records WHERE error_id = 'err_0001'"
        ).fetchone()
        assert row["recurrence_count"] == 5
        # Should still only have 1 row
        assert citadel._conn.execute("SELECT COUNT(*) as cnt FROM error_records").fetchone()["cnt"] == 1


class TestBackupSkills:
    def test_skills_ingested(self, citadel: CitadelOne) -> None:
        count = citadel.backup_skills()
        assert count == 2

        rows = citadel._conn.execute("SELECT * FROM skills ORDER BY skill_id").fetchall()
        assert len(rows) == 2
        assert rows[0]["name"] == "Python Variables"
        assert rows[1]["level"] == 4

    def test_skills_upsert(self, citadel: CitadelOne, project: Path) -> None:
        citadel.backup_skills()

        # Update skill level
        with open(project / "guardian_skills.json") as f:
            data = json.load(f)
        data["skills"][0]["level"] = 5
        data["skills"][0]["level_label"] = "EXPERT"
        with open(project / "guardian_skills.json", "w") as f:
            json.dump(data, f)

        citadel.backup_skills()
        row = citadel._conn.execute(
            "SELECT level, level_label FROM skills WHERE skill_id = 'skill_0001'"
        ).fetchone()
        assert row["level"] == 5
        assert row["level_label"] == "EXPERT"
        assert citadel._conn.execute("SELECT COUNT(*) as cnt FROM skills").fetchone()["cnt"] == 2


class TestBackupVaultMetadata:
    def test_no_vault_returns_zero(self, citadel: CitadelOne) -> None:
        count = citadel.backup_vault_metadata(vault=None)
        assert count == 0

    def test_vault_metadata_ingested(self, citadel: CitadelOne) -> None:
        """Test with a mock vault object."""
        class FakeVault:
            def list_keys(self):
                return ["API_KEY", "DB_PASSWORD"]

            def get_meta(self, key_name):
                from types import SimpleNamespace
                metas = {
                    "API_KEY": SimpleNamespace(
                        key_name="API_KEY", service="github", scope="read",
                        created_at="2026-01-01T00:00:00Z", rotated_at="2026-03-01T00:00:00Z",
                        expires_at="2026-12-31T00:00:00Z", rotation_days=90,
                    ),
                    "DB_PASSWORD": SimpleNamespace(
                        key_name="DB_PASSWORD", service="postgres", scope="admin",
                        created_at="2026-02-01T00:00:00Z", rotated_at="2026-03-15T00:00:00Z",
                        expires_at="", rotation_days=30,
                    ),
                }
                return metas.get(key_name)

        count = citadel.backup_vault_metadata(vault=FakeVault())
        assert count == 2

        rows = citadel._conn.execute("SELECT * FROM vault_metadata ORDER BY key_name").fetchall()
        assert len(rows) == 2
        assert rows[0]["key_name"] == "API_KEY"
        assert rows[0]["service"] == "github"
        assert rows[1]["key_name"] == "DB_PASSWORD"

    def test_vault_metadata_idempotent(self, citadel: CitadelOne) -> None:
        class FakeVault:
            def list_keys(self):
                return ["KEY1"]

            def get_meta(self, key_name):
                from types import SimpleNamespace
                return SimpleNamespace(
                    key_name="KEY1", service="svc", scope="read",
                    created_at="2026-01-01T00:00:00Z", rotated_at="2026-03-01T00:00:00Z",
                    expires_at="", rotation_days=90,
                )

        vault = FakeVault()
        citadel.backup_vault_metadata(vault=vault)
        citadel.backup_vault_metadata(vault=vault)
        assert citadel._conn.execute("SELECT COUNT(*) as cnt FROM vault_metadata").fetchone()["cnt"] == 1


# ------------------------------------------------------------------
# Restore methods
# ------------------------------------------------------------------

class TestRestore:
    def test_restore_audit_log(self, citadel: CitadelOne) -> None:
        citadel.backup_audit_log()
        entries = citadel.restore_audit_log()
        assert len(entries) == 2
        assert entries[0]["agent"] == "chronos"
        assert entries[1]["requires_review"] is True

    def test_restore_financial_data(self, citadel: CitadelOne) -> None:
        citadel.backup_financial_data()
        data = citadel.restore_financial_data()
        assert len(data["accounts"]) == 2
        assert len(data["transactions"]) == 2
        assert len(data["bills"]) == 1
        assert len(data["budgets"]) == 1
        assert len(data["net_worth_history"]) == 2
        # Check JSON fields are parsed
        assert isinstance(data["transactions"][0]["metadata"], dict)
        assert isinstance(data["net_worth_history"][0]["by_type"], dict)

    def test_restore_operation_logs(self, citadel: CitadelOne) -> None:
        citadel.backup_operation_logs()
        entries = citadel.restore_operation_logs()
        assert len(entries) == 2
        assert entries[0]["entry_id"] == 1
        assert isinstance(entries[0]["tags"], list)

    def test_restore_errors(self, citadel: CitadelOne) -> None:
        citadel.backup_errors()
        errors = citadel.restore_errors()
        assert len(errors) == 1
        assert errors[0]["error_id"] == "err_0001"
        assert errors[0]["resolved"] is True

    def test_restore_skills(self, citadel: CitadelOne) -> None:
        citadel.backup_skills()
        skills = citadel.restore_skills()
        assert len(skills) == 2
        assert skills[0]["skill_id"] == "skill_0001"
        assert isinstance(skills[0]["evidence"], list)

    def test_restore_config(self, citadel: CitadelOne) -> None:
        citadel.backup_config()
        config = citadel.restore_config()
        assert config["owner"] == "Test Owner"
        assert config["timezone"] == "America/Chicago"


# ------------------------------------------------------------------
# Full backup
# ------------------------------------------------------------------

class TestFullBackup:
    def test_full_backup_runs_all(self, citadel: CitadelOne) -> None:
        results = citadel.full_backup()

        assert results["audit_log"] == 2
        assert results["financial"] > 0
        assert results["evaluations"] == 1
        assert results["config"] == 3
        assert results["operation_logs"] == 2
        assert results["errors"] == 1
        assert results["skills"] == 2
        assert results["vault_metadata"] == 0  # No vault provided

    def test_full_backup_logs_to_manifest(self, citadel: CitadelOne) -> None:
        citadel.full_backup()
        full_entries = citadel._conn.execute(
            "SELECT * FROM backup_manifest WHERE backup_type = 'full'"
        ).fetchall()
        assert len(full_entries) == 1
        assert full_entries[0]["status"] == "success"

    def test_full_backup_idempotent(self, citadel: CitadelOne) -> None:
        """Running full_backup twice should not duplicate data rows."""
        citadel.full_backup()
        citadel.full_backup()
        assert citadel._conn.execute("SELECT COUNT(*) as cnt FROM audit_log").fetchone()["cnt"] == 2
        assert citadel._conn.execute("SELECT COUNT(*) as cnt FROM accounts").fetchone()["cnt"] == 2
        assert citadel._conn.execute("SELECT COUNT(*) as cnt FROM operation_logs").fetchone()["cnt"] == 2
        assert citadel._conn.execute("SELECT COUNT(*) as cnt FROM error_records").fetchone()["cnt"] == 1
        assert citadel._conn.execute("SELECT COUNT(*) as cnt FROM skills").fetchone()["cnt"] == 2


# ------------------------------------------------------------------
# Backup manifest & status
# ------------------------------------------------------------------

class TestBackupManifest:
    def test_manifest_tracks_all_operations(self, citadel: CitadelOne) -> None:
        citadel.full_backup()
        manifest = citadel._conn.execute("SELECT * FROM backup_manifest").fetchall()
        # 8 individual + 1 full = 9
        assert len(manifest) == 9

    def test_get_backup_status(self, citadel: CitadelOne) -> None:
        citadel.full_backup()
        status = citadel.get_backup_status()
        assert "table_counts" in status
        assert status["table_counts"]["audit_log"] == 2
        assert status["table_counts"]["accounts"] == 2
        assert status["last_full_backup"] is not None
        assert status["total_backup_operations"] == 9
        assert "db_path" in status


# ------------------------------------------------------------------
# Integrity verification
# ------------------------------------------------------------------

class TestIntegrity:
    def test_verify_after_full_backup(self, citadel: CitadelOne) -> None:
        citadel.full_backup()
        result = citadel.verify_integrity()
        assert result["is_consistent"] is True
        assert result["checks"]["audit_log"]["match"] is True
        assert result["checks"]["accounts"]["match"] is True
        assert result["checks"]["operation_logs"]["match"] is True

    def test_verify_detects_mismatch(self, citadel: CitadelOne, project: Path) -> None:
        citadel.full_backup()

        # Add a new audit entry to source without re-backing-up
        with open(project / "logs" / "audit.jsonl", "a") as f:
            f.write(json.dumps({
                "timestamp": "2026-04-01T00:00:00Z", "agent": "new",
                "action": "test", "severity": "info", "details": {},
                "requires_review": False,
            }) + "\n")

        result = citadel.verify_integrity()
        assert result["checks"]["audit_log"]["match"] is False
        assert result["is_consistent"] is False


# ------------------------------------------------------------------
# Missing files
# ------------------------------------------------------------------

class TestMissingFiles:
    def test_backup_with_no_files(self, tmp_path: Path) -> None:
        """Backup should succeed gracefully when source files are missing."""
        db_path = tmp_path / "data" / "citadel_one.db"
        c = CitadelOne(db_path=db_path, project_root=tmp_path)
        try:
            results = c.full_backup()
            assert results["audit_log"] == 0
            assert results["financial"] == 0
            assert results["operation_logs"] == 0
            assert results["errors"] == 0
            assert results["skills"] == 0
        finally:
            c.close()


# ------------------------------------------------------------------
# Context manager
# ------------------------------------------------------------------

class TestContextManager:
    def test_context_manager(self, project: Path) -> None:
        db_path = project / "data" / "citadel_one.db"
        with CitadelOne(db_path=db_path, project_root=project) as c:
            c.full_backup()
            status = c.get_backup_status()
            assert status["table_counts"]["audit_log"] == 2
