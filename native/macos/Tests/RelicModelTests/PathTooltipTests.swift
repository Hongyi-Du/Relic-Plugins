import XCTest
import AppKit
import RelicCore
@testable import Relic

@MainActor final class PathTooltipTests: XCTestCase {
    func testLabelTooltipUsesItsExistingNativeViewWithoutChangingText() {
        let label = ReferenceLabel("11:42", size: 12).nativeHelp("Today 11:42")
        let view = label.makeLabelView()
        XCTAssertEqual(view.toolTip, "Today 11:42")
        XCTAssertEqual(view.string, "11:42")
        XCTAssertEqual(label.attributedText, ReferenceLabel("11:42", size: 12).attributedText)
    }

    func testTooltipBelongsToFileAnchorAndPreservesLinkAndInlineCode() throws {
        let source = "Read `/tmp/review.md:12` or [docs](https://example.com/docs)."
        let value = NativeMarkdown.attributed(NativeLinks.markdown(source))
        for title in ["预览文件", "Preview file"] {
            let rendered = NativeTextStyle.render(value, size: 14, fileLinkTooltip: title)
            let fileRange = (rendered.string as NSString).range(of: "/tmp/review.md:12")
            XCTAssertNotEqual(fileRange.location, NSNotFound)
            XCTAssertEqual(rendered.attribute(.toolTip, at: fileRange.location, effectiveRange: nil) as? String, title)
            let link = try XCTUnwrap(rendered.attribute(.link, at: fileRange.location, effectiveRange: nil) as? URL)
            XCTAssertEqual(link.scheme, "relic-file")
            XCTAssertEqual(URLComponents(url: link, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "line" })?.value, "12")
            XCTAssertEqual(NativeInlineCode.source(rendered), "Read /tmp/review.md:12 or docs.")
            XCTAssertNil(rendered.attribute(.toolTip, at: 0, effectiveRange: nil))
            XCTAssertNil(rendered.attribute(.toolTip, at: (rendered.string as NSString).range(of: "docs").location, effectiveRange: nil))
        }
    }

    func testPlainParagraphHasNoTooltipOrLayoutChange() {
        let value = NativeMarkdown.attributed("Ordinary **paragraph** without file anchors.")
        let baseline = NativeTextStyle.render(value, size: 14)
        let rendered = NativeTextStyle.render(value, size: 14, fileLinkTooltip: "Preview file")
        XCTAssertEqual(rendered, baseline)
        XCTAssertEqual(NativeTextStyle.contentSize(rendered, available: 200), NativeTextStyle.contentSize(baseline, available: 200))
    }

    func testExplicitFileAndAbsolutePathLinksUseNativeRangeHelp() {
        for destination in ["file:///tmp/report.md", "/tmp/report.md"] {
            var value = AttributedString("report")
            value.link = URL(string: destination)
            let rendered = NativeTextStyle.render(value, size: 14, fileLinkTooltip: "Preview file")
            XCTAssertEqual(rendered.attribute(.toolTip, at: 0, effectiveRange: nil) as? String, "Preview file")
            XCTAssertEqual(rendered.string, "report")
        }
    }
}
