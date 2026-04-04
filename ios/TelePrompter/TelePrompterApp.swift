import SwiftUI

@main
struct TelePrompterApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
                .preferredColorScheme(.dark)
        }
    }
}

/// Root application state shared across views
final class AppState: ObservableObject {
    @Published var selectedTab: Tab = .scripts
    @Published var isLoading = false

    let scriptStore = ScriptStore()
    let practiceStore = PracticeStore()
    let apiService: GuardianAPIService

    enum Tab: Hashable {
        case scripts, generate, practice, advisory
    }

    init() {
        let baseURL = UserDefaults.standard.string(forKey: "guardian_api_url")
            ?? "http://localhost:5200"
        let token = KeychainService.retrieve(key: "guardian_api_token") ?? ""
        self.apiService = GuardianAPIService(baseURL: baseURL, token: token)
    }
}
