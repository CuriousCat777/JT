"""
FETCHER — The Full Physical Exam
==================================
The search gave us vitals (title, snippet, URL).
Now we go deeper — actually visit each URL and pull the page content.

Think of it like going from a quick triage glance to a thorough physical:
  - Triage: "Patient reports chest pain" (the snippet)
  - Full exam: Listen to the heart, check labs, run EKG (the actual page)

The richer content feeds into the evaluator for better scoring.
"""

import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed


TIMEOUT = 10  # seconds per request
MAX_CONTENT_LENGTH = 5000  # characters to keep per page
MAX_WORKERS = 5  # parallel fetches

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Tags that contain navigation/boilerplate, not real content
NOISE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "noscript"]


def fetch_page(url):
    """
    Fetch a single URL and extract its text content.

    Returns the cleaned text (up to MAX_CONTENT_LENGTH chars),
    or None if the fetch fails for any reason.
    """
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Strip out noise — scripts, styles, navbars, footers
        for tag in soup(NOISE_TAGS):
            tag.decompose()

        # Extract visible text
        text = soup.get_text(separator=" ", strip=True)

        # Collapse whitespace runs into single spaces
        text = " ".join(text.split())

        # Truncate to keep storage reasonable
        return text[:MAX_CONTENT_LENGTH] if text else None

    except Exception:
        return None


def deep_fetch(results, max_workers=MAX_WORKERS):
    """
    Visit each result's URL and attach the full page content.

    Adds a 'page_content' field to each result dict:
      - String of extracted text if successful
      - None if the page couldn't be fetched

    Args:
        results: List of search result dicts (must have 'url' key).
        max_workers: How many pages to fetch in parallel.

    Returns:
        Number of pages successfully fetched.
    """
    fetched = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_result = {
            executor.submit(fetch_page, r["url"]): r
            for r in results
        }

        for future in as_completed(future_to_result):
            result = future_to_result[future]
            content = future.result()
            if content:
                result["page_content"] = content
                fetched += 1
            else:
                result["page_content"] = None

    return fetched
