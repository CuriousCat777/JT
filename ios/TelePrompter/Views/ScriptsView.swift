import SwiftUI

struct ScriptsView: View {
    @EnvironmentObject var appState: AppState
    @State private var selectedScript: Script?
    @State private var filterCategory: ScriptCategory?

    var body: some View {
        NavigationStack {
            Group {
                if appState.scriptStore.isLoading && appState.scriptStore.scripts.isEmpty {
                    ProgressView("Loading scripts...")
                } else if appState.scriptStore.scripts.isEmpty {
                    ContentUnavailableView(
                        "No Scripts",
                        systemImage: "doc.text",
                        description: Text("Generate a script or connect to Guardian One")
                    )
                } else {
                    List {
                        ForEach(filteredScripts) { script in
                            ScriptRow(script: script)
                                .onTapGesture {
                                    selectedScript = script
                                }
                        }
                        .onDelete { indexSet in
                            Task {
                                for index in indexSet {
                                    await appState.scriptStore.deleteScript(filteredScripts[index])
                                }
                            }
                        }
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle("Scripts")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button("All Categories") { filterCategory = nil }
                        Divider()
                        ForEach(ScriptCategory.allCases) { cat in
                            Button(cat.displayName) { filterCategory = cat }
                        }
                    } label: {
                        Image(systemName: "line.3.horizontal.decrease.circle")
                    }
                }
            }
            .refreshable {
                await appState.scriptStore.loadScripts(category: filterCategory)
            }
            .fullScreenCover(item: $selectedScript) { script in
                TeleprompterView(script: script)
            }
        }
    }

    private var filteredScripts: [Script] {
        if let cat = filterCategory {
            return appState.scriptStore.scripts.filter { $0.category == cat }
        }
        return appState.scriptStore.scripts
    }
}

struct ScriptRow: View {
    let script: Script

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                CategoryBadge(category: script.category)
                if script.aiGenerated {
                    Text("AI")
                        .font(.caption2).fontWeight(.bold)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(.green.opacity(0.2))
                        .foregroundStyle(.green)
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                }
            }
            Text(script.title)
                .font(.headline)
            if !script.scenario.isEmpty {
                Text(script.scenario)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 4)
    }
}

struct CategoryBadge: View {
    let category: ScriptCategory

    var body: some View {
        Label(category.displayName, systemImage: category.iconName)
            .font(.caption2).fontWeight(.semibold)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(.blue.opacity(0.15))
            .foregroundStyle(.blue)
            .clipShape(RoundedRectangle(cornerRadius: 6))
    }
}
