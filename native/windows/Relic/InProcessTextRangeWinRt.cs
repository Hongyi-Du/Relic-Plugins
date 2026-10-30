using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Automation.Provider;
using Microsoft.UI.Xaml.Automation.Text;
using System.Diagnostics;
using System.Text.Json.Nodes;

namespace Relic;

internal static partial class InProcessTextRangeProviderProbe
{
    // This observes the actual custom provider. It does not construct a
    // TextBlock or use a XAML element/clip rectangle as a text-range rectangle.
    private static JsonObject CaptureNativePathWinRt(NativePathText owner, string ownerId,
        Action<JsonObject> progress, out AutomationPeer? actualPeer)
    {
        var calls = new JsonArray(); var errors = new JsonArray();
        var receipt = new JsonObject
        {
            ["owner_id"] = ownerId, ["owner_type"] = owner.GetType().FullName,
            ["source"] = "Actual retained NativePathText and its existing AutomationPeer WinRT ITextProvider",
            ["status"] = "unavailable", ["started_qpc"] = Stopwatch.GetTimestamp(),
            ["calls"] = calls, ["errors"] = errors,
            ["coordinate_space"] = "Unmodified actual NativePathText ITextRangeProvider.GetBoundingRectangles values; this production provider returns screen-coordinate doubles",
            ["canonical_geometry_supplied"] = false, ["provider_errors_resolved"] = false,
            ["frame_continuity_proven"] = false,
            ["frame_unavailable_reason"] = "NativePathText is not registered with the existing TextBlock frame observer"
        };
        T Read<T>(string api, Func<T> action, Func<T, JsonNode?>? value = null)
        {
            var call = new JsonObject { ["api"] = api, ["started_qpc"] = Stopwatch.GetTimestamp(),
                ["managed_thread_id"] = Environment.CurrentManagedThreadId };
            calls.Add(call); progress(new JsonObject { ["api"] = api, ["status"] = "pending" });
            try
            {
                var result = action(); call["status"] = "returned";
                call["successful_hresult_not_exposed_by_projection"] = true;
                if (value != null) call["returned_value"] = value(result);
                return result;
            }
            catch (Exception error)
            {
                call["status"] = "failed"; call["hresult"] = error.HResult; call["error"] = error.ToString();
                errors.Add(new JsonObject { ["api"] = api, ["hresult"] = error.HResult, ["error"] = error.ToString() });
                throw;
            }
            finally { call["completed_qpc"] = Stopwatch.GetTimestamp(); progress((JsonObject)call.DeepClone()); }
        }
        void Action(string api, System.Action action) => Read(api, () => { action(); return true; });
        JsonObject Endpoint(ITextRangeProvider range, ITextRangeProvider document, TextPatternRangeEndpoint endpoint, string path)
        {
            var value = new JsonObject { ["endpoint"] = endpoint.ToString(),
                ["source"] = "Actual document clone, MoveEndpointByRange, CompareEndpoints and prefix UTF16 length" };
            var prefix = Read(path + ".DocumentRange.Clone", document.Clone);
            if (prefix == null) throw new InvalidOperationException("Actual NativePathText document Clone returned null");
            Action(path + ".MoveEndpointByRange", () => prefix.MoveEndpointByRange(TextPatternRangeEndpoint.End, range, endpoint));
            var start = Read(path + ".CompareStart", () => prefix.CompareEndpoints(TextPatternRangeEndpoint.Start, document, TextPatternRangeEndpoint.Start), x => JsonValue.Create(x));
            var end = Read(path + ".CompareEnd", () => prefix.CompareEndpoints(TextPatternRangeEndpoint.End, range, endpoint), x => JsonValue.Create(x));
            var collapsed = Read(path + ".ComparePrefixStartToEnd", () => prefix.CompareEndpoints(TextPatternRangeEndpoint.Start, prefix, TextPatternRangeEndpoint.End), x => JsonValue.Create(x));
            var text = Read(path + ".prefix.GetText(-1)", () => prefix.GetText(-1), InProcessTextRangeNative.Utf16);
            value["start_compare"] = start; value["end_compare"] = end; value["prefix_start_to_end_compare"] = collapsed;
            value["text"] = InProcessTextRangeNative.Utf16(text);
            value["verified_prefix_utf16_length"] = start == 0 && end == 0 && text != null ? text.Length : null;
            GC.KeepAlive(prefix); return value;
        }
        JsonObject Range(ITextRangeProvider? range, ITextRangeProvider document, string? documentText, string path)
        {
            var value = new JsonObject { ["range_path"] = path, ["is_null"] = range == null,
                ["range_type"] = range?.GetType().FullName, ["started_qpc"] = Stopwatch.GetTimestamp() };
            try
            {
                if (range == null) throw new InvalidOperationException("Actual NativePathText range is null");
                var text = Read(path + ".GetText(-1)", () => range.GetText(-1), InProcessTextRangeNative.Utf16);
                value["text"] = InProcessTextRangeNative.Utf16(text);
                var values = Read(path + ".GetBoundingRectangles", () => { range.GetBoundingRectangles(out var measured); return measured; });
                value["bounding_rectangle_values"] = values == null ? null : new JsonArray(values.Select(number =>
                    double.IsFinite(number) ? (JsonNode?)JsonValue.Create(number) : null).ToArray());
                value["bounding_rectangle_value_bits_hex"] = values == null ? null : new JsonArray(values.Select(number =>
                    (JsonNode?)JsonValue.Create(BitConverter.DoubleToUInt64Bits(number).ToString("X16"))).ToArray());
                value["all_rectangle_values_finite"] = values?.All(double.IsFinite);
                value["rectangle_value_count"] = values?.Length;
                if (values == null || values.Length % 4 != 0 || !values.All(double.IsFinite))
                    throw new InvalidOperationException("Actual NativePathText rectangle values are null, malformed or nonfinite");
                var start = Endpoint(range, document, TextPatternRangeEndpoint.Start, path + ".start");
                var end = Endpoint(range, document, TextPatternRangeEndpoint.End, path + ".end");
                value["start"] = start; value["end"] = end;
                if (start["verified_prefix_utf16_length"] is JsonValue sv && end["verified_prefix_utf16_length"] is JsonValue ev
                    && sv.TryGetValue<int>(out var s) && ev.TryGetValue<int>(out var e) && documentText != null && text != null)
                {
                    var within = s >= 0 && e >= s && e <= documentText.Length;
                    value["offsets_within_document_snapshot"] = within;
                    value["text_matches_document_snapshot_slice"] = within && string.Equals(documentText.Substring(s, e - s), text, StringComparison.Ordinal);
                }
            }
            catch (Exception error)
            { value["error"] = error.ToString(); errors.Add(new JsonObject { ["range_path"] = path, ["hresult"] = error.HResult, ["error"] = error.ToString() }); }
            finally { value["completed_qpc"] = Stopwatch.GetTimestamp(); progress((JsonObject)value.DeepClone()); GC.KeepAlive(range); }
            return value;
        }
        actualPeer = null;
        AutomationPeer? events = null;
        try
        {
            if (!owner.DispatcherQueue.HasThreadAccess) throw new InvalidOperationException("NativePathText must be observed on its actual UI thread");
            receipt["owner_text_before"] = InProcessTextRangeNative.Utf16(owner.SourceText);
            receipt["production_before"] = NativeCaptureNumbers.Prepare(owner.CaptureProductionPathReceipt(), "native path WinRT selection before");
            actualPeer = Read("FrameworkElementAutomationPeer.FromElement", () => FrameworkElementAutomationPeer.FromElement(owner));
            receipt["peer_is_null"] = actualPeer == null; receipt["peer_type"] = actualPeer?.GetType().FullName;
            if (actualPeer == null) { receipt["unavailable_reason"] = "Actual NativePathText has no existing peer"; return receipt; }
            var peer = actualPeer;
            var sameOwner = peer is FrameworkElementAutomationPeer elementPeer && ReferenceEquals(elementPeer.Owner, owner);
            receipt["peer_owner_same_object"] = sameOwner;
            if (!sameOwner) throw new InvalidOperationException("Actual NativePathText peer belongs to a different owner");
            events = peer.EventsSource;
            receipt["events_source_is_null"] = events == null; receipt["events_source_type"] = events?.GetType().FullName;
            var pattern = Read("AutomationPeer.GetPattern(Text)", () => peer.GetPattern(PatternInterface.Text));
            receipt["pattern_type"] = pattern?.GetType().FullName; receipt["pattern_same_as_peer"] = ReferenceEquals(pattern, peer);
            if (pattern is not ITextProvider provider) { receipt["unavailable_reason"] = "Actual existing peer exposes no WinRT ITextProvider"; return receipt; }
            var document = Read("ITextProvider.DocumentRange", () => provider.DocumentRange);
            if (document == null) throw new InvalidOperationException("Actual NativePathText DocumentRange is null");
            var before = Read("document-before.GetText(-1)", () => document.GetText(-1), InProcessTextRangeNative.Utf16);
            receipt["document_text_before"] = InProcessTextRangeNative.Utf16(before);
            receipt["document_range"] = Range(document, document, before, "document_range");
            var ranges = Read("ITextProvider.GetVisibleRanges", provider.GetVisibleRanges);
            if (ranges == null) throw new InvalidOperationException("Actual NativePathText GetVisibleRanges returned null");
            var visible = new JsonArray(); receipt["visible_ranges"] = visible;
            for (var index = 0; index < ranges.Length; index++) visible.Add(Range(ranges[index], document, before, "visible_ranges[" + index + "]"));
            var after = Read("document-after.GetText(-1)", () => document.GetText(-1), InProcessTextRangeNative.Utf16);
            receipt["document_text_after"] = InProcessTextRangeNative.Utf16(after);
            receipt["document_text_same_before_after"] = before != null && after != null ? string.Equals(before, after, StringComparison.Ordinal) : null;
            receipt["status"] = errors.Count == 0 ? "observed" : "observed-with-errors";
            GC.KeepAlive(provider); GC.KeepAlive(document); GC.KeepAlive(ranges);
        }
        catch (Exception error)
        { receipt["error"] = error.ToString(); errors.Add(new JsonObject { ["hresult"] = error.HResult, ["error"] = error.ToString() }); }
        finally
        {
            try
            {
                receipt["owner_text_after"] = InProcessTextRangeNative.Utf16(owner.SourceText);
                receipt["peer_same_object_after"] = ReferenceEquals(actualPeer, FrameworkElementAutomationPeer.FromElement(owner));
                receipt["events_source_same_object_after"] = actualPeer != null ? ReferenceEquals(events, actualPeer.EventsSource) : null;
                receipt["production_after"] = NativeCaptureNumbers.Prepare(owner.CaptureProductionPathReceipt(), "native path WinRT selection after");
            }
            catch (Exception error) { errors.Add(new JsonObject { ["api"] = "NativePathText recheck", ["error"] = error.ToString() }); }
            receipt["completed_qpc"] = Stopwatch.GetTimestamp();
            GC.KeepAlive(actualPeer); GC.KeepAlive(events); GC.KeepAlive(owner);
        }
        return receipt;
    }
}
