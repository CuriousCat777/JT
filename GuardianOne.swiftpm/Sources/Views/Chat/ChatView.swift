import SwiftUI

struct ChatView: View {
    @Environment(APIClient.self) private var api
    @State private var messages: [ChatMessage] = [
        ChatMessage(text: "Guardian One online. Type 'help' for commands.", sender: .system)
    ]
    @State private var input = ""
    @State private var useAI = false
    @State private var isSending = false

    var body: some View {
        VStack(spacing: 0) {
            // Mode toggle
            HStack {
                Spacer()
                Text("LOCAL")
                    .font(.caption)
                    .fontWeight(useAI ? .regular : .bold)
                    .foregroundStyle(useAI ? .secondary : .green)
                Toggle("", isOn: $useAI)
                    .toggleStyle(.switch)
                    .labelsHidden()
                    .scaleEffect(0.8)
                Text("AI")
                    .font(.caption)
                    .fontWeight(useAI ? .bold : .regular)
                    .foregroundStyle(useAI ? .purple : .secondary)
                Text(useAI ? "AI Engine" : "Deterministic")
                    .font(.caption2)
                    .fontWeight(.semibold)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(useAI ? Color.purple.opacity(0.15) : Color.green.opacity(0.15))
                    .foregroundStyle(useAI ? .purple : .green)
                    .clipShape(Capsule())
            }
            .padding(.horizontal)
            .padding(.vertical, 8)

            Divider()

            // Messages
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 12) {
                        ForEach(messages) { msg in
                            ChatBubble(message: msg)
                                .id(msg.id)
                        }
                        if isSending {
                            HStack {
                                ProgressView()
                                    .controlSize(.small)
                                Text("Guardian is thinking...")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Spacer()
                            }
                            .padding(.horizontal)
                            .id("typing")
                        }
                    }
                    .padding()
                }
                .onChange(of: messages.count) { _ in
                    withAnimation {
                        proxy.scrollTo(messages.last?.id, anchor: .bottom)
                    }
                }
                .onChange(of: isSending) { _ in
                    if isSending {
                        withAnimation {
                            proxy.scrollTo("typing", anchor: .bottom)
                        }
                    }
                }
            }

            Divider()

            // Input
            HStack(spacing: 12) {
                TextField("Talk to Guardian One...", text: $input)
                    .textFieldStyle(.plain)
                    .padding(10)
                    .background(Color.secondary.opacity(0.08))
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                    .onSubmit { send() }
                    .disabled(isSending)

                Button(action: send) {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title2)
                        .foregroundStyle(.blue)
                }
                .disabled(input.trimmingCharacters(in: .whitespaces).isEmpty || isSending)
                .keyboardShortcut(.return, modifiers: [])
            }
            .padding()
        }
        .navigationTitle("Guardian Chat")
    }

    private func send() {
        let text = input.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }
        input = ""

        messages.append(ChatMessage(text: text, sender: .user))
        isSending = true

        Task {
            do {
                let response = try await api.sendChat(message: text, useAI: useAI)
                messages.append(ChatMessage(
                    text: response.response,
                    sender: .guardian,
                    type: response.type ?? "guardian"
                ))
            } catch {
                messages.append(ChatMessage(
                    text: "Connection error: \(error.localizedDescription)",
                    sender: .guardian,
                    type: "error"
                ))
            }
            isSending = false
        }
    }
}

// MARK: - Chat Models

struct ChatMessage: Identifiable {
    let id = UUID()
    let text: String
    let sender: ChatSender
    var type: String = "guardian"
    let timestamp = Date()
}

enum ChatSender {
    case user, guardian, system
}

// MARK: - Chat Bubble

struct ChatBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.sender == .user { Spacer(minLength: 60) }

            VStack(alignment: message.sender == .user ? .trailing : .leading, spacing: 4) {
                Text(senderName)
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(senderColor)
                    .textCase(.uppercase)
                    .tracking(1)

                Text(message.text)
                    .font(.callout)
                    .foregroundStyle(message.sender == .system ? .secondary : .primary)
                    .textSelection(.enabled)
            }
            .padding(12)
            .background(backgroundColor, in: bubbleShape)

            if message.sender == .guardian || message.sender == .system { Spacer(minLength: 60) }
        }
        .padding(.horizontal, message.sender == .system ? 40 : 0)
    }

    private var senderName: String {
        switch message.sender {
        case .user: return "Jeremy"
        case .guardian: return "Guardian One"
        case .system: return ""
        }
    }

    private var senderColor: Color {
        switch message.sender {
        case .user: return .blue
        case .guardian: return message.type == "ai" ? .purple : .indigo
        case .system: return .clear
        }
    }

    private var backgroundColor: Color {
        switch message.sender {
        case .user: return .blue.opacity(0.12)
        case .guardian:
            if message.type == "error" { return .red.opacity(0.08) }
            if message.type == "ai" { return .purple.opacity(0.08) }
            return Color.secondary.opacity(0.08)
        case .system: return .clear
        }
    }

    private var bubbleShape: RoundedRectangle {
        RoundedRectangle(cornerRadius: 12)
    }
}
