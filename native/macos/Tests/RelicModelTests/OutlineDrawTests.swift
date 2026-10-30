import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class OutlineDrawTests: XCTestCase {
    func testOwnedLayerCandidateUsesItsSingleNativeTextKitDrawingPath() throws {
        _ = NSApplication.shared
        let view = ReferenceLabel("Relic → 组织", size: 14, lines: 0).makeLabelView()
        view.usesOwnedBackingImage = true
        view.frame = NSRect(x: 0, y: 0, width: 220, height: 40)
        view.wantsLayer = true
        let manager = try XCTUnwrap(view.layoutManager as? NativeGlyphLayoutManager)
        manager.recordDraws = true
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.contentView = view; window.orderFront(nil); defer { window.orderOut(nil) }
        view.layoutSubtreeIfNeeded(); view.display(); CATransaction.flush()
        let bitmap = try XCTUnwrap(CaptureRaster.forView(view))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let range = NSRange(location: 0, length: (view.string as NSString).length)
        XCTAssertEqual(manager.fontEvidence(for: range, in: view)["status"] as? String, "measured-current-draw")
        XCTAssertTrue(view.subviews.isEmpty)
        let children = view.layer?.sublayers ?? []
        XCTAssertTrue(children.isEmpty, "A label must not retain another AppKit content paint layer: \(children.map { String(describing: type(of: $0)) })")
        XCTAssertEqual(view.backingPaintObservation()["current"] as? Bool, true)
        var painted = false
        for y in 0..<bitmap.pixelsHigh {
            for x in 0..<bitmap.pixelsWide where (CaptureRaster.sRGBPixel(bitmap, x: x, y: y)?[3] ?? 0) > 0 {
                painted = true; break
            }
            if painted { break }
        }
        XCTAssertTrue(painted, "Removing an extra draw path must retain the actual glyph pixels")
    }

    func testOwnedLayerCandidateSurvivesTheActualSwiftUIHostingAndCapturePath() throws {
        _ = NSApplication.shared
        var images: [Data] = []
        for owned in [false, true] {
            let root = ReferenceLabel("Relic → 组织", size: 14, ownedLayer: owned)
                .frame(width: 180, height: 32)
            let host = NSHostingView(rootView: root)
            host.frame = NSRect(x: 0, y: 0, width: 180, height: 32)
            let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.contentView = host; window.orderFront(nil)
            host.layoutSubtreeIfNeeded(); host.displayIfNeeded(); CATransaction.flush()
            let bitmap = try XCTUnwrap(CaptureRaster.forView(host))
            host.cacheDisplay(in: host.bounds, to: bitmap)
            images.append(try XCTUnwrap(bitmap.representation(using: .png, properties: [:])))
            var painted = 0
            for y in 0..<bitmap.pixelsHigh { for x in 0..<bitmap.pixelsWide {
                if (CaptureRaster.sRGBPixel(bitmap, x: x, y: y)?[3] ?? 0) > 0 { painted += 1 }
            } }
            XCTAssertGreaterThan(painted, 0, "The actual hosting capture must include the label, owned=\(owned)")
            window.orderOut(nil)
        }
        if images[0] != images[1] {
            let package = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            let directory = package.appendingPathComponent(".build/draw-diagnostics", isDirectory: true)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try images[0].write(to: directory.appendingPathComponent("label-host-draw.png"))
            try images[1].write(to: directory.appendingPathComponent("label-host-layer.png"))
        }
        XCTAssertEqual(images[0], images[1], "The candidate must preserve every hosted label pixel")
    }

    func testSubmittedLabelLayerImagePreservesAppKitsActualBitmap() throws {
        _ = NSApplication.shared
        let view = ReferenceLabel("Relic 🙂 组织", size: 14).makeLabelView()
        view.usesOwnedBackingImage = true
        view.frame = NSRect(x: 0, y: 0, width: 180, height: 32)
        view.wantsLayer = true
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.contentView = view; window.orderFront(nil); defer { window.orderOut(nil) }
        view.layoutSubtreeIfNeeded(); view.display(); CATransaction.flush()
        let contents = try XCTUnwrap(view.layer?.contents)
        guard CFGetTypeID(contents as CFTypeRef) == CGImage.typeID else {
            XCTFail("The submitted backing store is not the owned CGImage"); return
        }
        let image = contents as! CGImage
        let actual = NSBitmapImageRep(cgImage: image)
        XCTAssertEqual(view.backingPaintObservation()["current"] as? Bool, true)
        view.textStorage?.replaceCharacters(in: NSRange(location: 0, length: 5), with: "Other")
        XCTAssertEqual(view.backingPaintObservation()["current"] as? Bool, false, "A source change cannot retain the earlier layer-image proof")

        let baseline = ReferenceLabel("Relic 🙂 组织", size: 14).makeLabelView()
        baseline.frame = view.frame
        (baseline.layoutManager as? NativeGlyphLayoutManager)?.drawsGlyphsIntoCurrentContext = false
        window.contentView = baseline
        baseline.wantsLayer = false
        baseline.layoutSubtreeIfNeeded()
        let expected = try XCTUnwrap(CaptureRaster.forView(baseline))
        baseline.cacheDisplay(in: baseline.bounds, to: expected)
        XCTAssertEqual(actual.pixelsWide, expected.pixelsWide)
        XCTAssertEqual(actual.pixelsHigh, expected.pixelsHigh)
        guard actual.pixelsWide == expected.pixelsWide && actual.pixelsHigh == expected.pixelsHigh else { return }
        var different = 0
        for y in 0..<actual.pixelsHigh { for x in 0..<actual.pixelsWide {
            if CaptureRaster.sRGBPixel(actual, x: x, y: y) != CaptureRaster.sRGBPixel(expected, x: x, y: y) { different += 1 }
        } }
        if different != 0 {
            let package = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            let directory = package.appendingPathComponent(".build/draw-diagnostics", isDirectory: true)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try actual.representation(using: .png, properties: [:])?.write(to: directory.appendingPathComponent("label-layer-actual.png"))
            try expected.representation(using: .png, properties: [:])?.write(to: directory.appendingPathComponent("label-layer-appkit.png"))
        }
        XCTAssertEqual(different, 0, "The submitted production layer image must retain every native glyph pixel")
    }

    func testTextOutlineContractRequiresItsActualCurrentNativeDrawAndRejectsAdditionalPaint() throws {
        _ = NSApplication.shared
        let view = ReferenceLabel("Measured passage", size: 13).makeLabelView()
        view.frame = NSRect(x: 0, y: 0, width: 160, height: 30)
        let manager = try XCTUnwrap(view.layoutManager as? NativeGlyphLayoutManager)
        manager.recordDraws = true
        let range = NSRange(location: 0, length: (view.string as NSString).length)
        func inspect() -> (paint: Any, evidence: [String: Any]) {
            TextOutlineCapture.inspect(view, range: range)
        }
        XCTAssertTrue(inspect().paint is NSNull, "An unmounted, undrawn label supplies no absence proof")
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = view; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        view.display(); CATransaction.flush()
        let bitmap = try XCTUnwrap(CaptureRaster.forView(view)); view.cacheDisplay(in: view.bounds, to: bitmap)
        let current = inspect()
        XCTAssertEqual(current.evidence["glyph_draw_status"] as? String, "measured-current-draw")
        // The test host can install AppKit text sublayers even on a view with
        // no NSView children (observed in 41044882354). Their paint is outside
        // this bounded contract. A visible presentation layer alone therefore
        // cannot justify the former assumption that absence must be proven.
        let nativeChildren = view.layer?.sublayers?.count ?? 0
        let presentedChildren = view.layer?.presentation()?.sublayers?.count ?? 0
        if nativeChildren > 0 || presentedChildren > 0 {
            XCTAssertTrue(current.paint is NSNull)
            XCTAssertEqual(current.evidence["absence_proven"] as? Bool, false)
            let errors = try XCTUnwrap(current.evidence["errors"] as? [String])
            XCTAssertTrue(errors.contains { $0.contains("layer paint/effects") })
            let layer = try XCTUnwrap(current.evidence["layer"] as? [String: Any])
            let children = try XCTUnwrap(layer["child_layers"] as? [[String: Any]])
            XCTAssertEqual(children.count, nativeChildren)
            for child in children {
                XCTAssertFalse((child["class"] as? String ?? "").isEmpty)
                XCTAssertEqual(child["drawing_duty_proven"] as? Bool, false)
            }
        } else if view.layer == nil || view.layer?.presentation() != nil {
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

    func testOutwardFocusOutlineRetainsItsActualOwnerBoundsAndPaintsTheOutsideMargin() throws {
        _ = NSApplication.shared
        let view = SurfacePaintProbe.SurfaceView(frame: NSRect(x: 0, y: 0, width: 201, height: 39))
        view.recordDraws = true
        view.configureOutline(SurfaceOutline(width: 2, color: .black.opacity(0.6), dash: [], offset: 1), corners: [8, 8, 8, 8])
        let window = NSWindow(contentRect: view.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.contentView = view; window.orderFront(nil); defer { window.orderOut(nil) }
        let bitmap = try XCTUnwrap(CaptureRaster.forView(view))
        view.cacheDisplay(in: view.bounds, to: bitmap)
        let draw = try XCTUnwrap(view.lastOutlineDraw)
        XCTAssertEqual(view.surfaceBounds, NSRect(x: 3, y: 3, width: 195, height: 33))
        XCTAssertEqual(draw.ownerBounds, view.surfaceBounds)
        XCTAssertEqual(draw.path.boundingBoxOfPath, NSRect(x: 1, y: 1, width: 199, height: 37))
        XCTAssertEqual(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 100, y: 0))[3], 153, accuracy: 1)
        XCTAssertEqual(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 100, y: 3))[3], 0)
        XCTAssertEqual(try XCTUnwrap(CaptureRaster.sRGBPixel(bitmap, x: 0, y: 0))[3], 0)
        let content = window.convertToScreen(view.convert(view.bounds, to: nil))
        let result = view.outlineReceipt(in: content)
        let paint = try XCTUnwrap(result.paint as? [String: Any])
        XCTAssertEqual(paint["offset"] as? Double, 1)
        XCTAssertEqual(paint["width"] as? Double, 2)
        XCTAssertEqual(ElementCapture.rect(result.evidence["owner_bounds"]), view.surfaceBounds)
        XCTAssertNoThrow(try JSONSerialization.data(withJSONObject: draw.raw))
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
