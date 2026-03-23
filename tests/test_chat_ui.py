"""Tests for the Rich terminal chat interface."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass, field
from typing import Any

import pytest

from guardian_one.core.chat_ui import (
    _timestamp,
    _make_agent_table,
    _response_panel,
    _alert_panel,
    _rec_panel,
    _handle_help,
    _handle_status,
    _handle_agents,
    _handle_run_agent,
    _handle_brief,
    _handle_devices,
    _handle_homelink,
    _handle_reviews,
    _handle_cfo,
    _handle_think,
    _print_welcome,
    guardian_chat,
    GUARDIAN_THEME,
)
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


# ── Helpers ──────────────────────────────────────────────────────


def _make_console() -> Console:
    """Console that captures output to a string buffer."""
    return Console(theme=GUARDIAN_THEME, file=StringIO(), force_terminal=True, width=120)


def _get_output(console: Console) -> str:
    """Extract captured output from a console."""
    console.file.seek(0)
    return console.file.read()


@dataclass
class FakeReport:
    agent_name: str = "test_agent"
    status: str = "idle"
    summary: str = "All systems operational"
    actions_taken: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    alerts: list = field(default_factory=list)
    data: dict = field(default_factory=dict)
    ai_reasoning: str = ""
    timestamp: str = "2026-03-23T00:00:00Z"


@dataclass
class FakeAuditEntry:
    agent: str = "cfo"
    action: str = "sync_complete"


@dataclass
class FakeHealthAssessment:
    risk_score: int = 2


def _make_guardian():
    """Build a mocked GuardianOne for chat UI tests."""
    guardian = MagicMock()
    guardian.list_agents.return_value = ["chronos", "cfo", "device_agent"]
    guardian.daily_summary.return_value = "=== Guardian One Daily Summary ==="

    # AI engine status
    guardian.ai_engine.status.return_value = {
        "active_provider": "ollama",
        "ollama": {"available": True, "model": "llama3"},
        "anthropic": {"available": False},
        "total_requests": 42,
        "agents_with_memory": ["cfo"],
    }

    # Agent mocks
    fake_agent = MagicMock()
    fake_agent.report.return_value = FakeReport()
    guardian.get_agent.return_value = fake_agent
    guardian.run_agent.return_value = FakeReport()

    # Monitor
    guardian.monitor.weekly_brief_text.return_value = "Weekly Brief: All secure."
    guardian.monitor.assess_service.return_value = FakeHealthAssessment()

    # Gateway
    guardian.gateway.list_services.return_value = ["notion_api", "google_calendar"]
    guardian.gateway.service_status.return_value = {"circuit_state": "closed"}

    # Vault
    guardian.vault.health_report.return_value = {
        "total_credentials": 5,
        "due_for_rotation": 0,
    }

    # Audit
    guardian.audit.pending_reviews.return_value = []

    # Think
    guardian.think.return_value = "I recommend reviewing your schedule."

    return guardian


# ── Unit Tests ───────────────────────────────────────────────────


class TestTimestamp:
    def test_returns_time_string(self):
        ts = _timestamp()
        assert len(ts) == 8  # HH:MM:SS
        assert ts.count(":") == 2


class TestResponsePanel:
    def test_returns_panel(self):
        panel = _response_panel("hello", title="Test")
        assert isinstance(panel, Panel)

    def test_custom_style(self):
        panel = _response_panel("hello", style="red")
        assert panel.border_style == "red"


class TestAlertPanel:
    def test_none_when_empty(self):
        assert _alert_panel([]) is None

    def test_returns_panel_with_alerts(self):
        panel = _alert_panel(["Low battery", "Firmware outdated"])
        assert isinstance(panel, Panel)


class TestRecPanel:
    def test_none_when_empty(self):
        assert _rec_panel([]) is None

    def test_returns_panel_with_recs(self):
        panel = _rec_panel(["Update firmware", "Rotate credentials"])
        assert isinstance(panel, Panel)


class TestMakeAgentTable:
    def test_builds_table(self):
        guardian = _make_guardian()
        table = _make_agent_table(guardian)
        assert isinstance(table, Table)

    def test_handles_report_error(self):
        guardian = _make_guardian()
        bad_agent = MagicMock()
        bad_agent.report.side_effect = RuntimeError("boom")
        guardian.get_agent.return_value = bad_agent
        # Should not raise
        table = _make_agent_table(guardian)
        assert isinstance(table, Table)


class TestHandleHelp:
    def test_prints_help(self):
        console = _make_console()
        _handle_help(console)
        output = _get_output(console)
        assert "Commands" in output
        assert "status" in output
        assert "quit" in output
        assert "cfo" in output


class TestHandleStatus:
    def test_prints_summary(self):
        console = _make_console()
        guardian = _make_guardian()
        _handle_status(console, guardian)
        output = _get_output(console)
        assert "Daily Summary" in output
        guardian.daily_summary.assert_called_once()


class TestHandleAgents:
    def test_prints_agent_table(self):
        console = _make_console()
        guardian = _make_guardian()
        _handle_agents(console, guardian)
        output = _get_output(console)
        assert "Registered Agents" in output


class TestHandleRunAgent:
    def test_run_valid_agent(self):
        console = _make_console()
        guardian = _make_guardian()
        _handle_run_agent(console, guardian, "cfo")
        output = _get_output(console)
        guardian.run_agent.assert_called_once_with("cfo")

    def test_run_unknown_agent(self):
        console = _make_console()
        guardian = _make_guardian()
        _handle_run_agent(console, guardian, "nonexistent")
        output = _get_output(console)
        assert "Unknown agent" in output

    def test_alerts_and_recs_shown(self):
        console = _make_console()
        guardian = _make_guardian()
        guardian.run_agent.return_value = FakeReport(
            alerts=["Battery low"],
            recommendations=["Charge device"],
        )
        _handle_run_agent(console, guardian, "cfo")
        output = _get_output(console)
        assert "Battery low" in output
        assert "Charge device" in output


class TestHandleBrief:
    def test_prints_brief(self):
        console = _make_console()
        guardian = _make_guardian()
        _handle_brief(console, guardian)
        output = _get_output(console)
        assert "Weekly Brief" in output or "H.O.M.E. L.I.N.K." in output


class TestHandleDevices:
    def test_no_device_agent(self):
        console = _make_console()
        guardian = _make_guardian()
        guardian.get_agent.return_value = None
        _handle_devices(console, guardian)
        output = _get_output(console)
        assert "not registered" in output

    def test_with_device_agent(self):
        console = _make_console()
        guardian = _make_guardian()
        _handle_devices(console, guardian)
        output = _get_output(console)
        assert "Device Inventory" in output or "operational" in output


class TestHandleHomelink:
    def test_prints_services(self):
        console = _make_console()
        guardian = _make_guardian()
        _handle_homelink(console, guardian)
        output = _get_output(console)
        assert "H.O.M.E. L.I.N.K." in output
        assert "notion_api" in output

    def test_no_services(self):
        console = _make_console()
        guardian = _make_guardian()
        guardian.gateway.list_services.return_value = []
        _handle_homelink(console, guardian)
        output = _get_output(console)
        assert "No services registered" in output


class TestHandleReviews:
    def test_no_pending(self):
        console = _make_console()
        guardian = _make_guardian()
        _handle_reviews(console, guardian)
        output = _get_output(console)
        assert "No items pending" in output

    def test_with_pending(self):
        console = _make_console()
        guardian = _make_guardian()
        guardian.audit.pending_reviews.return_value = [
            FakeAuditEntry("cfo", "sync_complete"),
            FakeAuditEntry("chronos", "schedule_conflict"),
        ]
        _handle_reviews(console, guardian)
        output = _get_output(console)
        assert "Need Review" in output


class TestHandleCfo:
    def test_prints_cfo_response(self):
        console = _make_console()
        guardian = _make_guardian()
        cfo_router = MagicMock()
        cfo_router.handle.return_value = MagicMock(
            text="  Net Worth: $25,000.00",
            ai_summary=None,
        )
        _handle_cfo(console, guardian, "net worth", cfo_router)
        output = _get_output(console)
        assert "25,000" in output

    def test_prints_ai_summary(self):
        console = _make_console()
        guardian = _make_guardian()
        cfo_router = MagicMock()
        cfo_router.handle.return_value = MagicMock(
            text="  Net Worth: $25,000.00",
            ai_summary="Your net worth has grown 8% this month.",
        )
        _handle_cfo(console, guardian, "net worth", cfo_router)
        output = _get_output(console)
        assert "grown 8%" in output


class TestHandleThink:
    def test_prints_ai_response(self):
        console = _make_console()
        guardian = _make_guardian()
        _handle_think(console, guardian, "what should I do today?")
        output = _get_output(console)
        assert "schedule" in output
        guardian.think.assert_called_once_with("what should I do today?")

    def test_handles_offline(self):
        console = _make_console()
        guardian = _make_guardian()
        guardian.think.side_effect = RuntimeError("Connection refused")
        _handle_think(console, guardian, "hello")
        output = _get_output(console)
        assert "offline" in output


class TestPrintWelcome:
    def test_prints_banner(self):
        console = _make_console()
        guardian = _make_guardian()
        _print_welcome(console, guardian)
        output = _get_output(console)
        assert "G U A R D I A N   O N E" in output
        assert "Jeremy" in output
        assert "3 online" in output
        assert "ollama" in output


class TestGuardianChatLoop:
    """Integration tests for the main chat loop."""

    def test_quit_command(self):
        guardian = _make_guardian()
        with patch("guardian_one.core.chat_ui.Prompt") as mock_prompt:
            mock_prompt.ask.return_value = "quit"
            guardian_chat(guardian)
        # Should exit cleanly

    def test_help_command(self):
        guardian = _make_guardian()
        with patch("guardian_one.core.chat_ui.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["help", "quit"]
            guardian_chat(guardian)

    def test_status_then_quit(self):
        guardian = _make_guardian()
        with patch("guardian_one.core.chat_ui.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["status", "quit"]
            guardian_chat(guardian)
        guardian.daily_summary.assert_called()

    def test_agents_command(self):
        guardian = _make_guardian()
        with patch("guardian_one.core.chat_ui.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["agents", "quit"]
            guardian_chat(guardian)

    def test_think_command(self):
        guardian = _make_guardian()
        with patch("guardian_one.core.chat_ui.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["think what should I do?", "quit"]
            guardian_chat(guardian)
        guardian.think.assert_called_once_with("what should I do?")

    def test_cfo_command(self):
        guardian = _make_guardian()
        # CFO command goes through the real CommandRouter, so mock it
        with patch("guardian_one.core.command_router.CommandRouter") as MockRouter:
            mock_router_inst = MagicMock()
            mock_router_inst.handle.return_value = MagicMock(
                text="  Net Worth: $25,000.00",
                ai_summary=None,
                intent=MagicMock(name="net_worth", confidence=0.9),
            )
            MockRouter.return_value = mock_router_inst
            with patch("guardian_one.core.chat_ui.Prompt") as mock_prompt:
                mock_prompt.ask.side_effect = ["cfo net worth", "quit"]
                guardian_chat(guardian)

    def test_keyboard_interrupt(self):
        guardian = _make_guardian()
        with patch("guardian_one.core.chat_ui.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = KeyboardInterrupt
            guardian_chat(guardian)
        # Should exit cleanly

    def test_eof_error(self):
        guardian = _make_guardian()
        with patch("guardian_one.core.chat_ui.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = EOFError
            guardian_chat(guardian)

    def test_empty_input_skipped(self):
        guardian = _make_guardian()
        with patch("guardian_one.core.chat_ui.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["", "   ", "quit"]
            guardian_chat(guardian)

    def test_clear_command(self):
        guardian = _make_guardian()
        with patch("guardian_one.core.chat_ui.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["clear", "quit"]
            guardian_chat(guardian)

    def test_run_agent_command(self):
        guardian = _make_guardian()
        with patch("guardian_one.core.chat_ui.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["agent cfo", "quit"]
            guardian_chat(guardian)
        guardian.run_agent.assert_called_once_with("cfo")

    def test_homelink_command(self):
        guardian = _make_guardian()
        with patch("guardian_one.core.chat_ui.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["homelink", "quit"]
            guardian_chat(guardian)

    def test_reviews_command(self):
        guardian = _make_guardian()
        with patch("guardian_one.core.chat_ui.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["reviews", "quit"]
            guardian_chat(guardian)

    def test_fallback_unknown_command(self):
        guardian = _make_guardian()
        with patch("guardian_one.core.chat_ui.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["xyzzy", "quit"]
            guardian_chat(guardian)

    def test_exit_aliases(self):
        for cmd in ("exit", "bye"):
            guardian = _make_guardian()
            with patch("guardian_one.core.chat_ui.Prompt") as mock_prompt:
                mock_prompt.ask.return_value = cmd
                guardian_chat(guardian)
