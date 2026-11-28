using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json.Nodes;

namespace Relic;

// Diagnostic only. No provider is constructed and no canonical field is changed.
// The actual peer is accessed on the UI thread. Its public COM Simple interface
// is marshaled to an MTA; await keeps WinUI pumping provider callbacks. Calling
// UiaNodeFromProvider on the UI thread would deadlock the existing identity read.
internal static partial class InProcessTextRangeProviderProbe
{
    [DllImport("ole32.dll", ExactSpelling = true)] private static extern int CoInitializeEx(IntPtr reserved, uint flags);
    [DllImport("ole32.dll", ExactSpelling = true)] private static extern void CoUninitialize();
    [DllImport("ole32.dll", ExactSpelling = true)] private static extern int CoMarshalInterThreadInterfaceInStream(ref Guid iid, IntPtr value, out IntPtr stream);
    [DllImport("ole32.dll", ExactSpelling = true)] private static extern int CoGetInterfaceAndReleaseStream(IntPtr stream, ref Guid iid, out IntPtr value);
    [DllImport("ole32.dll", ExactSpelling = true)] private static extern int CoReleaseMarshalData(IntPtr stream);

    internal static async Task<JsonObject> Capture(string directory, string caseId,
        IReadOnlyDictionary<DependencyObject, string> identities,
        IReadOnlyDictionary<DependencyObject, JsonObject> nodes, JsonObject winrtProbe, JsonObject observer,
        Func<TextBlock, AutomationPeer?, string, JsonObject?> frameCheckpoint)
    {
        var path = Path.Combine(directory, caseId + ".inprocess-text-range-provider-probe.json");
        using var progress = new StreamWriter(new FileStream(Path.Combine(directory, caseId + ".inprocess-text-range-provider-probe.progress.jsonl"),
            FileMode.Create, FileAccess.Write, FileShare.Read), new UTF8Encoding(false)) { AutoFlush = true };
        var owners = new JsonArray(); var selection = new JsonArray(); var errors = new JsonArray();
        var nativePathSelections = new JsonArray();
        var receipt = new JsonObject { ["contract"] = "actual-inprocess-com-text-range-diagnostic-v1", ["case_id"] = caseId,
            ["source"] = "Same retained actual TextBlock or NativePathText/peer, public COM provider vtables while independent observer holds UIA references",
            ["observer"] = observer.DeepClone(), ["started_qpc"] = Stopwatch.GetTimestamp(), ["qpc_frequency"] = Stopwatch.Frequency,
            ["selection_rule"] = "Actual current WinRT rectangle height > 0 and < 1, without name, position or expected-reference lookup",
            ["selection_scope"] = "Actual TextBlock owners sampled by TextRangeProviderProbe and separately observed actual NativePathText existing-peer WinRT providers; only observed subpixel ranges select COM reads",
            ["native_path_winrt_selection"] = nativePathSelections,
            ["selection"] = selection, ["owners"] = owners, ["errors"] = errors,
            ["winrt_file"] = caseId + ".text-range-provider-probe.json", ["external_com_file"] = caseId + ".uia.json",
            ["canonical_geometry_supplied"] = false, ["canonical_identity_supplied"] = false, ["provider_errors_resolved"] = false,
            ["create_peer_for_element_called"] = false, ["capture_completed"] = false,
            ["range_filter"] = "Actual DocumentRange, every GetVisibleRanges range and its observed TextUnit_Format subranges for selected owners" };
        void Save() => File.WriteAllText(path, receipt.ToJsonString());
        void Trace(string? ownerId, JsonObject step)
        {
            var copy = (JsonObject)step.DeepClone(); copy["owner_id"] = ownerId;
            copy["qpc"] = Stopwatch.GetTimestamp(); copy["managed_thread_id"] = Environment.CurrentManagedThreadId;
            copy["apartment_state"] = Thread.CurrentThread.GetApartmentState().ToString();
            progress.WriteLine(copy.ToJsonString());
        }
        Save();
        foreach (var (value, ownerId) in identities)
        {
            if (value is not FrameworkElement owner || (owner is not TextBlock && owner is not NativePathText)) continue;
            AutomationPeer? selectionPeer = null;
            JsonObject? pathWinrt = null;
            JsonObject[] records;
            if (owner is NativePathText nativePath)
            {
                pathWinrt = CaptureNativePathWinRt(nativePath, ownerId, step => Trace(ownerId, step), out selectionPeer);
                nativePathSelections.Add(pathWinrt); Save();
                foreach (var failure in pathWinrt["errors"]!.AsArray())
                    errors.Add(new JsonObject { ["owner_id"] = ownerId, ["source"] = "Actual NativePathText WinRT selection observation", ["error"] = failure?.DeepClone() });
                records = [pathWinrt];
            }
            else records = winrtProbe["owners"]?.AsArray().OfType<JsonObject>()
                .Where(item => item["owner_id"]?.ToString() == ownerId).ToArray() ?? [];
            var reasons = new JsonArray();
            if (records.Length == 1) CollectFractionalHeights(records[0], reasons);
            var selected = records.Length == 1 && reasons.Count != 0;
            selection.Add(new JsonObject { ["owner_id"] = ownerId, ["selected"] = selected,
                ["owner_type"] = owner.GetType().FullName,
                ["winrt_source"] = pathWinrt == null ? "TextRangeProviderProbe retained actual TextBlock" : "native_path_winrt_selection actual NativePathText existing peer",
                ["winrt_owner_record_count"] = records.Length, ["actual_fractional_height_ranges"] = reasons,
                ["reason"] = records.Length != 1 ? "No unique actual current WinRT owner receipt" : selected
                    ? "Actual WinRT provider returned a positive subpixel rectangle height" : "No observed positive subpixel rectangle height" });
            if (!selected) continue;
            var record = new JsonObject { ["owner_id"] = ownerId, ["owner_type"] = owner.GetType().FullName,
                ["status"] = "unavailable", ["started_qpc"] = Stopwatch.GetTimestamp(), ["lifecycle"] = new JsonArray() };
            if (pathWinrt != null) record["native_path_winrt_selection"] = pathWinrt.DeepClone();
            owners.Add(record); Save();
            var calls = record["lifecycle"]!.AsArray();
            void Check(string operation, int hr)
            {
                var step = AutomationIdentityNative.HResult(operation, hr); calls.Add(step); Trace(ownerId, step);
                if (hr < 0) throw new COMException(operation, hr);
            }
            void Release(IntPtr pointer, string label)
            {
                if (pointer == IntPtr.Zero) return;
                try
                {
                    var step = new JsonObject { ["api"] = "IUnknown.Release", ["owner"] = label,
                        ["pointer"] = AutomationIdentityNative.Pointer(pointer), ["remaining_references"] = Marshal.Release(pointer) };
                    calls.Add(step); Trace(ownerId, step);
                }
                catch (Exception ex) { errors.Add(new JsonObject { ["owner_id"] = ownerId, ["api"] = "Release " + label, ["error"] = ex.ToString() }); }
            }
            AutomationPeer? peer = null, events = null;
            var inspectable = IntPtr.Zero; var simple = IntPtr.Zero; var stream = IntPtr.Zero;
            var originThread = Environment.CurrentManagedThreadId; var marshaled = false;
            try
            {
                if (!owner.DispatcherQueue.HasThreadAccess) throw new InvalidOperationException("Actual owner read must start on its UI thread");
                peer = FrameworkElementAutomationPeer.FromElement(owner);
                record["peer_is_null"] = peer == null; record["peer_type"] = peer?.GetType().FullName;
                record["owner_text_before"] = InProcessTextRangeNative.Utf16(OwnerText(owner));
                if (peer == null) { record["unavailable_reason"] = "Actual owner has no existing peer"; continue; }
                if (pathWinrt != null)
                {
                    record["peer_same_object_as_winrt_selection"] = ReferenceEquals(selectionPeer, peer);
                    if (!ReferenceEquals(selectionPeer, peer)) throw new InvalidOperationException("Actual NativePathText peer changed after WinRT selection");
                }
                var sameOwner = peer is FrameworkElementAutomationPeer elementPeer && ReferenceEquals(elementPeer.Owner, owner);
                record["same_owner_object"] = sameOwner;
                if (!sameOwner) throw new InvalidOperationException("Actual peer owner differs from retained XAML object");
                events = peer.EventsSource;
                record["events_source_type"] = events?.GetType().FullName; record["events_source_is_null"] = events == null;
                record["frame_before"] = owner is TextBlock textOwner ? frameCheckpoint(textOwner, peer, "inprocess-com.before")?.DeepClone() : null;
                if (owner is NativePathText pathOwner)
                {
                    record["frame_unavailable_reason"] = "The existing TextBlock frame observer does not retain NativePathText; production snapshots are not a complete frame observer";
                    record["native_path_production_before"] = NativeCaptureNumbers.Prepare(pathOwner.CaptureProductionPathReceipt(), "inprocess native path before");
                    record["frame_continuity_proven"] = false;
                }
                record["held_identity_before"] = nodes.TryGetValue(owner, out var node)
                    ? node["automation_identity_evidence"]?.DeepClone() : null;
                inspectable = WinRT.MarshalInspectable<object>.FromManaged(peer);
                record["actual_peer_inspectable"] = AutomationIdentityNative.Pointer(inspectable);
                var iid = AutomationIdentityNative.SimpleId;
                var entry = new JsonObject(); record["public_provider_entry"] = entry;
                simple = InProcessTextRangeNative.AcquireSimpleThroughFragment(inspectable, new InProcessTextRangeNative.Api(), entry, step => Trace(ownerId, step));
                foreach (var failure in entry["errors"]!.AsArray())
                    errors.Add(new JsonObject { ["owner_id"] = ownerId, ["source"] = "Actual public provider-entry diagnostic", ["error"] = failure?.DeepClone() });
                record["origin_simple_pointer"] = AutomationIdentityNative.Pointer(simple);
                if (simple == IntPtr.Zero) throw new InvalidOperationException("The actual public Fragment-to-Simple provider route is unavailable; original QI failures retained");
                Check("CoMarshalInterThreadInterfaceInStream(Simple)", CoMarshalInterThreadInterfaceInStream(ref iid, simple, out stream));
                marshaled = true;
                if (stream == IntPtr.Zero) throw new InvalidOperationException("Simple marshal returned a null stream");
                record["stream_pointer"] = AutomationIdentityNative.Pointer(stream);
                // No UI object is touched by this worker. It owns only the
                // public marshaled proxy; STA stays pumping through this await.
                await Task.Run(() =>
                {
                    var initialized = false; var proxy = IntPtr.Zero;
                    try
                    {
                        var hr = CoInitializeEx(IntPtr.Zero, 0); initialized = hr >= 0; Check("CoInitializeEx(MTA)", hr);
                        var requested = AutomationIdentityNative.SimpleId;
                        var packet = stream;
                        try
                        {
                            hr = CoGetInterfaceAndReleaseStream(packet, ref requested, out proxy);
                            stream = IntPtr.Zero; record["stream_consumed_by_api"] = true;
                        }
                        catch
                        {
                            record["stream_consumption_unknown"] = true; record["unresolved_stream_pointer"] = AutomationIdentityNative.Pointer(packet);
                            stream = IntPtr.Zero; throw; // Never double-release unknown consumption.
                        }
                        Check("CoGetInterfaceAndReleaseStream(Simple)", hr);
                        if (proxy == IntPtr.Zero) throw new InvalidOperationException("Simple unmarshal returned null");
                        record["worker_simple_pointer"] = AutomationIdentityNative.Pointer(proxy);
                        record["native_identity"] = AutomationIdentityNative.Read(proxy, new AutomationIdentityNative.Api(), step => Trace(ownerId, step));
                        record["com"] = InProcessTextRangeNative.Read(proxy, new InProcessTextRangeNative.Api(), step => Trace(ownerId, step));
                    }
                    finally { Release(proxy, "MTA Simple proxy"); if (initialized) { CoUninitialize(); calls.Add(new JsonObject { ["api"] = "CoUninitialize", ["completed"] = true }); } }
                });
                if (!owner.DispatcherQueue.HasThreadAccess || Environment.CurrentManagedThreadId != originThread)
                    throw new InvalidOperationException("Provider diagnostic did not return to its origin apartment");
                record["status"] = record["com"]?["status"]?.DeepClone() ?? JsonValue.Create("unavailable");
                var heldIdentity = record["held_identity_before"];
                var currentIdentity = record["native_identity"];
                record["core_runtime_id_matches_held_identity"] =
                    heldIdentity?["status"]?.ToString() == "measured" && currentIdentity?["status"]?.ToString() == "measured"
                    && heldIdentity?["native"]?["core_runtime_id"]?["values"] is JsonArray heldValues
                    && currentIdentity?["core_runtime_id"]?["values"] is JsonArray currentValues
                    ? heldValues.Select(item => item!.GetValue<int>()).SequenceEqual(currentValues.Select(item => item!.GetValue<int>())) : null;
            }
            catch (Exception ex)
            {
                record["error"] = ex.ToString(); record["hresult"] = ex.HResult;
                errors.Add(new JsonObject { ["owner_id"] = ownerId, ["error"] = ex.ToString(), ["hresult"] = ex.HResult });
            }
            finally
            {
                try
                {
                    if (stream != IntPtr.Zero && Environment.CurrentManagedThreadId == originThread)
                    { if (marshaled) Check("CoReleaseMarshalData(unconsumed, origin)", CoReleaseMarshalData(stream)); }
                }
                catch (Exception ex) { record["marshal_cleanup_error"] = ex.ToString(); }
                finally { Release(stream, "unconsumed marshal stream"); Release(simple, "origin Simple QI"); Release(inspectable, "actual peer inspectable"); }
                try
                {
                    var after = FrameworkElementAutomationPeer.FromElement(owner);
                    record["peer_same_object_after"] = ReferenceEquals(peer, after);
                    record["events_source_same_object_after"] = peer != null ? ReferenceEquals(events, peer.EventsSource) : null;
                    record["owner_text_after"] = InProcessTextRangeNative.Utf16(OwnerText(owner));
                    record["frame_after"] = owner is TextBlock textOwner ? frameCheckpoint(textOwner, peer, "inprocess-com.after")?.DeepClone() : null;
                    if (owner is NativePathText pathOwner)
                        record["native_path_production_after"] = NativeCaptureNumbers.Prepare(pathOwner.CaptureProductionPathReceipt(), "inprocess native path after");
                }
                catch (Exception ex) { record["owner_recheck_error"] = ex.ToString(); }
                record["completed_qpc"] = Stopwatch.GetTimestamp();
                Trace(ownerId, new JsonObject { ["api"] = "owner", ["status"] = "completed", ["receipt"] = record.DeepClone() });
                Save(); GC.KeepAlive(events); GC.KeepAlive(peer); GC.KeepAlive(owner);
            }
        }
        receipt["capture_completed"] = true; receipt["completed_qpc"] = Stopwatch.GetTimestamp();
        receipt["selected_owner_count"] = owners.Count;
        receipt["selection_result"] = owners.Count == 0 ? "no-observed-subpixel-owner-in-TextBlock-or-NativePathText-scope" : "selected-actual-subpixel-TextBlock-or-NativePathText-owners";
        Save(); return receipt;
    }

    private static string OwnerText(FrameworkElement owner) => owner switch
    { TextBlock text => text.Text, NativePathText path => path.SourceText, _ => throw new InvalidOperationException("Unsupported actual text owner") };

    private static void CollectFractionalHeights(JsonObject owner, JsonArray reasons)
    {
        void Range(JsonObject? range, string path)
        {
            if (range?["bounding_rectangle_values"] is not JsonArray values || values.Count % 4 != 0) return;
            for (var offset = 3; offset < values.Count; offset += 4)
                if (values[offset] is JsonValue value && value.TryGetValue<double>(out var height) && height > 0 && height < 1)
                    reasons.Add(new JsonObject { ["range_path"] = path, ["rectangle_index"] = offset / 4,
                        ["actual_values"] = new JsonArray(values.Skip(offset - 3).Take(4).Select(item => item?.DeepClone()).ToArray()) });
            if (range["format_runs"] is JsonArray formats)
                for (var index = 0; index < formats.Count; index++) Range(formats[index] as JsonObject, path + ".format_runs[" + index + "]");
        }
        Range(owner["document_range"] as JsonObject, "document_range");
        if (owner["visible_ranges"] is JsonArray visible)
            for (var index = 0; index < visible.Count; index++) Range(visible[index] as JsonObject, "visible_ranges[" + index + "]");
    }
}
