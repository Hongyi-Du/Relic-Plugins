import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class ComposerDrawingTests: XCTestCase {
    private struct Editor: View {
        let enabled: Bool
        var body: some View {
            MentionEditor(text: .constant(""), placeholder: "Write a message", members: [], onMention: { _ in }, send: {})
                .frame(height: 26.4).disabled(!enabled)
        }
    }
    func testEmptyComposerPaintsItsPlaceholderAcrossResizingAndEnableChanges() async throws {
        _ = NSApplication.shared
        let model = Model()
        let host = NSHostingView(rootView: Editor(enabled: true).environmentObject(model))
        host.sizingOptions = []; host.autoresizingMask = [.width, .height]
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 800, height: 70), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = host; window.orderFront(nil)
        defer { model.stop(); window.orderOut(nil); window.contentView = nil; window.close() }
        func find(_ root: NSView) -> ComposerTextView? {
            if let editor = root as? ComposerTextView { return editor }
            for child in root.subviews { if let editor = find(child) { return editor } }
            return nil
        }
        for (width, enabled) in [(CGFloat(800), true), (300, false), (700, true), (300, true)] {
            host.rootView = Editor(enabled: enabled).environmentObject(model)
            window.setContentSize(NSSize(width: width, height: 70))
            try await Task.sleep(for: .milliseconds(100)); host.layoutSubtreeIfNeeded()
            let editor = try XCTUnwrap(find(host)), clip = try XCTUnwrap(editor.enclosingScrollView?.contentView)
            let placeholder = try XCTUnwrap(editor.placeholderView)
            XCTAssertEqual(editor.isEditable, enabled)
            XCTAssertGreaterThanOrEqual(editor.bounds.height, clip.bounds.height)
            XCTAssertGreaterThanOrEqual(placeholder.convert(placeholder.bounds, to: clip).intersection(clip.bounds).height, 20)
            XCTAssertEqual(placeholder.string, "Write a message"); XCTAssertFalse(placeholder.isHidden)
            let manager = try XCTUnwrap(placeholder.layoutManager as? NativeGlyphLayoutManager); manager.recordDraws = true
            let bitmap = try XCTUnwrap(CaptureRaster.forView(host)); host.cacheDisplay(in: host.bounds, to: bitmap)
            XCTAssertEqual(manager.fontEvidence(for: NSRange(location: 0, length: 15), in: placeholder)["status"] as? String, "measured-current-draw")
        }
    }

    func testUnrepresentableNativeMeasurementRetainsItsFailureAndPath() throws {
        var errors: [[String: String]] = []
        let actual = CaptureMeasurements.jsonValue(["nested": ["bounds": ["x": Double.infinity, "y": Double.nan, "width": 20.0]]], errors: &errors)
        XCTAssertEqual(Set(errors.compactMap { $0["path"] }), ["$.nested.bounds.x", "$.nested.bounds.y"])
        XCTAssertTrue(errors.allSatisfy { !$0["native_value", default: ""].isEmpty })
        XCTAssertNoThrow(try JSONSerialization.data(withJSONObject: actual))
    }
    func testPlaceholderUsesActualMountedGlyphSourceAndNeverChangesInputText() throws {
        _ = NSApplication.shared
        let editor = ComposerTextView.makeObserved(frame: NSRect(x: 0, y: 0, width: 300, height: 40))
        editor.setAccessibilityIdentifier("relic-composer/test")
        editor.placeholder = "Write a message"; editor.textContainerInset = NSSize(width: 0, height: 2)
        editor.updatePlaceholder()
        let label = try XCTUnwrap(editor.placeholderView)
        let manager = try XCTUnwrap(label.layoutManager as? NativeGlyphLayoutManager); manager.recordDraws = true
        let window = NSWindow(contentRect: editor.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = editor; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        editor.layoutSubtreeIfNeeded()
        let bitmap = try XCTUnwrap(CaptureRaster.forView(label)); label.cacheDisplay(in: label.bounds, to: bitmap)
        XCTAssertEqual(editor.string, ""); XCTAssertEqual(label.string, "Write a message")
        XCTAssertEqual(label.productionOwner, "relic-composer/test"); XCTAssertNil(label.hitTest(.zero))
        XCTAssertEqual(manager.fontEvidence(for: NSRange(location: 0, length: 15), in: label)["status"] as? String, "measured-current-draw")
        XCTAssertEqual(label.frame.origin, NSPoint(x: 0, y: 2))
        editor.string = "Actual draft"; editor.updatePlaceholder()
        XCTAssertTrue(label.isHidden); XCTAssertEqual(editor.string, "Actual draft")
        editor.string = ""; editor.updatePlaceholder()
        XCTAssertFalse(label.isHidden); XCTAssertTrue(editor.placeholderView === label)
    }

    func testEditableDrawIsBoundToItsInputWithoutReplacingNativeHitGeometry() throws {
        _ = NSApplication.shared
        let editor = ComposerTextView.makeObserved(frame: NSRect(x: 0, y: 0, width: 300, height: 40))
        editor.isEditable = true; editor.textContainerInset = .zero; editor.textContainer?.lineFragmentPadding = 0
        let paragraph = NSMutableParagraphStyle(); paragraph.minimumLineHeight = 22.4; paragraph.maximumLineHeight = 22.4
        editor.textStorage?.setAttributedString(NSAttributedString(string: "Actual draft", attributes: [.font: NSFont.systemFont(ofSize: 14), .paragraphStyle: paragraph, .foregroundColor: NSColor.black, .relicConfiguredFontWeight: 400]))
        let manager = try XCTUnwrap(editor.layoutManager as? NativeGlyphLayoutManager); manager.recordDraws = true
        let window = NSWindow(contentRect: editor.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false; window.contentView = editor; window.orderFront(nil)
        defer { window.orderOut(nil); window.contentView = nil; window.close() }
        let bitmap = try XCTUnwrap(CaptureRaster.forView(editor)); editor.cacheDisplay(in: editor.bounds, to: bitmap)
        let canvas = window.convertToScreen(editor.convert(editor.bounds, to: nil))
        let box = ElementCapture.box(editor.bounds)
        var node: [String: Any] = ["rect": box, "style": ["borderWidth": 1]]
        EditableTextCapture.attach(to: &node, view: editor, canvas: canvas)
        XCTAssertEqual(ElementCapture.rect(node["rect"]), editor.bounds)
        XCTAssertEqual((node["style"] as? [String: Any])?["borderWidth"] as? Int, 1)
        XCTAssertEqual((node["layout"] as? [String: Any])?["line_count"] as? Int, 1)
        let projection = try XCTUnwrap(node["projection"] as? [String: Any])
        XCTAssertEqual((projection["native_font_drawing"] as? [String: Any])?["status"] as? String, "measured-current-draw")
        let lines = try XCTUnwrap(node["text_bounds"] as? [[String: Double]])
        XCTAssertEqual(lines.count, 1, "Each actual native line retains its own rectangle")
        XCTAssertTrue(lines.flatMap { $0.values }.allSatisfy(\.isFinite))
        XCTAssertNil(node["native_measurement_errors"], "The mounted test input must have finite measured line geometry")
        XCTAssertNoThrow(try JSONSerialization.data(withJSONObject: node))
        if let failures = node["native_measurement_errors"] { print("Actual editable native measurement failures: \(failures)") }
    }
}
