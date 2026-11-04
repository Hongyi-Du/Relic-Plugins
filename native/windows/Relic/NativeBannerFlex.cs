namespace Relic;

// The two banner items use flex: 0 1 auto. The icon has no content minimum;
// normal text freezes at its actual indivisible-line minimum. Excess text may
// overflow a smaller container; it is never assigned a negative width.
internal static class NativeBannerFlex
{
    internal readonly record struct Intrinsic(double Natural, double Minimum);
    internal readonly record struct Allocation(double Icon, double Text);

    internal static Allocation Resolve(double available, double gap, double iconBase, Intrinsic text)
    {
        if ((!double.IsFinite(available) && !double.IsPositiveInfinity(available)) || available < 0
            || !double.IsFinite(gap) || gap < 0 || !double.IsFinite(iconBase) || iconBase < 0
            || !double.IsFinite(text.Natural) || text.Natural < 0
            || !double.IsFinite(text.Minimum) || text.Minimum < 0 || text.Minimum > text.Natural)
            throw new ArgumentException("Flex inputs must be actual nonnegative widths with a valid text minimum");
        var content = Math.Max(0, available - gap); var basis = iconBase + text.Natural;
        if (!double.IsFinite(basis)) throw new ArgumentException("The total flex basis must be representable");
        if (content >= basis || basis == 0) return new(iconBase, text.Natural);
        // Each shrink factor is one, so the scaled factors are the two bases.
        var icon = content * (iconBase / basis); var width = content * (text.Natural / basis);
        if (width < text.Minimum)
        {
            width = text.Minimum;
            icon = Math.Max(0, content - width);
        }
        return new(icon, width);
    }

    internal static Intrinsic NormalText(string paint, IReadOnlyList<NativePathLineBreaks.Cluster> clusters,
        IReadOnlyCollection<int> normalBoundaries, IReadOnlyCollection<int> characterBoundaries)
    {
        // These are the same measured clusters and boundaries consumed by
        // NoticeLines during production reflow. Width zero here asks that pure
        // policy for its indivisible segments; it is not XAML Measure(0).
        var unwrapped = NativeSelectableTextLayout.NoticeLines(paint, clusters, normalBoundaries, characterBoundaries, double.MaxValue);
        var indivisible = NativeSelectableTextLayout.NoticeLines(paint, clusters, normalBoundaries, characterBoundaries, 0);
        double Width(NativeSelectableTextLayout.Line line) => clusters
            .Where(cluster => cluster.Start >= line.Start && cluster.Start + cluster.Length <= line.End)
            .Sum(cluster => cluster.Width);
        return new(unwrapped.Select(Width).DefaultIfEmpty(0).Max(), indivisible.Select(Width).DefaultIfEmpty(0).Max());
    }
}
