using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json.Nodes;

namespace Relic;

// CI diagnostic only. This never supplies a canonical RuntimeId or changes an
// owner/peer. The two public pointer exits are observed before and after the
// normal independent UIA walk, keeping the original managed objects alive.
internal sealed class AutomationProviderProbe : IDisposable
{
    private sealed class Owner(FrameworkElement element, string id)
    {
        internal readonly FrameworkElement Element = element;
        internal readonly string Id = id;
        internal AutomationPeer? Peer;
        internal AutomationPeer? EventsSource;
        internal bool BeforePeerObserved, BeforeEventsSourceObserved;
        internal readonly JsonObject Receipt = new() { ["owner_id"] = id };
    }

    private static readonly Guid UnknownId = new("00000000-0000-0000-c000-000000000046");
    private readonly List<Owner> owners = [];
    private readonly int originThread = Environment.CurrentManagedThreadId;
    private readonly string outputPath;
    private readonly StreamWriter progress;
    private readonly JsonArray failures = [], phases = [], ownerReceipts = [];
    private readonly JsonObject receipt;
    private bool afterCaptured, disposed;

    private AutomationProviderProbe(string directory, string caseId)
    {
        outputPath = Path.Combine(directory, caseId + ".provider-probe.json");
        progress = new StreamWriter(new FileStream(Path.Combine(directory, caseId + ".provider-probe.progress.jsonl"),
            FileMode.Create, FileAccess.Write, FileShare.Read), new UTF8Encoding(false)) { AutoFlush = true };
        receipt = new JsonObject
        {
            ["source"] = "Actual retained AutomationPeer public pointer exits before/after independent UIA walk",
            ["case_id"] = caseId, ["qpc_frequency"] = Stopwatch.Frequency,
            ["origin_managed_thread_id"] = originThread,
            ["origin_apartment_state"] = Thread.CurrentThread.GetApartmentState().ToString(),
            ["metadata_modified"] = false, ["canonical_identity_supplied"] = false,
            ["queried_iids"] = new JsonArray(UnknownId.ToString(), AutomationIdentityNative.FragmentId.ToString()),
            ["scope"] = "Diagnostic QI HRESULTs and actual COM pointers only; no RuntimeId assembly, private-interface search or inferred identity",
            ["phases"] = phases, ["owners"] = ownerReceipts, ["failures"] = failures
        };
    }

    internal static AutomationProviderProbe Begin(string directory, string caseId,
        IReadOnlyDictionary<DependencyObject, string> identities)
    {
        var probe = new AutomationProviderProbe(directory, caseId);
        foreach (var (value, id) in identities)
            if (value is FrameworkElement element)
            {
                var owner = new Owner(element, id);
                probe.owners.Add(owner); probe.ownerReceipts.Add(owner.Receipt);
            }
        probe.CapturePhase("before-independent-uia", before: true);
        return probe;
    }

    internal void CaptureAfter()
    {
        if (disposed || afterCaptured) throw new InvalidOperationException("Provider probe after-phase already completed or disposed");
        afterCaptured = true;
        CapturePhase("after-independent-uia", before: false);
    }

    private void Failure(string api, Exception ex, JsonObject? target = null)
    {
        var failure = new JsonObject { ["api"] = api, ["exception_type"] = ex.GetType().FullName,
            ["hresult"] = ex.HResult, ["hresult_hex"] = "0x" + unchecked((uint)ex.HResult).ToString("X8"),
            ["error"] = ex.ToString() };
        failures.Add(failure.DeepClone());
        if (target != null) target["error"] = failure;
    }

    private void Trace(string phase, string? ownerId, string api, string status, JsonNode? evidence = null)
    {
        try
        {
            progress.WriteLine(new JsonObject { ["qpc"] = Stopwatch.GetTimestamp(), ["phase"] = phase,
                ["owner_id"] = ownerId, ["api"] = api, ["status"] = status,
                ["managed_thread_id"] = Environment.CurrentManagedThreadId,
                ["evidence"] = evidence?.DeepClone() }.ToJsonString());
        }
        catch (Exception ex) { Failure("provider probe progress write", ex); }
    }

    private void Save()
    {
        try { File.WriteAllText(outputPath, receipt.ToJsonString(), new UTF8Encoding(false)); }
        catch (Exception ex) { Failure("provider probe snapshot write", ex); }
    }

    private void CapturePhase(string phase, bool before)
    {
        var state = new JsonObject { ["phase"] = phase, ["started_qpc"] = Stopwatch.GetTimestamp(), ["completed"] = false };
        phases.Add(state); Save(); Trace(phase, null, "phase", "pending");
        if (Environment.CurrentManagedThreadId != originThread)
        {
            Failure("provider probe origin apartment", new InvalidOperationException("Probe left the original UI thread"), state);
            Save(); return;
        }
        foreach (var owner in owners)
        {
            var observed = new JsonObject { ["started_qpc"] = Stopwatch.GetTimestamp(),
                ["owner_type"] = owner.Element.GetType().FullName };
            owner.Receipt[before ? "before" : "after"] = observed;
            Trace(phase, owner.Id, "FrameworkElementAutomationPeer.FromElement", "pending");
            try
            {
                var current = FrameworkElementAutomationPeer.FromElement(owner.Element);
                observed["observed_peer_is_null"] = current == null;
                observed["observed_peer_type"] = current?.GetType().FullName;
                observed["observed_peer_owner_same_object"] = current is FrameworkElementAutomationPeer currentElementPeer
                    ? ReferenceEquals(currentElementPeer.Owner, owner.Element) : null;
                Trace(phase, owner.Id, "FrameworkElementAutomationPeer.FromElement", "completed");
                if (before) { owner.Peer = current; owner.BeforePeerObserved = true; }
                else observed["observed_peer_same_object_as_before"] = owner.BeforePeerObserved ? ReferenceEquals(current, owner.Peer) : null;

                var eventsSource = current?.EventsSource;
                observed["observed_events_source_is_null"] = eventsSource == null;
                observed["observed_events_source_type"] = eventsSource?.GetType().FullName;
                if (before) { owner.EventsSource = eventsSource; owner.BeforeEventsSourceObserved = true; }
                else observed["observed_events_source_same_object_as_before"] = owner.BeforeEventsSourceObserved
                    ? ReferenceEquals(eventsSource, owner.EventsSource) : null;

                // Always query the retained original peer. A peer that appears
                // only after UIA traversal is reported, not substituted for it.
                var retained = owner.Peer;
                observed["query_target"] = "Original peer retained from before-independent-uia";
                observed["retained_peer_is_null"] = retained == null;
                if (retained != null)
                {
                    observed["retained_peer_owner_same_object"] = retained is FrameworkElementAutomationPeer retainedElementPeer
                        ? ReferenceEquals(retainedElementPeer.Owner, owner.Element) : null;
                    observed["retained_events_source_same_object_as_before"] = owner.BeforeEventsSourceObserved
                        ? ReferenceEquals(retained.EventsSource, owner.EventsSource) : null;
                    ProbePointers(phase, owner.Id, retained, observed);
                }
                observed["completed"] = true;
            }
            catch (Exception ex) { observed["completed"] = false; Failure("observe retained production peer", ex, observed); }
            observed["completed_qpc"] = Stopwatch.GetTimestamp();
            Trace(phase, owner.Id, "owner", "completed", observed);
        }
        state["completed_qpc"] = Stopwatch.GetTimestamp(); state["completed"] = true;
        Trace(phase, null, "phase", "completed", state); Save();
    }

    private void ProbePointers(string phase, string ownerId, AutomationPeer peer, JsonObject observed)
    {
        observed["peer_is_iwinrtobject"] = peer is WinRT.IWinRTObject;
        var fromManaged = new JsonObject(); observed["from_managed"] = fromManaged;
        ProbePointer(phase, ownerId, "MarshalInspectable<object>.FromManaged(actual retained peer)",
            () => WinRT.MarshalInspectable<object>.FromManaged(peer), fromManaged);

        var native = new JsonObject(); observed["native_object"] = native;
        WinRT.IObjectReference? reference = null;
        ProbePointer(phase, ownerId, "IWinRTObject.NativeObject.GetRef(actual retained peer)", () =>
        {
            if (peer is not WinRT.IWinRTObject winrt) throw new InvalidOperationException("Actual peer does not implement IWinRTObject");
            native["has_unwrappable_native_object"] = winrt.HasUnwrappableNativeObject;
            reference = winrt.NativeObject;
            native["object_reference_type"] = reference.GetType().FullName;
            native["borrowed_this_ptr"] = AutomationIdentityNative.Pointer(reference.ThisPtr);
            return reference.GetRef(); // Own this one AddRef; never Dispose the peer's NativeObject.
        }, native);
        // Pointer equality is an observation only. It is not proof that QI took
        // the same inner/outer aggregation route or that a UIA identity exists.
        observed["same_iunknown_pointer"] = SuccessfulUnknown(fromManaged) is string left
            && SuccessfulUnknown(native) is string right ? left == right : null;
        GC.KeepAlive(reference); GC.KeepAlive(peer);
    }

    private static string? SuccessfulUnknown(JsonObject exit)
    {
        var query = exit["queries"]?.AsArray().OfType<JsonObject>().FirstOrDefault(item => item["iid"]?.ToString() == UnknownId.ToString());
        if (query == null) return null;
        var hr = query["hresult"]?.GetValue<int>();
        return hr.HasValue && hr.Value >= 0 && query["returned_nonnull"]?.GetValue<bool>() == true
            ? query["pointer"]?.ToString() : null;
    }

    private void ProbePointer(string phase, string ownerId, string api, Func<IntPtr> acquire, JsonObject target)
    {
        var pointer = IntPtr.Zero;
        target["api"] = api; target["queries"] = new JsonArray(); target["acquired"] = false;
        Trace(phase, ownerId, api, "pending");
        try
        {
            pointer = acquire(); target["pointer"] = AutomationIdentityNative.Pointer(pointer);
            target["acquired"] = pointer != IntPtr.Zero;
            Trace(phase, ownerId, api, "completed", target);
            if (pointer == IntPtr.Zero) throw new InvalidOperationException("Actual pointer acquisition returned null");
            foreach (var iid in new[] { UnknownId, AutomationIdentityNative.FragmentId })
            {
                var query = new JsonObject { ["iid"] = iid.ToString(), ["api"] = "IUnknown.QueryInterface", ["source_pointer"] = AutomationIdentityNative.Pointer(pointer) };
                target["queries"]!.AsArray().Add(query);
                var result = IntPtr.Zero; var hr = unchecked((int)0x80004005);
                Trace(phase, ownerId, api + ": QI " + iid, "pending");
                try
                {
                    var requested = iid; hr = Marshal.QueryInterface(pointer, ref requested, out result);
                    query["hresult"] = hr; query["hresult_hex"] = "0x" + unchecked((uint)hr).ToString("X8");
                    query["pointer"] = AutomationIdentityNative.Pointer(result); query["returned_nonnull"] = result != IntPtr.Zero;
                    Trace(phase, ownerId, api + ": QI " + iid, hr >= 0 ? "completed" : "failed", query);
                }
                catch (Exception ex) { Failure("QueryInterface(" + iid + ")", ex, query); }
                finally
                {
                    if (hr >= 0 && result != IntPtr.Zero) Release(phase, ownerId, result, "QI " + iid, query);
                    else if (result != IntPtr.Zero) query["failed_qi_pointer_ownership_unknown"] = true;
                }
            }
        }
        catch (Exception ex) { Failure(api, ex, target); Trace(phase, ownerId, api, "failed", target); }
        finally { if (pointer != IntPtr.Zero) Release(phase, ownerId, pointer, api, target); }
    }

    private void Release(string phase, string ownerId, IntPtr pointer, string owner, JsonObject target)
    {
        var release = new JsonObject { ["api"] = "IUnknown.Release", ["reference_owner"] = owner,
            ["pointer"] = AutomationIdentityNative.Pointer(pointer) };
        target["release"] = release; Trace(phase, ownerId, "Release " + owner, "pending");
        try { release["remaining_references"] = Marshal.Release(pointer); Trace(phase, ownerId, "Release " + owner, "completed", release); }
        catch (Exception ex) { Failure("Release " + owner, ex, release); Trace(phase, ownerId, "Release " + owner, "failed", release); }
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true; receipt["after_phase_requested"] = afterCaptured;
        receipt["disposed_qpc"] = Stopwatch.GetTimestamp(); Save();
        progress.Dispose(); owners.Clear(); // No native QI or new observation on disposal.
    }
}
