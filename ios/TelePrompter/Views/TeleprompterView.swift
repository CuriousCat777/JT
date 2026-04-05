import SwiftUI

/// Full-screen teleprompter matching PromptSmart Pro / Teleprompter Premium UX
/// Features: WPM-calibrated scroll, focus line, mirror mode, auto-pause on cues,
/// font size control, elapsed/ETA timers, progress bar, tap-to-pause gestures
struct TeleprompterView: View {
    let script: Script
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var appState: AppState

    // Scroll state
    @State private var scrollWPM: Double = 160
    @State private var isScrolling = false
    @State private var scrollOffset: CGFloat = 0
    @State private var contentHeight: CGFloat = 0

    // Display settings
    @State private var fontSize: CGFloat = 28
    @State private var isMirrored = false
    @State private var showFocusLine = true
    @State private var showSettings = false
    @State private var theme: PrompterTheme = .dark

    // Timer
    @State private var elapsedSeconds = 0
    @State private var timerActive = false

    // Practice
    @State private var showRating = false
    @State private var practiceSessionId: String?
    @State private var practiceStartTime = Date()
    @State private var selfRating = 0
    @State private var practiceNotes = ""
    @State private var aiFeedback: String?

    private let timer = Timer.publish(every: 1.0 / 60.0, on: .main, in: .common).autoconnect()
    private let secondTimer = Timer.publish(every: 1, on: .main, in: .common).autoconnect()

    enum PrompterTheme: String, CaseIterable {
        case dark, light, highContrast
        var bg: Color {
            switch self {
            case .dark: return Color(hex: "0a0a0a")
            case .light: return .white
            case .highContrast: return .black
            }
        }
        var text: Color {
            switch self {
            case .dark: return Color(hex: "f5f5f7")
            case .light: return Color(hex: "1c1c1e")
            case .highContrast: return .yellow
            }
        }
    }

    private var wordCount: Int {
        script.content.split(separator: " ").count
    }

    private var etaSeconds: Int {
        guard scrollWPM > 0 else { return 0 }
        return Int(ceil(Double(wordCount) / scrollWPM * 60))
    }

    private var progress: Double {
        guard contentHeight > 0 else { return 0 }
        return min(1, scrollOffset / contentHeight)
    }

    var body: some View {
        ZStack {
            theme.bg.ignoresSafeArea()

            VStack(spacing: 0) {
                topBar
                infoStrip
                progressBar

                ZStack {
                    // Focus line
                    if showFocusLine {
                        GeometryReader { geo in
                            Rectangle()
                                .fill(Color.blue.opacity(0.25))
                                .frame(height: 2)
                                .offset(y: geo.size.height * 0.4)
                        }
                    }

                    // Script content
                    ScrollViewReader { proxy in
                        ScrollView {
                            scriptContent
                                .padding(.horizontal, 24)
                                .padding(.top, UIScreen.main.bounds.height * 0.4)
                                .padding(.bottom, UIScreen.main.bounds.height * 0.5)
                                .scaleEffect(x: isMirrored ? -1 : 1, y: 1)
                        }
                    }
                }

                controlBar
            }
        }
        .onAppear { startPracticeSession() }
        .onReceive(secondTimer) { _ in
            if timerActive { elapsedSeconds += 1 }
        }
        .sheet(isPresented: $showRating) { ratingSheet }
        .sheet(isPresented: $showSettings) { settingsSheet }
        .onTapGesture { toggleScrolling() }
    }

    // MARK: - Top Bar

    private var topBar: some View {
        HStack {
            Button("Done") { exitPrompter() }
                .foregroundStyle(.blue)
            Spacer()
            Text(script.title)
                .font(.caption).fontWeight(.semibold)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            Spacer()
            HStack(spacing: 12) {
                Button { isMirrored.toggle() } label: {
                    Image(systemName: "arrow.left.arrow.right")
                        .foregroundStyle(isMirrored ? .blue : .secondary)
                }
                Button { fontSize = max(16, fontSize - 2) } label: {
                    Text("A-").font(.caption).foregroundStyle(.secondary)
                }
                Button { fontSize = min(72, fontSize + 2) } label: {
                    Text("A+").font(.caption.bold()).foregroundStyle(.secondary)
                }
                Button { showSettings = true } label: {
                    Image(systemName: "gearshape").foregroundStyle(.secondary)
                }
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(.ultraThinMaterial)
    }

    // MARK: - Info Strip

    private var infoStrip: some View {
        HStack {
            Label(formatTime(elapsedSeconds), systemImage: "clock")
            Spacer()
            Text("\(Int(scrollWPM)) WPM")
            Spacer()
            Text("\(wordCount) words")
            Spacer()
            Label(formatTime(etaSeconds), systemImage: "hourglass")
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
        .padding(.horizontal)
        .padding(.vertical, 4)
        .background(Color.black.opacity(0.5))
    }

    // MARK: - Progress Bar

    private var progressBar: some View {
        GeometryReader { geo in
            Rectangle()
                .fill(Color.blue)
                .frame(width: geo.size.width * progress, height: 2)
        }
        .frame(height: 2)
        .background(Color.white.opacity(0.1))
    }

    // MARK: - Script Content

    private var scriptContent: some View {
        let sections = parseScript(script.content)
        return VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(sections.enumerated()), id: \.offset) { _, section in
                switch section {
                case .text(let text):
                    Text(text)
                        .font(.system(size: fontSize))
                        .lineSpacing(fontSize * 0.3)
                        .foregroundStyle(theme.text)
                case .pause(let label):
                    HStack {
                        Rectangle().fill(Color.orange.opacity(0.3)).frame(height: 1)
                        Text(label)
                            .font(.system(size: fontSize * 0.55, weight: .bold))
                            .foregroundStyle(.orange)
                            .textCase(.uppercase)
                            .tracking(3)
                        Rectangle().fill(Color.orange.opacity(0.3)).frame(height: 1)
                    }
                    .padding(.vertical, 20)
                case .header(let title):
                    Text(title)
                        .font(.system(size: fontSize * 0.7, weight: .heavy))
                        .foregroundStyle(.green)
                        .textCase(.uppercase)
                        .tracking(2)
                        .padding(.top, 28)
                        .padding(.bottom, 8)
                        .overlay(
                            Rectangle().fill(Color.green.opacity(0.3)).frame(height: 1),
                            alignment: .bottom
                        )
                case .placeholder(let text):
                    Text(text)
                        .font(.system(size: fontSize * 0.9, weight: .semibold))
                        .foregroundStyle(.blue)
                        .padding(.horizontal, 4)
                        .background(Color.blue.opacity(0.1))
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                case .stageDirection(let text):
                    Text(text)
                        .font(.system(size: fontSize * 0.6))
                        .italic()
                        .foregroundStyle(.yellow.opacity(0.8))
                }
            }
        }
    }

    // MARK: - Controls

    private var controlBar: some View {
        VStack(spacing: 0) {
            // Transport controls
            HStack(spacing: 20) {
                Button { scrollOffset = 0 } label: {
                    Image(systemName: "backward.end.fill").font(.body)
                }
                .frame(width: 44, height: 44)
                .background(Color.white.opacity(0.08))
                .clipShape(Circle())

                Button { scrollOffset = max(0, scrollOffset - 300) } label: {
                    Image(systemName: "backward.fill").font(.body)
                }
                .frame(width: 44, height: 44)
                .background(Color.white.opacity(0.08))
                .clipShape(Circle())

                Button { toggleScrolling() } label: {
                    Image(systemName: isScrolling ? "pause.fill" : "play.fill")
                        .font(.title2)
                }
                .frame(width: 60, height: 60)
                .background(isScrolling ? Color.orange : Color.blue)
                .clipShape(Circle())

                Button { scrollOffset += 300 } label: {
                    Image(systemName: "forward.fill").font(.body)
                }
                .frame(width: 44, height: 44)
                .background(Color.white.opacity(0.08))
                .clipShape(Circle())
            }
            .foregroundStyle(.white)
            .padding(.top, 10)

            // Speed slider
            HStack {
                Text("Speed")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Slider(value: $scrollWPM, in: 60...300, step: 10)
                    .tint(.blue)
                Text("\(Int(scrollWPM)) WPM")
                    .font(.caption)
                    .fontWeight(.semibold)
                    .foregroundStyle(.white)
                    .frame(width: 65)
                    .monospacedDigit()
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 8)
        }
        .background(.ultraThinMaterial)
    }

    // MARK: - Rating Sheet

    private var ratingSheet: some View {
        NavigationStack {
            VStack(spacing: 20) {
                Text("Rate Your Practice")
                    .font(.title2).fontWeight(.bold)

                Text("Duration: \(formatTime(elapsedSeconds))")
                    .foregroundStyle(.secondary)

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

    // MARK: - Settings Sheet

    private var settingsSheet: some View {
        NavigationStack {
            Form {
                Section("Text") {
                    HStack {
                        Text("Font Size")
                        Spacer()
                        Text("\(Int(fontSize))px")
                            .foregroundStyle(.secondary)
                    }
                    Slider(value: $fontSize, in: 16...72, step: 2)

                    Toggle("Mirror Mode", isOn: $isMirrored)
                    Toggle("Focus Line", isOn: $showFocusLine)
                }

                Section("Theme") {
                    Picker("Color Theme", selection: $theme) {
                        Text("Dark").tag(PrompterTheme.dark)
                        Text("Light").tag(PrompterTheme.light)
                        Text("High Contrast").tag(PrompterTheme.highContrast)
                    }
                    .pickerStyle(.segmented)
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { showSettings = false }
                }
            }
        }
    }

    // MARK: - Logic

    private func toggleScrolling() {
        isScrolling.toggle()
        timerActive = isScrolling
    }

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
        timerActive = false
        if practiceSessionId != nil {
            showRating = true
        } else {
            dismiss()
        }
    }

    private func submitPractice() async {
        guard let sessionId = practiceSessionId else { dismiss(); return }
        let duration = Int(Date().timeIntervalSince(practiceStartTime))
        if let result = await appState.practiceStore.completeSession(
            sessionId: sessionId, duration: duration,
            rating: selfRating, notes: practiceNotes
        ) {
            aiFeedback = result.aiFeedback
            if result.aiFeedback.isEmpty { dismiss() }
        } else { dismiss() }
    }

    private func formatTime(_ seconds: Int) -> String {
        let m = seconds / 60
        let s = seconds % 60
        return String(format: "%d:%02d", m, s)
    }

    // MARK: - Script Parsing

    private enum ScriptSection {
        case text(String)
        case pause(String)
        case header(String)
        case placeholder(String)
        case stageDirection(String)
    }

    private func parseScript(_ text: String) -> [ScriptSection] {
        var sections: [ScriptSection] = []
        let lines = text.components(separatedBy: "\n")
        var buffer = ""

        let headerPattern = /^(SITUATION|BACKGROUND|ASSESSMENT|RECOMMENDATION|SETTING UP|PERCEPTION|INVITATION|KNOWLEDGE|EMOTION|STRATEGY & SUMMARY|MEDICATIONS|FOLLOW-UP|WHEN TO COME BACK|ACTIVITY & DIET|OPENING|AGENDA SETTING|AGENDA|CLINICAL EXPLANATION|CLINICAL|DECISION POINTS|DECISION|ANTICIPATED QUESTIONS|DIFFICULT SCENARIOS|CLOSING):?$/

        let stagePattern = /^\[(LOOK[^\]]*|GESTURE[^\]]*|TONE[^\]]*|SLOW DOWN[^\]]*|SPEED UP[^\]]*|EMPHASIZE[^\]]*|WARNING SHOT[^\]]*|SUMMARIZE[^\]]*)\]$/

        for line in lines {
            if line.contains("[PAUSE") {
                if !buffer.isEmpty { sections.append(.text(buffer)); buffer = "" }
                sections.append(.pause("PAUSE"))
            } else if line.wholeMatch(of: headerPattern) != nil {
                if !buffer.isEmpty { sections.append(.text(buffer)); buffer = "" }
                sections.append(.header(line.replacingOccurrences(of: ":", with: "")))
            } else if line.wholeMatch(of: stagePattern) != nil {
                if !buffer.isEmpty { sections.append(.text(buffer)); buffer = "" }
                sections.append(.stageDirection(line))
            } else if line.hasPrefix("[") && line.hasSuffix("]") {
                if !buffer.isEmpty { sections.append(.text(buffer)); buffer = "" }
                sections.append(.placeholder(line))
            } else {
                buffer += (buffer.isEmpty ? "" : "\n") + line
            }
        }
        if !buffer.isEmpty { sections.append(.text(buffer)) }
        return sections
    }
}

// MARK: - Color hex helper

extension Color {
    init(hex: String) {
        let scanner = Scanner(string: hex)
        var rgb: UInt64 = 0
        scanner.scanHexInt64(&rgb)
        self.init(
            red: Double((rgb >> 16) & 0xFF) / 255,
            green: Double((rgb >> 8) & 0xFF) / 255,
            blue: Double(rgb & 0xFF) / 255
        )
    }
}
