using Microsoft.UI.Xaml.Controls;
using Windows.Foundation;

namespace Relic;

internal sealed class NativeWindowLayout : Grid
{
    private int tracedPasses;

    protected override Size MeasureOverride(Size availableSize)
    {
        using var timing = PerformanceTrace.Measure("window.measure");
        // CI-only: which child the first window layouts spend their time in.
        // The first one took 230-320 ms at startup with no region measured
        // over 5 ms. Measuring each child first takes that cold work out on its
        // own; the layout below then measures them again as usual.
        if (PerformanceTrace.IsEnabled && tracedPasses < 6)
        {
            tracedPasses++;
            foreach (var child in Children)
            {
                var started = System.Diagnostics.Stopwatch.GetTimestamp();
                child.Measure(availableSize);
                var ms = System.Diagnostics.Stopwatch.GetElapsedTime(started).TotalMilliseconds;
                if (ms > 15)
                    PerformanceTrace.Note("window.measure.child", new { pass = tracedPasses, type = child.GetType().Name,
                        name = Microsoft.UI.Xaml.Automation.AutomationProperties.GetName(child),
                        children = Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(child), ms = Math.Round(ms, 1) });
            }
        }
        return base.MeasureOverride(availableSize);
    }
    protected override Size ArrangeOverride(Size finalSize)
    {
        using var timing = PerformanceTrace.Measure("window.arrange");
        return base.ArrangeOverride(finalSize);
    }
}
