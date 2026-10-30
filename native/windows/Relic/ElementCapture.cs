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
        var declaredContent = new Dictionary<DependencyObject, (string Owner, string Property)>();
        var renderIds = new Dictionary<DependencyObject, string>();
        var paintLayer = 0;
        var viewport = new Rect(0, 0, width, height);
        var cursor = new CapturePoint(); GetCursorPos(ref cursor); var clientOrigin = new CapturePoint(); ClientToScreen(WinRT.Interop.WindowNative.GetWindowHandle(this), ref clientOrigin);
        var hovered = new HashSet<UIElement>(VisualTreeHelper.FindElementsInHostCoordinates(new Point(cursor.x - clientOrigin.x, cursor.y - clientOrigin.y), root, true));
        string Region(DependencyObject value, string current)
        {
            if (ReferenceEquals(value, sidebarSurface)) return "sidebar";
            if (ReferenceEquals(value, inspectorSurface)) return "right-pane";
            if (ReferenceEquals(value, composerRegion)) return "composer";
            if (ReferenceEquals(value, stream) || ReferenceEquals(value, chatHead) || ReferenceEquals(value, conversationBanner) || ReferenceEquals(value, emptyConversation)) return "conversation";
            if (ReferenceEquals(value, menu) || ReferenceEquals(value, toolbar) || ReferenceEquals(value, navigationButtons)) return "header";
            if (value is ContentDialog) return "dialog";
            if (value is MenuFlyoutPresenter || value is MenuFlyoutItem || value is MenuFlyoutSubItem || value is NativeToastNotice) return "menu";
            return current;
        }
        void Walk(DependencyObject value, string? parent, string region, Rect clip, double ancestorOpacity, string? hidden, int siblingOrder = 0)
        {
            if (!visited.Add(value)) return;
            var id = "xaml-" + nodes.Count; var type = value.GetType().Name; region = Region(value, region);
            renderIds[value] = id;
            var node = new JsonObject { ["id"] = id, ["parent"] = parent, ["type"] = type, ["region"] = region, ["order"] = nodes.Count };
            if (value is UIElement ordered) node["canvas_z_index"] = Canvas.GetZIndex(ordered);
            node["render_sibling_order"] = siblingOrder;
            node["paint_order"] = nodes.Count;
            node["paint_layer"] = paintLayer;
            if (declaredContent.TryGetValue(value, out var contentOwner))
            {
                node["declared_content_owner"] = contentOwner.Owner;
                node["declared_content_source"] = contentOwner.Property;
            }
            if (value is ContentControl contentControl && contentControl.Content is DependencyObject controlContent) declaredContent[controlContent] = (id, "ContentControl.Content");
            if (value is Expander contentExpander && contentExpander.Content is DependencyObject expanderContent) declaredContent[expanderContent] = (id, "Expander.Content");
            // Only an object which also occurs in the actual visual walk can
            // receive this ownership. Tag strings and unused metadata do not
            // become rendered content or supply inferred labels.
            if (value is FrameworkElement tagged && tagged.Tag is UIElement tagContent) declaredContent[tagContent] = (id, "FrameworkElement.Tag UIElement in the actual visual tree");
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
                    var straightAxes = Math.Abs(m12) < 1e-8 && Math.Abs(m21) < 1e-8;
                    var swappedAxes = Math.Abs(m11) < 1e-8 && Math.Abs(m22) < 1e-8;
                    node["axis_aligned_transform"] = finiteTransform ? straightAxes || swappedAxes : null;
                    node["axis_alignment"] = !finiteTransform ? null : straightAxes ? "diagonal" : swappedAxes ? "quarter-turn-or-swapped-reflection" : "non-axis-aligned";
                    var corners = new JsonArray();
                    foreach (var local in new[] { new Point(0, 0), new Point(element.ActualWidth, 0), new Point(element.ActualWidth, element.ActualHeight), new Point(0, element.ActualHeight) })
                    {
                        var point = transform.TransformPoint(local);
                        corners.Add(new JsonObject { ["x"] = point.X, ["y"] = point.Y });
                    }
                    node["transformed_corners"] = corners;
                    node["transformed_corners_order"] = "top-left,top-right,bottom-right,bottom-left";
                    node["name"] = element.Name; node["accessible_name"] = AutomationProperties.GetName(element);
                    node["automation_id"] = AutomationProperties.GetAutomationId(element);
                    if (box.Width <= 0 || box.Height <= 0 || visible.Width <= 0 || visible.Height <= 0) hidden ??= "zero area or ancestor clip";
                    node["hidden_reason"] = hidden;
                    if ((element is ScrollViewer || type == "ScrollContentPresenter") && finiteBox) clip = IntersectCapture(clip, box);
                    node["style"] = CaptureStyle(element, opacity, id, errors, hidden == null);
                    if (element is NativeLabel nativeLabel)
                    {
                        var production = CaptureNativeLabel(nativeLabel);
                        node["native_label_evidence"] = production;
                        if (hidden == null && production["coverage_complete"]?.GetValue<bool>() != true)
                            errors.Add(id + ": actual DirectWrite production label evidence is incomplete: " + production["coverage_reason"]);
                    }
                    if (element is NativeTextarea textarea)
                    {
                        node["textarea_resize_evidence"] = new JsonObject
                        {
                            ["source"] = "Live production NativeTextarea properties",
                            ["sequence"] = textarea.ResizeSequence, ["delta_count"] = textarea.ResizeDeltaCount,
                            ["resizing"] = textarea.IsResizing, ["template_failure"] = textarea.ResizeTemplateFailure,
                            ["handle_attached"] = textarea.ResizeGrip?.IsLoaded == true
                        };
                        if (hidden == null && textarea.ResizeTemplateFailure != null) errors.Add(id + ": " + textarea.ResizeTemplateFailure);
                    }
                    if (element is Thumb resizeHandle && VisualTreeHelper.GetParent(resizeHandle) is NativeTextareaResizeGrip grip
                        && ReferenceEquals(grip.Handle, resizeHandle))
                    {
                        DependencyObject? owner = VisualTreeHelper.GetParent(grip);
                        while (owner != null && owner is not NativeTextarea) owner = VisualTreeHelper.GetParent(owner);
                        if (owner is NativeTextarea resizeOwner && ReferenceEquals(resizeOwner.ResizeGrip, grip) && renderIds.TryGetValue(owner, out var ownerId))
                            node["resize_handle_evidence"] = new JsonObject
                            {
                                ["source"] = "actual NativeTextarea.ResizeGrip.Handle object identity",
                                ["owner_id"] = ownerId, ["owner_type"] = resizeOwner.GetType().Name,
                                ["handle_type"] = resizeHandle.GetType().Name,
                                ["dragging"] = resizeHandle.IsDragging,
                                ["resize_sequence"] = resizeOwner.ResizeSequence,
                                ["resize_delta_count"] = resizeOwner.ResizeDeltaCount
                            };
                        else errors.Add(id + ": production textarea resize handle has no independently observed owner in this tree");
                    }
                    if (element is NativeShadowPanel nativeShadows)
                    {
                        var actual = new JsonArray();
                        foreach (var shadow in nativeShadows.RenderedShadows)
                            actual.Add(new JsonObject { ["blur_radius"] = shadow.BlurRadius,
                                ["offset"] = new JsonArray(shadow.Offset.X, shadow.Offset.Y, shadow.Offset.Z),
                                ["opacity"] = shadow.Opacity,
                                ["color"] = new JsonArray(shadow.Color.R, shadow.Color.G, shadow.Color.B, shadow.Color.A),
                                ["mask_type"] = shadow.Mask?.GetType().FullName, ["source_policy"] = shadow.SourcePolicy.ToString() });
                        node["composition_shadow_evidence"] = new JsonObject { ["source"] = "Actual production Composition DropShadow objects", ["layers"] = actual,
                            ["quantity"] = "Live Composition properties; CSS blur equivalence, clipping and final raster coverage remain unmeasured" };
                    }
                    node["paint_kind"] = element switch
                    {
                        Border or ContentPresenter => "rounded-rectangle", Panel => "rectangle", Rectangle => "rounded-rectangle",
                        Ellipse => "ellipse", Shape => "path", Image => "image", TextBlock or RichTextBlock or WorkspaceCodeView or NativeLabel or IconElement => "glyphs",
                        Control => "template", _ => "none"
                    };
                    node["render_type_evidence"] = new JsonObject { ["is_panel"] = element is Panel,
                        ["is_shape"] = element is Shape, ["is_content_control"] = element is ContentControl,
                        ["source"] = "Actual runtime XAML base types" };
                    if (element is Border borderElement) node["background_sizing"] = borderElement.BackgroundSizing.ToString();
                    if (element is ContentPresenter presenterElement) node["background_sizing"] = presenterElement.BackgroundSizing.ToString();
                    if (element is Rectangle rectangle) node["shape_corner_radius"] = new JsonObject { ["x"] = rectangle.RadiusX, ["y"] = rectangle.RadiusY };
                    node["text"] = CaptureText(element);
                    node["interaction_evidence"] = new JsonObject
                    {
                        ["is_control"] = element is Control,
                        ["is_tab_stop"] = element is Control keyboardControl ? keyboardControl.IsTabStop : null,
                        ["is_hit_test_visible"] = element.IsHitTestVisible,
                        ["source"] = "Actual XAML Control type, IsTabStop and IsHitTestVisible properties"
                    };
                    node["state"] = new JsonObject
                    {
                        ["enabled"] = element is Control control ? control.IsEnabled : null,
                        ["focused"] = element is Control focus ? focus.FocusState != FocusState.Unfocused : null,
                        ["selected"] = element is SelectorBarItem tab ? tab.IsSelected : element is SelectorItem item ? item.IsSelected : null,
                        ["current"] = element is ChartNodeButton chartNode ? chartNode.IsCurrent : null,
                        ["checked"] = element is ToggleButton toggle ? toggle.IsChecked : element is ToggleSwitch change ? change.IsOn : null,
                        ["indeterminate"] = element is ToggleButton triState ? triState.IsChecked == null : element is ToggleSwitch ? false : null,
                        ["expanded"] = element is Expander expander ? expander.IsExpanded : null,
                        ["hovered"] = hovered.Contains(element), ["unread"] = null
                    };
                    if (element is ChartNodeButton currentNode) node["state_evidence"] = new JsonObject
                    {
                        ["current"] = new JsonObject { ["value"] = currentNode.IsCurrent, ["source"] = "ChartNodeButton.IsCurrent", ["meaning"] = "Actual current organization state used by the chart control" }
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
                    else if (element is AnimatedIcon animatedIcon)
                        node["animated_icon_evidence"] = new JsonObject { ["source_type"] = animatedIcon.Source?.GetType().FullName,
                            ["state"] = AnimatedIcon.GetState(animatedIcon), ["fallback_type"] = animatedIcon.FallbackIconSource?.GetType().FullName,
                            ["frame_geometry"] = null, ["reason"] = "Animated source and current state are retained; fallback artwork is not substituted for the active frame" };
                    else if (element is Image renderedImage)
                    {
                        var bitmap = renderedImage.Source as Microsoft.UI.Xaml.Media.Imaging.BitmapImage;
                        node["image_source_evidence"] = new JsonObject { ["type"] = renderedImage.Source?.GetType().FullName,
                            ["uri"] = bitmap?.UriSource?.ToString(), ["pixel_width"] = bitmap?.PixelWidth, ["pixel_height"] = bitmap?.PixelHeight,
                            ["stretch"] = renderedImage.Stretch.ToString() };
                        if (bitmap?.UriSource is { } sourceUri) node["icon"] = new JsonObject { ["source"] = "image", ["glyph"] = sourceUri.ToString() };
                    }
                    else if (element is Microsoft.UI.Xaml.Shapes.Path path) node["icon"] = new JsonObject { ["source"] = "xaml-path", ["glyph"] = path.Data?.ToString() };
                    if (element is Shape renderedShape) CaptureStrokeEvidence(renderedShape, root, node, id, errors);
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
            Walk(popup.Child, null, popup.Child is MenuFlyoutPresenter or NativeToastNotice ? "menu" : "dialog", viewport, 1, null);
        }
        if (popups.Length > 1) errors.Add("Multiple popup roots: their collection order requires independent HWND/compositor z-order verification.");
        var result = new JsonObject
        {
            ["schema_version"] = 1, ["scene_id"] = caseId, ["client"] = "windows",
            ["viewport"] = new JsonObject { ["width"] = width, ["height"] = height, ["scale"] = root.XamlRoot.RasterizationScale },
            ["raw_nodes"] = nodes, ["extraction_errors"] = errors,
            ["capture_evidence"] = new JsonObject { ["message_scene"] = capturedMessageEvidence?.DeepClone(),
                ["textarea_resize_action"] = capturedTextareaEvidence?.DeepClone() },
            ["paint_order_source"] = "VisualTreeHelper children, stable Canvas.ZIndex then actual child index; popup roots above main root",
            ["popup_roots"] = popups.Length,
            ["pointer"] = new JsonObject { ["x"] = cursor.x - clientOrigin.x, ["y"] = cursor.y - clientOrigin.y }
        };
        CaptureFiniteMeasurements(result, errors);
        await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(directory, caseId + ".xaml.json"), result.ToJsonString());
        var manifestDirectory = System.IO.Path.GetDirectoryName(Environment.GetEnvironmentVariable("RELIC_VISUAL_MANIFEST"))!;
        // A request is immutable and belongs to one scene. Replacing the shared
        // previous request could race Python's open/read on Windows, whose file
        // handle need not allow delete/rename sharing.
        var requests = System.IO.Path.Combine(manifestDirectory, "element-requests");
        var receipts = System.IO.Path.Combine(manifestDirectory, "element-receipts");
        System.IO.Directory.CreateDirectory(requests); System.IO.Directory.CreateDirectory(receipts);
        var request = System.IO.Path.Combine(requests, caseId + ".json");
        var receipt = System.IO.Path.Combine(receipts, caseId + ".json");
        if (System.IO.File.Exists(request) || System.IO.File.Exists(receipt)) throw new InvalidOperationException("Duplicate element capture scene " + caseId);
        var origin = new CapturePoint(); var handle = WinRT.Interop.WindowNative.GetWindowHandle(this); ClientToScreen(handle, ref origin);
        await System.IO.File.WriteAllTextAsync(request + ".tmp", JsonSerializer.Serialize(new { case_id = caseId, pid = Environment.ProcessId, hwnd = (long)handle, origin = new { x = origin.x, y = origin.y }, width, height }));
        System.IO.File.Move(request + ".tmp", request);
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
    private static JsonArray? CaptureColor(Brush? brush) => brush is SolidColorBrush solid ? new JsonArray(solid.Color.R, solid.Color.G, solid.Color.B, solid.Color.A * solid.Opacity) : brush == null ? new JsonArray(0, 0, 0, 0) : null;
    private static JsonObject CaptureBrushEvidence(Brush? brush)
    {
        var result = new JsonObject { ["type"] = brush?.GetType().FullName, ["opacity"] = brush?.Opacity, ["solid_rgba"] = CaptureColor(brush) };
        if (brush is SolidColorBrush solid)
            result["solid_color_rgba8"] = new JsonArray(solid.Color.R, solid.Color.G, solid.Color.B, solid.Color.A);
        result["solid_rgba_quantity"] = "Actual unpremultiplied brush sRGB components in 0..255; color alpha multiplied by live Brush.Opacity without raster rounding";
        if (brush is GradientBrush gradient)
        {
            result["mapping_mode"] = gradient.MappingMode.ToString(); result["spread_method"] = gradient.SpreadMethod.ToString();
            result["color_interpolation"] = gradient.ColorInterpolationMode.ToString();
            result["stops"] = new JsonArray(gradient.GradientStops.Select(stop => (JsonNode)new JsonObject
                { ["offset"] = stop.Offset, ["rgba"] = new JsonArray(stop.Color.R, stop.Color.G, stop.Color.B, stop.Color.A) }).ToArray());
        }
        if (brush is LinearGradientBrush linear)
        {
            result["start"] = new JsonObject { ["x"] = linear.StartPoint.X, ["y"] = linear.StartPoint.Y };
            result["end"] = new JsonObject { ["x"] = linear.EndPoint.X, ["y"] = linear.EndPoint.Y };
        }
        if (brush is ImageBrush image) result["image"] = CaptureImageBrush(image);
        return result;
    }
    private static string CaptureText(FrameworkElement element) => element switch
    {
        TextBlock text => text.Text,
        NativeLabel text => text.Text,
        WorkspaceCodeView code => code.ReadSourceText(),
        ComposerInput input => input.Text,
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
    private static JsonObject CaptureStyle(FrameworkElement element, double opacity, string id, JsonArray errors, bool visible)
    {
        Brush? foreground = null, background = null, border = null; double? size = null, weight = null; var thickness = new Thickness(); var radius = new CornerRadius();
        switch (element)
        {
            case ReferenceVectorIcon v: foreground = v.VectorPath.Stroke; break;
            case Control c: foreground = c.Foreground; background = c.Background; border = c.BorderBrush; size = c.FontSize; weight = c.FontWeight.Weight; thickness = c.BorderThickness; radius = c.CornerRadius; break;
            case TextBlock t: foreground = t.Foreground; size = t.FontSize; weight = t.FontWeight.Weight; break;
            case RichTextBlock t: foreground = t.Foreground; size = t.FontSize; weight = t.FontWeight.Weight; break;
            case Border b: background = b.Background; border = b.BorderBrush; thickness = b.BorderThickness; radius = b.CornerRadius; break;
            case ContentPresenter p: foreground = p.Foreground; background = p.Background; border = p.BorderBrush; thickness = p.BorderThickness; radius = p.CornerRadius; size = p.FontSize; weight = p.FontWeight.Weight; break;
            case Panel p: background = p.Background; break;
            case FontIcon i: foreground = i.Foreground; size = i.FontSize; weight = i.FontWeight.Weight; break;
            case IconElement i: foreground = i.Foreground; break;
            case Shape s: foreground = s.Stroke; background = s.Fill; break;
        }
        var paintDiagnostics = new JsonArray();
        void PaintGap(string reason)
        {
            paintDiagnostics.Add(reason);
            if (visible) errors.Add(id + ": " + reason);
        }
        if (element.Shadow != null) PaintGap("actual " + element.Shadow.GetType().Name + " shadow needs paint measurement");
        if (element is NativeShadowPanel) PaintGap("production Composition DropShadow layers require independent raster/clip and blur-quantity measurement");
        if (background != null && background is not SolidColorBrush) PaintGap("actual " + background.GetType().Name + " background brush needs gradient/image measurement");
        var borderWidth = Math.Max(Math.Max(thickness.Left, thickness.Right), Math.Max(thickness.Top, thickness.Bottom));
        if (borderWidth > 0 && border != null && border is not SolidColorBrush) PaintGap("actual " + border.GetType().Name + " visible border brush needs directional gradient/image measurement");
        JsonArray? BorderColor(double width) => width > 0 ? CaptureColor(border) : new JsonArray(0, 0, 0, 0);
        return new JsonObject
        {
            ["font_size"] = size, ["font_weight"] = weight, ["foreground"] = foreground == null && size == null ? null : CaptureColor(foreground),
            ["background"] = CaptureColor(background), ["border_color"] = BorderColor(borderWidth),
            ["brush_evidence"] = new JsonObject { ["foreground"] = CaptureBrushEvidence(foreground), ["background"] = CaptureBrushEvidence(background), ["border"] = CaptureBrushEvidence(border) },
            ["paint_diagnostics"] = paintDiagnostics, ["paint_diagnostics_applicability"] = visible ? "visible" : "not-visible",
            ["background_image"] = background == null || background is SolidColorBrush ? "none" : null,
            ["background_brush_type"] = background?.GetType().Name,
            ["opacity"] = opacity,
            ["shadow"] = element.Shadow == null && element is not NativeShadowPanel ? new JsonArray() : null,
            ["shadow_type"] = element.Shadow?.GetType().Name,
            ["border_width"] = borderWidth,
            ["corner_radius"] = Math.Max(Math.Max(radius.TopLeft, radius.TopRight), Math.Max(radius.BottomRight, radius.BottomLeft)),
            ["border_widths"] = new JsonArray(thickness.Top, thickness.Right, thickness.Bottom, thickness.Left),
            ["border_widths_order"] = "top,right,bottom,left",
            ["border_colors"] = new JsonArray(BorderColor(thickness.Top), BorderColor(thickness.Right), BorderColor(thickness.Bottom), BorderColor(thickness.Left)),
            ["border_styles"] = new JsonArray(thickness.Top > 0 ? "solid" : "none", thickness.Right > 0 ? "solid" : "none", thickness.Bottom > 0 ? "solid" : "none", thickness.Left > 0 ? "solid" : "none"),
            ["corner_radii"] = new JsonArray(radius.TopLeft, radius.TopRight, radius.BottomRight, radius.BottomLeft)
        };
    }
    private static void CaptureStrokeEvidence(Shape shape, UIElement captureRoot, JsonObject node, string id, JsonArray errors)
    {
        var rawDashes = shape.StrokeDashArray?.ToArray() ?? [];
        string Cap(PenLineCap cap) => cap == PenLineCap.Flat ? "butt" : cap.ToString().ToLowerInvariant();
        var startCap = Cap(shape.StrokeStartLineCap); var endCap = Cap(shape.StrokeEndLineCap); var dashCap = Cap(shape.StrokeDashCap);
        var commonCap = startCap == endCap && (rawDashes.Length == 0 || startCap == dashCap) ? startCap : null;
        var strokeStyle = (JsonObject)node["style"]!;
        strokeStyle["stroke_dash"] = rawDashes.Length == 0 ? new JsonArray() : null;
        strokeStyle["stroke_dash_offset"] = null;
        strokeStyle["stroke_linecap"] = commonCap;
        strokeStyle["stroke_linejoin"] = shape.StrokeLineJoin.ToString().ToLowerInvariant();
        strokeStyle["stroke_miterlimit"] = shape.StrokeMiterLimit;
        var rawPattern = new JsonObject { ["dash_array"] = new JsonArray(rawDashes.Select(value => (JsonNode?)JsonValue.Create(value)).ToArray()),
            ["dash_offset"] = shape.StrokeDashOffset, ["dash_units"] = "multiples of Shape.StrokeThickness",
            ["start_linecap"] = startCap, ["end_linecap"] = endCap, ["dash_linecap"] = dashCap,
            ["linejoin"] = shape.StrokeLineJoin.ToString(), ["miter_limit"] = shape.StrokeMiterLimit };
        var visibleStroke = node["hidden_reason"] == null && shape.Stroke != null && shape.StrokeThickness > 0;
        if (commonCap == null && visibleStroke) errors.Add(id + ": distinct actual stroke start/end/dash caps cannot be represented by one canonical linecap");
        var transform = shape.TransformToVisual(captureRoot);
        var zero = transform.TransformPoint(new Point(0, 0));
        var unitX = transform.TransformPoint(new Point(1, 0)); var unitY = transform.TransformPoint(new Point(0, 1));
        // One-unit differences lose significant bits when WinUI's float-backed
        // transform adds a large window translation. Measure the actual shape
        // axes over their complete layout extent instead, retaining both reads.
        var extentX = shape.ActualWidth; var extentY = shape.ActualHeight;
        if (!(extentX > 0 && extentY > 0))
        {
            node["stroke_evidence"] = new JsonObject { ["raw_width"] = shape.StrokeThickness,
                ["raw_pattern"] = rawPattern,
                ["source_extent"] = new JsonObject { ["x"] = extentX, ["y"] = extentY },
                ["measurement_status"] = "No positive two-axis layout extent is available",
                ["source"] = "Actual Shape layout extent before TransformToVisual axis measurement" };
            node["style"]!["stroke_width"] = null;
            if (visibleStroke)
                errors.Add(id + ": stroke transform requires positive actual shape axes or measured directional line geometry");
            return;
        }
        var axisX = transform.TransformPoint(new Point(extentX, 0));
        var axisY = transform.TransformPoint(new Point(0, extentY));
        var ax = extentX > 0 ? (axisX.X - zero.X) / extentX : double.NaN;
        var ay = extentX > 0 ? (axisX.Y - zero.Y) / extentX : double.NaN;
        var bx = extentY > 0 ? (axisY.X - zero.X) / extentY : double.NaN;
        var by = extentY > 0 ? (axisY.Y - zero.Y) / extentY : double.NaN;
        var scaleX = Math.Sqrt(ax * ax + ay * ay); var scaleY = Math.Sqrt(bx * bx + by * by);
        var uniform = double.IsFinite(scaleX) && double.IsFinite(scaleY) && Math.Abs(scaleX - scaleY) < 1e-8 && Math.Abs(ax * bx + ay * by) < 1e-8;
        node["stroke_evidence"] = new JsonObject
        {
            ["raw_width"] = shape.StrokeThickness, ["scale_x"] = scaleX, ["scale_y"] = scaleY,
            ["raw_pattern"] = rawPattern,
            ["basis_x"] = new JsonObject { ["x"] = ax, ["y"] = ay }, ["basis_y"] = new JsonObject { ["x"] = bx, ["y"] = by },
            ["source_extent"] = new JsonObject { ["x"] = extentX, ["y"] = extentY },
            ["origin"] = new JsonObject { ["x"] = zero.X, ["y"] = zero.Y },
            ["axis_endpoint_x"] = new JsonObject { ["x"] = axisX.X, ["y"] = axisX.Y },
            ["axis_endpoint_y"] = new JsonObject { ["x"] = axisY.X, ["y"] = axisY.Y },
            ["unit_difference_x"] = new JsonObject { ["x"] = unitX.X - zero.X, ["y"] = unitX.Y - zero.Y },
            ["unit_difference_y"] = new JsonObject { ["x"] = unitY.X - zero.X, ["y"] = unitY.Y - zero.Y },
            ["source"] = "Shape.StrokeThickness and full actual Shape.TransformToVisual(content-root) layout-axis endpoints; unit-difference diagnostics retained"
        };
        node["style"]!["stroke_width"] = uniform ? shape.StrokeThickness * scaleX : null;
        if (uniform)
        {
            var strokeScale = shape.StrokeThickness * scaleX;
            // An odd pattern alternates stroke/gap on its next repetition, so
            // its complete measured period contains two copies (WinUI docs).
            var period = rawDashes.Length % 2 == 1 ? rawDashes.Concat(rawDashes).ToArray() : rawDashes;
            strokeStyle["stroke_dash"] = new JsonArray(period.Select(value => (JsonNode?)JsonValue.Create(value * strokeScale)).ToArray());
            strokeStyle["stroke_dash_offset"] = shape.StrokeDashOffset * strokeScale;
            if (rawDashes.Length > 0 && rawDashes.All(value => value == 0))
            {
                strokeStyle["stroke_dash"] = null;
                if (visibleStroke) errors.Add(id + ": actual all-zero WinUI dash pattern needs renderer evidence; SVG solid behavior is not presumed");
            }
        }
        node["style"]!["foreground"] = CaptureColor(shape.Stroke);
        if (!uniform && visibleStroke) errors.Add(id + ": nonuniform or non-finite actual stroke transform requires directional stroke measurement");
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
        if (element is WorkspaceCodeView code) return CaptureCodeDocument(code, id, errors, captureRoot, visible);
        if (element is ComposerInput input) return CaptureComposerDocument(input, id, errors, captureRoot, visible);
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
                var runBoxes = new JsonArray(); var runCarets = new JsonArray(); var runIncomplete = false;
                var caretRectangles = new List<Rect>();
                var length = range.end.Offset - range.start.Offset;
                for (var offset = 0; offset <= length; offset++)
                {
                    var pointer = range.start.GetPositionAtOffset(offset, LogicalDirection.Forward);
                    if (pointer == null) { incomplete = runIncomplete = true; errors.Add(id + ": TextPointer missing at offset " + offset); continue; }
                    // WinUI reports insertion-caret rectangles (often width 0),
                    // not glyph ink boxes. Measure both sides at interior text
                    // boundaries so wrapped line endings retain their advance.
                    var directions = offset == 0 ? new[] { LogicalDirection.Forward }
                        : offset == length ? new[] { LogicalDirection.Backward }
                        : new[] { LogicalDirection.Forward, LogicalDirection.Backward };
                    foreach (var direction in directions)
                    {
                        var box = pointer.GetCharacterRect(direction);
                        localBoxes.Add(CaptureBox(box));
                        if (!CaptureRectFinite(box))
                        {
                            incomplete = runIncomplete = true;
                            errors.Add(id + ": non-finite TextPointer caret rectangle at content offset " + pointer.Offset + " " + direction);
                        }
                        else if (box.Height > 0)
                        {
                            var actual = transform.TransformBounds(box);
                            runCarets.Add(new JsonObject { ["offset"] = pointer.Offset, ["direction"] = direction.ToString(), ["bounds"] = CaptureBox(actual) });
                            if (CaptureRectFinite(actual)) caretRectangles.Add(actual);
                            else incomplete = runIncomplete = true;
                        }
                    }
                }
                foreach (var line in caretRectangles.GroupBy(rect => (Math.Round(rect.Y, 4), Math.Round(rect.Height, 4))))
                {
                    if (line.Zip(line.Skip(1), (previous, next) => next.X < previous.X - 1e-6).Any(backwards => backwards))
                    {
                        incomplete = runIncomplete = true;
                        errors.Add(id + ": nonmonotonic caret sequence requires disjoint text-range geometry; an advance envelope alone cannot prove coverage");
                    }
                    var left = line.Min(rect => rect.X); var right = line.Max(rect => rect.Right);
                    var top = line.Min(rect => rect.Y); var bottom = line.Max(rect => rect.Bottom);
                    if (right <= left) continue;
                    var actual = new Rect(left, top, right - left, bottom - top);
                    boxes.Add(CaptureBox(actual)); runBoxes.Add(CaptureBox(actual)); ys.Add(Math.Round(actual.Y, 2));
                }
                if (range.leaf != null) runs.Add(new JsonObject
                {
                    ["type"] = range.leaf.GetType().Name,
                    ["text"] = range.leaf is Run run ? run.Text : "\n",
                    ["start_offset"] = range.start.Offset, ["end_offset"] = range.end.Offset,
                    ["font_size"] = range.leaf.FontSize, ["font_weight"] = range.leaf.FontWeight.Weight,
                    ["foreground"] = CaptureColor(range.leaf.Foreground), ["font_family"] = range.leaf.FontFamily.Source,
                    ["bounds"] = runBoxes, ["caret_evidence"] = runCarets,
                    ["bounds_measurement"] = "Per-line text advance envelope of actual forward/backward TextPointer caret rectangles including both Run boundaries",
                    ["coordinate_space"] = "content-window", ["geometry_complete"] = !runIncomplete
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
            ["actual_trimming"] = element is TextBlock trimmed ? new JsonObject
            {
                ["is_text_trimmed"] = trimmed.IsTextTrimmed,
                ["source"] = "Live TextBlock.IsTextTrimmed; actual control overflow state, not an ellipsis glyph rectangle",
                ["ellipsis_bounds"] = null
            } : null,
            ["placeholder"] = element is TextBox text ? text.PlaceholderText : null
        };
    }
    [System.Runtime.InteropServices.DllImport("user32.dll")] private static extern bool GetCursorPos(ref CapturePoint point);
}
