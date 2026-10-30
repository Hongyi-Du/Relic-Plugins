using System;
using System.Collections.Generic;

#if WINDOWS
using Microsoft.UI.Xaml.Controls;
using Windows.Foundation;
#endif

namespace Relic;

// Kept free of WinUI types so CI can verify the actual production calculation
// without creating a window. All dimensions and baselines come from the children.
internal readonly record struct MessageHeaderMetric(double Width, double Height, double Baseline);
internal readonly record struct MessageHeaderPlacement(double X, double Y, double Width, double Height);
internal sealed record MessageHeaderLayout(double Width, double Height,
    bool UsesMeasuredBaselines, IReadOnlyList<MessageHeaderPlacement> Children);

internal static class MessageHeaderLayoutEngine
{
    internal static MessageHeaderLayout Calculate(IReadOnlyList<MessageHeaderMetric> children,
        double availableWidth, double spacing)
    {
        var positions = new MessageHeaderPlacement[children.Count];
        double y = 0, widest = 0;
        var measured = true;
        var start = 0;
        while (start < children.Count)
        {
            var end = start;
            double x = 0;
            while (end < children.Count)
            {
                var child = children[end];
                if (end > start && x + child.Width > availableWidth) break;
                x += child.Width + spacing;
                end++;
            }

            double ascent = double.NegativeInfinity, descent = double.NegativeInfinity, tallest = 0;
            var rowMeasured = true;
            for (var i = start; i < end; i++)
            {
                var child = children[i];
                // WinUI can return the initial zero while no measured text layout
                // is available. A positive-height line needs a positive baseline.
                rowMeasured &= double.IsFinite(child.Baseline) && (child.Height == 0 || child.Baseline > 0);
                ascent = Math.Max(ascent, child.Baseline);
                descent = Math.Max(descent, child.Height - child.Baseline);
                tallest = Math.Max(tallest, child.Height);
            }

            // BaselineOffset may be NaN or not yet measured. Retain the top-aligned
            // row as a production fallback; do not synthesize font metrics or label
            // the fallback as measured. The original metric remains in the receipt.
            var rowHeight = rowMeasured ? ascent + descent : tallest;
            measured &= rowMeasured;
            x = 0;
            for (var i = start; i < end; i++)
            {
                var child = children[i];
                positions[i] = new(x, y + (rowMeasured ? ascent - child.Baseline : 0),
                    Math.Min(child.Width, availableWidth), child.Height);
                x += child.Width + spacing;
            }
            widest = Math.Max(widest, Math.Max(0, x - spacing));
            y += rowHeight;
            if (end < children.Count) y += spacing;
            start = end;
        }
        return new(Math.Min(availableWidth, widest), y, measured, positions);
    }
}

#if WINDOWS
// .msg .who aligns its differently sized name, identifier, recipient and time
// by their real first-line baselines, including each font's descent. ActionRow
// intentionally remains unchanged for other controls and action buttons.
public sealed class MessageHeaderRow : Panel
{
    public double Spacing { get; set; } = 6;
    internal IReadOnlyList<MessageHeaderMetric> MeasuredChildren { get; private set; } = Array.Empty<MessageHeaderMetric>();
    internal MessageHeaderLayout? LastLayout { get; private set; }

    private MessageHeaderLayout Layout(double width)
    {
        var metrics = new MessageHeaderMetric[Children.Count];
        for (var i = 0; i < Children.Count; i++)
        {
            var child = Children[i];
            metrics[i] = new(child.DesiredSize.Width, child.DesiredSize.Height,
                child is TextBlock text ? text.BaselineOffset : double.NaN);
        }
        MeasuredChildren = metrics;
        return LastLayout = MessageHeaderLayoutEngine.Calculate(metrics, width, Spacing);
    }

    protected override Size MeasureOverride(Size available)
    {
        foreach (var child in Children) child.Measure(new(available.Width, double.PositiveInfinity));
        var layout = Layout(available.Width);
        return new(layout.Width, layout.Height);
    }

    protected override Size ArrangeOverride(Size final)
    {
        var layout = Layout(final.Width);
        for (var i = 0; i < Children.Count; i++)
        {
            var child = layout.Children[i];
            Children[i].Arrange(new(child.X, child.Y, child.Width, child.Height));
        }
        return final;
    }
}
#endif
