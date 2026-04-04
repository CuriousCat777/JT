# TelePrompter — iOS App

Telehospitalist teleprompter + AI communication coach.
Part of the Guardian One ecosystem.

## Setup

1. Open Xcode (15.0+)
2. File > New > Project > iOS App
3. Product Name: `TelePrompter`
4. Bundle ID: `com.guardianone.teleprompter`
5. Interface: SwiftUI, Language: Swift
6. Copy all files from `TelePrompter/` into the Xcode project

## Dependencies (Swift Package Manager)

Add via File > Add Package Dependencies:

- **GRDB.swift**: `https://github.com/groue/GRDB.swift`
  - For production: use GRDB with SQLCipher for encrypted database
- **Optional — llama.cpp Swift bindings** for on-device inference

## Guardian One Connection

1. Start the API server:
   ```bash
   cd ~/JT
   python main.py --teleprompter --teleprompter-port 5200
   ```
2. In the app: Settings > Enter your API URL and token
3. The app caches scripts locally for offline use

## Architecture

```
TelePrompter/
├── TelePrompterApp.swift       # App entry point
├── Models/
│   ├── Script.swift            # Script data model
│   ├── PracticeSession.swift   # Practice session + stats
│   └── AdvisoryTip.swift       # AI coaching tips
├── Views/
│   ├── ContentView.swift       # Tab navigation
│   ├── ScriptsView.swift       # Script library
│   ├── TeleprompterView.swift  # Full-screen prompter
│   ├── GenerateView.swift      # AI script generation
│   ├── PracticeView.swift      # Practice stats + history
│   ├── AdvisoryView.swift      # AI coaching
│   └── SettingsView.swift      # Guardian One connection
├── ViewModels/
│   ├── ScriptStore.swift       # Script state management
│   └── PracticeStore.swift     # Practice state + sync
├── Services/
│   ├── GuardianAPIService.swift # Guardian One API client
│   └── KeychainService.swift    # Secure token storage
└── Database/
    └── LocalDatabase.swift      # Local SQLite (GRDB)
```

## Data Flow

```
[User Input] → [Local Script Generator / Guardian One API]
     ↓
[Teleprompter UI] → [Real-time Advisory]
     ↓
[Session Logged → Local DB → Sync → Guardian One]
```

## HIPAA Considerations

- On-device inference preferred (Core ML / llama.cpp)
- Local database encrypted with SQLCipher
- No PHI transmitted to external APIs
- Guardian One sync uses de-identified data only
- API token stored in iOS Keychain
