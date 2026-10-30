using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Automation.Provider;
using Microsoft.UI.Xaml.Automation.Text;
using Microsoft.UI.Xaml.Controls;
using System.Diagnostics;
using System.Text;
using System.Text.Json.Nodes;

namespace Relic;

// CI-only caller-owned diagnostic. Read the real owner's WinRT provider before
// any out-of-process/native UIA screen-coordinate bridge. This is deliberately
// not a source of canonical rectangles or RuntimeIds. In AppSDK 1.6 the provider
// can return a visible range whose bounding rectangle is then ancestor-clipped;
// neither that range's presence nor IsHidden=false proves viewport visibility.
// Pinned SDK sources:
// https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/core/text/common/textadapter.cpp
// https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/core/text/common/textrangeadapter.cpp
internal sealed class TextRangeProviderProbe : IDisposable
{
    private readonly string phase;
    private readonly int originThread = Environment.CurrentManagedThreadId;
    private readonly StreamWriter progress;
    private readonly string outputPath;
    private readonly JsonArray owners = [], errors = [], contractIssues = [];
    private readonly JsonObject receipt;
    private readonly Func<TextBlock, AutomationPeer?, string, JsonObject?>? frameCheckpoint;
    private TextBlock? currentOwner;
    private AutomationPeer? currentPeer;

    private TextRangeProviderProbe(string directory, string caseId, string phase,
        Func<TextBlock, AutomationPeer?, string, JsonObject?>? frameCheckpoint)
    {
        this.phase = phase;
        this.frameCheckpoint = frameCheckpoint;
        outputPath = Path.Combine(directory, caseId + ".text-range-provider-probe.json");
        progress = new StreamWriter(new FileStream(
            Path.Combine(directory, caseId + ".text-range-provider-probe.progress.jsonl"),
            FileMode.Create, FileAccess.Write, FileShare.Read), new UTF8Encoding(false)) { AutoFlush = true };
        receipt = new JsonObject
        {
            ["source"] = "Actual retained TextBlock owner and its existing AutomationPeer WinRT ITextProvider",
            ["case_id"] = caseId, ["phase"] = phase,
            ["started_qpc"] = Stopwatch.GetTimestamp(), ["qpc_frequency"] = Stopwatch.Frequency,
            ["origin_managed_thread_id"] = originThread,
            ["origin_apartment_state"] = Thread.CurrentThread.GetApartmentState().ToString(),
            ["owner_filter"] = "Every actual TextBlock in the supplied renderIds, including offscreen/zero-area owners; no name or geometry matching",
            ["range_filter"] = "Actual DocumentRange and every range returned by GetVisibleRanges; no geometry-based exclusion",
            ["coordinate_space"] = "Unmodified WinRT provider API values; no inferred or applied client/screen conversion",
            ["metadata_modified"] = false, ["create_peer_for_element_called"] = false,
            ["canonical_geometry_supplied"] = false, ["canonical_identity_supplied"] = false,
            ["success_hresult_observable"] = false,
            ["success_hresult_reason"] = "The C# WinRT projection exposes the result or an exception, not the original successful HRESULT",
            ["capture_completed"] = false, ["owners"] = owners,
            ["errors"] = errors, ["contract_issues"] = contractIssues
        };
    }

    internal static JsonObject Capture(string directory, string caseId,
        IReadOnlyDictionary<DependencyObject, string> identities,
        string phase = "after-independent-uia-and-provider-probe",
        Func<TextBlock, AutomationPeer?, string, JsonObject?>? frameCheckpoint = null)
    {
        using var probe = new TextRangeProviderProbe(directory, caseId, phase, frameCheckpoint);
        probe.receipt["supplied_owner_count"] = identities.Count;
        probe.Save(); probe.Trace(null, "capture", "pending");
        foreach (var (value, id) in identities)
        {
            if (value is not TextBlock textBlock) continue;
            probe.CaptureOwner(textBlock, id);
        }
        probe.receipt["capture_completed"] = true;
        probe.receipt["completed_qpc"] = Stopwatch.GetTimestamp();
        probe.receipt["captured_owner_count"] = probe.owners.Count;
        probe.receipt["error_count"] = probe.errors.Count;
        probe.receipt["contract_issue_count"] = probe.contractIssues.Count;
        probe.Trace(null, "capture", "completed", new JsonObject
        {
            ["captured_owner_count"] = probe.owners.Count, ["error_count"] = probe.errors.Count,
            ["contract_issue_count"] = probe.contractIssues.Count
        });
        probe.Save();
        return probe.receipt;
    }

    private void CaptureOwner(TextBlock owner, string ownerId)
    {
        currentOwner = owner;
        currentPeer = null;
        var observed = new JsonObject
        {
            ["owner_id"] = ownerId, ["owner_type"] = owner.GetType().FullName,
            ["started_qpc"] = Stopwatch.GetTimestamp(), ["calls"] = new JsonArray(),
            ["status"] = "pending", ["runtime_id_supplied"] = false
        };
        owners.Add(observed); Trace(ownerId, "owner", "pending");
        AutomationPeer? peer = null, eventsSource = null;
        var peerRead = false; var eventsRead = false;
        var errorsBefore = errors.Count; var issuesBefore = contractIssues.Count;
        try
        {
            if (!owner.DispatcherQueue.HasThreadAccess || Environment.CurrentManagedThreadId != originThread)
                throw new InvalidOperationException("Text-range probe must remain on the actual owner's UI thread");
            TryCall(ownerId, observed, "owner state before", () => OwnerState(owner), out var before, state => state);
            observed["owner_before"] = before?.DeepClone();
            peerRead = TryCall(ownerId, observed, "FrameworkElementAutomationPeer.FromElement",
                () => FrameworkElementAutomationPeer.FromElement(owner), out var existingPeer);
            peer = existingPeer;
            currentPeer = peer;
            observed["peer_is_null"] = peerRead ? peer == null : null;
            observed["peer_type"] = peer?.GetType().FullName;
            if (!peerRead || peer == null)
            {
                observed["status"] = peerRead ? "no-existing-peer" : "peer-read-failed";
                return;
            }
            observed["peer_owner_same_object"] = peer is FrameworkElementAutomationPeer frameworkPeer
                ? ReferenceEquals(frameworkPeer.Owner, owner) : null;
            eventsRead = TryCall(ownerId, observed, "AutomationPeer.EventsSource before", () => peer.EventsSource,
                out eventsSource, source => PeerObservation(source, owner, peer));
            observed["events_source_before"] = eventsRead ? PeerObservation(eventsSource, owner, peer) : null;

            if (!TryCall(ownerId, observed, "AutomationPeer.GetPattern(Text)",
                () => peer.GetPattern(PatternInterface.Text), out var pattern,
                result => new JsonObject { ["is_null"] = result == null, ["type"] = result?.GetType().FullName,
                    ["is_text_provider"] = result is ITextProvider }))
            { observed["status"] = "pattern-read-failed"; return; }
            if (pattern is not ITextProvider provider)
            { observed["status"] = "no-text-provider"; return; }

            TryCall(ownerId, observed, "ITextProvider.SupportedTextSelection", () => provider.SupportedTextSelection,
                out _, result => JsonValue.Create(result.ToString()));
            var documentRead = TryCall(ownerId, observed, "ITextProvider.DocumentRange", () => provider.DocumentRange,
                out var document, result => new JsonObject { ["is_null"] = result == null, ["type"] = result?.GetType().FullName });
            string? documentBefore = null;
            if (documentRead && document != null)
            {
                TryCall(ownerId, observed, "DocumentRange.GetText(-1) before", () => document.GetText(-1),
                    out documentBefore, TextValue);
                observed["document_text_before"] = TextValue(documentBefore);
                observed["document_range"] = CaptureRange(ownerId, "document", document, document, documentBefore);
            }
            else if (documentRead) Issue(ownerId, "ITextProvider.DocumentRange", "Provider returned null", observed);

            var visible = new JsonArray(); observed["visible_ranges"] = visible;
            if (TryCall(ownerId, observed, "ITextProvider.GetVisibleRanges", () => provider.GetVisibleRanges(),
                out var ranges, result => new JsonObject { ["is_null"] = result == null, ["length"] = result?.Length }))
            {
                if (ranges == null) Issue(ownerId, "ITextProvider.GetVisibleRanges", "Provider returned null rather than an array", observed);
                else for (var index = 0; index < ranges.Length; index++)
                    visible.Add(CaptureRange(ownerId, "visible-" + index, ranges[index], document, documentBefore));
            }
            if (documentRead && document != null
                && TryCall(ownerId, observed, "DocumentRange.GetText(-1) after", () => document.GetText(-1), out var documentAfter, TextValue))
            {
                observed["document_text_after"] = TextValue(documentAfter);
                observed["document_text_same_before_after"] = documentBefore != null && documentAfter != null
                    ? string.Equals(documentBefore, documentAfter, StringComparison.Ordinal) : null;
            }
            observed["status"] = "observed";
            GC.KeepAlive(document); GC.KeepAlive(provider); GC.KeepAlive(pattern);
        }
        catch (Exception ex) { Error(ownerId, "observe owner text provider", ex, observed); observed["status"] = "failed"; }
        finally
        {
            if (TryCall(ownerId, observed, "owner state after", () => OwnerState(owner), out var after, state => state))
            {
                observed["owner_after"] = after?.DeepClone();
                observed["owner_text_same_before_after"] = observed["owner_before"]?["text"] is JsonObject beforeText
                    && after?["text"] is JsonObject afterText
                    ? beforeText["utf16_le_base64"]?.ToString() == afterText["utf16_le_base64"]?.ToString() : null;
            }
            if (TryCall(ownerId, observed, "FrameworkElementAutomationPeer.FromElement after",
                () => FrameworkElementAutomationPeer.FromElement(owner), out var peerAfter))
            {
                observed["peer_same_object_after"] = peerRead ? ReferenceEquals(peerAfter, peer) : null;
                observed["peer_owner_same_object_after"] = peerAfter is FrameworkElementAutomationPeer elementPeer
                    ? ReferenceEquals(elementPeer.Owner, owner) : null;
            }
            if (peer != null && TryCall(ownerId, observed, "AutomationPeer.EventsSource after", () => peer.EventsSource,
                out var eventsAfter, source => PeerObservation(source, owner, peer)))
            {
                observed["events_source_after"] = PeerObservation(eventsAfter, owner, peer);
                observed["events_source_same_object_after"] = eventsRead ? ReferenceEquals(eventsAfter, eventsSource) : null;
            }
            observed["error_count"] = errors.Count - errorsBefore;
            observed["contract_issue_count"] = contractIssues.Count - issuesBefore;
            observed["completed_qpc"] = Stopwatch.GetTimestamp();
            // Each completed owner is durable in the AutoFlush journal even if
            // a later provider call hangs or crashes the capture process.
            Trace(ownerId, "owner", "completed", observed);
            GC.KeepAlive(peer); GC.KeepAlive(eventsSource); GC.KeepAlive(owner);
        }
    }

    private JsonObject CaptureRange(string ownerId, string rangeId, ITextRangeProvider? range,
        ITextRangeProvider? document, string? documentText)
    {
        var result = new JsonObject
        {
            ["range_id"] = rangeId, ["type"] = range?.GetType().FullName, ["is_null"] = range == null,
            ["started_qpc"] = Stopwatch.GetTimestamp(), ["calls"] = new JsonArray(),
            ["endpoint_source"] = "DocumentRange.Clone + MoveEndpointByRange + CompareEndpoints + actual prefix GetText(-1) UTF16 lengths",
            ["canonical_geometry_supplied"] = false
        };
        if (range == null)
        { Issue(ownerId, rangeId, "Provider returned a null range", result); return result; }
        TryCall(ownerId, result, rangeId + ".GetText(-1)", () => range.GetText(-1), out var text, TextValue);
        result["text"] = TextValue(text);
        result["frame_before_rectangles"] = ObserveFrame(rangeId + ".before_rectangles");
        if (TryCall(ownerId, result, rangeId + ".GetBoundingRectangles", () =>
            { range.GetBoundingRectangles(out var values); return values; }, out var rectangles, DoubleValues))
        {
            result["bounding_rectangle_values"] = DoubleValues(rectangles);
            result["bounding_rectangle_value_bits_hex"] = rectangles == null ? null : new JsonArray(
                rectangles.Select(value => (JsonNode?)JsonValue.Create(
                    unchecked((ulong)BitConverter.DoubleToInt64Bits(value)).ToString("X16"))).ToArray());
            result["rectangle_value_count"] = rectangles?.Length;
            result["rectangle_count"] = rectangles != null && rectangles.Length % 4 == 0 ? rectangles.Length / 4 : null;
            result["all_rectangle_values_finite"] = rectangles?.All(double.IsFinite);
            if (rectangles == null || rectangles.Length % 4 != 0)
                Issue(ownerId, rangeId + ".GetBoundingRectangles", "Returned array is null or is not a sequence of four-value rectangles", result);
            // Keep zero/negative dimensions and all IEEE754 values verbatim.
            // They remain diagnostic observations, never inferred hidden text.
        }
        result["frame_after_rectangles"] = ObserveFrame(rangeId + ".after_rectangles");
        if (document != null)
        {
            Compare(ownerId, result, "start_to_document_start", range, TextPatternRangeEndpoint.Start, document, TextPatternRangeEndpoint.Start);
            Compare(ownerId, result, "end_to_document_end", range, TextPatternRangeEndpoint.End, document, TextPatternRangeEndpoint.End);
            Compare(ownerId, result, "start_to_own_end", range, TextPatternRangeEndpoint.Start, range, TextPatternRangeEndpoint.End);
            var start = Endpoint(ownerId, rangeId, range, document, TextPatternRangeEndpoint.Start);
            var end = Endpoint(ownerId, rangeId, range, document, TextPatternRangeEndpoint.End);
            result["start"] = start; result["end"] = end;
            if (start["verified_prefix_utf16_length"] is JsonValue startValue && end["verified_prefix_utf16_length"] is JsonValue endValue
                && startValue.TryGetValue<int>(out var startOffset) && endValue.TryGetValue<int>(out var endOffset)
                && documentText != null && text != null)
            {
                var within = startOffset >= 0 && endOffset >= startOffset && endOffset <= documentText.Length;
                result["offsets_within_document_snapshot"] = within;
                result["text_matches_document_snapshot_slice"] = within
                    ? string.Equals(documentText.Substring(startOffset, endOffset - startOffset), text, StringComparison.Ordinal) : null;
            }
        }
        result["completed_qpc"] = Stopwatch.GetTimestamp();
        Trace(ownerId, rangeId, "completed", result);
        return result;
    }

    private JsonObject? ObserveFrame(string stage)
    {
        if (currentOwner == null || frameCheckpoint == null) return null;
        try { return frameCheckpoint(currentOwner, currentPeer, stage); }
        catch (Exception ex)
        {
            errors.Add(new JsonObject { ["source"] = "frame_checkpoint", ["stage"] = stage, ["error"] = ex.ToString() });
            return new JsonObject { ["stage"] = stage, ["error"] = ex.ToString(), ["continuity_proven"] = false };
        }
    }

    private JsonObject Endpoint(string ownerId, string rangeId,
        ITextRangeProvider range, ITextRangeProvider document, TextPatternRangeEndpoint endpoint)
    {
        var target = new JsonObject { ["endpoint"] = endpoint.ToString(), ["calls"] = new JsonArray() };
        var label = rangeId + ".endpoint-" + endpoint;
        if (!TryCall(ownerId, target, label + ".DocumentRange.Clone", () => document.Clone(), out var prefix)
            || prefix == null) return target;
        if (!TryAction(ownerId, target, label + ".MoveEndpointByRange(End,range," + endpoint + ")",
            () => prefix.MoveEndpointByRange(TextPatternRangeEndpoint.End, range, endpoint))) return target;
        var startAligned = Compare(ownerId, target, "prefix_start_to_document_start", prefix, TextPatternRangeEndpoint.Start, document, TextPatternRangeEndpoint.Start);
        var endAligned = Compare(ownerId, target, "prefix_end_to_range_endpoint", prefix, TextPatternRangeEndpoint.End, range, endpoint);
        if (TryCall(ownerId, target, label + ".prefix.GetText(-1)", () => prefix.GetText(-1), out var prefixText, TextValue))
        {
            target["actual_prefix_text"] = TextValue(prefixText);
            target["verified_prefix_utf16_length"] = startAligned == 0 && endAligned == 0 && prefixText != null ? prefixText.Length : null;
        }
        GC.KeepAlive(prefix);
        return target;
    }

    private int? Compare(string ownerId, JsonObject target, string label, ITextRangeProvider left,
        TextPatternRangeEndpoint leftEnd, ITextRangeProvider right, TextPatternRangeEndpoint rightEnd)
    {
        if (!TryCall(ownerId, target, label + ".CompareEndpoints(" + leftEnd + ",other," + rightEnd + ")",
            () => left.CompareEndpoints(leftEnd, right, rightEnd), out var compared, value => JsonValue.Create(value))) return null;
        target[label] = compared; // Sign/equality only, never a character offset.
        return compared;
    }

    private bool TryAction(string ownerId, JsonObject target, string api, Action action)
        => TryCall<object?>(ownerId, target, api, () => { action(); return null; }, out _);

    private bool TryCall<T>(string ownerId, JsonObject target, string api, Func<T> read, out T value,
        Func<T, JsonNode?>? encode = null)
    {
        value = default!;
        var call = new JsonObject { ["api"] = api, ["started_qpc"] = Stopwatch.GetTimestamp(),
            ["managed_thread_id"] = Environment.CurrentManagedThreadId, ["status"] = "pending", ["hresult"] = null };
        target["calls"]!.AsArray().Add(call); Trace(ownerId, api, "pending");
        try
        {
            value = read(); call["status"] = "returned"; call["returned_normally"] = true;
            call["successful_hresult_not_exposed_by_projection"] = true;
            if (encode != null) call["returned_value"] = encode(value)?.DeepClone();
            return true;
        }
        catch (Exception ex)
        {
            Error(ownerId, api, ex, call); call["status"] = "failed";
            call["returned_normally"] = false; call["hresult"] = ex.HResult;
            call["hresult_hex"] = "0x" + unchecked((uint)ex.HResult).ToString("X8");
            return false;
        }
        finally { call["completed_qpc"] = Stopwatch.GetTimestamp(); Trace(ownerId, api, call["status"]!.ToString(), call); }
    }

    private static JsonObject OwnerState(TextBlock owner)
    {
        var point = owner.TransformToVisual(null).TransformPoint(new Windows.Foundation.Point(0, 0));
        return new JsonObject
        {
            ["qpc"] = Stopwatch.GetTimestamp(), ["text"] = TextValue(owner.Text),
            ["is_loaded"] = owner.IsLoaded, ["visibility"] = owner.Visibility.ToString(),
            ["actual_width"] = Number(owner.ActualWidth), ["actual_height"] = Number(owner.ActualHeight),
            ["opacity"] = Number(owner.Opacity), ["root_origin_x"] = Number(point.X), ["root_origin_y"] = Number(point.Y),
            ["root_origin_source"] = "Actual owner.TransformToVisual(null).TransformPoint(0,0)",
            ["content_start_offset"] = owner.ContentStart.Offset, ["content_end_offset"] = owner.ContentEnd.Offset,
            ["is_text_trimmed"] = owner.IsTextTrimmed, ["text_trimming"] = owner.TextTrimming.ToString(),
            ["text_wrapping"] = owner.TextWrapping.ToString(), ["line_height"] = Number(owner.LineHeight)
        };
    }

    private static JsonObject PeerObservation(AutomationPeer? peer, TextBlock owner, AutomationPeer source)
        => new() { ["is_null"] = peer == null, ["type"] = peer?.GetType().FullName,
            ["same_object_as_observed_peer"] = ReferenceEquals(peer, source),
            ["owner_same_object"] = peer is FrameworkElementAutomationPeer framework ? ReferenceEquals(framework.Owner, owner) : null };

    private static JsonNode? TextValue(string? value)
    {
        if (value == null) return null;
        // Preserve every UTF16 code unit, including an unpaired surrogate that
        // the JSON string encoder may replace. Do not use encoder fallbacks.
        var bytes = new byte[value.Length * 2];
        for (var index = 0; index < value.Length; index++)
        { bytes[index * 2] = (byte)value[index]; bytes[index * 2 + 1] = (byte)(value[index] >> 8); }
        return new JsonObject { ["value"] = value, ["utf16_length"] = value.Length,
            ["utf16_le_base64"] = Convert.ToBase64String(bytes) };
    }

    private static JsonNode Number(double value) => double.IsFinite(value) ? JsonValue.Create(value)!
        : new JsonObject { ["ieee754"] = double.IsNaN(value) ? "NaN" : double.IsPositiveInfinity(value) ? "+Infinity" : "-Infinity",
            ["bits_hex"] = unchecked((ulong)BitConverter.DoubleToInt64Bits(value)).ToString("X16") };

    private static JsonNode? DoubleValues(double[]? values)
        => values == null ? null : new JsonArray(values.Select(Number).ToArray());

    private void Error(string ownerId, string api, Exception ex, JsonObject? target = null)
    {
        var failure = new JsonObject { ["owner_id"] = ownerId, ["api"] = api, ["qpc"] = Stopwatch.GetTimestamp(),
            ["exception_type"] = ex.GetType().FullName, ["hresult"] = ex.HResult,
            ["hresult_hex"] = "0x" + unchecked((uint)ex.HResult).ToString("X8"), ["error"] = ex.ToString() };
        errors.Add(failure.DeepClone());
        if (target != null) target["error"] = failure;
        Console.Error.WriteLine("TextRangeProviderProbe " + ownerId + " " + api + ": " + ex);
    }

    private void Issue(string ownerId, string api, string message, JsonObject target)
    {
        var issue = new JsonObject { ["owner_id"] = ownerId, ["api"] = api, ["message"] = message,
            ["qpc"] = Stopwatch.GetTimestamp(), ["hresult"] = null };
        contractIssues.Add(issue.DeepClone()); target["contract_issue"] = issue;
        Trace(ownerId, api, "contract-issue", issue);
    }

    private void Trace(string? ownerId, string api, string status, JsonNode? evidence = null)
    {
        try { progress.WriteLine(new JsonObject { ["qpc"] = Stopwatch.GetTimestamp(), ["phase"] = phase,
            ["owner_id"] = ownerId, ["api"] = api, ["status"] = status,
            ["managed_thread_id"] = Environment.CurrentManagedThreadId, ["evidence"] = evidence?.DeepClone() }.ToJsonString()); }
        catch (Exception ex) { Error(ownerId ?? "capture", "text range probe progress write", ex); }
    }

    private void Save()
    {
        try { File.WriteAllText(outputPath, receipt.ToJsonString(), new UTF8Encoding(false)); }
        catch (Exception ex) { Error("capture", "text range probe snapshot write", ex); }
    }

    public void Dispose() => progress.Dispose();
}
