using Microsoft.UI.Composition;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Hosting;
using Microsoft.UI.Xaml.Media;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private const string PreparedClipSource = "diagnostic-prepared backing Visual retained before authoritative capture";
    private sealed class PreparedClipOwner
    {
        internal required FrameworkElement Owner;
        internal required XamlRoot Root;
        internal required JsonObject Setup;
        internal Visual? Visual;
        internal CompositionClip? BaselineClip;
        internal CompositionGeometry? BaselineGeometry;
        internal bool Unloaded;
        internal RoutedEventHandler? UnloadedHandler;
        internal JsonObject? Baseline, BeforeReadback, AfterReadback;
    }
    private readonly Dictionary<FrameworkElement, PreparedClipOwner> preparedClipOwners = new(ReferenceEqualityComparer.Instance);
    private string? preparedClipCase;
    private JsonObject? preparedClipSetup, preparedClipRender;

    private void PrepareCompositionClipCapture(string caseId)
    {
        if (!VisualCaptureEnabled) throw new InvalidOperationException("Composition preparation is CI-only");
        EndCompositionClipCapture();
        preparedClipCase = caseId;
        preparedClipSetup = new JsonObject { ["case_id"] = caseId, ["started_qpc"] = Stopwatch.GetTimestamp(),
            ["completed_qpc"] = null, ["qpc_frequency"] = Stopwatch.Frequency, ["may_create"] = true,
            ["created_unknown"] = true, ["production_original_state_observed"] = false,
            ["quantity"] = "Explicit diagnostic preparation; may create handoff visuals and register listeners before the capture baseline" };
        var seen = new HashSet<DependencyObject>(ReferenceEqualityComparer.Instance);
        void Walk(DependencyObject value)
        {
            if (!seen.Add(value)) return;
            if (value is FrameworkElement owner && owner.IsLoaded && owner.XamlRoot is { } ownerRoot)
            {
                var setup = new JsonObject { ["index"] = preparedClipOwners.Count,
                    ["api"] = "ElementCompositionPreview.GetElementVisual(actual owner)",
                    ["started_qpc"] = Stopwatch.GetTimestamp(), ["completed_qpc"] = null,
                    ["may_create"] = true, ["created_unknown"] = true, ["returned"] = false };
                var retained = new PreparedClipOwner { Owner = owner, Root = ownerRoot, Setup = setup };
                retained.UnloadedHandler = (_, _) => retained.Unloaded = true;
                owner.Unloaded += retained.UnloadedHandler;
                preparedClipOwners.Add(owner, retained);
                try
                {
                    setup["owner_identity"] = PreparedClipIdentity(owner);
                    setup["root_identity"] = PreparedClipIdentity(ownerRoot);
                    // Supported, potentially mutating API. This is deliberately
                    // before render preparation and the authoritative baseline.
                    // It neither installs a clip nor changes Visual properties.
                    retained.Visual = ElementCompositionPreview.GetElementVisual(owner);
                    setup["returned"] = retained.Visual != null;
                    if (retained.Visual == null) throw new InvalidOperationException("Actual backing Visual was null");
                    setup["visual_identity"] = PreparedClipIdentity(retained.Visual);
                    setup["after_call"] = PreparedClipState(retained);
                }
                catch (Exception error) { setup["error"] = error.ToString(); }
                finally { setup["completed_qpc"] = Stopwatch.GetTimestamp(); }
            }
            for (var i = 0; i < VisualTreeHelper.GetChildrenCount(value); i++) Walk(VisualTreeHelper.GetChild(value, i));
        }
        Walk(root);
        foreach (var popup in VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot))
            if (popup.IsOpen && popup.Child != null) Walk(popup.Child);
        preparedClipSetup["completed_qpc"] = Stopwatch.GetTimestamp();
        preparedClipSetup["owner_count"] = preparedClipOwners.Count;
    }

    private void EstablishCompositionClipBaseline()
    {
        // Reuse the actual render/commit/flush observations that already precede
        // the PNG. These are preparation observations, not presentation proof.
        preparedClipRender = new JsonObject
        {
            ["case_id"] = capturedNativeLabelEvidence?["case_id"]?.DeepClone(),
            ["render_cycle"] = capturedNativeLabelEvidence?["render_cycle"]?.DeepClone(),
            ["request_commit"] = capturedNativeLabelEvidence?["request_commit"]?.DeepClone(),
            ["dwm_flush"] = capturedNativeLabelEvidence?["dwm_flush"]?.DeepClone(),
            ["failure"] = capturedNativeLabelEvidence?["failure"]?.DeepClone()
        };
        foreach (var retained in preparedClipOwners.Values)
        {
            try
            {
                // Keep these actual objects alive for the interval as well, so
                // an identity cannot appear equal merely through pointer reuse.
                retained.BaselineClip = retained.Visual?.Clip;
                retained.BaselineGeometry = (retained.BaselineClip as CompositionGeometricClip)?.Geometry;
                retained.Baseline = ReadPreparedClipState(retained);
            }
            catch (Exception error)
            {
                retained.Baseline = new JsonObject { ["error"] = error.ToString(), ["state"] = null };
            }
        }
    }

    private void CheckpointCompositionClipCapture(bool beforeReadback)
    {
        foreach (var retained in preparedClipOwners.Values)
        {
            var state = ReadPreparedClipState(retained);
            if (beforeReadback) retained.BeforeReadback = state;
            else retained.AfterReadback = state;
        }
    }

    private JsonObject ReadPreparedClipState(PreparedClipOwner retained)
    {
        var point = new JsonObject { ["started_qpc"] = Stopwatch.GetTimestamp(), ["state"] = null };
        try { point["state"] = PreparedClipState(retained); }
        catch (Exception error) { point["error"] = error.ToString(); }
        point["completed_qpc"] = Stopwatch.GetTimestamp();
        return point;
    }

    private JsonObject PreparedClipState(PreparedClipOwner retained)
    {
        if (retained.Visual == null) throw new InvalidOperationException("No actual Visual returned in preparation");
        var owner = retained.Owner; var visual = retained.Visual;
        var clip = visual.Clip; var geometry = (clip as CompositionGeometricClip)?.Geometry;
        var transform = owner.TransformToVisual(root);
        var origin = transform.TransformPoint(new Windows.Foundation.Point(0, 0));
        var x = transform.TransformPoint(new Windows.Foundation.Point(1, 0));
        var y = transform.TransformPoint(new Windows.Foundation.Point(0, 1));
        return new JsonObject
        {
            ["owner_identity"] = PreparedClipIdentity(owner), ["root_identity"] = PreparedClipIdentity(retained.Root),
            ["visual_identity"] = PreparedClipIdentity(visual),
            ["clip_identity"] = clip == null ? null : PreparedClipIdentity(clip),
            ["geometry_identity"] = geometry == null ? null : PreparedClipIdentity(geometry),
            ["retained_baseline_clip_identity"] = retained.BaselineClip == null ? null : PreparedClipIdentity(retained.BaselineClip),
            ["retained_baseline_geometry_identity"] = retained.BaselineGeometry == null ? null : PreparedClipIdentity(retained.BaselineGeometry),
            ["owner_is_loaded"] = owner.IsLoaded, ["owner_unloaded_since_setup"] = retained.Unloaded,
            ["same_xaml_root"] = ReferenceEquals(owner.XamlRoot, retained.Root),
            ["same_retained_owner"] = preparedClipOwners.TryGetValue(owner, out var current) && ReferenceEquals(current, retained),
            ["owner_local_bounds"] = CaptureBox(new Windows.Foundation.Rect(0, 0, owner.ActualWidth, owner.ActualHeight)),
            ["owner_to_window"] = new JsonObject { ["m11"] = x.X - origin.X, ["m12"] = x.Y - origin.Y,
                ["m21"] = y.X - origin.X, ["m22"] = y.Y - origin.Y, ["offset_x"] = origin.X, ["offset_y"] = origin.Y },
            ["xaml_clip_present"] = owner.Clip != null,
            ["properties"] = RetainedClipSnapshot(visual, clip)
        };
    }

    private JsonObject CapturePreparedCompositionClip(FrameworkElement owner, JsonObject node, JsonObject evidence)
    {
        if (!preparedClipOwners.TryGetValue(owner, out var retained)) return evidence;
        evidence["source"] = PreparedClipSource;
        evidence["quantity"] = "Prepared actual backing-Visual property getters; not unprepared production state, animation samples or final-PNG coverage";
        evidence["diagnostic_preparation"] = new JsonObject
        {
            ["setup"] = preparedClipSetup?.DeepClone(), ["owner_call"] = retained.Setup.DeepClone(),
            ["render_preparation"] = preparedClipRender?.DeepClone(), ["baseline"] = retained.Baseline?.DeepClone(),
            ["before_desktop_readback"] = retained.BeforeReadback?.DeepClone(), ["after_desktop_readback"] = retained.AfterReadback?.DeepClone(),
            ["capture_owner_same_object"] = ReferenceEquals(owner, retained.Owner),
            ["read_only_authoritative_window"] = true, ["production_original_state_observed"] = false
        };
        var receipt = (JsonObject)evidence["diagnostic_preparation"]!;
        try
        {
            if (preparedClipCase == null || retained.Visual == null || retained.Setup["error"] != null
                || preparedClipRender?["case_id"]?.GetValue<string>() != preparedClipCase || preparedClipRender?["failure"] != null
                || retained.Unloaded || !owner.IsLoaded || !ReferenceEquals(owner.XamlRoot, retained.Root))
                throw new InvalidOperationException("Prepared backing Visual/owner binding failed, unloaded or changed root");
            var before = ReadPreparedClipState(retained); var after = ReadPreparedClipState(retained);
            receipt["before_getters"] = before; receipt["after_getters"] = after;
            var points = new[] { retained.Baseline, retained.BeforeReadback, retained.AfterReadback, before, after };
            if (points.Any(point => point == null || point["error"] != null || point["state"] == null)
                || points.Any(point => !JsonNode.DeepEquals(point!["state"], points[0]!["state"])))
                throw new InvalidOperationException("Prepared backing Visual observations are missing or changed across readback and getters");
            var state = (JsonObject)before["state"]!;
            if (!JsonNode.DeepEquals(state["clip_identity"], state["retained_baseline_clip_identity"])
                || !JsonNode.DeepEquals(state["geometry_identity"], state["retained_baseline_geometry_identity"]))
                throw new InvalidOperationException("Composition clip or geometry differs from the strongly retained baseline object");
            evidence["before"] = state["properties"]!.DeepClone();
            evidence["after"] = after["state"]!["properties"]!.DeepClone();
            evidence["backing_visual_read"] = true; evidence["properties_stable"] = true;
            evidence["binding"] = new JsonObject
            {
                ["source"] = "actual IUnknown identities in retained preparation and read-only checkpoints",
                ["visual_same_object_after"] = JsonNode.DeepEquals(before["state"]!["visual_identity"], after["state"]!["visual_identity"]),
                ["clip_same_object_after"] = JsonNode.DeepEquals(before["state"]!["clip_identity"], after["state"]!["clip_identity"]),
                ["geometry_same_object_after"] = JsonNode.DeepEquals(before["state"]!["geometry_identity"], after["state"]!["geometry_identity"])
            };
            evidence["reason"] = null; evidence["status"] = "measured";
        }
        catch (Exception error)
        {
            evidence["status"] = "not-measured"; evidence["reason"] = error.Message;
            receipt["error"] = error.ToString();
        }
        return evidence;
    }

    private static string PreparedClipIdentity(object value)
    {
        IntPtr inspectable = IntPtr.Zero, identity = IntPtr.Zero;
        try
        {
            inspectable = WinRT.MarshalInspectable<object>.FromManaged(value);
            var iid = new Guid("00000000-0000-0000-c000-000000000046");
            Marshal.ThrowExceptionForHR(Marshal.QueryInterface(inspectable, ref iid, out identity));
            if (identity == IntPtr.Zero) throw new InvalidOperationException("Actual IUnknown identity is null");
            return AutomationIdentityNative.Pointer(identity);
        }
        finally { if (identity != IntPtr.Zero) Marshal.Release(identity); if (inspectable != IntPtr.Zero) Marshal.Release(inspectable); }
    }

    private async Task PublishCompositionClipPreparation(string directory, string caseId)
    {
        if (preparedClipCase != caseId || preparedClipSetup == null) return;
        var owners = new JsonArray();
        foreach (var retained in preparedClipOwners.Values)
            owners.Add(new JsonObject { ["owner_call"] = retained.Setup.DeepClone(),
                ["baseline"] = retained.Baseline?.DeepClone(), ["before_desktop_readback"] = retained.BeforeReadback?.DeepClone(),
                ["after_desktop_readback"] = retained.AfterReadback?.DeepClone(), ["owner_unloaded_since_setup"] = retained.Unloaded });
        var receipt = new JsonObject { ["source"] = PreparedClipSource, ["setup"] = preparedClipSetup.DeepClone(),
            ["render_preparation"] = preparedClipRender?.DeepClone(), ["owners"] = owners,
            ["presentation_identity_proven"] = false, ["production_original_state_observed"] = false };
        await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(directory, caseId + ".composition-clip-preparation.json"),
            NativeCaptureNumbers.Prepare(receipt, "Actual Composition diagnostic preparation").ToJsonString());
    }

    private void EndCompositionClipCapture()
    {
        foreach (var retained in preparedClipOwners.Values)
            if (retained.UnloadedHandler != null) retained.Owner.Unloaded -= retained.UnloadedHandler;
        // Visuals belong to XAML: drop our strong references, never Close/Dispose
        // the backing objects or try to undo WinUI's handoff state.
        preparedClipOwners.Clear(); preparedClipCase = null; preparedClipSetup = preparedClipRender = null;
    }
}
