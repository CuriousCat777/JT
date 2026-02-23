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

    Smart dedup at ingest: results whose URLs already exist in prior
    entries are filtered out — unless the new version is richer
    (has page_content where old didn't, or a higher score).

    Returns (filepath, new_count, skipped_count).
    """
    ensure_dirs()
    safe_name = name.lower().replace(" ", "_")
    filepath = os.path.join(RECORDS_DIR, f"{safe_name}_record.json")

    # Load existing record if one exists (append-only)
    existing = {"target": name, "entries": []}
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            existing = json.load(f)

    # Build a lookup of best existing result per URL
    existing_by_url = {}
    for entry in existing.get("entries", []):
        for result in entry.get("results", []):
            url = result.get("url", "")
            if url in existing_by_url:
                existing_by_url[url] = _pick_best(existing_by_url[url], result)
            else:
                existing_by_url[url] = result

    # Filter: only keep results that are new or better than what we have
    new_results = []
    skipped = 0
    for result in evaluated_results:
        url = result.get("url", "")
        if url in existing_by_url:
            best = _pick_best(existing_by_url[url], result)
            if best is result:
                # New version is better — include it
                new_results.append(result)
            else:
                skipped += 1
        else:
            new_results.append(result)

    if new_results:
        new_entry = {
            "added_at": datetime.now(timezone.utc).isoformat(),
            "result_count": len(new_results),
            "results": new_results,
        }
        existing["entries"].append(new_entry)

        with open(filepath, "w") as f:
            json.dump(existing, f, indent=2)

    return filepath, len(new_results), skipped


def load_record(name):
    """Read the permanent record for a person."""
    safe_name = name.lower().replace(" ", "_")
    filepath = os.path.join(RECORDS_DIR, f"{safe_name}_record.json")

    if not os.path.exists(filepath):
        return None

    with open(filepath, "r") as f:
        return json.load(f)


# ─── DEDUP (Chart Reconciliation) ────────────────────────────────────

def _pick_best(existing, candidate):
    """
    Given two results for the same URL, pick the richer one.

    Priority:
      1. Has page_content beats doesn't
      2. Higher relevance_score wins
      3. More recent retrieved_at wins
    """
    ex_has_content = bool(existing.get("page_content"))
    ca_has_content = bool(candidate.get("page_content"))

    if ca_has_content and not ex_has_content:
        return candidate
    if ex_has_content and not ca_has_content:
        return existing

    ex_score = existing.get("relevance_score", 0)
    ca_score = candidate.get("relevance_score", 0)
    if ca_score > ex_score:
        return candidate
    if ex_score > ca_score:
        return existing

    # Tie-break: most recent
    if candidate.get("retrieved_at", "") > existing.get("retrieved_at", ""):
        return candidate
    return existing


def deduplicate_record(name):
    """
    Consolidate a patient's chart — merge all entries, keep the best
    version of each result (by URL), write back as a single entry.

    Like chart reconciliation: two charts for the same patient get
    merged into one clean record. No data is lost — the richest
    version of every finding is kept.

    Returns (unique_count, duplicate_count) or None if no record exists.
    """
    record = load_record(name)
    if not record or not record.get("entries"):
        return None

    # Collect all results across all entries, grouped by URL
    best_by_url = {}
    total_results = 0

    for entry in record["entries"]:
        for result in entry.get("results", []):
            total_results += 1
            url = result.get("url", "")
            if url in best_by_url:
                best_by_url[url] = _pick_best(best_by_url[url], result)
            else:
                best_by_url[url] = result

    unique_results = list(best_by_url.values())
    unique_results.sort(
        key=lambda r: r.get("relevance_score", 0), reverse=True
    )

    duplicate_count = total_results - len(unique_results)

    # Write back as a single consolidated entry
    ensure_dirs()
    safe_name = name.lower().replace(" ", "_")
    filepath = os.path.join(RECORDS_DIR, f"{safe_name}_record.json")

    consolidated = {
        "target": record["target"],
        "entries": [
            {
                "added_at": datetime.now(timezone.utc).isoformat(),
                "consolidated_from": len(record["entries"]),
                "result_count": len(unique_results),
                "results": unique_results,
            }
        ],
    }

    with open(filepath, "w") as f:
        json.dump(consolidated, f, indent=2)

    return len(unique_results), duplicate_count


def _get_existing_urls(record):
    """Collect all URLs already in a record's entries."""
    urls = set()
    for entry in record.get("entries", []):
        for result in entry.get("results", []):
            urls.add(result.get("url", ""))
    return urls
