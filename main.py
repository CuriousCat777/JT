"""Guardian One — main entry point.

Usage:
    python main.py              # Run all agents once and print daily summary
    python main.py --schedule   # Start interactive scheduler (agents run on intervals)
    python main.py --summary    # Print daily summary only
    python main.py --dashboard  # Print CFO financial dashboard
    python main.py --validate   # CFO validation report (detailed, for review)
    python main.py --sync       # Continuous sync loop (Plaid + Empower + Rocket Money)
    python main.py --connect    # Connect bank accounts via Plaid (read-only)
    python main.py --agent NAME # Run a single agent
    python main.py --brief      # H.O.M.E. L.I.N.K. weekly security brief
    python main.py --homelink   # H.O.M.E. L.I.N.K. service status
    python main.py --sandbox    # Deploy Chronos+Archivist in sandbox, start daily eval
    python main.py --gmail      # Gmail inbox status + Rocket Money CSV check
    python main.py --csv PATH   # Parse a local Rocket Money CSV and summarize
    python main.py --notify     # Run daily review and send notifications (email/SMS)
    python main.py --notify-test # Send a test notification to verify email/SMS setup
    python main.py --calendar       # Show today's schedule + calendar status
    python main.py --calendar-week  # Show this week's schedule
    python main.py --calendar-sync  # Sync Google Calendar → Chronos + push bills to calendar
    python main.py --calendar-auth  # Authorize Google Calendar (opens browser for OAuth)
    python main.py --websites           # Show status of all managed websites
    python main.py --website-build DOMAIN  # Build a site (or 'all')
    python main.py --website-deploy DOMAIN # Deploy a site (or 'all')
    python main.py --website-sync       # Push website dashboards to Notion
    python main.py --notion-sync        # Full Notion workspace sync (agents, roadmap, health)
    python main.py --devices             # H.O.M.E. L.I.N.K. full dashboard
    python main.py --device-audit        # Run device security audit
    python main.py --rooms               # Show room layout with devices
    python main.py --scene movie         # Activate a scene (movie, work, away, goodnight)
    python main.py --home-event wake     # Fire event (wake, sleep, leave, arrive, sunrise, sunset)
    python main.py --flipper             # Flipper Zero device profiles
    python main.py --security-review     # Run security remediation review for all domains
    python main.py --security-review jtmdai.com  # Review a single domain
    python main.py --security-sync       # Push remediation status to Notion
    python main.py --connector-audit     # Audit Claude connector attack surface
    python main.py --power-tools          # Rails + Gin power tools status
    python main.py --rails-new APP        # Scaffold a new Rails app
    python main.py --gin-new APP          # Scaffold a new Gin app
    python main.py --rails-server PATH    # Start Rails dev server
    python main.py --gin-server PATH      # Start Gin dev server
    python main.py --rails-install        # Install Ruby on Rails via gem
    python main.py --cfo                  # Interactive CFO financial assistant (conversational)
    python main.py --sentinel             # IoT Sentinel dashboard (network + security)
    python main.py --sentinel-scan        # Run one-time network scan
    python main.py --sentinel-monitor     # Start continuous network monitoring
    python main.py --network-audit        # LAN security audit (VLAN, DNS, credentials)
    python main.py --vpn-status           # Tailscale VPN status
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Fix Windows console encoding — allow Unicode output without crashing
if sys.stdout.encoding and sys.stdout.encoding.lower().startswith("cp"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

from guardian_one.core.config import AgentConfig, load_config
from guardian_one.core.guardian import GuardianOne
from guardian_one.agents.chronos import Chronos
from guardian_one.agents.archivist import Archivist
from guardian_one.agents.cfo import CFO
from guardian_one.agents.doordash import DoorDashAgent
from guardian_one.agents.gmail_agent import GmailAgent
from guardian_one.agents.web_architect import WebArchitect
from guardian_one.agents.teleprompter import Teleprompter


def _build_agents(guardian: GuardianOne) -> None:
    """Instantiate and register all subordinate agents."""
    config = guardian.config

    chronos_cfg = config.agents.get("chronos", AgentConfig(name="chronos"))
    guardian.register_agent(Chronos(config=chronos_cfg, audit=guardian.audit))

    archivist_cfg = config.agents.get("archivist", AgentConfig(name="archivist"))
    guardian.register_agent(Archivist(config=archivist_cfg, audit=guardian.audit))

    cfo_cfg = config.agents.get("cfo", AgentConfig(name="cfo"))
    guardian.register_agent(CFO(config=cfo_cfg, audit=guardian.audit, data_dir=config.data_dir))

    doordash_cfg = config.agents.get("doordash", AgentConfig(name="doordash"))
    guardian.register_agent(DoorDashAgent(config=doordash_cfg, audit=guardian.audit))

    gmail_cfg = config.agents.get("gmail", AgentConfig(name="gmail"))
    guardian.register_agent(GmailAgent(
        config=gmail_cfg,
        audit=guardian.audit,
        data_dir=config.data_dir,
    ))

    wa_cfg = config.agents.get("web_architect", AgentConfig(name="web_architect"))
    guardian.register_agent(WebArchitect(config=wa_cfg, audit=guardian.audit))

    tp_cfg = config.agents.get("teleprompter", AgentConfig(name="teleprompter"))
    guardian.register_agent(Teleprompter(
        config=tp_cfg, audit=guardian.audit, data_dir=config.data_dir,
    ))


def _print_validation_report(cfo: CFO) -> None:
    """Print a formatted CFO validation report for presentation."""
    report = cfo.validation_report()

    print("=" * 70)
    print("  CFO VALIDATION REPORT — Guardian One Financial Intelligence")
    print("=" * 70)
    print(f"  Generated: {report['report_generated']}")
    print(f"  Ledger:    {report['ledger_path']}")
    print()

    # Net worth breakdown
    print("  NET WORTH SUMMARY")
    print("  " + "-" * 40)
    print(f"  Total Assets:      ${report['total_assets']:>12,.2f}")
    print(f"  Total Liabilities: ${report['total_liabilities']:>12,.2f}")
    print(f"  Net Worth:         ${report['net_worth']:>12,.2f}")
    print()

    # Balances by type
    print("  BALANCES BY TYPE")
    print("  " + "-" * 40)
    for acct_type, total in sorted(report["balances_by_type"].items()):
        print(f"  {acct_type:<20} ${total:>12,.2f}")
    print()

    # Account detail
    print("  ACCOUNT DETAIL")
    print("  " + "-" * 66)
    print(f"  {'Account':<40} {'Type':<12} {'Balance':>12}")
    print("  " + "-" * 66)
    for acct in report["accounts"]:
        print(f"  {acct['name']:<40} {acct['type']:<12} ${acct['balance']:>11,.2f}")
    print("  " + "-" * 66)
    print(f"  {'TOTAL':<40} {'':<12} ${report['net_worth']:>11,.2f}")
    print()

    # Bills
    bills = report["bills"]
    if bills["overdue"]:
        print("  OVERDUE BILLS")
        print("  " + "-" * 40)
        for b in bills["overdue"]:
            print(f"  [!] {b['name']}: ${b['amount']:.2f} — due {b['due']}")
        print()

    if bills["upcoming_30d"]:
        print("  UPCOMING BILLS (next 30 days)")
        print("  " + "-" * 40)
        for b in bills["upcoming_30d"]:
            auto = " (auto-pay)" if b["auto_pay"] else ""
            print(f"  {b['name']}: ${b['amount']:.2f} — due {b['due']}{auto}")
        print()

    # Tax recommendations
    print("  TAX RECOMMENDATIONS")
    print("  " + "-" * 40)
    for i, rec in enumerate(report["tax_recommendations"], 1):
        print(f"  {i}. {rec}")
    print()

    # Sync status
    rm = report["rocket_money"]
    emp = report["empower"]
    print("  SYNC STATUS")
    print("  " + "-" * 40)
    plaid = report.get("plaid", {})
    print(f"  Plaid:        {'connected' if plaid.get('connected') else 'offline'} ({plaid.get('connected_institutions', 0)} bank(s))")
    print(f"  Rocket Money: {'connected' if rm.get('connected') else 'offline'} (mode: {rm.get('sync_mode', 'n/a')})")
    print(f"  Empower:      {'connected' if emp.get('connected') else 'offline'}")
    print()
    print(f"  Accounts: {report['account_count']} | Transactions: {report['transaction_count']}")
    print("=" * 70)


def _run_sync_loop(cfo: CFO, interval: int = 300, once: bool = False) -> None:
    """Continuously sync Empower + Rocket Money accounts.

    Runs a sync cycle, prints updated balances, then sleeps for *interval*
    seconds before repeating.  Use --sync-once to run a single cycle.
    """
    cycle = 0
    try:
        while True:
            cycle += 1
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            print(f"\n{'=' * 60}")
            print(f"  SYNC CYCLE #{cycle} — {ts}")
            print(f"{'=' * 60}")

            results = cfo.sync_all()

            # Plaid results (direct bank connections)
            plaid = results.get("plaid", {})
            if plaid.get("connected"):
                print(f"  Plaid:        +{plaid.get('accounts_added', 0)} new, "
                      f"{plaid.get('accounts_updated', 0)} updated, "
                      f"+{plaid.get('transactions_added', 0)} txns "
                      f"from {plaid.get('institutions', 0)} bank(s)")
            else:
                inst_count = plaid.get("institutions", 0)
                if inst_count == 0 and not cfo.plaid.has_credentials:
                    print(f"  Plaid:        not configured (run --connect to link banks)")
                else:
                    print(f"  Plaid:        offline ({plaid.get('error', 'no credentials')})")

            # Empower results
            emp = results["empower"]
            if emp.get("connected"):
                print(f"  Empower:      +{emp['accounts_added']} new, "
                      f"{emp['accounts_updated']} updated, "
                      f"+{emp['transactions_added']} txns")
            else:
                print(f"  Empower:      offline ({emp.get('error', 'no credentials')})")

            # Rocket Money results
            rm = results["rocket_money"]
            print(f"  Rocket Money: {rm['source']} — "
                  f"+{rm['accounts_added']} new, "
                  f"{rm['accounts_updated']} updated, "
                  f"+{rm['transactions_added']} txns")

            # Updated balances
            print(f"\n  NET WORTH: ${results['net_worth']:,.2f}")
            print(f"  Accounts:  {results['account_count']}")
            print(f"  Transactions: {results['transaction_count']}")

            # Per-type breakdown
            by_type = cfo.balances_by_type()
            print()
            for acct_type, total in sorted(by_type.items()):
                print(f"    {acct_type:<15} ${total:>12,.2f}")

            # Quick account list
            print(f"\n  {'Account':<40} {'Balance':>12}")
            print("  " + "-" * 54)
            for acct in cfo._accounts.values():
                print(f"  {acct.name:<40} ${acct.balance:>11,.2f}")

            if once:
                print(f"\n  Single sync complete.")
                break

            print(f"\n  Next sync in {interval}s (Ctrl+C to stop)...")
            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n  Sync loop stopped after {cycle} cycle(s).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Guardian One — multi-agent system")
    parser.add_argument("--schedule", action="store_true", help="Start interactive scheduler")
    parser.add_argument("--summary", action="store_true", help="Print daily summary")
    parser.add_argument("--dashboard", action="store_true", help="Generate CFO Excel dashboard")
    parser.add_argument("--dashboard-password", type=str, default=None, help="Password-protect the Excel dashboard")
    parser.add_argument("--validate", action="store_true", help="CFO validation report for review")
    parser.add_argument("--sync", action="store_true", help="Continuous Plaid + Empower + Rocket Money sync loop")
    parser.add_argument("--sync-interval", type=int, default=300, help="Sync interval in seconds (default: 300 = 5min)")
    parser.add_argument("--sync-once", action="store_true", help="Run a single sync cycle then exit")
    parser.add_argument("--connect", action="store_true", help="Connect bank accounts via Plaid (read-only)")
    parser.add_argument("--connect-port", type=int, default=8234, help="Port for Plaid Link server (default: 8234)")
    parser.add_argument("--agent", type=str, help="Run a single agent by name")
    parser.add_argument("--brief", action="store_true", help="H.O.M.E. L.I.N.K. weekly security brief")
    parser.add_argument("--homelink", action="store_true", help="H.O.M.E. L.I.N.K. service status")
    parser.add_argument("--gmail", action="store_true", help="Gmail inbox + Rocket Money CSV check")
    parser.add_argument("--csv", type=str, help="Parse a local Rocket Money CSV file")
    parser.add_argument("--xlsx", type=str, help="Import a Rocket Money XLSX transaction export")
    parser.add_argument("--sandbox", action="store_true", help="Deploy first 2 agents in sandbox + start eval loop")
    parser.add_argument("--eval-interval", type=int, default=86400, help="Evaluation cycle interval in seconds (default: 86400 = 24h)")
    parser.add_argument("--notify", action="store_true", help="Run daily review and send notifications")
    parser.add_argument("--notify-test", action="store_true", help="Send a test notification to verify setup")
    parser.add_argument("--calendar", action="store_true", help="Show today's schedule + calendar status")
    parser.add_argument("--calendar-week", action="store_true", help="Show this week's schedule")
    parser.add_argument("--calendar-sync", action="store_true", help="Sync Google Calendar + push bills to calendar")
    parser.add_argument("--calendar-auth", action="store_true", help="Authorize Google Calendar (OAuth flow)")
    parser.add_argument("--websites", action="store_true", help="Show status of all managed websites")
    parser.add_argument("--website-build", type=str, default=None, help="Build a website by domain (or 'all')")
    parser.add_argument("--website-deploy", type=str, default=None, help="Deploy a website by domain (or 'all')")
    parser.add_argument("--website-sync", action="store_true", help="Push website dashboards to Notion")
    parser.add_argument("--notion-sync", action="store_true", help="Full Notion workspace sync (all dashboards)")
    parser.add_argument("--notion-preview", action="store_true", help="Preview Notion pages that would be created (no API needed)")
    parser.add_argument("--n8n-sync", action="store_true", help="Push n8n workflow status to Notion dashboard")
    parser.add_argument("--n8n-status", action="store_true", help="Show n8n connection and workflow status")
    parser.add_argument("--devices", action="store_true",
                        help="Show all managed IoT/LAN devices")
    parser.add_argument("--device-audit", action="store_true",
                        help="Run device security audit")
    parser.add_argument("--scene", type=str, default=None,
                        help="Activate a home scene (movie, work, away, goodnight)")
    parser.add_argument("--home-event", type=str, default=None,
                        help="Fire a schedule event (wake, sleep, leave, arrive, sunrise, sunset)")
    parser.add_argument("--flipper", action="store_true",
                        help="Show Flipper Zero device profiles and capabilities")
    parser.add_argument("--rooms", action="store_true",
                        help="Show room layout with devices")
    parser.add_argument("--security-review", nargs="?", const="all", default=None,
                        help="Security remediation review (domain or 'all')")
    parser.add_argument("--security-sync", action="store_true",
                        help="Push remediation status to Notion")
    parser.add_argument("--connector-audit", action="store_true",
                        help="Audit Claude connector/MCP attack surface")
    parser.add_argument("--cfo", action="store_true",
                        help="Interactive CFO financial assistant (conversational)")
    parser.add_argument("--sentinel", action="store_true",
                        help="IoT Sentinel dashboard (network security + device control)")
    parser.add_argument("--sentinel-scan", action="store_true",
                        help="Run a one-time network scan and report anomalies")
    parser.add_argument("--sentinel-monitor", action="store_true",
                        help="Start continuous network monitoring")
    parser.add_argument("--sentinel-approve", type=int, default=None,
                        help="Approve a pending sentinel recommendation by index")
    parser.add_argument("--sentinel-deny", type=int, default=None,
                        help="Deny a pending sentinel recommendation by index")
    parser.add_argument("--network-audit", action="store_true",
                        help="LAN security audit (VLAN, DNS blocking, credentials)")
    parser.add_argument("--vpn-status", action="store_true",
                        help="Tailscale VPN connection status")
    parser.add_argument("--cfo-clean", action="store_true",
                        help="Clean ledger: strip sandbox data, RM goals, zero-balance dupes")
    parser.add_argument("--cfo-clean-dry", action="store_true",
                        help="Preview ledger cleanup without modifying anything")
    parser.add_argument("--cfo-connect", action="store_true",
                        help="Connect real bank accounts via Plaid (development mode)")
    parser.add_argument("--cfo-connect-port", type=int, default=8234,
                        help="Port for Plaid Link server (default: 8234)")
    parser.add_argument("--ollama", action="store_true", help="Ollama AI engine status + models")
    parser.add_argument("--ollama-benchmark", nargs="?", const="default", default=None,
                        help="Benchmark an Ollama model (default: configured model)")
    parser.add_argument("--ollama-pull", type=str, default=None, help="Pull a model from Ollama registry")
    parser.add_argument("--ollama-delete", type=str, default=None, help="Delete a local Ollama model")
    # Power Tools — Rails + Gin
    parser.add_argument("--power-tools", action="store_true",
                        help="Show Rails + Gin power tools status")
    parser.add_argument("--rails-new", type=str, default=None,
                        help="Scaffold a new Rails app (name)")
    parser.add_argument("--rails-api", action="store_true",
                        help="Generate API-only Rails app (use with --rails-new)")
    parser.add_argument("--rails-db", type=str, default="sqlite3",
                        help="Database adapter for Rails (sqlite3/postgresql/mysql)")
    parser.add_argument("--rails-server", type=str, default=None,
                        help="Start Rails dev server (path to app)")
    parser.add_argument("--rails-port", type=int, default=3000,
                        help="Rails server port (default: 3000)")
    parser.add_argument("--rails-install", action="store_true",
                        help="Install Ruby on Rails via gem")
    parser.add_argument("--gin-new", type=str, default=None,
                        help="Scaffold a new Gin (Go) app (name)")
    parser.add_argument("--gin-module", type=str, default=None,
                        help="Go module path for Gin app (default: app name)")
    parser.add_argument("--gin-server", type=str, default=None,
                        help="Start Gin dev server (path to app)")
    parser.add_argument("--gin-port", type=int, default=8080,
                        help="Gin server port (default: 8080)")
    parser.add_argument("--devpanel", action="store_true", help="Launch web-based dev panel")
    parser.add_argument("--devpanel-port", type=int, default=5100, help="Dev panel port (default: 5100)")
    parser.add_argument("--config", type=str, default=None, help="Path to config YAML")
    args = parser.parse_args()

    config_path = Path(args.config) if args.config else None
    config = load_config(config_path)
    guardian = GuardianOne(config=config)
    _build_agents(guardian)

    if args.cfo:
        cfo = guardian.get_agent("cfo")
        if cfo and isinstance(cfo, CFO):
            from guardian_one.core.cfo_router import run_cfo_repl
            run_cfo_repl(cfo)
        else:
            print("CFO agent not available.")
        guardian.shutdown()
        return

    if args.cfo_clean or args.cfo_clean_dry:
        cfo = guardian.get_agent("cfo")
        if cfo and isinstance(cfo, CFO):
            dry = args.cfo_clean_dry
            mode = "DRY RUN (no changes)" if dry else "LIVE — modifying ledger"
            print(f"\n  CFO Ledger Cleanup — {mode}")
            print("  " + "=" * 50)

            # Back up before live cleanup
            if not dry:
                import shutil
                backup = Path(config.data_dir) / "cfo_ledger.backup.json"
                src = Path(config.data_dir) / "cfo_ledger.json"
                if src.exists():
                    shutil.copy2(src, backup)
                    print(f"  Backup saved: {backup}")

            result = cfo.clean_ledger(dry_run=dry)

            if result["accounts_removed"]:
                print(f"\n  Accounts to remove ({len(result['accounts_removed'])}):")
                for a in result["accounts_removed"]:
                    print(f"    - {a}")
            if result["transactions_removed"]:
                print(f"\n  Transactions to remove ({len(result['transactions_removed'])}):")
                shown = result["transactions_removed"][:20]
                for t in shown:
                    print(f"    - {t}")
                if len(result["transactions_removed"]) > 20:
                    print(f"    ... and {len(result['transactions_removed']) - 20} more")

            print(f"\n  Accounts:     {result['accounts_before']} -> {result['accounts_after']}")
            print(f"  Transactions: {result['transactions_before']} -> {result['transactions_after']}")

            if dry:
                print(f"\n  This was a dry run. Run --cfo-clean to apply.")
            else:
                # Show updated net worth
                nw = cfo.net_worth()
                print(f"\n  Updated net worth: ${nw:,.2f}")
                print(f"  Ledger saved.")
        else:
            print("CFO agent not available.")
        guardian.shutdown()
        return

    if args.cfo_connect:
        cfo = guardian.get_agent("cfo")
        if cfo and isinstance(cfo, CFO):
            from guardian_one.integrations.plaid_connect import run_plaid_link_server
            import os

            # Check and enforce development mode
            current_env = os.environ.get("PLAID_ENV", "sandbox")
            if current_env == "sandbox":
                print("\n  ================================================")
                print("  SWITCHING PLAID TO DEVELOPMENT MODE")
                print("  ================================================")
                print("  Your Plaid is currently in 'sandbox' (test data).")
                print("  Switching to 'development' for real bank access.")
                print()
                print("  If you haven't already:")
                print("  1. Go to https://dashboard.plaid.com")
                print("  2. Toggle your app to 'Development' mode")
                print("  3. Copy the Development secret (different from sandbox)")
                print("  4. Update PLAID_SECRET in .env with the development key")
                print()
                print("  Development mode is FREE for up to 100 bank connections.")
                print("  ================================================\n")

                # Update the env var for this session
                os.environ["PLAID_ENV"] = "development"

                # Also update the provider instance
                cfo.plaid._env = "development"
                cfo.plaid._base_url = "https://development.plaid.com"

            # Re-authenticate with new env
            if not cfo.plaid.has_credentials:
                print("  Set PLAID_CLIENT_ID and PLAID_SECRET in .env first.")
                print("  Get them free at https://dashboard.plaid.com/signup")
                guardian.shutdown()
                return

            auth_ok = cfo.plaid.authenticate()
            if not auth_ok:
                print(f"  Plaid auth failed: {cfo.plaid.last_error}")
                print()
                print("  Common fixes:")
                print("  - Make sure PLAID_SECRET is the Development key (not sandbox)")
                print("  - Toggle your Plaid app to Development at dashboard.plaid.com")
                guardian.shutdown()
                return

            print(f"  Plaid authenticated (env: {cfo.plaid._env})")
            result = run_plaid_link_server(cfo.plaid, port=args.cfo_connect_port)

            if result.get("success") and result.get("connected", 0) > 0:
                # Run an immediate sync to pull real data
                print("\n  Running initial sync...")
                sync = cfo.sync_plaid()
                print(f"  Pulled {sync.get('accounts_added', 0)} accounts, "
                      f"{sync.get('transactions_added', 0)} transactions")
                print(f"  Net worth: ${cfo.net_worth():,.2f}")
        else:
            print("CFO agent not available.")
        guardian.shutdown()
        return

    # --- Power Tools: Rails + Gin ---
    if (args.power_tools or args.rails_new or args.rails_server
            or args.rails_install or args.gin_new or args.gin_server):
        from guardian_one.integrations.rails_gin import (
            power_tools_status, scaffold_rails, scaffold_gin,
            start_rails_server, start_gin_server, install_rails,
        )

        if args.power_tools:
            status = power_tools_status()
            print()
            print("  POWER TOOLS — Rails + Gin")
            print("  " + "=" * 50)
            print(f"  Ruby:   {status['ruby']['status']:<16} {status['ruby']['version']}")
            print(f"  Rails:  {status['rails']['status']:<16} {status['rails']['version']}")
            print(f"  Go:     {status['go']['status']:<16} {status['go']['version']}")
            print(f"  Gin:    {status['gin']['status']:<16} {status['gin'].get('note', '')}")
            print()
            print("  RAILS CAPABILITIES")
            print("  " + "-" * 50)
            for cap in status["capabilities"]["rails"]:
                print(f"    - {cap}")
            print()
            print("  GIN CAPABILITIES")
            print("  " + "-" * 50)
            for cap in status["capabilities"]["gin"]:
                print(f"    - {cap}")
            print()
            print("  USE CASES")
            print("  " + "-" * 50)
            for key, desc in status["use_cases"].items():
                label = key.replace("_", " ").title()
                print(f"    {label}:")
                print(f"      {desc}")
            print()

        elif args.rails_install:
            print("\n  Installing Ruby on Rails...")
            result = install_rails()
            if result["success"]:
                if result.get("already_installed"):
                    print(f"  Rails already installed: {result['version']}")
                else:
                    print(f"  Rails installed: {result['version']}")
            else:
                print(f"  Installation failed: {result['error']}")

        elif args.rails_new:
            app_name = args.rails_new
            print(f"\n  Scaffolding Rails app: {app_name}")
            if args.rails_api:
                print("  Mode: API-only")
            print(f"  Database: {args.rails_db}")
            result = scaffold_rails(
                app_name=app_name,
                api_only=args.rails_api,
                database=args.rails_db,
            )
            if result["success"]:
                print(f"  [OK] Created at: {result['path']}")
                print(f"  Start with: python main.py --rails-server {result['path']}")
            else:
                print(f"  [FAILED] {result['error']}")

        elif args.gin_new:
            app_name = args.gin_new
            module = args.gin_module or app_name
            print(f"\n  Scaffolding Gin app: {app_name}")
            print(f"  Module: {module}")
            print(f"  Port: {args.gin_port}")
            result = scaffold_gin(
                app_name=app_name,
                module_path=module,
                port=args.gin_port,
            )
            if result["success"]:
                print(f"  [OK] Created at: {result['path']}")
                print(f"  Start with: python main.py --gin-server {result['path']}")
            else:
                print(f"  [FAILED] {result['error']}")

        elif args.rails_server:
            app_path = args.rails_server
            port = args.rails_port
            print(f"\n  Starting Rails server: {app_path} on port {port}")
            result = start_rails_server(app_path, port=port)
            if result["success"]:
                print(f"  [OK] PID {result['pid']} — {result['url']}")
            else:
                print(f"  [FAILED] {result['error']}")

        elif args.gin_server:
            app_path = args.gin_server
            port = args.gin_port
            print(f"\n  Starting Gin server: {app_path} on port {port}")
            result = start_gin_server(app_path, port=port)
            if result["success"]:
                print(f"  [OK] PID {result['pid']} — {result['url']}")
            else:
                print(f"  [FAILED] {result['error']}")

        guardian.shutdown()
        return

    if args.devpanel:
        from guardian_one.web.app import run_devpanel
        run_devpanel(guardian, port=args.devpanel_port)
        return

    if args.ollama or args.ollama_benchmark or args.ollama_pull or args.ollama_delete:
        from guardian_one.integrations.ollama_sync import OllamaSync

        ollama = OllamaSync(audit=guardian.audit)

        if args.ollama_pull:
            model_name = args.ollama_pull
            print(f"\n  Pulling model: {model_name}")
            print(f"  This may take a while for large models...")
            result = ollama.pull_model(model_name)
            if result["success"]:
                print(f"  [OK] {model_name} pulled successfully.")
            else:
                print(f"  [FAILED] {result['error']}")

        elif args.ollama_delete:
            model_name = args.ollama_delete
            print(f"\n  Deleting model: {model_name}")
            result = ollama.delete_model(model_name)
            if result["success"]:
                print(f"  [OK] {model_name} deleted.")
            else:
                print(f"  [FAILED] {result['error']}")

        elif args.ollama_benchmark:
            model_name = (
                args.ollama_benchmark
                if args.ollama_benchmark != "default"
                else None
            )
            target = model_name or "configured default"
            print(f"\n  Benchmarking: {target}")
            result = ollama.benchmark(model_name)
            if result.success:
                print(f"  Model:      {result.model}")
                print(f"  Tokens:     {result.tokens_generated}")
                print(f"  Speed:      {result.tokens_per_second} tok/s")
                print(f"  Total:      {result.total_duration_ms:.0f}ms")
                print(f"  Load:       {result.load_duration_ms:.0f}ms")
                print(f"  Inference:  {result.eval_duration_ms:.0f}ms")
            else:
                print(f"  [FAILED] {result.error}")

        else:
            # --ollama: show full status
            print(ollama.status_text())

            # Also show AI engine provider status
            ai_status = guardian.ai_status()
            active = ai_status["active_provider"] or "OFFLINE"
            print(f"  AI Engine")
            print(f"  " + "-" * 40)
            print(f"  Active provider: {active}")
            print(f"  Primary:  {ai_status['primary_provider']}")
            print(f"  Fallback: {ai_status['fallback_provider'] or 'none'}")
            print(f"  Requests: {ai_status['total_requests']}")
            print(f"  Tokens:   {ai_status['total_tokens']}")
            print()

        guardian.shutdown()
        return

    if args.sandbox:
        from guardian_one.core.sandbox import SandboxDeployer
        from guardian_one.core.evaluator import PerformanceEvaluator
        deployer = SandboxDeployer(guardian)
        if deployer.deploy():
            evaluator = PerformanceEvaluator(
                guardian,
                data_dir=config.data_dir,
                cycle_seconds=args.eval_interval,
            )
            evaluator.start()
        else:
            print("  Sandbox deployment failed. Fix issues above before retrying.")
        guardian.shutdown()
        return

    if args.schedule:
        from guardian_one.core.scheduler import Scheduler
        sched = Scheduler(guardian)
        sched.start()
        guardian.shutdown()
        return

    if args.devices or args.device_audit or args.scene or args.home_event or args.flipper or args.rooms:
        from guardian_one.agents.device_agent import DeviceAgent
        from guardian_one.homelink.devices import DeviceRegistry
        dev_config = AgentConfig(name="device_agent", enabled=True,
                                 allowed_resources=["devices", "network"])
        dev_registry = DeviceRegistry()
        dev_agent = DeviceAgent(config=dev_config, audit=guardian.audit,
                                device_registry=dev_registry)
        dev_agent.initialize()

        if args.scene:
            scene_id = f"scene-{args.scene}" if not args.scene.startswith("scene-") else args.scene
            results = dev_agent.activate_scene(scene_id)
            scene = dev_agent.automation.get_scene(scene_id)
            if scene:
                print(f"\n  Scene activated: {scene.name}")
                print(f"  {scene.description}")
                print(f"  Actions executed: {len(results)}")
                for r in results:
                    target = r["device_id"] or r["room_id"]
                    print(f"    -> {r['action']} on {target}")
            else:
                print(f"\n  Scene '{scene_id}' not found.")
                print("  Available scenes:")
                for s in dev_agent.automation.all_scenes():
                    print(f"    {s.scene_id}: {s.name}")

        elif args.home_event:
            event = args.home_event
            if event in ("sunrise", "sunset"):
                results = dev_agent.handle_solar_event(event)
            else:
                results = dev_agent.handle_schedule_event(event)
            print(f"\n  Event fired: {event}")
            print(f"  Actions executed: {len(results)}")
            for r in results:
                target = r["device_id"] or r["room_id"]
                print(f"    -> {r['action']} on {target}")

        elif args.flipper:
            flipper = dev_agent.flipper_audit()
            print("\n  FLIPPER ZERO — DEVICE INTERACTION PROFILES")
            print("  " + "=" * 50)
            for fp in flipper["devices"]:
                tested = "VERIFIED" if fp["tested"] else "UNTESTED"
                print(f"\n  {fp['device_id']}  [{tested}]")
                print(f"    Capabilities: {', '.join(fp['capabilities'])}")
                if fp["ir_file"]:
                    print(f"    IR remote: {fp['ir_file']}")
                if fp["sub_ghz_file"]:
                    print(f"    Sub-GHz: {fp['sub_ghz_file']}")
                if fp["notes"]:
                    print(f"    Notes: {fp['notes']}")
            print(f"\n  Total: {flipper['total_profiles']} profiles, "
                  f"{flipper['controllable_devices']} controllable, "
                  f"{flipper['untested_profiles']} untested")

        elif args.rooms:
            rooms = dev_registry.room_summary()
            print("\n  H.O.M.E. L.I.N.K. — ROOM LAYOUT")
            print("  " + "=" * 50)
            for room in rooms:
                auto_flags = []
                if room["auto_lights"]:
                    auto_flags.append("lights")
                if room["auto_blinds"]:
                    auto_flags.append("blinds")
                auto_str = f"  [auto: {', '.join(auto_flags)}]" if auto_flags else ""
                print(f"\n  {room['name']} ({room['type']}){auto_str}")
                for did in room["device_ids"]:
                    d = dev_registry.get(did)
                    if d:
                        print(f"    - {d.name} ({d.category.value})")

        elif args.device_audit:
            report = dev_agent.run()
            print(dev_agent.dashboard_text())
            if report.recommendations:
                print("  Recommendations:")
                for rec in report.recommendations:
                    print(f"    - {rec}")
            if report.alerts:
                print("\n  Alerts:")
                for alert in report.alerts:
                    print(f"    [!!] {alert}")
        else:
            print(dev_agent.dashboard_text())

    elif (args.sentinel or args.sentinel_scan or args.sentinel_monitor
          or args.sentinel_approve is not None or args.sentinel_deny is not None):
        from guardian_one.agents.iot_sentinel import IoTSentinel

        sentinel_cfg = config.agents.get(
            "iot_sentinel", AgentConfig(name="iot_sentinel", enabled=True,
                                        allowed_resources=["network", "devices", "mqtt", "security"]))
        sentinel = IoTSentinel(config=sentinel_cfg, audit=guardian.audit)
        sentinel.initialize()

        if args.sentinel_scan:
            report = sentinel.run()
            print(sentinel.dashboard_text())
            if report.recommendations:
                print("  Recommendations:")
                for rec in report.recommendations:
                    print(f"    - {rec}")
            if report.alerts:
                print("\n  Alerts:")
                for alert in report.alerts:
                    print(f"    [!!] {alert}")

        elif args.sentinel_monitor:
            print("\n  Starting continuous network monitoring...")
            print(f"  Subnet: {sentinel.scanner.subnet}")
            print(f"  Interval: {sentinel.monitor.scan_interval}s")
            print("  Press Ctrl+C to stop.\n")
            sentinel.start_monitoring()
            try:
                import signal
                signal.pause()
            except (KeyboardInterrupt, AttributeError):
                # AttributeError: signal.pause not available on Windows
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    pass
            sentinel.stop_monitoring()
            print("\n  Monitoring stopped.")
            print(sentinel.monitor.summary_text())

        elif args.sentinel_approve is not None:
            if sentinel.approve_recommendation(args.sentinel_approve):
                print(f"\n  Recommendation #{args.sentinel_approve} approved.")
            else:
                print(f"\n  Invalid recommendation index: {args.sentinel_approve}")
                pending = sentinel.pending_approvals()
                if pending:
                    print("  Pending approvals:")
                    for i, p in enumerate(pending):
                        print(f"    [{i}] {p['action']}: {p['description']}")
                else:
                    print("  No pending approvals.")

        elif args.sentinel_deny is not None:
            if sentinel.deny_recommendation(args.sentinel_deny):
                print(f"\n  Recommendation #{args.sentinel_deny} denied.")
            else:
                print(f"\n  Invalid recommendation index: {args.sentinel_deny}")

        else:
            # --sentinel: show dashboard
            sentinel.run()  # Run a scan to populate data
            print(sentinel.dashboard_text())

    elif args.network_audit:
        from guardian_one.homelink.lan_security import LanSecurityAuditor
        from guardian_one.homelink.devices import DeviceRegistry

        registry = DeviceRegistry()
        registry.load_defaults()
        auditor = LanSecurityAuditor(registry)
        print(auditor.audit_text())

    elif args.vpn_status:
        from guardian_one.homelink.tailscale import TailscaleClient
        client = TailscaleClient(audit=guardian.audit)
        print(client.summary_text())
        health = client.health_check()
        if health["issues"]:
            print("  Issues:")
            for issue in health["issues"]:
                print(f"    - {issue}")

    elif args.brief:
        print(guardian.monitor.weekly_brief_text())
    elif args.homelink:
        print(json.dumps(guardian.gateway.all_services_status(), indent=2))
        print(f"\nVault: {json.dumps(guardian.vault.health_report(), indent=2)}")
        print(f"\nRegistry: {guardian.registry.list_all()}")
    elif args.gmail:
        gmail = guardian.get_agent("gmail")
        if gmail and isinstance(gmail, GmailAgent):
            report = guardian.run_agent("gmail")
            print(json.dumps(report.__dict__, indent=2, default=str))
        else:
            print("Gmail agent not available.")
    elif args.csv:
        gmail = guardian.get_agent("gmail")
        if gmail and isinstance(gmail, GmailAgent):
            transactions = gmail.parse_rocket_money_csv(args.csv)
            summary = gmail.summarize_csv_transactions(transactions)
            print(f"\nRocket Money CSV: {args.csv}")
            print(f"Transactions: {summary['total_transactions']}")
            print(json.dumps(summary, indent=2, default=str))
        else:
            print("Gmail agent not available.")
    elif args.xlsx:
        cfo = guardian.get_agent("cfo")
        if cfo and isinstance(cfo, CFO):
            print(f"\n  Importing: {args.xlsx}")
            result = cfo.sync_from_xlsx(args.xlsx)
            print(f"  Transactions in file: {result['transactions_in_file']}")
            print(f"  New transactions added: {result['transactions_added']}")
            print(f"  Accounts added: {result['accounts_added']}")
            print(f"  Accounts updated: {result['accounts_updated']}")
            print(f"\n  Totals: {result['total_accounts']} accounts, {result['total_transactions']} transactions")
            print(f"  Net worth: ${cfo.net_worth():,.2f}")
            print(f"  Ledger saved.")
        else:
            print("CFO agent not available.")
    elif args.notify or args.notify_test:
        from guardian_one.utils.notifications import build_notification_stack, Urgency

        mgr, router = build_notification_stack(timezone_name=config.timezone)

        # Show channel status
        channels = [type(c).__name__ for c in mgr._channels]
        print(f"\n  Notification channels: {', '.join(channels)}")

        if args.notify_test:
            # Send a test notification to verify the setup
            n = mgr.notify(
                "Guardian", "Test Notification",
                "This is a test from Guardian One. If you see this, notifications are working!",
                Urgency.HIGH,
            )
            print(f"  Test notification sent ({n.urgency.value}).")
            if mgr.held_count > 0:
                print(f"  Note: {mgr.held_count} notification(s) held (quiet hours).")
                print(f"  Use HIGH/CRITICAL urgency during quiet hours.")
        else:
            # Full daily review → notifications
            cfo = guardian.get_agent("cfo")
            if cfo and isinstance(cfo, CFO):
                review = cfo.daily_review()
                net = cfo.net_worth()
                fired = router.route_daily_review(review, net_worth=net)

                print(f"\n  Daily review complete — {len(fired)} notification(s) fired:")
                for n in fired:
                    print(f"    [{n.urgency.value.upper():8s}] {n.title}")

                if mgr.held_count > 0:
                    print(f"\n  {mgr.held_count} notification(s) held for quiet hours (will send after 7 AM).")
            else:
                print("  CFO agent not available.")
    elif args.calendar_auth:
        chronos = guardian.get_agent("chronos")
        if chronos and isinstance(chronos, Chronos):
            from guardian_one.integrations.calendar_sync import GoogleCalendarProvider
            provider = GoogleCalendarProvider()
            if not provider.has_credentials:
                print("\n  Google Calendar credentials not found.")
                print("  To set up:")
                print("  1. Go to Google Cloud Console → APIs → Calendar API → Enable")
                print("  2. Create OAuth 2.0 credentials (Desktop app)")
                print("  3. Download the JSON file")
                print("  4. Save it as config/google_credentials.json")
                print("     (or set GOOGLE_CALENDAR_CREDENTIALS env var)")
            else:
                print("\n  Starting Google Calendar authorization...")
                success = provider.complete_oauth_flow()
                if success:
                    print("\n  Google Calendar authorized successfully!")
                    print("  Token saved — you can now use --calendar and --calendar-sync.")
                else:
                    print(f"\n  Authorization failed: {provider.last_error}")
        else:
            print("  Chronos agent not available.")
    elif args.calendar or args.calendar_week:
        chronos = guardian.get_agent("chronos")
        if chronos and isinstance(chronos, Chronos):
            # Show calendar status
            status = chronos.calendar_status()
            connected = status.get("authenticated", False)
            print(f"\n  Google Calendar: {'connected' if connected else 'offline'}")
            if not connected:
                err = status.get("last_error", "")
                if err:
                    print(f"  ({err})")
                print("  Run --calendar-auth to connect your Google Calendar.\n")

            if args.calendar_week:
                events = chronos.week_schedule()
                label = "THIS WEEK'S SCHEDULE"
            else:
                events = chronos.today_schedule()
                label = "TODAY'S SCHEDULE"

            print(f"\n  {label}")
            print("  " + "-" * 56)
            if not events:
                if connected:
                    print("  No events found.")
                else:
                    print("  (Calendar offline — showing local events only)")
            else:
                for ev in events:
                    start = ev.get("start", "")
                    end = ev.get("end", "")
                    # Format times nicely
                    try:
                        s = datetime.fromisoformat(start)
                        e = datetime.fromisoformat(end)
                        time_str = f"{s.strftime('%a %b %d %I:%M %p')} — {e.strftime('%I:%M %p')}"
                    except (ValueError, TypeError):
                        time_str = f"{start} — {end}"
                    loc = ev.get("location", "")
                    loc_str = f" @ {loc}" if loc else ""
                    print(f"  {time_str}")
                    print(f"    {ev['title']}{loc_str}")
                    print()
            print(f"  Total: {len(events)} event(s)")
        else:
            print("  Chronos agent not available.")
    elif args.calendar_sync:
        chronos = guardian.get_agent("chronos")
        if chronos and isinstance(chronos, Chronos):
            status = chronos.calendar_status()
            if not status.get("authenticated", False):
                print("\n  Google Calendar not connected.")
                print("  Run --calendar-auth first to authorize.")
            else:
                print("\n  Syncing Google Calendar...")
                # 1. Pull events from Google Calendar → Chronos
                sync_result = chronos.sync_google_calendar()
                print(f"  Pulled {sync_result['events_pulled']} events "
                      f"({sync_result.get('new_added', 0)} new)")
                if sync_result.get("conflicts"):
                    print(f"  Conflicts detected: {sync_result['conflicts']}")
                    for detail in sync_result.get("conflict_details", []):
                        print(f"    [!] {detail}")

                # 2. Push CFO bills → Google Calendar
                cfo = guardian.get_agent("cfo")
                if cfo and isinstance(cfo, CFO):
                    bills = [
                        {
                            "name": b.name,
                            "amount": b.amount,
                            "due_date": b.due_date,
                            "auto_pay": b.auto_pay,
                            "paid": b.paid,
                        }
                        for b in cfo._bills
                    ]
                    if bills:
                        bill_result = chronos.sync_bills_to_calendar(bills)
                        print(f"  Bills → Calendar: {bill_result.get('synced', 0)} added, "
                              f"{bill_result.get('skipped', 0)} skipped")
                    else:
                        print("  No bills to sync to calendar.")
                print(f"\n  Sync complete. Total events in Chronos: {sync_result.get('total_events', 0)}")
        else:
            print("  Chronos agent not available.")
    elif args.sync or args.sync_once:
        cfo = guardian.get_agent("cfo")
        if not (cfo and isinstance(cfo, CFO)):
            print("CFO agent not available.")
            guardian.shutdown()
            return
        _run_sync_loop(cfo, interval=args.sync_interval, once=args.sync_once)
    elif args.connect:
        cfo = guardian.get_agent("cfo")
        if cfo and isinstance(cfo, CFO):
            from guardian_one.integrations.plaid_connect import run_plaid_link_server
            result = run_plaid_link_server(cfo.plaid, port=args.connect_port)
            if not result.get("success"):
                print(f"\n  {result.get('error', 'Connection failed')}")
        else:
            print("CFO agent not available.")
    elif args.validate:
        cfo = guardian.get_agent("cfo")
        if cfo and isinstance(cfo, CFO):
            _print_validation_report(cfo)
        else:
            print("CFO agent not available.")
    elif args.agent:
        report = guardian.run_agent(args.agent)
        print(json.dumps(report.__dict__, indent=2, default=str))
    elif args.dashboard:
        cfo = guardian.get_agent("cfo")
        if cfo and isinstance(cfo, CFO):
            # Try to get Gmail financial data for the daily check
            gmail_data = None
            gmail = guardian.get_agent("gmail")
            if gmail:
                try:
                    from guardian_one.agents.gmail_agent import GmailAgent
                    if isinstance(gmail, GmailAgent):
                        inbox = gmail.check_inbox()
                        fin_emails = gmail.search_financial_emails(days_back=7)
                        gmail_data = {
                            "inbox": inbox,
                            "financial_emails": fin_emails,
                        }
                except Exception:
                    pass  # Gmail not configured — skip

            password = args.dashboard_password
            path = cfo.generate_excel(
                output_path=Path(config.data_dir) / "dashboard.xlsx",
                password=password,
                gmail_data=gmail_data,
            )
            print(f"\n  Dashboard saved to: {path}")
            if password:
                print(f"  Protected with password (sheets locked, structure locked).")
            print(f"  Open it in Excel, Google Sheets, or LibreOffice.")
            print()

            # Print the daily review summary
            review = cfo.daily_review(gmail_data)
            status_icon = {"all_clear": "[OK]", "review": "[!!]", "needs_attention": "[!!]"}.get(
                review["overall_status"], "[??]")
            print(f"  {status_icon} {review['overall_message']}")
            print()

            # Quick text summary
            d = cfo.dashboard()
            print(f"  Net Worth:     ${d['net_worth']:>12,.2f}")
            for atype, bal in d.get("balances_by_type", {}).items():
                label = atype.replace("_", " ").title()
                print(f"  {label + ':':15s} ${bal:>12,.2f}")

            # Budget alerts
            for alert in d.get("budget_alerts", []):
                print(f"  [BUDGET] {alert}")
        else:
            print("CFO agent not available.")
    elif args.notion_sync:
        from guardian_one.integrations.notion_sync import NotionSync
        import os

        root_page_id = os.environ.get("NOTION_ROOT_PAGE_ID", "")
        if not root_page_id:
            print("  NOTION_ROOT_PAGE_ID not set. Add it to .env to enable Notion sync.")
        else:
            sync = NotionSync(
                gateway=guardian.gateway,
                vault=guardian.vault,
                audit=guardian.audit,
                root_page_id=root_page_id,
            )

            # Collect agent data
            agents_data = []
            for name in guardian.list_agents():
                agent = guardian.get_agent(name)
                if agent:
                    try:
                        report = agent.report()
                        agents_data.append({
                            "name": name,
                            "status": report.status,
                            "health_score": 90 if report.status == "idle" else 70,
                            "schedule_interval": agent.config.schedule_interval_minutes,
                            "last_run": getattr(report, "last_run", "never"),
                            "allowed_resources": agent.config.allowed_resources,
                        })
                    except Exception:
                        agents_data.append({
                            "name": name,
                            "status": "unknown",
                            "health_score": 50,
                            "schedule_interval": 0,
                            "last_run": "never",
                            "allowed_resources": [],
                        })

            # Collect integration health from gateway
            services_data = []
            for svc_name in guardian.gateway.list_services():
                status = guardian.gateway.service_status(svc_name)
                health = guardian.monitor.assess_service(svc_name)
                services_data.append({
                    "name": svc_name,
                    "circuit_state": status.get("circuit_state", "unknown"),
                    "success_rate": status.get("success_rate", 0),
                    "avg_latency_ms": status.get("avg_latency_ms", 0),
                    "risk_score": health.risk_score,
                })

            # Roadmap phases (static for now)
            roadmap = [
                {"phase": "Phase 1 — Foundation", "status": "complete", "priority": "P0",
                 "description": "Core agents, Vault, Gateway, Audit, CLI"},
                {"phase": "Phase 2 — Financial Intelligence", "status": "complete", "priority": "P0",
                 "description": "CFO agent, Plaid, Empower, Rocket Money, Excel dashboards"},
                {"phase": "Phase 3 — Integrations", "status": "in_progress", "priority": "P1",
                 "description": "Notion sync, Google Calendar, Gmail, notifications"},
                {"phase": "Phase 4 — Web Properties", "status": "in_progress", "priority": "P1",
                 "description": "Website management, builds, deploys, security scans"},
                {"phase": "Phase 5 — Autonomy", "status": "planned", "priority": "P2",
                 "description": "Sandbox evaluator, self-healing, multi-device sync"},
            ]

            # Deliverables
            deliverables = [
                {"title": "Notion Workspace Sync", "status": "complete", "audience": "Jeremy",
                 "due_date": "2026-03-16", "description": "Write-only Notion dashboard push"},
                {"title": "Website Management", "status": "complete", "audience": "Jeremy",
                 "due_date": "2026-03-10", "description": "Build/deploy pipeline for 2 sites"},
                {"title": "Financial Dashboard", "status": "complete", "audience": "Jeremy",
                 "due_date": "2026-02-28", "description": "Excel dashboard + daily review"},
            ]

            print("\n  Syncing Guardian One workspace to Notion...")
            result = sync.full_sync(
                agents=agents_data,
                roadmap_phases=roadmap,
                services=services_data,
                deliverables=deliverables,
            )

            status = "OK" if result.success else "FAILED"
            print(f"  [{status}] {result.pages_created} pages created, "
                  f"{result.pages_updated} updated, "
                  f"{result.blocks_written} blocks written "
                  f"({result.duration_ms:.0f}ms)")
            if result.errors:
                for err in result.errors:
                    print(f"    [ERROR] {err}")

    elif args.notion_preview:
        from guardian_one.integrations.notion_sync import NotionSync

        # Build a lightweight sync instance (no API needed for preview)
        sync = NotionSync(
            gateway=guardian.gateway,
            vault=guardian.vault,
            audit=guardian.audit,
            root_page_id="preview-mode",
        )

        # Collect agent data
        agents_data = []
        for name in guardian.list_agents():
            agent = guardian.get_agent(name)
            if agent:
                try:
                    report = agent.report()
                    agents_data.append({
                        "name": name,
                        "status": report.status,
                        "health_score": 90 if report.status == "idle" else 70,
                        "schedule": f"every {agent.config.schedule_interval_minutes}m",
                        "allowed_resources": ", ".join(agent.config.allowed_resources) or "default",
                    })
                except Exception:
                    agents_data.append({
                        "name": name,
                        "status": "unknown",
                        "health_score": 50,
                        "schedule": "manual",
                        "allowed_resources": "default",
                    })

        # Integration health from gateway
        services_data = []
        for svc_name in guardian.gateway.list_services():
            status = guardian.gateway.service_status(svc_name)
            health = guardian.monitor.assess_service(svc_name)
            services_data.append({
                "name": svc_name,
                "circuit_state": status.get("circuit_state", "unknown"),
                "success_rate": status.get("success_rate", 0),
                "avg_latency_ms": status.get("avg_latency_ms", 0),
                "risk_score": health.risk_score,
            })

        roadmap = [
            {"phase": "Phase 1 — Foundation", "status": "complete", "priority": "P0",
             "description": "Core agents, Vault, Gateway, Audit, CLI"},
            {"phase": "Phase 2 — Financial Intelligence", "status": "complete", "priority": "P0",
             "description": "CFO agent, Plaid, Empower, Rocket Money, Excel dashboards"},
            {"phase": "Phase 3 — Integrations", "status": "in_progress", "priority": "P1",
             "description": "Notion sync, Google Calendar, Gmail, notifications"},
            {"phase": "Phase 4 — Web Properties", "status": "in_progress", "priority": "P1",
             "description": "Website management, builds, deploys, security scans"},
            {"phase": "Phase 5 — Autonomy", "status": "planned", "priority": "P2",
             "description": "Sandbox evaluator, self-healing, multi-device sync"},
        ]

        deliverables = [
            {"title": "Notion Workspace Sync", "status": "complete", "audience": "Jeremy",
             "due_date": "2026-03-16", "description": "Write-only Notion dashboard push"},
            {"title": "Website Management", "status": "complete", "audience": "Jeremy",
             "due_date": "2026-03-10", "description": "Build/deploy pipeline for 2 sites"},
            {"title": "Financial Dashboard", "status": "complete", "audience": "Jeremy",
             "due_date": "2026-02-28", "description": "Excel dashboard + daily review"},
        ]

        print(sync.preview_workspace(
            agents=agents_data,
            roadmap_phases=roadmap,
            services=services_data,
            deliverables=deliverables,
        ))

    elif args.n8n_sync:
        if not guardian.notion_sync:
            print("  NOTION_ROOT_PAGE_ID not set. Add it to .env to enable Notion sync.")
        else:
            print("\n  Syncing n8n workflow status to Notion...")
            result = guardian.sync_n8n_to_notion()
            if result:
                status = "OK" if result.success else "FAILED"
                print(f"  [{status}] {result.pages_created} pages created, "
                      f"{result.pages_updated} updated, "
                      f"{result.blocks_written} blocks written "
                      f"({result.duration_ms:.0f}ms)")
                if result.errors:
                    for err in result.errors:
                        print(f"    [ERROR] {err}")

    elif args.n8n_status:
        from guardian_one.integrations.n8n_sync import N8nWorkflow
        print("\n  n8n Workflow Engine Status")
        print("  " + "=" * 40)

        connected = False
        if guardian.n8n_provider.has_credentials:
            connected = guardian.n8n_provider.authenticate()

        print(f"  Connection: {'Connected' if connected else 'Disconnected'}")
        print(f"  Gateway service: {'registered' if guardian.n8n_provider.has_credentials else 'not found'}")

        if connected:
            workflows = guardian.n8n_provider.list_workflows()
            active = sum(1 for w in workflows if w.active)
            print(f"  Workflows: {len(workflows)} total, {active} active")
            for wf in workflows:
                icon = "[ON] " if wf.active else "[OFF]"
                print(f"    {icon} {wf.name} (id: {wf.id})")
        else:
            print("  Set N8N_BASE_URL and N8N_API_KEY in .env to connect.")

        # Show local workflows from WebArchitect if available
        wa = guardian.get_agent("web_architect")
        if wa and hasattr(wa, "list_workflows"):
            local_wfs = wa.list_workflows()
            if local_wfs:
                print(f"\n  Local workflows (WebArchitect): {len(local_wfs)}")
                for wf_id, wf in local_wfs.items():
                    print(f"    [{wf_id}] {wf.name}")

        print(f"\n  Notion sync: {'available' if guardian.notion_sync else 'not configured'}")
        if guardian.notion_sync:
            print("  Run --n8n-sync to push workflow status to Notion.")
        print()

    elif args.connector_audit:
        audit_report = guardian.registry.connector_audit()
        print()
        print("  CLAUDE CONNECTOR / MCP ATTACK SURFACE AUDIT")
        print("  " + "=" * 56)
        print(f"  Total registered:      {audit_report['total_registered']}")
        print(f"  Guardian integrations:  {audit_report['guardian_integrations']}")
        print(f"  MCP connectors:        {audit_report['mcp_connectors']}")
        print(f"  Total threats modeled:  {audit_report['total_threats_modeled']}")
        print()

        if audit_report["dangerous_connectors"]:
            print("  [!!] DANGEROUS CONNECTORS (disconnect when idle):")
            for name in audit_report["dangerous_connectors"]:
                record = guardian.registry.get(name)
                if record:
                    crits = sum(1 for t in record.threat_model if t.severity == "critical")
                    print(f"    [CRITICAL x{crits}] {name}: {record.description[:60]}...")
            print()

        if audit_report["critical_threat_services"]:
            print("  Services with CRITICAL threats:")
            for svc in audit_report["critical_threat_services"]:
                print(f"    {svc['service']}: {svc['count']} critical threat(s)")
            print()

        if audit_report["untracked_connectors"]:
            print(f"  Untracked connectors ({len(audit_report['untracked_connectors'])}):")
            for name in audit_report["untracked_connectors"]:
                print(f"    [-] {name}")
            print()

        print(f"  Recommendation: {audit_report['recommendation']}")
        print()

    elif args.security_review is not None or args.security_sync:
        from guardian_one.core.security_remediation import SecurityRemediationTracker

        tracker = SecurityRemediationTracker()
        domain = args.security_review if args.security_review else "all"

        if domain == "all" or args.security_sync:
            tracker.load_all_domains()
        else:
            tracker.load_domain_defaults(domain)

        if args.security_sync:
            from guardian_one.integrations.notion_remediation_sync import NotionRemediationSync
            from guardian_one.integrations.notion_sync import NotionSync
            import os

            root_page_id = os.environ.get("NOTION_ROOT_PAGE_ID", "")
            if not root_page_id:
                print("  NOTION_ROOT_PAGE_ID not set. Add it to .env to enable Notion sync.")
            else:
                sync = NotionSync(
                    gateway=guardian.gateway,
                    vault=guardian.vault,
                    audit=guardian.audit,
                    root_page_id=root_page_id,
                )
                rem_sync = NotionRemediationSync(sync, guardian.audit)
                result = rem_sync.push_remediation_dashboard(tracker)
                status = "OK" if result.success else "FAILED"
                print(f"  [{status}] Remediation dashboard — "
                      f"{result.blocks_written} blocks written ({result.duration_ms:.0f}ms)")
                if result.errors:
                    for err in result.errors:
                        print(f"    [ERROR] {err}")
        else:
            # CLI review
            print()
            print(tracker.summary_text())
            print()

            # Show overdue tasks prominently
            overdue = tracker.overdue_tasks()
            if overdue:
                print(f"\n  OVERDUE TASKS ({len(overdue)}):")
                for task in overdue:
                    print(f"    [!!] {task.severity.value}: {task.title} (due {task.due_date})")

            # Show agent responsibility breakdown
            stats = tracker.summary_stats()
            print(f"\n  Domains tracked: {', '.join(tracker.domains())}")
            print(f"  Auto-verifiable: {len(tracker.auto_verifiable_tasks())}/{stats['total_tasks']} tasks")

    elif args.websites or args.website_build or args.website_deploy or args.website_sync:
        from guardian_one.agents.website_manager import WebsiteManager

        wa_cfg = config.agents.get("web_architect", AgentConfig(name="web_architect"))
        mgr = WebsiteManager(config=wa_cfg, audit=guardian.audit)
        mgr.initialize()

        if args.website_build:
            domain = args.website_build
            if domain == "all":
                results = mgr.build_all()
                for d, build in results.items():
                    print(f"  [{build.status.upper()}] {d} — {len(build.pages_built)} pages built")
            else:
                build = mgr.build_site(domain)
                print(f"  [{build.status.upper()}] {domain} — {len(build.pages_built)} pages built")
                if build.errors:
                    for err in build.errors:
                        print(f"    [ERROR] {err}")

        elif args.website_deploy:
            domain = args.website_deploy
            if domain == "all":
                # Build first, then deploy
                mgr.build_all()
                results = mgr.deploy_all()
                for d, result in results.items():
                    if result.get("success"):
                        print(f"  [DEPLOYED] {d} — {result['pages_deployed']} pages, SSL enabled")
                    else:
                        print(f"  [FAILED] {d} — {result.get('error', 'unknown')}")
            else:
                mgr.build_site(domain)
                result = mgr.deploy_site(domain)
                if result.get("success"):
                    print(f"  [DEPLOYED] {domain} — {result['pages_deployed']} pages, SSL enabled")
                else:
                    print(f"  [FAILED] {domain} — {result.get('error', 'unknown')}")

        elif args.website_sync:
            from guardian_one.integrations.notion_website_sync import NotionWebsiteDashboard
            from guardian_one.integrations.notion_sync import NotionSync
            import os

            root_page_id = os.environ.get("NOTION_ROOT_PAGE_ID", "")
            if not root_page_id:
                print("  NOTION_ROOT_PAGE_ID not set. Add it to .env to enable Notion sync.")
            else:
                sync = NotionSync(
                    gateway=guardian.gateway,
                    vault=guardian.vault,
                    audit=guardian.audit,
                    root_page_id=root_page_id,
                )
                dashboard = NotionWebsiteDashboard(sync, guardian.audit)
                all_data = {d: mgr.site_dashboard_data(d) for d in mgr.list_sites()}
                results = dashboard.sync_all(all_data)
                for key, sr in results.items():
                    status = "OK" if sr.success else "FAILED"
                    print(f"  [{status}] {key} — {sr.blocks_written} blocks written")

        else:
            # --websites: show status
            print(mgr.summary())

    elif args.summary:
        print(guardian.daily_summary())
    else:
        reports = guardian.run_all()
        for report in reports:
            print(f"\n--- {report.agent_name} ---")
            print(f"  Status: {report.status}")
            print(f"  Summary: {report.summary}")
            if report.alerts:
                for alert in report.alerts:
                    print(f"  [ALERT] {alert}")
            if report.recommendations:
                for rec in report.recommendations:
                    print(f"  [REC] {rec}")
        print("\n" + "=" * 60)
        print(guardian.daily_summary())

    guardian.shutdown()


if __name__ == "__main__":
    main()
