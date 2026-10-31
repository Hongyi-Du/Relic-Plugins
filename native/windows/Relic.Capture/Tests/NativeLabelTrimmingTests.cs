using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
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
            var hitTest = ReadBounds(layout, text.Length);

            // Invoke the real layout and the actual factory omission object's
            // Draw, through the linked production renderer. Only the terminal
            // D2D sink is mocked; these assertions prove callback forwarding
            // and glyph submission, not ink bounds or screenshot presentation.
            using var target = new RecordingGlyphSink();
            using var renderer = new NativeLabelRenderer(target.Pointer, new IntPtr(1), 1,
                new Matrix { M11 = 1, M22 = 1 }, sign, captureDiagnostics: true);
            var drawHr = Method<DrawLayout>(layout, 58)(layout, IntPtr.Zero, renderer.Pointer, 0, 0);
            var diagnostic = JsonSerializer.Serialize(new
            {
                text, sign_metrics = signMetrics, line_metrics = narrow, hit_metrics = hitTest,
                draw_hresult = drawHr, callback_failure = renderer.CallbackFailure,
                inline_draws = renderer.InlineDraws,
                glyph_submissions = renderer.Runs.Select(run => new
                {
                    ordinal = run?["ordinal"], inline_draw_ordinal = run?["inline_draw_ordinal"],
                    submitted_to_d2d = run?["submitted_to_d2d"], glyph_indices = run?["glyph_indices"]
                })
            }, new JsonSerializerOptions { IncludeFields = true });
            void Require(bool condition, string expectation) => Assert.True(condition, expectation + "\n" + diagnostic);
            Require(drawHr >= 0 && renderer.CallbackFailure == null, "The actual layout and omission object must draw successfully");
            var omissions = renderer.InlineDraws.Where(row => row?["is_configured_trimming_sign"]?.GetValue<bool>() == true).ToArray();
            Require(omissions.Length == 1, "This horizontal single-line layout must draw its actual configured omission object once");
            var omission = omissions[0]!;
            Require(ComIdentity(sign) == omission["inline_com_identity"]!.GetValue<string>(), "The actual omission object's COM identity must match");
            Require(omission["draw_succeeded"]!.GetValue<bool>() && omission["glyph_run_count"]!.GetValue<int>() > 0,
                "The actual omission Draw must submit glyphs");
            Require(signMetrics.Height == omission["inline_metrics"]!["height"]!.GetValue<float>()
                && signMetrics.Width == omission["inline_metrics"]!["width"]!.GetValue<float>()
                && signMetrics.Baseline == omission["inline_metrics"]!["baseline"]!.GetValue<float>(),
                "Preserve the actual omission layout metrics, including a zero height");
            Require(renderer.Runs.Any(run => run?["inline_draw_ordinal"]?.GetValue<int>() == omission["ordinal"]!.GetValue<int>()
                && run["submitted_to_d2d"]!.GetValue<bool>() && run["glyph_indices"]!.AsArray().Count > 0)
                && target.GlyphCalls > 0, "The actual inline Draw must reach the production glyph submission path");
            Require(narrow.Length == 1 && narrow[0].Length == text.Length && narrow[0].IsTrimmed != 0,
                "The same narrow layout must retain the full source range and report trimming");
            Require(hitTest.Any(item => item.IsTrimmed != 0 && item.Length > 0), "The actual HitTestTextRange must report the replaced source range");
            Require(hitTest.All(item => (ulong)item.TextPosition + item.Length <= (ulong)text.Length
                && float.IsFinite(item.Left) && float.IsFinite(item.Top)
                && float.IsFinite(item.Width) && item.Width >= 0 && float.IsFinite(item.Height) && item.Height >= 0),
                "Actual hit-test layout regions must be finite and stay within the source UTF16 range; positive ink height is not required");

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

    [Theory]
    [InlineData(80f)]
    [InlineData(2000f)]
    public void NormalModeForwardsTheSameTerminalGlyphsWithoutDiagnosticCollections(float width)
    {
        if (!OperatingSystem.IsWindows()) return;
        const string text = "A long preview still paints its text and omission glyph when diagnostics are disabled.";
        IntPtr factory = IntPtr.Zero, format = IntPtr.Zero, layout = IntPtr.Zero, sign = IntPtr.Zero;
        try
        {
            var factoryId = new Guid("b859ee5a-d838-4b5b-a2e8-1adc7d93db48");
            Check(DWriteCreateFactory(0, ref factoryId, out factory));
            Check(Method<CreateFormat>(factory, 15)(factory, "Segoe UI", IntPtr.Zero, 400, 0, 5, 12, "en-US", out format));
            Check(Method<SetUInt>(format, 5)(format, 1));
            Check(Method<CreateLayout>(factory, 18)(factory, text, (uint)text.Length, format, width, 30, out layout));
            sign = ApplyCharacterEllipsis(factory, layout);
            using var diagnosticTarget = new RecordingGlyphSink();
            using var normalTarget = new RecordingGlyphSink();
            using var diagnostic = new NativeLabelRenderer(diagnosticTarget.Pointer, new IntPtr(1), 1,
                new Matrix { M11 = 1, M22 = 1 }, sign, captureDiagnostics: true);
            using var normal = new NativeLabelRenderer(normalTarget.Pointer, new IntPtr(1), 1,
                new Matrix { M11 = 1, M22 = 1 }, sign, captureDiagnostics: false);
            Check(Method<DrawLayout>(layout, 58)(layout, IntPtr.Zero, diagnostic.Pointer, 0, 0));
            Check(Method<DrawLayout>(layout, 58)(layout, IntPtr.Zero, normal.Pointer, 0, 0));
            Assert.Null(diagnostic.CallbackFailure);
            Assert.Null(normal.CallbackFailure);
            Assert.NotEmpty(diagnosticTarget.Submissions);
            Assert.Equal(diagnosticTarget.Submissions, normalTarget.Submissions);
            Assert.True(normalTarget.GlyphCalls > 0);
            Assert.Empty(normal.Runs);
            Assert.Empty(normal.InlineDraws);
            Assert.Empty(normal.Limitations);
            if (width == 80)
            {
                var omission = Assert.Single(diagnostic.InlineDraws);
                Assert.True(omission!["is_configured_trimming_sign"]!.GetValue<bool>());
                Assert.True(omission["glyph_run_count"]!.GetValue<int>() > 0);
            }
            else Assert.Empty(diagnostic.InlineDraws);
        }
        finally { Release(ref sign); Release(ref layout); Release(ref format); Release(ref factory); }
    }

    private sealed record GlyphSubmission(float X, float Y, uint Mode, IntPtr Brush,
        float EmSize, int Sideways, uint BidiLevel, string? Indices, string? Advances, string? Offsets);

    private sealed class RecordingGlyphSink : IDisposable
    {
        private readonly IntPtr vtable;
        private readonly DrawGlyph glyph;
        private readonly GlyphBounds bounds;
        private readonly GetWorldTransform transform;
        private readonly GetContextDpi dpi;
        private readonly GetUInt unitMode;
        internal IntPtr Pointer { get; }
        internal int GlyphCalls { get; private set; }
        internal List<GlyphSubmission> Submissions { get; } = [];
        internal RecordingGlyphSink()
        {
            // Slots/ABI match the production context calls. The zero fixture
            // bounds are intentionally not treated as visible glyph geometry.
            glyph = (_, point, pointer, brush, mode) =>
            {
                var run = Marshal.PtrToStructure<GlyphRun>(pointer);
                if (run.GlyphCount > 0) GlyphCalls++;
                // Copy the actual terminal sink arguments while DirectWrite's
                // callback pointers are valid; compare both production modes.
                string? Bytes(IntPtr source, int stride)
                {
                    if (source == IntPtr.Zero) return null;
                    var bytes = new byte[checked((int)run.GlyphCount * stride)];
                    Marshal.Copy(source, bytes, 0, bytes.Length); return Convert.ToBase64String(bytes);
                }
                Submissions.Add(new(point.X, point.Y, mode, brush, run.FontEmSize, run.IsSideways, run.BidiLevel,
                    Bytes(run.GlyphIndices, sizeof(ushort)), Bytes(run.GlyphAdvances, sizeof(float)),
                    Bytes(run.GlyphOffsets, Marshal.SizeOf<GlyphOffset>())));
            };
            bounds = (IntPtr self, PointF point, IntPtr run, uint mode, out RectF value) => { value = default; return 0; };
            transform = (IntPtr self, out Matrix value) => { value = new Matrix { M11 = 1, M22 = 1 }; };
            dpi = (IntPtr self, out float x, out float y) => { x = y = 96; };
            unitMode = _ => 0;
            vtable = Marshal.AllocHGlobal(82 * IntPtr.Size); Pointer = Marshal.AllocHGlobal(IntPtr.Size);
            for (var i = 0; i < 82; i++) Marshal.WriteIntPtr(vtable, i * IntPtr.Size, IntPtr.Zero);
            Marshal.WriteIntPtr(vtable, 29 * IntPtr.Size, Marshal.GetFunctionPointerForDelegate(glyph));
            Marshal.WriteIntPtr(vtable, 31 * IntPtr.Size, Marshal.GetFunctionPointerForDelegate(transform));
            Marshal.WriteIntPtr(vtable, 52 * IntPtr.Size, Marshal.GetFunctionPointerForDelegate(dpi));
            Marshal.WriteIntPtr(vtable, 72 * IntPtr.Size, Marshal.GetFunctionPointerForDelegate(bounds));
            Marshal.WriteIntPtr(vtable, 81 * IntPtr.Size, Marshal.GetFunctionPointerForDelegate(unitMode));
            Marshal.WriteIntPtr(Pointer, vtable);
        }
        public void Dispose()
        {
            Marshal.FreeHGlobal(Pointer); Marshal.FreeHGlobal(vtable);
            GC.KeepAlive(glyph); GC.KeepAlive(bounds); GC.KeepAlive(transform); GC.KeepAlive(dpi); GC.KeepAlive(unitMode);
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
