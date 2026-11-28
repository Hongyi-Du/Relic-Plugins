using System.Runtime.InteropServices;
using Relic;
using Xunit;

public sealed class TextRangeFormatEnumerationTests
{
    [Fact]
    public void ActualFormatEndpointsAreClampedToTheObservedParentWithoutChangingIt()
    {
        var source = new Source("abcdefghi", [3, 6, 9]);
        var parent = new Range(source, 1, 8);
        var observed = new List<(int Start, int End, ProbeFormatStep Step)>();
        Assert.Equal(3, TextRangeFormatEnumeration.Capture(parent,
            (range, step) => observed.Add((((Range)range).Start, ((Range)range).End, step))));
        Assert.Equal(new[] { (1, 3), (3, 6), (6, 8) }, observed.Select(value => (value.Start, value.End)));
        Assert.Equal(1, parent.Start); Assert.Equal(8, parent.End);
        Assert.True(observed[2].Step.EndVsParentEndBeforeClamp > 0);
        Assert.Equal(0, observed[2].Step.EndVsParentEndAfterClamp);
        Assert.All(observed, value => Assert.Equal(0, value.Step.StartVsPreviousStart));
        Assert.Equal(3, source.FormatCalls);
    }

    [Fact]
    public void RepeatedTextAndSurrogatePairsRetainTheirIndependentUtf16Spans()
    {
        var parent = new Range(new Source("aa\U0001F600aa", [2, 4, 6]), 0, 6);
        var observed = new List<(int, int, string)>();
        TextRangeFormatEnumeration.Capture(parent, (range, _) =>
        {
            var actual = (Range)range;
            observed.Add((actual.Start, actual.End, actual.Text));
        });
        Assert.Equal(new[] { (0, 2, "aa"), (2, 4, "\U0001F600"), (4, 6, "aa") }, observed);
    }

    [Fact]
    public void ComparisonsAreOrderingEvidenceNotCharacterOffsets()
    {
        // This provider deliberately returns magnitudes unrelated to distance.
        var parent = new Range(new Source("abcd", [2, 4]), 0, 4);
        var steps = new List<ProbeFormatStep>();
        Assert.Equal(2, TextRangeFormatEnumeration.Capture(parent, (_, step) => steps.Add(step)));
        Assert.All(steps, step => Assert.Equal(37, step.EndVsPreviousEnd));
        Assert.All(steps, step => Assert.Equal(-37, step.StartVsEnd));
    }

    [Fact]
    public void DegenerateParentHasAnObservedEmptyEnumeration()
    {
        var source = new Source("abc", [3]);
        Assert.Equal(0, TextRangeFormatEnumeration.Capture(new Range(source, 1, 1),
            (_, _) => throw new InvalidOperationException("No nondegenerate range exists")));
        Assert.Equal(0, source.FormatCalls);
    }

    [Fact]
    public void ReversedParentFailsBeforeAnyFormatMeasurement()
    {
        var source = new Source("abc", [3]);
        Assert.Throws<InvalidOperationException>(() => TextRangeFormatEnumeration.Capture(new Range(source, 2, 1), (_, _) => { }));
        Assert.Equal(0, source.FormatCalls);
    }

    [Theory]
    [InlineData("no-advance")]
    [InlineData("negative-move")]
    [InlineData("changed-start")]
    [InlineData("ignored-clamp")]
    public void InvalidProviderStepIsObservedThenFailsWithoutRepair(string fault)
    {
        var source = new Source("abcdef", [3, 6]) { Fault = fault };
        var parent = new Range(source, 0, fault == "ignored-clamp" ? 2 : 6);
        var observed = new List<(int, int, ProbeFormatStep)>();
        Assert.Throws<InvalidOperationException>(() => TextRangeFormatEnumeration.Capture(parent,
            (range, step) => observed.Add((((Range)range).Start, ((Range)range).End, step))));
        var actual = Assert.Single(observed);
        if (fault == "no-advance") { Assert.Equal(0, actual.Item2); Assert.Equal(0, actual.Item3.UnitsMoved); }
        if (fault == "negative-move") Assert.Equal(-1, actual.Item3.UnitsMoved);
        if (fault == "changed-start") Assert.Equal(1, actual.Item1);
        if (fault == "ignored-clamp") { Assert.Equal(3, actual.Item2); Assert.True(actual.Item3.EndVsParentEndAfterClamp > 0); }
        Assert.Equal(1, source.FormatCalls);
    }

    [Fact]
    public void ProviderExceptionRetainsEarlierMeasurementsAndOriginalHresult()
    {
        var failure = new COMException("actual mock provider failure", unchecked((int)0x8000FFFF));
        var source = new Source("abcdef", [3, 6]) { ThrowOnFormatCall = 2, Failure = failure };
        var spans = new List<(int, int)>();
        var caught = Assert.Throws<COMException>(() => TextRangeFormatEnumeration.Capture(new Range(source, 0, 6),
            (range, _) => spans.Add((((Range)range).Start, ((Range)range).End))));
        Assert.Same(failure, caught);
        Assert.Equal(unchecked((int)0x8000FFFF), caught.HResult);
        Assert.Equal(new[] { (0, 3) }, spans);
    }

    [Fact]
    public void IncompleteBoundedEnumerationRetainsTheActualPrefixAndFails()
    {
        var source = new Source("abcdef", [2, 4, 6]);
        var spans = new List<(int, int)>();
        var error = Assert.Throws<InvalidOperationException>(() => TextRangeFormatEnumeration.Capture(new Range(source, 0, 6),
            (range, _) => spans.Add((((Range)range).Start, ((Range)range).End)), maximumRuns: 1));
        Assert.Contains("coverage is incomplete", error.Message);
        Assert.Equal(new[] { (0, 2) }, spans); Assert.Equal(1, source.FormatCalls);
    }

    [Fact]
    public void EachFormatCallsItsOwnBoundsObserverAndPreservesProviderNumbers()
    {
        var raw = new[] { 1117d, 899.5999755859375, 180d, 0.4000244140625,
            0d, 0d, 10d, 0d, double.NaN, 2d, -1d, double.PositiveInfinity };
        var source = new Source("aabb", [2, 4]) { Bounds = raw };
        var snapshots = new List<double[]>();
        TextRangeFormatEnumeration.Capture(new Range(source, 0, 4), (range, _) => snapshots.Add(((Range)range).ReadBounds()));
        Assert.Equal(2, source.BoundsReads); Assert.Equal(2, snapshots.Count);
        Assert.All(snapshots, actual => Assert.Same(raw, actual));
        Assert.Equal(0.4000244140625, raw[3]); Assert.Equal(0, raw[7]);
        Assert.True(double.IsNaN(raw[8])); Assert.Equal(-1, raw[10]); Assert.True(double.IsPositiveInfinity(raw[11]));
    }

    private sealed class Source(string text, int[] boundaries)
    {
        internal string Text { get; } = text;
        internal int[] Boundaries { get; } = boundaries;
        internal string? Fault { get; init; }
        internal int FormatCalls, BoundsReads;
        internal int ThrowOnFormatCall { get; init; }
        internal Exception? Failure { get; init; }
        internal double[] Bounds { get; init; } = [];
    }

    private sealed class Range(Source source, int start, int end) : IProbeFormatRange
    {
        internal int Start { get; private set; } = start;
        internal int End { get; private set; } = end;
        internal string Text => source.Text.Substring(Start, End - Start);
        internal double[] ReadBounds() { source.BoundsReads++; return source.Bounds; }
        public IProbeFormatRange Clone() => new Range(source, Start, End);
        private int At(ProbeRangeEndpoint endpoint) => endpoint == ProbeRangeEndpoint.Start ? Start : End;
        public int CompareEndpoints(ProbeRangeEndpoint endpoint, IProbeFormatRange other, ProbeRangeEndpoint otherEndpoint)
            => Math.Sign(At(endpoint) - ((Range)other).At(otherEndpoint)) * 37;
        public void MoveEndpointByRange(ProbeRangeEndpoint endpoint, IProbeFormatRange other, ProbeRangeEndpoint otherEndpoint)
        {
            if (source.Fault == "ignored-clamp" && endpoint == ProbeRangeEndpoint.End && !ReferenceEquals(this, other)) return;
            var value = ((Range)other).At(otherEndpoint);
            if (endpoint == ProbeRangeEndpoint.Start) { Start = value; if (Start > End) End = Start; }
            else { End = value; if (End < Start) Start = End; }
        }
        public int MoveEndByOneFormat()
        {
            source.FormatCalls++;
            if (source.FormatCalls == source.ThrowOnFormatCall) throw source.Failure!;
            if (source.Fault == "no-advance") return 0;
            End = source.Boundaries.First(value => value > End);
            if (source.Fault == "changed-start") Start++;
            return source.Fault == "negative-move" ? -1 : 1;
        }
    }
}
