using System.Globalization;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Automation.Text;

// This executable is an out-of-process, read-only UIA observer. In particular it
// does not instantiate WinUI peers or invoke/expand/collapse native controls.
// The app remains on its UI thread while this tool reads its providers.
internal static class Program
{
    [MTAThread]
    private static int Main(string[] args)
    {
        if (Environment.GetEnvironmentVariable("GITHUB_ACTIONS") != "true")
        {
            Console.Error.WriteLine("UI Automation capture is CI-only; no local app is inspected.");
            return 2;
        }

        string? requestPath = null, outputPath = null;
        for (var index = 0; index < args.Length; index++)
        {
            if (index + 1 >= args.Length) return Usage();
            switch (args[index])
            {
                case "--request": requestPath = args[++index]; break;
                case "--output": outputPath = args[++index]; break;
                default: return Usage();
            }
        }
        if (requestPath == null || outputPath == null) return Usage();

        JsonObject result;
        try
        {
            var request = JsonNode.Parse(File.ReadAllText(requestPath))!.AsObject();
            result = new Capture(request).Run();
        }
        catch (Exception error)
        {
            result = new JsonObject
            {
                ["schema_version"] = 1,
                ["raw_nodes"] = new JsonArray(),
                ["extraction_errors"] = new JsonArray("UIA initialization failed: " + error)
            };
        }
        NumericEvidence.Sanitize(result, result["extraction_errors"]!.AsArray());
        SeparateKnownOffscreenDiagnostics(result);
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outputPath))!);
        File.WriteAllText(outputPath, result.ToJsonString(new JsonSerializerOptions(JsonSerializerOptions.Default) { WriteIndented = true }));
        // Measurements survive provider failures so the caller can create a
        // complete parity report rather than silently dropping this scene.
        return result["extraction_errors"]!.AsArray().Count == 0 ? 0 : 1;
    }

    private static int Usage()
    {
        Console.Error.WriteLine("Relic.Capture --request request.json --output scene.uia.json");
        return 2;
    }

    private static void SeparateKnownOffscreenDiagnostics(JsonObject result)
    {
        var nodes = result["raw_nodes"]!.AsArray();
        var byId = nodes.OfType<JsonObject>().Where(node => node["id"] != null).ToDictionary(node => node["id"]!.GetValue<string>());
        var rawErrors = result["extraction_errors"]!.AsArray();
        result["raw_extraction_errors"] = rawErrors.DeepClone();
        var visibleErrors = new JsonArray(); var nonvisible = new JsonArray();
        foreach (var error in rawErrors)
        {
            var text = error?.ToString() ?? "";
            var colon = text.IndexOf(':'); var id = colon >= 0 ? text[..colon] : text;
            byId.TryGetValue(id, out var source);
            var numericMeasurement = false;
            if (source == null && text.StartsWith("/raw_nodes/", StringComparison.Ordinal))
            {
                var indexText = text["/raw_nodes/".Length..].Split('/', ':')[0];
                if (int.TryParse(indexText, out var index) && index >= 0 && index < nodes.Count)
                {
                    source = nodes[index] as JsonObject;
                    numericMeasurement = true;
                }
            }
            var offscreen = source?["state"]?["offscreen"] is JsonValue flag && flag.TryGetValue<bool>(out var value) && value;
            var ownMeasurement = numericMeasurement || source?["measurement_errors"] is JsonArray measurements &&
                measurements.Any(measurement => text == source["id"]!.GetValue<string>() + ": " + measurement?.ToString());
            // Offscreen describes this node only. An identity/tree-walk failure
            // can conceal visible descendants, so it must still fail coverage.
            if (offscreen && ownMeasurement)
                nonvisible.Add(new JsonObject { ["source"] = "UIA", ["id"] = source!["id"]!.DeepClone(), ["diagnostic"] = error?.DeepClone(),
                    ["reason"] = "The provider measured IsOffscreen=true; this node has no visible element" });
            else visibleErrors.Add(error?.DeepClone());
        }
        result["extraction_errors"] = visibleErrors;
        result["nonvisible_diagnostics"] = nonvisible;
    }
}

internal sealed class Capture
{
    private readonly JsonObject request;
    private readonly int processId;
    private readonly double originX, originY;
    private readonly HashSet<string> seen = new(StringComparer.Ordinal);
    private readonly JsonArray nodes = new(), errors = new();
    private readonly TreeWalker walker = TreeWalker.RawViewWalker;
    private NativeTextEvidence? nativeText;
    private int nextId;

    public Capture(JsonObject request)
    {
        this.request = request;
        processId = request["pid"]!.GetValue<int>();
        if (processId <= 0) throw new ArgumentException("A positive native process ID is required.");
        originX = request["origin"]!["x"]!.GetValue<double>();
        originY = request["origin"]!["y"]!.GetValue<double>();
        if (!double.IsFinite(originX) || !double.IsFinite(originY))
            throw new ArgumentException("Client origin must contain finite measured coordinates.");
    }

    public JsonObject Run()
    {
        var handle = request["hwnd"]!.GetValue<long>();
        var primary = AutomationElement.FromHandle(new IntPtr(handle));
        if (primary.Current.ProcessId != processId)
            throw new InvalidOperationException("Requested HWND does not belong to the requested process.");
        Walk(primary, null, "primary-window");

        // Menu/Flyout HWNDs can be separate desktop children. Only enumerate
        // this PID's immediate desktop children; never inspect other apps.
        var roots = AutomationElement.RootElement.FindAll(TreeScope.Children,
            new PropertyCondition(AutomationElement.ProcessIdProperty, processId));
        foreach (AutomationElement root in roots) Walk(root, null, "process-popup-or-window");

        if (nodes.Count == 0) errors.Add("The native process exposed no UI Automation nodes.");
        return new JsonObject
        {
            ["schema_version"] = 1,
            ["case_id"] = request["case_id"]?.DeepClone(),
            ["client"] = "windows",
            ["pid"] = processId,
            ["primary_hwnd"] = handle,
            ["origin"] = request["origin"]!.DeepClone(),
            ["viewport"] = new JsonObject
            {
                ["width"] = request["width"]?.DeepClone(),
                ["height"] = request["height"]?.DeepClone(),
                ["scale"] = 1
            },
            ["source"] = "System.Windows.Automation.TreeWalker.RawViewWalker",
            ["raw_nodes"] = nodes,
            ["extraction_errors"] = errors
        };
    }

    private void Walk(AutomationElement element, string? parent, string rootKind)
    {
        var id = "uia-" + nextId++.ToString(CultureInfo.InvariantCulture);
        try
        {
            // Do not emit embedded foreign-process content, even when a native
            // provider includes it in its raw tree.
            if (element.Current.ProcessId != processId) return;
            var runtimeId = string.Join(".", element.GetRuntimeId());
            if (!seen.Add(runtimeId)) return;
            var unsupported = new JsonArray();
            var nodeErrors = new JsonArray();
            var node = new JsonObject
            {
                ["id"] = id, ["parent"] = parent, ["root_kind"] = rootKind,
                ["runtime_id"] = runtimeId,
                ["control_type"] = Property(element, AutomationElement.ControlTypeProperty, unsupported, nodeErrors),
                ["name"] = Property(element, AutomationElement.NameProperty, unsupported, nodeErrors),
                ["class_name"] = Property(element, AutomationElement.ClassNameProperty, unsupported, nodeErrors),
                ["automation_id"] = Property(element, AutomationElement.AutomationIdProperty, unsupported, nodeErrors),
                ["framework_id"] = Property(element, AutomationElement.FrameworkIdProperty, unsupported, nodeErrors),
                ["help_text"] = Property(element, AutomationElement.HelpTextProperty, unsupported, nodeErrors),
                ["native_window_handle"] = Property(element, AutomationElement.NativeWindowHandleProperty, unsupported, nodeErrors),
                ["is_control_element"] = Property(element, AutomationElement.IsControlElementProperty, unsupported, nodeErrors),
                ["is_content_element"] = Property(element, AutomationElement.IsContentElementProperty, unsupported, nodeErrors),
                ["bounds"] = BoundsProperty(element, nodeErrors),
                ["state"] = new JsonObject
                {
                    ["enabled"] = Property(element, AutomationElement.IsEnabledProperty, unsupported, nodeErrors),
                    ["focused"] = Property(element, AutomationElement.HasKeyboardFocusProperty, unsupported, nodeErrors),
                    ["focusable"] = Property(element, AutomationElement.IsKeyboardFocusableProperty, unsupported, nodeErrors),
                    ["offscreen"] = Property(element, AutomationElement.IsOffscreenProperty, unsupported, nodeErrors),
                    ["selected"] = null, ["checked"] = null, ["expanded"] = null
                },
                ["value"] = null, ["range_value"] = null, ["text_pattern"] = null,
                ["supported_patterns"] = new JsonArray(),
                ["unsupported_properties"] = unsupported,
                ["measurement_errors"] = nodeErrors
            };
            ReadPatterns(element, node, nodeErrors);
            nodes.Add(node);
            foreach (var error in nodeErrors) errors.Add(id + ": " + error?.ToString());

            // Do not prune offscreen/zero-size/title-bar parents here: visible
            // descendants and popup peers can extend outside a parent's box.
            var child = walker.GetFirstChild(element);
            while (child != null)
            {
                Walk(child, id, rootKind);
                child = walker.GetNextSibling(child);
            }
        }
        catch (Exception error) { errors.Add(id + ": tree traversal/identity: " + error.GetType().Name + ": " + error.Message); }
    }

    private void ReadPatterns(AutomationElement element, JsonObject node, JsonArray nodeErrors)
    {
        var supported = node["supported_patterns"]!.AsArray();
        var state = node["state"]!.AsObject();
        ReadPattern<ValuePattern>(element, ValuePattern.Pattern, supported, nodeErrors, value =>
        {
            node["value"] = value.Current.Value;
            state["read_only"] = value.Current.IsReadOnly;
        });
        ReadPattern<RangeValuePattern>(element, RangeValuePattern.Pattern, supported, nodeErrors, value =>
        {
            node["range_value"] = new JsonObject
            {
                ["value"] = value.Current.Value, ["minimum"] = value.Current.Minimum,
                ["maximum"] = value.Current.Maximum, ["small_change"] = value.Current.SmallChange,
                ["large_change"] = value.Current.LargeChange, ["read_only"] = value.Current.IsReadOnly
            };
        });
        ReadPattern<SelectionItemPattern>(element, SelectionItemPattern.Pattern, supported, nodeErrors,
            value => state["selected"] = value.Current.IsSelected);
        ReadPattern<TogglePattern>(element, TogglePattern.Pattern, supported, nodeErrors, value =>
        {
            var toggle = value.Current.ToggleState;
            state["toggle"] = toggle.ToString();
            state["checked"] = toggle == ToggleState.Indeterminate ? null : JsonValue.Create(toggle == ToggleState.On);
            state["indeterminate"] = toggle == ToggleState.Indeterminate;
        });
        ReadPattern<ExpandCollapsePattern>(element, ExpandCollapsePattern.Pattern, supported, nodeErrors, value =>
        {
            var expanded = value.Current.ExpandCollapseState;
            state["expand_collapse"] = expanded.ToString();
            state["expanded"] = expanded is ExpandCollapseState.PartiallyExpanded or ExpandCollapseState.LeafNode
                ? null : JsonValue.Create(expanded == ExpandCollapseState.Expanded);
        });
        ReadPattern<TextPattern>(element, TextPattern.Pattern, supported, nodeErrors, value =>
        {
            var document = value.DocumentRange;
            var ranges = new JsonArray();
            foreach (var range in value.GetVisibleRanges()) ranges.Add(ReadTextRange(range, document, nodeErrors, includeRuns: true));
            var pattern = new JsonObject
            {
                ["document"] = ReadTextRange(document, document, nodeErrors, includeRuns: false),
                ["visible_ranges"] = ranges,
                ["supported_text_selection"] = value.SupportedTextSelection.ToString()
            };
            node["text_pattern"] = pattern;
            nativeText ??= new NativeTextEvidence(processId, originX, originY);
            nativeText.Attach(element, value, pattern, nodeErrors);
        });
    }

    private static void ReadPattern<T>(AutomationElement element, AutomationPattern pattern,
        JsonArray supported, JsonArray errors, Action<T> read) where T : BasePattern
    {
        try
        {
            if (!element.TryGetCurrentPattern(pattern, out var value)) return;
            supported.Add(pattern.ProgrammaticName);
            read((T)value);
        }
        catch (Exception error) { errors.Add(pattern.ProgrammaticName + ": " + error.GetType().Name + ": " + error.Message); }
    }

    private JsonObject ReadTextRange(TextPatternRange range, TextPatternRange document, JsonArray errors, bool includeRuns)
    {
        var attributes = new JsonObject(); var status = new JsonObject();
        foreach (var (name, attribute) in new[]
        {
            ("font_size", TextPattern.FontSizeAttribute), ("font_weight", TextPattern.FontWeightAttribute),
            ("font_family", TextPattern.FontNameAttribute), ("foreground", TextPattern.ForegroundColorAttribute),
            ("background", TextPattern.BackgroundColorAttribute), ("italic", TextPattern.IsItalicAttribute),
            ("horizontal_alignment", TextPattern.HorizontalTextAlignmentAttribute)
        })
        {
            try
            {
                var value = range.GetAttributeValue(attribute);
                if (ReferenceEquals(value, AutomationElement.NotSupported)) { attributes[name] = null; status[name] = "unsupported"; }
                else if (ReferenceEquals(value, TextPattern.MixedAttributeValue)) { attributes[name] = null; status[name] = "mixed"; }
                else
                {
                    attributes[name] = name is "foreground" or "background" ? ColorRef(value) : Json(value);
                    status[name] = value is double number && !double.IsFinite(number) ||
                        value is float single && !float.IsFinite(single) ? "nonfinite" : "measured";
                }
            }
            catch (Exception error) { attributes[name] = null; status[name] = "error"; errors.Add(attribute.ProgrammaticName + ": " + error.Message); }
        }
        var rectangles = new JsonArray(); var managedRectangles = new JsonArray(); var diagnostics = new JsonArray();
        var bounds = range.GetBoundingRectangles();
        foreach (var box in bounds)
        {
            managedRectangles.Add(NativeTextEvidence.ManagedRectangle(box));
            if (box.IsEmpty)
            {
                rectangles.Add(new JsonObject { ["x"] = null, ["y"] = null, ["width"] = null, ["height"] = null });
                diagnostics.Add("Managed Rect.Empty at index " + (rectangles.Count - 1) + "; .NET projects native width<=0 or height<=0 to this sentinel. Original native geometry is unmeasured until the paired COM query succeeds.");
            }
            else rectangles.Add(Rectangle(box.X, box.Y, box.Width, box.Height));
        }
        var result = new JsonObject
        {
            ["text"] = range.GetText(-1), ["bounds"] = rectangles,
            ["managed_bounds"] = managedRectangles, ["managed_bounds_diagnostics"] = diagnostics,
            ["range_identity"] = NativeTextEvidence.ManagedIdentity(range, document),
            ["bounds_source"] = "Managed UIA Rect[]; awaiting independent native COM range identity/geometry verification",
            ["attributes"] = attributes, ["attribute_status"] = status,
            ["font_size_unit"] = "pt"
        };
        if (status["font_family"]?.ToString() == "measured" && attributes["font_family"] is JsonValue familyValue &&
            familyValue.TryGetValue<string>(out var familyName) && !string.IsNullOrEmpty(familyName))
            result["font_family_coverage"] = FontFamilyEvidence.Inspect(familyName, result["text"]?.ToString() ?? "");
        if (includeRuns)
        {
            var runs = new JsonArray();
            var cursor = range.Clone();
            cursor.MoveEndpointByRange(TextPatternRangeEndpoint.End, cursor, TextPatternRangeEndpoint.Start);
            var count = 0;
            while (cursor.CompareEndpoints(TextPatternRangeEndpoint.Start, range, TextPatternRangeEndpoint.End) < 0)
            {
                if (++count > 10000) { errors.Add("UIA text format range enumeration exceeded 10000 runs."); break; }
                if (cursor.MoveEndpointByUnit(TextPatternRangeEndpoint.End, TextUnit.Format, 1) == 0)
                { errors.Add("UIA text format endpoint did not advance."); break; }
                if (cursor.CompareEndpoints(TextPatternRangeEndpoint.End, range, TextPatternRangeEndpoint.End) > 0)
                    cursor.MoveEndpointByRange(TextPatternRangeEndpoint.End, range, TextPatternRangeEndpoint.End);
                runs.Add(ReadTextRange(cursor, document, errors, includeRuns: false));
                cursor.MoveEndpointByRange(TextPatternRangeEndpoint.Start, cursor, TextPatternRangeEndpoint.End);
            }
            result["format_runs"] = runs;
        }
        return result;
    }

    private JsonNode? BoundsProperty(AutomationElement element, JsonArray errors)
    {
        try
        {
            var bounds = element.Current.BoundingRectangle;
            if (bounds.IsEmpty)
            {
                errors.Add("BoundingRectangle is empty; raw x=" + bounds.X.ToString("R", CultureInfo.InvariantCulture) +
                    ", y=" + bounds.Y.ToString("R", CultureInfo.InvariantCulture) + ", width=" + bounds.Width.ToString("R", CultureInfo.InvariantCulture) +
                    ", height=" + bounds.Height.ToString("R", CultureInfo.InvariantCulture));
                return null;
            }
            return Rectangle(bounds.X, bounds.Y, bounds.Width, bounds.Height);
        }
        catch (Exception error) { errors.Add("BoundingRectangle: " + error.Message); return null; }
    }

    private JsonObject Rectangle(double x, double y, double width, double height) => new()
    {
        ["x"] = x - originX, ["y"] = y - originY, ["width"] = width, ["height"] = height
    };

    private static JsonNode? Property(AutomationElement element, AutomationProperty property, JsonArray unsupported, JsonArray errors)
    {
        try
        {
            var value = element.GetCurrentPropertyValue(property, ignoreDefaultValue: true);
            if (ReferenceEquals(value, AutomationElement.NotSupported)) { unsupported.Add(property.ProgrammaticName); return null; }
            return Json(value);
        }
        catch (Exception error) { errors.Add(property.ProgrammaticName + ": " + error.Message); return null; }
    }

    private static JsonNode? Json(object? value) => value switch
    {
        null => null, string text => JsonValue.Create(text), bool flag => JsonValue.Create(flag),
        int number => JsonValue.Create(number), double number => JsonValue.Create(number), float number => JsonValue.Create(number),
        long number => JsonValue.Create(number), uint number => JsonValue.Create(number), short number => JsonValue.Create(number),
        byte number => JsonValue.Create(number), decimal number => JsonValue.Create(number),
        ControlType type => JsonValue.Create(type.ProgrammaticName),
        Enum item => JsonValue.Create(item.ToString()),
        _ => JsonValue.Create(Convert.ToString(value, CultureInfo.InvariantCulture))
    };

    private static JsonArray ColorRef(object value)
    {
        var packed = Convert.ToInt32(value, CultureInfo.InvariantCulture);
        return new JsonArray(packed & 0xff, (packed >> 8) & 0xff, (packed >> 16) & 0xff, 255);
    }
}

internal static class FontFamilyEvidence
{
    private sealed record FamilyRecord(List<System.Windows.Media.GlyphTypeface> Faces, string? Error);
    private static readonly Dictionary<string, FamilyRecord> families = new(StringComparer.OrdinalIgnoreCase);

    public static JsonObject Inspect(string familyName, string text)
    {
        var evidence = new JsonObject
        {
            ["provider_family_name"] = familyName,
            ["source"] = "UIA FontNameAttribute plus read-only system font metadata/cmap inspection",
            ["proves_actual_render_face"] = false,
            ["limitation"] = "Character coverage can reject an impossible provider family; it does not identify the actual DirectWrite glyph run or fallback face"
        };
        try
        {
            if (!families.TryGetValue(familyName, out var family))
            {
                var matching = System.Windows.Media.Fonts.SystemFontFamilies.Where(candidate =>
                    candidate.Source.Equals(familyName, StringComparison.OrdinalIgnoreCase) ||
                    candidate.FamilyNames.Values.Any(name => name.Equals(familyName, StringComparison.OrdinalIgnoreCase))).ToArray();
                var faces = new List<System.Windows.Media.GlyphTypeface>(); var failures = new List<string>();
                foreach (var candidate in matching)
                    foreach (var face in candidate.GetTypefaces())
                    {
                        try { if (face.TryGetGlyphTypeface(out var glyphs)) faces.Add(glyphs); }
                        catch (Exception error) { failures.Add(error.GetType().Name + ": " + error.Message); }
                    }
                family = new FamilyRecord(faces, matching.Length == 0 ? "Provider family is absent from the measured system font family collection" :
                    faces.Count == 0 ? "No readable physical typeface for the provider family: " + string.Join("; ", failures) : null);
                families[familyName] = family;
            }
            evidence["physical_faces"] = new JsonArray(family.Faces.Select(face => (JsonNode)new JsonObject
            {
                ["uri"] = face.FontUri.ToString(),
                ["family_names"] = new JsonArray(face.FamilyNames.Values.Distinct().Select(name => (JsonNode)JsonValue.Create(name)!).ToArray())
            }).ToArray());
            if (family.Error != null)
            {
                evidence["status"] = "unresolved"; evidence["reason"] = family.Error; return evidence;
            }
            var scalars = text.EnumerateRunes().Where(rune => Rune.GetUnicodeCategory(rune) is not (UnicodeCategory.Control or UnicodeCategory.Format)
                && rune.Value is not (>= 0xFE00 and <= 0xFE0F) && rune.Value is not (>= 0xE0100 and <= 0xE01EF)).Select(rune => rune.Value).Distinct().ToArray();
            var missing = scalars.Where(scalar => !family.Faces.Any(face => face.CharacterToGlyphMap.TryGetValue(scalar, out var glyph) && glyph != 0)).ToArray();
            evidence["checked_scalars"] = new JsonArray(scalars.Select(scalar => (JsonNode)JsonValue.Create("U+" + scalar.ToString("X4", CultureInfo.InvariantCulture))!).ToArray());
            evidence["missing_scalars"] = new JsonArray(missing.Select(scalar => (JsonNode)JsonValue.Create("U+" + scalar.ToString("X4", CultureInfo.InvariantCulture))!).ToArray());
            evidence["status"] = missing.Length == 0 ? "family-can-cover-scalars" : "provider-family-cannot-cover-text";
            if (missing.Length > 0) evidence["reason"] = "UIA names a family whose physical faces cannot cover the visible text; actual fallback glyph runs are unmeasured";
        }
        catch (Exception error)
        {
            evidence["status"] = "unresolved"; evidence["reason"] = error.GetType().Name + ": " + error.Message;
        }
        return evidence;
    }
}
