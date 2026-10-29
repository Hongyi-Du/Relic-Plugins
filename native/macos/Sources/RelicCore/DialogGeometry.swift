import Foundation

public struct DialogGeometry {
    public let kind: String
    public let window: CGSize
    public init(kind: String, window: CGSize) { self.kind = kind; self.window = window }
    public var width: CGFloat {
        switch kind {
        case "settings": return min(920, max(0, window.width - 40))
        case "details": return min(1180, max(0, window.width - 40))
        case "chart": return max(0, window.width - 40)
        case "card": return min(340, max(0, window.width - 24))
        case "copies": return min(760, max(0, window.width - 32))
        case "member", "protocolForm", "forward": return min(620, max(0, window.width - 32))
        default: return min(520, max(0, window.width - 32))
        }
    }
    public var height: CGFloat? {
        switch kind {
        case "settings": return min(640, max(0, window.height - 48))
        case "details", "chart": return max(0, window.height - 56)
        default: return nil
        }
    }
    public var maximumHeight: CGFloat { max(0, window.height - (kind == "card" ? 24 : kind == "copies" ? 56 : 60)) }
    public func cardOrigin(anchor: CGRect) -> CGPoint {
        CGPoint(x: max(12, min(anchor.maxX + 8, window.width - 356)), y: min(max(12, anchor.minY - 12), max(12, window.height - 520)))
    }
}
