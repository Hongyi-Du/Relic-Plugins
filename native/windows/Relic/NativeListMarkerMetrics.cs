using System;

namespace Relic;

internal readonly record struct NativeMarkerRect(double X, double Y, double Width, double Height);

// Production disc layout. Integer arithmetic follows the fixed Chromium
// ListMarker::RelativeSymbolMarkerRect/SymbolMarkerWidth/InlineMarginsForOutside;
// only this platform's actual primary-face metrics enter the calculation.
// https://github.com/chromium/chromium/blob/156.0.8078.4/third_party/blink/renderer/core/layout/list/list_marker.cc
// https://github.com/chromium/chromium/blob/156.0.8078.4/third_party/blink/renderer/core/paint/text_fragment_painter.cc
internal readonly record struct NativeListMarkerMetrics(int Ascent, int Descent)
{
    internal int Diameter => (Ascent * 2 / 3 + 1) / 2;
    internal int Width => Diameter + 2;
    internal int Height => Ascent + Descent;
    internal int DistanceBeforeText => Ascent * 2 / 3 + 8;
    internal NativeMarkerRect Disc => new(1, 3 * (Ascent - Ascent * 2 / 3) / 2, Diameter, Diameter);
    internal NativeMarkerRect Outside(double textStart, double actualBaseline) =>
        new(textStart - DistanceBeforeText, actualBaseline - Ascent, Width, Height);

    internal static NativeListMarkerMetrics FromDesignUnits(int unitsPerEm, int ascent, int descent, double emSize)
    {
        if (unitsPerEm <= 0 || ascent <= 0 || descent < 0 || !double.IsFinite(emSize) || emSize <= 0)
            throw new ArgumentOutOfRangeException(nameof(emSize), "Native disc requires finite positive primary font metrics");
        // FontMetrics::SetAscent/SetDescent uses lroundf before symbol layout.
        var a = checked((int)Math.Round((float)(ascent * emSize / unitsPerEm), MidpointRounding.AwayFromZero));
        var d = checked((int)Math.Round((float)(descent * emSize / unitsPerEm), MidpointRounding.AwayFromZero));
        if (a <= 0) throw new ArgumentOutOfRangeException(nameof(emSize), "Primary-font ascent rounds to zero");
        return new(a, d);
    }

    internal static NativeMarkerRect Snap(NativeMarkerRect local, double windowX, double windowY, double scale)
    {
        if (!double.IsFinite(windowX) || !double.IsFinite(windowY) || !double.IsFinite(scale) || scale <= 0
            || !double.IsFinite(local.X) || !double.IsFinite(local.Y) || !double.IsFinite(local.Width) || !double.IsFinite(local.Height)
            || local.Width < 0 || local.Height < 0) throw new ArgumentOutOfRangeException(nameof(scale));
        static double Edge(double value) => Math.Floor(value + .5);
        var left = Edge((windowX + local.X) * scale); var top = Edge((windowY + local.Y) * scale);
        var right = Edge((windowX + local.X + local.Width) * scale); var bottom = Edge((windowY + local.Y + local.Height) * scale);
        if (!double.IsFinite(left) || !double.IsFinite(top) || !double.IsFinite(right) || !double.IsFinite(bottom))
            throw new ArgumentOutOfRangeException(nameof(scale), "Device-space symbol edges are non-finite");
        return new(left / scale - windowX, top / scale - windowY, (right - left) / scale, (bottom - top) / scale);
    }
}
