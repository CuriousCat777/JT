import SwiftUI

struct RegistryView: View {
    @Environment(APIClient.self) private var api
    @State private var integrations: [Integration] = []
    @State private var selectedThreat: ThreatDetail?
    @State private var isLoading = true
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let error { ErrorBanner(message: error) }

                ForEach(integrations) { integration in
                    IntegrationCard(integration: integration) {
                        await loadThreats(integration.name)
                    }
                }

                // Threat detail sheet
            }
            .padding(24)
        }
        .navigationTitle("Registry")
        .refreshable { await load() }
        .task { await load() }
        .overlay { if isLoading { LoadingView() } }
        .sheet(item: $selectedThreat) { detail in
            ThreatDetailSheet(detail: detail)
        }
    }

    private func load() async {
        isLoading = true
        error = nil
        do { integrations = try await api.fetchRegistry() }
        catch { self.error = error.localizedDescription }
        isLoading = false
    }

    private func loadThreats(_ name: String) async {
        do { selectedThreat = try await api.fetchThreats(name) }
        catch { self.error = error.localizedDescription }
    }
}

extension ThreatDetail: Identifiable {
    var id: String { name }
}

struct IntegrationCard: View {
    let integration: Integration
    let onViewThreats: () async -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(integration.name)
                        .font(.headline)
                    Text(integration.description)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                StatusBadge(integration.status)
            }

            Grid(alignment: .leading, horizontalSpacing: 20, verticalSpacing: 6) {
                GridRow {
                    Text("Auth")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(integration.authMethod)
                        .font(.caption)
                }
                GridRow {
                    Text("Owner")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(integration.ownerAgent)
                        .font(.caption)
                }
                GridRow {
                    Text("Threats")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("\(integration.threatCount)")
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundStyle(integration.threatCount > 0 ? .orange : .green)
                }
            }

            if !integration.vaultKeys.isEmpty {
                HStack(spacing: 6) {
                    ForEach(integration.vaultKeys, id: \.self) { key in
                        Text(key)
                            .font(.system(size: 10, design: .monospaced))
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.purple.opacity(0.1))
                            .clipShape(RoundedRectangle(cornerRadius: 4))
                    }
                }
            }

            if integration.threatCount > 0 {
                Button("View Threats") { Task { await onViewThreats() } }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
            }
        }
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
    }
}

struct ThreatDetailSheet: View {
    let detail: ThreatDetail
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    ForEach(detail.threats) { threat in
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Text(threat.risk)
                                    .font(.callout)
                                    .fontWeight(.semibold)
                                Spacer()
                                StatusBadge(threat.severity)
                            }
                            Text(threat.mitigation)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(12)
                        .background(borderColor(threat.severity).opacity(0.06))
                        .overlay(
                            Rectangle()
                                .fill(borderColor(threat.severity))
                                .frame(width: 3),
                            alignment: .leading
                        )
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                    }

                    if let impact = detail.failureImpact {
                        VStack(alignment: .leading, spacing: 4) {
                            SectionHeader(title: "Failure Impact")
                            Text(impact).font(.callout)
                        }
                    }
                    if let rollback = detail.rollbackProcedure {
                        VStack(alignment: .leading, spacing: 4) {
                            SectionHeader(title: "Rollback Procedure")
                            Text(rollback).font(.callout)
                        }
                    }
                }
                .padding(24)
            }
            .navigationTitle("\(detail.name) — Threats")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        #if os(macOS)
        .frame(minWidth: 500, minHeight: 400)
        #endif
    }

    private func borderColor(_ severity: String) -> Color {
        switch severity.lowercased() {
        case "critical": return .red
        case "high": return .orange
        case "medium": return .yellow
        case "low": return .green
        default: return .secondary
        }
    }
}
