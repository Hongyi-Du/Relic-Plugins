using Relic;
using Xunit;

namespace Relic.Capture.Tests;

public sealed class NativeListMarkerMetricsTests
{
    [Fact]
    public void ActualDesignUnitsDrivePrimaryAscentAndDiscRatherThanBulletGlyphWidth()
    {
        var marker = NativeListMarkerMetrics.FromDesignUnits(1000, 1050, 300, 13.5);
        Assert.Equal(14, marker.Ascent); Assert.Equal(4, marker.Descent);
        Assert.Equal(5, marker.Diameter); Assert.Equal(7, marker.Width); Assert.Equal(18, marker.Height);
        Assert.Equal(new NativeMarkerRect(1, 7, 5, 5), marker.Disc);
        Assert.Equal(17, marker.DistanceBeforeText);
    }

    [Fact]
    public void PrimaryMetricTiesUseLroundNotBankersRounding()
    {
        var marker = NativeListMarkerMetrics.FromDesignUnits(1000, 1250, 250, 10);
        Assert.Equal(13, marker.Ascent); Assert.Equal(3, marker.Descent);
    }

    [Fact]
    public void DifferentActualFontSizesProduceDifferentSymbolGeometry()
    {
        var small = NativeListMarkerMetrics.FromDesignUnits(2048, 2048, 512, 12);
        var large = NativeListMarkerMetrics.FromDesignUnits(2048, 2048, 512, 18);
        Assert.Equal(4, small.Diameter); Assert.Equal(6, large.Diameter);
        Assert.NotEqual(small.Width, large.Width);
    }

    [Fact]
    public void OutsidePlacementSharesActualTextBaselineAndRetainsMarkerBox()
    {
        var marker = new NativeListMarkerMetrics(14, 4);
        var placed = marker.Outside(22, 16.25);
        Assert.Equal(16.25, placed.Y + marker.Ascent);
        Assert.Equal(22, placed.X + marker.DistanceBeforeText);
        Assert.Equal(marker.Width, placed.Width); Assert.Equal(marker.Height, placed.Height);
    }

    [Fact]
    public void PixelSnapUsesBothWindowEdgesAndActualFractionalOrigin()
    {
        var snapped = NativeListMarkerMetrics.Snap(new(1, 7, 5, 5), 10.25, 20.4, 1);
        Assert.Equal(.75, snapped.X, 10); Assert.Equal(6.6, snapped.Y, 10);
        Assert.Equal(5, snapped.Width); Assert.Equal(5, snapped.Height);
        Assert.Equal(11, snapped.X + 10.25, 10); Assert.Equal(27, snapped.Y + 20.4, 10);
    }

    [Fact]
    public void FractionalDisplayScaleChangesActualDipExtent()
    {
        var snapped = NativeListMarkerMetrics.Snap(new(1, 7, 5, 5), 10.2, 20.2, 1.25);
        Assert.Equal(4.8, snapped.Width, 10); Assert.Equal(4.8, snapped.Height, 10);
        Assert.Equal(14, (snapped.X + 10.2) * 1.25, 10);
        Assert.Equal(34, (snapped.Y + 20.2) * 1.25, 10);
    }

    [Fact]
    public void NegativeHalfPixelEdgesRoundTowardPositiveInfinity()
    {
        var snapped = NativeListMarkerMetrics.Snap(new(-.5, -.5, 2, 2), 0, 0, 1);
        Assert.Equal(new NativeMarkerRect(0, 0, 2, 2), snapped);
    }

    [Theory]
    [InlineData(0)] [InlineData(-1)] [InlineData(double.NaN)] [InlineData(double.PositiveInfinity)]
    public void InvalidDisplayScaleNeverProducesReplacementGeometry(double scale) =>
        Assert.Throws<ArgumentOutOfRangeException>(() => NativeListMarkerMetrics.Snap(new(1, 7, 5, 5), 0, 0, scale));

    [Fact]
    public void MissingFontMetricsCannotTurnIntoAConstantDisc()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => NativeListMarkerMetrics.FromDesignUnits(0, 14, 4, 13.5));
        Assert.Throws<ArgumentOutOfRangeException>(() => NativeListMarkerMetrics.FromDesignUnits(1000, 0, 4, 13.5));
        Assert.Throws<ArgumentOutOfRangeException>(() => NativeListMarkerMetrics.FromDesignUnits(1000, 1000, 300, double.NaN));
    }
}
