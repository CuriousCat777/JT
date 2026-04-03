import SwiftUI

struct MorningBriefView: View {
    @Environment(APIClient.self) private var api
    @State private var status: SystemStatus?
    @State private var agents: [AgentDetail] = []
    @State private var health: [ServiceHealth] = []
    @State private var audit: [AuditEntry] = []
    @State private var error: String?
    @State private var isLoading = true

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Greeting
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(greeting()), Jeremy.")
                        .font(.title)
                        .fontWeight(.bold)
                    Text(Date(), format: .dateTime.weekday(.wide).month(.wide).day().year())
                        .foregroundStyle(.secondary)
                }

                if let error {
                    ErrorBanner(message: error)
                }

                // Quick stats
                if let status {
                    LazyVGrid(columns: [
                        GridItem(.flexible()),
                        GridItem(.flexible()),
                        GridItem(.flexible()),
                        GridItem(.flexible()),
                    ], spacing: 12) {
                        StatCard("Agents", value: "\(status.agents.count)",
                                subtitle: "\(status.agents.filter { $0.enabled }.count) enabled",
                                color: .blue)
                        StatCard("Audit Events", value: "\(audit.count)",
                                subtitle: "recent entries",
                                color: .purple)
                        StatCard("Services", value: "\(health.count)",
                                subtitle: "\(health.filter { $0.circuitState == "closed" }.count) healthy",
                                color: .green)
                        let avgSuccess = health.isEmpty ? 1.0 : health.map(\.successRate).reduce(0, +) / Double(health.count)
                        StatCard("Success Rate", value: "\(Int(avgSuccess * 100))%",
                                subtitle: "across all services",
                                color: avgSuccess > 0.95 ? .green : .orange)
                    }
                }

                // Two-column: Websites + Agents
                HStack(alignment: .top, spacing: 16) {
                    // Websites
                    VStack(alignment: .leading, spacing: 12) {
                        SectionHeader(title: "Websites")
                        WebsiteRow(name: "jtmdai.com", desc: "JTMD AI — Business", status: "LIVE", isUp: true)
                        Divider()
                        WebsiteRow(name: "drjeremytabernero.org", desc: "Personal & Professional", status: "DOWN", isUp: false)
                    }
                    .padding()
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))

                    // Agent status
                    VStack(alignment: .leading, spacing: 8) {
                        SectionHeader(title: "Agent Status")
                        ForEach(agents) { agent in
                            HStack {
                                Text(agent.name)
                                    .font(.callout)
                                    .fontWeight(.medium)
                                Spacer()
                                StatusBadge(agent.status)
                            }
                            if agent.id != agents.last?.id {
                                Divider()
                            }
                        }
                    }
                    .padding()
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
                }

                // Service health
                VStack(alignment: .leading, spacing: 12) {
                    SectionHeader(title: "Service Health")
                    ServiceHealthTable(services: health)
                }
                .padding()
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))

                // Recent audit
                VStack(alignment: .leading, spacing: 8) {
                    SectionHeader(title: "Recent Activity")
                    ForEach(audit.prefix(8)) { entry in
                        HStack(spacing: 12) {
                            Text(entry.timestamp.prefix(19).replacingOccurrences(of: "T", with: " "))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .monospacedDigit()
                            Text(entry.agent)
                                .font(.caption)
                                .fontWeight(.medium)
                                .foregroundStyle(.blue)
                                .frame(width: 100, alignment: .leading)
                            StatusBadge(entry.severity)
                            Text(entry.action)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }
                }
                .padding()
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
            }
            .padding(24)
        }
        .navigationTitle("Morning Brief")
        .refreshable { await loadAll() }
        .task { await loadAll() }
        .overlay { if isLoading { LoadingView() } }
    }

    private func loadAll() async {
        isLoading = true
        error = nil
        do {
            async let s = api.fetchStatus()
            async let a = api.fetchAgents()
            async let h = api.fetchServiceHealth()
            async let au = api.fetchAudit(limit: 15)
            status = try await s
            agents = try await a
            health = try await h
            audit = try await au
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }
}

// MARK: - Subviews

struct WebsiteRow: View {
    let name: String
    let desc: String
    let status: String
    let isUp: Bool

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(name)
                    .font(.callout)
                    .fontWeight(.semibold)
                Text(desc)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            StatusBadge(status, color: isUp ? .green : .red)
        }
    }
}

struct ServiceHealthTable: View {
    let services: [ServiceHealth]

    var body: some View {
        Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 10) {
            GridRow {
                Text("SERVICE").font(.caption2).fontWeight(.bold).foregroundStyle(.secondary)
                Text("CIRCUIT").font(.caption2).fontWeight(.bold).foregroundStyle(.secondary)
                Text("SUCCESS").font(.caption2).fontWeight(.bold).foregroundStyle(.secondary)
                Text("LATENCY").font(.caption2).fontWeight(.bold).foregroundStyle(.secondary)
                Text("RISK").font(.caption2).fontWeight(.bold).foregroundStyle(.secondary)
            }
            Divider()
            ForEach(services) { svc in
                GridRow {
                    Text(svc.service)
                        .font(.callout)
                    StatusBadge(svc.circuitState)
                    Text("\(Int(svc.successRate * 100))%")
                        .font(.callout)
                        .monospacedDigit()
                    Text("\(Int(svc.avgLatencyMs)) ms")
                        .font(.callout)
                        .monospacedDigit()
                    RiskMeter(score: svc.riskScore)
                }
            }
        }
    }
}
