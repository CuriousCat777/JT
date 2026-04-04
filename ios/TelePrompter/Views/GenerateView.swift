import SwiftUI

struct GenerateView: View {
    @EnvironmentObject var appState: AppState
    @State private var category: ScriptCategory = .general
    @State private var chiefComplaint = ""
    @State private var patientAge = ""
    @State private var setting = ""
    @State private var scenario = ""
    @State private var generatedScript: Script?

    var body: some View {
        NavigationStack {
            Form {
                Section("Encounter Details") {
                    Picker("Category", selection: $category) {
                        ForEach(ScriptCategory.allCases) { cat in
                            Label(cat.displayName, systemImage: cat.iconName)
                                .tag(cat)
                        }
                    }

                    TextField("Chief Complaint", text: $chiefComplaint)
                        .textInputAutocapitalization(.sentences)

                    TextField("Patient Age", text: $patientAge)
                        .keyboardType(.numberPad)

                    TextField("Setting (e.g., ICU, night shift)", text: $setting)
                }

                Section("Scenario (optional)") {
                    TextEditor(text: $scenario)
                        .frame(minHeight: 80)
                }

                Section {
                    Button {
                        Task { await generate() }
                    } label: {
                        HStack {
                            Spacer()
                            if appState.scriptStore.isLoading {
                                ProgressView()
                                    .padding(.trailing, 8)
                            }
                            Text(appState.scriptStore.isLoading ? "Generating..." : "Generate Script")
                                .fontWeight(.semibold)
                            Spacer()
                        }
                    }
                    .disabled(chiefComplaint.isEmpty && scenario.isEmpty)
                    .disabled(appState.scriptStore.isLoading)
                }
            }
            .navigationTitle("Generate")
            .fullScreenCover(item: $generatedScript) { script in
                TeleprompterView(script: script)
            }
        }
    }

    private func generate() async {
        let result = await appState.scriptStore.generateScript(
            scenario: scenario,
            category: category,
            chiefComplaint: chiefComplaint,
            age: patientAge,
            setting: setting
        )
        if let script = result {
            generatedScript = script
        }
    }
}
