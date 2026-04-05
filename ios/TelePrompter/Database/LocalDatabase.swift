import Foundation

/// Local encrypted SQLite database for offline-first practice tracking.
///
/// In production, replace this with GRDB + SQLCipher for encrypted storage.
/// This implementation uses JSON file storage as a build-ready placeholder
/// that mirrors the GRDB schema design.
///
/// Schema (for GRDB migration):
/// ```sql
/// CREATE TABLE encounters (
///   id TEXT PRIMARY KEY,
///   timestamp DATETIME NOT NULL,
///   encounter_type TEXT NOT NULL,
///   complexity_score INTEGER DEFAULT 0,
///   script_used TEXT,
///   ai_suggestions TEXT,
///   outcome_score INTEGER DEFAULT 0,
///   notes TEXT,
///   synced INTEGER DEFAULT 0
/// );
///
/// CREATE TABLE performance_metrics (
///   id TEXT PRIMARY KEY,
///   metric_name TEXT NOT NULL,
///   value REAL NOT NULL,
///   timestamp DATETIME NOT NULL,
///   synced INTEGER DEFAULT 0
/// );
///
/// CREATE TABLE scripts_cache (
///   id TEXT PRIMARY KEY,
///   title TEXT NOT NULL,
///   category TEXT NOT NULL,
///   content TEXT NOT NULL,
///   updated_at DATETIME NOT NULL
/// );
/// ```
final class LocalDatabase: ObservableObject {
    @Published var encounters: [LocalEncounter] = []
    @Published var metrics: [PerformanceMetric] = []
    @Published var cachedScripts: [Script] = []

    private let fileURL: URL

    init() {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        self.fileURL = docs.appendingPathComponent("teleprompter_local.json")
        load()
    }

    // MARK: - Encounters

    func recordEncounter(_ encounter: LocalEncounter) {
        encounters.append(encounter)
        save()
    }

    func unsyncedEncounters() -> [LocalEncounter] {
        encounters.filter { !$0.synced }
    }

    func markSynced(ids: [String]) {
        for i in encounters.indices {
            if ids.contains(encounters[i].id) {
                encounters[i].synced = true
            }
        }
        save()
    }

    // MARK: - Metrics

    func recordMetric(name: String, value: Double) {
        let metric = PerformanceMetric(
            id: UUID().uuidString,
            metricName: name,
            value: value,
            timestamp: Date(),
            synced: false
        )
        metrics.append(metric)
        save()
    }

    /// Derived metrics
    func scriptDeviationRate() -> Double {
        let total = encounters.count
        guard total > 0 else { return 0 }
        let deviated = encounters.filter { $0.outcomeScore < 3 }.count
        return Double(deviated) / Double(total)
    }

    func aiSuggestionAcceptanceRate() -> Double {
        let withSuggestions = encounters.filter { !$0.aiSuggestions.isEmpty }
        guard !withSuggestions.isEmpty else { return 0 }
        let accepted = withSuggestions.filter { $0.outcomeScore >= 4 }.count
        return Double(accepted) / Double(withSuggestions.count)
    }

    func averageTimeToDecision() -> Double {
        let completed = encounters.filter { $0.outcomeScore > 0 }
        guard !completed.isEmpty else { return 0 }
        let totalTime = completed.reduce(0) { $0 + Double($1.complexityScore * 60) }
        return totalTime / Double(completed.count)
    }

    // MARK: - Script Cache

    func cacheScripts(_ scripts: [Script]) {
        cachedScripts = scripts
        save()
    }

    // MARK: - Persistence

    private func load() {
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return }
        do {
            let data = try Data(contentsOf: fileURL)
            let db = try JSONDecoder.iso8601.decode(DatabaseSnapshot.self, from: data)
            encounters = db.encounters
            metrics = db.metrics
        } catch {
            print("LocalDatabase load error: \(error)")
        }
    }

    private func save() {
        let snapshot = DatabaseSnapshot(
            encounters: encounters,
            metrics: metrics,
            savedAt: Date()
        )
        do {
            let data = try JSONEncoder.iso8601.encode(snapshot)
            try data.write(to: fileURL, options: .atomic)
        } catch {
            print("LocalDatabase save error: \(error)")
        }
    }
}

// MARK: - Local models

struct LocalEncounter: Identifiable, Codable {
    let id: String
    var timestamp: Date
    var encounterType: String
    var complexityScore: Int
    var scriptUsed: String
    var aiSuggestions: String
    var outcomeScore: Int
    var notes: String
    var synced: Bool
}

struct PerformanceMetric: Identifiable, Codable {
    let id: String
    var metricName: String
    var value: Double
    var timestamp: Date
    var synced: Bool
}

private struct DatabaseSnapshot: Codable {
    let encounters: [LocalEncounter]
    let metrics: [PerformanceMetric]
    let savedAt: Date
}

// MARK: - Encoder/Decoder helpers

extension JSONDecoder {
    static let iso8601: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()
}

extension JSONEncoder {
    static let iso8601: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = .prettyPrinted
        return encoder
    }()
}
