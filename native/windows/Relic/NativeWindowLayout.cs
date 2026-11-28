using Microsoft.UI.Xaml.Controls;
using Windows.Foundation;

namespace Relic;

internal sealed class NativeWindowLayout : Grid
{
    protected override Size MeasureOverride(Size availableSize)
    {
        using var timing = PerformanceTrace.Measure("window.measure");
        return base.MeasureOverride(availableSize);
    }
    protected override Size ArrangeOverride(Size finalSize)
    {
        using var timing = PerformanceTrace.Measure("window.arrange");
        return base.ArrangeOverride(finalSize);
    }
}
