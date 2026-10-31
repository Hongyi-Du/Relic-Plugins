import XCTest
import AppKit
@testable import Relic

@MainActor final class TextMeasurementCacheTests: XCTestCase {
    func testPreferredWidthsReuseIdenticalSourceButRecomputeChangedFontAndText() {
        let cache = PreferredTextWidthCache()
        var calls = 0
        let source = NSMutableAttributedString(attributedString: NativeTextStyle.render(AttributedString("A passage"), size: 13))
        func measured(_ value: NSAttributedString) -> CGFloat {
            cache.width(value) { calls += 1; return NativeTextStyle.preferredWidth(value) }
        }
        let first = measured(source)
        XCTAssertEqual(measured(NSAttributedString(attributedString: source)), first)
        XCTAssertEqual(calls, 1)
        source.setAttributedString(NativeTextStyle.render(AttributedString("A passage"), size: 20))
        XCTAssertGreaterThan(measured(source), first)
        XCTAssertEqual(calls, 2)
        source.setAttributedString(NativeTextStyle.render(AttributedString("B passage"), size: 20))
        _ = measured(source)
        XCTAssertEqual(calls, 3)
        source.setAttributedString(NativeTextStyle.render(AttributedString("A passage"), size: 13))
        XCTAssertEqual(measured(source), first)
        XCTAssertEqual(calls, 3, "A mutable caller must not alter a retained cache key")
    }
    func testRepeatedProposalsAndChangedSourceMatchIndependentTextKitLayouts() {
        let cache = TextMeasurementCache(), paths = PathLineBreaks()
        let source = NSMutableAttributedString(string: "")
        for text in [String(repeating: "长消息 with words and /tmp/file.swift ", count: 15), "短消息", "different **style**"] {
            source.setAttributedString(NativeTextStyle.render(AttributedString(text), size: 13, lineHeight: 20))
            for width in [CGFloat(420), 140, 420, 90, 140] {
                for limit in [0, 1, 3] {
                    let mode: NSLineBreakMode = limit == 0 ? .byWordWrapping : .byTruncatingTail
                    let storage = NSTextStorage(attributedString: source), layout = NSLayoutManager()
                    let container = NSTextContainer(containerSize: CGSize(width: width, height: .greatestFiniteMagnitude))
                    container.lineFragmentPadding = 0; container.maximumNumberOfLines = limit; container.lineBreakMode = mode
                    storage.addLayoutManager(layout); layout.addTextContainer(container); layout.ensureLayout(for: container)
                    let used = layout.usedRect(for: container)
                    let measured = cache.label(source, width: width, lines: limit, mode: mode, minimum: 20, pathBreaks: paths)
                    XCTAssertEqual(measured.width, min(width, ceil(used.width)), accuracy: 0.01, "characters=\(text.count), width=\(width), lines=\(limit)")
                    XCTAssertEqual(measured.height, max(20, used.height), accuracy: 0.01, "characters=\(text.count), width=\(width), lines=\(limit)")
                }
            }
        }
    }
    func testPassageCacheInvalidatesForFontAndInlineContentChanges() {
        let cache = PassageMeasurementCache()
        for size in [CGFloat(12), 16, 12] {
            for text in [String(repeating: "Long passage. ", count: 25), "Short passage."] {
                let value = NativeTextStyle.render(AttributedString(text), size: size)
                for width in [CGFloat(200), 400, 200] {
                    for lines in [0, 3] {
                        XCTAssertEqual(cache.size(value, width: width, lines: lines), NativeTextStyle.contentSize(value, available: width, maximumLines: lines))
                    }
                }
            }
        }
    }
}
