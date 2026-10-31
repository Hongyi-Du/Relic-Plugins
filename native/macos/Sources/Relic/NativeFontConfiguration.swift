import Foundation

extension NSAttributedString.Key {
    // The style requested by the native control, retained separately from the
    // resolved NSFont and actual glyph-callback variations. Neither substitutes
    // for the other when comparing computed style with selected font faces.
    static let relicConfiguredFontWeight = NSAttributedString.Key("RelicConfiguredFontWeight")
}
