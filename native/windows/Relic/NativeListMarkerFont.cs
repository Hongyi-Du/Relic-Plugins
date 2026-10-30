using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using static Relic.NativeLabelInterop;

namespace Relic;

internal static class NativeListMarkerFont
{
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int GetCollection(IntPtr self, out IntPtr collection, int updates);
    [UnmanagedFunctionPointer(CallingConvention.StdCall, CharSet = CharSet.Unicode)] private delegate int FindFamily(IntPtr self, [MarshalAs(UnmanagedType.LPWStr)] string name, out uint index, out int exists);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int GetFamily(IntPtr self, uint index, out IntPtr family);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int MatchFont(IntPtr self, uint weight, uint stretch, uint style, out IntPtr font);

    internal static (NativeListMarkerMetrics Metrics, JsonObject Evidence) Read(string familyList, double size, string locale)
        => ReadPrimary(familyList, size, locale, 400, forTextLine: false);

    internal static (NativeListMarkerMetrics Metrics, JsonObject Evidence) ReadForLine(string familyList, double size, string locale, uint weight)
        => ReadPrimary(familyList, size, locale, weight, forTextLine: true);

    private static (NativeListMarkerMetrics Metrics, JsonObject Evidence) ReadPrimary(string familyList, double size, string locale, uint weight, bool forTextLine)
    {
        IntPtr collection = IntPtr.Zero, family = IntPtr.Zero, font = IntPtr.Zero, face = IntPtr.Zero;
        var lookups = new JsonArray();
        try
        {
            var factory = NativeLabelDevice.Shared.WriteFactory;
            Check(Method<GetCollection>(factory, 3)(factory, out collection, 0));
            string? selected = null;
            foreach (var candidate in familyList.Split(',').Select(value => value.Trim().Trim('"')))
            {
                if (candidate.Length == 0) continue;
                var hr = Method<FindFamily>(collection, 5)(collection, candidate, out var index, out var exists);
                lookups.Add(new JsonObject { ["family"] = candidate, ["hresult"] = hr, ["exists"] = exists != 0, ["index"] = index });
                Check(hr); if (exists == 0) continue;
                Check(Method<GetFamily>(collection, 4)(collection, index, out family)); selected = candidate; break;
            }
            if (family == IntPtr.Zero) throw new InvalidOperationException("No declared primary font is installed for the native primary-font layout");
            // IDWriteFontFamily inherits FontList slots 3..5; GetFamilyNames is
            // slot 6 and GetFirstMatchingFont(weight,stretch,style) is slot 7.
            // https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritefontfamily-getfirstmatchingfont
            Check(Method<MatchFont>(family, 7)(family, weight, 5, 0, out font));
            Check(Method<InterfaceResult>(font, 13)(font, out face));
            Method<GetFontMetrics>(face, 8)(face, out var raw);
            var metrics = NativeListMarkerMetrics.FromDesignUnits(raw.DesignUnitsPerEm, raw.Ascent, raw.Descent, size);
            Check(Method<InterfaceResult>(family, 6)(family, out var names));
            var evidence = new JsonObject
            {
                ["source"] = forTextLine
                    ? "Actual production line primary font: system collection FindFamilyName/GetFirstMatchingFont/CreateFontFace/GetMetrics"
                    : "Actual production disc primary font: system collection FindFamilyName/GetFirstMatchingFont/CreateFontFace/GetMetrics",
                ["family_request"] = familyList, ["locale_request"] = locale, ["selected_family"] = selected,
                ["family_lookups"] = lookups, ["family_names"] = ReadNames(names), ["requested_size"] = size, ["requested_weight"] = weight,
                ["face_index"] = Method<GetUInt>(face, 5)(face), ["simulations"] = Method<GetUInt>(face, 6)(face),
                ["units_per_em"] = raw.DesignUnitsPerEm, ["ascent_design_units"] = raw.Ascent,
                ["descent_design_units"] = raw.Descent, ["line_gap_design_units"] = raw.LineGap,
                ["native_ascent"] = raw.Ascent * size / raw.DesignUnitsPerEm,
                ["native_descent"] = raw.Descent * size / raw.DesignUnitsPerEm,
                ["layout_ascent"] = metrics.Ascent, ["layout_descent"] = metrics.Descent,
                ["quantity"] = forTextLine
                    ? "Actual primary metrics used for the production line strut; not a glyph-run font measurement"
                    : "Actual primary metrics used to lay out and draw a geometric disc; not a glyph-run font measurement"
            };
            return (metrics, evidence);
        }
        finally { Release(ref face); Release(ref font); Release(ref family); Release(ref collection); }
    }
}
