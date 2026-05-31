import SwiftUI

// MARK: - CoachView
// A chat assistant grounded in the user's OWN metrics. Today's Claude insight (summary +
// recommendations) sits at the top as a starting point; below it, a chat that sends the
// full history to the server's /v1/chat (Claude) via MetricsRepository.chat. All
// server-side — no API key on the device. Degrades gracefully when the server has no
// Claude key (the assistant says so instead of erroring).

private struct ChatTurn: Identifiable, Equatable {
    let id = UUID()
    let role: String   // "user" | "assistant"
    let text: String
}

struct CoachView: View {
    @EnvironmentObject private var metrics: MetricsRepository

    @State private var turns: [ChatTurn] = []
    @State private var input: String = ""
    @State private var sending = false
    @State private var insight: Insight?

    var body: some View {
        NavigationStack {
            ZStack {
                WH.Color.background.ignoresSafeArea()
                VStack(spacing: 0) {
                    ScreenHeader("Coach")
                    transcript
                    inputBar
                }
            }
            .toolbar(.hidden, for: .navigationBar)
        }
        .preferredColorScheme(.dark)
        .task { insight = await metrics.insight(forDay: metrics.todayString()) }
    }

    // MARK: - Transcript

    private var transcript: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: WH.Spacing.md) {
                    if let ins = insight { insightCard(ins) }
                    if turns.isEmpty { emptyState }
                    ForEach(turns) { bubble($0) }
                    if sending { typingRow }
                    Color.clear.frame(height: 1).id("bottom")
                }
                .padding(WH.Spacing.md)
            }
            .onChange(of: turns.count) { _ in
                withAnimation { proxy.scrollTo("bottom", anchor: .bottom) }
            }
        }
    }

    private func bubble(_ t: ChatTurn) -> some View {
        let isUser = t.role == "user"
        return HStack {
            if isUser { Spacer(minLength: 44) }
            Text(t.text)
                .font(.system(size: 15))
                .foregroundStyle(isUser ? Color.white : WH.Color.textPrimary)
                .padding(.horizontal, WH.Spacing.md)
                .padding(.vertical, WH.Spacing.sm)
                .background(isUser ? WH.Color.strainBlue : WH.Color.surface,
                            in: RoundedRectangle(cornerRadius: WH.Radius.card, style: .continuous))
            if !isUser { Spacer(minLength: 44) }
        }
    }

    private var typingRow: some View {
        HStack {
            Text("…")
                .font(.system(size: 18, weight: .bold))
                .foregroundStyle(WH.Color.textSecondary)
                .padding(.horizontal, WH.Spacing.md)
                .padding(.vertical, WH.Spacing.sm)
                .background(WH.Color.surface, in: RoundedRectangle(cornerRadius: WH.Radius.card))
            Spacer(minLength: 44)
        }
    }

    private func insightCard(_ ins: Insight) -> some View {
        VStack(alignment: .leading, spacing: WH.Spacing.sm) {
            Text("TODAY")
                .font(WH.Font.cardTitle)
                .foregroundStyle(WH.Color.textSecondary)
                .tracking(1.2)
            Text(ins.summary)
                .font(.system(size: 15))
                .foregroundStyle(WH.Color.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(ins.recommendations, id: \.self) { r in
                HStack(alignment: .top, spacing: WH.Spacing.xs) {
                    Text("•").foregroundStyle(WH.Color.recoveryGreen)
                    Text(r).font(WH.Font.caption).foregroundStyle(WH.Color.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(WH.Spacing.md)
        .background(WH.Color.surface,
                    in: RoundedRectangle(cornerRadius: WH.Radius.card, style: .continuous))
    }

    private var emptyState: some View {
        VStack(alignment: .leading, spacing: WH.Spacing.xs) {
            Text("Ask about your data")
                .font(.system(size: 17, weight: .semibold, design: .rounded))
                .foregroundStyle(WH.Color.textPrimary)
            Text("e.g. “Why was my recovery low this week?” or “How did last night's sleep affect my HRV?”")
                .font(WH.Font.caption)
                .foregroundStyle(WH.Color.textSecondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, WH.Spacing.sm)
    }

    // MARK: - Input

    private var inputBar: some View {
        HStack(spacing: WH.Spacing.sm) {
            TextField("Ask your coach…", text: $input, axis: .vertical)
                .textFieldStyle(.plain)
                .font(.system(size: 15))
                .foregroundStyle(WH.Color.textPrimary)
                .padding(.horizontal, WH.Spacing.md)
                .padding(.vertical, WH.Spacing.sm)
                .background(WH.Color.surface2, in: RoundedRectangle(cornerRadius: WH.Radius.card, style: .continuous))
                .lineLimit(1...4)
                .disabled(sending)
            Button(action: { Task { await send() } }) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 30))
                    .foregroundStyle(canSend ? WH.Color.strainBlue : WH.Color.textSecondary)
            }
            .disabled(!canSend)
        }
        .padding(WH.Spacing.md)
    }

    private var canSend: Bool {
        !sending && !input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    @MainActor
    private func send() async {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        input = ""
        turns.append(ChatTurn(role: "user", text: text))
        sending = true
        let history = turns.map { ["role": $0.role, "content": $0.text] }
        let reply = await metrics.chat(history)
        sending = false
        turns.append(ChatTurn(
            role: "assistant",
            text: (reply?.isEmpty == false) ? reply!
                : "I couldn't reach the coach. Check that your server is online and ANTHROPIC_API_KEY is set."))
    }
}

// MARK: - Preview

#Preview("Coach") {
    CoachView()
        .environmentObject(MetricsRepository(deviceId: "preview"))
}
