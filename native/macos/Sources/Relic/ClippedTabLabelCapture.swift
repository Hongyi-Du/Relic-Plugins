import AppKit

/// A tab can retain its accessible name while its entire native label lies
/// outside the horizontal viewport. The name must not become painted text.
/// Only a single explicitly owned, mounted label with an empty actual native
/// visibleRect supplies this absence; partial clipping and unknown owners do not.
@MainActor enum ClippedTabLabelCapture {
    static func attach(to elements: inout [[String: Any]], labels: [ReferenceLabelView], window: NSWindow) {
        let mounted = labels.filter { $0.window === window && $0.productionOwner != nil }
        for index in elements.indices {
            guard elements[index]["kind"] as? String == "tab",
                  let identifier = elements[index]["identifier"] as? String,
                  identifier.hasPrefix("relic-tab/"), elements[index]["owned_text_id"] == nil else { continue }
            let owners = elements.filter { $0["identifier"] as? String == identifier }
            let sources = mounted.filter { $0.productionOwner == identifier }
            guard owners.count == 1, sources.count == 1, let label = sources.first,
                  label.productionParent == identifier, window.isVisible,
                  !label.isHiddenOrHasHiddenAncestor, NativeVisibility.opacity(label) > 0,
                  !label.isEditable, !label.string.isEmpty,
                  label.visibleRect.isEmpty || label.visibleRect.isNull else { continue }
            let screen = window.convertToScreen(label.convert(label.bounds, to: nil))
            elements[index]["text"] = ""
            elements[index]["native_clipped_tab_label"] = [
                "source": "explicit production tab/label ownership and current NSView.visibleRect",
                "owner_identifier": identifier, "label_identity": String(describing: ObjectIdentifier(label)),
                "window_identity": String(describing: ObjectIdentifier(window)), "source_text": label.string,
                "native_bounds": ElementCapture.box(label.bounds), "screen_bounds": ElementCapture.box(screen),
                "native_visible_rect": label.visibleRect.isNull ? NSNull() : ElementCapture.box(label.visibleRect),
                "native_structure": NativeElementStructure.evidence(label, parent: identifier),
                "scope": "Visible text only; the tab and its actual accessible name remain unchanged"]
        }
    }
}
