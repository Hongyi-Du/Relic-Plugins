using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Hosting;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    // Scope: each actual primitive's own renderer, not its descendants or the
    // whole compositor. No CSS-like property absence is used as evidence.
    private JsonObject CaptureOutlineOwners(Dictionary<DependencyObject, string> ids,
        Dictionary<DependencyObject, JsonObject> nodes)
    {
        const string source = "winui-own-outline-v1";
        var global = new JsonObject { ["source"] = source,
            ["focus_api"] = "FocusManager.GetFocusedElement(actual root.XamlRoot)" };
        object? focused = null;
        try
        {
            focused = FocusManager.GetFocusedElement(root.XamlRoot);
            global["status"] = "measured";
            global["focused_object_is_null"] = focused == null;
            global["focused_object_type"] = focused?.GetType().FullName;
            global["focused_object_id"] = focused is DependencyObject dependency && ids.TryGetValue(dependency, out var id) ? id : null;
            global["focused_object_focus_state"] = focused is UIElement ui ? ui.FocusState.ToString() : null;
            global["focused_object_use_system_focus_visuals"] = focused is UIElement focusUi ? focusUi.UseSystemFocusVisuals : null;
        }
        catch (Exception ex) { global["status"] = "error"; global["error"] = ex.ToString(); }

        (JsonArray Ids, bool Complete) Parents(DependencyObject value)
        {
            var result = new JsonArray(); var seen = new HashSet<DependencyObject>();
            for (DependencyObject? current = value; current != null; current = VisualTreeHelper.GetParent(current))
            {
                if (!seen.Add(current) || !ids.TryGetValue(current, out var id)) return (result, false);
                result.Add(id);
                // The actual capture root is a deliberate tree boundary. Its
                // platform host may have uncaptured ancestors; those cannot
                // change ancestry relationships between two objects inside it.
                if (ReferenceEquals(current, root)) return (result, true);
            }
            return (result, true);
        }
        foreach (var (value, node) in nodes)
        {
            if (value is not FrameworkElement element) continue;
            var actual = value.GetType();
            var receipt = new JsonObject { ["source"] = source, ["owner_id"] = ids[value],
                ["runtime_type"] = actual.FullName,
                ["own_paint_contract"] = PrimitiveOutlineContract(actual),
                ["scope"] = "Exact native primitive own fill/border/stroke/glyph/image paint; separately owned children are not folded into this receipt" };
            node["outline_owner_evidence"] = receipt;
            if (LocalLayoutOutlineContract(actual) is { } local)
            {
                receipt["local_layout"] = new JsonObject
                {
                    ["source"] = "actual local layout Type.BaseType/IsSealed and exact audited source contract",
                    ["owner_id"] = ids[value], ["base_type"] = actual.BaseType?.FullName,
                    ["is_sealed"] = actual.IsSealed, ["audited_source"] = local.Source
                };
            }
            try
            {
                var focus = new JsonObject { ["status"] = "measured", ["state"] = element.FocusState.ToString(),
                    ["use_system_focus_visuals"] = element.UseSystemFocusVisuals,
                    ["is_template_focus_target"] = Control.GetIsTemplateFocusTarget(element),
                    ["global"] = global.DeepClone() };
                receipt["focus"] = focus;
                var ownerParents = Parents(element);
                focus["owner_ancestry"] = ownerParents.Ids;
                focus["owner_ancestry_complete"] = ownerParents.Complete;
                if (global["status"]?.GetValue<string>() == "measured" && focused == null)
                    focus["relationship"] = "no-focused-object";
                else if (focused is DependencyObject dependency && ids.TryGetValue(dependency, out var focusedId))
                {
                    var focusedParents = Parents(dependency);
                    focus["focused_ancestry"] = focusedParents.Ids;
                    focus["focused_ancestry_complete"] = focusedParents.Complete;
                    focus["relationship"] = !ownerParents.Complete || !focusedParents.Complete ? null
                        : ReferenceEquals(element, dependency) ? "same-object"
                        : ownerParents.Ids.Any(id => id?.GetValue<string>() == focusedId) ? "focused-object-is-ancestor"
                        : focusedParents.Ids.Any(id => id?.GetValue<string>() == ids[value]) ? "owner-is-ancestor-of-focused-object"
                        : "unrelated-in-captured-visual-tree";
                }
                else focus["relationship"] = null;
                // This API observes app hand-in only. It does not claim to
                // enumerate framework visuals or prove an active focus ring.
                // https://learn.microsoft.com/en-us/windows/windows-app-sdk/api/winrt/microsoft.ui.xaml.hosting.elementcompositionpreview.getelementchildvisual
                var handIn = ElementCompositionPreview.GetElementChildVisual(element);
                receipt["composition"] = new JsonObject { ["status"] = "measured",
                    ["api"] = "ElementCompositionPreview.GetElementChildVisual(actual owner)",
                    ["child_visual_present"] = handIn != null, ["child_visual_type"] = handIn?.GetType().FullName,
                    ["shadow_present"] = element.Shadow != null, ["shadow_type"] = element.Shadow?.GetType().FullName };
                var children = new JsonArray(); var complete = true;
                var count = VisualTreeHelper.GetChildrenCount(element);
                for (var index = 0; index < count; index++)
                {
                    var child = VisualTreeHelper.GetChild(element, index);
                    var known = ids.TryGetValue(child, out var childId);
                    var sameParent = ReferenceEquals(VisualTreeHelper.GetParent(child), element);
                    complete &= known && sameParent && nodes.TryGetValue(child, out var childNode)
                        && childNode["parent"]?.GetValue<string>() == ids[value];
                    children.Add(new JsonObject { ["id"] = childId, ["index"] = index, ["same_parent_object"] = sameParent });
                }
                receipt["children"] = new JsonObject { ["status"] = "measured", ["complete"] = complete, ["items"] = children };
                if (actual == typeof(ScrollContentPresenter))
                {
                    // Exact sealed SDK type: its native base is CContentPresenter,
                    // whose own background/border uses BorderRenderHelper. The
                    // scrolling geometry/Clip and every child remain independent.
                    // https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/core/controls/generated/CScrollContentPresenter.g.h#L17
                    // https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/core/hw/BaseContentRenderer.cpp#L1132
                    receipt["scroll_presenter"] = new JsonObject
                    {
                        ["source"] = "actual exact ScrollContentPresenter runtime BaseType/IsSealed and current visual-child count",
                        ["status"] = "measured", ["owner_id"] = ids[value],
                        ["base_type"] = actual.BaseType?.FullName, ["is_sealed"] = actual.IsSealed,
                        ["visual_child_count"] = count,
                        ["audited_sdk_source"] = "https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/core/controls/generated/CScrollContentPresenter.g.h"
                    };
                }
                if (actual == typeof(OverviewChipView) || actual == typeof(OverviewBadgeView))
                {
                    var token = (OverviewTokenView)value;
                    var presenter = count == 1 ? VisualTreeHelper.GetChild(token, 0) as ContentPresenter : null;
                    var content = token.Content as DependencyObject;
                    // Exact local sealed leaves, not arbitrary ContentControl.
                    // SDK 1.6.9 ContentControl's own pre/post draw handles only
                    // ListViewBaseItem chrome; these classes have no such base.
                    // Their real ContentPresenter supplies fill/border/content.
                    // https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/core/hw/BaseContentRenderer.cpp#L1338
                    // https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/core/inc/ContentControl.h#L72
                    receipt["overview_token_content"] = new JsonObject
                    {
                        ["source"] = "actual sealed OverviewTokenView leaf runtime, template and ContentPresenter/Content object identities",
                        ["status"] = "measured", ["owner_id"] = ids[value],
                        ["base_type"] = actual.BaseType?.FullName, ["base_base_type"] = actual.BaseType?.BaseType?.FullName,
                        ["is_sealed"] = actual.IsSealed,
                        ["audited_source"] = "native/windows/Relic/OverviewStyles.cs#OverviewTokenView",
                        ["template_present"] = token.Template != null, ["template_type"] = token.Template?.GetType().FullName,
                        ["visual_child_count"] = count,
                        ["presenter_id"] = presenter != null && ids.TryGetValue(presenter, out var presenterId) ? presenterId : null,
                        ["presenter_runtime_type"] = presenter?.GetType().FullName,
                        ["presenter_is_current_only_child"] = presenter != null && presenter.GetType() == typeof(ContentPresenter)
                            && count == 1 && ReferenceEquals(VisualTreeHelper.GetChild(token, 0), presenter)
                            && ReferenceEquals(VisualTreeHelper.GetParent(presenter), token),
                        ["content_id"] = content != null && ids.TryGetValue(content, out var tokenContentId) ? tokenContentId : null,
                        ["content_type"] = content?.GetType().Name,
                        ["presenter_content_same_object"] = presenter != null && content != null && ReferenceEquals(presenter.Content, content),
                        ["content_is_current_presenter_child"] = presenter != null && content != null
                            && VisualTreeHelper.GetChildrenCount(presenter) == 1
                            && ReferenceEquals(VisualTreeHelper.GetChild(presenter, 0), content)
                            && ReferenceEquals(VisualTreeHelper.GetParent(content), presenter)
                    };
                }
                if (actual == typeof(NativeStateDotView))
                {
                    var dot = (NativeStateDotView)value;
                    // The exact production Grid has ordinary native panel
                    // paint and two separately captured Ellipse paint layers.
                    // No inset-shadow equivalence follows from this contract.
                    receipt["state_dot_grid"] = new JsonObject
                    {
                        ["source"] = "actual sealed NativeStateDotView runtime and Surround/VacancyRing object identities",
                        ["status"] = "measured", ["owner_id"] = ids[value],
                        ["base_type"] = actual.BaseType?.FullName, ["is_sealed"] = actual.IsSealed,
                        ["audited_source"] = "native/windows/Relic/NativeStateDotView.cs#NativeStateDotView",
                        ["visual_child_count"] = count, ["panel_child_count"] = dot.Children.Count,
                        ["surround_id"] = ids.TryGetValue(dot.Surround, out var surroundId) ? surroundId : null,
                        ["vacancy_ring_id"] = ids.TryGetValue(dot.VacancyRing, out var vacancyId) ? vacancyId : null,
                        ["production_layers_are_current_children"] = dot.HasCurrentPaintChildren && count == 2
                            && dot.Surround.GetType() == typeof(Ellipse) && dot.VacancyRing.GetType() == typeof(Ellipse)
                            && ReferenceEquals(VisualTreeHelper.GetChild(dot, 0), dot.Surround)
                            && ReferenceEquals(VisualTreeHelper.GetChild(dot, 1), dot.VacancyRing)
                            && ReferenceEquals(VisualTreeHelper.GetParent(dot.Surround), dot)
                            && ReferenceEquals(VisualTreeHelper.GetParent(dot.VacancyRing), dot)
                    };
                }
                if (actual == typeof(PersonPicture))
                {
                    var picture = (PersonPicture)value;
                    var template = picture.Template;
                    // Fixed SDK: PersonPicture is an UNSEALED Control. Its
                    // exact implementation updates template children/brushes
                    // and VisualState; it has no separate content renderer.
                    // https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/controls/dev/PersonPicture/PersonPicture.idl
                    // https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/controls/dev/PersonPicture/PersonPicture.cpp
                    // HWWalk's Control container has no own drawing case;
                    // focus and independently rendered children are separate:
                    // https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/core/hw/hwwalk.cpp#L1498
                    receipt["person_picture_template"] = new JsonObject
                    {
                        ["source"] = "actual exact PersonPicture runtime, Control.Template and current visual children",
                        ["status"] = "measured", ["owner_id"] = ids[value],
                        ["base_type"] = actual.BaseType?.FullName, ["is_sealed"] = actual.IsSealed,
                        ["template_present"] = template != null, ["template_type"] = template?.GetType().FullName,
                        ["visual_child_count"] = count,
                        ["audited_sdk_source"] = "https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/controls/dev/PersonPicture/PersonPicture.cpp"
                    };
                }
                if (actual == typeof(NativeLabel))
                {
                    var label = (NativeLabel)value;
                    var image = count == 1 ? VisualTreeHelper.GetChild(label, 0) as Image : null;
                    var binding = image == null ? null : label.CaptureProductionImageBinding(image);
                    if (binding != null) binding["owner_id"] = ids[value];
                    // NativeLabel is not layout-only: it draws into its real
                    // child's SurfaceImageSource. This contract covers only
                    // the parent's native Panel paint, never the child's glyph
                    // paint, actual presentation, focus, or attached visuals.
                    receipt["native_label_content"] = new JsonObject
                    {
                        ["source"] = "actual sealed NativeLabel runtime and sole production Image object identity",
                        ["status"] = "measured", ["owner_id"] = ids[value],
                        ["base_type"] = actual.BaseType?.FullName, ["is_sealed"] = actual.IsSealed,
                        ["audited_source"] = "native/windows/Relic/NativeLabel.cs#NativeLabel",
                        ["visual_child_count"] = count, ["panel_child_count"] = label.Children.Count,
                        ["image_id"] = image != null && ids.TryGetValue(image, out var imageId) ? imageId : null,
                        ["production_image_is_current_only_child"] = image != null && image.GetType() == typeof(Image)
                            && label.Children.Count == 1 && ReferenceEquals(label.Children[0], image)
                            && label.OwnsProductionImage(image) && ReferenceEquals(VisualTreeHelper.GetParent(image), label),
                        ["production_image_binding"] = binding
                    };
                }
                if (value.GetType() == typeof(ReferenceVectorIcon))
                {
                    var icon = (ReferenceVectorIcon)value;
                    var content = icon.Content as Viewbox;
                    var canvasPath = new JsonArray(); var canvasPathComplete = false;
                    var visited = new HashSet<DependencyObject>();
                    for (DependencyObject? current = icon.VectorCanvas; current != null; current = VisualTreeHelper.GetParent(current))
                    {
                        if (!visited.Add(current) || !ids.TryGetValue(current, out var currentId)) break;
                        canvasPath.Add(currentId);
                        if (ReferenceEquals(current, icon)) { canvasPathComplete = true; break; }
                    }
                    // These are the live production fields/properties, not a
                    // reconstructed path or an inference from names/geometry.
                    receipt["vector_content"] = new JsonObject
                    {
                        ["source"] = "actual ReferenceVectorIcon Content/VectorCanvas/VectorPath object identities",
                        ["status"] = "measured", ["owner_id"] = ids[value],
                        ["template_is_null"] = icon.Template == null,
                        ["content_id"] = content != null && ids.TryGetValue(content, out var contentId) ? contentId : null,
                        ["canvas_id"] = ids.TryGetValue(icon.VectorCanvas, out var canvasId) ? canvasId : null,
                        ["path_id"] = ids.TryGetValue(icon.VectorPath, out var pathId) ? pathId : null,
                        ["content_is_current_visual_child"] = content != null && content.GetType() == typeof(Viewbox)
                            && count == 1 && ReferenceEquals(VisualTreeHelper.GetChild(icon, 0), content),
                        ["viewbox_child_is_vector_canvas"] = content != null && ReferenceEquals(content.Child, icon.VectorCanvas),
                        ["canvas_children_are_vector_path"] = icon.VectorCanvas.Children.Count == 1
                            && ReferenceEquals(icon.VectorCanvas.Children[0], icon.VectorPath)
                            && VisualTreeHelper.GetChildrenCount(icon.VectorCanvas) == 1
                            && ReferenceEquals(VisualTreeHelper.GetChild(icon.VectorCanvas, 0), icon.VectorPath),
                        ["canvas_visual_path"] = canvasPath, ["canvas_visual_path_complete"] = canvasPathComplete
                    };
                }
                receipt["status"] = "measured";
            }
            catch (Exception ex) { receipt["status"] = "error"; receipt["error"] = ex.ToString(); }
        }
        return global;
    }

    private static string? PrimitiveOutlineContract(Type actual) =>
        actual == typeof(Border) ? "native-border-fill-and-border"
        : actual == typeof(ContentPresenter) ? "native-presenter-fill-border-and-content"
        : actual == typeof(ScrollContentPresenter) ? "native-scroll-content-presenter-fill-border-and-content"
        : actual == typeof(Grid) || actual == typeof(StackPanel) || actual == typeof(Canvas) ? "native-panel-background"
        : actual == typeof(Rectangle) || actual == typeof(Ellipse) || actual == typeof(Line)
            || actual == typeof(Microsoft.UI.Xaml.Shapes.Path) || actual == typeof(Polygon) || actual == typeof(Polyline) ? "native-shape-fill-and-stroke"
        : actual == typeof(TextBlock) || actual == typeof(RichTextBlock) ? "native-text-glyphs"
        : actual == typeof(Image) ? "native-image-content"
        // The pinned SDK's pre/post-children switches have no own renderer
        // for these exact core control types. Their applied template children
        // still receive independent receipts below; focus and app Composition
        // are NOT covered by this contract. Do not generalize to ContentControl
        // (which has its own renderer), presenters, or arbitrary subclasses.
        : TemplateChildOnlyControl(actual) ? "native-core-control-template-children-only"
        // Exact SDK 1.6.9, commit da699b040bddc2a6adf660512a7c6db8a96bfbe3:
        // src/dxaml/xcp/core/inc/Viewbox.h and core/elements/Viewbox.cpp:
        // CFrameworkElement scale/arrange only; the internal Border is a child.
        // core/hw/hwwalk.cpp:1498-1593 draws neither Viewbox nor ordinary
        // UserControl content. CControl.h:355-361 permits a background only for
        // Page. ReferenceVectorIcon is our exact sealed UserControl whose only
        // stroke is the independently captured VectorPath under its live Canvas.
        // Focus, hand-in Composition and direct-child proofs still apply above.
        : actual == typeof(Viewbox) ? "native-viewbox-child-transform"
        : actual == typeof(ReferenceVectorIcon) ? "relic-reference-vector-usercontrol-child-only"
        // This unsealed SDK class is accepted only by exact runtime equality,
        // with its actual present template and complete nonempty child set.
        : actual == typeof(PersonPicture) ? "native-personpicture-control-template-children-only"
        : actual == typeof(OverviewChipView) || actual == typeof(OverviewBadgeView) ? "relic-overview-token-template-content"
        : actual == typeof(NativeStateDotView) ? "relic-state-dot-grid-owned-ellipses"
        // Exact sealed app renderer: native Panel paint plus an independently
        // owned Image surface. The live runtime/child/binding proof is required
        // above; no arbitrary Panel subclass or unmeasured image inherits it.
        : actual == typeof(NativeLabel) ? "relic-native-label-panel-bound-image"
        : LocalLayoutOutlineContract(actual)?.Contract;

    private static bool TemplateChildOnlyControl(Type actual) =>
        actual == typeof(Button) || actual == typeof(Microsoft.UI.Xaml.Controls.Primitives.RepeatButton)
        || actual == typeof(Microsoft.UI.Xaml.Controls.Primitives.ToggleButton)
        || actual == typeof(Microsoft.UI.Xaml.Controls.Primitives.ScrollBar)
        || actual == typeof(Microsoft.UI.Xaml.Controls.Primitives.Thumb)
        || actual == typeof(ScrollViewer) || actual == typeof(ListViewItem)
        || actual == typeof(ListView) || actual == typeof(ComboBox) || actual == typeof(TextBox);

    // These six exact sealed production types add layout or a region peer only.
    // Their own background/border follows the fixed SDK's CPanel path:
    // https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/core/hw/hwwalk.cpp#L1508
    // This is not a contract for arbitrary Panel subclasses. Actual focus,
    // hand-in Composition, Shadow and visual-child identities remain required.
    private static (string Contract, string Source)? LocalLayoutOutlineContract(Type actual) =>
        actual == typeof(CenteredFractionLayout) ? ("relic-centered-fraction-panel-layout-only", "native/windows/Relic/Conversation.cs#CenteredFractionLayout")
        : actual == typeof(MessageBubbleLayout) ? ("relic-message-bubble-panel-layout-only", "native/windows/Relic/Conversation.cs#MessageBubbleLayout")
        : actual == typeof(MessageHeaderRow) ? ("relic-message-header-panel-layout-only", "native/windows/Relic/MessageHeaderRow.cs#MessageHeaderRow")
        : actual == typeof(ActionRow) ? ("relic-action-row-panel-layout-only", "native/windows/Relic/Design.cs#ActionRow")
        : actual == typeof(DetailsFilterRow) ? ("relic-details-filter-panel-layout-only", "native/windows/Relic/DetailsStyles.cs#DetailsFilterRow")
        : actual == typeof(NativeRegionGrid) ? ("relic-region-grid-peer-only", "native/windows/Relic/NativeRegion.cs#NativeRegionGrid") : null;
}
