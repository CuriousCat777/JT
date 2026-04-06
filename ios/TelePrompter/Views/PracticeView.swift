import SwiftUI

struct PracticeView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    statsGrid
                    sessionHistory
                }
                .padding(.top)
            }
            .navigationTitle("Practice")
            .refreshable {
                await appState.practiceStore.loadStats()
            }
            .onAppear {
                Task { await appState.practiceStore.loadStats() }
            }
        }
    }

    private var statsGrid: some View {
        LazyVGrid(columns: [
            GridItem(.flexible()),
            GridItem(.flexible()),
        ], spacing: 12) {
            StatCard(
                value: "\(appState.practiceStore.stats?.totalSessions ?? 0)",
                label: "Total Sessions",
                color: .blue
            )
            StatCard(
                value: String(format: "%.1f",
                              appState.practiceStore.stats?.averageRating ?? 0),
                label: "Avg Rating",
                color: .orange
            )
            StatCard(
                value: "\(Int(appState.practiceStore.stats?.totalPracticeMinutes ?? 0))",
                label: "Minutes",
                color: .green
            )
            StatCard(
                value: "\(appState.practiceStore.stats?.sessionsThisWeek ?? 0)",
                label: "This Week",
                color: .purple
            )
        }
        .padding(.horizontal)
    }

    private var sessionHistory: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Session History")
                .font(.headline)
                .padding(.horizontal)

            if appState.practiceStore.sessions.isEmpty {
                ContentUnavailableView(
                    "No Sessions",
                    systemImage: "chart.line.uptrend.xyaxis",
                    description: Text("Complete a practice run to see your history")
                )
            } else {
                ForEach(appState.practiceStore.sessions) { session in
                    SessionRow(session: session)
                }
            }
        }
    }
}

struct StatCard: View {
    let value: String
    let label: String
    let color: Color

    var body: some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.title).fontWeight(.bold)
                .foregroundStyle(color)
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding()
        .background(Color(.systemGray6))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

struct SessionRow: View {
    let session: PracticeSession

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(session.scriptTitle)
                    .font(.subheadline).fontWeight(.medium)
                Text(session.startedAt, style: .date)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            HStack(spacing: 2) {
                ForEach(1...5, id: \.self) { star in
                    Image(systemName: star <= session.selfRating ? "star.fill" : "star")
                        .font(.caption2)
                        .foregroundStyle(star <= session.selfRating ? .orange : .gray)
                }
            }
            Text("\(session.durationSeconds / 60)m")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
    }
}
