# Guardian One - Privacy Policy

**Effective Date:** 2026-03-19
**Owner:** Jeremy Paulo Salvino Tabernero

---

## Overview

Guardian One is a personal financial management application that runs locally
on the owner's personal workstation. It connects to financial data providers
(Plaid, Empower) to aggregate the owner's own account data for budgeting,
expense tracking, and financial planning.

## Data Collection

Guardian One collects the following data via Plaid Link:
- Account names, types, and balances
- Transaction history (date, description, amount, category)
- Institution metadata

**No data is collected from any user other than the application owner.**

## Data Use

Financial data is used exclusively for:
- Personal budget tracking and expense categorization
- Net worth calculation and trend analysis
- Bill payment monitoring and reminders
- Tax optimization recommendations
- Financial scenario planning (e.g., home affordability)

## Data Storage

- All data is stored locally on the owner's personal machine
- API credentials are encrypted using AES-256-GCM with PBKDF2 key derivation
- No data is stored in cloud databases or third-party servers
- No data is transmitted to analytics services

## Data Sharing

Guardian One does **not** share financial data with any third party.

The only external data transmission is:
- **Plaid API:** Read-only requests to pull the owner's own account data
- **Empower API:** Read-only requests to pull retirement account data
- **Notion API:** Optional write-only dashboard push with a content
  classification gate that blocks all PII/PHI before transmission

## Data Retention

- Financial data is retained locally until manually deleted by the owner
- There is no minimum retention period
- The owner can delete all data at any time by removing the data directory
- Individual bank connections can be revoked, removing associated tokens

## Data Deletion

To delete all financial data:
- Remove `data/cfo_ledger.json` (financial records)
- Remove `data/vault.enc` (encrypted credentials)
- Remove `data/plaid_tokens.json` (bank connection tokens)
- Remove `logs/` directory (audit trail)

To disconnect a single bank:
- Use the `disconnect_institution()` function to revoke the Plaid access token
- Remove associated accounts from the ledger via `clean_ledger()`

## Security

See the companion Information Security Policy for full details. Summary:
- Encryption at rest (AES-256-GCM)
- Encryption in transit (TLS 1.3)
- Role-based access control
- Immutable audit logging
- Read-only financial data access (no money movement capability)

## Consent

The application owner explicitly initiates all bank connections via Plaid Link's
secure OAuth flow. No accounts are connected without direct user action.

## Contact

Jeremy Paulo Salvino Tabernero
jeremytabernero@gmail.com

---

**Last Updated:** 2026-03-19
