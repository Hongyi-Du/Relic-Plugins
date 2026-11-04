using Relic;
using Xunit;

namespace Relic.Capture.Tests;

public sealed class NativeSelectableTextLayoutTests
{
    // These are controlled shaping/break fixtures. They test the production
    // policy; they do not claim to measure any installed font or live UI.
    private static NativePathLineBreaks.Cluster[] Units(string text) =>
        Enumerable.Range(0, text.Length).Select(i => new NativePathLineBreaks.Cluster(i, 1, 1)).ToArray();
    private static int[] Characters(string text) => Enumerable.Range(0, text.Length + 1).ToArray();

    [Fact]
    public void ExistingPathStyleAndSourceStayUnchanged()
    {
        var style = NativeSelectableTextStyle.Path("actual configured UI family");
        Assert.Equal("Cascadia Code", style.Family); Assert.Equal(11.5, style.Size);
        Assert.Equal(18.4, style.LineHeight); Assert.Equal(12.5, style.StrutSize); Assert.Equal(20, style.StrutLineHeight);
        Assert.False(style.NormalWhitespace); Assert.False(style.Center);
        const string source = "C:\\a  b\tfile\r\nnext";
        var map = NativeTextSourceMap.Create(source, style.NormalWhitespace);
        Assert.Equal(source, map.Paint);
        for (var i = 0; i <= source.Length; i++)
        { Assert.Equal(i, map.SourceStart(i)); Assert.Equal(i, map.SourceEnd(i)); Assert.Equal(i, map.PaintPosition(i)); }
        Assert.Equal((2, 9), map.PaintRange(2, 9));
    }

    [Fact]
    public void NoticeStyleHasItsOwnUiFontLineBoxWithoutThePathStrut()
    {
        var style = NativeSelectableTextStyle.Notice("actual configured UI family");
        Assert.Equal("actual configured UI family", style.Family); Assert.Equal(12, style.Size);
        Assert.Equal(19.2, style.LineHeight); Assert.Equal((ushort)400, style.Weight);
        Assert.True(style.Center); Assert.True(style.NormalWhitespace); Assert.Null(style.StrutFamily);
    }

    [Fact]
    public void PathStillEmergencyWrapsTheSameLongWord()
    {
        const string source = "abcdef";
        var lines = NativePathLineBreaks.Select(source.Length, Units(source), [0, 6], Characters(source), 3);
        Assert.Equal(new[] { new NativePathLineBreaks.Line(0, 3, true), new(3, 6, false) }, lines);
    }

    [Fact]
    public void NoticeRetainsOriginalNewlinesAndMapsCollapsedWhiteSpace()
    {
        const string source = "A \t\r\n B";
        var map = NativeTextSourceMap.Create(source, true);
        Assert.Equal(source, map.Source); Assert.Equal("A B", map.Paint);
        Assert.Equal(new NativeTextSourceMap.Span(1, 1, 6), map.Spans[1]);
        Assert.Equal((1, 2), map.PaintRange(3, 5)); // selecting the original CR/LF selects its painted space
        Assert.Equal("\r\n", map.Source[3..5]);
        Assert.Equal(1, map.SourceHit(1, 0, 3)); Assert.Equal(6, map.SourceHit(2, 0, 3));
        Assert.Equal(7, map.SourceHit(3, 0, 3));
        Assert.Equal(source, map.Source[..]); // select-all/copy uses untouched source, not Paint
    }

    [Fact]
    public void NormalWhiteSpacePreservesNbspSurrogatesAndCjkSource()
    {
        const string source = "甲\r\n乙\u00a0😀";
        var map = NativeTextSourceMap.Create(source, true);
        Assert.Equal("甲 乙\u00a0😀", map.Paint); Assert.Equal(source, map.Source);
        Assert.Equal((4, 6), map.PaintRange(5, 7));
        Assert.Equal(5, map.SourceStart(4)); Assert.Equal(7, map.SourceEnd(6));
    }

    [Fact]
    public void NewlineNextToZwspIsRemovedWithoutDeletingTheOriginalRange()
    {
        var map = NativeTextSourceMap.Create("a\u200b\r\n b", true);
        Assert.Equal("a\u200bb", map.Paint);
        Assert.Equal("\r\n ", map.Source[2..5]); Assert.Equal((3, 3), map.PaintRange(2, 5));
        Assert.Equal(5, map.SourceStart(2));
    }

    [Fact]
    public void FormFeedIsNotClassifiedAsCollapsibleNormalWhitespace()
    {
        var map = NativeTextSourceMap.Create("a\f b", true);
        Assert.Equal("a\f b", map.Paint);
        Assert.Equal(new NativeTextSourceMap.Span(1, 1, 2), map.Spans[1]);
    }

    [Fact]
    public void WhitespaceAtLineEdgesDoesNotConsumeLineWidth()
    {
        const string text = " a b c ";
        var lines = NativeSelectableTextLayout.NoticeLines(text, Units(text), [0, 1, 3, 5, 7], Characters(text), 3);
        Assert.Equal(new[] { new NativeSelectableTextLayout.Line(1, 4, false), new(5, 6, false) }, lines);
        Assert.Equal("a b", text[lines[0].Start..lines[0].End]);
    }

    [Fact]
    public void CjkWrapsAtActualNormalBoundariesWithoutEmergencyBreaks()
    {
        const string text = "甲乙丙丁";
        var lines = NativeSelectableTextLayout.NoticeLines(text, Units(text), [0, 1, 2, 3, 4], Characters(text), 2);
        Assert.Equal(new[] { new NativeSelectableTextLayout.Line(0, 2, false), new(2, 4, false) }, lines);
    }

    [Fact]
    public void LongWordOverflowsAndIsCenteredWithoutLosingAnySource()
    {
        const string text = "abcdef gh";
        var lines = NativeSelectableTextLayout.NoticeLines(text, Units(text), [0, 7, 9], Characters(text), 3);
        Assert.Equal(new[] { new NativeSelectableTextLayout.Line(0, 6, false), new(7, 9, false) }, lines);
        var firstX = NativeSelectableTextLayout.LineX(3, 6, true);
        var nextX = NativeSelectableTextLayout.LineX(3, 2, true);
        Assert.Equal(-1.5, firstX); Assert.Equal(.5, nextX);
        var ownerX = NativeSelectableTextLayout.OwnerX(2.5, firstX);
        Assert.Equal(.5, NativeSelectableTextLayout.LocalX(ownerX, nextX)); // actual X used by vertical selection
        Assert.Equal(2.5, NativeSelectableTextLayout.LocalX(ownerX, firstX)); // hit-test inverse
    }

    [Fact]
    public void ShapedClusterCannotBeSplitByAReportedBreak()
    {
        const string text = "😀中";
        var lines = NativeSelectableTextLayout.NoticeLines(text, [new(0, 2, 2), new(2, 1, 1)],
            [0, 1, 2, 3], [0, 2, 3], 1);
        Assert.Equal(new[] { new NativeSelectableTextLayout.Line(0, 2, false), new(2, 3, false) }, lines);
    }

    [Fact]
    public void WhitespaceOnlySourceIsPreservedWithoutInventingGlyphs()
    {
        var map = NativeTextSourceMap.Create(" \r\n\t", true);
        Assert.Equal(" ", map.Paint); Assert.Equal(" \r\n\t", map.Source);
        Assert.Empty(NativeSelectableTextLayout.NoticeLines(map.Paint, Units(map.Paint), [0, 1], [0, 1], 10));
    }

    [Fact]
    public void InvalidMeasurementFailsInsteadOfFabricatingLineGeometry()
    {
        Assert.Throws<ArgumentException>(() => NativeSelectableTextLayout.NoticeLines("ab", [new(0, 1, 1)], [0, 2], [0, 1, 2], 20));
        Assert.Throws<ArgumentException>(() => NativeSelectableTextLayout.NoticeLines("a", [new(0, 1, double.NaN)], [0, 1], [0, 1], 20));
        Assert.Throws<ArgumentException>(() => NativeSelectableTextLayout.LineX(double.NaN, 10, true));
    }
}
