using System.Globalization;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Automation.Text;

// System.Windows.Automation replaces every native rectangle whose width OR
// height is <= 0 with Rect.Empty. Its +/-Infinity values therefore do not prove
// that the provider returned infinities. Read the COM SAFEARRAY before that
// lossy projection. Never recover a range by searching its text or screen box.
internal sealed class NativeTextEvidence(int processId, double originX, double originY, CaptureProgress progress)
{
    private readonly IAutomation automation = (IAutomation)Activator.CreateInstance(
        Type.GetTypeFromCLSID(new Guid("ff48dba4-60ef-4201-aa87-54103eef594e"), throwOnError: true)!)!;
    private readonly Dictionary<IntPtr, WindowIndex> indexes = new();
    private JsonObject? activeContext;

    private sealed class WindowIndex
    {
        public readonly Dictionary<string, INativeElement> Elements = new(StringComparer.Ordinal);
        public readonly Dictionary<string, JsonObject> Observations = new(StringComparer.Ordinal);
        public readonly JsonArray TraversalErrors = new();
        public readonly JsonObject Evidence = new() { ["status"] = "incomplete", ["source"] = "One actual IUIAutomation.RawViewWalker HWND subtree enumeration" };
        public Exception? Error;
    }

    public void Attach(AutomationElement managedElement, TextPattern managedPattern, JsonObject pattern, JsonArray errors)
    {
        var evidence = new JsonObject
        {
            ["source"] = "IUIAutomationTextRange.GetBoundingRectangles COM SAFEARRAY<double>; before the .NET Rect[] projection",
            ["status"] = "incomplete", ["range_identity_basis"] = "Same RuntimeId, stable full document text, and unique exact document-prefix endpoints"
        };
        pattern["native_com"] = evidence;
        var watch = Stopwatch.StartNew();
        try
        {
            var runtimeId = managedElement.GetRuntimeId();
            evidence["runtime_id"] = Ints(runtimeId);
            activeContext = new JsonObject { ["runtime_id"] = Ints(runtimeId) };
            progress.Record("uia-capture/native/attach", "started", activeContext);
            var lookup = new JsonObject(); evidence["lookup"] = lookup;
            var element = progress.Measure("uia-capture/native/resolve", () => Resolve(managedElement, runtimeId, lookup), activeContext);
            var nativePattern = progress.Measure("uia-capture/native/text-pattern", () => (INativeTextPattern)element.GetCurrentPattern(TextPattern.Pattern.Id), activeContext);
            var document = progress.Measure("uia-capture/native/document-range", nativePattern.GetDocumentRange, activeContext);
            var documentText = progress.Measure("uia-capture/native/document-text-before", () => document.GetText(-1), activeContext);
            evidence["document_text_before"] = documentText;
            var nativeDocument = ReadRange(document, document, false, errors);
            evidence["document"] = nativeDocument;
            var visible = new JsonArray(); evidence["visible_ranges"] = visible;
            var nativeRanges = progress.Measure("uia-capture/native/visible-ranges", nativePattern.GetVisibleRanges, activeContext);
            var rangeCount = nativeRanges.GetLength();
            if (rangeCount < 0 || rangeCount > 10000) throw new InvalidOperationException("Invalid COM visible range count: " + rangeCount);
            for (var index = 0; index < rangeCount; index++)
            {
                progress.Record("uia-capture/native/visible-range", "started", new JsonObject { ["runtime_id"] = Ints(runtimeId), ["index"] = index });
                visible.Add(ReadRange(nativeRanges.GetElement(index), document, true, errors));
            }

            var nativeAfter = progress.Measure("uia-capture/native/document-text-after", () => document.GetText(-1), activeContext);
            var managedAfter = progress.Measure("uia-capture/managed/document-text-after", () => managedPattern.DocumentRange.GetText(-1), activeContext);
            evidence["document_text_after"] = nativeAfter;
            evidence["managed_document_text_after"] = managedAfter;
            var capturedText = pattern["document"]?["text"]?.GetValue<string>();
            if (documentText != nativeAfter || documentText != managedAfter || documentText != capturedText)
                throw new InvalidOperationException("Managed/COM document changed or differs; range identities cannot be established.");
            if (!runtimeId.SequenceEqual(managedElement.GetRuntimeId()) || !runtimeId.SequenceEqual(element.GetRuntimeId()))
                throw new InvalidOperationException("RuntimeId changed while reading text evidence.");
            if (managedElement.Current.ProcessId != processId ||
                Convert.ToInt32(element.GetCurrentPropertyValue(AutomationElement.ProcessIdProperty.Id), CultureInfo.InvariantCulture) != processId)
                throw new InvalidOperationException("Process identity changed while reading text evidence.");

            // Check the entire correspondence before replacing any managed box.
            // Prefixes are obtained through MoveEndpointByRange/GetText on the
            // actual ranges; repeating text elsewhere in the document cannot
            // create a substitute range. Duplicate endpoint keys still fail.
            var pairs = new List<(JsonObject Managed, JsonObject Native)>();
            Pair(pattern["document"]!.AsObject(), nativeDocument, pairs);
            PairLists(pattern["visible_ranges"]!.AsArray(), visible, pairs);
            foreach (var pair in pairs) VerifyProjection(pair.Managed, pair.Native);
            foreach (var (managed, native) in pairs)
            {
                managed["bounds"] = native["bounds"]!.DeepClone();
                managed["bounds_source"] = "Same uniquely identified native COM range; all returned rectangles retained";
                managed["bounds_status"] = native["bounds_status"]!.DeepClone();
                managed["native_bounds_raw"] = native["bounds_raw"]!.DeepClone();
                managed["native_range_identity"] = native["range_identity"]!.DeepClone();
                managed["native_is_hidden"] = native["is_hidden"]?.DeepClone();
            }
            evidence["status"] = "matched-to-managed-ranges";
            evidence["matched_range_count"] = pairs.Count;
        }
        catch (Exception error)
        {
            evidence["error"] = error.GetType().Name + ": " + error.Message;
            errors.Add("Native COM text evidence: " + evidence["error"]!.ToString());
        }
        finally
        {
            evidence["duration_ms"] = watch.Elapsed.TotalMilliseconds;
            progress.Record("uia-capture/native/attach", evidence["status"]!.GetValue<string>(), new JsonObject { ["evidence"] = evidence.DeepClone() });
            activeContext = null;
        }
    }

    private INativeElement Resolve(AutomationElement managed, int[] runtimeId, JsonObject evidence)
    {
        var watch = Stopwatch.StartNew();
        var ancestor = managed; var hwnd = IntPtr.Zero;
        for (var depth = 0; ancestor != null && depth < 1000; depth++)
        {
            if (ancestor.Current.ProcessId != processId) break;
            var handle = ancestor.Current.NativeWindowHandle;
            if (handle != 0) { hwnd = new IntPtr(handle); break; }
            ancestor = TreeWalker.RawViewWalker.GetParent(ancestor);
        }
        if (hwnd == IntPtr.Zero) throw new InvalidOperationException("No same-process HWND ancestor for native RuntimeId lookup.");
        evidence["hwnd"] = hwnd.ToInt64();
        evidence["ancestor_lookup_ms"] = watch.Elapsed.TotalMilliseconds;
        var cached = indexes.TryGetValue(hwnd, out var index);
        evidence["index_cache_hit"] = cached;
        if (!cached)
        {
            index = new WindowIndex();
            // Cache failed/incomplete enumeration too: retrying it for each text
            // node multiplies provider stalls and cannot establish completeness.
            indexes.Add(hwnd, index);
            BuildIndex(hwnd, index);
        }
        evidence["index"] = index!.Evidence.DeepClone();
        if (index.Error != null) throw new InvalidOperationException("Native HWND index is incomplete; identity cannot be established.", index.Error);
        if (runtimeId.Length == 0) throw new InvalidOperationException("Managed RuntimeId is empty.");
        var foundMatch = index.Elements.TryGetValue(RuntimeKey(runtimeId), out var found);
        evidence["match_count"] = foundMatch ? 1 : 0;
        progress.Record("uia-capture/native/index/lookup", "measured", new JsonObject { ["runtime_id"] = Ints(runtimeId), ["lookup"] = evidence.DeepClone() });
        if (!foundMatch) throw new InvalidOperationException("RuntimeId is absent from the completed native raw HWND index.");
        var freshWatch = Stopwatch.StartNew();
        if (!found!.GetRuntimeId().SequenceEqual(runtimeId) || Convert.ToInt32(found.GetCurrentPropertyValue(AutomationElement.ProcessIdProperty.Id), CultureInfo.InvariantCulture) != processId ||
            !managed.GetRuntimeId().SequenceEqual(runtimeId) || managed.Current.ProcessId != processId)
            throw new InvalidOperationException("Native element identity/process does not equal the managed observation.");
        evidence["fresh_identity_check_ms"] = freshWatch.Elapsed.TotalMilliseconds;
        evidence["duration_ms"] = watch.Elapsed.TotalMilliseconds;
        return found;
    }

    private static string RuntimeKey(int[] runtimeId) => string.Join(".", runtimeId);

    private void BuildIndex(IntPtr hwnd, WindowIndex index)
    {
        var watch = Stopwatch.StartNew();
        var context = new JsonObject { ["hwnd"] = hwnd.ToInt64() };
        progress.Record("uia-capture/native/index", "started", context);
        try
        {
            var root = progress.Measure("uia-capture/native/index/root", () => automation.ElementFromHandle(hwnd), context);
            var walker = progress.Measure("uia-capture/native/index/raw-walker", automation.GetRawViewWalker, context);
            Visit(root, 0, null);
            index.Evidence["status"] = index.Error == null ? "complete" : "incomplete";

            void Visit(INativeElement element, int depth, int[]? parentRuntimeId)
            {
                if (depth > 1000 || index.Elements.Count >= 100000)
                    throw new InvalidOperationException("Native raw tree exceeded the traversal safety bound; index is incomplete.");
                var stage = new JsonObject { ["hwnd"] = hwnd.ToInt64(), ["depth"] = depth, ["indexed_nodes"] = index.Elements.Count,
                    ["parent_runtime_id"] = parentRuntimeId == null ? null : Ints(parentRuntimeId) };
                progress.Record("uia-capture/native/index/node", "started", stage);
                var pid = Convert.ToInt32(element.GetCurrentPropertyValue(AutomationElement.ProcessIdProperty.Id), CultureInfo.InvariantCulture);
                if (pid != processId)
                    throw new InvalidOperationException("Native raw HWND subtree exposed a different process; index is incomplete.");
                var runtimeId = element.GetRuntimeId();
                stage["runtime_id"] = Ints(runtimeId);
                if (runtimeId.Length == 0) throw new InvalidOperationException("Native raw tree contains an empty RuntimeId.");
                var key = RuntimeKey(runtimeId);
                if (!index.Elements.TryAdd(key, element))
                {
                    index.Evidence["duplicate_runtime_id"] = Ints(runtimeId);
                    var duplicate = new JsonObject
                    {
                        ["kind"] = "duplicate-runtime-id", ["first_observation"] = index.Observations[key].DeepClone(),
                        ["repeated_edge"] = stage.DeepClone(), ["first_element_current"] = DescribeElement(index.Elements[key]),
                        ["repeated_element_current"] = DescribeElement(element),
                        ["diagnostic"] = "The repeated edge is not recursively entered; index remains incomplete and no lookup is accepted. Other sibling branches are still measured."
                    };
                    index.TraversalErrors.Add(duplicate);
                    index.Error ??= new InvalidOperationException("Native raw tree contains a duplicate RuntimeId; no element is chosen and index is incomplete.");
                    progress.Record("uia-capture/native/index/duplicate", "failed", duplicate);
                    return;
                }
                index.Observations.Add(key, stage.DeepClone().AsObject());
                progress.Record("uia-capture/native/index/node", "indexed", stage);
                var child = progress.Measure("uia-capture/native/index/first-child", () => walker.GetFirstChildElement(element), stage);
                var siblingIds = new HashSet<string>(StringComparer.Ordinal);
                while (child != null)
                {
                    var childRuntimeId = child.GetRuntimeId();
                    if (!siblingIds.Add(RuntimeKey(childRuntimeId)))
                    {
                        var cycle = new JsonObject { ["kind"] = "repeated-sibling-edge", ["parent_runtime_id"] = Ints(runtimeId),
                            ["child_runtime_id"] = Ints(childRuntimeId), ["child_current"] = DescribeElement(child),
                            ["diagnostic"] = "Sibling enumeration would revisit the same RuntimeId; this branch is incomplete." };
                        index.TraversalErrors.Add(cycle);
                        index.Error ??= new InvalidOperationException("Native raw tree contains a repeated sibling RuntimeId; index is incomplete.");
                        progress.Record("uia-capture/native/index/sibling-cycle", "failed", cycle);
                        break;
                    }
                    Visit(child, depth + 1, runtimeId);
                    var current = child;
                    child = progress.Measure("uia-capture/native/index/next-sibling", () => walker.GetNextSiblingElement(current), stage);
                }
            }
        }
        catch (Exception error)
        {
            index.Error = error;
            index.Evidence["error"] = error.ToString();
        }
        finally
        {
            index.Evidence["node_count"] = index.Elements.Count;
            index.Evidence["traversal_errors"] = index.TraversalErrors;
            index.Evidence["duration_ms"] = watch.Elapsed.TotalMilliseconds;
            index.Evidence["hwnd"] = hwnd.ToInt64();
            progress.Record("uia-capture/native/index", index.Evidence["status"]!.GetValue<string>(), index.Evidence);
        }
    }

    private static JsonObject DescribeElement(INativeElement element)
    {
        var result = new JsonObject();
        foreach (var (name, property) in new[]
        {
            ("process_id", AutomationElement.ProcessIdProperty), ("class_name", AutomationElement.ClassNameProperty),
            ("control_type", AutomationElement.ControlTypeProperty), ("name", AutomationElement.NameProperty),
            ("bounds_screen", AutomationElement.BoundingRectangleProperty), ("offscreen", AutomationElement.IsOffscreenProperty)
        })
        {
            try { result[name] = NativeProperty(element.GetCurrentPropertyValue(property.Id)); }
            catch (Exception error) { result[name] = new JsonObject { ["status"] = "error", ["error"] = error.ToString() }; }
        }
        try { result["runtime_id"] = Ints(element.GetRuntimeId()); }
        catch (Exception error) { result["runtime_id_error"] = error.ToString(); }
        return result;
    }

    private static JsonNode? NativeProperty(object? value) => value switch
    {
        null => null, string text => JsonValue.Create(text), bool flag => JsonValue.Create(flag),
        int integer => JsonValue.Create(integer), double number => Number(number),
        Array values => new JsonArray(values.Cast<object?>().Select(NativeProperty).ToArray()),
        _ => new JsonObject { ["status"] = "unsupported-native-property-value", ["managed_type"] = value.GetType().FullName }
    };

    public static JsonObject ManagedIdentity(TextPatternRange range, TextPatternRange document)
    {
        var beforeStart = document.Clone(); beforeStart.MoveEndpointByRange(TextPatternRangeEndpoint.End, range, TextPatternRangeEndpoint.Start);
        var beforeEnd = document.Clone(); beforeEnd.MoveEndpointByRange(TextPatternRangeEndpoint.End, range, TextPatternRangeEndpoint.End);
        return Identity(beforeStart.GetText(-1), beforeEnd.GetText(-1), range.GetText(-1),
            range.CompareEndpoints(TextPatternRangeEndpoint.Start, range, TextPatternRangeEndpoint.End) == 0,
            range.CompareEndpoints(TextPatternRangeEndpoint.Start, document, TextPatternRangeEndpoint.Start) >= 0 &&
            range.CompareEndpoints(TextPatternRangeEndpoint.End, document, TextPatternRangeEndpoint.End) <= 0);
    }

    private static JsonObject NativeIdentity(INativeTextRange range, INativeTextRange document)
    {
        var beforeStart = document.Clone(); beforeStart.MoveEndpointByRange(1, range, 0);
        var beforeEnd = document.Clone(); beforeEnd.MoveEndpointByRange(1, range, 1);
        return Identity(beforeStart.GetText(-1), beforeEnd.GetText(-1), range.GetText(-1),
            range.CompareEndpoints(0, range, 1) == 0,
            range.CompareEndpoints(0, document, 0) >= 0 && range.CompareEndpoints(1, document, 1) <= 0);
    }

    private static JsonObject Identity(string startPrefix, string endPrefix, string text, bool degenerate, bool contained)
    {
        var valid = contained && startPrefix + text == endPrefix && (degenerate == (startPrefix.Length == endPrefix.Length));
        return new JsonObject
        {
            ["start_prefix"] = startPrefix, ["end_prefix"] = endPrefix,
            ["start_utf16"] = startPrefix.Length, ["end_utf16"] = endPrefix.Length,
            ["degenerate"] = degenerate, ["within_document"] = contained,
            ["text_partition_valid"] = valid,
            ["source"] = "Actual document clone endpoints moved to this range by MoveEndpointByRange; GetText prefixes, not text search"
        };
    }

    private JsonObject ReadRange(INativeTextRange range, INativeTextRange document, bool includeRuns, JsonArray errors)
    {
        var result = new JsonObject
        {
            ["text"] = progress.Measure("uia-capture/native/range/text", () => range.GetText(-1), activeContext),
            ["range_identity"] = progress.Measure("uia-capture/native/range/identity", () => NativeIdentity(range, document), activeContext)
        };
        var values = progress.Measure("uia-capture/native/range/bounding-rectangles", range.GetBoundingRectangles, activeContext);
        result["bounds_raw"] = values == null ? null : new JsonArray(values.Select(Number).ToArray());
        result["bounds_raw_ieee754_bits"] = values == null ? null : new JsonArray(values.Select(value =>
            (JsonNode?)JsonValue.Create(BitConverter.DoubleToInt64Bits(value).ToString("X16", CultureInfo.InvariantCulture))).ToArray());
        result["raw_coordinate_space"] = "UI Automation screen coordinates before window-origin subtraction";
        progress.Record("uia-capture/native/range/raw-bounds", "measured", new JsonObject { ["runtime"] = activeContext?.DeepClone(), ["range"] = result.DeepClone() });
        var rectangles = new JsonArray(); result["bounds"] = rectangles;
        var statuses = new JsonArray(); result["rectangle_statuses"] = statuses;
        var degenerate = result["range_identity"]!["degenerate"]!.GetValue<bool>();
        var status = "measured";
        if (values == null || values.Length % 4 != 0)
        {
            status = "invalid-native-array";
            errors.Add("COM text range returned null or a SAFEARRAY length not divisible by four.");
        }
        else if (values.Length == 0)
        {
            status = degenerate ? "empty-array-degenerate-range" : "empty-array-nondegenerate-range";
            // An empty array does not say why the text has no visible bounds.
            if (!degenerate) errors.Add("COM nondegenerate text range has an empty rectangle array; visibility/coverage is unresolved.");
        }
        else for (var index = 0; index < values.Length; index += 4)
        {
            var x = values[index]; var y = values[index + 1]; var width = values[index + 2]; var height = values[index + 3];
            var finite = double.IsFinite(x) && double.IsFinite(y) && double.IsFinite(width) && double.IsFinite(height);
            var kind = !finite ? "provider-nonfinite" : width < 0 || height < 0 ? "negative-dimension" : width == 0 || height == 0 ? "zero-area" : "positive-area";
            statuses.Add(kind);
            rectangles.Add(new JsonObject { ["x"] = finite ? JsonValue.Create(x - originX) : null,
                ["y"] = finite ? JsonValue.Create(y - originY) : null, ["width"] = double.IsFinite(width) ? JsonValue.Create(width) : null,
                ["height"] = double.IsFinite(height) ? JsonValue.Create(height) : null });
            if (kind != "positive-area")
            {
                status = "contains-" + kind;
                errors.Add("COM text rectangle " + index / 4 + " is " + kind + "; original values retained, no inference that its text is hidden or covered.");
            }
        }
        result["bounds_status"] = status;
        try
        {
            var hidden = range.GetAttributeValue(TextPattern.IsHiddenAttribute.Id);
            result["is_hidden"] = hidden is bool flag ? JsonValue.Create(flag) : null;
            result["is_hidden_status"] = hidden is bool ? "measured" : "unsupported-or-mixed";
        }
        catch (Exception error) { result["is_hidden_status"] = "error"; result["is_hidden_error"] = error.Message; }
        if (includeRuns)
        {
            var runs = new JsonArray(); result["format_runs"] = runs;
            var cursor = range.Clone(); cursor.MoveEndpointByRange(1, cursor, 0); var count = 0;
            while (cursor.CompareEndpoints(0, range, 1) < 0)
            {
                if (++count > 10000) throw new InvalidOperationException("COM format range enumeration exceeded 10000 runs.");
                if (cursor.MoveEndpointByUnit(1, (int)TextUnit.Format, 1) == 0) throw new InvalidOperationException("COM format endpoint did not advance.");
                if (cursor.CompareEndpoints(1, range, 1) > 0) cursor.MoveEndpointByRange(1, range, 1);
                runs.Add(ReadRange(cursor, document, false, errors));
                cursor.MoveEndpointByRange(0, cursor, 1);
            }
        }
        return result;
    }

    private static string Key(JsonObject range)
    {
        var identity = range["range_identity"]!.AsObject();
        if (identity["text_partition_valid"]?.GetValue<bool>() != true)
            throw new InvalidOperationException("Range has ambiguous/non-text endpoint positions; cannot correlate native and managed ranges.");
        return new JsonArray(identity["start_prefix"]!.DeepClone(), identity["end_prefix"]!.DeepClone(),
            identity["degenerate"]!.DeepClone(), range["text"]!.DeepClone()).ToJsonString();
    }

    private static void Pair(JsonObject managed, JsonObject native, List<(JsonObject, JsonObject)> pairs)
    {
        if (Key(managed) != Key(native)) throw new InvalidOperationException("Managed/COM range endpoint identity differs.");
        pairs.Add((managed, native));
        if (managed["format_runs"] is JsonArray managedRuns && native["format_runs"] is JsonArray nativeRuns)
            PairLists(managedRuns, nativeRuns, pairs);
        else if (managed.ContainsKey("format_runs") != native.ContainsKey("format_runs"))
            throw new InvalidOperationException("Managed/COM format range coverage differs.");
    }

    private static void PairLists(JsonArray managed, JsonArray native, List<(JsonObject, JsonObject)> pairs)
    {
        if (managed.Count != native.Count) throw new InvalidOperationException("Managed/COM range counts differ.");
        var nativeByKey = new Dictionary<string, JsonObject>(StringComparer.Ordinal);
        foreach (var value in native.OfType<JsonObject>())
            if (!nativeByKey.TryAdd(Key(value), value)) throw new InvalidOperationException("COM ranges have duplicate logical endpoint identities.");
        var used = new HashSet<string>(StringComparer.Ordinal);
        foreach (var value in managed.OfType<JsonObject>())
        {
            var key = Key(value);
            if (!used.Add(key) || !nativeByKey.TryGetValue(key, out var counterpart))
                throw new InvalidOperationException("Managed range has no unique COM range with the same document endpoints.");
            Pair(value, counterpart, pairs);
        }
    }

    private void VerifyProjection(JsonObject managed, JsonObject native)
    {
        var observed = managed["managed_bounds"]!.AsArray();
        var values = native["bounds_raw"] as JsonArray;
        if (values == null || values.Count % 4 != 0 || observed.Count != values.Count / 4)
            throw new InvalidOperationException("COM and managed rectangle array shapes differ.");
        for (var index = 0; index < observed.Count; index++)
        {
            var raw = new double[4];
            for (var component = 0; component < 4; component++)
                if (values[index * 4 + component] is not JsonValue scalar || !scalar.TryGetValue<double>(out raw[component]) || !double.IsFinite(raw[component]))
                    throw new InvalidOperationException("Native COM rectangle is nonfinite; no managed conversion correspondence is asserted.");
            var box = observed[index]!.AsObject();
            var expectedEmpty = raw[2] <= 0 || raw[3] <= 0;
            if (box["is_empty"]!.GetValue<bool>() != expectedEmpty)
                throw new InvalidOperationException("Managed Rect.Empty does not match the measured COM width/height conversion.");
            if (!expectedEmpty)
            {
                var fields = new[] { "x", "y", "width", "height" };
                for (var component = 0; component < 4; component++)
                    if (box[fields[component]]!.GetValue<double>() != raw[component])
                        throw new InvalidOperationException("Managed/COM bounds changed during the paired observations.");
            }
        }
    }

    public static JsonObject ManagedRectangle(Rect rectangle) => new()
    {
        ["is_empty"] = rectangle.IsEmpty, ["x"] = Number(rectangle.X), ["y"] = Number(rectangle.Y),
        ["width"] = Number(rectangle.Width), ["height"] = Number(rectangle.Height),
        ["source"] = "Actual managed Rect; Rect.Empty may be the .NET projection of a finite zero/negative dimension"
    };

    private static JsonNode Number(double value) => double.IsFinite(value) ? JsonValue.Create(value)! : new JsonObject
    {
        ["ieee754"] = value.ToString("R", CultureInfo.InvariantCulture),
        ["bits_hex"] = BitConverter.DoubleToInt64Bits(value).ToString("X16", CultureInfo.InvariantCulture)
    };
    private static JsonArray Ints(IEnumerable<int> values) => new(values.Select(value => (JsonNode?)JsonValue.Create(value)).ToArray());

    // Vtable order and GUIDs are from Windows SDK UIAutomationClient.h. Unused
    // slots deliberately have no callable implementation and are never invoked.
    [ComImport, Guid("30cbe57d-d9d0-452a-ab13-7ac5ac4825ee"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IAutomation
    {
        void UnusedCompareElements(); void UnusedCompareRuntimeIds(); void UnusedGetRootElement();
        INativeElement ElementFromHandle(IntPtr hwnd);
        void UnusedElementFromPoint(); void UnusedGetFocusedElement(); void UnusedGetRootElementBuildCache();
        void UnusedElementFromHandleBuildCache(); void UnusedElementFromPointBuildCache(); void UnusedGetFocusedElementBuildCache();
        void UnusedCreateTreeWalker(); void UnusedControlViewWalker(); void UnusedContentViewWalker(); INativeTreeWalker GetRawViewWalker();
        void UnusedRawViewCondition(); void UnusedControlViewCondition(); void UnusedContentViewCondition();
        void UnusedCreateCacheRequest(); void UnusedCreateTrueCondition(); void UnusedCreateFalseCondition();
        INativeCondition CreatePropertyCondition(int propertyId, [MarshalAs(UnmanagedType.Struct)] object value);
    }
    [ComImport, Guid("4042c624-389c-4afc-a630-9df854a541fc"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface INativeTreeWalker
    {
        INativeElement? GetParentElement(INativeElement element);
        INativeElement? GetFirstChildElement(INativeElement element);
        // This slot exists between first-child and next-sibling in the SDK.
        // Omitting it calls GetLastChildElement when walking siblings, silently
        // truncating a HWND index to its first child's descendants.
        INativeElement? GetLastChildElement(INativeElement element);
        INativeElement? GetNextSiblingElement(INativeElement element);
    }
    [ComImport, Guid("d22108aa-8ac5-49a5-837b-37bbb3d7591e"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface INativeElement
    {
        void UnusedSetFocus();
        [return: MarshalAs(UnmanagedType.SafeArray, SafeArraySubType = VarEnum.VT_I4)] int[] GetRuntimeId();
        void UnusedFindFirst();
        INativeElementArray FindAll(int scope, INativeCondition condition);
        void UnusedFindFirstBuildCache(); void UnusedFindAllBuildCache(); void UnusedBuildUpdatedCache();
        [return: MarshalAs(UnmanagedType.Struct)] object GetCurrentPropertyValue(int propertyId);
        void UnusedGetCurrentPropertyValueEx(); void UnusedGetCachedPropertyValue(); void UnusedGetCachedPropertyValueEx();
        void UnusedGetCurrentPatternAs(); void UnusedGetCachedPatternAs();
        [return: MarshalAs(UnmanagedType.IUnknown)] object GetCurrentPattern(int patternId);
    }
    [ComImport, Guid("352ffba8-0973-437c-a61f-f64cafd81df9"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface INativeCondition { }
    [ComImport, Guid("14314595-b4bc-4055-95f2-58f2e42c9855"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface INativeElementArray { int GetLength(); INativeElement GetElement(int index); }
    [ComImport, Guid("32eba289-3583-42c9-9c59-3b6d9a1e9b6a"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface INativeTextPattern
    {
        void UnusedRangeFromPoint(); void UnusedRangeFromChild(); void UnusedGetSelection();
        INativeTextRangeArray GetVisibleRanges(); INativeTextRange GetDocumentRange();
    }
    [ComImport, Guid("ce4ae76a-e717-4c98-81ea-47371d028eb6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface INativeTextRangeArray { int GetLength(); INativeTextRange GetElement(int index); }
    [ComImport, Guid("a543cc6a-f4ae-494b-8239-c814481187a8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface INativeTextRange
    {
        INativeTextRange Clone(); void UnusedCompare();
        int CompareEndpoints(int sourceEndpoint, INativeTextRange target, int targetEndpoint);
        void UnusedExpandToEnclosingUnit(); void UnusedFindAttribute(); void UnusedFindText();
        [return: MarshalAs(UnmanagedType.Struct)] object GetAttributeValue(int attributeId);
        [return: MarshalAs(UnmanagedType.SafeArray, SafeArraySubType = VarEnum.VT_R8)] double[]? GetBoundingRectangles();
        void UnusedGetEnclosingElement();
        [return: MarshalAs(UnmanagedType.BStr)] string GetText(int maxLength);
        void UnusedMove();
        int MoveEndpointByUnit(int endpoint, int unit, int count);
        void MoveEndpointByRange(int sourceEndpoint, INativeTextRange target, int targetEndpoint);
    }
}
