import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class OutlineDrawTests: XCTestCase {
    func testTextOutlineContractRequiresItsActualCurrentNativeDrawAndRejectsAdditionalPaint() throws {
        _ = NSApplication.shared
        let view = ReferenceLabel("Measured passage", size: 13).makeLabelView()
        view.frame = NSRect(x: 0, y: 0, width: 160, height: 30)
        let manager = try XCTUnwrap(view.layoutManager as? NativeGlyphLayoutManager)
        manager.recordDraws = true
        let range = NSRange(location: 0, length: (view.string as NSString).length)
        func inspect() -> (paint: Any, evidence: [String: Any]) {
            TextOutlineCapture.inspect(view, range: range, fontDraw: manager.fontEvidence(for: range, in: view))
        }
        XCTAssertTrue(inspect().paint is NSNull, "An unmounted, undrawn label supplies no absence proof")
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        view.display(); CATransaction.flush()
        let bitmap = try XCTUnwrap(CaptureRaster.forView(view)); view.cacheDisplay(in: view.bounds, to: bitmap)
        let current = inspect()
        // AppKit can omit a presentation layer in the unit-test host. In that
        // case absence stays unknown; mounted application captures supply it.
        if view.layer == nil || view.layer?.presentation() != nil {
            XCTAssertEqual(current.paint as? String, "none", String(describing: current.evidence))
            XCTAssertEqual(current.evidence["absence_proven"] as? Bool, true)
        } else { XCTAssertTrue(current.paint is NSNull) }
        view.focusRingType = .exterior
        XCTAssertTrue(inspect().paint is NSNull)
        view.focusRingType = .none; view.isEditable = true
        XCTAssertTrue(inspect().paint is NSNull)
        view.isEditable = false
        let extra = NSView(frame: NSRect(x: 0, y: 0, width: 2, height: 2)); view.addSubview(extra)
        XCTAssertTrue(inspect().paint is NSNull)
        extra.removeFromSuperview()
        view.wantsLayer = true; view.layer?.borderWidth = 2
        XCTAssertTrue(inspect().paint is NSNull)
        XCTAssertEqual(inspect().evidence["absence_proven"] as? Bool, false)
    }

    func testLabelOwnOutlineAbsenceCannotProvideItsButtonOutline() {
        var nodes: [[String: Any]] = [
            ["id": "button", "identifier": "relic-text-button/test", "style": ["outline": NSNull()]],
            ["id": "label", "production_owner": "relic-text-button/test", "text": "Save", "style": ["outline": "none"],
             "projection": ["native_text_outline": ["absence_proven": true, "scope": "text span only"]]]
        ]
        XCTAssertTrue(ElementOwnership.attachLabels(to: &nodes).isEmpty)
        XCTAssertEqual(nodes.count, 1)
        XCTAssertTrue((nodes.first?["style"] as? [String: Any])?["outline"] is NSNull)
        XCTAssertNil(nodes.first?["projection"], "Retained label evidence remains separate from the button's own paint")
        XCTAssertNotNil(nodes.first?["owned_text_evidence"])
    }

    func testRecordedDashPhaseIsUsedByTheActualNativeRaster() throws {
        let view = SurfacePaintProbe.SurfaceView(frame: NSRect(x: 0, y: 0, width: 22, height: 22))
        view.recordDraws = true
        var rasters: [Data] = []
        for phase in [CGFloat(0), CGFloat(3)] {
            view.configureOutline(SurfaceOutline(width: 1.5, color: .black, dash: [3, 3], phase: phase), corners: [6, 6, 6, 6])
            let bitmap = try XCTUnwrap(CaptureRaster.forView(view))
            view.cacheDisplay(in: view.bounds, to: bitmap)
            let receipt = try XCTUnwrap(view.lastOutlineDraw)
            XCTAssertEqual(receipt.phase, phase)
            XCTAssertEqual(receipt.revision, view.outlineRevision)
            XCTAssertEqual(receipt.path.boundingBoxOfPath.minX, 0.75, accuracy: 0.001)
            XCTAssertEqual(receipt.path.boundingBoxOfPath.maxX, 21.25, accuracy: 0.001)
            XCTAssertEqual(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 11, y: 11))[3], 0,
                "An independent outline must not fill the avatar interior")
            XCTAssertEqual(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 0, y: 0))[3], 0,
                "The actual rounded path must preserve its clear corner")
            rasters.append(try XCTUnwrap(bitmap.representation(using: .png, properties: [:])))
            XCTAssertTrue(view.outlineReceipt(in: view.bounds).paint is NSNull,
                "A unit bitmap is not proof of a mounted window's current outline")
            XCTAssertNoThrow(try JSONSerialization.data(withJSONObject: receipt.raw))
        }
        XCTAssertNotEqual(rasters[0], rasters[1], "The receipt's changed phase must change the real native paint")
    }

    func testClearingOutlineDoesNotReuseTheEarlierDrawOrClaimOwnerAbsence() throws {
        let view = SurfacePaintProbe.SurfaceView(frame: NSRect(x: 0, y: 0, width: 22, height: 22))
        view.recordDraws = true
        view.configureOutline(SurfaceOutline(width: 1.5, color: .black, dash: [3, 3]), corners: [6, 6, 6, 6])
        let bitmap = try XCTUnwrap(CaptureRaster.forView(view))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let previous = try XCTUnwrap(view.lastOutlineDraw)
        view.configureOutline(nil, corners: [6, 6, 6, 6])
        XCTAssertGreaterThan(view.outlineRevision, previous.revision)
        let receipt = view.outlineReceipt(in: view.bounds)
        XCTAssertTrue(receipt.paint is NSNull)
        XCTAssertEqual(receipt.evidence["absence_proven"] as? Bool, false)
        XCTAssertEqual(view.lastOutlineDraw?.sequence, previous.sequence, "Retain earlier raw evidence without projecting it as current paint")
    }
}
