"""
================================================================================
GUARDIAN ONE — PYTHON LESSON 3: Classes, Objects, and Your First API Call
================================================================================

WHAT THIS BUILDS:
    Lessons 1-2 used functions and raw dictionaries. That works, but it gets
    messy as systems grow. This lesson wraps Guardian One in a CLASS —
    the core building block of professional Python.

    After this lesson, your Guardian One has:
    - A GuardianLog class (your log becomes an object with methods)
    - A GuardianEntry class (entries become smart objects, not dumb dicts)
    - Live API calls (fetch real data from the internet)
    - A formatted dashboard report
    - Command-line argument parsing

WHAT YOU'LL LEARN (13 new concepts):
    1.  Classes and __init__ (blueprints for objects)
    2.  self (how objects reference themselves)
    3.  Methods (functions that belong to a class)
    4.  Properties (@property — computed attributes)
    5.  __str__ and __repr__ (how objects describe themselves)
    6.  Class composition (objects containing objects)
    7.  Static methods (@staticmethod — no self needed)
    8.  HTTP requests with urllib (stdlib, no pip install)
    9.  JSON API consumption (parse live data)
    10. sys.argv deep dive (command-line argument parsing)
    11. String formatting (.format, f-strings, padding, alignment)
    12. Dataclass-style patterns (structured data without boilerplate)
    13. Building a text dashboard (formatted report output)

HOW TO RUN:
    Put this file in the SAME FOLDER as guardian_one_log.json
    Then: python guardian_lesson_3.py

PREREQUISITE: Lessons 1-2 completed. guardian_one_log.json exists.
================================================================================
"""

import json
import os
import sys
import hashlib
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "guardian_one_log.json")

print("=" * 70)
print("GUARDIAN ONE — LESSON 3: Classes, Objects, and APIs")
print("=" * 70)
print()


# =============================================================================
# CONCEPT 1: CLASSES AND __init__
# =============================================================================
# A CLASS is a blueprint for creating objects. An OBJECT is an instance
# of a class — a specific thing built from the blueprint.
#
# Clinical analogy:
#   - The class is a PROTOCOL (e.g., "Sepsis Bundle")
#   - Each patient you apply it to is an OBJECT (an instance)
#   - The protocol defines what steps exist (methods)
#   - Each patient has their own vitals and labs (attributes)
#
# Syntax:
#   class ClassName:
#       def __init__(self, param1, param2):
#           self.attribute = param1
#
# __init__ is the CONSTRUCTOR — it runs when you create a new object.
# Think of it as the admission orders: "When this patient arrives, do this."

print("--- CONCEPT 1: Classes and __init__ ---")
print()


class GuardianEntry:
    """
    Represents a single Guardian One log entry.
    Instead of passing raw dictionaries around, we now have
    a smart object that knows how to describe and validate itself.
    """

    # =========================================================================
    # CONCEPT 2: self
    # =========================================================================
    # 'self' refers to THE SPECIFIC OBJECT being created or used.
    # Every method in a class gets 'self' as its first parameter.
    #
    # When you write: entry = GuardianEntry(1, "financial", ...)
    # Python translates that to: GuardianEntry.__init__(entry, 1, "financial", ...)
    #                                                    ^^^^^ this becomes 'self'
    #
    # self.entry_id means "THIS entry's ID" — not some other entry's.
    # Like "this patient's blood pressure" vs. just "blood pressure."

    def __init__(self, entry_id, category, intent, summary,
                 context=None, outcome=None, confidence="high",
                 tags=None, metadata=None, timestamp=None,
                 prev_hash="GENESIS", entry_hash=None):
        """Create a new GuardianEntry."""
        self.entry_id = entry_id
        self.category = category
        self.intent = intent
        self.summary = summary
        self.context = context
        self.outcome = outcome
        self.confidence = confidence
        self.tags = tags or []          # if tags is None, use empty list
        self.metadata = metadata or {}
        self.prev_hash = prev_hash
        self.timestamp = timestamp or datetime.now(
            tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.entry_hash = entry_hash  # set first (may be None)

        # Compute hash on creation if not provided
        if not self.entry_hash:
            self.entry_hash = self._compute_hash()

    # =========================================================================
    # CONCEPT 3: METHODS
    # =========================================================================
    # A method is a function that belongs to a class. It operates on
    # the object's data using 'self'.
    #
    # Functions (Lesson 1):  compute_hash(entry_dict)  — takes data as input
    # Methods (Lesson 3):    entry.compute_hash()      — uses self's data
    #
    # The difference: methods KNOW which object they're working on.

    def _compute_hash(self):
        """Compute SHA-256 hash of this entry's data."""
        # Leading underscore _ means "private" — internal use only.
        # It's a convention, not enforced, but professionals follow it.
        data = self.to_dict()
        data.pop("entry_hash", None)
        raw = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self):
        """Convert this entry to a plain dictionary (for JSON saving)."""
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "category": self.category,
            "intent": self.intent,
            "summary": self.summary,
            "context": self.context,
            "outcome": self.outcome,
            "confidence": self.confidence,
            "references": [],
            "documents": [],
            "tags": self.tags,
            "metadata": self.metadata,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash
        }

    def verify(self):
        """Check if this entry's hash is still valid."""
        return self._compute_hash() == self.entry_hash

    def has_tag(self, tag):
        """Check if this entry has a specific tag (case-insensitive)."""
        return tag.lower() in [t.lower() for t in self.tags]

    def matches_text(self, search_term):
        """Check if search term appears in summary, context, or outcome."""
        haystack = " ".join([
            str(self.summary or ""),
            str(self.context or ""),
            str(self.outcome or "")
        ]).lower()
        return search_term.lower() in haystack

    # =========================================================================
    # CONCEPT 4: PROPERTIES (@property)
    # =========================================================================
    # A property looks like an attribute but is actually computed on access.
    # You read it like: entry.age_hours (no parentheses — it looks like data)
    # But internally it runs a function.
    #
    # This is perfect for values that depend on other data.
    # Like: a patient's "BMI" is computed from height and weight.

    @property
    def age_hours(self):
        """How many hours ago was this entry created?"""
        try:
            created = datetime.strptime(
                self.timestamp.replace("Z", ""),
                "%Y-%m-%dT%H:%M:%S"
            )
            now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
            delta = now - created
            return round(delta.total_seconds() / 3600, 1)
        except (ValueError, AttributeError):
            return 0.0

    @property
    def cost(self):
        """Pull cost from metadata (amount_usd or cost_usd), or 0."""
        return float(
            self.metadata.get("amount_usd")
            or self.metadata.get("cost_usd")
            or 0
        )

    @property
    def hash_short(self):
        """First 12 characters of the hash."""
        return self.entry_hash[:12] + "..." if self.entry_hash else "none"

    # =========================================================================
    # CONCEPT 5: __str__ AND __repr__
    # =========================================================================
    # __str__  — human-readable description. Used by print().
    # __repr__ — technical description. Used by debuggers and logs.
    #
    # Without these, print(entry) shows: <GuardianEntry object at 0x7f...>
    # With them, print(entry) shows something useful.
    #
    # Rule of thumb:
    #   __str__  = what you'd tell a colleague
    #   __repr__ = what you'd put in a chart note

    def __str__(self):
        """Human-readable: what you see when you print(entry)."""
        return f"[{self.entry_id}] {self.category.upper()} — {self.summary}"

    def __repr__(self):
        """Technical: what you see in debugger or logs."""
        return (f"GuardianEntry(id={self.entry_id}, "
                f"cat='{self.category}', hash='{self.hash_short}')")


# --- DEMO: Using the class ---

print("  Creating a GuardianEntry object:")
demo_entry = GuardianEntry(
    entry_id=99,
    category="system",
    intent="observation",
    summary="Lesson 3 demo entry — testing class creation.",
    context="Built during Python Lesson 3.",
    tags=["lesson-3", "demo", "class-test"]
)

# __str__ in action:
print(f"  print(entry):  {demo_entry}")

# __repr__ in action:
print(f"  repr(entry):   {repr(demo_entry)}")

# Properties:
print(f"  entry.cost:       ${demo_entry.cost:.2f}")
print(f"  entry.age_hours:  {demo_entry.age_hours}h")
print(f"  entry.hash_short: {demo_entry.hash_short}")

# Methods:
print(f"  entry.verify():       {demo_entry.verify()}")
print(f"  entry.has_tag('demo'): {demo_entry.has_tag('demo')}")
print(f"  entry.has_tag('xyz'):  {demo_entry.has_tag('xyz')}")
print(f"  entry.matches_text('lesson'): {demo_entry.matches_text('lesson')}")
print()


# =============================================================================
# CONCEPT 6: CLASS COMPOSITION (Objects containing Objects)
# =============================================================================
# Composition = one class CONTAINS instances of another class.
# GuardianLog contains a LIST of GuardianEntry objects.
#
# This is how real systems are built:
#   Hospital contains Departments
#   Department contains Providers
#   Provider contains Patients
#   Patient contains Encounters
#
# Each level knows how to manage its own data.

print("--- CONCEPT 6: Class Composition (GuardianLog) ---")
print()


class GuardianLog:
    """
    The full Guardian One log — a collection of entries with
    methods for querying, exporting, and analysis.
    """

    def __init__(self, filepath=None):
        """Load log from file, or start empty."""
        self.filepath = filepath
        self.entries = []     # list of GuardianEntry objects
        self.version = "0.2.2"
        self.owner = "Jeremy Tabernero, MD"

        if filepath and os.path.exists(filepath):
            self._load_from_file(filepath)

    def _load_from_file(self, filepath):
        """Load entries from JSON and convert to GuardianEntry objects."""
        try:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                doc = json.load(f)
            raw_entries = doc.get("entries", [])
            for raw in raw_entries:
                entry = GuardianEntry(
                    entry_id=raw.get("entry_id", 0),
                    category=raw.get("category", "system"),
                    intent=raw.get("intent", "observation"),
                    summary=raw.get("summary", ""),
                    context=raw.get("context"),
                    outcome=raw.get("outcome"),
                    confidence=raw.get("confidence", "high"),
                    tags=raw.get("tags", []),
                    metadata=raw.get("metadata", {}),
                    timestamp=raw.get("timestamp"),
                    prev_hash=raw.get("prev_hash", "GENESIS"),
                    entry_hash=raw.get("entry_hash")
                )
                self.entries.append(entry)
        except (json.JSONDecodeError, PermissionError) as e:
            print(f"  Error loading log: {e}")

    # =========================================================================
    # CONCEPT 7: STATIC METHODS (@staticmethod)
    # =========================================================================
    # A static method belongs to the class but doesn't use 'self'.
    # It doesn't need a specific object — it's a utility function
    # that logically belongs with the class.
    #
    # Like: a hospital protocol for "How to calculate BMI" doesn't
    # need a specific patient. It's a formula that belongs to the
    # clinical domain.

    @staticmethod
    def format_currency(amount):
        """Format a number as USD currency string."""
        if amount == 0:
            return "$0.00"
        return f"${amount:,.2f}"

    # --- Query Methods ---

    def filter_by_category(self, category):
        """Return entries matching a category."""
        return [e for e in self.entries
                if e.category.lower() == category.lower()]

    def filter_by_tag(self, tag):
        """Return entries that have a specific tag."""
        return [e for e in self.entries if e.has_tag(tag)]

    def search(self, text):
        """Return entries matching a text search."""
        return [e for e in self.entries if e.matches_text(text)]

    def filter_by_date(self, after=None, before=None):
        """Return entries within a date range."""
        results = []
        for entry in self.entries:
            try:
                ts = entry.timestamp.replace("Z", "")
                entry_dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
            except (ValueError, AttributeError):
                continue

            if after:
                after_dt = datetime.strptime(after, "%Y-%m-%d")
                if entry_dt < after_dt:
                    continue
            if before:
                before_dt = datetime.strptime(before, "%Y-%m-%d")
                before_dt = before_dt.replace(hour=23, minute=59, second=59)
                if entry_dt > before_dt:
                    continue

            results.append(entry)
        return results

    # --- Analysis Properties ---

    @property
    def count(self):
        """Total number of entries."""
        return len(self.entries)

    @property
    def total_spending(self):
        """Sum of all non-correction entry costs."""
        return sum(e.cost for e in self.entries
                   if e.category != "correction")

    @property
    def categories(self):
        """Dict of category -> count."""
        cats = {}
        for e in self.entries:
            cats[e.category] = cats.get(e.category, 0) + 1
        return dict(sorted(cats.items(), key=lambda x: -x[1]))

    @property
    def all_tags(self):
        """Sorted list of unique tags."""
        tags = set()
        for e in self.entries:
            tags.update(t.lower() for t in e.tags)
        return sorted(tags)

    def verify_chain(self):
        """Verify hash integrity of all entries. Returns (valid, failures)."""
        failures = []
        for i, entry in enumerate(self.entries):
            if not entry.verify():
                failures.append(entry.entry_id)
        return len(failures) == 0, failures

    # =========================================================================
    # __str__ for the log itself
    # =========================================================================

    def __str__(self):
        return f"GuardianLog({self.count} entries, {self.format_currency(self.total_spending)} tracked)"

    def __repr__(self):
        return f"GuardianLog(entries={self.count}, file='{self.filepath}')"


# --- DEMO: Load your real log as a class ---

log = GuardianLog(LOG_FILE)

if log.count == 0:
    print("  No entries found. Run 'python guardian_system_2.py list' first.")
    sys.exit(1)

print(f"  Loaded: {log}")
print(f"  repr:   {repr(log)}")
print()

# Now instead of raw dict operations, we use METHODS:
print("  Financial entries:")
for e in log.filter_by_category("financial"):
    print(f"    {e}")    # __str__ makes this clean

print()
print("  Entries tagged 'overlord-guardian':")
for e in log.filter_by_tag("overlord-guardian"):
    print(f"    {e}")

print()
valid, failures = log.verify_chain()
print(f"  Chain integrity: {'VALID' if valid else 'BROKEN at entries ' + str(failures)}")
print(f"  Total spending:  {log.format_currency(log.total_spending)}")
print(f"  Categories:      {log.categories}")
print(f"  Unique tags:     {len(log.all_tags)}")
print()


# =============================================================================
# CONCEPT 8: HTTP REQUESTS (urllib — standard library)
# =============================================================================
# urllib is Python's built-in way to fetch data from the internet.
# No pip install needed. It's verbose compared to 'requests' library,
# but it works everywhere with zero dependencies.
#
# Structure:
#   urllib.request.urlopen(url)  — opens a connection
#   response.read()              — gets the raw bytes
#   .decode("utf-8")             — converts bytes to string
#
# This is how your Guardian system will eventually pull:
#   - Market data for financial tracking
#   - API status checks
#   - Live healthcare AI news

print("--- CONCEPT 8: HTTP Requests (urllib) ---")
print()

import urllib.request
import urllib.error

def fetch_url(url, timeout=10):
    """
    Fetch content from a URL. Returns (data_string, error_string).
    Uses tuple return pattern from Lesson 2.
    """
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "GuardianOne/0.2.2"
        })
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read().decode("utf-8")
            return data, None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return None, f"Connection failed: {e.reason}"
    except Exception as e:
        return None, str(e)


# Let's fetch a REAL public API — no API key needed
# This gets the current UTC time from a world time API

print("  Fetching live data from the internet...")
data, error = fetch_url("https://worldtimeapi.org/api/timezone/America/Chicago")

if error:
    print(f"  Network request failed: {error}")
    print("  (This is fine — you might be offline. The lesson continues.)")
    live_time = None
else:
    # =========================================================================
    # CONCEPT 9: JSON API CONSUMPTION
    # =========================================================================
    # Most APIs return JSON. You already know JSON from Lesson 1.
    # The workflow is always:
    #   1. Fetch the raw text from URL
    #   2. Parse it with json.loads() (loads = load from string)
    #   3. Navigate the resulting dictionary
    #
    # This is the foundation of ALL API integrations.

    try:
        time_data = json.loads(data)
        live_time = time_data.get("datetime", "unknown")
        tz = time_data.get("timezone", "unknown")
        print(f"  API Response (worldtimeapi.org):")
        print(f"    Your timezone:  {tz}")
        print(f"    Current time:   {live_time}")
        print(f"    Day of week:    {time_data.get('day_of_week', '?')}")
        print(f"    Week number:    {time_data.get('week_number', '?')}")
    except json.JSONDecodeError:
        print("  Got response but couldn't parse JSON.")
        live_time = None

print()

# Second API call — fetch a random piece of advice (fun demo)
print("  Fetching random advice...")
data2, error2 = fetch_url("https://api.adviceslip.com/advice")
if not error2:
    try:
        advice = json.loads(data2)
        print(f"  Random advice: \"{advice['slip']['advice']}\"")
    except (json.JSONDecodeError, KeyError):
        print("  Couldn't parse advice API.")
else:
    print(f"  Advice API unavailable: {error2}")
print()


# =============================================================================
# CONCEPT 10: sys.argv DEEP DIVE (Command-Line Arguments)
# =============================================================================
# sys.argv is a LIST of strings passed from the command line.
#
#   python script.py hello world 42
#   sys.argv = ["script.py", "hello", "world", "42"]
#                  [0]          [1]      [2]     [3]
#
# This is how guardian_system.py knows you typed "list" or "query".
# EVERYTHING in argv is a STRING — even numbers. You must convert.

print("--- CONCEPT 10: Command-Line Arguments ---")
print()

print(f"  sys.argv = {sys.argv}")
print(f"  Script name: {sys.argv[0]}")
print(f"  Arguments: {sys.argv[1:]}")
print()

# Pattern: Parse named arguments
def parse_args(argv):
    """
    Parse command-line arguments into a dictionary.
    Example: --name Jeremy --age 33 -> {"name": "Jeremy", "age": "33"}
    """
    args = {}
    i = 1  # skip script name
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv):
            key = argv[i][2:]       # strip the --
            value = argv[i + 1]
            args[key] = value
            i += 2
        else:
            # Positional argument (no --)
            args.setdefault("_positional", []).append(argv[i])
            i += 1
    return args

# Demo with fake argv:
fake_argv = ["script.py", "query", "--category", "financial", "--tag", "hardware"]
parsed = parse_args(fake_argv)
print(f"  Fake argv: {fake_argv}")
print(f"  Parsed:    {parsed}")
print()


# =============================================================================
# CONCEPT 11: STRING FORMATTING (Advanced)
# =============================================================================
# You know f-strings from Lesson 1. Here's the advanced version.
#
# Alignment and padding:
#   f"{'text':<20}"   — left-align in 20 chars
#   f"{'text':>20}"   — right-align in 20 chars
#   f"{'text':^20}"   — center in 20 chars
#   f"{42:05d}"        — pad with zeros: "00042"
#   f"{3.14:.2f}"      — 2 decimal places
#   f"{1234567:,}"     — comma separator: "1,234,567"
#
# This is what makes dashboard output look professional.

print("--- CONCEPT 11: String Formatting ---")
print()

# Alignment demo
items = [
    ("ROG Strix Laptop", 2149.00, "financial"),
    ("Cloudflare Domain", 10.46, "professional"),
    ("Chaos Vet Visit", 0.00, "medical"),
]

print(f"  {'ITEM':<25} {'COST':>10} {'CATEGORY':>15}")
print(f"  {'-'*25} {'-'*10} {'-'*15}")
for name, cost, cat in items:
    print(f"  {name:<25} {cost:>10,.2f} {cat:>15}")
print()

# Number formatting
big_number = 10000000
print(f"  Plain:     {big_number}")
print(f"  Commas:    {big_number:,}")
print(f"  Currency:  ${big_number:,.2f}")
print(f"  Padded:    {big_number:015,}")  # 15 chars, zero-padded
print(f"  Sci:       {big_number:.2e}")   # scientific notation
print()


# =============================================================================
# CONCEPT 12 & 13: BUILDING A TEXT DASHBOARD
# =============================================================================
# Combining everything: classes + formatting + data analysis
# into a professional dashboard report.
#
# This is what Guardian One will eventually display.

print("=" * 70)
print("  GUARDIAN ONE — SYSTEM DASHBOARD")
print("=" * 70)
print()

def build_dashboard(log):
    """
    Generate a formatted text dashboard from a GuardianLog.
    This is a preview of what a full TUI/web dashboard would show.
    """
    width = 66

    # --- Header ---
    print(f"  {'OWNER':<15} {log.owner}")
    print(f"  {'ENTRIES':<15} {log.count}")
    print(f"  {'SPENDING':<15} {log.format_currency(log.total_spending)}")

    valid, failures = log.verify_chain()
    status = "INTACT" if valid else f"BROKEN ({len(failures)} failures)"
    print(f"  {'CHAIN':<15} {status}")
    print(f"  {'VERSION':<15} {log.version}")
    print()

    # --- Category Breakdown ---
    print(f"  {'CATEGORIES':=^{width}}")
    print()
    cats = log.categories
    max_count = max(cats.values()) if cats else 1
    for cat, count in cats.items():
        bar_len = int((count / max_count) * 30)
        bar = "#" * bar_len
        print(f"  {cat:<22} {bar:<30} {count}")
    print()

    # --- Recent Entries ---
    print(f"  {'RECENT ENTRIES':=^{width}}")
    print()
    recent = sorted(log.entries, key=lambda e: e.timestamp, reverse=True)[:5]
    for entry in recent:
        cost_str = f"  {log.format_currency(entry.cost)}" if entry.cost > 0 else ""
        age = f"{entry.age_hours:.0f}h ago"
        print(f"  [{entry.entry_id:>2}] {entry.category:<20} {entry.summary[:30]:<30} {age}{cost_str}")
    print()

    # --- Tag Cloud ---
    print(f"  {'TOP TAGS':=^{width}}")
    print()
    tag_counts = {}
    for e in log.entries:
        for t in e.tags:
            tag_counts[t.lower()] = tag_counts.get(t.lower(), 0) + 1
    top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:12]

    # Print tags in rows of 4
    row = []
    for tag, count in top_tags:
        row.append(f"#{tag}({count})")
        if len(row) == 4:
            print(f"  {'  '.join(f'{t:<18}' for t in row)}")
            row = []
    if row:
        print(f"  {'  '.join(f'{t:<18}' for t in row)}")
    print()

    # --- Spending Summary ---
    spending_entries = [e for e in log.entries
                       if e.cost > 0 and e.category != "correction"]
    if spending_entries:
        print(f"  {'SPENDING LEDGER':=^{width}}")
        print()
        print(f"  {'ID':<5} {'DATE':<12} {'DESCRIPTION':<30} {'AMOUNT':>10}")
        print(f"  {'-'*5} {'-'*12} {'-'*30} {'-'*10}")
        for e in spending_entries:
            date = e.timestamp[:10]
            desc = e.summary[:30]
            print(f"  {e.entry_id:<5} {date:<12} {desc:<30} {log.format_currency(e.cost):>10}")
        print(f"  {'':5} {'':12} {'TOTAL':<30} {log.format_currency(log.total_spending):>10}")
        print()

    # --- Integrity Report ---
    print(f"  {'HASH CHAIN':=^{width}}")
    print()
    for entry in log.entries:
        icon = "+" if entry.verify() else "X"
        print(f"  {icon} [{entry.entry_id:>2}] {entry.hash_short}")
    print()
    if valid:
        print(f"  ALL {log.count} ENTRIES VERIFIED. CHAIN INTACT.")
    else:
        print(f"  WARNING: {len(failures)} HASH FAILURES DETECTED.")
    print()


# Run the dashboard
build_dashboard(log)


# =============================================================================
# HOMEWORK / CHALLENGES
# =============================================================================
print("=" * 70)
print("  CHALLENGES")
print("=" * 70)
print()
print("  1. EASY: Add a method to GuardianEntry called 'is_expensive()'")
print("     that returns True if cost > $500.")
print()
print("  2. MEDIUM: Add a 'filter_by_cost(min, max)' method to GuardianLog")
print("     that returns entries with cost in the given range.")
print()
print("  3. MEDIUM: Modify fetch_url() to cache responses — if the same")
print("     URL was fetched in the last 5 minutes, return the cached version.")
print()
print("  4. HARD: Build a second API call that fetches Bitcoin price from")
print("     a public API and adds it to the dashboard.")
print()
print("  5. HARD: Make the dashboard show a spending trend — if this month's")
print("     spending is higher than last month, show an UP arrow.")
print()
print()

# =============================================================================
# LESSON COMPLETE
# =============================================================================
print("=" * 70)
print("  LESSON 3 COMPLETE")
print("=" * 70)
print()
print("  NEW CONCEPTS:")
print("    1.  Classes + __init__    — blueprints for objects")
print("    2.  self                  — object self-reference")
print("    3.  Methods               — functions on objects")
print("    4.  @property             — computed attributes")
print("    5.  __str__ / __repr__    — object descriptions")
print("    6.  Class composition     — objects inside objects")
print("    7.  @staticmethod         — class utilities")
print("    8.  urllib HTTP requests   — fetch from the internet")
print("    9.  JSON API consumption   — parse live data")
print("    10. sys.argv parsing       — command-line arguments")
print("    11. String formatting      — aligned, padded output")
print("    12. Dataclass patterns     — structured data objects")
print("    13. Text dashboard         — formatted reports")
print()
print("  TOTAL CONCEPTS ACROSS 3 LESSONS: 39")
print()
print("  YOUR GUARDIAN ONE NOW HAS:")
print("    Lesson 1: Log engine, entries, hash chain, file I/O")
print("    Lesson 2: Date queries, CSV export, backup, sorting")
print("    Lesson 3: OOP structure, live API calls, dashboard")
print()
print("  NEXT: Lesson 4 — Web server, HTML dashboard, real-time updates.")
print()
