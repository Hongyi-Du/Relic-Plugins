using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private static void CaptureNativeTextareaPlaceholders(Dictionary<DependencyObject, string> ids,
        Dictionary<DependencyObject, JsonObject> records)
    {
        foreach (var (value, record) in records)
        {
            if (value is not NativeTextarea owner) continue;
            var receipt = new JsonObject
            {
                ["source"] = "Actual NativeTextarea.GetTemplateChild on its already-applied template",
                ["version"] = 1, ["owner_id"] = ids[owner], ["status"] = "incomplete",
                ["template_part_name"] = "PlaceholderTextContentPresenter",
                ["read_only"] = true, ["errors"] = new JsonArray()
            };
            record["textarea_placeholder_evidence"] = receipt;
            try
            {
                var template = owner.Template;
                var partObject = owner.ReadAppliedPlaceholderPart();
                var part = partObject as TextBlock;
                var found = partObject != null && ids.TryGetValue(partObject, out _) && records.ContainsKey(partObject);
                receipt["part_id"] = found ? ids[partObject!] : null;
                receipt["part_runtime_type"] = partObject?.GetType().FullName;
                receipt["same_part_object_in_capture"] = found;
                JsonObject State() => new()
                {
                    ["value"] = owner.Text, ["placeholder"] = owner.PlaceholderText,
                    ["owner_is_loaded"] = owner.IsLoaded, ["owner_visibility"] = owner.Visibility.ToString(),
                    ["owner_opacity"] = owner.Opacity, ["part_text"] = part?.Text,
                    ["part_is_loaded"] = part?.IsLoaded, ["part_visibility"] = part?.Visibility.ToString(),
                    ["part_opacity"] = part?.Opacity,
                    ["part_style"] = part == null ? null : new JsonObject
                    {
                        ["font_size"] = part.FontSize, ["font_weight"] = part.FontWeight.Weight,
                        ["foreground"] = CaptureColor(part.Foreground),
                        ["foreground_brush"] = CaptureBrushEvidence(part.Foreground)
                    },
                    ["same_xaml_root"] = part?.XamlRoot != null && ReferenceEquals(owner.XamlRoot, part.XamlRoot)
                };
                var before = State(); var edges = new JsonArray(); var reached = false;
                var complete = found && part != null && template != null;
                var seen = new HashSet<DependencyObject>(ReferenceEqualityComparer.Instance);
                for (DependencyObject? child = partObject; child != null && seen.Add(child); child = VisualTreeHelper.GetParent(child))
                {
                    if (ReferenceEquals(child, owner)) { reached = true; break; }
                    var parent = VisualTreeHelper.GetParent(child);
                    var childFound = ids.TryGetValue(child, out var childId);
                    var parentFound = parent != null && ids.TryGetValue(parent, out _);
                    var parentId = parentFound ? ids[parent!] : null;
                    var same = childFound && parentFound && records.TryGetValue(child, out var childRecord)
                        && childRecord["parent"]?.GetValue<string>() == parentId;
                    complete &= same;
                    edges.Add(new JsonObject { ["child_id"] = childId, ["parent_id"] = parentId,
                        ["actual_parent_in_visual_walk"] = parentFound, ["captured_parent_matches"] = same });
                }
                var after = State();
                var samePart = ReferenceEquals(partObject, owner.ReadAppliedPlaceholderPart());
                var sameTemplate = ReferenceEquals(template, owner.Template);
                var stable = JsonNode.DeepEquals(before, after);
                complete &= reached && samePart && sameTemplate && stable;
                receipt["before"] = before; receipt["after"] = after;
                receipt["actual_ancestor_edges"] = edges;
                receipt["part_same_object_after"] = samePart;
                receipt["template_same_object_after"] = sameTemplate;
                receipt["getters_unchanged"] = stable;
                receipt["status"] = complete ? "measured" : "incomplete";
                if (!complete) ((JsonArray)receipt["errors"]!).Add("Applied placeholder part or its actual owner/parent chain is missing or changed");
            }
            catch (Exception error)
            {
                receipt["exception_type"] = error.GetType().FullName;
                receipt["hresult"] = error.HResult;
                ((JsonArray)receipt["errors"]!).Add(error.Message);
            }
        }
    }
}
