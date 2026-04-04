import SwiftUI

struct AdvisoryView: View {
    @EnvironmentObject var appState: AppState
    @State private var scenario = ""
    @State private var tips: [AdvisoryTip] = []
    @State private var isLoading = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    // Input section
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Describe a scenario for coaching")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)

                        TextEditor(text: $scenario)
                            .frame(minHeight: 80)
                            .padding(8)
                            .background(Color(.systemGray6))
                            .clipShape(RoundedRectangle(cornerRadius: 12))

                        Button {
                            Task { await askAdvisory() }
                        } label: {
                            HStack {
                                Spacer()
                                if isLoading {
                                    ProgressView()
                                        .padding(.trailing, 8)
                                }
                                Text(isLoading ? "Thinking..." : "Get Advice")
                                    .fontWeight(.semibold)
                                Spacer()
                            }
                            .padding()
                            .background(scenario.isEmpty ? Color.gray : Color.blue)
                            .foregroundStyle(.white)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                        .disabled(scenario.isEmpty || isLoading)
                    }
                    .padding(.horizontal)

                    // Tips list
                    if tips.isEmpty {
                        ContentUnavailableView(
                            "No Tips Yet",
                            systemImage: "lightbulb",
                            description: Text("Ask for advisory coaching above")
                        )
                        .padding(.top, 40)
                    } else {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Recent Coaching")
                                .font(.headline)
                                .padding(.horizontal)

                            ForEach(tips) { tip in
                                TipCard(tip: tip)
                            }
                        }
                    }
                }
                .padding(.top)
            }
            .navigationTitle("Advisory")
            .onAppear { Task { await loadTips() } }
        }
    }

    private func askAdvisory() async {
        isLoading = true
        do {
            let tip = try await appState.apiService.getAdvisory(scenario: scenario)
            tips.insert(tip, at: 0)
            scenario = ""
        } catch {
            // Handle error silently
        }
        isLoading = false
    }

    private func loadTips() async {
        do {
            tips = try await appState.apiService.fetchTips()
        } catch {
            // Offline — keep empty
        }
    }
}

struct TipCard: View {
    let tip: AdvisoryTip

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "sparkles")
                    .foregroundStyle(.blue)
                Text(tip.scenario)
                    .font(.caption)
                    .foregroundStyle(.blue)
            }
            Text(tip.content)
                .font(.body)
                .foregroundStyle(.secondary)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.systemGray6))
        .overlay(
            Rectangle()
                .fill(Color.blue)
                .frame(width: 3),
            alignment: .leading
        )
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .padding(.horizontal)
    }
}
