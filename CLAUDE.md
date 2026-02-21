# CLAUDE.md — Guardian Project Instructions

## What is this project?

Guardian is an AI project manager for agent-driven workflows. It replaces Asana/Notion with a code-native system that AI agents interact with directly. The product focus is execution, deployment, improvement, and dynamic evolution.

## Project structure

```
guardian/
  __init__.py      # Package init, version
  __main__.py      # Entry point for `python -m guardian`
  store.py         # JSON-backed task storage engine (no external DB)
  triage.py        # Claude API-powered triage engine
  cli.py           # CLI for humans: add/list/update/delete/board/triage/review/intake
  agent.py         # Programmatic API for other AI agents to submit/retrieve tasks
  data/            # Runtime data (gitignored)
    tasks.json     # Task database (auto-created)
```

## How to run

```bash
# CLI usage
python -m guardian add "Task title" -d "Description" -s "source-name"
python -m guardian list [-v] [--status backlog] [--priority high]
python -m guardian board
python -m guardian triage [--id TASK_ID]
python -m guardian review
echo '{"title":"...","source":"agent"}' | python -m guardian intake [--triage]

# Programmatic (from other Python code/agents)
from guardian.agent import submit_task, submit_batch, get_next_task
```

## Key conventions

- **Python 3.10+** required (uses `match/case`, type hints with `list[str]`)
- **No external database** — all state lives in `guardian/data/tasks.json`
- **Claude API** via `anthropic` SDK for triage and board review
- **ANTHROPIC_API_KEY** env var required for AI features; CLI works without it in manual mode
- Task IDs are 8-char UUID prefixes (e.g. `15470e12`)
- Task statuses: `backlog` -> `ready` -> `in_progress` -> `done` (also `blocked`)
- Task priorities: `critical`, `high`, `medium`, `low`, `unset`
- Task categories: `bug`, `feature`, `improvement`, `infra`, `research`, `ops`, `uncategorized`

## When modifying this project

- Keep the flat-file JSON store — do not introduce a database
- Keep the CLI thin — business logic belongs in `store.py`, `triage.py`, or `agent.py`
- The `agent.py` module is the contract surface for other AI agents — changes there should be backward-compatible
- The triage system prompt lives in `triage.py` (SYSTEM_PROMPT constant) — tune it there
- Test CLI changes by running `python -m guardian` commands directly
- `guardian/data/` is gitignored — never commit `tasks.json`

## Dependencies

- `anthropic>=0.42.0` — Claude API SDK
- Standard library only otherwise (json, uuid, datetime, argparse, pathlib)

## License

Apache 2.0
