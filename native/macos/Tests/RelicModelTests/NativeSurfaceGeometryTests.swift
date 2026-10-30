import XCTest
import AppKit
import SwiftUI
import RelicAX
import ApplicationServices
@testable import Relic

@MainActor final class NativeSurfaceGeometryTests: XCTestCase {
    func testPaddedTextButtonExposesItsWholeInteractiveBox() async throws {
        _ = NSApplication.shared
        let owner = "relic-tab/padded-button-test"
        let sample = TextButton("Tab", size: 12, weight: 400, height: 24, padding: 9, fillsWidth: true, identifier: owner) {}.buttonStyle(.plain)
        let host = NSHostingView(rootView: sample)
        let window = NSWindow(contentRect: NSRect(x: 80, y: 80, width: 100, height: 24), styleMask: [.borderless], backing: .buffered, defer: false)
        window.contentView = host; window.orderFront(nil); defer { window.orderOut(nil) }
        // Use the same public self-process AX activation as the CI app capture.
        // SwiftUI otherwise may leave its accessibility tree unmaterialized.
        let axResult = await Task.detached {
            let app = AXUIElementCreateApplication(getpid())
            AXUIElementSetMessagingTimeout(app, 2)
            var windows: CFTypeRef?
            return AXUIElementCopyAttributeValue(app, kAXWindowsAttribute as CFString, &windows).rawValue
        }.value
        host.layoutSubtreeIfNeeded(); window.displayIfNeeded()
        // SwiftUI publishes hosted accessibility nodes on its next transaction.
        try await Task.sleep(for: .milliseconds(50))
        host.layoutSubtreeIfNeeded(); window.displayIfNeeded()
        var seen = Set<ObjectIdentifier>(), observed: [String] = []
        func find(_ value: AnyObject) -> NSRect? {
            guard seen.insert(ObjectIdentifier(value)).inserted else { return nil }
            let ax = RelicAXRead(value)
            observed.append(String(describing: type(of: value)) + ":" + (ax["identifier"] as? String ?? ""))
            if ax["identifier"] as? String == owner { return (ax["frame"] as? NSValue)?.rectValue }
            for child in RelicAXChildren(value) { if let frame = find(child as AnyObject) { return frame } }
            if let view = value as? NSView { for child in view.subviews { if let frame = find(child) { return frame } } }
            return nil
        }
        let measured = find(host)
        let actual = try XCTUnwrap(measured, "AX initialization=\(axResult); " + observed.joined(separator: ", "))
        XCTAssertEqual(actual.size, NSSize(width: 100, height: 24), "The button's padding participates in native interaction and accessibility")
    }

    func testMountedWindowBackgroundHasItsOwnNativeOwnerIdentity() throws {
        let host = NSHostingView(rootView: Color.white.background(InitialWindowFocus()))
        let window = NSWindow(contentRect: NSRect(x: 80, y: 80, width: 240, height: 140), styleMask: [.borderless], backing: .buffered, defer: false)
        window.contentView = host; window.orderFront(nil); defer { window.orderOut(nil) }
        host.layoutSubtreeIfNeeded()
        XCTAssertTrue(window.contentView === host)
        XCTAssertEqual(RelicAXRead(host)["identifier"] as? String, InitialWindowFocus.surfaceIdentity,
            "The actual hosting root, not an equal-sized modal backdrop, owns the window background")
    }

    func testSelectedSwatchKeepsItsPaintedButtonBoxSeparateFromSelectionRings() throws {
        let host = NSHostingView(rootView: SettingsSwatch(name: "clay", selected: true, action: {}).padding(8))
        let window = NSWindow(contentRect: NSRect(x: 80, y: 80, width: 40, height: 40), styleMask: [.borderless], backing: .buffered, defer: false)
        window.contentView = host; window.orderFront(nil); defer { window.orderOut(nil) }
        host.layoutSubtreeIfNeeded(); window.displayIfNeeded()
        let content = window.convertToScreen(host.convert(host.bounds, to: nil))
        let surface = try XCTUnwrap(SurfacePaintProbe.snapshots(in: content).first { ($0["owner"] as? String)?.hasPrefix("relic-icon-button/swatch/") == true })
        let measured = try XCTUnwrap(surface["rectValue"] as? NSValue).rectValue
        XCTAssertEqual(measured.size, NSSize(width: 24, height: 24))
        let style = try XCTUnwrap(surface["style"] as? [String: Any])
        XCTAssertEqual(style["borderWidth"] as? Double, 2)
        let rings = try XCTUnwrap(style["shadow"] as? [[String: Any]])
        XCTAssertEqual(rings.compactMap { $0["spread_radius"] as? Double }, [2, 4])
        var button: [String: Any] = ["kind": "icon-button", "identifier": surface["owner"]!, "rect": ElementCapture.box(measured.insetBy(dx: -4, dy: -4))]
        NativeSurfaceGeometry.attach(to: &button, surface: surface, viewport: host.bounds)
        XCTAssertEqual(ElementCapture.rect(button["rect"]), measured)
        XCTAssertEqual(ElementCapture.rect(button["ax_content_rect"]).width, 32)
    }

    func testSwiftUIHostedCheckboxKeepsItsActualHitFrameOnThePaintedTrack() throws {
        let host = NSHostingView(rootView: ReferenceSwitch("Auto wake", isOn: .constant(false)))
        let window = NSWindow(contentRect: NSRect(x: 80, y: 80, width: 32, height: 18),
            styleMask: [.borderless], backing: .buffered, defer: false)
        window.contentView = host; window.orderFront(nil)
        defer { window.orderOut(nil) }
        host.layoutSubtreeIfNeeded(); window.displayIfNeeded()
        func find(_ view: NSView) -> ReferenceSwitchButton? {
            if let button = view as? ReferenceSwitchButton { return button }
            return view.subviews.lazy.compactMap(find).first
        }
        let button = try XCTUnwrap(find(host))
        XCTAssertEqual(button.bounds.size, NSSize(width: 32, height: 18))
        let actual = try XCTUnwrap(RelicAXRead(button)["frame"] as? NSValue).rectValue
        XCTAssertEqual(actual.size, NSSize(width: 32, height: 18))
        let content = window.convertToScreen(host.convert(host.bounds, to: nil))
        let owner = try XCTUnwrap(button.accessibilityIdentifier())
        let surface = try XCTUnwrap(SurfacePaintProbe.snapshots(in: content).first { $0["owner"] as? String == owner })
        XCTAssertEqual(ElementCapture.topLeft(actual, in: content), try XCTUnwrap(surface["rectValue"] as? NSValue).rectValue,
            "Native interaction and painted geometry must agree after actual SwiftUI layout")
    }

    func testPaddedCardUsesItsMountedSurfaceWhileRetainingAXContentBounds() throws {
        let owner = "relic-card/geometry-test"
        let sample = ReferenceLabel("A padded card", size: 13)
            .frame(width: 150, height: 20).padding(.horizontal, 10).padding(.vertical, 8)
            .modifier(RecordedSurface(background: .white, radius: 8, kind: "card", owner: owner))
        let host = NSHostingView(rootView: sample)
        let window = NSWindow(contentRect: NSRect(x: 80, y: 80, width: 170, height: 36),
            styleMask: [.borderless], backing: .buffered, defer: false)
        window.contentView = host; window.orderFront(nil)
        defer { window.orderOut(nil) }
        host.layoutSubtreeIfNeeded(); window.displayIfNeeded()
        let content = window.convertToScreen(host.convert(host.bounds, to: nil))
        let surface = try XCTUnwrap(SurfacePaintProbe.snapshots(in: content).first { $0["owner"] as? String == owner })
        let measured = try XCTUnwrap(surface["rectValue"] as? NSValue).rectValue
        XCTAssertEqual(measured.width, 170, accuracy: 0.01)
        XCTAssertEqual(measured.height, 36, accuracy: 0.01)
        let contentBounds = ElementCapture.box(NSRect(x: 10, y: 8, width: 150, height: 20))
        // The real SwiftUI AXGroup arrives as a region before its actual
        // production surface supplies the more specific card kind.
        var element: [String: Any] = ["kind": "region", "identifier": owner, "rect": contentBounds]
        NativeSurfaceGeometry.attach(to: &element, surface: surface, viewport: host.bounds)
        XCTAssertEqual(ElementCapture.rect(element["rect"]), measured)
        XCTAssertEqual(ElementCapture.rect(element["ax_content_rect"]), ElementCapture.rect(contentBounds))
        XCTAssertNotNil(element["native_surface_geometry"])
        // An unrelated but geometrically identical owner cannot lend its box.
        var unrelated: [String: Any] = ["kind": "card", "identifier": "different", "rect": contentBounds]
        NativeSurfaceGeometry.attach(to: &unrelated, surface: surface, viewport: host.bounds)
        XCTAssertNil(unrelated["native_surface_geometry"])
        XCTAssertEqual(ElementCapture.rect(unrelated["rect"]), ElementCapture.rect(contentBounds))
    }
}
