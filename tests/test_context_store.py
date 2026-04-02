"""Tests for the OpenViking-inspired agent context store."""

import json
from pathlib import Path

import pytest

from guardian_one.core.context_store import ContextStore


@pytest.fixture
def store(tmp_path):
    """Create a context store using a temporary directory."""
    return ContextStore(data_dir=tmp_path)


class TestPutAndGet:
    """Tests for basic key-value operations."""

    def test_put_and_get(self, store):
        store.put("cfo", "state", "last_sync", "2024-01-15")
        assert store.get("cfo", "state", "last_sync") == "2024-01-15"

    def test_get_missing_returns_default(self, store):
        assert store.get("cfo", "state", "nonexistent") is None
        assert store.get("cfo", "state", "nonexistent", "fallback") == "fallback"

    def test_put_overwrites(self, store):
        store.put("cfo", "state", "count", 1)
        store.put("cfo", "state", "count", 2)
        assert store.get("cfo", "state", "count") == 2

    def test_put_complex_value(self, store):
        data = {"accounts": ["checking", "savings"], "total": 5000.50}
        store.put("cfo", "state", "balances", data)
        result = store.get("cfo", "state", "balances")
        assert result == data

    def test_separate_agents(self, store):
        store.put("cfo", "state", "key", "cfo_value")
        store.put("chronos", "state", "key", "chronos_value")
        assert store.get("cfo", "state", "key") == "cfo_value"
        assert store.get("chronos", "state", "key") == "chronos_value"

    def test_separate_categories(self, store):
        store.put("cfo", "state", "key", "state_val")
        store.put("cfo", "skills", "key", "skills_val")
        assert store.get("cfo", "state", "key") == "state_val"
        assert store.get("cfo", "skills", "key") == "skills_val"


class TestDelete:
    """Tests for key deletion."""

    def test_delete_existing(self, store):
        store.put("cfo", "state", "temp", "data")
        assert store.delete("cfo", "state", "temp") is True
        assert store.get("cfo", "state", "temp") is None

    def test_delete_nonexistent(self, store):
        assert store.delete("cfo", "state", "nope") is False


class TestListKeys:
    """Tests for listing keys."""

    def test_list_empty(self, store):
        assert store.list_keys("cfo", "state") == []

    def test_list_with_data(self, store):
        store.put("cfo", "state", "a", 1)
        store.put("cfo", "state", "b", 2)
        keys = store.list_keys("cfo", "state")
        assert sorted(keys) == ["a", "b"]


class TestMemoryLog:
    """Tests for rolling memory log (append/get_log)."""

    def test_append_and_retrieve(self, store):
        store.append("cfo", "memory", {"role": "system", "content": "Hello"})
        store.append("cfo", "memory", {"role": "user", "content": "Check budget"})
        log = store.get_log("cfo", "memory")
        assert len(log) == 2
        assert log[0]["content"] == "Hello"
        assert log[1]["content"] == "Check budget"
        assert "ts" in log[0]

    def test_log_rolling_window(self, store):
        store.MAX_MEMORY_ENTRIES = 5
        for i in range(10):
            store.append("cfo", "memory", {"msg": f"entry_{i}"})
        log = store.get_log("cfo", "memory", last_n=100)
        assert len(log) == 5
        assert log[0]["msg"] == "entry_5"  # oldest kept

    def test_get_log_last_n(self, store):
        for i in range(10):
            store.append("cfo", "memory", {"i": i})
        log = store.get_log("cfo", "memory", last_n=3)
        assert len(log) == 3
        assert log[0]["i"] == 7

    def test_empty_log(self, store):
        assert store.get_log("cfo", "memory") == []


class TestClear:
    """Tests for clearing context."""

    def test_clear_category(self, store):
        store.put("cfo", "state", "key", "val")
        store.clear("cfo", "state")
        assert store.get("cfo", "state", "key") is None

    def test_clear_all_categories(self, store):
        store.put("cfo", "state", "a", 1)
        store.put("cfo", "skills", "b", 2)
        store.put("cfo", "memory", "c", 3)
        store.clear("cfo")
        assert store.get("cfo", "state", "a") is None
        assert store.get("cfo", "skills", "b") is None
        assert store.get("cfo", "memory", "c") is None


class TestGlobalContext:
    """Tests for cross-agent shared context."""

    def test_set_and_get_global(self, store):
        store.set_global("system_priority", "security_audit")
        assert store.get_global("system_priority") == "security_audit"

    def test_global_isolated_from_agents(self, store):
        store.set_global("key", "global_val")
        store.put("cfo", "state", "key", "cfo_val")
        assert store.get_global("key") == "global_val"
        assert store.get("cfo", "state", "key") == "cfo_val"


class TestPersistence:
    """Tests for file-backed persistence across store instances."""

    def test_survives_restart(self, tmp_path):
        store1 = ContextStore(data_dir=tmp_path)
        store1.put("cfo", "state", "persistent", "yes")

        store2 = ContextStore(data_dir=tmp_path)
        assert store2.get("cfo", "state", "persistent") == "yes"

    def test_file_structure(self, tmp_path):
        store = ContextStore(data_dir=tmp_path)
        store.put("cfo", "state", "key", "val")
        ctx_dir = tmp_path / "context" / "cfo"
        assert ctx_dir.exists()
        assert (ctx_dir / "state.json").exists()
        data = json.loads((ctx_dir / "state.json").read_text())
        assert "key" in data


class TestSnapshot:
    """Tests for full agent snapshots."""

    def test_snapshot(self, store):
        store.put("cfo", "state", "a", 1)
        store.put("cfo", "skills", "b", 2)
        snap = store.snapshot("cfo")
        assert "state" in snap
        assert "skills" in snap
        assert "memory" in snap

    def test_agents_with_context(self, store):
        store.put("cfo", "state", "x", 1)
        store.put("chronos", "state", "y", 2)
        agents = store.agents_with_context()
        assert "cfo" in agents
        assert "chronos" in agents


class TestValidation:
    """Tests for input validation."""

    def test_invalid_category_raises(self, store):
        with pytest.raises(ValueError, match="Invalid category"):
            store.put("cfo", "invalid_cat", "key", "val")

    def test_invalid_category_get(self, store):
        with pytest.raises(ValueError, match="Invalid category"):
            store.get("cfo", "bad", "key")
