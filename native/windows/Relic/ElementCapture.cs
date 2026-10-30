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
        if (capturedNativeLabelEvidence?["failure"] != null)
            errors.Add("NativeLabel capture observer failed; frame/surface synchronization remains unmeasured: " + capturedNativeLabelEvidence["failure"]);
        if (capturedNativeLabelEvidence?["surface_readback_errors"] is JsonArray readbackErrors)
            foreach (var error in readbackErrors) errors.Add("NativeLabel actual target readback: " + error);
        var declaredContent = new Dictionary<DependencyObject, (string Owner, string Property)>();
        var renderIds = new Dictionary<DependencyObject, string>();
        var renderNodes = new Dictionary<DependencyObject, JsonObject>();
        var inlineOwners = new List<(FrameworkElement Owner, JsonObject Node, bool Visible)>();
        var fencedCodeOwners = new List<(Border Owner, MarkdownSemantic.FencedCode Content, JsonObject Node, bool Visible)>();
        var stateDotOwners = new List<(NativeStateDotView Owner, JsonObject Node, bool Visible)>();
        var scrollbarOwners = new List<(ScrollBar Owner, JsonObject Node, bool Visible)>();
        var paintLayer = 0;
        var viewport = new Rect(0, 0, width, height);
        var cursor = new CapturePoint(); GetCursorPos(ref cursor); var clientOrigin = new CapturePoint(); ClientToScreen(WinRT.Interop.WindowNative.GetWindowHandle(this), ref clientOrigin);
        var hovered = new HashSet<UIElement>(VisualTreeHelper.FindElementsInHostCoordinates(new Point(cursor.x - clientOrigin.x, cursor.y - clientOrigin.y), root, true));
        string Region(DependencyObject value, string current)
        {
            if (ReferenceEquals(value, titlebarRegion)) return "header";
            if (ReferenceEquals(value, treeRegion)) return "sidebar";
            if (ReferenceEquals(value, chatRegion) || ReferenceEquals(value, chatScroll)) return "conversation";
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
            renderNodes[value] = node;
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
                    node["language"] = element.Language;
                    if (ReferenceEquals(element, chatScroll))
                        node["region_container_evidence"] = new JsonObject
                        {
                            ["source"] = "actual MainWindow.chatScroll object identity", ["owner_type"] = nameof(MainWindow)
                        };
                    node["automation_id"] = AutomationProperties.GetAutomationId(element);
                    if (box.Width <= 0 || box.Height <= 0 || visible.Width <= 0 || visible.Height <= 0) hidden ??= "zero area or ancestor clip";
                    node["hidden_reason"] = hidden;
                    var compositionClip = CaptureCompositionClip(element, node);
                    node["composition_clip_evidence"] = compositionClip;
                    if (hidden == null && compositionClip["status"]?.GetValue<string>() != "measured")
                        errors.Add(id + ": Composition clip remains unmeasured: " + compositionClip["reason"]);
                    if ((element is ScrollViewer || type == "ScrollContentPresenter") && finiteBox) clip = IntersectCapture(clip, box);
                    node["style"] = CaptureStyle(element, opacity, id, errors, hidden == null);
                    if (element is NativeLabel nativeLabel)
                    {
                        var production = CaptureNativeLabel(nativeLabel);
                        node["native_label_evidence"] = production;
                        if (hidden == null && production["coverage_complete"]?.GetValue<bool>() != true)
                            errors.Add(id + ": actual DirectWrite production label evidence is incomplete: " + production["coverage_reason"]);
                    }
                    if (element is Image productionImage && VisualTreeHelper.GetParent(productionImage) is NativeLabel labelOwner
                        && labelOwner.OwnsProductionImage(productionImage) && renderIds.TryGetValue(labelOwner, out var labelOwnerId))
                    {
                        var binding = labelOwner.CaptureProductionImageBinding(productionImage);
                        binding["owner_id"] = labelOwnerId; node["native_label_surface_evidence"] = binding;
                        if (hidden == null && binding["surface_binding_same_com_identity"]?.GetValue<bool>() != true)
                            errors.Add(id + ": NativeLabel production image has no verified binding to its actual drawn surface");
                    }
                    if (element is TextBlock or RichTextBlock) inlineOwners.Add((element, node, hidden == null));
                    if (element is Border markdownContainer && MarkdownSemantic.TryGetFencedCode(markdownContainer, out var fencedCode) && fencedCode != null)
                        fencedCodeOwners.Add((markdownContainer, fencedCode, node, hidden == null));
                    if (element is NativeStateDotView stateDot) stateDotOwners.Add((stateDot, node, hidden == null));
                    if (element is ScrollBar scrollbar) scrollbarOwners.Add((scrollbar, node, hidden == null));
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
                    if (element is Thumb panelHandle && ReferenceEquals(panelHandle, panelResize))
                        node["resize_handle_evidence"] = new JsonObject
                        {
                            ["source"] = "actual MainWindow.panelResize object identity",
                            ["owner_type"] = nameof(MainWindow), ["handle_type"] = panelHandle.GetType().Name,
                            ["dragging"] = panelHandle.IsDragging
                        };
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
                            ["lifecycle"] = nativeShadows.ShadowLifecycleEvidence(),
                            ["quantity"] = "Live Composition properties; CSS blur equivalence, clipping and final raster coverage remain unmeasured" };
                    }
                    node["paint_kind"] = element switch
                    {
                        NativeLabel => "glyphs",
                        Border or ContentPresenter => "rounded-rectangle", Panel => "rectangle", Rectangle => "rounded-rectangle",
                        Ellipse => "ellipse", Shape => "path", Image => "image", TextBlock or RichTextBlock or WorkspaceCodeView or IconElement => "glyphs",
                        Control => "template", _ => "none"
                    };
                    node["render_type_evidence"] = new JsonObject { ["is_panel"] = element is Panel,
                        ["is_shape"] = element is Shape, ["is_content_control"] = element is ContentControl,
                        ["is_control"] = element is Control,
                        ["control_template_present"] = element is Control templatedControl ? templatedControl.Template != null : null,
                        ["source"] = "Actual runtime XAML base types" };
                    if (element is Border borderElement) node["background_sizing"] = borderElement.BackgroundSizing.ToString();
                    if (element is ContentPresenter presenterElement) node["background_sizing"] = presenterElement.BackgroundSizing.ToString();
                    if (element is Rectangle rectangle) node["shape_corner_radius"] = new JsonObject { ["x"] = rectangle.RadiusX, ["y"] = rectangle.RadiusY };
                    node["text"] = CaptureText(element);
                    if (element is TextBlock or RichTextBlock)
                        node["font_weight_configuration"] = CaptureFontWeightConfiguration(element, id, id,
                            node["style"]?["font_weight"]?.GetValue<double>());
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
                    if (element is NativeSidebarRow sidebarRow)
                    {
                        var sidebarState = sidebarRow.CaptureSidebarState();
                        node["state"]!["expanded"] = sidebarState["expanded"]?.DeepClone();
                        node["state"]!["unread"] = sidebarState["unread"]?.DeepClone();
                        node["state_evidence"] = sidebarState;
                        if (sidebarState["row_kind"]?.GetValue<string>() == "chat" && sidebarState["unread"] == null)
                            errors.Add(id + ": the actual sidebar chat content or retained unread badge is no longer bound to this row; unread state is unknown");
                    }
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
                        var svg = renderedImage.Source as Microsoft.UI.Xaml.Media.Imaging.SvgImageSource;
                        var svgAsset = NativeSvgAsset.Capture(renderedImage);
                        node["image_source_evidence"] = new JsonObject { ["type"] = renderedImage.Source?.GetType().FullName,
                            ["uri"] = bitmap?.UriSource?.ToString() ?? svg?.UriSource?.ToString(), ["pixel_width"] = bitmap?.PixelWidth, ["pixel_height"] = bitmap?.PixelHeight,
                            ["stretch"] = renderedImage.Stretch.ToString(), ["svg_asset"] = svgAsset };
                        if ((svg != null || svgAsset != null) && hidden == null && svgAsset?["content_binding_complete"]?.GetValue<bool>() != true)
                            errors.Add(id + ": actual SVG source bytes/decode/binding evidence is incomplete; URI is not image content identity");
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
        var outlineFocusEvidence = CaptureOutlineOwners(renderIds, renderNodes);
        CaptureNativeDialogSurfaces(renderIds, renderNodes);
        CaptureNativeToggleParts(renderIds, renderNodes);
        CaptureNativeTextareaPlaceholders(renderIds, renderNodes);
        CaptureNativeAvatarParts(renderIds, renderNodes);
        CaptureNativeInsetShadows(renderIds, renderNodes);
        CaptureSelectorContentBindings(renderIds, renderNodes);
        // Bind the retained badge by actual object identity only after its
        // independent visual record exists. Role badges are not unread badges.
        foreach (var (value, record) in renderNodes)
            if (value is NativeSidebarRow sidebarRow && record["state_evidence"] is JsonObject sidebarEvidence)
            {
                sidebarEvidence["owner_id"] = renderIds[sidebarRow];
                if (sidebarRow.BoundUnreadBadge is { } actualBadge && sidebarEvidence["chat_badge"] is JsonObject badgeEvidence)
                {
                    var found = renderIds.TryGetValue(actualBadge, out var badgeId) && renderNodes.ContainsKey(actualBadge);
                    badgeEvidence["badge_id"] = badgeId;
                    badgeEvidence["badge_in_actual_visual_walk"] = found;
                    if (!found) errors.Add(renderIds[sidebarRow] + ": retained sidebar unread badge has no independent current visual record");
                }
            }
        foreach (var (value, markerId) in renderIds)
            if (value is NativeListMarker marker && renderNodes.TryGetValue(value, out var markerNode))
            {
                renderIds.TryGetValue(marker.Disc, out var ellipseId);
                var parent = VisualTreeHelper.GetParent(marker.Disc);
                var parentId = parent != null && renderIds.TryGetValue(parent, out var knownParent) ? knownParent : null;
                var markerEvidence = marker.Capture(markerId, ellipseId, parentId, root);
                markerEvidence["window_content_id"] = renderIds.TryGetValue(root, out var rootId) ? rootId : null;
                markerEvidence["item_text_id"] = marker.ItemText != null && renderIds.TryGetValue(marker.ItemText, out var textId) ? textId : null;
                markerNode["native_list_marker_evidence"] = markerEvidence;
            }
        BindTextRangeFrameOwners(renderIds);
        // Second pass: bind retained production line objects only after every
        // actual popup/visual child has its independent traversal id.
        foreach (var (value, record) in renderNodes)
        {
            if (value is not NativePathText pathOwner) continue;
            try
            {
                var pathReceipt = pathOwner.CaptureProductionPathReceipt(); pathReceipt["owner_id"] = renderIds[pathOwner];
                var bindings = new JsonArray(); var complete = pathReceipt["status"]?.GetValue<string>() == "laid-out";
                foreach (var line in pathOwner.PaintedLines)
                {
                    var binding = pathOwner.CaptureProductionLineBinding(line.Label);
                    var found = renderIds.TryGetValue(line.Label, out var lineId) && renderNodes.ContainsKey(line.Label);
                    binding["owner_id"] = renderIds[pathOwner]; binding["line_id"] = lineId;
                    binding["line_in_actual_visual_walk"] = found;
                    var ancestors = new JsonArray(); var reachedOwner = false; var edgesMatch = true;
                    var seen = new HashSet<DependencyObject>(ReferenceEqualityComparer.Instance);
                    for (DependencyObject? current = line.Label; current != null && seen.Add(current); current = VisualTreeHelper.GetParent(current))
                    {
                        var actualParent = VisualTreeHelper.GetParent(current);
                        var childFound = renderIds.TryGetValue(current, out var childId);
                        var parentFound = actualParent != null && renderIds.TryGetValue(actualParent, out _);
                        var parentId = parentFound ? renderIds[actualParent!] : null;
                        if (ReferenceEquals(current, pathOwner)) { reachedOwner = true; break; }
                        var capturedMatches = childFound && parentFound && renderNodes[current]["parent"]?.GetValue<string>() == parentId;
                        edgesMatch &= capturedMatches;
                        ancestors.Add(new JsonObject { ["child_id"] = childId, ["parent_id"] = parentId,
                            ["actual_parent_in_visual_walk"] = parentFound, ["captured_parent_matches"] = capturedMatches });
                    }
                    binding["actual_ancestor_edges"] = ancestors;
                    binding["reaches_same_owner_object"] = reachedOwner;
                    binding["all_captured_edges_match"] = edgesMatch;
                    // Normal whitespace can have a different painted string.
                    // Preserve the actual source comparison (including false),
                    // and separately bind the real line to its production map.
                    var sourceSliceMatches = pathOwner.SourceText[line.Start..line.End] == line.Label.Text;
                    var mappedPaintMatches = binding["paint_slice_matches"]?.GetValue<bool>() == true
                        && binding["source_slice_matches"]?.GetValue<bool>() == sourceSliceMatches
                        && binding["complete_source_text"]?.GetValue<string>() == pathOwner.SourceText
                        && binding["source_to_paint"]?["source_text"]?.GetValue<string>() == pathOwner.SourceText
                        && JsonNode.DeepEquals(binding["source_to_paint"], pathReceipt["source_to_paint"])
                        && JsonNode.DeepEquals(binding["text_style"], pathReceipt["text_style"]);
                    binding["same_production_source_to_paint_map"] = mappedPaintMatches;
                    complete &= found && reachedOwner && edgesMatch && pathOwner.OwnsProductionLine(line.Label)
                        && mappedPaintMatches
                        && binding["same_current_body_parent"]?.GetValue<bool>() == true
                        && binding["same_content_body"]?.GetValue<bool>() == true;
                    if (found) renderNodes[line.Label]["native_path_line_evidence"] = binding.DeepClone();
                    bindings.Add(binding);
                }
                pathReceipt["actual_line_bindings"] = bindings; pathReceipt["actual_visual_bindings_complete"] = complete;
                record["native_path_evidence"] = pathReceipt;
                if (!complete && record["hidden_reason"] == null)
                    errors.Add(renderIds[pathOwner] + ": actual production path layout or retained visual line binding is incomplete");
            }
            catch (Exception error)
            {
                record["native_path_binding_error"] = error.ToString();
                if (record["hidden_reason"] == null) errors.Add(renderIds[pathOwner] + ": path object/source binding: " + error.Message);
            }
        }
        foreach (var (value, record) in renderNodes)
        {
            if (value is not MessageHeaderRow header) continue;
            var metrics = new JsonArray();
            var current = header.LastLayout != null && header.MeasuredChildren.Count == header.Children.Count;
            for (var index = 0; index < header.Children.Count; index++)
            {
                var child = header.Children[index];
                var baseline = child is NativeLabel label ? label.FirstBaseline : child is TextBlock text ? text.BaselineOffset : double.NaN;
                var measured = index < header.MeasuredChildren.Count ? header.MeasuredChildren[index] : (MessageHeaderMetric?)null;
                var sameMetrics = measured is { } prior && prior.Width == child.DesiredSize.Width
                    && prior.Height == child.DesiredSize.Height && prior.Baseline.Equals(baseline);
                current &= sameMetrics;
                metrics.Add(new JsonObject { ["index"] = index, ["id"] = renderIds.GetValueOrDefault(child),
                    ["same_parent_object"] = ReferenceEquals(VisualTreeHelper.GetParent(child), header),
                    ["desired_width"] = child.DesiredSize.Width, ["desired_height"] = child.DesiredSize.Height,
                    ["baseline"] = double.IsFinite(baseline) ? baseline : null,
                    ["baseline_finite"] = double.IsFinite(baseline), ["matches_last_layout_metrics"] = sameMetrics });
            }
            record["message_header_baseline_evidence"] = new JsonObject
            {
                ["source"] = "Actual MessageHeaderRow layout with each current production label first baseline",
                ["current_metrics_match"] = current, ["uses_measured_baselines"] = header.LastLayout?.UsesMeasuredBaselines,
                ["layout_width"] = header.LastLayout?.Width, ["layout_height"] = header.LastLayout?.Height,
                ["spacing"] = header.Spacing, ["children"] = metrics
            };
        }
        // Retain the original owners/peers across the independent UIA traversal.
        // This sidecar diagnoses provider initialization/COM aggregation only;
        // it never supplies or substitutes canonical element identities.
        using var providerProbe = AutomationProviderProbe.Begin(directory, caseId, renderIds);
        foreach (var (owner, ownerNode, visible) in scrollbarOwners)
        {
            var ownerId = renderIds[owner]; var edges = new JsonArray(); var roots = new JsonArray();
            var thumbs = new JsonArray(); var paints = new JsonArray(); var complete = owner.Template != null;
            var actualThumbs = new List<(Thumb Thumb, JsonArray Path)>();
            void ReadScrollbarChildren(DependencyObject parent, JsonArray path)
            {
                var count = VisualTreeHelper.GetChildrenCount(parent);
                for (var index = 0; index < count; index++)
                {
                    var child = VisualTreeHelper.GetChild(parent, index);
                    var parentFound = renderIds.TryGetValue(parent, out var parentId);
                    var childFound = renderIds.TryGetValue(child, out var childId);
                    var sameParent = ReferenceEquals(VisualTreeHelper.GetParent(child), parent);
                    var capturedParentMatches = childFound && renderNodes[child]["parent"]?.GetValue<string>() == parentId;
                    complete &= parentFound && childFound && sameParent && capturedParentMatches;
                    var edge = new JsonObject { ["id"] = childId, ["parent_id"] = parentId,
                        ["child_index"] = index, ["same_parent_object"] = sameParent,
                        ["captured_parent_matches"] = capturedParentMatches };
                    edges.Add(edge); if (ReferenceEquals(parent, owner)) roots.Add(childId);
                    var nextPath = (JsonArray)path.DeepClone(); nextPath.Add(edge.DeepClone());
                    if (childFound && child is FrameworkElement layoutElement)
                        renderNodes[child]["scrollbar_layout_evidence"] = new JsonObject
                        {
                            ["source"] = "Actual current ScrollBar template FrameworkElement properties",
                            ["horizontal_alignment"] = layoutElement.HorizontalAlignment.ToString(),
                            ["vertical_alignment"] = layoutElement.VerticalAlignment.ToString(),
                            ["use_layout_rounding"] = layoutElement.UseLayoutRounding,
                            ["width"] = double.IsFinite(layoutElement.Width) ? layoutElement.Width : null,
                            ["height"] = double.IsFinite(layoutElement.Height) ? layoutElement.Height : null,
                            ["width_is_auto"] = double.IsNaN(layoutElement.Width), ["height_is_auto"] = double.IsNaN(layoutElement.Height),
                            ["min_width"] = double.IsFinite(layoutElement.MinWidth) ? layoutElement.MinWidth : null,
                            ["min_height"] = double.IsFinite(layoutElement.MinHeight) ? layoutElement.MinHeight : null,
                            ["max_width"] = double.IsFinite(layoutElement.MaxWidth) ? layoutElement.MaxWidth : null,
                            ["max_height"] = double.IsFinite(layoutElement.MaxHeight) ? layoutElement.MaxHeight : null,
                            ["max_width_unbounded"] = double.IsPositiveInfinity(layoutElement.MaxWidth),
                            ["max_height_unbounded"] = double.IsPositiveInfinity(layoutElement.MaxHeight)
                        };
                    if (childFound && child is RepeatButton pageButton)
                        renderNodes[child]["scrollbar_page_hit_evidence"] = new JsonObject
                        {
                            ["source"] = "Actual RepeatButton object in current ScrollBar template subtree",
                            ["owner_id"] = ownerId, ["path"] = nextPath.DeepClone(),
                            ["is_pressed"] = pageButton.IsPressed, ["delay"] = pageButton.Delay,
                            ["interval"] = pageButton.Interval,
                            ["quantity"] = "Actual input region and repeat timing; no visible paint or action direction is inferred"
                        };
                    if (child is Thumb thumb) { thumbs.Add(childId); actualThumbs.Add((thumb, nextPath)); }
                    if (childFound && renderNodes[child]["paint_kind"]?.GetValue<string>() is { } paintKind
                        && paintKind is not "none" and not "template") paints.Add(childId);
                    // An independently nested ScrollBar owns its own template tree.
                    if (child is not ScrollBar) ReadScrollbarChildren(child, nextPath);
                }
            }
            ReadScrollbarChildren(owner, new JsonArray());
            double? FiniteScroll(double value) => double.IsFinite(value) ? value : null;
            var range = new JsonObject { ["minimum"] = FiniteScroll(owner.Minimum), ["maximum"] = FiniteScroll(owner.Maximum),
                ["value"] = FiniteScroll(owner.Value), ["small_change"] = FiniteScroll(owner.SmallChange),
                ["large_change"] = FiniteScroll(owner.LargeChange), ["viewport_size"] = FiniteScroll(owner.ViewportSize) };
            ownerNode["scrollbar_evidence"] = new JsonObject
            {
                ["source"] = "actual ScrollBar runtime properties and current visual subtree",
                ["complete"] = complete, ["template_present"] = owner.Template != null,
                ["orientation"] = owner.Orientation.ToString().ToLowerInvariant(), ["range"] = range,
                ["template_roots"] = roots, ["visual_subtree"] = edges, ["thumb_ids"] = thumbs, ["paint_ids"] = paints,
                ["quantity"] = "Actual control hit bounds and retained template paint layers; range does not determine paint geometry"
            };
            foreach (var (thumb, path) in actualThumbs)
                if (renderNodes.TryGetValue(thumb, out var thumbNode))
                    thumbNode["scrollbar_thumb_evidence"] = new JsonObject
                    {
                        ["source"] = "actual Thumb visual ancestry to ScrollBar and current template subtree identities",
                        ["complete"] = complete, ["owner_id"] = ownerId, ["path"] = path,
                        ["dragging"] = thumb.IsDragging,
                        ["quantity"] = "Actual Thumb hit bounds; descendant paint is measured independently"
                    };
            if (visible && !complete) errors.Add(ownerId + ": ScrollBar template objects changed or are absent from the captured render tree");
        }
        foreach (var (owner, ownerNode, visible) in stateDotOwners)
        {
            var ownerId = renderIds[owner]; var currentChildren = new JsonArray(); var layers = new JsonArray();
            var complete = owner.HasCurrentPaintChildren;
            foreach (var child in owner.Children)
            {
                var found = renderIds.TryGetValue(child, out var childId);
                currentChildren.Add(childId); complete &= found;
            }
            foreach (var (role, paint) in owner.OwnedPaintLayers())
            {
                var found = renderIds.TryGetValue(paint, out var paintId);
                var index = owner.Children.IndexOf(paint);
                complete &= found && index >= 0 && ReferenceEquals(VisualTreeHelper.GetParent(paint), owner);
                layers.Add(new JsonObject { ["id"] = paintId, ["property"] = role, ["child_index"] = index });
                if (found)
                    renderNodes[paint]["state_dot_layer_evidence"] = new JsonObject
                    {
                        ["source"] = "actual NativeStateDotView owned Ellipse object identity",
                        ["owner_id"] = ownerId, ["property"] = role, ["child_index"] = index
                    };
            }
            ownerNode["state_dot_evidence"] = new JsonObject
            {
                ["source"] = "actual NativeStateDotView owned paint objects and current Children order",
                ["complete"] = complete, ["current_children_same_objects"] = owner.HasCurrentPaintChildren,
                ["current_children"] = currentChildren, ["layers"] = layers,
                ["quantity"] = "Production compound paint ownership; no CSS shadow or final raster equivalence is asserted"
            };
            if (visible && !complete) errors.Add(ownerId + ": state-dot paint objects are detached, replaced or absent from the actual render tree");
        }
        foreach (var (owner, content, ownerNode, visible) in fencedCodeOwners)
        {
            var ownerId = renderIds[owner];
            var actualScroller = ReferenceEquals(owner.Child, content.Scroller);
            var actualText = ReferenceEquals(content.Scroller.Content, content.Text);
            var foundScroller = renderIds.TryGetValue(content.Scroller, out var scrollerId);
            var foundText = renderIds.TryGetValue(content.Text, out var textId);
            var complete = actualScroller && actualText && foundScroller && foundText;
            ownerNode["markdown_code_evidence"] = new JsonObject
            {
                ["source"] = "actual MarkdownSemantic.RegisterFencedCode object identities", ["kind"] = "fenced-code",
                ["complete"] = complete, ["scroller_id"] = scrollerId, ["text_id"] = textId,
                ["border_child_is_registered_scroller"] = actualScroller, ["scroller_content_is_registered_text"] = actualText
            };
            if (foundScroller)
                renderNodes[content.Scroller]["markdown_code_scroller_evidence"] = new JsonObject
                {
                    ["source"] = "actual MarkdownSemantic.RegisterFencedCode scroller object identity",
                    ["owner_id"] = ownerId, ["text_id"] = textId
                };
            if (foundText)
                renderNodes[content.Text]["markdown_code_text_evidence"] = new JsonObject
                {
                    ["source"] = "actual MarkdownSemantic.RegisterFencedCode text object identity",
                    ["owner_id"] = ownerId, ["scroller_id"] = scrollerId
                };
            if (visible && !complete)
                errors.Add(ownerId + ": registered fenced-code content is detached, replaced or absent from the actual render tree; code semantics are incomplete");
        }
        // Resolve actual InlineUIContainer.Child object references only after
        // the visual walk has assigned IDs. No text/box matching supplies order.
        foreach (var (owner, ownerNode, visible) in inlineOwners)
        {
            var ownerId = renderIds[owner]; var entries = new JsonArray(); var complete = true; var runIndex = 0;
            foreach (var (inline, path) in CaptureInlineSequence(owner))
            {
                var pathArray = new JsonArray(); foreach (var index in path) pathArray.Add(index);
                var entry = new JsonObject { ["ordinal"] = entries.Count, ["type"] = inline.GetType().Name,
                    ["collection_path"] = pathArray, ["start_offset"] = inline.ContentStart.Offset, ["end_offset"] = inline.ContentEnd.Offset };
                if (inline is Microsoft.UI.Xaml.Documents.Run or LineBreak) entry["run_index"] = runIndex++;
                else if (inline is InlineUIContainer container)
                {
                    entry["child_source"] = "actual InlineUIContainer.Child object identity";
                    entry["child_id"] = null; entry["child_type"] = container.Child?.GetType().Name;
                    if (container.Child != null && renderIds.TryGetValue(container.Child, out var childId))
                    {
                        entry["child_id"] = childId;
                        renderNodes[container.Child]["inline_child_evidence"] = new JsonObject
                        {
                            ["source"] = "actual InlineUIContainer.Child object identity", ["owner_id"] = ownerId,
                            ["ordinal"] = entries.Count, ["collection_path"] = pathArray.DeepClone(),
                            ["start_offset"] = inline.ContentStart.Offset, ["end_offset"] = inline.ContentEnd.Offset
                        };
                    }
                    else
                    {
                        complete = false;
                        if (visible) errors.Add(ownerId + ": actual InlineUIContainer.Child is missing from the rendered tree; reading order is incomplete");
                    }
                }
                else { complete = false; if (visible) errors.Add(ownerId + ": unhandled actual Inline type " + inline.GetType().Name); }
                entries.Add(entry);
            }
            ownerNode["inline_order_evidence"] = new JsonObject
            {
                ["source"] = "actual InlineCollection order and InlineUIContainer.Child object identity",
                ["complete"] = complete, ["entries"] = entries
            };
        }
        if (popups.Length > 1) errors.Add("Multiple popup roots: their collection order requires independent HWND/compositor z-order verification.");
        var result = new JsonObject
        {
            ["schema_version"] = 1, ["scene_id"] = caseId, ["client"] = "windows",
            ["viewport"] = new JsonObject { ["width"] = width, ["height"] = height, ["scale"] = root.XamlRoot.RasterizationScale },
            ["raw_nodes"] = nodes, ["extraction_errors"] = errors,
            ["capture_evidence"] = new JsonObject { ["message_scene"] = capturedMessageEvidence?.DeepClone(),
                ["outline_focus"] = outlineFocusEvidence,
                ["textarea_resize_action"] = capturedTextareaEvidence?.DeepClone(),
                ["panel_resize_action"] = capturedPanelResizeEvidence?.DeepClone(),
                ["native_label_frame"] = capturedNativeLabelEvidence?.DeepClone(), ["pointer_input"] = capturePointerReceipts.DeepClone() },
            ["paint_order_source"] = "VisualTreeHelper children, stable Canvas.ZIndex then actual child index; popup roots above main root",
            ["popup_roots"] = popups.Length,
            ["pointer"] = new JsonObject { ["x"] = cursor.x - clientOrigin.x, ["y"] = cursor.y - clientOrigin.y }
        };
        CaptureFiniteMeasurements(result, errors);
        await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(directory, caseId + ".xaml.json"),
            NativeCaptureNumbers.Prepare(result, "Actual XAML extraction").ToJsonString());
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
        var observerPid = completed["observer_pid"]?.GetValue<int>();
        if (completed["observer_held"]?.GetValue<bool>() != true || observerPid is not > 0)
            throw new InvalidOperationException("Independent UIA observer was not held for the native provider observation");
        var probeStatus = "failed";
        try
        {
            providerProbe.CaptureAfter();
            var identityObserver = new JsonObject { ["case_id"] = caseId,
                ["app_pid"] = Environment.ProcessId, ["observer_pid"] = observerPid };
            // a3ca2a3 measured that the actual provider interfaces become
            // available while this independent observer holds its references.
            // Read the complete UIA-core IDs here, from the retained XAML owners;
            // the earlier QI failures remain in the separate before/after probe.
            await CaptureAutomationIdentities(directory, caseId, renderIds, renderNodes, identityObserver);
            result["capture_evidence"]!["automation_identity_observer"] = identityObserver.DeepClone();
            var winrtTextRangeProbe = TextRangeProviderProbe.Capture(directory, caseId, renderIds,
                frameCheckpoint: ObserveTextRangeFrameProvider);
            result["capture_evidence"]!["inprocess_text_range_probe"] = await InProcessTextRangeProviderProbe.Capture(
                directory, caseId, renderIds, renderNodes, winrtTextRangeProbe, identityObserver,
                ObserveTextRangeFrameProvider);
            CheckpointTextRangeFrameCapture("after_text_range_provider_probe");
            if (capturedTextRangeFrameEvidence != null)
            {
                result["capture_evidence"]!["text_range_frame"] = capturedTextRangeFrameEvidence.DeepClone();
                var framePath = System.IO.Path.Combine(directory, caseId + ".text-range-frame.json");
                await System.IO.File.WriteAllTextAsync(framePath + ".tmp", capturedTextRangeFrameEvidence.ToJsonString());
                System.IO.File.Move(framePath + ".tmp", framePath, overwrite: true);
            }
            // Python has published the held-observer receipt and waits for the
            // native probes before reading/projecting this file. Close this
            // write before acknowledging that those reads have completed.
            var finalXamlPath = System.IO.Path.Combine(directory, caseId + ".xaml.json");
            await System.IO.File.WriteAllTextAsync(finalXamlPath + ".tmp",
                NativeCaptureNumbers.Prepare(result, "Actual XAML extraction after retained observer").ToJsonString());
            System.IO.File.Move(finalXamlPath + ".tmp", finalXamlPath, overwrite: true);
            probeStatus = "observed";
        }
        finally
        {
            // The independent observer retains its actual element/provider
            // references until Python receives this bound observation receipt.
            // "observed" means these reads completed, not that QI/parity passed.
            var probeReceipt = System.IO.Path.Combine(receipts, caseId + ".probes.json");
            await System.IO.File.WriteAllTextAsync(probeReceipt + ".tmp", JsonSerializer.Serialize(new
            { case_id = caseId, app_pid = Environment.ProcessId, observer_pid = observerPid, status = probeStatus }));
            System.IO.File.Move(probeReceipt + ".tmp", probeReceipt);
        }
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
    private static JsonObject CaptureFontWeightConfiguration(DependencyObject source, string ownerId, string sourceId, double? rawStyleWeight)
    {
        // These effective XAML requests include property inheritance. They are
        // inputs to font selection, not measurements of the selected/fallback face.
        var (property, value, text) = source switch
        {
            TextBlock block => ("TextBlock.FontWeight.Weight", (double)block.FontWeight.Weight, block.Text),
            RichTextBlock block => ("RichTextBlock.FontWeight.Weight", (double)block.FontWeight.Weight, CaptureText(block)),
            Run run => ("Run.FontWeight.Weight", (double)run.FontWeight.Weight, run.Text),
            _ => throw new ArgumentException("Configured weight requires an actual XAML text owner", nameof(source))
        };
        return new JsonObject
        {
            ["version"] = 1, ["source"] = "actual XAML text-owner FontWeight.Weight getter",
            ["property"] = property, ["value"] = value, ["runtime_type"] = source.GetType().FullName,
            ["source_id"] = sourceId, ["owner_id"] = ownerId, ["text"] = text,
            ["raw_style_font_weight"] = rawStyleWeight,
            ["quantity"] = "effective configured request; not resolved render-face weight"
        };
    }
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
            case Grid g: background = g.Background; border = g.BorderBrush; thickness = g.BorderThickness; radius = g.CornerRadius; break;
            case StackPanel s: background = s.Background; border = s.BorderBrush; thickness = s.BorderThickness; radius = s.CornerRadius; break;
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
        var result = new JsonObject
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
        if (element is NativeLabel label)
        {
            var production = label.CaptureProductionReceipt();
            var current = CurrentNativeLabelSubmission(production);
            var draw = production["draw"];
            result["native_label_style_evidence"] = new JsonObject
            {
                ["source"] = "Current bound NativeLabel production draw, actual TextFormat getters and D2D brush inputs",
                ["current_submission_verified"] = current,
                ["layout_revision"] = draw?["layout_revision"]?.DeepClone(),
                ["surface_revision"] = draw?["surface_revision"]?.DeepClone(),
                ["draw_ordinal"] = draw?["draw_ordinal"]?.DeepClone(),
                ["actual_text_format"] = draw?["actual_text_format"]?.DeepClone(),
                ["brush_input_srgb_unpremultiplied_0_255"] = draw?["brush_input_srgb_unpremultiplied_0_255"]?.DeepClone()
            };
            if (current)
            {
                result["font_size"] = draw?["actual_text_format"]?["font_size"]?.DeepClone();
                result["font_weight"] = draw?["actual_text_format"]?["font_weight"]?.DeepClone();
                result["foreground"] = draw?["brush_input_srgb_unpremultiplied_0_255"]?.DeepClone();
            }
            else if (visible) errors.Add(id + ": NativeLabel actual text style has no current successful bound production draw");
        }
        return result;
    }
    private static void CaptureStrokeEvidence(Shape shape, UIElement captureRoot, JsonObject node, string id, JsonArray errors)
    {
        if (shape.GetType() == typeof(Ellipse))
            node["shape_geometry_evidence"] = new JsonObject
            {
                ["source"] = "actual Ellipse layout and Shape inputs", ["owner_id"] = id,
                ["runtime_type"] = shape.GetType().FullName,
                ["stretch"] = shape.Stretch.ToString(), ["stretch_value"] = (int)shape.Stretch,
                ["actual_width"] = shape.ActualWidth, ["actual_height"] = shape.ActualHeight,
                ["stroke_is_null"] = shape.Stroke == null, ["stroke_thickness"] = shape.StrokeThickness,
                ["scope"] = "Actual native geometry inputs only; no reference contour or screenshot-frame equivalence is supplied"
            };
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
    private static IEnumerable<(Inline Inline, int[] Path)> CaptureInlineSequence(FrameworkElement owner)
    {
        static IEnumerable<(Inline Inline, int[] Path)> Walk(InlineCollection collection, int[] prefix)
        {
            for (var index = 0; index < collection.Count; index++)
            {
                var inline = collection[index]; var path = prefix.Append(index).ToArray();
                if (inline is Span span) { foreach (var child in Walk(span.Inlines, path)) yield return child; }
                else yield return (inline, path);
            }
        }
        if (owner is TextBlock plain) { foreach (var entry in Walk(plain.Inlines, new[] { 0 })) yield return entry; }
        else if (owner is RichTextBlock rich)
            for (var block = 0; block < rich.Blocks.Count; block++)
                if (rich.Blocks[block] is Paragraph paragraph)
                    foreach (var entry in Walk(paragraph.Inlines, new[] { block })) yield return entry;
    }
    private static JsonObject CaptureTextLayout(FrameworkElement element, string id, JsonArray errors, UIElement captureRoot, bool visible)
    {
        if (element is WorkspaceCodeView code) return CaptureLineBreakStrategies(CaptureCodeDocument(code, id, errors, captureRoot, visible), code, id);
        if (element is ComposerInput input) return CaptureLineBreakStrategies(CaptureComposerDocument(input, id, errors, captureRoot, visible), input, id);
        if (element is NativeLabel label)
        {
            var production = label.CaptureProductionReceipt(); var current = CurrentNativeLabelSubmission(production);
            var draw = production["draw"];
            var rows = draw?["line_metrics"] as JsonArray;
            var trimming = draw?["trimming"];
            var wordWrapping = current ? draw?["actual_text_format"]?["word_wrapping"]?.GetValue<uint>() : null;
            return new JsonObject
            {
                ["wrap"] = wordWrapping switch { 1 => "none", 3 => "word", _ => null },
                ["break_strategy_version"] = 1,
                ["normal_break_strategy"] = wordWrapping switch { 1 => "none", 3 => "word", _ => null },
                ["emergency_break_strategy"] = wordWrapping is 1 or 3 ? "none" : null,
                ["line_break_configuration"] = new JsonObject
                {
                    ["source"] = "IDWriteTextLayout.GetWordWrapping on the current production NativeLabel layout", ["owner"] = id,
                    ["raw"] = new JsonObject { ["word_wrapping"] = draw?["actual_text_format"]?["word_wrapping"]?.DeepClone(),
                        ["current_production_submission"] = current, ["layout_revision"] = draw?["layout_revision"]?.DeepClone() }
                },
                ["truncation"] = !current ? null : trimming?["granularity"]?.GetValue<uint>() == 0 ? "none"
                    : trimming?["granularity"]?.GetValue<uint>() == 1 && trimming?["same_sign_com_identity"]?.GetValue<bool>() == true ? "ellipsis" : null,
                ["line_count"] = current ? draw?["layout_metrics"]?["line_count"]?.DeepClone() : null,
                ["character_boxes"] = new JsonArray(), ["local_character_boxes"] = new JsonArray(),
                ["character_boxes_coordinate_space"] = "content-window", ["rich_text_runs"] = new JsonArray(),
                ["text_geometry_status"] = visible ? "unmeasured-equivalent-text-line-quantity" : "not-visible",
                ["actual_trimming"] = new JsonObject
                {
                    ["source"] = "Actual NativeLabel production Draw line metrics and GetTrimming; no inferred ellipsis rectangle",
                    ["is_text_trimmed"] = current && rows is { Count: > 0 } ? rows.Any(row => row?["is_trimmed"]?.GetValue<bool>() == true) : null,
                    ["layout_revision"] = draw?["layout_revision"]?.DeepClone(), ["draw_ordinal"] = draw?["draw_ordinal"]?.DeepClone(),
                    ["ellipsis_bounds"] = null, ["production_trimming"] = trimming?.DeepClone()
                },
                ["placeholder"] = null
            };
        }
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
                if (range.leaf != null)
                {
                    var actualWeight = range.leaf.FontWeight.Weight;
                    JsonObject? weightConfiguration = null;
                    if (range.leaf is Run actualRun)
                    {
                        weightConfiguration = CaptureFontWeightConfiguration(actualRun, id, id + ":run:" + runs.Count, actualWeight);
                        weightConfiguration["run_index"] = runs.Count;
                        weightConfiguration["start_offset"] = range.start.Offset;
                        weightConfiguration["end_offset"] = range.end.Offset;
                    }
                    runs.Add(new JsonObject
                    {
                        ["type"] = range.leaf.GetType().Name,
                        ["own_paint_evidence"] = new JsonObject { ["source"] = "actual TextElement runtime type and owner ContentStart/ContentEnd range",
                            ["runtime_type"] = range.leaf.GetType().FullName, ["owner_id"] = id,
                            ["start_offset"] = range.start.Offset, ["end_offset"] = range.end.Offset,
                            ["exact_run_type"] = range.leaf.GetType() == typeof(Run) },
                        ["text"] = range.leaf is Run run ? run.Text : "\n",
                        ["start_offset"] = range.start.Offset, ["end_offset"] = range.end.Offset,
                        ["font_size"] = range.leaf.FontSize, ["font_weight"] = actualWeight,
                        ["font_weight_configuration"] = weightConfiguration,
                        ["foreground"] = CaptureColor(range.leaf.Foreground), ["font_family"] = range.leaf.FontFamily.Source,
                        ["bounds"] = runBoxes, ["caret_evidence"] = runCarets,
                        ["bounds_measurement"] = "Per-line text advance envelope of actual forward/backward TextPointer caret rectangles including both Run boundaries",
                        ["coordinate_space"] = "content-window", ["geometry_complete"] = !runIncomplete
                    });
                }
            }
            lines = incomplete ? null : ys.Count;
        }
        return CaptureLineBreakStrategies(new JsonObject
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
        }, element, id);
    }
    private static JsonObject CaptureLineBreakStrategies(JsonObject layout, FrameworkElement element, string id)
    {
        TextWrapping? actual = element switch
        {
            TextBlock text => text.TextWrapping, RichTextBlock text => text.TextWrapping,
            TextBox text => text.TextWrapping, RichEditBox text => text.TextWrapping, _ => null
        };
        // WinUI Wrap uses normal opportunities and breaks an otherwise-unbreakable
        // word only when necessary. WrapWholeWords allows that word to overflow.
        // Neither actual enum is a request for unconditional character wrapping.
        layout["break_strategy_version"] = 1;
        layout["normal_break_strategy"] = actual switch
        {
            TextWrapping.NoWrap => "none", TextWrapping.Wrap or TextWrapping.WrapWholeWords => "word", _ => null
        };
        layout["emergency_break_strategy"] = actual switch
        {
            TextWrapping.NoWrap or TextWrapping.WrapWholeWords => "none", TextWrapping.Wrap => "break-unbreakable", _ => null
        };
        layout["line_break_configuration"] = new JsonObject
        {
            ["source"] = "Live WinUI TextWrapping property; Windows App SDK 1.6 enum semantics", ["owner"] = id,
            ["raw"] = new JsonObject { ["text_wrapping"] = actual?.ToString(), ["text_wrapping_value"] = actual.HasValue ? (int)actual.Value : null,
                ["control_type"] = element.GetType().FullName, ["language"] = element.Language }
        };
        return layout;
    }
    [System.Runtime.InteropServices.DllImport("user32.dll")] private static extern bool GetCursorPos(ref CapturePoint point);
}
