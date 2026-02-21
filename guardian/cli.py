"""Guardian CLI — command-line interface for humans and agents."""

import argparse
import json
import sys

from guardian.store import (
    add_task,
    delete_task,
    get_all_tasks,
    get_board_summary,
    get_task,
    get_tasks,
    update_task,
)


def _print_task(task: dict, verbose: bool = False) -> None:
    priority_icons = {
        "critical": "[!!!]",
        "high": "[!! ]",
        "medium": "[ ! ]",
        "low": "[   ]",
        "unset": "[ ? ]",
    }
    icon = priority_icons.get(task["priority"], "[ ? ]")
    status_display = task["status"].upper().replace("_", " ")
    print(f"  {icon} {task['id']}  {status_display:<12} {task['title']}")
    if verbose:
        if task["description"]:
            print(f"         desc: {task['description']}")
        print(f"         category: {task['category']}  source: {task['source']}")
        if task["labels"]:
            print(f"         labels: {', '.join(task['labels'])}")
        if task["triage_notes"]:
            print(f"         notes: {task['triage_notes']}")
        print()


def cmd_add(args: argparse.Namespace) -> None:
    task = add_task(
        title=args.title,
        description=args.description or "",
        source=args.source or "human",
    )
    print(f"Added task {task['id']}: {task['title']}")


def cmd_list(args: argparse.Namespace) -> None:
    tasks = get_tasks(
        status=args.status,
        priority=args.priority,
        category=args.category,
    )
    if not tasks:
        print("No tasks found.")
        return
    print(f"\n  {'PRIO':<7} {'ID':<10} {'STATUS':<12} TITLE")
    print(f"  {'----':<7} {'--':<10} {'------':<12} -----")
    for t in tasks:
        _print_task(t, verbose=args.verbose)
    print(f"\n  {len(tasks)} task(s)\n")


def cmd_show(args: argparse.Namespace) -> None:
    task = get_task(args.id)
    if not task:
        print(f"Task {args.id} not found.")
        sys.exit(1)
    print(json.dumps(task, indent=2))


def cmd_update(args: argparse.Namespace) -> None:
    fields = {}
    if args.status:
        fields["status"] = args.status
    if args.priority:
        fields["priority"] = args.priority
    if args.category:
        fields["category"] = args.category
    if not fields:
        print("No fields to update. Use --status, --priority, or --category.")
        return
    result = update_task(args.id, **fields)
    if result:
        print(f"Updated task {args.id}")
    else:
        print(f"Task {args.id} not found.")
        sys.exit(1)


def cmd_delete(args: argparse.Namespace) -> None:
    if delete_task(args.id):
        print(f"Deleted task {args.id}")
    else:
        print(f"Task {args.id} not found.")
        sys.exit(1)


def cmd_board(args: argparse.Namespace) -> None:
    summary = get_board_summary()
    print("\n  GUARDIAN BOARD")
    print(f"  Total tasks: {summary['total']}\n")

    if summary["by_status"]:
        print("  By Status:")
        for status, count in sorted(summary["by_status"].items()):
            print(f"    {status:<14} {count}")

    if summary["by_priority"]:
        print("\n  By Priority:")
        order = ["critical", "high", "medium", "low", "unset"]
        for p in order:
            if p in summary["by_priority"]:
                print(f"    {p:<14} {summary['by_priority'][p]}")

    if summary["by_category"]:
        print("\n  By Category:")
        for cat, count in sorted(summary["by_category"].items()):
            print(f"    {cat:<14} {count}")
    print()


def cmd_triage(args: argparse.Namespace) -> None:
    try:
        from guardian.triage import triage_backlog, triage_task
    except Exception as e:
        print(f"Triage unavailable: {e}")
        sys.exit(1)

    if args.id:
        task = get_task(args.id)
        if not task:
            print(f"Task {args.id} not found.")
            sys.exit(1)
        print(f"Triaging task {args.id}...")
        result = triage_task(task)
        print(json.dumps(result["triage"], indent=2))
    else:
        print("Triaging all backlog tasks...")
        results = triage_backlog()
        for r in results:
            if "error" in r:
                print(f"  ERROR on {r['task']['id']}: {r['error']}")
            else:
                t = r["task"]
                print(f"  {t['id']} -> {t['priority']} / {t['category']} / {t['status']}")
        print(f"\n  Triaged {len(results)} task(s)")


def cmd_review(args: argparse.Namespace) -> None:
    try:
        from guardian.triage import review_board
    except Exception as e:
        print(f"Board review unavailable: {e}")
        sys.exit(1)

    print("Reviewing board with AI...")
    result = review_board()
    print(json.dumps(result, indent=2))


def cmd_intake(args: argparse.Namespace) -> None:
    """Accept a JSON task payload from stdin (for agent integration)."""
    raw = sys.stdin.read().strip()
    if not raw:
        print("No input received. Pipe JSON to stdin.")
        sys.exit(1)
    payload = json.loads(raw)

    if isinstance(payload, list):
        tasks = payload
    else:
        tasks = [payload]

    added = []
    for p in tasks:
        task = add_task(
            title=p.get("title", "Untitled"),
            description=p.get("description", ""),
            source=p.get("source", "agent"),
            priority=p.get("priority"),
            category=p.get("category"),
            labels=p.get("labels"),
        )
        added.append(task)

    if args.triage:
        try:
            from guardian.triage import triage_task

            for task in added:
                triage_task(task)
                print(f"  Triaged: {task['id']} - {task['title']}")
        except Exception as e:
            print(f"  Auto-triage failed: {e}")

    output = json.dumps([{"id": t["id"], "title": t["title"]} for t in added])
    print(output)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="guardian",
        description="Guardian — AI Project Manager",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # add
    p_add = sub.add_parser("add", help="Add a new task")
    p_add.add_argument("title", help="Task title")
    p_add.add_argument("-d", "--description", help="Task description")
    p_add.add_argument("-s", "--source", default="human", help="Task source")
    p_add.set_defaults(func=cmd_add)

    # list
    p_list = sub.add_parser("list", help="List tasks")
    p_list.add_argument("--status", help="Filter by status")
    p_list.add_argument("--priority", help="Filter by priority")
    p_list.add_argument("--category", help="Filter by category")
    p_list.add_argument("-v", "--verbose", action="store_true")
    p_list.set_defaults(func=cmd_list)

    # show
    p_show = sub.add_parser("show", help="Show task details")
    p_show.add_argument("id", help="Task ID")
    p_show.set_defaults(func=cmd_show)

    # update
    p_update = sub.add_parser("update", help="Update a task")
    p_update.add_argument("id", help="Task ID")
    p_update.add_argument("--status", choices=["backlog", "ready", "in_progress", "blocked", "done"])
    p_update.add_argument("--priority", choices=["critical", "high", "medium", "low"])
    p_update.add_argument("--category", choices=["bug", "feature", "improvement", "infra", "research", "ops"])
    p_update.set_defaults(func=cmd_update)

    # delete
    p_del = sub.add_parser("delete", help="Delete a task")
    p_del.add_argument("id", help="Task ID")
    p_del.set_defaults(func=cmd_delete)

    # board
    p_board = sub.add_parser("board", help="Show board summary")
    p_board.set_defaults(func=cmd_board)

    # triage
    p_triage = sub.add_parser("triage", help="AI-triage tasks")
    p_triage.add_argument("--id", help="Triage a specific task (default: all backlog)")
    p_triage.set_defaults(func=cmd_triage)

    # review
    p_review = sub.add_parser("review", help="AI board review and recommendations")
    p_review.set_defaults(func=cmd_review)

    # intake
    p_intake = sub.add_parser("intake", help="Accept task(s) from agents via stdin JSON")
    p_intake.add_argument("--triage", action="store_true", help="Auto-triage on intake")
    p_intake.set_defaults(func=cmd_intake)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
