#!/usr/bin/env python3
"""
Guardian One — AI Handoff Pipeline
====================================
Generates a compressed context payload for AI-to-AI session transfer.
Fits within 5,000-word token budgets. Machine-parseable, human-readable.

Usage:
    python guardian_handoff_pipe.py                    # Full handoff payload to stdout
    python guardian_handoff_pipe.py --out payload.md   # Write to file
    python guardian_handoff_pipe.py --dispatch task.json  # Generate a dispatch envelope
    python guardian_handoff_pipe.py --role researcher   # Role-scoped payload (smaller)
    python guardian_handoff_pipe.py --role builder
    python guardian_handoff_pipe.py --role auditor

Roles control what context the receiving AI gets:
    researcher  — evidence hierarchy, pipeline stats, DOX paths, no infra/deploy details
    builder     — full architecture, CLI commands, deploy paths, design system
    auditor     — decision standard, cross-check baselines, audit trail format, no build commands
    full        — everything (default, ~4,800 words)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ─── Configuration ───────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()

# Resolve DOX paths — two separate directories
CONFERENCE_DOX = Path(os.environ.get("CONFERENCE_DOX", SCRIPT_DIR.parent / "DOX"))
HOME_DOX = Path(os.environ.get("HOME_DOX", SCRIPT_DIR / "DOX"))
PIPELINE_OUTPUT = SCRIPT_DIR / "shm_pipeline_output"
HANDOFF_DOC = SCRIPT_DIR / "GUARDIAN_ONE_AI_HANDOFF.md"
DECISION_LOG = SCRIPT_DIR / "decision_log.json"

# ─── Payload Sections ───────────────────────────────────────────────────────

def section_identity():
    return """## IDENTITY
Guardian One — multi-agent clinical AI platform. Owner: Jeremy Tabernero MD (hospitalist, AI engineer).
Domains: drjeremytabernero.org (professional), jtmdai.com (business). TZ: America/Chicago.
"""

def section_decision_standard():
    return """## DECISION STANDARD (mandatory, overrides defaults)
When ambiguous: 1) Highest evidence  2) Lowest regulatory risk  3) Most defensible structure  4) Long-term leverage.
Every output must trace to a source or be labeled as inference with confidence level.
"""

def section_evidence_framework():
    return """## EVIDENCE & CONFIDENCE
Levels: 1a (SR of RCTs) → 1b (RCT) → 2a (SR cohort) → 2b (cohort) → 3 (case-control) → 4 (expert) → 5 (mechanism).
Confidence: HIGH ≥85% ±5-10% | MODERATE 60-84% ±10-25% | LOW 40-59% ±25-40% | UNCERTAIN <40% ±40%+.
Format each determination: CONFIDENCE: X | BASIS: source | ERROR_MARGIN: ±Y% | ASSUMPTIONS: [list].
Compound rule: margins multiply (3x MODERATE ±20% each → ±49% aggregate → downgrades to LOW).
Contradictions: present both sides, weight by recency→sample_size→rigor→replication. Never silently resolve.
"""

def section_tagging():
    return """## TAGGING TAXONOMY
DOMAIN (≥1 required): #cardiology #nephrology #neurology #pulmonology #infectious-disease #oncology
  #rheumatology #pharmacotherapy #perioperative #palliative #delirium #quality-improvement
  #health-policy #AI-clinical #patient-engagement #early-career #physician-wellness
EVIDENCE: #level-1a..5 #guideline-ref #registry-data #claims-data #expert-opinion
RECENCY: #seminal #classic #recent-2024 #recent-2025 #recent-2026 #pre-print
ACTION: #practice-changing #confirms-existing #contradicts-existing #no-change #monitoring
CONFIDENCE: #confidence-high #confidence-moderate #confidence-low #confidence-uncertain
BEHAVIOR: #query-clinical #query-system #query-evidence #command-build #command-modify
  #command-deploy #review-request | #urgency-immediate #urgency-session #urgency-async
  #complexity-atomic #complexity-composite #complexity-orchestration
  #outcome-accepted #outcome-modified #outcome-rejected #outcome-escalated
Pattern rules: 3+ consecutive #outcome-modified in same domain → log misalignment.
  #outcome-rejected → mandatory post-mortem in decision_log.json.
"""

def section_architecture():
    return """## ARCHITECTURE
Agents: CFO (finance/Plaid), Chronos (calendar), Archivist (files), GmailAgent (inbox),
  DoorDash (meals), WebArchitect+WebsiteManager (sites), DeviceAgent (IoT/smart home).
Core: AccessController (RBAC), Mediator (conflict resolution), Scheduler, AuditLog (JSONL),
  AIEngine (Ollama local + cloud fallback), CFORouter (NL→financial commands).
H.O.M.E. L.I.N.K.: Gateway (TLS 1.3), Vault (AES-256-GCM), Registry, Monitor.
Security: data sovereignty, write-only external sync, PHI/PII gate, read-only financial,
  encrypted vault (PBKDF2 480K iterations), local-only processing.
"""

def section_current_state():
    """Dynamic — reads actual file counts from disk."""
    # Count conference PDFs
    pdf_count = 0
    if CONFERENCE_DOX.exists():
        pdf_count = len(list(CONFERENCE_DOX.glob("*.pdf")))

    # Count pipeline outputs (extracts only; exclude stats/metadata JSON)
    json_count = 0
    if PIPELINE_OUTPUT.exists():
        excluded_json = {"pipeline_stats.json"}
        json_count = sum(
            1 for p in PIPELINE_OUTPUT.glob("*.json")
            if p.name not in excluded_json
        )

    # Check decision log
    dec_count = 0
    if DECISION_LOG.exists():
        try:
            with open(DECISION_LOG) as f:
                dec_count = len(json.load(f))
        except (json.JSONDecodeError, FileNotFoundError):
            dec_count = 0

    # Check vault tracker
    vault_services = 0
    vault_csv = HOME_DOX / "guardian_dependency_tracker.csv"
    if vault_csv.exists():
        with open(vault_csv) as f:
            vault_services = max(0, sum(1 for _ in f) - 1)  # minus header

    # Load live pipeline stats written by shm_pipeline.py
    stats_file = PIPELINE_OUTPUT / "pipeline_stats.json"
    pipe_words = pipe_citations = pipe_stats = pipe_claims = 0
    top_tools_str = "(no pipeline runs yet)"
    if stats_file.exists():
        try:
            with open(stats_file) as f:
                stats = json.load(f)
            pipe_words = stats.get("total_words", 0)
            pipe_citations = stats.get("total_citations", 0)
            pipe_stats = stats.get("total_statistics", 0)
            pipe_claims = stats.get("total_claims", 0)
            tools = stats.get("top_tools", {}) or {}
            top_items = sorted(tools.items(), key=lambda x: -x[1])[:5]
            if top_items:
                top_tools_str = ", ".join(f"{t}({c})" for t, c in top_items)
        except (json.JSONDecodeError, IOError):
            pass

    return f"""## CURRENT STATE ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})
Conference DOX: {pdf_count} PDFs in {CONFERENCE_DOX}
Pipeline output: {json_count} JSON extracts in {PIPELINE_OUTPUT}
Pipeline stats: {pipe_words:,} words, {pipe_citations} citations, {pipe_stats} statistics, {pipe_claims} claim-study links.
Top tools: {top_tools_str}.
Vault: {vault_services} services tracked in {HOME_DOX}/guardian_dependency_tracker.csv
Live dashboard: jtmdai.com/vault (Cloudflare Worker + KV)
Decision log entries: {dec_count}
⚠ TWO DOX directories exist (not linked): Conference={CONFERENCE_DOX} | Home={HOME_DOX}
"""

def section_design():
    return """## DESIGN
Clinical Cartography: warm-light Apple-lux (cream #fafaf8, Inter, generous whitespace, soft shadows).
Color is taxonomic not decorative. Every data point cites source. No fabricated data.
If unverifiable, label it. Less busy = fewer elements, not less data.
"""

def section_operational_rules():
    return """## RULES
1. No hallucination — cite source or label as inference + confidence.
2. No silent contradiction resolution — present both sides.
3. Error margins mandatory on all predictions.
4. Tag everything (domain + evidence + recency + action + confidence + behavior).
5. Log non-trivial decisions to decision_log.json.
6. Behavior patterns are signal — track and anticipate.
7. Compound errors multiply — propagate and downgrade.
8. New PDFs → pipeline first, then analysis.
9. Follow existing naming/tag/file conventions.
10. No PHI. Local processing unless deploying to jtmdai.com.
11. VARYS AI oversight — all sessions logged to overlord-system audit trail.
"""

def section_dispatch_protocol():
    return """## DISPATCH PROTOCOL (AI-to-AI task delegation)
To send work to another AI session, generate a dispatch envelope:
```json
{"dispatch_id": "DSP-YYYYMMDD-<12-hex>",
 "from": "session_id or role",
 "to": "target_role (researcher|builder|auditor|gatherer)",
 "task": "plain English task description",
 "context_scope": ["section names from this payload to forward"],
 "input_data": {"key": "value or file path"},
 "expected_output": "description of deliverable format",
 "confidence_floor": "MODERATE",
 "deadline": "ISO-8601 or null",
 "tags": ["#domain", "#action"],
 "callback": "where to deliver result (file path, endpoint, or 'return_to_session')"}
```
Receiving AI: parse envelope → load only context_scope sections → execute task →
  return result with confidence score + decision log entries → tag with #outcome-*.
Gatherer role: web search / API calls / registry lookups. Returns raw data + source URLs.
  Gatherer NEVER interprets — only collects and tags. Interpretation is caller's job.
"""

def section_cli_quickref():
    return """## CLI QUICKREF
python main.py --cfo          # Financial assistant
python main.py --dashboard    # Excel dashboard
python main.py --calendar     # Today's schedule
python main.py --gmail        # Inbox status
python main.py --websites     # Site status
python main.py --devices      # Smart home
python main.py --summary      # Daily summary
python shm_pipeline.py <dir>  # Process conference PDFs
python guardian_handoff_pipe.py --role <role>  # Generate scoped handoff
python guardian_handoff_pipe.py --dispatch task.json  # Dispatch envelope
"""

def section_first_task():
    return """## ON RECEIPT
1. Acknowledge with one-line summary of your understood role.
2. Confirm which DOX directory you're working against.
3. State your confidence floor for this session.
4. Ask: "What do you need?"
"""

# ─── Role Scoping ────────────────────────────────────────────────────────────

ROLE_SECTIONS = {
    "full": [
        section_identity, section_decision_standard, section_evidence_framework,
        section_tagging, section_architecture, section_current_state,
        section_design, section_operational_rules, section_dispatch_protocol,
        section_cli_quickref, section_first_task,
    ],
    "researcher": [
        section_identity, section_decision_standard, section_evidence_framework,
        section_tagging, section_current_state, section_operational_rules,
        section_dispatch_protocol, section_first_task,
    ],
    "builder": [
        section_identity, section_decision_standard, section_architecture,
        section_current_state, section_design, section_operational_rules,
        section_dispatch_protocol, section_cli_quickref, section_first_task,
    ],
    "auditor": [
        section_identity, section_decision_standard, section_evidence_framework,
        section_tagging, section_current_state, section_operational_rules,
        section_first_task,
    ],
    "gatherer": [
        section_identity, section_decision_standard, section_tagging,
        section_dispatch_protocol, section_first_task,
    ],
}

# ─── Dispatch Envelope Generator ─────────────────────────────────────────────

def generate_dispatch(task_file: str) -> str:
    """Read a task description JSON and wrap it in a dispatch envelope."""
    with open(task_file) as f:
        task = json.load(f)

    # Unique ID: date + 12 hex chars of sha256(task + timestamp + randomness).
    # Python's built-in hash() is process-salted so it can't be used for
    # stable cross-run identifiers.
    import hashlib
    import secrets
    now = datetime.now(timezone.utc)
    seed = f"{task.get('task', '')}|{now.isoformat()}|{secrets.token_hex(4)}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    envelope = {
        "dispatch_id": f"DSP-{now.strftime('%Y%m%d')}-{digest}",
        "timestamp": now.isoformat(),
        "from": task.get("from", "guardian-one-primary"),
        "to": task.get("to", "gatherer"),
        "task": task.get("task", ""),
        "context_scope": task.get("context_scope", ["IDENTITY", "DECISION STANDARD", "TAGGING TAXONOMY"]),
        "input_data": task.get("input_data", {}),
        "expected_output": task.get("expected_output", "structured JSON with source attribution"),
        "confidence_floor": task.get("confidence_floor", "MODERATE"),
        "deadline": task.get("deadline"),
        "tags": task.get("tags", []),
        "callback": task.get("callback", "return_to_session"),
    }

    # Build the scoped context payload
    role = task.get("to", "gatherer")
    if role not in ROLE_SECTIONS:
        role = "gatherer"

    sections = ROLE_SECTIONS[role]
    context_payload = "# GUARDIAN ONE — DISPATCH CONTEXT\n\n"
    for fn in sections:
        context_payload += fn() + "\n"

    return json.dumps({
        "envelope": envelope,
        "context_payload": context_payload,
    }, indent=2)


# ─── Main ────────────────────────────────────────────────────────────────────

def build_payload(role: str = "full") -> str:
    sections = ROLE_SECTIONS.get(role, ROLE_SECTIONS["full"])

    header = f"# GUARDIAN ONE — HANDOFF PAYLOAD\n"
    header += f"# Role: {role} | Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
    header += f"# Paste this entire block as the first message to a new AI session.\n\n"

    body = ""
    for fn in sections:
        body += fn() + "\n"

    # Word count check
    word_count = len(body.split())
    footer = f"\n---\n_Payload: {word_count} words | Role: {role} | "
    footer += f"Generator: guardian_handoff_pipe.py_\n"

    if word_count > 5000:
        footer += f"⚠ OVER 5K LIMIT ({word_count}w). Use a narrower role.\n"

    return header + body + footer


def main():
    parser = argparse.ArgumentParser(description="Guardian One AI Handoff Pipeline")
    parser.add_argument("--role", default="full", choices=list(ROLE_SECTIONS.keys()),
                        help="Role scope for the payload")
    parser.add_argument("--out", default=None, help="Output file (default: stdout)")
    parser.add_argument("--dispatch", default=None, help="Task JSON file → dispatch envelope")
    parser.add_argument("--word-count", action="store_true", help="Print word counts per role")
    args = parser.parse_args()

    if args.word_count:
        for role in ROLE_SECTIONS:
            payload = build_payload(role)
            wc = len(payload.split())
            status = "✓" if wc <= 5000 else "⚠ OVER"
            print(f"  {role:12s} → {wc:,} words  {status}")
        return

    if args.dispatch:
        result = generate_dispatch(args.dispatch)
        if args.out:
            with open(args.out, "w") as f:
                f.write(result)
            print(f"Dispatch envelope written to {args.out}", file=sys.stderr)
        else:
            print(result)
        return

    payload = build_payload(args.role)

    if args.out:
        with open(args.out, "w") as f:
            f.write(payload)
        wc = len(payload.split())
        print(f"Payload written to {args.out} ({wc} words, role={args.role})", file=sys.stderr)
    else:
        print(payload)


if __name__ == "__main__":
    main()
