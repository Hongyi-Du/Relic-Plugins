using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using static Relic.NativeLabelInterop;

namespace Relic;

internal sealed record NativePathMeasurement(IReadOnlyList<NativePathLineBreaks.Cluster> Clusters,
    double NaturalHeight, double Baseline, JsonObject Evidence, NativePathIntrinsicWidths? IntrinsicWidths = null);

internal sealed record NativePathIntrinsicWidths(double Width, double WidthIncludingTrailingWhitespace, double MinimumWidth);

internal static class NativePathMeasure
{
    [StructLayout(LayoutKind.Sequential)] private struct ClusterMetrics
    { internal float Width; internal ushort Length, Flags; }

    private static T[] Read<T>(IntPtr layout, int slot) where T : struct
    {
        var call = Method<GetArray>(layout, slot); var first = call(layout, IntPtr.Zero, 0, out var count);
        if (first < 0 && first != unchecked((int)0x8007007A)) Check(first);
        if (count == 0) return [];
        var buffer = Marshal.AllocHGlobal(checked((int)count * Marshal.SizeOf<T>()));
        try
        {
            Check(call(layout, buffer, count, out var actual));
            if (actual > count) throw new InvalidOperationException("DirectWrite exceeded its actual buffer");
            var values = new T[actual];
            for (var i = 0; i < values.Length; i++) values[i] = Marshal.PtrToStructure<T>(buffer + i * Marshal.SizeOf<T>());
            return values;
        }
        finally { Marshal.FreeHGlobal(buffer); }
    }

    internal static NativePathMeasurement Shape(string text, string families, double size, ushort weight, string locale,
        bool measureIntrinsicWidths = false)
    {
        using var timing = PerformanceTrace.Measure("NativePath.shape");
        IntPtr format = IntPtr.Zero, layout = IntPtr.Zero;
        try
        {
            var factory = NativeLabelDevice.Shared.WriteFactory;
            Check(Method<CreateFormat>(factory, 15)(factory, families.Split(',')[0].Trim().Trim('"'), IntPtr.Zero,
                weight, 0, 5, checked((float)size), locale, out format));
            // A banner obtains both intrinsic widths from this same production
            // source-measurement layout. Its very wide box does not wrap; the
            // WHOLE_WORD policy defines the non-emergency minimum. Existing
            // path/notice measurements retain their original NO_WRAP policy.
            Check(Method<SetUInt>(format, 5)(format, measureIntrinsicWidths ? 3u : 1u));
            Check(Method<CreateLayout>(factory, 18)(factory, text, checked((uint)text.Length), format, float.MaxValue, float.MaxValue, out layout));
            var fallback = NativeLabelFallback.Apply(factory, layout, families);
            NativePathIntrinsicWidths? intrinsic = null; JsonObject? intrinsicEvidence = null;
            if (measureIntrinsicWidths)
            {
                var metricsResult = Method<GetTextMetrics>(layout, 60)(layout, out var metrics);
                Check(metricsResult);
                var minimumResult = Method<DetermineMinWidth>(layout, 63)(layout, out var minimum);
                Check(minimumResult);
                if (!float.IsFinite(metrics.Width) || metrics.Width < 0
                    || !float.IsFinite(metrics.WidthIncludingTrailingWhitespace) || metrics.WidthIncludingTrailingWhitespace < 0
                    || !float.IsFinite(minimum) || minimum < 0)
                    throw new InvalidOperationException("Actual DirectWrite intrinsic widths must be finite and nonnegative");
                intrinsic = new(metrics.Width, metrics.WidthIncludingTrailingWhitespace, minimum);
                if (CaptureDiagnostics) intrinsicEvidence = new JsonObject
                {
                    ["source"] = "GetMetrics and DetermineMinWidth on the actual production source-measurement IDWriteTextLayout",
                    ["quantity"] = "Production flex and line-breaking input, not a per-line drawing layout or final glyph bounds",
                    ["layout_com_identity"] = ComIdentity(layout), ["get_metrics_hresult"] = metricsResult,
                    ["determine_min_width_hresult"] = minimumResult, ["word_wrapping"] = 3,
                    ["width"] = metrics.Width, ["width_including_trailing_whitespace"] = metrics.WidthIncludingTrailingWhitespace,
                    ["minimum_width_without_emergency_breaking"] = minimum,
                    ["layout_width"] = metrics.LayoutWidth, ["layout_height"] = metrics.LayoutHeight
                };
            }
            var lines = Read<LineMetrics>(layout, 59);
            if (lines.Length != 1 || !float.IsFinite(lines[0].Height) || lines[0].Height <= 0
                || !float.IsFinite(lines[0].Baseline) || lines[0].Baseline <= 0)
                throw new InvalidOperationException("Path source requires one measurable unwrapped paragraph");
            var clusters = new List<NativePathLineBreaks.Cluster>(); var position = 0; var raw = new JsonArray();
            foreach (var cluster in Read<ClusterMetrics>(layout, 62))
            {
                clusters.Add(new NativePathLineBreaks.Cluster(position, cluster.Length, cluster.Width));
                if (CaptureDiagnostics) raw.Add(new JsonObject { ["start_utf16"] = position, ["length_utf16"] = cluster.Length,
                    ["width"] = cluster.Width, ["raw_flags"] = cluster.Flags });
                position += cluster.Length;
            }
            if (position != text.Length) throw new InvalidOperationException("Measured path clusters do not cover the actual source");
            if (!CaptureDiagnostics) return new NativePathMeasurement(clusters, lines[0].Height, lines[0].Baseline, new JsonObject(), intrinsic);
            return new NativePathMeasurement(clusters, lines[0].Height, lines[0].Baseline, new JsonObject
            {
                ["source"] = "Production unwrapped DirectWrite layout used to choose source line ranges",
                ["scope"] = "Line breaking measurement; actual glyph drawing is on each retained NativeLabel line layout",
                ["source_text"] = text, ["layout_com_identity_at_measurement"] = ComIdentity(layout),
                ["configured_family_list"] = families, ["configured_size"] = size, ["configured_weight"] = weight,
                ["locale"] = locale, ["fallback_configuration"] = fallback, ["clusters"] = raw,
                ["natural_height"] = lines[0].Height, ["baseline"] = lines[0].Baseline,
                ["intrinsic_widths"] = intrinsicEvidence
            }, intrinsic);
        }
        finally { Release(ref layout); Release(ref format); }
    }
}
