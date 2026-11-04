import AppKit

enum NativeTextRasterization {
    // app.css requests -webkit-font-smoothing: antialiased. Blink's macOS
    // CreateSkFont selects antialiasing without font smoothing for that value:
    // https://raw.githubusercontent.com/chromium/chromium/main/third_party/blink/renderer/platform/fonts/mac/font_platform_data_mac.mm
    // Apply this only to the app's own text draws; never change user defaults.
    static func begin(_ context: CGContext) {
        context.saveGState()
        context.setShouldAntialias(true)
        context.setShouldSmoothFonts(false)
    }
    static let inputs: [String: Any] = ["should_antialias": true, "should_smooth_fonts": false,
        "source": "production CoreGraphics setters around native text draw",
        "presentation_equivalence_proven": false]
}
