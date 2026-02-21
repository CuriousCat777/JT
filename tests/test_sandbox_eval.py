"""Tests for sandbox deployment and performance evaluator."""

import tempfile
from pathlib import Path

from guardian_one.core.config import AgentConfig, GuardianConfig
from guardian_one.core.guardian import GuardianOne
from guardian_one.core.sandbox import SandboxDeployer, StepStatus
from guardian_one.core.evaluator import (
    PerformanceEvaluator,
    _evaluate_agent,
    score_to_rating,
    RATING_SCALE,
    EvaluationCycle,
)
from guardian_one.core.base_agent import AgentReport, AgentStatus
from guardian_one.agents.chronos import Chronos
from guardian_one.agents.archivist import Archivist


def _make_guardian() -> GuardianOne:
    config = GuardianConfig(
        log_dir=tempfile.mkdtemp(),
        data_dir=tempfile.mkdtemp(),
        agents={
            "chronos": AgentConfig(name="chronos", allowed_resources=["calendar"]),
            "archivist": AgentConfig(name="archivist", allowed_resources=["files"]),
        },
    )
    guardian = GuardianOne(config)
    guardian.register_agent(Chronos(config.agents["chronos"], guardian.audit))
    guardian.register_agent(Archivist(config.agents["archivist"], guardian.audit))
    return guardian


# ------------------------------------------------------------------
# Rating scale tests
# ------------------------------------------------------------------


def test_score_to_rating_exceptional():
    assert score_to_rating(100.0) == 5
    assert score_to_rating(90.0) == 5


def test_score_to_rating_proficient():
    assert score_to_rating(89.0) == 4
    assert score_to_rating(75.0) == 4


def test_score_to_rating_adequate():
    assert score_to_rating(74.0) == 3
    assert score_to_rating(50.0) == 3


def test_score_to_rating_needs_work():
    assert score_to_rating(49.0) == 2
    assert score_to_rating(25.0) == 2


def test_score_to_rating_critical():
    assert score_to_rating(24.0) == 1
    assert score_to_rating(0.0) == 1


def test_rating_scale_has_all_levels():
    assert set(RATING_SCALE.keys()) == {1, 2, 3, 4, 5}
    for level, info in RATING_SCALE.items():
        assert "label" in info
        assert "range" in info
        assert "description" in info


# ------------------------------------------------------------------
# Sandbox deployment tests
# ------------------------------------------------------------------


def test_sandbox_deploy_passes_all_steps():
    guardian = _make_guardian()
    deployer = SandboxDeployer(guardian)
    result = deployer.deploy()
    assert result is True
    assert deployer.is_active is True


def test_sandbox_checklist_has_10_steps():
    guardian = _make_guardian()
    deployer = SandboxDeployer(guardian)
    deployer.deploy()
    summary = deployer.checklist_summary()
    assert len(summary) == 10
    for step in summary:
        assert step["status"] == "passed"


def test_sandbox_captures_reports():
    guardian = _make_guardian()
    deployer = SandboxDeployer(guardian)
    deployer.deploy()
    reports = deployer.reports
    assert "chronos" in reports
    assert "archivist" in reports


def test_sandbox_audit_trail():
    guardian = _make_guardian()
    deployer = SandboxDeployer(guardian)
    deployer.deploy()
    entries = guardian.audit.query(agent="sandbox")
    actions = [e.action for e in entries]
    assert "sandbox_boot" in actions
    assert "sandbox_deployment_complete" in actions


# ------------------------------------------------------------------
# Agent evaluation tests
# ------------------------------------------------------------------


def test_evaluate_healthy_agent():
    report = AgentReport(
        agent_name="chronos",
        status="idle",
        summary="0 upcoming events, 0 conflicts.",
        actions_taken=["Found 0 events in next 12 hours."],
        recommendations=["Sleep duration is in a healthy range."],
        alerts=[],
        data={"upcoming_count": 0, "sleep": {"status": "no_data"}},
    )
    evaluation = _evaluate_agent("chronos", report, AgentStatus.IDLE, cycle=1)

    assert evaluation.agent_name == "chronos"
    assert evaluation.cycle == 1
    assert len(evaluation.metrics) == 5
    assert evaluation.overall_pct >= 75.0  # Healthy agent should score well
    assert evaluation.overall_rating >= 4
    assert evaluation.rating_label in ("Exceptional", "Proficient")


def test_evaluate_errored_agent():
    report = AgentReport(
        agent_name="test_agent",
        status="error",
        summary="Error: connection failed",
        actions_taken=[],
        recommendations=[],
        alerts=["Connection failed", "Retry exhausted", "Service down"],
        data={},
    )
    evaluation = _evaluate_agent("test_agent", report, AgentStatus.ERROR, cycle=1)

    assert evaluation.overall_pct < 50.0
    assert evaluation.overall_rating <= 2


def test_evaluate_disabled_agent():
    report = AgentReport(
        agent_name="test_agent",
        status="disabled",
        summary="Agent disabled.",
    )
    evaluation = _evaluate_agent("test_agent", report, AgentStatus.DISABLED, cycle=1)

    assert evaluation.overall_pct < 50.0
    assert evaluation.overall_rating <= 2


# ------------------------------------------------------------------
# Evaluator cycle tests
# ------------------------------------------------------------------


def test_evaluator_single_cycle():
    guardian = _make_guardian()
    evaluator = PerformanceEvaluator(
        guardian, data_dir=guardian.config.data_dir
    )
    cycle = evaluator.run_cycle()

    assert isinstance(cycle, EvaluationCycle)
    assert cycle.cycle == 1
    assert len(cycle.evaluations) == 2
    assert cycle.system_overall_pct > 0
    assert cycle.system_overall_rating >= 1


def test_evaluator_multiple_cycles():
    guardian = _make_guardian()
    evaluator = PerformanceEvaluator(
        guardian, data_dir=guardian.config.data_dir
    )
    cycle1 = evaluator.run_cycle()
    cycle2 = evaluator.run_cycle()

    assert cycle1.cycle == 1
    assert cycle2.cycle == 2
    assert len(evaluator._history) == 2


def test_evaluator_persists_results():
    guardian = _make_guardian()
    data_dir = guardian.config.data_dir
    evaluator = PerformanceEvaluator(guardian, data_dir=data_dir)
    evaluator.run_cycle()

    eval_file = Path(data_dir) / "evaluations.jsonl"
    assert eval_file.exists()
    content = eval_file.read_text()
    assert "chronos" in content
    assert "archivist" in content


def test_evaluator_audit_trail():
    guardian = _make_guardian()
    evaluator = PerformanceEvaluator(
        guardian, data_dir=guardian.config.data_dir
    )
    evaluator.run_cycle()

    entries = guardian.audit.query(agent="evaluator")
    actions = [e.action for e in entries]
    assert "eval_cycle_1" in actions
