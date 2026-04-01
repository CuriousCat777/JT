"""Tests for Varys — Intelligence Coordinator Agent."""

import pytest

from guardian_one.core.audit import AuditLog
from guardian_one.core.config import AgentConfig
from guardian_one.core.base_agent import AgentStatus
from guardian_one.agents.varys import Varys


@pytest.fixture
def tmp_audit(tmp_path):
    return AuditLog(log_dir=tmp_path / "logs")


@pytest.fixture
def varys(tmp_audit):
    cfg = AgentConfig(name="varys")
    v = Varys(config=cfg, audit=tmp_audit)
    v.initialize()
    return v


class TestVarysLifecycle:
    def test_initialize(self, varys):
        assert varys.status == AgentStatus.IDLE

    def test_run_returns_report(self, varys):
        report = varys.run()
        assert report.agent_name == "varys"

    def test_report_before_intel(self, varys):
        report = varys.report()
        assert report.agent_name == "varys"


class TestIntelReception:
    def test_receive_intel(self, varys):
        varys.receive_intel(
            source="boris",
            category="breach",
            severity="high",
            title="Port scan detected",
            details={"port": 9999},
        )
        intel = varys.get_intel()
        assert len(intel) == 1
        assert intel[0].source == "boris"

    def test_filter_by_category(self, varys):
        varys.receive_intel("boris", "breach", "high", "breach 1", {})
        varys.receive_intel("boris", "degradation", "medium", "slow api", {})
        assert len(varys.get_intel(category="breach")) == 1

    def test_filter_by_severity(self, varys):
        varys.receive_intel("boris", "health", "low", "minor", {})
        varys.receive_intel("boris", "health", "critical", "major", {})
        assert len(varys.get_intel(severity="critical")) == 1

    def test_acknowledge(self, varys):
        varys.receive_intel("boris", "health", "low", "hello", {})
        varys.acknowledge(0)
        unack = varys.get_intel(acknowledged=False)
        assert len(unack) == 0


class TestVarysAnalysis:
    def test_run_with_intel(self, varys):
        varys.receive_intel("boris", "breach", "critical", "breach!", {})
        varys.receive_intel("boris", "repair", "high", "repair needed", {})
        report = varys.run()
        assert report.data.get("total_intel") == 2

    def test_daily_brief(self, varys):
        varys.receive_intel("boris", "breach", "high", "alert", {})
        brief = varys.daily_brief()
        assert "VARYS" in brief or "varys" in brief.lower()
        assert "alert" in brief.lower() or "breach" in brief.lower()


class TestVarysAudit:
    def test_intel_logged(self, tmp_audit, varys):
        varys.receive_intel("boris", "health", "low", "test intel", {})
        entries = tmp_audit.query(agent="varys", limit=10)
        assert any("intel_received" in e.action for e in entries)
