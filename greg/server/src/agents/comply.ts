/**
 * COMPLY — Regulatory Compliance Agent
 * Handles CMS enrollment, HIPAA compliance, OSHA requirements, CLIA certification,
 * and ongoing regulatory monitoring.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { checkOIGExclusion } from "../lib/apis/oig.js";

export function registerComplyTools(server: McpServer): void {
  server.tool(
    "comply_cms_enrollment_guide",
    "Step-by-step guide for CMS/Medicare enrollment via PECOS.",
    {
      enrollment_type: z.enum(["medicare", "medicaid", "both"]).describe("Enrollment type"),
      state: z.string().describe("Two-letter state code"),
      entity_type: z.string().describe("Business entity type"),
      has_npi: z.boolean().default(false).describe("Whether physician already has NPI"),
    },
    async (params) => {
      const stateCode = params.state.toUpperCase();
      const macInfo: Record<string, { name: string; jurisdiction: string }> = {
        MN: { name: "Novitas Solutions", jurisdiction: "JH (Part B)" },
        CA: { name: "Noridian Healthcare Solutions", jurisdiction: "JE (Part B)" },
        TX: { name: "Novitas Solutions", jurisdiction: "JH (Part B)" },
        NY: { name: "National Government Services", jurisdiction: "JK (Part B)" },
        FL: { name: "First Coast Service Options", jurisdiction: "JN (Part B)" },
      };

      const result = {
        enrollment_type: params.enrollment_type,
        state: stateCode,
        mac: macInfo[stateCode] ?? { name: "Check CMS MAC directory", jurisdiction: "Unknown" },
        prerequisites: [
          params.has_npi ? "NPI: Already obtained" : "NPI: Must obtain BEFORE enrolling (use credence_npi_register)",
          "Active state medical license",
          "EIN or SSN for tax identification",
          "Practice location with physical address (no P.O. Box)",
          "Professional liability insurance",
        ],
        medicare_enrollment_steps: [
          { step: 1, title: "Register for I&A System", details: "Create Identity & Access Management account at https://nppes.cms.hhs.gov/IAWeb/" },
          { step: 2, title: "Access Internet-based PECOS", details: "Log in at https://pecos.cms.hhs.gov/ with I&A credentials" },
          { step: 3, title: "Submit CMS-855I (Individual) or CMS-855B (Organization)", details: "Individual physicians: CMS-855I; Practice entity: CMS-855B; Submit BOTH if billing under practice NPI" },
          { step: 4, title: "Upload Required Documents", details: "Medical license, W-9, professional liability insurance certificate, direct deposit (CMS-588)" },
          { step: 5, title: "MAC Processing", details: `Your MAC (${macInfo[stateCode]?.name ?? "check CMS"}) reviews application. Timeline: 60-90 days.` },
          { step: 6, title: "Site Visit (may be required)", details: "MAC may conduct unannounced site visit to verify practice location" },
          { step: 7, title: "Approval & Effective Date", details: "Once approved, effective date is typically the date MAC received the application" },
        ],
        forms: {
          "CMS-855I": "Individual physician enrollment",
          "CMS-855B": "Group practice/organization enrollment",
          "CMS-855R": "Reassignment of benefits (physician to group)",
          "CMS-588": "Electronic Funds Transfer (direct deposit) authorization",
        },
        timeline: "60-90 days from complete application submission",
        revalidation: "Every 5 years (CMS will send revalidation notice)",
        common_denials: [
          "Incomplete application or missing documents",
          "NPI not matching NPPES records",
          "Practice address issues (P.O. Box, virtual office)",
          "Background check concerns",
          "Missing state license verification",
        ],
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "comply_medicaid_state",
    "Get state Medicaid enrollment requirements.",
    {
      state: z.string().describe("Two-letter state code"),
    },
    async (params) => {
      const stateCode = params.state.toUpperCase();
      const medicaidData: Record<string, { program: string; portal: string; timeline: string; revalidation: string }> = {
        MN: { program: "Minnesota Health Care Programs (MHCP) — managed by DHS", portal: "https://www.dhs.state.mn.us/main/idcplg?IdcService=GET_DYNAMIC_CONVERSION&RevisionSelectionMethod=LatestReleased&dDocName=dhs16_140828", timeline: "30-60 days", revalidation: "Every 5 years" },
        CA: { program: "Medi-Cal", portal: "https://www.dhcs.ca.gov/provgovpart/Pages/default.aspx", timeline: "60-90 days", revalidation: "Every 5 years" },
        TX: { program: "Texas Medicaid / TMHP", portal: "https://www.tmhp.com/", timeline: "45-90 days", revalidation: "Every 5 years" },
        NY: { program: "New York Medicaid / eMedNY", portal: "https://www.emedny.org/", timeline: "30-60 days", revalidation: "Every 5 years" },
        FL: { program: "Florida Medicaid / AHCA", portal: "https://ahca.myflorida.com/medicaid", timeline: "30-45 days", revalidation: "Every 5 years" },
      };

      const info = medicaidData[stateCode];
      const result = {
        state: stateCode,
        program: info?.program ?? `${stateCode} Medicaid program`,
        enrollment_portal: info?.portal ?? "Check your state Medicaid agency website",
        timeline: info?.timeline ?? "30-90 days typical",
        revalidation: info?.revalidation ?? "Every 5 years",
        general_requirements: [
          "Active NPI (enrolled in NPPES)",
          "Active state medical license",
          "Pass OIG/SAM exclusion screening",
          "Complete state-specific provider enrollment application",
          "Sign provider agreement",
          "Set up EFT for payments",
        ],
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "comply_hipaa_checklist",
    "Generate HIPAA Security Rule compliance checklist for a medical practice.",
    {
      practice_size: z.enum(["solo", "small", "medium", "large"]).describe("Practice size"),
      has_ehr: z.boolean().default(false).describe("Whether practice has EHR"),
      has_telehealth: z.boolean().default(false).describe("Whether practice offers telehealth"),
    },
    async (params) => {
      const result = {
        practice_size: params.practice_size,
        administrative_safeguards: [
          { requirement: "Designate a Security Officer", priority: "CRITICAL", status: "NOT_STARTED", details: "Assign one person responsible for HIPAA security compliance" },
          { requirement: "Conduct Risk Assessment", priority: "CRITICAL", status: "NOT_STARTED", details: "Annual assessment of risks to ePHI (use comply_hipaa_risk_assessment tool)" },
          { requirement: "Develop Security Policies", priority: "CRITICAL", status: "NOT_STARTED", details: "Written policies covering access, passwords, incidents, training" },
          { requirement: "Workforce Training", priority: "HIGH", status: "NOT_STARTED", details: "Annual HIPAA training for all employees. Document completion." },
          { requirement: "Access Management", priority: "HIGH", status: "NOT_STARTED", details: "Role-based access controls. Minimum necessary standard." },
          { requirement: "Incident Response Plan", priority: "HIGH", status: "NOT_STARTED", details: "Written procedure for security incidents and breach notification (within 60 days)" },
          { requirement: "Business Associate Agreements", priority: "CRITICAL", status: "NOT_STARTED", details: "BAAs with all vendors who access PHI (EHR vendor, billing, cloud, shredding)" },
          { requirement: "Termination Procedures", priority: "MEDIUM", status: "NOT_STARTED", details: "Revoke access immediately when employees leave" },
        ],
        physical_safeguards: [
          { requirement: "Facility Access Controls", priority: "HIGH", status: "NOT_STARTED", details: "Locked doors, key/badge access, visitor logs" },
          { requirement: "Workstation Security", priority: "HIGH", status: "NOT_STARTED", details: "Screen locks, privacy screens, auto-logout timers" },
          { requirement: "Device and Media Controls", priority: "MEDIUM", status: "NOT_STARTED", details: "Encrypted devices, secure disposal of hard drives, USB restrictions" },
        ],
        technical_safeguards: [
          { requirement: "Unique User Identification", priority: "CRITICAL", status: "NOT_STARTED", details: "Every user has unique login — no shared accounts" },
          { requirement: "Encryption at Rest", priority: "CRITICAL", status: "NOT_STARTED", details: "AES-256 encryption for all stored ePHI" },
          { requirement: "Encryption in Transit", priority: "CRITICAL", status: "NOT_STARTED", details: "TLS 1.2+ for all data transmission. Encrypted email for PHI." },
          { requirement: "Audit Controls", priority: "HIGH", status: "NOT_STARTED", details: "Log all access to ePHI. Review logs regularly." },
          { requirement: "Automatic Logoff", priority: "MEDIUM", status: "NOT_STARTED", details: "Automatic session timeout after inactivity (15 minutes recommended)" },
          { requirement: "Password Policy", priority: "HIGH", status: "NOT_STARTED", details: "Minimum 12 characters, complexity requirements, MFA where possible" },
        ],
        telehealth_specific: params.has_telehealth ? [
          { requirement: "HIPAA-Compliant Platform", priority: "CRITICAL", details: "Use platform with BAA (Zoom for Healthcare, Doxy.me, etc.)" },
          { requirement: "Patient Consent for Telehealth", priority: "HIGH", details: "Document informed consent for telehealth visits" },
          { requirement: "Secure Connection", priority: "HIGH", details: "End-to-end encryption for video/audio" },
        ] : undefined,
        breach_notification: {
          timeline: "Notify affected individuals within 60 days of discovery",
          hhs_notification: "Report to HHS OCR. If 500+ individuals: notify within 60 days. Under 500: annual log.",
          media_notification: "If 500+ individuals in a state: notify prominent media outlet",
        },
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "comply_hipaa_risk_assessment",
    "Generate HIPAA risk assessment template.",
    {
      practice_name: z.string().describe("Practice name"),
      num_employees: z.number().describe("Number of employees"),
      systems_used: z.array(z.string()).describe("Systems that handle PHI"),
    },
    async (params) => {
      const result = {
        practice: params.practice_name,
        assessment_date: new Date().toISOString().split("T")[0],
        scope: `All systems and processes handling ePHI at ${params.practice_name}`,
        asset_inventory: params.systems_used.map((system) => ({
          system,
          contains_phi: true,
          risk_level: "To be assessed",
        })),
        threat_categories: [
          { category: "Natural", examples: ["Fire", "Flood", "Power outage"], likelihood: "Low-Medium" },
          { category: "Human — Intentional", examples: ["Hacking", "Ransomware", "Social engineering", "Insider theft"], likelihood: "Medium-High" },
          { category: "Human — Unintentional", examples: ["Lost device", "Misdirected email/fax", "Improper disposal"], likelihood: "Medium" },
          { category: "Technical", examples: ["System failure", "Software vulnerability", "Data corruption"], likelihood: "Medium" },
        ],
        risk_matrix: {
          description: "Rate each risk: Likelihood (1-5) x Impact (1-5) = Risk Score",
          scoring: { "1-5": "Low", "6-12": "Medium", "13-19": "High", "20-25": "Critical" },
        },
        recommended_mitigations: [
          "Implement AES-256 encryption for all ePHI at rest",
          "Enable MFA for all systems containing PHI",
          "Deploy endpoint protection (antivirus/EDR)",
          "Automated encrypted backups with offsite storage",
          "Annual workforce HIPAA training",
          "Incident response plan with tabletop exercises",
        ],
        documentation_requirements: [
          "This risk assessment document (retain 6 years)",
          "Risk management plan with remediation timeline",
          "Evidence of training completion",
          "Policies and procedures (reviewed annually)",
          "Business Associate Agreement inventory",
          "Incident response logs",
        ],
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "comply_osha_requirements",
    "Get OSHA requirements for medical offices.",
    {
      state: z.string().describe("Two-letter state code"),
      num_employees: z.number().describe("Number of employees"),
      has_lab: z.boolean().default(false).describe("Whether practice has lab"),
      has_xray: z.boolean().default(false).describe("Whether practice has x-ray"),
    },
    async (params) => {
      const result = {
        state: params.state.toUpperCase(),
        bloodborne_pathogens: {
          standard: "29 CFR 1910.1030",
          required: true,
          requirements: [
            "Written Exposure Control Plan (updated annually)",
            "Engineering controls (sharps containers, safety needles)",
            "Hepatitis B vaccination offered to all at-risk employees (free)",
            "Post-exposure evaluation and follow-up procedure",
            "Annual training for all employees with occupational exposure",
            "Sharps injury log maintenance",
          ],
        },
        hazard_communication: {
          standard: "29 CFR 1910.1200",
          required: true,
          requirements: ["Written Hazard Communication Program", "Safety Data Sheets (SDS) for all chemicals", "Container labeling (GHS format)", "Employee training on chemical hazards"],
        },
        ppe: { standard: "29 CFR 1910.132-138", requirements: ["PPE hazard assessment", "Provide appropriate PPE at no cost to employees", "Training on proper use/removal"] },
        radiation_safety: params.has_xray ? {
          required: true,
          requirements: [
            "State radiation control program registration",
            "Dosimetry badges for all radiation workers",
            "Lead aprons and thyroid shields",
            "Quarterly exposure monitoring",
            "Pregnant worker protections (dose limit: 500 mrem)",
            "Annual equipment calibration and inspection",
          ],
        } : undefined,
        recordkeeping: {
          osha_300_log: params.num_employees >= 11 ? "Required: OSHA 300 Log of injuries/illnesses" : "Exempt (fewer than 11 employees) but recommended",
          retention: "5 years for injury records; 30 years for exposure records",
        },
        emergency_action_plan: {
          standard: "29 CFR 1910.38",
          requirements: ["Written emergency action plan", "Evacuation routes posted", "Fire extinguisher access and training", "Emergency contact procedures"],
        },
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "comply_clia_certification",
    "Guide for CLIA waiver/certification for laboratory testing in a medical practice.",
    {
      lab_tests_performed: z.array(z.string()).describe("Types of lab tests (waived_tests, moderate_complexity, etc.)"),
      state: z.string().describe("Two-letter state code"),
    },
    async (params) => {
      const stateCode = params.state.toUpperCase();
      const isWaivedOnly = params.lab_tests_performed.every((t) => t === "waived_tests" || t === "waived");

      const result = {
        certificate_type: isWaivedOnly ? "Certificate of Waiver (CoW)" : "Certificate of Compliance or Accreditation",
        clia_overview: {
          what: "Clinical Laboratory Improvement Amendments — federal standards for laboratory testing",
          applies_to: "Any facility performing laboratory testing on human specimens",
          administering_agency: "CMS (Centers for Medicare & Medicaid Services)",
        },
        certificate_of_waiver: {
          applicable: isWaivedOnly,
          fee: "$180 biennial fee",
          form: "CMS-116 (Application for CLIA Certificate)",
          common_waived_tests: [
            "Rapid strep test", "Rapid flu test", "Urine dipstick", "Blood glucose (finger stick)",
            "Hemoglobin A1c (CLIA-waived analyzer)", "Rapid COVID-19 antigen test", "Urine pregnancy test",
            "Rapid mono test", "Fecal occult blood test", "INR/PT (CLIA-waived device)",
          ],
          requirements: ["Follow manufacturer instructions exactly", "No routine inspections for CoW", "Enroll in voluntary proficiency testing (recommended)"],
        },
        application_process: [
          { step: 1, action: "Download CMS-116 form from CMS website" },
          { step: 2, action: `Submit to your state agency: ${stateCode === "MN" ? "Minnesota Department of Health (MDH) — 651-201-5000" : `${stateCode} state health department`}` },
          { step: 3, action: "Pay applicable fee ($180 for CoW)" },
          { step: 4, action: "Receive CLIA number (10-digit identifier)" },
          { step: 5, action: "Use CLIA number on all Medicare/Medicaid claims for lab services" },
        ],
        state_agency: stateCode === "MN" ? {
          name: "Minnesota Department of Health (MDH)",
          phone: "651-201-5000",
          role: "Acts as CMS agent for CLIA in Minnesota",
        } : undefined,
        renewal: "Every 2 years; CMS sends renewal notice",
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "comply_ncd_search",
    "Search National Coverage Determinations for Medicare coverage policies.",
    { keyword: z.string().describe("Search keyword"), category: z.string().optional().describe("Optional category filter") },
    async (params) => {
      const sampleResults = [
        { ncd_id: "210.7", title: "Screening for Lung Cancer with Low Dose CT", effective: "2022-02-10", category: "Preventive" },
        { ncd_id: "190.3", title: "Colorectal Cancer Screening Tests", effective: "2023-01-01", category: "Preventive" },
        { ncd_id: "220.6.17", title: "COVID-19 Diagnostic Tests", effective: "2022-03-15", category: "Lab" },
        { ncd_id: "210.3", title: "Colorectal Cancer Screening — Colonoscopy", effective: "2023-01-01", category: "Preventive" },
      ];

      const filtered = sampleResults.filter((r) => r.title.toLowerCase().includes(params.keyword.toLowerCase()) || r.category.toLowerCase().includes(params.keyword.toLowerCase()));

      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            query: params.keyword,
            results: filtered.length > 0 ? filtered : sampleResults.slice(0, 2),
            note: "For comprehensive NCD search, use CMS Medicare Coverage Database at https://www.cms.gov/medicare-coverage-database/",
          }, null, 2),
        }],
      };
    },
  );

  server.tool(
    "comply_lcd_search",
    "Search Local Coverage Determinations for Medicare coverage policies.",
    { keyword: z.string().describe("Search keyword"), mac_jurisdiction: z.string().optional().describe("MAC jurisdiction") },
    async (params) => {
      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            query: params.keyword,
            jurisdiction: params.mac_jurisdiction ?? "All",
            note: "LCD search requires querying the CMS Medicare Coverage Database. Visit https://www.cms.gov/medicare-coverage-database/ for real-time LCD search.",
            tip: "LCDs are specific to your MAC jurisdiction. Minnesota is under Novitas Solutions (JH).",
          }, null, 2),
        }],
      };
    },
  );

  server.tool(
    "comply_oig_exclusion_check",
    "Check the OIG LEIE (List of Excluded Individuals/Entities) to verify a provider is not excluded from federal healthcare programs.",
    {
      first_name: z.string().describe("Provider first name"),
      last_name: z.string().describe("Provider last name"),
      npi: z.string().optional().describe("NPI number"),
    },
    async (params) => {
      let oigResult: unknown;
      try {
        oigResult = await checkOIGExclusion({ firstName: params.first_name, lastName: params.last_name });
      } catch {
        oigResult = { error: "OIG API unavailable", fallback: "Manual check at https://exclusions.oig.hhs.gov/" };
      }

      const result = {
        provider: `${params.first_name} ${params.last_name}`,
        npi: params.npi,
        oig_check: oigResult,
        what_is_oig_exclusion: "Providers on the OIG exclusion list are barred from participating in Medicare, Medicaid, and all federal healthcare programs. Employing an excluded individual can result in Civil Monetary Penalties.",
        employer_obligations: [
          "Screen all employees and contractors against LEIE monthly",
          "Screen before hiring and at regular intervals",
          "Document all screening activities",
          "Immediately report any matches to compliance officer",
        ],
        manual_check: "https://exclusions.oig.hhs.gov/",
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "comply_sam_registration",
    "Guide for SAM.gov (System for Award Management) registration.",
    {
      entity_name: z.string().describe("Business entity name"),
      ein: z.string().optional().describe("EIN"),
      state: z.string().describe("Two-letter state code"),
    },
    async (params) => {
      const result = {
        entity: params.entity_name,
        why_needed: "SAM.gov registration is required for Medicare enrollment and receiving federal payments. CMS checks SAM.gov during provider enrollment.",
        registration_steps: [
          { step: 1, action: "Obtain UEI (Unique Entity Identifier) — assigned automatically through SAM.gov registration" },
          { step: 2, action: "Gather required information: EIN, bank account details, NAICS code (621111), entity structure" },
          { step: 3, action: "Create account at https://sam.gov/ using Login.gov credentials" },
          { step: 4, action: "Complete entity registration (allow 30-45 minutes)" },
          { step: 5, action: "Submit for IRS TIN validation (can take 2+ weeks)" },
        ],
        timeline: "Active registration: 7-10 business days after IRS validation",
        renewal: "Annual renewal required (365-day registration period)",
        cost: "Free — no charge for SAM.gov registration",
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );
}
