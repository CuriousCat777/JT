import SwiftUI

// MARK: - Reusable Components

struct StatCard: View {
    let label: String
    let value: String
    let subtitle: String?
    var color: Color = .primary

    init(_ label: String, value: String, subtitle: String? = nil, color: Color = .primary) {
        self.label = label
        self.value = value
        self.subtitle = subtitle
        self.color = color
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label.uppercased())
                .font(.caption2)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)
                .tracking(1)
            Text(value)
                .font(.system(size: 28, weight: .bold, design: .rounded))
                .foregroundStyle(color)
            if let subtitle {
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
    }
}

struct StatusBadge: View {
    let text: String
    var color: Color

    init(_ text: String, color: Color? = nil) {
        self.text = text
        self.color = color ?? Self.colorFor(text)
    }

    static func colorFor(_ status: String) -> Color {
        switch status.lowercased() {
        case "idle", "ready", "active", "live", "closed", "healthy":
            return .green
        case "running", "in_progress":
            return .blue
        case "error", "critical", "down", "open":
            return .red
        case "warning", "half_open":
            return .orange
        case "disabled":
            return .gray
        default:
            return .secondary
        }
    }

    var body: some View {
        Text(text.uppercased())
            .font(.caption2)
            .fontWeight(.bold)
            .tracking(0.5)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(color.opacity(0.15))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }
}

struct RiskMeter: View {
    let score: Int

    var color: Color {
        switch score {
        case 0...1: return .green
        case 2: return .yellow
        case 3: return .orange
        default: return .red
        }
    }

    var body: some View {
        HStack(spacing: 3) {
            ForEach(1...5, id: \.self) { i in
                RoundedRectangle(cornerRadius: 2)
                    .fill(i <= score ? color : Color.secondary.opacity(0.2))
                    .frame(width: 14, height: 8)
            }
        }
    }
}

struct SectionHeader: View {
    let title: String

    var body: some View {
        Text(title.uppercased())
            .font(.caption)
            .fontWeight(.semibold)
            .foregroundStyle(.secondary)
            .tracking(1.5)
            .padding(.bottom, 4)
    }
}

struct ErrorBanner: View {
    let message: String

    var body: some View {
        HStack {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.red)
            Text(message)
                .font(.callout)
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.red.opacity(0.1), in: RoundedRectangle(cornerRadius: 10))
    }
}

struct LoadingView: View {
    var label: String = "Loading..."

    var body: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Greeting

func greeting() -> String {
    let hour = Calendar.current.component(.hour, from: Date())
    switch hour {
    case 5..<12: return "Good morning"
    case 12..<17: return "Good afternoon"
    case 17..<22: return "Good evening"
    default: return "Good night"
    }
}
