using System.Text;

namespace Relic;

// Production policy shared by selectable path text and normal-whitespace notices.
// Source offsets always address the untouched original string; paint offsets
// address the actual string supplied to the retained NativeLabel line objects.
internal sealed record NativeSelectableTextStyle(string Kind, string Family, double Size,
    ushort Weight, double LineHeight, bool Center, bool NormalWhitespace,
    string? StrutFamily, double StrutSize, double StrutLineHeight)
{
    internal static NativeSelectableTextStyle Path(string uiFamily) =>
        new("path", "Cascadia Code", 11.5, 400, 18.4, false, false, uiFamily, 12.5, 20);
    internal static NativeSelectableTextStyle Notice(string uiFamily) =>
        new("notice", uiFamily, 12, 400, 19.2, true, true, null, 0, 0);
    internal static NativeSelectableTextStyle Banner(string uiFamily) =>
        new("banner", uiFamily, 12.5, 400, 20, false, true, null, 0, 0);
}

internal sealed class NativeTextSourceMap
{
    internal readonly record struct Span(int PaintStart, int SourceStart, int SourceEnd);
    internal string Source { get; }
    internal string Paint { get; }
    internal IReadOnlyList<Span> Spans { get; }

    private NativeTextSourceMap(string source, string paint, IReadOnlyList<Span> spans)
    { Source = source; Paint = paint; Spans = spans; }

    internal static NativeTextSourceMap Create(string source, bool normalWhitespace)
    {
        var paint = new StringBuilder(); var spans = new List<Span>();
        for (var i = 0; i < source.Length;)
        {
            var start = i;
            if (normalWhitespace && IsCollapsible(source[i]))
            {
                var newline = false;
                while (i < source.Length && IsCollapsible(source[i]))
                { newline |= source[i] is '\r' or '\n'; i++; }
                // Blink's normal-white-space segment-break rule removes a
                // newline adjacent to ZWSP; CJK-wide removal is disabled there.
                // https://source.chromium.org/chromium/chromium/src/+/main:third_party/blink/renderer/core/layout/inline/inline_items_builder.cc
                if (newline && (start > 0 && source[start - 1] == '\u200b'
                    || i < source.Length && source[i] == '\u200b')) continue;
                spans.Add(new Span(paint.Length, start, i)); paint.Append(' ');
            }
            else
            { spans.Add(new Span(paint.Length, i, i + 1)); paint.Append(source[i++]); }
        }
        return new(source, paint.ToString(), spans);
    }

    // Blink's actual IsCollapsibleSpace excludes form feed and NBSP.
    private static bool IsCollapsible(char value) => value is ' ' or '\t' or '\r' or '\n';

    internal int SourceStart(int paintPosition)
    {
        if (paintPosition < 0 || paintPosition > Paint.Length) throw new ArgumentOutOfRangeException(nameof(paintPosition));
        return paintPosition < Spans.Count ? Spans[paintPosition].SourceStart : Source.Length;
    }
    internal int SourceEnd(int paintPosition)
    {
        if (paintPosition < 0 || paintPosition > Paint.Length) throw new ArgumentOutOfRangeException(nameof(paintPosition));
        return paintPosition > 0 ? Spans[paintPosition - 1].SourceEnd : 0;
    }
    internal int SourceHit(int paintPosition, int lineStart, int lineEnd) =>
        paintPosition >= lineEnd ? SourceEnd(lineEnd) : SourceStart(Math.Max(lineStart, paintPosition));
    internal int PaintPosition(int sourcePosition)
    {
        sourcePosition = Math.Clamp(sourcePosition, 0, Source.Length);
        for (var i = 0; i < Spans.Count; i++)
            if (sourcePosition < Spans[i].SourceEnd) return i;
        return Paint.Length;
    }
    internal (int Start, int End) PaintRange(int sourceStart, int sourceEnd)
    {
        if (sourceStart < 0 || sourceEnd < sourceStart || sourceEnd > Source.Length)
            throw new ArgumentOutOfRangeException(nameof(sourceStart));
        var start = Spans.Count; var end = start;
        if (sourceStart == sourceEnd) return (PaintPosition(sourceStart), PaintPosition(sourceStart));
        for (var i = 0; i < Spans.Count; i++)
            if (Spans[i].SourceEnd > sourceStart && Spans[i].SourceStart < sourceEnd)
            { start = Math.Min(start, i); end = i + 1; }
        return (start, end);
    }
}

internal static class NativeSelectableTextLayout
{
    internal readonly record struct Line(int Start, int End, bool Emergency);

    // normal wrapping: discard collapsible spaces at line edges; break only at
    // measured ICU/cluster boundaries. An indivisible overlong word overflows;
    // the cwd's emergency-break policy is intentionally not used here.
    internal static IReadOnlyList<Line> NoticeLines(string paint,
        IReadOnlyList<NativePathLineBreaks.Cluster> clusters,
        IReadOnlyCollection<int> normalBoundaries, IReadOnlyCollection<int> characterBoundaries, double width)
    {
        if (!double.IsFinite(width) || width < 0) throw new ArgumentOutOfRangeException(nameof(width));
        var advances = new SortedDictionary<int, double> { [0] = 0 };
        var position = 0; double advance = 0;
        foreach (var cluster in clusters)
        {
            if (cluster.Start != position || cluster.Length <= 0 || cluster.Length > paint.Length - position
                || !double.IsFinite(cluster.Width) || cluster.Width < 0)
                throw new ArgumentException("Actual clusters must cover the complete paint string");
            position += cluster.Length; advance += cluster.Width; advances[position] = advance;
        }
        if (position != paint.Length || !normalBoundaries.Contains(0) || !normalBoundaries.Contains(paint.Length)
            || !characterBoundaries.Contains(0) || !characterBoundaries.Contains(paint.Length)
            || normalBoundaries.Concat(characterBoundaries).Any(n => n < 0 || n > paint.Length))
            throw new ArgumentException("Actual boundaries must cover the complete paint string");
        var normal = normalBoundaries.Where(n => advances.ContainsKey(n) && characterBoundaries.Contains(n)).Order().ToArray();
        var result = new List<Line>(); var start = 0;
        while (start < paint.Length)
        {
            while (start < paint.Length && paint[start] == ' ') start++;
            if (start == paint.Length) break;
            if (!advances.ContainsKey(start)) throw new ArgumentException("Leading-space boundary splits a shaped cluster");
            var options = normal.Where(n => n > start).Select(n =>
            {
                var end = n;
                while (end > start && paint[end - 1] == ' ') end--;
                if (!advances.ContainsKey(end)) throw new ArgumentException("Trailing-space boundary splits a shaped cluster");
                return (Consume: n, End: end, Width: advances[end] - advances[start]);
            }).Where(n => n.End > start).ToArray();
            if (options.Length == 0) throw new ArgumentException("No progressing normal text boundary");
            var fitting = options.Where(n => n.Width <= width).ToArray();
            var chosen = fitting.Length > 0 ? fitting[^1] : options[0];
            result.Add(new(start, chosen.End, false)); start = chosen.Consume;
        }
        return result;
    }

    internal static double LineX(double viewportWidth, double lineWidth, bool center)
    {
        if (!double.IsFinite(viewportWidth) || !double.IsFinite(lineWidth) || viewportWidth < 0 || lineWidth < 0)
            throw new ArgumentException("Actual arranged widths must be finite and nonnegative");
        return center ? (viewportWidth - lineWidth) / 2 : 0;
    }
    internal static double LocalX(double ownerX, double lineX) => ownerX - lineX;
    internal static double OwnerX(double localX, double lineX) => localX + lineX;
}
