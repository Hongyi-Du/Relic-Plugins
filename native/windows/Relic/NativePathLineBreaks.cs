namespace Relic;

// Pure policy over measured ICU boundaries and measured DirectWrite clusters.
// No font assumptions, source edits, fixture widths or fixed line positions.
internal static class NativePathLineBreaks
{
    internal readonly record struct Cluster(int Start, int Length, double Width);
    internal readonly record struct Line(int Start, int End, bool Emergency);

    internal static IReadOnlyList<Line> Select(int textLength, IReadOnlyList<Cluster> clusters,
        IReadOnlyCollection<int> normalBoundaries, IReadOnlyCollection<int> characterBoundaries, double width)
    {
        if (textLength < 0 || !double.IsFinite(width) || width < 0) throw new ArgumentOutOfRangeException(nameof(width));
        var advances = new SortedDictionary<int, double> { [0] = 0 };
        var position = 0; double advance = 0;
        foreach (var cluster in clusters)
        {
            if (cluster.Start != position || cluster.Length <= 0 || !double.IsFinite(cluster.Width) || cluster.Width < 0
                || cluster.Length > textLength - position) throw new ArgumentException("Measured clusters must cover the exact source in order");
            position += cluster.Length; advance += cluster.Width; advances[position] = advance;
        }
        if (position != textLength) throw new ArgumentException("Measured clusters do not cover the source");
        if (!normalBoundaries.Contains(0) || !normalBoundaries.Contains(textLength)
            || !characterBoundaries.Contains(0) || !characterBoundaries.Contains(textLength)
            || normalBoundaries.Concat(characterBoundaries).Any(n => n < 0 || n > textLength))
            throw new ArgumentException("Actual ICU boundaries must include both source endpoints");
        var safe = advances.Keys.Where(characterBoundaries.Contains).ToArray();
        var normal = new HashSet<int>(normalBoundaries.Where(n => Array.BinarySearch(safe, n) >= 0));
        var result = new List<Line>(); var start = 0;
        while (start < textLength)
        {
            var candidates = safe.Where(end => end > start).ToArray();
            if (candidates.Length == 0) throw new ArgumentException("No progressing safe character boundary");
            var fitting = candidates.Where(end => advances[end] - advances[start] <= width).ToArray();
            var end = fitting.LastOrDefault(normal.Contains);
            var emergency = end == 0;
            if (emergency) end = fitting.Length > 0 ? fitting[^1] : candidates[0];
            result.Add(new Line(start, end, emergency)); start = end;
        }
        return result;
    }

    internal static int Move(IReadOnlyList<int> boundaries, int position, int count, out int moved)
    {
        if (count == 0) { moved = 0; return position; }
        if (boundaries.Count == 0) { moved = 0; return position; }
        var current = count >= 0 ? boundaries.TakeWhile(n => n <= position).Count() - 1
                                : boundaries.TakeWhile(n => n < position).Count();
        current = Math.Clamp(current, 0, boundaries.Count - 1);
        var target = (int)Math.Clamp((long)current + count, 0, boundaries.Count - 1);
        moved = target - current; return boundaries[target];
    }

    internal static (double Ascent, double Descent) LineBox(double parentAscent, double parentHeight, double childAscent, double childHeight)
    {
        if (new[] { parentAscent, parentHeight, childAscent, childHeight }.Any(n => !double.IsFinite(n))
            || parentHeight <= 0 || childHeight <= 0) throw new ArgumentException("Actual line metrics are required");
        return (Math.Max(parentAscent, childAscent), Math.Max(parentHeight - parentAscent, childHeight - childAscent));
    }
}
