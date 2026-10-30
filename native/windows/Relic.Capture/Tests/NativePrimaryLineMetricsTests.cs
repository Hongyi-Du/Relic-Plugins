using Relic;
using Xunit;

namespace Relic.Capture.Tests;

public sealed class NativePrimaryLineMetricsTests
{
    [Fact]
    public void RecordedPrimaryFacesProduceTheMixedHeaderBaselineAndFullDescent()
    {
        // db91b1b actual renderer: Segoe UI Variable Text and Cascadia Code.
        // These are recorded font inputs; no scene coordinate enters layout.
        var name = NativePrimaryLineMetrics.FromPrimary(NativeListMarkerMetrics.FromDesignUnits(2048, 2210, 514, 12.5), 16.25);
        var identifier = NativePrimaryLineMetrics.FromPrimary(NativeListMarkerMetrics.FromDesignUnits(2048, 1900, 480, 11), 14.3);
        var recipient = NativePrimaryLineMetrics.FromPrimary(NativeListMarkerMetrics.FromDesignUnits(2048, 2210, 514, 12), 15.6);
        Assert.Equal(13, name.Baseline);
        Assert.Equal(10, identifier.Baseline);
        Assert.Equal(12, recipient.Baseline);
        var row = MessageHeaderLayoutEngine.Calculate([
            new(75, name.Height, name.Baseline), new(58, identifier.Height, identifier.Baseline),
            new(38, recipient.Height, recipient.Baseline)], 500, 6);
        Assert.Equal(3, row.Children[1].Y);
        Assert.Equal(1, row.Children[2].Y);
        Assert.Equal(17.296875, row.Height);
        Assert.Equal(row.Height, row.Children[1].Y + identifier.Height);
    }

    [Fact]
    public void WrappedRowsUseTheirOwnActualFontMetrics()
    {
        var name = NativePrimaryLineMetrics.FromPrimary(new(13, 3), 16.25);
        var identifier = NativePrimaryLineMetrics.FromPrimary(new(10, 3), 14.3);
        var row = MessageHeaderLayoutEngine.Calculate([
            new(75, name.Height, name.Baseline), new(58, identifier.Height, identifier.Baseline)], 100, 6);
        Assert.Equal(0, row.Children[0].Y);
        Assert.Equal(22.25, row.Children[1].Y);
        Assert.Equal(36.546875, row.Height);
    }

    [Theory]
    [InlineData(20.3, 2, 3.296875)]
    [InlineData(14.3, -1, 0.296875)]
    [InlineData(14, -1, 0)]
    public void RemainingLeadingIsKeptBelowTheBaseline(double height, double before, double after)
    {
        var actual = NativePrimaryLineMetrics.FromPrimary(new(12, 3), height);
        Assert.Equal(before, actual.LeadingBefore);
        Assert.Equal(after, actual.LeadingAfter);
        Assert.Equal(actual.Height, actual.PrimaryAscent + actual.PrimaryDescent + before + after);
    }

    [Fact]
    public void OneNegativeFixedPointUnitIsDividedBeforeFlooring()
    {
        var actual = NativePrimaryLineMetrics.FromPrimary(new(12, 3), 15 - 1d / 64);
        Assert.Equal(0, actual.LeadingBefore);
        Assert.Equal(-1d / 64, actual.LeadingAfter);
        Assert.Equal(12, actual.Baseline);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(-1)]
    [InlineData(double.NaN)]
    [InlineData(double.PositiveInfinity)]
    public void InvalidLineHeightDoesNotInventMetrics(double height) =>
        Assert.Throws<ArgumentOutOfRangeException>(() => NativePrimaryLineMetrics.FromPrimary(new(12, 3), height));

    [Fact]
    public void MissingOrInvalidPrimaryMetricsDoNotFallBackToAConfiguredFontSize()
    {
        Assert.Throws<ArgumentOutOfRangeException>(() => NativePrimaryLineMetrics.FromPrimary(new(0, 3), 16));
        Assert.Throws<ArgumentOutOfRangeException>(() => NativePrimaryLineMetrics.FromPrimary(new(12, -1), 16));
    }
}
