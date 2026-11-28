using System.Text.RegularExpressions;
using System.Threading.Channels;

namespace Relic.Core;

public sealed record PreparedInline(string Kind, string Text, bool CodePath = false);
public sealed record PreparedText(string Text, IReadOnlyList<PreparedInline> Parts);
public sealed record PreparedListItem(PreparedText Text, bool Indented);
public sealed record MarkdownBlock(string Kind, PreparedText? Text = null, string Source = "",
    string Author = "", IReadOnlyList<IReadOnlyList<PreparedText>>? Rows = null, bool TableHeading = false,
    IReadOnlyList<PreparedListItem>? Items = null, bool Ordered = false, int Start = 1);
public sealed record PreparedMarkdown(IReadOnlyList<MarkdownBlock> Blocks);

// Parsing has no XAML, preferences or live-view dependencies. The exact existing
// block precedence and inline vocabulary are retained; only their execution
// moves off the UI dispatcher.
public static class MarkdownParser
{
    public static PreparedText Inline(string text) => new(text, InlineParts.Parse(text)
        .Select(part => new PreparedInline(part.Kind, part.Text, part.Kind == "code" && InlineParts.IsAbsolute(part.Text))).ToArray());

    public static PreparedMarkdown Parse(string markdown)
    {
        var blocks = new List<MarkdownBlock>(); var lines = markdown.Replace("\r\n", "\n").Split('\n');
        for (var i = 0; i < lines.Length; i++)
        {
            var line = lines[i];
            if (line.TrimStart().StartsWith("```"))
            {
                var code = new List<string>(); while (++i < lines.Length && !lines[i].TrimStart().StartsWith("```")) code.Add(lines[i]);
                blocks.Add(new("code", Source: string.Join("\n", code))); continue;
            }
            if (Regex.IsMatch(line, @"^\s*\|.*\|\s*$"))
            {
                var table = new List<string> { line };
                while (i + 1 < lines.Length && Regex.IsMatch(lines[i + 1], @"^\s*\|.*\|\s*$")) table.Add(lines[++i]);
                bool Rule(string value) => Regex.IsMatch(value, @"^\s*\|?\s*:?-{2,}");
                var heading = table.Count > 1 && Rule(table[1]);
                var rows = table.Where(value => !Rule(value)).Select(value => (IReadOnlyList<PreparedText>)value.Trim().Trim('|').Split('|').Select(cell => Inline(cell.Trim())).ToArray()).ToArray();
                blocks.Add(new("table", Rows: rows, TableHeading: heading)); continue;
            }
            var title = Regex.Match(line, @"^(#{1,6})\s+(.+)");
            if (title.Success) { blocks.Add(new("heading", Inline(title.Groups[2].Value))); continue; }
            if (string.IsNullOrWhiteSpace(line)) continue;
            if (Regex.IsMatch(line, @"^\s*>"))
            {
                var quote = new List<string> { Regex.Replace(line, @"^\s*>\s?", "") };
                while (i + 1 < lines.Length && Regex.IsMatch(lines[i + 1], @"^\s*>")) quote.Add(Regex.Replace(lines[++i], @"^\s*>\s?", ""));
                var source = string.Join("\n", quote); var author = Regex.Match(source, @"^([^\n：:]{1,40})[：:]\s?([\s\S]*)$");
                blocks.Add(new("quote", Source: author.Success ? author.Groups[2].Value : source, Author: author.Success ? author.Groups[1].Value : "")); continue;
            }
            var list = Regex.Match(line, @"^(\s*)([-*•+]|\d+[.)])\s+(.*)$");
            if (list.Success)
            {
                var ordered = char.IsDigit(list.Groups[2].Value[0]);
                var start = ordered && int.TryParse(list.Groups[2].Value.TrimEnd('.', ')'), out var number) ? number : 1;
                var items = new List<PreparedListItem>();
                do
                {
                    var text = list.Groups[3].Value; var indented = list.Groups[1].Value.Length >= 2;
                    while (i + 1 < lines.Length && Regex.IsMatch(lines[i + 1], @"^\s{2,}\S") && !Regex.IsMatch(lines[i + 1], @"^\s*(?:>|\|.*\|\s*$|(?:[-*•+]|\d+[.)])\s+)")) text += "\n" + lines[++i].Trim();
                    items.Add(new(Inline(text), indented));
                    if (i + 1 >= lines.Length) break;
                    list = Regex.Match(lines[i + 1], @"^(\s*)([-*•+]|\d+[.)])\s+(.*)$");
                    if (!list.Success) break; i++;
                } while (true);
                blocks.Add(new("list", Items: items, Ordered: ordered, Start: start)); continue;
            }
            var paragraph = new List<string> { line };
            while (i + 1 < lines.Length && !string.IsNullOrWhiteSpace(lines[i + 1]) && !Regex.IsMatch(lines[i + 1], @"^\s*(?:```|>|#{1,6}\s|[-*•+]\s|\d+[.)]\s|\|.*\|\s*$)")) paragraph.Add(lines[++i]);
            blocks.Add(new("paragraph", Inline(string.Join("\n", paragraph))));
        }
        return new(blocks);
    }
}

// One worker for every native message/document, a fixed queue, and a bounded LRU.
// Offscreen/recycled controls cancel their requests; queued canceled jobs are
// skipped without parsing. No thread or Task.Run is created per message.
public sealed class MarkdownPreparation : IAsyncDisposable
{
    public static MarkdownPreparation Shared { get; } = new();
    private readonly record struct Key(string Text, bool Document);
    private sealed record Work(Key Key, CancellationToken Cancellation, TaskCompletionSource<object> Completion);
    private readonly Channel<Work> queue;
    private readonly Dictionary<Key, (object Value, LinkedListNode<Key> Node)> cache = new();
    private readonly LinkedList<Key> order = new();
    private readonly object sync = new();
    private readonly int entryLimit, characterLimit;
    private readonly Task worker;
    private int characters, active, peakActive;
    public MarkdownPreparation(int entryLimit = 256, int characterLimit = 2_000_000, int queueCapacity = 128)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(entryLimit, 1);
        ArgumentOutOfRangeException.ThrowIfLessThan(characterLimit, 1);
        this.entryLimit = entryLimit; this.characterLimit = characterLimit;
        queue = Channel.CreateBounded<Work>(new BoundedChannelOptions(queueCapacity) { SingleReader = true, FullMode = BoundedChannelFullMode.Wait });
        worker = Task.Run(Consume);
    }
    public async ValueTask DisposeAsync() { queue.Writer.TryComplete(); await worker.ConfigureAwait(false); }
    public (int Entries, int Characters, int PeakActive) Snapshot { get { lock (sync) return (cache.Count, characters, peakActive); } }
    public async Task<PreparedMarkdown> Document(string text, CancellationToken cancellation) => (PreparedMarkdown)await Prepare(new(text, true), cancellation).ConfigureAwait(false);
    public async Task<PreparedText> Inline(string text, CancellationToken cancellation) => (PreparedText)await Prepare(new(text, false), cancellation).ConfigureAwait(false);
    private async Task<object> Prepare(Key key, CancellationToken cancellation)
    {
        cancellation.ThrowIfCancellationRequested();
        lock (sync)
            if (cache.TryGetValue(key, out var found)) { order.Remove(found.Node); order.AddLast(found.Node); return found.Value; }
        var completion = new TaskCompletionSource<object>(TaskCreationOptions.RunContinuationsAsynchronously);
        await queue.Writer.WriteAsync(new(key, cancellation, completion), cancellation).ConfigureAwait(false);
        return await completion.Task.WaitAsync(cancellation).ConfigureAwait(false);
    }
    private async Task Consume()
    {
        await foreach (var work in queue.Reader.ReadAllAsync().ConfigureAwait(false))
        {
            if (work.Cancellation.IsCancellationRequested) { work.Completion.TrySetCanceled(work.Cancellation); continue; }
            try
            {
                object value;
                lock (sync)
                {
                    if (cache.TryGetValue(work.Key, out var found)) { work.Completion.TrySetResult(found.Value); continue; }
                    active++; peakActive = Math.Max(peakActive, active);
                }
                try { value = work.Key.Document ? MarkdownParser.Parse(work.Key.Text) : MarkdownParser.Inline(work.Key.Text); }
                finally { lock (sync) active--; }
                lock (sync)
                {
                    if (work.Key.Text.Length <= characterLimit)
                    {
                        while (cache.Count >= entryLimit || characters + work.Key.Text.Length > characterLimit)
                        { var oldest = order.First!; characters -= oldest.Value.Text.Length; cache.Remove(oldest.Value); order.RemoveFirst(); }
                        var node = order.AddLast(work.Key); cache.Add(work.Key, (value, node)); characters += work.Key.Text.Length;
                    }
                }
                work.Completion.TrySetResult(value);
            }
            catch (Exception error) { work.Completion.TrySetException(error); }
        }
    }
}
