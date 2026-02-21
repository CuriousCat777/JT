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
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from guardian_one.core.config import AgentConfig, load_config
from guardian_one.core.guardian import GuardianOne
from guardian_one.agents.chronos import Chronos
from guardian_one.agents.archivist import Archivist
from guardian_one.agents.cfo import CFO
from guardian_one.agents.doordash import DoorDashAgent
from guardian_one.agents.gmail_agent import GmailAgent
from guardian_one.agents.web_architect import WebArchitect


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
    parser.add_argument("--sandbox", action="store_true", help="Deploy first 2 agents in sandbox + start eval loop")
    parser.add_argument("--eval-interval", type=int, default=86400, help="Evaluation cycle interval in seconds (default: 86400 = 24h)")
    parser.add_argument("--config", type=str, default=None, help="Path to config YAML")
    args = parser.parse_args()

    config_path = Path(args.config) if args.config else None
    config = load_config(config_path)
    guardian = GuardianOne(config=config)
    _build_agents(guardian)

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

    if args.brief:
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
