"""Web research tools for Guardian One's AI engine.

Provides internet search and page fetching so the AI can research
questions autonomously. Uses DuckDuckGo (no API key) and httpx.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# -- Tool definitions for Claude tool_use API ----------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "web_search",
        "description": (
            "Search the internet for current information. Use this when you need "
            "up-to-date facts, news, prices, research, or anything not in your "
            "training data. Returns top results with titles, URLs, and snippets."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Number of results to return (default 5, max 10).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_fetch",
        "description": (
            "Fetch and read the text content of a web page. Use this to get details "
            "from a specific URL found via web_search, or a URL the user provides. "
            "Returns the page text (HTML stripped), truncated to ~8000 chars."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL to fetch.",
                },
            },
            "required": ["url"],
        },
    },
]


# -- Tool implementations -----------------------------------------------------

def _search_via_ddgs(query: str, max_results: int) -> list[dict[str, str]] | None:
    """Try DuckDuckGo search via the ddgs/duckduckgo-search package."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return results if results else None
    except Exception:
        return None


def _search_via_html(query: str, max_results: int) -> list[dict[str, str]] | None:
    """Fallback: scrape DuckDuckGo HTML lite for search results."""
    try:
        import httpx
        from bs4 import BeautifulSoup

        resp = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (compatible; GuardianOne/1.0)"},
            timeout=10.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        results = []
        for item in soup.select(".result")[:max_results]:
            title_el = item.select_one(".result__a")
            snippet_el = item.select_one(".result__snippet")
            if title_el:
                results.append({
                    "title": title_el.get_text(strip=True),
                    "href": title_el.get("href", ""),
                    "body": snippet_el.get_text(strip=True) if snippet_el else "",
                })
        return results if results else None
    except Exception:
        return None


def _search_via_brave(query: str, max_results: int) -> list[dict[str, str]] | None:
    """Try Brave Search API if BRAVE_API_KEY is set."""
    import os
    api_key = os.environ.get("BRAVE_API_KEY", "")
    if not api_key:
        return None
    try:
        import httpx
        resp = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": max_results},
            headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for r in data.get("web", {}).get("results", [])[:max_results]:
            results.append({
                "title": r.get("title", ""),
                "href": r.get("url", ""),
                "body": r.get("description", ""),
            })
        return results if results else None
    except Exception:
        return None


def web_search(query: str, max_results: int = 5) -> str:
    """Search the internet. Tries multiple backends in order."""
    max_results = min(max(max_results, 1), 10)

    # Try each search backend
    results = (
        _search_via_brave(query, max_results)
        or _search_via_ddgs(query, max_results)
        or _search_via_html(query, max_results)
    )

    if not results:
        return f"No results found for: {query}"

    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "No title")
        url = r.get("href", r.get("link", ""))
        snippet = r.get("body", r.get("snippet", ""))
        lines.append(f"{i}. **{title}**\n   URL: {url}\n   {snippet}")

    return "\n\n".join(lines)


def web_fetch(url: str) -> str:
    """Fetch a web page and return its text content."""
    try:
        import httpx
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; GuardianOne/1.0)",
        }
        resp = httpx.get(url, headers=headers, timeout=15.0, follow_redirects=True)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove script/style/nav elements
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        # Collapse blank lines and truncate
        lines = [line for line in text.splitlines() if line.strip()]
        text = "\n".join(lines)

        if len(text) > 8000:
            text = text[:8000] + "\n\n[... truncated ...]"

        return text if text else "Page returned no readable text content."

    except ImportError:
        return "Error: beautifulsoup4 or httpx not installed."
    except Exception as exc:
        logger.error("Web fetch error: %s", exc)
        return f"Fetch error: {exc}"


# -- Dispatcher ----------------------------------------------------------------

TOOL_HANDLERS = {
    "web_search": web_search,
    "web_fetch": web_fetch,
}


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    """Execute a tool by name and return the result as a string."""
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return f"Unknown tool: {name}"
    try:
        return handler(**arguments)
    except Exception as exc:
        logger.error("Tool execution error (%s): %s", name, exc)
        return f"Tool error: {exc}"
