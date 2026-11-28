using Relic;
using Xunit;

namespace Relic.Capture.Tests;

public sealed class NativeBannerFlexTests
{
    [Fact]
    public void NaturalWidthDoesNotGrowIntoUnusedSpace()
    {
        var input = new NativeBannerFlex.Intrinsic(120, 30);
        Assert.Equal(new NativeBannerFlex.Allocation(15, 120), NativeBannerFlex.Resolve(300, 8, 15, input));
        Assert.Equal(new NativeBannerFlex.Allocation(15, 120), NativeBannerFlex.Resolve(double.PositiveInfinity, 8, 15, input));
    }

    [Fact]
    public void NegativeSpaceUsesBothScaledShrinkFactors()
    {
        var result = NativeBannerFlex.Resolve(108, 8, 20, new(180, 40));
        Assert.Equal(10, result.Icon, 10);
        Assert.Equal(90, result.Text, 10);
        Assert.Equal(108, result.Icon + 8 + result.Text, 10);
    }

    [Fact]
    public void ActualMinimumFreezesTextAndRedistributesRemainingSpace()
    {
        var result = NativeBannerFlex.Resolve(108, 8, 20, new(180, 95));
        Assert.Equal(5, result.Icon);
        Assert.Equal(95, result.Text);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(4)]
    [InlineData(8)]
    [InlineData(50)]
    public void IndivisibleTextOverflowsInsteadOfReceivingNegativeOrInventedWidth(double available)
    {
        var result = NativeBannerFlex.Resolve(available, 8, 15, new(120, 70));
        Assert.Equal(0, result.Icon);
        Assert.Equal(70, result.Text);
    }

    [Fact]
    public void ZeroBasesAndZeroSpaceRemainNonnegative()
    {
        Assert.Equal(new NativeBannerFlex.Allocation(0, 0), NativeBannerFlex.Resolve(0, 8, 0, new(0, 0)));
        Assert.Equal(new NativeBannerFlex.Allocation(0, 0), NativeBannerFlex.Resolve(0, 8, 15, new(120, 0)));
    }

    [Fact]
    public void InvalidMeasurementsAreNotSilentlyReplaced()
    {
        foreach (var input in new[] { new NativeBannerFlex.Intrinsic(double.NaN, 0), new(double.PositiveInfinity, 0),
                     new(20, -1), new(20, 21), new(20, double.NaN) })
            Assert.Throws<ArgumentException>(() => NativeBannerFlex.Resolve(100, 8, 15, input));
        Assert.Throws<ArgumentException>(() => NativeBannerFlex.Resolve(-1, 8, 15, new(100, 20)));
        Assert.Throws<ArgumentException>(() => NativeBannerFlex.Resolve(double.NaN, 8, 15, new(100, 20)));
        Assert.Throws<ArgumentException>(() => NativeBannerFlex.Resolve(100, 8, double.MaxValue, new(double.MaxValue, 20)));
    }

    [Fact]
    public void NormalWidthsUseTheSameProductionWhitespaceAndBoundaryPolicy()
    {
        // Synthetic actual advances; neither a Windows font measurement nor
        // reference screenshot widths. Leading/trailing normal spaces are not
        // part of the painted max-content line.
        const string text = " ab cd ";
        var clusters = text.Select((character, i) => new NativePathLineBreaks.Cluster(i, 1, character == ' ' ? 3 : 8)).ToArray();
        var widths = NativeBannerFlex.NormalText(text, clusters, [0, 1, 4, 7], Enumerable.Range(0, text.Length + 1).ToArray());
        Assert.Equal(35, widths.Natural);
        Assert.Equal(16, widths.Minimum);
    }

    [Fact]
    public void CjkAndLongIndivisibleWordsKeepTheirActualBreakPolicies()
    {
        var cjk = Enumerable.Range(0, 4).Select(i => new NativePathLineBreaks.Cluster(i, 1, 12.5)).ToArray();
        Assert.Equal(new NativeBannerFlex.Intrinsic(50, 12.5), NativeBannerFlex.NormalText("验收任务", cjk, [0, 1, 2, 3, 4], [0, 1, 2, 3, 4]));
        var word = Enumerable.Range(0, 8).Select(i => new NativePathLineBreaks.Cluster(i, 1, 8)).ToArray();
        Assert.Equal(new NativeBannerFlex.Intrinsic(64, 64), NativeBannerFlex.NormalText("abcdefgh", word, [0, 8], Enumerable.Range(0, 9).ToArray()));
    }

    [Fact]
    public void MissingClusterCoverageCannotSupplyIntrinsicWidths()
    {
        Assert.Throws<ArgumentException>(() => NativeBannerFlex.NormalText("ab", [new(0, 1, 8)], [0, 2], [0, 1, 2]));
    }
}
