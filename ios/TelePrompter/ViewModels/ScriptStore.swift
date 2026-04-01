import Foundation

/// Manages script state, handles API sync + local caching
@MainActor
final class ScriptStore: ObservableObject {
    @Published var scripts: [Script] = []
    @Published var isLoading = false
    @Published var error: String?

    private var apiService: GuardianAPIService?
    private let localDB = LocalDatabase()

    func configure(api: GuardianAPIService) {
        self.apiService = api
    }

    func loadScripts(category: ScriptCategory? = nil) async {
        guard let api = apiService else { return }
        isLoading = true
        error = nil
        do {
            scripts = try await api.fetchScripts(category: category)
            localDB.cacheScripts(scripts)
        } catch {
            // Fall back to cached scripts
            scripts = localDB.cachedScripts
            self.error = "Offline — showing cached scripts"
        }
        isLoading = false
    }

    func generateScript(scenario: String, category: ScriptCategory,
                        chiefComplaint: String, age: String, setting: String) async -> Script? {
        guard let api = apiService else { return nil }
        isLoading = true
        do {
            let script = try await api.generateScript(
                scenario: scenario, category: category,
                chiefComplaint: chiefComplaint, age: age, setting: setting
            )
            scripts.insert(script, at: 0)
            isLoading = false
            return script
        } catch {
            self.error = "Failed to generate script"
            isLoading = false
            return nil
        }
    }

    func deleteScript(_ script: Script) async {
        guard let api = apiService else { return }
        do {
            try await api.deleteScript(id: script.id)
            scripts.removeAll { $0.id == script.id }
        } catch {
            self.error = "Failed to delete script"
        }
    }
}
