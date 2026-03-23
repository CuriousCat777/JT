import SwiftUI

struct SettingsView: View {
    @Environment(APIClient.self) private var api
    @State private var serverURL: String = ""
    @State private var testResult: TestResult?
    @State private var isTesting = false

    enum TestResult {
        case success(String)
        case failure(String)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text("Settings")
                    .font(.title2)
                    .fontWeight(.bold)

                // Server connection
                VStack(alignment: .leading, spacing: 16) {
                    SectionHeader(title: "Server Connection")

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Guardian One Server URL")
                            .font(.callout)
                            .fontWeight(.medium)
                        Text("The Flask backend that powers Guardian One. This runs on your machine or server.")
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        HStack(spacing: 12) {
                            TextField("http://localhost:5100", text: $serverURL)
                                .textFieldStyle(.roundedBorder)
                                .onSubmit { saveURL() }

                            Button("Save") { saveURL() }
                                .buttonStyle(.borderedProminent)

                            Button("Test") { Task { await testConnection() } }
                                .buttonStyle(.bordered)
                                .disabled(isTesting)
                        }
                    }

                    if let result = testResult {
                        switch result {
                        case .success(let msg):
                            HStack(spacing: 8) {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(.green)
                                Text(msg)
                                    .font(.caption)
                                    .foregroundStyle(.green)
                            }
                        case .failure(let msg):
                            HStack(spacing: 8) {
                                Image(systemName: "xmark.circle.fill")
                                    .foregroundStyle(.red)
                                Text(msg)
                                    .font(.caption)
                                    .foregroundStyle(.red)
                            }
                        }
                    }
                }
                .padding()
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))

                // Quick reference
                VStack(alignment: .leading, spacing: 12) {
                    SectionHeader(title: "Quick Reference")
                    referenceRow("Start server", "python main.py --devpanel")
                    referenceRow("Custom port", "python main.py --devpanel --port 8080")
                    referenceRow("Daemon mode", "python main.py --daemon")
                    referenceRow("Default URL", "http://localhost:5100")
                }
                .padding()
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))

                // About
                VStack(alignment: .leading, spacing: 8) {
                    SectionHeader(title: "About")
                    Text("Guardian One")
                        .font(.callout)
                        .fontWeight(.semibold)
                    Text("Sovereign AI Orchestration Platform")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("Built for Jeremy Paulo Salvino Tabernero")
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
                .padding()
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
            }
            .padding(24)
        }
        .navigationTitle("Settings")
        .onAppear { serverURL = api.baseURL }
    }

    private func saveURL() {
        let trimmed = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        api.baseURL = trimmed
        testResult = .success("URL saved: \(trimmed)")
    }

    private func testConnection() async {
        isTesting = true
        testResult = nil
        do {
            let status = try await api.fetchStatus()
            testResult = .success("Connected. Owner: \(status.owner), \(status.agents.count) agents online.")
        } catch {
            testResult = .failure("Connection failed: \(error.localizedDescription)")
        }
        isTesting = false
    }

    private func referenceRow(_ label: String, _ command: String) -> some View {
        HStack {
            Text(label)
                .font(.callout)
                .foregroundStyle(.secondary)
                .frame(width: 120, alignment: .leading)
            Text(command)
                .font(.system(.caption, design: .monospaced))
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.secondary.opacity(0.08))
                .clipShape(RoundedRectangle(cornerRadius: 4))
        }
    }
}
