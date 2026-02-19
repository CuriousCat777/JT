"""Guardian One — main entry point.

Usage:
    python main.py              # Run all agents once and print daily summary
    python main.py --summary    # Print daily summary only
    python main.py --dashboard  # Print CFO financial dashboard
    python main.py --agent NAME # Run a single agent
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from guardian_one.core.config import AgentConfig, load_config
from guardian_one.core.guardian import GuardianOne
from guardian_one.agents.chronos import Chronos
from guardian_one.agents.archivist import Archivist
from guardian_one.agents.cfo import CFO


def _build_agents(guardian: GuardianOne) -> None:
    """Instantiate and register all subordinate agents."""
    config = guardian.config

    chronos_cfg = config.agents.get("chronos", AgentConfig(name="chronos"))
    guardian.register_agent(Chronos(config=chronos_cfg, audit=guardian.audit))

    archivist_cfg = config.agents.get("archivist", AgentConfig(name="archivist"))
    guardian.register_agent(Archivist(config=archivist_cfg, audit=guardian.audit))

    cfo_cfg = config.agents.get("cfo", AgentConfig(name="cfo"))
    guardian.register_agent(CFO(config=cfo_cfg, audit=guardian.audit))


def main() -> None:
    parser = argparse.ArgumentParser(description="Guardian One — multi-agent system")
    parser.add_argument("--summary", action="store_true", help="Print daily summary")
    parser.add_argument("--dashboard", action="store_true", help="Print CFO dashboard")
    parser.add_argument("--agent", type=str, help="Run a single agent by name")
    parser.add_argument("--config", type=str, default=None, help="Path to config YAML")
    args = parser.parse_args()

    config_path = Path(args.config) if args.config else None
    config = load_config(config_path)
    guardian = GuardianOne(config=config)
    _build_agents(guardian)

    if args.agent:
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
        # Default: run all agents and print summary
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
