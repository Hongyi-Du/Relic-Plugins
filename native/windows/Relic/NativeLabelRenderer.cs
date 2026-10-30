using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using static Relic.NativeLabelInterop;

namespace Relic;

// This object is the renderer passed to the production layout.Draw, not an
// observer of a second layout. Its hand-written IUnknown vtable avoids relying
// on CLR/WinRT interface projection for the native DirectWrite callback ABI.
internal sealed class NativeLabelRenderer : IDisposable
{
    private static readonly Guid UnknownId = new("00000000-0000-0000-c000-000000000046");
    private static readonly Guid SnappingId = new("eaf3a2da-ecf4-4d24-b644-b34f6842024b");
    private static readonly Guid RendererId = new("ef8a8135-5cc6-45fe-8825-c5a0724eb819");
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int QueryCallback(IntPtr self, ref Guid iid, out IntPtr value);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate uint RefCallback(IntPtr self);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int SnapCallback(IntPtr self, IntPtr context, out int disabled);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int TransformCallback(IntPtr self, IntPtr context, out Matrix transform);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int DpiCallback(IntPtr self, IntPtr context, out float dpi);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int GlyphCallback(IntPtr self, IntPtr context, float x, float y, uint measuringMode, IntPtr run, IntPtr description, IntPtr effect);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int DecorationCallback(IntPtr self, IntPtr context, float x, float y, IntPtr decoration, IntPtr effect);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int InlineCallback(IntPtr self, IntPtr context, float x, float y, IntPtr inline, int sideways, int rightToLeft, IntPtr effect);

    private static readonly Delegate[] Callbacks =
    {
        new QueryCallback(QueryInterface), new RefCallback(AddRef), new RefCallback(ReleaseReference),
        new SnapCallback(Snapping), new TransformCallback(CurrentTransform), new DpiCallback(PixelsPerDip),
        new GlyphCallback(Glyph), new DecorationCallback(Decoration), new DecorationCallback(Decoration), new InlineCallback(Inline)
    };
    private static readonly IntPtr Vtable = CreateVtable();
    private readonly IntPtr context, brush;
    private readonly float pixelsPerDip;
    private readonly Matrix transform;
    private int references = 1;
    private bool disposed;
    internal IntPtr Pointer { get; private set; }
    internal JsonArray Runs { get; } = new();
    internal JsonArray InlineDraws { get; } = new();
    internal JsonArray Limitations { get; } = new();
    internal string? CallbackFailure { get; private set; }
    private readonly string? trimmingSignIdentity;
    private readonly Stack<int> inlineStack = new();

    internal NativeLabelRenderer(IntPtr context, IntPtr brush, float pixelsPerDip, Matrix transform, IntPtr trimmingSign = default)
    {
        this.context = context; this.brush = brush; this.pixelsPerDip = pixelsPerDip; this.transform = transform;
        trimmingSignIdentity = trimmingSign == IntPtr.Zero ? null : ComIdentity(trimmingSign);
        Pointer = Marshal.AllocHGlobal(2 * IntPtr.Size);
        Marshal.WriteIntPtr(Pointer, Vtable);
        Marshal.WriteIntPtr(Pointer, IntPtr.Size, GCHandle.ToIntPtr(GCHandle.Alloc(this)));
    }
    private static IntPtr CreateVtable()
    {
        var pointer = Marshal.AllocHGlobal(Callbacks.Length * IntPtr.Size);
        for (var i = 0; i < Callbacks.Length; i++) Marshal.WriteIntPtr(pointer, i * IntPtr.Size, Marshal.GetFunctionPointerForDelegate(Callbacks[i]));
        return pointer;
    }
    private static NativeLabelRenderer Owner(IntPtr self) => (NativeLabelRenderer)GCHandle.FromIntPtr(Marshal.ReadIntPtr(self, IntPtr.Size)).Target!;
    private static int QueryInterface(IntPtr self, ref Guid iid, out IntPtr value)
    {
        if (iid == UnknownId || iid == SnappingId || iid == RendererId) { value = self; AddRef(self); return 0; }
        value = IntPtr.Zero; return unchecked((int)0x80004002);
    }
    private static uint AddRef(IntPtr self) => checked((uint)Interlocked.Increment(ref Owner(self).references));
    private static uint ReleaseReference(IntPtr self)
    {
        var owner = Owner(self); var count = Interlocked.Decrement(ref owner.references);
        if (count == 0)
        {
            var handle = GCHandle.FromIntPtr(Marshal.ReadIntPtr(self, IntPtr.Size));
            owner.Pointer = IntPtr.Zero; handle.Free(); Marshal.FreeHGlobal(self);
        }
        return checked((uint)count);
    }
    private static int Snapping(IntPtr self, IntPtr context, out int disabled) { disabled = 0; return 0; }
    private static int CurrentTransform(IntPtr self, IntPtr context, out Matrix transform) { transform = Owner(self).transform; return 0; }
    private static int PixelsPerDip(IntPtr self, IntPtr context, out float dpi) { dpi = Owner(self).pixelsPerDip; return 0; }
    private static int Glyph(IntPtr self, IntPtr context, float x, float y, uint mode, IntPtr run, IntPtr description, IntPtr effect)
    {
        try { return Owner(self).DrawGlyph(x, y, mode, run, description, effect); }
        catch (Exception ex) { Owner(self).CallbackFailure = ex.ToString(); return Marshal.GetHRForException(ex); }
    }
    private static int Decoration(IntPtr self, IntPtr context, float x, float y, IntPtr decoration, IntPtr effect)
    {
        // The first production use is plain, single-line menu labels. If a caller
        // introduces decorated text it must implement its actual paint first.
        Owner(self).CallbackFailure = "underline/strikethrough rendering is not implemented by NativeLabel";
        return unchecked((int)0x80004001);
    }
    private static int Inline(IntPtr self, IntPtr context, float x, float y, IntPtr inline, int sideways, int rightToLeft, IntPtr effect)
    {
        var owner = Owner(self);
        var ordinal = owner.InlineDraws.Count;
        var record = new JsonObject
        {
            ["ordinal"] = ordinal, ["source"] = "Actual IDWriteTextRenderer.DrawInlineObject callback and IDWriteInlineObject.Draw forwarding",
            ["parent_inline_draw_ordinal"] = owner.inlineStack.Count == 0 ? null : owner.inlineStack.Peek(),
            ["origin_x"] = x, ["origin_y"] = y, ["sideways"] = sideways != 0, ["right_to_left"] = rightToLeft != 0,
            ["inline_com_identity"] = null, ["is_configured_trimming_sign"] = null,
            ["inline_metrics"] = null, ["draw_hresult"] = null, ["draw_succeeded"] = false,
            ["actual_d2d_context"] = owner.ReadActualContext(),
            ["first_glyph_run_ordinal"] = owner.Runs.Count
        };
        owner.InlineDraws.Add(record);
        try
        {
            // Metadata failures remain explicit but must not suppress a valid
            // inline object's actual paint. Never infer identity from its size.
            try
            {
                var identity = ComIdentity(inline); record["inline_com_identity"] = identity;
                record["is_configured_trimming_sign"] = owner.trimmingSignIdentity != null && identity == owner.trimmingSignIdentity;
                Check(Method<GetInlineMetrics>(inline, 4)(inline, out var metrics));
                record["inline_metrics"] = new JsonObject { ["width"] = metrics.Width, ["height"] = metrics.Height,
                    ["baseline"] = metrics.Baseline, ["supports_sideways"] = metrics.SupportsSideways != 0,
                    ["quantity"] = "IDWriteInlineObject.GetMetrics layout extent; not glyph ink" };
            }
            catch (Exception ex)
            {
                record["metadata_failure"] = ex.ToString();
                owner.Limitations.Add("Actual inline-object identity/metrics are incomplete: " + ex.Message);
            }
            owner.inlineStack.Push(ordinal);
            var hr = Method<DrawInline>(inline, 3)(inline, context, self, x, y, sideways, rightToLeft, effect);
            record["draw_hresult"] = hr; record["draw_succeeded"] = hr >= 0;
            if (hr < 0) owner.CallbackFailure ??= "Actual IDWriteInlineObject.Draw failed: 0x" + hr.ToString("x8");
            return hr;
        }
        catch (Exception ex)
        {
            owner.CallbackFailure = ex.ToString(); var hr = Marshal.GetHRForException(ex);
            record["draw_hresult"] = hr; record["draw_failure"] = ex.ToString(); return hr;
        }
        finally
        {
            if (owner.inlineStack.Count > 0 && owner.inlineStack.Peek() == ordinal) owner.inlineStack.Pop();
            record["glyph_run_count"] = owner.Runs.Count - record["first_glyph_run_ordinal"]!.GetValue<int>();
        }
    }
    private int DrawGlyph(float x, float y, uint mode, IntPtr originalRun, IntPtr descriptionPointer, IntPtr effect)
    {
        if (effect != IntPtr.Zero) throw new NotSupportedException("NativeLabel does not paint custom drawing effects");
        var run = Marshal.PtrToStructure<GlyphRun>(originalRun);
        if (run.IsSideways != 0) throw new NotSupportedException("NativeLabel only implements horizontal, non-sideways text");
        var glyphs = new JsonArray(); var advances = new JsonArray(); var offsets = new JsonArray();
        for (uint i = 0; i < run.GlyphCount; i++)
        {
            glyphs.Add((ushort)Marshal.ReadInt16(run.GlyphIndices, checked((int)i * 2)));
            // Null advances/offsets have defined DirectWrite defaults. Keep them
            // null instead of manufacturing measured positions for that case.
            if (run.GlyphAdvances != IntPtr.Zero) advances.Add(Marshal.PtrToStructure<float>(run.GlyphAdvances + checked((int)i * sizeof(float))));
            if (run.GlyphOffsets != IntPtr.Zero)
            {
                var offset = Marshal.PtrToStructure<GlyphOffset>(run.GlyphOffsets + checked((int)i * Marshal.SizeOf<GlyphOffset>()));
                offsets.Add(new JsonObject { ["advance"] = offset.AdvanceOffset, ["ascender"] = offset.AscenderOffset });
            }
        }
        JsonObject? description = null;
        if (descriptionPointer != IntPtr.Zero)
        {
            var d = Marshal.PtrToStructure<GlyphDescription>(descriptionPointer); var clusters = new JsonArray();
            if (d.ClusterMap != IntPtr.Zero)
                for (uint i = 0; i < d.TextLength; i++) clusters.Add((ushort)Marshal.ReadInt16(d.ClusterMap, checked((int)i * 2)));
            description = new JsonObject { ["text"] = Marshal.PtrToStringUni(d.Text, checked((int)d.TextLength)),
                ["text_position_utf16"] = d.TextPosition, ["text_length_utf16"] = d.TextLength,
                ["locale"] = Marshal.PtrToStringUni(d.LocaleName), ["cluster_map"] = d.ClusterMap == IntPtr.Zero ? null : clusters };
        }
        JsonObject face;
        try { face = FaceEvidence(run.FontFace, Limitations); }
        catch (Exception ex)
        {
            // Unsupported metadata must fail capture coverage, not replace or
            // suppress the valid original glyph run's production paint.
            Limitations.Add("actual font-face metadata is incomplete: " + ex.Message);
            face = new JsonObject { ["source"] = "DWRITE_GLYPH_RUN.fontFace", ["measurement_failure"] = ex.ToString(),
                ["family_names"] = null, ["face_names"] = null, ["postscript_names"] = null,
                ["axes"] = null, ["files"] = null, ["metrics_design_units"] = null, ["color_font"] = null };
        }
        if (face["color_font"]?.GetValue<bool>() != false)
            Limitations.Add("color glyph layer translation is not implemented; this run only submits the base outline and is not complete color-glyph evidence");
        var baseline = new PointF(x, y);
        var actualContext = ReadActualContext();
        var boundsHr = Method<GlyphBounds>(context, 72)(context, baseline, originalRun, mode, out var inkBounds);
        if (boundsHr < 0) Limitations.Add("GetGlyphRunWorldBounds failed: 0x" + boundsHr.ToString("x8"));
        // This exact native pointer received from layout.Draw is what is painted.
        // No copied/reconstructed run, substitute face, or capture-only layout.
        Method<NativeLabelInterop.DrawGlyph>(context, 29)(context, baseline, originalRun, brush, mode);
        Runs.Add(new JsonObject { ["ordinal"] = Runs.Count, ["submitted_to_d2d"] = true,
            ["source"] = "IDWriteTextLayout.Draw -> IDWriteTextRenderer.DrawGlyphRun -> ID2D1RenderTarget.DrawGlyphRun",
            ["baseline_x"] = x, ["baseline_y"] = y, ["em_size"] = run.FontEmSize,
            ["bidi_level"] = run.BidiLevel, ["sideways"] = false, ["measuring_mode"] = mode,
            ["from_inline_object"] = inlineStack.Count > 0,
            ["inline_draw_ordinal"] = inlineStack.Count == 0 ? null : inlineStack.Peek(), ["description"] = description,
            ["glyph_indices"] = glyphs, ["glyph_advances"] = run.GlyphAdvances == IntPtr.Zero ? null : advances,
            ["glyph_offsets"] = run.GlyphOffsets == IntPtr.Zero ? null : offsets,
            ["face"] = face, ["ink_bounds_world_dip"] = boundsHr >= 0 ? Box(inkBounds) : null,
            ["actual_d2d_context"] = actualContext,
            ["ink_bounds_quantity"] = "D2D GetGlyphRunWorldBounds; not DOM Range or text selection bounds" });
        return 0;
    }
    private JsonObject ReadActualContext()
    {
        var result = new JsonObject
        {
            ["source"] = "Actual ID2D1DeviceContext getters at the production draw callback",
            ["world_transform"] = null, ["dpi"] = null, ["unit_mode"] = null
        };
        try
        {
            // d2d1.h: RenderTarget slots 31/52 are void with explicit output
            // pointers. d2d1_1.h: DeviceContext slot 81 returns a scalar enum.
            Method<GetWorldTransform>(context, 31)(context, out var world);
            Method<GetContextDpi>(context, 52)(context, out var x, out var y);
            result["world_transform"] = NativeLabelInterop.Transform(world);
            result["dpi"] = new JsonObject { ["x"] = x, ["y"] = y };
            result["unit_mode"] = Method<GetUInt>(context, 81)(context);
        }
        catch (Exception ex)
        {
            result["measurement_failure"] = ex.ToString();
            Limitations.Add("Actual D2D context geometry is incomplete: " + ex.Message);
        }
        return result;
    }
    public void Dispose()
    {
        if (disposed) return; disposed = true;
        if (Pointer != IntPtr.Zero) ReleaseReference(Pointer);
    }
}
