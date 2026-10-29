import Foundation

public enum InspectorGeometry {
    public static func width(window: CGFloat, saved: CGFloat, files: Bool) -> CGFloat {
        let preferred = saved > 0 && saved.isFinite ? saved : files ? 520 : 320
        return max(280, min(preferred, window * 0.6)).rounded()
    }
}
