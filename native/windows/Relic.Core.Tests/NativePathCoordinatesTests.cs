using Relic;
using Xunit;

namespace Relic.Core.Tests;

public sealed class NativePathCoordinatesTests
{
    // Recorded f6220c9 file-code NativePathText xaml-538 / uia-117.
    // The original provider added the clipped peer Y (96) to the owner-local
    // clip offset (18.3500061), yielding 114.3500061 instead of root Y=96.
    private const double OwnerX = 467.1083984375;
    private const double OwnerY = 77.64999389648438;
    private const double LocalClipY = 18.350006103515625;
    private static readonly NativePathCoordinates.Bounds Local = new(0, 0, 251.783203125, 19.200000762939453);
    private static readonly NativePathCoordinates.Bounds Clip = new(0, LocalClipY, 251.783203125, 698);

    private static NativePathCoordinates.Bounds ToRoot(NativePathCoordinates.Bounds bounds) =>
        new(bounds.X + OwnerX, bounds.Y + OwnerY, bounds.Width, bounds.Height);

    [Fact]
    public void RecordedPartialLineUsesUnclippedOriginAndRetainsSubpixelHeight()
    {
        var result = NativePathCoordinates.ToRasterizedClient(Local, Clip, ToRoot, 1);
        Assert.NotNull(result);
        Assert.Equal(new NativePathCoordinates.Bounds(OwnerX, 96, 251.783203125, 0.8499946594238281), result.Value);
        Assert.NotEqual(114.35000610351562, result.Value.Y);
    }

    [Theory]
    [InlineData(1.0)]
    [InlineData(1.25)]
    [InlineData(1.5)]
    [InlineData(2.0)]
    public void RasterizationScalesTheWholeRootRectangleOnceWithoutScreenOrigin(double scale)
    {
        var result = NativePathCoordinates.ToRasterizedClient(Local, Clip, ToRoot, scale)!.Value;
        Assert.Equal(OwnerX * scale, result.X);
        Assert.Equal(96 * scale, result.Y);
        Assert.Equal(251.783203125 * scale, result.Width);
        Assert.Equal(0.8499946594238281 * scale, result.Height);
        // No HWND origin (+8,+31 in the recorded CI window) enters this API.
        Assert.NotEqual(OwnerX * scale + 8, result.X);
        Assert.NotEqual(96 * scale + 31, result.Y);
    }

    [Theory]
    [InlineData(1.0)]
    [InlineData(1.5)]
    public void HitTestingReversesRootScaleThenTheActualUnclippedTransform(double scale)
    {
        var providerPoint = new NativePathCoordinates.Point((OwnerX + 125.25) * scale, 96.25 * scale);
        var local = NativePathCoordinates.ToOwner(providerPoint,
            root => new(root.X - OwnerX, root.Y - OwnerY), scale);
        Assert.Equal(125.25, local.X);
        Assert.Equal(18.600006103515625, local.Y);
        Assert.NotEqual(0.25, local.Y); // Subtracting the clipped peer Y would be wrong.
    }

    [Fact]
    public void ActualRenderTransformParticipatesInRangeAndInverseHitTesting()
    {
        NativePathCoordinates.Bounds Transform(NativePathCoordinates.Bounds value) =>
            new(value.X * 2 + 10, value.Y * 3 + 20, value.Width * 2, value.Height * 3);
        var result = NativePathCoordinates.ToRasterizedClient(new(2, 3, 10, 8), new(0, 5, 30, 40), Transform, 1.5)!.Value;
        Assert.Equal(new NativePathCoordinates.Bounds(21, 52.5, 30, 27), result);
        var point = NativePathCoordinates.ToOwner(new(21, 52.5),
            root => new((root.X - 10) / 2, (root.Y - 20) / 3), 1.5);
        Assert.Equal(new NativePathCoordinates.Point(2, 5), point);
    }

    [Fact]
    public void FullyClippedRangeHasNoGeometryAndDoesNotInvokeTransform()
    {
        var calls = 0;
        var result = NativePathCoordinates.ToRasterizedClient(Local, new(0, 20, 1000, 10), bounds =>
        {
            calls++;
            return ToRoot(bounds);
        }, 1);
        Assert.Null(result);
        Assert.Equal(0, calls);
    }

    [Fact]
    public void ClipOriginNeverReplacesTheOwnerTransformForHorizontalClippingEither()
    {
        var result = NativePathCoordinates.ToRasterizedClient(new(0, 0, 20.5, 5), new(20, 0, 10, 5),
            bounds => new(bounds.X - 12, bounds.Y + 30, bounds.Width, bounds.Height), 1)!.Value;
        Assert.Equal(new NativePathCoordinates.Bounds(8, 30, 0.5, 5), result);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    [InlineData(double.NaN)]
    [InlineData(double.PositiveInfinity)]
    public void UnknownOrInvalidScaleDoesNotDefaultToOne(double scale)
    {
        Assert.Throws<InvalidOperationException>(() => NativePathCoordinates.ToRasterizedClient(Local, Clip, ToRoot, scale));
        Assert.Throws<InvalidOperationException>(() => NativePathCoordinates.ToOwner(new(1, 2), point => point, scale));
    }

    [Fact]
    public void NonfiniteActualTransformDoesNotManufactureAVisibleBoxOrPoint()
    {
        Assert.Throws<InvalidOperationException>(() => NativePathCoordinates.ToRasterizedClient(Local, Clip,
            bounds => new(double.PositiveInfinity, bounds.Y, bounds.Width, bounds.Height), 1));
        Assert.Throws<InvalidOperationException>(() => NativePathCoordinates.ToOwner(new(1, 2),
            point => new(point.X, double.NaN), 1));
    }
}
