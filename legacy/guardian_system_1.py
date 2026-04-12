#!/usr/bin/env python3
"""
================================================================================
GUARDIAN ONE — CLI System v0.2.0
================================================================================
Full command-line interface for your sovereign identity log.
Includes: entry management, querying, hash verification, interaction logging.

USAGE:
    python guardian_system.py list
    python guardian_system.py add
    python guardian_system.py query --category financial
    python guardian_system.py query --tag chaos
    python guardian_system.py search "laptop"
    python guardian_system.py check
    python guardian_system.py stats
    python guardian_system.py log-interaction --request "Asked Claude for X" --type code --outcome "Got Y"

Run without arguments to see help.
================================================================================
"""

import json
import hashlib
import sys
import os
from datetime import datetime, timezone

# =============================================================================
# CONFIGURATION
# =============================================================================

LOG_FILE = "guardian_one_log.json"
INTERACTIONS_FILE = "interactions_log.json"
VERSION = "0.2.0"

# Valid values for structured fields
VALID_CATEGORIES = [
    "financial", "medical_self", "medical_dependent", "professional",
    "legal", "document", "system", "relational", "correction",
    "state_snapshot", "claude_interaction"
]

VALID_INTENTS = [
    "decision", "observation", "correction", "query", "reflection", "archive"
]

VALID_CONFIDENCE = ["high", "moderate", "low"]

VALID_RESPONSE_TYPES = ["code", "analysis", "design", "document", "conversation", "debug", "lesson"]

# =============================================================================
# TERMINAL COLORS
# =============================================================================
# These work on Mac/Linux terminals and Windows Terminal (Win 10+).
# If your terminal shows weird characters instead of colors, run:
#     python guardian_system.py list --no-color
#
# WHY: \033[ is an "escape code" that tells the terminal to change color.
# The number after [ picks the color. "0m" resets to normal.

class C:
    """Terminal color codes. Access like C.GREEN, C.BOLD, etc."""
    GREEN  = "\033[92m"
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    PURPLE = "\033[95m"
    CYAN   = "\033[96m"
    DIM    = "\033[90m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

# Global flag — set to True if user passes --no-color
NO_COLOR = "--no-color" in sys.argv
if NO_COLOR:
    # Override all colors with empty strings
    for attr in ["GREEN", "RED", "YELLOW", "BLUE", "PURPLE", "CYAN", "DIM", "BOLD", "RESET"]:
        setattr(C, attr, "")
    sys.argv.remove("--no-color")


# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def get_timestamp():
    """Return current UTC time in ISO-8601 format."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_hash(entry_dict):
    """SHA-256 hash of an entry dict. Excludes entry_hash field."""
    hashable = dict(entry_dict)
    hashable.pop("entry_hash", None)
    raw = json.dumps(hashable, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_log():
    """
    Load the Guardian One log from disk.

    RETURNS: (list of entries, dict full document)
    If file doesn't exist, returns empty structures.

    WHY TWO RETURNS?
    The JSON file has a wrapper: {"owner": ..., "entries": [...], "entry_count": N}
    You usually want just the entries list, but sometimes need the full doc.
    """
    if not os.path.exists(LOG_FILE):
        return [], None

    try:
        with open(LOG_FILE, "r") as f:
            doc = json.load(f)
        entries = doc.get("entries", [])
        return entries, doc
    except json.JSONDecodeError as e:
        # THIS MEANS: Your JSON file has a syntax error.
        # Common causes: You edited it by hand and forgot a comma or quote.
        print(f"{C.RED}ERROR: {LOG_FILE} contains invalid JSON.{C.RESET}")
        print(f"{C.DIM}  Why: The file was likely edited manually and has a syntax error.")
        print(f"  Details: {e}")
        print(f"  Fix: Open {LOG_FILE} in a text editor, find the error near line {e.lineno}.{C.RESET}")
        sys.exit(1)
    except PermissionError:
        # THIS MEANS: Your OS won't let Python read the file.
        print(f"{C.RED}ERROR: Permission denied reading {LOG_FILE}.{C.RESET}")
        print(f"{C.DIM}  Why: The file is locked by another program, or you don't have read access.")
        print(f"  Fix: Close any program using the file, or check file permissions.{C.RESET}")
        sys.exit(1)


def save_log(entries, doc=None):
    """
    Save entries to the Guardian One log file.

    If a full document wrapper exists, updates it.
    Otherwise creates a new wrapper.
    """
    if doc is None:
        doc = {
            "log_version": VERSION,
            "owner": "Jeremy Tabernero, MD",
            "created": get_timestamp(),
            "entries": entries,
            "entry_count": len(entries)
        }
    else:
        doc["entries"] = entries
        doc["entry_count"] = len(entries)

    try:
        with open(LOG_FILE, "w") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
    except PermissionError:
        print(f"{C.RED}ERROR: Can't write to {LOG_FILE}.{C.RESET}")
        print(f"{C.DIM}  Why: File is locked or you don't have write permission.")
        print(f"  Fix: Close any program using the file.{C.RESET}")
        sys.exit(1)


def load_interactions():
    """Load the interactions log. Returns list of interactions."""
    if not os.path.exists(INTERACTIONS_FILE):
        return []
    try:
        with open(INTERACTIONS_FILE, "r") as f:
            doc = json.load(f)
        return doc.get("interactions", [])
    except (json.JSONDecodeError, PermissionError):
        return []


def save_interactions(interactions):
    """Save interactions log to disk."""
    doc = {
        "log_version": VERSION,
        "owner": "Jeremy Tabernero, MD",
        "description": "Auto-logged Claude interactions with file artifact tracking",
        "interaction_count": len(interactions),
        "interactions": interactions
    }
    with open(INTERACTIONS_FILE, "w") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)


def get_next_id(entries):
    """Get the next entry ID based on existing entries."""
    if not entries:
        return 1
    return max(e.get("entry_id", 0) for e in entries) + 1


def get_prev_hash(entries):
    """Get the hash of the last entry, or GENESIS if empty."""
    if not entries:
        return "GENESIS"
    return entries[-1].get("entry_hash", "GENESIS")


def create_entry(entries, category, intent, summary, context,
                 outcome=None, confidence="high", tags=None,
                 metadata=None, references=None, documents=None):
    """Create a new entry, chain it, hash it, return it."""
    tags = tags or []
    metadata = metadata or {}
    references = references or []
    documents = documents or []

    entry = {
        "entry_id": get_next_id(entries),
        "timestamp": get_timestamp(),
        "category": category,
        "intent": intent,
        "summary": summary,
        "context": context,
        "outcome": outcome,
        "confidence": confidence,
        "references": references,
        "documents": documents,
        "tags": tags,
        "metadata": metadata,
        "prev_hash": get_prev_hash(entries),
        "entry_hash": ""
    }
    entry["entry_hash"] = compute_hash(entry)
    return entry


# =============================================================================
# DISPLAY HELPERS
# =============================================================================

def print_header(text):
    print()
    print(f"{C.GREEN}{'=' * 70}{C.RESET}")
    print(f"{C.BOLD}{C.GREEN}  {text}{C.RESET}")
    print(f"{C.GREEN}{'=' * 70}{C.RESET}")
    print()


def print_entry(entry, show_hash=False):
    """Pretty-print a single entry."""
    eid = entry.get("entry_id", "?")
    cat = entry.get("category", "unknown")
    summary = entry.get("summary", "")
    ts = entry.get("timestamp", "")
    intent = entry.get("intent", "")
    tags = entry.get("tags", [])
    outcome = entry.get("outcome")
    confidence = entry.get("confidence", "")
    metadata = entry.get("metadata", {})

    # Color the category
    cat_colors = {
        "financial": C.YELLOW,
        "medical_self": C.RED,
        "medical_dependent": C.RED,
        "professional": C.BLUE,
        "legal": C.PURPLE,
        "system": C.CYAN,
        "correction": C.DIM,
        "claude_interaction": C.GREEN,
    }
    cat_color = cat_colors.get(cat, C.RESET)

    print(f"  {C.BOLD}[{eid}]{C.RESET}  {cat_color}{cat.upper()}{C.RESET}  {C.DIM}{ts}{C.RESET}")
    print(f"       {C.BOLD}{summary}{C.RESET}")

    if outcome:
        print(f"       {C.DIM}Outcome:{C.RESET} {outcome}")

    if tags:
        tag_str = " ".join([f"{C.CYAN}#{t}{C.RESET}" for t in tags])
        print(f"       {tag_str}")

    if metadata:
        for k, v in metadata.items():
            print(f"       {C.DIM}{k}:{C.RESET} {v}")

    if show_hash:
        h = entry.get("entry_hash", "")
        print(f"       {C.DIM}hash: {h[:16]}...{C.RESET}")

    # Check for interaction link
    refs = entry.get("documents", [])
    for r in refs:
        if "interactions_log" in str(r):
            print(f"       {C.GREEN}→ {r}{C.RESET}")

    print()


# =============================================================================
# COMMANDS
# =============================================================================

def cmd_help():
    """Show usage instructions."""
    print_header("GUARDIAN ONE — CLI v" + VERSION)
    print(f"  {C.BOLD}python guardian_system.py{C.RESET} {C.GREEN}<command>{C.RESET} {C.DIM}[options]{C.RESET}")
    print()

    commands = [
        ("list",            "Show all entries (newest first)"),
        ("add",             "Add a new entry interactively"),
        ("query",           "Filter entries by --category, --tag, --intent"),
        ("search \"text\"",   "Find entries containing text in summary/context"),
        ("check",           "Verify hash chain integrity"),
        ("stats",           "Show log statistics"),
        ("log-interaction", "Log a Claude interaction"),
    ]

    print(f"  {C.BOLD}COMMANDS:{C.RESET}")
    for cmd, desc in commands:
        print(f"    {C.GREEN}{cmd:<22}{C.RESET} {desc}")

    print()
    print(f"  {C.BOLD}EXAMPLES:{C.RESET}")
    print(f"    {C.DIM}python guardian_system.py list{C.RESET}")
    print(f"    {C.DIM}python guardian_system.py query --category financial{C.RESET}")
    print(f"    {C.DIM}python guardian_system.py query --tag chaos --tag impa{C.RESET}")
    print(f"    {C.DIM}python guardian_system.py search \"laptop\"{C.RESET}")
    print(f"    {C.DIM}python guardian_system.py add{C.RESET}")
    print(f"    {C.DIM}python guardian_system.py log-interaction --request \"Asked for CLI\" --type code --outcome \"Delivered guardian_system.py\"{C.RESET}")
    print()
    print(f"  {C.BOLD}OPTIONS:{C.RESET}")
    print(f"    {C.DIM}--no-color    Disable terminal colors (if your terminal shows weird chars){C.RESET}")
    print()


def cmd_list():
    """List all entries, newest first."""
    entries, doc = load_log()

    if not entries:
        print_header("GUARDIAN ONE — LOG EMPTY")
        print(f"  {C.DIM}No entries yet. Run:{C.RESET}")
        print(f"    {C.GREEN}python guardian_system.py add{C.RESET}")
        print(f"  {C.DIM}Or run the lesson first to generate sample data:{C.RESET}")
        print(f"    {C.GREEN}python guardian_one_lesson.py{C.RESET}")
        print()
        return

    print_header(f"GUARDIAN ONE — ALL ENTRIES ({len(entries)})")

    # Show newest first
    for entry in reversed(entries):
        print_entry(entry, show_hash=True)


def cmd_query(args):
    """Filter entries by category, tag, or intent."""
    entries, doc = load_log()

    if not entries:
        print(f"  {C.DIM}Log is empty. Nothing to query.{C.RESET}")
        return

    # Parse arguments
    category = None
    tags = []
    intent = None

    i = 0
    while i < len(args):
        if args[i] == "--category" and i + 1 < len(args):
            category = args[i + 1].lower()
            # Validate category
            if category not in VALID_CATEGORIES:
                print(f"\n  {C.RED}ERROR: Category \"{category}\" not recognized.{C.RESET}")
                print(f"  {C.DIM}Why: Guardian One uses a fixed set of categories for consistency.")
                print(f"  Valid categories:{C.RESET}")
                for vc in VALID_CATEGORIES:
                    print(f"    {C.GREEN}{vc}{C.RESET}")
                print()
                return
            i += 2
        elif args[i] == "--tag" and i + 1 < len(args):
            tags.append(args[i + 1].lower())
            i += 2
        elif args[i] == "--tags" and i + 1 < len(args):
            # Support --tags chaos,impa syntax
            tags.extend([t.strip().lower() for t in args[i + 1].split(",")])
            i += 2
        elif args[i] == "--intent" and i + 1 < len(args):
            intent = args[i + 1].lower()
            if intent not in VALID_INTENTS:
                print(f"\n  {C.RED}ERROR: Intent \"{intent}\" not recognized.{C.RESET}")
                print(f"  {C.DIM}Valid intents:{C.RESET}")
                for vi in VALID_INTENTS:
                    print(f"    {C.GREEN}{vi}{C.RESET}")
                print()
                return
            i += 2
        else:
            print(f"\n  {C.RED}ERROR: Unknown option \"{args[i]}\"{C.RESET}")
            print(f"  {C.DIM}Why: query expects --category, --tag, --tags, or --intent.")
            print(f"  Example: python guardian_system.py query --category financial{C.RESET}")
            print()
            return

    if not category and not tags and not intent:
        print(f"\n  {C.RED}ERROR: No filter specified.{C.RESET}")
        print(f"  {C.DIM}Why: query needs at least one filter to know what you're looking for.")
        print(f"  Examples:")
        print(f"    python guardian_system.py query --category financial")
        print(f"    python guardian_system.py query --tag chaos")
        print(f"    python guardian_system.py query --intent decision{C.RESET}")
        print()
        return

    # Filter
    results = []
    for entry in entries:
        match = True
        if category and entry.get("category", "").lower() != category:
            match = False
        if tags:
            entry_tags = [t.lower() for t in entry.get("tags", [])]
            for required_tag in tags:
                if required_tag not in entry_tags:
                    match = False
                    break
        if intent and entry.get("intent", "").lower() != intent:
            match = False
        if match:
            results.append(entry)

    # Build filter description
    filter_parts = []
    if category:
        filter_parts.append(f"category={category}")
    if tags:
        filter_parts.append(f"tags={','.join(tags)}")
    if intent:
        filter_parts.append(f"intent={intent}")
    filter_desc = " + ".join(filter_parts)

    print_header(f"QUERY RESULTS — {filter_desc}")

    if not results:
        print(f"  {C.DIM}No entries match this filter.{C.RESET}")
        print(f"  {C.DIM}Tip: Run 'python guardian_system.py list' to see all entries.{C.RESET}")
        print()
        return

    print(f"  {C.DIM}{len(results)} match(es) found:{C.RESET}")
    print()
    for entry in results:
        print_entry(entry)


def cmd_search(args):
    """Full-text search across summary and context fields."""
    if not args:
        print(f"\n  {C.RED}ERROR: No search term provided.{C.RESET}")
        print(f"  {C.DIM}Why: search needs to know what text to look for.")
        print(f"  Example: python guardian_system.py search \"laptop\"{C.RESET}")
        print()
        return

    term = " ".join(args).lower().strip('"').strip("'")
    entries, doc = load_log()

    if not entries:
        print(f"  {C.DIM}Log is empty.{C.RESET}")
        return

    results = []
    for entry in entries:
        searchable = " ".join([
            str(entry.get("summary", "")),
            str(entry.get("context", "")),
            str(entry.get("outcome", "")),
            " ".join(entry.get("tags", [])),
        ]).lower()
        if term in searchable:
            results.append(entry)

    print_header(f"SEARCH RESULTS — \"{term}\"")

    if not results:
        print(f"  {C.DIM}No entries contain \"{term}\".{C.RESET}")
        print(f"  {C.DIM}Tip: search checks summary, context, outcome, and tags.{C.RESET}")
        print()
        return

    print(f"  {C.DIM}{len(results)} match(es):{C.RESET}")
    print()
    for entry in results:
        print_entry(entry)


def cmd_check():
    """Verify hash chain integrity."""
    entries, doc = load_log()

    if not entries:
        print(f"  {C.DIM}Log is empty. Nothing to verify.{C.RESET}")
        return

    print_header("HASH CHAIN VERIFICATION")

    all_valid = True
    for i, entry in enumerate(entries):
        eid = entry.get("entry_id", "?")
        expected = compute_hash(entry)
        actual = entry.get("entry_hash", "")

        # Check self-hash
        if expected != actual:
            print(f"  {C.RED}✗ Entry {eid}: HASH MISMATCH{C.RESET}")
            print(f"    {C.DIM}Expected: {expected[:24]}...")
            print(f"    Got:      {actual[:24]}...")
            print(f"    Why: This entry was modified after it was created.{C.RESET}")
            all_valid = False
        else:
            print(f"  {C.GREEN}✓ Entry {eid}: VALID{C.RESET}  {C.DIM}{actual[:16]}...{C.RESET}")

        # Check chain link
        if i > 0:
            prev_expected = entries[i - 1].get("entry_hash", "")
            prev_actual = entry.get("prev_hash", "")
            if prev_expected != prev_actual:
                print(f"    {C.RED}✗ CHAIN BREAK: Entry {eid} doesn't link to entry {entries[i-1].get('entry_id', '?')}{C.RESET}")
                print(f"    {C.DIM}Why: The previous entry was modified or an entry was inserted/deleted.")
                print(f"    This means the log has been tampered with.{C.RESET}")
                all_valid = False
            else:
                print(f"    {C.DIM}↳ chain link valid{C.RESET}")
        else:
            prev = entry.get("prev_hash", "")
            if prev == "GENESIS":
                print(f"    {C.DIM}↳ genesis entry{C.RESET}")

    print()
    if all_valid:
        print(f"  {C.GREEN}{C.BOLD}CHAIN STATUS: ALL {len(entries)} HASHES VALID. LOG INTEGRITY CONFIRMED.{C.RESET}")
    else:
        print(f"  {C.RED}{C.BOLD}CHAIN STATUS: INTEGRITY FAILURES DETECTED. LOG MAY BE TAMPERED.{C.RESET}")
    print()


def cmd_stats():
    """Show log statistics."""
    entries, doc = load_log()
    interactions = load_interactions()

    print_header("GUARDIAN ONE — STATISTICS")

    print(f"  {C.BOLD}Log File:{C.RESET}          {LOG_FILE}")
    print(f"  {C.BOLD}Total Entries:{C.RESET}      {len(entries)}")
    print(f"  {C.BOLD}Interactions:{C.RESET}       {len(interactions)}")
    print()

    if not entries:
        return

    # Category breakdown
    cats = {}
    for e in entries:
        cat = e.get("category", "unknown")
        cats[cat] = cats.get(cat, 0) + 1

    print(f"  {C.BOLD}By Category:{C.RESET}")
    for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
        bar = "█" * count
        print(f"    {cat:<22} {C.GREEN}{bar}{C.RESET} {count}")
    print()

    # Tag cloud
    all_tags = {}
    for e in entries:
        for t in e.get("tags", []):
            all_tags[t] = all_tags.get(t, 0) + 1

    if all_tags:
        print(f"  {C.BOLD}Top Tags:{C.RESET}")
        for tag, count in sorted(all_tags.items(), key=lambda x: -x[1])[:10]:
            print(f"    {C.CYAN}#{tag}{C.RESET}  ({count})")
        print()

    # Financial summary
    total = 0.0
    for e in entries:
        if e.get("category") == "correction":
            continue
        meta = e.get("metadata", {})
        amount = meta.get("amount_usd") or meta.get("cost_usd") or 0
        if amount:
            total += float(amount)

    if total > 0:
        print(f"  {C.BOLD}Total Tracked Spending:{C.RESET}  {C.YELLOW}${total:,.2f}{C.RESET}")
        print()

    # Time range
    timestamps = [e.get("timestamp", "") for e in entries if e.get("timestamp")]
    if timestamps:
        print(f"  {C.BOLD}First Entry:{C.RESET}        {timestamps[0]}")
        print(f"  {C.BOLD}Latest Entry:{C.RESET}       {timestamps[-1]}")
    print()


def cmd_add():
    """Interactive entry creation."""
    entries, doc = load_log()

    print_header("ADD NEW ENTRY")
    print(f"  {C.DIM}Fill in each field. Press Enter to skip optional fields.{C.RESET}")
    print()

    # Category
    print(f"  {C.BOLD}Category{C.RESET} (required):")
    for i, cat in enumerate(VALID_CATEGORIES):
        print(f"    {C.GREEN}{i+1:>2}{C.RESET}. {cat}")
    print()

    try:
        cat_input = input(f"  {C.CYAN}Enter number or name: {C.RESET}").strip()
    except (KeyboardInterrupt, EOFError):
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")
        return

    # Resolve category
    if cat_input.isdigit():
        idx = int(cat_input) - 1
        if 0 <= idx < len(VALID_CATEGORIES):
            category = VALID_CATEGORIES[idx]
        else:
            print(f"  {C.RED}ERROR: Number {cat_input} is out of range (1-{len(VALID_CATEGORIES)}).{C.RESET}")
            return
    elif cat_input.lower() in VALID_CATEGORIES:
        category = cat_input.lower()
    else:
        print(f"  {C.RED}ERROR: \"{cat_input}\" is not a valid category.{C.RESET}")
        print(f"  {C.DIM}Why: Guardian One uses a fixed set of categories to keep data queryable.{C.RESET}")
        return

    # Intent
    print(f"\n  {C.BOLD}Intent{C.RESET} (required):")
    for i, intent in enumerate(VALID_INTENTS):
        print(f"    {C.GREEN}{i+1}{C.RESET}. {intent}")
    print()

    try:
        int_input = input(f"  {C.CYAN}Enter number or name: {C.RESET}").strip()
    except (KeyboardInterrupt, EOFError):
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")
        return

    if int_input.isdigit():
        idx = int(int_input) - 1
        if 0 <= idx < len(VALID_INTENTS):
            intent = VALID_INTENTS[idx]
        else:
            print(f"  {C.RED}ERROR: Number out of range.{C.RESET}")
            return
    elif int_input.lower() in VALID_INTENTS:
        intent = int_input.lower()
    else:
        print(f"  {C.RED}ERROR: \"{int_input}\" is not a valid intent.{C.RESET}")
        return

    # Summary, Context, Outcome
    try:
        print()
        summary = input(f"  {C.CYAN}Summary (one line): {C.RESET}").strip()
        if not summary:
            print(f"  {C.RED}ERROR: Summary is required.{C.RESET}")
            print(f"  {C.DIM}Why: Every entry needs at least a one-line description of what happened.{C.RESET}")
            return

        context = input(f"  {C.CYAN}Context (why): {C.RESET}").strip() or None
        outcome = input(f"  {C.CYAN}Outcome (result, optional): {C.RESET}").strip() or None

        tags_raw = input(f"  {C.CYAN}Tags (comma-separated, optional): {C.RESET}").strip()
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        conf_input = input(f"  {C.CYAN}Confidence [high/moderate/low, default=high]: {C.RESET}").strip().lower()
        confidence = conf_input if conf_input in VALID_CONFIDENCE else "high"

    except (KeyboardInterrupt, EOFError):
        print(f"\n  {C.DIM}Cancelled.{C.RESET}")
        return

    # Create and save
    entry = create_entry(
        entries, category, intent, summary,
        context=context, outcome=outcome,
        confidence=confidence, tags=tags
    )

    entries.append(entry)
    save_log(entries, doc)

    print()
    print(f"  {C.GREEN}✓ Entry #{entry['entry_id']} created and saved.{C.RESET}")
    print()
    print_entry(entry, show_hash=True)


def cmd_log_interaction(args):
    """
    Log a Claude interaction. Creates entry in BOTH logs.

    Usage:
      python guardian_system.py log-interaction \
          --request "What I asked Claude" \
          --type code \
          --outcome "What I received" \
          --files file1.py,file2.html \
          --tags python,lesson \
          --duration 120
    """
    entries, doc = load_log()
    interactions = load_interactions()

    # Parse args
    request_text = None
    response_type = None
    outcome = None
    files = []
    tags = []
    duration = None

    i = 0
    while i < len(args):
        if args[i] == "--request" and i + 1 < len(args):
            request_text = args[i + 1]
            i += 2
        elif args[i] == "--type" and i + 1 < len(args):
            response_type = args[i + 1].lower()
            if response_type not in VALID_RESPONSE_TYPES:
                print(f"\n  {C.RED}ERROR: Response type \"{response_type}\" not recognized.{C.RESET}")
                print(f"  {C.DIM}Valid types: {', '.join(VALID_RESPONSE_TYPES)}{C.RESET}")
                print()
                return
            i += 2
        elif args[i] == "--outcome" and i + 1 < len(args):
            outcome = args[i + 1]
            i += 2
        elif args[i] == "--files" and i + 1 < len(args):
            files = [f.strip() for f in args[i + 1].split(",") if f.strip()]
            i += 2
        elif args[i] == "--tags" and i + 1 < len(args):
            tags = [t.strip() for t in args[i + 1].split(",") if t.strip()]
            i += 2
        elif args[i] == "--duration" and i + 1 < len(args):
            try:
                duration = int(args[i + 1])
            except ValueError:
                print(f"\n  {C.RED}ERROR: Duration must be a number (seconds).{C.RESET}")
                print(f"  {C.DIM}Example: --duration 120{C.RESET}")
                return
            i += 2
        else:
            print(f"\n  {C.RED}ERROR: Unknown option \"{args[i]}\"{C.RESET}")
            print(f"  {C.DIM}Valid options: --request, --type, --outcome, --files, --tags, --duration{C.RESET}")
            return

    if not request_text:
        print(f"\n  {C.RED}ERROR: --request is required.{C.RESET}")
        print(f"  {C.DIM}Why: The interaction log needs to know what you asked Claude.")
        print(f"  Example: --request \"Asked Claude to build Guardian CLI v0.2\"{C.RESET}")
        print()
        return

    # Build interaction record
    interaction_id = len(interactions) + 1
    timestamp = get_timestamp()

    interaction = {
        "interaction_id": interaction_id,
        "date_requested": timestamp,
        "date_response_received": timestamp,
        "request_text": request_text,
        "response_type": response_type or "conversation",
        "outcome": outcome,
        "duration_seconds": duration,
        "tags": tags,
        "file_artifacts": [],
        "file_contents_snapshot": {}
    }

    # Process files — read content for plain text snapshot
    for filepath in files:
        interaction["file_artifacts"].append(filepath)
        # Try to read file contents for the snapshot
        if os.path.exists(filepath):
            try:
                with open(filepath, "r") as f:
                    content = f.read()
                # Store first 500 chars as preview + full path
                interaction["file_contents_snapshot"][filepath] = {
                    "size_bytes": len(content),
                    "preview": content[:500] + ("..." if len(content) > 500 else ""),
                    "full_content_available": True
                }
            except Exception:
                interaction["file_contents_snapshot"][filepath] = {
                    "error": "Could not read file",
                    "full_content_available": False
                }
        else:
            interaction["file_contents_snapshot"][filepath] = {
                "error": f"File not found at {filepath}",
                "full_content_available": False
            }

    # Save to interactions log
    interactions.append(interaction)
    save_interactions(interactions)

    # Also create a Guardian One entry
    guardian_entry = create_entry(
        entries,
        category="claude_interaction",
        intent="observation",
        summary=f"Claude: {outcome or request_text}",
        context=request_text,
        outcome=outcome,
        tags=tags + ["claude-interaction"],
        metadata={
            "response_type": response_type or "conversation",
            "duration_seconds": duration,
            "file_count": len(files),
        },
        documents=[f"{INTERACTIONS_FILE}#interaction_{interaction_id}"] + files
    )

    entries.append(guardian_entry)
    save_log(entries, doc)

    print()
    print(f"  {C.GREEN}✓ Interaction #{interaction_id} logged to {INTERACTIONS_FILE}{C.RESET}")
    print(f"  {C.GREEN}✓ Guardian entry #{guardian_entry['entry_id']} created (CLAUDE_INTERACTION){C.RESET}")
    print()
    print_entry(guardian_entry, show_hash=True)


# =============================================================================
# MAIN — ARGUMENT ROUTER
# =============================================================================

def main():
    """
    Route command-line arguments to the right function.

    HOW THIS WORKS:
    sys.argv is a list of everything you typed after "python".
    Example: python guardian_system.py query --tag chaos
    sys.argv = ["guardian_system.py", "query", "--tag", "chaos"]
    sys.argv[0] = the script name (always)
    sys.argv[1] = the command
    sys.argv[2:] = everything after the command (the arguments)
    """
    # If no command given, show help
    if len(sys.argv) < 2:
        cmd_help()
        return

    command = sys.argv[1].lower()
    args = sys.argv[2:]  # Everything after the command

    # Route to the right function
    if command == "help" or command == "--help" or command == "-h":
        cmd_help()
    elif command == "list":
        cmd_list()
    elif command == "add":
        cmd_add()
    elif command == "query":
        cmd_query(args)
    elif command == "search":
        cmd_search(args)
    elif command == "check":
        cmd_check()
    elif command == "stats":
        cmd_stats()
    elif command == "log-interaction":
        cmd_log_interaction(args)
    else:
        print(f"\n  {C.RED}ERROR: Unknown command \"{command}\"{C.RESET}")
        print(f"  {C.DIM}Why: \"{command}\" isn't one of Guardian One's commands.")
        print(f"  Did you mean one of these?{C.RESET}")
        print()

        # Suggest closest match
        valid_commands = ["list", "add", "query", "search", "check", "stats", "log-interaction", "help"]
        for vc in valid_commands:
            # Simple similarity: check if any characters overlap
            if command[0] == vc[0] or command in vc or vc in command:
                print(f"    {C.GREEN}python guardian_system.py {vc}{C.RESET}")

        print()
        print(f"  {C.DIM}Run 'python guardian_system.py help' for full command list.{C.RESET}")
        print()


if __name__ == "__main__":
    main()
