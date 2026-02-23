"""
TESTS — The Lab
================
"Check the labs before you treat."

These tests verify that our evaluator (triage nurse) is
scoring results correctly BEFORE we use it on real data.

Run with:  python -m pytest tests/
"""

from src.evaluator import score_result, evaluate_results
from src.fetcher import fetch_page
from src.storage import _pick_best, save_to_records, load_record, deduplicate_record
import json
import os
import shutil


# ── Test: Full name in title should score high ────────────────────

def test_full_name_in_title_scores_high():
    """
    Like checking troponin on a chest pain patient.
    If the target's full name is in the page title,
    that's a strong positive — score should reflect it.
    """
    result = {
        "title": "John Smith - Software Engineer at Google",
        "snippet": "John Smith is a senior engineer based in Austin.",
        "url": "https://linkedin.com/in/johnsmith",
    }

    score = score_result(result, "John Smith")

    # Name in title (35) + name in snippet (25) + linkedin (15) = 75+
    assert score >= 70, f"Expected >= 70, got {score}"


# ── Test: No name match should score low ─────────────────────────

def test_no_name_match_scores_low():
    """
    Like running a full workup on someone and everything
    comes back normal — this result isn't our patient.
    """
    result = {
        "title": "Best Pizza Restaurants in Chicago",
        "snippet": "Check out the top 10 pizza spots downtown.",
        "url": "https://foodblog.com/pizza",
    }

    score = score_result(result, "John Smith")

    assert score < 40, f"Expected < 40, got {score}"


# ── Test: Evaluate splits into admitted and discharged ────────────

def test_evaluate_splits_correctly():
    """
    Triage should sort patients into two groups:
    those who need admission and those who can go home.
    """
    results = [
        {  # Should be admitted — strong match
            "title": "Jane Doe - LinkedIn Profile",
            "snippet": "Jane Doe is a product manager at Stripe.",
            "url": "https://linkedin.com/in/janedoe",
        },
        {  # Should be discharged — no match
            "title": "Weather forecast for Tuesday",
            "snippet": "Expect rain in the afternoon.",
            "url": "https://weather.com/forecast",
        },
    ]

    admitted, discharged = evaluate_results(results, "Jane Doe")

    assert len(admitted) == 1, f"Expected 1 admitted, got {len(admitted)}"
    assert len(discharged) == 1, f"Expected 1 discharged, got {len(discharged)}"
    assert admitted[0]["title"].startswith("Jane Doe")


# ── Test: Page content boosts score ───────────────────────────

def test_page_content_boosts_score():
    """
    The full physical exam (deep fetch) should reveal more about
    the patient than the initial triage glance (snippet alone).
    """
    result_without = {
        "title": "Some Profile Page",
        "snippet": "A short bio.",
        "url": "https://example.com/profile",
    }

    result_with = {
        "title": "Some Profile Page",
        "snippet": "A short bio.",
        "url": "https://example.com/profile",
        "page_content": "John Smith is a software engineer at Google "
                        "with expertise in distributed systems.",
    }

    score_without = score_result(result_without, "John Smith")
    score_with = score_result(result_with, "John Smith")

    assert score_with > score_without, (
        f"Page content should boost score: {score_with} vs {score_without}"
    )


# ── Test: Fetcher handles bad URL gracefully ──────────────────

def test_fetch_page_bad_url_returns_none():
    """
    If a page can't be reached, the fetcher should return None
    instead of crashing — like a patient who doesn't show up
    for their appointment. Note it, move on.
    """
    result = fetch_page("https://this-domain-does-not-exist-12345.fake/page")
    assert result is None


# ── Test: _pick_best keeps richer version ─────────────────────

def test_pick_best_prefers_page_content():
    """
    When two charts exist for the same patient, keep the one
    with more detailed notes (page_content).
    """
    old = {"url": "https://example.com", "relevance_score": 80}
    new = {"url": "https://example.com", "relevance_score": 80,
           "page_content": "Full page text here"}

    assert _pick_best(old, new) is new
    assert _pick_best(new, old) is new


def test_pick_best_prefers_higher_score():
    """Both have content — pick the higher score."""
    low = {"url": "https://example.com", "relevance_score": 60,
           "page_content": "Some text"}
    high = {"url": "https://example.com", "relevance_score": 90,
            "page_content": "Some text"}

    assert _pick_best(low, high) is high
    assert _pick_best(high, low) is high


# ── Test: save_to_records skips exact duplicates ──────────────

def test_save_to_records_skips_duplicates(tmp_path, monkeypatch):
    """
    If the same URL already exists in the record and the new
    version isn't richer, skip it — don't admit the same patient twice.
    """
    # Point storage at a temp directory
    monkeypatch.setattr("src.storage.RECORDS_DIR", str(tmp_path))

    results_run1 = [
        {"title": "Page A", "url": "https://a.com", "snippet": "A",
         "relevance_score": 80, "disposition": "admitted",
         "page_content": "Full content of A"},
    ]

    results_run2 = [
        {"title": "Page A", "url": "https://a.com", "snippet": "A",
         "relevance_score": 80, "disposition": "admitted",
         "page_content": "Full content of A"},
        {"title": "Page B", "url": "https://b.com", "snippet": "B",
         "relevance_score": 70, "disposition": "admitted"},
    ]

    # First run — both should be saved
    _, new1, skip1 = save_to_records("Test Person", results_run1)
    assert new1 == 1
    assert skip1 == 0

    # Second run — Page A is a dupe, Page B is new
    _, new2, skip2 = save_to_records("Test Person", results_run2)
    assert new2 == 1  # Only Page B
    assert skip2 == 1  # Page A skipped


# ── Test: deduplicate_record consolidates entries ─────────────

def test_deduplicate_record(tmp_path, monkeypatch):
    """
    Two chart entries with overlapping URLs should merge into
    one clean record, keeping the richer version of each.
    """
    monkeypatch.setattr("src.storage.RECORDS_DIR", str(tmp_path))

    # Write a record with 2 entries sharing the same URL
    record = {
        "target": "Test Person",
        "entries": [
            {
                "added_at": "2026-01-01T00:00:00+00:00",
                "result_count": 1,
                "results": [
                    {"title": "Page A", "url": "https://a.com",
                     "relevance_score": 80},
                ],
            },
            {
                "added_at": "2026-02-01T00:00:00+00:00",
                "result_count": 2,
                "results": [
                    {"title": "Page A", "url": "https://a.com",
                     "relevance_score": 80,
                     "page_content": "Rich content"},
                    {"title": "Page B", "url": "https://b.com",
                     "relevance_score": 70},
                ],
            },
        ],
    }

    filepath = tmp_path / "test_person_record.json"
    with open(filepath, "w") as f:
        json.dump(record, f)

    unique, dupes = deduplicate_record("Test Person")
    assert unique == 2   # A and B
    assert dupes == 1    # One duplicate of A removed

    # Verify the consolidated record keeps the richer version
    with open(filepath) as f:
        result = json.load(f)
    assert len(result["entries"]) == 1
    results = result["entries"][0]["results"]
    page_a = [r for r in results if r["url"] == "https://a.com"][0]
    assert page_a.get("page_content") == "Rich content"
