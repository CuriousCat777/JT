# VARYS — Cybersecurity Sentinel System

## Plan Handoff Document

**Status**: Design Complete — Ready for Implementation
**Owner**: Guardian One (JT repo)
**Date**: 2026-04-03

---

## Overview

VARYS is the cybersecurity sentinel within the Overlord Guardian ecosystem. It operates as a modular, event-driven security orchestration system with three core layers: Ingestion, Detection, and Response.

### Distribution Across Repos

| Layer | Repo | Path | Rationale |
|-------|------|------|-----------|
| **Brain + Orchestration** | JT | `guardian_one/varys/` | Core agent lives alongside other Guardian agents |
| **Detection Rules + Anomaly** | JT | `guardian_one/varys/detection/` | Tightly coupled to response engine |
| **Response Engine** | JT | `guardian_one/varys/response/` | Needs access to Guardian core (audit, security, notifications) |
| **Threat Intel Search** | Ryzen | `search/threat_intel/` | Leverages existing search infrastructure (Whoosh/Typesense/Meilisearch) |
| **React Dashboard** | JT | `guardian_one/varys/dashboard/` | Vite+React SPA served alongside Flask API |

---

## Implementation Plan

### Phase 1: Foundation (JT repo)

**Goal**: VARYS agent skeleton integrated into Guardian One

#### Files to Create

```
guardian_one/varys/
├── __init__.py
├── agent.py                # VarysAgent(BaseAgent) — main orchestrator
├── config.py               # VARYS-specific config loader
├── ingestion/
│   ├── __init__.py
│   ├── wazuh_connector.py  # Wazuh manager API client
│   ├── auth_logs.py        # Okta / Azure AD / local auth log parser
│   ├── cloud_logs.py       # AWS CloudTrail / GCP Audit ingestion
│   └── network.py          # Zeek / Suricata telemetry connector
├── detection/
│   ├── __init__.py
│   ├── sigma_engine.py     # Sigma rule loader + matcher
│   ├── anomaly.py          # PyOD IsolationForest behavioral detection
│   ├── risk_scoring.py     # Composite risk score calculator
│   └── rules/
│       ├── privilege_escalation.yaml
│       ├── lateral_movement.yaml
│       ├── credential_abuse.yaml
│       └── data_exfiltration.yaml
├── response/
│   ├── __init__.py
│   ├── containment.py      # Host isolation, process kill
│   ├── identity.py         # Token/session revocation
│   ├── alerting.py         # Slack/email/notification dispatch
│   └── playbooks/
│       ├── critical_incident.yaml
│       └── suspicious_login.yaml
├── brain/
│   ├── __init__.py
│   ├── llm_triage.py       # LLM-assisted alert triage + summarization
│   └── incident_report.py  # Auto-generated incident reports
└── api/
    ├── __init__.py
    └── routes.py            # FastAPI/Flask blueprint for VARYS endpoints
```

#### Integration Points (JT)

- `guardian_one/core/guardian.py` — Register `VarysAgent` in agent list
- `guardian_one/core/ai_engine.py` — LLM layer for `brain/llm_triage.py`
- `guardian_one/core/audit.py` — Immutable logging for all VARYS actions
- `guardian_one/core/security.py` — Access control for VARYS API
- `guardian_one/utils/notifications.py` — Alert dispatch
- `guardian_one/homelink/lan_security.py` — Network scan data feed

#### Dependencies to Add (requirements.txt)

```
wazuh-api>=4.0
pyod>=1.1
sigma-cli>=0.9
opensearch-py>=2.4
```

---

### Phase 2: Threat Intel Search (Ryzen repo)

**Goal**: Extend search infrastructure to index and query threat intelligence

#### Files to Create

```
search/threat_intel/
├── __init__.py
├── ioc_indexer.py           # Index IOCs (IPs, hashes, domains) into search engines
├── sigma_search.py          # Search Sigma rules by ATT&CK technique/tactic
├── cve_monitor.py           # CVE feed ingestion + relevance scoring
└── threat_feed_connector.py # MISP / OTX / AbuseIPDB feed connectors
```

#### Integration Points (Ryzen)

- `search/server.py` — Add `/api/threat-intel/search` endpoint
- `search/seed_documents.py` — Add threat intel sample data seeder
- `search/tests/` — Threat intel search test suite (extend existing 3,099 tests)
- Reuse existing Whoosh/Typesense/Meilisearch multi-engine pattern

#### New Test Categories

- IOC search (IP, hash, domain, URL)
- Sigma rule search by technique ID
- CVE relevance ranking
- Feed freshness validation

---

### Phase 3: React Dashboard (JT repo)

**Goal**: Real-time security dashboard served alongside Flask

#### Files to Create

```
guardian_one/varys/dashboard/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── index.html
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/
│   │   └── varys.ts          # API client for VARYS endpoints
│   ├── components/
│   │   ├── AlertFeed.tsx      # Live alert stream
│   │   ├── ThreatMap.tsx      # Geo-mapped threat origins
│   │   ├── RiskGauge.tsx      # Composite risk score dial
│   │   ├── IncidentTimeline.tsx
│   │   └── DetectionRules.tsx # Rule management UI
│   ├── hooks/
│   │   └── useVarysSocket.ts  # WebSocket for real-time events
│   └── styles/
│       └── globals.css
└── public/
```

#### Stack

- React 19 + TypeScript
- Vite (dev server + build)
- Tailwind CSS
- Recharts (visualizations)
- WebSocket for real-time alert feed

#### Build Integration

```bash
# Dev
cd guardian_one/varys/dashboard && npm run dev  # Vite on port 5173

# Production
npm run build  # Output to guardian_one/web/static/varys/
```

Flask serves the built React app at `/varys/dashboard`.

---

## Detection Logic Reference

### Sigma Rule Format

```yaml
title: Suspicious Privilege Escalation
logsource:
  category: process_creation
detection:
  selection:
    CommandLine|contains:
      - "sudo su"
      - "chmod 777"
  condition: selection
level: high
tags:
  - attack.privilege_escalation
  - attack.t1548
```

### Anomaly Detection

```python
from pyod.models.iforest import IForest

model = IForest(contamination=0.05)
model.fit(user_behavior_baseline)

if model.predict(new_event) == 1:
    flag = "anomaly"
```

### LLM Triage

```python
def triage(event):
    prompt = f"""
    You are VARYS, a cybersecurity sentinel.
    Analyze this event:
    {event}

    Output:
    - severity (low/med/high/critical)
    - likely attack type (MITRE ATT&CK)
    - recommended action
    """
    return ai_engine.query(prompt)
```

---

## Response Engine

### Deterministic-first, AI-assisted-second

```python
if severity == "critical":
    containment.isolate_host(ip)
    identity.revoke_tokens(user)
    alerting.send("CRITICAL INCIDENT", channels=["slack", "email"])
elif severity == "high":
    alerting.send("HIGH SEVERITY ALERT", channels=["slack"])
    # Queue for human review
```

### Safety Constraints

- **NEVER** auto-execute destructive actions without rule confirmation
- **NEVER** allow LLM to directly invoke containment — LLM recommends, rules execute
- All response actions logged to `guardian_one/core/audit.py`
- Human override always available via CLI and dashboard

---

## Risk Mitigations

| Risk | Mitigation |
|------|-----------|
| False positives | Layered detection (rules + ML + LLM triage) |
| LLM hallucination | LLM recommends only; deterministic rules execute |
| Log ingestion gaps | Health monitor with alerting on ingestion failures |
| VARYS as attack target | Isolated process, mTLS API auth, audit trail |
| Alert fatigue | Severity thresholds, deduplication, LLM summarization |

---

## Session Pickup Instructions

Future Claude Code sessions should:

1. Read this document first
2. Check `guardian_one/varys/` for existing implementation progress
3. Run `python -m pytest tests/ -v` and `python -m pytest search/tests/ -v` before and after changes
4. Follow the phased approach — don't skip ahead
5. Register VarysAgent in `guardian_one/core/guardian.py` once Phase 1 skeleton is complete
