using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private static void CaptureNativeAvatarParts(Dictionary<DependencyObject, string> ids,
        Dictionary<DependencyObject, JsonObject> records)
    {
        foreach (var (value, record) in records)
        {
            if (value is not NativeAvatarPicture owner) continue;
            var frame = owner.ReplyFrame;
            var organization = owner.Paint as NativeOrganizationAvatarPaint;
            if (frame == null && organization?.SubgroupOutline == null) continue;
            var kind = organization != null ? "organization-outline" : "reply-border";
            var parts = new Dictionary<string, DependencyObject> { ["paint"] = owner.Paint };
            if (organization != null)
            {
                parts["surface"] = organization.Surface; parts["initial"] = organization.Initial;
                if (organization.SubgroupOutline != null) parts["outline"] = organization.SubgroupOutline;
            }
            if (frame != null) { parts["frame"] = frame.Surface; parts["layout"] = frame.Layout; }
            JsonObject State() => new()
            {
                ["owner_tag_is_paint"] = ReferenceEquals(owner.Tag, owner.Paint),
                ["owner_template_is_retained"] = ReferenceEquals(owner.Template, owner.PaintTemplate),
                ["owner_is_loaded"] = owner.IsLoaded, ["owner_is_tab_stop"] = owner.IsTabStop,
                ["organization_current_parts"] = organization?.HasCurrentParts,
                ["organization_has_cabinet_ring"] = organization == null ? null : organization.CabinetRing != null,
                ["reply_current_parts"] = frame?.HasCurrentParts,
                ["reply_frame_count"] = frame == null ? 0 : 1,
                ["reply_frame_contract_type"] = frame?.GetType().FullName
            };
            var before = State(); var errors = new JsonArray(); var partRows = new JsonArray();
            var edges = new JsonArray(); var seenEdges = new HashSet<string>(); var complete = true;
            foreach (var (role, part) in parts)
            {
                var captured = ids.TryGetValue(part, out var id) && records.ContainsKey(part);
                complete &= captured;
                partRows.Add(new JsonObject { ["role"] = role, ["id"] = id,
                    ["runtime_type"] = part.GetType().FullName, ["same_retained_object_in_capture"] = captured });
            }
            void Path(DependencyObject start, DependencyObject end)
            {
                var reached = false; var seen = new HashSet<DependencyObject>(ReferenceEqualityComparer.Instance);
                for (DependencyObject? child = start; child != null && seen.Add(child); child = VisualTreeHelper.GetParent(child))
                {
                    if (ReferenceEquals(child, end)) { reached = true; break; }
                    var parent = VisualTreeHelper.GetParent(child);
                    var childFound = ids.TryGetValue(child, out var childId);
                    var parentFound = parent != null && ids.TryGetValue(parent, out _);
                    var parentId = parentFound ? ids[parent!] : null;
                    var same = childFound && parentFound && records.TryGetValue(child, out var childNode)
                        && childNode["parent"]?.GetValue<string>() == parentId;
                    complete &= same;
                    if (seenEdges.Add(childId ?? "uncaptured")) edges.Add(new JsonObject
                    { ["child_id"] = childId, ["parent_id"] = parentId,
                        ["actual_parent_in_visual_walk"] = parentFound, ["captured_parent_matches"] = same });
                }
                complete &= reached;
            }
            Path(owner.Paint, owner);
            if (organization != null)
            {
                Path(organization.Surface, owner); Path(organization.Initial, owner);
                if (organization.SubgroupOutline != null) Path(organization.SubgroupOutline, owner);
                complete &= organization.HasCurrentParts && organization.SubgroupOutline != null && frame == null;
            }
            if (frame != null) { Path(owner, frame.Surface); complete &= frame.HasCurrentParts && organization == null; }
            else if (organization == null) complete = false;
            var after = State(); var stable = JsonNode.DeepEquals(before, after);
            complete &= owner.HasCurrentPaint && stable;
            if (!complete) errors.Add("Retained avatar parts or their actual parent chain are missing, ambiguous or changed");
            record["native_avatar_parts"] = new JsonObject
            {
                ["source"] = "Actual retained NativeAvatarPicture production parts and visual parent identities",
                ["version"] = 1, ["status"] = complete ? "measured" : "incomplete", ["kind"] = kind,
                ["owner_id"] = ids[owner], ["owner_runtime_type"] = owner.GetType().FullName,
                ["parts"] = partRows, ["actual_ancestor_edges"] = edges,
                ["before"] = before, ["after"] = after, ["getters_unchanged"] = stable,
                ["errors"] = errors, ["observed_at_utc"] = DateTimeOffset.UtcNow.ToString("O"),
                ["scope"] = "Decorative avatar outline or outer border only; image/icon/label content and status dots retain their own evidence; no final pixel or antialias equivalence"
            };
        }
    }
}
