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
        void Walk(DependencyObject value, string? parent, string region, Rect clip, double ancestorOpacity, string? hidden)
        {
            if (!visited.Add(value)) return;
            var id = "xaml-" + nodes.Count; var type = value.GetType().Name; region = Region(value, region);
            var node = new JsonObject { ["id"] = id, ["parent"] = parent, ["type"] = type, ["region"] = region, ["order"] = nodes.Count };
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
                    clip = IntersectCapture(clip, transformed);
                }
                else if (ui.Clip != null) errors.Add(id + ": nonrectangular clip requires coverage instrumentation");
            }
            if (value is FrameworkElement element)
            {
                try
                {
                    var box = element.TransformToVisual(root).TransformBounds(new Rect(0, 0, element.ActualWidth, element.ActualHeight));
                    var visible = IntersectCapture(clip, box);
                    node["bounds"] = CaptureBox(box); node["visible_bounds"] = CaptureBox(visible);
                    node["name"] = element.Name; node["accessible_name"] = AutomationProperties.GetName(element);
                    if (box.Width <= 0 || box.Height <= 0 || visible.Width <= 0 || visible.Height <= 0) hidden ??= "zero area or ancestor clip";
                    node["hidden_reason"] = hidden;
                    if (element is ScrollViewer || type == "ScrollContentPresenter") clip = IntersectCapture(clip, box);
                    node["style"] = CaptureStyle(element);
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
                    node["layout"] = CaptureTextLayout(element);
                    if (element is FontIcon fontIcon) node["icon"] = new JsonObject { ["source"] = fontIcon.FontFamily.Source, ["glyph"] = fontIcon.Glyph };
                    else if (element is ReferenceVectorIcon vectorIcon)
                    {
                        var shape = new JsonObject { ["tag"] = "svg", ["attributes"] = new JsonObject { ["height"] = vectorIcon.Height.ToString(System.Globalization.CultureInfo.InvariantCulture), ["viewBox"] = "0 0 24 24", ["width"] = vectorIcon.Width.ToString(System.Globalization.CultureInfo.InvariantCulture) },
                            ["children"] = new JsonArray(new JsonObject { ["tag"] = "path", ["attributes"] = new JsonObject { ["d"] = vectorIcon.PathData }, ["children"] = new JsonArray() }) };
                        node["icon"] = new JsonObject { ["source"] = "svg", ["glyph"] = shape.ToJsonString() };
                        node["vector_path"] = vectorIcon.PathData; node["vector_stroke_width"] = vectorIcon.VectorPath.StrokeThickness;
                    }
                    else if (element is SymbolIcon symbolIcon) node["icon"] = new JsonObject { ["source"] = "Segoe MDL2 Assets", ["glyph"] = ((int)symbolIcon.Symbol).ToString("X") };
                    else if (element is Microsoft.UI.Xaml.Shapes.Path path) node["icon"] = new JsonObject { ["source"] = "xaml-path", ["glyph"] = path.Data?.ToString() };
                    if (element is TextBlock block) node["font_family"] = block.FontFamily.Source;
                    if (element is Control fontControl) node["font_family"] = fontControl.FontFamily.Source;
                }
                catch (Exception ex) { node["measurement_error"] = ex.Message; errors.Add(id + ": " + ex.Message); }
            }
            else node["hidden_reason"] = "non-rendering dependency object";
            for (var i = 0; i < VisualTreeHelper.GetChildrenCount(value); i++) Walk(VisualTreeHelper.GetChild(value, i), id, region, clip, opacity, hidden);
        }
        Walk(root, null, "window", viewport, 1, null);
        foreach (var popup in VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot))
            if (popup.IsOpen && popup.Child != null) Walk(popup.Child, null, popup.Child is MenuFlyoutPresenter ? "menu" : "dialog", viewport, 1, null);
        var result = new JsonObject
        {
            ["schema_version"] = 1, ["scene_id"] = caseId, ["client"] = "windows",
            ["viewport"] = new JsonObject { ["width"] = width, ["height"] = height, ["scale"] = root.XamlRoot.RasterizationScale },
            ["raw_nodes"] = nodes, ["extraction_errors"] = errors
        };
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
    private static JsonObject CaptureBox(Rect box) => new() { ["x"] = box.X, ["y"] = box.Y, ["width"] = box.Width, ["height"] = box.Height };
    private static JsonArray? CaptureColor(Brush? brush) => brush is SolidColorBrush solid ? new JsonArray(solid.Color.R, solid.Color.G, solid.Color.B, (byte)Math.Round(solid.Color.A * solid.Opacity)) : brush == null ? new JsonArray(0, 0, 0, 0) : null;
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
    private static JsonObject CaptureStyle(FrameworkElement element)
    {
        Brush? foreground = null, background = null, border = null; double? size = null, weight = null; var thickness = new Thickness(); var radius = new CornerRadius();
        switch (element)
        {
            case Control c: foreground = c.Foreground; background = c.Background; border = c.BorderBrush; size = c.FontSize; weight = c.FontWeight.Weight; thickness = c.BorderThickness; radius = c.CornerRadius; break;
            case TextBlock t: foreground = t.Foreground; size = t.FontSize; weight = t.FontWeight.Weight; break;
            case RichTextBlock t: foreground = t.Foreground; size = t.FontSize; weight = t.FontWeight.Weight; break;
            case Border b: background = b.Background; border = b.BorderBrush; thickness = b.BorderThickness; radius = b.CornerRadius; break;
            case Panel p: background = p.Background; break;
            case FontIcon i: foreground = i.Foreground; size = i.FontSize; weight = i.FontWeight.Weight; break;
            case IconElement i: foreground = i.Foreground; break;
            case Shape s: background = s.Fill; border = s.Stroke; thickness = new Thickness(s.StrokeThickness); break;
        }
        return new JsonObject
        {
            ["font_size"] = size, ["font_weight"] = weight, ["foreground"] = foreground == null && size == null ? null : CaptureColor(foreground),
            ["background"] = CaptureColor(background), ["border_color"] = CaptureColor(border),
            ["border_width"] = Math.Max(Math.Max(thickness.Left, thickness.Right), Math.Max(thickness.Top, thickness.Bottom)),
            ["corner_radius"] = radius.TopLeft,
            ["border_widths"] = new JsonArray(thickness.Left, thickness.Top, thickness.Right, thickness.Bottom),
            ["corner_radii"] = new JsonArray(radius.TopLeft, radius.TopRight, radius.BottomRight, radius.BottomLeft)
        };
    }
    private static JsonObject CaptureTextLayout(FrameworkElement element)
    {
        var wrap = element switch { TextBlock t => t.TextWrapping.ToString(), RichTextBlock t => t.TextWrapping.ToString(), TextBox t => t.TextWrapping.ToString(), _ => "" };
        var trim = element switch { TextBlock t => t.TextTrimming.ToString(), RichTextBlock t => t.TextTrimming.ToString(), _ => "" };
        int? lines = null; var boxes = new JsonArray();
        TextPointer? start = element switch { TextBlock t => t.ContentStart, RichTextBlock t => t.ContentStart, _ => null };
        TextPointer? end = element switch { TextBlock t => t.ContentEnd, RichTextBlock t => t.ContentEnd, _ => null };
        if (start != null && end != null)
        {
            var ys = new HashSet<double>();
            for (var offset = 0; offset < end.Offset - start.Offset; offset++)
            {
                var pointer = start.GetPositionAtOffset(offset, LogicalDirection.Forward);
                if (pointer == null) continue;
                var box = pointer.GetCharacterRect(LogicalDirection.Forward);
                if (box.Height > 0) { ys.Add(Math.Round(box.Y, 2)); boxes.Add(CaptureBox(box)); }
            }
            lines = ys.Count;
        }
        return new JsonObject
        {
            ["wrap"] = wrap.Length == 0 ? null : wrap == "NoWrap" ? "none" : wrap == "WrapWholeWords" ? "word" : "character",
            ["truncation"] = trim.Length == 0 ? null : trim.Contains("Ellipsis") ? "ellipsis" : trim == "Clip" ? "clip" : "none",
            ["line_count"] = lines, ["character_boxes"] = boxes,
            ["placeholder"] = element is TextBox text ? text.PlaceholderText : null
        };
    }
    [System.Runtime.InteropServices.DllImport("user32.dll")] private static extern bool GetCursorPos(ref CapturePoint point);
}
