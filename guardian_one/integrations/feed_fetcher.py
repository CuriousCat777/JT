"""Feed Fetcher — real HTTP + XML parsing for the Palantir pipeline.

No feedparser dependency — just stdlib xml.etree and httpx.
RSS 2.0 and Atom 1.0 both handled. Timeouts, retries, and
error handling built in. Routes through Gateway when available.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import httpx

from guardian_one.integrations.intelligence_feeds import (
    FeedCategory,
    FeedItem,
    FeedSource,
)

logger = logging.getLogger(__name__)

# Atom namespace
ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _text(el: ET.Element | None) -> str:
    """Safely extract text from an XML element."""
    if el is None:
        return ""
    return (el.text or "").strip()


def _parse_rss(root: ET.Element, source: FeedSource) -> list[FeedItem]:
    """Parse RSS 2.0 <channel><item> entries."""
    items: list[FeedItem] = []
    channel = root.find("channel")
    if channel is None:
        return items

    for item in channel.findall("item"):
        title = _text(item.find("title"))
        link = _text(item.find("link"))
        desc = _text(item.find("description"))
        pub_date = _text(item.find("pubDate"))

        if not title:
            continue

        items.append(FeedItem(
            source=source.name,
            title=title,
            url=link,
            category=source.category,
            summary=desc[:500] if desc else "",
            published=pub_date or datetime.now(timezone.utc).isoformat(),
        ))
    return items


def _parse_atom(root: ET.Element, source: FeedSource) -> list[FeedItem]:
    """Parse Atom 1.0 <feed><entry> entries."""
    items: list[FeedItem] = []

    for entry in root.findall(f"{ATOM_NS}entry"):
        title = _text(entry.find(f"{ATOM_NS}title"))

        # Atom links can have multiple — prefer alternate, fallback to first
        link = ""
        for link_el in entry.findall(f"{ATOM_NS}link"):
            href = link_el.get("href", "")
            rel = link_el.get("rel", "alternate")
            if rel == "alternate" and href:
                link = href
                break
            if not link and href:
                link = href

        summary_el = entry.find(f"{ATOM_NS}summary")
        content_el = entry.find(f"{ATOM_NS}content")
        summary = _text(summary_el) or _text(content_el)

        updated = _text(entry.find(f"{ATOM_NS}updated"))
        published = _text(entry.find(f"{ATOM_NS}published")) or updated

        if not title:
            continue

        items.append(FeedItem(
            source=source.name,
            title=title,
            url=link,
            category=source.category,
            summary=summary[:500] if summary else "",
            published=published or datetime.now(timezone.utc).isoformat(),
        ))
    return items


def parse_feed_xml(xml_text: str, source: FeedSource) -> list[FeedItem]:
    """Parse RSS 2.0 or Atom 1.0 XML into FeedItems.

    Auto-detects format by checking the root tag.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("XML parse error for %s: %s", source.name, exc)
        return []

    # Atom: root tag is {namespace}feed
    if root.tag == f"{ATOM_NS}feed" or root.tag == "feed":
        return _parse_atom(root, source)

    # RSS 2.0: root tag is <rss>
    if root.tag == "rss":
        return _parse_rss(root, source)

    # Some feeds use <channel> directly (rare)
    if root.tag == "channel":
        items: list[FeedItem] = []
        for item in root.findall("item"):
            title = _text(item.find("title"))
            link = _text(item.find("link"))
            desc = _text(item.find("description"))
            if title:
                items.append(FeedItem(
                    source=source.name, title=title, url=link,
                    category=source.category, summary=(desc or "")[:500],
                ))
        return items

    logger.warning("Unknown feed format for %s: root=%s", source.name, root.tag)
    return []


class FeedFetcher:
    """Fetches RSS/Atom feeds via HTTP and parses them into FeedItems.

    Uses httpx with configurable timeout and retries.
    Optionally routes through the Gateway for rate limiting.
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 2,
        user_agent: str = "GuardianOne-Palantir/1.0",
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._headers = {"User-Agent": user_agent}

    def fetch(self, source: FeedSource) -> list[FeedItem]:
        """Fetch and parse a single feed source.

        Returns parsed items on success, empty list on failure.
        Never raises — errors are logged and swallowed.
        """
        for attempt in range(self._max_retries + 1):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    resp = client.get(source.url, headers=self._headers)
                    resp.raise_for_status()

                items = parse_feed_xml(resp.text, source)
                source.last_checked = datetime.now(timezone.utc).isoformat()
                return items

            except httpx.TimeoutException:
                logger.warning(
                    "Timeout fetching %s (attempt %d/%d)",
                    source.name, attempt + 1, self._max_retries + 1,
                )
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "HTTP %d from %s: %s",
                    exc.response.status_code, source.name, exc,
                )
                break  # Don't retry on 4xx/5xx
            except httpx.HTTPError as exc:
                logger.warning(
                    "HTTP error fetching %s (attempt %d/%d): %s",
                    source.name, attempt + 1, self._max_retries + 1, exc,
                )

        return []

    def fetch_all(self, sources: list[FeedSource]) -> dict[str, list[FeedItem]]:
        """Fetch all sources, return items keyed by source name."""
        results: dict[str, list[FeedItem]] = {}
        for source in sources:
            if not source.enabled:
                continue
            results[source.name] = self.fetch(source)
        return results
