using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using static Relic.NativeLabelInterop;

namespace Relic;

// Sets the real production layout's fallback policy. This is configuration, not
// evidence of which font drew a character: that evidence remains in DrawGlyphRun.
internal static class NativeLabelFallback
{
    private static readonly Guid Factory2 = new("0439fc60-ca44-4994-8dee-3a9af7b732ec");
    private static readonly Guid Layout2 = new("1093c18f-8d5e-43f0-b064-0917311b525e");
    private static readonly Guid Unknown = new("00000000-0000-0000-c000-000000000046");
    [StructLayout(LayoutKind.Sequential)] private struct UnicodeRange { public uint First, Last; }
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int AddMapping(IntPtr self, ref UnicodeRange range,
        uint rangeCount, IntPtr familyNames, uint familyCount, IntPtr collection, IntPtr locale, IntPtr baseFamily, float scale);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int SetInterface(IntPtr self, IntPtr value);

    internal static JsonObject Apply(IntPtr factory, IntPtr productionLayout, string familyList)
    {
        var families = familyList.Split(',').Select(value => value.Trim().Trim('"')).ToArray();
        if (families.Length == 0 || families.Any(string.IsNullOrEmpty))
            throw new ArgumentException("NativeLabel fallback requires nonempty ordered family names", nameof(familyList));
        IntPtr factory2 = IntPtr.Zero, layout2 = IntPtr.Zero, builder = IntPtr.Zero, system = IntPtr.Zero,
            fallback = IntPtr.Zero, readback = IntPtr.Zero, fallbackIdentity = IntPtr.Zero, readbackIdentity = IntPtr.Zero;
        var names = Marshal.AllocHGlobal(checked(families.Length * IntPtr.Size)); var allocatedNames = new List<IntPtr>();
        try
        {
            factory2 = Query(factory, Factory2); layout2 = Query(productionLayout, Layout2);
            // IDWriteFactory contributes slots 3..23 and Factory1 adds 24..25.
            Check(Method<InterfaceResult>(factory2, 26)(factory2, out system));
            Check(Method<InterfaceResult>(factory2, 27)(factory2, out builder));
            for (var i = 0; i < families.Length; i++)
            {
                var name = Marshal.StringToHGlobalUni(families[i]); allocatedNames.Add(name);
                Marshal.WriteIntPtr(names, checked(i * IntPtr.Size), name);
            }
            var range = new UnicodeRange { First = 0, Last = 0x10ffff };
            Check(Method<AddMapping>(builder, 3)(builder, ref range, 1, names, checked((uint)families.Length),
                IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, 1));
            // Microsoft's AddMappings contract gives mappings appended first
            // priority over the appended system list. The family array itself is
            // the application's unmodified declared order, with no guessed cmap.
            Check(Method<SetInterface>(builder, 4)(builder, system));
            Check(Method<InterfaceResult>(builder, 5)(builder, out fallback));
            // TextLayout finishes at 66, Layout1 at 70; Layout2 fallback is 78/79.
            var setResult = Method<SetInterface>(layout2, 78)(layout2, fallback); Check(setResult);
            if (!CaptureDiagnostics) return new JsonObject();
            Check(Method<InterfaceResult>(layout2, 79)(layout2, out readback));
            fallbackIdentity = Query(fallback, Unknown); readbackIdentity = Query(readback, Unknown);
            if (fallbackIdentity != readbackIdentity) throw new InvalidOperationException("The production layout did not return the fallback object just applied to it");
            var values = new JsonArray(); foreach (var family in families) values.Add(family);
            return new JsonObject
            {
                ["source"] = "IDWriteFontFallbackBuilder applied to the same production IDWriteTextLayout2",
                ["target_families_in_order"] = values, ["range_first"] = range.First, ["range_last"] = range.Last,
                ["collection"] = "system", ["locale_filter"] = null, ["base_family_filter"] = null,
                ["scale"] = 1, ["system_fallback_appended_last"] = true,
                ["set_font_fallback_hresult"] = setResult, ["readback_same_com_identity"] = true,
                ["measured_drawn_font"] = false
            };
        }
        finally
        {
            foreach (var name in allocatedNames) Marshal.FreeHGlobal(name); Marshal.FreeHGlobal(names);
            Release(ref readbackIdentity); Release(ref fallbackIdentity); Release(ref readback);
            Release(ref fallback); Release(ref system); Release(ref builder); Release(ref layout2); Release(ref factory2);
        }
    }
}
