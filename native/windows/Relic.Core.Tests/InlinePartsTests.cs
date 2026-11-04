using Relic.Core;
using Xunit;

public class InlinePartsTests
{
    [Fact] public void UnsupportedMarkdownKeepsItsVisibleMarkers()
    {
        var parts = InlineParts.Parse("*em* _other_ [read](https://example.com/a) [file](/tmp/a.py) [label](relative.md)").ToArray();
        Assert.Equal(new[]
        {
            new InlinePart("text", "*em* _other_ [read]("),
            new InlinePart("url", "https://example.com/a", "https://example.com/a"),
            new InlinePart("text", ") [file]("),
            new InlinePart("path", "/tmp/a.py", "/tmp/a.py"),
            new InlinePart("text", ") [label](relative.md)")
        }, parts);
    }

    [Fact] public void CodeAndBoldAreSingleTokensWithoutNestedParsing()
    {
        Assert.Equal(new[]
        {
            new InlinePart("code", "/tmp/a b.py:9"),
            new InlinePart("text", " "),
            new InlinePart("code", "https://example.com/a"),
            new InlinePart("text", " "),
            new InlinePart("bold", "use `code` /tmp/x")
        }, InlineParts.Parse("`/tmp/a b.py:9` `https://example.com/a` **use `code` /tmp/x**").ToArray());
    }

    [Fact] public void UrlConsumesItsPathAndBarePathsKeepTrailingPunctuationOutside()
    {
        Assert.Equal(new[]
        {
            new InlinePart("url", "https://example.com/a/b?x=1.", "https://example.com/a/b?x=1."),
            new InlinePart("text", " "),
            new InlinePart("path", "/tmp/a.py:12:3", "/tmp/a.py:12:3"),
            new InlinePart("text", ".,;:!"),
            new InlinePart("text", "?， relative/file.md //server/share")
        }, InlineParts.Parse("https://example.com/a/b?x=1. /tmp/a.py:12:3.,;:!?， relative/file.md //server/share").ToArray());
    }

    [Fact] public void ReferenceUsesAsciiWordBoundariesAroundBarePaths()
    {
        Assert.Equal(new[]
        {
            new InlinePart("text", "é"), new InlinePart("path", "/tmp/a", "/tmp/a"),
            new InlinePart("text", " 中"), new InlinePart("path", "C:\\work\\b", "C:\\work\\b"),
            new InlinePart("text", " x/tmp/c ./tmp/d")
        }, InlineParts.Parse("é/tmp/a 中C:\\work\\b x/tmp/c ./tmp/d").ToArray());
    }

    [Fact] public void ReferenceWhitespaceStopsBomButRetainsNextLineCharacterInUrls()
    {
        var address = "https://example.com/a\u0085b";
        Assert.Equal(new[]
        {
            new InlinePart("url", address, address),
            new InlinePart("text", "\uFEFF"),
            new InlinePart("path", "/tmp/c", "/tmp/c")
        }, InlineParts.Parse(address + "\uFEFF/tmp/c").ToArray());
    }

    [Theory]
    [InlineData("/tmp/a b.py:12:3", "/tmp/a b.py", 12)]
    [InlineData("C:\\work folder\\x.cs:4", "C:\\work folder\\x.cs", 4)]
    [InlineData("C:/work/x.cs", "C:/work/x.cs", 0)]
    [InlineData("/tmp/a.py:١٢", "/tmp/a.py:١٢", 0)]
    public void CodePathPreviewRetainsSpacesAndSourceLine(string source, string path, int line)
    {
        var code = Assert.Single(InlineParts.Parse("`" + source + "`"));
        Assert.Equal("code", code.Kind);
        Assert.True(InlineParts.IsAbsolute(code.Text));
        Assert.Equal((path, line), InlineParts.PathTarget(code.Text));
    }
}
