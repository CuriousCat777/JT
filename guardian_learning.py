"""
================================================================================
GUARDIAN ONE — LEARNING INTELLIGENCE MODULE (guardian_learning.py)
================================================================================

PURPOSE:
    Track what you know, what you don't, and what's blocking you.
    This module is three systems in one:

    1. SKILL GRAPH  — Maps skills to goals with dependency chains.
       "To build an AI agent, I need: Python OOP, HTTP APIs, prompt
       engineering, error handling..." — then tracks your proficiency
       in each, identifies gaps, and prioritizes what to learn next.

    2. ERROR TRACKER — Logs every mistake, misconception, and failed
       attempt with context. Detects PATTERNS: "You've made the same
       file-path error 4 times in 2 days. Here's the fix pattern."

    3. WORKFLOW MONITOR — Records command sequences, timestamps,
       and friction points. Detects: repeated commands (you're stuck),
       long pauses (you're confused), error-correction loops.

    Together: the system knows what you're trying to build, what
    skills you need, which ones you're weak in, and WHERE you
    specifically struggle — so it can tell you exactly what to
    study or practice next.

USAGE:
    python guardian_learning.py [command] [options]

    SKILL COMMANDS:
        add-skill       --name "Python OOP" --domain python --level 0
        add-goal        --name "Build AI Agent" --skills "Python OOP,HTTP APIs"
        assess          --skill "Python OOP" --level 3 --evidence "Completed Lesson 3"
        gaps            Show all knowledge gaps for active goals
        roadmap         Prioritized learning path to reach goals
        skills          List all tracked skills with levels
        goals           List all goals with completion status

    ERROR TRACKING:
        log-error       --type misconception --what "Pasted code into PowerShell"
                        --why "Didn't understand file execution vs interpreter"
                        --fix "Use: python filename.py"
        log-error       --type syntax --what "Missing colon after if"
                        --context "guardian_lesson_2.py line 45"
        errors          Show all logged errors
        patterns        Detect recurring error patterns

    WORKFLOW MONITORING:
        log-cmd         --cmd "python guardian_system.py list" --result success
        log-cmd         --cmd "cd Downloads" --result success
        log-cmd         --cmd "dir /s" --result fail --note "Wrong shell syntax"
        friction        Show detected friction points
        session         Show current session summary

    ANALYSIS:
        dashboard       Full learning intelligence report
        export          Export all data to CSV
        suggest         AI-ready prompt: what to study next

FILES CREATED:
    guardian_skills.json     — Skill graph and goal data
    guardian_errors.json     — Error and misconception log
    guardian_workflow.json   — Command and workflow history

INTEGRATES WITH:
    guardian_one_log.json    — Cross-references Guardian entries
    interactions_log.json    — Links to Claude session data
================================================================================
"""

import json
import os
import sys
import hashlib
from datetime import datetime, timezone
from collections import Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_FILE = os.path.join(SCRIPT_DIR, "guardian_skills.json")
ERRORS_FILE = os.path.join(SCRIPT_DIR, "guardian_errors.json")
WORKFLOW_FILE = os.path.join(SCRIPT_DIR, "guardian_workflow.json")


# =============================================================================
# DATA STRUCTURES
# =============================================================================

def utc_now():
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_hash(data_dict):
    raw = json.dumps(data_dict, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# Proficiency scale (0-5, maps to clinical competency model)
PROFICIENCY_LEVELS = {
    0: "UNKNOWN",       # Never encountered
    1: "EXPOSED",       # Seen it, can't do it alone
    2: "BEGINNER",      # Can do with heavy reference
    3: "COMPETENT",     # Can do with occasional reference
    4: "PROFICIENT",    # Can do reliably, can teach basics
    5: "EXPERT",        # Can teach, debug, architect with it
}

# Error categories
ERROR_TYPES = [
    "misconception",    # Believed something false
    "syntax",           # Code syntax error
    "logic",            # Code runs but wrong result
    "navigation",       # Wrong directory, wrong file, wrong path
    "environment",      # Wrong Python version, missing module, OS issue
    "conceptual",       # Misunderstood how something works
    "workflow",         # Did steps in wrong order
    "communication",    # Misread instructions or output
    "memory",           # Forgot something previously learned
    "tooling",          # Used wrong tool for the job
]


# =============================================================================
# FILE I/O (battle-tested from Lesson 2)
# =============================================================================

def load_json(filepath, default):
    """Load JSON with full error handling. Returns default on any failure."""
    try:
        if not os.path.exists(filepath):
            return default
        with open(str(filepath), "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except (json.JSONDecodeError, PermissionError, OSError):
        return default


def save_json(filepath, data):
    """Atomic-safe JSON write."""
    tmp = str(filepath) + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # Atomic replace
        if os.path.exists(str(filepath)):
            backup = str(filepath) + ".bak"
            try:
                os.replace(str(filepath), backup)
            except OSError:
                pass
        os.replace(tmp, str(filepath))
        return True
    except Exception as e:
        print(f"  Save failed: {e}")
        return False


# =============================================================================
# SKILL GRAPH ENGINE
# =============================================================================

def init_skills_db():
    """Initialize or load the skills database."""
    default = {
        "version": "0.1.0",
        "owner": "Jeremy Tabernero, MD",
        "skills": [],
        "goals": [],
        "assessments": [],
        "created": utc_now(),
        "last_updated": utc_now()
    }
    return load_json(SKILLS_FILE, default)


def add_skill(name, domain, description="", dependencies=None, level=0):
    """Add a skill to the graph."""
    db = init_skills_db()

    # Check for duplicates
    existing = [s for s in db["skills"] if s["name"].lower() == name.lower()]
    if existing:
        print(f"  Skill '{name}' already exists (level {existing[0]['level']})")
        return False

    skill = {
        "id": f"skill_{len(db['skills']) + 1:04d}",
        "name": name,
        "domain": domain,
        "description": description,
        "dependencies": dependencies or [],
        "level": level,
        "level_label": PROFICIENCY_LEVELS.get(level, "UNKNOWN"),
        "created": utc_now(),
        "last_assessed": None,
        "assessment_count": 0,
        "evidence": [],
        "hash": ""
    }
    skill["hash"] = make_hash(skill)
    db["skills"].append(skill)
    db["last_updated"] = utc_now()

    save_json(SKILLS_FILE, db)
    print(f"  Added skill: {name} [{domain}] Level {level} ({PROFICIENCY_LEVELS[level]})")
    return True


def add_goal(name, description="", required_skills=None, target_date=None):
    """Add a goal that requires specific skills."""
    db = init_skills_db()

    # Check for duplicates
    existing = [g for g in db["goals"] if g["name"].lower() == name.lower()]
    if existing:
        print(f"  Goal '{name}' already exists.")
        return False

    # Auto-create skills that don't exist yet
    skill_names = required_skills or []
    existing_skill_names = [s["name"].lower() for s in db["skills"]]

    for sname in skill_names:
        if sname.lower() not in existing_skill_names:
            print(f"  Auto-creating skill: {sname} (level 0)")
            skill = {
                "id": f"skill_{len(db['skills']) + 1:04d}",
                "name": sname,
                "domain": "auto-detected",
                "description": f"Required for: {name}",
                "dependencies": [],
                "level": 0,
                "level_label": "UNKNOWN",
                "created": utc_now(),
                "last_assessed": None,
                "assessment_count": 0,
                "evidence": [],
                "hash": ""
            }
            skill["hash"] = make_hash(skill)
            db["skills"].append(skill)

    goal = {
        "id": f"goal_{len(db['goals']) + 1:04d}",
        "name": name,
        "description": description,
        "required_skills": skill_names,
        "min_level_required": 3,  # COMPETENT minimum
        "target_date": target_date,
        "status": "active",
        "created": utc_now(),
        "hash": ""
    }
    goal["hash"] = make_hash(goal)
    db["goals"].append(goal)
    db["last_updated"] = utc_now()

    save_json(SKILLS_FILE, db)
    print(f"  Added goal: {name}")
    print(f"  Required skills ({len(skill_names)}): {', '.join(skill_names)}")
    return True


def assess_skill(skill_name, new_level, evidence=""):
    """Update proficiency level for a skill with evidence."""
    db = init_skills_db()

    matches = [s for s in db["skills"]
               if s["name"].lower() == skill_name.lower()]
    if not matches:
        print(f"  Skill '{skill_name}' not found. Use add-skill first.")
        return False

    skill = matches[0]
    old_level = skill["level"]
    skill["level"] = max(0, min(5, new_level))
    skill["level_label"] = PROFICIENCY_LEVELS[skill["level"]]
    skill["last_assessed"] = utc_now()
    skill["assessment_count"] += 1
    if evidence:
        skill["evidence"].append({
            "date": utc_now(),
            "level_from": old_level,
            "level_to": skill["level"],
            "evidence": evidence
        })
    skill["hash"] = make_hash(skill)

    # Also log the assessment
    db["assessments"].append({
        "skill": skill_name,
        "from_level": old_level,
        "to_level": skill["level"],
        "evidence": evidence,
        "timestamp": utc_now()
    })
    db["last_updated"] = utc_now()

    save_json(SKILLS_FILE, db)
    direction = "UP" if skill["level"] > old_level else ("DOWN" if skill["level"] < old_level else "SAME")
    print(f"  {skill_name}: {old_level} -> {skill['level']} ({skill['level_label']}) [{direction}]")
    if evidence:
        print(f"  Evidence: {evidence}")
    return True


def show_gaps():
    """Show all knowledge gaps — skills below required level for active goals."""
    db = init_skills_db()
    active_goals = [g for g in db["goals"] if g["status"] == "active"]

    if not active_goals:
        print("  No active goals. Use add-goal to set one.")
        return

    skill_map = {s["name"].lower(): s for s in db["skills"]}
    total_gaps = 0

    for goal in active_goals:
        min_level = goal.get("min_level_required", 3)
        gaps = []

        for sname in goal["required_skills"]:
            skill = skill_map.get(sname.lower())
            if not skill:
                gaps.append((sname, 0, min_level, "NOT TRACKED"))
            elif skill["level"] < min_level:
                gaps.append((sname, skill["level"], min_level,
                             PROFICIENCY_LEVELS[skill["level"]]))

        print(f"  GOAL: {goal['name']}")
        if goal.get("target_date"):
            print(f"  Target: {goal['target_date']}")

        if not gaps:
            print(f"  Status: ALL SKILLS MET (>= level {min_level})")
        else:
            print(f"  Gaps ({len(gaps)}):")
            for sname, current, required, label in sorted(gaps, key=lambda x: x[1]):
                deficit = required - current
                bar = "#" * current + "." * deficit
                print(f"    {sname:<30} [{bar:<5}] {current}/{required} ({label})")
            total_gaps += len(gaps)

        # Completion percentage
        total_skills = len(goal["required_skills"])
        met = total_skills - len(gaps)
        pct = int((met / total_skills) * 100) if total_skills else 0
        print(f"  Progress: {met}/{total_skills} skills met ({pct}%)")
        print()

    print(f"  Total gaps across all goals: {total_gaps}")


def show_roadmap():
    """Prioritized learning path — what to study next and why."""
    db = init_skills_db()
    active_goals = [g for g in db["goals"] if g["status"] == "active"]
    skill_map = {s["name"].lower(): s for s in db["skills"]}

    if not active_goals:
        print("  No active goals.")
        return

    # Build priority queue: skills needed by most goals, at lowest level
    skill_demand = Counter()  # how many goals need this skill
    skill_urgency = {}        # (current_level, deficit, goal_count)

    for goal in active_goals:
        min_level = goal.get("min_level_required", 3)
        for sname in goal["required_skills"]:
            skill = skill_map.get(sname.lower())
            current = skill["level"] if skill else 0
            deficit = max(0, min_level - current)
            if deficit > 0:
                skill_demand[sname] += 1
                if sname not in skill_urgency or deficit > skill_urgency[sname][1]:
                    skill_urgency[sname] = (current, deficit, skill_demand[sname])

    if not skill_urgency:
        print("  No gaps found. All skills meet goal requirements.")
        return

    # Sort: highest demand first, then largest deficit, then lowest level
    ranked = sorted(skill_urgency.items(),
                    key=lambda x: (-x[1][2], -x[1][1], x[1][0]))

    print(f"  LEARNING ROADMAP — Prioritized by impact")
    print(f"  {'PRIORITY':<10} {'SKILL':<30} {'LEVEL':<12} {'DEFICIT':<10} {'GOALS':<6}")
    print(f"  {'-'*10} {'-'*30} {'-'*12} {'-'*10} {'-'*6}")

    for rank, (sname, (current, deficit, demand)) in enumerate(ranked, 1):
        level_str = f"{current} -> {current + deficit}"
        print(f"  #{rank:<9} {sname:<30} {level_str:<12} {deficit:<10} {demand}")

    print()
    print(f"  SUGGESTED NEXT ACTION:")
    top_skill = ranked[0][0]
    top_level = ranked[0][1][0]
    print(f"    Study: {top_skill}")
    print(f"    Current: Level {top_level} ({PROFICIENCY_LEVELS[top_level]})")
    print(f"    Target:  Level 3 (COMPETENT)")
    print(f"    Why: Blocks {ranked[0][1][2]} goal(s)")


def show_skills():
    """List all tracked skills."""
    db = init_skills_db()
    if not db["skills"]:
        print("  No skills tracked. Use add-skill to start.")
        return

    # Group by domain
    domains = {}
    for s in db["skills"]:
        d = s.get("domain", "general")
        domains.setdefault(d, []).append(s)

    for domain, skills in sorted(domains.items()):
        print(f"  [{domain.upper()}]")
        for s in sorted(skills, key=lambda x: -x["level"]):
            bar = "#" * s["level"] + "." * (5 - s["level"])
            assessed = s.get("last_assessed", "never")
            if assessed and assessed != "never":
                assessed = assessed[:10]
            print(f"    {s['name']:<30} [{bar}] {s['level']}/5 "
                  f"({s['level_label']:<12}) assessed: {assessed}")
        print()


def show_goals():
    """List all goals with status."""
    db = init_skills_db()
    if not db["goals"]:
        print("  No goals. Use add-goal to set one.")
        return

    skill_map = {s["name"].lower(): s for s in db["skills"]}

    for g in db["goals"]:
        status_icon = "+" if g["status"] == "active" else "-"
        print(f"  {status_icon} {g['name']} [{g['status'].upper()}]")
        if g.get("description"):
            print(f"    {g['description']}")

        total = len(g["required_skills"])
        met = sum(1 for sn in g["required_skills"]
                  if skill_map.get(sn.lower(), {}).get("level", 0) >= g.get("min_level_required", 3))
        pct = int((met / total) * 100) if total else 0
        print(f"    Skills: {met}/{total} met ({pct}%)")
        print(f"    Required: {', '.join(g['required_skills'][:5])}")
        if len(g["required_skills"]) > 5:
            print(f"             ...and {len(g['required_skills']) - 5} more")
        print()


# =============================================================================
# ERROR PATTERN TRACKER
# =============================================================================

def init_errors_db():
    default = {
        "version": "0.1.0",
        "errors": [],
        "created": utc_now(),
        "last_updated": utc_now()
    }
    return load_json(ERRORS_FILE, default)


def log_error(error_type, what, why="", fix="", context="", related_skill=""):
    """Log an error, misconception, or failed attempt."""
    db = init_errors_db()

    if error_type not in ERROR_TYPES:
        print(f"  Invalid error type. Choose from: {', '.join(ERROR_TYPES)}")
        return False

    error = {
        "id": f"err_{len(db['errors']) + 1:04d}",
        "timestamp": utc_now(),
        "type": error_type,
        "what": what,
        "why": why,
        "fix": fix,
        "context": context,
        "related_skill": related_skill,
        "recurrence_count": 1,
        "resolved": False,
        "hash": ""
    }

    # Check if this is a REPEAT of a previous error (same type + similar what)
    for existing in db["errors"]:
        if (existing["type"] == error_type and
            _similarity(existing["what"], what) > 0.6):
            existing["recurrence_count"] += 1
            existing["last_recurrence"] = utc_now()
            if fix and not existing.get("fix"):
                existing["fix"] = fix
            db["last_updated"] = utc_now()
            save_json(ERRORS_FILE, db)
            print(f"  RECURRING ERROR (x{existing['recurrence_count']}): {what[:60]}")
            print(f"  Pattern: You've made this same mistake {existing['recurrence_count']} times.")
            if existing.get("fix"):
                print(f"  Known fix: {existing['fix']}")
            return True

    error["hash"] = make_hash(error)
    db["errors"].append(error)
    db["last_updated"] = utc_now()

    save_json(ERRORS_FILE, db)
    print(f"  Logged [{error_type}]: {what[:60]}")
    if fix:
        print(f"  Fix: {fix}")
    return True


def _similarity(a, b):
    """Simple word overlap similarity (0-1)."""
    if not a or not b:
        return 0
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0
    overlap = words_a & words_b
    return len(overlap) / max(len(words_a), len(words_b))


def show_errors():
    """Show all logged errors."""
    db = init_errors_db()
    if not db["errors"]:
        print("  No errors logged. Use log-error to start tracking.")
        return

    # Sort by recurrence (most repeated first)
    sorted_errors = sorted(db["errors"],
                           key=lambda e: -e.get("recurrence_count", 1))

    for e in sorted_errors:
        repeat = f" (x{e['recurrence_count']})" if e['recurrence_count'] > 1 else ""
        resolved = " [RESOLVED]" if e.get("resolved") else ""
        print(f"  [{e['type'].upper()}]{repeat}{resolved}")
        print(f"    What: {e['what']}")
        if e.get("why"):
            print(f"    Why:  {e['why']}")
        if e.get("fix"):
            print(f"    Fix:  {e['fix']}")
        if e.get("related_skill"):
            print(f"    Skill: {e['related_skill']}")
        print(f"    When: {e['timestamp'][:10]}")
        print()


def show_patterns():
    """Detect and display recurring error patterns."""
    db = init_errors_db()
    errors = db.get("errors", [])

    if not errors:
        print("  No errors to analyze.")
        return

    # Pattern 1: Recurring errors
    recurring = [e for e in errors if e.get("recurrence_count", 1) > 1]
    if recurring:
        print("  RECURRING ERRORS (same mistake multiple times):")
        for e in sorted(recurring, key=lambda x: -x["recurrence_count"]):
            print(f"    x{e['recurrence_count']} [{e['type']}] {e['what'][:50]}")
            if e.get("fix"):
                print(f"        Fix: {e['fix']}")
        print()

    # Pattern 2: Error type frequency
    type_counts = Counter(e["type"] for e in errors)
    print("  ERROR TYPE DISTRIBUTION:")
    for etype, count in type_counts.most_common():
        bar = "#" * min(count * 3, 30)
        print(f"    {etype:<18} {bar} {count}")
    print()

    # Pattern 3: Skills with most errors
    skill_errors = Counter(
        e.get("related_skill", "unlinked") for e in errors
        if e.get("related_skill")
    )
    if skill_errors:
        print("  SKILLS WITH MOST ERRORS:")
        for skill, count in skill_errors.most_common(5):
            print(f"    {skill:<30} {count} errors")
        print()

    # Pattern 4: Unresolved with known fixes (action items)
    fixable = [e for e in errors
               if not e.get("resolved") and e.get("fix")]
    if fixable:
        print(f"  ACTIONABLE ({len(fixable)} errors with known fixes):")
        for e in fixable:
            print(f"    [{e['type']}] {e['what'][:40]}")
            print(f"      -> {e['fix']}")
        print()


# =============================================================================
# WORKFLOW MONITOR
# =============================================================================

def init_workflow_db():
    default = {
        "version": "0.1.0",
        "commands": [],
        "sessions": [],
        "current_session": None,
        "created": utc_now(),
        "last_updated": utc_now()
    }
    return load_json(WORKFLOW_FILE, default)


def log_command(cmd, result="success", note="", duration_seconds=0):
    """Log a command execution for workflow analysis."""
    db = init_workflow_db()

    entry = {
        "id": f"cmd_{len(db['commands']) + 1:04d}",
        "timestamp": utc_now(),
        "command": cmd,
        "result": result,  # success, fail, partial
        "note": note,
        "duration_seconds": duration_seconds,
        "session": db.get("current_session")
    }

    db["commands"].append(entry)
    db["last_updated"] = utc_now()

    save_json(WORKFLOW_FILE, db)
    icon = "+" if result == "success" else "X" if result == "fail" else "~"
    print(f"  {icon} {cmd[:60]}")
    return True


def show_friction():
    """Detect workflow friction from command history."""
    db = init_workflow_db()
    commands = db.get("commands", [])

    if len(commands) < 2:
        print("  Need more command history. Use log-cmd to track commands.")
        return

    print("  WORKFLOW FRICTION ANALYSIS")
    print()

    # Pattern 1: Repeated failures (stuck loops)
    fail_streaks = []
    streak = 0
    for cmd in commands:
        if cmd["result"] == "fail":
            streak += 1
        else:
            if streak >= 2:
                fail_streaks.append(streak)
            streak = 0

    if fail_streaks:
        print(f"  STUCK LOOPS DETECTED: {len(fail_streaks)} sequences of repeated failures")
        print(f"  Longest streak: {max(fail_streaks)} consecutive failures")
        print()

    # Pattern 2: Most failed commands
    failed = [c for c in commands if c["result"] == "fail"]
    if failed:
        fail_cmds = Counter(c["command"] for c in failed)
        print("  MOST FAILED COMMANDS:")
        for cmd, count in fail_cmds.most_common(5):
            print(f"    x{count} {cmd[:50]}")
        print()

    # Pattern 3: Command frequency (what you do most)
    all_cmds = Counter(c["command"] for c in commands)
    print("  MOST FREQUENT COMMANDS:")
    for cmd, count in all_cmds.most_common(10):
        print(f"    x{count} {cmd[:50]}")
    print()

    # Pattern 4: Success rate
    total = len(commands)
    successes = sum(1 for c in commands if c["result"] == "success")
    failures = sum(1 for c in commands if c["result"] == "fail")
    rate = int((successes / total) * 100) if total else 0
    print(f"  SUCCESS RATE: {rate}% ({successes}/{total})")
    print(f"  Failures: {failures}")


def show_session():
    """Show current session summary."""
    db = init_workflow_db()
    commands = db.get("commands", [])

    if not commands:
        print("  No commands logged in this session.")
        return

    total = len(commands)
    successes = sum(1 for c in commands if c["result"] == "success")
    failures = sum(1 for c in commands if c["result"] == "fail")

    first_ts = commands[0]["timestamp"][:19]
    last_ts = commands[-1]["timestamp"][:19]

    print(f"  SESSION SUMMARY")
    print(f"  Commands:  {total}")
    print(f"  Successes: {successes}")
    print(f"  Failures:  {failures}")
    print(f"  First:     {first_ts}")
    print(f"  Last:      {last_ts}")
    print()
    print(f"  Last 10 commands:")
    for c in commands[-10:]:
        icon = "+" if c["result"] == "success" else "X"
        print(f"    {icon} {c['timestamp'][11:19]} {c['command'][:50]}")


# =============================================================================
# COMBINED DASHBOARD
# =============================================================================

def show_dashboard():
    """Full learning intelligence report."""
    skills_db = init_skills_db()
    errors_db = init_errors_db()
    workflow_db = init_workflow_db()

    print("=" * 70)
    print("  GUARDIAN ONE — LEARNING INTELLIGENCE DASHBOARD")
    print("=" * 70)
    print()

    # Skills summary
    skills = skills_db.get("skills", [])
    goals = [g for g in skills_db.get("goals", []) if g["status"] == "active"]

    print(f"  SKILLS TRACKED:    {len(skills)}")
    print(f"  ACTIVE GOALS:      {len(goals)}")

    if skills:
        levels = Counter(s["level"] for s in skills)
        for lvl in range(6):
            count = levels.get(lvl, 0)
            if count:
                bar = "#" * count
                print(f"    Level {lvl} ({PROFICIENCY_LEVELS[lvl]:<12}): {bar} {count}")

    print()

    # Errors summary
    errors = errors_db.get("errors", [])
    unresolved = [e for e in errors if not e.get("resolved")]
    recurring = [e for e in errors if e.get("recurrence_count", 1) > 1]

    print(f"  ERRORS LOGGED:     {len(errors)}")
    print(f"  UNRESOLVED:        {len(unresolved)}")
    print(f"  RECURRING:         {len(recurring)}")

    if recurring:
        worst = max(recurring, key=lambda e: e["recurrence_count"])
        print(f"  WORST PATTERN:     x{worst['recurrence_count']} {worst['what'][:40]}")

    print()

    # Workflow summary
    commands = workflow_db.get("commands", [])
    total_cmds = len(commands)
    successes = sum(1 for c in commands if c["result"] == "success")
    rate = int((successes / total_cmds) * 100) if total_cmds else 0

    print(f"  COMMANDS TRACKED:  {total_cmds}")
    print(f"  SUCCESS RATE:      {rate}%")

    print()

    # Top 3 gaps
    skill_map = {s["name"].lower(): s for s in skills}
    all_gaps = []
    for goal in goals:
        min_level = goal.get("min_level_required", 3)
        for sname in goal["required_skills"]:
            skill = skill_map.get(sname.lower())
            current = skill["level"] if skill else 0
            if current < min_level:
                all_gaps.append((sname, current, min_level,
                                 min_level - current))

    if all_gaps:
        all_gaps.sort(key=lambda x: -x[3])
        print(f"  TOP KNOWLEDGE GAPS:")
        for sname, current, target, deficit in all_gaps[:5]:
            print(f"    {sname:<30} {current}/{target} (deficit: {deficit})")

    print()
    print(f"  Generated: {utc_now()}")
    print()


# =============================================================================
# AI-READY SUGGESTION EXPORT
# =============================================================================

def show_suggestion():
    """Generate a prompt-ready summary for Claude to give learning advice."""
    skills_db = init_skills_db()
    errors_db = init_errors_db()

    skills = skills_db.get("skills", [])
    goals = [g for g in skills_db.get("goals", []) if g["status"] == "active"]
    errors = errors_db.get("errors", [])

    print("  === COPY THIS INTO CLAUDE FOR PERSONALIZED ADVICE ===")
    print()
    print("  I'm tracking my learning with Guardian One. Here's my current state:")
    print()

    if goals:
        print(f"  GOALS ({len(goals)}):")
        for g in goals:
            print(f"    - {g['name']}: {', '.join(g['required_skills'][:5])}")
    print()

    if skills:
        print(f"  SKILLS ({len(skills)}):")
        for s in sorted(skills, key=lambda x: x["level"]):
            print(f"    - {s['name']}: Level {s['level']}/5 ({s['level_label']})")
    print()

    recurring = [e for e in errors if e.get("recurrence_count", 1) > 1]
    if recurring:
        print(f"  RECURRING MISTAKES:")
        for e in recurring:
            print(f"    - [{e['type']}] {e['what']} (x{e['recurrence_count']})")
    print()

    print("  Based on this, what should I study next and how?")
    print()
    print("  === END ===")


# =============================================================================
# SEED DATA — Your real progress from Lessons 1-4
# =============================================================================

def seed_initial_data():
    """Pre-populate with your actual learning data from Guardian lessons."""
    db = init_skills_db()

    if db["skills"]:
        print("  Skills database already has data. Skipping seed.")
        return

    print("  Seeding initial data from your Guardian One lessons...")
    print()

    # Skills learned from Lessons 1-4 (52 concepts mapped to skills)
    seed_skills = [
        # Python fundamentals (Lesson 1)
        ("Python Variables & Types", "python-core", 3, "Lesson 1: used in Guardian entries"),
        ("Python Dictionaries", "python-core", 3, "Lesson 1: Guardian entries are dicts"),
        ("Python Functions", "python-core", 3, "Lesson 1: wrote create_entry(), compute_hash()"),
        ("Python File I/O", "python-core", 3, "Lessons 1-2: read/write JSON files"),
        ("Python Loops & Filtering", "python-core", 2, "Lesson 1: basic loops; Lesson 2: list comprehensions"),
        ("Python f-strings", "python-core", 3, "Used across all lessons"),
        ("Python Imports", "python-core", 2, "Lesson 1: json, hashlib, datetime, os"),
        ("Python Lists", "python-core", 3, "Lesson 1: entries stored as lists"),
        ("JSON Format", "data-formats", 3, "Core of Guardian One storage"),
        ("SHA-256 Hashing", "security", 2, "Lesson 1: hash chain, verify integrity"),

        # Intermediate (Lesson 2)
        ("Error Handling (try/except)", "python-core", 2, "Lesson 2: file loading, JSON parsing"),
        ("Date Parsing & Comparison", "python-core", 2, "Lesson 2: strptime, date ranges"),
        ("List Comprehensions", "python-core", 2, "Lesson 2: one-line filtering"),
        ("Sorting with Lambda", "python-core", 2, "Lesson 2: sorted() with key functions"),
        ("CSV Export", "data-formats", 2, "Lesson 2: csv module, Excel-ready output"),
        ("File Backup (shutil)", "python-core", 2, "Lesson 2: timestamped backups"),
        ("String Methods", "python-core", 2, "Lesson 2: .strip, .lower, .replace, etc."),
        ("os.path Operations", "python-core", 2, "Lesson 2: exists, join, getsize, basename"),

        # OOP & APIs (Lesson 3)
        ("Python Classes & __init__", "python-oop", 1, "Lesson 3: GuardianEntry, GuardianLog"),
        ("self & Instance Methods", "python-oop", 1, "Lesson 3: methods on objects"),
        ("Properties (@property)", "python-oop", 1, "Lesson 3: computed attributes"),
        ("__str__ & __repr__", "python-oop", 1, "Lesson 3: object descriptions"),
        ("Class Composition", "python-oop", 1, "Lesson 3: GuardianLog contains GuardianEntry"),
        ("Static Methods", "python-oop", 1, "Lesson 3: @staticmethod"),
        ("HTTP Requests (urllib)", "networking", 1, "Lesson 3: fetch_url(), live API calls"),
        ("JSON API Consumption", "networking", 1, "Lesson 3: parse API responses"),
        ("sys.argv Parsing", "python-core", 1, "Lesson 3: command-line arguments"),
        ("Advanced String Formatting", "python-core", 2, "Lesson 3: alignment, padding, currency"),

        # Web Server (Lesson 4)
        ("HTTP Protocol Basics", "web-dev", 1, "Lesson 4: GET, POST, status codes"),
        ("Python http.server", "web-dev", 1, "Lesson 4: built-in web server"),
        ("URL Routing", "web-dev", 1, "Lesson 4: path -> handler mapping"),
        ("HTML Generation", "web-dev", 1, "Lesson 4: server-side rendering"),
        ("CSS Styling", "web-dev", 1, "Lesson 4: dark theme dashboard"),
        ("JSON API Endpoints", "web-dev", 1, "Lesson 4: /api/entries, /api/stats"),
        ("Query Parameters", "web-dev", 1, "Lesson 4: ?category=financial&limit=5"),
        ("Content Types", "web-dev", 1, "Lesson 4: text/html vs application/json"),

        # Still needed for AI agent goal
        ("Python async/await", "python-advanced", 0, "Not yet covered"),
        ("Prompt Engineering", "ai-engineering", 1, "Used with Claude, not formalized"),
        ("LLM API Integration", "ai-engineering", 0, "Not yet covered"),
        ("Agent Loop Architecture", "ai-engineering", 0, "Not yet covered"),
        ("Token Management", "ai-engineering", 0, "Not yet covered"),
        ("Tool Use / Function Calling", "ai-engineering", 0, "Not yet covered"),
        ("State Machine Design", "architecture", 0, "Not yet covered"),
        ("SQLite / Database", "data-storage", 0, "Not yet covered"),
        ("Logging & Observability", "operations", 1, "Partial: Guardian log + workflow monitor"),
        ("Testing (unittest/pytest)", "python-core", 0, "Not yet covered"),
        ("Windows PowerShell", "environment", 1, "Learned through friction in CLI session"),
        ("Git Version Control", "environment", 0, "Not yet covered"),
    ]

    for name, domain, level, evidence in seed_skills:
        skill = {
            "id": f"skill_{len(db['skills']) + 1:04d}",
            "name": name,
            "domain": domain,
            "description": "",
            "dependencies": [],
            "level": level,
            "level_label": PROFICIENCY_LEVELS[level],
            "created": utc_now(),
            "last_assessed": utc_now(),
            "assessment_count": 1,
            "evidence": [{"date": utc_now(), "level_from": 0,
                          "level_to": level, "evidence": evidence}],
            "hash": ""
        }
        skill["hash"] = make_hash(skill)
        db["skills"].append(skill)

    # Seed goal: Build AI Agent
    db["goals"].append({
        "id": "goal_0001",
        "name": "Build AI Monitoring Agent",
        "description": "Self-monitoring AI agent that learns from user behavior, "
                       "detects misconceptions, and adapts dynamically",
        "required_skills": [
            "Python Classes & __init__", "self & Instance Methods",
            "Error Handling (try/except)", "HTTP Requests (urllib)",
            "JSON API Consumption", "JSON API Endpoints",
            "Python async/await", "LLM API Integration",
            "Agent Loop Architecture", "Token Management",
            "Tool Use / Function Calling", "State Machine Design",
            "Prompt Engineering", "Logging & Observability",
            "SQLite / Database", "Testing (unittest/pytest)"
        ],
        "min_level_required": 3,
        "target_date": "2026-06-01",
        "status": "active",
        "created": utc_now(),
        "hash": ""
    })

    # Seed errors from this session
    errors_db = init_errors_db()
    seed_errors = [
        ("navigation", "Ran python from wrong directory",
         "Files in Downloads but terminal was in C:\\Users\\jerem",
         "cd Downloads first, then python filename.py",
         "Lesson deployment session", "Windows PowerShell"),
        ("workflow", "Pasted Python code directly into PowerShell",
         "Didn't understand difference between running a file and typing code",
         "Always use: python filename.py — never paste code into terminal",
         "Lesson 4 attempt", "Python File I/O"),
        ("environment", "File downloaded with _2 suffix",
         "Browser auto-renamed duplicate downloads",
         "Check actual filename with: dir or Get-ChildItem",
         "Guardian CLI deployment", "Windows PowerShell"),
        ("communication", "Used CMD syntax in PowerShell",
         "dir /s is CMD; PowerShell uses Get-ChildItem -Recurse",
         "In PowerShell: Get-ChildItem -Recurse -Filter *.py",
         "File finding session", "Windows PowerShell"),
    ]
    for etype, what, why, fix, context, skill in seed_errors:
        error = {
            "id": f"err_{len(errors_db['errors']) + 1:04d}",
            "timestamp": utc_now(),
            "type": etype,
            "what": what,
            "why": why,
            "fix": fix,
            "context": context,
            "related_skill": skill,
            "recurrence_count": 1,
            "resolved": True,
            "hash": ""
        }
        error["hash"] = make_hash(error)
        errors_db["errors"].append(error)

    errors_db["last_updated"] = utc_now()
    db["last_updated"] = utc_now()

    save_json(SKILLS_FILE, db)
    save_json(ERRORS_FILE, errors_db)

    print(f"  Seeded {len(db['skills'])} skills across {len(set(s['domain'] for s in db['skills']))} domains")
    print(f"  Seeded {len(db['goals'])} goal")
    print(f"  Seeded {len(errors_db['errors'])} resolved errors from this session")


# =============================================================================
# CSV EXPORT
# =============================================================================

def export_all():
    """Export all learning data to CSV files."""
    import csv

    skills_db = init_skills_db()
    errors_db = init_errors_db()
    workflow_db = init_workflow_db()

    # Export skills
    skills_csv = os.path.join(SCRIPT_DIR, "guardian_skills_export.csv")
    with open(skills_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "domain", "level", "level_label", "assessment_count",
                     "last_assessed", "evidence_summary"])
        for s in skills_db.get("skills", []):
            evidence = "; ".join(e["evidence"] for e in s.get("evidence", []))
            w.writerow([s["name"], s["domain"], s["level"], s["level_label"],
                        s["assessment_count"], s.get("last_assessed", ""),
                        evidence[:200]])
    print(f"  Skills: {skills_csv}")

    # Export errors
    errors_csv = os.path.join(SCRIPT_DIR, "guardian_errors_export.csv")
    with open(errors_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["type", "what", "why", "fix", "recurrence", "resolved", "timestamp"])
        for e in errors_db.get("errors", []):
            w.writerow([e["type"], e["what"], e.get("why", ""), e.get("fix", ""),
                        e.get("recurrence_count", 1), e.get("resolved", False),
                        e["timestamp"]])
    print(f"  Errors: {errors_csv}")

    # Export workflow
    workflow_csv = os.path.join(SCRIPT_DIR, "guardian_workflow_export.csv")
    with open(workflow_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["command", "result", "note", "timestamp"])
        for c in workflow_db.get("commands", []):
            w.writerow([c["command"], c["result"], c.get("note", ""),
                        c["timestamp"]])
    print(f"  Workflow: {workflow_csv}")


# =============================================================================
# CLI INTERFACE
# =============================================================================

def print_help():
    print("""
GUARDIAN ONE — LEARNING INTELLIGENCE MODULE

  SKILL TRACKING:
    add-skill       --name "X" --domain Y [--level N] [--desc "..."]
    add-goal        --name "X" --skills "A,B,C" [--target "2026-06-01"]
    assess          --skill "X" --level N [--evidence "..."]
    gaps            Knowledge gaps for active goals
    roadmap         Prioritized learning path
    skills          List all skills
    goals           List all goals

  ERROR TRACKING:
    log-error       --type TYPE --what "..." [--why "..."] [--fix "..."]
                    [--context "..."] [--skill "..."]
                    Types: misconception, syntax, logic, navigation,
                           environment, conceptual, workflow,
                           communication, memory, tooling
    errors          Show all errors
    patterns        Detect error patterns

  WORKFLOW:
    log-cmd         --cmd "..." --result success|fail [--note "..."]
    friction        Workflow friction analysis
    session         Current session summary

  ANALYSIS:
    dashboard       Full learning intelligence report
    export          Export all data to CSV
    suggest         AI-ready learning prompt

  SETUP:
    seed            Load initial data from Lessons 1-4
    help            This message
""")


def parse_named_args(argv):
    """Parse --key value pairs from argv."""
    args = {}
    i = 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv):
            key = argv[i][2:]
            args[key] = argv[i + 1]
            i += 2
        else:
            i += 1
    return args


def main():
    if len(sys.argv) < 2:
        print_help()
        return

    command = sys.argv[1].lower()
    args = parse_named_args(sys.argv[2:])

    # --- Skill commands ---
    if command == "add-skill":
        name = args.get("name", "")
        domain = args.get("domain", "general")
        level = int(args.get("level", 0))
        desc = args.get("desc", "")
        if not name:
            print("  Required: --name \"Skill Name\"")
            return
        add_skill(name, domain, desc, level=level)

    elif command == "add-goal":
        name = args.get("name", "")
        skills = [s.strip() for s in args.get("skills", "").split(",") if s.strip()]
        target = args.get("target")
        desc = args.get("desc", "")
        if not name or not skills:
            print("  Required: --name \"Goal\" --skills \"Skill1,Skill2,...\"")
            return
        add_goal(name, desc, skills, target)

    elif command == "assess":
        skill = args.get("skill", "")
        level = int(args.get("level", 0))
        evidence = args.get("evidence", "")
        if not skill:
            print("  Required: --skill \"Skill Name\" --level N")
            return
        assess_skill(skill, level, evidence)

    elif command == "gaps":
        show_gaps()

    elif command == "roadmap":
        show_roadmap()

    elif command == "skills":
        show_skills()

    elif command == "goals":
        show_goals()

    # --- Error commands ---
    elif command == "log-error":
        etype = args.get("type", "")
        what = args.get("what", "")
        if not etype or not what:
            print("  Required: --type TYPE --what \"description\"")
            print(f"  Types: {', '.join(ERROR_TYPES)}")
            return
        log_error(etype, what, args.get("why", ""), args.get("fix", ""),
                  args.get("context", ""), args.get("skill", ""))

    elif command == "errors":
        show_errors()

    elif command == "patterns":
        show_patterns()

    # --- Workflow commands ---
    elif command == "log-cmd":
        cmd = args.get("cmd", "")
        result = args.get("result", "success")
        if not cmd:
            print("  Required: --cmd \"command\" --result success|fail")
            return
        log_command(cmd, result, args.get("note", ""))

    elif command == "friction":
        show_friction()

    elif command == "session":
        show_session()

    # --- Analysis commands ---
    elif command == "dashboard":
        show_dashboard()

    elif command == "export":
        export_all()

    elif command == "suggest":
        show_suggestion()

    elif command == "seed":
        seed_initial_data()

    elif command == "help":
        print_help()

    else:
        print(f"  Unknown command: {command}")
        print(f"  Run: python guardian_learning.py help")


if __name__ == "__main__":
    main()
