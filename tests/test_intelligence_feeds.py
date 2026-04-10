"""Tests for the Palantír intelligence feed pipeline."""

import tempfile
from pathlib import Path

from guardian_one.core.audit import AuditLog
from guardian_one.core.base_agent import AgentStatus
from guardian_one.core.config import AgentConfig
from guardian_one.agents.archivist import Archivist
from guardian_one.integrations.intelligence_feeds import (
    DEFAULT_FEEDS,
    FeedCategory,
    FeedItem,
    FeedPriority,
    FeedSource,
    IntelligencePipeline,
    score_priority,
)


def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


# ------------------------------------------------------------------
# Priority scoring
# ------------------------------------------------------------------

def test_score_critical_on_cve():
    p = score_priority("CVE-2026-1234 discovered", "", [])
    assert p == FeedPriority.CRITICAL


def test_score_critical_on_breach():
    p = score_priority("Major data breach at MegaCorp", "", [])
    assert p == FeedPriority.CRITICAL


def test_score_high_on_model_launch():
    p = score_priority("Claude 5 launched today", "", [])
    assert p == FeedPriority.HIGH


def test_score_high_on_source_keyword():
    p = score_priority("Regular blog post", "", ["regular"])
    assert p == FeedPriority.HIGH


def test_score_medium_default():
    p = score_priority("Another day in tech", "", [])
    assert p == FeedPriority.MEDIUM


# ------------------------------------------------------------------
# FeedItem
# ------------------------------------------------------------------

def test_feed_item_deterministic_id():
    a = FeedItem(source="HN", title="Hello", url="https://example.com", category=FeedCategory.TECH_NEWS)
    b = FeedItem(source="HN", title="Hello", url="https://other.com", category=FeedCategory.TECH_NEWS)
    assert a.item_id == b.item_id  # same source + title = same ID


def test_feed_item_different_id():
    a = FeedItem(source="HN", title="Hello", url="", category=FeedCategory.TECH_NEWS)
    b = FeedItem(source="HN", title="World", url="", category=FeedCategory.TECH_NEWS)
    assert a.item_id != b.item_id


# ------------------------------------------------------------------
# IntelligencePipeline
# ------------------------------------------------------------------

def test_pipeline_default_sources():
    pipeline = IntelligencePipeline()
    assert len(pipeline.sources) == len(DEFAULT_FEEDS)
    assert len(pipeline.active_sources) > 0


def test_pipeline_ingest_dedup():
    pipeline = IntelligencePipeline(feeds=[])
    item = FeedItem(source="Test", title="A", url="", category=FeedCategory.TECH_NEWS)
    assert pipeline.ingest(item) is True
    assert pipeline.ingest(item) is False  # duplicate


def test_pipeline_ingest_batch():
    pipeline = IntelligencePipeline(feeds=[])
    items = [
        FeedItem(source="A", title=f"Item {i}", url="", category=FeedCategory.TECH_NEWS)
        for i in range(5)
    ]
    count = pipeline.ingest_batch(items)
    assert count == 5
    assert pipeline.stats()["total_items"] == 5


def test_pipeline_unread_filter():
    pipeline = IntelligencePipeline(feeds=[])
    pipeline.ingest(FeedItem(source="A", title="Tech", url="", category=FeedCategory.TECH_NEWS))
    pipeline.ingest(FeedItem(source="B", title="AI", url="", category=FeedCategory.AI_COMPANY))

    tech = pipeline.unread(category=FeedCategory.TECH_NEWS)
    assert len(tech) == 1
    assert tech[0].source == "A"


def test_pipeline_critical_alerts():
    pipeline = IntelligencePipeline(feeds=[])
    pipeline.ingest(FeedItem(
        source="Alert", title="CVE-2026-9999 zero-day in OpenSSL",
        url="", category=FeedCategory.TECH_NEWS,
    ))
    pipeline.ingest(FeedItem(
        source="Blog", title="Nice weather today",
        url="", category=FeedCategory.TECH_NEWS,
    ))
    critical = pipeline.critical_alerts()
    assert len(critical) == 1
    assert "CVE" in critical[0].title


def test_pipeline_mark_read():
    pipeline = IntelligencePipeline(feeds=[])
    item = FeedItem(source="X", title="Y", url="", category=FeedCategory.TECH_NEWS)
    pipeline.ingest(item)
    assert len(pipeline.unread()) == 1
    pipeline.mark_read(item.item_id)
    assert len(pipeline.unread()) == 0


def test_pipeline_search():
    pipeline = IntelligencePipeline(feeds=[])
    pipeline.ingest(FeedItem(source="A", title="Rust compiler update", url="", category=FeedCategory.TECH_NEWS))
    pipeline.ingest(FeedItem(source="B", title="Python 3.13 released", url="", category=FeedCategory.TECH_NEWS))
    results = pipeline.search("rust")
    assert len(results) == 1


def test_pipeline_briefing():
    pipeline = IntelligencePipeline(feeds=[])
    pipeline.ingest(FeedItem(
        source="Sec", title="Critical data breach at BigCorp",
        url="https://example.com", category=FeedCategory.FINANCIAL,
    ))
    pipeline.ingest(FeedItem(
        source="HN", title="Show HN: Cool project",
        url="https://hn.com", category=FeedCategory.TECH_NEWS,
    ))
    briefing = pipeline.briefing()
    assert briefing["critical_count"] == 1
    assert briefing["total_unread"] == 2
    assert "generated_at" in briefing


def test_pipeline_stats():
    pipeline = IntelligencePipeline(feeds=[])
    pipeline.ingest(FeedItem(source="A", title="X", url="", category=FeedCategory.AI_COMPANY))
    stats = pipeline.stats()
    assert stats["total_items"] == 1
    assert stats["by_category"]["ai_company"] == 1


def test_pipeline_add_remove_source():
    pipeline = IntelligencePipeline(feeds=[])
    src = FeedSource(name="Custom", url="https://example.com/feed", category=FeedCategory.TECH_NEWS)
    pipeline.add_source(src)
    assert len(pipeline.sources) == 1
    assert pipeline.remove_source("Custom") is True
    assert len(pipeline.sources) == 0


# ------------------------------------------------------------------
# Archivist + Palantír integration
# ------------------------------------------------------------------

def test_archivist_palantir_ingest():
    agent = Archivist(AgentConfig(name="archivist"), _make_audit())
    agent.initialize()

    items = [
        FeedItem(source="HN", title="New Rust release", url="", category=FeedCategory.TECH_NEWS),
        FeedItem(source="Anthropic", title="Claude 5 launch", url="", category=FeedCategory.AI_COMPANY),
    ]
    count = agent.ingest_feed_items(items)
    assert count == 2


def test_archivist_intelligence_briefing():
    agent = Archivist(AgentConfig(name="archivist"), _make_audit())
    agent.initialize()

    agent.ingest_feed_items([
        FeedItem(source="SEC", title="Data breach at MegaCorp", url="", category=FeedCategory.FINANCIAL),
    ])
    briefing = agent.intelligence_briefing()
    assert briefing["critical_count"] == 1
    assert briefing["total_unread"] == 1


def test_archivist_run_includes_palantir():
    agent = Archivist(AgentConfig(name="archivist"), _make_audit())
    agent.initialize()

    agent.ingest_feed_items([
        FeedItem(source="Alert", title="CVE-2026-0001 in Linux kernel", url="", category=FeedCategory.TECH_NEWS),
        FeedItem(source="Blog", title="Nice post", url="", category=FeedCategory.AI_COMPANY),
    ])

    report = agent.run()
    assert any("PALANTÍR CRITICAL" in a for a in report.alerts)
    assert "palantir" in report.data
    assert report.data["palantir"]["total_items"] == 2


def test_archivist_report_includes_palantir_stats():
    agent = Archivist(AgentConfig(name="archivist"), _make_audit())
    agent.initialize()
    agent.ingest_feed_items([
        FeedItem(source="X", title="Y", url="", category=FeedCategory.GITHUB),
    ])
    report = agent.report()
    assert "palantir" in report.data
    assert "intel items" in report.summary
