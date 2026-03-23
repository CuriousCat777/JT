import Foundation

// MARK: - System Status

struct SystemStatus: Codable {
    let owner: String
    let timezone: String
    let agents: [AgentSummary]
    let timestamp: String
}

struct AgentSummary: Codable, Identifiable {
    var id: String { name }
    let name: String
    let status: String
    let enabled: Bool
    let intervalMin: Int?
    let allowedResources: [String]

    enum CodingKeys: String, CodingKey {
        case name, status, enabled
        case intervalMin = "interval_min"
        case allowedResources = "allowed_resources"
    }
}

// MARK: - Agent Detail

struct AgentDetail: Codable, Identifiable {
    var id: String { name }
    let name: String
    let status: String
    let enabled: Bool
    let intervalMin: Int?
    let allowedResources: [String]
    let report: AgentReport?

    enum CodingKeys: String, CodingKey {
        case name, status, enabled, report
        case intervalMin = "interval_min"
        case allowedResources = "allowed_resources"
    }
}

struct AgentReport: Codable {
    let agentName: String?
    let status: String?
    let summary: String?
    let alerts: [String]?
    let recommendations: [String]?
    let timestamp: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case agentName = "agent_name"
        case status, summary, alerts, recommendations, timestamp, error
    }
}

// MARK: - Agent Run Result

struct AgentRunResult: Codable {
    let agentName: String
    let status: String
    let summary: String
    let alerts: [String]?
    let recommendations: [String]?
    let actionsTaken: [String]?
    let timestamp: String?

    enum CodingKeys: String, CodingKey {
        case agentName = "agent_name"
        case status, summary, alerts, recommendations, timestamp
        case actionsTaken = "actions_taken"
    }
}

struct AgentRunAllResult: Codable {
    let agentName: String
    let status: String
    let summary: String
    let alerts: [String]?

    enum CodingKeys: String, CodingKey {
        case agentName = "agent_name"
        case status, summary, alerts
    }
}

// MARK: - Audit

struct AuditEntry: Codable, Identifiable {
    var id: String { "\(timestamp)-\(agent)-\(action)" }
    let timestamp: String
    let agent: String
    let action: String
    let severity: String
    let details: String?
    let requiresReview: Bool?

    enum CodingKeys: String, CodingKey {
        case timestamp, agent, action, severity, details
        case requiresReview = "requires_review"
    }
}

struct AuditSummary: Codable {
    let summary: String
}

// MARK: - H.O.M.E. L.I.N.K.

struct ServiceHealth: Codable, Identifiable {
    var id: String { service }
    let service: String
    let circuitState: String
    let successRate: Double
    let avgLatencyMs: Double
    let rateLimitRemaining: Int?
    let riskScore: Int

    enum CodingKeys: String, CodingKey {
        case service
        case circuitState = "circuit_state"
        case successRate = "success_rate"
        case avgLatencyMs = "avg_latency_ms"
        case rateLimitRemaining = "rate_limit_remaining"
        case riskScore = "risk_score"
    }
}

struct Anomaly: Codable, Identifiable {
    var id: String { "\(service)-\(type)-\(detectedAt)" }
    let service: String
    let type: String
    let description: String
    let severity: String
    let detectedAt: String

    enum CodingKeys: String, CodingKey {
        case service, type, description, severity
        case detectedAt = "detected_at"
    }
}

// MARK: - Vault

struct VaultStatus: Codable {
    let health: [String: AnyCodableValue]
    let credentials: [CredentialMeta]
}

struct CredentialMeta: Codable, Identifiable {
    var id: String { keyName }
    let keyName: String
    let service: String
    let scope: String
    let createdAt: String?
    let rotatedAt: String?
    let expiresAt: String?
    let rotationDays: Int?

    enum CodingKeys: String, CodingKey {
        case keyName = "key_name"
        case service, scope
        case createdAt = "created_at"
        case rotatedAt = "rotated_at"
        case expiresAt = "expires_at"
        case rotationDays = "rotation_days"
    }
}

// MARK: - Registry

struct Integration: Codable, Identifiable {
    var id: String { name }
    let name: String
    let description: String
    let baseUrl: String
    let authMethod: String
    let ownerAgent: String
    let status: String
    let threatCount: Int
    let vaultKeys: [String]

    enum CodingKeys: String, CodingKey {
        case name, description, status
        case baseUrl = "base_url"
        case authMethod = "auth_method"
        case ownerAgent = "owner_agent"
        case threatCount = "threat_count"
        case vaultKeys = "vault_keys"
    }
}

struct ThreatDetail: Codable {
    let name: String
    let threats: [Threat]
    let failureImpact: String?
    let rollbackProcedure: String?

    enum CodingKeys: String, CodingKey {
        case name, threats
        case failureImpact = "failure_impact"
        case rollbackProcedure = "rollback_procedure"
    }
}

struct Threat: Codable, Identifiable {
    var id: String { risk }
    let risk: String
    let severity: String
    let mitigation: String
}

// MARK: - Config

struct AppConfig: Codable {
    let owner: String
    let timezone: String
    let dailySummaryHour: Int?
    let dataDir: String?
    let logDir: String?
    let agents: [String: AgentConfigEntry]?

    enum CodingKeys: String, CodingKey {
        case owner, timezone, agents
        case dailySummaryHour = "daily_summary_hour"
        case dataDir = "data_dir"
        case logDir = "log_dir"
    }
}

struct AgentConfigEntry: Codable {
    let enabled: Bool
    let scheduleIntervalMinutes: Int?
    let allowedResources: [String]?

    enum CodingKeys: String, CodingKey {
        case enabled
        case scheduleIntervalMinutes = "schedule_interval_minutes"
        case allowedResources = "allowed_resources"
    }
}

// MARK: - Chat

struct ChatRequest: Codable {
    let message: String
    let useAi: Bool

    enum CodingKeys: String, CodingKey {
        case message
        case useAi = "use_ai"
    }
}

struct ChatResponse: Codable {
    let response: String
    let type: String?
}

// MARK: - Daily Summary

struct DailySummary: Codable {
    let summary: String
}

// MARK: - Flexible JSON Value

enum AnyCodableValue: Codable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let v = try? container.decode(Bool.self) { self = .bool(v) }
        else if let v = try? container.decode(Int.self) { self = .int(v) }
        else if let v = try? container.decode(Double.self) { self = .double(v) }
        else if let v = try? container.decode(String.self) { self = .string(v) }
        else { self = .null }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let v): try container.encode(v)
        case .int(let v): try container.encode(v)
        case .double(let v): try container.encode(v)
        case .bool(let v): try container.encode(v)
        case .null: try container.encodeNil()
        }
    }

    var displayString: String {
        switch self {
        case .string(let v): return v
        case .int(let v): return "\(v)"
        case .double(let v): return String(format: "%.1f", v)
        case .bool(let v): return v ? "true" : "false"
        case .null: return "—"
        }
    }
}
