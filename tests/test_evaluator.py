"""
TESTS — The Lab
================
"Check the labs before you treat."

These tests verify that our evaluator (triage nurse) is
scoring results correctly BEFORE we use it on real data.

Run with:  python -m pytest tests/
"""

from src.evaluator import score_result, evaluate_results


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
