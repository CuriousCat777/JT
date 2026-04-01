import SwiftUI

/// Full-screen teleprompter with auto-scroll and practice tracking
struct TeleprompterView: View {
    let script: Script
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var appState: AppState

    @State private var scrollSpeed: Double = 3
    @State private var isScrolling = false
    @State private var scrollOffset: CGFloat = 0
    @State private var showRating = false
    @State private var practiceSessionId: String?
    @State private var practiceStartTime = Date()
    @State private var selfRating = 0
    @State private var practiceNotes = ""
    @State private var aiFeedback: String?

    private let timer = Timer.publish(every: 1.0 / 60.0, on: .main, in: .common).autoconnect()

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VStack(spacing: 0) {
                // Header
                HStack {
                    Button("Done") { exitPrompter() }
                        .foregroundStyle(.blue)
                    Spacer()
                    Text(script.title)
                        .font(.subheadline).fontWeight(.semibold)
                        .lineLimit(1)
                    Spacer()
                    // Mirror button placeholder
                    Text("Done").opacity(0)
                }
                .padding(.horizontal)
                .padding(.vertical, 12)
                .background(.ultraThinMaterial)

                // Script content
                ScrollViewReader { proxy in
                    ScrollView {
                        scriptContent
                            .padding(.horizontal, 24)
                            .padding(.vertical, 40)
                            .id("content")
                    }
                }
                .onReceive(timer) { _ in
                    guard isScrolling else { return }
                    scrollOffset += scrollSpeed * 0.5
                }

                // Controls
                controlBar
            }
        }
        .onAppear { startPracticeSession() }
        .sheet(isPresented: $showRating) { ratingSheet }
    }

    // MARK: - Script Content

    private var scriptContent: some View {
        let sections = parseScript(script.content)
        return VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(sections.enumerated()), id: \.offset) { _, section in
                switch section {
                case .text(let text):
                    Text(text)
                        .font(.title2)
                        .fontWeight(.regular)
                        .lineSpacing(8)
                        .foregroundStyle(.white)
                case .pause(let label):
                    HStack {
                        Spacer()
                        Text("--- \(label) ---")
                            .font(.callout).fontWeight(.bold)
                            .foregroundStyle(.orange)
                            .padding(.vertical, 16)
                        Spacer()
                    }
                case .header(let title):
                    Text(title)
                        .font(.headline)
                        .foregroundStyle(.green)
                        .textCase(.uppercase)
                        .tracking(1)
                        .padding(.top, 24)
                        .padding(.bottom, 8)
                case .placeholder(let text):
                    Text(text)
                        .font(.title3)
                        .foregroundStyle(.blue)
                        .fontWeight(.semibold)
                }
            }
        }
    }

    // MARK: - Controls

    private var controlBar: some View {
        HStack(spacing: 16) {
            // Rewind
            Button { scrollOffset = max(0, scrollOffset - 200) } label: {
                Image(systemName: "backward.fill")
                    .font(.title3)
            }
            .frame(width: 44, height: 44)
            .background(Color.white.opacity(0.1))
            .clipShape(Circle())

            // Play/Pause
            Button { isScrolling.toggle() } label: {
                Image(systemName: isScrolling ? "pause.fill" : "play.fill")
                    .font(.title2)
            }
            .frame(width: 56, height: 56)
            .background(Color.blue)
            .clipShape(Circle())

            // Forward
            Button { scrollOffset += 200 } label: {
                Image(systemName: "forward.fill")
                    .font(.title3)
            }
            .frame(width: 44, height: 44)
            .background(Color.white.opacity(0.1))
            .clipShape(Circle())

            Spacer()

            // Speed slider
            VStack(spacing: 2) {
                Slider(value: $scrollSpeed, in: 1...10, step: 1)
                    .tint(.blue)
                Text("\(Int(scrollSpeed))x")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(width: 100)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 12)
        .background(.ultraThinMaterial)
        .foregroundStyle(.white)
    }

    // MARK: - Rating Sheet

    private var ratingSheet: some View {
        NavigationStack {
            VStack(spacing: 20) {
                Text("Rate Your Practice")
                    .font(.title2).fontWeight(.bold)

                Text("How did that session feel?")
                    .foregroundStyle(.secondary)

                // Stars
                HStack(spacing: 12) {
                    ForEach(1...5, id: \.self) { star in
                        Button {
                            selfRating = star
                        } label: {
                            Image(systemName: star <= selfRating ? "star.fill" : "star")
                                .font(.largeTitle)
                                .foregroundStyle(star <= selfRating ? .orange : .gray)
                        }
                    }
                }
                .padding()

                TextField("Notes (optional)", text: $practiceNotes, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .lineLimit(3...6)
                    .padding(.horizontal)

                if let feedback = aiFeedback {
                    VStack(alignment: .leading, spacing: 8) {
                        Label("AI Feedback", systemImage: "sparkles")
                            .font(.headline)
                        Text(feedback)
                            .font(.body)
                            .foregroundStyle(.secondary)
                    }
                    .padding()
                    .background(Color.blue.opacity(0.1))
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .padding(.horizontal)
                }

                Button {
                    Task { await submitPractice() }
                } label: {
                    Text("Submit")
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(selfRating > 0 ? Color.blue : Color.gray)
                        .foregroundStyle(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                }
                .disabled(selfRating == 0)
                .padding(.horizontal)

                Button("Skip") { dismiss() }
                    .foregroundStyle(.secondary)

                Spacer()
            }
            .padding(.top, 20)
        }
    }

    // MARK: - Logic

    private func startPracticeSession() {
        practiceStartTime = Date()
        Task {
            if let session = await appState.practiceStore.startSession(scriptId: script.id) {
                practiceSessionId = session.id
            }
        }
    }

    private func exitPrompter() {
        isScrolling = false
        if practiceSessionId != nil {
            showRating = true
        } else {
            dismiss()
        }
    }

    private func submitPractice() async {
        guard let sessionId = practiceSessionId else {
            dismiss()
            return
        }
        let duration = Int(Date().timeIntervalSince(practiceStartTime))
        if let result = await appState.practiceStore.completeSession(
            sessionId: sessionId, duration: duration,
            rating: selfRating, notes: practiceNotes
        ) {
            aiFeedback = result.aiFeedback
            if result.aiFeedback.isEmpty {
                dismiss()
            }
            // Feedback is shown in the sheet; user will dismiss after reading
        } else {
            dismiss()
        }
    }

    // MARK: - Script Parsing

    private enum ScriptSection {
        case text(String)
        case pause(String)
        case header(String)
        case placeholder(String)
    }

    private func parseScript(_ text: String) -> [ScriptSection] {
        var sections: [ScriptSection] = []
        let lines = text.components(separatedBy: "\n")
        var buffer = ""

        let headerPattern = /^(SITUATION|BACKGROUND|ASSESSMENT|RECOMMENDATION|SETTING UP|PERCEPTION|INVITATION|KNOWLEDGE|EMOTION|STRATEGY & SUMMARY|MEDICATIONS|FOLLOW-UP|WHEN TO COME BACK|ACTIVITY & DIET|OPENING|AGENDA|CLINICAL|DECISION|CLOSING):?$/

        for line in lines {
            if line.contains("[PAUSE") {
                if !buffer.isEmpty {
                    sections.append(.text(buffer))
                    buffer = ""
                }
                let label = line.replacingOccurrences(of: "[", with: "")
                    .replacingOccurrences(of: "]", with: "")
                sections.append(.pause(label))
            } else if line.wholeMatch(of: headerPattern) != nil {
                if !buffer.isEmpty {
                    sections.append(.text(buffer))
                    buffer = ""
                }
                sections.append(.header(line.replacingOccurrences(of: ":", with: "")))
            } else if line.hasPrefix("[") && line.hasSuffix("]") {
                if !buffer.isEmpty {
                    sections.append(.text(buffer))
                    buffer = ""
                }
                sections.append(.placeholder(line))
            } else {
                buffer += (buffer.isEmpty ? "" : "\n") + line
            }
        }

        if !buffer.isEmpty {
            sections.append(.text(buffer))
        }

        return sections
    }
}
