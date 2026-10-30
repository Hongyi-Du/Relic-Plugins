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
            var receipt = new JsonObject { ["source"] = source, ["owner_id"] = ids[value],
                ["runtime_type"] = value.GetType().FullName,
                ["own_paint_contract"] = PrimitiveOutlineContract(value.GetType()),
                ["scope"] = "Exact native primitive own fill/border/stroke/glyph/image paint; separately owned children are not folded into this receipt" };
            node["outline_owner_evidence"] = receipt;
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
        : actual == typeof(Grid) || actual == typeof(StackPanel) || actual == typeof(Canvas) ? "native-panel-background"
        : actual == typeof(Rectangle) || actual == typeof(Ellipse) || actual == typeof(Line)
            || actual == typeof(Microsoft.UI.Xaml.Shapes.Path) || actual == typeof(Polygon) || actual == typeof(Polyline) ? "native-shape-fill-and-stroke"
        : actual == typeof(TextBlock) || actual == typeof(RichTextBlock) ? "native-text-glyphs"
        : actual == typeof(Image) ? "native-image-content"
        // Exact SDK 1.6.9, commit da699b040bddc2a6adf660512a7c6db8a96bfbe3:
        // src/dxaml/xcp/core/inc/Viewbox.h and core/elements/Viewbox.cpp:
        // CFrameworkElement scale/arrange only; the internal Border is a child.
        // core/hw/hwwalk.cpp:1498-1593 draws neither Viewbox nor ordinary
        // UserControl content. CControl.h:355-361 permits a background only for
        // Page. ReferenceVectorIcon is our exact sealed UserControl whose only
        // stroke is the independently captured VectorPath under its live Canvas.
        // Focus, hand-in Composition and direct-child proofs still apply above.
        : actual == typeof(Viewbox) ? "native-viewbox-child-transform"
        : actual == typeof(ReferenceVectorIcon) ? "relic-reference-vector-usercontrol-child-only" : null;
}
