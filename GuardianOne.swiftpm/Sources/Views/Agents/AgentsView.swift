import SwiftUI

struct AgentsView: View {
    @Environment(APIClient.self) private var api
    @State private var agents: [AgentDetail] = []
    @State private var isLoading = true
    @State private var error: String?
    @State private var runningAgent: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text("Agents")
                        .font(.title2)
                        .fontWeight(.bold)
                    Spacer()
                    Button("Run All") { Task { await runAll() } }
                        .buttonStyle(.borderedProminent)
                        .disabled(runningAgent != nil)
                }

                if let error {
                    ErrorBanner(message: error)
                }

                LazyVGrid(columns: [
                    GridItem(.flexible(), spacing: 16),
                    GridItem(.flexible(), spacing: 16),
                ], spacing: 16) {
                    ForEach(agents) { agent in
                        AgentCard(
                            agent: agent,
                            isRunning: runningAgent == agent.name,
                            onRun: { await runAgent(agent.name) }
                        )
                    }
                }
            }
            .padding(24)
        }
        .navigationTitle("Agents")
        .refreshable { await load() }
        .task { await load() }
        .overlay { if isLoading { LoadingView() } }
    }

    private func load() async {
        isLoading = true
        error = nil
        do { agents = try await api.fetchAgents() }
        catch { self.error = error.localizedDescription }
        isLoading = false
    }

    private func runAgent(_ name: String) async {
        runningAgent = name
        do {
            _ = try await api.runAgent(name)
            await load()
        } catch {
            self.error = error.localizedDescription
        }
        runningAgent = nil
    }

    private func runAll() async {
        runningAgent = "__all__"
        do {
            _ = try await api.runAllAgents()
            await load()
        } catch {
            self.error = error.localizedDescription
        }
        runningAgent = nil
    }
}

// MARK: - Agent Card

struct AgentCard: View {
    let agent: AgentDetail
    let isRunning: Bool
    let onRun: () async -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Header
            HStack {
                Text(agent.name)
                    .font(.headline)
                Spacer()
                StatusBadge(agent.status)
            }

            // Report summary
            if let report = agent.report {
                if let summary = report.summary {
                    Text(summary)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(3)
                }
                if let alerts = report.alerts, !alerts.isEmpty {
                    ForEach(alerts.prefix(3), id: \.self) { alert in
                        HStack(spacing: 6) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .font(.caption2)
                                .foregroundStyle(.orange)
                            Text(alert)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }
                }
            }

            // Resource tags
            if !agent.allowedResources.isEmpty {
                HStack(spacing: 6) {
                    ForEach(agent.allowedResources, id: \.self) { res in
                        Text(res)
                            .font(.system(size: 10, design: .monospaced))
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.secondary.opacity(0.1))
                            .clipShape(RoundedRectangle(cornerRadius: 4))
                    }
                }
            }

            // Meta + Run
            HStack {
                if let interval = agent.intervalMin {
                    Text("Every \(interval) min")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
                Spacer()
                Button {
                    Task { await onRun() }
                } label: {
                    if isRunning {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Label("Run", systemImage: "play.fill")
                    }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(isRunning || !agent.enabled)
            }
        }
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
        .opacity(agent.enabled ? 1 : 0.5)
    }
}
