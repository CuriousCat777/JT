import Foundation

/// Clinical teleprompter script
struct Script: Identifiable, Codable, Hashable {
    let id: String
    var title: String
    var category: ScriptCategory
    var scenario: String
    var content: String
    var tags: [String]
    var scrollSpeed: Int
    var createdAt: Date
    var updatedAt: Date
    var aiGenerated: Bool
    var notes: String

    enum CodingKeys: String, CodingKey {
        case id = "script_id"
        case title, category, scenario, content, tags
        case scrollSpeed = "scroll_speed"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case aiGenerated = "ai_generated"
        case notes
    }
}

enum ScriptCategory: String, Codable, CaseIterable, Identifiable {
    case admission
    case discharge
    case consult
    case code
    case handoff
    case family
    case badNews = "bad_news"
    case informedConsent = "informed_consent"
    case crossCover = "cross_cover"
    case general

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .admission: return "Admission"
        case .discharge: return "Discharge"
        case .consult: return "Consultation"
        case .code: return "Code / Rapid Response"
        case .handoff: return "Handoff (SBAR)"
        case .family: return "Family Meeting"
        case .badNews: return "Difficult News"
        case .informedConsent: return "Informed Consent"
        case .crossCover: return "Cross-Cover"
        case .general: return "General"
        }
    }

    var iconName: String {
        switch self {
        case .admission: return "person.badge.plus"
        case .discharge: return "arrow.right.circle"
        case .consult: return "phone.badge.waveform"
        case .code: return "bolt.heart"
        case .handoff: return "arrow.left.arrow.right"
        case .family: return "person.3"
        case .badNews: return "exclamationmark.bubble"
        case .informedConsent: return "signature"
        case .crossCover: return "moon.stars"
        case .general: return "doc.text"
        }
    }
}
