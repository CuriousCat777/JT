"""
GUARDIAN — Main Program
========================
The attending physician running the whole case.

Program flow (exactly as you described it):
  1. Search internet for things associated with user named (x)
  2. Hold data in transient folder
  3. Copy and evaluate for relevance
  4. Relevant → Add to permanent record
  5. Not relevant → Delete
  6. End program

Usage:
  python -m src.main "John Smith"
  python -m src.main --demo              (uses sample data, no internet needed)
"""

import sys

from src.searcher import search_person
from src.sample_data import SAMPLE_RESULTS
from src.evaluator import evaluate_results
from src.storage import (
    save_to_transient,
    clear_transient,
    save_to_records,
)


def run(target_name, demo=False):
    """
    Execute the full Guardian workflow for a target name.
    """
    print("=" * 60)
    print(f"  GUARDIAN — Intelligence Gathering")
    print(f"  Target: {target_name}")
    if demo:
        print(f"  Mode:   DEMO (using sample data)")
    print("=" * 60)

    # ── STEP 1: Search (Intake) ─────────────────────────────────
    if demo:
        print(f"\n[1/5] Loading sample data for '{target_name}'...")
        results = SAMPLE_RESULTS
    else:
        print(f"\n[1/5] Searching the web for '{target_name}'...")
        results = search_person(target_name)
    print(f"      Found {len(results)} unique results.")

    if not results:
        print("\n  No results found. Exiting.")
        return

    # ── STEP 2: Hold in transient (Observation Room) ────────────
    print(f"\n[2/5] Storing raw results in transient folder...")
    transient_path = save_to_transient(target_name, results)
    print(f"      Saved to: {transient_path}")

    # ── STEP 3: Evaluate (Triage) ──────────────────────────────
    print(f"\n[3/5] Evaluating relevance of each result...")
    admitted, discharged = evaluate_results(results, target_name)
    print(f"      Admitted:    {len(admitted)} results (relevant)")
    print(f"      Discharged:  {len(discharged)} results (not relevant)")

    # Show top admitted results
    if admitted:
        print(f"\n      --- Top Results ---")
        for i, r in enumerate(admitted[:5], 1):
            score = r['relevance_score']
            print(f"      {i}. [{score}/100] {r['title'][:60]}")
            print(f"         {r['url']}")

    # ── STEP 4: Store relevant results (Admit to Records) ──────
    if admitted:
        print(f"\n[4/5] Saving {len(admitted)} results to permanent record...")
        record_path = save_to_records(target_name, admitted)
        print(f"      Record saved: {record_path}")
    else:
        print(f"\n[4/5] No results met the relevance threshold. Nothing to save.")

    # ── STEP 5: Clean up transient (Discharge) ─────────────────
    print(f"\n[5/5] Clearing transient data...")
    cleared = clear_transient()
    print(f"      Cleared {cleared} temporary file(s).")

    # ── DONE ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"  COMPLETE")
    print(f"  {len(admitted)} results saved to permanent record.")
    print(f"  {len(discharged)} results discarded.")
    print("=" * 60)


def main():
    """Entry point — get target name from args or prompt."""
    demo = "--demo" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--demo"]

    if args:
        target_name = " ".join(args)
    elif demo:
        target_name = "John Smith"
    else:
        print("GUARDIAN — Web Intelligence Gathering Tool")
        print("-" * 40)
        target_name = input("Enter target name: ").strip()

    if not target_name:
        print("Error: No name provided.")
        sys.exit(1)

    run(target_name, demo=demo)


if __name__ == "__main__":
    main()
