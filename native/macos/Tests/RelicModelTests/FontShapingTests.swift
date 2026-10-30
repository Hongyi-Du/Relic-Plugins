import XCTest
import AppKit
import CoreText
@testable import Relic

@MainActor final class FontShapingTests: XCTestCase {
    func testRecipientArrowUsesTheActualReferenceSystemFallbackAndAdvance() throws {
        // Actual 682034a DOM Range and CDP face list for the group recipient.
        let view = ReferenceLabel("→ 全体", size: 12, lineHeight: 15.6, lines: 0).makeLabelView()
        (view.layoutManager as? NativeGlyphLayoutManager)?.recordDraws = true
        view.frame = NSRect(x: 0, y: 0, width: 160, height: 40)
        view.textContainer?.containerSize = view.bounds.size
        let bitmap = try XCTUnwrap(CaptureRaster.forView(view)); view.cacheDisplay(in: view.bounds, to: bitmap)
        let row = try XCTUnwrap(ElementCapture.textRuns(view).first)
        let style = try XCTUnwrap(row["style"] as? [String: Any])
        let faces = try XCTUnwrap(style["rendered_fonts"] as? [[String: Any]])
        XCTAssertEqual(Set(faces.compactMap { $0["postscript_name"] as? String }), [".SFNS-Regular", "PingFangSC-Regular"])
        let rect = try XCTUnwrap(row["local_rect"] as? NSValue).rectValue
        XCTAssertEqual(rect.width, 39.625, accuracy: 0.5)
    }

    func testChineseStrongEmphasisKeepsTheBaseOpticalConfigurationAndMeasuredAdvance() throws {
        // Actual DOM Range from bbe04a3 zh-CN/light/1440x900/group. The old
        // NSFontManager conversion lost optical sizing and measured 168px.
        let value = try AttributedString(markdown: "**聊天、概况、工作区、设置**")
        let production = NativeTextStyle.render(value, size: 14)
        let font = try XCTUnwrap(production.attribute(.font, at: 0, effectiveRange: nil) as? NSFont)
        XCTAssertEqual(production.attribute(.relicConfiguredFontWeight, at: 0, effectiveRange: nil) as? Int, 700)
        XCTAssertEqual(ElementCapture.cssWeight(font), 600, "The actual selected Semibold face must remain distinct from the requested bold style")
        XCTAssertEqual(CTFontCopyAttribute(font as CTFont, kCTFontOpticalSizeAttribute) as? String, "auto")
        let actual = CTLineGetTypographicBounds(CTLineCreateWithAttributedString(production), nil, nil, nil)
        print("FONT STRONG CJK actual=\(actual) reference=171.375")
        XCTAssertEqual(actual, 171.375, accuracy: 0.5)
    }
    func testNativeStrongEmphasisPreservesTheReferenceFaceAndOpticalAdvances() throws {
        // Independent DOMRange / CDP font evidence from 8fbed05,
        // en-US/light/1440x900/group. Never consumed by production rendering.
        let value = try AttributedString(markdown: "**Chat, Overview, Workspace, and Settings**")
        let production = NativeTextStyle.render(value, size: 14)
        let line = CTLineCreateWithAttributedString(production)
        let actual = CTLineGetTypographicBounds(line, nil, nil, nil)
        let faces = ElementCapture.reshapedFonts(production).compactMap { $0["postscript_name"] as? String }
        print("FONT STRONG actual=\(actual) reference=292.40625 faces=\(faces)")
        XCTAssertEqual(actual, 292.40625, accuracy: 0.5)
        XCTAssertEqual(Set(faces), ["PingFangSC-Semibold"])
    }
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
