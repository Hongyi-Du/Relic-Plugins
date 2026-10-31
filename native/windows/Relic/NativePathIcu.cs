using System.Runtime.InteropServices;
using System.Text.Json.Nodes;

namespace Relic;

internal sealed record NativePathBoundaries(int[] Lines, int[] Characters, int[] Words, JsonObject Evidence);

internal static class NativePathIcu
{
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate IntPtr Open(int type, IntPtr locale, IntPtr text, int length, ref int error);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate int Position(IntPtr iterator);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate void Close(IntPtr iterator);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate void Version([Out] byte[] version);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate IntPtr Locale(IntPtr iterator, int type, ref int error);

    internal static NativePathBoundaries Read(string text, string locale)
    {
        IntPtr common = IntPtr.Zero, international = IntPtr.Zero, input = IntPtr.Zero, language = IntPtr.Zero;
        try
        {
            var folder = Environment.GetFolderPath(Environment.SpecialFolder.System);
            var path = Path.Combine(folder, "icu.dll");
            if (NativeLibrary.TryLoad(path, out common)) international = common;
            else
            {
                path = Path.Combine(folder, "icuuc.dll"); common = NativeLibrary.Load(path);
                international = NativeLibrary.Load(Path.Combine(folder, "icuin.dll"));
            }
            T Export<T>(IntPtr module, string name) where T : Delegate => Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(module, name));
            var version = new byte[4]; var unicode = new byte[4];
            Export<Version>(common, "u_getVersion")(version); Export<Version>(common, "u_getUnicodeVersion")(unicode);
            var open = Export<Open>(international, "ubrk_open"); var first = Export<Position>(international, "ubrk_first");
            var next = Export<Position>(international, "ubrk_next"); var close = Export<Close>(international, "ubrk_close");
            var getLocale = Export<Locale>(international, "ubrk_getLocaleByType");
            input = Marshal.StringToHGlobalUni(text); language = Marshal.StringToCoTaskMemUTF8(locale);
            var receipts = new JsonArray();
            int[] Boundaries(int type)
            {
                var error = 0; var iterator = open(type, language, input, text.Length, ref error);
                if (iterator == IntPtr.Zero || error > 0) throw new InvalidOperationException("System ICU ubrk_open failed: " + error);
                try
                {
                    var localeError = 0; var actualLocale = Marshal.PtrToStringUTF8(getLocale(iterator, 0, ref localeError));
                    if (localeError > 0) throw new InvalidOperationException("System ICU actual locale unavailable: " + localeError);
                    var result = new List<int>();
                    for (var p = first(iterator); p != -1; p = next(iterator))
                    {
                        if (p < 0 || p > text.Length || result.Count > text.Length || result.Count > 0 && p <= result[^1])
                            throw new InvalidOperationException("System ICU returned an invalid source boundary");
                        result.Add(p);
                    }
                    if (result.Count == 0 || result[0] != 0 || result[^1] != text.Length)
                        throw new InvalidOperationException("System ICU did not cover the complete source");
                    if (NativeLabelInterop.CaptureDiagnostics) receipts.Add(new JsonObject { ["type"] = type, ["open_status"] = error, ["actual_locale"] = actualLocale,
                        ["actual_locale_status"] = localeError, ["boundaries_utf16"] = new JsonArray(result.Select(n => JsonValue.Create(n)).ToArray()) });
                    return result.ToArray();
                }
                finally { close(iterator); }
            }
            var lines = Boundaries(2); var characters = Boundaries(0); var words = Boundaries(1);
            if (!NativeLabelInterop.CaptureDiagnostics) return new NativePathBoundaries(lines, characters, words, new JsonObject());
            return new NativePathBoundaries(lines, characters, words, new JsonObject
            {
                ["source"] = "Actual system ICU ubrk iterators over the unchanged production source",
                ["library"] = path, ["icu_version"] = string.Join(".", version), ["unicode_version"] = string.Join(".", unicode),
                ["requested_locale"] = locale, ["source_text"] = text, ["iterators"] = receipts
            });
        }
        finally
        {
            if (input != IntPtr.Zero) Marshal.FreeHGlobal(input);
            if (language != IntPtr.Zero) Marshal.FreeCoTaskMem(language);
            if (international != IntPtr.Zero && international != common) NativeLibrary.Free(international);
            if (common != IntPtr.Zero) NativeLibrary.Free(common);
        }
    }
}
