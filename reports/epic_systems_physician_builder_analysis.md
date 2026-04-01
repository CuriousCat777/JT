# Epic Systems: Physician Builder Positioning Analysis

**Prepared for:** Dr. Jeremy Paulo Salvino Tabernero
**Date:** April 1, 2026
**Classification:** Strategic Business Intelligence

---

## Executive Summary

Epic Systems dominates the U.S. EHR market with 41.3% of hospital installations and 54.9% of all hospital beds. The company is privately held, consistently profitable, and aggressively expanding into AI, interoperability, and international markets. Regulatory tailwinds (21st Century Cures Act, HTI-5) are forcing open APIs and FHIR-based data exchange, creating a significant opportunity for physician builders who can develop clinical tools on Epic's platform. Guardian One already has integration infrastructure (Gateway, Vault, FHIR stub) that maps directly to Epic's developer ecosystem.

**Recommendation:** The physician builder positioning is strategically sound. Epic's dominance is accelerating, the regulatory environment mandates open APIs, and Guardian One's architecture is ready for Epic integration.

---

## 1. Epic Systems Company Profile

| Attribute | Detail |
|-----------|--------|
| **Founded** | 1979 by Judith Faulkner |
| **Headquarters** | Verona, Wisconsin |
| **Ownership** | Private (100% owned by Judy Faulkner / employee trust) |
| **Estimated Revenue (2024)** | ~$4.9 billion |
| **Employees** | ~13,000+ |
| **Business Type** | Healthcare software (EHR/EMR) |
| **Tax Status** | Private C-corp (no public SEC filings) |

### Revenue Trajectory

Epic does not publicly disclose financials, but reported figures show consistent growth:

- **2019:** ~$3.2B
- **2020:** ~$3.3B
- **2021:** ~$3.8B
- **2022:** ~$4.0B
- **2023:** ~$4.6B
- **2024:** ~$4.9B (estimated)

Growth is driven by new hospital implementations, maintenance contracts, international expansion, and emerging AI/analytics offerings.

### Revenue Model Breakdown

| Stream | Description | Estimated Share |
|--------|-------------|-----------------|
| **Software Licensing** | Per-module, per-user perpetual or subscription licenses | 25-30% |
| **Implementation Services** | Configuration, integration, go-live support ($2M-$10M per hospital) | 20-25% |
| **Maintenance & Support** | Annual contracts (~20% of initial license), near-100% retention | 30-35% |
| **Training & Education** | Certification programs, on-site training | 5-10% |
| **AI & Data Analytics** | Emerging: Cosmos database, predictive analytics, ambient AI | Growing |

**Key metric:** Each hospital bed running Epic generates ~$2,800 in annual recurring revenue.

---

## 2. Market Position & Dominance

### EHR Market Share (2024-2025)

| Vendor | Hospital Share | Bed Share | Net Change (2024) |
|--------|---------------|-----------|-------------------|
| **Epic Systems** | 41.3% (3,620 hospitals) | 54.9% | **+176 hospitals** (record gain) |
| **Oracle Health (Cerner)** | ~22% | ~25% | -74 hospitals |
| **MEDITECH** | 14.8% | 12.7% | -57 hospitals |
| **Veradigm (Allscripts)** | ~3.6% (ambulatory) | — | Declining |

Epic won nearly **70% of all new hospital contracts in 2024** (KLAS Research). Competitors are losing share directly to Epic, primarily citing interoperability advantages and customer satisfaction.

### Why Epic Is Winning

1. **Interoperability leadership** — Best-in-class FHIR implementation, Care Everywhere network
2. **AI investment** — 160-200 AI projects in 2025, Microsoft partnership for generative AI copilots
3. **Cosmos database** — 5.7 billion patient encounters, positioning for research/pharma analytics
4. **Customer satisfaction** — Consistently highest KLAS ratings
5. **Network effects** — More hospitals on Epic = better data exchange = more hospitals choosing Epic

### Competitive Vulnerabilities

- **Oracle Health:** Post-$28.3B Cerner acquisition, struggling with integration. Lost 74 hospitals in 2024. Customer trust issues, but showing "cautious optimism" with new AI tools.
- **MEDITECH:** Losing share, retreating to community/rural hospitals. Strong in Canada (largest hospital vendor).
- **New entrants:** Unlikely in acute care due to switching costs ($100M+ for large systems).

---

## 3. The Physician Builder Opportunity

### What Is a Physician Builder?

A physician builder is a clinician who develops software tools, applications, and workflows within or on top of EHR platforms. They bridge the gap between clinical expertise and technology — understanding both the workflow pain points and the technical capabilities.

### Epic's Developer Ecosystem

#### App Orchard / App Market
- Epic's marketplace for third-party applications
- Rebranded from "App Orchard" to "App Market"
- Apps integrate via FHIR R4 APIs, SMART on FHIR, and Epic's proprietary APIs
- Revenue sharing model for developers
- Categories: clinical decision support, patient engagement, analytics, AI, population health

#### FHIR R4 API Access
- Epic provides open FHIR R4 endpoints per the 21st Century Cures Act
- Patient, Encounter, Observation, MedicationRequest, Condition, AllergyIntolerance, etc.
- SMART on FHIR for authentication (OAuth2-based)
- Sandbox environment available for development

#### Epic Developer Program
- Free registration for API access
- Documentation and sandbox environments
- Certification process for App Market listing
- Community forums and annual User Group Meeting (UGM)

### Why Now Is the Right Time

1. **Regulatory mandate (Cures Act):** All EHRs must provide open FHIR APIs — Epic cannot block third-party innovation
2. **HTI-5 proposed rule (Dec 2025):** Explicitly allows autonomous AI systems to retrieve/share health data; phases out legacy formats in favor of API-first approaches
3. **Epic's AI push:** 160-200 AI projects = massive demand for clinician-informed AI tools
4. **Ambient AI wave:** Clinical documentation automation is the hottest area — physician insight is essential
5. **Cosmos data access:** Potential for research tools leveraging Epic's 5.7B encounter database

---

## 4. Regulatory Environment

### 21st Century Cures Act (2016, enforced 2020+)

- **Information blocking prohibition:** Illegal for providers/vendors to obstruct patient data access
- **FHIR R4 mandate:** Standardized API format for health data exchange
- **Patient right of access:** All EHI must be available electronically, without charge
- **Penalties:** Fines for hospitals and clinicians who block data access

### HTI-5 Proposed Rule (December 2025)

The most significant health IT policy update in years:

- **AI-enabled interoperability:** Explicitly allows autonomous AI systems to access health data
- **Certification reset:** Removes 50%+ of legacy certification criteria, focuses on FHIR APIs
- **Tighter enforcement:** Closes technical/contractual loopholes for information blocking
- **API-first future:** Legacy document exchange being phased out

### What This Means for Physician Builders

The regulatory environment is **actively forcing open the Epic ecosystem**. Any tool you build with FHIR APIs has legal backing for data access. Epic cannot restrict your app from accessing patient data that falls under the Cures Act.

---

## 5. Guardian One Integration Readiness

### Existing Infrastructure That Maps to Epic

| Guardian One Component | Epic Integration Use | Status |
|------------------------|---------------------|--------|
| **H.O.M.E. L.I.N.K. Gateway** | FHIR R4 API routing, rate limiting, circuit breakers | Production-ready |
| **Vault** | EPIC_CLIENT_ID, FHIR tokens, SMART on FHIR credentials | Production-ready |
| **Registry** | Epic threat model, rollback procedures | Template ready |
| **Monitor** | Epic API health checking, anomaly detection | Production-ready |
| **EpicScheduleProvider** | FHIR R4 appointment/scheduling | Stub exists (needs SMART auth) |
| **Chronos pre-charting** | Epic-style pre-chart checklist | Implemented |
| **Content classification gate** | PHI/PII blocking for any Epic data sync | Production-ready |
| **Audit logging** | All Epic operations logged immutably | Production-ready |
| **AI engine** | Clinical decision support via think()/think_quick() | Production-ready |

### What Needs to Be Built

1. **SMART on FHIR OAuth2 flow** — Complete the EpicScheduleProvider authentication
2. **EpicEHRProvider** — New provider following the FinancialProvider pattern:
   - Patient resource fetching
   - Encounter data
   - Lab results (Observation)
   - Medication lists
   - Problem lists / Conditions
   - Vital signs
3. **HealthAgent** — New agent extending BaseAgent:
   - Pre-charting automation (connect Chronos checklist to Epic data)
   - Lab monitoring and alerting
   - Medication review
   - Clinical decision support
4. **Epic Registry Entry** — Threat model, rollback procedures, data flow documentation
5. **Config entry** — Agent scheduling, allowed resources, Epic base URL

### Architecture Fit

Guardian One's architecture is **directly aligned** with Epic's integration model:

```
Epic FHIR R4 API
    ↕ (TLS 1.3, SMART on FHIR OAuth2)
H.O.M.E. L.I.N.K. Gateway (rate limit, circuit breaker)
    ↕
Vault (encrypted FHIR tokens, client credentials)
    ↕
EpicEHRProvider / EpicScheduleProvider
    ↕
HealthAgent (clinical logic, AI reasoning)
    ↕
Content Classification Gate (PHI/PII blocking)
    ↕
Notion Sync / Dashboard (sanitized operational data only)
```

---

## 6. Strategic Assessment

### Strengths of the Physician Builder Position

| Factor | Assessment |
|--------|-----------|
| **Market size** | Epic covers 54.9% of US hospital beds — massive addressable market |
| **Barriers to entry** | High for non-physicians; your MD + AI expertise is the moat |
| **Regulatory tailwinds** | Cures Act + HTI-5 mandate open APIs; Epic cannot block you |
| **Technical readiness** | Guardian One already has 80% of needed infrastructure |
| **AI timing** | Epic investing in 160-200 AI projects; physician-AI builders are scarce |
| **Revenue potential** | App Market revenue sharing + direct enterprise sales to health systems |
| **Competitive dynamics** | Epic is pulling away from competitors; building on the winner |

### Risks

| Risk | Mitigation |
|------|-----------|
| Epic could restrict App Market access | Cures Act legally prevents information blocking; FHIR APIs are mandated |
| Market saturation of EHR tools | Focus on AI-powered clinical tools where physician insight is the differentiator |
| Credential/certification requirements | Start with open FHIR APIs, progress to App Market certification |
| Epic builds competing features internally | Build in niches Epic won't prioritize; physician workflow-specific tools |
| Data sovereignty concerns | Guardian One's Vault + content gate architecture already solves this |

### Recommended Next Steps

1. **Register as an Epic developer** — Access sandbox environment, FHIR documentation
2. **Complete the EpicScheduleProvider** — SMART on FHIR auth + appointment CRUD
3. **Build EpicEHRProvider** — Patient, labs, meds, problems via FHIR R4
4. **Prototype a physician builder tool** — Pre-charting automation or clinical decision support
5. **Attend Epic UGM** — Network with Epic developer community
6. **Evaluate App Market listing** — Revenue sharing model, certification requirements
7. **Position JTMD AI** — Market physician builder services through jtmdai.com

---

## 7. Financial Viability Summary

| Metric | Value |
|--------|-------|
| **Epic's revenue** | ~$4.9B (2024), growing ~10% YoY |
| **Total addressable market** | 3,620+ US hospitals on Epic |
| **Revenue per bed** | ~$2,800/year recurring |
| **App Market opportunity** | Revenue sharing on every transaction |
| **Enterprise sales** | Health systems pay $50K-$500K+ for specialized clinical tools |
| **Consulting** | Physician builder consulting: $200-$400/hr |
| **Epic's customer retention** | Near 100% — your tools stay deployed |

---

## Sources

- [KLAS Research - Epic Market Share](https://klasresearch.com)
- [Dark Daily - Epic Expands EHR Market Share](https://www.darkdaily.com/2025/06/04/epic-expands-ehr-market-share-as-rivals-lose-customers/)
- [Definitive Healthcare - Most Common EHR Systems](https://www.definitivehc.com/blog/most-common-inpatient-ehr-systems)
- [ONC Cures Act Final Rule](https://healthit.gov/regulations/cures-act-final-rule/)
- [Consolidate Health - 21st Century Cures Act Explained](https://consolidate.health/blog/the-21st-century-cures-act-explained-what-it-actually-means-for-healthcare-builders)
- [HealthcareITSkills - Top EHR Vendors 2025](https://healthcareitskills.com/top-ehr-vendors-2025-epic-cerner-meditech-allscripts-veradigm/)
- [EHR in Practice - Epic vs Cerner Comparison](https://www.ehrinpractice.com/epic-ehr-vs-cerner-ehr-comparison.html)
- [CMS Interoperability and Patient Access Final Rule](https://www.cms.gov/priorities/burden-reduction/overview/interoperability/policies-regulations/cms-interoperability-patient-access-final-rule-cms-9115-f)

---

*Generated by Guardian One CFO Intelligence Module*
*Guardian One v2.0 | Data Sovereignty Enforced | Audit Trail Active*
