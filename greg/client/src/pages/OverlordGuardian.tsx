import { useEffect, useState, type ReactNode } from 'react';

// ─── THEME: "Sovereign Dark" — industrial/utilitarian, not AI slop ───
const T = {
  bg: '#0a0c10',
  bgCard: '#12151c',
  bgCardHover: '#181c26',
  bgAccent: '#1a1e2a',
  border: '#252a38',
  borderActive: '#3a4260',
  text: '#c8cdd8',
  textMuted: '#6b7394',
  textBright: '#e8ecf4',
  green: '#2dd4a0',
  greenDim: '#1a3d32',
  red: '#f0506e',
  redDim: '#3d1a24',
  amber: '#f5a623',
  amberDim: '#3d321a',
  blue: '#4da6ff',
  blueDim: '#1a2d3d',
  purple: '#a78bfa',
  purpleDim: '#2a1a3d',
  cyan: '#22d3ee',
  mono: "'IBM Plex Mono', 'Fira Code', monospace",
  sans: "'IBM Plex Sans', 'DM Sans', system-ui, sans-serif",
};

type StatusKey = 'DONE' | 'ACTIVE' | 'BLOCKED' | 'PENDING' | 'DESIGNED';

const STATUS: Record<StatusKey, { color: string; bg: string; label: string }> = {
  DONE: { color: T.green, bg: T.greenDim, label: 'COMPLETE' },
  ACTIVE: { color: T.blue, bg: T.blueDim, label: 'IN PROGRESS' },
  BLOCKED: { color: T.red, bg: T.redDim, label: 'BLOCKED' },
  PENDING: { color: T.amber, bg: T.amberDim, label: 'PENDING' },
  DESIGNED: { color: T.purple, bg: T.purpleDim, label: 'DESIGNED' },
};

// ─── DATA: Full project state from all prior conversations + project knowledge ───
const SYSTEM_STATE = {
  owner: 'Jeremy Paulo Salvino Tabernero, MD',
  system: 'Overlord Guardian',
  version: 'Phase 1 — Foundation',
  authority: 'Root → Guardian One → Subordinate Agents',
  lastUpdate: '2026-04-03',
  hardware: [
    {
      name: 'ASUS ROG Strix Flow',
      role: 'PRIMARY DEV',
      ram: '64GB',
      os: 'Windows',
      status: 'ACTIVE',
      notes: 'Command Center. $2,149. Alienware external monitor.',
    },
    {
      name: 'MacBook Air',
      role: 'MOBILE DEV',
      ram: '—',
      os: 'macOS',
      status: 'BLOCKED',
      notes: 'Python 3.12.3 only. Missing: Homebrew, Git, Node, Claude Code CLI.',
    },
    {
      name: 'MacBook Pro',
      role: 'SECONDARY',
      ram: '—',
      os: 'macOS',
      status: 'ACTIVE',
      notes: 'Cursor + vibe coding environment.',
    },
    {
      name: 'Dell Desktop',
      role: 'HEAVY COMPUTE',
      ram: '—',
      os: 'WSL2/Ubuntu',
      status: 'ACTIVE',
      notes: 'WSL2 for heavier workloads.',
    },
  ],
  network: {
    upstream: 'Starlink (locked hardware — no VLAN, no MAC allowlist)',
    devices: 27,
    gap: 'Cannot enforce network policy. Management plane locked.',
    recommendation: 'Ubiquiti UniFi Dream Machine SE — open decision.',
  },
};

const AGENTS = [
  {
    id: 'guardian-one',
    name: 'Guardian One',
    role: 'Orchestrator / Sovereign Identity Log',
    status: 'DESIGNED',
    progress: 75,
    description:
      'Append-only, hash-chained decision log. Foundation layer for all agents. Schema v0.1.0 complete. Log engine, entries, hash chain, file I/O, date queries, CSV export, backup, sorting, OOP structure, API calls, text dashboard, web server + HTML dashboard all covered across 4 lessons + launcher.',
    artifacts: [
      'schema.py (v0.1.0)',
      'guardian_system.py (CLI)',
      'guardian_lesson_2.py',
      'guardian_lesson_3.py (OOP + API)',
      'guardian_lesson_4.py (Web + HTML)',
      'guardian_launcher.py (Control Center CLI)',
      'guardian_one_log.json',
    ],
    categories: [
      'financial',
      'medical_self',
      'medical_dependent',
      'professional',
      'legal',
      'document',
      'system',
      'relational',
      'correction',
      'state_snapshot',
    ],
    next: 'Deploy log engine to ROG. Initialize production log. Connect to Discovery module.',
  },
  {
    id: 'varys',
    name: 'VARYS',
    role: 'Network Intelligence (Master of Whisperers)',
    status: 'DESIGNED',
    progress: 60,
    description:
      'Nine-pillar network intelligence agent. Device discovery, trust-tier classification (SOVEREIGN/TRUSTED/MONITORED/QUARANTINE/UNKNOWN), security monitoring, energy tracking, maintenance alerting, plain English comms, ranked action plans, immutable hash-chained audit logging, behavioral drift detection. Dashboard at localhost:8181.',
    artifacts: [
      'varys.py (production agent)',
      'deploy_varys.sh (bash deploy)',
      'CLAUDE.md (Guardian handoff directive)',
      'CLAUDE_MASTER.md (combined operating directive)',
    ],
    categories: [
      'device_discovery',
      'trust_classification',
      'security_monitoring',
      'energy_tracking',
      'maintenance_alerting',
      'audit_logging',
      'drift_detection',
    ],
    next: 'Requires router upgrade (UniFi Dream Machine SE) for enforcement vs. observation-only. Deploy observation mode on current hardware.',
  },
  {
    id: 'discovery',
    name: 'Discovery Module',
    role: 'Record Discovery & Retrieval Tracker',
    status: 'DESIGNED',
    progress: 50,
    description:
      'Maps all known and requestable records about the user. Each record source has location, legal basis, retrieval method, and status. Integrates with Guardian One log via guardian_entry_id. Covers professional licenses, provider registries, employer profiles, education, financial, credit, insurance, medical, government, data brokers, social media, background checks, legal/court, property, immigration, domain registration.',
    artifacts: ['discovery.py (v0.1.0)', 'Discovery Report (Python schema)', 'OSINT Digital Footprint Report', 'OSINT Validation Pipeline'],
    categories: ['DISCOVERED', 'REQUESTED', 'RECEIVED', 'DEPOSITED', 'OPTED_OUT', 'UNAVAILABLE', 'NEEDS_VERIFICATION'],
    next: 'Execute record requests. Begin HIPAA/FCRA/CCPA retrieval cycles. Populate Stage 5 user validation checkpoint.',
  },
  {
    id: 'jtmedai',
    name: 'JTMedAI',
    role: 'Healthcare AI Integration Intelligence',
    status: 'ACTIVE',
    progress: 40,
    description:
      'AI integration intelligence for healthcare systems. Telehealth simulation pipeline with case telehosp_ami_001 (high-acuity chest pain / ACS). Scoring rubric, teaching points, safety net gap analysis. Dashboard deployed at jtmdai.com. CFO dashboard variant. Transparency dashboard with analytics consent layer. Self-sovereign physician identity (W3C DID compliant).',
    artifacts: ['jtmedai_dashboard (React)', 'jtmedai_prototype (React — DID identity)', 'jtmdai_cfo_dashboard', 'telehosp_ami_001 case', 'jtmdai.com domain (registered)'],
    categories: ['telehealth_sim', 'friction_mapping', 'adoption_analytics', 'trust_index', 'physician_identity'],
    next: 'Build out case library. Deploy physician identity attestation. Connect to Guardian One for credential verification.',
  },
  {
    id: 'chronos',
    name: 'Chronos',
    role: 'Time & Schedule Intelligence',
    status: 'PENDING',
    progress: 0,
    description: 'Planned agent for temporal awareness, scheduling, and deadline management. Not yet designed.',
    artifacts: [],
    categories: [],
    next: 'Awaiting Phase 1 foundation completion.',
  },
  {
    id: 'data-custodian',
    name: 'Data Custodian',
    role: 'Data Governance & Backup',
    status: 'PENDING',
    progress: 0,
    description: 'Planned agent for data lifecycle management, backup orchestration, and storage sovereignty. Not yet designed.',
    artifacts: [],
    categories: [],
    next: 'Awaiting Phase 1 foundation completion.',
  },
  {
    id: 'finops',
    name: 'FinOps',
    role: 'Financial Operations Intelligence',
    status: 'PENDING',
    progress: 0,
    description: 'Planned agent for financial tracking, budget analysis, and spending intelligence. Not yet designed.',
    artifacts: [],
    categories: [],
    next: 'Awaiting Phase 1 foundation completion.',
  },
] as const;

const PHASE1_TASKS = [
  {
    id: 1,
    title: 'ROG Strix Environment Bootstrap',
    agent: 'SYSTEM',
    status: 'ACTIVE',
    priority: 'P0',
    description: 'Install Python 3.12+, Git, Node.js, Claude Code CLI on ROG Strix. Create ~/overlord-system/ scaffold. Initialize git repo.',
    blockers: [],
    coworkAction: 'Execute install commands via terminal. Verify each block sequentially.',
  },
  {
    id: 2,
    title: 'MacBook Air Environment Completion',
    agent: 'SYSTEM',
    status: 'BLOCKED',
    priority: 'P1',
    description: 'Complete Homebrew → Git → Node → Claude Code CLI chain. Last diagnostic: Python 3.12.3 only. All other deps missing.',
    blockers: ['Requires physical access to MacBook Air'],
    coworkAction: 'Generate step-by-step terminal script. Verify via diagnostic block.',
  },
  {
    id: 3,
    title: 'Guardian One Log Engine Deployment',
    agent: 'guardian-one',
    status: 'PENDING',
    priority: 'P0',
    description: 'Deploy schema.py + log engine to ROG ~/overlord-system/overlord-guardian/. Initialize production log with GENESIS entry. Verify hash chain integrity.',
    blockers: ['Task 1'],
    coworkAction: 'Copy lesson artifacts to production paths. Run initialization script. Verify chain.',
  },
  {
    id: 4,
    title: 'Guardian One Web Dashboard',
    agent: 'guardian-one',
    status: 'DESIGNED',
    priority: 'P1',
    description: 'Deploy Lesson 4 web server (Flask) to ROG. Expose dashboard at localhost:8080. Categories, spending ledger, hash chain visualization.',
    blockers: ['Task 3'],
    coworkAction: 'Deploy guardian_lesson_4.py as service. Configure autostart.',
  },
  {
    id: 5,
    title: 'VARYS Observation Mode Deploy',
    agent: 'varys',
    status: 'PENDING',
    priority: 'P1',
    description: 'Deploy varys.py in observation-only mode on ROG. Scan 27-device Starlink LAN. Classify devices into trust tiers. Dashboard at localhost:8181.',
    blockers: ['Task 1'],
    coworkAction: 'Run deploy_varys.sh. Monitor initial device scan. Review trust classifications.',
  },
  {
    id: 6,
    title: 'UniFi Dream Machine SE Decision',
    agent: 'varys',
    status: 'PENDING',
    priority: 'P2',
    description: 'Purchase and install Ubiquiti UniFi Dream Machine SE. Enable VLAN segmentation, MAC allowlisting, management-plane access. Required for VARYS enforcement mode.',
    blockers: ['Budget approval'],
    coworkAction: 'Research current pricing. Present cost-benefit to Jeremy for approval.',
  },
  {
    id: 7,
    title: 'Discovery Module Record Requests',
    agent: 'discovery',
    status: 'PENDING',
    priority: 'P2',
    description: 'Execute HIPAA, FCRA, CCPA record retrieval requests from Discovery Report sources. Track status in Guardian One log.',
    blockers: ['Task 3'],
    coworkAction: 'Generate request letters from templates. Track submission dates. Update record statuses.',
  },
  {
    id: 8,
    title: 'OSINT Validation Pipeline Stage 5',
    agent: 'discovery',
    status: 'PENDING',
    priority: 'P2',
    description: 'Complete user validation checkpoint. Cross-reference OSINT findings with private documents. Update Data Exposure Risk Matrix.',
    blockers: ['Task 7'],
    coworkAction: 'Present validation interface. Flag discrepancies. Generate final memory package.',
  },
  {
    id: 9,
    title: 'JTMedAI Case Library Expansion',
    agent: 'jtmedai',
    status: 'PENDING',
    priority: 'P2',
    description: 'Build additional telehealth simulation cases beyond telehosp_ami_001. Target: 5 high-acuity scenarios covering stroke, sepsis, DKA, PE, and anaphylaxis.',
    blockers: [],
    coworkAction: 'Use ami_001 as template. Generate case structures. Jeremy validates clinical accuracy.',
  },
  {
    id: 10,
    title: 'CLAUDE_MASTER.md Consolidation',
    agent: 'SYSTEM',
    status: 'DESIGNED',
    priority: 'P1',
    description: 'Unify all agent directives into single CLAUDE_MASTER.md. Covers VARYS + telehealth simulation + Guardian One. Deploy to ~/overlord-system/.',
    blockers: ['Task 1'],
    coworkAction: 'Merge existing directives. Add Guardian One + Discovery sections. Deploy to scaffold.',
  },
] as const;

const LEGAL_FRAMEWORK = [
  {
    statute: 'HIPAA Security Rule §164.308',
    scope: 'Administrative safeguards',
    relevance: 'Authority + obligation to manage network-connected devices handling PHI',
  },
  {
    statute: 'HIPAA Security Rule §164.312',
    scope: 'Technical safeguards',
    relevance: 'Access controls, audit controls, transmission security — VARYS enforcement justification',
  },
  {
    statute: 'Negligence Standards',
    scope: 'Tort liability',
    relevance: 'Network ownership creates duty of care. Locked management plane = documented gap.',
  },
  {
    statute: 'FCRA',
    scope: 'Credit reporting',
    relevance: 'Right to request credit records — Discovery Module retrieval',
  },
  {
    statute: 'CCPA',
    scope: 'Consumer privacy',
    relevance: 'Data broker opt-out rights — Discovery Module opt-out tracking',
  },
];

type BadgeProps = { status: string };
function Badge({ status }: BadgeProps) {
  const s = STATUS[(status as StatusKey) || 'PENDING'] || STATUS.PENDING;
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 3,
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: '0.08em',
        fontFamily: T.mono,
        color: s.color,
        background: s.bg,
        border: `1px solid ${s.color}33`,
      }}
    >
      {s.label}
    </span>
  );
}

type ProgressBarProps = { value: number; color?: string };
function ProgressBar({ value, color }: ProgressBarProps) {
  return (
    <div style={{ width: '100%', height: 4, background: T.bgAccent, borderRadius: 2, overflow: 'hidden' }}>
      <div style={{ width: `${value}%`, height: '100%', background: color || T.green, borderRadius: 2, transition: 'width 0.6s ease' }} />
    </div>
  );
}

type StatCardProps = { label: string; value: number | string; sub?: string; color?: string };
function StatCard({ label, value, sub, color }: StatCardProps) {
  return (
    <div
      style={{
        background: T.bgCard,
        border: `1px solid ${T.border}`,
        padding: '16px 20px',
        flex: '1 1 160px',
        minWidth: 140,
      }}
    >
      <div style={{ fontFamily: T.mono, fontSize: 10, color: T.textMuted, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 8 }}>{label}</div>
      <div style={{ fontFamily: T.mono, fontSize: 28, fontWeight: 700, color: color || T.textBright, lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontFamily: T.mono, fontSize: 11, color: T.textMuted, marginTop: 6 }}>{sub}</div>}
    </div>
  );
}

type SectionProps = { title: string; subtitle?: string; children: ReactNode };
function Section({ title, subtitle, children }: SectionProps) {
  return (
    <div style={{ marginBottom: 32 }}>
      <div style={{ borderBottom: `1px solid ${T.border}`, paddingBottom: 8, marginBottom: 16 }}>
        <h2 style={{ fontFamily: T.sans, fontSize: 16, fontWeight: 700, color: T.textBright, margin: 0, letterSpacing: '-0.01em' }}>{title}</h2>
        {subtitle && <div style={{ fontFamily: T.mono, fontSize: 11, color: T.textMuted, marginTop: 4 }}>{subtitle}</div>}
      </div>
      {children}
    </div>
  );
}

function DashboardView() {
  const activeAgents = AGENTS.filter((a) => a.status !== 'PENDING').length;
  const totalArtifacts = AGENTS.reduce((s, a) => s + a.artifacts.length, 0);
  const p0Tasks = PHASE1_TASKS.filter((t) => t.priority === 'P0').length;
  const blockedTasks = PHASE1_TASKS.filter((t) => t.status === 'BLOCKED').length;

  return (
    <>
      <Section title='SYSTEM OVERVIEW' subtitle={`Last sync: ${SYSTEM_STATE.lastUpdate} · Authority: ${SYSTEM_STATE.authority}`}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
          <StatCard label='Agents Designed' value={activeAgents} sub={`of ${AGENTS.length} planned`} color={T.blue} />
          <StatCard label='Artifacts Built' value={totalArtifacts} sub='schemas, agents, dashboards' color={T.green} />
          <StatCard label='P0 Tasks' value={p0Tasks} sub='critical path' color={T.amber} />
          <StatCard label='Blocked' value={blockedTasks} sub='needs intervention' color={T.red} />
          <StatCard label='LAN Devices' value={SYSTEM_STATE.network.devices} sub='Starlink (locked)' color={T.purple} />
        </div>
      </Section>

      <Section title='AGENT STATUS MATRIX' subtitle='Current state of all Overlord Guardian agents'>
        <div style={{ display: 'grid', gap: 10 }}>
          {AGENTS.map((a) => (
            <div
              key={a.id}
              style={{
                background: T.bgCard,
                border: `1px solid ${T.border}`,
                padding: '14px 18px',
                display: 'grid',
                gridTemplateColumns: '180px 1fr 100px 80px',
                alignItems: 'center',
                gap: 12,
              }}
            >
              <div>
                <div style={{ fontFamily: T.sans, fontSize: 14, fontWeight: 600, color: T.textBright }}>{a.name}</div>
                <div style={{ fontFamily: T.mono, fontSize: 10, color: T.textMuted, marginTop: 2 }}>{a.role}</div>
              </div>
              <ProgressBar value={a.progress} color={STATUS[a.status]?.color} />
              <div style={{ fontFamily: T.mono, fontSize: 12, color: T.textMuted, textAlign: 'right' }}>{a.progress}%</div>
              <Badge status={a.status} />
            </div>
          ))}
        </div>
      </Section>

      <Section title='HARDWARE FLEET' subtitle='Development infrastructure status'>
        <div style={{ display: 'grid', gap: 8 }}>
          {SYSTEM_STATE.hardware.map((h, i) => (
            <div
              key={`${h.name}-${i}`}
              style={{
                background: T.bgCard,
                border: `1px solid ${T.border}`,
                padding: '12px 18px',
                display: 'grid',
                gridTemplateColumns: '200px 100px 80px 1fr',
                alignItems: 'center',
                gap: 12,
              }}
            >
              <div>
                <span style={{ fontFamily: T.sans, fontSize: 13, fontWeight: 600, color: T.textBright }}>{h.name}</span>
                {h.ram !== '—' && <span style={{ fontFamily: T.mono, fontSize: 10, color: T.textMuted, marginLeft: 8 }}>{h.ram}</span>}
              </div>
              <span
                style={{
                  fontFamily: T.mono,
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: '0.08em',
                  color: h.status === 'ACTIVE' ? T.green : T.red,
                }}
              >
                {h.status}
              </span>
              <span style={{ fontFamily: T.mono, fontSize: 10, color: T.textMuted }}>{h.role}</span>
              <span style={{ fontFamily: T.mono, fontSize: 11, color: T.textMuted }}>{h.notes}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title='NETWORK SOVEREIGNTY GAP' subtitle='Critical infrastructure limitation'>
        <div style={{ background: T.redDim, border: `1px solid ${T.red}44`, padding: 18 }}>
          <div style={{ fontFamily: T.sans, fontSize: 13, fontWeight: 600, color: T.red, marginBottom: 8 }}>ENFORCEMENT BLOCKED — Starlink router management plane is locked</div>
          <div style={{ fontFamily: T.mono, fontSize: 12, color: T.text, lineHeight: 1.6 }}>
            {SYSTEM_STATE.network.devices} devices on LAN. VARYS can observe but cannot enforce policy (no VLAN segmentation, no MAC allowlisting, no management-plane access). Using locked-down
            upstream hardware represents a documented gap in a security posture you have established legal responsibility for under HIPAA §164.308 and §164.312. Recommendation:
            {` ${SYSTEM_STATE.network.recommendation}`}
          </div>
        </div>
      </Section>
    </>
  );
}

function AgentsView() {
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <Section title='AGENT DEEP DIVE' subtitle='Click an agent for full specification'>
      <div style={{ display: 'grid', gap: 12 }}>
        {AGENTS.map((a) => (
          <div
            key={a.id}
            onClick={() => setSelected(selected === a.id ? null : a.id)}
            style={{
              background: selected === a.id ? T.bgCardHover : T.bgCard,
              border: `1px solid ${selected === a.id ? T.borderActive : T.border}`,
              padding: 18,
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <div>
                <span style={{ fontFamily: T.sans, fontSize: 15, fontWeight: 700, color: T.textBright }}>{a.name}</span>
                <span style={{ fontFamily: T.mono, fontSize: 11, color: T.textMuted, marginLeft: 12 }}>{a.role}</span>
              </div>
              <Badge status={a.status} />
            </div>
            <ProgressBar value={a.progress} color={STATUS[a.status]?.color} />

            {selected === a.id && (
              <div style={{ marginTop: 16, borderTop: `1px solid ${T.border}`, paddingTop: 16 }}>
                <div style={{ fontFamily: T.mono, fontSize: 12, color: T.text, lineHeight: 1.7, marginBottom: 16 }}>{a.description}</div>

                {a.artifacts.length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontFamily: T.mono, fontSize: 10, color: T.textMuted, letterSpacing: '0.1em', marginBottom: 8 }}>ARTIFACTS</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {a.artifacts.map((ar, i) => (
                        <span
                          key={`${ar}-${i}`}
                          style={{
                            fontFamily: T.mono,
                            fontSize: 11,
                            padding: '3px 10px',
                            background: T.bgAccent,
                            border: `1px solid ${T.border}`,
                            color: T.green,
                          }}
                        >
                          {ar}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {a.categories.length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontFamily: T.mono, fontSize: 10, color: T.textMuted, letterSpacing: '0.1em', marginBottom: 8 }}>CATEGORIES</div>
                    <div style={{ fontFamily: T.mono, fontSize: 11, color: T.textMuted, lineHeight: 1.8 }}>{a.categories.join(' · ')}</div>
                  </div>
                )}

                <div style={{ background: T.blueDim, border: `1px solid ${T.blue}33`, padding: 12 }}>
                  <div style={{ fontFamily: T.mono, fontSize: 10, color: T.blue, letterSpacing: '0.1em', marginBottom: 4 }}>NEXT ACTION</div>
                  <div style={{ fontFamily: T.mono, fontSize: 12, color: T.text }}>{a.next}</div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </Section>
  );
}

function TasksView() {
  const [filter, setFilter] = useState<'ALL' | 'P0' | 'P1' | 'P2'>('ALL');
  const filtered = filter === 'ALL' ? PHASE1_TASKS : PHASE1_TASKS.filter((t) => t.priority === filter);

  return (
    <Section title='PHASE 1 TASK BOARD' subtitle={`${PHASE1_TASKS.length} tasks · Cowork execution directives`}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {(['ALL', 'P0', 'P1', 'P2'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              fontFamily: T.mono,
              fontSize: 11,
              fontWeight: 600,
              padding: '6px 14px',
              background: filter === f ? T.bgAccent : 'transparent',
              border: `1px solid ${filter === f ? T.borderActive : T.border}`,
              color: filter === f ? T.textBright : T.textMuted,
              cursor: 'pointer',
              letterSpacing: '0.06em',
            }}
          >
            {f}
          </button>
        ))}
      </div>

      <div style={{ display: 'grid', gap: 10 }}>
        {filtered.map((t) => (
          <div
            key={t.id}
            style={{
              background: T.bgCard,
              border: `1px solid ${T.border}`,
              padding: 16,
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span
                  style={{
                    fontFamily: T.mono,
                    fontSize: 10,
                    fontWeight: 700,
                    padding: '2px 6px',
                    background: t.priority === 'P0' ? T.redDim : t.priority === 'P1' ? T.amberDim : T.bgAccent,
                    color: t.priority === 'P0' ? T.red : t.priority === 'P1' ? T.amber : T.textMuted,
                    border: `1px solid ${t.priority === 'P0' ? T.red : t.priority === 'P1' ? T.amber : T.border}33`,
                  }}
                >
                  {t.priority}
                </span>
                <span style={{ fontFamily: T.sans, fontSize: 13, fontWeight: 600, color: T.textBright }}>{t.title}</span>
              </div>
              <Badge status={t.status} />
            </div>
            <div style={{ fontFamily: T.mono, fontSize: 11, color: T.textMuted, marginBottom: 8, lineHeight: 1.6 }}>{t.description}</div>
            {t.blockers.length > 0 && (
              <div style={{ fontFamily: T.mono, fontSize: 10, color: T.red, marginBottom: 6 }}>BLOCKERS: {t.blockers.join(', ')}</div>
            )}
            <div style={{ background: T.greenDim, border: `1px solid ${T.green}33`, padding: '8px 12px' }}>
              <span style={{ fontFamily: T.mono, fontSize: 10, color: T.green, letterSpacing: '0.08em' }}>COWORK → </span>
              <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text }}>{t.coworkAction}</span>
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}

function LegalView() {
  return (
    <Section title='LEGAL & COMPLIANCE FRAMEWORK' subtitle='Statutory basis for network sovereignty and data governance'>
      <div style={{ display: 'grid', gap: 8 }}>
        {LEGAL_FRAMEWORK.map((l, i) => (
          <div
            key={`${l.statute}-${i}`}
            style={{
              background: T.bgCard,
              border: `1px solid ${T.border}`,
              padding: 14,
              display: 'grid',
              gridTemplateColumns: '220px 180px 1fr',
              gap: 12,
              alignItems: 'start',
            }}
          >
            <div style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 600, color: T.amber }}>{l.statute}</div>
            <div style={{ fontFamily: T.mono, fontSize: 11, color: T.textMuted }}>{l.scope}</div>
            <div style={{ fontFamily: T.mono, fontSize: 11, color: T.text, lineHeight: 1.5 }}>{l.relevance}</div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 24, background: T.bgCard, border: `1px solid ${T.border}`, padding: 18 }}>
        <div style={{ fontFamily: T.mono, fontSize: 10, color: T.textMuted, letterSpacing: '0.1em', marginBottom: 12 }}>CORE PRINCIPLES</div>
        <div style={{ fontFamily: T.mono, fontSize: 12, color: T.text, lineHeight: 1.8 }}>
          {[
            'Network ownership of IoT devices creates both the authority and the legal obligation to manage them.',
            'Using locked-down upstream hardware represents a documented gap in security posture.',
            'The authority chain is immutable and non-delegable: Jeremy (Root) → Guardian One → Subordinate Agents.',
            'No external party sits within the authority chain.',
            'Outputs should be production-ready, not illustrative — comprehensive and expansive.',
            'OSINT validation pipeline: 7-stage process from raw ingest through validated identity file.',
          ].map((p, i) => (
            <div key={i} style={{ marginBottom: 6 }}>
              <span style={{ color: T.green, marginRight: 8 }}>▸</span>
              {p}
            </div>
          ))}
        </div>
      </div>
    </Section>
  );
}

function SchemaView() {
  return (
    <Section title='GUARDIAN ONE SCHEMA v0.1.0' subtitle='Append-only, hash-chained sovereign identity & choice log'>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div style={{ background: T.bgCard, border: `1px solid ${T.border}`, padding: 16 }}>
          <div style={{ fontFamily: T.mono, fontSize: 10, color: T.textMuted, letterSpacing: '0.1em', marginBottom: 12 }}>ENTRY CATEGORIES</div>
          {['financial', 'medical_self', 'medical_dependent', 'professional', 'legal', 'document', 'system', 'relational', 'correction', 'state_snapshot'].map((c, i) => (
            <div key={`${c}-${i}`} style={{ fontFamily: T.mono, fontSize: 11, color: T.text, padding: '3px 0', borderBottom: `1px solid ${T.border}` }}>
              <span style={{ color: T.green, marginRight: 8 }}>◆</span>
              {c}
            </div>
          ))}
        </div>
        <div style={{ background: T.bgCard, border: `1px solid ${T.border}`, padding: 16 }}>
          <div style={{ fontFamily: T.mono, fontSize: 10, color: T.textMuted, letterSpacing: '0.1em', marginBottom: 12 }}>ENTRY INTENTS</div>
          {[
            { name: 'DECISION', desc: 'You chose something' },
            { name: 'OBSERVATION', desc: 'You perceived/learned something' },
            { name: 'RECEIPT', desc: 'You received a document, notice, result' },
            { name: 'GENERATION', desc: 'You created something' },
            { name: 'CORRECTION', desc: "You're correcting a prior entry" },
            { name: 'MILESTONE', desc: 'Significant threshold crossed' },
            { name: 'SNAPSHOT', desc: 'Periodic state capture' },
          ].map((item, i) => (
            <div key={`${item.name}-${i}`} style={{ fontFamily: T.mono, fontSize: 11, color: T.text, padding: '3px 0', borderBottom: `1px solid ${T.border}` }}>
              <span style={{ color: T.blue, marginRight: 8 }}>◆</span>
              <span style={{ fontWeight: 600 }}>{item.name}</span>
              <span style={{ color: T.textMuted, marginLeft: 8 }}>— {item.desc}</span>
            </div>
          ))}
        </div>
      </div>

      <div style={{ marginTop: 16, background: T.bgCard, border: `1px solid ${T.border}`, padding: 16 }}>
        <div style={{ fontFamily: T.mono, fontSize: 10, color: T.textMuted, letterSpacing: '0.1em', marginBottom: 12 }}>ENTRY FIELDS</div>
        <div style={{ fontFamily: T.mono, fontSize: 11, color: T.text, lineHeight: 1.8 }}>
          {[
            'entry_id: int — auto-incrementing, immutable sequence position',
            'timestamp: str — UTC ISO-8601',
            'category: EntryCategory — primary domain',
            'intent: EntryIntent — action type',
            'summary: str — one-line human-readable',
            'context: str — why this happened, what was considered',
            'outcome: str|None — what resulted',
            'confidence: Confidence — high/moderate/low/uncertain',
            'references: list[int] — related entry_ids',
            'documents: list[str] — associated file paths',
            'tags: list[str] — freeform, searchable',
            'metadata: dict — structured key-value pairs',
            'prev_hash: str — SHA-256 of previous entry (chain integrity)',
            'entry_hash: str — SHA-256 of this entry (computed on write)',
          ].map((f, i) => (
            <div key={i}>
              <span style={{ color: T.amber }}>│</span> {f}
            </div>
          ))}
        </div>
      </div>

      <div style={{ marginTop: 16, background: T.bgCard, border: `1px solid ${T.border}`, padding: 16 }}>
        <div style={{ fontFamily: T.mono, fontSize: 10, color: T.textMuted, letterSpacing: '0.1em', marginBottom: 12 }}>SEED ENTRIES (from schema.py)</div>
        {[
          { id: 1, cat: 'financial', summary: 'Purchased ASUS ROG Strix Flow (64GB) for development', cost: '$2,149' },
          { id: 2, cat: 'medical_dependent', summary: 'Maintained Chaos on Cyclosporine 50mg q12h + Prednisone 10mg q12h (IMPA)', cost: '—' },
          { id: 3, cat: 'system', summary: 'Defined Guardian One schema v0.1.0', cost: '—' },
          { id: 4, cat: 'correction', summary: 'Correcting entry 1: actual purchase price was $2,149', cost: '—' },
          { id: 5, cat: 'professional', summary: 'Registered jtmdai.com and deployed JTMedAI dashboard', cost: '—' },
        ].map((e) => (
          <div
            key={e.id}
            style={{
              fontFamily: T.mono,
              fontSize: 11,
              color: T.text,
              padding: '6px 0',
              borderBottom: `1px solid ${T.border}`,
              display: 'grid',
              gridTemplateColumns: '30px 150px 1fr 60px',
              gap: 8,
            }}
          >
            <span style={{ color: T.textMuted }}>#{e.id}</span>
            <span style={{ color: T.blue }}>{e.cat}</span>
            <span>{e.summary}</span>
            <span style={{ color: T.green, textAlign: 'right' }}>{e.cost}</span>
          </div>
        ))}
      </div>
    </Section>
  );
}

const TABS = [
  { id: 'dashboard', label: 'OVERVIEW' },
  { id: 'agents', label: 'AGENTS' },
  { id: 'tasks', label: 'TASK BOARD' },
  { id: 'schema', label: 'SCHEMA' },
  { id: 'legal', label: 'LEGAL' },
] as const;

export default function OverlordGuardian() {
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]['id']>('dashboard');
  const [clock, setClock] = useState(new Date());

  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <div
      style={{
        background: T.bg,
        color: T.text,
        fontFamily: T.sans,
        minHeight: '100vh',
        padding: 0,
      }}
    >
      <div
        style={{
          borderBottom: `1px solid ${T.border}`,
          padding: '12px 24px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          position: 'sticky',
          top: 0,
          background: T.bg,
          zIndex: 10,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ fontFamily: T.mono, fontSize: 14, fontWeight: 700, color: T.green, letterSpacing: '0.15em' }}>◈ OVERLORD GUARDIAN</div>
          <div style={{ fontFamily: T.mono, fontSize: 10, color: T.textMuted, letterSpacing: '0.1em' }}>PHASE 1 COMMAND CENTER</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{ fontFamily: T.mono, fontSize: 10, color: T.textMuted }}>ROG STRIX · {SYSTEM_STATE.network.devices} DEVICES · STARLINK</div>
          <div style={{ fontFamily: T.mono, fontSize: 11, color: T.green }}>{clock.toLocaleTimeString('en-US', { hour12: false })}</div>
        </div>
      </div>

      <div
        style={{
          background: T.bgAccent,
          borderBottom: `1px solid ${T.border}`,
          padding: '6px 24px',
          display: 'flex',
          justifyContent: 'space-between',
          fontFamily: T.mono,
          fontSize: 10,
          color: T.textMuted,
          letterSpacing: '0.06em',
        }}
      >
        <span>OWNER: {SYSTEM_STATE.owner}</span>
        <span>CHAIN: {SYSTEM_STATE.authority}</span>
        <span>TARGET: COWORK @ ROG STRIX FLOW</span>
      </div>

      <div
        style={{
          borderBottom: `1px solid ${T.border}`,
          padding: '0 24px',
          display: 'flex',
          gap: 0,
        }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              fontFamily: T.mono,
              fontSize: 11,
              fontWeight: 600,
              padding: '12px 20px',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: activeTab === tab.id ? T.green : T.textMuted,
              borderBottom: activeTab === tab.id ? `2px solid ${T.green}` : '2px solid transparent',
              letterSpacing: '0.08em',
              transition: 'all 0.2s',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div style={{ padding: '24px', maxWidth: 1200, margin: '0 auto' }}>
        {activeTab === 'dashboard' && <DashboardView />}
        {activeTab === 'agents' && <AgentsView />}
        {activeTab === 'tasks' && <TasksView />}
        {activeTab === 'schema' && <SchemaView />}
        {activeTab === 'legal' && <LegalView />}
      </div>

      <div
        style={{
          borderTop: `1px solid ${T.border}`,
          padding: '16px 24px',
          textAlign: 'center',
          fontFamily: T.mono,
          fontSize: 10,
          color: T.textMuted,
        }}
      >
        OVERLORD GUARDIAN · Phase 1 Cowork Handoff · Build {SYSTEM_STATE.lastUpdate} · Tabernero Consulting LLC © 2026
      </div>
    </div>
  );
}
