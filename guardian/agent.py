"""Agent integration — programmatic API for other AI agents to submit work."""

import json
from typing import Optional

from guardian.store import add_task, get_all_tasks, get_board_summary, get_task
from guardian.triage import triage_task


def submit_task(
    title: str,
    description: str = "",
    source: str = "agent",
    auto_triage: bool = False,
) -> dict:
    """Submit a task programmatically. Returns the created task dict.

    Usage from another agent/script:
        from guardian.agent import submit_task
        result = submit_task(
            title="Fix login timeout on mobile",
            description="Users on iOS report 30s timeout on auth endpoint",
            source="monitoring-agent",
            auto_triage=True,
        )
    """
    task = add_task(title=title, description=description, source=source)

    if auto_triage:
        try:
            triage_result = triage_task(task)
            return triage_result["task"]
        except Exception:
            return task

    return task


def submit_batch(tasks: list[dict], auto_triage: bool = False) -> list[dict]:
    """Submit multiple tasks at once.

    Each dict in the list should have at least "title".
    Optional keys: "description", "source", "labels".
    """
    results = []
    for t in tasks:
        result = submit_task(
            title=t.get("title", "Untitled"),
            description=t.get("description", ""),
            source=t.get("source", "agent"),
            auto_triage=auto_triage,
        )
        results.append(result)
    return results


def get_next_task(category: Optional[str] = None) -> Optional[dict]:
    """Get the highest-priority ready task for an agent to pick up.

    Returns the task dict or None if nothing is ready.
    """
    tasks = get_all_tasks()
    ready = [t for t in tasks if t["status"] == "ready"]

    if category:
        ready = [t for t in ready if t["category"] == category]

    if not ready:
        return None

    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "unset": 4}
    ready.sort(key=lambda t: priority_order.get(t["priority"], 4))
    return ready[0]


def report_status() -> dict:
    """Return the current board state as a dict for agent consumption."""
    return {
        "summary": get_board_summary(),
        "tasks": get_all_tasks(),
    }
