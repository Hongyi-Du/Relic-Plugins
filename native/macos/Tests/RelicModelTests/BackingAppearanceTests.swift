import XCTest
import AppKit
import SwiftUI
@testable import Relic

@MainActor final class BackingAppearanceTests: XCTestCase {
    func testOwnedImagesResolveTheMountedViewsAppearanceForEveryPainter() throws {
        _ = NSApplication.shared
        let painters: [(String, (Bool) -> AnyView)] = [
            ("label", { AnyView(ReferenceLabel("Theme 组织", size: 14, color: RelicStyle.ink, ownedLayer: $0)) }),
            ("icon", { AnyView(ElementPaintProbe(name: "plus", size: 24, color: RelicStyle.ink, owner: nil, opacity: 1, ownedLayer: $0).frame(width: 24, height: 24)) }),
            ("fill", { AnyView(NativeSurfaceFill(color: RelicStyle.background, corners: [8,8,8,8], owner: nil, ownedLayer: $0)) })
        ]
        for (name, painter) in painters {
            var themes: [Data] = []
            for dark in [false, true] {
                var images: [Data] = []
                for owned in [false, true] {
                    let root = painter(owned).frame(width: 180, height: 32).environment(\.colorScheme, dark ? .dark : .light)
                    let host = NSHostingView(rootView: root)
                    host.frame = NSRect(x: 0, y: 0, width: 180, height: 32)
                    let appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
                    host.appearance = appearance
                    let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
                    window.isReleasedWhenClosed = false; window.appearance = appearance; window.contentView = host
                    window.orderFront(nil)
                    defer { window.orderOut(nil); window.contentView = nil; window.close() }
                    host.layoutSubtreeIfNeeded(); host.display(); CATransaction.flush()
                    let bitmap = try XCTUnwrap(CaptureRaster.forView(host)); host.cacheDisplay(in: host.bounds, to: bitmap)
                    images.append(try XCTUnwrap(bitmap.representation(using: .png, properties: [:])))
                }
                if images[0] != images[1] {
                    let package = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
                    let directory = package.appendingPathComponent(".build/draw-diagnostics", isDirectory: true)
                    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                    try images[0].write(to: directory.appendingPathComponent("appearance-\(name)-\(dark)-original.png"))
                    try images[1].write(to: directory.appendingPathComponent("appearance-\(name)-\(dark)-owned.png"))
                }
                XCTAssertEqual(images[0], images[1], "The actual mounted \(name) must preserve its \(dark ? "dark" : "light") appearance")
                themes.append(images[1])
            }
            XCTAssertNotEqual(themes[0], themes[1], "Both appearances producing the same pixels would hide a dynamic-color failure: \(name)")
        }
    }
}
