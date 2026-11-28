using Xunit;

namespace Relic.Core.Tests;

public sealed class NativePathLineBreakTests
{
    private static NativePathLineBreaks.Cluster[] Units(int length, double width = 1) =>
        Enumerable.Range(0, length).Select(i => new NativePathLineBreaks.Cluster(i, 1, width)).ToArray();
    private static int[] Characters(int length) => Enumerable.Range(0, length + 1).ToArray();

    [Fact]
    public void RecordedIcuOpportunitiesDifferFromDwriteDirectoryBreaks()
    {
        // efeaf76 member-card-model.path-line-break-probe.json: actual 64
        // one-unit clusters, actual width, ICU boundaries and cluster advance.
        // These inputs test policy only; they do not represent a rendered test.
        var clusters = Units(64, 6.7382812);
        var icu = new[] { 0, 2, 11, 25, 56, 64 };
        var lines = NativePathLineBreaks.Select(64, clusters, icu, Characters(64), 238);
        Assert.Equal(new[] { 25, 56, 64 }, lines.Select(line => line.End));
        Assert.All(lines, line => Assert.False(line.Emergency));
        var dwrite = new[] { 0, 2, 4, 11, 18, 25, 32, 39, 47, 52, 56, 58, 64 };
        Assert.Equal(new[] { 32, 64 }, NativePathLineBreaks.Select(64, clusters, dwrite, Characters(64), 238).Select(line => line.End));
    }

    [Fact]
    public void NormalOpportunityWinsOverLaterEmergencyBoundary()
    {
        var lines = NativePathLineBreaks.Select(10, Units(10), new[] { 0, 3, 10 }, Characters(10), 6);
        Assert.Equal(new[] { 3, 9, 10 }, lines.Select(line => line.End));
        Assert.Equal(new[] { false, true, false }, lines.Select(line => line.Emergency));
    }

    [Fact]
    public void EmergencyNeverSplitsMeasuredClusterOrUnicodeGrapheme()
    {
        var clusters = new[] { new NativePathLineBreaks.Cluster(0, 2, 5), new NativePathLineBreaks.Cluster(2, 1, 2),
            new NativePathLineBreaks.Cluster(3, 1, 0), new NativePathLineBreaks.Cluster(4, 1, 2) };
        var lines = NativePathLineBreaks.Select(5, clusters, new[] { 0, 5 }, new[] { 0, 2, 4, 5 }, 3);
        Assert.Equal(new[] { 2, 4, 5 }, lines.Select(line => line.End));
        Assert.Equal(0, lines[0].Start);
        Assert.True(lines[0].Emergency); // One indivisible cluster can exceed available width.
    }

    [Fact]
    public void WidthChangesLineChoicesWithoutEditingSource()
    {
        var widths = new[] { 2d, 4d, 8d };
        var counts = widths.Select(width => NativePathLineBreaks.Select(8, Units(8), new[] { 0, 2, 4, 6, 8 }, Characters(8), width).Count);
        Assert.Equal(new[] { 4, 2, 1 }, counts);
        Assert.Single(NativePathLineBreaks.Select(2, Units(2), new[] { 0, 2 }, Characters(2), 2));
        Assert.Empty(NativePathLineBreaks.Select(0, [], new[] { 0 }, new[] { 0 }, 0));
    }

    [Fact]
    public void MissingOrInvalidActualMeasurementsAreRejected()
    {
        Assert.Throws<ArgumentException>(() => NativePathLineBreaks.Select(3, Units(2), new[] { 0, 3 }, Characters(3), 3));
        Assert.Throws<ArgumentException>(() => NativePathLineBreaks.Select(2, Units(2), new[] { 0 }, Characters(2), 2));
        Assert.Throws<ArgumentException>(() => NativePathLineBreaks.Select(2, Units(2, double.NaN), new[] { 0, 2 }, Characters(2), 2));
        Assert.Throws<ArgumentException>(() => NativePathLineBreaks.Select(2, Units(2), new[] { 0, 2, 3 }, Characters(2), 2));
        Assert.Throws<ArgumentOutOfRangeException>(() => NativePathLineBreaks.Select(2, Units(2), new[] { 0, 2 }, Characters(2), double.NaN));
    }

    [Fact]
    public void TextUnitMovementPreservesZeroCountAndSourceEndpoints()
    {
        var points = new[] { 0, 2, 7, 9 };
        Assert.Equal(4, NativePathLineBreaks.Move(points, 4, 0, out var moved)); Assert.Equal(0, moved);
        Assert.Equal(7, NativePathLineBreaks.Move(points, 4, 1, out moved)); Assert.Equal(1, moved);
        Assert.Equal(2, NativePathLineBreaks.Move(points, 4, -1, out moved)); Assert.Equal(-1, moved);
        Assert.Equal(9, NativePathLineBreaks.Move(points, 7, int.MaxValue, out moved)); Assert.Equal(1, moved);
        Assert.Equal(0, NativePathLineBreaks.Move(points, 2, int.MinValue, out moved)); Assert.Equal(-1, moved);
    }

    [Fact]
    public void ActualParentAndInlineMetricsBothContributeToTheStrut()
    {
        var (ascent, descent) = NativePathLineBreaks.LineBox(14, 20, 15, 18.4);
        Assert.Equal(15, ascent); Assert.Equal(6, descent);
        (ascent, descent) = NativePathLineBreaks.LineBox(14, 20, 12, 18.4);
        Assert.Equal(14, ascent); Assert.Equal(6.4, descent, 10);
        Assert.Throws<ArgumentException>(() => NativePathLineBreaks.LineBox(double.NaN, 20, 12, 18.4));
    }
}
