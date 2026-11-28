import AppKit
import CoreGraphics
import RelicCore

/// CI only: make the complete native window reachable by the real pointer.
/// Mode selection uses the runner's advertised display modes, never rescales
/// the window, screenshot or extracted geometry to fit a smaller screen.
@MainActor final class CaptureDisplay {
    private let display = CGMainDisplayID()
    private let original: CGDisplayMode?
    private let output: URL
    private var record: [String: Any]
    private var switched = false
    init(cases: [Node], output: URL) throws {
        guard ProcessInfo.processInfo.environment["GITHUB_ACTIONS"] == "true" else { throw RelicError.message("Capture display preparation is restricted to GitHub Actions") }
        self.output = output.appendingPathComponent("native-display.json")
        original = CGDisplayCopyDisplayMode(display)
        let modes = CGDisplayCopyAllDisplayModes(display, nil) as? [CGDisplayMode] ?? []
        let requiredWidth = (cases.map { $0["width"].integer }.max() ?? 1440) + 40
        let requiredHeight = (cases.map { $0["height"].integer }.max() ?? 900) + 80
        func description(_ mode: CGDisplayMode) -> [String: Any] {
            ["width": mode.width, "height": mode.height, "pixel_width": mode.pixelWidth, "pixel_height": mode.pixelHeight,
             "refresh_rate": mode.refreshRate, "desktop_usable": mode.isUsableForDesktopGUI()]
        }
        let before = CGDisplayBounds(display)
        record = ["display_id": display, "before_bounds": ElementCapture.box(before), "required_width": requiredWidth,
                  "required_height": requiredHeight, "advertised_modes": modes.map(description), "original": original.map(description) as Any? ?? NSNull()]
        if before.width < CGFloat(requiredWidth) || before.height < CGFloat(requiredHeight) {
            let candidates = modes.filter { $0.width >= requiredWidth && $0.height >= requiredHeight && $0.isUsableForDesktopGUI() }
                .sorted { $0.width * $0.height < $1.width * $1.height }
            if let mode = candidates.first {
                let result = CGDisplaySetDisplayMode(display, mode, nil)
                switched = result == .success
                record["requested_mode"] = description(mode); record["set_result"] = result.rawValue
            } else { record["unavailable"] = "No advertised mode fits the requested native client area plus window frame and pointer margin" }
        }
        record["after_bounds"] = ElementCapture.box(CGDisplayBounds(display))
        save()
        print("Native capture display: before=\(before), after=\(CGDisplayBounds(display)), advertised_modes=\(modes.count), changed=\(switched)"); fflush(stdout)
    }
    func restore() {
        if switched { record["restore_result"] = CGDisplaySetDisplayMode(display, original, nil).rawValue; switched = false }
        record["restored_bounds"] = ElementCapture.box(CGDisplayBounds(display)); save()
    }
    private func save() { if let data = try? JSONSerialization.data(withJSONObject: record, options: [.prettyPrinted, .sortedKeys]) { try? data.write(to: output) } }
}
