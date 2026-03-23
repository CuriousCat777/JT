import SwiftUI

@main
struct GuardianOneApp: App {
    @State private var api = APIClient()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(api)
        }
        #if os(macOS)
        .defaultSize(width: 1200, height: 800)
        #endif
    }
}

// MARK: - Root Navigation

struct ContentView: View {
    @Environment(APIClient.self) private var api
    @State private var selection: NavItem = .morning

    var body: some View {
        NavigationSplitView {
            SidebarView(selection: $selection)
        } detail: {
            DetailView(selection: selection)
        }
        #if os(iOS)
        .navigationSplitViewStyle(.balanced)
        #endif
    }
}

// MARK: - Navigation Items

enum NavItem: String, CaseIterable, Identifiable {
    case morning = "Morning Brief"
    case agents = "Agents"
    case chat = "Guardian Chat"
    case websites = "Websites"
    case finances = "Finances"
    case services = "Services"
    case vault = "Vault"
    case registry = "Registry"
    case audit = "Audit Log"
    case config = "Config"
    case settings = "Settings"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .morning: return "sun.max"
        case .agents: return "cpu"
        case .chat: return "bubble.left.and.bubble.right"
        case .websites: return "globe"
        case .finances: return "dollarsign.circle"
        case .services: return "server.rack"
        case .vault: return "lock.shield"
        case .registry: return "list.bullet.rectangle"
        case .audit: return "doc.text.magnifyingglass"
        case .config: return "gearshape"
        case .settings: return "wrench.and.screwdriver"
        }
    }

    var section: String {
        switch self {
        case .morning: return "Daily"
        case .agents, .chat: return "Operations"
        case .websites, .finances: return "Properties"
        case .services, .vault, .registry: return "Infrastructure"
        case .audit, .config, .settings: return "System"
        }
    }
}

// MARK: - Sidebar

struct SidebarView: View {
    @Binding var selection: NavItem

    private var grouped: [(String, [NavItem])] {
        let order = ["Daily", "Operations", "Properties", "Infrastructure", "System"]
        let dict = Dictionary(grouping: NavItem.allCases, by: \.section)
        return order.compactMap { key in
            guard let items = dict[key] else { return nil }
            return (key, items)
        }
    }

    var body: some View {
        List(selection: $selection) {
            ForEach(grouped, id: \.0) { section, items in
                Section(section) {
                    ForEach(items) { item in
                        Label(item.rawValue, systemImage: item.icon)
                            .tag(item)
                    }
                }
            }
        }
        .navigationTitle("Guardian One")
        #if os(macOS)
        .navigationSplitViewColumnWidth(min: 200, ideal: 220, max: 280)
        #endif
    }
}

// MARK: - Detail Router

struct DetailView: View {
    let selection: NavItem

    var body: some View {
        switch selection {
        case .morning: MorningBriefView()
        case .agents: AgentsView()
        case .chat: ChatView()
        case .websites: WebsitesView()
        case .finances: FinancesView()
        case .services: ServicesView()
        case .vault: VaultView()
        case .registry: RegistryView()
        case .audit: AuditView()
        case .config: ConfigView()
        case .settings: SettingsView()
        }
    }
}
