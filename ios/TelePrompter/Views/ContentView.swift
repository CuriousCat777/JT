import SwiftUI

struct ContentView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        TabView(selection: $appState.selectedTab) {
            ScriptsView()
                .tabItem {
                    Image(systemName: "doc.text")
                    Text("Scripts")
                }
                .tag(AppState.Tab.scripts)

            GenerateView()
                .tabItem {
                    Image(systemName: "bolt.fill")
                    Text("Generate")
                }
                .tag(AppState.Tab.generate)

            PracticeView()
                .tabItem {
                    Image(systemName: "chart.line.uptrend.xyaxis")
                    Text("Practice")
                }
                .tag(AppState.Tab.practice)

            AdvisoryView()
                .tabItem {
                    Image(systemName: "questionmark.circle")
                    Text("Advisory")
                }
                .tag(AppState.Tab.advisory)
        }
        .tint(.blue)
        .onAppear {
            appState.scriptStore.configure(api: appState.apiService)
            appState.practiceStore.configure(api: appState.apiService)
            Task { await appState.scriptStore.loadScripts() }
        }
    }
}
