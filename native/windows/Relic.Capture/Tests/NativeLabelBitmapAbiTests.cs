using System.Reflection;
using System.Runtime.InteropServices;
using Relic;
using Xunit;
using static Relic.NativeLabelInterop;

public sealed class NativeLabelBitmapAbiTests
{
    // This contract caused all 17 scenes in 067eec6 to crash in GetPixelSize.
    // COM virtual struct returns put the caller's result buffer after `this`;
    // they do not use the ordinary C function's struct-return convention.
    // https://github.com/microsoft/CsWin32/issues/731
    // https://github.com/microsoft/win32metadata/issues/636
    [Theory]
    [InlineData(typeof(GetBitmapPixelSize), typeof(SizeU))]
    [InlineData(typeof(GetBitmapPixelFormat), typeof(PixelFormat))]
    public void BitmapGettersUseVoidSelfAndExplicitOutputBuffer(Type getter, Type result)
    {
        var invoke = getter.GetMethod("Invoke")!;
        Assert.Equal(typeof(void), invoke.ReturnType);
        var parameters = invoke.GetParameters();
        Assert.Equal(2, parameters.Length);
        Assert.Equal(typeof(IntPtr), parameters[0].ParameterType);
        Assert.Equal(result.MakeByRefType(), parameters[1].ParameterType);
        Assert.True(parameters[1].IsOut);
        Assert.Equal(CallingConvention.StdCall,
            getter.GetCustomAttribute<UnmanagedFunctionPointerAttribute>()!.CallingConvention);
        Assert.Equal(8, Marshal.SizeOf(result));
    }

    [Fact]
    public void ActualGetterDelegatesReadBothFieldsThroughControlledVtableSlots()
    {
        var vtable = Marshal.AllocHGlobal(7 * IntPtr.Size);
        var instance = Marshal.AllocHGlobal(IntPtr.Size);
        IntPtr sizeSelf = IntPtr.Zero, formatSelf = IntPtr.Zero;
        var sizeCalls = 0; var formatCalls = 0;
        GetBitmapPixelSize sizeCallback = (IntPtr self, out SizeU result) =>
        {
            sizeSelf = self; sizeCalls++;
            result = new SizeU { Width = 0x12345678, Height = 0x89abcdef };
        };
        GetBitmapPixelFormat formatCallback = (IntPtr self, out PixelFormat result) =>
        {
            formatSelf = self; formatCalls++;
            result = new PixelFormat { Format = 87, AlphaMode = 1 };
        };
        try
        {
            for (var slot = 0; slot < 7; slot++) Marshal.WriteIntPtr(vtable, slot * IntPtr.Size, IntPtr.Zero);
            Marshal.WriteIntPtr(vtable, 5 * IntPtr.Size, Marshal.GetFunctionPointerForDelegate(sizeCallback));
            Marshal.WriteIntPtr(vtable, 6 * IntPtr.Size, Marshal.GetFunctionPointerForDelegate(formatCallback));
            Marshal.WriteIntPtr(instance, vtable);

            // Invoke the linked production declarations and vtable resolver.
            // This is a managed callback fixture, not a claim of a real D2D draw.
            Method<GetBitmapPixelSize>(instance, 5)(instance, out var size);
            Method<GetBitmapPixelFormat>(instance, 6)(instance, out var format);

            Assert.Equal(instance, sizeSelf); Assert.Equal(instance, formatSelf);
            Assert.Equal(1, sizeCalls); Assert.Equal(1, formatCalls);
            Assert.Equal(0x12345678u, size.Width); Assert.Equal(0x89abcdefu, size.Height);
            Assert.Equal(87u, format.Format); Assert.Equal(1u, format.AlphaMode);
        }
        finally
        {
            GC.KeepAlive(sizeCallback); GC.KeepAlive(formatCallback);
            Marshal.FreeHGlobal(instance); Marshal.FreeHGlobal(vtable);
        }
    }
}
