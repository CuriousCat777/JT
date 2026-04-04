import Foundation

/// Records a single practice test session
struct PracticeSession: Identifiable, Codable {
    let id: String
    var scriptId: String
    var scriptTitle: String
    var startedAt: Date
    var completedAt: Date?
    var durationSeconds: Int
    var selfRating: Int
    var aiFeedback: String
    var areasOfStrength: [String]
    var areasToImprove: [String]
    var notes: String
    var completed: Bool

    enum CodingKeys: String, CodingKey {
        case id = "session_id"
        case scriptId = "script_id"
        case scriptTitle = "script_title"
        case startedAt = "started_at"
        case completedAt = "completed_at"
        case durationSeconds = "duration_seconds"
        case selfRating = "self_rating"
        case aiFeedback = "ai_feedback"
        case areasOfStrength = "areas_of_strength"
        case areasToImprove = "areas_to_improve"
        case notes, completed
    }
}

/// Aggregate practice metrics
struct PracticeStats: Codable {
    var totalSessions: Int
    var averageRating: Double
    var bestRating: Int
    var totalPracticeMinutes: Double
    var sessionsThisWeek: Int
    var categoriesPracticed: [String: Int]

    enum CodingKeys: String, CodingKey {
        case totalSessions = "total_sessions"
        case averageRating = "average_rating"
        case bestRating = "best_rating"
        case totalPracticeMinutes = "total_practice_minutes"
        case sessionsThisWeek = "sessions_this_week"
        case categoriesPracticed = "categories_practiced"
    }
}

/// Encounter data logged to Guardian One
struct EncounterLog: Codable {
    var encounterType: String
    var scriptId: String
    var complexityScore: Int
    var durationSeconds: Int
    var outcomeScore: Int
    var aiSuggestions: String
    var notes: String

    enum CodingKeys: String, CodingKey {
        case encounterType = "encounter_type"
        case scriptId = "script_id"
        case complexityScore = "complexity_score"
        case durationSeconds = "duration_seconds"
        case outcomeScore = "outcome_score"
        case aiSuggestions = "ai_suggestions"
        case notes
    }
}
