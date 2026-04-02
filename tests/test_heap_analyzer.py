"""Tests for the Heap Analyzer agent — V8 .heapsnapshot parsing and analysis."""

import json
import tempfile
from pathlib import Path

import pytest

from guardian_one.core.audit import AuditLog
from guardian_one.core.base_agent import AgentStatus
from guardian_one.core.config import AgentConfig
from guardian_one.agents.heap_analyzer import (
    HeapAnalyzer,
    HeapNode,
    HeapSnapshotParser,
    HeapSummary,
    DiagnosticsInfo,
    compute_summary,
    parse_diagnostics,
    print_heap_report,
    _format_bytes,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


def _make_analyzer() -> HeapAnalyzer:
    return HeapAnalyzer(AgentConfig(name="heap_analyzer"), _make_audit())


def _minimal_snapshot(
    nodes: list[int] | None = None,
    strings: list[str] | None = None,
    node_count: int | None = None,
    edge_count: int = 0,
) -> dict:
    """Build a minimal valid V8 heap snapshot dict.

    Default: one node of type 'object', name 'Foo', id=1, self_size=128,
    edge_count=0, trace_node_id=0, detachedness=0.
    """
    if strings is None:
        strings = ["", "Foo", "bar"]
    if nodes is None:
        # type=3 (object), name=1 (Foo), id=1, self_size=128, edges=0, trace=0, detached=0
        nodes = [3, 1, 1, 128, 0, 0, 0]

    return {
        "snapshot": {
            "meta": {
                "node_fields": [
                    "type", "name", "id", "self_size",
                    "edge_count", "trace_node_id", "detachedness",
                ],
                "node_types": [
                    ["hidden", "array", "string", "object", "code",
                     "closure", "regexp", "number", "native",
                     "synthetic", "concatenated string", "sliced string",
                     "symbol", "bigint"],
                    "string", "number", "number", "number", "number", "number",
                ],
                "edge_fields": ["type", "name_or_index", "to_node"],
                "edge_types": [
                    ["context", "element", "property", "internal",
                     "hidden", "shortcut", "weak"],
                    "string_or_number", "node",
                ],
            },
            "node_count": node_count if node_count is not None else len(nodes) // 7,
            "edge_count": edge_count,
        },
        "nodes": nodes,
        "edges": [],
        "strings": strings,
    }


def _write_snapshot(tmp: Path, data: dict) -> Path:
    p = tmp / "test.heapsnapshot"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _write_diagnostics(tmp: Path, data: dict) -> Path:
    p = tmp / "test-diagnostics.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# _format_bytes
# ---------------------------------------------------------------------------

class TestFormatBytes:
    def test_bytes(self):
        assert _format_bytes(0) == "0 B"
        assert _format_bytes(512) == "512 B"

    def test_kilobytes(self):
        assert _format_bytes(1024) == "1.0 KB"
        assert _format_bytes(2048) == "2.0 KB"

    def test_megabytes(self):
        assert _format_bytes(1024 ** 2) == "1.0 MB"
        assert _format_bytes(int(1.5 * 1024 ** 2)) == "1.5 MB"

    def test_gigabytes(self):
        assert _format_bytes(1024 ** 3) == "1.00 GB"


# ---------------------------------------------------------------------------
# HeapSnapshotParser
# ---------------------------------------------------------------------------

class TestHeapSnapshotParser:
    def test_load_minimal(self, tmp_path):
        snap = _minimal_snapshot()
        p = _write_snapshot(tmp_path, snap)
        parser = HeapSnapshotParser(p)
        parser.load()

        assert len(parser.nodes) == 1
        node = parser.nodes[0]
        assert node.node_type == "object"
        assert node.name == "Foo"
        assert node.self_size == 128
        assert node.node_id == 1

    def test_multiple_nodes(self, tmp_path):
        nodes = [
            3, 1, 1, 128, 0, 0, 0,   # object "Foo" 128B
            2, 2, 2, 64, 0, 0, 0,     # string "bar" 64B
            5, 1, 3, 256, 0, 0, 0,    # closure "Foo" 256B
        ]
        snap = _minimal_snapshot(nodes=nodes, node_count=3)
        p = _write_snapshot(tmp_path, snap)
        parser = HeapSnapshotParser(p)
        parser.load()

        assert len(parser.nodes) == 3
        assert parser.nodes[0].node_type == "object"
        assert parser.nodes[1].node_type == "string"
        assert parser.nodes[2].node_type == "closure"

    def test_file_not_found(self):
        parser = HeapSnapshotParser("/nonexistent/file.heapsnapshot")
        with pytest.raises(FileNotFoundError):
            parser.load()

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.heapsnapshot"
        p.write_text("", encoding="utf-8")
        parser = HeapSnapshotParser(p)
        with pytest.raises(ValueError, match="empty"):
            parser.load()

    def test_edge_and_node_counts(self, tmp_path):
        snap = _minimal_snapshot(edge_count=42, node_count=1)
        p = _write_snapshot(tmp_path, snap)
        parser = HeapSnapshotParser(p)
        parser.load()

        assert parser.get_edge_count() == 42
        assert parser.get_node_count() == 1

    def test_detached_node(self, tmp_path):
        # detachedness = 1 (last field)
        nodes = [3, 1, 1, 128, 0, 0, 1]
        snap = _minimal_snapshot(nodes=nodes)
        p = _write_snapshot(tmp_path, snap)
        parser = HeapSnapshotParser(p)
        parser.load()

        assert parser.nodes[0].detachedness == 1

    def test_unknown_type_index(self, tmp_path):
        # type index 99 doesn't exist in node_types
        nodes = [99, 1, 1, 64, 0, 0, 0]
        snap = _minimal_snapshot(nodes=nodes)
        p = _write_snapshot(tmp_path, snap)
        parser = HeapSnapshotParser(p)
        parser.load()

        assert "unknown" in parser.nodes[0].node_type

    def test_path_property(self, tmp_path):
        snap = _minimal_snapshot()
        p = _write_snapshot(tmp_path, snap)
        parser = HeapSnapshotParser(p)
        assert parser.path == p


# ---------------------------------------------------------------------------
# parse_diagnostics
# ---------------------------------------------------------------------------

class TestParseDiagnostics:
    def test_node_report_format(self, tmp_path):
        data = {
            "header": {
                "event": "HeapSnapshot",
                "trigger": "manual",
                "nodejsVersion": "v20.11.0",
                "osName": "Linux",
                "osMachine": "x86_64",
            },
            "javascriptHeap": {
                "totalMemory": 50_000_000,
                "usedMemory": 30_000_000,
            },
            "resourceUsage": {
                "rss": 100_000_000,
            },
        }
        p = _write_diagnostics(tmp_path, data)
        info = parse_diagnostics(p)

        assert info.event == "HeapSnapshot"
        assert info.trigger == "manual"
        assert info.node_version == "v20.11.0"
        assert info.os_name == "Linux"
        assert info.os_machine == "x86_64"
        assert info.heap_total_bytes == 50_000_000
        assert info.heap_used_bytes == 30_000_000
        assert info.rss_bytes == 100_000_000

    def test_flat_format(self, tmp_path):
        data = {
            "event": "OOM",
            "heapTotal": 80_000_000,
            "heapUsed": 75_000_000,
            "rss": 120_000_000,
        }
        p = _write_diagnostics(tmp_path, data)
        info = parse_diagnostics(p)

        assert info.event == "OOM"
        assert info.heap_total_bytes == 80_000_000
        assert info.heap_used_bytes == 75_000_000
        assert info.rss_bytes == 120_000_000

    def test_missing_file(self):
        info = parse_diagnostics("/nonexistent/diag.json")
        assert info.event == ""
        assert info.heap_total_bytes == 0

    def test_raw_preserved(self, tmp_path):
        data = {"event": "test", "custom_field": 42}
        p = _write_diagnostics(tmp_path, data)
        info = parse_diagnostics(p)
        assert info.raw["custom_field"] == 42


# ---------------------------------------------------------------------------
# compute_summary
# ---------------------------------------------------------------------------

class TestComputeSummary:
    def _load_parser(self, tmp_path, snap_data):
        p = _write_snapshot(tmp_path, snap_data)
        parser = HeapSnapshotParser(p)
        parser.load()
        return parser

    def test_basic_summary(self, tmp_path):
        snap = _minimal_snapshot()
        parser = self._load_parser(tmp_path, snap)
        summary = compute_summary(parser)

        assert summary.total_nodes == 1
        assert summary.total_size_bytes == 128
        assert "object" in summary.node_count_by_type
        assert summary.node_count_by_type["object"] == 1

    def test_size_by_type(self, tmp_path):
        nodes = [
            3, 1, 1, 100, 0, 0, 0,  # object 100B
            3, 2, 2, 200, 0, 0, 0,  # object 200B
            2, 1, 3, 50, 0, 0, 0,   # string 50B
        ]
        snap = _minimal_snapshot(nodes=nodes, node_count=3)
        parser = self._load_parser(tmp_path, snap)
        summary = compute_summary(parser)

        assert summary.total_size_bytes == 350
        assert summary.size_by_type["object"] == 300
        assert summary.size_by_type["string"] == 50

    def test_top_constructors(self, tmp_path):
        nodes = [
            3, 1, 1, 500, 0, 0, 0,  # object "Foo" 500B
            3, 1, 2, 300, 0, 0, 0,  # object "Foo" 300B
            3, 2, 3, 100, 0, 0, 0,  # object "bar" 100B
        ]
        snap = _minimal_snapshot(nodes=nodes, node_count=3)
        parser = self._load_parser(tmp_path, snap)
        summary = compute_summary(parser)

        assert len(summary.top_constructors) >= 2
        # Foo should be first (800B total)
        assert summary.top_constructors[0]["name"] == "Foo"
        assert summary.top_constructors[0]["total_size"] == 800
        assert summary.top_constructors[0]["count"] == 2

    def test_detached_nodes_counted(self, tmp_path):
        nodes = [
            3, 1, 1, 128, 0, 0, 1,  # detached
            3, 2, 2, 64, 0, 0, 0,   # normal
            3, 1, 3, 32, 0, 0, 1,   # detached
        ]
        snap = _minimal_snapshot(nodes=nodes, node_count=3)
        parser = self._load_parser(tmp_path, snap)
        summary = compute_summary(parser)

        assert summary.detached_nodes == 2
        assert any("detached" in r.lower() for r in summary.recommendations)

    def test_large_objects_flagged(self, tmp_path):
        big = 2 * 1024 * 1024  # 2MB
        nodes = [3, 1, 1, big, 0, 0, 0]
        snap = _minimal_snapshot(nodes=nodes)
        parser = self._load_parser(tmp_path, snap)
        summary = compute_summary(parser)

        assert len(summary.large_objects) == 1
        assert summary.large_objects[0]["size"] == big
        assert any("exceed" in r.lower() or "large" in r.lower() for r in summary.recommendations)

    def test_custom_large_threshold(self, tmp_path):
        nodes = [3, 1, 1, 500, 0, 0, 0]
        snap = _minimal_snapshot(nodes=nodes)
        parser = self._load_parser(tmp_path, snap)
        # threshold 100 => 500B object should be flagged
        summary = compute_summary(parser, large_object_threshold=100)
        assert len(summary.large_objects) == 1

    def test_duplicate_strings(self, tmp_path):
        # 5 string nodes all with name index 1 ("Foo")
        nodes = []
        for i in range(5):
            nodes.extend([2, 1, i + 1, 20, 0, 0, 0])
        snap = _minimal_snapshot(nodes=nodes, node_count=5)
        parser = self._load_parser(tmp_path, snap)
        summary = compute_summary(parser)

        assert len(summary.duplicate_strings) >= 1
        assert summary.duplicate_strings[0]["value"] == "Foo"
        assert summary.duplicate_strings[0]["count"] == 5

    def test_no_duplicates_below_threshold(self, tmp_path):
        # 2 strings with same name — below 3-occurrence threshold
        nodes = [
            2, 1, 1, 20, 0, 0, 0,
            2, 1, 2, 20, 0, 0, 0,
        ]
        snap = _minimal_snapshot(nodes=nodes, node_count=2)
        parser = self._load_parser(tmp_path, snap)
        summary = compute_summary(parser)

        assert len(summary.duplicate_strings) == 0

    def test_top_objects_sorted(self, tmp_path):
        nodes = [
            3, 1, 1, 50, 0, 0, 0,
            3, 2, 2, 999, 0, 0, 0,
            3, 1, 3, 200, 0, 0, 0,
        ]
        snap = _minimal_snapshot(nodes=nodes, node_count=3)
        parser = self._load_parser(tmp_path, snap)
        summary = compute_summary(parser)

        assert summary.top_objects[0]["self_size"] == 999
        assert summary.top_objects[1]["self_size"] == 200

    def test_diagnostics_included(self, tmp_path):
        snap = _minimal_snapshot()
        parser = self._load_parser(tmp_path, snap)
        diag = DiagnosticsInfo(
            event="HeapSnapshot",
            node_version="v20.11.0",
            heap_total_bytes=50_000_000,
            heap_used_bytes=30_000_000,
        )
        summary = compute_summary(parser, diagnostics=diag)

        assert summary.diagnostics["event"] == "HeapSnapshot"
        assert summary.diagnostics["node_version"] == "v20.11.0"

    def test_healthy_heap_recommendation(self, tmp_path):
        nodes = [3, 1, 1, 128, 0, 0, 0]
        snap = _minimal_snapshot(nodes=nodes)
        parser = self._load_parser(tmp_path, snap)
        summary = compute_summary(parser)

        assert any("healthy" in r.lower() or "no major" in r.lower() for r in summary.recommendations)

    def test_closure_heavy_recommendation(self, tmp_path):
        # All closures — should trigger the closure warning
        nodes = []
        for i in range(10):
            nodes.extend([5, 1, i + 1, 100, 0, 0, 0])  # type 5 = closure
        snap = _minimal_snapshot(nodes=nodes, node_count=10)
        parser = self._load_parser(tmp_path, snap)
        summary = compute_summary(parser)

        assert any("closure" in r.lower() for r in summary.recommendations)

    def test_array_heavy_recommendation(self, tmp_path):
        # All arrays — should trigger the array warning
        nodes = []
        for i in range(10):
            nodes.extend([1, 1, i + 1, 100, 0, 0, 0])  # type 1 = array
        snap = _minimal_snapshot(nodes=nodes, node_count=10)
        parser = self._load_parser(tmp_path, snap)
        summary = compute_summary(parser)

        assert any("array" in r.lower() for r in summary.recommendations)

    def test_top_n_limits(self, tmp_path):
        nodes = []
        strings = [""]
        for i in range(50):
            strings.append(f"Obj{i}")
            nodes.extend([3, i + 1, i + 1, (i + 1) * 10, 0, 0, 0])
        snap = _minimal_snapshot(nodes=nodes, strings=strings, node_count=50)
        parser = self._load_parser(tmp_path, snap)
        summary = compute_summary(parser, top_n=5)

        assert len(summary.top_constructors) <= 5
        assert len(summary.top_objects) <= 5


# ---------------------------------------------------------------------------
# HeapAnalyzer agent
# ---------------------------------------------------------------------------

class TestHeapAnalyzerAgent:
    def test_initialize(self):
        analyzer = _make_analyzer()
        analyzer.initialize()
        assert analyzer.status == AgentStatus.IDLE

    def test_report_before_analysis(self):
        analyzer = _make_analyzer()
        analyzer.initialize()
        report = analyzer.report()

        assert report.agent_name == "heap_analyzer"
        assert report.status == "idle"
        assert "No heap snapshot" in report.summary

    def test_analyze_produces_summary(self, tmp_path):
        snap = _minimal_snapshot()
        p = _write_snapshot(tmp_path, snap)
        analyzer = _make_analyzer()
        analyzer.initialize()

        summary = analyzer.analyze(p)

        assert isinstance(summary, HeapSummary)
        assert summary.total_nodes == 1
        assert summary.total_size_bytes == 128
        assert summary.parse_time_ms > 0

    def test_report_after_analysis(self, tmp_path):
        snap = _minimal_snapshot()
        p = _write_snapshot(tmp_path, snap)
        analyzer = _make_analyzer()
        analyzer.initialize()
        analyzer.analyze(p)

        report = analyzer.report()
        assert report.status == "ok"
        assert "1" in report.summary  # "1 nodes"
        assert len(report.recommendations) > 0

    def test_analyze_with_diagnostics(self, tmp_path):
        snap = _minimal_snapshot()
        sp = _write_snapshot(tmp_path, snap)
        diag = {"event": "HeapSnapshot", "heapTotal": 50_000_000}
        dp = _write_diagnostics(tmp_path, diag)

        analyzer = _make_analyzer()
        analyzer.initialize()
        summary = analyzer.analyze(sp, diagnostics_path=dp)

        assert summary.diagnostics["event"] == "HeapSnapshot"

    def test_analyze_file_not_found(self):
        analyzer = _make_analyzer()
        analyzer.initialize()

        with pytest.raises(FileNotFoundError):
            analyzer.analyze("/nonexistent/file.heapsnapshot")

        assert analyzer.status == AgentStatus.ERROR

    def test_run_returns_report(self):
        analyzer = _make_analyzer()
        analyzer.initialize()
        report = analyzer.run()

        assert report.agent_name == "heap_analyzer"

    def test_status_transitions(self, tmp_path):
        snap = _minimal_snapshot()
        p = _write_snapshot(tmp_path, snap)
        analyzer = _make_analyzer()
        analyzer.initialize()

        assert analyzer.status == AgentStatus.IDLE
        # After successful analysis, should be back to IDLE
        analyzer.analyze(p)
        assert analyzer.status == AgentStatus.IDLE

    def test_multiple_analyses(self, tmp_path):
        """Second analysis replaces the first."""
        snap1 = _minimal_snapshot(nodes=[3, 1, 1, 100, 0, 0, 0])
        p1 = _write_snapshot(tmp_path, snap1)

        snap2_data = _minimal_snapshot(nodes=[3, 1, 1, 999, 0, 0, 0])
        p2 = tmp_path / "second.heapsnapshot"
        p2.write_text(json.dumps(snap2_data), encoding="utf-8")

        analyzer = _make_analyzer()
        analyzer.initialize()

        s1 = analyzer.analyze(p1)
        assert s1.total_size_bytes == 100

        s2 = analyzer.analyze(p2)
        assert s2.total_size_bytes == 999

        report = analyzer.report()
        assert "999" in report.summary or "second" in report.summary


# ---------------------------------------------------------------------------
# print_heap_report (smoke test — just ensure it doesn't crash)
# ---------------------------------------------------------------------------

class TestPrintReport:
    def test_print_minimal(self, tmp_path, capsys):
        snap = _minimal_snapshot()
        p = _write_snapshot(tmp_path, snap)
        parser = HeapSnapshotParser(p)
        parser.load()
        summary = compute_summary(parser)

        print_heap_report(summary)
        out = capsys.readouterr().out

        assert "HEAP SNAPSHOT ANALYSIS" in out
        assert "HEAP OVERVIEW" in out
        assert "RECOMMENDATIONS" in out

    def test_print_with_diagnostics(self, tmp_path, capsys):
        snap = _minimal_snapshot()
        p = _write_snapshot(tmp_path, snap)
        parser = HeapSnapshotParser(p)
        parser.load()
        diag = DiagnosticsInfo(
            event="HeapSnapshot",
            node_version="v20.11.0",
            os_name="Linux",
            heap_total_bytes=50_000_000,
        )
        summary = compute_summary(parser, diagnostics=diag)

        print_heap_report(summary)
        out = capsys.readouterr().out

        assert "RUNTIME DIAGNOSTICS" in out
        assert "v20.11.0" in out

    def test_print_with_large_objects(self, tmp_path, capsys):
        big = 2 * 1024 * 1024
        nodes = [3, 1, 1, big, 0, 0, 0]
        snap = _minimal_snapshot(nodes=nodes)
        p = _write_snapshot(tmp_path, snap)
        parser = HeapSnapshotParser(p)
        parser.load()
        summary = compute_summary(parser)

        print_heap_report(summary)
        out = capsys.readouterr().out

        assert "LARGE OBJECTS" in out

    def test_print_with_duplicate_strings(self, tmp_path, capsys):
        nodes = []
        for i in range(5):
            nodes.extend([2, 1, i + 1, 20, 0, 0, 0])
        snap = _minimal_snapshot(nodes=nodes, node_count=5)
        p = _write_snapshot(tmp_path, snap)
        parser = HeapSnapshotParser(p)
        parser.load()
        summary = compute_summary(parser)

        print_heap_report(summary)
        out = capsys.readouterr().out

        assert "DUPLICATE STRINGS" in out
