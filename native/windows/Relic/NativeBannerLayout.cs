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

    // Measure and arrange can disagree by layout rounding. At a 150% display
    // scale the parent measured this panel at 420 and arranged it at 420.667
    // (one device pixel). Re-measuring the children for that difference set the
    // icon's width again (11.3096 instead of 11.2913), which asked for another
    // measure at 420, and so on: the widths alternated for 250 passes and WinUI
    // ended the app with a layout cycle (AG_E_LAYOUT_CYCLE). A rounding
    // difference keeps the measured allocation; a real one re-measures, at most
    // once per dispatcher turn, so this panel cannot keep layout from settling.
    private const double RoundingTolerance = 2;
    private long remeasuredTurn = -1;

    protected override Size ArrangeOverride(Size finalSize)
    {
        if (!(Math.Abs(finalSize.Width - measuredAvailable) <= RoundingTolerance) && remeasuredTurn != LayoutFeedback.Turn)
        {
            remeasuredTurn = LayoutFeedback.Turn;
            LayoutFeedback.Note("banner.arrange_remeasure", finalSize.Width, measuredAvailable);
            MeasureChildren(finalSize.Width);
        }
        icon.Arrange(new Rect(0, 0, allocation.Icon, iconHeight));
        text.Arrange(new Rect(allocation.Icon + gap, 0, allocation.Text, text.DesiredSize.Height));
        return finalSize;
    }
}
