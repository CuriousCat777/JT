/**
 * LEDGER — Financial Management Agent
 * Handles medical billing, insurance claims, payroll, tax preparation,
 * and financial forecasting.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

export function registerLedgerTools(server: McpServer): void {
  server.tool(
    "ledger_claim_create",
    "Generate a CMS-1500 or 837P claim for a clinical encounter.",
    {
      encounter_id: z.string().describe("Encounter UUID"),
      practice_id: z.string().describe("Practice UUID"),
      claim_type: z.enum(["CMS1500", "837P"]).default("837P"),
      payer_name: z.string().describe("Insurance payer name"),
      payer_id: z.string().optional().describe("Payer ID"),
      diagnosis_codes: z.array(z.string()).describe("ICD-10 diagnosis codes"),
      procedure_codes: z.array(z.object({ code: z.string(), modifier: z.string().optional(), units: z.number().default(1), charge: z.number() })).describe("CPT codes with charges"),
      service_date: z.string().describe("Date of service"),
      place_of_service: z.string().default("11").describe("Place of service code"),
    },
    async (params) => {
      const totalCharge = params.procedure_codes.reduce((sum, p) => sum + p.charge * p.units, 0);
      const result = {
        claim: {
          id: crypto.randomUUID(),
          type: params.claim_type,
          status: "DRAFT",
          total_charge: totalCharge.toFixed(2),
          created_at: new Date().toISOString(),
        },
        cms1500_mapping: {
          box_1: "Medicare/Medicaid/Other (payer type)",
          box_2: "Patient name",
          box_3: "Patient DOB and sex",
          box_17: "Referring provider",
          box_21: params.diagnosis_codes.map((code, i) => `Diagnosis ${String.fromCharCode(65 + i)}: ${code}`),
          box_24: params.procedure_codes.map((p) => ({
            service_date: params.service_date,
            place_of_service: params.place_of_service,
            cpt: p.code,
            modifier: p.modifier ?? "",
            diagnosis_pointer: "A",
            charge: `$${(p.charge * p.units).toFixed(2)}`,
            units: p.units,
          })),
          box_28: `Total Charge: $${totalCharge.toFixed(2)}`,
          box_33: "Billing provider info + NPI",
        },
        edi_837p: {
          format: "ANSI X12 837P (Professional)",
          loops: ["2000A (Billing Provider)", "2000B (Subscriber)", "2300 (Claim)", "2400 (Service Line)"],
          clearinghouse: "Submit via clearinghouse (Availity, Trizetto, Change Healthcare)",
        },
        submission_checklist: [
          "Verify patient eligibility before submission",
          "Ensure diagnosis codes support medical necessity for procedures",
          "Check for clean claim requirements (no missing fields)",
          "Submit within timely filing limit (Medicare: 365 days; varies by payer)",
        ],
      };
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "ledger_claim_status",
    "Check claim status and provide guidance on claim tracking.",
    {
      claim_id: z.string().optional().describe("Internal claim ID"),
      payer_claim_number: z.string().optional().describe("Payer-assigned claim number"),
      payer_name: z.string().describe("Insurance payer name"),
    },
    async (params) => {
      const result = {
        claim: params,
        status_tracking: {
          edi_transaction: "ANSI X12 276 (Status Inquiry) / 277 (Status Response)",
          common_statuses: [
            { code: "A0", meaning: "Forwarded to payer", action: "Wait for processing" },
            { code: "A1", meaning: "Accepted for processing", action: "Allow 14-30 days" },
            { code: "A2", meaning: "Accepted — awaiting additional info", action: "Check for requests" },
            { code: "P1", meaning: "Pending — additional info requested", action: "Submit requested documentation" },
            { code: "F1", meaning: "Finalized — paid", action: "Post payment" },
            { code: "F4", meaning: "Finalized — denied", action: "Review denial reason; appeal if appropriate" },
          ],
          denial_reasons: [
            { code: "CO-4", reason: "Procedure code inconsistent with modifier", action: "Correct and resubmit" },
            { code: "CO-16", reason: "Claim lacks information needed for adjudication", action: "Add missing information" },
            { code: "CO-50", reason: "Not medically necessary", action: "Submit medical records/appeal" },
            { code: "CO-97", reason: "Service bundled", action: "Review bundling rules; use modifier if appropriate" },
            { code: "PR-1", reason: "Deductible", action: "Bill patient" },
            { code: "PR-2", reason: "Coinsurance", action: "Bill patient" },
          ],
        },
        appeal_process: {
          timeline: "Most payers allow 60-180 days for appeal",
          levels: ["Level 1: Internal appeal with supporting documentation", "Level 2: External/independent review", "Level 3: Administrative hearing (Medicare)"],
        },
      };
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "ledger_revenue_forecast",
    "Project practice revenue based on patient volume and payer mix.",
    {
      monthly_patient_volume: z.number().describe("Expected monthly patient visits"),
      payer_mix: z.object({
        medicare_pct: z.number().describe("Medicare %"),
        medicaid_pct: z.number().describe("Medicaid %"),
        commercial_pct: z.number().describe("Commercial %"),
        self_pay_pct: z.number().describe("Self-pay %"),
      }),
      average_visit_charge: z.number().describe("Average billed charge per visit"),
      specialty: z.string().describe("Medical specialty"),
      state: z.string().describe("Two-letter state code"),
    },
    async (params) => {
      const pm = params.payer_mix;
      const vol = params.monthly_patient_volume;
      const charge = params.average_visit_charge;

      const medicareRevenue = vol * (pm.medicare_pct / 100) * charge * 0.80;
      const medicaidRevenue = vol * (pm.medicaid_pct / 100) * charge * 0.55;
      const commercialRevenue = vol * (pm.commercial_pct / 100) * charge * 0.90;
      const selfPayRevenue = vol * (pm.self_pay_pct / 100) * charge * 0.40;

      const monthlyGross = vol * charge;
      const monthlyNet = medicareRevenue + medicaidRevenue + commercialRevenue + selfPayRevenue;
      const collectionRate = ((monthlyNet / monthlyGross) * 100).toFixed(1);

      const result = {
        assumptions: {
          monthly_volume: vol,
          average_charge: `$${charge}`,
          payer_mix: pm,
          reimbursement_rates: { medicare: "~80% of billed", medicaid: "~55% of billed", commercial: "~90% of billed", self_pay: "~40% collection" },
        },
        monthly_projection: {
          gross_charges: `$${monthlyGross.toFixed(0)}`,
          net_collections: `$${monthlyNet.toFixed(0)}`,
          collection_rate: `${collectionRate}%`,
          by_payer: {
            medicare: `$${medicareRevenue.toFixed(0)}`,
            medicaid: `$${medicaidRevenue.toFixed(0)}`,
            commercial: `$${commercialRevenue.toFixed(0)}`,
            self_pay: `$${selfPayRevenue.toFixed(0)}`,
          },
        },
        quarterly_projection: `$${(monthlyNet * 3).toFixed(0)}`,
        annual_projection: `$${(monthlyNet * 12).toFixed(0)}`,
        breakeven_analysis: {
          estimated_monthly_overhead: "$25,000-$45,000 (solo primary care)",
          visits_needed_to_breakeven: `${Math.ceil(35000 / (monthlyNet / vol))} visits/month (at $35K overhead)`,
          note: "Actual overhead varies by location, staffing, and lease costs",
        },
        benchmarks: {
          primary_care: { median_collections: "$450,000-$650,000/year", median_overhead: "55-65% of collections" },
          note: "MGMA data for primary care practices",
        },
      };
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "ledger_expense_track",
    "Track practice expenses by category.",
    {
      practice_id: z.string().describe("Practice UUID"),
      category: z.enum(["rent", "utilities", "supplies", "equipment", "staff", "insurance", "technology", "marketing", "professional_services", "other"]),
      description: z.string().describe("Expense description"),
      amount: z.number().describe("Amount"),
      date: z.string().describe("Expense date"),
      recurring: z.boolean().default(false),
      frequency: z.enum(["monthly", "quarterly", "annual"]).optional(),
    },
    async (params) => {
      const annualized = params.recurring
        ? params.amount * (params.frequency === "monthly" ? 12 : params.frequency === "quarterly" ? 4 : 1)
        : params.amount;

      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            expense: { id: crypto.randomUUID(), ...params, annualized_cost: annualized.toFixed(2) },
            category_benchmarks: {
              rent: "7-10% of collections",
              staff: "25-35% of collections",
              supplies: "5-8% of collections",
              insurance: "3-5% of collections",
              technology: "2-4% of collections",
            },
          }, null, 2),
        }],
      };
    },
  );

  server.tool(
    "ledger_payroll_calculate",
    "Calculate payroll with tax withholding for practice employees.",
    {
      employees: z.array(z.object({
        role: z.string(),
        salary_or_hourly: z.enum(["salary", "hourly"]),
        rate: z.number(),
        hours_per_week: z.number().default(40),
      })),
      state: z.string().describe("Two-letter state code"),
      pay_period: z.enum(["weekly", "biweekly", "monthly"]).default("biweekly"),
    },
    async (params) => {
      const periodsPerYear = params.pay_period === "weekly" ? 52 : params.pay_period === "biweekly" ? 26 : 12;
      const stateCode = params.state.toUpperCase();
      const stateTaxRate = stateCode === "MN" ? 0.0535 : stateCode === "CA" ? 0.04 : stateCode === "TX" ? 0 : stateCode === "FL" ? 0 : 0.04;

      const payroll = params.employees.map((emp) => {
        const annualGross = emp.salary_or_hourly === "salary" ? emp.rate : emp.rate * emp.hours_per_week * 52;
        const periodGross = annualGross / periodsPerYear;
        const fica = periodGross * 0.0765;
        const federalTax = periodGross * 0.22; // simplified 22% bracket
        const stateTax = periodGross * stateTaxRate;
        const netPay = periodGross - fica - federalTax - stateTax;

        return {
          role: emp.role,
          annual_salary: `$${annualGross.toFixed(0)}`,
          period_gross: `$${periodGross.toFixed(2)}`,
          deductions: {
            fica_employee: `$${fica.toFixed(2)} (7.65%)`,
            federal_withholding: `$${federalTax.toFixed(2)} (est.)`,
            state_withholding: `$${stateTax.toFixed(2)} (${stateCode}: ${(stateTaxRate * 100).toFixed(2)}%)`,
          },
          net_pay: `$${netPay.toFixed(2)}`,
          employer_costs: {
            fica_match: `$${fica.toFixed(2)} (7.65%)`,
            futa: `$${(periodGross * 0.006).toFixed(2)} (0.6%)`,
            suta: `$${(periodGross * 0.02).toFixed(2)} (est. 2%)`,
            workers_comp: `$${(periodGross * 0.01).toFixed(2)} (est. 1%)`,
          },
        };
      });

      const totalPeriodCost = payroll.reduce((sum, p) => {
        const gross = parseFloat(p.period_gross.replace("$", ""));
        return sum + gross * 1.1165; // gross + employer costs
      }, 0);

      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            pay_period: params.pay_period,
            state: stateCode,
            employees: payroll,
            total_period_cost: `$${totalPeriodCost.toFixed(2)} (including employer taxes)`,
            annual_labor_cost: `$${(totalPeriodCost * periodsPerYear).toFixed(0)}`,
            note: "Tax withholding is estimated. Actual amounts depend on W-4 elections, filing status, and current tax tables.",
          }, null, 2),
        }],
      };
    },
  );

  server.tool(
    "ledger_tax_estimate",
    "Estimate quarterly taxes for a medical practice.",
    {
      annual_revenue: z.number().describe("Estimated annual revenue"),
      annual_expenses: z.number().describe("Estimated annual expenses"),
      entity_type: z.enum(["PLLC", "PC", "S_CORP", "SOLE_PROP"]),
      state: z.string().describe("Two-letter state code"),
      filing_status: z.enum(["single", "married_joint"]).default("single"),
    },
    async (params) => {
      const netIncome = params.annual_revenue - params.annual_expenses;
      const isPassThrough = ["PLLC", "SOLE_PROP"].includes(params.entity_type);
      const selfEmploymentTax = isPassThrough ? netIncome * 0.9235 * 0.153 : 0;
      const qbiDeduction = isPassThrough ? Math.min(netIncome * 0.20, 191950) : 0;
      const taxableIncome = netIncome - (isPassThrough ? selfEmploymentTax * 0.5 : 0) - qbiDeduction;

      // Simplified federal brackets for 2024
      let federalTax: number;
      if (params.filing_status === "single") {
        if (taxableIncome <= 11600) federalTax = taxableIncome * 0.10;
        else if (taxableIncome <= 47150) federalTax = 1160 + (taxableIncome - 11600) * 0.12;
        else if (taxableIncome <= 100525) federalTax = 5426 + (taxableIncome - 47150) * 0.22;
        else if (taxableIncome <= 191950) federalTax = 17169 + (taxableIncome - 100525) * 0.24;
        else if (taxableIncome <= 243725) federalTax = 39111 + (taxableIncome - 191950) * 0.32;
        else federalTax = 55679 + (taxableIncome - 243725) * 0.35;
      } else {
        if (taxableIncome <= 23200) federalTax = taxableIncome * 0.10;
        else if (taxableIncome <= 94300) federalTax = 2320 + (taxableIncome - 23200) * 0.12;
        else federalTax = 10852 + (taxableIncome - 94300) * 0.22;
      }

      const stateCode = params.state.toUpperCase();
      const stateTaxRate = stateCode === "MN" ? 0.0785 : stateCode === "CA" ? 0.093 : stateCode === "TX" ? 0 : stateCode === "FL" ? 0 : 0.05;
      const stateTax = netIncome * stateTaxRate;

      const totalTax = federalTax + selfEmploymentTax + stateTax;
      const quarterlyPayment = totalTax / 4;

      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            summary: {
              annual_revenue: `$${params.annual_revenue.toLocaleString()}`,
              annual_expenses: `$${params.annual_expenses.toLocaleString()}`,
              net_income: `$${netIncome.toLocaleString()}`,
              entity_type: params.entity_type,
            },
            tax_breakdown: {
              federal_income_tax: `$${federalTax.toFixed(0)}`,
              self_employment_tax: isPassThrough ? `$${selfEmploymentTax.toFixed(0)}` : "N/A (S-Corp/C-Corp)",
              state_tax: `$${stateTax.toFixed(0)} (${stateCode}: ${(stateTaxRate * 100).toFixed(1)}%)`,
              qbi_deduction: isPassThrough ? `$${qbiDeduction.toFixed(0)} (Section 199A)` : "N/A",
              total_estimated_tax: `$${totalTax.toFixed(0)}`,
              effective_rate: `${((totalTax / netIncome) * 100).toFixed(1)}%`,
            },
            quarterly_estimates: {
              q1_due: "April 15",
              q2_due: "June 15",
              q3_due: "September 15",
              q4_due: "January 15 (following year)",
              payment_per_quarter: `$${quarterlyPayment.toFixed(0)}`,
            },
            disclaimer: "These are estimates based on simplified tax calculations. Consult a tax professional (CPA) for accurate tax planning.",
          }, null, 2),
        }],
      };
    },
  );

  server.tool(
    "ledger_profit_loss",
    "Generate a P&L statement template with benchmark percentages.",
    {
      practice_id: z.string().describe("Practice UUID"),
      period: z.enum(["monthly", "quarterly", "annual"]).default("monthly"),
      start_date: z.string().describe("Period start date"),
    },
    async (params) => {
      const result = {
        statement: {
          practice_id: params.practice_id,
          period: params.period,
          start_date: params.start_date,
          template: {
            revenue: {
              patient_services: { amount: 0, benchmark: "90-95% of total revenue" },
              ancillary_services: { amount: 0, benchmark: "3-8% of total revenue" },
              other_revenue: { amount: 0, benchmark: "1-3% of total revenue" },
              total_revenue: 0,
            },
            operating_expenses: {
              physician_compensation: { amount: 0, benchmark: "30-40% of collections" },
              staff_salaries_benefits: { amount: 0, benchmark: "20-25% of collections" },
              rent_occupancy: { amount: 0, benchmark: "5-10% of collections" },
              medical_supplies: { amount: 0, benchmark: "5-8% of collections" },
              insurance: { amount: 0, benchmark: "3-5% of collections" },
              technology_ehr: { amount: 0, benchmark: "2-4% of collections" },
              billing_collections: { amount: 0, benchmark: "4-8% of collections" },
              marketing: { amount: 0, benchmark: "1-3% of collections" },
              professional_services: { amount: 0, benchmark: "1-2% of collections" },
              office_supplies: { amount: 0, benchmark: "1-2% of collections" },
              total_expenses: 0,
            },
            net_income: 0,
            net_margin_benchmark: "Primary care: 5-15%; Specialty: 15-30%",
          },
        },
      };
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    },
  );

  server.tool(
    "ledger_startup_budget",
    "Generate detailed startup cost budget for a medical practice.",
    {
      practice_type: z.enum(["solo_primary_care", "solo_specialty", "group"]),
      location_type: z.enum(["urban", "suburban", "rural"]),
      state: z.string().describe("Two-letter state code"),
      square_footage: z.number().optional().describe("Planned office square footage"),
    },
    async (params) => {
      const sqft = params.square_footage ?? (params.practice_type === "solo_primary_care" ? 1500 : params.practice_type === "solo_specialty" ? 2000 : 3500);
      const isRural = params.location_type === "rural";
      const rentMultiplier = isRural ? 0.6 : params.location_type === "suburban" ? 0.85 : 1.0;

      const budget = {
        practice_type: params.practice_type,
        location: `${params.location_type} — ${params.state.toUpperCase()}`,
        square_footage: sqft,
        categories: {
          leasehold_improvements: {
            low: Math.round(sqft * 50 * rentMultiplier),
            high: Math.round(sqft * 150 * rentMultiplier),
            notes: "Build-out, exam rooms, reception, ADA compliance",
          },
          medical_equipment: {
            low: 50000, high: 200000,
            items: ["Exam tables ($2K-$5K each)", "Otoscope/ophthalmoscope sets ($500-$1.5K)", "Blood pressure monitors", "EKG machine ($2K-$8K)", "Point-of-care testing equipment ($5K-$15K)", "Minor procedure instruments ($5K-$15K)"],
          },
          technology: {
            low: 10000, high: 30000,
            items: ["EHR system ($200-$700/mo/provider)", "Practice management software", "Computers and monitors ($5K-$10K)", "Networking/Wi-Fi ($2K-$5K)", "Phone system ($1K-$3K)", "Printer/scanner/fax ($1K-$2K)"],
          },
          furniture: { low: 10000, high: 25000, items: ["Reception furniture", "Office desks/chairs", "Waiting room seating", "Storage/filing"] },
          initial_marketing: { low: 5000, high: 15000, items: ["Website ($2K-$5K)", "Signage ($1K-$3K)", "Google Business listing", "Local advertising", "Announcement mailings"] },
          working_capital: {
            low: 75000, high: 150000,
            notes: "3-6 months operating expenses. Critical — revenue won't start for 60-90 days after opening due to billing cycle.",
          },
          legal_accounting: { low: 5000, high: 15000, items: ["Business formation ($2K-$5K)", "Operating agreement ($2K-$5K)", "CPA setup ($1K-$3K)", "Contract review"] },
          insurance_deposits: { low: 5000, high: 25000, items: ["Malpractice (first premium)", "General liability", "Workers comp deposit", "Property insurance"] },
          licensing_credentialing: { low: 2000, high: 8000, items: ["State license fees", "DEA registration ($888)", "CLIA certificate ($180)", "Business license", "Credentialing costs"] },
        },
        total_estimate: { low: 0, high: 0 },
        rural_advantages: isRural ? [
          "Lower rent/lease costs (40-60% less than urban)",
          "USDA B&I loan guarantees available",
          "NHSC loan repayment ($50K+ for HPSA service)",
          "Rural Health Clinic (RHC) designation — enhanced reimbursement",
          "State and federal grant programs for rural healthcare",
          "Community Development Financial Institution (CDFI) lending",
          params.state.toUpperCase() === "MN" ? "Ely, MN specific: Low rent (~$8-12/sqft), strong community support, potential HRSA grant eligibility" : undefined,
        ].filter(Boolean) : undefined,
      };

      // Calculate totals
      const cats = budget.categories;
      budget.total_estimate.low = Object.values(cats).reduce((sum, c) => sum + (c as { low: number }).low, 0);
      budget.total_estimate.high = Object.values(cats).reduce((sum, c) => sum + (c as { high: number }).high, 0);

      return { content: [{ type: "text", text: JSON.stringify(budget, null, 2) }] };
    },
  );
}
