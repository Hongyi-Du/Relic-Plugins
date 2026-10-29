using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Documents;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using System.Text.Json;
using System.Text.Json.Nodes;
using Windows.Foundation;

namespace Relic;

public sealed partial class MainWindow
{
    // CI-only evidence from the rendered XAML tree, supplementing the independent
    // out-of-process UIA walk. No property is read from reference measurements.
    private async Task CaptureElementEvidence(string directory, string caseId, int width, int height)
    {
        if (!VisualCaptureEnabled) throw new InvalidOperationException("Element capture is CI-only");
        var nodes = new JsonArray(); var errors = new JsonArray(); var visited = new HashSet<DependencyObject>();
        var declaredContent = new Dictionary<DependencyObject, string>();
        var paintLayer = 0;
        var viewport = new Rect(0, 0, width, height);
        var cursor = new CapturePoint(); GetCursorPos(ref cursor); var clientOrigin = new CapturePoint(); ClientToScreen(WinRT.Interop.WindowNative.GetWindowHandle(this), ref clientOrigin);
        var hovered = new HashSet<UIElement>(VisualTreeHelper.FindElementsInHostCoordinates(new Point(cursor.x - clientOrigin.x, cursor.y - clientOrigin.y), root, true));
        string Region(DependencyObject value, string current)
        {
            if (ReferenceEquals(value, sidebarSurface)) return "sidebar";
            if (ReferenceEquals(value, inspectorSurface)) return "right-pane";
            if (ReferenceEquals(value, composerSurface)) return "composer";
            if (ReferenceEquals(value, stream) || ReferenceEquals(value, chatHead) || ReferenceEquals(value, conversationBanner) || ReferenceEquals(value, emptyConversation)) return "conversation";
            if (ReferenceEquals(value, menu) || ReferenceEquals(value, toolbar) || ReferenceEquals(value, navigationButtons)) return "header";
            if (value is ContentDialog) return "dialog";
            if (value is MenuFlyoutPresenter || value is MenuFlyoutItem || value is MenuFlyoutSubItem) return "menu";
            return current;
        }
        void Walk(DependencyObject value, string? parent, string region, Rect clip, double ancestorOpacity, string? hidden, int siblingOrder = 0)
        {
            if (!visited.Add(value)) return;
            var id = "xaml-" + nodes.Count; var type = value.GetType().Name; region = Region(value, region);
            var node = new JsonObject { ["id"] = id, ["parent"] = parent, ["type"] = type, ["region"] = region, ["order"] = nodes.Count };
            if (value is UIElement ordered) node["canvas_z_index"] = Canvas.GetZIndex(ordered);
            node["render_sibling_order"] = siblingOrder;
            node["paint_order"] = nodes.Count;
            node["paint_layer"] = paintLayer;
            if (declaredContent.TryGetValue(value, out var contentOwner)) node["declared_content_owner"] = contentOwner;
            if (value is ContentControl contentControl && contentControl.Content is DependencyObject controlContent) declaredContent[controlContent] = id;
            if (value is Expander contentExpander && contentExpander.Content is DependencyObject expanderContent) declaredContent[expanderContent] = id;
            nodes.Add(node);
            var opacity = ancestorOpacity;
            if (value is UIElement ui)
            {
                opacity *= ui.Opacity;
                if (ui.Visibility != Visibility.Visible) hidden ??= "collapsed ancestor";
                if (opacity <= 0) hidden ??= "zero opacity";
                node["opacity"] = opacity;
                if (ui.Clip is RectangleGeometry rectangular)
                {
                    var transformed = ui.TransformToVisual(root).TransformBounds(rectangular.Rect);
                    node["clip"] = new JsonObject { ["kind"] = "rectangle", ["local_bounds"] = CaptureBox(rectangular.Rect), ["bounds"] = CaptureBox(transformed) };
                    if (CaptureRectFinite(transformed)) clip = IntersectCapture(clip, transformed);
                    else errors.Add(id + ": non-finite transformed clip; ancestor clip measurement incomplete");
                }
                else if (ui.Clip != null)
                {
                    node["clip"] = new JsonObject { ["kind"] = ui.Clip.GetType().Name, ["supported"] = false };
                    errors.Add(id + ": nonrectangular clip requires coverage instrumentation");
                }
                else node["clip"] = null;
            }
            if (value is FrameworkElement element)
            {
                try
                {
                    var box = element.TransformToVisual(root).TransformBounds(new Rect(0, 0, element.ActualWidth, element.ActualHeight));
                    var finiteBox = CaptureRectFinite(box);
                    var visible = finiteBox ? IntersectCapture(clip, box) : box;
                    node["bounds"] = CaptureBox(box); node["visible_bounds"] = CaptureBox(visible);
                    if (!finiteBox) errors.Add(id + ": rendered box is non-finite; visible box is unmeasured");
                    node["ancestor_clip"] = CaptureBox(clip);
                    var transform = element.TransformToVisual(root);
                    node["local_bounds"] = CaptureBox(new Rect(0, 0, element.ActualWidth, element.ActualHeight));
                    var zero = transform.TransformPoint(new Point(0, 0));
                    var unitX = transform.TransformPoint(new Point(1, 0));
                    var unitY = transform.TransformPoint(new Point(0, 1));
                    var m11 = unitX.X - zero.X; var m12 = unitX.Y - zero.Y;
                    var m21 = unitY.X - zero.X; var m22 = unitY.Y - zero.Y;
                    node["transform"] = new JsonObject { ["m11"] = m11, ["m12"] = m12, ["m21"] = m21, ["m22"] = m22, ["offset_x"] = zero.X, ["offset_y"] = zero.Y };
                    var finiteTransform = double.IsFinite(m11) && double.IsFinite(m12) && double.IsFinite(m21) && double.IsFinite(m22) && double.IsFinite(zero.X) && double.IsFinite(zero.Y);
                    node["axis_aligned_transform"] = finiteTransform ? Math.Abs(m12) < 1e-8 && Math.Abs(m21) < 1e-8 : null;
                    var corners = new JsonArray();
                    foreach (var local in new[] { new Point(0, 0), new Point(element.ActualWidth, 0), new Point(element.ActualWidth, element.ActualHeight), new Point(0, element.ActualHeight) })
                    {
                        var point = transform.TransformPoint(local);
                        corners.Add(new JsonObject { ["x"] = point.X, ["y"] = point.Y });
                    }
                    node["transformed_corners"] = corners;
                    node["transformed_corners_order"] = "top-left,top-right,bottom-right,bottom-left";
                    node["name"] = element.Name; node["accessible_name"] = AutomationProperties.GetName(element);
                    if (box.Width <= 0 || box.Height <= 0 || visible.Width <= 0 || visible.Height <= 0) hidden ??= "zero area or ancestor clip";
                    node["hidden_reason"] = hidden;
                    if ((element is ScrollViewer || type == "ScrollContentPresenter") && finiteBox) clip = IntersectCapture(clip, box);
                    node["style"] = CaptureStyle(element, opacity, id, errors);
                    node["paint_kind"] = element switch
                    {
                        Border => "rounded-rectangle", Panel => "rectangle", Rectangle => "rounded-rectangle",
                        Ellipse => "ellipse", Shape => "path", Image => "image", TextBlock or RichTextBlock or IconElement => "glyphs",
                        Control => "template", _ => "none"
                    };
                    if (element is Border borderElement) node["background_sizing"] = borderElement.BackgroundSizing.ToString();
                    if (element is Rectangle rectangle) node["shape_corner_radius"] = new JsonObject { ["x"] = rectangle.RadiusX, ["y"] = rectangle.RadiusY };
                    node["text"] = CaptureText(element);
                    node["state"] = new JsonObject
                    {
                        ["enabled"] = element is Control control ? control.IsEnabled : null,
                        ["focused"] = element is Control focus ? focus.FocusState != FocusState.Unfocused : null,
                        ["selected"] = element is SelectorBarItem tab ? tab.IsSelected : element is SelectorItem item ? item.IsSelected : null,
                        ["checked"] = element is ToggleButton toggle ? toggle.IsChecked : element is ToggleSwitch change ? change.IsOn : null,
                        ["expanded"] = element is Expander expander ? expander.IsExpanded : null,
                        ["hovered"] = hovered.Contains(element), ["unread"] = null
                    };
                    node["layout"] = CaptureTextLayout(element, id, errors, root, hidden == null);
                    if (element is FontIcon fontIcon) node["icon"] = new JsonObject { ["source"] = fontIcon.FontFamily.Source, ["glyph"] = fontIcon.Glyph };
                    else if (element is ReferenceVectorIcon vectorIcon)
                    {
                        var shape = new JsonObject { ["tag"] = "svg", ["attributes"] = new JsonObject { ["height"] = CaptureFiniteAttribute(vectorIcon.Height, id + ".icon.height", errors), ["viewBox"] = "0 0 24 24", ["width"] = CaptureFiniteAttribute(vectorIcon.Width, id + ".icon.width", errors) },
                            ["children"] = new JsonArray(new JsonObject { ["tag"] = "path", ["attributes"] = new JsonObject { ["d"] = vectorIcon.PathData }, ["children"] = new JsonArray() }) };
                        node["icon"] = new JsonObject { ["source"] = "svg", ["glyph"] = shape.ToJsonString() };
                        node["vector_path"] = vectorIcon.PathData; node["vector_stroke_width"] = vectorIcon.VectorPath.StrokeThickness;
                        CaptureStrokeEvidence(vectorIcon.VectorPath, root, node, id, errors);
                    }
                    else if (element is SymbolIcon symbolIcon) node["icon"] = new JsonObject { ["source"] = "Segoe MDL2 Assets", ["glyph"] = ((int)symbolIcon.Symbol).ToString("X") };
                    else if (element is Microsoft.UI.Xaml.Shapes.Path path) node["icon"] = new JsonObject { ["source"] = "xaml-path", ["glyph"] = path.Data?.ToString() };
                    if (element is Shape renderedShape && renderedShape.Stroke != null) CaptureStrokeEvidence(renderedShape, root, node, id, errors);
                    if (element is TextBlock block) node["font_family"] = block.FontFamily.Source;
                    if (element is Control fontControl) node["font_family"] = fontControl.FontFamily.Source;
                }
                catch (Exception ex) { node["measurement_error"] = ex.Message; errors.Add(id + ": " + ex.Message); }
            }
            else node["hidden_reason"] = "non-rendering dependency object";
            var renderedChildren = Enumerable.Range(0, VisualTreeHelper.GetChildrenCount(value))
                .Select(index => (child: VisualTreeHelper.GetChild(value, index), index))
                .OrderBy(item => item.child is UIElement child ? Canvas.GetZIndex(child) : 0).ThenBy(item => item.index);
            foreach (var child in renderedChildren) Walk(child.child, id, region, clip, opacity, hidden, child.index);
        }
        Walk(root, null, "window", viewport, 1, null);
        var popups = VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot).Where(p => p.IsOpen && p.Child != null).ToArray();
        foreach (var popup in popups)
        {
            paintLayer++;
            Walk(popup.Child, null, popup.Child is MenuFlyoutPresenter ? "menu" : "dialog", viewport, 1, null);
        }
        if (popups.Length > 1) errors.Add("Multiple popup roots: their collection order requires independent HWND/compositor z-order verification.");
        var result = new JsonObject
        {
            ["schema_version"] = 1, ["scene_id"] = caseId, ["client"] = "windows",
            ["viewport"] = new JsonObject { ["width"] = width, ["height"] = height, ["scale"] = root.XamlRoot.RasterizationScale },
            ["raw_nodes"] = nodes, ["extraction_errors"] = errors,
            ["paint_order_source"] = "VisualTreeHelper children, stable Canvas.ZIndex then actual child index; popup roots above main root",
            ["popup_roots"] = popups.Length,
            ["pointer"] = new JsonObject { ["x"] = cursor.x - clientOrigin.x, ["y"] = cursor.y - clientOrigin.y }
        };
        CaptureFiniteMeasurements(result, errors);
        await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(directory, caseId + ".xaml.json"), result.ToJsonString());
        var manifestDirectory = System.IO.Path.GetDirectoryName(Environment.GetEnvironmentVariable("RELIC_VISUAL_MANIFEST"))!;
        var request = System.IO.Path.Combine(manifestDirectory, "elements-request.json");
        var receipt = System.IO.Path.Combine(manifestDirectory, "elements-complete.json");
        if (System.IO.File.Exists(receipt)) System.IO.File.Delete(receipt);
        var origin = new CapturePoint(); var handle = WinRT.Interop.WindowNative.GetWindowHandle(this); ClientToScreen(handle, ref origin);
        await System.IO.File.WriteAllTextAsync(request + ".tmp", JsonSerializer.Serialize(new { case_id = caseId, pid = Environment.ProcessId, hwnd = (long)handle, origin = new { x = origin.x, y = origin.y }, width, height }));
        System.IO.File.Move(request + ".tmp", request, true);
        // Yield the dispatcher while the independent process reads UIA. Holding
        // the UI thread here would deadlock real provider calls.
        var until = DateTime.UtcNow.AddSeconds(85);
        while (!System.IO.File.Exists(receipt))
        {
            if (DateTime.UtcNow >= until) throw new TimeoutException("Independent UIA evidence was not returned for " + caseId);
            await Task.Delay(50);
        }
        var completed = JsonNode.Parse(await System.IO.File.ReadAllTextAsync(receipt))!;
        if (completed["case_id"]?.GetValue<string>() != caseId) throw new InvalidOperationException("Stale element capture acknowledgement");
    }

    private static Rect IntersectCapture(Rect a, Rect b)
    {
        var x = Math.Max(a.X, b.X); var y = Math.Max(a.Y, b.Y);
        return new Rect(x, y, Math.Max(0, Math.Min(a.Right, b.Right) - x), Math.Max(0, Math.Min(a.Bottom, b.Bottom) - y));
    }
    private static bool CaptureRectFinite(Rect box) => double.IsFinite(box.X) && double.IsFinite(box.Y) && double.IsFinite(box.Width) && double.IsFinite(box.Height);
    private static JsonObject CaptureBox(Rect box) => new() { ["x"] = box.X, ["y"] = box.Y, ["width"] = box.Width, ["height"] = box.Height };
    // Keep JSON numeric types strict. Invalid provider/layout values are missing
    // measurements with exact raw reasons, never named floats or invented zeroes.
    private static void CaptureFiniteMeasurements(JsonObject result, JsonArray errors)
    {
        var invalid = new JsonArray();
        void Missing(JsonNode parent, string key, JsonValue value, string path)
        {
            var raw = value.TryGetValue<double>(out var number) ? number.ToString("R", System.Globalization.CultureInfo.InvariantCulture)
                : value.TryGetValue<float>(out var single) ? single.ToString("R", System.Globalization.CultureInfo.InvariantCulture) : "non-finite number";
            if (parent is JsonObject obj) obj[key] = null; else ((JsonArray)parent)[int.Parse(key, System.Globalization.CultureInfo.InvariantCulture)] = null;
            invalid.Add(new JsonObject { ["path"] = path, ["raw_value"] = raw, ["reason"] = "Actual measurement is not a finite JSON number" });
            errors.Add(path + ": non-finite actual measurement " + raw);
        }
        bool Invalid(JsonNode? value) => value is JsonValue scalar &&
            (scalar.TryGetValue<double>(out var number) && !double.IsFinite(number) ||
             scalar.TryGetValue<float>(out var single) && !float.IsFinite(single));
        void Walk(JsonNode? value, string path)
        {
            if (value is JsonObject obj)
            {
                foreach (var field in obj.ToArray())
                {
                    var next = path + "/" + field.Key.Replace("~", "~0").Replace("/", "~1");
                    if (Invalid(field.Value)) Missing(obj, field.Key, (JsonValue)field.Value!, next); else Walk(field.Value, next);
                }
            }
            else if (value is JsonArray array)
            {
                for (var index = 0; index < array.Count; index++)
                {
                    var key = index.ToString(System.Globalization.CultureInfo.InvariantCulture); var next = path + "/" + key;
                    if (Invalid(array[index])) Missing(array, key, (JsonValue)array[index]!, next); else Walk(array[index], next);
                }
            }
        }
        Walk(result, "");
        result["nonfinite_measurements"] = invalid;
    }
    private static string? CaptureFiniteAttribute(double value, string path, JsonArray errors)
    {
        if (double.IsFinite(value)) return value.ToString(System.Globalization.CultureInfo.InvariantCulture);
        errors.Add(path + ": non-finite actual SVG dimension " + value.ToString("R", System.Globalization.CultureInfo.InvariantCulture));
        return null;
    }
    private static JsonArray? CaptureColor(Brush? brush) => brush is SolidColorBrush solid ? new JsonArray(solid.Color.R, solid.Color.G, solid.Color.B, Math.Round(solid.Color.A * solid.Opacity)) : brush == null ? new JsonArray(0, 0, 0, 0) : null;
    private static string CaptureText(FrameworkElement element) => element switch
    {
        TextBlock text => text.Text,
        TextBox box => box.Text,
        PasswordBox => "", // Password values are never evidence.
        ContentControl control when control.Content is string label => label,
        SelectorBarItem tab => tab.Text,
        MenuFlyoutItem item => item.Text,
        MenuFlyoutSubItem item => item.Text,
        MenuBarItem item => item.Title,
        RichTextBlock rich => string.Join("\n", rich.Blocks.OfType<Paragraph>().Select(p => CaptureInlines(p.Inlines))),
        _ => ""
    };
    private static string CaptureInlines(InlineCollection inlines) => string.Concat(inlines.Select(i => i switch { Run run => run.Text, LineBreak => "\n", Span span => CaptureInlines(span.Inlines), _ => "" }));
    private static JsonObject CaptureStyle(FrameworkElement element, double opacity, string id, JsonArray errors)
    {
        Brush? foreground = null, background = null, border = null; double? size = null, weight = null; var thickness = new Thickness(); var radius = new CornerRadius();
        switch (element)
        {
            case ReferenceVectorIcon v: foreground = v.VectorPath.Stroke; break;
            case Control c: foreground = c.Foreground; background = c.Background; border = c.BorderBrush; size = c.FontSize; weight = c.FontWeight.Weight; thickness = c.BorderThickness; radius = c.CornerRadius; break;
            case TextBlock t: foreground = t.Foreground; size = t.FontSize; weight = t.FontWeight.Weight; break;
            case RichTextBlock t: foreground = t.Foreground; size = t.FontSize; weight = t.FontWeight.Weight; break;
            case Border b: background = b.Background; border = b.BorderBrush; thickness = b.BorderThickness; radius = b.CornerRadius; break;
            case Panel p: background = p.Background; break;
            case FontIcon i: foreground = i.Foreground; size = i.FontSize; weight = i.FontWeight.Weight; break;
            case IconElement i: foreground = i.Foreground; break;
            case Shape s: foreground = s.Stroke; background = s.Fill; break;
        }
        if (element.Shadow != null) errors.Add(id + ": actual " + element.Shadow.GetType().Name + " shadow needs paint measurement");
        if (background != null && background is not SolidColorBrush) errors.Add(id + ": actual " + background.GetType().Name + " background brush needs gradient/image measurement");
        return new JsonObject
        {
            ["font_size"] = size, ["font_weight"] = weight, ["foreground"] = foreground == null && size == null ? null : CaptureColor(foreground),
            ["background"] = CaptureColor(background), ["border_color"] = CaptureColor(border),
            ["background_image"] = background == null || background is SolidColorBrush ? "none" : null,
            ["background_brush_type"] = background?.GetType().Name,
            ["opacity"] = opacity,
            ["shadow"] = element.Shadow == null ? new JsonArray() : null,
            ["shadow_type"] = element.Shadow?.GetType().Name,
            ["border_width"] = Math.Max(Math.Max(thickness.Left, thickness.Right), Math.Max(thickness.Top, thickness.Bottom)),
            ["corner_radius"] = radius.TopLeft,
            ["border_widths"] = new JsonArray(thickness.Top, thickness.Right, thickness.Bottom, thickness.Left),
            ["border_widths_order"] = "top,right,bottom,left",
            ["border_colors"] = new JsonArray(CaptureColor(border), CaptureColor(border), CaptureColor(border), CaptureColor(border)),
            ["corner_radii"] = new JsonArray(radius.TopLeft, radius.TopRight, radius.BottomRight, radius.BottomLeft)
        };
    }
    private static void CaptureStrokeEvidence(Shape shape, UIElement captureRoot, JsonObject node, string id, JsonArray errors)
    {
        var transform = shape.TransformToVisual(captureRoot);
        var zero = transform.TransformPoint(new Point(0, 0));
        var unitX = transform.TransformPoint(new Point(1, 0)); var unitY = transform.TransformPoint(new Point(0, 1));
        var ax = unitX.X - zero.X; var ay = unitX.Y - zero.Y;
        var bx = unitY.X - zero.X; var by = unitY.Y - zero.Y;
        var scaleX = Math.Sqrt(ax * ax + ay * ay); var scaleY = Math.Sqrt(bx * bx + by * by);
        var uniform = double.IsFinite(scaleX) && double.IsFinite(scaleY) && Math.Abs(scaleX - scaleY) < 1e-8 && Math.Abs(ax * bx + ay * by) < 1e-8;
        node["stroke_evidence"] = new JsonObject
        {
            ["raw_width"] = shape.StrokeThickness, ["scale_x"] = scaleX, ["scale_y"] = scaleY,
            ["basis_x"] = new JsonObject { ["x"] = ax, ["y"] = ay }, ["basis_y"] = new JsonObject { ["x"] = bx, ["y"] = by },
            ["source"] = "Shape.StrokeThickness and actual Shape.TransformToVisual(content-root)"
        };
        node["style"]!["stroke_width"] = uniform ? shape.StrokeThickness * scaleX : null;
        node["style"]!["foreground"] = CaptureColor(shape.Stroke);
        if (!uniform) errors.Add(id + ": nonuniform or non-finite actual stroke transform requires directional stroke measurement");
    }
    private static IEnumerable<TextElement> CaptureTextLeaves(InlineCollection inlines)
    {
        foreach (var inline in inlines)
        {
            if (inline is Microsoft.UI.Xaml.Documents.Run or LineBreak) yield return inline;
            else if (inline is Span span) foreach (var leaf in CaptureTextLeaves(span.Inlines)) yield return leaf;
        }
    }
    private static JsonObject CaptureTextLayout(FrameworkElement element, string id, JsonArray errors, UIElement captureRoot, bool visible)
    {
        var wrap = element switch { TextBlock t => t.TextWrapping.ToString(), RichTextBlock t => t.TextWrapping.ToString(), TextBox t => t.TextWrapping.ToString(), _ => "" };
        var trim = element switch { TextBlock t => t.TextTrimming.ToString(), RichTextBlock t => t.TextTrimming.ToString(), _ => "" };
        int? lines = null; var boxes = new JsonArray(); var localBoxes = new JsonArray(); var runs = new JsonArray();
        TextPointer? start = element switch { TextBlock t => t.ContentStart, RichTextBlock t => t.ContentStart, _ => null };
        TextPointer? end = element switch { TextBlock t => t.ContentEnd, RichTextBlock t => t.ContentEnd, _ => null };
        if (visible && start != null && end != null)
        {
            var ys = new HashSet<double>(); var incomplete = false;
            var leaves = element switch
            {
                TextBlock plainText => CaptureTextLeaves(plainText.Inlines).ToArray(),
                RichTextBlock rich => rich.Blocks.OfType<Paragraph>().SelectMany(p => CaptureTextLeaves(p.Inlines)).ToArray(),
                _ => Array.Empty<TextElement>()
            };
            var ranges = leaves.Length > 0
                ? leaves.Select(leaf => (start: leaf.ContentStart, end: leaf.ContentEnd, leaf: (TextElement?)leaf)).ToArray()
                : new[] { (start, end, leaf: (TextElement?)null) };
            var transform = element.TransformToVisual(captureRoot);
            foreach (var range in ranges)
            {
                var runBoxes = new JsonArray(); var runIncomplete = false;
                for (var offset = 0; offset < range.end.Offset - range.start.Offset; offset++)
                {
                    var pointer = range.start.GetPositionAtOffset(offset, LogicalDirection.Forward);
                    if (pointer == null) { incomplete = runIncomplete = true; errors.Add(id + ": TextPointer missing at offset " + offset); continue; }
                    var box = pointer.GetCharacterRect(LogicalDirection.Forward);
                    localBoxes.Add(CaptureBox(box));
                    if (!CaptureRectFinite(box))
                    {
                        incomplete = runIncomplete = true;
                        errors.Add(id + ": non-finite TextPointer rectangle at content offset " + pointer.Offset);
                    }
                    else if (box.Height > 0)
                    {
                        var actual = transform.TransformBounds(box);
                        boxes.Add(CaptureBox(actual)); runBoxes.Add(CaptureBox(actual));
                        if (CaptureRectFinite(actual)) ys.Add(Math.Round(actual.Y, 2));
                        else incomplete = runIncomplete = true;
                    }
                }
                if (range.leaf != null) runs.Add(new JsonObject
                {
                    ["type"] = range.leaf.GetType().Name,
                    ["text"] = range.leaf is Run run ? run.Text : "\n",
                    ["start_offset"] = range.start.Offset, ["end_offset"] = range.end.Offset,
                    ["font_size"] = range.leaf.FontSize, ["font_weight"] = range.leaf.FontWeight.Weight,
                    ["foreground"] = CaptureColor(range.leaf.Foreground), ["font_family"] = range.leaf.FontFamily.Source,
                    ["bounds"] = runBoxes, ["coordinate_space"] = "content-window", ["geometry_complete"] = !runIncomplete
                });
            }
            lines = incomplete ? null : ys.Count;
        }
        return new JsonObject
        {
            ["wrap"] = wrap.Length == 0 ? null : wrap == "NoWrap" ? "none" : wrap == "WrapWholeWords" ? "word" : "character",
            ["truncation"] = trim.Length == 0 ? null : trim.Contains("Ellipsis") ? "ellipsis" : trim == "Clip" ? "clip" : "none",
            ["line_count"] = lines, ["character_boxes"] = boxes,
            ["character_boxes_coordinate_space"] = "content-window", ["local_character_boxes"] = localBoxes,
            ["text_geometry_status"] = visible ? "measured-or-explicit-error" : "not-visible",
            ["rich_text_runs"] = runs,
            ["placeholder"] = element is TextBox text ? text.PlaceholderText : null
        };
    }
    [System.Runtime.InteropServices.DllImport("user32.dll")] private static extern bool GetCursorPos(ref CapturePoint point);
}
