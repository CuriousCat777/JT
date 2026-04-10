# Guardian One — One-Page App Summary

## What it is
Guardian One is a Python-based multi-agent personal operations platform that coordinates specialized agents (e.g., Chronos, Archivist, CFO) under a central orchestrator. It emphasizes local control/data sovereignty, access policies, auditability, and secure integration routing.

## Who it's for
Primary user/persona: an owner-operator who wants one command surface to coordinate personal scheduling, finance, automation, and security workflows (the repo defaults to owner "Jeremy Paulo Salvino Tabernero").

## What it does (key features)
- Boots a central Guardian orchestrator that registers and supervises multiple agents.
- Runs all agents or one targeted agent via CLI flags.
- Enforces per-identity/per-agent access policies for allowed resources.
- Logs system/agent actions and produces daily summaries with pending-review alerts.
- Mediates cross-agent conflicts (time overlap, budget, resource contention).
- Routes external service calls through a gateway with service registry + monitoring.
- Secures secrets in an encrypted vault and auto-seeds selected credentials from environment variables.

## How it works (repo-evidenced architecture)
- **Entry/Control Plane:** `main.py` parses CLI options and builds core agents (Chronos, Archivist, CFO, DoorDash, Gmail, WebArchitect, DevCoach).
- **Core Orchestrator:** `GuardianOne` initializes config, audit log, mediator, access controller, AI engine, gateway, vault, integration registry, and monitor.
- **Security Layer:** Access policies and encrypted vault are initialized at startup; passphrase is required (`GUARDIAN_MASTER_PASSPHRASE`).
- **Agent Lifecycle:** Agents are registered, initialized, and run individually or as a full run cycle; conflicts are checked and recorded.
- **Service/Data Flow:** Config (`config/guardian_config.yaml`) + env vars -> Guardian boot -> agent execution -> conflict resolution + audit records -> summary/report outputs.
- **Not found in repo:** End-user UI architecture diagram and production infrastructure topology.

## How to run (minimal getting started)
1. Install Python 3.10+ and dependencies: `pip install -r requirements.txt`.
2. Create a passphrase env var for the vault (required): `GUARDIAN_MASTER_PASSPHRASE=<your-secret>`.
3. (Optional) Add `.env` credentials for integrations used by your scenario.
4. Run once: `python main.py`.
5. Useful quick checks: `python main.py --summary` and `python main.py --agent cfo`.
