"""AI triage engine — uses Claude to classify, prioritize, and route tasks."""

import json
import os

import anthropic

from guardian.store import get_all_tasks, update_task

SYSTEM_PROMPT = """\
You are Guardian, an AI project manager. Your job is to triage incoming tasks \
for a software product team that uses AI agents for execution, deployment, \
improvement, and dynamic evolution.

When triaging a task, you must return a JSON object with these fields:
- "priority": one of "critical", "high", "medium", "low"
- "category": one of "bug", "feature", "improvement", "infra", "research", "ops"
- "labels": a list of relevant short tags (e.g. ["api", "auth", "frontend"])
- "status": one of "backlog", "ready", "in_progress", "blocked", "done"
- "triage_notes": a 1-2 sentence assessment of urgency, dependencies, and \
suggested next step

Consider:
1. Impact on the product (user-facing vs internal)
2. Blocking potential (does this block other work?)
3. Effort estimate (quick win vs multi-day)
4. Risk (security, data loss, downtime)
5. Source credibility (agent-generated vs human-requested)

Respond ONLY with the JSON object. No markdown fences, no explanation."""

BOARD_REVIEW_PROMPT = """\
You are Guardian, an AI project manager. Review the current task board and \
provide a prioritized action plan.

Current board state:
{board_json}

Analyze the board and return a JSON object with:
- "recommended_order": list of task IDs in the order they should be worked on
- "blocked_tasks": list of task IDs that appear blocked and why
- "quick_wins": list of task IDs that can be done fast with high impact
- "risks": any risks you see in the current backlog
- "summary": a 2-3 sentence executive summary of board health

Respond ONLY with the JSON object. No markdown fences, no explanation."""


def _get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "Set ANTHROPIC_API_KEY to enable AI triage. "
            "Without it, Guardian runs in manual mode only."
        )
    return anthropic.Anthropic(api_key=api_key)


def triage_task(task: dict) -> dict:
    """Use Claude to triage a single task. Returns the triage result."""
    client = _get_client()

    user_message = (
        f"Triage this task:\n"
        f"Title: {task['title']}\n"
        f"Description: {task['description']}\n"
        f"Source: {task['source']}\n"
        f"Current status: {task['status']}\n"
        f"Current priority: {task['priority']}"
    )

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    result_text = next(
        (b.text for b in response.content if b.type == "text"), "{}"
    )
    triage_result = json.loads(result_text)

    updated = update_task(
        task["id"],
        priority=triage_result.get("priority", task["priority"]),
        category=triage_result.get("category", task["category"]),
        labels=triage_result.get("labels", task["labels"]),
        status=triage_result.get("status", task["status"]),
        triage_notes=triage_result.get("triage_notes", ""),
    )

    return {"task": updated, "triage": triage_result}


def triage_backlog() -> list[dict]:
    """Triage all tasks currently in backlog with unset priority."""
    tasks = get_all_tasks()
    untriaged = [
        t for t in tasks if t["priority"] == "unset" or t["status"] == "backlog"
    ]
    results = []
    for t in untriaged:
        try:
            result = triage_task(t)
            results.append(result)
        except Exception as e:
            results.append({"task": t, "error": str(e)})
    return results


def review_board() -> dict:
    """Use Claude to review the entire board and recommend priorities."""
    client = _get_client()
    tasks = get_all_tasks()

    if not tasks:
        return {"summary": "Board is empty. Add tasks to get started."}

    board_json = json.dumps(tasks, indent=2)
    prompt = BOARD_REVIEW_PROMPT.format(board_json=board_json)

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        thinking={"type": "adaptive"},
        system="You are Guardian, an AI project manager.",
        messages=[{"role": "user", "content": prompt}],
    )

    result_text = next(
        (b.text for b in response.content if b.type == "text"), "{}"
    )
    return json.loads(result_text)
