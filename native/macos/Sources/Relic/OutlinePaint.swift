import AppKit
import SwiftUI

/// Retains the path actually submitted to CoreGraphics. This is a draw receipt,
/// not a contour reconstructed from an element's expected bounding rectangle.
@MainActor struct OutlineDrawReceipt {
    let path: CGPath
    let bounds: CGRect
    let ownerBounds: CGRect
    let width: CGFloat
    let offset: CGFloat
    let dash: [CGFloat]
    let phase: CGFloat
    let color: [Double]
    let contextTransform: CGAffineTransform
    let contextClip: CGRect
    let revision: Int
    let sequence: Int
    let viewIdentity: String
    let windowIdentity: String?

    static func pathString(_ path: CGPath, map: @escaping (CGPoint) -> CGPoint) -> String {
        var commands: [String] = []
        path.applyWithBlock { item in
            let element = item.pointee
            let command: String, count: Int
            switch element.type {
            case .moveToPoint: command = "M"; count = 1
            case .addLineToPoint: command = "L"; count = 1
            case .addQuadCurveToPoint: command = "Q"; count = 2
            case .addCurveToPoint: command = "C"; count = 3
            case .closeSubpath: command = "Z"; count = 0
            @unknown default: command = "?"; count = 0
            }
            commands.append(command + (0..<count).map { index in
                let point = map(element.points[index])
                return String(Double(point.x)) + " " + String(Double(point.y))
            }.joined(separator: " "))
        }
        return commands.joined(separator: " ")
    }

    var raw: [String: Any] {
        ["source": "production SurfacePaintProbe.SurfaceView.draw",
         "sequence": sequence, "revision": revision,
         "view_identity": viewIdentity, "window_identity": windowIdentity as Any? ?? NSNull(),
         "local_bounds": ElementCapture.box(bounds), "local_owner_bounds": ElementCapture.box(ownerBounds), "local_stroke_path": Self.pathString(path, map: { $0 }),
         "outline_offset": Double(offset),
         "stroke_width": Double(width), "stroke_dash": dash.map(Double.init), "stroke_phase": Double(phase),
         "stroke_color": color, "line_cap": "butt", "line_join": "miter",
         "context_transform": [contextTransform.a, contextTransform.b, contextTransform.c, contextTransform.d, contextTransform.tx, contextTransform.ty],
         "context_clip": ElementCapture.box(contextClip), "draw_returned": true,
         "contour_quantity": "actual CG stroke centerline; dash segments and phase retained separately",
         "presentation_identity_proven": false]
    }

    func projected(view: NSView, content: NSRect, currentRevision: Int) -> (paint: Any, evidence: [String: Any]) {
        var evidence = raw
        guard let window = view.window, window.isVisible, !view.isHiddenOrHasHiddenAncestor,
              revision == currentRevision, bounds == view.bounds,
              viewIdentity == String(describing: ObjectIdentifier(view)),
              windowIdentity == String(describing: ObjectIdentifier(window)) else {
            evidence["errors"] = ["Outline draw no longer matches the visible mounted view, bounds or configuration"]
            return (NSNull(), evidence)
        }
        func point(_ point: CGPoint) -> CGPoint {
            let screen = window.convertPoint(toScreen: view.convert(point, to: nil))
            return CGPoint(x: screen.x - content.minX, y: content.maxY - screen.y)
        }
        let origin = point(.zero), x = point(CGPoint(x: 1, y: 0)), y = point(CGPoint(x: 0, y: 1))
        let a = x.x - origin.x, b = x.y - origin.y, c = y.x - origin.x, d = y.y - origin.y
        let sx = hypot(a, b), sy = hypot(c, d)
        let uniform = sx > 0 && abs(sx - sy) < 0.000001 && abs(a * c + b * d) < 0.000001
        evidence["local_to_window"] = [a, b, c, d, origin.x, origin.y]
        evidence["owner_bounds"] = ElementCapture.box(ElementCapture.topLeft(window.convertToScreen(view.convert(ownerBounds, to: nil)), in: content))
        evidence["errors"] = uniform ? [] : ["Nonuniform outline transform leaves width, dash and offset unmeasured"]
        let paint: [String: Any] = ["style": dash.isEmpty ? "solid" : "dashed", "color": color,
            "width": uniform ? Double(width * sx) as Any : NSNull(),
            "offset": uniform ? Double(offset * sx) as Any : NSNull(),
            "dash": uniform ? dash.map { Double($0 * sx) } as Any : NSNull(),
            "dash_offset": !dash.isEmpty && uniform ? Double(phase * sx) as Any : NSNull(),
            "contour": ["coordinate_space": "window", "paths": [["d": Self.pathString(path, map: point)]]]]
        return (paint, evidence)
    }
}
