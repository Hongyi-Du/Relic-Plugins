import SwiftUI

struct InputSuggestionsState {
    let id: String
    let controlID: String
    let anchor: CGRect
    let values: [String]
    let choose: (String) -> Void
    var selected = 0
    mutating func move(_ direction: Int) { if !values.isEmpty { selected = (selected + direction + values.count) % values.count } }
}

struct InputSuggestionAnchor: PreferenceKey {
    static var defaultValue = CGRect.zero
    static func reduce(value: inout CGRect, nextValue: () -> CGRect) { value = nextValue() }
}

/// An ordinary native overlay owned by the same input in both interactive use
/// and capture. Keeping it in the window avoids NSPopover's nil layout-anchor
/// failure when an NSHostingView is resized between CI cases.
struct InputSuggestionsLayer: View {
    @EnvironmentObject var m: Model
    var body: some View {
        if let menu = m.inputSuggestions {
            GeometryReader { geometry in
                let width = min(max(menu.anchor.width, 120), geometry.size.width - 24)
                let height = min(CGFloat(menu.values.count) * 28 + 8, 288)
                let x = max(12, min(menu.anchor.minX, geometry.size.width - width - 12))
                let y = menu.anchor.maxY + height + 4 <= geometry.size.height - 12 ? menu.anchor.maxY + 4 : max(12, menu.anchor.minY - height - 4)
                ZStack(alignment: .topLeading) {
                    Color.clear.contentShape(Rectangle()).onTapGesture { m.inputSuggestions = nil }.accessibilityHidden(true)
                    ScrollView {
                        VStack(alignment: .leading, spacing: 0) {
                            ForEach(Array(menu.values.enumerated()), id: \.offset) { index, value in
                                TextButton(value, size: 12.5, weight: 400, height: 28, padding: 8) { menu.choose(value); m.inputSuggestions = nil }
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .buttonStyle(QuietButtonStyle(selected: index == menu.selected, selectionApplicable: true)).focusable(false)
                                    .onHover { if $0 { m.inputSuggestions?.selected = index } }
                            }
                        }.padding(4)
                    }.frame(width: width, height: height)
                        .modifier(RecordedSurface(background: RelicStyle.card, border: RelicStyle.border, borderWidth: 1, radius: 8, kind: "region", shadows: SurfaceShadow.small))
                        .accessibilityElement(children: .contain).accessibilityIdentifier("relic-suggestions/" + menu.controlID)
                        .measuredRegion("menu").offset(x: x, y: y)
                }
            }
        }
    }
}
