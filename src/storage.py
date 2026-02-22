"""
STORAGE — The Medical Records Department
==========================================
Manages two areas:

  1. TRANSIENT (data/transient/)
     The observation room. Data lands here first.
     Temporary. Gets cleared after each run.

  2. RECORDS (data/records/)
     The permanent medical chart. Append-only.
     Once data is admitted here, it stays.
     Each search target gets their own file.
"""

import json
import os
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSIENT_DIR = os.path.join(BASE_DIR, "data", "transient")
RECORDS_DIR = os.path.join(BASE_DIR, "data", "records")


def ensure_dirs():
    """Make sure both storage areas exist."""
    os.makedirs(TRANSIENT_DIR, exist_ok=True)
    os.makedirs(RECORDS_DIR, exist_ok=True)


# ─── TRANSIENT (Observation Room) ─────────────────────────────────────

def save_to_transient(name, results):
    """
    Drop raw search results into the observation room.
    This is temporary holding — not the permanent record.

    Returns the file path where data was saved.
    """
    ensure_dirs()
    safe_name = name.lower().replace(" ", "_")
    filename = f"{safe_name}_raw.json"
    filepath = os.path.join(TRANSIENT_DIR, filename)

    with open(filepath, "w") as f:
        json.dump({
            "target": name,
            "result_count": len(results),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "results": results,
        }, f, indent=2)

    return filepath


def load_from_transient(name):
    """Read raw results back from the observation room."""
    safe_name = name.lower().replace(" ", "_")
    filepath = os.path.join(TRANSIENT_DIR, f"{safe_name}_raw.json")

    if not os.path.exists(filepath):
        return None

    with open(filepath, "r") as f:
        return json.load(f)


def clear_transient():
    """
    Wipe the observation room clean.
    Called at the end of a run — transient data doesn't persist.
    """
    ensure_dirs()
    count = 0
    for filename in os.listdir(TRANSIENT_DIR):
        filepath = os.path.join(TRANSIENT_DIR, filename)
        if os.path.isfile(filepath) and filename != ".gitkeep":
            os.remove(filepath)
            count += 1
    return count


# ─── RECORDS (Permanent Chart — Append Only) ──────────────────────────

def save_to_records(name, evaluated_results):
    """
    Admit vetted data to the permanent record.

    This is APPEND-ONLY: if a record already exists for this person,
    new results are added alongside the old ones. Nothing is overwritten.

    Think of it like adding a new note to a patient's chart —
    you never erase previous notes.
    """
    ensure_dirs()
    safe_name = name.lower().replace(" ", "_")
    filepath = os.path.join(RECORDS_DIR, f"{safe_name}_record.json")

    # Load existing record if one exists (append-only)
    existing = {"target": name, "entries": []}
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            existing = json.load(f)

    # Create the new entry
    new_entry = {
        "added_at": datetime.now(timezone.utc).isoformat(),
        "result_count": len(evaluated_results),
        "results": evaluated_results,
    }

    existing["entries"].append(new_entry)

    with open(filepath, "w") as f:
        json.dump(existing, f, indent=2)

    return filepath


def load_record(name):
    """Read the permanent record for a person."""
    safe_name = name.lower().replace(" ", "_")
    filepath = os.path.join(RECORDS_DIR, f"{safe_name}_record.json")

    if not os.path.exists(filepath):
        return None

    with open(filepath, "r") as f:
        return json.load(f)
