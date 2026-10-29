import SwiftUI

struct NativeToastMessage: Identifiable {
    let id = UUID()
    let text: String
    let seconds: Double
}

extension Model {
    func showNotice(_ text: String, seconds: Double) {
        // Keep legacy notice readers current while giving this production toast
        // the explicit lifetime requested by its action.
        notice = text
        if let last = toasts.indices.last { toasts[last] = NativeToastMessage(text: text, seconds: seconds) }
    }
    func dismissToast(_ id: UUID) { toasts.removeAll { $0.id == id } }
}

/// Reference notifications occupy one floating position; later notifications
/// paint above earlier ones, and each owns its independent lifetime.
struct NativeToasts: View {
    @EnvironmentObject var m: Model
    var body: some View {
        ZStack(alignment: .bottom) {
            ForEach(m.toasts) { item in
                ReferenceLabel(item.text, size: 13, color: RelicStyle.background, lineHeight: 20.8, lines: 0)
                    .padding(.horizontal, 16).padding(.vertical, 9)
                    .modifier(RecordedSurface(background: RelicStyle.ink, radius: 10, kind: "card", shadows: SurfaceShadow.dialog))
                    .frame(maxWidth: min(560, max(1, m.windowSize.width - 40)))
                    .accessibilityIdentifier("relic-toast/" + item.id.uuidString)
                    .task {
                        do { try await Task.sleep(for: .seconds(item.seconds)); m.dismissToast(item.id) }
                        catch { /* Removing a toast cancels only its own expiry. */ }
                    }
            }
        }.padding(.bottom, 28).environment(\.captureRegion, "window")
    }
}
