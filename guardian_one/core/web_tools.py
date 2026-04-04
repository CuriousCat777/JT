"""Web research tools for Guardian One's AI engine.

Provides internet search and page fetching so the AI can research
questions autonomously. Uses DuckDuckGo (no API key) and httpx.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse
from typing import Any

logger = logging.getLogger(__name__)

# -- URL safety ----------------------------------------------------------------

_ALLOWED_SCHEMES = {"http", "https"}


def _is_safe_url(url: str) -> tuple[bool, str]:
    """Validate a URL against SSRF: scheme allowlist + block private/loopback IPs.

    Returns (safe, reason).
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Malformed URL"

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False, f"Blocked scheme: {parsed.scheme}"

    hostname = parsed.hostname
    if not hostname:
        return False, "No hostname in URL"

    # Block obvious localhost variants
    if hostname in ("localhost", "0.0.0.0", "127.0.0.1", "::1", "[::1]"):
        return False, "Blocked: localhost"

    # Resolve hostname and check all IPs
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for _family, _type, _proto, _canonname, sockaddr in infos:
            ip = ipaddress.ip_address(sockaddr[0])
            if not ip.is_global:
                return False, f"Blocked: non-global IP {ip}"
    except socket.gaierror:
        return False, f"Cannot resolve hostname: {hostname}"

    return True, ""

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


_MAX_FETCH_BYTES = 2 * 1024 * 1024  # 2 MB max download
_ALLOWED_PORTS = {80, 443, None}  # None = default port for scheme


def web_fetch(url: str) -> str:
    """Fetch a web page and return its text content.

    Security: validates URL scheme + DNS resolution against private IPs,
    resolves once to avoid TOCTOU/DNS-rebinding, limits response size,
    restricts ports to 80/443.
    """
    safe, reason = _is_safe_url(url)
    if not safe:
        return f"URL blocked: {reason}"

    try:
        import httpx
        from bs4 import BeautifulSoup

        parsed = urlparse(url)
        hostname = parsed.hostname or ""

        # Restrict ports to reduce SSRF surface
        if parsed.port not in _ALLOWED_PORTS:
            return f"URL blocked: non-standard port {parsed.port}"

        # Resolve hostname once for DNS-rebinding protection
        infos = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80),
                                   socket.AF_UNSPEC, socket.SOCK_STREAM)
        if not infos:
            return f"URL blocked: cannot resolve {hostname}"
        resolved_ip = infos[0][4][0]

        # Re-check the resolved IP (defence in depth)
        ip = ipaddress.ip_address(resolved_ip)
        if not ip.is_global:
            return f"URL blocked: non-global IP {ip}"

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; GuardianOne/1.0)",
        }

        if parsed.scheme == "http":
            # Rewrite plain HTTP to resolved IP to prevent DNS rebinding.
            headers["Host"] = hostname if not parsed.port else f"{hostname}:{parsed.port}"
            ip_netloc = f"[{resolved_ip}]" if ip.version == 6 else resolved_ip
            if parsed.port:
                ip_netloc = f"{ip_netloc}:{parsed.port}"
            fetch_url = parsed._replace(netloc=ip_netloc).geturl()
        else:
            # Keep original HTTPS hostname so TLS uses correct SNI and
            # certificate verification remains enabled.
            fetch_url = url

        with httpx.stream("GET", fetch_url, headers=headers, timeout=15.0,
                          follow_redirects=False, verify=True) as resp:
            resp.raise_for_status()

            # Stream with size limit
            chunks = []
            total = 0
            for chunk in resp.iter_bytes(chunk_size=8192):
                total += len(chunk)
                if total > _MAX_FETCH_BYTES:
                    break
                chunks.append(chunk)
            body = b"".join(chunks).decode("utf-8", errors="replace")

        soup = BeautifulSoup(body, "html.parser")

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
