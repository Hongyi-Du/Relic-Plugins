import SwiftUI
import AppKit

/// SwiftUI text for labels inside rows that are rebuilt on every chat switch
/// or history page. It keeps the label's font, color and line height without
/// creating a native text view and TextKit layout for each label.
struct PlainLabel: View {
    let text: String
    var size: CGFloat = 14
    var weight = 400
    var color: Color = RelicStyle.ink
    var lineHeight: CGFloat? = nil
    var monospaced = false
    init(_ text: String, size: CGFloat = 14, weight: Int = 400, color: Color = RelicStyle.ink,
         lineHeight: CGFloat? = nil, monospaced: Bool = false) {
        self.text = text; self.size = size; self.weight = weight; self.color = color
        self.lineHeight = lineHeight; self.monospaced = monospaced
    }
    var body: some View {
        let font = monospaced ? RelicStyle.monoFont(size) : RelicStyle.nativeFont(size, weight: weight)
        let natural = font.ascender - font.descender + font.leading
        let extra = max(0, (lineHeight ?? size * 1.6) - natural)
        Text(verbatim: text)
            .font(Font(font))
            .foregroundStyle(color)
            .lineSpacing(extra)
            .padding(.vertical, extra / 2)
    }
}
