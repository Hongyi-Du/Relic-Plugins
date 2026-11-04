import SwiftUI

struct MemberCardButton<Label: View>: View {
    @EnvironmentObject var m: Model
    let member: String
    @ViewBuilder let label: () -> Label
    @State private var anchor = CGRect.zero
    var body: some View {
        Button { m.openCard(member, anchor: anchor) } label: { label() }
            .background(GeometryReader { proxy in
                Color.clear.preference(key: CardAnchor.self, value: proxy.frame(in: .named("relic-window")))
            }).onPreferenceChange(CardAnchor.self) { anchor = $0 }
    }
}
private struct CardAnchor: PreferenceKey {
    static var defaultValue = CGRect.zero
    static func reduce(value: inout CGRect, nextValue: () -> CGRect) { value = nextValue() }
}
