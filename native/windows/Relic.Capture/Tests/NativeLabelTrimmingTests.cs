using System.Reflection;
using System.Runtime.InteropServices;
using Relic;
using Xunit;
using static Relic.NativeLabelInterop;

public sealed class NativeLabelTrimmingTests
{
    [Theory]
    [InlineData(typeof(GetTrimming), typeof(Trimming), 3)]
    [InlineData(typeof(GetInlineMetrics), typeof(InlineMetrics), 2)]
    public void NativeOutputStructuresUseHresultAndExplicitOutParameters(Type method, Type output, int count)
    {
        var invoke = method.GetMethod("Invoke")!;
        Assert.Equal(typeof(int), invoke.ReturnType);
        var parameters = invoke.GetParameters();
        Assert.Equal(count, parameters.Length);
        Assert.Equal(typeof(IntPtr), parameters[0].ParameterType);
        Assert.Equal(output.MakeByRefType(), parameters[1].ParameterType);
        Assert.True(parameters[1].IsOut);
        Assert.Equal(CallingConvention.StdCall,
            method.GetCustomAttribute<UnmanagedFunctionPointerAttribute>()!.CallingConvention);
        Assert.Equal(output == typeof(Trimming) ? 12 : 16, Marshal.SizeOf(output));
        if (method == typeof(GetTrimming))
        {
            Assert.Equal(typeof(IntPtr).MakeByRefType(), parameters[2].ParameterType);
            Assert.True(parameters[2].IsOut);
        }
    }

    // CI-only Windows tests: DirectWrite is used headlessly; no WinUI window,
    // app, server or console program is launched. This verifies the linked
    // production trimming helper on its actual layout, not fake font metrics.
    [Theory]
    [InlineData("A long sidebar preview retains its full source text and terminal period.")]
    [InlineData("设计师：三个窗口尺寸都会检查，长标题会换行或显示省略提示。")]
    public void RealLayoutKeepsItsOmissionObjectAndChangesTrimStateWithActualWidth(string text)
    {
        if (!OperatingSystem.IsWindows()) return;
        IntPtr factory = IntPtr.Zero, format = IntPtr.Zero, layout = IntPtr.Zero, sign = IntPtr.Zero, returnedSign = IntPtr.Zero;
        try
        {
            var factoryId = new Guid("b859ee5a-d838-4b5b-a2e8-1adc7d93db48");
            Check(DWriteCreateFactory(0, ref factoryId, out factory));
            Check(Method<CreateFormat>(factory, 15)(factory, "Segoe UI", IntPtr.Zero, 400, 0, 5, 12, "zh-CN", out format));
            Check(Method<SetUInt>(format, 5)(format, 1));
            Check(Method<CreateLayout>(factory, 18)(factory, text, (uint)text.Length, format, 2000, 30, out layout));
            sign = ApplyCharacterEllipsis(factory, layout);
            Check(Method<GetTrimming>(layout, 17)(layout, out var options, out returnedSign));
            Assert.Equal(1u, options.Granularity);
            Assert.Equal(0u, options.Delimiter);
            Assert.Equal(0u, options.DelimiterCount);
            Assert.NotEqual(IntPtr.Zero, returnedSign);
            Assert.Equal(ComIdentity(sign), ComIdentity(returnedSign));
            Check(Method<GetInlineMetrics>(returnedSign, 4)(returnedSign, out var signMetrics));
            Assert.True(signMetrics.Width > 0);
            // GetMetrics reports inline layout dimensions, not ink. The
            // factory omission sign may have zero height; glyph emission is
            // instead checked through its actual Draw callbacks below.
            // https://learn.microsoft.com/en-us/windows/win32/api/dwrite/ns-dwrite-dwrite_inline_object_metrics
            Assert.True(float.IsFinite(signMetrics.Height) && signMetrics.Height >= 0,
                $"Actual omission metrics: width={signMetrics.Width:R}, height={signMetrics.Height:R}, baseline={signMetrics.Baseline:R}");
            Assert.True(float.IsFinite(signMetrics.Baseline));
            Assert.DoesNotContain(ReadLines(layout), line => line.IsTrimmed != 0);

            Check(Method<SetFloat>(layout, 28)(layout, 80));
            var narrow = ReadLines(layout);
            Assert.Single(narrow);
            Assert.Equal((uint)text.Length, narrow[0].Length);
            Assert.NotEqual(0, narrow[0].IsTrimmed);
            var hitTest = ReadBounds(layout, text.Length);
            Assert.Contains(hitTest, item => item.IsTrimmed != 0 && item.Width > 0 && item.Height > 0);
            Assert.All(hitTest, item => Assert.True(item.TextPosition + item.Length <= text.Length));

            // Invoke the real layout and the actual factory omission object's
            // Draw, through the linked production renderer. Only the terminal
            // D2D sink is mocked; these assertions prove callback forwarding
            // and glyph submission, not ink bounds or screenshot presentation.
            using var target = new RecordingGlyphSink();
            using var renderer = new NativeLabelRenderer(target.Pointer, new IntPtr(1), 1,
                new Matrix { M11 = 1, M22 = 1 }, sign);
            Check(Method<DrawLayout>(layout, 58)(layout, IntPtr.Zero, renderer.Pointer, 0, 0));
            Assert.Null(renderer.CallbackFailure);
            var omission = Assert.Single(renderer.InlineDraws.Where(row => row?["is_configured_trimming_sign"]?.GetValue<bool>() == true));
            Assert.Equal(ComIdentity(sign), omission!["inline_com_identity"]!.GetValue<string>());
            Assert.True(omission["draw_succeeded"]!.GetValue<bool>());
            Assert.True(omission["glyph_run_count"]!.GetValue<int>() > 0);
            Assert.Equal(signMetrics.Height, omission["inline_metrics"]!["height"]!.GetValue<float>());
            Assert.Contains(renderer.Runs, run => run?["inline_draw_ordinal"]?.GetValue<int>() == omission["ordinal"]!.GetValue<int>()
                && run["submitted_to_d2d"]!.GetValue<bool>() && run["glyph_indices"]!.AsArray().Count > 0);
            Assert.True(target.GlyphCalls > 0);

            // Re-expand this same layout. No separate measurement layout is
            // permitted to provide the untrimmed state or omitted text range.
            Check(Method<SetFloat>(layout, 28)(layout, 2000));
            var expanded = ReadLines(layout);
            Assert.Single(expanded);
            Assert.Equal((uint)text.Length, expanded[0].Length);
            Assert.Equal(0, expanded[0].IsTrimmed);
        }
        finally
        {
            Release(ref returnedSign); Release(ref sign); Release(ref layout); Release(ref format); Release(ref factory);
        }
    }

    private sealed class RecordingGlyphSink : IDisposable
    {
        private readonly IntPtr vtable;
        private readonly DrawGlyph glyph;
        private readonly GlyphBounds bounds;
        internal IntPtr Pointer { get; }
        internal int GlyphCalls { get; private set; }
        internal RecordingGlyphSink()
        {
            // Slots/ABI match the production context calls. The zero fixture
            // bounds are intentionally not treated as visible glyph geometry.
            glyph = (_, _, run, _, _) => { if (Marshal.PtrToStructure<GlyphRun>(run).GlyphCount > 0) GlyphCalls++; };
            bounds = (IntPtr self, PointF point, IntPtr run, uint mode, out RectF value) => { value = default; return 0; };
            vtable = Marshal.AllocHGlobal(73 * IntPtr.Size); Pointer = Marshal.AllocHGlobal(IntPtr.Size);
            for (var i = 0; i < 73; i++) Marshal.WriteIntPtr(vtable, i * IntPtr.Size, IntPtr.Zero);
            Marshal.WriteIntPtr(vtable, 29 * IntPtr.Size, Marshal.GetFunctionPointerForDelegate(glyph));
            Marshal.WriteIntPtr(vtable, 72 * IntPtr.Size, Marshal.GetFunctionPointerForDelegate(bounds));
            Marshal.WriteIntPtr(Pointer, vtable);
        }
        public void Dispose()
        {
            Marshal.FreeHGlobal(Pointer); Marshal.FreeHGlobal(vtable);
            GC.KeepAlive(glyph); GC.KeepAlive(bounds);
        }
    }

    private static LineMetrics[] ReadLines(IntPtr layout)
    {
        var hr = Method<GetArray>(layout, 59)(layout, IntPtr.Zero, 0, out var count);
        if (hr < 0 && hr != unchecked((int)0x8007007A)) Check(hr);
        var buffer = Marshal.AllocHGlobal(checked((int)count * Marshal.SizeOf<LineMetrics>()));
        try
        {
            Check(Method<GetArray>(layout, 59)(layout, buffer, count, out var actual));
            return Enumerable.Range(0, checked((int)actual))
                .Select(i => Marshal.PtrToStructure<LineMetrics>(buffer + i * Marshal.SizeOf<LineMetrics>())).ToArray();
        }
        finally { Marshal.FreeHGlobal(buffer); }
    }

    private static HitTestMetrics[] ReadBounds(IntPtr layout, int length)
    {
        var hr = Method<HitTestRange>(layout, 66)(layout, 0, (uint)length, 0, 0, IntPtr.Zero, 0, out var count);
        if (hr < 0 && hr != unchecked((int)0x8007007A)) Check(hr);
        var buffer = Marshal.AllocHGlobal(checked((int)count * Marshal.SizeOf<HitTestMetrics>()));
        try
        {
            Check(Method<HitTestRange>(layout, 66)(layout, 0, (uint)length, 0, 0, buffer, count, out var actual));
            return Enumerable.Range(0, checked((int)actual))
                .Select(i => Marshal.PtrToStructure<HitTestMetrics>(buffer + i * Marshal.SizeOf<HitTestMetrics>())).ToArray();
        }
        finally { Marshal.FreeHGlobal(buffer); }
    }
}
