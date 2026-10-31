import SwiftUI
import CoreGraphics

// Native geometry for the reference icon assets. No SVG/HTML rendering engine is
// involved. The source path is retained alongside the CGPath for capture evidence.
enum VectorPath {
    enum ParseError: Error { case invalidCommand(String), incompleteCommand(String) }
    static func parse(_ source: String) throws -> CGPath {
        let regex = try NSRegularExpression(pattern: #"[a-zA-Z]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"#)
        let ns = source as NSString
        let tokens = regex.matches(in: source, range: NSRange(location: 0, length: ns.length)).map { ns.substring(with: $0.range) }
        let path = CGMutablePath()
        var cursor = CGPoint.zero, start = CGPoint.zero, control = CGPoint.zero
        var index = 0, command = "", previous = ""
        func number() throws -> CGFloat {
            guard index < tokens.count, let value = Double(tokens[index]) else { throw ParseError.incompleteCommand(command) }
            index += 1; return CGFloat(value)
        }
        while index < tokens.count {
            if tokens[index].first?.isLetter == true { command = tokens[index]; index += 1 }
            let relative = command == command.lowercased()
            let origin = relative ? cursor : .zero
            func point() throws -> CGPoint { CGPoint(x: try number() + origin.x, y: try number() + origin.y) }
            switch command.uppercased() {
            case "M":
                cursor = try point(); start = cursor; path.move(to: cursor)
                command = relative ? "l" : "L"
            case "L": cursor = try point(); path.addLine(to: cursor)
            case "H": cursor.x = try number() + origin.x; path.addLine(to: cursor)
            case "V": cursor.y = try number() + origin.y; path.addLine(to: cursor)
            case "C":
                let c1 = try point(), c2 = try point(), end = try point()
                path.addCurve(to: end, control1: c1, control2: c2); cursor = end; control = c2
            case "S":
                let c1 = ["C", "S"].contains(previous) ? CGPoint(x: 2 * cursor.x - control.x, y: 2 * cursor.y - control.y) : cursor
                let c2 = try point(), end = try point()
                path.addCurve(to: end, control1: c1, control2: c2); cursor = end; control = c2
            case "Q":
                let c = try point(), end = try point()
                path.addQuadCurve(to: end, control: c); cursor = end; control = c
            case "A":
                let rx = try number(), ry = try number(), angle = try number()
                let large = try number() != 0, sweep = try number() != 0, end = try point()
                arc(path, from: cursor, to: end, rx: rx, ry: ry, angle: angle, large: large, sweep: sweep); cursor = end
            case "Z": path.closeSubpath(); cursor = start; command = ""
            default: throw ParseError.invalidCommand(command)
            }
            previous = command.uppercased()
        }
        return path
    }

    // SVG 2 Appendix B.2.4/5 endpoint-to-center conversion. CoreGraphics renders
    // the resulting elliptical arc directly instead of a raster substitute.
    private static func arc(_ path: CGMutablePath, from p: CGPoint, to q: CGPoint, rx initialX: CGFloat, ry initialY: CGFloat, angle: CGFloat, large: Bool, sweep: Bool) {
        guard p != q else { return }
        var rx = abs(initialX), ry = abs(initialY)
        guard rx > 0, ry > 0 else { path.addLine(to: q); return }
        let phi = angle * .pi / 180, c = cos(phi), s = sin(phi)
        let dx = (p.x - q.x) / 2, dy = (p.y - q.y) / 2
        let x = c * dx + s * dy, y = -s * dx + c * dy
        let scale = x * x / (rx * rx) + y * y / (ry * ry)
        if scale > 1 { rx *= sqrt(scale); ry *= sqrt(scale) }
        let numerator = rx * rx * ry * ry - rx * rx * y * y - ry * ry * x * x
        let denominator = rx * rx * y * y + ry * ry * x * x
        let factor = (large == sweep ? CGFloat(-1) : 1) * sqrt(max(0, numerator / denominator))
        let cx = factor * rx * y / ry, cy = -factor * ry * x / rx
        let center = CGPoint(x: c * cx - s * cy + (p.x + q.x) / 2, y: s * cx + c * cy + (p.y + q.y) / 2)
        let ux = (x - cx) / rx, uy = (y - cy) / ry
        let vx = (-x - cx) / rx, vy = (-y - cy) / ry
        let start = atan2(uy, ux)
        var delta = atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        if sweep && delta < 0 { delta += 2 * .pi }
        if !sweep && delta > 0 { delta -= 2 * .pi }
        let transform = CGAffineTransform(a: c * rx, b: s * rx, c: -s * ry, d: c * ry, tx: center.x, ty: center.y)
        path.addRelativeArc(center: .zero, radius: 1, startAngle: start, delta: delta, transform: transform)
    }
}

struct ReferenceIcon: View {
    let name: String
    var size: CGFloat = 18
    var color: Color = RelicStyle.secondary
    var owner: String? = nil
    var flexibleWidth = false
    @Environment(\.captureOpacity) private var opacity
    var body: some View {
        if flexibleWidth {
            ElementPaintProbe(name: name, size: size, color: color, owner: owner, opacity: opacity)
                .frame(minWidth: 0, idealWidth: size, maxWidth: .infinity).frame(height: size)
                .accessibilityHidden(true)
        } else {
            ElementPaintProbe(name: name, size: size, color: color, owner: owner, opacity: opacity)
                .frame(width: size, height: size)
                .accessibilityHidden(true)
        }
    }
}
