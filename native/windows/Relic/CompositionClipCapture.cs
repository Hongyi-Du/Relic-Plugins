using Microsoft.UI.Xaml;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private static JsonObject CaptureCompositionClip(FrameworkElement owner, JsonObject ownerNode)
    {
        // GetElementVisual is not a read-only way to discover an existing visual.
        // In the shipped WinUI source, EnsureHandOffVisual can create a visual,
        // attach transform listeners and dirty the composition tree. Doing that
        // between the PNG and UIA reads changes the object being measured.
        // https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/core/core/elements/uielement.cpp#L7213
        // The current production code retains a logo clip and shadow hand-in
        // visuals, but no backing Visual with an independently retained owner
        // binding. Neither object proves the current backing Visual. Preserve
        // that measurement gap instead of creating one during extraction.
        return new JsonObject
        {
            ["source"] = "Actual XAML owner; backing Visual not read during authoritative capture",
            ["status"] = "not-measured", ["owner_id"] = ownerNode["id"]?.DeepClone(),
            ["owner_runtime_type"] = owner.GetType().FullName, ["owner_type"] = owner.GetType().Name,
            ["owner_is_loaded"] = owner.IsLoaded, ["observed_at_utc"] = DateTimeOffset.UtcNow.ToString("O"),
            ["owner_local_bounds"] = ownerNode["local_bounds"]?.DeepClone(),
            ["owner_to_window"] = ownerNode["transform"]?.DeepClone(),
            ["xaml_clip_present"] = owner.Clip != null,
            ["backing_visual_read"] = false, ["production_backing_visual_binding_available"] = false,
            ["before"] = null, ["after"] = null, ["binding"] = null, ["properties_stable"] = null,
            ["reason"] = "No production-retained backing Visual/owner binding is available. GetElementVisual may create handoff state and is not called in the authoritative capture window; Composition clip presence and geometry remain unmeasured.",
            ["quantity"] = "Actual XAML owner identity and separately retained UIElement.Clip evidence only; no backing Visual clip observation",
            ["presentation_identity_proven"] = false
        };
    }
}
