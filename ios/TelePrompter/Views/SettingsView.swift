import SwiftUI

/// Settings for Guardian One connection and app preferences
struct SettingsView: View {
    @AppStorage("guardian_api_url") private var apiURL = "http://localhost:5200"
    @State private var apiToken = ""
    @State private var connectionStatus: ConnectionStatus = .unknown
    @EnvironmentObject var appState: AppState

    enum ConnectionStatus {
        case unknown, checking, connected, failed
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Guardian One Connection") {
                    TextField("API URL", text: $apiURL)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    SecureField("API Token", text: $apiToken)
                        .textInputAutocapitalization(.never)

                    Button {
                        saveAndTest()
                    } label: {
                        HStack {
                            Text("Test Connection")
                            Spacer()
                            switch connectionStatus {
                            case .unknown:
                                Image(systemName: "circle").foregroundStyle(.gray)
                            case .checking:
                                ProgressView()
                            case .connected:
                                Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                            case .failed:
                                Image(systemName: "xmark.circle.fill").foregroundStyle(.red)
                            }
                        }
                    }
                }

                Section("Data") {
                    Button("Sync to Guardian One") {
                        Task { await appState.practiceStore.syncToGuardianOne() }
                    }
                }

                Section("About") {
                    LabeledContent("App", value: "TelePrompter v1.0")
                    LabeledContent("System", value: "Guardian One")
                    LabeledContent("Built for", value: "Dr. Jeremy Tabernero")
                }
            }
            .navigationTitle("Settings")
            .onAppear {
                apiToken = KeychainService.retrieve(key: "guardian_api_token") ?? ""
            }
        }
    }

    private func saveAndTest() {
        if !apiToken.isEmpty {
            appState.apiService.updateToken(apiToken)
        }
        connectionStatus = .checking
        Task {
            do {
                let ok = try await appState.apiService.healthCheck()
                connectionStatus = ok ? .connected : .failed
            } catch {
                connectionStatus = .failed
            }
        }
    }
}
