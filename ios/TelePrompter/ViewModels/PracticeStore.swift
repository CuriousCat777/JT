import Foundation

/// Manages practice session state + analytics
@MainActor
final class PracticeStore: ObservableObject {
    @Published var sessions: [PracticeSession] = []
    @Published var stats: PracticeStats?
    @Published var isLoading = false

    private var apiService: GuardianAPIService?
    private let localDB = LocalDatabase()

    func configure(api: GuardianAPIService) {
        self.apiService = api
    }

    func loadStats() async {
        guard let api = apiService else { return }
        isLoading = true
        do {
            stats = try await api.fetchStats()
            sessions = try await api.fetchSessions(limit: 30)
        } catch {
            // Use local metrics as fallback
            stats = PracticeStats(
                totalSessions: localDB.encounters.count,
                averageRating: 0,
                bestRating: 0,
                totalPracticeMinutes: 0,
                sessionsThisWeek: 0,
                categoriesPracticed: [:]
            )
        }
        isLoading = false
    }

    func startSession(scriptId: String) async -> PracticeSession? {
        guard let api = apiService else { return nil }
        return try? await api.startSession(scriptId: scriptId)
    }

    func completeSession(sessionId: String, duration: Int,
                         rating: Int, notes: String) async -> PracticeSession? {
        guard let api = apiService else { return nil }
        do {
            let session = try await api.completeSession(
                sessionId: sessionId, durationSeconds: duration,
                selfRating: rating, notes: notes
            )
            // Also log locally
            localDB.recordEncounter(LocalEncounter(
                id: session.id,
                timestamp: Date(),
                encounterType: session.scriptTitle,
                complexityScore: 0,
                scriptUsed: session.scriptId,
                aiSuggestions: session.aiFeedback,
                outcomeScore: rating,
                notes: notes,
                synced: true
            ))
            return session
        } catch {
            return nil
        }
    }

    /// Sync unsynced local encounters to Guardian One
    func syncToGuardianOne() async {
        guard let api = apiService else { return }
        let unsynced = localDB.unsyncedEncounters()
        var syncedIds: [String] = []

        for encounter in unsynced {
            let log = EncounterLog(
                encounterType: encounter.encounterType,
                scriptId: encounter.scriptUsed,
                complexityScore: encounter.complexityScore,
                durationSeconds: encounter.complexityScore * 60,
                outcomeScore: encounter.outcomeScore,
                aiSuggestions: encounter.aiSuggestions,
                notes: encounter.notes
            )
            do {
                try await api.logEncounter(log)
                syncedIds.append(encounter.id)
            } catch {
                break // Stop on first failure
            }
        }

        if !syncedIds.isEmpty {
            localDB.markSynced(ids: syncedIds)
        }
    }
}
