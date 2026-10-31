import SwiftUI
import RelicCore

/// Opening a dialog must not republish the entire conversation and organization
/// model. Only this overlay subscribes to presentation changes; the live data
/// underneath keeps its existing native views and scroll position.
@MainActor final class DialogPresentation: ObservableObject {
    @Published var sheet: Model.Sheet?
}

struct DialogPresentationLayer: View {
    @ObservedObject var presentation: DialogPresentation
    var body: some View {
        if let sheet = presentation.sheet { DialogLayer(sheet: sheet) }
    }
}

// These are production window-relative layouts, shared by pointer/keyboard
// invocation and CI. The native content remains in the application's NSWindow.
struct DialogLayer: View {
    @EnvironmentObject var m: Model
    let sheet: Model.Sheet
    @State private var contentTitle = ""
    @State private var scrimIdentity = "relic-scrim/" + UUID().uuidString
    @State private var panelIdentity = "relic-dialog-panel/" + UUID().uuidString
    private var layout: DialogGeometry { DialogGeometry(kind: sheet.rawValue, window: m.windowSize) }
    private var title: String {
        switch sheet {
        case .chart: return m.t("chart.title")
        case .settings: return m.t("common.settings")
        case .details: return m.t("details.dialog")
        case .copies: return m.t("cc.title")
        default: return contentTitle
        }
    }
    var body: some View {
        ZStack(alignment: sheet == .card ? .topLeading : .center) {
            Color.clear.contentShape(Rectangle())
                .modifier(RecordedSurface(background: sheet == .card ? .clear : Color(red: 15/255, green: 14/255, blue: 12/255).opacity(0.32), kind: "region", owner: scrimIdentity))
                .accessibilityElement(children: .contain).accessibilityIdentifier(scrimIdentity).accessibilityLabel("")
                .onTapGesture { m.sheet = nil }
            panel
                .offset(x: sheet == .card ? layout.cardOrigin(anchor: m.cardAnchor).x : 0,
                        y: sheet == .card ? layout.cardOrigin(anchor: m.cardAnchor).y : 0)
        }.frame(maxWidth: .infinity, maxHeight: .infinity)
            .onExitCommand { m.sheet = nil }
    }
    private var panel: some View {
        Group {
            if let height = layout.height {
                SheetContent(sheet: sheet).frame(width: layout.width, height: height)
            } else {
                FittingScroll(maxHeight: layout.maximumHeight, accessibilityOwner: panelIdentity, accessibilityTitle: title) {
                    // The reference card's 18px padding sits inside its 1px
                    // border. RecordedSurface draws that border inside the
                    // outer frame, so reserve it in the real content layout.
                    SheetContent(sheet: sheet).padding(sheet == .card ? 19 : 22)
                }.frame(width: layout.width)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .modifier(RecordedSurface(background: RelicStyle.card, border: sheet == .card ? RelicStyle.line : .clear, borderWidth: sheet == .card ? 1 : 0, radius: 16, kind: sheet == .card ? "card" : "region", owner: panelIdentity, shadows: SurfaceShadow.dialog, nativeFill: true))
        .overlay(alignment: .topTrailing) {
            if sheet == .settings {
                IconButton(title: m.t("common.close"), icon: "x") { m.sheet = nil }.padding(14)
            }
        }.measuredRegion("dialog", createsAccessibilityContainer: false)
            .modifier(DialogAccessibilityOwner(identifier: layout.height == nil ? nil : panelIdentity, title: title))
            .onPreferenceChange(DialogTitlePreference.self) { contentTitle = $0 }
    }
}

// A content-sized dialog is itself the scroll region. Let its actual
// NSScrollView own the name and controls instead of adding a second accessible
// region at the same bounds. Fixed-height dialogs keep their native container.
private struct DialogAccessibilityOwner: ViewModifier {
    let identifier: String?
    let title: String
    @ViewBuilder func body(content: Content) -> some View {
        if let identifier {
            content.accessibilityElement(children: .contain)
                .accessibilityLabel(title).accessibilityIdentifier(identifier)
        } else { content }
    }
}

struct DialogTitlePreference: PreferenceKey {
    static var defaultValue = ""
    static func reduce(value: inout String, nextValue: () -> String) {
        let next = nextValue(); if !next.isEmpty { value = next }
    }
}

// Content determines the height until the viewport limit is reached. The outer
// scroll view then scrolls the same content, rather than clipping a fixed sheet.
struct FittingScroll<Content: View>: View {
    let maxHeight: CGFloat
    var accessibilityOwner: String? = nil
    var accessibilityTitle = ""
    @ViewBuilder let content: () -> Content
    @State private var contentHeight: CGFloat = 0
    var body: some View {
        ScrollView {
            content().frame(maxWidth: .infinity, alignment: .topLeading)
                .background(GeometryReader { proxy in Color.clear.preference(key: DialogContentHeight.self, value: proxy.size.height) })
                .background {
                    if let accessibilityOwner {
                        NativeScrollOwner(identifier: accessibilityOwner, title: accessibilityTitle)
                    }
                }
        }.frame(height: min(maxHeight, contentHeight > 0 ? contentHeight : maxHeight))
            .onPreferenceChange(DialogContentHeight.self) { contentHeight = $0 }
    }
}
private struct DialogContentHeight: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = max(value, nextValue()) }
}
