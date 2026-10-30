using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using System.Text.Json.Nodes;
using Windows.Foundation;

namespace Relic;

// A disc is native shape paint, not a substituted font's bullet glyph.
internal sealed class NativeListMarker : Panel
{
    internal Ellipse Disc { get; }
    internal NativeListMarkerMetrics Metrics { get; }
    private readonly JsonObject fontEvidence;
    private JsonObject? arranged;
    private string? failure;
    private long sequence;
    private XamlRoot? observedRoot;
    private (double X, double Y, double Scale)? snappedAt;
    internal RichTextBlock? ItemText { get; set; }
    internal double ItemBaseline { get; set; }
    internal string? BaselineSource { get; set; }

    internal NativeListMarker(string families, double size, string locale, SolidColorBrush foreground)
    {
        var primary = NativeListMarkerFont.Read(families, size, locale); Metrics = primary.Metrics; fontEvidence = primary.Evidence;
        UseLayoutRounding = false; IsHitTestVisible = false;
        AutomationProperties.SetName(this, "• ");
        Disc = new Ellipse { Fill = foreground, Stroke = null, StrokeThickness = 0,
            Stretch = Stretch.Fill, UseLayoutRounding = false, IsHitTestVisible = false };
        AutomationProperties.SetAccessibilityView(Disc, AccessibilityView.Raw); Children.Add(Disc);
        Loaded += (_, _) =>
        {
            if (observedRoot != null) observedRoot.Changed -= RootChanged;
            observedRoot = XamlRoot; if (observedRoot != null) observedRoot.Changed += RootChanged;
            snappedAt = null; InvalidateArrange();
        };
        Unloaded += (_, _) =>
        {
            if (observedRoot != null) observedRoot.Changed -= RootChanged;
            observedRoot = null; snappedAt = null;
        };
        LayoutUpdated += (_, _) =>
        {
            if (!IsLoaded || XamlRoot?.Content is not UIElement root) return;
            var origin = TransformToVisual(root).TransformPoint(new Point(0, 0));
            var current = (origin.X, origin.Y, XamlRoot.RasterizationScale);
            if (snappedAt != current) InvalidateArrange();
        };
    }

    private void RootChanged(XamlRoot sender, XamlRootChangedEventArgs args) { snappedAt = null; InvalidateArrange(); }
    protected override AutomationPeer OnCreateAutomationPeer() => new MarkerPeer(this);
    private sealed class MarkerPeer(NativeListMarker owner) : FrameworkElementAutomationPeer(owner)
    {
        protected override AutomationControlType GetAutomationControlTypeCore() => AutomationControlType.Image;
        protected override string GetClassNameCore() => nameof(NativeListMarker);
        protected override string GetNameCore() => "• ";
        protected override bool IsContentElementCore() => true;
        protected override bool IsControlElementCore() => true;
        protected override IList<AutomationPeer> GetChildrenCore() => new List<AutomationPeer>();
    }

    protected override Size MeasureOverride(Size availableSize)
    {
        Disc.Measure(new Size(Metrics.Diameter, Metrics.Diameter));
        return new Size(Metrics.Width, Metrics.Height);
    }

    protected override Size ArrangeOverride(Size finalSize)
    {
        var local = Metrics.Disc; failure = null; JsonObject? transformEvidence = null;
        if (XamlRoot?.Content is UIElement root)
        {
            var transform = TransformToVisual(root);
            var origin = transform.TransformPoint(new Point(0, 0));
            var axisX = transform.TransformPoint(new Point(1, 0)); var axisY = transform.TransformPoint(new Point(0, 1));
            var scale = XamlRoot.RasterizationScale;
            snappedAt = (origin.X, origin.Y, scale);
            transformEvidence = new JsonObject { ["source"] = "actual marker.TransformToVisual(XamlRoot.Content) and XamlRoot.RasterizationScale",
                ["origin"] = new JsonArray(origin.X, origin.Y), ["unit_x"] = new JsonArray(axisX.X, axisX.Y),
                ["unit_y"] = new JsonArray(axisY.X, axisY.Y), ["rasterization_scale"] = scale };
            if (axisX.X - origin.X == 1 && axisX.Y == origin.Y && axisY.X == origin.X && axisY.Y - origin.Y == 1)
                local = NativeListMarkerMetrics.Snap(local, origin.X, origin.Y, scale);
            else failure = "Native disc pixel snapping has an unsupported non-translation actual owner transform";
        }
        else failure = "Native disc has no mounted XamlRoot coordinate basis yet";
        // Arrange the actual retained Ellipse. No second renderer is used for capture.
        Disc.Arrange(new Rect(local.X, local.Y, local.Width, local.Height));
        arranged = new JsonObject
        {
            ["source"] = "Production NativeListMarker.ArrangeOverride -> actual Ellipse.Arrange",
            ["sequence"] = ++sequence, ["at_utc"] = DateTimeOffset.UtcNow.ToString("O"),
            ["owner_size"] = new JsonArray(finalSize.Width, finalSize.Height),
            ["ideal_local_ellipse"] = Box(Metrics.Disc), ["arranged_local_ellipse"] = Box(local),
            ["coordinate_basis"] = transformEvidence, ["failure"] = failure,
            ["quantity"] = "Actual native Ellipse layout and paint properties; not an observed framework raster callback",
            ["presentation_identity_proven"] = false
        };
        return finalSize;
    }

    internal JsonObject Capture(string ownerId, string? ellipseId, string? actualParentId, UIElement windowContent)
    {
        var result = new JsonObject
        {
            ["source"] = "Actual retained native list-disc owner and Ellipse child",
            ["owner_id"] = ownerId, ["ellipse_id"] = ellipseId, ["ellipse_parent_id"] = actualParentId,
            ["same_direct_child"] = ReferenceEquals(VisualTreeHelper.GetParent(Disc), this),
            ["owner_is_loaded"] = IsLoaded, ["ellipse_is_loaded"] = Disc.IsLoaded,
            ["symbol"] = "disc", ["alternative_text"] = AutomationProperties.GetName(this),
            ["actual_primary_font"] = fontEvidence.DeepClone(), ["current_arrangement"] = arranged?.DeepClone(),
            ["item_baseline"] = ItemBaseline, ["item_baseline_source"] = BaselineSource,
            ["ellipse_actual_size"] = new JsonArray(Disc.ActualWidth, Disc.ActualHeight),
            ["ellipse_stroke_thickness"] = Disc.StrokeThickness, ["ellipse_has_stroke"] = Disc.Stroke != null,
            ["ellipse_fill_type"] = Disc.Fill?.GetType().FullName,
            ["ellipse_fill_rgba8"] = Disc.Fill is SolidColorBrush brush ? new JsonArray(brush.Color.R, brush.Color.G, brush.Color.B, brush.Color.A) : null,
            ["ellipse_fill_opacity"] = Disc.Fill?.Opacity, ["ellipse_opacity"] = Disc.Opacity,
            ["ellipse_visibility"] = Disc.Visibility.ToString(), ["ellipse_is_hit_test_visible"] = Disc.IsHitTestVisible,
            ["draw_callback_observed"] = false, ["presentation_identity_proven"] = false, ["failure"] = failure
        };
        try
        {
            var local = Disc.TransformToVisual(this).TransformBounds(new Rect(0, 0, Disc.ActualWidth, Disc.ActualHeight));
            var actualLocal = new JsonObject { ["x"] = local.X, ["y"] = local.Y, ["width"] = local.Width, ["height"] = local.Height };
            result["actual_local_ellipse"] = actualLocal;
            result["current_arrangement_matches_actual_geometry"] = arranged != null
                && JsonNode.DeepEquals(arranged["arranged_local_ellipse"], actualLocal)
                && arranged["owner_size"] is JsonArray ownerSize
                && ownerSize[0]?.GetValue<double>() == ActualWidth && ownerSize[1]?.GetValue<double>() == ActualHeight;
            var transform = Disc.TransformToVisual(windowContent);
            var origin = transform.TransformPoint(new Point(0, 0)); var x = transform.TransformPoint(new Point(1, 0)); var y = transform.TransformPoint(new Point(0, 1));
            result["ellipse_to_window"] = new JsonObject { ["source"] = "actual retained Ellipse.TransformToVisual(windowContent)",
                ["m11"] = x.X - origin.X, ["m12"] = x.Y - origin.Y, ["m21"] = y.X - origin.X, ["m22"] = y.Y - origin.Y,
                ["offset_x"] = origin.X, ["offset_y"] = origin.Y };
            var bounds = transform.TransformBounds(new Rect(0, 0, Disc.ActualWidth, Disc.ActualHeight));
            result["ellipse_window_bounds"] = new JsonObject { ["x"] = bounds.X, ["y"] = bounds.Y, ["width"] = bounds.Width, ["height"] = bounds.Height };
            result["actual_rasterization_scale"] = XamlRoot?.RasterizationScale;
            result["same_window_xaml_root"] = ReferenceEquals(XamlRoot, windowContent.XamlRoot);
        }
        catch (Exception error) { result["coordinate_failure"] = new JsonObject { ["type"] = error.GetType().FullName, ["hresult"] = error.HResult, ["message"] = error.Message }; }
        return result;
    }
    private static JsonObject Box(NativeMarkerRect rect) => new() { ["x"] = rect.X, ["y"] = rect.Y, ["width"] = rect.Width, ["height"] = rect.Height };
}

// The list item owns its normal 22px content indent. The outside marker's
// font box follows the actual first text baseline rather than a fixed Y offset.
internal sealed class NativeListItemPanel : Panel
{
    private readonly NativeListMarker marker;
    private readonly RichTextBlock text;
    private readonly double lineHeight;
    private readonly bool emptyText;
    internal NativeListItemPanel(NativeListMarker marker, RichTextBlock text, double lineHeight, bool emptyText)
    { this.marker = marker; this.text = text; this.lineHeight = lineHeight; this.emptyText = emptyText;
        marker.ItemText = text; UseLayoutRounding = false; Children.Add(marker); Children.Add(text); }
    protected override Size MeasureOverride(Size availableSize)
    {
        text.Measure(new Size(Math.Max(0, availableSize.Width - 22), availableSize.Height));
        marker.Measure(availableSize);
        return new Size(22 + text.DesiredSize.Width, Math.Max(lineHeight, Math.Max(text.DesiredSize.Height, marker.DesiredSize.Height)));
    }
    protected override Size ArrangeOverride(Size finalSize)
    {
        text.Arrange(new Rect(22, 0, Math.Max(0, finalSize.Width - 22), finalSize.Height));
        var baseline = emptyText ? marker.Metrics.Ascent + (lineHeight - marker.Metrics.Height) / 2 : text.BaselineOffset;
        marker.ItemBaseline = baseline;
        marker.BaselineSource = emptyText ? "Empty list item primary-font strut at its requested line height" : "Actual production RichTextBlock.BaselineOffset after Arrange";
        var placement = marker.Metrics.Outside(22, baseline);
        marker.Arrange(new Rect(placement.X, placement.Y, placement.Width, placement.Height));
        return finalSize;
    }
}
