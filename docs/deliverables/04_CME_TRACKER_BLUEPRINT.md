# CME Conference Tracker Blueprint (US Hospitalist Physicians)

## 1) Product Goal
Build a **web-first CME Conference Tracker** for US hospitalist clinicians (MD/DO/NP/PA) that:
- Discovers and organizes recurring hospital medicine CME events.
- Helps users choose high-yield conferences for career goals and board requirements.
- Tracks registration, travel logistics, sessions attended, and credit accrual.
- Verifies clinician identity and licensure using open/public data sources.
- Produces export-ready documentation for credentialing and board maintenance.

---

## 2) Users and Jobs-To-Be-Done
### Primary user
- Practicing hospitalists and advanced practice clinicians needing reliable CME tracking.

### Core jobs
1. "Tell me which conferences maximize my CME value this year."
2. "Register and plan travel quickly with minimal admin overhead."
3. "Track completed credits by board category (ABIM/ABFM/ACCME-compatible formats)."
4. "Maintain audit-ready records for credentialing, renewal, and compliance."

---

## 3) Scope: MVP → V1
## MVP (Website)
- Chat-style onboarding.
- Physician verification module (identity + license check).
- CME event discovery + ranking for hospital medicine.
- Personal conference planner (budget, dates, agenda).
- Credit tracker + downloadable evidence packet.

## V1 (App-store roadmap)
- iOS/Android companion app.
- Real-time in-conference assistant.
- Badge/QR session check-in ingestion.
- Receipt OCR and expense reconciliation.

---

## 4) Compliance and Regulatory Positioning
- Treat as **administrative/educational workflow software**, not medical diagnosis.
- Minimize PHI storage; store only required profile and professional credential data.
- Enforce strong data governance:
  - Encryption at rest and in transit.
  - Role-based access control.
  - Immutable audit logs for verification actions.
- Clearly disclose verification confidence and source provenance to the user.

---

## 5) Data Sources (Open/Public + User-Provided)
### Hospital medicine conference and CME sources
- Society of Hospital Medicine (conference pages, public event listings).
- Major academic center CME catalogs (e.g., Mayo, Johns Hopkins, UCSF, Harvard, Stanford where publicly listed).
- Public ACCME-recognized provider event pages and published conference metadata.

### Credential verification sources
- State medical board license lookups (public verification portals).
- NPI registry/NPPES public provider records.
- Public institution directories (when available).

### User-provided records
- Conference registrations, agendas, transcripts, certificates, receipts.

---

## 6) Architecture (n8n + Notion + Figma + Web App)
```text
[Physician Chat UI]
      |
      v
[API Gateway / Auth]
      |
      +--> [Verification Service]
      |         |- NPI + state board checks
      |         |- confidence score + audit log
      |
      +--> [Conference Intelligence Service]
      |         |- OSINT crawlers + source normalization
      |         |- conference scoring + recommendation model
      |
      +--> [Planner & Tracker Service]
      |         |- registration status
      |         |- schedule + logistics
      |         |- CME credit ledger + exports
      |
      +--> [Agent Orchestrator]
                |- planner agent
                |- verification agent
                |- conference concierge agent

[Automation layer: n8n]
  - ingestion workflows
  - periodic verification jobs
  - reminders and notifications

[Knowledge/ops layer: Notion]
  - source catalog
  - workflow runbooks
  - admin dashboards
  - QA review queues

[Design/collab: Figma]
  - user flows
  - component system
  - handoff specs
```

---

## 7) AI Agent Farm (OSINT + Planning)
## Agent roles
1. **Physician Verification Agent**
   - Validates identity claims against public registries.
   - Produces: verified/unverified/conflict statuses with evidence links.
2. **Conference Discovery Agent**
   - Monitors hospital medicine CME events and updates normalized records.
3. **CME Strategy Agent**
   - Recommends conferences based on specialty focus, budget, location, and CME gaps.
4. **Logistics Agent**
   - Builds conference plan (travel, lodging, schedule blocks, reminders).
5. **Credit Ledger Agent**
   - Reconciles claimed attendance vs. uploaded evidence and session records.

## Guardrails
- Every recommendation links to source evidence.
- Verification actions are fully logged.
- Human override available for disputed records.

---

## 8) Physician Verification Module (Detailed)
## Inputs
- Full name, credentials, specialty, state, license number (optional but encouraged), NPI (optional).

## Workflow
1. Parse identity entities from onboarding chat.
2. Query NPI/NPPES by name and specialty.
3. Query state board portals (where publicly queryable).
4. Match against employer/institution footprint when available.
5. Compute confidence score:
   - strong match: name + NPI + active license + specialty alignment.
   - partial match: missing one trusted element.
   - conflict: multiple inconsistent records.
6. Return result with provenance:
   - status: Verified / Needs Review / Not Verified.
   - reason codes + source URLs + timestamp.

## Outputs
- Verification badge in user profile.
- Audit trail entry with immutable hash/event id.
- Reverification cadence (e.g., monthly or pre-report generation).

---

## 9) CME Planning and Tracking Data Model (MVP)
## Entities
- `UserProfile`
- `ProviderVerification`
- `Conference`
- `ConferenceSession`
- `Registration`
- `TravelPlan`
- `CMEClaim`
- `EvidenceDocument`
- `BoardRequirementProfile`
- `AuditEvent`

## Key relationships
- One user has many conferences and many claims.
- Each claim references one or more evidence documents.
- Verification status is versioned, never overwritten.

---

## 10) n8n Workflow Design
## Workflow A: Conference ingestion (daily)
- Trigger: cron.
- Steps: fetch sources → parse metadata → deduplicate → classify hospitalist relevance → score quality → write to DB + Notion catalog.

## Workflow B: User onboarding + verification (event-driven)
- Trigger: user submits onboarding chat.
- Steps: identity extraction → verification checks → confidence scoring → persist audit event → notify user.

## Workflow C: CME credit reconciliation (weekly + on upload)
- Trigger: certificate upload or schedule.
- Steps: OCR/document parse → map to session/conference → validate against provider metadata → update credit ledger.

## Workflow D: Compliance reminders
- Trigger: upcoming board cycle milestones.
- Steps: compute gap-to-target credits → suggest best-fit conferences → push reminders.

---

## 11) Notion Workspace Structure
- **Database: Source Registry** (conference links, trust score, crawl cadence).
- **Database: Verification Cases** (automatic and manual reviews).
- **Database: Conference Catalog** (normalized event metadata).
- **Database: User Support Queue** (exceptions/disputes).
- **Dashboard: Operational Health** (workflow success rates, stale sources, review backlog).

---

## 12) Figma Deliverables
1. **Information architecture map** (onboarding → verification → planner → tracker → export).
2. **Low-fi wireframes**:
   - chat onboarding
   - verification evidence screen
   - conference compare view
   - CME ledger and export panel
3. **Design system primitives**:
   - status chips (verified/conflict/pending)
   - timeline components
   - audit log table
4. **Prototype** of end-to-end "Plan + Track + Export" flow.

---

## 13) Deployment Pipeline (Full)
## Environments
- `dev` → `staging` → `prod`

## CI/CD
1. Lint/test on pull request.
2. Build web app + API containers.
3. Run migration checks.
4. Deploy to staging.
5. Run smoke tests for:
   - chat onboarding
   - verification service
   - conference search
   - ledger export
6. Manual approval gate.
7. Production deploy (blue/green or rolling).
8. Post-deploy monitors and rollback hooks.

## Observability
- Centralized logs for agent actions.
- Metrics: verification latency, source freshness, ingestion success, ledger mismatch rate.
- Alerts for source failures and verification anomalies.

---

## 14) Prioritized 90-Day Plan
## Days 0–30
- Finalize data schema and verification logic.
- Build chat onboarding and minimal profile.
- Launch conference ingestion workflow for SHM + top academic CME sources.

## Days 31–60
- Ship planner dashboard and first recommendation model.
- Add evidence upload + credit ledger.
- Add Notion ops workspace and QA workflow.

## Days 61–90
- Add export reports and audit package.
- Harden security, add reverification scheduler.
- Pilot with 10–20 hospitalist clinicians and capture usability metrics.

---

## 15) Success Metrics
- Time to onboard and verify user profile.
- Conference recommendation acceptance rate.
- Percentage of CME claims with complete evidence.
- Reduction in manual tracking time per clinician.
- Number of board-cycle users reaching target credits on time.

---

## 16) Risks and Mitigations
- **Risk:** Public source variability/unstructured data.
  - **Mitigation:** Source scoring + human review queue + fallback parsers.
- **Risk:** License portal changes/breakage.
  - **Mitigation:** connector abstraction and monitor-based retries.
- **Risk:** User trust in automated verification.
  - **Mitigation:** transparent evidence display and dispute workflow.
- **Risk:** Scope creep into full clinical systems.
  - **Mitigation:** strict product boundary around CME operations and verification.

---

## 17) Immediate Next Actions
1. Build Figma architecture board and user journey map.
2. Stand up n8n workflows A and B with dummy data.
3. Create Notion databases and operational dashboard.
4. Implement first version of Verification API (NPI + one pilot state).
5. Demo end-to-end onboarding → recommendation → claim tracking.
