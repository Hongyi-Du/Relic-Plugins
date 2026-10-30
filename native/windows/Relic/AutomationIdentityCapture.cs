using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
#if WINDOWS
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
#endif

namespace Relic;

// Linked unchanged into the net8.0 pure ABI tests. The WinUI caller below is
// compiled only into the actual Windows app; tests never create a peer/window.
internal static class AutomationIdentityNative
{
    internal static readonly Guid FragmentId = new("f7063da8-8359-439c-9297-bbc5299a7d87");
    internal static readonly Guid SimpleId = new("d6dd68d1-86fd-4332-8666-9abedea2d24c");
    internal const int FragmentRuntimeIdSlot = 4;
    // Windows SDK UIAutomationCore.h: IUnknown slots 0..2, Navigate=3,
    // GetRuntimeId=4. This is HRESULT + SAFEARRAY**, never a struct return.
    // https://learn.microsoft.com/en-us/windows/win32/api/uiautomationcore/nf-uiautomationcore-irawelementproviderfragment-getruntimeid
    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    internal delegate int FragmentRuntimeId(IntPtr self, out IntPtr array);
    internal static T Method<T>(IntPtr instance, int slot) where T : Delegate =>
        Marshal.GetDelegateForFunctionPointer<T>(Marshal.ReadIntPtr(Marshal.ReadIntPtr(instance), checked(slot * IntPtr.Size)));

    internal interface IApi
    {
        int Query(IntPtr value, Guid iid, out IntPtr result);
        int FragmentIdRead(IntPtr fragment, out IntPtr array);
        int NodeFromProvider(IntPtr simple, out IntPtr node);
        int RuntimeIdRead(IntPtr node, out IntPtr array);
        uint ArrayDimensions(IntPtr array);
        uint ArrayElementSize(IntPtr array);
        int ArrayType(IntPtr array, out ushort type);
        int ArrayLower(IntPtr array, uint dimension, out int lower);
        int ArrayUpper(IntPtr array, uint dimension, out int upper);
        int ArrayElement(IntPtr array, ref int index, out int value);
        int ArrayDestroy(IntPtr array);
        bool NodeRelease(IntPtr node);
        int Release(IntPtr value);
    }
    internal sealed class Api : IApi
    {
        public int Query(IntPtr value, Guid iid, out IntPtr result) => Marshal.QueryInterface(value, ref iid, out result);
        public int FragmentIdRead(IntPtr fragment, out IntPtr array) => Method<FragmentRuntimeId>(fragment, FragmentRuntimeIdSlot)(fragment, out array);
        public int NodeFromProvider(IntPtr simple, out IntPtr node) => UiaNodeFromProvider(simple, out node);
        public int RuntimeIdRead(IntPtr node, out IntPtr array) => UiaGetRuntimeId(node, out array);
        public uint ArrayDimensions(IntPtr array) => SafeArrayGetDim(array);
        public uint ArrayElementSize(IntPtr array) => SafeArrayGetElemsize(array);
        public int ArrayType(IntPtr array, out ushort type) => SafeArrayGetVartype(array, out type);
        public int ArrayLower(IntPtr array, uint dimension, out int lower) => SafeArrayGetLBound(array, dimension, out lower);
        public int ArrayUpper(IntPtr array, uint dimension, out int upper) => SafeArrayGetUBound(array, dimension, out upper);
        public int ArrayElement(IntPtr array, ref int index, out int value) => SafeArrayGetElement(array, ref index, out value);
        public int ArrayDestroy(IntPtr array) => SafeArrayDestroy(array);
        public bool NodeRelease(IntPtr node) => UiaNodeRelease(node);
        public int Release(IntPtr value) => Marshal.Release(value);
    }

    [DllImport("UIAutomationCore.dll", ExactSpelling = true)]
    private static extern int UiaNodeFromProvider(IntPtr simple, out IntPtr node);
    [DllImport("UIAutomationCore.dll", ExactSpelling = true)]
    private static extern int UiaGetRuntimeId(IntPtr node, out IntPtr array);
    [DllImport("UIAutomationCore.dll", ExactSpelling = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool UiaNodeRelease(IntPtr node);
    [DllImport("oleaut32.dll", ExactSpelling = true)] private static extern uint SafeArrayGetDim(IntPtr array);
    [DllImport("oleaut32.dll", ExactSpelling = true)] private static extern uint SafeArrayGetElemsize(IntPtr array);
    [DllImport("oleaut32.dll", ExactSpelling = true)] private static extern int SafeArrayGetVartype(IntPtr array, out ushort type);
    [DllImport("oleaut32.dll", ExactSpelling = true)] private static extern int SafeArrayGetLBound(IntPtr array, uint dimension, out int lower);
    [DllImport("oleaut32.dll", ExactSpelling = true)] private static extern int SafeArrayGetUBound(IntPtr array, uint dimension, out int upper);
    [DllImport("oleaut32.dll", ExactSpelling = true)] private static extern int SafeArrayGetElement(IntPtr array, ref int index, out int value);
    [DllImport("oleaut32.dll", ExactSpelling = true)] private static extern int SafeArrayDestroy(IntPtr array);

    internal static string Pointer(IntPtr value) => "0x" + unchecked((ulong)value.ToInt64()).ToString("X");
    internal static JsonObject HResult(string operation, int hr) => new()
    { ["api"] = operation, ["hresult"] = hr, ["hresult_hex"] = "0x" + unchecked((uint)hr).ToString("X8"), ["succeeded"] = hr >= 0 };

    // peerInspectable is borrowed; the WinUI caller retains/releases its own
    // MarshalInspectable reference. Every native result owned here is released.
    internal static JsonObject Read(IntPtr peerInspectable, IApi api, Action<JsonObject>? progress = null)
    {
        var receipt = new JsonObject { ["source"] = "Actual AutomationPeer QI to native UIA fragment and UIA core node",
            ["status"] = "unknown", ["peer_inspectable"] = Pointer(peerInspectable),
            ["runtime_id_policy"] = "Opaque full UIA core RuntimeId; no prefix/suffix assembly",
            ["core_api_note"] = "UiaNodeFromProvider/UiaGetRuntimeId are public deprecated C APIs; actual return values and failures are retained" };
        var steps = new JsonArray(); var lifecycle = new JsonArray(); receipt["steps"] = steps; receipt["lifecycle"] = lifecycle;
        var fragment = IntPtr.Zero; var simple = IntPtr.Zero; var node = IntPtr.Zero;
        var failures = new JsonArray(); receipt["failures"] = failures;
        void Trace(string operation, string status)
        {
            try { progress?.Invoke(new JsonObject { ["api"] = operation, ["status"] = status }); }
            catch (Exception ex) { failures.Add("Progress journal write: " + ex); }
        }
        void Check(string operation, int hr)
        {
            steps.Add(HResult(operation, hr));
            Trace(operation, hr < 0 ? "failed" : "completed");
            if (hr < 0) throw new COMException(operation, hr);
        }
        int[] ReadArray(string name, Func<(int Hr, IntPtr Array)> query)
        {
            var data = new JsonObject { ["status"] = "unknown",
                ["api"] = name == "fragment_runtime_id" ? "IRawElementProviderFragment.GetRuntimeId" : "UiaGetRuntimeId" };
            receipt[name] = data;
            IntPtr array = IntPtr.Zero;
            try
            {
                Trace(name, "pending");
                var response = query(); array = response.Array;
                data["pointer"] = Pointer(array); Check(name, response.Hr);
                if (array == IntPtr.Zero) throw new InvalidOperationException(name + " returned no SAFEARRAY; absence is not a RuntimeId");
                Trace("SafeArrayGetDim(" + name + ")", "pending");
                var dimensions = api.ArrayDimensions(array); data["dimensions"] = dimensions;
                Trace("SafeArrayGetDim(" + name + ")", "completed");
                Trace("SafeArrayGetElemsize(" + name + ")", "pending");
                data["element_size"] = api.ArrayElementSize(array);
                Trace("SafeArrayGetElemsize(" + name + ")", "completed");
                Trace("SafeArrayGetVartype(" + name + ")", "pending");
                Check("SafeArrayGetVartype(" + name + ")", api.ArrayType(array, out var type)); data["vartype"] = type;
                var limits = new JsonArray(); data["dimension_bounds"] = limits;
                // Runtime IDs require one dimension. Retain every reported
                // dimension before rejecting any unrepresentable shape.
                if (dimensions > 32) throw new InvalidOperationException("SAFEARRAY dimension count exceeds the observer's bounded metadata walk");
                for (uint dimension = 1; dimension <= dimensions; dimension++)
                {
                    var bound = new JsonObject { ["dimension"] = dimension }; limits.Add(bound);
                    Trace("SafeArrayGetLBound(" + name + "," + dimension + ")", "pending");
                    Check("SafeArrayGetLBound(" + name + "," + dimension + ")", api.ArrayLower(array, dimension, out var lower)); bound["lower"] = lower;
                    Trace("SafeArrayGetUBound(" + name + "," + dimension + ")", "pending");
                    Check("SafeArrayGetUBound(" + name + "," + dimension + ")", api.ArrayUpper(array, dimension, out var upper)); bound["upper"] = upper;
                }
                if (dimensions != 1 || type != 3 || data["element_size"]!.GetValue<uint>() != 4)
                    throw new InvalidOperationException("RuntimeId SAFEARRAY is not one-dimensional VT_I4 with 4-byte elements");
                var low = limits[0]!["lower"]!.GetValue<int>(); var high = limits[0]!["upper"]!.GetValue<int>();
                var count = (long)high - low + 1; data["element_count"] = count;
                if (count <= 0 || count > 4096) throw new InvalidOperationException("RuntimeId array length is empty or exceeds the observer's bounded read");
                var values = new JsonArray(); data["values"] = values; var result = new int[(int)count];
                for (var offset = 0; offset < result.Length; offset++)
                {
                    var index = checked(low + offset);
                    Trace("SafeArrayGetElement(" + name + "," + index + ")", "pending");
                    Check("SafeArrayGetElement(" + name + "," + index + ")", api.ArrayElement(array, ref index, out var value));
                    values.Add(value); result[offset] = value;
                }
                data["status"] = "measured";
                return result;
            }
            catch (Exception ex) { data["error"] = ex.ToString(); throw; }
            finally
            {
                if (array != IntPtr.Zero)
                {
                    try
                    {
                        Trace("SafeArrayDestroy(" + name + ")", "pending");
                        var hr = api.ArrayDestroy(array); var release = HResult("SafeArrayDestroy(" + name + ")", hr);
                        release["pointer"] = Pointer(array); lifecycle.Add(release);
                        Trace("SafeArrayDestroy(" + name + ")", hr < 0 ? "failed" : "completed");
                        if (hr < 0) failures.Add(release.DeepClone());
                    }
                    catch (Exception ex) { failures.Add("SafeArrayDestroy(" + name + "): " + ex); }
                }
            }
        }
        try
        {
            Trace("QueryInterface(IRawElementProviderFragment)", "pending");
            Check("QueryInterface(IRawElementProviderFragment)", api.Query(peerInspectable, FragmentId, out fragment));
            receipt["fragment_pointer"] = Pointer(fragment);
            if (fragment == IntPtr.Zero) throw new InvalidOperationException("Successful fragment QI returned null");
            ReadArray("fragment_runtime_id", () => { var hr = api.FragmentIdRead(fragment, out var array); return (hr, array); });
            Trace("QueryInterface(IRawElementProviderSimple)", "pending");
            Check("QueryInterface(IRawElementProviderSimple)", api.Query(fragment, SimpleId, out simple));
            receipt["simple_pointer"] = Pointer(simple);
            if (simple == IntPtr.Zero) throw new InvalidOperationException("Successful native simple QI returned null");
            Trace("UiaNodeFromProvider", "pending");
            Check("UiaNodeFromProvider", api.NodeFromProvider(simple, out node)); receipt["core_node"] = Pointer(node);
            if (node == IntPtr.Zero) throw new InvalidOperationException("Successful UiaNodeFromProvider returned null");
            var before = ReadArray("core_runtime_id", () => { var hr = api.RuntimeIdRead(node, out var array); return (hr, array); });
            var after = ReadArray("core_runtime_id_recheck", () => { var hr = api.RuntimeIdRead(node, out var array); return (hr, array); });
            receipt["core_runtime_id_stable"] = before.SequenceEqual(after);
            if (!before.SequenceEqual(after)) throw new InvalidOperationException("Actual UIA core RuntimeId changed during capture");
        }
        catch (Exception ex) { failures.Add(new JsonObject { ["type"] = ex.GetType().FullName, ["hresult"] = ex.HResult, ["error"] = ex.ToString() }); }
        finally
        {
            if (node != IntPtr.Zero)
            {
                try
                {
                    Trace("UiaNodeRelease", "pending");
                    var released = api.NodeRelease(node);
                    var record = new JsonObject { ["api"] = "UiaNodeRelease", ["pointer"] = Pointer(node), ["returned_bool"] = released };
                    lifecycle.Add(record); if (!released) failures.Add(record.DeepClone());
                    Trace("UiaNodeRelease", released ? "completed" : "failed");
                }
                catch (Exception ex) { failures.Add("UiaNodeRelease: " + ex); }
            }
            foreach (var (pointer, name) in new[] { (simple, "native simple"), (fragment, "native fragment") })
            {
                if (pointer == IntPtr.Zero) continue;
                try
                {
                    Trace("IUnknown.Release(" + name + ")", "pending");
                    lifecycle.Add(new JsonObject { ["api"] = "IUnknown.Release", ["owner"] = name, ["pointer"] = Pointer(pointer), ["remaining_references"] = api.Release(pointer) });
                    Trace("IUnknown.Release(" + name + ")", "completed");
                }
                catch (Exception ex) { failures.Add("IUnknown.Release(" + name + "): " + ex); }
            }
        }
        receipt["status"] = failures.Count == 0 && receipt["core_runtime_id_stable"]?.GetValue<bool>() == true ? "measured" : "unknown";
        return receipt;
    }
}

// An inter-thread stream is the only native object transferred between the UI
// apartment and the worker. The borrowed STA peer pointer never enters Task.Run.
// https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-comarshalinterthreadinterfaceinstream
// https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-cogetinterfaceandreleasestream
internal sealed class AutomationIdentityMarshal
{
    internal interface IApi
    {
        int QueryFragment(IntPtr peer, out IntPtr fragment);
        int MarshalFragment(IntPtr fragment, out IntPtr stream);
        int InitializeMta();
        int UnmarshalFragmentAndReleaseStream(IntPtr stream, out IntPtr fragment);
        void Uninitialize();
        int ReleaseMarshalData(IntPtr stream);
        int Release(IntPtr pointer);
    }
    internal sealed class Api : IApi
    {
        public int QueryFragment(IntPtr peer, out IntPtr fragment)
        { var iid = AutomationIdentityNative.FragmentId; return Marshal.QueryInterface(peer, ref iid, out fragment); }
        public int MarshalFragment(IntPtr fragment, out IntPtr stream)
        { var iid = AutomationIdentityNative.FragmentId; return CoMarshalInterThreadInterfaceInStream(ref iid, fragment, out stream); }
        public int InitializeMta() => CoInitializeEx(IntPtr.Zero, 0); // COINIT_MULTITHREADED
        public int UnmarshalFragmentAndReleaseStream(IntPtr stream, out IntPtr fragment)
        { var iid = AutomationIdentityNative.FragmentId; return CoGetInterfaceAndReleaseStream(stream, ref iid, out fragment); }
        public void Uninitialize() => CoUninitialize();
        public int ReleaseMarshalData(IntPtr stream) => CoReleaseMarshalData(stream);
        public int Release(IntPtr pointer) => Marshal.Release(pointer);
    }
    [DllImport("ole32.dll", ExactSpelling = true)]
    private static extern int CoMarshalInterThreadInterfaceInStream(ref Guid iid, IntPtr value, out IntPtr stream);
    [DllImport("ole32.dll", ExactSpelling = true)]
    private static extern int CoGetInterfaceAndReleaseStream(IntPtr stream, ref Guid iid, out IntPtr value);
    [DllImport("ole32.dll", ExactSpelling = true)] private static extern int CoInitializeEx(IntPtr reserved, uint flags);
    [DllImport("ole32.dll", ExactSpelling = true)] private static extern void CoUninitialize();
    [DllImport("ole32.dll", ExactSpelling = true)] private static extern int CoReleaseMarshalData(IntPtr stream);

    private readonly IApi api;
    private readonly Action<JsonObject>? progress;
    private readonly int originThread = Environment.CurrentManagedThreadId;
    private readonly JsonArray steps = [], failures = [], lifecycle = [];
    private IntPtr stream;
    private bool packetWasMarshaled, workerReadCompleted, finished;
    internal JsonObject Receipt { get; }

    internal AutomationIdentityMarshal(IApi api, Action<JsonObject>? progress = null)
    {
        this.api = api; this.progress = progress;
        Receipt = new JsonObject { ["source"] = "Actual COM inter-apartment marshal stream and MTA UIA core read",
            ["status"] = "unknown", ["origin_managed_thread_id"] = originThread,
            ["origin_apartment_state"] = Thread.CurrentThread.GetApartmentState().ToString(),
            ["interface_iid"] = AutomationIdentityNative.FragmentId.ToString(),
            ["steps"] = steps, ["failures"] = failures, ["lifecycle"] = lifecycle,
            ["stream_consumed_by_unmarshal"] = false, ["stream_consumption_unknown"] = false,
            ["worker_read_completed"] = false };
    }
    private void Trace(string operation, string status)
    {
        try { progress?.Invoke(new JsonObject { ["api"] = operation, ["status"] = status,
            ["managed_thread_id"] = Environment.CurrentManagedThreadId,
            ["apartment_state"] = Thread.CurrentThread.GetApartmentState().ToString() }); }
        catch (Exception ex) { Fail("Progress journal write", ex); }
    }
    private void Fail(string operation, Exception ex) => failures.Add(new JsonObject {
        ["api"] = operation, ["type"] = ex.GetType().FullName, ["hresult"] = ex.HResult, ["error"] = ex.ToString() });
    private void Check(string operation, int hr)
    {
        steps.Add(AutomationIdentityNative.HResult(operation, hr)); Trace(operation, hr < 0 ? "failed" : "completed");
        if (hr < 0) throw new COMException(operation, hr);
    }
    private void ReleasePointer(IntPtr pointer, string owner)
    {
        if (pointer == IntPtr.Zero) return;
        try
        {
            Trace("IUnknown.Release(" + owner + ")", "pending");
            lifecycle.Add(new JsonObject { ["api"] = "IUnknown.Release", ["owner"] = owner,
                ["pointer"] = AutomationIdentityNative.Pointer(pointer), ["remaining_references"] = api.Release(pointer) });
            Trace("IUnknown.Release(" + owner + ")", "completed");
        }
        catch (Exception ex) { Fail("IUnknown.Release(" + owner + ")", ex); }
    }

    // Called only in the original UI apartment. This peer is never dereferenced
    // on the worker; the marshaled packet owns the cross-apartment reference.
    internal bool Prepare(IntPtr peer)
    {
        IntPtr fragment = IntPtr.Zero;
        try
        {
            if (Environment.CurrentManagedThreadId != originThread) throw new InvalidOperationException("Marshal preparation left its origin apartment");
            Trace("QueryInterface(IRawElementProviderFragment, origin)", "pending");
            Check("QueryInterface(IRawElementProviderFragment, origin)", api.QueryFragment(peer, out fragment));
            Receipt["origin_fragment"] = AutomationIdentityNative.Pointer(fragment);
            if (fragment == IntPtr.Zero) throw new InvalidOperationException("Origin fragment QI returned null");
            Trace("CoMarshalInterThreadInterfaceInStream", "pending");
            var hr = api.MarshalFragment(fragment, out stream);
            packetWasMarshaled = hr >= 0;
            Receipt["stream_pointer"] = AutomationIdentityNative.Pointer(stream);
            Check("CoMarshalInterThreadInterfaceInStream", hr);
            if (stream == IntPtr.Zero) throw new InvalidOperationException("Successful interface marshal returned no stream");
        }
        catch (Exception ex) { Fail("Prepare actual fragment marshal", ex); }
        finally { ReleasePointer(fragment, "origin fragment after marshaling"); }
        return failures.Count == 0 && stream != IntPtr.Zero && packetWasMarshaled;
    }

    // Task.Run calls this synchronously on one MTA worker. All native results,
    // including the proxy, are released before balancing CoInitializeEx.
    internal JsonObject? ReadWorker(AutomationIdentityNative.IApi nativeApi)
    {
        bool initialized = false; IntPtr proxy = IntPtr.Zero; JsonObject? native = null;
        Receipt["worker_managed_thread_id"] = Environment.CurrentManagedThreadId;
        Receipt["worker_apartment_state_before"] = Thread.CurrentThread.GetApartmentState().ToString();
        try
        {
            if (Environment.CurrentManagedThreadId == originThread) throw new InvalidOperationException("UIA core read must not run on the origin UI thread");
            Trace("CoInitializeEx(COINIT_MULTITHREADED)", "pending");
            var hr = api.InitializeMta(); initialized = hr >= 0;
            Check("CoInitializeEx(COINIT_MULTITHREADED)", hr);
            Receipt["worker_apartment_state_after"] = Thread.CurrentThread.GetApartmentState().ToString();
            if (stream == IntPtr.Zero || !packetWasMarshaled) throw new InvalidOperationException("No actual marshaled fragment stream is available");
            Trace("CoGetInterfaceAndReleaseStream", "pending");
            try
            {
                hr = api.UnmarshalFragmentAndReleaseStream(stream, out proxy);
                // The documented API releases IStream even when HRESULT fails.
                // Never release this consumed stream a second time on the UI.
                lifecycle.Add(new JsonObject { ["api"] = "CoGetInterfaceAndReleaseStream", ["stream_pointer"] = AutomationIdentityNative.Pointer(stream),
                    ["stream_released_by_api"] = true, ["hresult"] = hr, ["hresult_hex"] = "0x" + unchecked((uint)hr).ToString("X8") });
                stream = IntPtr.Zero; Receipt["stream_consumed_by_unmarshal"] = true;
            }
            catch (Exception ex)
            {
                // A managed interop exception provides no API return/consumption
                // receipt. Do not guess that releasing this stream again is safe.
                Receipt["stream_consumption_unknown"] = true;
                Receipt["unresolved_stream_pointer"] = AutomationIdentityNative.Pointer(stream);
                stream = IntPtr.Zero; Fail("CoGetInterfaceAndReleaseStream consumption unknown", ex); throw;
            }
            Check("CoGetInterfaceAndReleaseStream", hr);
            Receipt["worker_fragment_proxy"] = AutomationIdentityNative.Pointer(proxy);
            if (proxy == IntPtr.Zero) throw new InvalidOperationException("Successful interface unmarshal returned null");
            native = AutomationIdentityNative.Read(proxy, nativeApi, progress);
            workerReadCompleted = true; Receipt["worker_read_completed"] = true;
        }
        catch (Exception ex) { Fail("MTA identity read", ex); }
        finally
        {
            ReleasePointer(proxy, "MTA fragment proxy");
            if (initialized)
            {
                try
                {
                    Trace("CoUninitialize", "pending"); api.Uninitialize();
                    lifecycle.Add(new JsonObject { ["api"] = "CoUninitialize", ["completed"] = true });
                    Trace("CoUninitialize", "completed");
                }
                catch (Exception ex) { Fail("CoUninitialize", ex); }
            }
        }
        return native;
    }

    // Scheduling/COM initialization can fail before the receiver consumes the
    // stream. Only the original apartment may release its unused marshal data.
    // https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-coreleasemarshaldata
    internal void FinishOnOrigin()
    {
        if (finished) return;
        finished = true;
        Receipt["finish_managed_thread_id"] = Environment.CurrentManagedThreadId;
        Receipt["returned_to_origin_thread"] = Environment.CurrentManagedThreadId == originThread;
        if (Environment.CurrentManagedThreadId != originThread)
        {
            Fail("Finish marshal packet", new InvalidOperationException("Origin apartment was not restored; unused marshal data cannot safely be released here"));
            Receipt["unresolved_stream_pointer"] = AutomationIdentityNative.Pointer(stream);
        }
        else if (stream != IntPtr.Zero)
        {
            try
            {
                if (packetWasMarshaled)
                {
                    Trace("CoReleaseMarshalData(unconsumed stream, origin)", "pending");
                    var hr = api.ReleaseMarshalData(stream);
                    lifecycle.Add(AutomationIdentityNative.HResult("CoReleaseMarshalData(unconsumed stream, origin)", hr));
                    Check("CoReleaseMarshalData(unconsumed stream, origin)", hr);
                }
            }
            catch (Exception ex) { Fail("Release unused marshal packet", ex); }
            finally { ReleasePointer(stream, "unconsumed marshal stream on origin"); stream = IntPtr.Zero; }
        }
        Receipt["status"] = failures.Count == 0 && workerReadCompleted ? "measured" : "unknown";
    }
}

#if WINDOWS
public sealed partial class MainWindow
{
    private async Task CaptureAutomationIdentities(string directory, string caseId, Dictionary<DependencyObject, string> ids,
        Dictionary<DependencyObject, JsonObject> nodes)
    {
        if (!VisualCaptureEnabled) throw new InvalidOperationException("Automation identity capture is CI-only");
        // Flush to the OS cache after each entered/returned native API. A UIA
        // core stall or process fault must not erase the last attempted stage.
        using var progressStream = new FileStream(System.IO.Path.Combine(directory, caseId + ".automation-identity.progress.jsonl"),
            FileMode.Create, FileAccess.Write, FileShare.ReadWrite);
        using var writer = new StreamWriter(progressStream) { AutoFlush = true };
        var watch = System.Diagnostics.Stopwatch.StartNew(); long sequence = 0;
        foreach (var (value, record) in nodes)
        {
            if (value is not UIElement element) continue;
            var ownerId = ids[value];
            var receipt = new JsonObject { ["source"] = "Actual FrameworkElementAutomationPeer.FromElement owner binding",
                ["status"] = "unknown", ["owner_id"] = ownerId, ["process_id"] = Environment.ProcessId,
                ["api"] = "FrameworkElementAutomationPeer.FromElement(actual captured UIElement)",
                ["metadata_modified"] = false,
                ["peer_creation_note"] = "WinUI FromElement may lazily create its existing production peer/provider infrastructure; CreatePeerForElement is not called" };
            record["automation_identity_evidence"] = receipt;
            void Trace(JsonObject stage)
            {
                stage["owner_id"] = ownerId; stage["elapsed_ms"] = watch.Elapsed.TotalMilliseconds; stage["sequence"] = ++sequence;
                stage["managed_thread_id"] = Environment.CurrentManagedThreadId;
                writer.WriteLine(stage.ToJsonString());
            }
            IntPtr inspectable = IntPtr.Zero;
            try
            {
                Trace(new JsonObject { ["api"] = "FrameworkElementAutomationPeer.FromElement", ["status"] = "pending" });
                var peer = FrameworkElementAutomationPeer.FromElement(element);
                Trace(new JsonObject { ["api"] = "FrameworkElementAutomationPeer.FromElement", ["status"] = "completed", ["peer_is_null"] = peer == null });
                receipt["peer_is_null"] = peer == null;
                if (peer == null) { receipt["status"] = "no-peer"; continue; }
                receipt["peer_type"] = peer.GetType().FullName;
                var owner = (peer as FrameworkElementAutomationPeer)?.Owner;
                var sameOwner = ReferenceEquals(owner, element); receipt["same_owner_object"] = sameOwner;
                receipt["peer_owner_id"] = owner != null && ids.TryGetValue(owner, out var actualOwnerId) ? actualOwnerId : null;
                var eventsSource = peer.EventsSource;
                receipt["events_source_type"] = eventsSource?.GetType().FullName;
                receipt["events_source_same_peer"] = ReferenceEquals(eventsSource, peer);
                receipt["events_source_is_null"] = eventsSource == null;
                if (!sameOwner) throw new InvalidOperationException("Actual peer owner does not match this XAML object");
                // Actual native WinUI peer supports QI for native fragment.
                // ProviderFromPeer returns a distinct WinRT wrapper, not this COM interface.
                // https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/dxaml/lib/AutomationPeer_Partial.cpp#L88
                Trace(new JsonObject { ["api"] = "MarshalInspectable.FromManaged(actual peer)", ["status"] = "pending" });
                inspectable = WinRT.MarshalInspectable<object>.FromManaged(peer);
                Trace(new JsonObject { ["api"] = "MarshalInspectable.FromManaged(actual peer)", ["status"] = "completed", ["pointer"] = AutomationIdentityNative.Pointer(inspectable) });
                var transport = new AutomationIdentityMarshal(new AutomationIdentityMarshal.Api(), Trace);
                receipt["apartment_transport"] = transport.Receipt;
                JsonObject? native = null;
                try
                {
                    if (transport.Prepare(inspectable))
                    {
                        // Preserve the UI synchronization context: the await
                        // pumps WinUI while COM calls back to its STA provider.
                        native = await Task.Run(() => transport.ReadWorker(new AutomationIdentityNative.Api()));
                    }
                }
                finally { transport.FinishOnOrigin(); }
                receipt["native"] = native;
                if (!DispatcherQueue.HasThreadAccess) throw new InvalidOperationException("Identity capture did not return to the UI dispatcher");
                Trace(new JsonObject { ["api"] = "FrameworkElementAutomationPeer.FromElement recheck", ["status"] = "pending" });
                var current = FrameworkElementAutomationPeer.FromElement(element);
                Trace(new JsonObject { ["api"] = "FrameworkElementAutomationPeer.FromElement recheck", ["status"] = "completed" });
                receipt["peer_same_object_after"] = ReferenceEquals(current, peer);
                receipt["events_source_same_object_after"] = ReferenceEquals(peer.EventsSource, eventsSource);
                receipt["status"] = native?["status"]?.GetValue<string>() == "measured"
                    && transport.Receipt["status"]?.GetValue<string>() == "measured"
                    && ReferenceEquals(current, peer) && receipt["events_source_same_object_after"]!.GetValue<bool>() ? "measured" : "unknown";
            }
            catch (Exception ex) { receipt["error"] = ex.ToString(); receipt["hresult"] = ex.HResult; receipt["status"] = "unknown"; }
            finally
            {
                if (inspectable != IntPtr.Zero)
                {
                    try { receipt["inspectable_release"] = new JsonObject { ["pointer"] = AutomationIdentityNative.Pointer(inspectable), ["remaining_references"] = Marshal.Release(inspectable) }; }
                    catch (Exception ex) { receipt["inspectable_release_error"] = ex.ToString(); receipt["status"] = "unknown"; }
                }
                try { Trace(new JsonObject { ["api"] = "capture-owner", ["status"] = receipt["status"]?.DeepClone(), ["evidence"] = receipt.DeepClone() }); }
                catch (Exception ex) { receipt["progress_error"] = ex.ToString(); receipt["status"] = "unknown"; }
            }
        }
    }
}
#endif
