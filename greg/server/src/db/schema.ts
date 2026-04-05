import {
  pgTable,
  pgEnum,
  uuid,
  varchar,
  text,
  timestamp,
  jsonb,
  boolean,
  decimal,
  integer,
  date,
} from "drizzle-orm/pg-core";

// ── Enums ──────────────────────────────────────────────────────────────────────

export const entityTypeEnum = pgEnum("entity_type", [
  "PLLC",
  "PC",
  "SOLE_PROP",
  "S_CORP",
  "C_CORP",
]);

export const practiceStatusEnum = pgEnum("practice_status", [
  "PLANNING",
  "FORMING",
  "ACTIVE",
  "SUSPENDED",
]);

export const credentialTypeEnum = pgEnum("credential_type", [
  "NPI",
  "DEA",
  "STATE_LICENSE",
  "BOARD_CERT",
  "CAQH",
  "HOSPITAL_PRIVILEGE",
]);

export const credentialStatusEnum = pgEnum("credential_status", [
  "PENDING",
  "ACTIVE",
  "EXPIRED",
  "REVOKED",
  "SUSPENDED",
]);

export const complianceDomainEnum = pgEnum("compliance_domain", [
  "HIPAA",
  "CMS",
  "OSHA",
  "CLIA",
  "STATE",
  "PAYER",
]);

export const complianceStatusEnum = pgEnum("compliance_status", [
  "NOT_STARTED",
  "IN_PROGRESS",
  "COMPLETED",
  "OVERDUE",
  "NA",
]);

export const encounterStatusEnum = pgEnum("encounter_status", [
  "PLANNED",
  "IN_PROGRESS",
  "COMPLETED",
  "CANCELLED",
]);

export const claimTypeEnum = pgEnum("claim_type", ["CMS1500", "837P"]);

export const claimStatusEnum = pgEnum("claim_status", [
  "DRAFT",
  "SUBMITTED",
  "PENDING",
  "PAID",
  "DENIED",
  "APPEALED",
]);

export const financialRecordTypeEnum = pgEnum("financial_record_type", [
  "REVENUE",
  "EXPENSE",
  "PAYROLL",
  "TAX",
]);

// ── Tables ─────────────────────────────────────────────────────────────────────

export const physicians = pgTable("physicians", {
  id: uuid("id").primaryKey().defaultRandom(),
  npi: varchar("npi", { length: 10 }),
  firstName: varchar("first_name", { length: 100 }).notNull(),
  lastName: varchar("last_name", { length: 100 }).notNull(),
  email: varchar("email", { length: 255 }).notNull(),
  deaNumber: varchar("dea_number", { length: 20 }),
  specialties: jsonb("specialties").$type<string[]>().default([]),
  boardCertifications: jsonb("board_certifications")
    .$type<{ board: string; specialty: string; expires: string }[]>()
    .default([]),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  updatedAt: timestamp("updated_at").defaultNow().notNull(),
});

export const practices = pgTable("practices", {
  id: uuid("id").primaryKey().defaultRandom(),
  physicianId: uuid("physician_id")
    .references(() => physicians.id)
    .notNull(),
  name: varchar("name", { length: 255 }).notNull(),
  entityType: entityTypeEnum("entity_type").notNull(),
  ein: varchar("ein", { length: 20 }),
  taxId: varchar("tax_id", { length: 20 }),
  state: varchar("state", { length: 2 }).notNull(),
  formedDate: date("formed_date"),
  status: practiceStatusEnum("status").default("PLANNING").notNull(),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  updatedAt: timestamp("updated_at").defaultNow().notNull(),
});

export const locations = pgTable("locations", {
  id: uuid("id").primaryKey().defaultRandom(),
  practiceId: uuid("practice_id")
    .references(() => practices.id)
    .notNull(),
  addressLine1: varchar("address_line1", { length: 255 }).notNull(),
  addressLine2: varchar("address_line2", { length: 255 }),
  city: varchar("city", { length: 100 }).notNull(),
  state: varchar("state", { length: 2 }).notNull(),
  zip: varchar("zip", { length: 10 }).notNull(),
  county: varchar("county", { length: 100 }),
  phone: varchar("phone", { length: 20 }),
  fax: varchar("fax", { length: 20 }),
  isPrimary: boolean("is_primary").default(false).notNull(),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});

export const credentials = pgTable("credentials", {
  id: uuid("id").primaryKey().defaultRandom(),
  physicianId: uuid("physician_id")
    .references(() => physicians.id)
    .notNull(),
  credentialType: credentialTypeEnum("credential_type").notNull(),
  identifier: varchar("identifier", { length: 100 }).notNull(),
  issuingAuthority: varchar("issuing_authority", { length: 255 }),
  state: varchar("state", { length: 2 }),
  status: credentialStatusEnum("status").default("PENDING").notNull(),
  issuedDate: date("issued_date"),
  expiryDate: date("expiry_date"),
  notes: text("notes"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  updatedAt: timestamp("updated_at").defaultNow().notNull(),
});

export const complianceItems = pgTable("compliance_items", {
  id: uuid("id").primaryKey().defaultRandom(),
  practiceId: uuid("practice_id")
    .references(() => practices.id)
    .notNull(),
  domain: complianceDomainEnum("domain").notNull(),
  requirement: varchar("requirement", { length: 255 }).notNull(),
  description: text("description"),
  status: complianceStatusEnum("status").default("NOT_STARTED").notNull(),
  dueDate: date("due_date"),
  completedDate: date("completed_date"),
  evidenceUrl: varchar("evidence_url", { length: 500 }),
  lastChecked: timestamp("last_checked"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  updatedAt: timestamp("updated_at").defaultNow().notNull(),
});

export const patients = pgTable("patients", {
  id: uuid("id").primaryKey().defaultRandom(),
  practiceId: uuid("practice_id")
    .references(() => practices.id)
    .notNull(),
  mrn: varchar("mrn", { length: 50 }).unique().notNull(),
  fhirId: varchar("fhir_id", { length: 100 }),
  firstName: varchar("first_name", { length: 100 }).notNull(),
  lastName: varchar("last_name", { length: 100 }).notNull(),
  dateOfBirth: date("date_of_birth").notNull(),
  gender: varchar("gender", { length: 20 }),
  phone: varchar("phone", { length: 20 }),
  email: varchar("email", { length: 255 }),
  address: jsonb("address").$type<{
    line1: string;
    line2?: string;
    city: string;
    state: string;
    zip: string;
  }>(),
  insurance: jsonb("insurance").$type<{
    payerName: string;
    payerId: string;
    memberId: string;
    groupNumber?: string;
    planType?: string;
  }>(),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  updatedAt: timestamp("updated_at").defaultNow().notNull(),
});

export const encounters = pgTable("encounters", {
  id: uuid("id").primaryKey().defaultRandom(),
  patientId: uuid("patient_id")
    .references(() => patients.id)
    .notNull(),
  physicianId: uuid("physician_id")
    .references(() => physicians.id)
    .notNull(),
  practiceId: uuid("practice_id")
    .references(() => practices.id)
    .notNull(),
  encounterDate: timestamp("encounter_date").notNull(),
  encounterType: varchar("encounter_type", { length: 50 }).notNull(),
  chiefComplaint: text("chief_complaint"),
  assessment: text("assessment"),
  plan: text("plan"),
  icd10Codes: jsonb("icd10_codes").$type<string[]>().default([]),
  cptCodes: jsonb("cpt_codes").$type<string[]>().default([]),
  status: encounterStatusEnum("status").default("PLANNED").notNull(),
  notes: text("notes"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});

export const claims = pgTable("claims", {
  id: uuid("id").primaryKey().defaultRandom(),
  encounterId: uuid("encounter_id")
    .references(() => encounters.id)
    .notNull(),
  practiceId: uuid("practice_id")
    .references(() => practices.id)
    .notNull(),
  claimType: claimTypeEnum("claim_type").notNull(),
  payerName: varchar("payer_name", { length: 255 }).notNull(),
  payerId: varchar("payer_id", { length: 50 }),
  totalCharge: decimal("total_charge", { precision: 10, scale: 2 }).notNull(),
  amountPaid: decimal("amount_paid", { precision: 10, scale: 2 }).default("0"),
  status: claimStatusEnum("status").default("DRAFT").notNull(),
  submittedDate: date("submitted_date"),
  paidDate: date("paid_date"),
  denialReason: text("denial_reason"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  updatedAt: timestamp("updated_at").defaultNow().notNull(),
});

export const financialRecords = pgTable("financial_records", {
  id: uuid("id").primaryKey().defaultRandom(),
  practiceId: uuid("practice_id")
    .references(() => practices.id)
    .notNull(),
  recordType: financialRecordTypeEnum("record_type").notNull(),
  category: varchar("category", { length: 100 }).notNull(),
  description: text("description"),
  amount: decimal("amount", { precision: 12, scale: 2 }).notNull(),
  date: date("date").notNull(),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});

export const referralNetwork = pgTable("referral_network", {
  id: uuid("id").primaryKey().defaultRandom(),
  practiceId: uuid("practice_id")
    .references(() => practices.id)
    .notNull(),
  providerName: varchar("provider_name", { length: 255 }).notNull(),
  providerNpi: varchar("provider_npi", { length: 10 }),
  specialty: varchar("specialty", { length: 100 }),
  organization: varchar("organization", { length: 255 }),
  phone: varchar("phone", { length: 20 }),
  fax: varchar("fax", { length: 20 }),
  fhirEndpoint: varchar("fhir_endpoint", { length: 500 }),
  notes: text("notes"),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});

export const onboardingProgress = pgTable("onboarding_progress", {
  id: uuid("id").primaryKey().defaultRandom(),
  physicianId: uuid("physician_id")
    .references(() => physicians.id)
    .notNull(),
  practiceId: uuid("practice_id").references(() => practices.id),
  currentStep: integer("current_step").default(0).notNull(),
  stepsCompleted: jsonb("steps_completed")
    .$type<{ step: string; completedAt: string }[]>()
    .default([]),
  assessmentData: jsonb("assessment_data").$type<Record<string, unknown>>().default({}),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  updatedAt: timestamp("updated_at").defaultNow().notNull(),
});
