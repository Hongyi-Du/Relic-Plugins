import AppKit
import SwiftUI

// A production component supplies its real parent identity. The sibling order
// comes from mounted AppKit subviews, never from reference positions or text.
private struct NativeElementParentKey: EnvironmentKey {
    static let defaultValue: String? = nil
}
extension EnvironmentValues {
    var nativeElementParent: String? {
        get { self[NativeElementParentKey.self] }
        set { self[NativeElementParentKey.self] = newValue }
    }
}

@MainActor enum NativeElementStructure {
    static func path(_ view: NSView) -> [Int]? {
        guard let root = view.window?.contentView else { return nil }
        var current = view, result: [Int] = []
        while current !== root {
            guard let parent = current.superview,
                  let index = parent.subviews.firstIndex(where: { $0 === current }) else { return nil }
            result.insert(index, at: 0); current = parent
        }
        return result
    }
    static func evidence(_ view: NSView, parent: String?) -> [String: Any] {
        ["parent_identifier": parent as Any? ?? NSNull(),
         "native_subview_path": path(view) as Any? ?? NSNull(),
         "source": "production parent environment and current NSView.subviews ancestry",
         "view_identity": String(describing: ObjectIdentifier(view)),
         "window_identity": view.window.map { String(describing: ObjectIdentifier($0)) } as Any? ?? NSNull()]
    }
}
