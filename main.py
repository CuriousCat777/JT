"""Guardian One — main entry point.

Usage:
    python main.py              # Run all agents once and print daily summary
    python main.py --summary    # Print daily summary only
    python main.py --dashboard  # Print CFO financial dashboard
    python main.py --agent NAME # Run a single agent
    python main.py --brief      # H.O.M.E. L.I.N.K. weekly security brief
    python main.py --homelink   # H.O.M.E. L.I.N.K. service status
    python main.py --gmail      # Gmail inbox status + Rocket Money CSV check
    python main.py --csv PATH   # Parse a local Rocket Money CSV and summarize
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from guardian_one.core.config import AgentConfig, load_config
from guardian_one.core.guardian import GuardianOne
from guardian_one.agents.chronos import Chronos
from guardian_one.agents.archivist import Archivist
from guardian_one.agents.cfo import CFO
from guardian_one.agents.doordash import DoorDashAgent
from guardian_one.agents.gmail_agent import GmailAgent


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Guardian One — multi-agent system")
    parser.add_argument("--summary", action="store_true", help="Print daily summary")
    parser.add_argument("--dashboard", action="store_true", help="Print CFO dashboard")
    parser.add_argument("--agent", type=str, help="Run a single agent by name")
    parser.add_argument("--brief", action="store_true", help="H.O.M.E. L.I.N.K. weekly security brief")
    parser.add_argument("--homelink", action="store_true", help="H.O.M.E. L.I.N.K. service status")
    parser.add_argument("--gmail", action="store_true", help="Gmail inbox + Rocket Money CSV check")
    parser.add_argument("--csv", type=str, help="Parse a local Rocket Money CSV file")
    parser.add_argument("--config", type=str, default=None, help="Path to config YAML")
    args = parser.parse_args()

    config_path = Path(args.config) if args.config else None
    config = load_config(config_path)
    guardian = GuardianOne(config=config)
    _build_agents(guardian)

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
    elif args.agent:
        report = guardian.run_agent(args.agent)
        print(json.dumps(report.__dict__, indent=2, default=str))
    elif args.dashboard:
        cfo = guardian.get_agent("cfo")
        if cfo and isinstance(cfo, CFO):
            print(json.dumps(cfo.dashboard(), indent=2, default=str))
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
