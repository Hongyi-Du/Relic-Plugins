import XCTest
import AppKit
@testable import Relic

@MainActor final class NativeTextPreparationTests: XCTestCase {
    func testRealFontAndGlyphPreparationLeavesTheMainActor() async {
        let result = await NativeTextPreparation.shared.prepare("秘书处 Group chat 研发 👩🏽‍💻")
        XCTAssertFalse(result.mainThread)
        XCTAssertEqual(result.styles, 13)
        XCTAssertGreaterThan(result.glyphs, 0)
    }
    func testCachedFontMetricsKeepIndependentTextKitBaselines() {
        for size in [CGFloat(10), 12.5, 14, 24] {
            for weight in [400, 600, 700] {
                let font = RelicStyle.nativeFont(size, weight: weight)
                let native = NSLayoutManager().defaultLineHeight(for: font)
                for height in [size, size * 1.6, size * 2] {
                    XCTAssertEqual(NativeLineMetrics.baselineOffset(font: font, lineHeight: height), max(0, height - native) / 2)
                }
            }
        }
    }
}
