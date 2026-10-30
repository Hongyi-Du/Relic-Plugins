import XCTest
import AppKit
import RelicAX
@testable import Relic

@MainActor final class ReferenceSelectTests: XCTestCase {
    func testActualSelectedTitleDrawRetainsItsColorAndPopupSelection() throws {
        let popup = ReferencePopUpButton(frame: NSRect(x: 0, y: 0, width: 220, height: 23), pullsDown: false)
        popup.cell = ReferencePopUpCell(textCell: "", pullsDown: false)
        popup.isBordered = false
        popup.addItems(withTitles: ["Relic workspace", "Secretariat"])
        popup.selectItem(at: 1)
        popup.configureAccessibility(title: "Parent")
        let color = NSColor(srgbRed: 27/255, green: 27/255, blue: 26/255, alpha: 1)
        popup.configureTitle(pointSize: 14, color: color)
        (popup.titleLabel.layoutManager as? NativeGlyphLayoutManager)?.recordDraws = true
        popup.layoutSubtreeIfNeeded()
        let bitmap = try XCTUnwrap(CaptureRaster.forView(popup))
        popup.cacheDisplay(in: popup.bounds, to: bitmap)
        let row = try XCTUnwrap(ElementCapture.textRuns(popup.titleLabel).first)
        let style = try XCTUnwrap(row["style"] as? [String: Any])
        let fonts = try XCTUnwrap(style["rendered_fonts"] as? [[String: Any]])
        XCTAssertFalse(fonts.isEmpty, "The title must actually reach the glyph drawing callback")
        XCTAssertEqual(row["text"] as? String, "Secretariat")
        XCTAssertEqual(popup.titleLabel.productionOwner, "relic-dropdown/Parent")
        XCTAssertEqual(popup.indexOfSelectedItem, 1)
        XCTAssertEqual(popup.itemTitles, ["Relic workspace", "Secretariat"])
        let actual = try XCTUnwrap(style["color"] as? [Double])
        for (value, expected) in zip(actual, [27.0, 27, 26, 255]) { XCTAssertEqual(value, expected, accuracy: 0.01) }
        XCTAssertEqual(RelicAXRead(try XCTUnwrap(popup.cell))["identifier"] as? String, "relic-dropdown/Parent")
        popup.selectItem(at: 0)
        popup.configureTitle(pointSize: 14, color: color)
        XCTAssertEqual(popup.titleLabel.string, "Relic workspace")
        XCTAssertEqual(popup.indexOfSelectedItem, 0)
        XCTAssertEqual(popup.itemTitles.count, 2)
    }
}
