using System;

namespace Relic;

// Explicit unitless CSS line-height on an ordinary (non-SVG) inline box.
// The primary font supplies the strut even when a glyph uses a fallback face.
// Chromium 156 computes integer font ascent/descent, then floors the *upper*
// half-leading. The remaining fractional leading belongs below the baseline.
// https://github.com/chromium/chromium/blob/156.0.8078.4/third_party/blink/renderer/core/layout/inline/inline_box_state.cc
// https://github.com/chromium/chromium/blob/156.0.8078.4/third_party/blink/renderer/core/layout/inline/line_utils.cc
// https://github.com/chromium/chromium/blob/156.0.8078.4/third_party/blink/renderer/platform/geometry/layout_unit.h
internal readonly record struct NativePrimaryLineMetrics(double Height, double Baseline,
    int PrimaryAscent, int PrimaryDescent, double LeadingBefore, double LeadingAfter)
{
    internal static NativePrimaryLineMetrics FromPrimary(NativeListMarkerMetrics primary, double lineHeight)
    {
        if (primary.Ascent <= 0 || primary.Descent < 0 || !double.IsFinite(lineHeight) || lineHeight <= 0)
            throw new ArgumentOutOfRangeException(nameof(lineHeight), "A primary-font line requires measured finite metrics");
        // A unitless line-height is a percentage of the fixed-point font size.
        // MinimumValueForLength constructs LayoutUnit by truncating to 1/64px.
        var rawHeight = checked((int)(lineHeight * 64));
        if (rawHeight <= 0) throw new ArgumentOutOfRangeException(nameof(lineHeight));
        var rawLeading = checked(rawHeight - checked((primary.Ascent + primary.Descent) * 64));
        // LayoutUnit / integer first truncates toward zero, then Floor() applies.
        // Preserve that order for negative leading with an odd 1/64px remainder.
        var leadingBefore = Math.Floor((rawLeading / 2) / 64d);
        var height = rawHeight / 64d;
        return new(height, primary.Ascent + leadingBefore, primary.Ascent, primary.Descent,
            leadingBefore, height - primary.Ascent - primary.Descent - leadingBefore);
    }
}
