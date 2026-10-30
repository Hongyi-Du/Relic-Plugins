using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private void CaptureNativeAvatarParts(Dictionary<DependencyObject, string> ids,
        Dictionary<DependencyObject, JsonObject> records)
    {
        foreach (var (value, record) in records)
        {
            if (value is not PersonPicture picture || !nativeAvatarPictures.TryGetValue(picture, out var owner)) continue;
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
                ["owner_tag_is_paint"] = ReferenceEquals(picture.Tag, owner.Paint),
                ["owner_template_is_retained"] = ReferenceEquals(picture.Template, owner.PaintTemplate),
                ["owner_is_loaded"] = picture.IsLoaded, ["owner_is_tab_stop"] = picture.IsTabStop,
                ["composition_picture_is_owner"] = ReferenceEquals(owner.Picture, picture),
                ["retained_composition_same_object"] = nativeAvatarPictures.TryGetValue(picture, out var current) && ReferenceEquals(current, owner),
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
            Path(owner.Paint, picture);
            if (organization != null)
            {
                Path(organization.Surface, picture); Path(organization.Initial, picture);
                if (organization.SubgroupOutline != null) Path(organization.SubgroupOutline, picture);
                complete &= organization.HasCurrentParts && organization.SubgroupOutline != null && frame == null;
            }
            if (frame != null) { Path(picture, frame.Surface); complete &= frame.HasCurrentParts && organization == null; }
            else if (organization == null) complete = false;
            var after = State(); var stable = JsonNode.DeepEquals(before, after);
            complete &= owner.HasCurrentPaint && ReferenceEquals(owner.Picture, picture) && stable;
            if (!complete) errors.Add("Retained avatar parts or their actual parent chain are missing, ambiguous or changed");
            record["native_avatar_parts"] = new JsonObject
            {
                ["source"] = "Actual retained NativeAvatarPicture production parts and visual parent identities",
                ["version"] = 2, ["status"] = complete ? "measured" : "incomplete", ["kind"] = kind,
                ["owner_id"] = ids[picture], ["owner_runtime_type"] = picture.GetType().FullName,
                ["composition_runtime_type"] = owner.GetType().FullName,
                ["parts"] = partRows, ["actual_ancestor_edges"] = edges,
                ["before"] = before, ["after"] = after, ["getters_unchanged"] = stable,
                ["errors"] = errors, ["observed_at_utc"] = DateTimeOffset.UtcNow.ToString("O"),
                ["scope"] = "Decorative avatar outline or outer border only; image/icon/label content and status dots retain their own evidence; no final pixel or antialias equivalence"
            };
        }
    }
}
