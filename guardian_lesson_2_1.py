"""
================================================================================
GUARDIAN ONE — PYTHON LESSON 2: Time, Export, and Backup
================================================================================

WHAT THIS BUILDS:
    Lesson 1 built the log engine. Now we make it smarter.
    After this lesson, your Guardian One can:
    - Query entries by date range ("show me everything from today")
    - Sort entries by any field
    - Export your log to CSV (opens in Excel)
    - Create timestamped backups
    - Handle errors gracefully

WHAT YOU'LL LEARN (13 new concepts):
    1.  Parsing strings into dates (datetime.strptime / fromisoformat)
    2.  Comparing dates (>, <, >=, <=)
    3.  try / except (error handling — your code doesn't crash)
    4.  List comprehensions (one-line filtering)
    5.  Sorting with key functions (lambda)
    6.  The csv module (writing spreadsheets)
    7.  shutil.copy (file backup)
    8.  String methods (.split, .strip, .lower, .replace, .startswith)
    9.  enumerate() (loop with index)
    10. Type checking (isinstance)
    11. Multiple return values (tuples)
    12. Default arguments and None handling
    13. os.path operations (exists, join, getsize, basename)

HOW TO RUN:
    Put this file in the SAME FOLDER as guardian_one_log.json
    Then: python guardian_lesson_2.py

PREREQUISITE: Lesson 1 completed. guardian_one_log.json exists.
================================================================================
"""

import json
import os
import sys
from datetime import datetime, timezone

# Where is this script? We look for the log in the same folder.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "guardian_one_log.json")

print("=" * 70)
print("GUARDIAN ONE — LESSON 2: Time, Export, and Backup")
print("=" * 70)
print()


# =============================================================================
# CONCEPT 1: TRY / EXCEPT (Error Handling)
# =============================================================================
# In Lesson 1, if something went wrong, the program crashed.
# try/except lets you CATCH errors and handle them gracefully.
#
# This is how professionals write code. You don't hope things work —
# you plan for what happens when they don't.
#
# Structure:
#   try:
#       # code that might fail
#   except SomeErrorType as e:
#       # what to do when it fails
#
# Think of it like clinical risk stratification:
#   Try the treatment. If adverse reaction, follow protocol.

print("--- CONCEPT 1: Error Handling (try / except) ---")
print()

# EXAMPLE 1: File not found
try:
    with open("nonexistent_file.json", "r") as f:
        data = json.load(f)
    print("This line never runs if the file doesn't exist")
except FileNotFoundError:
    print("  Caught FileNotFoundError — file doesn't exist, but we didn't crash.")

# EXAMPLE 2: Bad JSON
try:
    broken_json = '{"name": "Jeremy", BAD DATA}'
    parsed = json.loads(broken_json)
except json.JSONDecodeError as e:
    print(f"  Caught JSONDecodeError — invalid JSON at position {e.pos}")

# EXAMPLE 3: Multiple except blocks (most specific first)
try:
    number = int("not_a_number")
except ValueError:
    print("  Caught ValueError — 'not_a_number' can't become an integer")
except Exception as e:
    # This catches EVERYTHING else. Use as a safety net, not a habit.
    print(f"  Caught generic: {e}")

# EXAMPLE 4: finally (runs no matter what)
print()
print("  'finally' block always runs — good for cleanup:")
try:
    result = 10 / 2
    print(f"    10 / 2 = {result}")
except ZeroDivisionError:
    print("    Can't divide by zero")
finally:
    print("    (this always prints, success or failure)")

print()

# *** NOW LET'S USE IT FOR REAL ***
# Load the Guardian log with proper error handling:

def load_guardian_log(filepath):
    """
    Load Guardian One log with full error handling.
    Returns (entries, error_message). If error, entries is empty list.
    """
    # =========================================================================
    # CONCEPT 11: MULTIPLE RETURN VALUES (Tuples)
    # =========================================================================
    # A function can return multiple values separated by commas.
    # Python packs them into a TUPLE — an immutable sequence.
    #
    #   def example():
    #       return "hello", 42, True
    #
    #   a, b, c = example()  # "unpacking"
    #   # a = "hello", b = 42, c = True
    #
    # We use this pattern to return BOTH the data AND any error message.
    # This is cleaner than crashing or using global variables.

    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            doc = json.load(f)
        entries = doc.get("entries", [])
        return entries, None  # <-- two values: data, no error

    except FileNotFoundError:
        return [], f"File not found: {filepath}"

    except json.JSONDecodeError as e:
        return [], f"Invalid JSON at line {e.lineno}: {e.msg}"

    except PermissionError:
        return [], f"Permission denied: {filepath}"


print("--- Loading your Guardian One log ---")
entries, error = load_guardian_log(LOG_FILE)  # <-- unpacking the tuple

if error:
    print(f"  ERROR: {error}")
    print(f"  Make sure guardian_one_log.json is in: {SCRIPT_DIR}")
    print(f"  Run 'python guardian_system_2.py list' first to create it.")
    sys.exit(1)

print(f"  Loaded {len(entries)} entries from {os.path.basename(LOG_FILE)}")
print()


# =============================================================================
# CONCEPT 2: PARSING DATES (datetime.strptime / fromisoformat)
# =============================================================================
# Your Guardian entries have timestamps like "2026-02-23T17:20:16Z"
# That's a STRING. To compare dates, you need a datetime OBJECT.
#
# Two ways to parse:
#   datetime.strptime(string, format)    — works everywhere
#   datetime.fromisoformat(string)       — cleaner but pickier
#
# strptime format codes (the ones you'll actually use):
#   %Y = 4-digit year (2026)
#   %m = 2-digit month (02)
#   %d = 2-digit day (23)
#   %H = hour 24h (17)
#   %M = minute (20)
#   %S = second (16)
#
# Think of it like: you're telling Python the PATTERN of your date string.

print("--- CONCEPT 2: Parsing Dates ---")
print()

# Your timestamp format: "2026-02-23T17:20:16Z"
example_ts = "2026-02-23T17:20:16Z"

# Method 1: strptime (spell out the pattern)
parsed_1 = datetime.strptime(example_ts, "%Y-%m-%dT%H:%M:%SZ")
print(f"  Original string:  '{example_ts}'")
print(f"  Parsed (strptime): {parsed_1}")
print(f"  Type:              {type(parsed_1)}")

# Once parsed, you can pull out individual parts:
print(f"  Year:  {parsed_1.year}")
print(f"  Month: {parsed_1.month}")
print(f"  Day:   {parsed_1.day}")
print(f"  Hour:  {parsed_1.hour}")
print()

# Method 2: fromisoformat (cleaner, but needs the Z removed or replaced)
clean_ts = example_ts.replace("Z", "+00:00")
parsed_2 = datetime.fromisoformat(clean_ts)
print(f"  Parsed (fromisoformat): {parsed_2}")
print()

# Let's make a reusable function:
def parse_timestamp(ts_string):
    """
    Parse a Guardian One timestamp into a datetime object.
    Handles both '2026-02-23T17:20:16Z' and '2026-02-23' formats.
    Returns None if parsing fails (instead of crashing).
    """
    # =========================================================================
    # CONCEPT 12: DEFAULT ARGUMENTS AND NONE HANDLING
    # =========================================================================
    # Returning None when something fails is a Python convention.
    # The caller checks: if result is None, something went wrong.
    # This is gentler than raising an exception for expected failures.

    if not ts_string or not isinstance(ts_string, str):
        return None

    # =========================================================================
    # CONCEPT 8: STRING METHODS
    # =========================================================================
    # Strings in Python have dozens of built-in methods. Key ones:
    #
    #   .strip()       — remove whitespace from both ends
    #   .lower()       — convert to lowercase
    #   .upper()       — convert to uppercase
    #   .replace(a,b)  — replace all occurrences of a with b
    #   .split(sep)    — break string into a list
    #   .startswith(s) — does the string start with s?
    #   .endswith(s)   — does the string end with s?
    #   .find(s)       — position of s, or -1 if not found
    #
    # These are NON-DESTRUCTIVE — they return a new string.
    # The original is unchanged (strings are immutable).

    ts_string = ts_string.strip()

    try:
        # Full timestamp: "2026-02-23T17:20:16Z"
        if "T" in ts_string:
            clean = ts_string.replace("Z", "").replace("+00:00", "")
            return datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S")

        # Date only: "2026-02-23"
        if len(ts_string) == 10 and ts_string[4] == "-":
            return datetime.strptime(ts_string, "%Y-%m-%d")

        # Year-month: "2026-02"
        if len(ts_string) == 7 and ts_string[4] == "-":
            return datetime.strptime(ts_string, "%Y-%m")

        return None
    except ValueError:
        return None


# Test it with all formats:
print("  parse_timestamp tests:")
for test in ["2026-02-23T17:20:16Z", "2026-02-23", "2026-02", "bad input", "", None]:
    result = parse_timestamp(test)
    status = result.strftime("%Y-%m-%d %H:%M") if result else "None"
    print(f"    '{test}' -> {status}")
print()


# =============================================================================
# CONCEPT 3: COMPARING DATES
# =============================================================================
# Once you have datetime objects, you can compare them with > < >= <= == !=
# Just like numbers. This is incredibly powerful.
#
# Clinical analogy: "Is this lab value within normal range?"
# Same logic: "Is this entry within my date range?"

print("--- CONCEPT 3: Comparing Dates ---")
print()

date_a = parse_timestamp("2026-02-23T10:00:00Z")
date_b = parse_timestamp("2026-02-23T17:00:00Z")
date_c = parse_timestamp("2026-02-24T08:00:00Z")

print(f"  A = Feb 23 10:00")
print(f"  B = Feb 23 17:00")
print(f"  C = Feb 24 08:00")
print(f"  A < B? {date_a < date_b}")    # True — earlier in the day
print(f"  B < C? {date_b < date_c}")    # True — different day
print(f"  C < A? {date_c < date_a}")    # False
print(f"  A == A? {date_a == date_a}")   # True
print()


# =============================================================================
# CONCEPT 4: LIST COMPREHENSIONS
# =============================================================================
# A list comprehension builds a new list from an existing one in ONE LINE.
# It's the Python way to filter and transform data.
#
# Syntax:
#   [expression  for item in iterable  if condition]
#
# Which reads as:
#   "Give me [expression] for each [item] in [iterable] where [condition]"
#
# This replaces 4-5 lines of loop code with one clear line.
# Once you learn this, you'll use it constantly.

print("--- CONCEPT 4: List Comprehensions ---")
print()

# Simple example: square numbers 1-10
squares = [n * n for n in range(1, 11)]
print(f"  Squares: {squares}")

# Filter: only even squares
even_squares = [n * n for n in range(1, 11) if n % 2 == 0]
print(f"  Even squares: {even_squares}")

# Real use: get all tags from your Guardian log
all_tags = [tag for entry in entries for tag in entry.get("tags", [])]
print(f"  All tags in your log: {all_tags}")

# Unique tags (convert to set, then back to sorted list)
unique_tags = sorted(set(all_tags))
print(f"  Unique tags: {unique_tags}")

# Get just the summaries
summaries = [e.get("summary", "") for e in entries]
print(f"  Summaries:")
for s in summaries:
    print(f"    - {s}")
print()

# CRITICAL USE: Filter entries by category in ONE LINE
financial = [e for e in entries if e.get("category") == "financial"]
print(f"  Financial entries: {len(financial)}")

# Filter entries that mention 'Chaos' anywhere
chaos_entries = [e for e in entries if "chaos" in str(e).lower()]
print(f"  Entries mentioning Chaos: {len(chaos_entries)}")
print()


# =============================================================================
# CONCEPT 5: DATE RANGE QUERIES (combining concepts 1-4)
# =============================================================================
# Now we combine: parse dates, compare them, filter with comprehensions.
# This is the first real FEATURE we're building.

print("--- CONCEPT 5: Date Range Queries ---")
print()

def query_by_date(entries, after=None, before=None):
    """
    Filter entries by date range.

    Parameters:
        entries — list of Guardian entries
        after   — string like "2026-02-23" (entries AFTER this date)
        before  — string like "2026-02-24" (entries BEFORE this date)

    Returns:
        List of matching entries.

    This is how real database queries work:
        SELECT * FROM entries WHERE timestamp >= after AND timestamp <= before
    """
    after_dt = parse_timestamp(after) if after else None
    before_dt = parse_timestamp(before) if before else None

    # If before is a date only (no time), set it to end of that day
    # So "before 2026-02-23" means "up to 23:59:59 on Feb 23"
    if before_dt and before and len(before.strip()) == 10:
        before_dt = before_dt.replace(hour=23, minute=59, second=59)

    results = []
    for entry in entries:
        entry_dt = parse_timestamp(entry.get("timestamp", ""))
        if entry_dt is None:
            continue

        # Check bounds
        if after_dt and entry_dt < after_dt:
            continue
        if before_dt and entry_dt > before_dt:
            continue

        results.append(entry)

    return results


# Test: All entries from today (Feb 23, 2026)
todays = query_by_date(entries, after="2026-02-23", before="2026-02-23")
print(f"  Entries from Feb 23: {len(todays)}")
for e in todays:
    print(f"    [{e['entry_id']}] {e['category'].upper()} — {e['summary']}")
print()

# Could also do:
# last_week = query_by_date(entries, after="2026-02-16", before="2026-02-23")
# february = query_by_date(entries, after="2026-02-01", before="2026-02-28")


# =============================================================================
# CONCEPT 6: SORTING WITH KEY FUNCTIONS (lambda)
# =============================================================================
# Python's sorted() function can sort ANYTHING — you just tell it
# WHAT TO SORT BY using a key function.
#
# A LAMBDA is a tiny anonymous function. One line, no name.
#   lambda x: x["age"]     means "given x, return x's age"
#
# Clinical analogy:
#   "Sort these patients by acuity" — you're defining the sort KEY.

print("--- CONCEPT 6: Sorting ---")
print()

# Sort entries by entry_id (ascending — default)
by_id = sorted(entries, key=lambda e: e.get("entry_id", 0))
print("  Sorted by ID (ascending):")
for e in by_id:
    print(f"    [{e['entry_id']}] {e['summary'][:50]}")
print()

# Sort by timestamp (newest first — reverse=True)
by_time = sorted(entries, key=lambda e: e.get("timestamp", ""), reverse=True)
print("  Sorted by time (newest first):")
for e in by_time:
    print(f"    [{e['entry_id']}] {e['timestamp'][:10]} {e['summary'][:40]}")
print()

# Sort by category alphabetically
by_cat = sorted(entries, key=lambda e: e.get("category", ""))
print("  Sorted by category:")
for e in by_cat:
    print(f"    [{e['entry_id']}] {e['category']:<22} {e['summary'][:35]}")
print()


# =============================================================================
# CONCEPT 7: ENUMERATE (Loop with Index)
# =============================================================================
# enumerate() gives you BOTH the index AND the value in a loop.
# Instead of tracking a counter variable yourself.
#
#   for i, item in enumerate(my_list):
#       # i = 0, 1, 2, ...
#       # item = the actual value
#
# start=1 makes it count from 1 instead of 0.

print("--- CONCEPT 7: enumerate() ---")
print()

# Without enumerate (the old way):
print("  Without enumerate:")
count = 0
for e in entries[:3]:
    count += 1
    print(f"    {count}. {e['summary'][:50]}")

print()

# With enumerate (the Python way):
print("  With enumerate:")
for i, e in enumerate(entries[:3], start=1):
    print(f"    {i}. {e['summary'][:50]}")

print()


# =============================================================================
# CONCEPT 8: TYPE CHECKING (isinstance)
# =============================================================================
# Sometimes you need to check what TYPE a value is before using it.
#
#   isinstance(value, type)     returns True or False
#   isinstance(value, (t1,t2))  checks multiple types
#
# This prevents crashes when data is unexpected.
# Defensive coding — like checking allergies before prescribing.

print("--- CONCEPT 8: Type Checking ---")
print()

test_values = ["hello", 42, 3.14, True, None, [1,2], {"key": "val"}]

for val in test_values:
    if isinstance(val, str):
        label = "string"
    elif isinstance(val, bool):
        # IMPORTANT: check bool BEFORE int — bool is a subclass of int in Python!
        label = "boolean"
    elif isinstance(val, int):
        label = "integer"
    elif isinstance(val, float):
        label = "float"
    elif isinstance(val, list):
        label = "list"
    elif isinstance(val, dict):
        label = "dict"
    elif val is None:
        label = "None"
    else:
        label = "unknown"
    print(f"    {str(val):<20} -> {label}")

print()
print("  Why this matters: metadata values can be strings, numbers, or lists.")
print("  You need to handle each type differently when exporting to CSV.")
print()


# =============================================================================
# CONCEPT 9: THE CSV MODULE (Exporting to Spreadsheet)
# =============================================================================
# CSV = Comma Separated Values. Excel, Google Sheets, and every data tool reads it.
# Python's csv module handles the tricky parts: escaping commas, quoting, etc.
#
# This is your first EXPORT feature.

print("--- CONCEPT 9: CSV Export ---")
print()

import csv

def export_to_csv(entries, output_path):
    """
    Export Guardian entries to a CSV file that opens in Excel.

    Returns: (success: bool, message: str)
    """
    if not entries:
        return False, "No entries to export"

    # Define columns. We flatten the nested structure for spreadsheet use.
    columns = [
        "entry_id", "timestamp", "category", "intent",
        "summary", "context", "outcome", "confidence",
        "tags", "amount_usd", "entry_hash"
    ]

    try:
        # =====================================================================
        # NOTE: newline="" is REQUIRED for csv module on Windows.
        # Without it, you get blank lines between every row in Excel.
        # This is a classic Windows Python gotcha.
        # =====================================================================
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)

            # Write header row
            writer.writerow(columns)

            # Write data rows
            for entry in entries:
                # Tags: join list into a single string with semicolons
                tags = "; ".join(entry.get("tags", []))

                # Amount: pull from metadata (might not exist)
                meta = entry.get("metadata", {})
                amount = meta.get("amount_usd") or meta.get("cost_usd") or ""

                row = [
                    entry.get("entry_id", ""),
                    entry.get("timestamp", ""),
                    entry.get("category", ""),
                    entry.get("intent", ""),
                    entry.get("summary", ""),
                    entry.get("context", ""),
                    entry.get("outcome", ""),
                    entry.get("confidence", ""),
                    tags,
                    amount,
                    entry.get("entry_hash", "")[:16] + "..."
                ]
                writer.writerow(row)

        return True, f"Exported {len(entries)} entries to {output_path}"

    except PermissionError:
        return False, f"Cannot write to {output_path} — file may be open in Excel"
    except Exception as e:
        return False, f"Export failed: {e}"


# Run the export
csv_path = os.path.join(SCRIPT_DIR, "guardian_export.csv")
success, message = export_to_csv(entries, csv_path)
print(f"  {message}")
if success:
    # =========================================================================
    # CONCEPT 13: OS.PATH OPERATIONS
    # =========================================================================
    # os.path has everything you need for file paths:
    #   os.path.exists(p)    — does the file exist?
    #   os.path.getsize(p)   — file size in bytes
    #   os.path.basename(p)  — filename without directory
    #   os.path.dirname(p)   — directory without filename
    #   os.path.join(a, b)   — combine path parts (handles / vs \)
    #   os.path.splitext(p)  — split name and extension

    size = os.path.getsize(csv_path)
    name = os.path.basename(csv_path)
    print(f"  File: {name}")
    print(f"  Size: {size:,} bytes")
    print(f"  Path: {csv_path}")
    print()
    print(f"  TIP: Open this in Excel or Google Sheets:")
    print(f"    Double-click the file, or")
    print(f"    In Excel: File > Open > {name}")
print()


# =============================================================================
# CONCEPT 10: FILE BACKUP (shutil.copy)
# =============================================================================
# shutil = "shell utilities" — high-level file operations.
# shutil.copy(src, dst) copies a file. That's it.
#
# We timestamp the backup so you can have multiple versions.
# This is your first DATA PROTECTION feature.

print("--- CONCEPT 10: Timestamped Backup ---")
print()

import shutil

def backup_log(filepath):
    """
    Create a timestamped backup of the Guardian log.
    Example: guardian_one_log.json -> guardian_one_log_backup_20260223_172016.json

    Returns: (success: bool, backup_path_or_error: str)
    """
    if not os.path.exists(filepath):
        return False, "Nothing to backup — file doesn't exist"

    # Build backup filename with timestamp
    now = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Split "guardian_one_log.json" into ("guardian_one_log", ".json")
    name, ext = os.path.splitext(filepath)
    backup_path = f"{name}_backup_{now}{ext}"

    try:
        shutil.copy(filepath, backup_path)
        size = os.path.getsize(backup_path)
        return True, backup_path
    except PermissionError:
        return False, "Permission denied — close any programs using the file"
    except Exception as e:
        return False, str(e)


# Run the backup
success, result = backup_log(LOG_FILE)
if success:
    size = os.path.getsize(result)
    print(f"  Backup created: {os.path.basename(result)}")
    print(f"  Size: {size:,} bytes")
    print(f"  Path: {result}")
else:
    print(f"  Backup failed: {result}")
print()


# =============================================================================
# PUTTING IT ALL TOGETHER: Combined Query Engine
# =============================================================================
# This function uses EVERY concept from this lesson.
# It's a real, usable query engine for your Guardian log.

print("=" * 70)
print("  COMBINED DEMO: Advanced Query Engine")
print("=" * 70)
print()

def advanced_query(entries, category=None, tag=None, text=None,
                   after=None, before=None, sort_by="timestamp",
                   reverse=True, limit=None):
    """
    Query Guardian entries with multiple filters and sorting.

    Parameters:
        category  — filter by category (exact match)
        tag       — filter by tag (any match)
        text      — search in summary + context + outcome
        after     — entries after this date (string)
        before    — entries before this date (string)
        sort_by   — field to sort by ("timestamp", "entry_id", "category")
        reverse   — True = newest first
        limit     — max results to return (None = all)

    Returns:
        Filtered, sorted list of entries.
    """
    # Step 1: Start with all entries (list comprehension with complex filter)
    results = entries  # start with everything

    # Step 2: Apply filters (each one narrows the results)
    if category:
        results = [e for e in results
                   if e.get("category", "").lower() == category.lower()]

    if tag:
        results = [e for e in results
                   if tag.lower() in [t.lower() for t in e.get("tags", [])]]

    if text:
        results = [e for e in results
                   if text.lower() in " ".join([
                       str(e.get("summary", "")),
                       str(e.get("context", "")),
                       str(e.get("outcome", ""))
                   ]).lower()]

    if after or before:
        results = query_by_date(results, after=after, before=before)

    # Step 3: Sort
    results = sorted(results, key=lambda e: e.get(sort_by, ""), reverse=reverse)

    # Step 4: Limit
    if limit:
        results = results[:limit]

    return results


# Demo queries using YOUR real data:

print("  Query 1: All financial entries, newest first")
q1 = advanced_query(entries, category="financial")
for e in q1:
    print(f"    [{e['entry_id']}] {e['summary']}")
print()

print("  Query 2: Entries with tag 'overlord-guardian'")
q2 = advanced_query(entries, tag="overlord-guardian")
for e in q2:
    print(f"    [{e['entry_id']}] {e['category']}: {e['summary'][:50]}")
print()

print("  Query 3: Text search for 'Cloudflare'")
q3 = advanced_query(entries, text="cloudflare")
for e in q3:
    print(f"    [{e['entry_id']}] {e['summary']}")
print()

print("  Query 4: Everything from Feb 23, sorted by category")
q4 = advanced_query(entries, after="2026-02-23", sort_by="category", reverse=False)
for e in q4:
    print(f"    [{e['entry_id']}] {e['category']:<22} {e['summary'][:35]}")
print()

print("  Query 5: Latest 3 entries")
q5 = advanced_query(entries, sort_by="timestamp", reverse=True, limit=3)
for e in q5:
    print(f"    [{e['entry_id']}] {e['timestamp'][:10]} {e['summary'][:40]}")
print()


# =============================================================================
# HOMEWORK / CHALLENGES
# =============================================================================
print("=" * 70)
print("  CHALLENGES (try these to level up)")
print("=" * 70)
print()
print("  1. EASY: Change the CSV export to include more metadata fields.")
print("     Hint: Look at the 'columns' list in export_to_csv().")
print()
print("  2. MEDIUM: Write a function that finds entries with NO tags.")
print("     Hint: [e for e in entries if not e.get('tags')]")
print()
print("  3. MEDIUM: Add a 'cost' column to the CSV that pulls amount_usd")
print("     OR cost_usd from metadata (some entries have one, some the other).")
print()
print("  4. HARD: Write a function that detects duplicate entries")
print("     (same summary + same category + same date).")
print()
print("  5. HARD: Create a monthly spending summary that groups entries")
print("     by month and totals the amount_usd for each.")
print()
print()

# =============================================================================
# LESSON COMPLETE — SUMMARY
# =============================================================================
print("=" * 70)
print("  LESSON 2 COMPLETE")
print("=" * 70)
print()
print("  NEW CONCEPTS LEARNED:")
print("    1.  try/except       — your code doesn't crash anymore")
print("    2.  Date parsing     — strings become comparable dates")
print("    3.  Date comparison  — filter entries by time range")
print("    4.  List comprehensions — one-line filtering")
print("    5.  Sorting + lambda — sort anything by anything")
print("    6.  csv module       — export to spreadsheet")
print("    7.  shutil.copy      — automated backups")
print("    8.  String methods   — .strip(), .lower(), .replace(), etc.")
print("    9.  enumerate()      — loop with index")
print("    10. isinstance()     — type checking")
print("    11. Multiple returns — functions return (data, error)")
print("    12. None handling    — graceful defaults")
print("    13. os.path          — file paths done right")
print()
print("  FILES CREATED:")
print(f"    CSV Export: {csv_path}")
print(f"    Log Backup: {result if success else 'none'}")
print()
print("  YOUR GUARDIAN SYSTEM NOW HAS:")
print("    - Date range queries")
print("    - Advanced multi-filter search")
print("    - CSV export (opens in Excel)")
print("    - Timestamped backup")
print()
print("  NEXT: Lesson 3 — Classes, the Dashboard, and your first API.")
print()
