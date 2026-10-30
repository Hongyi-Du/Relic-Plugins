import SwiftUI
import RelicCore

// These are production window-relative layouts, shared by pointer/keyboard
// invocation and CI. The native content remains in the application's NSWindow.
struct DialogLayer: View {
    @EnvironmentObject var m: Model
    let sheet: Model.Sheet
    private var layout: DialogGeometry { DialogGeometry(kind: sheet.rawValue, window: m.windowSize) }
    var body: some View {
        ZStack(alignment: sheet == .card ? .topLeading : .center) {
            Color.clear.contentShape(Rectangle())
                .modifier(RecordedSurface(background: sheet == .card ? .clear : Color(red: 15/255, green: 14/255, blue: 12/255).opacity(0.32), kind: "region"))
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
                FittingScroll(maxHeight: layout.maximumHeight) {
                    SheetContent(sheet: sheet).padding(sheet == .card ? 18 : 22)
                }.frame(width: layout.width)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .modifier(RecordedSurface(background: RelicStyle.card, border: sheet == .card ? RelicStyle.line : .clear, borderWidth: sheet == .card ? 1 : 0, radius: 16, kind: sheet == .card ? "card" : "region", shadows: SurfaceShadow.dialog))
        .overlay(alignment: .topTrailing) {
            if [.settings, .details, .chart].contains(sheet) {
                IconButton(title: m.t("common.close"), icon: "x") { m.sheet = nil }.padding(14)
            }
        }.measuredRegion("dialog", createsAccessibilityContainer: false).accessibilityElement(children: .contain)
    }
}

// Content determines the height until the viewport limit is reached. The outer
// scroll view then scrolls the same content, rather than clipping a fixed sheet.
struct FittingScroll<Content: View>: View {
    let maxHeight: CGFloat
    @ViewBuilder let content: () -> Content
    @State private var contentHeight: CGFloat = 0
    var body: some View {
        ScrollView {
            content().frame(maxWidth: .infinity, alignment: .topLeading)
                .background(GeometryReader { proxy in Color.clear.preference(key: DialogContentHeight.self, value: proxy.size.height) })
        }.frame(height: min(maxHeight, contentHeight > 0 ? contentHeight : maxHeight))
            .onPreferenceChange(DialogContentHeight.self) { contentHeight = $0 }
    }
}
private struct DialogContentHeight: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = max(value, nextValue()) }
}
