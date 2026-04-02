"""Agent Context Store — OpenViking-inspired persistent memory for agents.

Provides hierarchical, persistent context that agents can read/write across
sessions. Each agent gets its own namespace, with a shared global namespace
for cross-agent coordination.

Architecture (inspired by OpenViking's file-system paradigm):
    context/
    ├── _global/           # Cross-agent shared context
    │   ├── priorities.json
    │   └── conflicts.json
    ├── chronos/           # Per-agent namespaces
    │   ├── memory.json    # Conversation/reasoning memory
    │   ├── state.json     # Persistent state across runs
    │   └── skills.json    # Learned patterns/preferences
    ├── cfo/
    │   ├── memory.json
    │   ├── state.json
    │   └── skills.json
    └── ...

Usage:
    store = ContextStore(data_dir="data")
    store.put("cfo", "state", "last_sync", {"plaid": "2024-01-15T10:00:00Z"})
    val = store.get("cfo", "state", "last_sync")
    store.append("cfo", "memory", {"role": "assistant", "content": "Budget on track"})
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ContextStore:
    """Thread-safe, file-backed context store for agent memory and state."""

    GLOBAL_NS = "_global"
    CATEGORIES = ("memory", "state", "skills")
    MAX_MEMORY_ENTRIES = 200  # per-agent rolling memory window

    def __init__(self, data_dir: str | Path = "data") -> None:
        self._root = Path(data_dir) / "context"
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._cache: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put(self, agent: str, category: str, key: str, value: Any) -> None:
        """Store a key-value pair in an agent's context category.

        Args:
            agent: Agent name (or ContextStore.GLOBAL_NS for shared).
            category: One of 'memory', 'state', 'skills'.
            key: The key to store under.
            value: Any JSON-serializable value.
        """
        self._validate_category(category)
        with self._lock:
            data = self._load(agent, category)
            data[key] = {
                "value": value,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save(agent, category, data)

    def get(self, agent: str, category: str, key: str, default: Any = None) -> Any:
        """Retrieve a value from an agent's context.

        Returns the raw value (unwrapped from metadata), or default.
        """
        self._validate_category(category)
        with self._lock:
            data = self._load(agent, category)
        entry = data.get(key)
        if entry is None:
            return default
        return entry.get("value", default)

    def delete(self, agent: str, category: str, key: str) -> bool:
        """Remove a key from context. Returns True if it existed."""
        self._validate_category(category)
        with self._lock:
            data = self._load(agent, category)
            if key in data:
                del data[key]
                self._save(agent, category, data)
                return True
        return False

    def list_keys(self, agent: str, category: str) -> list[str]:
        """List all keys in an agent's context category."""
        self._validate_category(category)
        with self._lock:
            data = self._load(agent, category)
        return list(data.keys())

    def append(self, agent: str, category: str, entry: dict[str, Any]) -> None:
        """Append to a rolling memory log (used for conversation history).

        Entries are stored as a list under the '_log' key, capped at
        MAX_MEMORY_ENTRIES with oldest entries evicted.
        """
        self._validate_category(category)
        with self._lock:
            data = self._load(agent, category)
            log = data.get("_log", {"value": [], "updated_at": ""})
            entries = log.get("value", [])
            entries.append({
                **entry,
                "ts": datetime.now(timezone.utc).isoformat(),
            })
            # Evict oldest if over limit
            if len(entries) > self.MAX_MEMORY_ENTRIES:
                entries = entries[-self.MAX_MEMORY_ENTRIES:]
            data["_log"] = {
                "value": entries,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._save(agent, category, data)

    def get_log(self, agent: str, category: str, last_n: int = 50) -> list[dict]:
        """Retrieve recent entries from the rolling memory log."""
        self._validate_category(category)
        with self._lock:
            data = self._load(agent, category)
        log = data.get("_log", {}).get("value", [])
        return log[-last_n:]

    def get_all(self, agent: str, category: str) -> dict[str, Any]:
        """Get entire context category (for snapshots/debugging)."""
        self._validate_category(category)
        with self._lock:
            return self._load(agent, category)

    def clear(self, agent: str, category: str | None = None) -> None:
        """Clear an agent's context. If category is None, clear all."""
        with self._lock:
            if category:
                self._validate_category(category)
                self._save(agent, category, {})
            else:
                for cat in self.CATEGORIES:
                    self._save(agent, cat, {})

    def agents_with_context(self) -> list[str]:
        """List all agent namespaces that have stored context."""
        if not self._root.exists():
            return []
        return sorted([
            d.name for d in self._root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ])

    def snapshot(self, agent: str) -> dict[str, dict]:
        """Full snapshot of an agent's context across all categories."""
        result = {}
        for cat in self.CATEGORIES:
            with self._lock:
                result[cat] = self._load(agent, cat)
        return result

    # ------------------------------------------------------------------
    # Cross-agent shared context
    # ------------------------------------------------------------------

    def set_global(self, key: str, value: Any) -> None:
        """Store a value in the global shared namespace."""
        self.put(self.GLOBAL_NS, "state", key, value)

    def get_global(self, key: str, default: Any = None) -> Any:
        """Retrieve from the global shared namespace."""
        return self.get(self.GLOBAL_NS, "state", key, default)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _validate_category(self, category: str) -> None:
        if category not in self.CATEGORIES:
            raise ValueError(
                f"Invalid category '{category}'. Must be one of: {self.CATEGORIES}"
            )

    def _file_path(self, agent: str, category: str) -> Path:
        agent_dir = self._root / agent
        agent_dir.mkdir(parents=True, exist_ok=True)
        return agent_dir / f"{category}.json"

    def _cache_key(self, agent: str, category: str) -> str:
        return f"{agent}/{category}"

    def _load(self, agent: str, category: str) -> dict[str, Any]:
        ck = self._cache_key(agent, category)
        if ck in self._cache:
            return self._cache[ck]
        fp = self._file_path(agent, category)
        if fp.exists():
            try:
                data = json.loads(fp.read_text())
                self._cache[ck] = data
                return data
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save(self, agent: str, category: str, data: dict[str, Any]) -> None:
        ck = self._cache_key(agent, category)
        self._cache[ck] = data
        fp = self._file_path(agent, category)
        # Atomic write: write to temp, then rename
        tmp = fp.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str))
        tmp.rename(fp)
