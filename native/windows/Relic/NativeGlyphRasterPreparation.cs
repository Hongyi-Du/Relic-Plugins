using System.Runtime.InteropServices;
using static Relic.NativeLabelInterop;

namespace Relic;

// IDWriteFactory::CreateGlyphRunAnalysis retains rasterized glyphs in the font
// cache. WinUI DWriteFontAndScriptServices and NativeWriteFactory both request
// DWRITE_FACTORY_TYPE_SHARED from dwrite.dll. This warms that CPU cache, not
// WinUI's private texture atlas. The final pixels still come from TextBlock.
// https://learn.microsoft.com/windows/win32/api/dwrite/nf-dwrite-idwritefactory-createglyphrunanalysis
internal static class NativeGlyphRasterPreparation
{
    internal sealed record Request(string Text, string Families, string Locale, float Size,
        uint Weight, uint Style, uint Stretch, float Scale, bool RightToLeft);

    internal sealed class Prepared : IDisposable
    {
        private readonly Queue<IntPtr> analyses = [];
        internal int Glyphs { get; set; }
        internal void Retain(IntPtr analysis)
        {
            analyses.Enqueue(analysis);
            // Lifetime is a mounted label, never an unbounded text-keyed cache.
            // Pathological mixed-font names cannot retain unlimited analyses.
            if (analyses.Count > 16) { var oldest = analyses.Dequeue(); Release(ref oldest); }
        }
        public void Dispose()
        { while (analyses.TryDequeue(out var analysis)) Release(ref analysis); }
    }

    private static readonly Guid Factory2Id = new("0439fc60-ca44-4994-8dee-3a9af7b732ec");
    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    private delegate int RecommendedMode(IntPtr self, float size, float dpiX, float dpiY,
        IntPtr transform, int sideways, uint threshold, uint measuring, IntPtr parameters,
        out uint rendering, out uint gridFit);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    private delegate int CreateAnalysis(IntPtr self, IntPtr run, ref Matrix transform,
        uint rendering, uint measuring, uint gridFit, uint antialias, float x, float y, out IntPtr analysis);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    private delegate int TextureBounds(IntPtr self, uint type, out Rect bounds);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    private delegate int AlphaTexture(IntPtr self, uint type, ref Rect bounds, IntPtr bytes, uint count);

    internal static Prepared Prepare(Request request, CancellationToken cancellation)
    {
        using var timing = PerformanceTrace.Measure("glyph.prepare.worker");
        var prepared = new Prepared();
        IntPtr format = IntPtr.Zero, layout = IntPtr.Zero, factory2 = IntPtr.Zero, parameters = IntPtr.Zero;
        try
        {
            cancellation.ThrowIfCancellationRequested();
            if (request.Text.Length == 0) return prepared;
            var factory = NativeWriteFactory.Shared;
            var family = request.Families.Split(',')[0].Trim().Trim('"');
            Check(Method<CreateFormat>(factory, 15)(factory, family, IntPtr.Zero, request.Weight,
                request.Style, request.Stretch, request.Size, request.Locale, out format));
            Check(Method<SetUInt>(format, 5)(format, 1)); // No wrap; retain real shaping/fallback.
            Check(Method<SetUInt>(format, 6)(format, request.RightToLeft ? 1u : 0u));
            Check(Method<CreateLayout>(factory, 18)(factory, request.Text, (uint)request.Text.Length,
                format, 1_000_000, 10_000, out layout));
            NativeLabelFallback.Apply(factory, layout, request.Families);
            factory2 = Query(factory, Factory2Id);
            Check(Method<InterfaceResult>(factory, 10)(factory, out parameters));
            using var renderer = new Renderer(request, factory2, parameters, prepared, cancellation);
            Check(Method<DrawLayout>(layout, 58)(layout, IntPtr.Zero, renderer.Pointer, 0, 0));
            if (renderer.Failure != null) throw renderer.Failure;
            cancellation.ThrowIfCancellationRequested();
            PerformanceTrace.Count("glyph.prepare.glyphs", prepared.Glyphs);
            return prepared;
        }
        catch { prepared.Dispose(); throw; }
        finally { Release(ref parameters); Release(ref factory2); Release(ref layout); Release(ref format); }
    }

    // A pure CPU IDWriteTextRenderer callback. GlyphRun pointers belong to the
    // synchronous layout.Draw call; they never escape to a second thread.
    private sealed class Renderer : IDisposable
    {
        private static readonly Guid Unknown = new("00000000-0000-0000-c000-000000000046");
        private static readonly Guid Snapping = new("eaf3a2da-ecf4-4d24-b644-b34f6842024b");
        private static readonly Guid TextRenderer = new("ef8a8135-5cc6-45fe-8825-c5a0724eb819");
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int QueryCallback(IntPtr self, ref Guid iid, out IntPtr value);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate uint RefCallback(IntPtr self);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int SnapCallback(IntPtr self, IntPtr context, out int disabled);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int TransformCallback(IntPtr self, IntPtr context, out Matrix matrix);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int DpiCallback(IntPtr self, IntPtr context, out float dpi);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int GlyphCallback(IntPtr self, IntPtr context, float x, float y, uint mode, IntPtr run, IntPtr description, IntPtr effect);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int DecorationCallback(IntPtr self, IntPtr context, float x, float y, IntPtr decoration, IntPtr effect);
        [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int InlineCallback(IntPtr self, IntPtr context, float x, float y, IntPtr inline, int sideways, int rtl, IntPtr effect);
        private static readonly Delegate[] callbacks = [new QueryCallback(QueryInterface), new RefCallback(AddRef),
            new RefCallback(ReleaseReference), new SnapCallback(PixelSnapping), new TransformCallback(Transform),
            new DpiCallback(Dpi), new GlyphCallback(Glyph), new DecorationCallback(Decoration),
            new DecorationCallback(Decoration), new InlineCallback(Inline)];
        private static readonly IntPtr vtable = CreateVtable();
        private readonly Request request;
        private readonly IntPtr factory, parameters;
        private readonly Prepared prepared;
        private readonly CancellationToken cancellation;
        private int references = 1;
        internal IntPtr Pointer { get; private set; }
        internal Exception? Failure { get; private set; }
        internal Renderer(Request request, IntPtr factory, IntPtr parameters, Prepared prepared, CancellationToken cancellation)
        {
            this.request = request; this.factory = factory; this.parameters = parameters;
            this.prepared = prepared; this.cancellation = cancellation;
            Pointer = Marshal.AllocHGlobal(2 * IntPtr.Size);
            Marshal.WriteIntPtr(Pointer, vtable);
            Marshal.WriteIntPtr(Pointer, IntPtr.Size, GCHandle.ToIntPtr(GCHandle.Alloc(this)));
        }
        private static IntPtr CreateVtable()
        {
            var table = Marshal.AllocHGlobal(callbacks.Length * IntPtr.Size);
            for (var i = 0; i < callbacks.Length; i++) Marshal.WriteIntPtr(table, i * IntPtr.Size, Marshal.GetFunctionPointerForDelegate(callbacks[i]));
            return table;
        }
        private static Renderer Owner(IntPtr self) => (Renderer)GCHandle.FromIntPtr(Marshal.ReadIntPtr(self, IntPtr.Size)).Target!;
        private static int QueryInterface(IntPtr self, ref Guid iid, out IntPtr value)
        {
            if (iid == Unknown || iid == Snapping || iid == TextRenderer) { value = self; AddRef(self); return 0; }
            value = IntPtr.Zero; return unchecked((int)0x80004002);
        }
        private static uint AddRef(IntPtr self) => (uint)Interlocked.Increment(ref Owner(self).references);
        private static uint ReleaseReference(IntPtr self)
        {
            var owner = Owner(self); var remaining = Interlocked.Decrement(ref owner.references);
            if (remaining == 0)
            {
                GCHandle.FromIntPtr(Marshal.ReadIntPtr(self, IntPtr.Size)).Free();
                owner.Pointer = IntPtr.Zero; Marshal.FreeHGlobal(self);
            }
            return (uint)remaining;
        }
        private static int PixelSnapping(IntPtr self, IntPtr context, out int disabled) { disabled = 0; return 0; }
        private static int Transform(IntPtr self, IntPtr context, out Matrix matrix) { matrix = new() { M11 = 1, M22 = 1 }; return 0; }
        private static int Dpi(IntPtr self, IntPtr context, out float dpi) { dpi = Owner(self).request.Scale; return 0; }
        private static int Decoration(IntPtr self, IntPtr context, float x, float y, IntPtr decoration, IntPtr effect) => 0;
        private static int Inline(IntPtr self, IntPtr context, float x, float y, IntPtr inline, int sideways, int rtl, IntPtr effect) =>
            Method<DrawInline>(inline, 3)(inline, context, self, x, y, sideways, rtl, effect);
        private static int Glyph(IntPtr self, IntPtr context, float x, float y, uint mode, IntPtr run, IntPtr description, IntPtr effect)
        {
            try { Owner(self).PrepareRun(run, mode, x, y); return 0; }
            catch (Exception error) { Owner(self).Failure = error; return Marshal.GetHRForException(error); }
        }
        private void PrepareRun(IntPtr pointer, uint measuring, float x, float y)
        {
            cancellation.ThrowIfCancellationRequested();
            var run = Marshal.PtrToStructure<GlyphRun>(pointer);
            if (run.GlyphCount == 0) return;
            IntPtr face2 = IntPtr.Zero, analysis = IntPtr.Zero, bytes = IntPtr.Zero;
            try
            {
                face2 = Query(run.FontFace, FontFace2);
                // Match D2D's recommended raster mode for the real font/scale.
                // FontFace2 slot 34; Factory2 slot 30 (Windows SDK dwrite_2.h).
                Check(Method<RecommendedMode>(face2, 34)(face2, run.FontEmSize, 96 * request.Scale,
                    96 * request.Scale, IntPtr.Zero, run.IsSideways, 0, measuring, parameters, out var rendering, out var gridFit));
                if (rendering is 0 or 6) throw new NotSupportedException("Glyph preparation requires a raster rendering mode");
                var transform = new Matrix { M11 = request.Scale, M22 = request.Scale };
                // WinUI renders an alpha-coverage atlas: grayscale, natural
                // measuring, and the monitor-scaled transform. Alpha mode does
                // not change the final TextBlock rendering settings.
                Check(Method<CreateAnalysis>(factory, 30)(factory, pointer, ref transform, rendering,
                    measuring, gridFit, 1, x, y, out analysis));
                Check(Method<TextureBounds>(analysis, 3)(analysis, 0, out var bounds));
                bytes = Marshal.AllocHGlobal(256 * 64);
                for (var top = bounds.Top; top < bounds.Bottom; top += 64)
                    for (var left = bounds.Left; left < bounds.Right; left += 256)
                    {
                        cancellation.ThrowIfCancellationRequested();
                        var tile = new Rect { Left = left, Top = top, Right = Math.Min(left + 256, bounds.Right), Bottom = Math.Min(top + 64, bounds.Bottom) };
                        Check(Method<AlphaTexture>(analysis, 4)(analysis, 0, ref tile, bytes, (uint)((tile.Right - tile.Left) * (tile.Bottom - tile.Top))));
                    }
                prepared.Glyphs += checked((int)run.GlyphCount);
                prepared.Retain(analysis); analysis = IntPtr.Zero;
            }
            finally { if (bytes != IntPtr.Zero) Marshal.FreeHGlobal(bytes); Release(ref analysis); Release(ref face2); }
        }
        public void Dispose() { if (Pointer != IntPtr.Zero) ReleaseReference(Pointer); }
    }
}
