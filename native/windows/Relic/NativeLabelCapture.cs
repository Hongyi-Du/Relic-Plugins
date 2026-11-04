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
    private JsonObject CaptureNativeLabel(NativeLabel label)
    {
        var result = label.CaptureProductionReceipt();
        int? index = null;
        if (capturedNativeLabels != null)
            for (var i = 0; i < capturedNativeLabels.Length; i++)
                if (ReferenceEquals(label, capturedNativeLabels[i])) { index = i; break; }
        result["capture_binding"] = new JsonObject
        {
            ["source"] = "Actual NativeLabel object ReferenceEquals against the capture observer label array",
            ["capture_label_index"] = index, ["same_object_reference"] = index != null,
            ["case_id"] = capturedNativeLabelEvidence?["case_id"]?.DeepClone()
        };
        return result;
    }

    private static bool CurrentNativeLabelSubmission(JsonObject evidence)
    {
        if (evidence["current_submission"] is not JsonObject state || evidence["draw"] is not JsonObject draw) return false;
        return state["is_loaded"]?.GetValue<bool>() == true && state["queued"]?.GetValue<bool>() == false
            && state["rendering"]?.GetValue<bool>() == false && state["surface_binding_same_com_identity"]?.GetValue<bool>() == true
            && evidence["last_failure"] == null && draw["surface_end_draw_succeeded"]?.GetValue<bool>() == true
            && draw["draw_hresult"]?.GetValue<int>() >= 0 && draw["surface_end_draw_hresult"]?.GetValue<int>() >= 0
            && JsonNode.DeepEquals(draw["layout_revision"], evidence["current_layout_revision"])
            && JsonNode.DeepEquals(draw["surface_revision"], evidence["current_surface_revision"])
            && JsonNode.DeepEquals(draw["draw_ordinal"], evidence["current_draw_ordinal"]);
    }

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

    private static async Task ObserveNativeLabelRenderCycle(JsonObject record, Action requestActualRedraw)
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
        try
        {
            // Static windows may produce Rendering without a new Rendered
            // event. Submit the same labels through their production renderer
            // after subscribing, instead of waiting for unrelated UI damage.
            record["redraw_request_started_qpc"] = Stopwatch.GetTimestamp();
            requestActualRedraw();
            record["redraw_request_completed_qpc"] = Stopwatch.GetTimestamp();
            await completion.Task.WaitAsync(TimeSpan.FromSeconds(10));
        }
        finally { CompositionTarget.Rendering -= onRendering; CompositionTarget.Rendered -= OnRendered; }
    }

    private async Task BeginNativeLabelCaptureAsync(string outputDirectory, string caseId)
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
            var labelsToDraw = NativeLabelsForCapture();
            cycle["requested_label_count"] = labelsToDraw.Length;
            await ObserveNativeLabelRenderCycle(cycle, () =>
            {
                foreach (var label in labelsToDraw) label.RequestCaptureRedraw();
            });
            // Rendered can precede queued production text work, especially when
            // a modal realizes labels while background shaping finishes. Wait
            // for the real submissions before establishing the frame baseline;
            // this does not force a draw, replace evidence or accept a blank.
            var submissions = Stopwatch.StartNew();
            while (NativeLabelsForCapture().Any(label => !label.HasCurrentDraw))
            {
                if (submissions.Elapsed > TimeSpan.FromSeconds(10))
                    throw new TimeoutException("Native labels did not finish their requested production draw: "
                        + new JsonArray(NativeLabelsForCapture().Where(label => !label.HasCurrentDraw)
                            .Select(label => (JsonNode)label.DrawState()).ToArray()).ToJsonString());
                await Task.Delay(16);
            }
            cycle["production_submission_wait_ms"] = submissions.Elapsed.TotalMilliseconds;
            // A completed Rendered callback can still precede the Image's
            // pending arrange. db91b1b retained seven real settings labels
            // whose images changed from 0x0 to their actual dimensions while
            // RequestCommitAsync yielded. Keep that preparation observation,
            // and establish the immutable baseline only after the requested
            // commit/flush have completed, before the first desktop readback.
            var preparingLabels = NativeLabelsForCapture();
            capturedNativeLabelEvidence["before_commit_preparation"] = ObserveNativeLabelVersions(preparingLabels);
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
            capturedNativeLabels = NativeLabelsForCapture();
            capturedNativeLabelBaseline = ObserveNativeLabelVersions(capturedNativeLabels);
            capturedNativeLabelEvidence["baseline"] = capturedNativeLabelBaseline.DeepClone();
            capturedNativeLabelEvidence["baseline_established_qpc"] = Stopwatch.GetTimestamp();
            var draws = new JsonArray();
            for (var i = 0; i < capturedNativeLabels.Length; i++)
                draws.Add(new JsonObject { ["capture_label_index"] = i, ["production_receipt"] = capturedNativeLabels[i].CaptureProductionReceipt() });
            capturedNativeLabelEvidence["production_draws"] = draws;
            CheckpointNativeLabelCapture("after_render_and_commit_requests");
        }
        catch (Exception ex)
        {
            capturedNativeLabelEvidence["failure"] = ex.ToString();
            // Preserve the actual PNG and other source measurements even when
            // this independent observer fails. The scene still fails after
            // extraction, and its raw JSON retains the missing frame evidence.
            capturedNativeLabels = null; capturedNativeLabelBaseline = null;
        }
        finally
        {
            // Export even if the frame observer or EndDraw failed. These are
            // the current production target's bytes, not a replacement PNG.
            var readbacks = new JsonArray(); var readbackErrors = new JsonArray();
            capturedNativeLabelEvidence["surface_readbacks"] = readbacks;
            capturedNativeLabelEvidence["surface_readback_errors"] = readbackErrors;
            try
            {
                var labels = NativeLabelsForCapture();
                for (var i = 0; i < labels.Length; i++)
                {
                    try
                    {
                        var record = labels[i].WriteCaptureReadback(System.IO.Path.Combine(outputDirectory, "native-label-surfaces"), caseId, i);
                        record["directory"] = "native-label-surfaces"; readbacks.Add(record);
                        if (record["status"]?.ToString() != "surface-pixels-read"
                            || record["is_current_draw_at_export"]?.GetValue<bool>() != true
                            || record["surface_submission_succeeded"]?.GetValue<bool>() != true)
                            readbackErrors.Add("Actual NativeLabel target readback is incomplete for label " + i);
                    }
                    catch (Exception exportError)
                    {
                        readbacks.Add(new JsonObject { ["capture_label_index"] = i, ["status"] = "export-failed", ["failure"] = exportError.ToString() });
                        readbackErrors.Add("Actual NativeLabel target export failed for label " + i + ": " + exportError);
                    }
                }
            }
            catch (Exception walkError) { readbackErrors.Add("Actual NativeLabel readback membership is unmeasured: " + walkError); }
        }
    }

    private void RequireNativeLabelCaptureCompleted()
    {
        if (capturedNativeLabelEvidence?["failure"] is { } failure)
            throw new InvalidOperationException("NativeLabel frame evidence failed: " + failure);
        if (capturedNativeLabelEvidence?["surface_readback_errors"] is JsonArray { Count: > 0 } errors)
            throw new InvalidOperationException("NativeLabel actual surface readback failed: " + errors);
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
