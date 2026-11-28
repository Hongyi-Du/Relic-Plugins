using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using static Relic.NativeLabelInterop;

namespace Relic;

// Production native geometry operation, not a reference-derived capture path.
// ID2D1Geometry::CombineWithGeometry(EXCLUDE) computes R - Translate(R, dx, dy),
// including arbitrarily narrow corner intersections. No guessed left strip.
internal static class NativeInsetShadowPath
{
    internal const float FlatteningTolerance = .01f;
    [StructLayout(LayoutKind.Sequential)] private struct Arc
    { internal PointF Point, Size; internal float Rotation; internal uint Sweep, ArcSize; }
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate void FactoryGetter(IntPtr self, out IntPtr factory);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int CreateInterface(IntPtr self, out IntPtr value);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate void BeginFigure(IntPtr self, PointF start, uint begin);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate void AddLine(IntPtr self, PointF point);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate void AddArc(IntPtr self, ref Arc arc);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate void EndFigure(IntPtr self, uint end);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int Close(IntPtr self);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int Combine(IntPtr self, IntPtr input, uint mode, ref Matrix transform, float tolerance, IntPtr sink);

#if WINDOWS
    internal static (IReadOnlyList<NativeInsetCommand> Commands, JsonObject Receipt) Exclude(NativeInsetContour contour, float dx, float dy)
    {
        if (!float.IsFinite(dx) || !float.IsFinite(dy)) throw new ArgumentOutOfRangeException(nameof(dx));
        IntPtr factory = IntPtr.Zero, geometry = IntPtr.Zero, sink = IntPtr.Zero;
        var record = new JsonObject { ["source"] = "Production ID2D1Geometry.CombineWithGeometry EXCLUDE into native geometry sink",
            ["operation"] = "exclude-translated-self", ["offset_x"] = dx, ["offset_y"] = dy,
            ["flattening_tolerance"] = FlatteningTolerance, ["input_commands"] = Commands(contour.Commands),
            ["padding_edge"] = new JsonArray(contour.X, contour.Y, contour.Width, contour.Height),
            ["padding_radii"] = new JsonArray(contour.Radii.Select(v => (JsonNode?)JsonValue.Create(v)).ToArray()) };
        void Checked(string key, int hr) { record[key] = hr; Check(hr); }
        try
        {
            Method<FactoryGetter>(NativeLabelDevice.Shared.Device, 3)(NativeLabelDevice.Shared.Device, out factory);
            if (factory == IntPtr.Zero) throw new InvalidOperationException("Actual native device has no geometry factory");
            Checked("create_path_hresult", Method<CreateInterface>(factory, 10)(factory, out geometry));
            Checked("open_hresult", Method<CreateInterface>(geometry, 17)(geometry, out sink));
            Method<SetEnum>(sink, 3)(sink, 0); // D2D1_FILL_MODE_ALTERNATE.
            foreach (var command in contour.Commands)
            {
                var v = command.Values;
                switch (command.Kind)
                {
                    case "M": Method<BeginFigure>(sink, 5)(sink, new PointF((float)v[0], (float)v[1]), 0); break;
                    case "L": Method<AddLine>(sink, 10)(sink, new PointF((float)v[0], (float)v[1])); break;
                    case "A":
                        var arc = new Arc { Point = new PointF((float)v[0], (float)v[1]), Size = new PointF((float)v[2], (float)v[3]), Sweep = 1, ArcSize = 0 };
                        Method<AddArc>(sink, 14)(sink, ref arc); break; // ID2D1GeometrySink::AddArc.
                    case "Z": Method<EndFigure>(sink, 8)(sink, 1); break;
                    default: throw new InvalidOperationException("Unknown production rounded path command");
                }
            }
            Checked("close_hresult", Method<Close>(sink, 9)(sink));
            using var output = new NativeInsetShadowSink();
            var translation = new Matrix { M11 = 1, M22 = 1, Dx = dx, Dy = dy };
            // ID2D1Geometry slot 11; EXCLUDE=3. Output belongs to this operation.
            // https://learn.microsoft.com/en-us/windows/win32/api/d2d1/nf-d2d1-id2d1geometry-combinewithgeometry(id2d1geometry_d2d1_combine_mode_constd2d1_matrix_3x2_f_float_id2d1simplifiedgeometrysink)
            Checked("combine_hresult", Method<Combine>(geometry, 11)(geometry, geometry, 3, ref translation, FlatteningTolerance, output.Pointer));
            output.Finish();
            record["output_fill_mode"] = output.FillMode; record["output_commands"] = Commands(output.Commands);
            record["failure"] = null;
            return (output.Commands.ToArray(), record);
        }
        finally { Release(ref sink); Release(ref geometry); Release(ref factory); }
    }
#endif

    internal static JsonArray Commands(IEnumerable<NativeInsetCommand> commands)
    {
        var result = new JsonArray();
        foreach (var command in commands) { var values = new JsonArray(); foreach (var value in command.Values) values.Add(value);
            result.Add(new JsonObject { ["kind"] = command.Kind, ["values"] = values }); }
        return result;
    }
}

// Exact ID2D1SimplifiedGeometrySink ABI. The native combine operation writes
// directly into this production path builder. Callbacks never throw across COM.
internal sealed class NativeInsetShadowSink : IDisposable
{
    private static readonly Guid Unknown = new("00000000-0000-0000-c000-000000000046");
    private static readonly Guid Sink = new("2cd9069e-12e2-11dc-9fed-001143a055f9");
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int Query(IntPtr self, ref Guid iid, out IntPtr result);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate uint Ref(IntPtr self);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate void EnumCall(IntPtr self, uint value);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate void Begin(IntPtr self, PointF point, uint begin);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate void ArrayCall(IntPtr self, IntPtr values, uint count);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] internal delegate int CloseCall(IntPtr self);
    private static readonly Delegate[] Callbacks = [new Query(QueryInterface), new Ref(AddRef), new Ref(ReleaseRef),
        new EnumCall(SetFill), new EnumCall(SetFlags), new Begin(Start), new ArrayCall(Lines), new ArrayCall(Beziers), new EnumCall(End), new CloseCall(Close)];
    private static readonly IntPtr Vtable = CreateVtable();
    private int references = 1; private bool inFigure, disposed; private Exception? failure;
    // The production output path starts in the D2D/XAML alternate fill mode;
    // a native SetFillMode callback changes this exact builder's current mode.
    internal uint FillMode { get; private set; }
    internal List<NativeInsetCommand> Commands { get; } = [];
    internal IntPtr Pointer { get; private set; }
    internal NativeInsetShadowSink()
    {
        Pointer = Marshal.AllocHGlobal(2 * IntPtr.Size); Marshal.WriteIntPtr(Pointer, Vtable);
        Marshal.WriteIntPtr(Pointer, IntPtr.Size, GCHandle.ToIntPtr(GCHandle.Alloc(this)));
    }
    private static IntPtr CreateVtable()
    {
        var result = Marshal.AllocHGlobal(Callbacks.Length * IntPtr.Size);
        for (var i = 0; i < Callbacks.Length; i++) Marshal.WriteIntPtr(result, i * IntPtr.Size, Marshal.GetFunctionPointerForDelegate(Callbacks[i]));
        return result;
    }
    private static NativeInsetShadowSink Owner(IntPtr self) => (NativeInsetShadowSink)GCHandle.FromIntPtr(Marshal.ReadIntPtr(self, IntPtr.Size)).Target!;
    private static int QueryInterface(IntPtr self, ref Guid iid, out IntPtr result)
    {
        if (iid == Unknown || iid == Sink) { result = self; AddRef(self); return 0; }
        result = IntPtr.Zero; return unchecked((int)0x80004002);
    }
    private static uint AddRef(IntPtr self) => checked((uint)Interlocked.Increment(ref Owner(self).references));
    private static uint ReleaseRef(IntPtr self)
    {
        var owner = Owner(self); var count = Interlocked.Decrement(ref owner.references);
        if (count == 0) { GCHandle.FromIntPtr(Marshal.ReadIntPtr(self, IntPtr.Size)).Free(); Marshal.FreeHGlobal(self); owner.Pointer = IntPtr.Zero; }
        return checked((uint)count);
    }
    private void Guard(Action action) { if (failure != null) return; try { action(); } catch (Exception e) { failure = e; } }
    private static void SetFill(IntPtr self, uint value) => Owner(self).Guard(() =>
    { if (value > 1) throw new InvalidOperationException("Unknown native fill mode"); Owner(self).FillMode = value; });
    private static void SetFlags(IntPtr self, uint value) => Owner(self).Guard(() =>
    { if (value != 0) throw new NotSupportedException("Unexpected native path segment flags"); });
    private static void Start(IntPtr self, PointF p, uint begin) => Owner(self).Guard(() =>
    {
        var o = Owner(self); if (o.inFigure || begin != 0) throw new InvalidOperationException("Invalid native filled figure");
        o.inFigure = true; o.Add("M", p.X, p.Y);
    });
    private static void Lines(IntPtr self, IntPtr values, uint count) => Owner(self).Guard(() =>
    {
        var o = Owner(self); if (!o.inFigure) throw new InvalidOperationException("Native lines without figure");
        for (var i = 0; i < count; i++) { var p = Marshal.PtrToStructure<PointF>(values + checked((int)i * 8)); o.Add("L", p.X, p.Y); }
    });
    private static void Beziers(IntPtr self, IntPtr values, uint count) => Owner(self).Guard(() =>
    {
        var o = Owner(self); if (!o.inFigure) throw new InvalidOperationException("Native curves without figure");
        for (var i = 0; i < count; i++) { var p = values + checked((int)i * 24);
            var a = Marshal.PtrToStructure<PointF>(p); var b = Marshal.PtrToStructure<PointF>(p + 8); var c = Marshal.PtrToStructure<PointF>(p + 16);
            o.Add("C", a.X, a.Y, b.X, b.Y, c.X, c.Y); }
    });
    private static void End(IntPtr self, uint end) => Owner(self).Guard(() =>
    { var o = Owner(self); if (!o.inFigure || end != 1) throw new InvalidOperationException("Inset shadow output must be closed"); o.Add("Z"); o.inFigure = false; });
    private static int Close(IntPtr self) { try { Owner(self).Finish(); return 0; } catch (Exception e) { return Marshal.GetHRForException(e); } }
    private void Add(string kind, params double[] values)
    { if (values.Any(v => !double.IsFinite(v))) throw new InvalidOperationException("Native geometry contains nonfinite coordinates"); Commands.Add(new(kind, values)); }
    internal void Finish() { if (failure != null) throw new InvalidOperationException("Native shadow geometry sink failed", failure);
        if (inFigure) throw new InvalidOperationException("Native geometry ended in an open figure"); }
    public void Dispose() { if (disposed) return; disposed = true; ReleaseRef(Pointer); }
}
