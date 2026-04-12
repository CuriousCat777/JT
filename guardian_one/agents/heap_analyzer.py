"""Heap Analyzer — V8 Heap Snapshot Analysis Agent.

Responsibilities:
- Parse V8 .heapsnapshot files (Chrome/Node.js heap dumps)
- Parse companion -diagnostics.json files
- Identify top memory consumers by constructor/type
- Detect potential memory leaks (large retained sizes, detached DOM nodes)
- Analyze string duplication and overhead
- Produce actionable summaries with recommendations
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig


# ---------------------------------------------------------------------------
# V8 heap snapshot field indices (per the V8 serialization format)
# ---------------------------------------------------------------------------

# node_fields: type, name, id, self_size, edge_count, trace_node_id, detachedness
NODE_FIELD_COUNT = 7
NODE_TYPE_IX = 0
NODE_NAME_IX = 1
NODE_ID_IX = 2
NODE_SELF_SIZE_IX = 3
NODE_EDGE_COUNT_IX = 4
NODE_DETACHEDNESS_IX = 6

# edge_fields: type, name_or_index, to_node
EDGE_FIELD_COUNT = 3
EDGE_TYPE_IX = 0
EDGE_NAME_IX = 1
EDGE_TO_NODE_IX = 2


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class HeapNode:
    """A single node in the heap graph."""
    node_index: int
    node_type: str
    name: str
    node_id: int
    self_size: int
    edge_count: int
    detachedness: int = 0


@dataclass
class HeapSummary:
    """High-level statistics from a parsed heap snapshot."""
    snapshot_path: str
    total_nodes: int = 0
    total_edges: int = 0
    total_size_bytes: int = 0
    node_count_by_type: dict[str, int] = field(default_factory=dict)
    size_by_type: dict[str, int] = field(default_factory=dict)
    top_constructors: list[dict[str, Any]] = field(default_factory=list)
    top_objects: list[dict[str, Any]] = field(default_factory=list)
    duplicate_strings: list[dict[str, Any]] = field(default_factory=list)
    detached_nodes: int = 0
    large_objects: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    parse_time_ms: float = 0.0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class DiagnosticsInfo:
    """Parsed companion diagnostics JSON."""
    version: str = ""
    event: str = ""
    trigger: str = ""
    node_version: str = ""
    os_name: str = ""
    os_machine: str = ""
    heap_total_bytes: int = 0
    heap_used_bytes: int = 0
    rss_bytes: int = 0
    resource_usage: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class HeapSnapshotParser:
    """Parses V8 .heapsnapshot JSON files into queryable structures.

    V8 heap snapshot format stores nodes and edges as flat integer arrays
    with field metadata in the snapshot header. This parser reconstructs
    the object graph and computes aggregate statistics.
    """

    def __init__(self, snapshot_path: str | Path) -> None:
        self._path = Path(snapshot_path)
        self._raw: dict[str, Any] = {}
        self._nodes: list[HeapNode] = []
        self._strings: list[str] = []
        self._node_types: list[str] = []
        self._edge_types: list[str] = []
        self._node_fields: list[str] = []
        self._edge_fields: list[str] = []
        self._node_field_count: int = NODE_FIELD_COUNT
        self._edge_field_count: int = EDGE_FIELD_COUNT

    @property
    def path(self) -> Path:
        return self._path

    @property
    def nodes(self) -> list[HeapNode]:
        return self._nodes

    def load(self) -> None:
        """Load and parse the snapshot file."""
        if not self._path.exists():
            raise FileNotFoundError(f"Heap snapshot not found: {self._path}")
        if self._path.stat().st_size == 0:
            raise ValueError(f"Heap snapshot is empty: {self._path}")

        with open(self._path, "r", encoding="utf-8") as f:
            self._raw = json.load(f)

        self._parse_metadata()
        self._parse_nodes()

    def _parse_metadata(self) -> None:
        """Extract field definitions and string table from snapshot header."""
        snapshot_meta = self._raw.get("snapshot", {})
        meta = snapshot_meta.get("meta", {})

        self._node_fields = meta.get("node_fields", [])
        self._edge_fields = meta.get("edge_fields", [])
        self._strings = self._raw.get("strings", [])

        # node_types and edge_types are arrays-of-arrays; first element is the type list
        node_types_raw = meta.get("node_types", [])
        if node_types_raw and isinstance(node_types_raw[0], list):
            self._node_types = node_types_raw[0]
        elif node_types_raw:
            self._node_types = node_types_raw

        edge_types_raw = meta.get("edge_types", [])
        if edge_types_raw and isinstance(edge_types_raw[0], list):
            self._edge_types = edge_types_raw[0]
        elif edge_types_raw:
            self._edge_types = edge_types_raw

        if self._node_fields:
            self._node_field_count = len(self._node_fields)
        if self._edge_fields:
            self._edge_field_count = len(self._edge_fields)

    def _parse_nodes(self) -> None:
        """Walk the flat node array and build HeapNode objects."""
        nodes_arr = self._raw.get("nodes", [])
        fc = self._node_field_count
        total = len(nodes_arr)
        result: list[HeapNode] = []

        for i in range(0, total, fc):
            type_ix = nodes_arr[i + NODE_TYPE_IX] if (i + NODE_TYPE_IX) < total else 0
            name_ix = nodes_arr[i + NODE_NAME_IX] if (i + NODE_NAME_IX) < total else 0
            node_id = nodes_arr[i + NODE_ID_IX] if (i + NODE_ID_IX) < total else 0
            self_size = nodes_arr[i + NODE_SELF_SIZE_IX] if (i + NODE_SELF_SIZE_IX) < total else 0
            edge_count = nodes_arr[i + NODE_EDGE_COUNT_IX] if (i + NODE_EDGE_COUNT_IX) < total else 0
            detachedness = nodes_arr[i + NODE_DETACHEDNESS_IX] if (i + NODE_DETACHEDNESS_IX < total and fc > NODE_DETACHEDNESS_IX) else 0

            node_type = self._node_types[type_ix] if type_ix < len(self._node_types) else f"unknown({type_ix})"
            name = self._strings[name_ix] if name_ix < len(self._strings) else f"<string#{name_ix}>"

            result.append(HeapNode(
                node_index=i // fc,
                node_type=node_type,
                name=name,
                node_id=node_id,
                self_size=self_size,
                edge_count=edge_count,
                detachedness=detachedness,
            ))

        self._nodes = result

    def get_edge_count(self) -> int:
        """Return total edge count from snapshot metadata."""
        return self._raw.get("snapshot", {}).get("edge_count", 0)

    def get_node_count(self) -> int:
        """Return total node count from snapshot metadata."""
        return self._raw.get("snapshot", {}).get("node_count", 0)


# ---------------------------------------------------------------------------
# Diagnostics parser
# ---------------------------------------------------------------------------

def parse_diagnostics(path: str | Path) -> DiagnosticsInfo:
    """Parse a V8 diagnostics JSON companion file."""
    p = Path(path)
    if not p.exists():
        return DiagnosticsInfo()

    with open(p, "r", encoding="utf-8") as f:
        raw = json.load(f)

    info = DiagnosticsInfo(raw=raw)

    # Top-level fields (Node.js diagnostic report format)
    header = raw.get("header", raw)
    info.event = header.get("event", raw.get("event", ""))
    info.trigger = header.get("trigger", raw.get("trigger", ""))
    info.node_version = header.get("nodejsVersion", raw.get("nodejsVersion", ""))
    info.os_name = header.get("osName", raw.get("osName", ""))
    info.os_machine = header.get("osMachine", raw.get("osMachine", ""))

    # JS heap from either javascriptHeap or resourceUsage
    js_heap = raw.get("javascriptHeap", {})
    if js_heap:
        info.heap_total_bytes = js_heap.get("totalMemory", 0)
        info.heap_used_bytes = js_heap.get("usedMemory", js_heap.get("totalCommitted", 0))

    res = raw.get("resourceUsage", {})
    if res:
        info.resource_usage = res
        info.rss_bytes = res.get("rss", 0)

    # Flat structure fallback
    if not info.heap_total_bytes:
        info.heap_total_bytes = raw.get("heapTotal", raw.get("heap_total", 0))
    if not info.heap_used_bytes:
        info.heap_used_bytes = raw.get("heapUsed", raw.get("heap_used", 0))
    if not info.rss_bytes:
        info.rss_bytes = raw.get("rss", 0)

    return info


# ---------------------------------------------------------------------------
# Analyzer (stateless functions operating on parsed data)
# ---------------------------------------------------------------------------

def _format_bytes(n: int) -> str:
    """Human-readable byte size."""
    if n < 1024:
        return f"{n} B"
    elif n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    elif n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    else:
        return f"{n / 1024 ** 3:.2f} GB"


def compute_summary(
    parser: HeapSnapshotParser,
    diagnostics: DiagnosticsInfo | None = None,
    top_n: int = 20,
    large_object_threshold: int = 1024 * 1024,  # 1 MB
) -> HeapSummary:
    """Compute aggregate statistics from a parsed heap snapshot.

    Args:
        parser: A loaded HeapSnapshotParser.
        diagnostics: Optional companion diagnostics info.
        top_n: Number of top entries to include in rankings.
        large_object_threshold: Byte size to flag an object as 'large'.

    Returns:
        HeapSummary with statistics and recommendations.
    """
    summary = HeapSummary(snapshot_path=str(parser.path))
    nodes = parser.nodes

    summary.total_nodes = len(nodes)
    summary.total_edges = parser.get_edge_count()

    # --- aggregate by type ---
    type_counts: dict[str, int] = {}
    type_sizes: dict[str, int] = {}
    constructor_sizes: dict[str, int] = {}
    constructor_counts: dict[str, int] = {}
    string_values: dict[str, int] = {}
    detached = 0
    large: list[dict[str, Any]] = []
    total_size = 0

    for node in nodes:
        total_size += node.self_size

        type_counts[node.node_type] = type_counts.get(node.node_type, 0) + 1
        type_sizes[node.node_type] = type_sizes.get(node.node_type, 0) + node.self_size

        # Constructor-level grouping (name for object/closure types)
        if node.node_type in ("object", "closure", "regexp"):
            key = node.name or "(anonymous)"
            constructor_sizes[key] = constructor_sizes.get(key, 0) + node.self_size
            constructor_counts[key] = constructor_counts.get(key, 0) + 1

        # String duplication tracking
        if node.node_type == "string" and node.name:
            string_values[node.name] = string_values.get(node.name, 0) + 1

        # Detached nodes
        if node.detachedness and node.detachedness > 0:
            detached += 1

        # Large objects
        if node.self_size >= large_object_threshold:
            large.append({
                "name": node.name,
                "type": node.node_type,
                "size": node.self_size,
                "size_human": _format_bytes(node.self_size),
                "id": node.node_id,
            })

    summary.total_size_bytes = total_size
    summary.node_count_by_type = dict(sorted(type_counts.items(), key=lambda x: -x[1]))
    summary.size_by_type = dict(sorted(type_sizes.items(), key=lambda x: -x[1]))
    summary.detached_nodes = detached

    # Top constructors by total size
    sorted_ctors = sorted(constructor_sizes.items(), key=lambda x: -x[1])[:top_n]
    summary.top_constructors = [
        {
            "name": name,
            "total_size": size,
            "total_size_human": _format_bytes(size),
            "count": constructor_counts[name],
            "avg_size": size // max(constructor_counts[name], 1),
        }
        for name, size in sorted_ctors
    ]

    # Top individual objects by self_size
    sorted_objects = sorted(nodes, key=lambda n: -n.self_size)[:top_n]
    summary.top_objects = [
        {
            "name": n.name,
            "type": n.node_type,
            "self_size": n.self_size,
            "self_size_human": _format_bytes(n.self_size),
            "id": n.node_id,
        }
        for n in sorted_objects
    ]

    # Duplicate strings (only those appearing 3+ times)
    dupes = [(s, c) for s, c in string_values.items() if c >= 3]
    dupes.sort(key=lambda x: -x[1])
    summary.duplicate_strings = [
        {"value": s[:120], "count": c, "est_waste": _format_bytes(len(s.encode("utf-8", "replace")) * (c - 1))}
        for s, c in dupes[:top_n]
    ]

    # Large objects sorted by size
    large.sort(key=lambda x: -x["size"])
    summary.large_objects = large[:top_n]

    # Diagnostics
    if diagnostics:
        summary.diagnostics = {
            "event": diagnostics.event,
            "trigger": diagnostics.trigger,
            "node_version": diagnostics.node_version,
            "os": f"{diagnostics.os_name} {diagnostics.os_machine}".strip(),
            "heap_total": _format_bytes(diagnostics.heap_total_bytes),
            "heap_used": _format_bytes(diagnostics.heap_used_bytes),
            "rss": _format_bytes(diagnostics.rss_bytes),
        }

    # --- Recommendations ---
    recs: list[str] = []
    if detached > 0:
        recs.append(
            f"Found {detached} detached node(s) — possible DOM/listener leaks. "
            "Investigate event listeners and element references that survive removal."
        )
    if len(large) > 0:
        recs.append(
            f"{len(large)} object(s) exceed {_format_bytes(large_object_threshold)}. "
            "Consider streaming, pagination, or lazy loading for large data."
        )
    if dupes:
        top_dupe = dupes[0]
        recs.append(
            f"String '{top_dupe[0][:40]}' is duplicated {top_dupe[1]} times. "
            "String interning or constants could reduce memory waste."
        )
    # Type-specific checks
    closure_size = type_sizes.get("closure", 0)
    if closure_size > total_size * 0.3 and total_size > 0:
        recs.append(
            f"Closures account for {closure_size / total_size * 100:.0f}% of heap. "
            "Review function scoping — closures may be capturing unneeded variables."
        )
    array_size = type_sizes.get("array", 0)
    if array_size > total_size * 0.4 and total_size > 0:
        recs.append(
            f"Arrays account for {array_size / total_size * 100:.0f}% of heap. "
            "Check for unbounded caches, logs, or accumulator arrays."
        )
    if not recs:
        recs.append("No major concerns detected. Heap distribution looks healthy.")

    summary.recommendations = recs
    return summary


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class HeapAnalyzer(BaseAgent):
    """Guardian One agent for analyzing V8 heap snapshots.

    Accepts .heapsnapshot files and optional -diagnostics.json companions,
    producing structured memory analysis reports with recommendations.
    """

    def __init__(
        self,
        config: AgentConfig,
        audit: AuditLog,
    ) -> None:
        super().__init__(config=config, audit=audit)
        self._last_summary: HeapSummary | None = None

    def initialize(self) -> None:
        self.log("heap_analyzer_ready")

    def run(self) -> AgentReport:
        """No-op periodic run — analysis is triggered via analyze()."""
        return self.report()

    def report(self) -> AgentReport:
        if self._last_summary:
            s = self._last_summary
            return AgentReport(
                agent_name=self.name,
                status="ok",
                summary=(
                    f"Last analysis: {s.snapshot_path} — "
                    f"{s.total_nodes:,} nodes, {_format_bytes(s.total_size_bytes)}"
                ),
                recommendations=s.recommendations,
                data={"summary": _summary_to_dict(s)},
            )
        return AgentReport(
            agent_name=self.name,
            status="idle",
            summary="No heap snapshot analyzed yet.",
        )

    def analyze(
        self,
        snapshot_path: str | Path,
        diagnostics_path: str | Path | None = None,
        top_n: int = 20,
        large_threshold: int = 1024 * 1024,
    ) -> HeapSummary:
        """Analyze a V8 heap snapshot file.

        Args:
            snapshot_path: Path to .heapsnapshot file.
            diagnostics_path: Optional companion -diagnostics.json.
            top_n: Number of top entries per category.
            large_threshold: Byte threshold for flagging large objects.

        Returns:
            HeapSummary with full analysis results.
        """
        import time as _time

        self._set_status(AgentStatus.RUNNING)
        self.log("analyze_start", details={"path": str(snapshot_path)})

        t0 = _time.monotonic()

        try:
            parser = HeapSnapshotParser(snapshot_path)
            parser.load()

            diag = None
            if diagnostics_path:
                diag = parse_diagnostics(diagnostics_path)

            summary = compute_summary(
                parser,
                diagnostics=diag,
                top_n=top_n,
                large_object_threshold=large_threshold,
            )
            summary.parse_time_ms = (_time.monotonic() - t0) * 1000

            self._last_summary = summary
            self._set_status(AgentStatus.IDLE)

            self.log(
                "analyze_complete",
                details={
                    "nodes": summary.total_nodes,
                    "total_size": summary.total_size_bytes,
                    "parse_ms": round(summary.parse_time_ms, 1),
                    "recommendations": len(summary.recommendations),
                },
            )
            return summary

        except Exception as exc:
            self._set_status(AgentStatus.ERROR)
            self.log(
                "analyze_error",
                severity=Severity.ERROR,
                details={"error": str(exc), "path": str(snapshot_path)},
            )
            raise


def _summary_to_dict(s: HeapSummary) -> dict[str, Any]:
    """Convert a HeapSummary to a JSON-serializable dict."""
    return {
        "snapshot_path": s.snapshot_path,
        "total_nodes": s.total_nodes,
        "total_edges": s.total_edges,
        "total_size_bytes": s.total_size_bytes,
        "total_size_human": _format_bytes(s.total_size_bytes),
        "node_count_by_type": s.node_count_by_type,
        "size_by_type": {k: {"bytes": v, "human": _format_bytes(v)} for k, v in s.size_by_type.items()},
        "top_constructors": s.top_constructors,
        "top_objects": s.top_objects,
        "duplicate_strings": s.duplicate_strings,
        "detached_nodes": s.detached_nodes,
        "large_objects": s.large_objects,
        "diagnostics": s.diagnostics,
        "recommendations": s.recommendations,
        "parse_time_ms": round(s.parse_time_ms, 1),
        "timestamp": s.timestamp,
    }


# ---------------------------------------------------------------------------
# CLI formatting helpers
# ---------------------------------------------------------------------------

def print_heap_report(summary: HeapSummary) -> None:
    """Pretty-print a HeapSummary to stdout."""
    print()
    print("=" * 70)
    print("  HEAP SNAPSHOT ANALYSIS — Guardian One")
    print("=" * 70)
    print(f"  File:       {summary.snapshot_path}")
    print(f"  Parsed:     {summary.timestamp}")
    print(f"  Parse time: {summary.parse_time_ms:.0f} ms")
    print()

    # Diagnostics
    if summary.diagnostics:
        d = summary.diagnostics
        print("  RUNTIME DIAGNOSTICS")
        print("  " + "-" * 40)
        if d.get("node_version"):
            print(f"  Node.js:    {d['node_version']}")
        if d.get("os"):
            print(f"  OS:         {d['os']}")
        if d.get("event"):
            print(f"  Event:      {d['event']}")
        if d.get("trigger"):
            print(f"  Trigger:    {d['trigger']}")
        if d.get("heap_total"):
            print(f"  Heap total: {d['heap_total']}")
        if d.get("heap_used"):
            print(f"  Heap used:  {d['heap_used']}")
        if d.get("rss"):
            print(f"  RSS:        {d['rss']}")
        print()

    # Overview
    print("  HEAP OVERVIEW")
    print("  " + "-" * 40)
    print(f"  Total nodes:    {summary.total_nodes:>12,}")
    print(f"  Total edges:    {summary.total_edges:>12,}")
    print(f"  Total size:     {_format_bytes(summary.total_size_bytes):>12}")
    print(f"  Detached nodes: {summary.detached_nodes:>12,}")
    print()

    # Size by type
    print("  SIZE BY NODE TYPE")
    print("  " + "-" * 50)
    print(f"  {'Type':<20} {'Count':>10} {'Size':>12} {'%':>6}")
    print("  " + "-" * 50)
    total = max(summary.total_size_bytes, 1)
    for ntype, size in list(summary.size_by_type.items())[:12]:
        count = summary.node_count_by_type.get(ntype, 0)
        pct = size / total * 100
        print(f"  {ntype:<20} {count:>10,} {_format_bytes(size):>12} {pct:>5.1f}%")
    print()

    # Top constructors
    if summary.top_constructors:
        print("  TOP CONSTRUCTORS (by total size)")
        print("  " + "-" * 60)
        print(f"  {'Constructor':<30} {'Count':>8} {'Total':>10} {'Avg':>10}")
        print("  " + "-" * 60)
        for c in summary.top_constructors[:15]:
            print(
                f"  {c['name'][:29]:<30} {c['count']:>8,} "
                f"{c['total_size_human']:>10} {_format_bytes(c['avg_size']):>10}"
            )
        print()

    # Top individual objects
    if summary.top_objects:
        print("  TOP OBJECTS (by self size)")
        print("  " + "-" * 60)
        print(f"  {'Name':<35} {'Type':<12} {'Size':>10}")
        print("  " + "-" * 60)
        for o in summary.top_objects[:15]:
            name = o["name"][:34] if o["name"] else "(anonymous)"
            print(f"  {name:<35} {o['type']:<12} {o['self_size_human']:>10}")
        print()

    # Large objects
    if summary.large_objects:
        print("  LARGE OBJECTS (>= 1 MB)")
        print("  " + "-" * 50)
        for o in summary.large_objects[:10]:
            name = o["name"][:40] if o["name"] else "(anonymous)"
            print(f"  {name:<40} {o['size_human']:>10}")
        print()

    # Duplicate strings
    if summary.duplicate_strings:
        print("  DUPLICATE STRINGS (3+ occurrences)")
        print("  " + "-" * 60)
        print(f"  {'Value':<40} {'Count':>8} {'Est. Waste':>10}")
        print("  " + "-" * 60)
        for s in summary.duplicate_strings[:10]:
            val = s["value"][:39]
            print(f"  {val:<40} {s['count']:>8,} {s['est_waste']:>10}")
        print()

    # Recommendations
    print("  RECOMMENDATIONS")
    print("  " + "-" * 50)
    for i, rec in enumerate(summary.recommendations, 1):
        print(f"  {i}. {rec}")
    print()
    print("=" * 70)
