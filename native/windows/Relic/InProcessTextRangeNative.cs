using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;

namespace Relic;

// Public provider ABI, checked against Windows SDK 10.0.26100.0 UIAutomationCore.h.
// These are provider interfaces, not IUIAutomationTextPattern client interfaces.
// https://learn.microsoft.com/en-us/windows/win32/api/uiautomationcore/nn-uiautomationcore-itextrangeprovider
internal static class InProcessTextRangeNative
{
    internal static readonly Guid TextProviderId = new("3589c92c-63f3-4367-99bb-ada653b77cf2");
    internal static readonly Guid TextRangeProviderId = new("5347ad7b-c355-46f8-aff5-909033582f63");
    internal const int TextPatternId = 10014;
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int PointerResult(IntPtr self, out IntPtr result);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int PatternResult(IntPtr self, int pattern, out IntPtr result);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int TextResult(IntPtr self, int length, out IntPtr result);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int MoveEndpoint(IntPtr self, int endpoint, IntPtr target, int targetEndpoint);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int MoveEndpointUnit(IntPtr self, int endpoint, int unit, int count, out int moved);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int CompareEndpoint(IntPtr self, int endpoint, IntPtr target, int targetEndpoint, out int comparison);

    internal interface IApi
    {
        int Query(IntPtr source, Guid iid, out IntPtr result);
        int Pattern(IntPtr simple, out IntPtr result);
        int Document(IntPtr provider, out IntPtr result);
        int Visible(IntPtr provider, out IntPtr array);
        int Clone(IntPtr range, out IntPtr result);
        int Text(IntPtr range, out IntPtr bstr);
        int Rectangles(IntPtr range, out IntPtr array);
        int Move(IntPtr range, int endpoint, IntPtr target, int targetEndpoint);
        int MoveUnit(IntPtr range, int endpoint, int unit, int count, out int moved);
        int Compare(IntPtr range, int endpoint, IntPtr target, int targetEndpoint, out int comparison);
        uint Dimensions(IntPtr array);
        uint ElementSize(IntPtr array);
        int ArrayType(IntPtr array, out ushort type);
        int Lower(IntPtr array, out int lower);
        int Upper(IntPtr array, out int upper);
        int Double(IntPtr array, int index, out double value);
        int Unknown(IntPtr array, int index, out IntPtr value);
        int Destroy(IntPtr array);
        string? String(IntPtr bstr);
        uint StringLength(IntPtr bstr);
        void FreeString(IntPtr bstr);
        int Release(IntPtr value);
    }

    internal sealed class Api : IApi
    {
        public int Query(IntPtr source, Guid iid, out IntPtr result) => Marshal.QueryInterface(source, ref iid, out result);
        public int Pattern(IntPtr simple, out IntPtr result) => AutomationIdentityNative.Method<PatternResult>(simple, 4)(simple, TextPatternId, out result);
        public int Document(IntPtr provider, out IntPtr result) => AutomationIdentityNative.Method<PointerResult>(provider, 7)(provider, out result);
        public int Visible(IntPtr provider, out IntPtr array) => AutomationIdentityNative.Method<PointerResult>(provider, 4)(provider, out array);
        public int Clone(IntPtr range, out IntPtr result) => AutomationIdentityNative.Method<PointerResult>(range, 3)(range, out result);
        public int Text(IntPtr range, out IntPtr bstr) => AutomationIdentityNative.Method<TextResult>(range, 12)(range, -1, out bstr);
        public int Rectangles(IntPtr range, out IntPtr array) => AutomationIdentityNative.Method<PointerResult>(range, 10)(range, out array);
        public int Move(IntPtr range, int endpoint, IntPtr target, int targetEndpoint) => AutomationIdentityNative.Method<MoveEndpoint>(range, 15)(range, endpoint, target, targetEndpoint);
        public int MoveUnit(IntPtr range, int endpoint, int unit, int count, out int moved) => AutomationIdentityNative.Method<MoveEndpointUnit>(range, 14)(range, endpoint, unit, count, out moved);
        public int Compare(IntPtr range, int endpoint, IntPtr target, int targetEndpoint, out int comparison) => AutomationIdentityNative.Method<CompareEndpoint>(range, 5)(range, endpoint, target, targetEndpoint, out comparison);
        public uint Dimensions(IntPtr array) => SafeArrayGetDim(array);
        public uint ElementSize(IntPtr array) => SafeArrayGetElemsize(array);
        public int ArrayType(IntPtr array, out ushort type) => SafeArrayGetVartype(array, out type);
        public int Lower(IntPtr array, out int lower) => SafeArrayGetLBound(array, 1, out lower);
        public int Upper(IntPtr array, out int upper) => SafeArrayGetUBound(array, 1, out upper);
        public int Double(IntPtr array, int index, out double value) => SafeArrayGetDouble(array, ref index, out value);
        public int Unknown(IntPtr array, int index, out IntPtr value) => SafeArrayGetUnknown(array, ref index, out value);
        public int Destroy(IntPtr array) => SafeArrayDestroy(array);
        public string? String(IntPtr bstr) => bstr == IntPtr.Zero ? null : Marshal.PtrToStringBSTR(bstr);
        public uint StringLength(IntPtr bstr) => SysStringLen(bstr);
        public void FreeString(IntPtr bstr) => Marshal.FreeBSTR(bstr);
        public int Release(IntPtr value) => Marshal.Release(value);
    }
    [DllImport("oleaut32.dll", ExactSpelling = true)] private static extern uint SafeArrayGetDim(IntPtr array);
    [DllImport("oleaut32.dll", ExactSpelling = true)] private static extern uint SysStringLen(IntPtr bstr);
    [DllImport("oleaut32.dll", ExactSpelling = true)] private static extern uint SafeArrayGetElemsize(IntPtr array);
    [DllImport("oleaut32.dll", ExactSpelling = true)] private static extern int SafeArrayGetVartype(IntPtr array, out ushort type);
    [DllImport("oleaut32.dll", ExactSpelling = true)] private static extern int SafeArrayGetLBound(IntPtr array, uint dimension, out int lower);
    [DllImport("oleaut32.dll", ExactSpelling = true)] private static extern int SafeArrayGetUBound(IntPtr array, uint dimension, out int upper);
    [DllImport("oleaut32.dll", EntryPoint = "SafeArrayGetElement", ExactSpelling = true)] private static extern int SafeArrayGetDouble(IntPtr array, ref int index, out double value);
    [DllImport("oleaut32.dll", EntryPoint = "SafeArrayGetElement", ExactSpelling = true)] private static extern int SafeArrayGetUnknown(IntPtr array, ref int index, out IntPtr value);
    [DllImport("oleaut32.dll", ExactSpelling = true)] private static extern int SafeArrayDestroy(IntPtr array);

    // 20e17bc measured that Simple is unavailable directly on the actual WinRT
    // peer, while its public Fragment -> Simple route succeeds for that same
    // retained owner. Keep the direct failure and use exactly the already
    // measured public interface chain, never a guessed IID or replacement peer.
    // The returned Simple reference belongs to the caller; all intermediate
    // successful QI references are released here.
    internal static IntPtr AcquireSimpleThroughFragment(IntPtr actualPeer, IApi api,
        JsonObject receipt, Action<JsonObject>? progress = null)
    {
        var calls = new JsonArray(); var errors = new JsonArray(); var lifecycle = new JsonArray();
        receipt["source"] = "Actual retained peer QI(Fragment) then actual Fragment QI(Simple)";
        receipt["direct_simple_query_preserved"] = true; receipt["calls"] = calls;
        receipt["errors"] = errors; receipt["lifecycle"] = lifecycle; receipt["status"] = "unavailable";
        var direct = IntPtr.Zero; var fragment = IntPtr.Zero; var simple = IntPtr.Zero;
        bool directOwned = false, fragmentOwned = false, simpleOwned = false, transferred = false;
        bool Query(string name, IntPtr source, Guid iid, out IntPtr pointer, out bool owned)
        {
            progress?.Invoke(new JsonObject { ["api"] = name, ["status"] = "pending" });
            pointer = IntPtr.Zero; owned = false;
            var hr = api.Query(source, iid, out pointer);
            var step = AutomationIdentityNative.HResult(name, hr);
            step["source_pointer"] = AutomationIdentityNative.Pointer(source);
            step["iid"] = iid.ToString(); step["returned_pointer"] = AutomationIdentityNative.Pointer(pointer);
            calls.Add(step); progress?.Invoke((JsonObject)step.DeepClone());
            owned = hr >= 0 && pointer != IntPtr.Zero;
            if (!owned)
            {
                errors.Add(new JsonObject { ["api"] = name, ["hresult"] = hr,
                    ["hresult_hex"] = "0x" + unchecked((uint)hr).ToString("X8"),
                    ["returned_pointer"] = AutomationIdentityNative.Pointer(pointer),
                    ["failure"] = hr < 0 ? "Actual public QueryInterface failed" : "Successful QueryInterface returned null",
                    ["failed_pointer_ownership_unknown"] = hr < 0 && pointer != IntPtr.Zero });
            }
            return owned;
        }
        void Release(IntPtr pointer, bool owned, string name)
        {
            if (!owned) return;
            try { lifecycle.Add(new JsonObject { ["api"] = "IUnknown.Release", ["owner"] = name,
                ["pointer"] = AutomationIdentityNative.Pointer(pointer), ["remaining_references"] = api.Release(pointer) }); }
            catch (Exception ex) { errors.Add(new JsonObject { ["api"] = "Release " + name, ["error"] = ex.ToString(), ["hresult"] = ex.HResult }); }
        }
        try
        {
            // This result is diagnostic, not silently retried or discarded.
            // Even if it succeeds, use the same public route as the held-ID read.
            Query("QI(IRawElementProviderSimple, actual peer direct)", actualPeer, AutomationIdentityNative.SimpleId, out direct, out directOwned);
            if (!Query("QI(IRawElementProviderFragment, actual peer)", actualPeer, AutomationIdentityNative.FragmentId, out fragment, out fragmentOwned))
                return IntPtr.Zero;
            if (!Query("QI(IRawElementProviderSimple, actual fragment)", fragment, AutomationIdentityNative.SimpleId, out simple, out simpleOwned))
                return IntPtr.Zero;
            receipt["status"] = "acquired-through-actual-fragment";
            receipt["simple_pointer"] = AutomationIdentityNative.Pointer(simple);
            receipt["simple_reference_transferred_to_caller"] = true; transferred = true;
            return simple;
        }
        catch (Exception ex)
        {
            errors.Add(new JsonObject { ["api"] = "Acquire public Simple through actual Fragment", ["error"] = ex.ToString(), ["hresult"] = ex.HResult });
            return IntPtr.Zero;
        }
        finally
        {
            if (!transferred) Release(simple, simpleOwned, "untransferred Fragment Simple QI");
            Release(fragment, fragmentOwned, "actual peer Fragment QI");
            Release(direct, directOwned, "direct peer Simple QI diagnostic");
        }
    }

    // The caller owns simple. SAFEARRAYGetElement AddRefs VT_UNKNOWN values;
    // release each copied reference separately from destruction of its array.
    internal static JsonObject Read(IntPtr simple, IApi api, Action<JsonObject>? progress = null)
    {
        var calls = new JsonArray(); var errors = new JsonArray(); var lifecycle = new JsonArray();
        var result = new JsonObject { ["source"] = "Actual in-process public COM provider vtables and SAFEARRAY values",
            ["status"] = "unavailable", ["simple_pointer"] = AutomationIdentityNative.Pointer(simple),
            ["calls"] = calls, ["errors"] = errors, ["lifecycle"] = lifecycle,
            ["coordinate_space"] = "Unmodified ITextRangeProvider.GetBoundingRectangles screen-coordinate doubles",
            ["canonical_geometry_supplied"] = false, ["provider_errors_resolved"] = false };
        void Trace(string operation, string status, JsonNode? value = null) => progress?.Invoke(new JsonObject
        { ["api"] = operation, ["status"] = status, ["qpc"] = Stopwatch.GetTimestamp(), ["result"] = value?.DeepClone() });
        void Check(string operation, int hr)
        {
            var call = AutomationIdentityNative.HResult(operation, hr); calls.Add(call); Trace(operation, hr < 0 ? "failed" : "completed", call);
            if (hr < 0) throw new COMException(operation, hr);
        }
        void Fail(string operation, Exception ex) => errors.Add(new JsonObject { ["api"] = operation,
            ["exception_type"] = ex.GetType().FullName, ["hresult"] = ex.HResult, ["error"] = ex.ToString() });
        void Release(IntPtr pointer, string owner)
        {
            if (pointer == IntPtr.Zero) return;
            try { lifecycle.Add(new JsonObject { ["api"] = "IUnknown.Release", ["owner"] = owner,
                ["pointer"] = AutomationIdentityNative.Pointer(pointer), ["remaining_references"] = api.Release(pointer) }); }
            catch (Exception ex) { Fail("Release " + owner, ex); }
        }
        void Destroy(IntPtr array, string owner)
        {
            if (array == IntPtr.Zero) return;
            try { Check("SafeArrayDestroy " + owner, api.Destroy(array)); }
            catch (Exception ex) { Fail("Destroy " + owner, ex); }
        }
        (int lower, int upper) Bounds(IntPtr array, ushort expectedType, uint expectedSize, JsonObject record)
        {
            record["is_null"] = array == IntPtr.Zero;
            if (array == IntPtr.Zero) throw new InvalidOperationException("Provider returned a null SAFEARRAY");
            var dimensions = api.Dimensions(array); var elementSize = api.ElementSize(array);
            Check("SafeArrayGetVartype", api.ArrayType(array, out var type));
            record["dimensions"] = dimensions; record["element_size"] = elementSize; record["vartype"] = type;
            if (dimensions != 1 || type != expectedType || elementSize != expectedSize)
                throw new InvalidOperationException("SAFEARRAY shape/type does not match the public provider ABI");
            Check("SafeArrayGetLBound", api.Lower(array, out var lower)); Check("SafeArrayGetUBound", api.Upper(array, out var upper));
            record["lower_bound"] = lower; record["upper_bound"] = upper;
            var count = (long)upper - lower + 1; record["element_count"] = count;
            if (count < 0 || count > 1000000) throw new InvalidOperationException("Invalid or unbounded diagnostic SAFEARRAY size");
            return (lower, upper);
        }
        string? Text(IntPtr range, string path, JsonObject record)
        {
            var bstr = IntPtr.Zero;
            try
            {
                Trace(path + ".GetText(-1)", "pending"); Check(path + ".GetText(-1)", api.Text(range, out bstr));
                var length = api.StringLength(bstr);
                record["bstr"] = new JsonObject { ["pointer_is_null"] = bstr == IntPtr.Zero,
                    ["sys_string_len"] = length, ["source"] = "SysStringLen on the actual successful GetText BSTR" };
                Trace(path + ".SysStringLen", "observed", record["bstr"]);
                var text = api.String(bstr); record["text"] = Utf16(text);
                if ((bstr == IntPtr.Zero && length != 0) || (bstr != IntPtr.Zero && (text == null || text.Length != length)))
                    throw new InvalidOperationException("Actual BSTR length differs from its UTF16 projection");
                return text;
            }
            finally { if (bstr != IntPtr.Zero) api.FreeString(bstr); }
        }
        JsonObject Endpoint(IntPtr range, IntPtr document, int endpoint, string path)
        {
            var value = new JsonObject { ["endpoint"] = endpoint, ["source"] = "DocumentRange.Clone + MoveEndpointByRange + CompareEndpoints + actual prefix GetText UTF16 length" };
            var prefix = IntPtr.Zero;
            try
            {
                Trace(path + ".Clone", "pending"); Check(path + ".Clone", api.Clone(document, out prefix));
                if (prefix == IntPtr.Zero) throw new InvalidOperationException("Clone returned no actual range");
                Check(path + ".MoveEndpointByRange", api.Move(prefix, 1, range, endpoint));
                Check(path + ".CompareEnd", api.Compare(prefix, 1, range, endpoint, out var end));
                Check(path + ".CompareStart", api.Compare(prefix, 0, document, 0, out var start));
                Check(path + ".ComparePrefixStartToEnd", api.Compare(prefix, 0, prefix, 1, out var collapsed));
                value["end_compare"] = end; value["start_compare"] = start; value["prefix_start_to_end_compare"] = collapsed;
                var text = Text(prefix, path + ".prefix", value);
                // SysStringLen(null) is specified as zero. Preserve the actual
                // null BSTR; only an independently collapsed prefix can use it
                // as a measured zero offset, never a failed/missing GetText.
                // https://learn.microsoft.com/en-us/windows/win32/api/oleauto/nf-oleauto-sysstringlen
                var measuredNullPrefix = text == null && value["bstr"]?["pointer_is_null"]?.GetValue<bool>() == true
                    && value["bstr"]?["sys_string_len"]?.GetValue<uint>() == 0 && collapsed == 0;
                value["null_bstr_collapsed_prefix"] = measuredNullPrefix;
                int? measuredLength = text != null ? text.Length : measuredNullPrefix ? 0 : null;
                value["verified_prefix_utf16_length"] = start == 0 && end == 0 ? measuredLength : null;
            }
            catch (Exception ex) { Fail(path, ex); value["error"] = ex.ToString(); }
            finally { Release(prefix, path + " prefix"); }
            return value;
        }
        JsonObject Range(IntPtr range, IntPtr document, string? documentText, string path)
        {
            var value = new JsonObject { ["range_path"] = path, ["pointer"] = AutomationIdentityNative.Pointer(range),
                ["started_qpc"] = Stopwatch.GetTimestamp(), ["canonical_geometry_supplied"] = false };
            var array = IntPtr.Zero;
            try
            {
                var text = Text(range, path, value);
                // Bind the actual source endpoints before geometry. A failed
                // rectangle getter must not erase the independently read span.
                if (document != IntPtr.Zero)
                {
                    var start = Endpoint(range, document, 0, path + ".start"); var end = Endpoint(range, document, 1, path + ".end");
                    value["start"] = start; value["end"] = end;
                    if (start["verified_prefix_utf16_length"] is JsonValue sv && end["verified_prefix_utf16_length"] is JsonValue ev
                        && sv.TryGetValue<int>(out var s) && ev.TryGetValue<int>(out var e) && documentText != null && text != null)
                    {
                        var within = s >= 0 && e >= s && e <= documentText.Length;
                        value["offsets_within_document_snapshot"] = within;
                        value["text_matches_document_snapshot_slice"] = within && string.Equals(documentText.Substring(s, e - s), text, StringComparison.Ordinal);
                    }
                }
                Trace(path + ".GetBoundingRectangles", "pending"); Check(path + ".GetBoundingRectangles", api.Rectangles(range, out array));
                var metadata = new JsonObject(); value["safearray"] = metadata;
                var (lower, upper) = Bounds(array, 5 /* VT_R8 */, sizeof(double), metadata);
                var numbers = new JsonArray(); var bits = new JsonArray(); value["bounding_rectangle_values"] = numbers;
                value["bounding_rectangle_value_bits_hex"] = bits;
                for (long index = lower; index <= upper; index++)
                {
                    Check("SafeArrayGetElement(VT_R8)", api.Double(array, checked((int)index), out var number));
                    numbers.Add(double.IsFinite(number) ? JsonValue.Create(number) : null);
                    bits.Add(unchecked((ulong)BitConverter.DoubleToInt64Bits(number)).ToString("X16"));
                }
                value["rectangle_value_count"] = numbers.Count; value["rectangle_count"] = numbers.Count % 4 == 0 ? numbers.Count / 4 : null;
                value["all_rectangle_values_finite"] = numbers.All(item => item != null);
                if (numbers.Count % 4 != 0) throw new InvalidOperationException("Actual rectangle array is not a multiple of four");
            }
            catch (Exception ex) { Fail(path, ex); value["error"] = ex.ToString(); }
            finally { Destroy(array, path + " rectangles"); value["completed_qpc"] = Stopwatch.GetTimestamp(); Trace(path, "observed", value); }
            return value;
        }
        void CaptureFormats(IntPtr parent, IntPtr document, string? documentText, string path, JsonObject parentValue)
        {
            var ranges = new JsonArray(); parentValue["format_runs"] = ranges;
            var enumeration = new JsonObject
            {
                ["source"] = "Actual COM Clone/MoveEndpointByRange/MoveEndpointByUnit(End, Format, 1)/CompareEndpoints",
                ["status"] = "incomplete", ["maximum_runs"] = 10000, ["complete"] = false
            };
            parentValue["format_enumeration"] = enumeration;
            var cursor = IntPtr.Zero;
            int Compare(IntPtr left, int leftEndpoint, IntPtr right, int rightEndpoint, string operation)
            {
                Check(operation, api.Compare(left, leftEndpoint, right, rightEndpoint, out var compared));
                Trace(operation, "observed", new JsonObject { ["comparison"] = compared });
                return compared;
            }
            try
            {
                var pathPrefix = path + ".format_enumeration";
                var parentOrder = Compare(parent, 0, parent, 1, pathPrefix + ".CompareParentStartToEnd");
                enumeration["parent_start_vs_end"] = parentOrder;
                if (parentOrder > 0) throw new InvalidOperationException("COM parent text range has reversed endpoints");
                Check(pathPrefix + ".Clone", api.Clone(parent, out cursor));
                enumeration["cursor_pointer"] = AutomationIdentityNative.Pointer(cursor);
                if (cursor == IntPtr.Zero) throw new InvalidOperationException("Format Clone returned no actual cursor");
                Check(pathPrefix + ".CollapseEndToStart", api.Move(cursor, 1, cursor, 0));
                while (true)
                {
                    var runPath = path + ".format_runs[" + ranges.Count + "]";
                    var remaining = Compare(cursor, 0, parent, 1, runPath + ".CompareStartToParentEnd");
                    enumeration["final_start_vs_parent_end"] = remaining;
                    if (remaining == 0) { enumeration["complete"] = true; enumeration["status"] = "observed"; break; }
                    if (remaining > 0) throw new InvalidOperationException("COM format cursor advanced beyond its parent range");
                    if (ranges.Count >= 10000) throw new InvalidOperationException("COM format enumeration exceeded 10000 runs; coverage is incomplete");
                    var previous = IntPtr.Zero;
                    try
                    {
                        Check(runPath + ".ClonePrevious", api.Clone(cursor, out previous));
                        if (previous == IntPtr.Zero) throw new InvalidOperationException("Previous format Clone returned no actual range");
                        Check(runPath + ".MoveEndpointByUnit(End,Format,1)", api.MoveUnit(cursor, 1, 1 /* TextUnit_Format */, 1, out var moved));
                        var step = new JsonObject { ["index"] = ranges.Count, ["units_moved"] = moved,
                            ["cursor_pointer"] = AutomationIdentityNative.Pointer(cursor), ["previous_pointer"] = AutomationIdentityNative.Pointer(previous) };
                        var beyond = Compare(cursor, 1, parent, 1, runPath + ".CompareEndToParentEndBeforeClamp");
                        step["end_vs_parent_end_before_clamp"] = beyond;
                        if (beyond > 0) Check(runPath + ".ClampEndToParentEnd", api.Move(cursor, 1, parent, 1));
                        var startUnchanged = Compare(cursor, 0, previous, 0, runPath + ".CompareStartToPreviousStart");
                        var endAdvanced = Compare(cursor, 1, previous, 1, runPath + ".CompareEndToPreviousEnd");
                        var nondegenerate = Compare(cursor, 0, cursor, 1, runPath + ".CompareStartToEnd");
                        var endInside = Compare(cursor, 1, parent, 1, runPath + ".CompareEndToParentEndAfterClamp");
                        step["start_vs_previous_start"] = startUnchanged; step["end_vs_previous_end"] = endAdvanced;
                        step["start_vs_end"] = nondegenerate; step["end_vs_parent_end_after_clamp"] = endInside;
                        Trace(runPath + ".format_step", "observed", step);
                        // Retain the actual bad step/range as well. It may not
                        // establish complete coverage, but never becomes fake
                        // geometry or a silently skipped interval.
                        var item = Range(cursor, document, documentText, runPath);
                        item["format_step"] = step; ranges.Add(item);
                        if (moved <= 0 || startUnchanged != 0 || endAdvanced <= 0 || nondegenerate >= 0 || endInside > 0)
                            throw new InvalidOperationException("COM format step did not produce an advancing nondegenerate range with unchanged start inside its parent");
                        Check(runPath + ".MoveStartToEnd", api.Move(cursor, 0, cursor, 1));
                    }
                    finally { Release(previous, runPath + " previous range"); }
                }
            }
            catch (Exception ex) { Fail(path + ".format_enumeration", ex); enumeration["error"] = ex.ToString(); }
            finally
            {
                enumeration["observed_run_count"] = ranges.Count;
                Release(cursor, path + " format cursor"); Trace(path + ".format_enumeration", enumeration["status"]!.ToString(), enumeration);
            }
        }

        var pattern = IntPtr.Zero; var provider = IntPtr.Zero; var document = IntPtr.Zero; var visible = IntPtr.Zero;
        try
        {
            Trace("IRawElementProviderSimple.GetPatternProvider(Text)", "pending");
            Check("IRawElementProviderSimple.GetPatternProvider(Text)", api.Pattern(simple, out pattern));
            result["pattern_pointer"] = AutomationIdentityNative.Pointer(pattern);
            if (pattern == IntPtr.Zero) { result["unavailable_reason"] = "Actual GetPatternProvider(Text) returned null"; return result; }
            Check("QI(ITextProvider)", api.Query(pattern, TextProviderId, out provider));
            if (provider == IntPtr.Zero) throw new InvalidOperationException("QI(ITextProvider) returned null");
            result["provider_pointer"] = AutomationIdentityNative.Pointer(provider);
            Trace("ITextProvider.DocumentRange", "pending"); Check("ITextProvider.DocumentRange", api.Document(provider, out document));
            if (document == IntPtr.Zero) throw new InvalidOperationException("DocumentRange returned null");
            var before = new JsonObject(); var documentText = Text(document, "document-before", before); result["document_text_before"] = before;
            result["document_range"] = Range(document, document, documentText, "document_range");
            Trace("ITextProvider.GetVisibleRanges", "pending"); Check("ITextProvider.GetVisibleRanges", api.Visible(provider, out visible));
            var visibleMetadata = new JsonObject(); result["visible_safearray"] = visibleMetadata;
            var (lower, upper) = Bounds(visible, 13 /* VT_UNKNOWN */, (uint)IntPtr.Size, visibleMetadata);
            var ranges = new JsonArray(); result["visible_ranges"] = ranges;
            for (long index = lower; index <= upper; index++)
            {
                var unknown = IntPtr.Zero; var range = IntPtr.Zero;
                try
                {
                    Check("SafeArrayGetElement(VT_UNKNOWN)", api.Unknown(visible, checked((int)index), out unknown));
                    if (unknown == IntPtr.Zero) throw new InvalidOperationException("Actual visible range element is null");
                    Check("QI(ITextRangeProvider)", api.Query(unknown, TextRangeProviderId, out range));
                    if (range == IntPtr.Zero) throw new InvalidOperationException("QI(ITextRangeProvider) returned null");
                    var item = Range(range, document, documentText, "visible_ranges[" + (index - lower) + "]");
                    item["safearray_index"] = index; ranges.Add(item);
                    CaptureFormats(range, document, documentText, "visible_ranges[" + (index - lower) + "]", item);
                }
                catch (Exception ex) { Fail("visible range " + index, ex); ranges.Add(new JsonObject { ["safearray_index"] = index, ["error"] = ex.ToString() }); }
                finally { Release(range, "visible ITextRangeProvider"); Release(unknown, "copied visible SAFEARRAY IUnknown"); }
            }
            var after = new JsonObject(); var afterText = Text(document, "document-after", after); result["document_text_after"] = after;
            result["document_text_same_before_after"] = documentText != null && afterText != null ? string.Equals(documentText, afterText, StringComparison.Ordinal) : null;
            result["status"] = errors.Count == 0 ? "observed" : "observed-with-errors";
        }
        catch (Exception ex) { Fail("Read actual public COM text provider", ex); }
        finally
        {
            Destroy(visible, "visible ranges"); Release(document, "DocumentRange"); Release(provider, "QI ITextProvider"); Release(pattern, "GetPatternProvider IUnknown");
            if (errors.Count != 0 && result["status"]?.ToString() == "observed") result["status"] = "observed-with-errors";
        }
        return result;
    }

    internal static JsonObject Utf16(string? text)
    {
        if (text == null) return new JsonObject { ["is_null"] = true };
        // Encoding.Unicode's replacement fallback would lose lone surrogates.
        var bytes = new byte[checked(text.Length * 2)];
        for (var i = 0; i < text.Length; i++) { bytes[i * 2] = (byte)text[i]; bytes[i * 2 + 1] = (byte)(text[i] >> 8); }
        return new JsonObject { ["is_null"] = false, ["utf16_length"] = text.Length, ["utf16_le_base64"] = Convert.ToBase64String(bytes) };
    }
}
