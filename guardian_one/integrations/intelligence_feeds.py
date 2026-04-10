"""Palantír — Strategic Intelligence Feed Pipeline.

The Archivist's seeing stone. Monitors RSS feeds, company blogs,
GitHub releases, and financial feeds on a 15-minute cycle.
Each feed produces FeedItem entries that get scored by priority
and surfaced in the Archivist's sovereignty report.

Think of it as a CIO's morning briefing — but it never sleeps.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class FeedCategory(Enum):
    TECH_NEWS = "tech_news"
    AI_COMPANY = "ai_company"
    GITHUB = "github"
    FINANCIAL = "financial"


class FeedPriority(Enum):
    CRITICAL = "critical"    # Breaking: security vuln, major release, market crash
    HIGH = "high"            # Important: new model launch, earnings, trending repo
    MEDIUM = "medium"        # Useful: blog post, minor release, industry news
    LOW = "low"              # FYI: opinion pieces, roundups


@dataclass
class FeedSource:
    """A single RSS/API feed to monitor."""
    name: str
    url: str
    category: FeedCategory
    enabled: bool = True
    refresh_minutes: int = 15
    last_checked: str | None = None
    priority_keywords: list[str] = field(default_factory=list)


@dataclass
class FeedItem:
    """A single item from an intelligence feed."""
    source: str
    title: str
    url: str
    category: FeedCategory
    priority: FeedPriority = FeedPriority.MEDIUM
    summary: str = ""
    published: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    tags: list[str] = field(default_factory=list)
    read: bool = False

    @property
    def item_id(self) -> str:
        """Deterministic ID from source + title for dedup."""
        raw = f"{self.source}:{self.title}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]


# ------------------------------------------------------------------
# Priority keywords — items matching these get bumped up
# ------------------------------------------------------------------

CRITICAL_KEYWORDS = [
    "security vulnerability", "cve-", "data breach", "zero-day",
    "emergency patch", "critical update", "service outage",
    "market crash", "sec investigation",
]

HIGH_KEYWORDS = [
    "new model", "gpt-", "claude", "gemini", "llama", "mistral",
    "series a", "series b", "ipo", "acquisition", "launch",
    "trending", "breaking", "earnings", "quarterly results",
    "open source", "release candidate",
]


def score_priority(title: str, summary: str, source_keywords: list[str]) -> FeedPriority:
    """Score an item's priority based on keyword matching.

    Like Varys's little birds — certain words make ears perk up.
    """
    text = f"{title} {summary}".lower()

    for kw in CRITICAL_KEYWORDS:
        if kw in text:
            return FeedPriority.CRITICAL

    for kw in HIGH_KEYWORDS + source_keywords:
        if kw in text:
            return FeedPriority.HIGH

    return FeedPriority.MEDIUM


# ------------------------------------------------------------------
# Default feed sources — the Palantír's network
# ------------------------------------------------------------------

DEFAULT_FEEDS: list[FeedSource] = [
    # Tech news
    FeedSource(
        name="Hacker News",
        url="https://hnrss.org/frontpage",
        category=FeedCategory.TECH_NEWS,
        priority_keywords=["show hn", "ask hn"],
    ),
    FeedSource(
        name="TechCrunch",
        url="https://techcrunch.com/feed/",
        category=FeedCategory.TECH_NEWS,
    ),
    FeedSource(
        name="Ars Technica",
        url="https://feeds.arstechnica.com/arstechnica/index",
        category=FeedCategory.TECH_NEWS,
    ),
    FeedSource(
        name="The Verge",
        url="https://www.theverge.com/rss/index.xml",
        category=FeedCategory.TECH_NEWS,
    ),
    FeedSource(
        name="Wired",
        url="https://www.wired.com/feed/rss",
        category=FeedCategory.TECH_NEWS,
    ),

    # AI company blogs
    FeedSource(
        name="Anthropic Blog",
        url="https://www.anthropic.com/blog/rss.xml",
        category=FeedCategory.AI_COMPANY,
        priority_keywords=["claude", "safety", "constitutional"],
    ),
    FeedSource(
        name="OpenAI Blog",
        url="https://openai.com/blog/rss.xml",
        category=FeedCategory.AI_COMPANY,
        priority_keywords=["gpt", "dall-e", "sora", "o1", "o3"],
    ),
    FeedSource(
        name="Google DeepMind",
        url="https://deepmind.google/blog/rss.xml",
        category=FeedCategory.AI_COMPANY,
        priority_keywords=["gemini", "alphafold", "gemma"],
    ),
    FeedSource(
        name="Meta AI Blog",
        url="https://ai.meta.com/blog/rss/",
        category=FeedCategory.AI_COMPANY,
        priority_keywords=["llama", "codellama"],
    ),
    FeedSource(
        name="Mistral AI Blog",
        url="https://mistral.ai/feed.xml",
        category=FeedCategory.AI_COMPANY,
        priority_keywords=["mixtral", "mistral"],
    ),

    # GitHub trending / releases
    FeedSource(
        name="GitHub Trending",
        url="https://github.com/trending",
        category=FeedCategory.GITHUB,
        priority_keywords=["stars", "trending"],
    ),

    # Financial / market feeds
    FeedSource(
        name="Yahoo Finance Top Stories",
        url="https://finance.yahoo.com/news/rssindex",
        category=FeedCategory.FINANCIAL,
        priority_keywords=["earnings", "fed", "interest rate"],
    ),
    FeedSource(
        name="SEC EDGAR Filings",
        url="https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=&dateb=&owner=include&count=40&search_text=&start=0&output=atom",
        category=FeedCategory.FINANCIAL,
        priority_keywords=["10-k", "10-q", "8-k"],
    ),
]


class IntelligencePipeline:
    """The Palantír — strategic intelligence feed aggregator.

    Collects, deduplicates, scores, and stores feed items.
    Designed to be called on a 15-minute cycle by the Archivist
    or the scheduler. Never fetches in production without a real
    HTTP client injected — tests run entirely on fake data.
    """

    def __init__(
        self,
        feeds: list[FeedSource] | None = None,
        max_items_per_source: int = 50,
    ) -> None:
        self._feeds: dict[str, FeedSource] = {}
        self._items: dict[str, FeedItem] = {}  # keyed by item_id
        self._max_per_source = max_items_per_source

        for source in (DEFAULT_FEEDS if feeds is None else feeds):
            self._feeds[source.name] = source

    @property
    def sources(self) -> list[FeedSource]:
        return list(self._feeds.values())

    @property
    def active_sources(self) -> list[FeedSource]:
        return [f for f in self._feeds.values() if f.enabled]

    def add_source(self, source: FeedSource) -> None:
        self._feeds[source.name] = source

    def remove_source(self, name: str) -> bool:
        return self._feeds.pop(name, None) is not None

    # ------------------------------------------------------------------
    # Item ingestion
    # ------------------------------------------------------------------

    def ingest(self, item: FeedItem) -> bool:
        """Add a feed item, dedup by item_id. Returns True if new."""
        if item.item_id in self._items:
            return False

        # Auto-score priority
        source = self._feeds.get(item.source)
        source_kw = source.priority_keywords if source else []
        item.priority = score_priority(item.title, item.summary, source_kw)

        self._items[item.item_id] = item
        return True

    def ingest_batch(self, items: list[FeedItem]) -> int:
        """Ingest multiple items. Returns count of new items."""
        return sum(1 for item in items if self.ingest(item))

    def refresh(self, fetcher: Any = None) -> dict[str, Any]:
        """Fetch all active feeds and ingest new items.

        Pass a FeedFetcher instance. If None, returns an error dict
        (won't crash — just can't fetch without a fetcher).
        """
        if fetcher is None:
            return {"error": "No fetcher provided — cannot refresh."}

        total_new = 0
        sources_checked = 0
        errors: list[str] = []

        for source in self.active_sources:
            try:
                items = fetcher.fetch(source)
                total_new += self.ingest_batch(items)
                sources_checked += 1
            except Exception as exc:
                errors.append(f"{source.name}: {exc}")

        return {
            "new_items": total_new,
            "sources_checked": sources_checked,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def unread(self, category: FeedCategory | None = None) -> list[FeedItem]:
        """Get unread items, optionally filtered by category. Newest first."""
        items = [i for i in self._items.values() if not i.read]
        if category:
            items = [i for i in items if i.category == category]
        items.sort(key=lambda i: i.published, reverse=True)
        return items

    def by_priority(self, priority: FeedPriority) -> list[FeedItem]:
        """Get all items at a given priority level."""
        return [i for i in self._items.values() if i.priority == priority]

    def critical_alerts(self) -> list[FeedItem]:
        """CRITICAL items that haven't been read yet — the red phone."""
        return [
            i for i in self._items.values()
            if i.priority == FeedPriority.CRITICAL and not i.read
        ]

    def mark_read(self, item_id: str) -> bool:
        item = self._items.get(item_id)
        if item:
            item.read = True
            return True
        return False

    def search(self, query: str) -> list[FeedItem]:
        """Search items by title/summary text."""
        q = query.lower()
        return [
            i for i in self._items.values()
            if q in i.title.lower() or q in i.summary.lower()
        ]

    # ------------------------------------------------------------------
    # Digest / briefing
    # ------------------------------------------------------------------

    def briefing(self, max_items: int = 20) -> dict[str, Any]:
        """Generate a CIO-level intelligence briefing.

        Returns a structured digest: critical alerts first,
        then high-priority items, grouped by category.
        """
        critical = self.critical_alerts()
        high = [i for i in self.by_priority(FeedPriority.HIGH) if not i.read]

        by_category: dict[str, list[dict[str, str]]] = {}
        for item in self.unread()[:max_items]:
            cat = item.category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append({
                "title": item.title,
                "source": item.source,
                "priority": item.priority.value,
                "url": item.url,
            })

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "critical_count": len(critical),
            "high_priority_count": len(high),
            "total_unread": len(self.unread()),
            "critical_alerts": [
                {"title": i.title, "source": i.source, "url": i.url}
                for i in critical
            ],
            "by_category": by_category,
            "sources_active": len(self.active_sources),
            "sources_total": len(self._feeds),
        }

    def stats(self) -> dict[str, Any]:
        """Pipeline health stats."""
        return {
            "total_items": len(self._items),
            "unread": len(self.unread()),
            "critical": len(self.critical_alerts()),
            "sources": len(self._feeds),
            "active_sources": len(self.active_sources),
            "by_category": {
                cat.value: len([
                    i for i in self._items.values()
                    if i.category == cat
                ])
                for cat in FeedCategory
            },
        }
