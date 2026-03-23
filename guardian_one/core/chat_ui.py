"""Rich terminal chat interface for Guardian One.

Replaces the plain-text _guardian_chat with a styled terminal UI
using the Rich library — panels, tables, spinners, and color-coded output.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, TYPE_CHECKING

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich import box

if TYPE_CHECKING:
    from guardian_one.core.guardian import GuardianOne

# ── Theme ────────────────────────────────────────────────────────

GUARDIAN_THEME = Theme({
    "g.header": "bold cyan",
    "g.agent": "bold green",
    "g.alert": "bold red",
    "g.rec": "bold yellow",
    "g.info": "dim white",
    "g.prompt": "bold white",
    "g.command": "bold magenta",
    "g.success": "bold green",
    "g.error": "bold red",
    "g.muted": "dim",
    "g.label": "bold cyan",
    "g.value": "white",
    "g.scene": "bold blue",
})

# ── Helpers ──────────────────────────────────────────────────────


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _make_agent_table(guardian: GuardianOne) -> Table:
    """Build a Rich table showing all agents and their status."""
    table = Table(
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("Agent", style="bold white", min_width=18)
    table.add_column("Status", min_width=10)
    table.add_column("Summary", max_width=55)

    for name in guardian.list_agents():
        agent = guardian.get_agent(name)
        if agent:
            try:
                report = agent.report()
                status_style = {
                    "idle": "green",
                    "running": "yellow",
                    "error": "red",
                    "disabled": "dim",
                }.get(report.status, "white")
                table.add_row(
                    name,
                    Text(report.status, style=status_style),
                    report.summary[:55] if report.summary else "-",
                )
            except Exception as e:
                table.add_row(name, Text("error", style="red"), str(e)[:55])
    return table


def _response_panel(
    content: str,
    title: str = "Guardian One",
    style: str = "cyan",
) -> Panel:
    """Wrap a response in a styled panel."""
    return Panel(
        content,
        title=f"[bold]{title}[/bold]",
        title_align="left",
        border_style=style,
        padding=(1, 2),
    )


def _alert_panel(alerts: list[str], title: str = "Alerts") -> Panel | None:
    if not alerts:
        return None
    text = Text()
    for a in alerts:
        text.append("  ! ", style="bold red")
        text.append(a + "\n")
    return Panel(text, title=f"[bold red]{title}[/bold red]", border_style="red")


def _rec_panel(recs: list[str], title: str = "Recommendations") -> Panel | None:
    if not recs:
        return None
    text = Text()
    for r in recs:
        text.append("  > ", style="bold yellow")
        text.append(r + "\n")
    return Panel(text, title=f"[bold yellow]{title}[/bold yellow]", border_style="yellow")


# ── Command Handlers ─────────────────────────────────────────────


def _handle_status(console: Console, guardian: GuardianOne) -> None:
    with console.status("[g.info]Generating daily summary...", spinner="dots"):
        summary = guardian.daily_summary()
    console.print(_response_panel(summary, title="Daily Summary"))


def _handle_agents(console: Console, guardian: GuardianOne) -> None:
    table = _make_agent_table(guardian)
    console.print()
    console.print(Panel(table, title="[bold]Registered Agents[/bold]", border_style="cyan"))
    console.print()


def _handle_run_agent(console: Console, guardian: GuardianOne, agent_name: str) -> None:
    available = guardian.list_agents()
    if agent_name not in available:
        console.print(f"[g.error]Unknown agent:[/g.error] {agent_name}")
        console.print(f"[g.muted]Available: {', '.join(available)}[/g.muted]")
        return

    with console.status(f"[g.info]Running {agent_name}...", spinner="dots"):
        report = guardian.run_agent(agent_name)

    style = "green" if report.status == "idle" else "yellow" if report.status == "running" else "red"
    console.print(_response_panel(
        f"[{style}]{report.status.upper()}[/{style}]  {report.summary}",
        title=agent_name,
        style=style,
    ))
    if report.alerts:
        console.print(_alert_panel(report.alerts))
    if report.recommendations:
        console.print(_rec_panel(report.recommendations))


def _handle_brief(console: Console, guardian: GuardianOne) -> None:
    with console.status("[g.info]Generating weekly brief...", spinner="dots"):
        brief = guardian.monitor.weekly_brief_text()
    console.print(_response_panel(brief, title="H.O.M.E. L.I.N.K. Weekly Brief", style="blue"))


def _handle_devices(console: Console, guardian: GuardianOne) -> None:
    dev_agent = guardian.get_agent("device_agent")
    if not dev_agent:
        console.print("[g.error]DeviceAgent not registered.[/g.error]")
        return
    report = dev_agent.report()
    console.print(_response_panel(report.summary, title="Device Inventory", style="blue"))
    if report.alerts:
        console.print(_alert_panel(report.alerts))


def _handle_rooms(console: Console, guardian: GuardianOne) -> None:
    dev_agent = guardian.get_agent("device_agent")
    if not dev_agent:
        console.print("[g.error]DeviceAgent not registered.[/g.error]")
        return

    rooms = dev_agent.device_registry.room_summary()
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Room", style="bold white")
    table.add_column("Type", style="g.muted")
    table.add_column("Devices", justify="right")

    for room in rooms:
        table.add_row(room["name"], room["type"], str(room["device_count"]))

    console.print()
    console.print(Panel(table, title="[bold]Room Layout[/bold]", border_style="blue"))

    # Device detail under each room
    for room in rooms:
        if room["device_ids"]:
            text = Text()
            for did in room["device_ids"]:
                d = dev_agent.device_registry.get(did)
                if d:
                    status_style = "green" if d.status.value == "online" else "red" if d.status.value == "offline" else "yellow"
                    text.append(f"  {d.device_id}: ", style="bold")
                    text.append(f"{d.name} ", style="white")
                    text.append(f"[{d.status.value}]", style=status_style)
                    text.append("\n")
            console.print(Panel(text, title=f"[bold]{room['name']}[/bold]", border_style="dim"))
    console.print()


def _handle_scene(console: Console, guardian: GuardianOne, scene_name: str) -> None:
    dev_agent = guardian.get_agent("device_agent")
    if not dev_agent:
        console.print("[g.error]DeviceAgent not registered.[/g.error]")
        return

    scene_id = f"scene-{scene_name}" if not scene_name.startswith("scene-") else scene_name
    with console.status(f"[g.scene]Activating scene: {scene_name}...", spinner="dots"):
        results = dev_agent.activate_scene(scene_id)

    scene = dev_agent.automation.get_scene(scene_id)
    if scene:
        text = Text()
        text.append(f"{scene.description}\n\n", style="white")
        for r in results:
            target = r["device_id"] or r["room_id"]
            text.append(f"  -> ", style="bold green")
            text.append(f"{r['action']} ", style="white")
            text.append(f"on {target}\n", style="g.muted")
        console.print(_response_panel(text, title=f"Scene: {scene.name}", style="blue"))
    else:
        available = ", ".join(
            s.scene_id.replace("scene-", "") for s in dev_agent.automation.all_scenes()
        )
        console.print(f"[g.error]Scene '{scene_id}' not found.[/g.error]")
        console.print(f"[g.muted]Available: {available}[/g.muted]")


def _handle_event(console: Console, guardian: GuardianOne, event_name: str) -> None:
    dev_agent = guardian.get_agent("device_agent")
    if not dev_agent:
        console.print("[g.error]DeviceAgent not registered.[/g.error]")
        return

    with console.status(f"[g.info]Firing event: {event_name}...", spinner="dots"):
        if event_name in ("sunrise", "sunset"):
            results = dev_agent.handle_solar_event(event_name)
        else:
            results = dev_agent.handle_schedule_event(event_name)

    text = Text()
    text.append(f"Actions: {len(results)}\n\n")
    for r in results:
        target = r["device_id"] or r["room_id"]
        text.append(f"  -> ", style="bold green")
        text.append(f"{r['action']} ", style="white")
        text.append(f"on {target}\n", style="g.muted")
    console.print(_response_panel(text, title=f"Event: {event_name}", style="green"))


def _handle_audit(console: Console, guardian: GuardianOne) -> None:
    dev_agent = guardian.get_agent("device_agent")
    if not dev_agent:
        console.print("[g.error]DeviceAgent not registered.[/g.error]")
        return

    with console.status("[g.info]Running security audit...", spinner="dots"):
        audit_result = dev_agent.device_registry.security_audit()

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("Severity", min_width=10)
    table.add_column("Device", min_width=15)
    table.add_column("Issue")

    for issue in audit_result["issues"][:15]:
        sev = issue["severity"].upper()
        sev_style = "red" if sev in ("HIGH", "CRITICAL") else "yellow" if sev == "MEDIUM" else "white"
        table.add_row(
            Text(sev, style=sev_style),
            issue["device"],
            issue["issue"],
        )

    console.print()
    console.print(Panel(
        table,
        title=f"[bold]Security Audit — {audit_result['summary']}[/bold]",
        border_style="red",
    ))
    console.print()


def _handle_homelink(console: Console, guardian: GuardianOne) -> None:
    services = guardian.gateway.list_services()
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
    table.add_column("Service", min_width=25, style="bold")
    table.add_column("Circuit", min_width=12)
    table.add_column("Risk", justify="center")

    if services:
        for svc in services:
            status = guardian.gateway.service_status(svc)
            risk = guardian.monitor.assess_service(svc)
            circuit_style = "green" if status["circuit_state"] == "closed" else "red"
            risk_style = "green" if risk.risk_score <= 2 else "yellow" if risk.risk_score <= 3 else "red"
            table.add_row(
                svc,
                Text(status["circuit_state"], style=circuit_style),
                Text(f"{risk.risk_score}/5", style=risk_style),
            )
    else:
        table.add_row("No services registered", "-", "-")

    vault_health = guardian.vault.health_report()
    vault_info = f"Vault: {vault_health['total_credentials']} credentials"

    console.print()
    console.print(Panel(table, title="[bold]H.O.M.E. L.I.N.K. Services[/bold]", border_style="blue"))
    console.print(f"  [g.muted]{vault_info}[/g.muted]")
    console.print()


def _handle_reviews(console: Console, guardian: GuardianOne) -> None:
    pending = guardian.audit.pending_reviews()
    if not pending:
        console.print(_response_panel("[green]No items pending review.[/green]", title="Reviews"))
        return

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("Agent", style="bold")
    table.add_column("Action")

    for entry in pending[:10]:
        table.add_row(entry.agent, entry.action)

    console.print(Panel(
        table,
        title=f"[bold yellow]{len(pending)} Items Need Review[/bold yellow]",
        border_style="yellow",
    ))


def _handle_cfo(console: Console, guardian: GuardianOne, query: str, cfo_router: Any) -> None:
    with console.status("[g.info]Asking CFO...", spinner="dots"):
        result = cfo_router.handle(query)

    console.print(_response_panel(result.text, title="CFO", style="green"))
    if result.ai_summary:
        console.print(Panel(
            result.ai_summary,
            title="[bold]AI Analysis[/bold]",
            title_align="left",
            border_style="dim cyan",
            padding=(0, 2),
        ))


def _handle_think(console: Console, guardian: GuardianOne, question: str) -> None:
    with console.status("[g.info]Guardian AI is thinking...", spinner="dots"):
        try:
            answer = guardian.think(question)
        except Exception as e:
            console.print(f"[g.error]AI engine offline:[/g.error] {e}")
            console.print("[g.muted]Guardian can still run all deterministic commands.[/g.muted]")
            return

    console.print(_response_panel(answer, title="Guardian AI", style="cyan"))


def _handle_help(console: Console) -> None:
    table = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style="bold cyan",
        padding=(0, 2),
    )
    table.add_column("Command", style="bold magenta", min_width=28)
    table.add_column("Description")

    commands = [
        ("status", "Full system status & daily summary"),
        ("agents", "List all agents and their state"),
        ("agent <name>", "Run a specific agent"),
        ("brief", "Weekly H.O.M.E. L.I.N.K. security brief"),
        ("devices", "Device inventory"),
        ("rooms", "Room layout with devices"),
        ("scene <name>", "Activate scene (movie/work/away/goodnight)"),
        ("event <name>", "Fire event (wake/sleep/leave/arrive)"),
        ("audit", "Device security audit"),
        ("homelink", "H.O.M.E. L.I.N.K. service status"),
        ("reviews", "Items needing your review"),
        ("cfo <question>", "Talk to CFO about finances"),
        ("think <question>", "Ask Guardian AI anything"),
        ("clear", "Clear the screen"),
        ("help", "Show this help"),
        ("quit", "Exit Guardian One"),
    ]
    for cmd, desc in commands:
        table.add_row(cmd, desc)

    console.print()
    console.print(Panel(table, title="[bold]Commands[/bold]", border_style="cyan"))
    console.print("[g.muted]  Tip: Type any financial question directly to talk to the CFO.[/g.muted]")
    console.print()


# ── Welcome Banner ───────────────────────────────────────────────


def _print_welcome(console: Console, guardian: GuardianOne) -> None:
    agents = guardian.list_agents()
    agent_list = ", ".join(agents) if agents else "none"

    header = Text()
    header.append("\n")
    header.append("  G U A R D I A N   O N E\n", style="bold cyan")
    header.append("  Sovereign Coordinator\n\n", style="dim cyan")
    header.append("  Owner: ", style="g.muted")
    header.append("Jeremy Paulo Salvino Tabernero\n", style="bold white")
    header.append("  Agents: ", style="g.muted")
    header.append(f"{len(agents)} online", style="bold green")
    header.append(f" — {agent_list}\n", style="g.muted")

    ai_status = guardian.ai_engine.status()
    active_provider = ai_status["active_provider"] or "offline"
    provider_style = "bold green" if active_provider != "offline" else "bold red"
    header.append("  AI: ", style="g.muted")
    header.append(active_provider, style=provider_style)
    header.append("\n")

    console.print(Panel(
        header,
        border_style="cyan",
        box=box.DOUBLE,
        padding=(0, 1),
    ))
    console.print("[g.muted]  Type [bold]help[/bold] for commands, or just start talking.[/g.muted]\n")


# ── Main Chat Loop ───────────────────────────────────────────────


def guardian_chat(guardian: GuardianOne) -> None:
    """Rich interactive chat with Guardian One."""
    from guardian_one.core.command_router import CommandRouter

    console = Console(theme=GUARDIAN_THEME)
    cfo_router = CommandRouter(guardian)

    _print_welcome(console, guardian)

    while True:
        try:
            console.print()
            raw = Prompt.ask(f"  [g.prompt][{_timestamp()}] Jeremy[/g.prompt]")
            raw = raw.strip()

            if not raw:
                continue

            lowered = raw.lower()

            if lowered in ("quit", "exit", "bye"):
                console.print()
                console.print(Panel(
                    "[bold cyan]Guardian One signing off. Stay sovereign, Jeremy.[/bold cyan]",
                    border_style="cyan",
                    box=box.DOUBLE,
                ))
                break

            elif lowered in ("help", "?"):
                _handle_help(console)

            elif lowered == "clear":
                console.clear()
                _print_welcome(console, guardian)

            elif lowered == "status":
                _handle_status(console, guardian)

            elif lowered == "agents":
                _handle_agents(console, guardian)

            elif lowered.startswith("agent "):
                _handle_run_agent(console, guardian, raw[6:].strip())

            elif lowered == "brief":
                _handle_brief(console, guardian)

            elif lowered == "devices":
                _handle_devices(console, guardian)

            elif lowered == "rooms":
                _handle_rooms(console, guardian)

            elif lowered.startswith("scene "):
                _handle_scene(console, guardian, raw[6:].strip())

            elif lowered.startswith("event "):
                _handle_event(console, guardian, raw[6:].strip())

            elif lowered == "audit":
                _handle_audit(console, guardian)

            elif lowered == "homelink":
                _handle_homelink(console, guardian)

            elif lowered == "reviews":
                _handle_reviews(console, guardian)

            elif lowered.startswith("cfo "):
                _handle_cfo(console, guardian, raw[4:].strip(), cfo_router)

            elif lowered.startswith("think "):
                _handle_think(console, guardian, raw[6:].strip())

            else:
                # Fallback: try CFO router for financial queries
                with console.status("[g.info]Processing...", spinner="dots"):
                    result = cfo_router.handle(raw)

                if result.intent.name != "help" or result.intent.confidence > 0.8:
                    _handle_cfo(console, guardian, raw, cfo_router)
                else:
                    console.print(
                        f"[g.muted]  I don't understand [bold]'{raw}'[/bold]. "
                        f"Type [bold]help[/bold] for commands.[/g.muted]"
                    )

        except (KeyboardInterrupt, EOFError):
            console.print()
            console.print(Panel(
                "[bold cyan]Guardian One signing off. Stay sovereign, Jeremy.[/bold cyan]",
                border_style="cyan",
                box=box.DOUBLE,
            ))
            break
