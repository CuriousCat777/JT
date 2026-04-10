"""Tests for the feed fetcher — real XML parsing, mock HTTP."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import httpx

from guardian_one.core.audit import AuditLog
from guardian_one.core.config import AgentConfig
from guardian_one.agents.archivist import Archivist
from guardian_one.integrations.feed_fetcher import (
    FeedFetcher,
    parse_feed_xml,
)
from guardian_one.integrations.intelligence_feeds import (
    FeedCategory,
    FeedSource,
    IntelligencePipeline,
)


# ------------------------------------------------------------------
# Sample XML payloads
# ------------------------------------------------------------------

RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>CVE-2026-1234 Critical Vulnerability</title>
      <link>https://example.com/cve-2026</link>
      <description>A critical zero-day was found.</description>
      <pubDate>Thu, 03 Apr 2026 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>New Rust Release</title>
      <link>https://example.com/rust</link>
      <description>Rust 1.85 is out.</description>
      <pubDate>Thu, 03 Apr 2026 11:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""

ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Anthropic Blog</title>
  <entry>
    <title>Claude 5 Launch</title>
    <link href="https://anthropic.com/blog/claude-5" rel="alternate"/>
    <summary>We are excited to announce Claude 5.</summary>
    <published>2026-04-03T10:00:00Z</published>
  </entry>
  <entry>
    <title>Safety Research Update</title>
    <link href="https://anthropic.com/blog/safety" rel="alternate"/>
    <content>New interpretability findings.</content>
    <updated>2026-04-02T09:00:00Z</updated>
  </entry>
</feed>"""

MALFORMED_XML = """<not valid xml at all <><>"""


def _make_audit():
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


def _make_source(name="Test", url="https://example.com/feed", category=FeedCategory.TECH_NEWS):
    return FeedSource(name=name, url=url, category=category)


# ------------------------------------------------------------------
# XML parsing
# ------------------------------------------------------------------

def test_parse_rss():
    source = _make_source()
    items = parse_feed_xml(RSS_XML, source)
    assert len(items) == 2
    assert items[0].title == "CVE-2026-1234 Critical Vulnerability"
    assert items[0].url == "https://example.com/cve-2026"
    assert items[0].source == "Test"
    assert items[0].category == FeedCategory.TECH_NEWS


def test_parse_atom():
    source = _make_source(name="Anthropic", category=FeedCategory.AI_COMPANY)
    items = parse_feed_xml(ATOM_XML, source)
    assert len(items) == 2
    assert items[0].title == "Claude 5 Launch"
    assert items[0].url == "https://anthropic.com/blog/claude-5"
    assert "Claude 5" in items[0].summary


def test_parse_malformed_xml():
    source = _make_source()
    items = parse_feed_xml(MALFORMED_XML, source)
    assert items == []


def test_parse_empty_items():
    xml = """<?xml version="1.0"?><rss><channel><title>Empty</title></channel></rss>"""
    items = parse_feed_xml(xml, _make_source())
    assert items == []


def test_parse_atom_uses_content_as_summary():
    """When <summary> is missing, <content> should be used."""
    source = _make_source()
    items = parse_feed_xml(ATOM_XML, source)
    # Second entry has <content> but no <summary>
    assert items[1].summary == "New interpretability findings."


# ------------------------------------------------------------------
# FeedFetcher with mock HTTP
# ------------------------------------------------------------------

def test_fetcher_success():
    source = _make_source()
    fetcher = FeedFetcher(timeout=5)

    mock_response = httpx.Response(200, text=RSS_XML, request=httpx.Request("GET", source.url))
    with patch("httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.get.return_value = mock_response
        items = fetcher.fetch(source)

    assert len(items) == 2
    assert source.last_checked is not None


def test_fetcher_timeout_retries():
    source = _make_source()
    fetcher = FeedFetcher(timeout=1, max_retries=1)

    with patch("httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.get.side_effect = httpx.TimeoutException("timed out")
        items = fetcher.fetch(source)

    assert items == []
    # Should have been called max_retries + 1 times
    assert instance.get.call_count == 2


def test_fetcher_http_error_no_retry():
    source = _make_source()
    fetcher = FeedFetcher(max_retries=2)

    mock_response = httpx.Response(404)
    mock_response.request = httpx.Request("GET", source.url)
    with patch("httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.get.return_value = mock_response
        items = fetcher.fetch(source)

    assert items == []
    # 4xx should NOT retry
    assert instance.get.call_count == 1


def test_fetcher_fetch_all():
    sources = [
        _make_source(name="A", url="https://a.com/feed"),
        _make_source(name="B", url="https://b.com/feed"),
        FeedSource(name="C", url="https://c.com", category=FeedCategory.TECH_NEWS, enabled=False),
    ]
    fetcher = FeedFetcher()

    mock_response = httpx.Response(200, text=RSS_XML, request=httpx.Request("GET", "https://a.com/feed"))
    with patch("httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.get.return_value = mock_response
        results = fetcher.fetch_all(sources)

    assert "A" in results
    assert "B" in results
    assert "C" not in results  # disabled


# ------------------------------------------------------------------
# Pipeline refresh()
# ------------------------------------------------------------------

def test_pipeline_refresh_with_fetcher():
    pipeline = IntelligencePipeline()

    mock_fetcher = MagicMock()
    mock_fetcher.fetch.return_value = parse_feed_xml(RSS_XML, _make_source(name="HN"))

    result = pipeline.refresh(mock_fetcher)
    assert result["new_items"] == 2
    assert result["sources_checked"] == len(pipeline.active_sources)
    assert len(result["errors"]) == 0


def test_pipeline_refresh_without_fetcher():
    pipeline = IntelligencePipeline()
    result = pipeline.refresh(None)
    assert "error" in result


def test_pipeline_refresh_deduplicates():
    pipeline = IntelligencePipeline(feeds=[_make_source(name="A")])

    items = parse_feed_xml(RSS_XML, _make_source(name="A"))
    mock_fetcher = MagicMock()
    mock_fetcher.fetch.return_value = items

    # First refresh ingests 2
    r1 = pipeline.refresh(mock_fetcher)
    assert r1["new_items"] == 2

    # Second refresh deduplicates
    r2 = pipeline.refresh(mock_fetcher)
    assert r2["new_items"] == 0


# ------------------------------------------------------------------
# Archivist + live refresh
# ------------------------------------------------------------------

def test_archivist_palantir_refresh():
    agent = Archivist(AgentConfig(name="archivist"), _make_audit())
    agent.initialize()

    mock_fetcher = MagicMock()
    mock_fetcher.fetch.return_value = parse_feed_xml(
        ATOM_XML, _make_source(name="Anthropic", category=FeedCategory.AI_COMPANY)
    )

    result = agent.palantir.refresh(mock_fetcher)
    assert result["new_items"] == 2

    briefing = agent.intelligence_briefing()
    assert briefing["total_unread"] == 2
