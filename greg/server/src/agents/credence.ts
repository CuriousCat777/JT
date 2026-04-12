/**
 * CREDENCE — Credentialing & Licensing Agent
 * Handles physician identity verification, NPI registration, DEA licensing,
 * and state medical board credentialing.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { searchNPI, validateNPI } from "../lib/apis/nppes.js";

const STATE_BOARDS: Record<string, {
  name: string;
  website: string;
  applicationUrl: string;
  fees: string;
  processingTime: string;
  cmeRequirements: string;
  examsAccepted: string[];
  supervisedPractice: string;
  telemedicineRules: string;
}> = {
  MN: {
    name: "Minnesota Board of Medical Practice",
    website: "https://mn.gov/boards/medical-practice/",
    applicationUrl: "https://mn.gov/boards/medical-practice/applicants/",
    fees: "Initial license: $368; Renewal (biennial): $368",
    processingTime: "4-8 weeks for complete applications",
    cmeRequirements: "75 CME credits per triennial period; must include 2 credits in opioid prescribing",
    examsAccepted: ["USMLE Step 1, 2, 3", "COMLEX Level 1, 2-CE, 3"],
    supervisedPractice: "No mandatory supervised practice for fully licensed physicians",
    telemedicineRules: "Interstate Medical Licensure Compact member; telemedicine practice requires MN license; audio-only allowed for established patients",
  },
  CA: {
    name: "Medical Board of California",
    website: "https://www.mbc.ca.gov/",
    applicationUrl: "https://www.mbc.ca.gov/licensing/physicians-and-surgeons/",
    fees: "Initial license: $783; Renewal (biennial): $783",
    processingTime: "60-90 days; can take 6+ months with background check delays",
    cmeRequirements: "50 CME credits per biennial renewal; must include 12 hours AMA Category 1",
    examsAccepted: ["USMLE Step 1, 2 CK, 3", "COMLEX Level 1, 2-CE, 3 (with additional evaluation)"],
    supervisedPractice: "36 months ACGME/AOA accredited residency required",
    telemedicineRules: "Must hold CA license; Business & Professions Code 2290.5; informed consent required; not part of IMLC",
  },
  TX: {
    name: "Texas Medical Board",
    website: "https://www.tmb.state.tx.us/",
    applicationUrl: "https://www.tmb.state.tx.us/page/licensing",
    fees: "Initial license: $1,020; Renewal (biennial): $654 (even birth years) or $754 (odd birth years)",
    processingTime: "90-120 days average",
    cmeRequirements: "48 CME hours per biennial period; 24 must be in formal courses; 2 hours medical ethics required",
    examsAccepted: ["USMLE Step 1, 2, 3", "COMLEX Level 1, 2-CE, 3"],
    supervisedPractice: "1 year of approved postgraduate training minimum for limited license",
    telemedicineRules: "Must establish physician-patient relationship; SB 1107 requires in-state license; no IMLC membership",
  },
  NY: {
    name: "New York State Education Department — Office of the Professions",
    website: "http://www.op.nysed.gov/prof/med/",
    applicationUrl: "http://www.op.nysed.gov/prof/med/medlic.htm",
    fees: "Initial registration: $735; Triennial renewal: $600",
    processingTime: "8-12 weeks after complete application",
    cmeRequirements: "No mandatory CME for re-registration (but hospitals may require); 2 hours infection control, 3 hours pain/palliative care required on initial registration",
    examsAccepted: ["USMLE Step 1, 2 CK, 2 CS (or pathway), 3"],
    supervisedPractice: "3 years approved residency",
    telemedicineRules: "Must hold NY license; informed consent required; prescribing via telehealth allowed with established relationship; not IMLC member",
  },
  FL: {
    name: "Florida Board of Medicine",
    website: "https://flboardofmedicine.gov/",
    applicationUrl: "https://flboardofmedicine.gov/licensing/",
    fees: "Initial license: $575; Biennial renewal: $479.50",
    processingTime: "60-90 days",
    cmeRequirements: "40 CME hours per biennium; includes 2 hours medical errors, 2 hours controlled substances, 2 hours human trafficking, 1 hour HIV/AIDS",
    examsAccepted: ["USMLE Step 1, 2, 3", "COMLEX Level 1, 2-CE, 3"],
    supervisedPractice: "1 year postgraduate training for restricted license; 2 years for full",
    telemedicineRules: "Must hold FL license; standard of care applies; telehealth registration required; IMLC member state",
  },
};

export function registerCredenceTools(server: McpServer): void {
  server.tool(
    "credence_npi_lookup",
    "Search and validate NPI numbers via the NPPES registry. Can search by NPI number, name, state, or taxonomy/specialty.",
    {
      npi: z.string().optional().describe("10-digit NPI number"),
      first_name: z.string().optional().describe("Provider first name"),
      last_name: z.string().optional().describe("Provider last name"),
      state: z.string().optional().describe("Two-letter state code (e.g., MN)"),
      taxonomy: z.string().optional().describe("Taxonomy/specialty description"),
    },
    async (params) => {
      const results: Record<string, unknown> = {};

      if (params.npi) {
        results.npi_validation = {
          npi: params.npi,
          valid_format: validateNPI(params.npi),
          check_digit_algorithm: "Luhn mod-10 variant (ISO/IEC 7812)",
        };
      }

      try {
        const npiResults = await searchNPI({
          number: params.npi,
          first_name: params.first_name,
          last_name: params.last_name,
          state: params.state,
          taxonomy_description: params.taxonomy,
        });
        results.nppes_results = npiResults;
      } catch (error) {
        results.nppes_results = {
          error: "Failed to query NPPES API",
          message: error instanceof Error ? error.message : "Unknown error",
          fallback: "Visit https://npiregistry.cms.hhs.gov/ for manual lookup",
        };
      }

      results.notes = {
        api: "NPPES NPI Registry (free, no authentication required)",
        endpoint: "https://npiregistry.cms.hhs.gov/api/?version=2.1",
        npi_types: { "NPI-1": "Individual provider", "NPI-2": "Organization" },
      };

      return { content: [{ type: "text", text: JSON.stringify(results, null, 2) }] };
    },
  );

  server.tool(
    "credence_npi_register",
    "Guide through the NPI application process. Returns step-by-step instructions for obtaining a National Provider Identifier.",
    {
      first_name: z.string().describe("Physician first name"),
      last_name: z.string().describe("Physician last name"),
      entity_type: z.enum(["individual", "organization"]).default("individual").describe("NPI-1 (individual) or NPI-2 (organization)"),
      state: z.string().describe("State of primary practice location"),
      specialty: z.string().describe("Primary medical specialty"),
    },
    async (params) => {
      const result = {
        physician: `${params.first_name} ${params.last_name}`,
        npi_type: params.entity_type === "individual" ? "NPI-1 (Individual)" : "NPI-2 (Organization)",
        application_steps: [
          {
            step: 1,
            title: "Gather Required Information",
            details: [
              "Social Security Number (for NPI-1)",
              "State medical license number and state",
              `Primary practice address in ${params.state}`,
              `Taxonomy code for ${params.specialty}`,
              "Authorized official information (for NPI-2)",
              "Date of birth and graduation date",
            ],
          },
          {
            step: 2,
            title: "Access NPPES Online Application",
            details: [
              "Visit https://nppes.cms.hhs.gov/",
              "Create an Identity & Access (I&A) account if you don't have one",
              "You'll need your NPPES User ID and password",
              "The I&A system uses multi-factor authentication",
            ],
          },
          {
            step: 3,
            title: "Complete the Application",
            details: [
              `Select Entity Type: ${params.entity_type === "individual" ? "Type 1 (Individual)" : "Type 2 (Organization)"}`,
              "Enter personal/organizational information",
              `Add primary taxonomy: Search for '${params.specialty}'`,
              `Add practice location in ${params.state}`,
              "Provide mailing address",
              "Submit the application electronically",
            ],
          },
          {
            step: 4,
            title: "Alternative: Paper Application (CMS-10114)",
            details: [
              "Download form from https://www.cms.gov/Medicare/CMS-Forms/CMS-Forms",
              "Mail to: NPI Enumerator, P.O. Box 6059, Fargo, ND 58108-6059",
              "Paper processing takes 20+ business days",
            ],
          },
        ],
        timeline: {
          online: "7-10 business days for NPI assignment",
          paper: "20+ business days",
          expedited: "Not available — all applications processed in order received",
        },
        cost: "Free — there is no charge for NPI application",
        after_receiving_npi: [
          "Update NPI on all claim forms and billing systems",
          "Register with state Medicaid program",
          "Enroll in Medicare via PECOS (if accepting Medicare)",
          "Update CAQH ProView profile",
          "Notify all insurance payers",
        ],
        important_notes: [
          "NPI is a lifetime identifier — it does not expire",
          "You must update NPPES within 30 days of any changes",
          "Individual providers get NPI-1; practices get NPI-2",
          "One physician can have only one NPI-1",
        ],
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "credence_dea_status",
    "Check DEA registration status and provide guidance on DEA registration for controlled substance prescribing.",
    {
      dea_number: z.string().optional().describe("DEA registration number"),
      physician_name: z.string().optional().describe("Physician full name"),
      state: z.string().optional().describe("State to check DEA registration"),
    },
    async (params) => {
      const result: Record<string, unknown> = {
        lookup_info: {
          note: "DEA registration status is not available via free public API",
          verification_portal: "https://apps.deadiversion.usdoj.gov/webforms2/spring/validationLogin",
          ntis_database: "DEA maintains the Automation of Reports and Consolidated Orders System (ARCOS)",
        },
      };

      if (params.dea_number) {
        const deaPattern = /^[A-Z][A-Z9]\d{7}$/;
        result.dea_validation = {
          number: params.dea_number,
          format_valid: deaPattern.test(params.dea_number),
          format_description: "DEA numbers: 2 letters + 7 digits. First letter indicates registrant type (A/B=Dispensers, M=Mid-level)",
        };
      }

      result.registration_guide = {
        form: "DEA Form 224 — New Registration for Retail Pharmacy, Hospital/Clinic, Practitioner, Teaching Institution",
        apply_online: "https://apps.deadiversion.usdoj.gov/webforms2/spring/main?execution=e1s1",
        fee: "$888 for 3-year registration (as of 2024)",
        processing_time: "4-6 weeks",
        schedules: {
          II: "High abuse potential, accepted medical use (oxycodone, fentanyl, methylphenidate)",
          III: "Moderate abuse potential (testosterone, buprenorphine, ketamine)",
          IV: "Lower abuse potential (benzodiazepines, zolpidem, tramadol)",
          V: "Lowest abuse potential (cough preparations with codeine, pregabalin)",
        },
        requirements: [
          "Active state medical license in the state of practice",
          "State controlled substance registration (if required by state)",
          "Physical practice address (P.O. Box not accepted)",
          "Background check by DEA",
        ],
        state_specific: params.state ? {
          state: params.state,
          note: `Check ${params.state} Board of Pharmacy for state-level controlled substance registration requirements`,
          pmp_required: "Most states require registration with Prescription Monitoring Program (PMP)",
          mn_specifics: params.state === "MN" ? {
            state_registration: "Minnesota Board of Pharmacy CSR required",
            pmp: "MN PMP (Minnesota Prescription Monitoring Program) — mandatory check before prescribing Schedule II-IV",
            epcs: "Electronic Prescribing for Controlled Substances (EPCS) — required in MN since January 2021",
          } : undefined,
        } : undefined,
        renewal: {
          frequency: "Every 3 years",
          reminder: "DEA sends renewal notice 60 days before expiration",
          online_renewal: "https://apps.deadiversion.usdoj.gov/webforms2/spring/main",
        },
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "credence_state_license_check",
    "Verify state medical license status and retrieve state-specific licensing requirements.",
    {
      state: z.string().describe("Two-letter state code"),
      license_number: z.string().optional().describe("Medical license number"),
      physician_name: z.string().optional().describe("Physician full name"),
    },
    async (params) => {
      const stateCode = params.state.toUpperCase();
      const board = STATE_BOARDS[stateCode];

      const result: Record<string, unknown> = {
        state: stateCode,
        board_info: board ?? {
          note: `Detailed data for ${stateCode} not in embedded database. Check FSMB (Federation of State Medical Boards) at https://www.fsmb.org/`,
          fsmb_portal: "https://www.fsmb.org/licensure/state-medical-boards/",
        },
      };

      if (params.license_number) {
        result.verification = {
          license_number: params.license_number,
          note: "Real-time license verification requires direct query to state medical board database",
          verification_url: board?.website ?? "Check FSMB DocInfo: https://www.fsmb.org/docinfo/",
        };
      }

      result.general_requirements = {
        education: "MD or DO from LCME/COCA-accredited medical school (or equivalent with ECFMG certification for IMGs)",
        residency: "Completion of ACGME or AOA-accredited residency program",
        examinations: "USMLE Steps 1, 2, and 3 (or COMLEX equivalents)",
        background_check: "Criminal background check via FBI fingerprint submission",
        application_components: [
          "Completed application form",
          "Medical school transcripts",
          "Residency completion verification",
          "ECFMG certificate (if IMG)",
          "Exam score reports",
          "Malpractice history disclosure",
          "State and federal background checks",
          "Passport-style photographs",
          "Application fee",
        ],
      };

      result.multistate_options = {
        imlc: {
          name: "Interstate Medical Licensure Compact",
          member_states: "40+ states and territories",
          url: "https://www.imlcc.org/",
          mn_member: stateCode === "MN" ? true : undefined,
          benefits: "Expedited licensure in multiple states through single application",
          eligibility: "Must have primary state of medical licensure as Compact member",
        },
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "credence_board_requirements",
    "Retrieve detailed state medical board requirements for physician licensure.",
    {
      state: z.string().describe("Two-letter state code"),
    },
    async (params) => {
      const stateCode = params.state.toUpperCase();
      const board = STATE_BOARDS[stateCode];

      if (!board) {
        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              state: stateCode,
              error: `Detailed board requirements for ${stateCode} not in embedded database`,
              recommendation: "Check FSMB at https://www.fsmb.org/licensure/state-medical-boards/",
              general_steps: [
                "1. Verify medical education credentials",
                "2. Pass required examinations (USMLE/COMLEX)",
                "3. Complete postgraduate training",
                "4. Submit application to state board",
                "5. Pass background check",
                "6. Receive license and register with DEA if needed",
              ],
            }, null, 2),
          }],
        };
      }

      const result = {
        state: stateCode,
        board_name: board.name,
        website: board.website,
        application_url: board.applicationUrl,
        licensing_requirements: {
          exams_accepted: board.examsAccepted,
          fees: board.fees,
          processing_time: board.processingTime,
          cme_requirements: board.cmeRequirements,
          supervised_practice: board.supervisedPractice,
          telemedicine_rules: board.telemedicineRules,
        },
        application_checklist: [
          "Completed application form",
          "Application fee payment",
          "Medical school diploma and transcripts (verified through primary source)",
          "ECFMG certificate (International Medical Graduates only)",
          "Examination score reports (USMLE or COMLEX)",
          "Postgraduate training verification (ACGME/AOA)",
          "Letters of recommendation (typically 3)",
          "Malpractice claims history (from NPDB self-query)",
          "Criminal background check (state + FBI fingerprints)",
          "Passport-style photographs",
          "Copy of birth certificate or passport",
          "Current CV/resume",
          "DEA registration (if applicable)",
          "CAQH ProView profile",
        ],
        renewal_info: {
          frequency: stateCode === "NY" ? "Triennial" : "Biennial",
          cme_required: board.cmeRequirements,
          online_renewal: `Available through ${board.website}`,
        },
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "credence_caqh_status",
    "Check CAQH ProView credentialing status and provide registration guidance.",
    {
      caqh_id: z.string().optional().describe("CAQH provider ID"),
      physician_name: z.string().optional().describe("Physician full name"),
    },
    async (params) => {
      const result = {
        caqh_proview: {
          description: "CAQH ProView is a universal provider credentialing database used by most health plans",
          website: "https://proview.caqh.org/",
          cost: "Free for providers (health plans pay for access)",
        },
        registration_steps: [
          {
            step: 1,
            title: "Obtain CAQH ID",
            details: "Contact a participating health plan or visit CAQH website. Many plans will assign a CAQH ID when you join their network.",
          },
          {
            step: 2,
            title: "Complete ProView Profile",
            details: "Enter comprehensive practice and personal information including education, training, work history, malpractice, and licenses.",
          },
          {
            step: 3,
            title: "Upload Supporting Documents",
            details: "Upload copies of: medical license, DEA certificate, malpractice insurance face sheet, board certificates, CV, W-9.",
          },
          {
            step: 4,
            title: "Authorize Health Plans",
            details: "Select which health plans can access your data for credentialing purposes.",
          },
          {
            step: 5,
            title: "Attest and Submit",
            details: "Review all information for accuracy and submit electronic attestation.",
          },
        ],
        re_attestation: {
          frequency: "Every 120 days (quarterly)",
          process: "Review and confirm all data is current, update any changes",
          consequence_of_missing: "Profile becomes inactive; health plans cannot use it for credentialing",
          tip: "Set calendar reminders for 110 days to allow time for updates",
        },
        required_documents: [
          "Current state medical license(s)",
          "DEA registration certificate",
          "Board certification(s)",
          "Professional liability insurance face sheet",
          "Hospital privilege letters",
          "Current CV/resume",
          "Government-issued photo ID",
          "W-9 form",
          "Disclosure questions (malpractice, sanctions, criminal history)",
        ],
        participating_plans: {
          note: "900+ health plans and organizations use CAQH ProView",
          examples: [
            "UnitedHealthcare",
            "Aetna",
            "Cigna",
            "Blue Cross Blue Shield plans",
            "Humana",
            "Medicare Advantage plans",
          ],
        },
        lookup: params.caqh_id ? {
          caqh_id: params.caqh_id,
          note: "Direct status check requires CAQH API credentials (health plan access only). Log into ProView to check your own status.",
        } : undefined,
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "credence_hospital_privileges",
    "Track and guide hospital privilege applications, including typical timelines and required documentation.",
    {
      hospital_name: z.string().describe("Name of the hospital"),
      physician_name: z.string().describe("Physician full name"),
      specialty: z.string().describe("Medical specialty"),
      state: z.string().describe("Two-letter state code"),
    },
    async (params) => {
      const stateCode = params.state.toUpperCase();
      const isMinnesota = stateCode === "MN";

      const result = {
        application: {
          hospital: params.hospital_name,
          physician: params.physician_name,
          specialty: params.specialty,
          state: stateCode,
        },
        typical_timeline: {
          initial_application: "2-4 weeks to gather and submit",
          primary_source_verification: "30-60 days",
          credentials_committee_review: "30-45 days",
          medical_executive_committee: "14-30 days",
          board_approval: "14-30 days",
          total_estimated: "90-180 days from submission to privileges granted",
          provisional_period: "Typically 12-24 months of proctored cases",
        },
        required_documents: [
          "Completed privilege application form",
          "Current CV/resume",
          "Medical school diploma",
          "Residency/fellowship completion letter",
          "Board certification or eligibility letter",
          "Current state medical license",
          "DEA registration",
          "ECFMG certificate (if applicable)",
          "Malpractice insurance certificate (minimum coverage varies by hospital)",
          "Professional references (typically 3-5 from same specialty)",
          "Case logs (for procedural specialties)",
          "Peer recommendations",
          "NPDB self-query results",
          "Immunization records (Hep B, TB, COVID-19, flu)",
          "BLS/ACLS/PALS certification as applicable",
          "Query responses from all previous hospitals",
        ],
        privilege_categories: {
          courtesy: "Occasional admissions (typically < 12/year)",
          active: "Regular admissions with committee obligations",
          consulting: "Consultation only, no direct admissions",
          telemedicine: "Remote consultations via telehealth platform",
        },
        common_challenges: [
          "Delays in primary source verification from training programs",
          "Gaps in employment history requiring explanation letters",
          "Malpractice history disclosure and review",
          "Meeting minimum case volume requirements for procedural privileges",
          "Navigating the OPPE/FPPE proctoring requirements",
        ],
        minnesota_specific: isMinnesota ? {
          regional_hospitals: [
            {
              name: "Ely-Bloomenson Community Hospital",
              location: "Ely, MN",
              type: "Critical Access Hospital (25 beds)",
              system: "Independent (affiliated with Essentia Health network)",
              notes: "Primary hospital serving Ely area; limited specialty services — most complex cases transferred to Duluth",
              contact: "218-365-3271",
            },
            {
              name: "Essentia Health — St. Mary's Medical Center",
              location: "Duluth, MN (~100 miles from Ely)",
              type: "Level II Trauma Center",
              system: "Essentia Health",
              notes: "Regional referral center; full specialty services; FHIR-enabled for data exchange",
              privileges_process: "Apply through Essentia Health Medical Staff Office",
            },
            {
              name: "Essentia Health — Virginia Medical Center",
              location: "Virginia, MN (~60 miles from Ely)",
              type: "Community Hospital",
              system: "Essentia Health",
              notes: "Closer option for intermediate-level care",
            },
          ],
          essentia_health_network: {
            description: "Essentia Health is the primary health system serving northeastern Minnesota",
            headquarters: "Duluth, MN",
            privilege_application: "Centralized credentialing through Essentia Medical Staff Services",
            fhir_capability: "Essentia uses Epic EHR with FHIR R4 APIs available",
          },
        } : undefined,
        reappointment: {
          frequency: "Every 2 years at most hospitals",
          requirements: [
            "Current license and DEA",
            "Updated malpractice insurance",
            "CME credits in specialty area",
            "Ongoing Professional Practice Evaluation (OPPE) review",
            "Minimum case volume requirements (if applicable)",
            "Board certification maintenance",
          ],
        },
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );
}
