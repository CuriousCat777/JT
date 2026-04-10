/**
 * NEXUS — Community & Network Agent
 * Manages the hub-and-spoke relationship between the independent practice
 * and larger health systems, plus community outreach.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

export function registerNexusTools(server: McpServer): void {
  server.tool(
    "nexus_system_directory",
    "Find nearby health systems, specialists, labs, and pharmacies for referral and coordination.",
    {
      location: z.string().describe("City, State or ZIP code"),
      radius_miles: z.number().default(50).describe("Search radius in miles"),
      provider_type: z.enum(["hospital", "specialist", "lab", "imaging", "pharmacy", "all"]).default("all"),
    },
    async (params) => {
      const isElyMN = params.location.toLowerCase().includes("ely") && params.location.toLowerCase().includes("mn");
      const isNortheastMN = isElyMN || params.location.toLowerCase().includes("duluth") || params.location.includes("55731");

      const result: Record<string, unknown> = {
        search: { location: params.location, radius: `${params.radius_miles} miles`, type: params.provider_type },
      };

      if (isNortheastMN) {
        result.results = {
          hospitals: [
            { name: "Ely-Bloomenson Community Hospital", location: "Ely, MN", distance: "0 mi", type: "Critical Access Hospital (25 beds)", services: ["Emergency", "Inpatient", "Lab", "Radiology", "Rehab"], phone: "218-365-3271" },
            { name: "Essentia Health — Virginia", location: "Virginia, MN", distance: "~60 mi", type: "Community Hospital", services: ["Emergency", "Surgery", "OB", "Imaging", "Lab"], system: "Essentia Health" },
            { name: "Essentia Health — St. Mary's Medical Center", location: "Duluth, MN", distance: "~100 mi", type: "Level II Trauma Center (380 beds)", services: ["Full specialty services", "Trauma", "NICU", "Cardiac", "Oncology", "Neurosurgery"], system: "Essentia Health", fhir: "Epic FHIR R4" },
            { name: "St. Luke's Hospital", location: "Duluth, MN", distance: "~100 mi", type: "Level II Trauma Center", services: ["Full specialty services", "Trauma", "Heart Center"], system: "St. Luke's" },
          ],
          labs: [
            { name: "Ely-Bloomenson Lab", distance: "0 mi", services: ["Routine labs", "Point-of-care"] },
            { name: "Essentia Health Lab — Duluth", distance: "~100 mi", services: ["Reference lab", "Pathology", "Specialty testing"] },
            { name: "Quest Diagnostics", services: ["Send-out/reference testing"], note: "Nearest draw station likely Virginia or Duluth" },
          ],
          pharmacies: [
            { name: "Ely Pharmacy / Local pharmacy", location: "Ely, MN", note: "Small town pharmacy — verify e-prescribing capability" },
            { name: "Chain pharmacies", location: "Virginia/Duluth, MN", note: "Walgreens, CVS available in larger towns" },
          ],
          specialists_nearby: [
            { specialty: "Cardiology", nearest: "Essentia Health — Duluth (~100 mi)" },
            { specialty: "Orthopedics", nearest: "Essentia Health — Virginia/Duluth" },
            { specialty: "Gastroenterology", nearest: "Essentia Health — Duluth" },
            { specialty: "Mental Health", nearest: "Limited local options; telehealth recommended" },
            { specialty: "Dermatology", nearest: "Duluth; consider teledermatology" },
          ],
        };
        result.rural_considerations = [
          "Limited specialty access — telehealth and periodic visiting specialists are key",
          "Transfer agreements with Essentia Health critical for emergencies",
          "EMS response times can be 20+ minutes for advanced life support",
          "Consider joining Essentia Health's referral network for seamless patient transfers",
        ];
      } else {
        result.results = {
          note: "For real-time provider directory search, use:",
          resources: [
            "CMS Provider Directory: https://www.medicare.gov/care-compare/",
            "NPPES Registry: https://npiregistry.cms.hhs.gov/",
            "HRSA Find a Health Center: https://findahealthcenter.hrsa.gov/",
          ],
        };
      }

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "nexus_referral_network",
    "Build and manage your referral network of specialists and facilities.",
    {
      practice_id: z.string().describe("Practice UUID"),
      action: z.enum(["add", "remove", "list", "search"]),
      provider_info: z.object({
        name: z.string().optional(),
        npi: z.string().optional(),
        specialty: z.string().optional(),
        organization: z.string().optional(),
        phone: z.string().optional(),
        fax: z.string().optional(),
      }).optional(),
    },
    async (params) => {
      const result: Record<string, unknown> = { action: params.action, practice_id: params.practice_id };

      if (params.action === "add" && params.provider_info) {
        result.added = { id: crypto.randomUUID(), ...params.provider_info, added_at: new Date().toISOString() };
      } else if (params.action === "list") {
        result.note = "Referral network listing requires database query. This returns the recommended specialties for a primary care referral network.";
        result.recommended_network = [
          "Cardiology", "Dermatology", "Endocrinology", "Gastroenterology",
          "General Surgery", "Neurology", "OB/GYN", "Ophthalmology",
          "Orthopedics", "Otolaryngology (ENT)", "Pain Management",
          "Psychiatry/Psychology", "Pulmonology", "Rheumatology", "Urology",
        ];
      } else if (params.action === "search") {
        result.search_resources = [
          "Use credence_npi_lookup to find specialists by NPI",
          "CMS Care Compare: https://www.medicare.gov/care-compare/",
          "State medical society directories",
        ];
      }

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "nexus_telehealth_setup",
    "Configure telehealth capabilities for the practice.",
    {
      state: z.string().describe("Two-letter state code"),
      specialties: z.array(z.string()).describe("Practice specialties"),
      patient_volume_estimate: z.number().describe("Monthly patient volume estimate"),
    },
    async (params) => {
      const stateCode = params.state.toUpperCase();
      const result = {
        state: stateCode,
        platform_recommendations: [
          { name: "Doxy.me", cost: "Free (basic) / $35-$50/mo (pro)", hipaa: true, features: ["No download required", "Virtual waiting room", "Screen share"], best_for: "Solo/small practices starting telehealth" },
          { name: "Zoom for Healthcare", cost: "$200/mo/host", hipaa: true, features: ["BAA available", "Waiting room", "Recording", "Integration APIs"], best_for: "Practices wanting robust video with EHR integration" },
          { name: "EHR-integrated", cost: "Included with EHR subscription", hipaa: true, features: ["Seamless charting", "Scheduling integration", "Patient portal"], best_for: "Practices already using an EHR with built-in telehealth" },
        ],
        billing_codes: {
          synchronous_video: ["99201-99215 (E&M with modifier -95 or Place of Service 02)", "GT modifier for telehealth (Medicare)"],
          telephone_only: ["99441 (5-10 min)", "99442 (11-20 min)", "99443 (21-30 min)"],
          e_visits: ["99421 (5-10 min cumulative)", "99422 (11-20 min)", "99423 (21+ min)"],
          remote_monitoring: ["99453 (device setup)", "99454 (device supply, 30 days)", "99457 (first 20 min clinical staff time)", "99458 (additional 20 min)"],
        },
        state_requirements: {
          mn: stateCode === "MN" ? {
            imlc_member: true,
            audio_only: "Allowed for established patients",
            prescribing: "Allowed via telehealth with established relationship",
            parity_law: "Minnesota requires commercial payers to reimburse telehealth at same rate as in-person",
          } : undefined,
        },
        technical_requirements: [
          "Broadband internet (minimum 10 Mbps down / 5 Mbps up; recommend 25/10)",
          "HIPAA-compliant platform with BAA",
          "Webcam (1080p recommended)",
          "Professional lighting and background",
          "Headset with microphone for audio quality",
          "Backup plan (phone number) if video fails",
        ],
        rural_telehealth: {
          note: "Telehealth is especially valuable for rural practices like Ely, MN",
          benefits: [
            "Reduce patient travel for follow-ups",
            "Access to specialist teleconsultation",
            "After-hours urgent care triage",
            "Mental health services (often limited locally)",
            "Chronic disease monitoring",
          ],
        },
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "nexus_community_health_data",
    "Pull community health needs assessment data for practice planning.",
    {
      location: z.string().describe("City, State or County, State or ZIP"),
    },
    async (params) => {
      const isEly = params.location.toLowerCase().includes("ely") || params.location.toLowerCase().includes("st. louis county");

      const result: Record<string, unknown> = { location: params.location };

      if (isEly) {
        result.community_profile = {
          area: "Ely, MN / St. Louis County",
          population: "~3,400 (city); ~200,000 (county)",
          demographics: {
            median_age: "50+ years (aging population)",
            percent_over_65: "~22% (above national average of 17%)",
            percent_uninsured: "~5% (MN has high insurance coverage)",
          },
          health_indicators: {
            top_causes_of_death: ["Heart disease", "Cancer", "Chronic lower respiratory disease", "Unintentional injuries", "Alzheimer's"],
            health_disparities: ["Mental health access limited", "Substance use disorders (especially alcohol)", "Distance to specialty care", "Aging population with multiple chronic conditions"],
            hpsa_designation: {
              status: "Check HRSA HPSA finder at https://data.hrsa.gov/tools/shortage-area",
              likely_designation: "Parts of St. Louis County are designated HPSA for primary care and mental health",
              benefits: "NHSC loan repayment, enhanced Medicare reimbursement, recruitment incentives",
            },
          },
          provider_ratio: {
            primary_care: "Below recommended ratio (target: 1:1500)",
            mental_health: "Significant shortage",
            specialists: "Must travel 60-100+ miles for most specialties",
          },
          opportunities: [
            "Strong need for primary care — limited local providers",
            "Behavioral health services severely underserved",
            "Chronic disease management (diabetes, heart disease, COPD)",
            "Geriatric care for aging population",
            "Sports medicine / outdoor recreation injuries (BWCA tourism)",
            "Telehealth expansion to reduce travel burden",
          ],
        };
      } else {
        result.data_sources = [
          "County Health Rankings: https://www.countyhealthrankings.org/",
          "HRSA Health Center Data: https://data.hrsa.gov/",
          "CDC PLACES: https://www.cdc.gov/places/",
          "Census Bureau: https://data.census.gov/",
        ];
      }

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "nexus_provider_directory_listing",
    "Manage practice listings in provider directories.",
    {
      physician_name: z.string().describe("Physician name"),
      npi: z.string().describe("NPI number"),
      practice_name: z.string().describe("Practice name"),
      specialties: z.array(z.string()).describe("Specialties"),
      address: z.string().describe("Practice address"),
      phone: z.string().describe("Practice phone"),
      accepting_new_patients: z.boolean().default(true),
      insurance_accepted: z.array(z.string()).optional().describe("Insurance plans accepted"),
    },
    async (params) => {
      const result = {
        provider: params.physician_name,
        directories_to_update: [
          { name: "NPPES/NPI Registry", url: "https://nppes.cms.hhs.gov/", priority: "CRITICAL", action: "Update practice address and phone in NPPES" },
          { name: "CAQH ProView", url: "https://proview.caqh.org/", priority: "CRITICAL", action: "Update profile; health plans pull from CAQH" },
          { name: "Google Business Profile", url: "https://business.google.com/", priority: "HIGH", action: "Create/claim listing. Add photos, hours, services." },
          { name: "Insurance Company Directories", priority: "HIGH", action: "Each payer you're credentialed with has a provider directory. Verify your listing." },
          { name: "Healthgrades", url: "https://www.healthgrades.com/", priority: "MEDIUM", action: "Claim free profile" },
          { name: "Vitals.com", url: "https://www.vitals.com/", priority: "MEDIUM", action: "Claim free profile" },
          { name: "WebMD", url: "https://doctor.webmd.com/", priority: "MEDIUM", action: "Claim free profile" },
          { name: "Zocdoc", url: "https://www.zocdoc.com/", priority: "MEDIUM", action: "Paid listing with online scheduling (if desired)" },
          { name: "State Medical Society", priority: "MEDIUM", action: "Join and list in physician finder" },
          { name: "Local Chamber of Commerce", priority: "LOW", action: "Join for community visibility" },
          { name: "Yelp", url: "https://biz.yelp.com/", priority: "LOW", action: "Claim listing; respond to reviews" },
        ],
        listing_consistency: "Ensure NAP (Name, Address, Phone) is identical across ALL directories. Inconsistencies hurt search rankings.",
        online_presence_checklist: [
          "Professional website with services, insurance accepted, and online scheduling",
          "Google Business Profile with photos and accurate hours",
          "Consistent NAP across all directories",
          "Patient reviews strategy (ask satisfied patients; respond to all reviews)",
          "Social media presence (Facebook at minimum for local community)",
        ],
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "nexus_patient_portal_setup",
    "Configure a patient-facing portal for your practice.",
    {
      practice_name: z.string().describe("Practice name"),
      ehr_system: z.string().describe("EHR system name"),
      features: z.array(z.string()).describe("Desired features"),
    },
    async (params) => {
      const result = {
        practice: params.practice_name,
        ehr: params.ehr_system,
        portal_requirements: {
          onc_certification: "21st Century Cures Act requires patient access to their health data via APIs",
          information_blocking: "Cannot block patient access to their data (8 limited exceptions)",
          patient_api: "Must provide FHIR R4 API access for patient-facing apps",
        },
        recommended_features: {
          core: ["Secure messaging with provider", "View test results", "Request prescription refills", "View visit summaries"],
          scheduling: ["Online appointment booking", "Appointment reminders (email/text)", "Cancellation/rescheduling"],
          billing: ["View statements online", "Online bill pay", "Insurance information update"],
          forms: ["New patient intake forms", "Health history questionnaire", "Consent forms (e-signature)"],
          telehealth: ["Video visit integration", "Pre-visit questionnaire"],
        },
        hipaa_requirements: [
          "Secure authentication (MFA recommended)",
          "Encrypted data transmission (TLS 1.2+)",
          "Audit logging of all patient data access",
          "Automatic session timeout",
          "BAA with portal vendor",
        ],
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "nexus_emergency_protocol",
    "Generate emergency protocols for the practice.",
    {
      practice_location: z.string().describe("City, State"),
      nearest_hospital: z.string().describe("Nearest hospital name"),
      practice_capabilities: z.array(z.string()).optional().describe("Practice emergency capabilities"),
    },
    async (params) => {
      const isEly = params.practice_location.toLowerCase().includes("ely");

      const result = {
        practice: params.practice_location,
        nearest_hospital: params.nearest_hospital,
        emergency_protocols: {
          when_to_call_911: [
            "Chest pain with cardiac features", "Stroke symptoms (FAST)", "Anaphylaxis not responding to epinephrine",
            "Active seizure > 5 minutes", "Severe trauma", "Respiratory failure", "Cardiac arrest",
            "Acute abdomen with hemodynamic instability", "Active hemorrhage",
          ],
          office_emergency_equipment: [
            "AED (Automated External Defibrillator)",
            "Epinephrine auto-injectors (1:1,000)",
            "Oral airways and bag-valve mask",
            "Oxygen supply with nasal cannula and mask",
            "Pulse oximeter",
            "Blood glucose meter",
            "IV supplies and normal saline",
            "Aspirin (chewable 325mg)",
            "Nitroglycerin sublingual",
            "Albuterol nebulizer",
            "Diphenhydramine injectable",
            "Glucagon kit",
          ],
          staff_requirements: [
            "All clinical staff: current BLS certification",
            "Physicians: ACLS certification recommended",
            "Regular emergency drills (quarterly recommended)",
            "Posted emergency procedures at each workstation",
          ],
        },
        transfer_agreements: {
          required: true,
          description: "Formal agreements with nearby hospitals for patient transfers",
          elements: ["Contact procedures and phone numbers", "Patient information transfer protocols", "Transportation arrangements", "Follow-up communication"],
        },
        rural_specific: isEly ? {
          ems_response: "Advanced Life Support (ALS) may take 20+ minutes to reach Ely",
          implications: [
            "Office must be prepared to stabilize patients for extended periods",
            "Consider stocking more emergency medications than urban practices",
            "Helicopter EMS (HEMS) may be needed for critical transfers to Duluth",
            "Weather (winter) can delay ground and air transport",
          ],
          transfer_options: [
            { destination: "Ely-Bloomenson Community Hospital", distance: "In town", level: "Critical Access — stabilization and basic emergencies" },
            { destination: "Essentia Health — Virginia", distance: "~60 mi", level: "Community hospital — surgery, OB" },
            { destination: "Essentia Health — Duluth", distance: "~100 mi", level: "Level II Trauma — full specialty services" },
          ],
          air_medical: "Life Link III or North Memorial Air Care — helicopter transport to Duluth for critical patients",
        } : undefined,
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );
}
