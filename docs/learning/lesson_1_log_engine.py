"""
================================================================================
GUARDIAN ONE — PYTHON LESSON 1: Your First Working Log Engine
================================================================================

WHAT THIS FILE IS:
    This is a real, working Python program. It's also a lesson.
    Every section teaches you a Python concept by building a piece
    of Guardian One that actually does something.

HOW TO USE THIS FILE:
    1. Open a terminal (Command Prompt on Windows, Terminal on Mac/Linux)
    2. Type: python guardian_one_lesson.py
    3. Watch it run. Read the output.
    4. Come back to this file. Read the comments. Change things. Run again.

WHAT YOU'LL LEARN:
    - Variables and data types (strings, numbers, booleans, lists, dicts)
    - Dictionaries (the backbone of Guardian One)
    - Lists (how entries are stored)
    - Functions (reusable actions)
    - File I/O (saving and loading your log)
    - Loops and filtering (querying your data)
    - f-strings (formatting output)

PREREQUISITE: Python 3.10+ installed.
    Check by running: python --version
================================================================================
"""

# =============================================================================
# CONCEPT 1: IMPORTS
# =============================================================================
# "import" loads code that someone else already wrote so you don't have to.
# Think of it like: "I need these tools from the toolbox."

import json                    # Reads and writes JSON files (your log format)
import hashlib                 # Creates SHA-256 hashes (chain integrity)
from datetime import datetime  # Handles dates and times
import os                      # Interacts with the file system

# =============================================================================
# CONCEPT 2: VARIABLES
# =============================================================================
# A variable is a name that points to a value. That's it.
# Python figures out the type automatically — you don't declare it.

# This is a STRING — text wrapped in quotes
log_version = "0.1.0"

# This is an INTEGER — a whole number
next_entry_id = 1

# This is a BOOLEAN — True or False, nothing else
log_initialized = False

# This is the FILE PATH where your log will be saved
# We'll create this file automatically
LOG_FILE = "guardian_one_log.json"

print("=" * 70)
print("GUARDIAN ONE — Log Engine v" + log_version)
print("=" * 70)
print()

# =============================================================================
# CONCEPT 3: DICTIONARIES (dicts)
# =============================================================================
# A dictionary is the single most important data structure in Python.
# It maps KEYS to VALUES. Like a real dictionary maps words to definitions.
#
# Syntax: { "key": value, "another_key": another_value }
#
# Guardian One entries ARE dictionaries.
# JSON files ARE dictionaries.
# API responses ARE dictionaries.
# This is the #1 thing to understand.

# Here's a simple one:
owner = {
    "name": "Jeremy Tabernero, MD",
    "role": "Hospitalist Physician",
    "employer": "Essentia Health",
    "location": "Duluth, MN"
}

# ACCESS a value by its key:
print("Owner:", owner["name"])
print("Role:", owner["role"])
print()

# You can also use .get() which won't crash if the key doesn't exist:
print("Email:", owner.get("email", "not set"))  # Returns "not set" instead of crashing
print()


# =============================================================================
# CONCEPT 4: FUNCTIONS
# =============================================================================
# A function is a reusable block of code. You define it once, call it many times.
#
# Syntax:
#   def function_name(parameter1, parameter2):
#       # do stuff
#       return result
#
# Think of it like writing a protocol. Once written, anyone can follow it.

def get_timestamp():
    """Return the current time in UTC ISO-8601 format."""
    return datetime.now(tz=__import__('datetime').timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# Call it:
print("Current UTC time:", get_timestamp())
print()


def compute_hash(entry_dict):
    """
    Compute SHA-256 hash of an entry.
    This is what makes Guardian One tamper-evident.
    If anyone changes a single character in an entry, the hash changes.
    """
    # Step 1: Make a copy so we don't modify the original
    hashable = dict(entry_dict)

    # Step 2: Remove the hash field itself (can't hash your own hash)
    hashable.pop("entry_hash", None)

    # Step 3: Convert to a JSON string (deterministic with sort_keys)
    raw = json.dumps(hashable, sort_keys=True, ensure_ascii=False)

    # Step 4: Hash it
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# =============================================================================
# CONCEPT 5: CREATING AN ENTRY (Building a Dictionary)
# =============================================================================
# This function creates a single Guardian One log entry.
# It takes in the parts, assembles them into a dictionary, and returns it.

def create_entry(
    entry_id,           # int — sequence number
    category,           # string — "financial", "medical_self", etc.
    intent,             # string — "decision", "observation", etc.
    summary,            # string — one-line description
    context,            # string — why this happened
    outcome=None,       # string or None — what resulted
    confidence="high",  # string — "high", "moderate", "low"
    references=None,    # list of ints — related entry IDs
    documents=None,     # list of strings — file paths
    tags=None,          # list of strings — searchable tags
    metadata=None,      # dict — structured key-value data
    prev_hash="GENESIS" # string — hash of previous entry
):
    """
    Build a Guardian One entry as a plain dictionary.

    WHY A DICTIONARY AND NOT A CLASS?
    The schema.py you designed uses Python dataclasses, which is the
    production-grade approach. But for learning, a dictionary is the same
    concept without the extra syntax. Once you understand dicts, classes
    are just dicts with superpowers.
    """

    # "or" here means: if references is None, use an empty list instead
    # This is a common Python pattern to avoid mutable default arguments
    references = references or []
    documents = documents or []
    tags = tags or []
    metadata = metadata or {}

    entry = {
        "entry_id": entry_id,
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
        "prev_hash": prev_hash,
        "entry_hash": ""  # Will be computed next
    }

    # Compute and set the hash — this seals the entry
    entry["entry_hash"] = compute_hash(entry)

    return entry


# =============================================================================
# CONCEPT 6: LISTS
# =============================================================================
# A list is an ordered collection. Square brackets.
# Your log is a list of entries (dictionaries).
#
# Syntax: [item1, item2, item3]
#
# Lists are ordered, indexed starting at 0, and can hold anything.

log = []  # Empty list. This is your Guardian One log in memory.


# =============================================================================
# CONCEPT 7: BUILDING THE LOG — 5 Real Entries
# =============================================================================
# Now we create 5 real entries from your actual life and decisions.
# Each one teaches a slightly different pattern.

print("-" * 70)
print("WRITING ENTRIES")
print("-" * 70)
print()

# ---- ENTRY 1: Hardware Purchase ----
entry_1 = create_entry(
    entry_id=1,
    category="financial",
    intent="decision",
    summary="Purchased ASUS ROG Strix Flow laptop, 64GB RAM.",
    context=(
        "MacBook Pro memory constraints bottlenecking agent development. "
        "Needed hardware that eliminates RAM as a variable. "
        "Evaluated ROG Strix vs Razer Blade vs Framework 16."
    ),
    outcome="Purchased. Development environment migrated.",
    confidence="high",
    tags=["hardware", "development", "overlord-guardian"],
    metadata={
        "amount_usd": 2149.00,
        "vendor": "ASUS",
        "model": "ROG Strix Flow",
        "ram_gb": 64
    },
    prev_hash="GENESIS"  # First entry — no previous hash
)
log.append(entry_1)  # .append() adds an item to the end of a list
print(f"  Entry {entry_1['entry_id']}: {entry_1['summary']}")

# ---- ENTRY 2: Chaos Veterinary Decision ----
entry_2 = create_entry(
    entry_id=2,
    category="medical_dependent",
    intent="decision",
    summary="Maintained Chaos on Cyclosporine 50mg q12h + Prednisone 10mg q12h.",
    context=(
        "IMPA diagnosis via BluePearl Golden Valley. "
        "Discussed taper timeline with vet. "
        "Current labs stable. No adverse effects noted."
    ),
    outcome="Continuing current regimen. Recheck in 4 weeks.",
    confidence="high",
    tags=["chaos", "impa", "cyclosporine", "prednisone"],
    metadata={
        "patient": "Chaos",
        "species": "canine",
        "breed": "French Bulldog",
        "provider": "Happy Tails Superior WI / BluePearl Golden Valley"
    },
    prev_hash=entry_1["entry_hash"]  # Chain link to previous entry
)
log.append(entry_2)
print(f"  Entry {entry_2['entry_id']}: {entry_2['summary']}")

# ---- ENTRY 3: Guardian One Schema Design ----
entry_3 = create_entry(
    entry_id=3,
    category="system",
    intent="generation",
    summary="Defined Guardian One schema v0.1.0.",
    context=(
        "Conceptualized sovereign identity log as foundation layer "
        "for Overlord Guardian stack. Append-only, hash-chained, "
        "JSON-native. Designed with Claude."
    ),
    outcome="Schema finalized. Ready for log engine implementation.",
    confidence="moderate",
    tags=["guardian-one", "overlord-guardian", "architecture"],
    metadata={
        "schema_version": "0.1.0",
        "stack_layer": "foundation"
    },
    prev_hash=entry_2["entry_hash"]
)
log.append(entry_3)
print(f"  Entry {entry_3['entry_id']}: {entry_3['summary']}")

# ---- ENTRY 4: Correction (fixes Entry 1) ----
entry_4 = create_entry(
    entry_id=4,
    category="correction",
    intent="correction",
    summary="Correcting entry 1: actual purchase price was $2,149.",
    context=(
        "Original entry left amount_usd as None. "
        "Located receipt and updating record."
    ),
    outcome="Financial metadata now complete for ROG Strix purchase.",
    confidence="high",
    references=[1],  # Points back to the entry being corrected
    documents=["receipts/2026/rog_strix_purchase.pdf"],
    tags=["correction", "hardware", "financial"],
    metadata={
        "corrects_entry_id": 1,
        "corrected_field": "metadata.amount_usd",
        "corrected_value": 2149.00
    },
    prev_hash=entry_3["entry_hash"]
)
log.append(entry_4)
print(f"  Entry {entry_4['entry_id']}: {entry_4['summary']}")

# ---- ENTRY 5: Domain Registration (what you just did today) ----
entry_5 = create_entry(
    entry_id=5,
    category="professional",
    intent="decision",
    summary="Registered jtmdai.com and deployed JTMedAI dashboard.",
    context=(
        "Built healthcare AI integration intelligence dashboard. "
        "Registered domain via Cloudflare for $10.46/year. "
        "Deployed static site via Cloudflare Workers. "
        "Dashboard tracks AI adoption friction, market caps, and news."
    ),
    outcome="Site live at jtmdai.com. First public advisory asset.",
    confidence="high",
    tags=["jtmedai", "website", "cloudflare", "advisory", "professional"],
    metadata={
        "domain": "jtmdai.com",
        "registrar": "Cloudflare",
        "cost_usd": 10.46,
        "hosting": "Cloudflare Workers (free tier)",
        "invoice": "IN-58178604"
    },
    prev_hash=entry_4["entry_hash"]
)
log.append(entry_5)
print(f"  Entry {entry_5['entry_id']}: {entry_5['summary']}")

print()
print(f"  Total entries in log: {len(log)}")
print()


# =============================================================================
# CONCEPT 8: FILE I/O — Saving to Disk
# =============================================================================
# Everything above exists only in memory. If you close Python, it's gone.
# File I/O (Input/Output) lets you save data to a file and read it back.
#
# json.dump()  → writes Python data to a JSON file
# json.load()  → reads a JSON file back into Python data
#
# "with open(...) as f" is a CONTEXT MANAGER — it automatically closes
# the file when done, even if an error occurs. Always use this pattern.

print("-" * 70)
print("SAVING LOG TO DISK")
print("-" * 70)
print()

# Build the full log document
log_document = {
    "schema_version": log_version,
    "owner": owner,
    "entry_count": len(log),
    "entries": log
}

# Write it to disk
with open(LOG_FILE, "w") as f:
    json.dump(log_document, f, indent=2)

# os.path.getsize returns file size in bytes
file_size = os.path.getsize(LOG_FILE)
print(f"  Saved to: {LOG_FILE}")
print(f"  File size: {file_size:,} bytes")
print()


# =============================================================================
# CONCEPT 9: READING IT BACK
# =============================================================================
# Prove the save worked by reading the file back into a NEW variable.

with open(LOG_FILE, "r") as f:
    loaded_log = json.load(f)

print(f"  Loaded back: {loaded_log['entry_count']} entries")
print(f"  Schema version: {loaded_log['schema_version']}")
print(f"  Owner: {loaded_log['owner']['name']}")
print()


# =============================================================================
# CONCEPT 10: QUERYING — Filtering and Searching
# =============================================================================
# This is where Guardian One becomes useful.
# "Querying" means: give me only the entries that match some condition.
#
# In Python, you do this with LOOPS and CONDITIONS.
#
# A FOR loop walks through each item in a list, one at a time:
#   for entry in log:
#       # do something with each entry
#
# An IF statement checks a condition:
#   if entry["category"] == "financial":
#       # only runs for financial entries

print("-" * 70)
print("QUERYING THE LOG")
print("-" * 70)
print()

# ---- Query 1: All financial entries ----
print("  QUERY: All financial entries")
print("  " + "-" * 40)
for entry in log:
    if entry["category"] == "financial":
        print(f"    [{entry['entry_id']}] {entry['summary']}")
print()

# ---- Query 2: What medical decisions have I made for Chaos? ----
print("  QUERY: Medical decisions for Chaos")
print("  " + "-" * 40)
for entry in log:
    if entry["category"] == "medical_dependent" and "chaos" in entry["tags"]:
        print(f"    [{entry['entry_id']}] {entry['summary']}")
        print(f"    Outcome: {entry['outcome']}")
print()

# ---- Query 3: All corrections ----
print("  QUERY: All corrections")
print("  " + "-" * 40)
for entry in log:
    if entry["category"] == "correction":
        corrects_id = entry["metadata"].get("corrects_entry_id", "?")
        print(f"    [{entry['entry_id']}] Corrects entry {corrects_id}: {entry['summary']}")
print()

# ---- Query 4: Entries with a specific tag ----
search_tag = "overlord-guardian"
print(f"  QUERY: All entries tagged '{search_tag}'")
print("  " + "-" * 40)
for entry in log:
    if search_tag in entry["tags"]:
        print(f"    [{entry['entry_id']}] {entry['summary']}")
print()

# ---- Query 5: Total spending from metadata ----
print("  QUERY: Total spending tracked in log")
print("  " + "-" * 40)
total_spent = 0.0
for entry in log:
    # .get() returns None if key doesn't exist, and we skip corrections
    # to avoid double-counting
    amount = entry["metadata"].get("cost_usd") or entry["metadata"].get("amount_usd")
    if amount and entry["category"] != "correction":
        total_spent += amount
        print(f"    [{entry['entry_id']}] ${amount:,.2f} — {entry['summary'][:50]}")
total_spent_display = f"${total_spent:,.2f}"
print(f"    {'':>4}  TOTAL: {total_spent_display}")
print()


# =============================================================================
# CONCEPT 11: HASH CHAIN VERIFICATION
# =============================================================================
# This is the integrity feature. We walk the chain and verify every link.
# If anyone tampered with an entry, the hashes won't match.

print("-" * 70)
print("VERIFYING HASH CHAIN INTEGRITY")
print("-" * 70)
print()

chain_valid = True
for i, entry in enumerate(log):
    # Recompute the hash from the entry's current data
    expected_hash = compute_hash(entry)
    actual_hash = entry["entry_hash"]

    if expected_hash != actual_hash:
        print(f"  INTEGRITY FAILURE at entry {entry['entry_id']}")
        chain_valid = False
    else:
        print(f"  Entry {entry['entry_id']}: HASH VALID  [{actual_hash[:16]}...]")

    # Check chain link (skip first entry — it has no predecessor)
    if i > 0:
        expected_prev = log[i - 1]["entry_hash"]
        actual_prev = entry["prev_hash"]
        if expected_prev != actual_prev:
            print(f"    CHAIN BREAK: prev_hash does not match entry {i}")
            chain_valid = False

print()
if chain_valid:
    print("  CHAIN STATUS: ALL HASHES VALID. LOG INTEGRITY CONFIRMED.")
else:
    print("  CHAIN STATUS: INTEGRITY FAILURE DETECTED.")
print()


# =============================================================================
# CONCEPT 12: REUSABLE QUERY FUNCTION
# =============================================================================
# Instead of writing a loop every time, write a FUNCTION that does it for you.
# This is the jump from "I can write code" to "I can build tools."

def query_log(entries, category=None, tag=None, intent=None):
    """
    Filter log entries by category, tag, and/or intent.
    Returns a list of matching entries.

    Usage:
        results = query_log(log, category="financial")
        results = query_log(log, tag="chaos")
        results = query_log(log, category="system", tag="guardian-one")
    """
    results = []
    for entry in entries:
        # Start by assuming it matches
        matches = True

        # Check each filter — if provided and doesn't match, reject
        if category and entry["category"] != category:
            matches = False
        if tag and tag not in entry["tags"]:
            matches = False
        if intent and entry["intent"] != intent:
            matches = False

        if matches:
            results.append(entry)

    return results


# Demo the query function
print("-" * 70)
print("REUSABLE QUERY FUNCTION DEMO")
print("-" * 70)
print()

# Find all decisions
decisions = query_log(log, intent="decision")
print(f"  All decisions ({len(decisions)} found):")
for d in decisions:
    print(f"    [{d['entry_id']}] {d['summary']}")
print()

# Find everything tagged "guardian-one"
g1_entries = query_log(log, tag="guardian-one")
print(f"  Guardian One related ({len(g1_entries)} found):")
for g in g1_entries:
    print(f"    [{g['entry_id']}] {g['summary']}")
print()


# =============================================================================
# CONCEPT 13: ADDING A NEW ENTRY (Interactive)
# =============================================================================
# This section shows how you'd add entries going forward.
# Uncomment the lines below to try it interactively.
#
# To uncomment: remove the # at the start of each line.

# print("ADD A NEW ENTRY")
# print("-" * 40)
# summary = input("  Summary (one line): ")
# category = input("  Category (financial/medical_self/professional/system): ")
# context = input("  Context (why?): ")
# tags_input = input("  Tags (comma-separated): ")
# tags = [t.strip() for t in tags_input.split(",")]
#
# new_entry = create_entry(
#     entry_id=len(log) + 1,
#     category=category,
#     intent="decision",
#     summary=summary,
#     context=context,
#     tags=tags,
#     prev_hash=log[-1]["entry_hash"]  # log[-1] = last item in the list
# )
# log.append(new_entry)
# print(f"  Added entry {new_entry['entry_id']}: {new_entry['summary']}")


# =============================================================================
# FINAL OUTPUT
# =============================================================================
print("=" * 70)
print("LESSON COMPLETE")
print("=" * 70)
print()
print("WHAT YOU JUST LEARNED:")
print("  1. Variables       — storing values with names")
print("  2. Strings         — text in quotes")
print("  3. Dictionaries    — key:value pairs (the core of JSON)")
print("  4. Lists           — ordered collections")
print("  5. Functions       — reusable code blocks (def)")
print("  6. f-strings       — formatted text with {variables}")
print("  7. File I/O        — saving/loading JSON to disk")
print("  8. Loops           — for entry in log:")
print("  9. Conditions      — if/and/or logic")
print("  10. Hashing        — SHA-256 integrity verification")
print("  11. Query function — filtering data programmatically")
print()
print("FILES CREATED:")
print(f"  {LOG_FILE} — Your Guardian One log (open it in any text editor)")
print()
print("NEXT STEPS:")
print("  - Open guardian_one_log.json and read it. It's human-readable.")
print("  - Uncomment the interactive section (Concept 13) and add entries.")
print("  - Try breaking an entry (change a summary) and re-run to see")
print("    the hash chain catch the tampering.")
print("  - Lesson 2: Build a command-line interface for Guardian One.")
print()
print("=" * 70)
