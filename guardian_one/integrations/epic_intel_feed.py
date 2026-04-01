"""Epic Intelligence Feed — RSS news + financial data with SQLite storage.

Aggregates healthcare/Epic news from RSS feeds and stores in a
SQL-queryable SQLite database for decision support.

Usage:
    feed = EpicIntelFeed(db_path="data/epic_intel.db")
    feed.refresh()                          # Fetch all RSS feeds
    articles = feed.query_articles(limit=20)
    feed.search("physician builder")        # Full-text search

SQL direct access:
    import sqlite3
    conn = sqlite3.connect("data/epic_intel.db")
    cursor = conn.execute("SELECT * FROM articles WHERE category = 'epic' ORDER BY published DESC LIMIT 10")

Tables:
    articles    — RSS articles with title, summary, url, category, source, published, fetched_at
    market_data — EHR market metrics snapshots (revenue, market_share, etc.)
    competitors — Competitor tracking (Oracle Health, MEDITECH, etc.)
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class FeedArticle:
    """A single article from an RSS feed."""
    title: str
    url: str
    summary: str = ""
    source: str = ""
    category: str = ""       # epic, ehr, fhir, ai_health, regulatory, financial
    published: str = ""
    fetched_at: str = ""
    content_hash: str = ""

    def __post_init__(self):
        if not self.content_hash:
            raw = f"{self.title}{self.url}".encode()
            self.content_hash = hashlib.sha256(raw).hexdigest()[:16]
        if not self.fetched_at:
            self.fetched_at = datetime.now(timezone.utc).isoformat()


@dataclass
class MarketSnapshot:
    """Point-in-time EHR market data."""
    date: str
    vendor: str
    metric: str              # revenue, hospital_share, bed_share, net_change
    value: float
    unit: str = ""           # percent, dollars, count
    source: str = ""
    notes: str = ""


# ---------------------------------------------------------------------------
# RSS Feed definitions
# ---------------------------------------------------------------------------

EPIC_RSS_FEEDS: list[dict[str, str]] = [
    # Healthcare IT News
    {
        "url": "https://www.healthcareitnews.com/feed",
        "source": "Healthcare IT News",
        "category": "ehr",
    },
    # Becker's Health IT
    {
        "url": "https://www.beckershospitalreview.com/healthcare-information-technology.feed",
        "source": "Beckers Health IT",
        "category": "ehr",
    },
    # HIMSS
    {
        "url": "https://www.himss.org/news/feed",
        "source": "HIMSS",
        "category": "ehr",
    },
    # HIT Consultant
    {
        "url": "https://hitconsultant.net/feed/",
        "source": "HIT Consultant",
        "category": "ai_health",
    },
    # Fierce Healthcare
    {
        "url": "https://www.fiercehealthcare.com/rss/xml",
        "source": "Fierce Healthcare",
        "category": "ehr",
    },
    # ONC Health IT
    {
        "url": "https://www.healthit.gov/topic/newsroom/feed",
        "source": "ONC HealthIT.gov",
        "category": "regulatory",
    },
    # Federal Register — Health IT rules
    {
        "url": "https://www.federalregister.gov/api/v1/documents.rss?conditions%5Bagencies%5D%5B%5D=health-and-human-services-department",
        "source": "Federal Register HHS",
        "category": "regulatory",
    },
]

# Keywords to prioritize articles about Epic ecosystem
EPIC_KEYWORDS = [
    "epic systems", "epic ehr", "epic emr", "epic fhir",
    "physician builder", "app orchard", "app market", "epic showroom",
    "smart on fhir", "cds hooks", "judy faulkner",
    "oracle health", "cerner", "meditech",
    "21st century cures", "information blocking", "interoperability",
    "ambient ai", "clinical ai", "ai scribe",
    "fhir r4", "uscdi", "tefca",
    "cosmos", "mychart",
]


# ---------------------------------------------------------------------------
# SQLite schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    summary TEXT DEFAULT '',
    source TEXT DEFAULT '',
    category TEXT DEFAULT '',
    published TEXT DEFAULT '',
    fetched_at TEXT NOT NULL,
    relevance_score REAL DEFAULT 0.0,
    read INTEGER DEFAULT 0,
    starred INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published DESC);
CREATE INDEX IF NOT EXISTS idx_articles_relevance ON articles(relevance_score DESC);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source);

CREATE TABLE IF NOT EXISTS market_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    vendor TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT DEFAULT '',
    source TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_market_vendor ON market_data(vendor);
CREATE INDEX IF NOT EXISTS idx_market_metric ON market_data(metric);
CREATE INDEX IF NOT EXISTS idx_market_date ON market_data(date DESC);

CREATE TABLE IF NOT EXISTS competitors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor TEXT NOT NULL,
    hospital_share REAL DEFAULT 0,
    bed_share REAL DEFAULT 0,
    net_change_2024 INTEGER DEFAULT 0,
    revenue_est TEXT DEFAULT '',
    ai_projects TEXT DEFAULT '',
    strengths TEXT DEFAULT '',
    weaknesses TEXT DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_competitors_vendor ON competitors(vendor);

CREATE TABLE IF NOT EXISTS feed_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    source_name TEXT NOT NULL,
    category TEXT DEFAULT '',
    last_fetched TEXT DEFAULT '',
    fetch_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1
);
"""

SEED_MARKET_DATA = [
    ("2024-12-31", "Epic Systems", "revenue", 5.7, "billion_usd", "Beckers", ""),
    ("2024-12-31", "Epic Systems", "hospital_share", 42.3, "percent", "KLAS Research", "3,620 hospitals"),
    ("2024-12-31", "Epic Systems", "bed_share", 54.9, "percent", "KLAS Research", ""),
    ("2024-12-31", "Epic Systems", "net_hospital_change", 176, "count", "KLAS Research", "Record gain"),
    ("2024-12-31", "Epic Systems", "patient_records", 325, "million", "Epic", ""),
    ("2024-12-31", "Epic Systems", "ai_projects", 200, "count", "Epic UGM", "160-200 active"),
    ("2024-12-31", "Epic Systems", "app_market_apps", 1000, "count", "Epic", ""),
    ("2024-12-31", "Epic Systems", "fhir_api_calls", 8, "billion", "Epic", "Since USCDI v3"),
    ("2024-12-31", "Oracle Health", "hospital_share", 22.9, "percent", "KLAS Research", ""),
    ("2024-12-31", "Oracle Health", "bed_share", 22.1, "percent", "KLAS Research", ""),
    ("2024-12-31", "Oracle Health", "net_hospital_change", -74, "count", "KLAS Research", ""),
    ("2024-12-31", "MEDITECH", "hospital_share", 14.8, "percent", "KLAS Research", ""),
    ("2024-12-31", "MEDITECH", "bed_share", 12.7, "percent", "KLAS Research", ""),
    ("2024-12-31", "MEDITECH", "net_hospital_change", -57, "count", "KLAS Research", ""),
]

SEED_COMPETITORS = [
    ("Epic Systems", 42.3, 54.9, 176, "$5.7B", "160-200",
     "Interoperability leadership, AI investment, Cosmos database, near-100% retention",
     "Private/opaque pricing, vendor lock-in risk, builds competing features internally"),
    ("Oracle Health", 22.9, 22.1, -74, "~$6B (Oracle Health segment)", "Clinical AI Agent",
     "Oracle cloud infrastructure, DoD/VA dominance, $28.3B investment backing",
     "Customer trust issues post-acquisition, losing hospitals, 10pt drop in satisfaction"),
    ("MEDITECH", 14.8, 12.7, -57, "~$500M", "Expanse cloud platform",
     "Budget-friendly, largest in Canada, community hospital focus",
     "Losing share to Epic, limited AI investment, smaller ecosystem"),
]


# ---------------------------------------------------------------------------
# Feed parser
# ---------------------------------------------------------------------------

def _parse_rss(xml_text: str, source: str, category: str) -> list[FeedArticle]:
    """Parse RSS/Atom XML into FeedArticle list."""
    articles: list[FeedArticle] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return articles

    # RSS 2.0
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if title and link:
            # Strip HTML from description
            desc = re.sub(r"<[^>]+>", "", desc)[:500]
            articles.append(FeedArticle(
                title=title, url=link, summary=desc,
                source=source, category=category, published=pub,
            ))

    # Atom fallback
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", ns):
        title = (entry.findtext("atom:title", "", ns) or "").strip()
        link_el = entry.find("atom:link", ns)
        link = link_el.get("href", "") if link_el is not None else ""
        summary = (entry.findtext("atom:summary", "", ns) or "").strip()
        pub = (entry.findtext("atom:published", "", ns) or
               entry.findtext("atom:updated", "", ns) or "").strip()
        if title and link:
            summary = re.sub(r"<[^>]+>", "", summary)[:500]
            articles.append(FeedArticle(
                title=title, url=link, summary=summary,
                source=source, category=category, published=pub,
            ))

    return articles


def _score_relevance(article: FeedArticle) -> float:
    """Score article relevance to Epic physician builder strategy (0-1)."""
    text = f"{article.title} {article.summary}".lower()
    hits = sum(1 for kw in EPIC_KEYWORDS if kw in text)
    # Normalize: 3+ keyword hits = 1.0
    return min(hits / 3.0, 1.0)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class EpicIntelFeed:
    """Epic intelligence feed with SQLite-backed storage.

    Fetches RSS feeds, scores relevance, and stores in a SQL-queryable
    database for the Epic physician builder decision dashboard.
    """

    def __init__(self, db_path: str | Path = "data/epic_intel.db") -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self) -> None:
        """Create tables and seed initial data."""
        self.conn.executescript(SCHEMA_SQL)

        # Seed market data if empty
        count = self.conn.execute("SELECT COUNT(*) FROM market_data").fetchone()[0]
        if count == 0:
            now = datetime.now(timezone.utc).isoformat()
            self.conn.executemany(
                "INSERT INTO market_data (date, vendor, metric, value, unit, source, notes, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(*row, now) for row in SEED_MARKET_DATA],
            )

        # Seed competitors if empty
        count = self.conn.execute("SELECT COUNT(*) FROM competitors").fetchone()[0]
        if count == 0:
            now = datetime.now(timezone.utc).isoformat()
            self.conn.executemany(
                "INSERT INTO competitors (vendor, hospital_share, bed_share, net_change_2024, "
                "revenue_est, ai_projects, strengths, weaknesses, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(*row, now) for row in SEED_COMPETITORS],
            )

        # Seed feed sources if empty
        count = self.conn.execute("SELECT COUNT(*) FROM feed_sources").fetchone()[0]
        if count == 0:
            self.conn.executemany(
                "INSERT INTO feed_sources (url, source_name, category) VALUES (?, ?, ?)",
                [(f["url"], f["source"], f["category"]) for f in EPIC_RSS_FEEDS],
            )

        self.conn.commit()

    # ------------------------------------------------------------------
    # Feed fetching
    # ------------------------------------------------------------------

    def _fetch_feed(self, url: str, timeout: int = 15) -> str | None:
        """Fetch RSS feed XML from URL."""
        try:
            req = Request(url, headers={
                "User-Agent": "GuardianOne/2.0 EpicIntelFeed",
                "Accept": "application/rss+xml, application/xml, text/xml",
            })
            with urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (URLError, TimeoutError, OSError):
            return None

    def refresh(self, timeout: int = 15) -> dict[str, Any]:
        """Fetch all RSS feeds and store new articles."""
        stats = {"feeds_checked": 0, "new_articles": 0, "errors": 0}
        now = datetime.now(timezone.utc).isoformat()

        feeds = self.conn.execute(
            "SELECT url, source_name, category FROM feed_sources WHERE enabled = 1"
        ).fetchall()

        for feed in feeds:
            stats["feeds_checked"] += 1
            xml = self._fetch_feed(feed["url"], timeout=timeout)

            if xml is None:
                stats["errors"] += 1
                self.conn.execute(
                    "UPDATE feed_sources SET error_count = error_count + 1 WHERE url = ?",
                    (feed["url"],),
                )
                continue

            articles = _parse_rss(xml, feed["source_name"], feed["category"])

            for article in articles:
                article.relevance_score = _score_relevance(article)
                try:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO articles "
                        "(content_hash, title, url, summary, source, category, "
                        "published, fetched_at, relevance_score) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (article.content_hash, article.title, article.url,
                         article.summary, article.source, article.category,
                         article.published, article.fetched_at,
                         _score_relevance(article)),
                    )
                    if self.conn.total_changes:
                        stats["new_articles"] += 1
                except sqlite3.IntegrityError:
                    pass  # Duplicate — already exists

            self.conn.execute(
                "UPDATE feed_sources SET last_fetched = ?, fetch_count = fetch_count + 1 "
                "WHERE url = ?",
                (now, feed["url"]),
            )

        self.conn.commit()
        return stats

    # ------------------------------------------------------------------
    # Query methods (SQL-friendly)
    # ------------------------------------------------------------------

    def query_articles(
        self,
        category: str | None = None,
        source: str | None = None,
        min_relevance: float = 0.0,
        starred_only: bool = False,
        limit: int = 25,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query articles with filters. Returns dicts for JSON serialization."""
        conditions = ["1=1"]
        params: list[Any] = []

        if category:
            conditions.append("category = ?")
            params.append(category)
        if source:
            conditions.append("source = ?")
            params.append(source)
        if min_relevance > 0:
            conditions.append("relevance_score >= ?")
            params.append(min_relevance)
        if starred_only:
            conditions.append("starred = 1")

        where = " AND ".join(conditions)
        params.extend([limit, offset])

        rows = self.conn.execute(
            f"SELECT * FROM articles WHERE {where} "
            "ORDER BY relevance_score DESC, published DESC "
            "LIMIT ? OFFSET ?",
            params,
        ).fetchall()

        return [dict(row) for row in rows]

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search articles by keyword in title and summary."""
        pattern = f"%{query}%"
        rows = self.conn.execute(
            "SELECT * FROM articles WHERE title LIKE ? OR summary LIKE ? "
            "ORDER BY relevance_score DESC, published DESC LIMIT ?",
            (pattern, pattern, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_market_data(
        self,
        vendor: str | None = None,
        metric: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query market data snapshots."""
        conditions = ["1=1"]
        params: list[Any] = []
        if vendor:
            conditions.append("vendor = ?")
            params.append(vendor)
        if metric:
            conditions.append("metric = ?")
            params.append(metric)

        where = " AND ".join(conditions)
        rows = self.conn.execute(
            f"SELECT * FROM market_data WHERE {where} ORDER BY date DESC",
            params,
        ).fetchall()
        return [dict(row) for row in rows]

    def get_competitors(self) -> list[dict[str, Any]]:
        """Get all competitor data."""
        rows = self.conn.execute(
            "SELECT * FROM competitors ORDER BY hospital_share DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def add_market_snapshot(self, snapshot: MarketSnapshot) -> None:
        """Add a new market data point."""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT INTO market_data (date, vendor, metric, value, unit, source, notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (snapshot.date, snapshot.vendor, snapshot.metric, snapshot.value,
             snapshot.unit, snapshot.source, snapshot.notes, now),
        )
        self.conn.commit()

    def star_article(self, article_id: int) -> None:
        """Star/unstar an article for later reference."""
        self.conn.execute(
            "UPDATE articles SET starred = CASE WHEN starred = 1 THEN 0 ELSE 1 END WHERE id = ?",
            (article_id,),
        )
        self.conn.commit()

    def stats(self) -> dict[str, Any]:
        """Dashboard stats for the intelligence feed."""
        total = self.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        high_rel = self.conn.execute(
            "SELECT COUNT(*) FROM articles WHERE relevance_score >= 0.5"
        ).fetchone()[0]
        starred = self.conn.execute(
            "SELECT COUNT(*) FROM articles WHERE starred = 1"
        ).fetchone()[0]
        sources = self.conn.execute(
            "SELECT COUNT(*) FROM feed_sources WHERE enabled = 1"
        ).fetchone()[0]
        categories = self.conn.execute(
            "SELECT category, COUNT(*) as cnt FROM articles GROUP BY category ORDER BY cnt DESC"
        ).fetchall()

        return {
            "total_articles": total,
            "high_relevance": high_rel,
            "starred": starred,
            "active_sources": sources,
            "by_category": {row["category"]: row["cnt"] for row in categories},
            "db_path": str(self._db_path),
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
