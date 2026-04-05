# Agency AI → Guardian One Agent Map

Maps Agency AI personality specs (from Ryzen library) to Guardian One's
runtime agents. Use this as a reference when enhancing Guardian One agents
with Agency-sourced patterns, workflows, and deliverables.

## Active Agent Mappings

| Guardian One Agent | Agency Personality | File | Enhancement |
|---|---|---|---|
| **Guardian** (core/guardian.py) | Agents Orchestrator | `curated/agents-orchestrator.md` | Pipeline orchestration, quality gates, retry logic |
| **CFO** (agents/cfo.py) | Finance Tracker | `curated/support-finance-tracker.md` | Budget frameworks, variance analysis, compliance |
| **Security** (core/security.py) | Security Engineer | `curated/engineering-security-engineer.md` | Threat modeling, SDLC integration, supply chain |
| **Security** (core/security_remediation.py) | Threat Detection Engineer | `curated/engineering-threat-detection-engineer.md` | Detection rules, anomaly patterns, alert tuning |
| **Web Architect** (agents/web_architect.py) | DevOps Automator | `curated/engineering-devops-automator.md` | CI/CD pipelines, deployment automation |
| **Web Architect** (agents/website_manager.py) | SRE | `curated/engineering-sre.md` | Reliability, SLOs, incident management |
| **Archivist** (agents/archivist.py) | Legal Compliance Checker | `curated/support-legal-compliance-checker.md` | Data governance, retention policies, audit |
| **Archivist** (agents/archivist.py) | Compliance Auditor | `curated/compliance-auditor.md` | Regulatory compliance, evidence collection |
| **H.O.M.E. L.I.N.K.** (homelink/) | Infrastructure Maintainer | `curated/support-infrastructure-maintainer.md` | System health, monitoring, capacity planning |
| **Device Agent** (agents/device_agent.py) | Incident Response Commander | `curated/engineering-incident-response-commander.md` | Incident handling, escalation procedures |
| **Health Agent** (planned) | Healthcare Marketing Compliance | `curated/healthcare-marketing-compliance.md` | HIPAA compliance, clinical content review |
| **Scheduler** (core/scheduler.py) | Workflow Architect | `curated/specialized-workflow-architect.md` | Workflow design, automation patterns |
| **Evaluator** (core/evaluator.py) | Reality Checker | `curated/testing-reality-checker.md` | Quality validation, evidence-based scoring |

## New Capabilities (Not Yet in Guardian One)

These Agency agents represent capabilities that could extend Guardian One:

| Agency Agent | Potential Guardian One Role |
|---|---|
| Backend Architect | Code architecture review for Guardian One itself |
| API Tester | Automated API testing for integrations |
| Evidence Collector | Visual regression testing for managed websites |
| Analytics Reporter | Operational analytics and trend reporting |
| Executive Summary Generator | Weekly/monthly executive briefs |
| Senior Project Manager | Roadmap tracking and sprint planning |
| Sprint Prioritizer | Task prioritization for the ROADMAP_LIVE items |
| Workflow Optimizer | Optimize agent scheduling and coordination |

## Strategy Resources

The `strategy/` directory contains NEXUS orchestration docs:

- `strategy/QUICKSTART.md` — Quick start for multi-agent pipelines
- `strategy/nexus-strategy.md` — Full NEXUS doctrine
- `strategy/playbooks/` — Phase-by-phase playbooks (discovery → launch → operate)
- `strategy/runbooks/` — Scenario-specific runbooks (MVP, incident response, etc.)
- `strategy/coordination/` — Agent activation prompts and handoff templates

## Full Library

The complete Agency AI library (150+ agents across 17 divisions) lives in the
**Ryzen** repository. Browse it for additional agents as Guardian One evolves.
