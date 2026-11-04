using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;

namespace Relic;

// The pure classifier is also compiled into Core.Tests. COM calls occur only
// in ObserveOutline, against the run already in the production draw callback.
internal static class NativeGlyphBounds
{
    internal readonly record struct Bounds(float Left, float Top, float Right, float Bottom)
    {
        internal bool Finite => float.IsFinite(Left) && float.IsFinite(Top) && float.IsFinite(Right) && float.IsFinite(Bottom);
        internal bool Ordered => Finite && Left <= Right && Top <= Bottom;
    }

    internal static JsonObject Classify(int hresult, Bounds bounds, Func<JsonObject> observeOutline)
    {
        var result = new JsonObject
        {
            ["source"] = "Actual GetGlyphRunWorldBounds result and same-callback glyph outline observation",
            ["bounds_hresult"] = hresult, ["bounds_hresult_hex"] = Hex(hresult),
            ["raw_bounds"] = new JsonObject { ["left"] = Number(bounds.Left), ["top"] = Number(bounds.Top),
                ["right"] = Number(bounds.Right), ["bottom"] = Number(bounds.Bottom) },
            ["raw_bounds_classification"] = !bounds.Finite ? "nonfinite" : bounds.Ordered ? "finite-ordered" : "reversed",
            ["classification"] = "unclassified", ["outline"] = null, ["failure"] = null,
            ["quantity"] = "Glyph-run world ink envelope or separately observed empty base outline; never advance/layout or final PNG coverage"
        };
        if (hresult < 0)
        {
            result["classification"] = "api-failed";
            result["failure"] = "GetGlyphRunWorldBounds failed: " + Hex(hresult);
        }
        else if (bounds.Ordered) result["classification"] = "finite";
        else
        {
            try
            {
                var outline = observeOutline();
                result["outline"] = outline;
                if (OutlineEmpty(outline)) result["classification"] = "outline-empty";
                else result["failure"] = "Abnormal world bounds are not proven to have an empty base glyph outline";
            }
            catch (Exception error) { result["failure"] = error.ToString(); }
        }
        return result;
    }

    internal static bool OutlineEmpty(JsonObject value) =>
        value["source"]?.GetValue<string>() == "Actual same-run IDWriteFontFace.GetGlyphRunOutline into ID2D1PathGeometry"
        && value["failure"] is null && value["cleanup_failure"] is null && value["color_font"]?.GetValue<bool>() == false
        && new[] { "create_path_hresult", "open_hresult", "outline_hresult", "close_hresult", "segment_count_hresult", "figure_count_hresult" }
            .All(key => value[key] is JsonValue number && number.TryGetValue<int>(out var hr) && hr >= 0)
        && value["figure_count"]?.GetValue<uint>() == 0 && value["segment_count"]?.GetValue<uint>() == 0;

    private static JsonObject Number(float value) => new()
    {
        ["value"] = float.IsFinite(value) ? JsonValue.Create(value) : null,
        ["raw_value"] = value.ToString("R", CultureInfo.InvariantCulture), ["ieee754_format"] = "binary32",
        ["ieee754_bits"] = unchecked((uint)BitConverter.SingleToInt32Bits(value)).ToString("X8", CultureInfo.InvariantCulture)
    };
    private static string Hex(int value) => "0x" + unchecked((uint)value).ToString("X8", CultureInfo.InvariantCulture);

    // SDK dwrite.h DWRITE_GLYPH_RUN. We read the original callback pointer;
    // no glyph run or text layout is reconstructed for this observation.
    [StructLayout(LayoutKind.Sequential)] private struct GlyphRun
    { internal IntPtr Face; internal float Size; internal uint Count; internal IntPtr Indices, Advances, Offsets; internal int Sideways; internal uint Bidi; }
    [StructLayout(LayoutKind.Sequential)] private struct GlyphOffset { internal float Advance, Ascender; }
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate void FactoryGetter(IntPtr self, out IntPtr factory);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int CreateInterface(IntPtr self, out IntPtr result);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int CloseSink(IntPtr self);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int CountGetter(IntPtr self, out uint value);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int OutlineGetter(IntPtr self, float size,
        IntPtr glyphs, IntPtr advances, IntPtr offsets, uint count, int sideways, int rightToLeft, IntPtr sink);
    private static T Method<T>(IntPtr value, int slot) where T : Delegate =>
        Marshal.GetDelegateForFunctionPointer<T>(Marshal.ReadIntPtr(Marshal.ReadIntPtr(value), slot * IntPtr.Size));

    internal static JsonObject ObserveOutline(IntPtr context, IntPtr originalRun, int ordinal, bool? colorFont)
    {
        var result = new JsonObject
        {
            ["source"] = "Actual same-run IDWriteFontFace.GetGlyphRunOutline into ID2D1PathGeometry",
            ["glyph_run_ordinal"] = ordinal, ["callback_run_pointer"] = originalRun.ToString("x"),
            ["color_font"] = colorFont, ["binding"] = null, ["failure"] = null,
            ["figure_count"] = null, ["segment_count"] = null,
            ["create_path_hresult"] = null, ["open_hresult"] = null, ["outline_hresult"] = null,
            ["close_hresult"] = null, ["figure_count_hresult"] = null, ["segment_count_hresult"] = null,
            ["quantity"] = "Actual base outline topology; not glyph advance, raster pixels or final presentation"
        };
        IntPtr factory = IntPtr.Zero, geometry = IntPtr.Zero, sink = IntPtr.Zero;
        bool sinkClosed = false;
        void Check(string key, int hr) { result[key] = hr; if (hr < 0) Marshal.ThrowExceptionForHR(hr); }
        try
        {
            if (colorFont != false) throw new NotSupportedException("Color-font status is not false; base outline cannot establish absence of all glyph paint");
            if (context == IntPtr.Zero || originalRun == IntPtr.Zero) throw new InvalidOperationException("Actual context or callback run is absent");
            var run = Marshal.PtrToStructure<GlyphRun>(originalRun);
            if (run.Face == IntPtr.Zero || (run.Count > 0 && run.Indices == IntPtr.Zero)) throw new InvalidOperationException("Actual run font face or glyph indices are absent");
            var glyphs = new JsonArray(); var advances = new JsonArray(); var offsets = new JsonArray();
            for (var i = 0; i < run.Count; i++)
            {
                glyphs.Add((ushort)Marshal.ReadInt16(run.Indices, checked(i * 2)));
                if (run.Advances != IntPtr.Zero) advances.Add(Marshal.PtrToStructure<float>(run.Advances + checked(i * 4)));
                if (run.Offsets != IntPtr.Zero)
                {
                    var offset = Marshal.PtrToStructure<GlyphOffset>(run.Offsets + checked(i * 8));
                    offsets.Add(new JsonObject { ["advance"] = offset.Advance, ["ascender"] = offset.Ascender });
                }
            }
            result["binding"] = new JsonObject
            {
                ["font_face_process_pointer"] = run.Face.ToString("x"), ["em_size"] = run.Size, ["glyph_count"] = run.Count,
                ["glyph_indices"] = glyphs, ["glyph_advances"] = run.Advances == IntPtr.Zero ? null : advances,
                ["glyph_offsets"] = run.Offsets == IntPtr.Zero ? null : offsets, ["sideways"] = run.Sideways != 0,
                ["bidi_level"] = run.Bidi, ["right_to_left"] = (run.Bidi & 1) != 0
            };
            // ID2D1Resource::GetFactory (3) returns void and an owned reference.
            Method<FactoryGetter>(context, 3)(context, out factory);
            result["factory_process_pointer"] = factory.ToString("x");
            if (factory == IntPtr.Zero) throw new InvalidOperationException("Actual D2D context returned no factory");
            Check("create_path_hresult", Method<CreateInterface>(factory, 10)(factory, out geometry));
            if (geometry == IntPtr.Zero) throw new InvalidOperationException("CreatePathGeometry returned no path");
            // ID2D1PathGeometry::Open (17), GetSegmentCount (19), GetFigureCount (20).
            Check("open_hresult", Method<CreateInterface>(geometry, 17)(geometry, out sink));
            if (sink == IntPtr.Zero) throw new InvalidOperationException("Path Open returned no sink");
            // FontFace slot 14; original arrays and actual face are passed unchanged.
            Check("outline_hresult", Method<OutlineGetter>(run.Face, 14)(run.Face, run.Size, run.Indices,
                run.Advances, run.Offsets, run.Count, run.Sideways, (run.Bidi & 1) != 0 ? 1 : 0, sink));
            sinkClosed = true;
            Check("close_hresult", Method<CloseSink>(sink, 9)(sink));
            Check("segment_count_hresult", Method<CountGetter>(geometry, 19)(geometry, out var segments));
            result["segment_count"] = segments;
            Check("figure_count_hresult", Method<CountGetter>(geometry, 20)(geometry, out var figures));
            result["figure_count"] = figures;
        }
        catch (Exception error) { result["failure"] = error.ToString(); }
        finally
        {
            if (sink != IntPtr.Zero)
            {
                if (!sinkClosed)
                {
                    try { result["close_hresult"] = Method<CloseSink>(sink, 9)(sink); }
                    catch (Exception error) { result["cleanup_failure"] = error.ToString(); }
                }
                Marshal.Release(sink);
            }
            if (geometry != IntPtr.Zero) Marshal.Release(geometry);
            if (factory != IntPtr.Zero) Marshal.Release(factory);
        }
        return result;
    }
}
