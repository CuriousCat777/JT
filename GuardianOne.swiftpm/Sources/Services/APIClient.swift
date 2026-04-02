import Foundation

/// Networking layer for Guardian One's Flask backend API.
@Observable
final class APIClient {
    var baseURL: String {
        didSet { UserDefaults.standard.set(baseURL, forKey: "guardianBaseURL") }
    }

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        return d
    }()

    init() {
        self.baseURL = UserDefaults.standard.string(forKey: "guardianBaseURL")
            ?? "http://localhost:5100"
    }

    // MARK: - Generic Request

    private func request<T: Decodable>(_ path: String, method: String = "GET", body: Data? = nil) async throws -> T {
        guard let url = URL(string: "\(baseURL)\(path)") else {
            throw APIError.invalidURL
        }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.timeoutInterval = 30
        if let body {
            req.httpBody = body
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        guard (200...299).contains(http.statusCode) else {
            throw APIError.httpError(http.statusCode, String(data: data, encoding: .utf8) ?? "")
        }
        return try decoder.decode(T.self, from: data)
    }

    // MARK: - System

    func fetchStatus() async throws -> SystemStatus {
        try await request("/api/status")
    }

    func fetchSummary() async throws -> String {
        let result: DailySummary = try await request("/api/summary")
        return result.summary
    }

    func fetchConfig() async throws -> AppConfig {
        try await request("/api/config")
    }

    // MARK: - Agents

    func fetchAgents() async throws -> [AgentDetail] {
        try await request("/api/agents")
    }

    func runAgent(_ name: String) async throws -> AgentRunResult {
        try await request("/api/agents/\(name)/run", method: "POST")
    }

    func runAllAgents() async throws -> [AgentRunAllResult] {
        try await request("/api/agents/run-all", method: "POST")
    }

    // MARK: - Audit

    func fetchAudit(agent: String? = nil, severity: String? = nil, limit: Int = 100) async throws -> [AuditEntry] {
        var components = URLComponents()
        components.path = "/api/audit"
        var queryItems: [URLQueryItem] = []
        if let agent { queryItems.append(URLQueryItem(name: "agent", value: agent)) }
        if let severity { queryItems.append(URLQueryItem(name: "severity", value: severity)) }
        queryItems.append(URLQueryItem(name: "limit", value: String(limit)))
        components.queryItems = queryItems
        guard let path = components.string else { throw APIError.invalidURL }
        return try await request(path)
    }

    func fetchPendingReviews() async throws -> [AuditEntry] {
        try await request("/api/audit/pending")
    }

    func fetchAuditSummary() async throws -> String {
        let result: AuditSummary = try await request("/api/audit/summary")
        return result.summary
    }

    // MARK: - H.O.M.E. L.I.N.K.

    func fetchServiceHealth() async throws -> [ServiceHealth] {
        try await request("/api/homelink/health")
    }

    func fetchAnomalies() async throws -> [Anomaly] {
        try await request("/api/homelink/anomalies")
    }

    // MARK: - Vault

    func fetchVault() async throws -> VaultStatus {
        try await request("/api/vault")
    }

    // MARK: - Registry

    func fetchRegistry() async throws -> [Integration] {
        try await request("/api/registry")
    }

    func fetchThreats(_ name: String) async throws -> ThreatDetail {
        try await request("/api/registry/\(name)/threats")
    }

    // MARK: - Chat

    func sendChat(message: String, useAI: Bool) async throws -> ChatResponse {
        let body = try JSONEncoder().encode(ChatRequest(message: message, useAi: useAI))
        return try await request("/api/chat", method: "POST", body: body)
    }
}

// MARK: - Errors

enum APIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case httpError(Int, String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid server URL"
        case .invalidResponse: return "Invalid response from server"
        case .httpError(let code, let msg): return "HTTP \(code): \(msg)"
        }
    }
}
