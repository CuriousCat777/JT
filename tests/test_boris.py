"""Tests for Boris — System Connectivity & Infrastructure Health Agent."""

import json
from pathlib import Path

import pytest

from guardian_one.core.audit import AuditLog
from guardian_one.core.config import AgentConfig
from guardian_one.core.base_agent import AgentStatus
from guardian_one.agents.boris import (
    Boris,
    ComponentRepair,
    MCPConnection,
    TokenEntry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_audit(tmp_path):
    return AuditLog(log_dir=tmp_path / "logs")


@pytest.fixture
def web_root(tmp_path):
    """Create a minimal web_root with tokens.css and a template."""
    static = tmp_path / "web" / "static"
    static.mkdir(parents=True)
    templates = tmp_path / "web" / "templates"
    templates.mkdir(parents=True)

    tokens_css = static / "tokens.css"
    tokens_css.write_text("""\
:root {
  --g1-surface-root: #0d1117;
  --g1-surface-1: #161b22;
  --g1-border-default: #30363d;
  --g1-text-primary: #e6edf3;
  --g1-text-secondary: #c9d1d9;
  --g1-accent: #58a6ff;
  --g1-success: #3fb950;
  --g1-warning: #d29922;
  --g1-error: #f85149;
  --g1-font-sans: 'Inter', sans-serif;
  --g1-radius-md: 6px;
  --g1-shadow-sm: 0 1px 2px rgba(0,0,0,0.4);
  --g1-transition-fast: 120ms ease-in-out;
  --g1-space-4: 1rem;
  --g1-z-nav: 1000;
}
""")

    panel = templates / "panel.html"
    panel.write_text("""\
<style>
  body { background: var(--g1-surface-root); color: var(--g1-text-primary); }
  .border { border: 1px solid var(--g1-border-default); }
  .accent { color: var(--g1-accent); }
</style>
""")

    return tmp_path / "web"


@pytest.fixture
def boris(tmp_path, tmp_audit, web_root):
    cfg = AgentConfig(name="boris")
    agent = Boris(
        config=cfg,
        audit=tmp_audit,
        web_root=web_root,
        data_dir=tmp_path / "data",
    )
    agent.initialize()
    return agent


# ---------------------------------------------------------------------------
# Initialization & lifecycle
# ---------------------------------------------------------------------------

class TestBorisLifecycle:
    def test_initialize(self, boris):
        assert boris.status == AgentStatus.IDLE

    def test_run_returns_report(self, boris):
        report = boris.run()
        assert report.agent_name == "boris"
        assert report.status in ("operational", "attention_needed")
        assert boris.status == AgentStatus.IDLE

    def test_report_before_run(self, boris):
        report = boris.report()
        assert "not run yet" in report.summary.lower()

    def test_report_after_run(self, boris):
        boris.run()
        report = boris.report()
        assert "MCP" in report.summary


# ---------------------------------------------------------------------------
# MCP connections
# ---------------------------------------------------------------------------

class TestMCPConnections:
    def test_scan_populates_connections(self, boris):
        boris._scan_mcp_connections()
        conns = boris.get_mcp_connections()
        assert len(conns) > 0
        assert all(isinstance(c, MCPConnection) for c in conns)

    def test_connections_have_tool_counts(self, boris):
        boris._scan_mcp_connections()
        for c in boris.get_mcp_connections():
            assert c.tools_count >= 0
            assert c.status == "connected"

    def test_connection_to_dict(self):
        c = MCPConnection(server_id="test", name="Test MCP", status="connected", tools_count=5)
        d = c.to_dict()
        assert d["server_id"] == "test"
        assert d["tools_count"] == 5


# ---------------------------------------------------------------------------
# Token inventory
# ---------------------------------------------------------------------------

class TestTokenInventory:
    def test_scan_tokens(self, boris):
        boris._scan_tokens()
        tokens = boris.get_tokens()
        assert len(tokens) >= 15  # We defined 15 in the fixture
        assert all(isinstance(t, TokenEntry) for t in tokens)

    def test_token_categories(self, boris):
        boris._scan_tokens()
        summary = boris.get_token_summary()
        assert summary["total"] >= 15
        assert "surface" in summary["categories"]
        assert "border" in summary["categories"]

    def test_token_alignment_no_mismatches(self, boris):
        """All tokens in our fixture template are defined — no repairs created."""
        boris._scan_tokens()
        boris._check_token_alignment()
        token_repairs = [r for r in boris.get_repairs() if r.component.startswith("token:")]
        assert len(token_repairs) == 0

    def test_token_alignment_detects_mismatch(self, boris, web_root):
        """Add an undefined token reference and verify Boris catches it."""
        template = web_root / "templates" / "panel.html"
        content = template.read_text()
        content += "\n<div style='color: var(--g1-nonexistent-token)'>test</div>\n"
        template.write_text(content)

        boris._scan_tokens()
        boris._check_token_alignment()
        token_repairs = [r for r in boris.get_repairs() if "nonexistent" in r.component]
        assert len(token_repairs) == 1
        assert token_repairs[0].severity == "high"

    def test_token_entry_to_dict(self):
        t = TokenEntry(name="--g1-accent", value="#58a6ff", category="accent")
        d = t.to_dict()
        assert d["name"] == "--g1-accent"
        assert d["category"] == "accent"

    def test_token_referenced_by(self, boris):
        boris._scan_tokens()
        boris._check_token_alignment()
        referenced = [t for t in boris.get_tokens() if t.referenced_by]
        assert len(referenced) > 0  # At least some are referenced in panel.html


# ---------------------------------------------------------------------------
# Component repairs
# ---------------------------------------------------------------------------

class TestComponentRepairs:
    def test_add_repair(self, boris):
        repair = boris.add_repair("web:chat.html", "Missing ARIA landmark", severity="medium")
        assert repair.status == "open"
        assert repair.component == "web:chat.html"

    def test_resolve_repair(self, boris):
        boris.add_repair("web:panel.html", "Grid overflow bug")
        assert boris.resolve_repair("web:panel.html", notes="Fixed in commit abc")
        resolved = boris.get_repairs(status="resolved")
        assert len(resolved) == 1
        assert resolved[0].notes == "Fixed in commit abc"

    def test_resolve_nonexistent_returns_false(self, boris):
        assert boris.resolve_repair("nonexistent") is False

    def test_repairs_persist(self, boris, tmp_path):
        boris.add_repair("mcp:github", "Rate limit exceeded")
        boris._save_repairs()

        # Create new Boris instance pointing at same data dir
        cfg = AgentConfig(name="boris")
        boris2 = Boris(
            config=cfg,
            audit=boris.audit,
            data_dir=tmp_path / "data",
        )
        boris2.initialize()
        assert len(boris2.get_repairs()) == 1
        assert boris2.get_repairs()[0].component == "mcp:github"

    def test_get_repairs_by_status(self, boris):
        boris.add_repair("a", "issue a", severity="low")
        boris.add_repair("b", "issue b", severity="high")
        boris.resolve_repair("a", "done")
        assert len(boris.get_repairs(status="open")) == 1
        assert len(boris.get_repairs(status="resolved")) == 1

    def test_repair_to_dict(self):
        r = ComponentRepair(component="test", issue="broken", severity="critical")
        d = r.to_dict()
        assert d["component"] == "test"
        assert d["severity"] == "critical"


# ---------------------------------------------------------------------------
# Connectivity brief
# ---------------------------------------------------------------------------

class TestConnectivityBrief:
    def test_brief_format(self, boris):
        boris.run()
        brief = boris.connectivity_brief()
        assert "BORIS" in brief
        assert "MCP Connections" in brief
        assert "Token Inventory" in brief
        assert "Active Repairs" in brief

    def test_brief_shows_token_counts(self, boris):
        boris.run()
        brief = boris.connectivity_brief()
        assert "Total:" in brief
        assert "In use:" in brief


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

class TestBorisAudit:
    def test_initialize_logged(self, tmp_audit, boris):
        entries = tmp_audit.query(agent="boris", limit=10)
        assert any("initialize" in e.action for e in entries)

    def test_run_logged(self, tmp_audit, boris):
        boris.run()
        entries = tmp_audit.query(agent="boris", limit=10)
        assert any("run_complete" in e.action for e in entries)

    def test_repair_creation_logged(self, tmp_audit, boris):
        boris.add_repair("test", "test issue")
        entries = tmp_audit.query(agent="boris", limit=10)
        assert any("repair_created" in e.action for e in entries)
