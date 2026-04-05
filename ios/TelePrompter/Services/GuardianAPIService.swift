import Foundation

/// API client for Guardian One teleprompter endpoints
final class GuardianAPIService: ObservableObject {
    private let baseURL: String
    private var token: String
    private let session: URLSession
    private let decoder: JSONDecoder

    init(baseURL: String, token: String) {
        self.baseURL = baseURL
        self.token = token

        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        self.session = URLSession(configuration: config)

        self.decoder = JSONDecoder()
        self.decoder.dateDecodingStrategy = .iso8601
    }

    func updateToken(_ newToken: String) {
        self.token = newToken
        KeychainService.store(key: "guardian_api_token", value: newToken)
    }

    // MARK: - Scripts

    func fetchScripts(category: ScriptCategory? = nil) async throws -> [Script] {
        var path = "/api/scripts"
        if let cat = category { path += "?category=\(cat.rawValue)" }
        return try await get(path)
    }

    func fetchScript(id: String) async throws -> Script {
        return try await get("/api/scripts/\(id)")
    }

    func createScript(title: String, category: ScriptCategory, scenario: String,
                      content: String, tags: [String] = []) async throws -> Script {
        let body: [String: Any] = [
            "title": title,
            "category": category.rawValue,
            "scenario": scenario,
            "content": content,
            "tags": tags,
        ]
        return try await post("/api/scripts", body: body)
    }

    func deleteScript(id: String) async throws {
        let _: [String: Bool] = try await delete("/api/scripts/\(id)")
    }

    // MARK: - Script Generation

    func generateScript(scenario: String, category: ScriptCategory,
                        chiefComplaint: String = "", age: String = "",
                        setting: String = "") async throws -> Script {
        let body: [String: Any] = [
            "scenario": scenario,
            "category": category.rawValue,
            "chief_complaint": chiefComplaint,
            "patient_profile": ["age": age],
            "setting": setting.isEmpty ? category.rawValue : setting,
        ]
        return try await post("/api/generate-script", body: body)
    }

    // MARK: - Coaching

    func getCoaching(currentSection: String = "", transcript: String = "",
                     patientTone: String = "",
                     physicianPhrasing: String = "") async throws -> CoachingResponse {
        let body: [String: Any] = [
            "current_section": currentSection,
            "transcript": transcript,
            "patient_tone": patientTone,
            "physician_phrasing": physicianPhrasing,
        ]
        return try await post("/api/coach", body: body)
    }

    // MARK: - Practice Sessions

    func startSession(scriptId: String) async throws -> PracticeSession {
        return try await post("/api/sessions/start", body: ["script_id": scriptId])
    }

    func completeSession(sessionId: String, durationSeconds: Int,
                         selfRating: Int, notes: String = "") async throws -> PracticeSession {
        let body: [String: Any] = [
            "session_id": sessionId,
            "duration_seconds": durationSeconds,
            "self_rating": selfRating,
            "notes": notes,
        ]
        return try await post("/api/sessions/complete", body: body)
    }

    func fetchSessions(scriptId: String? = nil, limit: Int = 50) async throws -> [PracticeSession] {
        var path = "/api/sessions?limit=\(limit)"
        if let sid = scriptId { path += "&script_id=\(sid)" }
        return try await get(path)
    }

    func fetchStats() async throws -> PracticeStats {
        return try await get("/api/stats")
    }

    // MARK: - Encounter Logging

    func logEncounter(_ encounter: EncounterLog) async throws {
        let body: [String: Any] = [
            "encounter_type": encounter.encounterType,
            "script_id": encounter.scriptId,
            "complexity_score": encounter.complexityScore,
            "duration_seconds": encounter.durationSeconds,
            "outcome_score": encounter.outcomeScore,
            "ai_suggestions": encounter.aiSuggestions,
            "notes": encounter.notes,
        ]
        let _: [String: Any] = try await post("/api/log-encounter", body: body)
    }

    // MARK: - Advisory

    func getAdvisory(scenario: String, context: String = "") async throws -> AdvisoryTip {
        struct Response: Codable {
            let tip_id: String
            let advice: String
            let scenario: String
        }
        let resp: Response = try await post("/api/advisory",
                                            body: ["scenario": scenario, "context": context])
        return AdvisoryTip(
            id: resp.tip_id,
            category: "advisory",
            content: resp.advice,
            scenario: resp.scenario,
            createdAt: Date()
        )
    }

    func fetchTips(limit: Int = 20) async throws -> [AdvisoryTip] {
        return try await get("/api/tips?limit=\(limit)")
    }

    // MARK: - Health

    func healthCheck() async throws -> Bool {
        struct Health: Codable { let status: String }
        let h: Health = try await get("/api/health")
        return h.status == "ok"
    }

    // MARK: - HTTP helpers

    private func get<T: Decodable>(_ path: String) async throws -> T {
        var request = URLRequest(url: URL(string: "\(baseURL)\(path)")!)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, _) = try await session.data(for: request)
        return try decoder.decode(T.self, from: data)
    }

    private func post<T: Decodable>(_ path: String, body: [String: Any]) async throws -> T {
        var request = URLRequest(url: URL(string: "\(baseURL)\(path)")!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, _) = try await session.data(for: request)
        return try decoder.decode(T.self, from: data)
    }

    private func delete<T: Decodable>(_ path: String) async throws -> T {
        var request = URLRequest(url: URL(string: "\(baseURL)\(path)")!)
        request.httpMethod = "DELETE"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, _) = try await session.data(for: request)
        return try decoder.decode(T.self, from: data)
    }
}
