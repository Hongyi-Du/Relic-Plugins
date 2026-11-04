using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private static void CaptureNativeToggleParts(Dictionary<DependencyObject, string> ids,
        Dictionary<DependencyObject, JsonObject> records)
    {
        static JsonObject State(NativeOverviewToggle owner) => new()
        {
            ["is_checked"] = owner.IsChecked, ["is_three_state"] = owner.IsThreeState,
            ["is_enabled"] = owner.IsEnabled, ["focus_state"] = owner.FocusState.ToString(),
            ["is_loaded"] = owner.IsLoaded, ["thumb_is_hit_test_visible"] = owner.Thumb.IsHitTestVisible,
            ["thumb_child_is_null"] = owner.Thumb.Child == null
        };
        foreach (var (value, record) in records)
        {
            if (value is not NativeOverviewToggle owner) continue;
            var before = State(owner); var errors = new JsonArray(); var edges = new JsonArray();
            var ownerId = ids[owner];
            var trackFound = ids.TryGetValue(owner.Track, out var trackId);
            var shadowFound = ids.TryGetValue(owner.ThumbShadow, out var shadowId);
            var thumbFound = ids.TryGetValue(owner.Thumb, out var thumbId);
            var reached = false; var sameEdges = true;
            var seen = new HashSet<DependencyObject>(ReferenceEqualityComparer.Instance);
            for (DependencyObject? child = owner.Thumb; child != null && seen.Add(child); child = VisualTreeHelper.GetParent(child))
            {
                if (ReferenceEquals(child, owner)) { reached = true; break; }
                var parent = VisualTreeHelper.GetParent(child);
                var childFound = ids.TryGetValue(child, out var childId);
                var parentFound = parent != null && ids.TryGetValue(parent, out _);
                var parentId = parentFound ? ids[parent!] : null;
                var same = childFound && parentFound && records[child]["parent"]?.GetValue<string>() == parentId;
                sameEdges &= same;
                edges.Add(new JsonObject { ["child_id"] = childId, ["parent_id"] = parentId,
                    ["actual_parent_in_visual_walk"] = parentFound, ["captured_parent_matches"] = same });
            }
            var sameContent = ReferenceEquals(owner.Content, owner.Track);
            var sameTrackChild = ReferenceEquals(owner.Track.Child, owner.ThumbShadow);
            var sameSurface = ReferenceEquals(owner.ThumbShadow.Surface, owner.Thumb);
            var after = State(owner); var stableState = JsonNode.DeepEquals(before, after);
            var complete = trackFound && shadowFound && thumbFound && reached && sameEdges
                && sameContent && sameTrackChild && sameSurface && owner.HasCurrentParts && stableState;
            if (!complete) errors.Add("Retained production toggle parts, actual parent chain or getter snapshot changed or are missing");
            record["native_toggle_parts"] = new JsonObject
            {
                ["source"] = "Actual NativeOverviewToggle retained production parts and live getters", ["version"] = 1,
                ["status"] = complete ? "measured" : "incomplete", ["owner_id"] = ownerId,
                ["owner_runtime_type"] = owner.GetType().FullName, ["track_id"] = trackId,
                ["shadow_id"] = shadowId, ["thumb_id"] = thumbId,
                ["owner_content_is_track"] = sameContent, ["track_child_is_shadow"] = sameTrackChild,
                ["shadow_surface_is_thumb"] = sameSurface, ["current_parts_same_objects"] = owner.HasCurrentParts,
                ["part_contract"] = "NativeOverviewToggle decorative thumb; sealed production owner; no independent thumb input handler",
                ["actual_ancestor_edges"] = edges, ["reaches_same_owner_object"] = reached,
                ["all_captured_edges_match"] = sameEdges, ["before"] = before, ["after"] = after,
                ["getters_unchanged"] = stableState, ["observed_at_utc"] = DateTimeOffset.UtcNow.ToString("O"),
                ["errors"] = errors,
                ["quantity"] = "Live originating toggle state for its retained decorative thumb; not an independent thumb interaction or proof of final-frame paint"
            };
        }
    }
}
