/**
 * Zod validation shapes for GREG agent tool inputs.
 * These are plain objects of Zod properties (shapes) designed to be passed
 * directly to McpServer.tool() which accepts shape objects, not z.object() schemas.
 * Each agent file uses inline shapes for its tools; these are provided as a
 * centralized reference and can be used via z.object(shape) if needed elsewhere.
 */
import { z } from "zod";

// ── CREDENCE Agent Schemas ────────────────────────────────────────────────────

export const credenceNpiLookupSchema = {
  npi: z.string().optional().describe("10-digit NPI number to look up"),
  first_name: z.string().optional().describe("Provider first name"),
  last_name: z.string().optional().describe("Provider last name"),
  state: z.string().optional().describe("Two-letter state code (e.g., MN, CA)"),
  taxonomy: z.string().optional().describe("Taxonomy/specialty description"),
};

export const credenceNpiRegisterSchema = {
  first_name: z.string().describe("Physician first name"),
  last_name: z.string().describe("Physician last name"),
  entity_type: z.enum(["individual", "organization"]).default("individual").describe("NPI-1 (individual) or NPI-2 (organization)"),
  state: z.string().describe("State of primary practice"),
  specialty: z.string().describe("Primary medical specialty"),
};

export const credenceDeaStatusSchema = {
  dea_number: z.string().optional().describe("DEA registration number"),
  physician_name: z.string().optional().describe("Physician full name for lookup"),
  state: z.string().optional().describe("State to check DEA registration"),
};

export const credenceStateLicenseSchema = {
  state: z.string().describe("Two-letter state code"),
  license_number: z.string().optional().describe("Medical license number"),
  physician_name: z.string().optional().describe("Physician full name"),
};

export const credenceBoardRequirementsSchema = {
  state: z.string().describe("Two-letter state code"),
  specialty: z.string().optional().describe("Medical specialty (e.g., Family Medicine, Internal Medicine)"),
};

export const credenceCaqhStatusSchema = {
  caqh_id: z.string().optional().describe("CAQH ProView provider ID"),
  npi: z.string().optional().describe("NPI number for CAQH lookup"),
  physician_name: z.string().optional().describe("Physician full name"),
};

export const credenceHospitalPrivilegesSchema = {
  physician_id: z.string().optional().describe("Internal physician ID"),
  hospital_name: z.string().optional().describe("Hospital name to check"),
  state: z.string().optional().describe("State to search hospitals"),
  specialty: z.string().optional().describe("Specialty for privilege requirements"),
};

// ── FORMA Agent Schemas ───────────────────────────────────────────────────────

export const formaEntityRecommendSchema = {
  state: z.string().describe("State where practice will be formed"),
  num_physicians: z.number().default(1).describe("Number of physician owners"),
  annual_revenue_estimate: z.number().optional().describe("Estimated annual revenue"),
  has_non_physician_owners: z.boolean().default(false).describe("Whether non-physicians will own equity"),
  specialty: z.string().optional().describe("Primary medical specialty"),
};

export const formaStateRequirementsSchema = {
  state: z.string().describe("Two-letter state code"),
  entity_type: z.enum(["PLLC", "PC", "SOLE_PROP", "S_CORP", "C_CORP"]).optional().describe("Entity type to get requirements for"),
};

export const formaEinGuideSchema = {
  entity_type: z.enum(["PLLC", "PC", "SOLE_PROP", "S_CORP", "C_CORP"]).describe("Business entity type"),
  state: z.string().describe("State of formation"),
  responsible_party_name: z.string().describe("Name of responsible party (owner/officer)"),
  responsible_party_ssn_last4: z.string().optional().describe("Last 4 of SSN for verification guidance"),
};

export const formaOperatingAgreementSchema = {
  entity_type: z.enum(["PLLC", "PC"]).describe("Entity type (PLLC or PC)"),
  state: z.string().describe("State of formation"),
  num_members: z.number().default(1).describe("Number of members/shareholders"),
  practice_name: z.string().describe("Name of the practice"),
};

export const formaInsuranceRequirementsSchema = {
  state: z.string().describe("Two-letter state code"),
  specialty: z.string().describe("Medical specialty"),
  num_employees: z.number().default(1).describe("Number of employees including physician"),
  has_surgery: z.boolean().default(false).describe("Whether practice performs surgery"),
};

export const formaBankAccountChecklistSchema = {
  entity_type: z.enum(["PLLC", "PC", "SOLE_PROP", "S_CORP", "C_CORP"]).describe("Business entity type"),
  state: z.string().describe("State of practice"),
  practice_name: z.string().describe("Legal name of the practice"),
};

export const formaSbaLoansSchema = {
  state: z.string().describe("State of practice"),
  loan_purpose: z.string().optional().describe("Purpose of loan (startup, equipment, real estate)"),
  amount_needed: z.number().optional().describe("Estimated loan amount needed"),
};

// ── COMPLY Agent Schemas ──────────────────────────────────────────────────────

export const complyCmsEnrollmentGuideSchema = {
  provider_type: z.string().default("physician").describe("Provider type for enrollment"),
  state: z.string().optional().describe("State of practice"),
  has_npi: z.boolean().default(false).describe("Whether provider already has NPI"),
};

export const complyMedicaidStateSchema = {
  state: z.string().describe("Two-letter state code"),
  provider_type: z.string().default("physician").describe("Provider type"),
};

export const complyHipaaChecklistSchema = {
  practice_size: z.enum(["solo", "small", "medium", "large"]).default("solo").describe("Practice size category"),
  has_ehr: z.boolean().default(false).describe("Whether practice uses an EHR system"),
};

export const complyHipaaRiskAssessmentSchema = {
  practice_id: z.string().optional().describe("Practice ID for the assessment"),
  practice_name: z.string().optional().describe("Practice name"),
  include_template: z.boolean().default(true).describe("Include risk assessment template"),
};

export const complyOshaRequirementsSchema = {
  state: z.string().describe("Two-letter state code"),
  has_lab: z.boolean().default(false).describe("Whether practice has on-site lab"),
  has_xray: z.boolean().default(false).describe("Whether practice has X-ray equipment"),
  num_employees: z.number().default(1).describe("Number of employees"),
};

export const complyCliaSchema = {
  state: z.string().describe("Two-letter state code"),
  test_types: z.array(z.string()).optional().describe("Types of lab tests performed (e.g., rapid strep, urinalysis, glucose)"),
  waiver_only: z.boolean().default(true).describe("Whether seeking CLIA waiver only vs full certification"),
};

export const complyNcdSearchSchema = {
  keyword: z.string().optional().describe("Keyword to search NCDs"),
  ncd_id: z.string().optional().describe("Specific NCD ID"),
  category: z.string().optional().describe("NCD category"),
};

export const complyLcdSearchSchema = {
  keyword: z.string().optional().describe("Keyword to search LCDs"),
  lcd_id: z.string().optional().describe("Specific LCD ID"),
  state: z.string().optional().describe("State for LCD search"),
  contractor_number: z.string().optional().describe("MAC contractor number"),
};

export const complyOigExclusionCheckSchema = {
  first_name: z.string().optional().describe("Provider first name"),
  last_name: z.string().optional().describe("Provider last name"),
  npi: z.string().optional().describe("NPI number to check"),
  state: z.string().optional().describe("State to narrow search"),
};

export const complySamRegistrationSchema = {
  business_name: z.string().optional().describe("Legal business name"),
  ein: z.string().optional().describe("EIN for registration lookup"),
  state: z.string().optional().describe("State of business"),
};

// ── VITALS Agent Schemas ──────────────────────────────────────────────────────

export const vitalsPatientCreateSchema = {
  practice_id: z.string().describe("Practice ID"),
  first_name: z.string().describe("Patient first name"),
  last_name: z.string().describe("Patient last name"),
  date_of_birth: z.string().describe("Date of birth (YYYY-MM-DD)"),
  gender: z.string().optional().describe("Patient gender"),
  phone: z.string().optional().describe("Phone number"),
  email: z.string().optional().describe("Email address"),
  address: z.object({
    line1: z.string(),
    line2: z.string().optional(),
    city: z.string(),
    state: z.string(),
    zip: z.string(),
  }).optional().describe("Patient address"),
  insurance: z.object({
    payerName: z.string(),
    payerId: z.string(),
    memberId: z.string(),
    groupNumber: z.string().optional(),
    planType: z.string().optional(),
  }).optional().describe("Insurance information"),
};

export const vitalsEncounterCreateSchema = {
  patient_id: z.string().describe("Patient ID"),
  physician_id: z.string().describe("Physician ID"),
  practice_id: z.string().describe("Practice ID"),
  encounter_type: z.string().describe("Encounter type (e.g., office_visit, telehealth, follow_up)"),
  chief_complaint: z.string().optional().describe("Chief complaint"),
  assessment: z.string().optional().describe("Clinical assessment"),
  plan: z.string().optional().describe("Treatment plan"),
  icd10_codes: z.array(z.string()).optional().describe("ICD-10-CM diagnosis codes"),
  cpt_codes: z.array(z.string()).optional().describe("CPT procedure codes"),
  notes: z.string().optional().describe("Additional clinical notes"),
};

export const vitalsPrescriptionCreateSchema = {
  patient_id: z.string().describe("Patient ID"),
  physician_id: z.string().describe("Prescribing physician ID"),
  medication_name: z.string().describe("Medication name"),
  ndc_code: z.string().optional().describe("NDC code"),
  strength: z.string().describe("Medication strength (e.g., 500mg)"),
  dosage_form: z.string().describe("Dosage form (e.g., tablet, capsule)"),
  quantity: z.number().describe("Quantity to dispense"),
  days_supply: z.number().describe("Days supply"),
  sig: z.string().describe("Directions for use"),
  refills: z.number().default(0).describe("Number of refills"),
  daw: z.boolean().default(false).describe("Dispense as written"),
  pharmacy_ncpdp: z.string().optional().describe("Pharmacy NCPDP ID"),
};

export const vitalsLabOrderSchema = {
  patient_id: z.string().describe("Patient ID"),
  physician_id: z.string().describe("Ordering physician ID"),
  tests: z.array(z.object({
    loinc_code: z.string().describe("LOINC code for the test"),
    test_name: z.string().describe("Test name"),
    priority: z.enum(["routine", "stat", "urgent"]).default("routine"),
  })).describe("Lab tests to order"),
  clinical_notes: z.string().optional().describe("Clinical notes for the lab"),
  fasting_required: z.boolean().default(false).describe("Whether fasting is required"),
};

export const vitalsFhirPatientSearchSchema = {
  family: z.string().optional().describe("Family (last) name"),
  given: z.string().optional().describe("Given (first) name"),
  birthdate: z.string().optional().describe("Date of birth (YYYY-MM-DD)"),
  identifier: z.string().optional().describe("Patient identifier (MRN, etc.)"),
  fhir_server_url: z.string().optional().describe("FHIR server base URL"),
};

export const vitalsFhirSendReferralSchema = {
  patient_id: z.string().describe("Patient ID"),
  referring_physician_id: z.string().describe("Referring physician ID"),
  recipient_npi: z.string().describe("Recipient provider NPI"),
  recipient_name: z.string().describe("Recipient provider name"),
  specialty: z.string().describe("Referral specialty"),
  reason: z.string().describe("Reason for referral"),
  urgency: z.enum(["routine", "urgent", "stat"]).default("routine"),
  clinical_notes: z.string().optional().describe("Clinical summary for referral"),
  fhir_endpoint: z.string().optional().describe("Recipient FHIR endpoint URL"),
};

export const vitalsFhirReceiveResultsSchema = {
  patient_id: z.string().optional().describe("Patient ID to fetch results for"),
  order_id: z.string().optional().describe("Original order ID"),
  result_type: z.string().optional().describe("Type of result (lab, imaging, etc.)"),
  fhir_server_url: z.string().optional().describe("FHIR server base URL"),
};

export const vitalsIcd10SearchSchema = {
  query: z.string().describe("Search term for ICD-10-CM codes"),
  max_results: z.number().default(10).describe("Maximum results to return"),
};

export const vitalsCptSearchSchema = {
  query: z.string().describe("Search term for CPT codes"),
  category: z.string().optional().describe("CPT category (E/M, Surgery, etc.)"),
  max_results: z.number().default(10).describe("Maximum results to return"),
};

export const vitalsBackupLocalSchema = {
  practice_id: z.string().describe("Practice ID to backup"),
  backup_type: z.enum(["full", "incremental", "patients_only"]).default("full"),
  encryption_key_id: z.string().optional().describe("Encryption key identifier"),
};

// ── LEDGER Agent Schemas ──────────────────────────────────────────────────────

export const ledgerClaimCreateSchema = {
  encounter_id: z.string().describe("Encounter ID to generate claim from"),
  practice_id: z.string().describe("Practice ID"),
  claim_type: z.enum(["CMS1500", "837P"]).default("CMS1500").describe("Claim form type"),
  payer_name: z.string().describe("Insurance payer name"),
  payer_id: z.string().optional().describe("Payer ID"),
  diagnosis_codes: z.array(z.string()).describe("ICD-10-CM diagnosis codes"),
  procedure_codes: z.array(z.object({
    cpt: z.string().describe("CPT code"),
    modifier: z.string().optional().describe("CPT modifier"),
    units: z.number().default(1),
    charge: z.number().describe("Charge amount"),
  })).describe("Procedure codes with charges"),
};

export const ledgerClaimStatusSchema = {
  claim_id: z.string().optional().describe("Claim ID to check"),
  practice_id: z.string().optional().describe("Practice ID to list all claims"),
  status_filter: z.enum(["DRAFT", "SUBMITTED", "PENDING", "PAID", "DENIED", "APPEALED"]).optional(),
  date_from: z.string().optional().describe("Start date filter (YYYY-MM-DD)"),
  date_to: z.string().optional().describe("End date filter (YYYY-MM-DD)"),
};

export const ledgerRevenueForecastSchema = {
  practice_id: z.string().describe("Practice ID"),
  forecast_months: z.number().default(12).describe("Number of months to forecast"),
  monthly_patient_volume: z.number().optional().describe("Estimated monthly patient volume"),
  avg_reimbursement: z.number().optional().describe("Average reimbursement per visit"),
  payer_mix: z.object({
    medicare_pct: z.number().optional(),
    medicaid_pct: z.number().optional(),
    commercial_pct: z.number().optional(),
    self_pay_pct: z.number().optional(),
  }).optional().describe("Payer mix percentages"),
};

export const ledgerExpenseTrackSchema = {
  practice_id: z.string().describe("Practice ID"),
  category: z.string().describe("Expense category (rent, supplies, equipment, etc.)"),
  description: z.string().describe("Expense description"),
  amount: z.number().describe("Expense amount"),
  date: z.string().describe("Expense date (YYYY-MM-DD)"),
  recurring: z.boolean().default(false).describe("Whether this is a recurring expense"),
  recurrence_interval: z.enum(["monthly", "quarterly", "annually"]).optional(),
};

export const ledgerPayrollCalculateSchema = {
  practice_id: z.string().describe("Practice ID"),
  employee_name: z.string().describe("Employee name"),
  gross_salary: z.number().describe("Gross salary amount"),
  pay_period: z.enum(["weekly", "biweekly", "semimonthly", "monthly"]).describe("Pay period"),
  filing_status: z.enum(["single", "married", "head_of_household"]).default("single"),
  state: z.string().describe("State for tax calculation"),
  pre_tax_deductions: z.number().default(0).describe("Pre-tax deductions (401k, HSA, etc.)"),
  allowances: z.number().default(0).describe("W-4 allowances"),
};

export const ledgerTaxEstimateSchema = {
  practice_id: z.string().describe("Practice ID"),
  entity_type: z.enum(["PLLC", "PC", "SOLE_PROP", "S_CORP", "C_CORP"]).describe("Entity type"),
  state: z.string().describe("State of practice"),
  quarter: z.enum(["Q1", "Q2", "Q3", "Q4"]).describe("Tax quarter"),
  year: z.number().describe("Tax year"),
  gross_revenue: z.number().describe("Gross revenue for the quarter"),
  total_expenses: z.number().describe("Total deductible expenses"),
  owner_salary: z.number().optional().describe("Owner salary (for S-Corp)"),
};

export const ledgerProfitLossSchema = {
  practice_id: z.string().describe("Practice ID"),
  period_start: z.string().describe("Period start date (YYYY-MM-DD)"),
  period_end: z.string().describe("Period end date (YYYY-MM-DD)"),
};

export const ledgerStartupBudgetSchema = {
  state: z.string().describe("State of practice"),
  specialty: z.string().describe("Medical specialty"),
  practice_type: z.enum(["solo", "group", "telehealth_only"]).default("solo"),
  lease_or_own: z.enum(["lease", "own"]).default("lease"),
  num_exam_rooms: z.number().default(2).describe("Number of exam rooms"),
  has_procedures: z.boolean().default(false).describe("Whether practice will perform procedures"),
};

// ── NEXUS Agent Schemas ───────────────────────────────────────────────────────

export const nexusSystemDirectorySchema = {
  state: z.string().describe("Two-letter state code"),
  city: z.string().optional().describe("City name"),
  county: z.string().optional().describe("County name"),
  resource_type: z.enum(["hospital", "specialist", "lab", "imaging", "pharmacy", "all"]).default("all"),
  specialty: z.string().optional().describe("Specific specialty to search"),
  radius_miles: z.number().default(50).describe("Search radius in miles"),
};

export const nexusReferralNetworkSchema = {
  practice_id: z.string().describe("Practice ID"),
  action: z.enum(["list", "add", "remove", "search"]).describe("Action to perform"),
  provider_name: z.string().optional().describe("Provider name"),
  provider_npi: z.string().optional().describe("Provider NPI"),
  specialty: z.string().optional().describe("Specialty"),
  organization: z.string().optional().describe("Organization name"),
  phone: z.string().optional().describe("Phone number"),
  fax: z.string().optional().describe("Fax number"),
  fhir_endpoint: z.string().optional().describe("FHIR endpoint URL"),
};

export const nexusTelehealthSetupSchema = {
  practice_id: z.string().describe("Practice ID"),
  state: z.string().describe("State of practice"),
  platform_preference: z.string().optional().describe("Preferred telehealth platform"),
  specialties: z.array(z.string()).optional().describe("Specialties offering telehealth"),
};

export const nexusCommunityHealthDataSchema = {
  state: z.string().describe("Two-letter state code"),
  county: z.string().optional().describe("County name"),
  city: z.string().optional().describe("City name"),
  health_topics: z.array(z.string()).optional().describe("Specific health topics of interest"),
};

export const nexusProviderDirectorySchema = {
  practice_id: z.string().describe("Practice ID"),
  action: z.enum(["check", "update", "list_directories"]).describe("Action to perform"),
  directory_name: z.string().optional().describe("Specific directory to manage"),
};

export const nexusPatientPortalSetupSchema = {
  practice_id: z.string().describe("Practice ID"),
  features: z.array(z.string()).optional().describe("Desired portal features"),
  ehr_integration: z.string().optional().describe("EHR system for integration"),
};

export const nexusEmergencyProtocolSchema = {
  practice_id: z.string().describe("Practice ID"),
  state: z.string().describe("State of practice"),
  nearest_er: z.string().optional().describe("Nearest ER facility name"),
  practice_type: z.string().optional().describe("Practice type/specialty"),
};
