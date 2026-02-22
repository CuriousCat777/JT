"""
SEARCHER — The Intake Department
=================================
Takes a person's name, searches the internet, and brings back raw results.
Think of this as the ambulance arriving with a patient:
  - You don't know what's relevant yet
  - You just gather everything available
  - Sorting happens later (evaluator.py)
"""

import json
import os
from datetime import datetime, timezone

from duckduckgo_search import DDGS


def search_person(name, max_results=20):
    """
    Search the internet for publicly available information about a person.

    Args:
        name: The person's name to search for.
        max_results: How many results to pull back (default 20).

    Returns:
        A list of result dicts, each containing:
          - title: Page title
          - url: Link to the source
          - snippet: Text preview from the page
          - source: Which search produced it
          - retrieved_at: Timestamp of when we grabbed it
    """
    results = []
    timestamp = datetime.now(timezone.utc).isoformat()

    # Run multiple search queries to cast a wider net
    queries = [
        name,                          # Broad search
        f'"{name}" profile',           # Exact-match profile search
        f'"{name}" linkedin OR github', # Professional presence
    ]

    with DDGS() as ddg:
        for query in queries:
            try:
                hits = ddg.text(query, max_results=max_results)
                for hit in hits:
                    results.append({
                        "title": hit.get("title", ""),
                        "url": hit.get("href", ""),
                        "snippet": hit.get("body", ""),
                        "source_query": query,
                        "retrieved_at": timestamp,
                    })
            except Exception as e:
                print(f"  [!] Search failed for query '{query}': {e}")

    # Remove duplicate URLs (keep the first occurrence)
    seen_urls = set()
    unique_results = []
    for r in results:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            unique_results.append(r)

    return unique_results
