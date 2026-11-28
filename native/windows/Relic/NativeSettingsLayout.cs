using System.Diagnostics;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Foundation;

namespace Relic;

// Observe the real first measure of the unchanged settings subtrees. These
// subclasses delegate layout to the original native controls; no warmup,
// alternate measure or synthetic bounds replace the production operation.
internal static class NativeSettingsLayoutTrace
{
    private static readonly bool enabled = Environment.GetEnvironmentVariable("GITHUB_ACTIONS") == "true"
        && !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("RELIC_PERF_MANIFEST"));
    internal static long Start() => enabled ? Stopwatch.GetTimestamp() : 0;

    internal static void Finish(string name, long start, FrameworkElement owner, int itemCount = -1)
    {
        if (start == 0) return;
        var elapsed = Stopwatch.GetElapsedTime(start).TotalMilliseconds;
        if (elapsed <= 5) return;
        PerformanceTrace.Count(name, elapsed);
        PerformanceTrace.Count(name + ".OwnerType." + owner.GetType().Name, 1);
        if (itemCount >= 0) PerformanceTrace.Count(name + ".Items", itemCount);
        if (owner is not Panel panel) return;
        PerformanceTrace.Count(name + ".DirectChildren", panel.Children.Count);
        var types = new Dictionary<string, int>();
        // Only slow CI measurements enumerate their bounded direct children.
        // Keep template trees untouched and do not force ApplyTemplate/Layout.
        for (var index = 0; index < panel.Children.Count; index++)
        {
            var type = panel.Children[index].GetType().Name;
            types[type] = types.GetValueOrDefault(type) + 1;
        }
        foreach (var (type, count) in types) PerformanceTrace.Count(name + ".ChildType." + type, count);
    }

    // The first nodes of a subtree, with the text a node shows, to name a
    // slow row without guessing.
    internal static string[] Describe(DependencyObject root)
    {
        var nodes = new List<string>(); var pending = new Stack<(DependencyObject Node, int Depth)>();
        pending.Push((root, 0));
        while (pending.Count > 0 && nodes.Count < 24)
        {
            var (node, depth) = pending.Pop();
            var text = node switch
            {
                TextBlock block => block.Text,
                NativeLabel label => label.Text,
                ContentControl { Content: string content } => content,
                _ => null
            };
            nodes.Add(new string(' ', depth) + node.GetType().Name + (text is { Length: > 0 } ? ": " + (text.Length > 48 ? text[..48] + "…" : text) : ""));
            var count = Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(node);
            for (var index = count - 1; index >= 0; index--)
                pending.Push((Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChild(node, index), depth + 1));
        }
        return nodes.ToArray();
    }
}

internal sealed class NativeSettingsGrid(string scope) : Grid
{
    protected override Size MeasureOverride(Size availableSize)
    {
        var start = NativeSettingsLayoutTrace.Start();
        try { return base.MeasureOverride(availableSize); }
        finally { NativeSettingsLayoutTrace.Finish(scope + ".Measure", start, this); }
    }
    protected override Size ArrangeOverride(Size finalSize)
    {
        var start = NativeSettingsLayoutTrace.Start();
        try { return base.ArrangeOverride(finalSize); }
        finally { NativeSettingsLayoutTrace.Finish(scope + ".Arrange", start, this); }
    }
}

internal sealed class NativeSettingsStack(string scope) : StackPanel
{
    protected override Size MeasureOverride(Size availableSize)
    {
        var start = NativeSettingsLayoutTrace.Start();
        // CI-only: which direct child is slow. Each child is measured with
        // the constraint StackPanel gives it (the width inside the padding,
        // unbounded height), so the base measure below finds it measured
        // already; nothing is measured twice. The About page's four rows once
        // took 345 ms here, the settings page's 800 ms.
        if (start != 0 && Orientation == Orientation.Vertical)
        {
            var width = double.IsInfinity(availableSize.Width) ? availableSize.Width
                : Math.Max(0, availableSize.Width - Padding.Left - Padding.Right - BorderThickness.Left - BorderThickness.Right);
            for (var index = 0; index < Children.Count; index++)
            {
                var child = Children[index]; var childStart = Stopwatch.GetTimestamp();
                child.Measure(new Size(width, double.PositiveInfinity));
                var ms = Stopwatch.GetElapsedTime(childStart).TotalMilliseconds;
                if (ms > 20) PerformanceTrace.Note(scope + ".SlowChild", new { index, ms = Math.Round(ms, 1), tree = NativeSettingsLayoutTrace.Describe(child) });
            }
        }
        try { return base.MeasureOverride(availableSize); }
        finally { NativeSettingsLayoutTrace.Finish(scope + ".Measure", start, this); }
    }
    protected override Size ArrangeOverride(Size finalSize)
    {
        var start = NativeSettingsLayoutTrace.Start();
        try { return base.ArrangeOverride(finalSize); }
        finally { NativeSettingsLayoutTrace.Finish(scope + ".Arrange", start, this); }
    }
}
