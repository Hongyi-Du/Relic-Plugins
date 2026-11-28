using Relic;
using Xunit;

namespace Relic.Capture.Tests;

public sealed class MessageHeaderLayoutTests
{
    [Fact]
    public void DifferentFontBaselinesShareAnActualBaselineAndKeepBothDescents()
    {
        var children = new[] { new MessageHeaderMetric(31, 16.25, 12.5), new MessageHeaderMetric(26, 15.6, 11.4) };
        var result = MessageHeaderLayoutEngine.Calculate(children, 200, 6);
        Assert.True(result.UsesMeasuredBaselines);
        Assert.Equal(63, result.Width);
        Assert.Equal(16.7, result.Height, 10);
        Assert.Equal(0, result.Children[0].Y);
        Assert.Equal(1.1, result.Children[1].Y, 10);
        Assert.Equal(result.Children[0].Y + children[0].Baseline,
            result.Children[1].Y + children[1].Baseline, 10);
        Assert.Equal(result.Height, result.Children[1].Y + children[1].Height, 10);
    }

    [Fact]
    public void EachWrappedRowHasItsOwnBaselineAndKeepsTheExistingGap()
    {
        var children = new[] {
            new MessageHeaderMetric(30, 16, 12), new MessageHeaderMetric(20, 14, 9),
            new MessageHeaderMetric(30, 13, 11), new MessageHeaderMetric(20, 12, 8) };
        var result = MessageHeaderLayoutEngine.Calculate(children, 60, 6);
        Assert.True(result.UsesMeasuredBaselines);
        Assert.Equal(56, result.Width);
        Assert.Equal(38, result.Height);
        Assert.Equal(0, result.Children[0].Y);
        Assert.Equal(3, result.Children[1].Y);
        Assert.Equal(23, result.Children[2].Y);
        Assert.Equal(26, result.Children[3].Y);
        Assert.Equal(36, result.Children[1].X);
        Assert.Equal(0, result.Children[2].X);
    }

    [Fact]
    public void ExactWidthFitsWithoutWrappingOrATrailingGap()
    {
        var result = MessageHeaderLayoutEngine.Calculate(
            [new(25, 10, 8), new(19, 10, 8)], 50, 6);
        Assert.Equal(50, result.Width);
        Assert.Equal(10, result.Height);
        Assert.Equal(31, result.Children[1].X);
        Assert.Equal(0, result.Children[1].Y);
    }

    [Fact]
    public void OverwideSingleChildKeepsTheParentWidthConstraint()
    {
        var result = MessageHeaderLayoutEngine.Calculate([new(120, 16, 12)], 80, 6);
        Assert.Equal(80, result.Width);
        Assert.Equal(80, result.Children[0].Width);
        Assert.Equal(16, result.Height);
    }

    [Fact]
    public void UnavailableBaselineIsExplicitAndDoesNotInventFontMetrics()
    {
        var children = new[] { new MessageHeaderMetric(20, 16, 12), new MessageHeaderMetric(20, 14, double.NaN) };
        var result = MessageHeaderLayoutEngine.Calculate(children, 100, 6);
        Assert.False(result.UsesMeasuredBaselines);
        Assert.True(double.IsNaN(children[1].Baseline));
        Assert.Equal(16, result.Height);
        Assert.All(result.Children, child => Assert.Equal(0, child.Y));
    }

    [Fact]
    public void InitialZeroBaselineDoesNotClaimAMeasuredPositiveHeightLine()
    {
        var result = MessageHeaderLayoutEngine.Calculate([new(20, 16, 0)], 100, 6);
        Assert.False(result.UsesMeasuredBaselines);
        Assert.Equal(16, result.Height);
        Assert.Equal(0, result.Children[0].Y);
    }

    [Fact]
    public void EmptyHeaderHasNoPhantomLineOrGap()
    {
        var result = MessageHeaderLayoutEngine.Calculate([], 100, 6);
        Assert.Empty(result.Children);
        Assert.Equal(0, result.Width);
        Assert.Equal(0, result.Height);
    }
}
