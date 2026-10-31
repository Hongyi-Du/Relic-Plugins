import Foundation

/// All values are logical screen points. AppKit owns the backing-pixel mapping.
public enum WindowPlacement {
    public static func defaultFrame(in visible: CGRect) -> CGRect {
        let size = CGSize(width: min(1440, visible.width * 0.85), height: min(900, visible.height * 0.85))
        return CGRect(x: visible.midX - size.width / 2, y: visible.midY - size.height / 2,
                      width: size.width, height: size.height)
    }

    public static func minimumSize(in visible: CGRect) -> CGSize {
        // On a small display the minimum must not force a larger-than-default
        // window or push any part of it behind the menu bar or Dock.
        let available = defaultFrame(in: visible).size
        return CGSize(width: min(960, available.width), height: min(640, available.height))
    }

    public static func restoredFrame(_ saved: CGRect?, screens: [CGRect], preferred: CGRect) -> CGRect {
        guard let saved, valid(saved), let screen = screens.filter({ valid($0) }).max(by: {
            intersectionArea(saved, $0) < intersectionArea(saved, $1)
        }), intersectionArea(saved, screen) > 0 else { return defaultFrame(in: preferred) }
        return clamped(saved, to: screen)
    }

    public static func clamped(_ frame: CGRect, to visible: CGRect) -> CGRect {
        let minimum = minimumSize(in: visible)
        let width = min(visible.width, max(minimum.width, frame.width))
        let height = min(visible.height, max(minimum.height, frame.height))
        return CGRect(x: min(max(frame.minX, visible.minX), visible.maxX - width),
                      y: min(max(frame.minY, visible.minY), visible.maxY - height), width: width, height: height)
    }

    private static func valid(_ frame: CGRect) -> Bool {
        frame.origin.x.isFinite && frame.origin.y.isFinite && frame.width.isFinite && frame.height.isFinite
            && frame.width > 0 && frame.height > 0
    }
    private static func intersectionArea(_ lhs: CGRect, _ rhs: CGRect) -> CGFloat {
        let intersection = lhs.intersection(rhs)
        return intersection.isNull ? 0 : intersection.width * intersection.height
    }
}
