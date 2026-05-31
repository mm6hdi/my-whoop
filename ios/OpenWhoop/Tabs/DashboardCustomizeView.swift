import SwiftUI

// MARK: - DashboardCustomizeView
// Drag-to-reorder + show/hide editor for the Today cards. Mutates the bound DashboardLayout
// and persists every change (same UserDefaults-backed store the Today tab loads from).

struct DashboardCustomizeView: View {
    @Binding var layout: DashboardLayout
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach(layout.order) { card in
                        HStack {
                            Image(systemName: "line.3.horizontal")
                                .font(.system(size: 13))
                                .foregroundStyle(WH.Color.textSecondary.opacity(0.6))
                            Text(card.title)
                                .foregroundStyle(WH.Color.textPrimary)
                            Spacer()
                            Toggle("", isOn: binding(for: card)).labelsHidden()
                        }
                        .listRowBackground(WH.Color.surface)
                    }
                    .onMove { from, to in
                        layout.order.move(fromOffsets: from, toOffset: to)
                        persist()
                    }
                } header: {
                    Text("Cards — drag to reorder, toggle to show/hide")
                } footer: {
                    Text("The recovery ring stays pinned at the top.")
                        .font(WH.Font.caption)
                        .foregroundStyle(WH.Color.textSecondary)
                }
            }
            .environment(\.editMode, .constant(.active))   // always-on drag handles
            .scrollContentBackground(.hidden)
            .background(WH.Color.background)
            .navigationTitle("Customize")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .preferredColorScheme(.dark)
    }

    private func binding(for card: TodayCard) -> Binding<Bool> {
        Binding(
            get: { !layout.hidden.contains(card) },
            set: { show in
                if show { layout.hidden.remove(card) } else { layout.hidden.insert(card) }
                persist()
            }
        )
    }

    private func persist() { DashboardLayoutStore.save(layout) }
}

#Preview("Customize") {
    DashboardCustomizeView(layout: .constant(.default))
}
