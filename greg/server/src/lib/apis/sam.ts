/**
 * SAM.gov (System for Award Management) API Client
 * Checks entity registration and exclusion status
 * https://sam.gov/content/home
 */

const SAM_BASE_URL = "https://api.sam.gov/entity-information/v3/entities";

export interface SAMSearchParams {
  ueiSAM?: string;
  legalBusinessName?: string;
  dbaName?: string;
  cageCode?: string;
  npi?: string;
  stateCode?: string;
  registrationStatus?: "A" | "E" | "ID";
}

export interface SAMEntity {
  ueiSAM: string;
  ueiDUNS?: string;
  entityEFTIndicator?: string;
  cageCode?: string;
  dodaac?: string;
  legalBusinessName: string;
  dbaName?: string;
  purposeOfRegistrationCode: string;
  purposeOfRegistrationDesc: string;
  registrationStatus: string;
  registrationExpirationDate: string;
  activationDate: string;
  lastUpdateDate: string;
  physicalAddress: {
    addressLine1: string;
    addressLine2?: string;
    city: string;
    stateOrProvinceCode: string;
    zipCode: string;
    countryCode: string;
  };
  entityStartDate: string;
  fiscalYearEndCloseDate: string;
  submissionDate: string;
}

export interface SAMExclusion {
  classificationType: string;
  exclusionType: string;
  exclusionProgram: string;
  excludingAgencyCode: string;
  excludingAgencyName: string;
  exclusionName: string;
  npi?: string;
  activeDate: string;
  terminationDate?: string;
  recordStatus: string;
  description: string;
}

export interface SAMSearchResponse {
  totalRecords: number;
  entityData: SAMEntity[];
  error?: string;
}

export interface SAMExclusionResponse {
  totalRecords: number;
  exclusions: SAMExclusion[];
  searchDate: string;
  error?: string;
}

export async function searchSAMEntities(
  params: SAMSearchParams
): Promise<SAMSearchResponse> {
  const apiKey = process.env.SAM_API_KEY;

  const url = new URL(SAM_BASE_URL);
  url.searchParams.set("api_key", apiKey ?? "DEMO_KEY");

  if (params.ueiSAM) url.searchParams.set("ueiSAM", params.ueiSAM);
  if (params.legalBusinessName)
    url.searchParams.set("legalBusinessName", params.legalBusinessName);
  if (params.dbaName) url.searchParams.set("dbaName", params.dbaName);
  if (params.cageCode) url.searchParams.set("cageCode", params.cageCode);
  if (params.stateCode)
    url.searchParams.set("stateCode", params.stateCode);
  if (params.registrationStatus)
    url.searchParams.set("registrationStatus", params.registrationStatus);

  try {
    const response = await fetch(url.toString(), {
      headers: { Accept: "application/json" },
    });

    if (!response.ok) {
      throw new Error(`SAM.gov API error: ${response.status}`);
    }

    const data = await response.json();
    return data as SAMSearchResponse;
  } catch {
    return {
      totalRecords: 0,
      entityData: [],
      error:
        "Unable to reach SAM.gov API. Verify registration at https://sam.gov/. " +
        "Note: SAM.gov registration requires a UEI (Unique Entity Identifier) " +
        "and is required for federal contracts and grants.",
    };
  }
}

export async function checkSAMExclusions(
  name: string,
  npi?: string
): Promise<SAMExclusionResponse> {
  const apiKey = process.env.SAM_API_KEY;
  const exclusionUrl = "https://api.sam.gov/entity-information/v3/exclusions";

  const url = new URL(exclusionUrl);
  url.searchParams.set("api_key", apiKey ?? "DEMO_KEY");
  url.searchParams.set("q", name);

  try {
    const response = await fetch(url.toString(), {
      headers: { Accept: "application/json" },
    });

    if (!response.ok) {
      throw new Error(`SAM.gov Exclusion API error: ${response.status}`);
    }

    const data = await response.json();
    return {
      ...(data as SAMExclusionResponse),
      searchDate: new Date().toISOString(),
    };
  } catch {
    return {
      totalRecords: 0,
      exclusions: [],
      searchDate: new Date().toISOString(),
      error:
        "Unable to reach SAM.gov Exclusion API. Check manually at https://sam.gov/content/exclusions. " +
        "SAM.gov exclusion screening should be performed in addition to OIG LEIE checks.",
    };
  }
}

export function getSAMRegistrationGuide(): {
  steps: string[];
  requirements: string[];
  timeline: string;
  url: string;
  notes: string[];
} {
  return {
    steps: [
      "1. Obtain a UEI (Unique Entity Identifier) — assigned automatically during SAM registration",
      "2. Go to https://sam.gov/ and create a Login.gov account",
      "3. Start a new entity registration",
      "4. Complete the Core Data section (entity info, NAICS codes, POCs)",
      "5. Complete the Assertions section",
      "6. Complete the Representations and Certifications",
      "7. Submit and wait for IRS TIN validation (3-5 business days)",
      "8. Registration goes active after validation",
      "9. Renew annually to maintain active status",
    ],
    requirements: [
      "Legal business name matching IRS records",
      "EIN (Employer Identification Number) or TIN",
      "Physical address (no PO Boxes)",
      "Bank account for EFT (Electronic Funds Transfer)",
      "NAICS code(s) for your business activities",
      "Healthcare NAICS: 621111 (Offices of Physicians)",
    ],
    timeline: "7-10 business days for initial registration; annual renewal required",
    url: "https://sam.gov/content/entity-registration",
    notes: [
      "SAM.gov registration is FREE — beware of third-party sites charging fees",
      "Required for Medicare/Medicaid participation in some states",
      "Required for any federal grants or contracts",
      "Entity must be registered before submitting proposals for federal opportunities",
    ],
  };
}
