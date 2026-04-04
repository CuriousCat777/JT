import SwiftUI

struct AuditView: View {
    @Environment(APIClient.self) private var api
    @State private var entries: [AuditEntry] = []
    @State private var agentFilter: String = ""
    @State private var severityFilter: String = ""
    @State private var isLoading = true
    @State private var error: String?

    private let severities = ["", "info", "warning", "error", "critical"]

    var body: some View {
        VStack(spacing: 0) {
            // Filters
            HStack(spacing: 12) {
                TextField("Filter by agent...", text: $agentFilter)
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 200)

                Picker("Severity", selection: $severityFilter) {
                    Text("All Severity").tag("")
                    ForEach(severities.dropFirst(), id: \.self) { s in
                        Text(s.capitalized).tag(s)
                    }
                }
                .frame(maxWidth: 160)

                Button("Apply") { Task { await load() } }
                    .buttonStyle(.bordered)

                Spacer()

                Text("\(entries.count) entries")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding()

            Divider()

            // Log entries
            if let error {
                ErrorBanner(message: error).padding()
            }

            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(entries) { entry in
                        HStack(spacing: 14) {
                            Text(entry.timestamp.prefix(19).replacingOccurrences(of: "T", with: " "))
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(.secondary)
                                .frame(width: 160, alignment: .leading)

                            Text(entry.agent)
                                .font(.caption)
                                .fontWeight(.medium)
                                .foregroundStyle(.blue)
                                .frame(width: 100, alignment: .leading)

                            StatusBadge(entry.severity)
                                .frame(width: 80, alignment: .leading)

                            Text(entry.action)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)

                            Spacer()
                        }
                        .padding(.horizontal)
                        .padding(.vertical, 8)

                        Divider().padding(.leading)
                    }
                }
            }
        }
        .navigationTitle("Audit Log")
        .task { await load() }
        .overlay { if isLoading { LoadingView() } }
    }

    private func load() async {
        isLoading = true
        error = nil
        do {
            entries = try await api.fetchAudit(
                agent: agentFilter.isEmpty ? nil : agentFilter,
                severity: severityFilter.isEmpty ? nil : severityFilter,
                limit: 200
            )
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }
}

struct ConfigView: View {
    @Environment(APIClient.self) private var api
    @State private var config: AppConfig?
    @State private var isLoading = true
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let error { ErrorBanner(message: error) }

                if let config {
                    VStack(alignment: .leading, spacing: 12) {
                        SectionHeader(title: "System")
                        configRow("Owner", config.owner)
                        configRow("Timezone", config.timezone)
                        if let hour = config.dailySummaryHour {
                            configRow("Daily Summary Hour", "\(hour):00")
                        }
                        if let dir = config.dataDir { configRow("Data Dir", dir) }
                        if let dir = config.logDir { configRow("Log Dir", dir) }
                    }
                    .padding()
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))

                    if let agents = config.agents, !agents.isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
                            SectionHeader(title: "Agent Configuration")
                            ForEach(agents.sorted(by: { $0.key < $1.key }), id: \.key) { name, cfg in
                                HStack {
                                    Text(name)
                                        .font(.callout)
                                        .fontWeight(.medium)
                                    Spacer()
                                    if let interval = cfg.scheduleIntervalMinutes {
                                        Text("\(interval) min")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    StatusBadge(cfg.enabled ? "enabled" : "disabled")
                                }
                                if name != agents.sorted(by: { $0.key < $1.key }).last?.key {
                                    Divider()
                                }
                            }
                        }
                        .padding()
                        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
                    }
                }
            }
            .padding(24)
        }
        .navigationTitle("Config")
        .task { await load() }
        .overlay { if isLoading { LoadingView() } }
    }

    private func load() async {
        isLoading = true
        do { config = try await api.fetchConfig() }
        catch { self.error = error.localizedDescription }
        isLoading = false
    }

    private func configRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label)
                .font(.callout)
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.callout)
                .fontWeight(.medium)
        }
    }
}
