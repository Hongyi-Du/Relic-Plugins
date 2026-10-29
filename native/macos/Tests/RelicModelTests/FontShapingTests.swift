import XCTest
import AppKit
import CoreText
@testable import Relic

@MainActor final class FontShapingTests: XCTestCase {
    // Recorded DOMRange widths from the macOS reference capture, 4e18fc3,
    // en-US/light/1440x900/group. These are regression assertions only;
    // production rendering and element extraction never read this fixture.
    func testNativeParagraphAdvancesMatchReferenceWithoutAutomaticTracking() throws {
        let samples: [(String, CGFloat, CGFloat)] = [
            ("secretary made the subgroup “Native interface review”, led by designer", 12, 419.4375),
            ("secretary's task T1 is blocked", 12, 172.796875),
            ("Decisions will stay in the right pane without interrupting the conversation.", 14, 502.15625),
            ("Organization", 12, 73.96875)
        ]
        for (text, size, referenceWidth) in samples {
            let production = NativeTextStyle.render(AttributedString(text), size: size)
            let storage = NSTextStorage(attributedString: production), layout = NSLayoutManager()
            let container = NSTextContainer(containerSize: NSSize(width: 10_000, height: 1_000))
            container.lineFragmentPadding = 0
            storage.addLayoutManager(layout); layout.addTextContainer(container); layout.ensureLayout(for: container)
            let actual = layout.usedRect(for: container).width
            let defaultValue = NSAttributedString(string: text, attributes: [.font: RelicStyle.nativeFont(size, weight: 400)])
            let font = RelicStyle.nativeFont(size, weight: 400)
            if text == samples[0].0 {
                print("FONT DESCRIPTOR \(font.fontDescriptor.fontAttributes)")
                print("FONT VARIATION \(String(describing: CTFontCopyVariation(font as CTFont)))")
                print("FONT AXES \(String(describing: CTFontCopyVariationAxes(font as CTFont)))")
                print("FONT URL \(String(describing: CTFontCopyAttribute(font as CTFont, kCTFontURLAttribute)))")
                for optical in ["none", "auto"] {
                    let descriptor = CTFontDescriptorCreateWithAttributes([kCTFontOpticalSizeAttribute: optical] as CFDictionary)
                    let variant = CTFontCreateCopyWithAttributes(font as CTFont, size, nil, descriptor)
                    let value = NSAttributedString(string: text, attributes: [.font: variant])
                    print("FONT OPTICAL \(optical) width=\(CTLineGetTypographicBounds(CTLineCreateWithAttributedString(value), nil, nil, nil))")
                }
                let variants: [[NSAttributedString.Key: Any]] = [[.font: font, .kern: 0], [.font: font, .tracking: 0, .kern: 0], [.font: font, NSAttributedString.Key(kCTTrackingAttributeName as String): 0]]
                for attributes in variants {
                    let value = NSAttributedString(string: text, attributes: attributes)
                    print("FONT ATTRIBUTES \(attributes) width=\(CTLineGetTypographicBounds(CTLineCreateWithAttributedString(value), nil, nil, nil))")
                }
                let line = CTLineCreateWithAttributedString(defaultValue)
                for run in CTLineGetGlyphRuns(line) as! [CTRun] {
                    let count = CTRunGetGlyphCount(run)
                    var glyphs = [CGGlyph](repeating: 0, count: count), positions = [CGPoint](repeating: .zero, count: count), advances = [CGSize](repeating: .zero, count: count)
                    CTRunGetGlyphs(run, CFRange(location: 0, length: 0), &glyphs)
                    CTRunGetPositions(run, CFRange(location: 0, length: 0), &positions)
                    let nominal = CTFontGetAdvancesForGlyphs(font as CTFont, .horizontal, glyphs, &advances, count)
                    print("FONT GLYPHS nominal=\(nominal) glyphs=\(glyphs) positions=\(positions.map(\.x)) advances=\(advances.map(\.width))")
                }
            }
            let defaultWidth = CTLineGetTypographicBounds(CTLineCreateWithAttributedString(defaultValue), nil, nil, nil)
            let shaped = CTLineGetTypographicBounds(CTLineCreateWithAttributedString(production), nil, nil, nil)
            print("FONT ADVANCES size=\(size) TextKit=\(actual) CoreText=\(shaped) defaultTracking=\(defaultWidth) reference=\(referenceWidth) text=\(text)")
            XCTAssertEqual(actual, referenceWidth, accuracy: 0.5, text)
            XCTAssertEqual(actual, shaped, accuracy: 0.01, "Sizing and actual attributed shaping must agree")
        }
    }
}
