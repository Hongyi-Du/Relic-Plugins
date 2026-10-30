import AppKit
import SwiftUI

/// The actual background painter. Its path and fill are independent native
/// evidence for later occlusion validation; a receipt alone does not establish
/// that another element was behind it or absent from the final screenshot.
struct NativeSurfaceFill: NSViewRepresentable {
    let color: Color
    let corners: [CGFloat]
    let owner: String?
    @Environment(\.captureRegion) private var region
    private static let live = NSHashTable<NativeSurfaceFillView>.weakObjects()
    func makeNSView(context: Context) -> NativeSurfaceFillView {
        let view = NativeSurfaceFillView(); Self.live.add(view)
        return view
    }
    func updateNSView(_ view: NativeSurfaceFillView, context: Context) {
        view.configure(color: NSColor(color), corners: corners, owner: owner, region: region)
    }
    static func observations(in window: NSWindow) -> [[String: Any]] {
        live.allObjects.filter { $0.window === window && !$0.isHiddenOrHasHiddenAncestor }.map { $0.observation() }
    }
}

@MainActor final class NativeSurfaceFillView: NSView {
    private var color = NSColor.clear
    private var corners: [CGFloat] = [0,0,0,0]
    private var owner: String?, region = "window"
    private var revision = 0, sequence = 0
    private(set) var lastDraw: [String: Any]?
    var recordDraws = VisualCapture.enabled
    override var isFlipped: Bool { true }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }
    override func isAccessibilityElement() -> Bool { false }
    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance(); revision += 1; needsDisplay = true
    }
    func configure(color: NSColor, corners: [CGFloat], owner: String?, region: String) {
        precondition(corners.count == 4)
        guard self.color != color || self.corners != corners || self.owner != owner || self.region != region else { return }
        self.color = color; self.corners = corners; self.owner = owner; self.region = region
        revision += 1; needsDisplay = true
    }
    override func draw(_ dirtyRect: NSRect) {
        guard let context = NSGraphicsContext.current?.cgContext,
              let fill = color.usingColorSpace(.sRGB) else { return }
        let path = UnevenRoundedRectangle(topLeadingRadius: corners[0], bottomLeadingRadius: corners[3],
            bottomTrailingRadius: corners[2], topTrailingRadius: corners[1], style: .circular).path(in: bounds).cgPath
        context.saveGState()
        context.setAlpha(1); context.setBlendMode(.normal); context.setShouldAntialias(true)
        context.setFillColor(fill.cgColor); context.addPath(path); context.fillPath()
        if recordDraws {
            sequence += 1
            lastDraw = ["provider": "production NativeSurfaceFillView.draw / CGContext.fillPath",
                "draw_returned": true, "sequence": sequence, "revision": revision,
                "view_identity": String(describing: ObjectIdentifier(self)),
                "window_identity": window.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull(),
                "local_bounds": ElementCapture.box(bounds),
                "local_path": OutlineDrawReceipt.pathString(path, map: { $0 }),
                "fill": ElementCapture.rgba(fill), "fill_rule": "nonzero", "global_alpha": 1,
                "blend_mode": "normal", "antialias": true,
                "context_ctm": [context.ctm.a, context.ctm.b, context.ctm.c, context.ctm.d, context.ctm.tx, context.ctm.ty],
                "context_clip": ElementCapture.box(context.boundingBoxOfClipPath)]
        }
        context.restoreGState()
    }
    func observation() -> [String: Any] {
        var actualFill: [Double]?
        effectiveAppearance.performAsCurrentDrawingAppearance { actualFill = ElementCapture.rgba(color) as? [Double] }
        var result: [String: Any] = ["source": "production native surface fill observation",
            "owner_identifier": owner as Any? ?? NSNull(), "region": region,
            "native_structure": NativeElementStructure.evidence(self, parent: owner),
            "opacity_ancestry": NativeVisibility.opacityAncestry(self),
            "occlusion_proven": false,
            "measurement_limit": "A current actual fill is not proof of final screenshot compositing order or covered-element invisibility"]
        guard let window, window.isVisible, !isHiddenOrHasHiddenAncestor,
              let content = window.contentView, let draw = lastDraw,
              draw["revision"] as? Int == revision,
              draw["view_identity"] as? String == String(describing: ObjectIdentifier(self)),
              draw["window_identity"] as? String == String(describing: ObjectIdentifier(window)),
              ElementCapture.rect(draw["local_bounds"]) == bounds,
              let actualFill, draw["fill"] as? [Double] == actualFill else {
            result["current_draw"] = NSNull(); result["errors"] = ["No current mounted native fill draw"]
            return result
        }
        result["current_draw"] = draw
        result["screen_bounds"] = ElementCapture.box(window.convertToScreen(convert(bounds, to: nil)))
        result["screen_clip"] = NativeVisibility.screenClip(self).map(ElementCapture.box) as Any? ?? NSNull()
        result["content_screen_frame"] = ["source": "actual NSWindow.contentView convert(bounds,to:nil) then window.convertToScreen",
            "coordinate_space": "AppKit screen coordinates (bottom-left)",
            "window_identity": String(describing: ObjectIdentifier(window)),
            "bounds": ElementCapture.box(window.convertToScreen(content.convert(content.bounds, to: nil)))]
        result["errors"] = []
        return result
    }
}
