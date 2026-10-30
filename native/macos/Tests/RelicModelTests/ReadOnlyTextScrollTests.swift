import XCTest
import AppKit
@testable import Relic

@MainActor final class ReadOnlyTextScrollTests: XCTestCase {
    private final class Document: NSView { override var isFlipped: Bool { true } }

    func testReflowDoesNotRevealDormantInsertionPointButExplicitScrollingWorks() throws {
        for selectable in [false, true] {
            let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 340, height: 200))
            let document = Document(frame: NSRect(x: 0, y: 0, width: 340, height: 1200))
            scroll.documentView = document
            let storage = NSTextStorage(string: String(repeating: "Read-only passage with several words. ", count: 8),
                attributes: [.font: NSFont.systemFont(ofSize: 13)])
            let layout = NSLayoutManager(), container = NSTextContainer(size: NSSize(width: 300, height: 1000))
            storage.addLayoutManager(layout); layout.addTextContainer(container)
            let view: ReadOnlyTextView = selectable
                ? QuoteTextView(frame: NSRect(x: 16, y: 700, width: 300, height: 300), textContainer: container)
                : ReferenceLabelView(frame: NSRect(x: 16, y: 700, width: 300, height: 300), textContainer: container)
            view.isEditable = false; view.isSelectable = selectable
            view.isVerticallyResizable = false; view.isHorizontallyResizable = false
            container.widthTracksTextView = true
            view.setSelectedRange(NSRange(location: 12, length: selectable ? 8 : 0))
            document.addSubview(view)
            let selection = view.selectedRange()
            for offset in [CGFloat(0), 120, 450] {
                scroll.contentView.scroll(to: NSPoint(x: 0, y: offset))
                let before = scroll.contentView.bounds.origin
                for width in [CGFloat(290), 180, 300] {
                    view.setFrameSize(NSSize(width: width, height: 300))
                    layout.ensureLayout(for: container)
                    XCTAssertEqual(scroll.contentView.bounds.origin, before,
                        "A width change must preserve the containing page's reading position")
                    XCTAssertEqual(view.selectedRange(), selection)
                }
            }
            scroll.contentView.scroll(to: .zero)
            XCTAssertTrue(view.scrollToVisible(NSRect(x: 0, y: 10, width: 40, height: 20)),
                "An explicit scroll request remains available to selection and accessibility")
            XCTAssertGreaterThan(scroll.contentView.bounds.minY, 0)
            XCTAssertEqual(view.selectedRange(), selection)
        }
    }
}
