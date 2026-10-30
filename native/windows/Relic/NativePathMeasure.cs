using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using static Relic.NativeLabelInterop;

namespace Relic;

internal sealed record NativePathMeasurement(IReadOnlyList<NativePathLineBreaks.Cluster> Clusters,
    double NaturalHeight, double Baseline, JsonObject Evidence);

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

    internal static NativePathMeasurement Shape(string text, string families, double size, ushort weight, string locale)
    {
        IntPtr format = IntPtr.Zero, layout = IntPtr.Zero;
        try
        {
            var factory = NativeLabelDevice.Shared.WriteFactory;
            Check(Method<CreateFormat>(factory, 15)(factory, families.Split(',')[0].Trim().Trim('"'), IntPtr.Zero,
                weight, 0, 5, checked((float)size), locale, out format));
            Check(Method<SetUInt>(format, 5)(format, 1));
            Check(Method<CreateLayout>(factory, 18)(factory, text, checked((uint)text.Length), format, float.MaxValue, float.MaxValue, out layout));
            var fallback = NativeLabelFallback.Apply(factory, layout, families);
            var lines = Read<LineMetrics>(layout, 59);
            if (lines.Length != 1 || !float.IsFinite(lines[0].Height) || lines[0].Height <= 0
                || !float.IsFinite(lines[0].Baseline) || lines[0].Baseline <= 0)
                throw new InvalidOperationException("Path source requires one measurable unwrapped paragraph");
            var clusters = new List<NativePathLineBreaks.Cluster>(); var position = 0; var raw = new JsonArray();
            foreach (var cluster in Read<ClusterMetrics>(layout, 62))
            {
                clusters.Add(new NativePathLineBreaks.Cluster(position, cluster.Length, cluster.Width));
                raw.Add(new JsonObject { ["start_utf16"] = position, ["length_utf16"] = cluster.Length,
                    ["width"] = cluster.Width, ["raw_flags"] = cluster.Flags });
                position += cluster.Length;
            }
            if (position != text.Length) throw new InvalidOperationException("Measured path clusters do not cover the actual source");
            return new NativePathMeasurement(clusters, lines[0].Height, lines[0].Baseline, new JsonObject
            {
                ["source"] = "Production unwrapped DirectWrite layout used to choose source line ranges",
                ["scope"] = "Line breaking measurement; actual glyph drawing is on each retained NativeLabel line layout",
                ["source_text"] = text, ["layout_com_identity_at_measurement"] = ComIdentity(layout),
                ["configured_family_list"] = families, ["configured_size"] = size, ["configured_weight"] = weight,
                ["locale"] = locale, ["fallback_configuration"] = fallback, ["clusters"] = raw,
                ["natural_height"] = lines[0].Height, ["baseline"] = lines[0].Baseline
            });
        }
        finally { Release(ref layout); Release(ref format); }
    }
}
