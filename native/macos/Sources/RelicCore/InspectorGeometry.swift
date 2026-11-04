import Foundation

public enum InspectorGeometry {
    public static func sidebarWidth(window: CGFloat) -> CGFloat { window <= 820 ? 236 : 276 }
    public static func overlaysConversation(window: CGFloat) -> Bool { window <= 1180 }
    public static func width(window: CGFloat, saved: CGFloat, files: Bool) -> CGFloat {
        let preferred = saved > 0 && saved.isFinite ? saved : files ? 520 : 320
        return max(280, min(preferred, window * 0.6)).rounded()
    }
}
