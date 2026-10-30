using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json.Nodes;

namespace Relic;

// Raw ABI declarations are deliberately local to the production text renderer.
// Slots/structs come from Windows SDK 10.0.26100 dwrite*.h/d2d1*.h and the
// Microsoft.WindowsAppSDK 1.6 microsoft.ui.xaml.media.dxinterop.h header.
// No second text layout is created for capture or font prediction.
internal static class NativeLabelInterop
{
    internal static readonly Guid SurfaceWithD2D = new("cb833102-d5d1-448b-a31a-52a9509f24e6");
    internal static readonly Guid DeviceContext = new("e8f7fe7a-191c-466d-ad95-975678bda998");
    internal static readonly Guid FontFace3 = new("d37d7598-09be-4222-a236-2081341cc1f2");
    internal static readonly Guid FontFace5 = new("98eff3a5-b667-479a-b145-e2fa5b9fdc29");
    internal static readonly Guid FontFace2 = new("d8b768ff-64bc-4e66-982b-ec8e87f693f7");
    internal static readonly Guid LocalFontFileLoader = new("b2d9f3ec-c9fe-4a11-a2ec-d86208f7c0a2");

    internal static T Method<T>(IntPtr instance, int slot) where T : Delegate =>
        Marshal.GetDelegateForFunctionPointer<T>(Marshal.ReadIntPtr(Marshal.ReadIntPtr(instance), checked(slot * IntPtr.Size)));
    internal static void Check(int hr) { if (hr < 0) Marshal.ThrowExceptionForHR(hr); }
    internal static IntPtr Query(IntPtr instance, Guid iid)
    { var hr = Marshal.QueryInterface(instance, ref iid, out var result); Check(hr); return result; }
    internal static IntPtr TryQuery(IntPtr instance, Guid iid) => Marshal.QueryInterface(instance, ref iid, out var result) >= 0 ? result : IntPtr.Zero;
    internal static void Release(ref IntPtr instance) { if (instance != IntPtr.Zero) { Marshal.Release(instance); instance = IntPtr.Zero; } }

    [DllImport("dwrite.dll", ExactSpelling = true)]
    internal static extern int DWriteCreateFactory(uint factoryType, ref Guid iid, out IntPtr factory);
    [DllImport("d3d11.dll", ExactSpelling = true)]
    internal static extern int D3D11CreateDevice(IntPtr adapter, uint driverType, IntPtr software, uint flags,
        IntPtr featureLevels, uint featureLevelCount, uint sdkVersion, out IntPtr device, out uint featureLevel, out IntPtr immediateContext);
    [DllImport("d2d1.dll", ExactSpelling = true)]
    internal static extern int D2D1CreateDevice(IntPtr dxgiDevice, IntPtr creationProperties, out IntPtr device);

    [StructLayout(LayoutKind.Sequential)] internal struct Point { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] internal struct Rect { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] internal struct PointF { public float X, Y; public PointF(float x, float y) { X = x; Y = y; } }
    [StructLayout(LayoutKind.Sequential)] internal struct RectF { public float Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] internal struct Matrix { public float M11, M12, M21, M22, Dx, Dy; }
    [StructLayout(LayoutKind.Sequential)] internal struct ColorF { public float R, G, B, A; }
    [StructLayout(LayoutKind.Sequential)] internal struct TextMetrics
    { public float Left, Top, Width, WidthIncludingTrailingWhitespace, Height, LayoutWidth, LayoutHeight; public uint MaxBidiReorderingDepth, LineCount; }
    [StructLayout(LayoutKind.Sequential)] internal struct LineMetrics
    { public uint Length, TrailingWhitespaceLength, NewlineLength; public float Height, Baseline; public int IsTrimmed; }
    [StructLayout(LayoutKind.Sequential)] internal struct HitTestMetrics
    { public uint TextPosition, Length; public float Left, Top, Width, Height; public uint BidiLevel; public int IsText, IsTrimmed; }
    [StructLayout(LayoutKind.Sequential)] internal struct FontMetrics
    {
        public ushort DesignUnitsPerEm, Ascent, Descent;
        public short LineGap;
        public ushort CapHeight, XHeight;
        public short UnderlinePosition;
        public ushort UnderlineThickness;
        public short StrikethroughPosition;
        public ushort StrikethroughThickness;
    }
    [StructLayout(LayoutKind.Sequential)] internal struct GlyphRun
    { public IntPtr FontFace; public float FontEmSize; public uint GlyphCount; public IntPtr GlyphIndices, GlyphAdvances, GlyphOffsets; public int IsSideways; public uint BidiLevel; }
    [StructLayout(LayoutKind.Sequential)] internal struct GlyphOffset { public float AdvanceOffset, AscenderOffset; }
    [StructLayout(LayoutKind.Sequential)] internal struct GlyphDescription
    { public IntPtr LocaleName, Text; public uint TextLength; public IntPtr ClusterMap; public uint TextPosition; }
    [StructLayout(LayoutKind.Sequential)] internal struct FontAxis { public uint Tag; public float Value; }
    [StructLayout(LayoutKind.Sequential)] internal struct Trimming { public uint Granularity, Delimiter, DelimiterCount; }

    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int InterfaceResult(IntPtr self, out IntPtr result);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate uint GetUInt(IntPtr self);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int GetBool(IntPtr self);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int SetUInt(IntPtr self, uint value);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int SetFloat(IntPtr self, float value);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int SetDevice(IntPtr self, IntPtr device);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int BeginSurface(IntPtr self, ref Rect update, ref Guid iid, out IntPtr context, out Point offset);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int EndSurface(IntPtr self);
    [UnmanagedFunctionPointer(CallingConvention.StdCall, CharSet = CharSet.Unicode)] internal delegate int CreateFormat(IntPtr self,
        [MarshalAs(UnmanagedType.LPWStr)] string family, IntPtr collection, uint weight, uint style, uint stretch, float size,
        [MarshalAs(UnmanagedType.LPWStr)] string locale, out IntPtr format);
    [UnmanagedFunctionPointer(CallingConvention.StdCall, CharSet = CharSet.Unicode)] internal delegate int CreateLayout(IntPtr self,
        [MarshalAs(UnmanagedType.LPWStr)] string text, uint length, IntPtr format, float width, float height, out IntPtr layout);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int CreateEllipsis(IntPtr self, IntPtr format, out IntPtr sign);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int SetTrimming(IntPtr self, ref Trimming options, IntPtr sign);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int SetLineSpacing(IntPtr self, uint method, float height, float baseline);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int GetTextMetrics(IntPtr self, out TextMetrics metrics);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int GetArray(IntPtr self, IntPtr items, uint capacity, out uint count);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int GetAxes(IntPtr self, IntPtr items, uint count);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int HitTestRange(IntPtr self, uint start, uint length, float x, float y, IntPtr items, uint capacity, out uint count);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int DrawLayout(IntPtr self, IntPtr drawingContext, IntPtr renderer, float x, float y);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int DrawInline(IntPtr self, IntPtr context, IntPtr renderer, float x, float y, int sideways, int rightToLeft, IntPtr effect);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int CreateBrush(IntPtr self, ref ColorF color, IntPtr properties, out IntPtr brush);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate void SetTransform(IntPtr self, ref Matrix matrix);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate void SetDpi(IntPtr self, float x, float y);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate void SetEnum(IntPtr self, uint value);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate void Clear(IntPtr self, ref ColorF color);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate void PushClip(IntPtr self, ref RectF clip, uint antialias);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate void VoidCall(IntPtr self);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate void DrawGlyph(IntPtr self, PointF baseline, IntPtr run, IntPtr brush, uint mode);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int GlyphBounds(IntPtr self, PointF baseline, IntPtr run, uint mode, out RectF bounds);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate void GetFontMetrics(IntPtr self, out FontMetrics metrics);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int GetFontFiles(IntPtr self, ref uint count, IntPtr files);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int GetReferenceKey(IntPtr self, out IntPtr key, out uint length);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int GetNameLength(IntPtr self, uint index, out uint length);
    [UnmanagedFunctionPointer(CallingConvention.StdCall, CharSet = CharSet.Unicode)] internal delegate int GetName(IntPtr self, uint index, StringBuilder name, uint size);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int GetInfoNames(IntPtr self, uint id, out IntPtr names, out int exists);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int GetPathLength(IntPtr self, IntPtr key, uint keySize, out uint length);
    [UnmanagedFunctionPointer(CallingConvention.StdCall, CharSet = CharSet.Unicode)] internal delegate int GetPath(IntPtr self, IntPtr key, uint keySize, StringBuilder path, uint size);

    internal static JsonObject Box(RectF value) => new() { ["left"] = value.Left, ["top"] = value.Top, ["right"] = value.Right, ["bottom"] = value.Bottom };
    internal static JsonObject Transform(Matrix value) => new() { ["m11"] = value.M11, ["m12"] = value.M12, ["m21"] = value.M21, ["m22"] = value.M22, ["dx"] = value.Dx, ["dy"] = value.Dy };
    internal static JsonArray ReadNames(IntPtr strings)
    {
        var result = new JsonArray();
        try
        {
            var count = Method<GetUInt>(strings, 3)(strings);
            for (uint i = 0; i < count; i++)
            {
                Check(Method<GetNameLength>(strings, 5)(strings, i, out var localeLength));
                Check(Method<GetNameLength>(strings, 7)(strings, i, out var textLength));
                var locale = new StringBuilder(checked((int)localeLength + 1)); var text = new StringBuilder(checked((int)textLength + 1));
                Check(Method<GetName>(strings, 6)(strings, i, locale, localeLength + 1));
                Check(Method<GetName>(strings, 8)(strings, i, text, textLength + 1));
                result.Add(new JsonObject { ["locale"] = locale.ToString(), ["value"] = text.ToString() });
            }
            return result;
        }
        finally { Release(ref strings); }
    }

    internal static JsonObject FaceEvidence(IntPtr face, JsonArray limitations)
    {
        Method<GetFontMetrics>(face, 8)(face, out var m);
        var result = new JsonObject
        {
            ["source"] = "DWRITE_GLYPH_RUN.fontFace passed to the actual D2D DrawGlyphRun",
            ["face_index"] = Method<GetUInt>(face, 5)(face), ["simulations"] = Method<GetUInt>(face, 6)(face),
            ["metrics_design_units"] = new JsonObject { ["units_per_em"] = m.DesignUnitsPerEm, ["ascent"] = m.Ascent,
                ["descent"] = m.Descent, ["line_gap"] = m.LineGap, ["cap_height"] = m.CapHeight, ["x_height"] = m.XHeight,
                ["underline_position"] = m.UnderlinePosition, ["underline_thickness"] = m.UnderlineThickness,
                ["strikethrough_position"] = m.StrikethroughPosition, ["strikethrough_thickness"] = m.StrikethroughThickness },
            ["family_names"] = null, ["face_names"] = null, ["postscript_names"] = null,
            ["axes"] = null, ["color_font"] = null, ["files"] = null
        };
        var face3 = TryQuery(face, FontFace3);
        try
        {
            if (face3 != IntPtr.Zero)
            {
                Check(Method<InterfaceResult>(face3, 40)(face3, out var families)); result["family_names"] = ReadNames(families);
                Check(Method<InterfaceResult>(face3, 41)(face3, out var names)); result["face_names"] = ReadNames(names);
                Check(Method<GetInfoNames>(face3, 42)(face3, 17, out var postscript, out var exists));
                if (exists != 0) result["postscript_names"] = ReadNames(postscript); else Release(ref postscript);
                result["weight"] = Method<GetUInt>(face3, 37)(face3);
                result["stretch"] = Method<GetUInt>(face3, 38)(face3);
                result["style"] = Method<GetUInt>(face3, 39)(face3);
            }
            else limitations.Add("actual face has no IDWriteFontFace3; family/face/PostScript names are unmeasured");
        }
        finally { Release(ref face3); }
        var face5 = TryQuery(face, FontFace5);
        try
        {
            if (face5 != IntPtr.Zero)
            {
                var count = Method<GetUInt>(face5, 53)(face5); var axes = new JsonArray();
                var buffer = Marshal.AllocHGlobal(checked((int)count * Marshal.SizeOf<FontAxis>()));
                try
                {
                    Check(Method<GetAxes>(face5, 54)(face5, buffer, count));
                    for (uint i = 0; i < count; i++)
                    {
                        var axis = Marshal.PtrToStructure<FontAxis>(buffer + checked((int)i * Marshal.SizeOf<FontAxis>()));
                        var tag = new string(new[] { (char)(axis.Tag & 255), (char)((axis.Tag >> 8) & 255), (char)((axis.Tag >> 16) & 255), (char)((axis.Tag >> 24) & 255) });
                        axes.Add(new JsonObject { ["tag"] = tag, ["value"] = axis.Value });
                    }
                    result["axes"] = axes; result["has_variations"] = Method<GetBool>(face5, 55)(face5) != 0;
                }
                finally { Marshal.FreeHGlobal(buffer); }
            }
            else limitations.Add("actual face has no IDWriteFontFace5; variation axes are unmeasured");
        }
        finally { Release(ref face5); }
        var face2 = TryQuery(face, FontFace2);
        try { if (face2 != IntPtr.Zero) result["color_font"] = Method<GetBool>(face2, 30)(face2) != 0; }
        finally { Release(ref face2); }
        uint fileCount = 0; Check(Method<GetFontFiles>(face, 4)(face, ref fileCount, IntPtr.Zero));
        var pointers = Marshal.AllocHGlobal(checked((int)fileCount * IntPtr.Size)); var files = new JsonArray();
        var returnedFiles = new List<IntPtr>();
        try
        {
            Check(Method<GetFontFiles>(face, 4)(face, ref fileCount, pointers));
            for (uint i = 0; i < fileCount; i++) returnedFiles.Add(Marshal.ReadIntPtr(pointers, checked((int)i * IntPtr.Size)));
            for (uint i = 0; i < fileCount; i++)
            {
                var file = Marshal.ReadIntPtr(pointers, checked((int)i * IntPtr.Size)); IntPtr loader = IntPtr.Zero, local = IntPtr.Zero;
                try
                {
                    Check(Method<GetReferenceKey>(file, 3)(file, out var key, out var keySize));
                    var bytes = new byte[checked((int)keySize)]; Marshal.Copy(key, bytes, 0, bytes.Length);
                    Check(Method<InterfaceResult>(file, 4)(file, out loader));
                    var item = new JsonObject { ["reference_key_base64"] = Convert.ToBase64String(bytes), ["loader_process_identity"] = loader.ToString("x"), ["local_path"] = null };
                    local = TryQuery(loader, LocalFontFileLoader);
                    if (local != IntPtr.Zero)
                    {
                        Check(Method<GetPathLength>(local, 4)(local, key, keySize, out var length)); var path = new StringBuilder(checked((int)length + 1));
                        Check(Method<GetPath>(local, 5)(local, key, keySize, path, length + 1)); item["local_path"] = path.ToString();
                    }
                    files.Add(item);
                }
                finally { Release(ref local); Release(ref loader); }
            }
            result["files"] = files;
        }
        finally
        {
            foreach (var returned in returnedFiles) if (returned != IntPtr.Zero) Marshal.Release(returned);
            Marshal.FreeHGlobal(pointers);
        }
        return result;
    }
}

internal sealed class NativeLabelDevice
{
    internal static NativeLabelDevice Shared { get; } = new();
    internal IntPtr WriteFactory { get; }
    internal IntPtr Device { get; }
    internal string Driver { get; }
    private NativeLabelDevice()
    {
        var factoryId = new Guid("b859ee5a-d838-4b5b-a2e8-1adc7d93db48");
        NativeLabelInterop.Check(NativeLabelInterop.DWriteCreateFactory(0, ref factoryId, out var factory));
        IntPtr d3d = IntPtr.Zero, context = IntPtr.Zero, dxgi = IntPtr.Zero, d2d = IntPtr.Zero;
        try
        {
            var hr = NativeLabelInterop.D3D11CreateDevice(IntPtr.Zero, 1, IntPtr.Zero, 0x20, IntPtr.Zero, 0, 7, out d3d, out _, out context);
            Driver = "hardware";
            if (hr < 0)
            {
                NativeLabelInterop.Release(ref context); NativeLabelInterop.Release(ref d3d);
                hr = NativeLabelInterop.D3D11CreateDevice(IntPtr.Zero, 5, IntPtr.Zero, 0x20, IntPtr.Zero, 0, 7, out d3d, out _, out context); Driver = "WARP";
            }
            NativeLabelInterop.Check(hr);
            dxgi = NativeLabelInterop.Query(d3d, new Guid("54ec77fa-1377-44e6-8c32-88fd5f44c84c"));
            NativeLabelInterop.Check(NativeLabelInterop.D2D1CreateDevice(dxgi, IntPtr.Zero, out d2d));
            WriteFactory = factory; Device = d2d;
        }
        catch { NativeLabelInterop.Release(ref factory); NativeLabelInterop.Release(ref d2d); throw; }
        finally { NativeLabelInterop.Release(ref dxgi); NativeLabelInterop.Release(ref context); NativeLabelInterop.Release(ref d3d); }
        // The shared native factories/devices intentionally live for the process.
        // Per-label layouts, brushes, contexts and surface references are released.
    }
}
