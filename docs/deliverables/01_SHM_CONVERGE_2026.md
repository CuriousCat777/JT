# Guardian One: The Verified Clinical Narrative
## SHM Converge 2026 — Presentation Framework

**Target audience:** Hospitalists, clinical informaticists, care transition leads
**Format:** 20-minute oral presentation with slides
**Tone:** Clinical, evidence-based, no business model content

---

## SLIDE 1 — Title

**Guardian One: AI-Orchestrated Clinical Narratives for Safe Hospital-to-Community Transitions**

*[Speaker name, credentials]*
*[Institutional affiliation]*

---

## SLIDE 2 — The Problem We All Know

> "The discharge summary is the most important document in medicine that nobody reads, nobody trusts, and nobody verifies."

### By the Numbers

- **19.6%** of Medicare patients are readmitted within 30 days (CMS, 2024)
- **~$26 billion** annual cost of unplanned readmissions in the US
- **40–80%** of discharge medical information is lost during handoffs (Coleman & Berenson, JAMA)
- **50%+** of discharge summaries contain at least one medication discrepancy (Kripalani et al., J Hospital Medicine)
- **Hospital Readmissions Reduction Program (HRRP):** CMS penalizes ~2,500 hospitals annually, totaling ~$550M in payment reductions

**The gap:** We discharge patients with a PDF and a prayer.

---

## SLIDE 3 — Why Existing Solutions Fall Short

| Approach | What It Does | What It Misses |
|----------|-------------|----------------|
| **EHR discharge modules** (Epic, Cerner) | Templated summaries, auto-populated med lists | No verification against pharmacy fills, no post-discharge monitoring |
| **Care management platforms** (Bamboo Health, CarePort) | ADT notifications, post-acute referrals | Reactive — alerts *after* the fact, no clinical narrative construction |
| **Patient portals** (MyChart) | Patient-facing visit summaries | Passive — requires patient to read, interpret, and act |
| **Manual reconciliation** | Pharmacist-led med rec at discharge | Labor-intensive, error-prone, happens once at a point in time |

**Common failure mode:** All of these treat discharge as a *document event*, not as a *living, verified narrative* that follows the patient.

---

## SLIDE 4 — The Core Concept: Verified Clinical Narrative

Guardian One introduces a fundamentally different model:

### A clinical narrative is not a document. It is a continuously verified data structure.

**Three properties that make it different:**

1. **Verified** — Every claim (medication, diagnosis, follow-up order) is cross-referenced against source systems. Unverified claims are flagged, not hidden.

2. **Living** — The narrative updates as new data arrives: pharmacy fill confirmations, lab results, PCP visit notes, wearable vitals. It doesn't freeze at discharge.

3. **Sovereign** — The patient owns and controls their narrative. It travels with them across providers, not locked in one EHR.

---

## SLIDE 5 — Architecture (Clinical View)

```
┌─────────────────────────────────────────────────────┐
│                 GUARDIAN ONE                          │
│          (Orchestrator + Authority Layer)             │
│                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ Health Agent  │  │  CFO Agent   │  │  Chronos   │ │
│  │              │  │  (Financial) │  │ (Schedule)  │ │
│  │ • Epic/FHIR  │  │              │  │             │ │
│  │ • Med Rec    │  │  • Billing   │  │ • Follow-up │ │
│  │ • Wearables  │  │  • Insurance │  │ • Reminders │ │
│  │ • Error Det. │  │  • Claims    │  │ • Alerts    │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘ │
│         │                 │                  │        │
│         └─────────┬───────┴──────────┬───────┘        │
│                   │                  │                │
│            ┌──────┴──────┐   ┌───────┴──────┐        │
│            │  Mediator   │   │  Audit Log   │        │
│            │ (Conflicts) │   │ (Immutable)  │        │
│            └─────────────┘   └──────────────┘        │
└─────────────────────────────────────────────────────┘

Data flows IN from:              Data sovereignty:
• Epic (FHIR R4)                 • Patient owns all data
• Pharmacy systems               • Encrypted at rest (AES-256)
• Wearable APIs                  • Access-controlled per agent
• Lab interfaces                 • Full audit trail
```

**Key for hospitalists:** The Health Agent is where clinical logic lives. It doesn't replace your judgment — it catches what falls through the cracks.

---

## SLIDE 6 — Clinical Error Detection: How It Works

### Scenario: Mrs. Johnson, 72, CHF exacerbation, discharged Day 3

**What the discharge summary says:**
- Continue metoprolol 50mg BID
- New: furosemide 40mg daily
- Follow-up with PCP in 7 days
- Daily weights

**What Guardian One catches:**

| Check | Source | Finding | Flag |
|-------|--------|---------|------|
| Metoprolol dose | Admission med rec vs. discharge | Admission dose was 25mg BID — doubled without documented rationale | **UNVERIFIED** |
| Furosemide + K+ monitoring | Drug-lab interaction rules | No potassium check ordered within 7 days of new loop diuretic | **SAFETY FLAG** |
| PCP follow-up | Scheduling system | PCP has no availability within 14 days; no appointment scheduled | **UNSCHEDULED** |
| Daily weights | Wearable sync | Patient has no connected scale; instruction unverifiable | **NO DATA SOURCE** |
| Pharmacy fill | Pharmacy claims feed | Furosemide not filled 48h post-discharge | **NOT FILLED** |

**Result:** 5 actionable flags generated within 48 hours of discharge. Any one of these is a readmission risk.

---

## SLIDE 7 — Medication Reconciliation: Beyond the Point-in-Time Check

### Current State (What We Do Now)
```
Admission → Pharmacist Med Rec → [hospitalization] → Discharge Med Rec → PDF → Hope
```

### Guardian One Model
```
Admission → Continuous Reconciliation → Discharge → Post-Discharge Verification Loop
     ↑                                                        │
     └────────── Pharmacy fills, refills, adherence ──────────┘
```

**What changes:**
- Med rec isn't a one-time event — it's a **running process**
- Every medication on the discharge list is tracked to pharmacy fill
- Discrepancies between prescribed and dispensed trigger alerts
- Dose changes during hospitalization are flagged if undocumented
- Post-discharge: if a patient fills a PRN medication at unusual frequency, the system flags it

---

## SLIDE 8 — The Trust Problem: Verified vs. Unverified Claims

Guardian One introduces a **verification taxonomy** for every clinical assertion:

| Status | Meaning | Example |
|--------|---------|---------|
| **VERIFIED** | Cross-referenced against source system, confirmed | "Metoprolol 25mg BID" — matches pharmacy dispense record |
| **UNVERIFIED** | Claimed but no corroborating source found | "Allergic to penicillin" — no allergy documentation in Epic |
| **CONFLICTING** | Multiple sources disagree | Discharge says lisinopril 10mg; pharmacy filled lisinopril 20mg |
| **EXPIRED** | Was true but may no longer be (stale data) | "Last A1c 6.8%" — date: 14 months ago |
| **NO SOURCE** | Assertion has no data feed to verify against | "Patient exercises 3x/week" — no wearable connected |

**For the hospitalist:** When you receive a patient with a Guardian One narrative, you know *exactly* what you can trust and what you need to verify yourself. No more guessing.

---

## SLIDE 9 — Interoperability: Working With Epic, Not Against It

### FHIR R4 Integration Points

Guardian One connects to Epic via **standard FHIR R4 APIs** (no custom interfaces):

- **Patient** — demographics, identifiers
- **MedicationRequest** — active prescriptions, discharge meds
- **Condition** — problem list, active diagnoses
- **AllergyIntolerance** — allergy and adverse reaction records
- **Encounter** — admission/discharge/transfer events (ADT)
- **DiagnosticReport / Observation** — lab results, vitals
- **DocumentReference** — discharge summaries, clinical notes
- **CarePlan** — follow-up orders, post-discharge plans

### What This Means Practically

- Works with any Epic instance that exposes FHIR R4 (most do post-21st Century Cures Act)
- **Read-only by default** — Guardian One does not write back to the EHR
- No HL7v2 interfaces needed — pure REST/FHIR
- Patient-authorized via SMART on FHIR (patient grants access to their own data)

---

## SLIDE 10 — Wearable Integration: Closing the Post-Discharge Data Gap

The biggest blind spot after discharge: **what's happening to the patient at home?**

### Data Sources
- **Apple Health / Google Health Connect** — steps, heart rate, weight, blood pressure
- **Continuous glucose monitors** — Dexcom, Libre (for diabetic patients)
- **Smart scales** — daily weights (critical for CHF)
- **Blood pressure cuffs** — connected BP monitors
- **Pulse oximetry** — SpO2 trending

### Clinical Rules Engine
- CHF patient gains >3 lbs in 48 hours → **alert**
- Diabetic patient glucose >300 mg/dL for 4+ hours → **alert**
- Post-surgical patient resting HR >110 sustained → **alert**
- Patient with COPD exacerbation: SpO2 <88% trending → **alert**

**These alerts go to the patient's care team, not just the patient.** The verified narrative includes the wearable data as evidence.

---

## SLIDE 11 — Data Sovereignty: Why It Matters Clinically

### The Current Problem
- Patient data is siloed in each health system's EHR
- When a patient moves between systems, data doesn't follow
- Patients can't easily share their complete record with a new provider
- Health Information Exchanges (HIEs) are incomplete and inconsistent

### The Guardian One Approach
- **Patient controls access** — they decide which providers see which data
- **Portable narrative** — the verified clinical narrative is exportable (FHIR Bundle, PDF, or structured JSON)
- **No vendor lock-in** — data is stored in open standards, encrypted with patient-controlled keys
- **Audit trail** — every access is logged; the patient can see who viewed their data and when

**For hospitalists:** When your patient arrives from another system with a Guardian One narrative, you get a complete, verified clinical picture — not a faxed discharge summary from 2019.

---

## SLIDE 12 — What This Is NOT

Important to set expectations clearly:

- **NOT a replacement for clinical judgment** — Guardian One flags; clinicians decide
- **NOT an EHR** — it's a verification and orchestration layer that sits alongside the EHR
- **NOT a clinical decision support (CDS) system** — it doesn't recommend treatments; it verifies claims and catches discrepancies
- **NOT dependent on AI-generated clinical content** — the clinical data comes from source systems; AI orchestrates, verifies, and flags
- **NOT a business pitch** — this is a patient safety tool built on open standards

---

## SLIDE 13 — Implementation Pathway

### Phase 1: Single-Site Pilot (Months 1–6)
- Deploy at one academic medical center
- Focus: CHF and COPD patients (highest readmission risk)
- Integration: Epic FHIR R4 (read-only)
- Metric: Medication discrepancy detection rate

### Phase 2: Post-Discharge Loop (Months 4–9)
- Add pharmacy fill verification
- Add wearable data integration
- Add automated PCP follow-up scheduling verification
- Metric: Time-to-detection of post-discharge safety events

### Phase 3: Multi-Site Expansion (Months 9–18)
- Second and third sites (different EHR environments)
- Cross-system narrative portability
- Metric: 30-day readmission rate comparison (pre/post)

---

## SLIDE 14 — Preliminary Outcome Targets

| Metric | Current Baseline | Guardian One Target | Evidence Basis |
|--------|-----------------|-------------------|---------------|
| Medication discrepancies caught at discharge | ~50% detected by manual process | >90% detected by automated cross-reference | Kripalani et al., 2007 |
| Post-discharge medication non-fill detection | 5–7 days (if ever) | <48 hours | Pharmacy claims integration |
| Unscheduled follow-up detection | Often discovered at readmission | <24 hours post-discharge | Scheduling system integration |
| 30-day readmission rate (CHF) | ~22–25% nationally | Target: 15–18% (pilot) | Based on care transition intervention literature |
| Time to complete clinical narrative | N/A (doesn't exist today) | Real-time, continuous | System architecture |

---

## SLIDE 15 — Call to Action

### For Hospitalists
- **You know this problem.** Every time you admit a patient and can't trust the discharge summary from the last hospitalization, that's the gap Guardian One fills.
- **You don't need to change your workflow.** Guardian One works alongside your existing EHR. The verified narrative is an additional input, not a replacement.

### For Clinical Informatics Teams
- **FHIR R4 native.** No custom interfaces. If your Epic instance supports FHIR (and post-Cures Act, it must), Guardian One can connect.
- **Read-only by default.** No write-back risk. No EHR modification.

### For Quality/Safety Officers
- **Measurable.** Every flag Guardian One generates is logged, tracked, and auditable.
- **Targeted.** Start with high-risk populations (CHF, COPD) where readmission penalties are highest.

---

## APPENDIX A — Technical Specifications

| Component | Technology |
|-----------|-----------|
| Orchestration | Python multi-agent architecture (Guardian One core) |
| Data exchange | FHIR R4 (REST), SMART on FHIR for auth |
| Data storage | Encrypted at rest (AES-256), patient-controlled keys |
| Access control | Role-based with full audit trail |
| Conflict resolution | Built-in mediator for cross-agent data conflicts |
| Deployment | Containerized (Docker), cloud or on-premise |
| Compliance | HIPAA-ready architecture, BAA-compatible |

## APPENDIX B — Regulatory Considerations

- **HIPAA:** Patient data encrypted at rest and in transit; access-controlled; audit-logged
- **21st Century Cures Act:** Supports information blocking compliance — data flows freely with patient consent
- **FDA:** Guardian One is a **clinical decision support tool exempt from FDA device regulation** under 21st Century Cures Act Section 3060(a) — it displays, organizes, and flags information for clinician review; it does not independently diagnose or recommend treatment
- **State privacy laws:** Architecture supports state-specific consent requirements (e.g., California CMIA, New York SHIELD Act)

## APPENDIX C — References

1. Kripalani S, et al. "Deficits in communication and information transfer between hospital-based and primary care physicians." JAMA. 2007;297(8):831-841.
2. Coleman EA, Berenson RA. "Lost in transition: challenges and opportunities for improving the quality of transitional care." Ann Intern Med. 2004;141(7):533-536.
3. Forster AJ, et al. "The incidence and severity of adverse events affecting patients after discharge from the hospital." Ann Intern Med. 2003;138(3):161-167.
4. CMS Hospital Readmissions Reduction Program. Data.CMS.gov (2024).
5. ONC 21st Century Cures Act Final Rule. HealthIT.gov (2020).
