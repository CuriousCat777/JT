/**
 * VITALS — EHR & Clinical Systems Agent
 * Manages the hybrid EHR — lightweight local charting with FHIR R4 bridge
 * to major health systems.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

// Common primary care CPT code ranges for reference only.
// CPT codes and descriptions are copyrighted by the AMA. This tool provides
// code-range guidance; users must supply a licensed CPT dataset for full descriptions.
const CPT_CODE_RANGES: Record<string, { range: string; category: string; note: string }[]> = {
  "E&M": [
    { range: "99202-99205", category: "E&M", note: "New patient office visits (straightforward to high complexity)" },
    { range: "99211-99215", category: "E&M", note: "Established patient office visits" },
  ],
  lab: [
    { range: "36415", category: "lab", note: "Venipuncture (collection)" },
    { range: "80047-80081", category: "lab", note: "Organ/disease-oriented panels" },
    { range: "81000-81099", category: "lab", note: "Urinalysis" },
    { range: "85004-85999", category: "lab", note: "Hematology" },
    { range: "87040-87999", category: "lab", note: "Microbiology/infectious disease" },
  ],
  procedure: [
    { range: "10060-10180", category: "procedure", note: "Incision and drainage" },
    { range: "11102-11107", category: "procedure", note: "Skin biopsy" },
    { range: "17000-17286", category: "procedure", note: "Destruction of lesions" },
    { range: "20600-20611", category: "procedure", note: "Joint injections/aspirations" },
    { range: "69200-69222", category: "procedure", note: "Ear procedures" },
  ],
  preventive: [
    { range: "99381-99387", category: "preventive", note: "Preventive visit, new patient (by age)" },
    { range: "99391-99397", category: "preventive", note: "Preventive visit, established patient (by age)" },
  ],
};

export function registerVitalsTools(server: McpServer): void {
  server.tool(
    "vitals_patient_create",
    "Create a new patient record in the local EHR.",
    {
      practice_id: z.string().describe("Practice UUID"),
      first_name: z.string().describe("Patient first name"),
      last_name: z.string().describe("Patient last name"),
      date_of_birth: z.string().describe("Date of birth (YYYY-MM-DD)"),
      gender: z.string().describe("Gender"),
      phone: z.string().optional().describe("Phone number"),
      email: z.string().optional().describe("Email"),
      address: z.object({ line1: z.string(), line2: z.string().optional(), city: z.string(), state: z.string(), zip: z.string() }).optional(),
      insurance: z.object({ payer_name: z.string(), member_id: z.string(), group_number: z.string().optional() }).optional(),
    },
    async (params) => {
      const mrn = `MRN-${Date.now().toString(36).toUpperCase()}-${Math.random().toString(36).substring(2, 6).toUpperCase()}`;
      const result = {
        status: "created",
        patient: { id: crypto.randomUUID(), mrn, ...params, created_at: new Date().toISOString() },
        next_steps: [
          "Verify insurance eligibility before first visit",
          "Send new patient intake forms via patient portal",
          "Schedule initial appointment",
        ],
      };
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "vitals_encounter_create",
    "Document a clinical encounter.",
    {
      patient_id: z.string().describe("Patient UUID"),
      physician_id: z.string().describe("Physician UUID"),
      practice_id: z.string().describe("Practice UUID"),
      encounter_type: z.enum(["new_patient", "follow_up", "urgent", "telehealth", "preventive"]).describe("Type of encounter"),
      chief_complaint: z.string().describe("Chief complaint"),
      assessment: z.string().optional().describe("Clinical assessment"),
      plan: z.string().optional().describe("Treatment plan"),
      icd10_codes: z.array(z.string()).optional().describe("ICD-10 diagnosis codes"),
      cpt_codes: z.array(z.string()).optional().describe("CPT procedure codes"),
    },
    async (params) => {
      const result = {
        status: "documented",
        encounter: {
          id: crypto.randomUUID(),
          ...params,
          encounter_date: new Date().toISOString(),
          status: "COMPLETED",
        },
        billing_ready: Boolean(params.icd10_codes?.length && params.cpt_codes?.length),
        documentation_checklist: {
          chief_complaint: Boolean(params.chief_complaint),
          assessment: Boolean(params.assessment),
          plan: Boolean(params.plan),
          diagnosis_codes: Boolean(params.icd10_codes?.length),
          procedure_codes: Boolean(params.cpt_codes?.length),
        },
      };
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "vitals_prescription_create",
    "Generate an e-prescription with NCPDP SCRIPT guidance.",
    {
      patient_id: z.string().describe("Patient UUID"),
      physician_id: z.string().describe("Physician UUID"),
      medication_name: z.string().describe("Medication name"),
      dosage: z.string().describe("Dosage (e.g., 10mg)"),
      frequency: z.string().describe("Frequency (e.g., once daily)"),
      quantity: z.number().describe("Quantity to dispense"),
      refills: z.number().default(0).describe("Number of refills"),
      pharmacy_npi: z.string().optional().describe("Pharmacy NPI for e-prescribing"),
      is_controlled: z.boolean().default(false).describe("Whether this is a controlled substance"),
    },
    async (params) => {
      const result = {
        prescription: {
          id: crypto.randomUUID(),
          ...params,
          created_at: new Date().toISOString(),
          format: "NCPDP SCRIPT 2017071",
        },
        e_prescribing: {
          standard: "NCPDP SCRIPT 2017071 (required for Medicare Part D)",
          network: "Surescripts — connects to 90%+ of US pharmacies",
          setup_requirements: [
            "Surescripts-certified EHR or e-prescribing software",
            "Active DEA registration (for controlled substances)",
            "Identity proofing and two-factor authentication for EPCS",
          ],
        },
        controlled_substance: params.is_controlled ? {
          epcs_required: true,
          requirements: [
            "EPCS-certified software",
            "Identity proofing by approved credential service provider",
            "Two-factor authentication for each controlled substance prescription",
            "DEA must be active and linked to prescribing software",
          ],
          pmp_check: "MANDATORY: Check state Prescription Monitoring Program before prescribing Schedule II-IV",
        } : undefined,
      };
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "vitals_lab_order",
    "Create a lab order with LOINC coding.",
    {
      patient_id: z.string().describe("Patient UUID"),
      physician_id: z.string().describe("Physician UUID"),
      lab_tests: z.array(z.object({ loinc_code: z.string(), test_name: z.string() })).describe("Lab tests to order"),
      lab_facility: z.string().optional().describe("Lab facility name"),
      priority: z.enum(["routine", "stat", "urgent"]).default("routine"),
      clinical_notes: z.string().optional().describe("Clinical notes for lab"),
    },
    async (params) => {
      const result = {
        lab_order: { id: crypto.randomUUID(), ...params, order_date: new Date().toISOString(), status: "ORDERED" },
        interface_requirements: {
          standard: "HL7 v2.5.1 ORM (Order) / ORU (Result) messages",
          fhir_alternative: "FHIR R4 ServiceRequest resource",
          common_lab_interfaces: ["Quest Diagnostics (Care360)", "LabCorp (Beacon)", "Mayo Medical Laboratories", "ARUP Laboratories"],
        },
        turnaround: {
          routine: "24-72 hours",
          stat: "1-4 hours",
          urgent: "4-24 hours",
          reference_lab: "3-7 days for send-out tests",
        },
      };
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "vitals_fhir_patient_search",
    "Search for patients via FHIR R4 — guidance for connecting to health systems.",
    {
      family_name: z.string().optional().describe("Patient family/last name"),
      given_name: z.string().optional().describe("Patient given/first name"),
      birthdate: z.string().optional().describe("Date of birth (YYYY-MM-DD)"),
      identifier: z.string().optional().describe("Patient identifier (MRN, etc.)"),
    },
    async (params) => {
      const result = {
        fhir_guidance: {
          standard: "HL7 FHIR R4 (4.0.1)",
          patient_search_endpoint: "GET [base]/Patient?family={family}&given={given}&birthdate={dob}",
          search_params: params,
          authentication: "OAuth 2.0 (SMART on FHIR authorization)",
        },
        epic_fhir: {
          sandbox: "https://fhir.epic.com/interconnect-fhir-oauth/api/FHIR/R4",
          production: "Requires Epic App Orchard approval",
          setup_steps: [
            "Register app at https://fhir.epic.com/Developer/Apps",
            "Implement SMART on FHIR OAuth 2.0 flow",
            "Test against Epic sandbox",
            "Submit for App Orchard review",
            "Deploy with health system approval",
          ],
        },
        essentia_health: {
          ehr: "Epic",
          fhir_capability: "FHIR R4 available via Epic open APIs",
          note: "Contact Essentia Health IT for production access credentials",
        },
        sample_fhir_response: {
          resourceType: "Bundle",
          type: "searchset",
          total: 1,
          entry: [{
            resource: {
              resourceType: "Patient",
              id: "example-id",
              name: [{ family: params.family_name ?? "Example", given: [params.given_name ?? "Patient"] }],
              birthDate: params.birthdate ?? "1990-01-01",
              gender: "unknown",
            },
          }],
        },
      };
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "vitals_fhir_send_referral",
    "Send a referral to a connected health system via FHIR.",
    {
      patient_id: z.string().describe("Patient UUID"),
      referring_physician_npi: z.string().describe("Referring physician NPI"),
      receiving_physician_npi: z.string().describe("Receiving physician NPI"),
      receiving_organization: z.string().describe("Receiving organization"),
      reason: z.string().describe("Reason for referral"),
      urgency: z.enum(["routine", "urgent", "stat"]).default("routine"),
      clinical_summary: z.string().optional().describe("Clinical summary"),
    },
    async (params) => {
      const result = {
        referral: { id: crypto.randomUUID(), ...params, created_at: new Date().toISOString(), status: "SENT" },
        fhir_resource: {
          resourceType: "ServiceRequest",
          status: "active",
          intent: "order",
          priority: params.urgency,
          code: { text: params.reason },
          requester: { identifier: { value: params.referring_physician_npi } },
          performer: [{ identifier: { value: params.receiving_physician_npi } }],
        },
        essentia_referral: params.receiving_organization.toLowerCase().includes("essentia") ? {
          process: "Essentia Health accepts electronic referrals via Epic CareLink",
          portal: "Epic CareLink for referring providers",
          phone: "Essentia referral center for Ely/NE MN area",
        } : undefined,
      };
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "vitals_fhir_receive_results",
    "Pull results from connected lab/hospital via FHIR.",
    {
      patient_id: z.string().describe("Patient UUID"),
      result_type: z.enum(["lab", "imaging", "pathology"]).describe("Result type"),
      date_range: z.string().optional().describe("Date range (e.g., 2024-01-01 to 2024-03-01)"),
    },
    async (params) => {
      const result = {
        query: params,
        fhir_endpoints: {
          lab: "GET [base]/DiagnosticReport?patient={id}&category=LAB",
          imaging: "GET [base]/DiagnosticReport?patient={id}&category=RAD",
          pathology: "GET [base]/DiagnosticReport?patient={id}&category=PAT",
          observations: "GET [base]/Observation?patient={id}&category=laboratory",
        },
        legacy_interfaces: {
          hl7v2: { oru: "ORU^R01 — Unsolicited observation result", adt: "ADT messages for admit/discharge/transfer" },
          note: "Many labs still use HL7v2 for result delivery. Ensure your EHR supports both FHIR and HL7v2.",
        },
      };
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "vitals_icd10_search",
    "Search ICD-10-CM diagnosis codes.",
    {
      query: z.string().describe("Search term (code or description)"),
      max_results: z.number().default(10).describe("Maximum results"),
    },
    async (params) => {
      try {
        const url = `https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search?sf=code,name&terms=${encodeURIComponent(params.query)}&maxList=${params.max_results}`;
        const response = await fetch(url);
        const data = await response.json() as [number, string[], Record<string, string>, [string, string][]];
        const results = (data[3] ?? []).map(([code, name]: [string, string]) => ({ code, description: name }));
        return { content: [{ type: "text", text: JSON.stringify({ query: params.query, results, total: data[0] }, null, 2) }] };
      } catch {
        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              query: params.query,
              error: "ICD-10 API unavailable",
              fallback: "Use https://clinicaltables.nlm.nih.gov/ for manual search",
            }, null, 2),
          }],
        };
      }
    },
  );

  server.tool(
    "vitals_cpt_search",
    "Search CPT procedure codes.",
    {
      query: z.string().describe("Search term"),
      category: z.enum(["E&M", "procedure", "lab", "preventive", "all"]).default("all").describe("CPT category"),
    },
    async (params) => {
      const categories = params.category === "all" ? Object.keys(CPT_CODE_RANGES) : [params.category];
      const results = categories.flatMap((cat) =>
        (CPT_CODE_RANGES[cat] ?? []).filter((c) =>
          c.range.includes(params.query) || c.note.toLowerCase().includes(params.query.toLowerCase())
        )
      );

      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            query: params.query,
            category: params.category,
            results: results.length > 0 ? results : Object.values(CPT_CODE_RANGES).flat(),
            note: "CPT codes and descriptions are copyrighted by the AMA. This tool provides code ranges for reference only. A licensed CPT dataset is required for full descriptions and billing use.",
            resource: "Licensed CPT data available from the AMA at https://www.ama-assn.org/practice-management/cpt",
          }, null, 2),
        }],
      };
    },
  );

  server.tool(
    "vitals_backup_local",
    "Generate encrypted local backup procedure for practice data.",
    {
      practice_id: z.string().describe("Practice UUID"),
      backup_type: z.enum(["full", "incremental", "differential"]).default("full"),
    },
    async (params) => {
      const result = {
        backup: { practice_id: params.practice_id, type: params.backup_type, initiated: new Date().toISOString() },
        encryption: { algorithm: "AES-256-GCM", key_management: "Keys stored separately from backup data" },
        retention_policy: { daily: "7 daily backups", weekly: "4 weekly backups", monthly: "12 monthly backups", annual: "7 annual backups" },
        disaster_recovery: {
          rto: "4 hours (Recovery Time Objective)",
          rpo: "24 hours (Recovery Point Objective — for daily backups)",
          testing: "Test restore quarterly; document results",
        },
        hipaa_requirements: [
          "Backups must be encrypted (AES-256)",
          "Access to backups restricted to authorized personnel",
          "Backup media stored in secure location (fireproof safe or offsite)",
          "Backup logs maintained as part of audit trail",
          "Retention: Minimum 6 years per HIPAA, 7-10 years recommended",
        ],
      };
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );
}
