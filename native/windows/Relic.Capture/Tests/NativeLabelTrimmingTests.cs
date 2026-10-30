using System.Reflection;
using System.Runtime.InteropServices;
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
            Assert.True(signMetrics.Height > 0);
            Assert.False(ReadLines(layout).Any(line => line.IsTrimmed != 0));

            Check(Method<SetFloat>(layout, 28)(layout, 80));
            var narrow = ReadLines(layout);
            Assert.Single(narrow);
            Assert.Equal((uint)text.Length, narrow[0].Length);
            Assert.NotEqual(0, narrow[0].IsTrimmed);
            var hitTest = ReadBounds(layout, text.Length);
            Assert.Contains(hitTest, item => item.IsTrimmed != 0 && item.Width > 0 && item.Height > 0);
            Assert.All(hitTest, item => Assert.True(item.TextPosition + item.Length <= text.Length));

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
