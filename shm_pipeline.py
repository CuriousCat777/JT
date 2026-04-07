#!/usr/bin/env python3
"""
SHM Pipeline — Conference PDF processor + online SHM content collector.
=========================================================================
Processes local conference PDFs from DOX directories and runs as a daemon
that searches/collects online SHM-related content. Outputs structured JSON
to shm_pipeline_output/ for consumption by the handoff pipeline and AI agents.

Usage:
    python shm_pipeline.py <dir>                     # Process PDFs in directory
    python shm_pipeline.py --scan                    # Scan default DOX directories
    python shm_pipeline.py --daemon                  # Start online collector daemon
    python shm_pipeline.py --daemon --interval 600   # Daemon with 10-min cycle
    python shm_pipeline.py --stats                   # Show pipeline statistics
    python shm_pipeline.py --search "sepsis bundles" # One-shot online search
    python shm_pipeline.py --export                  # Export all data as handoff payload
    python shm_pipeline.py --skill-manifest          # Print skill manifest (for AI dispatch)

Daemon mode:
    Runs continuously, collecting SHM-related content from:
    - SHM conference abstracts and proceedings
    - PubMed/MEDLINE hospital medicine literature
    - Clinical practice guidelines (AHA, IDSA, ATS, etc.)
    - Quality improvement registries and measures
    - CMS policy updates relevant to hospitalists

Skill interface:
    Other AI agents can invoke this pipeline via the dispatch protocol:
    - process_pdfs(directory)     — extract from local PDFs
    - search_literature(query)    — search PubMed + SHM
    - get_statistics()            — pipeline stats
    - collect_online(topics)      — run one online collection cycle
    - export_all()                — export all data as JSON
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─── Configuration ───────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()
CONFERENCE_DOX = Path(os.environ.get("CONFERENCE_DOX", SCRIPT_DIR.parent / "DOX"))
HOME_DOX = Path(os.environ.get("HOME_DOX", SCRIPT_DIR / "DOX"))
OUTPUT_DIR = SCRIPT_DIR / "shm_pipeline_output"
STATS_FILE = OUTPUT_DIR / "pipeline_stats.json"
INDEX_FILE = OUTPUT_DIR / "extract_index.jsonl"
SEARCH_CACHE = OUTPUT_DIR / "search_cache"

# SHM-relevant search domains
SHM_TOPICS = [
    "hospital medicine", "hospitalist", "society of hospital medicine",
    "sepsis", "VTE prophylaxis", "delirium", "glycemic control",
    "care transitions", "discharge planning", "antimicrobial stewardship",
    "rapid response", "perioperative medicine", "palliative care inpatient",
    "observation medicine", "clinical documentation improvement",
    "high-value care", "diagnostic excellence",
]

# Evidence level patterns (for extraction)
_EVIDENCE_PATTERNS = {
    "systematic_review": re.compile(
        r"(?i)systematic\s+review|meta[\s-]?analysis|cochrane", re.I
    ),
    "rct": re.compile(r"(?i)randomized|randomised|RCT|controlled\s+trial"),
    "cohort": re.compile(r"(?i)cohort\s+study|prospective\s+study|retrospective"),
    "case_control": re.compile(r"(?i)case[\s-]?control"),
    "guideline": re.compile(r"(?i)practice\s+guideline|clinical\s+guideline|consensus\s+statement"),
    "expert_opinion": re.compile(r"(?i)expert\s+opinion|expert\s+consensus"),
}

# Citation pattern
_CITATION_RE = re.compile(
    r"(?:\d+\.\s+)?([A-Z][a-z]+(?:\s+[A-Z])?(?:\s+et\s+al\.?)?[,.]?\s+"
    r"(?:[\w\s]+\.?\s+)?\d{4}[;:]\s*\d+)"
)

# Statistics pattern
_STAT_RE = re.compile(
    r"(?:p\s*[<=]\s*0?\.\d+|"
    r"(?:HR|OR|RR|CI|NNT|NNH|AUC)\s*[=:]\s*[\d.]+|"
    r"\d+(?:\.\d+)?%|"
    r"n\s*=\s*[\d,]+)",
    re.I,
)

# Clinical tool mentions
_TOOL_NAMES = [
    "HEART", "START", "RASS", "bCAM", "CAM-ICU", "ABCDEF", "NEWS", "MEWS",
    "qSOFA", "SOFA", "CURB-65", "Wells", "Geneva", "CHADS", "CHA2DS2-VASc",
    "HAS-BLED", "Braden", "Morse", "LACE", "HOSPITAL",
]
_TOOL_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in _TOOL_NAMES) + r")\b"
)


# ─── Data Structures ─────────────────────────────────────────────────────────

@dataclass
class PDFExtract:
    """Structured extract from a single PDF document."""
    extract_id: str
    source_file: str
    source_dir: str
    title: str
    word_count: int
    citations: list[str] = field(default_factory=list)
    statistics: list[str] = field(default_factory=list)
    tools_mentioned: list[str] = field(default_factory=list)
    tool_mentions: dict[str, int] = field(default_factory=dict)
    evidence_levels: list[str] = field(default_factory=list)
    key_claims: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    processed_at: str = ""
    text_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OnlineResult:
    """A result from online SHM content collection."""
    result_id: str
    query: str
    source: str                      # pubmed, shm, guideline, cms
    title: str
    url: str
    snippet: str
    date_found: str
    relevance_score: float = 0.0
    tags: list[str] = field(default_factory=list)
    evidence_level: str = ""
    processed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineStats:
    """Running statistics for the pipeline."""
    total_pdfs_processed: int = 0
    total_words: int = 0
    total_citations: int = 0
    total_statistics: int = 0
    total_claims: int = 0
    total_tool_mentions: int = 0
    total_online_results: int = 0
    online_searches_run: int = 0
    last_pdf_run: str = ""
    last_online_run: str = ""
    seminal_studies: list[str] = field(default_factory=list)
    top_tools: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─── PDF Processing ──────────────────────────────────────────────────────────

def _extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from a PDF file.

    Tries PyMuPDF (fitz) first, falls back to pdfplumber, then pdfminer.
    Per-extractor runtime errors (corrupt/encrypted PDFs) log a warning
    and move on to the next extractor instead of aborting the whole run.
    """
    any_library_available = False

    # Try PyMuPDF
    try:
        import fitz  # type: ignore[import-untyped]
        any_library_available = True
    except ImportError:
        pass
    else:
        try:
            doc = fitz.open(str(pdf_path))
            try:
                text = ""
                for page in doc:
                    text += page.get_text()
                return text
            finally:
                doc.close()
        except Exception as exc:
            print(f"  [!] PyMuPDF failed for {pdf_path.name}: {exc}", file=sys.stderr)

    # Try pdfplumber
    try:
        import pdfplumber  # type: ignore[import-untyped]
        any_library_available = True
    except ImportError:
        pass
    else:
        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                return text
        except Exception as exc:
            print(f"  [!] pdfplumber failed for {pdf_path.name}: {exc}", file=sys.stderr)

    # Try pdfminer
    try:
        from pdfminer.high_level import extract_text  # type: ignore[import-untyped]
        any_library_available = True
    except ImportError:
        pass
    else:
        try:
            return extract_text(str(pdf_path))
        except Exception as exc:
            print(f"  [!] pdfminer failed for {pdf_path.name}: {exc}", file=sys.stderr)

    if not any_library_available:
        print("  [!] No PDF library available. Install: pip install PyMuPDF", file=sys.stderr)
    return ""


def process_pdf(pdf_path: Path) -> PDFExtract | None:
    """Process a single PDF into a structured extract."""
    text = _extract_text_from_pdf(pdf_path)
    if not text or len(text.strip()) < 50:
        return None

    # Basic metadata
    words = text.split()
    word_count = len(words)
    text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]

    # Extract title (first substantial line)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    title = lines[0][:120] if lines else pdf_path.stem

    # Extract citations
    citations = _CITATION_RE.findall(text)

    # Extract statistics
    statistics = _STAT_RE.findall(text)

    # Extract tool mentions
    tool_mentions = _TOOL_RE.findall(text)
    tool_counts: dict[str, int] = {}
    for t in tool_mentions:
        tool_counts[t] = tool_counts.get(t, 0) + 1

    # Detect evidence levels
    evidence_levels = []
    for level_name, pattern in _EVIDENCE_PATTERNS.items():
        if pattern.search(text):
            evidence_levels.append(level_name)

    # Extract key claims (sentences with statistics or strong assertions)
    claim_re = re.compile(
        r"[^.]*(?:significantly|associated with|reduced|increased|improved|"
        r"compared to|versus|p\s*[<=])[^.]*\.",
        re.I,
    )
    key_claims = [m.group().strip() for m in claim_re.finditer(text)][:20]

    # Build tags
    tags = []
    for level in evidence_levels:
        tag_map = {
            "systematic_review": "#level-1a",
            "rct": "#level-1b",
            "cohort": "#level-2b",
            "case_control": "#level-3",
            "guideline": "#guideline-ref",
            "expert_opinion": "#expert-opinion",
        }
        if level in tag_map:
            tags.append(tag_map[level])

    # Domain detection
    domain_keywords = {
        "#cardiology": ["cardiac", "heart failure", "atrial fibrillation", "ACS", "STEMI"],
        "#infectious-disease": ["sepsis", "antibiotic", "infection", "pneumonia", "bacteremia"],
        "#nephrology": ["AKI", "renal", "kidney", "dialysis", "creatinine"],
        "#pulmonology": ["COPD", "pneumonia", "respiratory", "ventilator", "oxygen"],
        "#neurology": ["stroke", "seizure", "delirium", "neurologic"],
        "#quality-improvement": ["quality", "readmission", "length of stay", "bundle"],
        "#perioperative": ["surgical", "perioperative", "postoperative", "preoperative"],
        "#palliative": ["palliative", "hospice", "goals of care", "advance directive"],
    }
    text_lower = text.lower()
    for domain_tag, keywords in domain_keywords.items():
        if any(kw.lower() in text_lower for kw in keywords):
            tags.append(domain_tag)

    extract_id = f"PDF-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{text_hash}"

    return PDFExtract(
        extract_id=extract_id,
        source_file=pdf_path.name,
        source_dir=str(pdf_path.parent),
        title=title,
        word_count=word_count,
        citations=citations[:50],  # cap at 50
        statistics=statistics[:100],
        tools_mentioned=list(tool_counts.keys()),
        tool_mentions=tool_counts,
        evidence_levels=evidence_levels,
        key_claims=key_claims,
        tags=tags,
        processed_at=datetime.now(timezone.utc).isoformat(),
        text_hash=text_hash,
    )


def process_directory(directory: Path) -> list[PDFExtract]:
    """Process all PDFs in a directory."""
    if not directory.exists():
        print(f"  Directory not found: {directory}", file=sys.stderr)
        return []

    pdfs = sorted(directory.glob("*.pdf"))
    if not pdfs:
        print(f"  No PDFs found in {directory}", file=sys.stderr)
        return []

    extracts = []
    for i, pdf in enumerate(pdfs, 1):
        print(f"  [{i}/{len(pdfs)}] Processing: {pdf.name}...")
        extract = process_pdf(pdf)
        if extract:
            extracts.append(extract)
            # Save individual extract with a unique, stable filename that
            # avoids collisions when identically named PDFs come from
            # different directories (stem + parent slug + content hash).
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            parent_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", pdf.parent.name or "root")
            # Sanitize stem too — PDF names can contain arbitrary characters
            stem_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", pdf.stem)
            out_path = OUTPUT_DIR / f"{parent_slug}__{stem_slug}__{extract.text_hash}.json"
            with open(out_path, "w") as f:
                json.dump(extract.to_dict(), f, indent=2)
        else:
            print(f"    [!] Could not extract text from {pdf.name}")

    return extracts


# ─── Online Collection ────────────────────────────────────────────────────────

class OnlineCollector:
    """Daemon that searches and collects SHM-related content online.

    Sources:
    - PubMed/MEDLINE (via E-utilities API — free, no key needed for low volume)
    - SHM abstracts and meeting proceedings
    - Clinical guideline repositories
    - CMS/Medicare policy updates

    All collection is local — results are stored as structured JSON.
    No PHI is involved (this is published literature and policy).
    """

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._cache_dir = output_dir / "search_cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._results_file = output_dir / "online_results.jsonl"
        self._result_counter = 0

    def search_pubmed(self, query: str, max_results: int = 20) -> list[OnlineResult]:
        """Search PubMed for hospital medicine literature.

        Uses NCBI E-utilities (esearch + efetch).
        Rate limit: 3 requests/second without API key.
        """
        try:
            import httpx
        except ImportError:
            print("  [!] httpx required for online search: pip install httpx", file=sys.stderr)
            return []

        results = []
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

        # NCBI recommends tool + email so they can contact on issues
        ncbi_id = {
            "tool": os.environ.get("NCBI_TOOL", "guardian-one-shm-pipeline"),
            "email": os.environ.get("NCBI_EMAIL", ""),
        }
        # Only include email if set (avoids sending empty param)
        ncbi_id = {k: v for k, v in ncbi_id.items() if v}

        try:
            # Step 1: Search for PMIDs
            search_params = {
                **ncbi_id,
                "db": "pubmed",
                "term": f"{query} AND hospital medicine[MeSH]",
                "retmax": max_results,
                "retmode": "json",
                "sort": "relevance",
            }
            with httpx.Client(timeout=30) as client:
                resp = client.get(f"{base_url}/esearch.fcgi", params=search_params)
                resp.raise_for_status()
                search_data = resp.json()

            pmids = search_data.get("esearchresult", {}).get("idlist", [])
            if not pmids:
                return []

            # Step 2: Fetch summaries
            time.sleep(0.34)  # Rate limit
            summary_params = {
                **ncbi_id,
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "json",
            }
            with httpx.Client(timeout=30) as client:
                resp = client.get(f"{base_url}/esummary.fcgi", params=summary_params)
                resp.raise_for_status()
                summary_data = resp.json()

            for pmid in pmids:
                article = summary_data.get("result", {}).get(pmid, {})
                if not article or not isinstance(article, dict):
                    continue

                title = article.get("title", "")
                source = article.get("source", "")
                pubdate = article.get("pubdate", "")

                result = OnlineResult(
                    result_id=f"PUBMED-{pmid}",
                    query=query,
                    source="pubmed",
                    title=title,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    snippet=f"{source}. {pubdate}.",
                    date_found=datetime.now(timezone.utc).isoformat(),
                    tags=["#registry-data", f"#recent-{pubdate[:4]}"] if pubdate else [],
                )
                results.append(result)

        except Exception as e:
            print(f"  [!] PubMed search error: {e}", file=sys.stderr)

        return results

    def search_shm(self, query: str) -> list[OnlineResult]:
        """Search SHM.org for conference content and resources.

        Uses web scraping of publicly available SHM content.
        """
        try:
            import httpx
        except ImportError:
            return []

        results = []
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                # SHM search endpoint
                resp = client.get(
                    "https://www.hospitalmedicine.org/",
                    params={"s": query},
                )
                resp.raise_for_status()
                # Parse basic results from response
                # (simple extraction — full scraping would need beautifulsoup)
                text = resp.text
                title_re = re.compile(r'<h[23][^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>')
                for match in list(title_re.finditer(text))[:10]:
                    url, title = match.groups()
                    results.append(OnlineResult(
                        result_id=f"SHM-{hashlib.md5(url.encode()).hexdigest()[:8]}",
                        query=query,
                        source="shm",
                        title=title.strip(),
                        url=url if url.startswith("http") else f"https://www.hospitalmedicine.org{url}",
                        snippet="",
                        date_found=datetime.now(timezone.utc).isoformat(),
                        tags=["#quality-improvement"],
                    ))
        except Exception as e:
            print(f"  [!] SHM search error: {e}", file=sys.stderr)

        return results

    def collect_cycle(self, topics: list[str] | None = None) -> list[OnlineResult]:
        """Run one collection cycle across all sources.

        Searches a rotating subset of SHM topics to stay within rate limits.
        """
        topics = topics or SHM_TOPICS
        # Rotate: pick 3 topics per cycle to avoid hammering APIs
        import random
        selected = random.sample(topics, min(3, len(topics)))

        all_results = []
        for topic in selected:
            print(f"  Searching: {topic}")

            # Check cache
            cache_key = hashlib.md5(topic.encode()).hexdigest()
            cache_file = self._cache_dir / f"{cache_key}.json"
            if cache_file.exists():
                age_hours = (
                    time.time() - cache_file.stat().st_mtime
                ) / 3600
                if age_hours < 24:
                    print(f"    (cached, {age_hours:.1f}h old)")
                    continue

            # PubMed search
            results = self.search_pubmed(topic, max_results=10)
            all_results.extend(results)
            time.sleep(0.5)  # Be nice to NCBI

            # SHM search
            shm_results = self.search_shm(topic)
            all_results.extend(shm_results)

            # Cache results
            with open(cache_file, "w") as f:
                json.dump({
                    "topic": topic,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "results": [r.to_dict() for r in results + shm_results],
                }, f, indent=2)

            time.sleep(1)  # Rate limit between topics

        # Append to results file
        if all_results:
            with open(self._results_file, "a") as f:
                for r in all_results:
                    f.write(json.dumps(r.to_dict()) + "\n")

        return all_results

    def get_all_results(self, limit: int = 100) -> list[dict[str, Any]]:
        """Read all collected online results."""
        if not self._results_file.exists():
            return []
        results = []
        with open(self._results_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                    if len(results) >= limit:
                        break
        return results


# ─── Statistics ───────────────────────────────────────────────────────────────

def load_stats() -> PipelineStats:
    """Load pipeline stats from disk. Returns empty stats on corrupt file."""
    if STATS_FILE.exists():
        try:
            with open(STATS_FILE) as f:
                data = json.load(f)
            return PipelineStats(**data)
        except (json.JSONDecodeError, IOError, TypeError) as exc:
            print(f"  [!] Corrupt pipeline_stats.json, using defaults: {exc}",
                  file=sys.stderr)
    return PipelineStats()


def save_stats(stats: PipelineStats) -> None:
    """Save pipeline stats to disk."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATS_FILE, "w") as f:
        json.dump(stats.to_dict(), f, indent=2)


def update_stats(extracts: list[PDFExtract], stats: PipelineStats) -> PipelineStats:
    """Update stats from a batch of extracts."""
    for e in extracts:
        stats.total_pdfs_processed += 1
        stats.total_words += e.word_count
        stats.total_citations += len(e.citations)
        stats.total_statistics += len(e.statistics)
        stats.total_claims += len(e.key_claims)
        # Use real per-tool frequency from tool_mentions; fall back to
        # deduped tools_mentioned only for extracts written by the old
        # code path (one count per tool = PDF-mention count).
        mentions = e.tool_mentions or {tool: 1 for tool in e.tools_mentioned}
        for tool, count in mentions.items():
            stats.top_tools[tool] = stats.top_tools.get(tool, 0) + count
            stats.total_tool_mentions += count
    stats.last_pdf_run = datetime.now(timezone.utc).isoformat()
    return stats


# ─── Daemon ───────────────────────────────────────────────────────────────────

class SHMDaemon:
    """Background daemon that continuously collects SHM content."""

    def __init__(self, interval_seconds: int = 600) -> None:
        self._interval = interval_seconds
        self._collector = OnlineCollector(OUTPUT_DIR)
        self._stop_event = threading.Event()
        self._cycle_count = 0

    def run(self) -> None:
        """Run the daemon (blocking)."""
        print(f"\n  SHM Pipeline Daemon — collecting every {self._interval}s")
        print(f"  Output: {OUTPUT_DIR}")
        print(f"  Topics: {len(SHM_TOPICS)} tracked")
        print(f"  Press Ctrl+C to stop.\n")

        import signal
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, lambda *_: self._stop_event.set())

        while not self._stop_event.is_set():
            self._cycle_count += 1
            print(f"  ── Cycle {self._cycle_count} "
                  f"({datetime.now().strftime('%H:%M:%S')}) ──")

            try:
                results = self._collector.collect_cycle()
                print(f"  Collected {len(results)} new results")

                # Update stats
                stats = load_stats()
                stats.total_online_results += len(results)
                stats.online_searches_run += 1
                stats.last_online_run = datetime.now(timezone.utc).isoformat()
                save_stats(stats)

            except Exception as e:
                print(f"  [!] Cycle error: {e}", file=sys.stderr)

            self._stop_event.wait(timeout=self._interval)

        print("\n  Daemon stopped.")


# ─── Skill Manifest ──────────────────────────────────────────────────────────

def skill_manifest() -> dict[str, Any]:
    """Return the skill manifest for AI dispatch integration."""
    return {
        "agent": "shm_pipeline",
        "version": "1.0.0",
        "description": (
            "SHM conference PDF processor + online hospital medicine content "
            "collector. Extracts citations, statistics, clinical tools, and "
            "evidence levels from PDFs. Daemon mode continuously collects "
            "PubMed and SHM content."
        ),
        "skills": [
            {
                "name": "process_pdfs",
                "description": "Extract structured data from conference PDFs",
                "params": {"directory": "path to PDF directory"},
                "returns": "list of PDFExtract objects",
            },
            {
                "name": "search_literature",
                "description": "Search PubMed + SHM for hospital medicine content",
                "params": {"query": "search terms", "max_results": "int (default 20)"},
                "returns": "list of OnlineResult objects",
            },
            {
                "name": "get_statistics",
                "description": "Pipeline processing statistics",
                "params": {},
                "returns": "PipelineStats object",
            },
            {
                "name": "collect_online",
                "description": "Run one online collection cycle (PubMed + SHM)",
                "params": {"topics": "optional topic list override"},
                "returns": "list of OnlineResult objects",
            },
            {
                "name": "export_all",
                "description": "Export all pipeline data (extracts + online results + stats) as JSON",
                "params": {},
                "returns": "dict with stats, extracts, online_results keys",
            },
        ],
        "daemon_modes": ["online_collector"],
        "data_sources": ["pubmed", "shm"],
        "output_dir": str(OUTPUT_DIR),
        "dispatch_roles": ["researcher", "gatherer"],
    }


# ─── Export ───────────────────────────────────────────────────────────────────

def export_pipeline_data() -> dict[str, Any]:
    """Export all pipeline data as a structured payload."""
    stats = load_stats()

    # Load all extracts
    extracts = []
    if OUTPUT_DIR.exists():
        for path in sorted(OUTPUT_DIR.glob("*.json")):
            if path.name in ("pipeline_stats.json",):
                continue
            try:
                with open(path) as f:
                    extracts.append(json.load(f))
            except (json.JSONDecodeError, IOError):
                continue

    # Load online results
    collector = OnlineCollector(OUTPUT_DIR)
    online = collector.get_all_results(limit=200)

    return {
        "pipeline": "shm_pipeline",
        "exported": datetime.now(timezone.utc).isoformat(),
        "stats": stats.to_dict(),
        "extracts": extracts,
        "online_results": online,
        "manifest": skill_manifest(),
    }


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SHM Pipeline — PDF processor + online collector")
    parser.add_argument("directory", nargs="?", default=None,
                        help="Directory of PDFs to process")
    parser.add_argument("--scan", action="store_true",
                        help="Scan default DOX directories")
    parser.add_argument("--daemon", action="store_true",
                        help="Start online collector daemon")
    parser.add_argument("--interval", type=int, default=600,
                        help="Daemon collection interval in seconds (default: 600)")
    parser.add_argument("--stats", action="store_true",
                        help="Show pipeline statistics")
    parser.add_argument("--search", type=str, default=None,
                        help="One-shot online search query")
    parser.add_argument("--export", action="store_true",
                        help="Export all pipeline data as JSON")
    parser.add_argument("--skill-manifest", action="store_true",
                        help="Print skill manifest for AI dispatch")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.skill_manifest:
        print(json.dumps(skill_manifest(), indent=2))
        return

    if args.stats:
        stats = load_stats()
        print("\n  SHM PIPELINE — STATISTICS")
        print("  " + "=" * 40)
        print(f"  PDFs processed:    {stats.total_pdfs_processed}")
        print(f"  Total words:       {stats.total_words:,}")
        print(f"  Citations:         {stats.total_citations:,}")
        print(f"  Statistics:        {stats.total_statistics:,}")
        print(f"  Key claims:        {stats.total_claims:,}")
        print(f"  Tool mentions:     {stats.total_tool_mentions:,}")
        print(f"  Online results:    {stats.total_online_results:,}")
        print(f"  Searches run:      {stats.online_searches_run}")
        if stats.top_tools:
            print(f"\n  Top clinical tools:")
            sorted_tools = sorted(stats.top_tools.items(), key=lambda x: -x[1])
            for tool, count in sorted_tools[:10]:
                print(f"    {tool:<16} {count}")
        if stats.last_pdf_run:
            print(f"\n  Last PDF run:      {stats.last_pdf_run}")
        if stats.last_online_run:
            print(f"  Last online run:   {stats.last_online_run}")
        print()
        return

    if args.search:
        collector = OnlineCollector(OUTPUT_DIR)
        print(f"\n  Searching: {args.search}")
        results = collector.search_pubmed(args.search)
        results.extend(collector.search_shm(args.search))
        print(f"  Found {len(results)} results:\n")
        for r in results:
            print(f"  [{r.source}] {r.title}")
            print(f"    {r.url}")
            if r.snippet:
                print(f"    {r.snippet}")
            print()

        # Update stats
        stats = load_stats()
        stats.total_online_results += len(results)
        stats.online_searches_run += 1
        stats.last_online_run = datetime.now(timezone.utc).isoformat()
        save_stats(stats)
        return

    if args.export:
        data = export_pipeline_data()
        print(json.dumps(data, indent=2))
        return

    if args.daemon:
        daemon = SHMDaemon(interval_seconds=args.interval)
        daemon.run()
        return

    # Process PDFs
    directories = []
    if args.directory:
        directories.append(Path(args.directory))
    elif args.scan:
        directories = [CONFERENCE_DOX, HOME_DOX]
    else:
        parser.print_help()
        return

    stats = load_stats()
    total_extracts = []

    for directory in directories:
        print(f"\n  Processing: {directory}")
        extracts = process_directory(directory)
        total_extracts.extend(extracts)
        print(f"  Extracted {len(extracts)} documents")

    if total_extracts:
        stats = update_stats(total_extracts, stats)
        save_stats(stats)

        # Write index
        with open(INDEX_FILE, "a") as f:
            for e in total_extracts:
                entry = {
                    "extract_id": e.extract_id,
                    "file": e.source_file,
                    "title": e.title[:80],
                    "words": e.word_count,
                    "citations": len(e.citations),
                    "tools": e.tools_mentioned,
                    "evidence": e.evidence_levels,
                    "tags": e.tags,
                }
                f.write(json.dumps(entry) + "\n")

        print(f"\n  Pipeline totals:")
        print(f"    Words: {stats.total_words:,}")
        print(f"    Citations: {stats.total_citations:,}")
        print(f"    Statistics: {stats.total_statistics:,}")
        print(f"    Claims: {stats.total_claims:,}")
        print(f"    Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
