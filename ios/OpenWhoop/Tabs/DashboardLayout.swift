import Foundation

// MARK: - Dashboard customization model
//
// Drives which cards the Today tab shows and in what order. Persisted to UserDefaults
// (same lightweight JSON pattern as ProfileStorage in SettingsView). The recovery hero
// ring is always pinned at the top and is NOT part of this set.

enum TodayCard: String, CaseIterable, Codable, Identifiable {
    case strain, sleep, hrv, rhr, spo2, skinTemp, respRate, exercise

    var id: String { rawValue }

    var title: String {
        switch self {
        case .strain:    return "Day Strain"
        case .sleep:     return "Last Night"
        case .hrv:       return "HRV"
        case .rhr:       return "Resting HR"
        case .spo2:      return "SpO₂"
        case .skinTemp:  return "Skin Temp"
        case .respRate:  return "Respiratory Rate"
        case .exercise:  return "Workouts"
        }
    }
}

struct DashboardLayout: Codable, Equatable {
    var order: [TodayCard]
    var hidden: Set<TodayCard>

    /// The classic five are shown by default; the extra biometric cards (already computed
    /// server-side but previously unsurfaced) start hidden so the default view is unchanged.
    static let `default` = DashboardLayout(
        order: [.strain, .sleep, .hrv, .rhr, .spo2, .skinTemp, .respRate, .exercise],
        hidden: [.spo2, .skinTemp, .respRate, .exercise]
    )

    /// Visible cards in display order.
    var visibleOrdered: [TodayCard] { order.filter { !hidden.contains($0) } }

    /// Fold in any cards added in newer app versions so a saved layout still shows them
    /// (appended at the end, hidden by default — matches the `default` policy).
    mutating func reconcile() {
        let known = Set(order)
        for c in TodayCard.allCases where !known.contains(c) {
            order.append(c)
            hidden.insert(c)
        }
        // Drop any cases that no longer exist (defensive against renames/removals).
        let valid = Set(TodayCard.allCases)
        order.removeAll { !valid.contains($0) }
        hidden = hidden.intersection(valid)
    }
}

enum DashboardLayoutStore {
    static let key = "com.openwhoop.dashboard.v1"

    static func load() -> DashboardLayout {
        guard let data = UserDefaults.standard.data(forKey: key),
              var layout = try? JSONDecoder().decode(DashboardLayout.self, from: data) else {
            return .default
        }
        layout.reconcile()
        return layout
    }

    static func save(_ layout: DashboardLayout) {
        if let data = try? JSONEncoder().encode(layout) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }
}
