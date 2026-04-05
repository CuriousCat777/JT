/**
 * OIG (Office of Inspector General) Exclusion Check Client
 * Searches the LEIE (List of Excluded Individuals/Entities) database
 * https://oig.hhs.gov/exclusions/exclusions_list.asp
 */

const OIG_BASE_URL = "https://oig.hhs.gov/exclusions/api";

export interface OIGSearchParams {
  first_name?: string;
  last_name?: string;
  npi?: string;
  state?: string;
  entity_type?: "individual" | "entity";
}

export interface OIGExclusion {
  lastName: string;
  firstName: string;
  middleName?: string;
  npi?: string;
  upin?: string;
  dob?: string;
  address: string;
  city: string;
  state: string;
  zip: string;
  exclusionType: string;
  exclusionDate: string;
  reinstatementDate?: string;
  waiverDate?: string;
  waiverState?: string;
  general: string;
  specialty: string;
}

export interface OIGSearchResponse {
  found: boolean;
  count: number;
  results: OIGExclusion[];
  searchDate: string;
  disclaimer: string;
}

export async function checkOIGExclusion(
  params: OIGSearchParams
): Promise<OIGSearchResponse> {
  const url = new URL(`${OIG_BASE_URL}/search`);

  if (params.first_name) url.searchParams.set("first_name", params.first_name);
  if (params.last_name) url.searchParams.set("last_name", params.last_name);
  if (params.npi) url.searchParams.set("npi", params.npi);
  if (params.state) url.searchParams.set("state", params.state);
  if (params.entity_type) url.searchParams.set("type", params.entity_type);

  try {
    const response = await fetch(url.toString(), {
      headers: { Accept: "application/json" },
    });

    if (!response.ok) {
      throw new Error(`OIG API error: ${response.status}`);
    }

    const data = await response.json();
    return data as OIGSearchResponse;
  } catch {
    // Fallback: return a structured response indicating the check should be
    // performed manually via the OIG website
    return {
      found: false,
      count: 0,
      results: [],
      searchDate: new Date().toISOString(),
      disclaimer:
        "Unable to reach OIG LEIE API. Please verify exclusion status manually at " +
        "https://exclusions.oig.hhs.gov/ — Federal regulations (42 CFR 1001) require " +
        "checking all employees, contractors, and providers against the LEIE before " +
        "hiring and monthly thereafter.",
    };
  }
}

/**
 * Check if a provider should be screened based on their role.
 * Returns guidance on OIG screening requirements.
 */
export function getOIGScreeningGuidance(): {
  frequency: string;
  whoToScreen: string[];
  consequences: string[];
  resources: string[];
} {
  return {
    frequency:
      "Monthly screening recommended; required before hire and at least monthly for Medicaid participation",
    whoToScreen: [
      "Physicians and licensed providers",
      "Nurses and clinical staff",
      "Billing and coding staff",
      "Administrative employees with access to federal healthcare programs",
      "Contractors and vendors",
      "Board members (if applicable)",
    ],
    consequences: [
      "Civil monetary penalties up to $100,000 per item/service",
      "Treble damages under the False Claims Act",
      "Exclusion from all federal healthcare programs",
      "Loss of Medicare/Medicaid billing privileges",
      "Personal liability for organization leadership",
    ],
    resources: [
      "OIG LEIE Database: https://exclusions.oig.hhs.gov/",
      "OIG Special Advisory Bulletin: https://oig.hhs.gov/documents/special-advisory-bulletins/885/sab-05092013.pdf",
      "GSA SAM.gov: https://sam.gov/ (additional exclusion screening)",
    ],
  };
}
