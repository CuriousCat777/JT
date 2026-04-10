/**
 * NPPES (National Plan and Provider Enumeration System) API Client
 * Endpoint: https://npiregistry.cms.hhs.gov/api/?version=2.1
 */

const NPPES_BASE_URL = "https://npiregistry.cms.hhs.gov/api/";

export interface NPPESSearchParams {
  number?: string;
  first_name?: string;
  last_name?: string;
  state?: string;
  taxonomy_description?: string;
  enumeration_type?: "NPI-1" | "NPI-2";
  limit?: number;
  skip?: number;
}

export interface NPPESAddress {
  country_code: string;
  country_name: string;
  address_purpose: string;
  address_type: string;
  address_1: string;
  address_2: string;
  city: string;
  state: string;
  postal_code: string;
  telephone_number: string;
  fax_number: string;
}

export interface NPPESTaxonomy {
  code: string;
  taxonomy_group: string;
  desc: string;
  state: string;
  license: string;
  primary: boolean;
}

export interface NPPESResult {
  created_epoch: number;
  enumeration_type: string;
  last_updated_epoch: number;
  number: string;
  addresses: NPPESAddress[];
  taxonomies: NPPESTaxonomy[];
  basic: {
    first_name: string;
    last_name: string;
    middle_name?: string;
    credential: string;
    sole_proprietor: string;
    gender: string;
    enumeration_date: string;
    last_updated: string;
    status: string;
    name_prefix?: string;
    name_suffix?: string;
    organization_name?: string;
  };
  other_names?: Array<{
    type: string;
    code: string;
    first_name: string;
    last_name: string;
  }>;
  identifiers?: Array<{
    code: string;
    desc: string;
    identifier: string;
    issuer: string;
    state: string;
  }>;
}

export interface NPPESResponse {
  result_count: number;
  results: NPPESResult[] | null;
  Errors?: Array<{ description: string; field: string; number: string }>;
}

export async function searchNPI(
  params: NPPESSearchParams
): Promise<NPPESResponse> {
  const url = new URL(NPPES_BASE_URL);
  url.searchParams.set("version", "2.1");

  if (params.number) url.searchParams.set("number", params.number);
  if (params.first_name)
    url.searchParams.set("first_name", params.first_name);
  if (params.last_name) url.searchParams.set("last_name", params.last_name);
  if (params.state) url.searchParams.set("state", params.state);
  if (params.taxonomy_description)
    url.searchParams.set("taxonomy_description", params.taxonomy_description);
  if (params.enumeration_type)
    url.searchParams.set("enumeration_type", params.enumeration_type);
  if (params.limit) url.searchParams.set("limit", String(params.limit));
  if (params.skip) url.searchParams.set("skip", String(params.skip));

  const response = await fetch(url.toString());
  if (!response.ok) {
    throw new Error(`NPPES API error: ${response.status} ${response.statusText}`);
  }

  return (await response.json()) as NPPESResponse;
}

/**
 * Validate an NPI number using the Luhn algorithm variant (ISO/IEC 7812).
 * The NPI is a 10-digit number. Prepend 80840 to the NPI, then run the
 * Luhn check on the resulting 15-digit number (the check digit is the last
 * digit of the original NPI).
 */
export function validateNPI(npi: string): {
  valid: boolean;
  reason?: string;
} {
  if (!/^\d{10}$/.test(npi)) {
    return { valid: false, reason: "NPI must be exactly 10 digits" };
  }

  // Prepend the constant prefix 80840 for the Luhn check
  const prefixed = "80840" + npi.substring(0, 9);
  const checkDigit = parseInt(npi[9], 10);

  let sum = 0;
  let alternate = true; // Start doubling from the rightmost digit of prefixed
  for (let i = prefixed.length - 1; i >= 0; i--) {
    let n = parseInt(prefixed[i], 10);
    if (alternate) {
      n *= 2;
      if (n > 9) n -= 9;
    }
    sum += n;
    alternate = !alternate;
  }

  const expected = (10 - (sum % 10)) % 10;

  if (checkDigit === expected) {
    return { valid: true };
  }

  return {
    valid: false,
    reason: `Check digit mismatch: expected ${expected}, got ${checkDigit}`,
  };
}
