import XCTest
@testable import RelicCore

final class WindowPlacementTests: XCTestCase {
    func testDefaultIsCappedAndCenteredInVisiblePoints() {
        let visible = CGRect(x: 100, y: 36, width: 2560, height: 1392)
        XCTAssertEqual(WindowPlacement.defaultFrame(in: visible), CGRect(x: 660, y: 282, width: 1440, height: 900))
        XCTAssertEqual(WindowPlacement.minimumSize(in: visible), CGSize(width: 960, height: 640))
    }

    func testPhysicalWorkAreasAtAllRequestedScalesUseTheSameLogicalPolicy() {
        let cases: [(CGFloat, CGSize, CGSize)] = [
            (1, CGSize(width: 1440, height: 900), CGSize(width: 960, height: 640)),
            (1.25, CGSize(width: 1800, height: 1125), CGSize(width: 1200, height: 800)),
            (1.5, CGSize(width: 2160, height: 1350), CGSize(width: 1440, height: 960)),
            (2, CGSize(width: 2880, height: 1774.8), CGSize(width: 1920, height: 1280))
        ]
        for (scale, pixels, minimumPixels) in cases {
            let visible = CGRect(x: 0, y: 0, width: 3840 / scale, height: 2088 / scale)
            let frame = WindowPlacement.defaultFrame(in: visible)
            XCTAssertEqual(frame.width * scale, pixels.width, accuracy: 0.001)
            XCTAssertEqual(frame.height * scale, pixels.height, accuracy: 0.001)
            let minimum = WindowPlacement.minimumSize(in: visible)
            XCTAssertEqual(minimum.width * scale, minimumPixels.width, accuracy: 0.001)
            XCTAssertEqual(minimum.height * scale, minimumPixels.height, accuracy: 0.001)
            XCTAssertEqual(frame.midX, visible.midX)
            XCTAssertEqual(frame.midY, visible.midY)
        }
    }

    func testSmallVisibleFrameLeavesSpaceForDesktopWithoutAnImpossibleMinimum() {
        let screen = CGRect(x: -900, y: 24, width: 900, height: 600)
        let frame = WindowPlacement.defaultFrame(in: screen)
        XCTAssertEqual(frame.size, CGSize(width: 765, height: 510))
        XCTAssertEqual(frame.midX, -450)
        XCTAssertEqual(frame.midY, 324)
        XCTAssertEqual(WindowPlacement.minimumSize(in: screen), frame.size)
        XCTAssertTrue(screen.contains(frame))
    }

    func testSavedFrameOnSecondaryMonitorIsRestoredInsteadOfRecentred() {
        let main = CGRect(x: 0, y: 30, width: 2560, height: 1392)
        let secondary = CGRect(x: -1920, y: 50, width: 1920, height: 1030)
        let saved = CGRect(x: -1800, y: 100, width: 1200, height: 800)
        XCTAssertEqual(WindowPlacement.restoredFrame(saved, screens: [main, secondary], preferred: main), saved)
    }

    func testOffscreenAndInvalidSavedFramesUseCurrentScreenDefault() {
        let visible = CGRect(x: 0, y: 24, width: 1440, height: 850)
        let cases: [CGRect?] = [nil, CGRect(x: 3000, y: 100, width: 1200, height: 800),
                               CGRect(x: CGFloat.nan, y: 0, width: 1000, height: 700), .zero]
        for saved in cases {
            XCTAssertEqual(WindowPlacement.restoredFrame(saved, screens: [visible], preferred: visible), WindowPlacement.defaultFrame(in: visible))
        }
    }

    func testOversizedOrPartlyOffscreenSavedFrameIsClampedToVisibleScreen() {
        let visible = CGRect(x: 0, y: 24, width: 1440, height: 850)
        XCTAssertEqual(WindowPlacement.restoredFrame(CGRect(x: 1300, y: -50, width: 1200, height: 700), screens: [visible], preferred: visible),
                       CGRect(x: 240, y: 24, width: 1200, height: 700))
        XCTAssertEqual(WindowPlacement.clamped(CGRect(x: -100, y: 100, width: 2500, height: 1500), to: visible), visible)
    }

    func testTooSmallSavedFrameGetsTheMinimumAndOrdinaryResizeIsNotCappedAtDefault() {
        let visible = CGRect(x: 0, y: 30, width: 2560, height: 1392)
        XCTAssertEqual(WindowPlacement.clamped(CGRect(x: 100, y: 100, width: 300, height: 200), to: visible),
                       CGRect(x: 100, y: 100, width: 960, height: 640))
        let expanded = CGRect(x: 100, y: 100, width: 1800, height: 1100)
        XCTAssertEqual(WindowPlacement.restoredFrame(expanded, screens: [visible], preferred: visible), expanded)
    }
}
