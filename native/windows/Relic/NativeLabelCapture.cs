using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    // The main XAML walk can attach this raw evidence to a real NativeLabel node.
    // It is intentionally not a canonical font/geometry conversion: presentation
    // synchronization, source text ownership and equal-quantity browser evidence
    // still have to be established by the capture/matcher work.
    private static JsonObject CaptureNativeLabel(NativeLabel label) => label.CaptureProductionReceipt();

    private JsonObject? capturedNativeLabelEvidence;
    private NativeLabel[]? capturedNativeLabels;
    private JsonArray? capturedNativeLabelBaseline;

    private NativeLabel[] NativeLabelsForCapture()
    {
        var result = new List<NativeLabel>(); var seen = new HashSet<DependencyObject>();
        void Walk(DependencyObject value, bool visible)
        {
            if (!seen.Add(value)) return;
            if (value is UIElement ui) visible &= ui.Visibility == Visibility.Visible && ui.Opacity > 0;
            if (!visible) return;
            // Do not omit an empty/zero-width failed label: readiness below must
            // reject it instead of accepting an empty set as successfully drawn.
            if (value is NativeLabel label && label.IsLoaded) result.Add(label);
            for (var i = 0; i < VisualTreeHelper.GetChildrenCount(value); i++) Walk(VisualTreeHelper.GetChild(value, i), visible);
        }
        Walk(root, true);
        foreach (var popup in VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot))
            if (popup.IsOpen && popup.Child != null) Walk(popup.Child, true);
        return result.ToArray();
    }

    private JsonArray ObserveNativeLabelVersions(NativeLabel[] labels)
    {
        var result = new JsonArray();
        for (var i = 0; i < labels.Length; i++)
            result.Add(new JsonObject { ["capture_label_index"] = i, ["state"] = labels[i].ObserveCaptureVersion(root) });
        return result;
    }

    private static async Task ObserveNativeLabelRenderCycle(JsonObject record)
    {
        var completion = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        JsonObject? rendering = null;
        EventHandler<object> onRendering = (_, args) =>
        {
            if (completion.Task.IsCompleted) return;
            rendering ??= new JsonObject { ["source"] = "CompositionTarget.Rendering", ["qpc"] = Stopwatch.GetTimestamp(),
                ["rendering_time_ticks"] = (args as RenderingEventArgs)?.RenderingTime.Ticks };
            record["rendering"] = rendering.DeepClone();
        };
        void OnRendered(object? sender, object args)
        {
            if (completion.Task.IsCompleted) return;
            if (args is not RenderedEventArgs rendered)
            {
                completion.TrySetException(new InvalidOperationException("Rendered callback did not expose actual RenderedEventArgs")); return;
            }
            if (rendering == null) return;
            record["rendered"] = new JsonObject { ["source"] = "CompositionTarget.Rendered",
                ["qpc"] = Stopwatch.GetTimestamp(), ["frame_duration_ticks"] = rendered.FrameDuration.Ticks };
            completion.TrySetResult(true);
        }
        CompositionTarget.Rendering += onRendering; CompositionTarget.Rendered += OnRendered;
        try { await completion.Task.WaitAsync(TimeSpan.FromSeconds(10)); }
        finally { CompositionTarget.Rendering -= onRendering; CompositionTarget.Rendered -= OnRendered; }
    }

    private async Task BeginNativeLabelCaptureAsync(string caseId)
    {
        if (!VisualCaptureEnabled) throw new InvalidOperationException("NativeLabel capture synchronization is CI-only");
        EndNativeLabelCapture();
        var cycle = new JsonObject { ["rendering"] = null, ["rendered"] = null,
            ["quantity"] = "Observed XAML render cycle; not a presented surface/frame identity" };
        capturedNativeLabelEvidence = new JsonObject
        {
            ["case_id"] = caseId, ["source"] = "Actual NativeLabel object references observed around desktop readback",
            ["qpc_frequency"] = Stopwatch.Frequency, ["render_cycle"] = cycle,
            ["request_commit"] = null, ["dwm_flush"] = null, ["baseline"] = null, ["production_draws"] = null, ["checkpoints"] = new JsonArray(),
            ["presented_frame_id"] = null, ["presentation_identity_proven"] = false,
            ["scope"] = "Checks actual label membership, surface binding, submitted draw revision and measured XAML geometry/clip stability. Does not certify final composed pixels, visibility through other layers, or a presented-frame identity."
        };
        try
        {
            root.UpdateLayout();
            await ObserveNativeLabelRenderCycle(cycle);
            capturedNativeLabels = NativeLabelsForCapture();
            capturedNativeLabelBaseline = ObserveNativeLabelVersions(capturedNativeLabels);
            capturedNativeLabelEvidence["baseline"] = capturedNativeLabelBaseline.DeepClone();
            var draws = new JsonArray();
            for (var i = 0; i < capturedNativeLabels.Length; i++)
                draws.Add(new JsonObject { ["capture_label_index"] = i, ["production_receipt"] = capturedNativeLabels[i].CaptureProductionReceipt() });
            capturedNativeLabelEvidence["production_draws"] = draws;
            var commit = new JsonObject { ["source"] = "Window.Compositor.RequestCommitAsync", ["started_qpc"] = Stopwatch.GetTimestamp(),
                ["completed_qpc"] = null, ["completed"] = false, ["quantity"] = "API action completion; not a presentation acknowledgement" };
            capturedNativeLabelEvidence["request_commit"] = commit;
            await Compositor.RequestCommitAsync().AsTask().WaitAsync(TimeSpan.FromSeconds(10));
            commit["completed_qpc"] = Stopwatch.GetTimestamp(); commit["completed"] = true;
            var flush = new JsonObject { ["source"] = "DwmFlush", ["started_qpc"] = Stopwatch.GetTimestamp(), ["completed_qpc"] = null, ["hresult"] = null,
                ["quantity"] = "Calling application's queued DirectX flush; no NativeLabel surface/frame identity is returned" };
            capturedNativeLabelEvidence["dwm_flush"] = flush;
            var flushResult = NativeLabelDwmFlush(); flush["completed_qpc"] = Stopwatch.GetTimestamp(); flush["hresult"] = flushResult;
            NativeLabelInterop.Check(flushResult);
            CheckpointNativeLabelCapture("after_render_and_commit_requests");
        }
        catch (Exception ex) { capturedNativeLabelEvidence["failure"] = ex.ToString(); throw; }
    }

    private void CheckpointNativeLabelCapture(string stage)
    {
        if (capturedNativeLabels == null || capturedNativeLabelBaseline == null || capturedNativeLabelEvidence == null) return;
        if (!VisualCaptureEnabled) throw new InvalidOperationException("NativeLabel capture checkpoint is CI-only");
        var observed = NativeLabelsForCapture();
        var sameObjects = observed.Length == capturedNativeLabels.Length
            && observed.Select((label, index) => ReferenceEquals(label, capturedNativeLabels[index])).All(same => same);
        JsonArray? versions = null; string? failure = null;
        try { if (sameObjects) versions = ObserveNativeLabelVersions(observed); }
        catch (Exception ex) { failure = ex.ToString(); }
        var stable = sameObjects && failure == null && JsonNode.DeepEquals(versions, capturedNativeLabelBaseline);
        ((JsonArray)capturedNativeLabelEvidence["checkpoints"]!).Add(new JsonObject
        {
            ["stage"] = stage, ["qpc"] = Stopwatch.GetTimestamp(), ["same_object_references"] = sameObjects,
            ["same_observed_state"] = stable, ["state"] = versions, ["failure"] = failure
        });
        if (!stable) throw new InvalidOperationException("Actual NativeLabel membership, binding, draw revision or geometry changed during " + stage + ": " + failure);
    }

    private void EndNativeLabelCapture()
    {
        capturedNativeLabels = null; capturedNativeLabelBaseline = null; capturedNativeLabelEvidence = null;
    }

    [DllImport("dwmapi.dll", EntryPoint = "DwmFlush", ExactSpelling = true)]
    private static extern int NativeLabelDwmFlush();
}
