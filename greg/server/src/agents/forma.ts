/**
 * FORMA — Business Formation Agent
 * Handles legal entity creation, tax registration, and business structure for medical practices.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

const STATE_FORMATION: Record<string, {
  filingFee: string;
  annualReport: string;
  registeredAgent: string;
  corporatePractice: string;
  formationUrl: string;
  processingTime: string;
}> = {
  MN: {
    filingFee: "LLC: $155 online; PC: $135 online",
    annualReport: "Annual renewal: $0 (no annual report fee for LLCs); PCs: $0 annual report",
    registeredAgent: "Required. Must be MN resident or registered business entity with MN address",
    corporatePractice: "Minnesota allows physician-owned PLLCs and PCs. No corporate practice of medicine prohibition for physician-owned entities.",
    formationUrl: "https://mblsportal.sos.state.mn.us/",
    processingTime: "Online: 1-2 business days; Mail: 5-7 business days",
  },
  CA: {
    filingFee: "PC: $100 Articles of Incorporation; LLC not available for physicians in CA",
    annualReport: "Annual minimum franchise tax: $800; Statement of Information: $25/year",
    registeredAgent: "Required. Must be CA resident or registered agent service",
    corporatePractice: "Strong corporate practice of medicine doctrine. Physicians MUST form a Professional Corporation (PC). PLLCs NOT available for physicians.",
    formationUrl: "https://www.sos.ca.gov/business/be/filing-tips",
    processingTime: "Online: 1-3 business days; Mail: 2-4 weeks",
  },
  TX: {
    filingFee: "PLLC: $300; PA: $300",
    annualReport: "Annual franchise tax report required. No tax due if revenue under $2.47M threshold",
    registeredAgent: "Required. Must be TX resident or registered agent service",
    corporatePractice: "Texas prohibits corporate practice of medicine but allows physician-owned PAs, PLLCs, and PCs",
    formationUrl: "https://www.sos.texas.gov/corp/forms_702.shtml",
    processingTime: "Online: 2-3 business days; Mail: 5-7 business days",
  },
  NY: {
    filingFee: "PLLC: $200; PC: $125; Publication requirement: $500-$2,000+",
    annualReport: "Biennial statement: $9",
    registeredAgent: "Required. Must be NY resident or registered agent. Publication in two newspapers required within 120 days of formation.",
    corporatePractice: "Strong corporate practice doctrine. Must form PC or PLLC. All shareholders/members must be licensed physicians.",
    formationUrl: "https://www.dos.ny.gov/corps/",
    processingTime: "Online: 1-2 business days; Mail: 2-4 weeks; Expedited (24hr): +$75",
  },
  FL: {
    filingFee: "PLLC: $125; PA: $35 + $70 designation",
    annualReport: "Annual report: $138.75 (LLC); $150 (Corporation)",
    registeredAgent: "Required. Must be FL resident or registered agent service",
    corporatePractice: "Florida allows physician-owned PLLCs and PAs. Less restrictive than CA/NY.",
    formationUrl: "https://dos.fl.gov/sunbiz/start-business/",
    processingTime: "Online: 1-2 business days; Mail: 5-10 business days",
  },
};

export function registerFormaTools(server: McpServer): void {
  server.tool(
    "forma_entity_recommend",
    "Recommend the best business entity type for a medical practice based on state, specialty, and situation.",
    {
      state: z.string().describe("Two-letter state code"),
      specialty: z.string().describe("Medical specialty"),
      num_physicians: z.number().default(1).describe("Number of physician owners"),
      revenue_estimate: z.string().optional().describe("Estimated annual revenue"),
      has_partners: z.boolean().default(false).describe("Whether there are non-physician partners"),
    },
    async (params) => {
      const stateCode = params.state.toUpperCase();
      const stateInfo = STATE_FORMATION[stateCode];
      const isSolo = params.num_physicians === 1;

      const entityOptions = [
        {
          type: "PLLC (Professional Limited Liability Company)",
          recommended: stateCode !== "CA",
          pros: [
            "Personal asset protection from malpractice claims against the practice",
            "Pass-through taxation (no double taxation)",
            "Flexible management structure",
            "Less administrative burden than corporation",
            isSolo ? "Simple single-member structure" : "Multi-member operating agreement flexibility",
          ],
          cons: [
            "No protection from YOUR OWN malpractice (only protects from other members' claims)",
            "Self-employment tax on all profits (for single-member)",
            "Some states (CA) don't allow PLLCs for physicians",
            "May need to convert to PC for certain payer contracts",
          ],
          best_for: "Solo practitioners or small groups wanting simplicity + liability protection",
        },
        {
          type: "PC (Professional Corporation)",
          recommended: stateCode === "CA" || params.num_physicians > 2,
          pros: [
            "Required in some states (CA)",
            "Well-understood structure by payers and hospitals",
            "Can elect S-Corp status for tax benefits",
            "Shareholders limited to licensed professionals",
            "Easier to add/remove physician-shareholders",
          ],
          cons: [
            "More administrative requirements (bylaws, minutes, resolutions)",
            "Annual meeting requirements",
            "If C-Corp: double taxation (unless S-Corp election)",
            "More complex formation documents",
          ],
          best_for: "States requiring PC, groups of 3+ physicians, or when planning to grow",
        },
        {
          type: "S-Corp Election (on PLLC or PC)",
          recommended: Boolean(params.revenue_estimate && parseInt(params.revenue_estimate) > 150000),
          pros: [
            "Potential self-employment tax savings (only salary subject to FICA)",
            "Pass-through taxation",
            "Can reduce overall tax burden by splitting income between salary and distributions",
          ],
          cons: [
            "Must pay reasonable salary (IRS scrutiny)",
            "Payroll administration required",
            "100 shareholder maximum",
            "Single class of stock only",
            "Calendar year-end required (usually)",
          ],
          best_for: "Practices with net income over $150K where tax savings from salary/distribution split justify additional payroll costs",
        },
        {
          type: "Sole Proprietorship",
          recommended: false,
          pros: [
            "Simplest to set up — no state filing required",
            "No separate tax return",
            "Complete control",
          ],
          cons: [
            "NO personal liability protection",
            "All personal assets at risk",
            "Harder to get business credit/loans",
            "Looks less professional to payers",
            "Not recommended for medical practices",
          ],
          best_for: "NOT recommended for medical practices due to liability exposure",
        },
      ];

      const result = {
        recommendation: {
          state: stateCode,
          specialty: params.specialty,
          num_physicians: params.num_physicians,
          primary_recommendation: stateCode === "CA" ? "PC with S-Corp election" : "PLLC with S-Corp election (if income > $150K)",
          reasoning: stateCode === "CA"
            ? "California requires Professional Corporations for physicians. PLLCs are not available."
            : `${stateCode} allows PLLCs for physicians, which provides the simplest structure with liability protection. Add S-Corp election when revenue justifies it.`,
        },
        state_rules: stateInfo ?? { note: `Check ${stateCode} Secretary of State for specific rules` },
        entity_options: entityOptions,
        next_steps: [
          "1. Choose entity type based on recommendation above",
          "2. Reserve business name with Secretary of State",
          "3. File formation documents (Articles of Organization/Incorporation)",
          "4. Obtain EIN from IRS (use forma_ein_guide tool)",
          "5. Draft Operating Agreement or Bylaws (use forma_operating_agreement tool)",
          "6. Open business bank account (use forma_bank_account_checklist tool)",
          "7. Obtain required insurance (use forma_insurance_requirements tool)",
          "8. File S-Corp election (Form 2553) within 75 days if applicable",
        ],
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "forma_state_requirements",
    "Retrieve state-specific business formation requirements for medical practices.",
    {
      state: z.string().describe("Two-letter state code"),
    },
    async (params) => {
      const stateCode = params.state.toUpperCase();
      const stateInfo = STATE_FORMATION[stateCode];

      const result = {
        state: stateCode,
        formation_details: stateInfo ?? {
          note: `Detailed formation data for ${stateCode} not in embedded database`,
          recommendation: "Check your state's Secretary of State website",
        },
        universal_requirements: [
          "Articles of Organization (LLC) or Articles of Incorporation (PC/PA)",
          "Registered agent with physical address in the state",
          "Business name that includes required professional designator (PLLC, PC, PA, etc.)",
          "Proof of professional licensure for all physician-members/shareholders",
          "Operating Agreement or Corporate Bylaws",
        ],
        name_requirements: {
          must_include: "Professional designator (PLLC, PC, PA, Ltd., etc.)",
          restrictions: "Cannot be misleading; some states prohibit certain terms",
          name_search: `Search name availability at ${stateInfo?.formationUrl ?? "your state SOS website"}`,
        },
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "forma_ein_guide",
    "Walk through the IRS EIN (Employer Identification Number) application process.",
    {},
    async () => {
      const result = {
        what_is_ein: "A 9-digit number (XX-XXXXXXX) assigned by the IRS to identify your business for tax purposes. Required for business bank accounts, hiring employees, and tax filing.",
        application_methods: {
          online: {
            url: "https://www.irs.gov/businesses/small-businesses-self-employed/apply-for-an-employer-identification-number-ein-online",
            availability: "Monday-Friday, 7am-10pm ET",
            processing: "Immediate — EIN assigned at end of session",
            recommended: true,
          },
          phone: { number: "800-829-4933", hours: "7am-7pm local time", processing: "Immediate" },
          fax: { form: "SS-4", processing: "4 business days" },
          mail: { form: "SS-4", address: "Internal Revenue Service, Attn: EIN Operation, Cincinnati, OH 45999", processing: "4-5 weeks" },
        },
        required_information: [
          "Legal name of entity (as filed with state)",
          "Trade name / DBA (if different)",
          "Responsible party name and SSN/ITIN (typically the physician-owner)",
          "Entity type (LLC, Corporation, etc.)",
          "Reason for applying (Started new business)",
          "Date business started or acquired",
          "Principal business activity (Health Care — Office of physicians)",
          "NAICS code: 621111 (Offices of Physicians)",
          "Number of employees expected in next 12 months",
          "Mailing address",
        ],
        after_receiving_ein: [
          "Save/print the EIN confirmation letter (CP 575)",
          "Open business bank account with EIN",
          "Update all tax forms (W-9, etc.)",
          "File Form 2553 within 75 days if electing S-Corp status",
          "Set up payroll system if hiring employees",
          "Register for state tax ID if required",
          "Use EIN for Medicare/Medicaid enrollment",
        ],
        important_notes: [
          "Only ONE EIN per responsible party per day online",
          "The responsible party must have a valid SSN or ITIN",
          "EIN is permanent — it does not expire",
          "If entity type changes, you may need a new EIN",
        ],
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "forma_operating_agreement",
    "Generate operating agreement template outline for a medical practice.",
    {
      entity_type: z.string().describe("Entity type (PLLC, PC, etc.)"),
      state: z.string().describe("Two-letter state code"),
      num_members: z.number().default(1).describe("Number of members/shareholders"),
      physician_name: z.string().describe("Primary physician name"),
      practice_name: z.string().describe("Practice name"),
    },
    async (params) => {
      const result = {
        document_title: `Operating Agreement of ${params.practice_name}`,
        entity_type: params.entity_type,
        state: params.state.toUpperCase(),
        sections: [
          { section: "Article I — Formation", content: ["Entity name and type", "State of formation and governing law", "Principal office address", "Registered agent", "Purpose: Practice of medicine"] },
          { section: "Article II — Members/Shareholders", content: [`${params.physician_name} — Managing Member`, "Membership requirements (must hold active medical license)", "Admission of new members", "Transfer restrictions"] },
          { section: "Article III — Capital Contributions", content: ["Initial capital contributions", "Additional contribution requirements", "Capital accounts", "No interest on contributions"] },
          { section: "Article IV — Profit & Loss Allocation", content: ["Distribution of profits (quarterly/annually)", "Loss allocation", "Tax distributions for estimated tax payments", "Guaranteed payments for services"] },
          { section: "Article V — Management", content: ["Manager-managed vs member-managed", "Voting rights and procedures", "Day-to-day operations authority", "Major decisions requiring unanimous consent", "Officer appointments"] },
          { section: "Article VI — Compensation", content: ["Physician compensation methodology", "Productivity-based vs equal distribution", "Benefits and retirement contributions", "Expense reimbursement policy"] },
          { section: "Article VII — Non-Compete & Non-Solicitation", content: ["Geographic restriction (reasonable radius)", "Time period (typically 1-2 years)", "Patient non-solicitation", "Employee non-solicitation", "Enforceability considerations"] },
          { section: "Article VIII — Disability & Death", content: ["Disability buyout provisions", "Life insurance requirements", "Valuation methodology", "Payment terms for buyout"] },
          { section: "Article IX — Dissolution", content: ["Events triggering dissolution", "Winding up procedures", "Distribution of assets", "Patient record transfer obligations", "Notification to state medical board"] },
        ],
        disclaimer: "This is a template outline only. Have a healthcare attorney review and customize the operating agreement for your specific situation.",
        estimated_attorney_cost: "$2,000 - $5,000 for drafting and review",
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "forma_insurance_requirements",
    "Get required insurance types and cost estimates for a medical practice.",
    {
      state: z.string().describe("Two-letter state code"),
      specialty: z.string().describe("Medical specialty"),
      num_employees: z.number().default(0).describe("Number of employees"),
    },
    async (params) => {
      const stateCode = params.state.toUpperCase();
      const result = {
        state: stateCode,
        required_insurance: [
          {
            type: "Professional Liability (Malpractice)",
            required: true,
            description: "Covers claims of medical negligence, misdiagnosis, or treatment errors",
            cost_range: "Family Medicine: $8,000-$20,000/yr; Surgery: $25,000-$50,000+/yr; OB/GYN: $40,000-$80,000/yr",
            coverage: "Typical: $1M per occurrence / $3M aggregate",
            types: { occurrence: "Covers incidents during policy period regardless of when claim filed (recommended)", claims_made: "Covers claims filed during policy period; requires tail coverage when leaving" },
            mn_specific: stateCode === "MN" ? "MN has no mandatory malpractice insurance requirement, but hospital privileges and payer contracts typically require it" : undefined,
          },
          {
            type: "General Liability",
            required: true,
            description: "Covers slip-and-fall, property damage, non-medical injuries",
            cost_range: "$500-$2,000/year",
            coverage: "Typical: $1M per occurrence / $2M aggregate",
          },
          {
            type: "Workers Compensation",
            required: params.num_employees > 0,
            description: "Required in most states when you have employees",
            cost_range: "$1,500-$5,000/year for small medical office",
            mn_specific: stateCode === "MN" ? "Required for all employers in Minnesota with exceptions for sole proprietors with no employees" : undefined,
          },
          {
            type: "Business Owner's Policy (BOP)",
            required: false,
            description: "Bundles general liability + commercial property insurance at a discount",
            cost_range: "$1,000-$3,000/year",
          },
          {
            type: "Cyber Liability / Data Breach",
            required: false,
            description: "Critical for HIPAA-covered entities. Covers data breach notification costs, ransomware, and regulatory fines",
            cost_range: "$1,000-$5,000/year",
            highly_recommended: true,
          },
          {
            type: "Employment Practices Liability (EPLI)",
            required: false,
            description: "Covers wrongful termination, discrimination, and harassment claims",
            cost_range: "$800-$3,000/year",
          },
        ],
        estimated_total: {
          solo_primary_care: "$12,000-$28,000/year",
          solo_specialty: "$20,000-$60,000/year",
          small_group: "$40,000-$100,000+/year",
        },
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "forma_bank_account_checklist",
    "Get checklist for opening a business bank account for a medical practice.",
    {
      entity_type: z.string().describe("Entity type (PLLC, PC, etc.)"),
      state: z.string().describe("Two-letter state code"),
    },
    async (params) => {
      const result = {
        required_documents: [
          "EIN Confirmation Letter (CP 575) from IRS",
          `Articles of Organization/Incorporation (certified copy from ${params.state.toUpperCase()} Secretary of State)`,
          "Operating Agreement or Corporate Bylaws",
          "Government-issued photo ID for all signers",
          "Social Security Number for all signers",
          "Business license (if required by municipality)",
          "Proof of business address",
        ],
        recommended_features: [
          "FDIC insured",
          "Online banking with bill pay",
          "Integration with QuickBooks/accounting software",
          "Positive pay (fraud protection for checks)",
          "Remote deposit capture",
          "Business credit card",
          "Line of credit availability",
          "Separate savings account for tax reserves",
        ],
        account_structure: [
          "Operating account — Day-to-day expenses and revenue deposits",
          "Payroll account — Dedicated account for payroll processing",
          "Tax reserve account — Set aside 25-35% of net income for quarterly taxes",
          "Emergency fund — 3-6 months of operating expenses",
        ],
        tips: [
          "Keep personal and business finances completely separate",
          "Never use personal accounts for business transactions",
          "Set up automatic transfers to tax reserve account",
          "Consider a bank that understands healthcare businesses",
          "Ask about SBA lending programs (if you may need loans)",
        ],
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "forma_sba_loans",
    "Search SBA loan programs applicable to medical practice startups.",
    {
      loan_amount: z.number().describe("Estimated loan amount needed"),
      state: z.string().describe("Two-letter state code"),
      practice_type: z.string().describe("Type of practice"),
      is_startup: z.boolean().default(true).describe("Whether this is a startup practice"),
    },
    async (params) => {
      const stateCode = params.state.toUpperCase();
      const isRural = stateCode === "MN"; // simplified check

      const result = {
        applicable_programs: [
          {
            program: "SBA 7(a) Loan",
            max_amount: "$5,000,000",
            interest_rate: "Prime + 2.25-2.75% (variable) or fixed rate options",
            term: "Up to 10 years (equipment/working capital); 25 years (real estate)",
            down_payment: "10-20%",
            eligibility: "For-profit business, meets SBA size standards, demonstrated need",
            best_for: "General startup costs, equipment, working capital, real estate",
            applicable: true,
          },
          {
            program: "SBA 504 Loan",
            max_amount: "$5,500,000",
            interest_rate: "Below-market fixed rate (typically 3-5%)",
            term: "10 or 20 years",
            structure: "50% bank, 40% CDC/SBA, 10% borrower",
            best_for: "Real estate purchase or major equipment; must create jobs",
            applicable: params.loan_amount > 100000,
          },
          {
            program: "SBA Microloan",
            max_amount: "$50,000",
            interest_rate: "8-13% (varies by intermediary lender)",
            term: "Up to 6 years",
            best_for: "Small startup costs, supplies, equipment, working capital",
            applicable: params.loan_amount <= 50000,
          },
          {
            program: "USDA Business & Industry (B&I) Loan Guarantee",
            max_amount: "$25,000,000",
            interest_rate: "Competitive — negotiated with lender",
            term: "Up to 30 years (real estate); 15 years (equipment)",
            eligibility: "Business in rural area (population < 50,000)",
            best_for: "Rural medical practices like Ely, MN",
            applicable: isRural,
            note: isRural ? "Ely, MN (pop. ~3,400) qualifies as rural. This program could significantly reduce borrowing costs." : undefined,
          },
          {
            program: "NHSC Loan Repayment Program",
            description: "Not a loan — pays off existing student loans in exchange for service in underserved areas",
            amount: "Up to $50,000 for 2-year initial commitment (tax-free)",
            eligibility: "Practice in HPSA (Health Professional Shortage Area)",
            applicable: true,
            note: "Check if your location is in a designated HPSA at https://data.hrsa.gov/tools/shortage-area",
          },
        ],
        application_tips: [
          "Prepare a detailed business plan with 3-5 year financial projections",
          "Have good personal credit (680+ preferred)",
          "Gather 2-3 years of personal tax returns",
          "Document all collateral available",
          "Start the process 3-6 months before you need funds",
        ],
      };

      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );
}
