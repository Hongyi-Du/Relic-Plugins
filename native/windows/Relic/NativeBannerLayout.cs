using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Foundation;

namespace Relic;

// Layout only: the existing vector icon and selectable text remain the real
// paint owners. The two children follow .banner's flex: 0 1 auto policy.
internal sealed class NativeBannerLayout : Panel
{
    private readonly MainWindow.ReferenceVectorIcon icon;
    private readonly NativePathText text;
    private readonly double iconBasis, iconHeight, gap;
    private NativeBannerFlex.Allocation allocation;
    private double measuredAvailable = double.NaN, measuredHeight;

    internal NativeBannerLayout(MainWindow.ReferenceVectorIcon icon, NativePathText text, double gap)
    {
        this.icon = icon; this.text = text; this.gap = gap;
        iconBasis = icon.Width; iconHeight = icon.Height;
        UseLayoutRounding = false;
        icon.HorizontalAlignment = HorizontalAlignment.Left;
        icon.VerticalAlignment = VerticalAlignment.Top;
        text.HorizontalAlignment = HorizontalAlignment.Stretch;
        text.VerticalAlignment = VerticalAlignment.Top;
        Children.Add(icon); Children.Add(text);
    }

    private void MeasureChildren(double available)
    {
        var hasIntrinsic = text.TryGetBannerIntrinsic(out var intrinsic);
        if (hasIntrinsic) allocation = NativeBannerFlex.Resolve(available, gap, iconBasis, intrinsic);
        else
        {
            // Preserve the original Auto + Star layout if measurement fails.
            // No width from a scene or reference capture is used as a default.
            var remaining = double.IsFinite(available) ? Math.Max(0, available - gap - iconBasis) : double.PositiveInfinity;
            text.Measure(new Size(remaining, double.PositiveInfinity));
            allocation = new(iconBasis, double.IsFinite(remaining) ? remaining : text.DesiredSize.Width);
        }
        icon.SetHorizontalViewportWidth(allocation.Icon);
        icon.Measure(new Size(allocation.Icon, iconHeight));
        text.Measure(new Size(allocation.Text, double.PositiveInfinity));
        measuredHeight = Math.Max(icon.DesiredSize.Height, text.DesiredSize.Height);
        measuredAvailable = available;
        text.ObserveBannerAllocation(available, gap, iconBasis, allocation, hasIntrinsic);
    }

    protected override Size MeasureOverride(Size availableSize)
    {
        MeasureChildren(availableSize.Width);
        return new Size(double.IsFinite(availableSize.Width) ? availableSize.Width : allocation.Icon + gap + allocation.Text, measuredHeight);
    }

    protected override Size ArrangeOverride(Size finalSize)
    {
        if (finalSize.Width != measuredAvailable) MeasureChildren(finalSize.Width);
        icon.Arrange(new Rect(0, 0, allocation.Icon, iconHeight));
        text.Arrange(new Rect(allocation.Icon + gap, 0, allocation.Text, text.DesiredSize.Height));
        return finalSize;
    }
}
