"""
EVALUATOR — The Triage Nurse
==============================
Looks at each raw search result and asks:
  "Is this actually about the person we're looking for?"

Scores each result on relevance. High-scoring results get
admitted to the permanent record. Low-scoring results get
discharged (deleted).

Scoring criteria:
  - Does the title or snippet contain the target name?
  - Does it come from a known profile/professional site?
  - Is the snippet substantive (not just a generic page)?
"""

# Sites that typically contain real profile information
PROFILE_DOMAINS = [
    "linkedin.com",
    "github.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "researchgate.net",
    "scholar.google.com",
    "medium.com",
    "about.me",
]


def score_result(result, target_name):
    """
    Score a single search result for relevance to the target person.

    Returns a score from 0 to 100:
      - 70+  = Highly relevant  → Admit to records
      - 40-69 = Maybe relevant  → Flag for review
      - 0-39  = Probably junk   → Discharge (delete)

    Think of it like triage:
      70+ = "This patient needs to be seen NOW"
      40-69 = "Keep in observation, reassess"
      0-39  = "Discharge home"
    """
    score = 0
    title = result.get("title", "").lower()
    snippet = result.get("snippet", "").lower()
    url = result.get("url", "").lower()
    name_lower = target_name.lower()

    # --- Name presence (most important signal) ---
    name_parts = name_lower.split()

    # Full name appears in title — strong signal
    if name_lower in title:
        score += 35

    # Full name appears in snippet
    if name_lower in snippet:
        score += 25

    # Individual name parts appear (partial match)
    for part in name_parts:
        if len(part) > 2:  # Skip short words like "J." or "A."
            if part in title:
                score += 8
            if part in snippet:
                score += 5

    # --- Source quality ---
    for domain in PROFILE_DOMAINS:
        if domain in url:
            score += 15
            break

    # --- Content substance ---
    # Longer snippets tend to have more real content
    if len(snippet) > 200:
        score += 5
    if len(snippet) > 400:
        score += 5

    # Cap at 100
    return min(score, 100)


def evaluate_results(results, target_name, admit_threshold=40):
    """
    Run triage on all search results.

    Returns two lists:
      - admitted: Results scoring at or above the threshold (go to records)
      - discharged: Results below the threshold (get deleted)

    Args:
        results: List of raw search result dicts.
        target_name: The person we searched for.
        admit_threshold: Minimum score to be admitted (default 40).
    """
    admitted = []
    discharged = []

    for result in results:
        result_score = score_result(result, target_name)
        result["relevance_score"] = result_score

        if result_score >= admit_threshold:
            result["disposition"] = "admitted"
            admitted.append(result)
        else:
            result["disposition"] = "discharged"
            discharged.append(result)

    # Sort admitted by score (highest first — sickest patients first)
    admitted.sort(key=lambda r: r["relevance_score"], reverse=True)

    return admitted, discharged
