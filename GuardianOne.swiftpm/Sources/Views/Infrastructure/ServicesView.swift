import SwiftUI

struct ServicesView: View {
    @Environment(APIClient.self) private var api
    @State private var services: [ServiceHealth] = []
    @State private var anomalies: [Anomaly] = []
    @State private var isLoading = true
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if let error { ErrorBanner(message: error) }

                // Stats row
                LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 3), spacing: 12) {
                    StatCard("Total Services", value: "\(services.count)", color: .blue)
                    let healthy = services.filter { $0.circuitState == "closed" }.count
                    StatCard("Healthy", value: "\(healthy)/\(services.count)", color: .green)
                    StatCard("Anomalies", value: "\(anomalies.count)",
                            color: anomalies.isEmpty ? .green : .red)
                }

                // Health table
                VStack(alignment: .leading, spacing: 12) {
                    SectionHeader(title: "Service Health")
                    ServiceHealthTable(services: services)
                }
                .padding()
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))

                // Anomalies
                if !anomalies.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        SectionHeader(title: "Active Anomalies")
                        ForEach(anomalies) { anomaly in
                            HStack(spacing: 12) {
                                Image(systemName: "exclamationmark.triangle.fill")
                                    .foregroundStyle(.orange)
                                VStack(alignment: .leading, spacing: 2) {
                                    HStack {
                                        Text(anomaly.service)
                                            .font(.callout)
                                            .fontWeight(.semibold)
                                        StatusBadge(anomaly.severity)
                                    }
                                    Text(anomaly.description)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                            }
                            .padding(12)
                            .background(Color.orange.opacity(0.06))
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                        }
                    }
                    .padding()
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
                }
            }
            .padding(24)
        }
        .navigationTitle("Services")
        .refreshable { await load() }
        .task { await load() }
        .overlay { if isLoading { LoadingView() } }
    }

    private func load() async {
        isLoading = true
        error = nil
        do {
            async let h = api.fetchServiceHealth()
            async let a = api.fetchAnomalies()
            services = try await h
            anomalies = try await a
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }
}
