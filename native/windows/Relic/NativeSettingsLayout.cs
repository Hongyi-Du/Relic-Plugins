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
