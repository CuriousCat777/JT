"""Task storage engine — flat-file JSON, no external DB needed."""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent / "data"
TASKS_FILE = DATA_DIR / "tasks.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict:
    if not TASKS_FILE.exists():
        return {"tasks": [], "meta": {"created": _now(), "version": 1}}
    with open(TASKS_FILE, "r") as f:
        return json.load(f)


def _save(db: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(TASKS_FILE, "w") as f:
        json.dump(db, f, indent=2)


def add_task(
    title: str,
    description: str = "",
    source: str = "human",
    priority: Optional[str] = None,
    category: Optional[str] = None,
    labels: Optional[list[str]] = None,
) -> dict:
    """Add a new task to the backlog."""
    db = _load()
    task = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "description": description,
        "source": source,
        "status": "backlog",
        "priority": priority or "unset",
        "category": category or "uncategorized",
        "labels": labels or [],
        "created_at": _now(),
        "updated_at": _now(),
        "triage_notes": "",
    }
    db["tasks"].append(task)
    _save(db)
    return task


def get_tasks(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
) -> list[dict]:
    """Query tasks with optional filters."""
    db = _load()
    tasks = db["tasks"]
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    if priority:
        tasks = [t for t in tasks if t["priority"] == priority]
    if category:
        tasks = [t for t in tasks if t["category"] == category]
    return tasks


def get_task(task_id: str) -> Optional[dict]:
    """Get a single task by ID."""
    db = _load()
    for t in db["tasks"]:
        if t["id"] == task_id:
            return t
    return None


def update_task(task_id: str, **fields) -> Optional[dict]:
    """Update fields on an existing task."""
    db = _load()
    for t in db["tasks"]:
        if t["id"] == task_id:
            for k, v in fields.items():
                if k in t:
                    t[k] = v
            t["updated_at"] = _now()
            _save(db)
            return t
    return None


def delete_task(task_id: str) -> bool:
    """Remove a task by ID."""
    db = _load()
    before = len(db["tasks"])
    db["tasks"] = [t for t in db["tasks"] if t["id"] != task_id]
    if len(db["tasks"]) < before:
        _save(db)
        return True
    return False


def get_all_tasks() -> list[dict]:
    """Return every task regardless of status."""
    return _load()["tasks"]


def get_board_summary() -> dict:
    """Return counts grouped by status and priority."""
    tasks = get_all_tasks()
    summary = {
        "total": len(tasks),
        "by_status": {},
        "by_priority": {},
        "by_category": {},
    }
    for t in tasks:
        summary["by_status"][t["status"]] = summary["by_status"].get(t["status"], 0) + 1
        summary["by_priority"][t["priority"]] = summary["by_priority"].get(t["priority"], 0) + 1
        summary["by_category"][t["category"]] = summary["by_category"].get(t["category"], 0) + 1
    return summary
