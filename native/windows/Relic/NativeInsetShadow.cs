using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Controls;
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;
using Windows.Foundation;
using ShapePath = Microsoft.UI.Xaml.Shapes.Path;

namespace Relic;

// One retained production decoration owned by the existing bubble Border.
// The Canvas contributes no desired size. Its path paints over the background
// and below the original content; the original content's layout stays intact.
internal sealed class NativeInsetShadow
{
    internal const string Source = "Actual retained Border inset-shadow path and original content composition";
    private static readonly ConditionalWeakTable<Border, NativeInsetShadow> Owners = new();
    internal Border Owner { get; }
    internal UIElement Content { get; }
    internal Grid Layout { get; } = new();
    internal Canvas Canvas { get; } = new() { IsHitTestVisible = false };
    internal ShapePath Path { get; } = new() { Stretch = Stretch.None, IsHitTestVisible = false, UseLayoutRounding = false, Stroke = null, StrokeThickness = 0 };
    private readonly float dx, dy;
    private PathGeometry? geometry;
    private JsonObject? operation;
    private (double Width, double Height, CornerRadius Radius, Thickness Border, Thickness Padding)? current;
    private string? failure;
    private long revision;

    internal static void Attach(Border owner, SolidColorBrush color, float dx = 3, float dy = 0)
    {
        if (Owners.TryGetValue(owner, out _)) throw new InvalidOperationException("Bubble already owns an inset shadow");
        Owners.Add(owner, new NativeInsetShadow(owner, color, dx, dy));
    }
    internal static bool TryGet(Border owner, out NativeInsetShadow? shadow) => Owners.TryGetValue(owner, out shadow);
    private NativeInsetShadow(Border owner, SolidColorBrush color, float dx, float dy)
    {
        Owner = owner; Content = owner.Child ?? throw new InvalidOperationException("Inset shadow requires the actual bubble content");
        this.dx = dx; this.dy = dy; Path.Fill = color;
        AutomationProperties.SetAccessibilityView(Path, AccessibilityView.Raw);
        AutomationProperties.SetAccessibilityView(Canvas, AccessibilityView.Raw);
        owner.Child = null; Canvas.Children.Add(Path); Layout.Children.Add(Canvas); Layout.Children.Add(Content); owner.Child = Layout;
        owner.Loaded += (_, _) => Update(); owner.SizeChanged += (_, _) => Update();
        foreach (var property in new[] { Border.CornerRadiusProperty, Border.BorderThicknessProperty, Border.PaddingProperty })
            owner.RegisterPropertyChangedCallback(property, (_, _) => Update());
    }
    private void Update()
    {
        if (Owner.ActualWidth <= 0 || Owner.ActualHeight <= 0) return;
        var state = (Owner.ActualWidth, Owner.ActualHeight, Owner.CornerRadius, Owner.BorderThickness, Owner.Padding);
        if (current == state && geometry != null && ReferenceEquals(Path.Data, geometry)) return;
        try
        {
            var r = Owner.CornerRadius; var b = Owner.BorderThickness; var p = Owner.Padding;
            var contour = NativeInsetShadowGeometry.PaddingEdge(Owner.ActualWidth, Owner.ActualHeight,
                b.Left, b.Top, b.Right, b.Bottom, r.TopLeft, r.TopRight, r.BottomRight, r.BottomLeft);
            var result = NativeInsetShadowPath.Exclude(contour, dx, dy);
            var next = new PathGeometry { FillRule = result.Receipt["output_fill_mode"]!.GetValue<uint>() == 0 ? FillRule.EvenOdd : FillRule.Nonzero };
            PathFigure? figure = null;
            foreach (var command in result.Commands)
            {
                var v = command.Values;
                switch (command.Kind)
                {
                    case "M": figure = new PathFigure { StartPoint = new Point(v[0], v[1]), IsFilled = true }; next.Figures.Add(figure); break;
                    case "L": figure!.Segments.Add(new LineSegment { Point = new Point(v[0], v[1]) }); break;
                    case "C": figure!.Segments.Add(new BezierSegment { Point1 = new Point(v[0], v[1]), Point2 = new Point(v[2], v[3]), Point3 = new Point(v[4], v[5]) }); break;
                    case "Z": figure!.IsClosed = true; figure = null; break;
                    default: throw new InvalidOperationException("Unexpected native inset output path");
                }
            }
            Path.Width = Owner.ActualWidth; Path.Height = Owner.ActualHeight;
            // Layout's origin is the actual content edge. The geometry is in
            // Border-local coordinates, including its actual padding-edge inset.
            Microsoft.UI.Xaml.Controls.Canvas.SetLeft(Path, -b.Left - p.Left);
            Microsoft.UI.Xaml.Controls.Canvas.SetTop(Path, -b.Top - p.Top);
            Path.Data = next; geometry = next; operation = result.Receipt; current = state;
            revision++; failure = null;
        }
        catch (Exception e) { failure = e.ToString(); }
    }
    private JsonArray ActualCommands()
    {
        if (Path.Data is not PathGeometry actual) throw new InvalidOperationException("The actual inset path is not PathGeometry");
        var commands = new List<NativeInsetCommand>();
        foreach (var figure in actual.Figures)
        {
            if (!figure.IsFilled || !figure.IsClosed) throw new InvalidOperationException("The actual inset path is not a closed filled shape");
            commands.Add(new("M", [figure.StartPoint.X, figure.StartPoint.Y]));
            foreach (var segment in figure.Segments)
                switch (segment)
                {
                    case LineSegment line: commands.Add(new("L", [line.Point.X, line.Point.Y])); break;
                    case BezierSegment curve: commands.Add(new("C", [curve.Point1.X, curve.Point1.Y, curve.Point2.X, curve.Point2.Y, curve.Point3.X, curve.Point3.Y])); break;
                    default: throw new InvalidOperationException("The actual inset path contains an unobserved segment type");
                }
            commands.Add(new("Z", []));
        }
        return NativeInsetShadowPath.Commands(commands);
    }
    internal JsonObject Observe(Dictionary<DependencyObject, string> ids, UIElement windowRoot)
    {
        string? Id(DependencyObject part) => ids.GetValueOrDefault(part);
        var r = Owner.CornerRadius; var b = Owner.BorderThickness; var p = Owner.Padding;
        var result = new JsonObject
        {
            ["source"] = Source, ["owner_id"] = Id(Owner), ["layout_id"] = Id(Layout), ["canvas_id"] = Id(Canvas), ["path_id"] = Id(Path), ["content_id"] = Id(Content),
            ["owner_child_is_layout"] = ReferenceEquals(Owner.Child, Layout),
            ["layout_children_are_retained_parts"] = Layout.Children.Count == 2 && ReferenceEquals(Layout.Children[0], Canvas) && ReferenceEquals(Layout.Children[1], Content),
            ["canvas_child_is_path"] = Canvas.Children.Count == 1 && ReferenceEquals(Canvas.Children[0], Path),
            ["current_path_same_object"] = geometry != null && ReferenceEquals(Path.Data, geometry),
            ["same_xaml_root"] = ReferenceEquals(Owner.XamlRoot, Path.XamlRoot) && ReferenceEquals(Owner.XamlRoot, windowRoot.XamlRoot),
            ["owner_is_loaded"] = Owner.IsLoaded, ["path_is_loaded"] = Path.IsLoaded,
            ["actual_size"] = new JsonArray(Owner.ActualWidth, Owner.ActualHeight),
            ["actual_radii"] = new JsonArray(r.TopLeft, r.TopRight, r.BottomRight, r.BottomLeft),
            ["actual_border_widths"] = new JsonArray(b.Top, b.Right, b.Bottom, b.Left),
            ["actual_padding"] = new JsonArray(p.Top, p.Right, p.Bottom, p.Left),
            ["current_layout_matches_operation"] = current == (Owner.ActualWidth, Owner.ActualHeight, r, b, p),
            ["path_hit_test_visible"] = Path.IsHitTestVisible, ["canvas_hit_test_visible"] = Canvas.IsHitTestVisible,
            ["path_accessibility_view"] = AutomationProperties.GetAccessibilityView(Path).ToString(),
            ["path_name"] = AutomationProperties.GetName(Path), ["path_stroke_present"] = Path.Stroke != null,
            ["path_stroke_thickness"] = Path.StrokeThickness, ["path_opacity"] = Path.Opacity,
            ["path_fill_type"] = Path.Fill?.GetType().Name, ["path_fill_opacity"] = Path.Fill?.Opacity,
            ["path_fill_rgba8"] = Path.Fill is SolidColorBrush brush ? new JsonArray(brush.Color.R, brush.Color.G, brush.Color.B, brush.Color.A) : null,
            ["path_size"] = new JsonArray(Path.ActualWidth, Path.ActualHeight), ["path_stretch"] = Path.Stretch.ToString(),
            ["path_fill_rule"] = (Path.Data as PathGeometry)?.FillRule.ToString(),
            ["revision"] = revision, ["operation"] = operation?.DeepClone(), ["failure"] = failure,
            ["quantity"] = "Actual native path operation, retained XAML paint and current properties; not a final raster or antialiasing measurement",
            ["presentation_identity_proven"] = false
        };
        try
        {
            var commands = ActualCommands(); result["actual_path_commands"] = commands;
            result["actual_path_matches_operation"] = JsonNode.DeepEquals(commands, operation?["output_commands"]);
            var transform = Path.TransformToVisual(Owner);
            var o = transform.TransformPoint(new Point(0, 0)); var x = transform.TransformPoint(new Point(1, 0)); var y = transform.TransformPoint(new Point(0, 1));
            result["actual_path_to_owner"] = new JsonArray(x.X - o.X, x.Y - o.Y, y.X - o.X, y.Y - o.Y, o.X, o.Y);
            result["path_geometry_transform_present"] = Path.Data?.Transform != null;
        }
        catch (Exception e) { result["observation_failure"] = e.ToString(); }
        return result;
    }
}

public sealed partial class MainWindow
{
    private void CaptureNativeInsetShadows(Dictionary<DependencyObject, string> ids, Dictionary<DependencyObject, JsonObject> nodes)
    {
        foreach (var (element, _) in ids)
            if (element is Border border && NativeInsetShadow.TryGet(border, out var shadow) && shadow != null && nodes.TryGetValue(element, out var node))
                node["native_inset_shadow"] = shadow.Observe(ids, root);
    }
}
