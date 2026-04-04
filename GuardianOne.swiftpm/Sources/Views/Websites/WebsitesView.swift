import SwiftUI

struct WebsitesView: View {
    @Environment(APIClient.self) private var api

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Website Management")
                    .font(.title2)
                    .fontWeight(.bold)

                LazyVGrid(columns: [
                    GridItem(.flexible(), spacing: 16),
                    GridItem(.flexible(), spacing: 16),
                ], spacing: 16) {
                    WebsiteSiteCard(
                        domain: "jtmdai.com",
                        subtitle: "JTMD AI — AI Solutions & Technology",
                        type: "Business",
                        hosting: "Cloud VPS",
                        pages: ["index", "about", "services", "contact", "case-studies"],
                        features: "Service catalog, case studies, AI demos, contact form",
                        isUp: true
                    )

                    WebsiteSiteCard(
                        domain: "drjeremytabernero.org",
                        subtitle: "Personal & Professional",
                        type: "Professional",
                        hosting: "Cloud VPS",
                        pages: ["index", "about", "contact", "CV", "publications"],
                        features: "CV download, publications list, contact form",
                        isUp: false
                    )
                }
            }
            .padding(24)
        }
        .navigationTitle("Websites")
    }
}

struct WebsiteSiteCard: View {
    let domain: String
    let subtitle: String
    let type: String
    let hosting: String
    let pages: [String]
    let features: String
    let isUp: Bool

    @State private var actionMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            // Header
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(domain)
                        .font(.headline)
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                StatusBadge(isUp ? "LIVE" : "DOWN", color: isUp ? .green : .red)
            }

            // Details
            VStack(alignment: .leading, spacing: 4) {
                detailRow("Type", type)
                detailRow("Hosting", hosting)
                detailRow("Pages", pages.joined(separator: ", "))
                detailRow("Features", features)
            }
            .font(.caption)

            if !isUp {
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                        .font(.caption)
                    Text("Action needed: site is offline")
                        .font(.caption)
                        .foregroundStyle(.red)
                        .fontWeight(.medium)
                }
            }

            // Actions
            HStack(spacing: 8) {
                Button("Build") { actionMessage = "Building \(domain)..." }
                    .buttonStyle(.bordered)
                    .controlSize(.small)

                if !isUp {
                    Button("Deploy Now") { actionMessage = "Deploying \(domain)..." }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                } else {
                    Button("Deploy") { actionMessage = "Deploying \(domain)..." }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                }
            }

            if let msg = actionMessage {
                Text(msg)
                    .font(.caption2)
                    .foregroundStyle(.blue)
                    .transition(.opacity)
            }
        }
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(isUp ? Color.clear : Color.red.opacity(0.3), lineWidth: 1)
        )
    }

    private func detailRow(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top) {
            Text(label + ":")
                .foregroundStyle(.secondary)
                .frame(width: 60, alignment: .leading)
            Text(value)
                .fontWeight(.medium)
        }
    }
}

// MARK: - Finances View

struct FinancesView: View {
    @Environment(APIClient.self) private var api

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Financial Overview")
                    .font(.title2)
                    .fontWeight(.bold)

                // Stats
                LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 3), spacing: 12) {
                    StatCard("Primary Tracker", value: "Rocket Money", subtitle: "API mode, syncing via CFO", color: .blue)
                    StatCard("Providers", value: "3 Active", subtitle: "Plaid, Empower, Rocket Money", color: .green)
                    StatCard("Dashboard", value: "Ready", subtitle: "Excel with password lock", color: .green)
                }

                // Quick actions
                VStack(alignment: .leading, spacing: 12) {
                    SectionHeader(title: "Quick Actions")
                    HStack(spacing: 10) {
                        Button("Run Daily Review") {}
                            .buttonStyle(.bordered)
                        Button("Sync All Accounts") {}
                            .buttonStyle(.bordered)
                        Button("Generate Dashboard") {}
                            .buttonStyle(.bordered)
                        Button("Check Gmail for CSV") {}
                            .buttonStyle(.bordered)
                    }
                }
                .padding()
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))

                // Connected services
                VStack(alignment: .leading, spacing: 12) {
                    SectionHeader(title: "Connected Services")
                    Grid(alignment: .leading, horizontalSpacing: 20, verticalSpacing: 10) {
                        GridRow {
                            Text("SERVICE").font(.caption2).fontWeight(.bold).foregroundStyle(.secondary)
                            Text("TYPE").font(.caption2).fontWeight(.bold).foregroundStyle(.secondary)
                            Text("MODE").font(.caption2).fontWeight(.bold).foregroundStyle(.secondary)
                            Text("STATUS").font(.caption2).fontWeight(.bold).foregroundStyle(.secondary)
                        }
                        Divider()
                        financeRow("Rocket Money", "Account aggregation", "API + CSV fallback")
                        financeRow("Plaid", "Direct bank connections", "OAuth + Link")
                        financeRow("Empower", "Retirement & investments", "API key")
                    }
                }
                .padding()
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
            }
            .padding(24)
        }
        .navigationTitle("Finances")
    }

    private func financeRow(_ name: String, _ type: String, _ mode: String) -> some View {
        GridRow {
            Text(name).font(.callout).fontWeight(.semibold)
            Text(type).font(.callout)
            Text(mode).font(.caption).foregroundStyle(.secondary)
            StatusBadge("Active", color: .green)
        }
    }
}
