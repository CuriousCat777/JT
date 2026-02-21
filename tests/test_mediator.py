"""Tests for the Mediator conflict resolution engine."""

import tempfile
from pathlib import Path

from guardian_one.core.audit import AuditLog
from guardian_one.core.mediator import (
    ConflictType,
    Mediator,
    Proposal,
    Resolution,
)


def _make_mediator() -> Mediator:
    audit = AuditLog(log_dir=Path(tempfile.mkdtemp()))
    return Mediator(audit=audit)


# ------------------------------------------------------------------
# Basic proposal submission
# ------------------------------------------------------------------


def test_submit_proposal():
    mediator = _make_mediator()
    p = Proposal(agent="chronos", action="schedule_meeting", resource="calendar")
    mediator.submit_proposal(p)
    assert len(mediator._pending_proposals) == 1


def test_submit_multiple_proposals():
    mediator = _make_mediator()
    mediator.submit_proposal(Proposal(agent="chronos", action="a", resource="calendar"))
    mediator.submit_proposal(Proposal(agent="archivist", action="b", resource="files"))
    mediator.submit_proposal(Proposal(agent="cfo", action="c", resource="accounts"))
    assert len(mediator._pending_proposals) == 3


# ------------------------------------------------------------------
# No conflicts
# ------------------------------------------------------------------


def test_no_conflicts_different_resources():
    mediator = _make_mediator()
    mediator.submit_proposal(Proposal(agent="chronos", action="a", resource="calendar"))
    mediator.submit_proposal(Proposal(agent="archivist", action="b", resource="files"))
    conflicts = mediator.check_conflicts()
    assert len(conflicts) == 0


def test_no_conflicts_same_agent():
    """Same agent accessing same resource should not trigger resource contention."""
    mediator = _make_mediator()
    mediator.submit_proposal(Proposal(agent="chronos", action="a", resource="calendar"))
    mediator.submit_proposal(Proposal(agent="chronos", action="b", resource="calendar"))
    conflicts = mediator.check_conflicts()
    assert len(conflicts) == 0


def test_no_conflicts_no_time_overlap():
    mediator = _make_mediator()
    mediator.submit_proposal(Proposal(
        agent="chronos", action="a", resource="r1",
        time_start="2026-02-21T09:00", time_end="2026-02-21T10:00",
    ))
    mediator.submit_proposal(Proposal(
        agent="archivist", action="b", resource="r2",
        time_start="2026-02-21T10:00", time_end="2026-02-21T11:00",
    ))
    conflicts = mediator.check_conflicts()
    assert len(conflicts) == 0


def test_empty_proposals_no_conflicts():
    mediator = _make_mediator()
    conflicts = mediator.check_conflicts()
    assert conflicts == []


# ------------------------------------------------------------------
# Time overlap conflicts
# ------------------------------------------------------------------


def test_time_overlap_chronos_wins():
    """Chronos has higher priority than archivist for time conflicts."""
    mediator = _make_mediator()
    mediator.submit_proposal(Proposal(
        agent="chronos", action="meeting", resource="calendar",
        time_start="2026-02-21T14:00", time_end="2026-02-21T15:00",
    ))
    mediator.submit_proposal(Proposal(
        agent="archivist", action="backup", resource="system",
        time_start="2026-02-21T14:30", time_end="2026-02-21T15:30",
    ))
    conflicts = mediator.check_conflicts()
    time_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.TIME_OVERLAP]
    assert len(time_conflicts) == 1
    assert time_conflicts[0].resolution == Resolution.APPROVE_FIRST


def test_time_overlap_cfo_vs_archivist():
    """CFO has higher priority than archivist."""
    mediator = _make_mediator()
    mediator.submit_proposal(Proposal(
        agent="archivist", action="backup", resource="r1",
        time_start="2026-02-21T14:00", time_end="2026-02-21T15:00",
    ))
    mediator.submit_proposal(Proposal(
        agent="cfo", action="payment", resource="r2",
        time_start="2026-02-21T14:30", time_end="2026-02-21T15:30",
    ))
    conflicts = mediator.check_conflicts()
    time_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.TIME_OVERLAP]
    assert len(time_conflicts) == 1
    assert time_conflicts[0].resolution == Resolution.APPROVE_SECOND


def test_time_overlap_equal_priority_defers_to_owner():
    """Unknown agents have equal priority — defer to Jeremy."""
    mediator = _make_mediator()
    mediator.submit_proposal(Proposal(
        agent="agent_x", action="a", resource="r1",
        time_start="2026-02-21T14:00", time_end="2026-02-21T15:00",
    ))
    mediator.submit_proposal(Proposal(
        agent="agent_y", action="b", resource="r2",
        time_start="2026-02-21T14:30", time_end="2026-02-21T15:30",
    ))
    conflicts = mediator.check_conflicts()
    time_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.TIME_OVERLAP]
    assert len(time_conflicts) == 1
    assert time_conflicts[0].resolution == Resolution.DEFER_TO_OWNER


# ------------------------------------------------------------------
# Resource contention
# ------------------------------------------------------------------


def test_resource_contention_different_agents():
    mediator = _make_mediator()
    mediator.submit_proposal(Proposal(agent="chronos", action="a", resource="shared_resource"))
    mediator.submit_proposal(Proposal(agent="archivist", action="b", resource="shared_resource"))
    conflicts = mediator.check_conflicts()
    resource_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.RESOURCE_CONTENTION]
    assert len(resource_conflicts) == 1
    assert resource_conflicts[0].resolution == Resolution.DEFER_TO_OWNER


def test_resource_contention_three_agents():
    """Three agents wanting same resource should produce 3 conflict pairs."""
    mediator = _make_mediator()
    mediator.submit_proposal(Proposal(agent="chronos", action="a", resource="shared"))
    mediator.submit_proposal(Proposal(agent="archivist", action="b", resource="shared"))
    mediator.submit_proposal(Proposal(agent="cfo", action="c", resource="shared"))
    conflicts = mediator.check_conflicts()
    resource_conflicts = [c for c in conflicts if c.conflict_type == ConflictType.RESOURCE_CONTENTION]
    # chronos-archivist, chronos-cfo, archivist-cfo = 3 pairs
    assert len(resource_conflicts) == 3


# ------------------------------------------------------------------
# Combined time + resource conflicts
# ------------------------------------------------------------------


def test_time_and_resource_conflict():
    """Same resource AND overlapping time produces both conflict types."""
    mediator = _make_mediator()
    mediator.submit_proposal(Proposal(
        agent="chronos", action="a", resource="calendar",
        time_start="2026-02-21T14:00", time_end="2026-02-21T15:00",
    ))
    mediator.submit_proposal(Proposal(
        agent="archivist", action="b", resource="calendar",
        time_start="2026-02-21T14:30", time_end="2026-02-21T15:30",
    ))
    conflicts = mediator.check_conflicts()
    types = {c.conflict_type for c in conflicts}
    assert ConflictType.TIME_OVERLAP in types
    assert ConflictType.RESOURCE_CONTENTION in types


# ------------------------------------------------------------------
# History and cleanup
# ------------------------------------------------------------------


def test_conflict_history_persists():
    mediator = _make_mediator()
    mediator.submit_proposal(Proposal(agent="chronos", action="a", resource="shared"))
    mediator.submit_proposal(Proposal(agent="archivist", action="b", resource="shared"))
    mediator.check_conflicts()
    history = mediator.conflict_history()
    assert len(history) >= 1


def test_clear_pending():
    mediator = _make_mediator()
    mediator.submit_proposal(Proposal(agent="chronos", action="a", resource="r"))
    mediator.submit_proposal(Proposal(agent="archivist", action="b", resource="r"))
    mediator.clear_pending()
    assert len(mediator._pending_proposals) == 0


def test_clear_pending_then_no_conflicts():
    mediator = _make_mediator()
    mediator.submit_proposal(Proposal(agent="chronos", action="a", resource="shared"))
    mediator.submit_proposal(Proposal(agent="archivist", action="b", resource="shared"))
    mediator.clear_pending()
    conflicts = mediator.check_conflicts()
    assert len(conflicts) == 0


def test_history_accumulates_across_cycles():
    mediator = _make_mediator()

    # Cycle 1
    mediator.submit_proposal(Proposal(agent="chronos", action="a", resource="shared"))
    mediator.submit_proposal(Proposal(agent="archivist", action="b", resource="shared"))
    mediator.check_conflicts()
    mediator.clear_pending()

    # Cycle 2
    mediator.submit_proposal(Proposal(agent="cfo", action="c", resource="accounts"))
    mediator.submit_proposal(Proposal(agent="archivist", action="d", resource="accounts"))
    mediator.check_conflicts()
    mediator.clear_pending()

    history = mediator.conflict_history()
    assert len(history) == 2


# ------------------------------------------------------------------
# Proposals with partial time data
# ------------------------------------------------------------------


def test_proposals_with_no_time_data():
    """Proposals without time fields should not trigger time overlap."""
    mediator = _make_mediator()
    mediator.submit_proposal(Proposal(agent="chronos", action="a", resource="r1"))
    mediator.submit_proposal(Proposal(agent="archivist", action="b", resource="r2"))
    conflicts = mediator.check_conflicts()
    assert len(conflicts) == 0


def test_proposals_with_partial_time_data():
    """If one proposal has time and other doesn't, no time conflict."""
    mediator = _make_mediator()
    mediator.submit_proposal(Proposal(
        agent="chronos", action="a", resource="r1",
        time_start="2026-02-21T14:00", time_end="2026-02-21T15:00",
    ))
    mediator.submit_proposal(Proposal(agent="archivist", action="b", resource="r2"))
    conflicts = mediator.check_conflicts()
    assert len(conflicts) == 0
