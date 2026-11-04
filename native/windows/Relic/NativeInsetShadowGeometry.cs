using System;
using System.Collections.Generic;

namespace Relic;

internal readonly record struct NativeInsetPoint(double X, double Y);
internal sealed record NativeInsetCommand(string Kind, double[] Values);
internal sealed record NativeInsetContour(IReadOnlyList<NativeInsetCommand> Commands,
    double X, double Y, double Width, double Height, double[] Radii);

internal static class NativeInsetShadowGeometry
{
    // CSS Backgrounds 3: normalize the border radii before deriving the
    // padding-edge ellipse radii. Inputs are actual production Border values.
    // https://www.w3.org/TR/css-backgrounds-3/#corner-shaping
    internal static NativeInsetContour PaddingEdge(double width, double height,
        double left, double top, double right, double bottom, double tl, double tr, double br, double bl)
    {
        foreach (var value in new[] { width, height, left, top, right, bottom, tl, tr, br, bl })
            if (!double.IsFinite(value) || value < 0) throw new ArgumentOutOfRangeException(nameof(width));
        if (width <= left + right || height <= top + bottom)
            throw new ArgumentOutOfRangeException(nameof(width), "The actual padding edge must have positive extent");
        var factor = 1d;
        void Limit(double extent, double sum) { if (sum > 0) factor = Math.Min(factor, extent / sum); }
        Limit(width, tl + tr); Limit(width, bl + br); Limit(height, tl + bl); Limit(height, tr + br);
        tl *= factor; tr *= factor; br *= factor; bl *= factor;
        var radii = new[] { Math.Max(0, tl - left), Math.Max(0, tl - top),
            Math.Max(0, tr - right), Math.Max(0, tr - top), Math.Max(0, br - right), Math.Max(0, br - bottom),
            Math.Max(0, bl - left), Math.Max(0, bl - bottom) };
        var x1 = width - right; var y1 = height - bottom;
        var commands = new List<NativeInsetCommand> { new("M", [left + radii[0], top]) };
        void Line(double x, double y) => commands.Add(new("L", [x, y]));
        void Arc(double x, double y, double rx, double ry)
        {
            // A zero axis is a straight corner, matching SVG/D2D arc semantics.
            if (rx == 0 || ry == 0) Line(x, y);
            else commands.Add(new("A", [x, y, rx, ry]));
        }
        Line(x1 - radii[2], top); Arc(x1, top + radii[3], radii[2], radii[3]);
        Line(x1, y1 - radii[5]); Arc(x1 - radii[4], y1, radii[4], radii[5]);
        Line(left + radii[6], y1); Arc(left, y1 - radii[7], radii[6], radii[7]);
        Line(left, top + radii[1]); Arc(left + radii[0], top, radii[0], radii[1]); commands.Add(new("Z", []));
        return new(commands, left, top, x1 - left, y1 - top, radii);
    }
}
