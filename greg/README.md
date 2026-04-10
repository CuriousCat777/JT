# GREG — Guiding Regulations, Establishment & Growth

An AI agent platform that guides physicians through every step of establishing an independent medical practice in the United States.

## Architecture

GREG is a **multi-agent orchestration platform** built on the Model Context Protocol (MCP). Six specialized agents handle different aspects of practice establishment:

| Agent | Purpose | Key Capabilities |
|-------|---------|-----------------|
| **CREDENCE** | Credentialing & Licensing | NPI lookup, DEA registration, state license verification |
| **FORMA** | Business Formation | Entity recommendation, EIN guidance, operating agreements |
| **COMPLY** | Regulatory Compliance | CMS enrollment, HIPAA toolkit, OIG exclusion checks |
| **VITALS** | EHR & Clinical Systems | Local charting, FHIR R4 bridge, e-prescribing |
| **LEDGER** | Financial Management | Billing, claims, payroll, tax estimation |
| **NEXUS** | Community & Network | Referral networks, telehealth, provider directories |

## Tech Stack

- **MCP Server**: TypeScript + `@modelcontextprotocol/sdk`
- **Database**: PostgreSQL + Drizzle ORM
- **Frontend**: React 18 + TypeScript + Tailwind CSS
- **Validation**: Zod schemas throughout
- **Auth**: JWT sessions + OAuth 2.1 for API integrations

## Quick Start

### MCP Server

```bash
cd greg/server
npm install
npm run dev
```

### Frontend

```bash
cd greg/client
npm install
npm run dev
```

## "Order Your Clinic" Flow

1. **Assessment** — Location, specialty, timeline, budget analysis
2. **Credentialing** — NPI, state license, DEA, CAQH (CREDENCE)
3. **Business Formation** — Entity type, EIN, insurance (FORMA)
4. **Regulatory Enrollment** — Medicare, HIPAA, CLIA (COMPLY)
5. **Clinical Setup** — EHR, FHIR bridge, e-prescribing (VITALS)
6. **Financial Setup** — Billing, payroll, projections (LEDGER)
7. **Launch** — Directory listings, referral network (NEXUS)

## The Ely, MN Scenario

A family medicine physician graduates residency and wants to open a clinic in Ely, Minnesota — a small town served by Essentia Health's regional system. Using GREG, they establish a financially solvent, regulatory-compliant clinic that serves as a community healthcare node, connecting locals to Essentia's specialty services while maintaining independent practice.

## Pricing Tiers

| Tier | Price | Features |
|------|-------|----------|
| **Explore** | Free | NPI lookup, readiness assessment, state research |
| **Starter** | $49/mo | Full credentialing, formation guidance, HIPAA toolkit |
| **Professional** | $149/mo | + EHR, billing, payroll, referral network |
| **Enterprise** | $299/mo | + Multi-provider, analytics, white-label portal |

## Regulatory Compliance

- HIPAA Technical Safeguards built-in (access control, audit, encryption)
- PHI stored locally on physician's infrastructure with AES-256 encryption at rest
- TLS 1.3 in transit for all external communications
- Role-based access controls with audit logging for all PHI access
- State-by-state compliance matrix for all 50 states + DC

## External APIs

| Service | Endpoint | Auth | Cost |
|---------|----------|------|------|
| NPPES/NPI | npiregistry.cms.hhs.gov | None | Free |
| Epic FHIR R4 | fhir.epic.com | OAuth 2.0 | Free (sandbox) |
| CMS Developer | developer.cms.gov | API Key | Free |
| ICD-10 Lookup | clinicaltables.nlm.nih.gov | None | Free |
| RxNorm | rxnav.nlm.nih.gov | None | Free |
| OIG LEIE | oig.hhs.gov | None | Free |
| SAM.gov | api.sam.gov | API Key | Free |

---

*GREG — Start My Practice MD*
