using System.Runtime.InteropServices;
using Relic;
using Xunit;
using static Relic.NativeLabelInterop;

namespace Relic.Capture.Tests;

public sealed class NativeInsetShadowTests
{
    [Fact]
    public void NormalBubbleUsesItsPaddingEdgeWithFourDifferentCorners()
    {
        var shape = NativeInsetShadowGeometry.PaddingEdge(420, 72, 0, 0, 0, 0, 4, 14, 14, 14);
        Assert.Equal(new double[] { 4, 4, 14, 14, 14, 14, 14, 14 }, shape.Radii);
        Assert.Equal(new double[] { 4, 0 }, shape.Commands[0].Values);
        Assert.Equal("Z", shape.Commands[^1].Kind);
        Assert.Equal(4, shape.Commands.Count(c => c.Kind == "A"));
        Assert.Equal(420, shape.Width); Assert.Equal(72, shape.Height);
    }

    [Fact]
    public void PlainBubbleKeepsItsRealBorderOutsideTheInsetShadow()
    {
        var shape = NativeInsetShadowGeometry.PaddingEdge(420, 72, 1, 1, 1, 1, 4, 14, 14, 14);
        Assert.Equal(new double[] { 3, 3, 13, 13, 13, 13, 13, 13 }, shape.Radii);
        Assert.Equal(1, shape.X); Assert.Equal(1, shape.Y);
        Assert.Equal(418, shape.Width); Assert.Equal(70, shape.Height);
        Assert.Equal(new double[] { 4, 1 }, shape.Commands[0].Values);
    }

    [Fact]
    public void NarrowShapesNormalizeRadiiInsteadOfClippingAConstantLeftStripe()
    {
        var shape = NativeInsetShadowGeometry.PaddingEdge(20, 10, 0, 0, 0, 0, 14, 14, 14, 14);
        Assert.All(shape.Radii, r => Assert.Equal(5, r));
        Assert.Equal(new double[] { 5, 0 }, shape.Commands[0].Values);
        Assert.Equal(new double[] { 20, 5, 5, 5 }, shape.Commands[2].Values);
    }

    [Fact]
    public void InvalidGeometryCannotBecomeAnInventedShadow()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => NativeInsetShadowGeometry.PaddingEdge(double.NaN, 40, 0, 0, 0, 0, 4, 14, 14, 14));
        Assert.Throws<ArgumentOutOfRangeException>(() => NativeInsetShadowGeometry.PaddingEdge(2, 40, 1, 0, 1, 0, 4, 14, 14, 14));
    }

    [Fact]
    public void NativeSimplifiedSinkConsumesActualPointAndCubicArrayAbi()
    {
        // Controlled COM vtable callbacks only: no D2D factory, HWND or UI.
        using var sink = new NativeInsetShadowSink();
        var p = sink.Pointer;
        Method<NativeInsetShadowSink.EnumCall>(p, 3)(p, 1);
        Method<NativeInsetShadowSink.Begin>(p, 5)(p, new PointF(2, 4), 0);
        var points = Marshal.AllocHGlobal(24);
        try
        {
            Marshal.StructureToPtr(new PointF(6, 8), points, false);
            Method<NativeInsetShadowSink.ArrayCall>(p, 6)(p, points, 1);
            Marshal.StructureToPtr(new PointF(10, 12), points, false);
            Marshal.StructureToPtr(new PointF(14, 16), points + 8, false);
            Marshal.StructureToPtr(new PointF(18, 20), points + 16, false);
            Method<NativeInsetShadowSink.ArrayCall>(p, 7)(p, points, 1);
        }
        finally { Marshal.FreeHGlobal(points); }
        Method<NativeInsetShadowSink.EnumCall>(p, 8)(p, 1);
        Assert.Equal(0, Method<NativeInsetShadowSink.CloseCall>(p, 9)(p));
        Assert.Equal((uint)1, sink.FillMode);
        Assert.Equal(new double[] { 2, 4 }, sink.Commands[0].Values);
        Assert.Equal(new double[] { 6, 8 }, sink.Commands[1].Values);
        Assert.Equal(new double[] { 10, 12, 14, 16, 18, 20 }, sink.Commands[2].Values);
        Assert.Equal("Z", sink.Commands[3].Kind);
    }

    [Fact]
    public void NativeCallbackFailureIsReturnedWithoutThrowingAcrossVoidAbi()
    {
        using var sink = new NativeInsetShadowSink(); var p = sink.Pointer;
        Method<NativeInsetShadowSink.Begin>(p, 5)(p, new PointF(float.NaN, 4), 0);
        Assert.True(Method<NativeInsetShadowSink.CloseCall>(p, 9)(p) < 0);
        Assert.Throws<InvalidOperationException>(sink.Finish);
    }
}
