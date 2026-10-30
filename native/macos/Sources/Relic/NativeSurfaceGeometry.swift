import AppKit

enum NativeSurfaceGeometry {
    // AXGroup reports its children's content union for some SwiftUI cards.
    // The visible card includes padding/borders painted by the uniquely owned
    // production surface. Keep both independently measured quantities.
    static func attach(to element: inout [String: Any], surface: [String: Any], viewport: NSRect) {
        guard let owner = surface["owner"] as? String,
              owner == element["identifier"] as? String,
              let kind = element["kind"] as? String,
              ["input", "dropdown", "card"].contains(kind),
              let value = surface["rectValue"] as? NSValue else { return }
        let rect = value.rectValue
        let visible = rect.intersection(ElementCapture.rect(surface["nativeVisibleBounds"])).intersection(viewport)
        guard !visible.isNull, visible.width > 0, visible.height > 0 else { return }
        element["ax_content_rect"] = element["rect"]
        element["rect"] = ElementCapture.box(rect)
        element["visibleRect"] = ElementCapture.box(visible)
        element["native_surface_geometry"] = [
            "source": "uniquely owned mounted production surface bounds converted through its actual NSWindow",
            "owner_identifier": owner,
            "surface_identity": (surface["evidence"] as? [String: Any])?["identity"] ?? NSNull(),
            "native_structure": surface["native_structure"] ?? NSNull()
        ]
    }
}
