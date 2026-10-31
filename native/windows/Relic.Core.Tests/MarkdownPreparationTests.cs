using Relic.Core;
using Xunit;

namespace Relic.Core.Tests;

public sealed class MarkdownPreparationTests
{
    [Fact]
    public void BlocksRetainExistingPrecedenceContentAndListNumbering()
    {
        var parsed = MarkdownParser.Parse("# Header **bold**\n\nfirst\nsecond\n\n> Alice: quoted\n> continuation\n\n3. first\n  continuation\n  - indented\n\n```cs\nvar x = 1;\n```\n\n| A | B |\n| -- | -- |\n| one | `two` |");
        Assert.Equal(new[] { "heading", "paragraph", "quote", "list", "code", "table" }, parsed.Blocks.Select(block => block.Kind));
        Assert.Equal("first\nsecond", parsed.Blocks[1].Text!.Text);
        Assert.Equal("Alice", parsed.Blocks[2].Author);
        Assert.Equal("quoted\ncontinuation", parsed.Blocks[2].Source);
        Assert.True(parsed.Blocks[3].Ordered); Assert.Equal(3, parsed.Blocks[3].Start);
        Assert.Equal("first\ncontinuation", parsed.Blocks[3].Items![0].Text.Text);
        Assert.True(parsed.Blocks[3].Items![1].Indented);
        Assert.Equal("var x = 1;", parsed.Blocks[4].Source);
        Assert.True(parsed.Blocks[5].TableHeading); Assert.Equal(2, parsed.Blocks[5].Rows!.Count);
        Assert.Equal("code", parsed.Blocks[5].Rows![1][1].Parts.Single().Kind);
    }

    [Fact]
    public void InlinePreparationPreservesSourceAndClickableCodePaths()
    {
        var inline = MarkdownParser.Inline("**bold** `/tmp/report.md:12` `literal` https://example.com/a S:\\work\\file.cs");
        Assert.Contains(inline.Parts, part => part.Kind == "bold" && part.Text == "bold");
        Assert.Contains(inline.Parts, part => part.Kind == "code" && part.CodePath && part.Text == "/tmp/report.md:12");
        Assert.Contains(inline.Parts, part => part.Kind == "code" && !part.CodePath && part.Text == "literal");
        Assert.Contains(inline.Parts, part => part.Kind == "url");
        Assert.Contains(inline.Parts, part => part.Kind == "path");
    }

    [Fact]
    public async Task QueueUsesOneParserAndCacheStaysWithinBothBounds()
    {
        await using var preparation = new MarkdownPreparation(entryLimit: 3, characterLimit: 100, queueCapacity: 2);
        var documents = await Task.WhenAll(Enumerable.Range(0, 40).Select(index => preparation.Document("**item** " + index + "\n\n" + new string('x', 24), CancellationToken.None)));
        Assert.Equal(40, documents.Length);
        var bounds = preparation.Snapshot;
        Assert.InRange(bounds.Entries, 1, 3); Assert.InRange(bounds.Characters, 1, 100); Assert.Equal(1, bounds.PeakActive);
        var one = await preparation.Inline("cache me", CancellationToken.None);
        var two = await preparation.Inline("cache me", CancellationToken.None);
        Assert.Same(one, two);
    }

    [Fact]
    public async Task CanceledOffscreenRequestDoesNotEnterCache()
    {
        await using var preparation = new MarkdownPreparation();
        using var cancellation = new CancellationTokenSource(); cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => preparation.Document("offscreen message", cancellation.Token));
        Assert.Equal(0, preparation.Snapshot.Entries);
    }
}
