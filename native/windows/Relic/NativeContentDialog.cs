using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using System.Text.Json.Nodes;

namespace Relic;

// Keep the native ContentDialog behavior and its protected template contract.
// A dialog's host fills the window; its BackgroundElement is the actual modal
// surface. Capture those distinct objects rather than searching by geometry.
internal sealed class NativeContentDialog : ContentDialog
{
    internal static readonly string[] SurfacePartNames =
        ["BackgroundElement", "Content", "ContentScrollViewer", "LayoutRoot", "SmokeLayerBackground"];
    internal readonly Dictionary<string, DependencyObject?> AppliedParts = [];
    internal ControlTemplate? AppliedTemplate { get; private set; }
    internal long TemplateRevision { get; private set; }

    protected override void OnApplyTemplate()
    {
        base.OnApplyTemplate();
        TemplateRevision++;
        AppliedTemplate = Template;
        AppliedParts.Clear();
        foreach (var name in SurfacePartNames) AppliedParts[name] = GetTemplateChild(name);
    }

    internal DependencyObject? CurrentPart(string name) => GetTemplateChild(name);

    internal void ApplySurfaceBrushes()
    {
        // ContentDialog reparents its smoke rectangle into a separate popup.
        // That popup resolves the SDK theme brush instead of the dialog-local
        // resource. Apply our actual production brush to the retained part
        // after opening; this keeps the native modal/focus behavior intact.
        if (GetTemplateChild("SmokeLayerBackground") is Microsoft.UI.Xaml.Shapes.Rectangle smoke
            && Resources.TryGetValue("ContentDialogSmokeFill", out var value) && value is Brush brush)
            smoke.Fill = brush;
    }
}

public sealed partial class MainWindow
{
    private void CaptureNativeDialogSurfaces(Dictionary<DependencyObject, string> ids,
        Dictionary<DependencyObject, JsonObject> nodes)
    {
        foreach (var dialog in ids.Keys.OfType<NativeContentDialog>())
        {
            var parts = new JsonObject();
            var evidence = new JsonObject
            {
                ["source"] = "Actual NativeContentDialog protected GetTemplateChild objects from its applied native ControlTemplate",
                ["owner_id"] = ids[dialog], ["owner_type"] = dialog.GetType().FullName,
                ["template_revision"] = dialog.TemplateRevision,
                ["template_is_nonnull"] = dialog.Template != null,
                ["same_applied_template_reference"] = ReferenceEquals(dialog.AppliedTemplate, dialog.Template),
                ["ui_thread_access"] = dialog.DispatcherQueue.HasThreadAccess,
                ["parts"] = parts,
                ["canonical_geometry_supplied"] = false,
                ["scope"] = "Actual template-object ownership only; host, modal surface, authored content and smoke layer remain distinct raw objects"
            };
            nodes[dialog]["dialog_surface_evidence"] = evidence;
            var authored = dialog.Content as DependencyObject;
            evidence["authored_content_id"] = authored != null && ids.TryGetValue(authored, out var contentId) ? contentId : null;
            evidence["authored_content_type"] = dialog.Content?.GetType().FullName;
            foreach (var name in NativeContentDialog.SurfacePartNames)
            {
                var record = new JsonObject { ["part_name"] = name };
                parts[name] = record;
                try
                {
                    var part = dialog.CurrentPart(name);
                    var applied = dialog.AppliedParts.TryGetValue(name, out var old);
                    record["is_null"] = part == null;
                    record["same_applied_part_reference"] = applied && ReferenceEquals(part, old);
                    record["runtime_type"] = part?.GetType().FullName;
                    record["id"] = part != null && ids.TryGetValue(part, out var id) ? id : null;
                    var path = new JsonArray(); var seen = new HashSet<DependencyObject>(ReferenceEqualityComparer.Instance);
                    var reachesOwner = false;
                    for (var current = part; current != null; current = VisualTreeHelper.GetParent(current))
                    {
                        if (!seen.Add(current)) { record["ancestry_cycle"] = true; break; }
                        path.Add(new JsonObject { ["id"] = ids.TryGetValue(current, out var parentId) ? parentId : null,
                            ["runtime_type"] = current.GetType().FullName });
                        if (ReferenceEquals(current, dialog)) { reachesOwner = true; break; }
                    }
                    record["actual_parent_path_to_owner"] = path;
                    record["path_reaches_owner"] = reachesOwner;
                    // Popup-hosted smoke parts can be outside this visual tree.
                    // An absent or non-owner path is retained, never invented.
                }
                catch (Exception ex) { record["error"] = ex.ToString(); }
            }
            evidence["template_revision_after"] = dialog.TemplateRevision;
            evidence["same_applied_template_reference_after"] = ReferenceEquals(dialog.AppliedTemplate, dialog.Template);
        }
    }
}
