import SwiftUI

// MARK: - TodayView
// The command-centre "Today" tab. Renders server-cached recovery/strain/sleep/HRV/RHR
// metrics pulled from MetricsRepository.
// Tapping any metric card → MetricDetailView (full history, range selector).

struct TodayView: View {
    @EnvironmentObject private var metrics: MetricsRepository
    @EnvironmentObject private var live: LiveViewModel

    // Card order + visibility (persisted); the recovery hero ring is pinned separately.
    @State private var layout = DashboardLayoutStore.load()
    @State private var showCustomize = false

    var body: some View {
        NavigationStack {
            ZStack {
                WH.Color.background.ignoresSafeArea()

                Group {
                    if metrics.isRefreshing && metrics.today == nil && metrics.lastNight == nil {
                        loadingView
                    } else {
                        scrollContent
                    }
                }
            }
            // Hide the system nav bar on the root so the custom ScreenHeader sits tight
            // below the status bar/Dynamic Island. Pushed detail views manage their own bars.
            .toolbar(.hidden, for: .navigationBar)
        }
        .preferredColorScheme(.dark)
        .task { await metrics.refresh() }
        .refreshable { await metrics.refresh() }
    }

    // MARK: - Loading

    private var loadingView: some View {
        VStack(spacing: WH.Spacing.md) {
            ProgressView()
                .tint(WH.Color.textSecondary)
            Text("Loading metrics…")
                .font(WH.Font.caption)
                .foregroundStyle(WH.Color.textSecondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Main scroll content

    private var scrollContent: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: WH.Spacing.lg) {

                // Custom tight header (replaces the hidden system large-title nav bar)
                // with a customize (reorder/show-hide) affordance.
                headerRow

                // Hero recovery ring (pinned; tappable → recovery history)
                heroSection

                // Customizable cards — order + visibility from DashboardLayout.
                ForEach(layout.visibleOrdered) { card in
                    cardView(card)
                }

                if let err = metrics.lastError {
                    errorBanner(err)
                }

                if metrics.today == nil && metrics.lastNight == nil && !metrics.isRefreshing {
                    emptyState
                }

                strapNote
                syncFooter

                Spacer(minLength: WH.Spacing.xl)
            }
            .padding(WH.Spacing.md)
        }
        .background(WH.Color.background)
        .sheet(isPresented: $showCustomize) {
            DashboardCustomizeView(layout: $layout)
        }
    }

    // MARK: - Header (title + customize)

    private var headerRow: some View {
        HStack(alignment: .firstTextBaseline) {
            ScreenHeader("Today")
            Spacer(minLength: 0)
            Button { showCustomize = true } label: {
                Image(systemName: "slider.horizontal.3")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundStyle(WH.Color.textSecondary)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Customize dashboard")
        }
    }

    // MARK: - Card dispatch (driven by DashboardLayout)

    @ViewBuilder
    private func cardView(_ card: TodayCard) -> some View {
        switch card {
        case .strain:
            NavigationLink(destination: MetricDetailView(kind: .strain)) { strainCard }
                .buttonStyle(.plain)
        case .sleep:
            NavigationLink(destination: MetricDetailView(kind: .sleepDuration)) { sleepCard }
                .buttonStyle(.plain)
        case .hrv:
            NavigationLink(destination: MetricDetailView(kind: .hrv)) {
                hrvCard.frame(maxWidth: .infinity)
            }
            .buttonStyle(.plain)
        case .rhr:
            NavigationLink(destination: MetricDetailView(kind: .rhr)) {
                rhrCard.frame(maxWidth: .infinity)
            }
            .buttonStyle(.plain)
        case .spo2:
            extraCard(title: "SpO₂",
                      value: metrics.today?.spo2Pct.map { String(format: "%.0f", $0) } ?? "—",
                      unit: metrics.today?.spo2Pct != nil ? "%" : nil,
                      accent: WH.Color.recoveryGreen)
        case .skinTemp:
            extraCard(title: "Skin Temp Δ",
                      value: metrics.today?.skinTempDevC.map { String(format: "%+.1f", $0) } ?? "—",
                      unit: metrics.today?.skinTempDevC != nil ? "°C" : nil,
                      accent: WH.Color.recoveryYellow)
        case .respRate:
            extraCard(title: "Respiratory Rate",
                      value: metrics.today?.respRateBpm.map { String(format: "%.1f", $0) } ?? "—",
                      unit: metrics.today?.respRateBpm != nil ? "rpm" : nil,
                      accent: WH.Color.strainBlue)
        case .exercise:
            extraCard(title: "Workouts",
                      value: metrics.today?.exerciseCount.map(String.init) ?? "—",
                      unit: nil,
                      accent: WH.Color.textPrimary)
        }
    }

    /// A plain (non-navigating) metric card for the extra biometric signals.
    private func extraCard(title: String, value: String, unit: String?, accent: Color) -> some View {
        MetricCard(title: title, value: value, unit: unit, accentColor: accent)
    }

    // MARK: - Hero section (recovery ring → recovery history)

    private var heroSection: some View {
        HStack {
            Spacer()
            NavigationLink(destination: MetricDetailView(kind: .recovery)) {
                if let recovery = metrics.today?.recovery {
                    RecoveryRing(percent: recovery * 100, size: 200, strokeWidth: 16)
                } else {
                    pendingRecoveryRing
                }
            }
            .buttonStyle(.plain)
            Spacer()
        }
        .padding(.top, WH.Spacing.sm)
    }

    private var pendingRecoveryRing: some View {
        ZStack {
            Circle()
                .stroke(WH.Color.ringTrack, lineWidth: 16)
            Circle()
                .stroke(WH.Color.ringTrack.opacity(0.5), lineWidth: 24)
                .blur(radius: 6)

            VStack(spacing: WH.Spacing.xs) {
                Text("—")
                    .font(WH.Font.metricHero(size: 64))
                    .foregroundStyle(WH.Color.textSecondary)
                    .monospacedDigit()
                Text("RECOVERY")
                    .font(WH.Font.cardTitle)
                    .foregroundStyle(WH.Color.textSecondary)
                    .tracking(1.5)
                Text("Pending")
                    .font(WH.Font.caption)
                    .foregroundStyle(WH.Color.textSecondary.opacity(0.7))
            }
        }
        .frame(width: 200, height: 200)
    }

    // MARK: - Strain card

    private var strainCard: some View {
        let value: String = {
            guard let s = metrics.today?.strain else { return "—" }
            return String(format: "%.1f", s)
        }()
        let hasStrain = metrics.today?.strain != nil
        return MetricCard(title: "Day Strain",
                          value: value,
                          unit: hasStrain ? "/ 21" : nil,
                          accentColor: hasStrain ? WH.Color.strainBlue : WH.Color.textSecondary)
    }

    // MARK: - Sleep card

    private var sleepCard: some View {
        let sleepMin: Double? = {
            if let m = metrics.today?.totalSleepMin, m > 0 { return m }
            if let s = metrics.lastNight {
                let d = Double(s.endTs - s.startTs) / 60
                return d > 0 ? d : nil
            }
            return nil
        }()

        let efficiency: Double? = {
            guard sleepMin != nil else { return nil }
            if let e = metrics.today?.efficiency, e > 0 { return e }
            if let e = metrics.lastNight?.efficiency, e > 0 { return e }
            return nil
        }()

        return VStack(alignment: .leading, spacing: WH.Spacing.sm) {
            HStack {
                Text("LAST NIGHT")
                    .font(WH.Font.cardTitle)
                    .foregroundStyle(WH.Color.textSecondary)
                    .tracking(1.2)
                Spacer()
            }

            if let min = sleepMin {
                HStack(alignment: .lastTextBaseline, spacing: WH.Spacing.sm) {
                    Text(formatSleepMinutes(min))
                        .font(WH.Font.metricLarge())
                        .foregroundStyle(WH.Color.textPrimary)
                        .monospacedDigit()

                    if let eff = efficiency {
                        Text("·  \(Int((eff * 100).rounded()))% efficiency")
                            .font(WH.Font.unit)
                            .foregroundStyle(WH.Color.textSecondary)
                    }

                    Spacer(minLength: 0)
                }
            } else {
                Text("No sleep data")
                    .font(WH.Font.metricMedium())
                    .foregroundStyle(WH.Color.textSecondary)
            }
        }
        .padding(WH.Spacing.md)
        .background(WH.Color.surface,
                    in: RoundedRectangle(cornerRadius: WH.Radius.card, style: .continuous))
    }

    // MARK: - HRV + RHR cards (rendered individually via cardView)

    private var hrvCard: some View {
        let hrv = metrics.today?.avgHrv ?? metrics.lastNight?.avgHrv
        let value = hrv.map { String(format: "%.0f", $0) } ?? "—"
        let accent: Color = hrv != nil ? WH.Color.recoveryGreen : WH.Color.textSecondary
        return MetricCard(title: "HRV",
                          value: value,
                          unit: hrv != nil ? "ms" : nil,
                          accentColor: accent)
    }

    private var rhrCard: some View {
        let rhr = metrics.today?.restingHr ?? metrics.lastNight?.restingHr
        let value = rhr.map { "\($0)" } ?? "—"
        let accent: Color = rhr != nil ? WH.Color.textPrimary : WH.Color.textSecondary
        return MetricCard(title: "Resting HR",
                          value: value,
                          unit: rhr != nil ? "bpm" : nil,
                          accentColor: accent)
    }

    // MARK: - Empty state

    private var emptyState: some View {
        HStack {
            Spacer()
            VStack(spacing: WH.Spacing.sm) {
                Image(systemName: "arrow.triangle.2.circlepath")
                    .font(.system(size: 32, weight: .light))
                    .foregroundStyle(WH.Color.textSecondary)
                Text("No metrics yet")
                    .font(.system(size: 17, weight: .semibold, design: .rounded))
                    .foregroundStyle(WH.Color.textPrimary)
                Text("Pull down to refresh")
                    .font(WH.Font.caption)
                    .foregroundStyle(WH.Color.textSecondary)
            }
            .padding(.vertical, WH.Spacing.xxl)
            Spacer()
        }
    }

    // MARK: - Live strap status row (HR + battery when connected; caption when not)

    /// Compact pill showing a single live reading (HR or battery).
    private func liveChip(icon: String, label: String, color: Color) -> some View {
        HStack(spacing: WH.Spacing.xs) {
            Image(systemName: icon)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(color)
            Text(label)
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundStyle(WH.Color.textPrimary)
                .monospacedDigit()
        }
        .padding(.horizontal, WH.Spacing.sm)
        .padding(.vertical, WH.Spacing.xs)
        .background(WH.Color.surface2,
                    in: Capsule())
    }

    /// Shows live HR + battery pills when connected; otherwise shows the connect caption.
    private var strapNote: some View {
        Group {
            if live.state.connected, let hr = live.state.heartRate {
                HStack(spacing: WH.Spacing.sm) {
                    liveChip(icon: "heart.fill",
                             label: "\(hr) BPM LIVE",
                             color: WH.Color.recoveryRed)
                    if let bat = live.state.batteryPct {
                        let pct = Int(bat.rounded())
                        let batColor: Color = pct > 30 ? WH.Color.recoveryGreen
                                                       : WH.Color.recoveryYellow
                        let batIcon = pct > 70 ? "battery.100" :
                                      pct > 30 ? "battery.50"  : "battery.25"
                        liveChip(icon: batIcon,
                                 label: "\(pct)%",
                                 color: batColor)
                    }
                    Spacer()
                }
            } else {
                HStack(spacing: WH.Spacing.xs) {
                    Image(systemName: "wave.3.right")
                        .font(.system(size: 11, weight: .regular))
                        .foregroundStyle(WH.Color.textSecondary.opacity(0.5))
                    Text("Live HR & battery appear when your strap is connected (Device tab)")
                        .font(WH.Font.caption)
                        .foregroundStyle(WH.Color.textSecondary.opacity(0.5))
                        .lineLimit(2)
                }
            }
        }
    }

    // MARK: - Sync footer

    private var syncFooter: some View {
        HStack {
            if metrics.isRefreshing {
                HStack(spacing: WH.Spacing.xs) {
                    ProgressView()
                        .scaleEffect(0.7)
                        .tint(WH.Color.textSecondary)
                    Text("Updating…")
                        .font(WH.Font.caption)
                        .foregroundStyle(WH.Color.textSecondary)
                }
            } else if let at = metrics.lastRefreshedAt {
                Text("Updated \(relativeTime(from: at))")
                    .font(WH.Font.caption)
                    .foregroundStyle(WH.Color.textSecondary)
            }
            Spacer()
        }
    }

    // MARK: - Error banner

    private func errorBanner(_ message: String) -> some View {
        HStack(spacing: WH.Spacing.sm) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(WH.Color.recoveryYellow)
            Text(message)
                .font(WH.Font.caption)
                .foregroundStyle(WH.Color.textSecondary)
                .lineLimit(2)
            Spacer()
        }
        .padding(WH.Spacing.sm)
        .background(WH.Color.surface2,
                    in: RoundedRectangle(cornerRadius: WH.Radius.chip, style: .continuous))
    }

    // MARK: - Formatting helpers

    private func formatSleepMinutes(_ totalMin: Double) -> String {
        guard totalMin > 0 else { return "—" }
        let hours = Int(totalMin) / 60
        let mins  = Int(totalMin) % 60
        if hours > 0 && mins > 0 { return "\(hours)h \(mins)m" }
        if hours > 0              { return "\(hours)h" }
        return "\(mins)m"
    }

    private func relativeTime(from date: Date) -> String {
        let elapsed = Int(-date.timeIntervalSinceNow)
        switch elapsed {
        case ..<5:   return "just now"
        case ..<60:  return "\(elapsed)s ago"
        case ..<3600:
            let m = elapsed / 60
            return "\(m)m ago"
        default:
            let h = elapsed / 3600
            return "\(h)h ago"
        }
    }
}

// MARK: - Preview

#Preview("Today — empty (cold start)") {
    TodayView()
        .environmentObject(MetricsRepository(deviceId: "preview"))
}

#Preview("Today — design gallery reference") {
    DesignGallery()
}
