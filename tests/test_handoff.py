"""Tests for the dynamic handoff tracker."""

import json
from pathlib import Path

import pytest

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.handoff import HandoffEntry, HandoffTracker, _slug


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_audit(tmp_path):
    return AuditLog(log_dir=tmp_path / "logs")


@pytest.fixture
def fake_vault():
    """Minimal vault-like object with store/retrieve."""

    class FakeVault:
        def __init__(self):
            self._data = {}

        def store(self, key_name, value, **kwargs):
            self._data[key_name] = value

        def retrieve(self, key_name):
            return self._data.get(key_name)

    return FakeVault()


@pytest.fixture
def tracker(tmp_path, tmp_audit, fake_vault):
    return HandoffTracker(
        repo_root=Path.cwd(),
        output_dir=tmp_path / "handoffs",
        audit=tmp_audit,
        vault=fake_vault,
    )


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestSlug:
    def test_basic(self):
        assert _slug("feat: add new feature") == "feat-add-new-feature"

    def test_special_chars(self):
        assert _slug("fix(web): bug #123!") == "fix-web-bug-123"

    def test_max_len(self):
        result = _slug("a very long commit message that should be truncated", max_len=20)
        assert len(result) <= 20

    def test_empty(self):
        assert _slug("") == ""


class TestHandoffEntry:
    def test_to_dict(self):
        entry = HandoffEntry(
            session_id="20260401_120000",
            timestamp="2026-04-01 12:00 UTC",
            branch="main",
            commits=[{"hash": "abc123", "message": "test", "date": "now"}],
            files_changed=["foo.py"],
            summary="test commit",
            test_result="5 passed",
            audit_snapshot=[],
        )
        d = entry.to_dict()
        assert d["session_id"] == "20260401_120000"
        assert d["branch"] == "main"
        assert len(d["commits"]) == 1

    def test_to_markdown(self):
        entry = HandoffEntry(
            session_id="20260401_120000",
            timestamp="2026-04-01 12:00 UTC",
            branch="feat/test",
            commits=[{"hash": "abc12345def", "message": "feat: cool thing", "date": "now"}],
            files_changed=["src/main.py", "tests/test_main.py"],
            summary="feat: cool thing",
            test_result="42 passed",
            audit_snapshot=[
                {"severity": "info", "agent": "cfo", "action": "daily_review"},
            ],
        )
        md = entry.to_markdown()
        assert "# Handoff: feat: cool thing" in md
        assert "`feat/test`" in md
        assert "42 passed" in md
        assert "`abc12345`" in md
        assert "`src/main.py`" in md
        assert "[INFO] cfo: daily_review" in md


class TestHandoffTracker:
    def test_generate_creates_markdown(self, tracker, tmp_path):
        entry = tracker.generate(run_tests=False, n_commits=3)
        md_files = list((tmp_path / "handoffs").glob("*.md"))
        assert len(md_files) == 1
        content = md_files[0].read_text()
        assert "# Handoff:" in content
        assert entry.branch in content

    def test_generate_backs_up_to_vault(self, tracker, fake_vault):
        entry = tracker.generate(run_tests=False, n_commits=3)
        key = f"HANDOFF_{entry.session_id}"
        assert fake_vault.retrieve(key) is not None
        restored = json.loads(fake_vault.retrieve(key))
        assert restored["session_id"] == entry.session_id

    def test_vault_index_updated(self, tracker, fake_vault):
        tracker.generate(run_tests=False, n_commits=2)
        tracker.generate(run_tests=False, n_commits=2)
        index = json.loads(fake_vault.retrieve("HANDOFF_INDEX"))
        assert len(index) == 2

    def test_list_handoffs(self, tracker, fake_vault):
        tracker.generate(run_tests=False, n_commits=2)
        entries = tracker.list_handoffs()
        assert len(entries) == 1
        assert "session_id" in entries[0]

    def test_restore_handoff(self, tracker, fake_vault):
        entry = tracker.generate(run_tests=False, n_commits=2)
        restored = tracker.restore_handoff(entry.session_id)
        assert restored is not None
        assert restored.session_id == entry.session_id
        assert restored.branch == entry.branch

    def test_restore_missing_returns_none(self, tracker):
        assert tracker.restore_handoff("nonexistent_99999") is None

    def test_audit_recorded(self, tracker, tmp_audit):
        tracker.generate(run_tests=False, n_commits=2)
        entries = tmp_audit.query(agent="handoff_tracker", limit=5)
        assert len(entries) >= 1
        assert "handoff_generated" in entries[0].action

    def test_no_vault_still_works(self, tmp_path, tmp_audit):
        tracker = HandoffTracker(
            repo_root=Path.cwd(),
            output_dir=tmp_path / "handoffs",
            audit=tmp_audit,
            vault=None,
        )
        entry = tracker.generate(run_tests=False, n_commits=2)
        assert entry.session_id
        md_files = list((tmp_path / "handoffs").glob("*.md"))
        assert len(md_files) == 1
