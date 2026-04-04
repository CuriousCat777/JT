import SwiftUI

struct VaultView: View {
    @Environment(APIClient.self) private var api
    @State private var vault: VaultStatus?
    @State private var isLoading = true
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if let error { ErrorBanner(message: error) }

                if let vault {
                    // Health stats
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 3), spacing: 12) {
                        StatCard("Credentials", value: "\(vault.credentials.count)", color: .blue)
                        let needRotation = vault.credentials.filter { ($0.rotationDays ?? 0) > 0 }.count
                        StatCard("With Rotation", value: "\(needRotation)", color: .green)
                        StatCard("Encryption", value: "Fernet", subtitle: "PBKDF2 derived", color: .purple)
                    }

                    // Credential table
                    VStack(alignment: .leading, spacing: 12) {
                        SectionHeader(title: "Credentials (metadata only)")
                        Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 10) {
                            GridRow {
                                Text("KEY").headerStyle()
                                Text("SERVICE").headerStyle()
                                Text("SCOPE").headerStyle()
                                Text("CREATED").headerStyle()
                                Text("ROTATED").headerStyle()
                                Text("ROTATION").headerStyle()
                            }
                            Divider()
                            ForEach(vault.credentials) { cred in
                                GridRow {
                                    Text(cred.keyName)
                                        .font(.callout)
                                        .fontWeight(.medium)
                                    Text(cred.service)
                                        .font(.callout)
                                    Text(cred.scope)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Text(cred.createdAt?.prefix(10) ?? "—")
                                        .font(.caption)
                                        .monospacedDigit()
                                    Text(cred.rotatedAt?.prefix(10) ?? "—")
                                        .font(.caption)
                                        .monospacedDigit()
                                    Text(cred.rotationDays.map { "\($0)d" } ?? "—")
                                        .font(.caption)
                                        .monospacedDigit()
                                }
                            }
                        }
                    }
                    .padding()
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
                }
            }
            .padding(24)
        }
        .navigationTitle("Vault")
        .refreshable { await load() }
        .task { await load() }
        .overlay { if isLoading { LoadingView() } }
    }

    private func load() async {
        isLoading = true
        error = nil
        do { vault = try await api.fetchVault() }
        catch { self.error = error.localizedDescription }
        isLoading = false
    }
}

private extension Text {
    func headerStyle() -> some View {
        self.font(.caption2)
            .fontWeight(.bold)
            .foregroundStyle(.secondary)
    }
}
