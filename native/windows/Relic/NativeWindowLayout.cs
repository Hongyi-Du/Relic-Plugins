using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Media;
using Windows.Foundation;

namespace Relic;

internal sealed class NativeWindowLayout : Grid
{
    private int tracedPasses;

    protected override Size MeasureOverride(Size availableSize)
    {
        using var timing = PerformanceTrace.Measure("window.measure");
        // CI-only: where the first window layouts spend their time. The fifth
        // took 206 ms at startup in the three columns while no region inside
        // them measured over 5 ms (run 41668161153). Measuring descendants
        // first, deepest first, each at the size it was last given, takes the
        // cold work of every element out on its own; the layout below then
        // measures them again as usual (cheaply, as nothing changed since).
        if (PerformanceTrace.IsEnabled && tracedPasses < 6)
        {
            tracedPasses++;
            foreach (var child in Children) Premeasure(child, availableSize, 0);
        }
        return base.MeasureOverride(availableSize);
    }
    protected override Size ArrangeOverride(Size finalSize)
    {
        using var timing = PerformanceTrace.Measure("window.arrange");
        return base.ArrangeOverride(finalSize);
    }

    private void Premeasure(UIElement element, Size size, int depth)
    {
        if (depth < 10)
        {
            var count = VisualTreeHelper.GetChildrenCount(element);
            for (var index = 0; index < count; index++)
                if (VisualTreeHelper.GetChild(element, index) is UIElement child)
                    Premeasure(child, LayoutInformation.GetAvailableSize(child), depth + 1);
        }
        var started = System.Diagnostics.Stopwatch.GetTimestamp();
        element.Measure(size);
        var ms = System.Diagnostics.Stopwatch.GetElapsedTime(started).TotalMilliseconds;
        if (ms <= 15) return;
        var path = new List<string>();
        for (DependencyObject? at = element; at != null && at != this && path.Count < 8; at = VisualTreeHelper.GetParent(at))
            path.Insert(0, at.GetType().Name);
        PerformanceTrace.Note("window.measure.element", new { pass = tracedPasses, depth, path = string.Join("/", path),
            name = Microsoft.UI.Xaml.Automation.AutomationProperties.GetName(element),
            text = (element as TextBlock)?.Text is { } text ? text[..Math.Min(text.Length, 24)] : null,
            children = VisualTreeHelper.GetChildrenCount(element), ms = Math.Round(ms, 1) });
    }
}
