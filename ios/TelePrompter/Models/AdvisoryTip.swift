import Foundation

/// AI-generated communication coaching tip
struct AdvisoryTip: Identifiable, Codable {
    let id: String
    var category: String
    var content: String
    var scenario: String
    var createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id = "tip_id"
        case category, content, scenario
        case createdAt = "created_at"
    }
}

/// Real-time coaching response from the AI
struct CoachingResponse: Codable {
    var tipId: String
    var rephrase: String
    var riskFlag: String
    var optimization: String
    var fullAdvice: String
    var aiProvider: String

    enum CodingKeys: String, CodingKey {
        case tipId = "tip_id"
        case rephrase
        case riskFlag = "risk_flag"
        case optimization
        case fullAdvice = "full_advice"
        case aiProvider = "ai_provider"
    }
}
