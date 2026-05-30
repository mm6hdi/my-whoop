import XCTest
@testable import OpenWhoop

final class DashboardLayoutTests: XCTestCase {

    func testDefaultShowsClassicFiveOnly() {
        // Extras (spo2/skinTemp/respRate/exercise) start hidden.
        XCTAssertEqual(DashboardLayout.default.visibleOrdered, [.strain, .sleep, .hrv, .rhr])
    }

    func testToggleVisibility() {
        var l = DashboardLayout.default
        l.hidden.remove(.spo2)
        XCTAssertEqual(l.visibleOrdered, [.strain, .sleep, .hrv, .rhr, .spo2])
        l.hidden.insert(.strain)
        XCTAssertEqual(l.visibleOrdered, [.sleep, .hrv, .rhr, .spo2])
    }

    func testReorderReflectedInVisibleOrder() {
        var l = DashboardLayout.default
        // Move strain to the end (pure array reorder; mirrors what .onMove does).
        l.order = [.sleep, .hrv, .rhr, .strain, .spo2, .skinTemp, .respRate, .exercise]
        XCTAssertEqual(l.visibleOrdered, [.sleep, .hrv, .rhr, .strain])
    }

    func testReconcileAddsMissingCardsHidden() {
        var l = DashboardLayout(order: [.strain], hidden: [])
        l.reconcile()
        XCTAssertEqual(Set(l.order), Set(TodayCard.allCases))   // every case now present
        XCTAssertEqual(l.visibleOrdered, [.strain])             // only the originally-present, visible one
        for c in TodayCard.allCases where c != .strain {
            XCTAssertTrue(l.hidden.contains(c), "newly added \(c) should default hidden")
        }
    }

    func testCodableRoundTrip() throws {
        var l = DashboardLayout.default
        l.hidden.remove(.exercise)
        l.order = [.sleep, .strain, .hrv, .rhr, .spo2, .skinTemp, .respRate, .exercise]
        let data = try JSONEncoder().encode(l)
        let back = try JSONDecoder().decode(DashboardLayout.self, from: data)
        XCTAssertEqual(back, l)
        XCTAssertEqual(back.visibleOrdered, [.sleep, .strain, .hrv, .rhr, .exercise])
    }

    func testStoreRoundTripViaUserDefaults() {
        var l = DashboardLayout.default
        l.hidden.remove(.respRate)
        DashboardLayoutStore.save(l)
        XCTAssertEqual(DashboardLayoutStore.load().visibleOrdered, l.visibleOrdered)
        UserDefaults.standard.removeObject(forKey: DashboardLayoutStore.key)   // repeatable
    }
}
