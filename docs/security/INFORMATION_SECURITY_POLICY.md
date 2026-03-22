# Guardian One - Information Security Policy

**Document Owner:** Jeremy Paulo Salvino Tabernero
**Last Updated:** 2026-03-19
**Version:** 1.0

---

## 1. Purpose

This policy defines the information security controls implemented by Guardian One,
a personal multi-agent AI system for financial management. Guardian One integrates
with financial data providers (Plaid, Empower) to aggregate account data for a
single authorized user.

## 2. Scope

This policy covers all data processed by Guardian One, including:
- Bank account balances and metadata
- Transaction history
- Investment and retirement account data
- Plaid API access tokens and credentials
- All external API communications

## 3. Data Classification

| Classification | Examples | Handling |
|---|---|---|
| **Confidential** | Plaid access tokens, API keys | AES-256-GCM encrypted vault, never logged |
| **Sensitive** | Account balances, transactions | Encrypted at rest, local storage only |
| **Internal** | Agent reports, audit logs | Local disk, no external transmission |

## 4. Access Control

### 4.1 Role-Based Access

Guardian One enforces role-based access via `AccessController` (core/security.py):

| Role | Scope | Description |
|---|---|---|
| **OWNER** | Full access | Jeremy Tabernero (sole user) |
| **GUARDIAN** | System coordination | Central orchestrator process |
| **AGENT** | Scoped per-agent | Each agent accesses only its allowed resources |
| **READONLY** | Read-only views | Audit/reporting interfaces |

### 4.2 Agent Isolation

Each agent declares `allowed_resources` at registration. The AccessController
denies any request outside the agent's scope. The CFO agent, for example, can
access financial data but not email content or calendar events.

### 4.3 Physical Access

The system runs on a single personal workstation. No remote access is configured.
No cloud deployment exists.

## 5. Credential Management

### 5.1 Encrypted Vault

All API keys, tokens, and secrets are stored in an encrypted vault (homelink/vault.py):

- **Algorithm:** Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256)
- **Key derivation:** PBKDF2-HMAC-SHA256 with 480,000 iterations
- **Salt:** Random 16-byte per-vault
- **Storage:** `data/vault.enc` (encrypted binary file)
- **Plaintext on disk:** Never. The master passphrase is held in memory only.

### 5.2 Plaid Token Storage

Plaid access tokens are stored in `data/plaid_tokens.json` with the following controls:
- Tokens are scoped per-institution
- Only read-only Plaid products are ever requested
- Tokens can be individually revoked via `disconnect_institution()`
- File permissions restricted to owner-only

### 5.3 Credential Rotation

The vault tracks `rotation_days` (default: 90) and `expires_at` per credential.
The health report flags credentials overdue for rotation.

## 6. Encryption

### 6.1 At Rest

| Asset | Method |
|---|---|
| API credentials | AES-256-GCM via Vault |
| Financial ledger | Local JSON file (OS-level file permissions) |
| Audit logs | Local JSONL files (OS-level file permissions) |

### 6.2 In Transit

All external API calls are routed through the Gateway (homelink/gateway.py):
- **TLS 1.3 minimum** enforced on all connections
- No plaintext HTTP endpoints permitted
- Certificate validation enabled (no cert pinning bypass)

## 7. Network Security

### 7.1 API Gateway

Every external API call passes through the Gateway, which enforces:

| Control | Implementation |
|---|---|
| **TLS enforcement** | SSLContext with PROTOCOL_TLS_CLIENT, minimum TLS 1.3 |
| **Rate limiting** | Per-service configurable (default: 60 req/min) |
| **Circuit breaker** | Opens after 5 consecutive failures, auto-recovers |
| **Timeout enforcement** | 30-second default per request |
| **Retry with backoff** | Up to 3 retries with exponential backoff |

### 7.2 Local-Only Services

- Plaid Link server binds to `127.0.0.1` only (never `0.0.0.0`)
- Dev panel accessible on localhost only
- No ports are exposed to the public internet

## 8. Plaid Integration Security

### 8.1 Read-Only Enforcement

The Plaid integration (integrations/financial_sync.py) enforces strict read-only access:

**Allowed products:** `transactions`, `auth`, `investments`, `liabilities`

**Blocked products (hardcoded):** `transfer`, `payment_initiation`, `deposit_switch`

**Endpoint allowlist:** The `_READ_ONLY_ENDPOINTS` frozenset explicitly lists every
permitted API path. The `_request()` method refuses to call any endpoint not on
this list — even if called programmatically.

### 8.2 No Money Movement

Guardian One has no capability to initiate transfers, payments, or any form of
money movement. This is enforced at the code level, not just by policy.

## 9. Logging and Monitoring

### 9.1 Audit Log

All agent actions are recorded via the immutable audit system (core/audit.py):

- **Format:** JSONL (one JSON object per line)
- **Storage:** `logs/audit.jsonl` with automatic rotation at 10 MB
- **Retention:** Append-only, never modified or deleted programmatically
- **Fields:** timestamp, agent, action, severity, details
- **Severity levels:** INFO, WARNING, ERROR, CRITICAL

### 9.2 What Gets Logged

- Every Plaid API call (endpoint, status, duration)
- Every financial sync cycle (accounts added/updated, transactions pulled)
- Every credential access from the vault
- Agent lifecycle events (start, stop, errors)
- Security policy violations (access denied events)

### 9.3 What Never Gets Logged

- API keys or access tokens (redacted in all log output)
- Account numbers or full credentials
- Raw financial data (only aggregate counts)

## 10. Data Handling

### 10.1 Storage

All data is stored locally on the owner's personal workstation:
- Financial ledger: `data/cfo_ledger.json`
- Encrypted vault: `data/vault.enc`
- Plaid tokens: `data/plaid_tokens.json`
- Audit logs: `logs/audit.jsonl`

### 10.2 No Cloud Storage

Financial data is never transmitted to cloud storage, third-party analytics,
or external databases. The only external communications are:
- Plaid API (to pull account/transaction data)
- Empower API (to pull retirement account data)
- Notion API (write-only dashboard push with PHI/PII content gate)

### 10.3 Content Classification Gate

Before any data is pushed to external services (e.g., Notion), it passes through
a content classification gate that scans for and blocks:
- Social Security Numbers
- Account numbers
- PHI (Protected Health Information)
- PII patterns (emails, phone numbers in financial context)

### 10.4 Data Retention and Deletion

- Data persists locally until the user deletes it
- No minimum retention period enforced
- Full deletion: remove `data/` directory
- Per-institution deletion: revoke Plaid token + remove accounts from ledger
- The `clean_ledger()` method provides automated data hygiene

## 11. Incident Response

### 11.1 Detection

- Audit logs capture all security-relevant events
- Circuit breaker detects service compromise (repeated auth failures)
- Gateway rate limiting detects unusual API usage patterns

### 11.2 Response Procedures

| Incident | Response |
|---|---|
| Compromised API key | Rotate via Vault, revoke old key at provider |
| Compromised Plaid token | Call `disconnect_institution()` to revoke |
| Unauthorized access attempt | Logged in audit trail, access denied by policy |
| Suspicious transactions | Flagged by `verify_transactions()` in daily review |

### 11.3 Recovery

- All credentials can be rotated independently without system downtime
- Plaid tokens can be re-established via the `--cfo-connect` OAuth flow
- Financial data can be re-synced from providers after credential rotation

## 12. Third-Party Risk

### 12.1 Integration Registry

Every external service integration is registered with a formal threat model
(homelink/registry.py) that includes:
- Top 5 risks per integration
- Severity classification
- Mitigation strategy
- Failure impact assessment
- Rollback procedure

### 12.2 Current Integrations

| Service | Auth Method | Data Flow | Risk Level |
|---|---|---|---|
| **Plaid** | OAuth2 + API key | Read-only account/transaction pull | Medium |
| **Empower** | API key | Read-only retirement account pull | Medium |
| **Notion** | Bearer token | Write-only dashboard push (PII-gated) | Low |
| **Google Calendar** | OAuth2 | Read/write calendar events | Low |
| **Gmail** | OAuth2 | Read-only inbox monitoring | Low |

## 13. Application Architecture

```
[Personal Workstation]
  |
  +-- Guardian One (Python CLI)
  |     +-- CFO Agent (financial data)
  |     +-- Chronos Agent (scheduling)
  |     +-- Other Agents (isolated)
  |     +-- AccessController (RBAC enforcement)
  |     +-- AuditLog (immutable logging)
  |
  +-- H.O.M.E. L.I.N.K. Service Layer
  |     +-- Gateway (TLS, rate limiting, circuit breaker)
  |     +-- Vault (AES-256 credential encryption)
  |     +-- Registry (threat models per integration)
  |     +-- Monitor (health checks)
  |
  +-- Local Storage
        +-- data/vault.enc (encrypted credentials)
        +-- data/cfo_ledger.json (financial data)
        +-- logs/audit.jsonl (audit trail)
```

No cloud infrastructure. No public endpoints. No multi-tenant access.

## 14. Compliance Statement

Guardian One is a personal-use system operated by a single individual for
managing their own financial accounts. It implements security controls consistent
with industry best practices for handling financial data, including encryption
at rest and in transit, role-based access control, immutable audit logging,
and strict read-only enforcement for financial data provider integrations.

---

**Approved by:** Jeremy Paulo Salvino Tabernero
**Date:** 2026-03-19
