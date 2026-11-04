using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Documents;
using Microsoft.UI.Xaml.Media;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json.Nodes;
using static Relic.NativeLabelInterop;

namespace Relic;

// CI-only candidate diagnostics. The source is the actual visible cwd label;
// the DWrite layout and ICU iterator are independent, unpainted probe objects.
// Nothing here supplies canonical geometry or changes production layout/text.
internal static class PathLineBreakProbe
{
    internal static void Capture(FrameworkElement root, TextBlock? owner, string caseId, string output)
    {
        if (Environment.GetEnvironmentVariable("GITHUB_ACTIONS") != "true"
            || string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("RELIC_VISUAL_MANIFEST"))) return;
        var path = Path.Combine(output, caseId + ".path-line-break-probe.json");
        var errors = new JsonArray(); var steps = new JsonArray();
        var receipt = new JsonObject
        {
            ["source"] = "Visible member-card cwd inputs and independent native line-break candidates",
            ["case_id"] = caseId, ["app_pid"] = Environment.ProcessId,
            ["started_qpc"] = Stopwatch.GetTimestamp(), ["qpc_frequency"] = Stopwatch.Frequency,
            ["status"] = "pending", ["completed"] = false, ["errors"] = errors, ["steps"] = steps,
            ["canonical_geometry_supplied"] = false, ["production_text_modified"] = false,
            ["production_layout_replaced"] = false,
            ["scope"] = "Candidate break positions only; source glyph face, CSS strut equivalence and screenshot-frame identity are not established"
        };
        void Save()
        {
            try
            {
                File.WriteAllText(path + ".tmp", receipt.ToJsonString(), new UTF8Encoding(false));
                File.Move(path + ".tmp", path, true);
            }
            catch (Exception error) { Console.Error.WriteLine("PathLineBreakProbe write: " + error); }
        }
        void Phase(string name) { steps.Add(new JsonObject { ["phase"] = name, ["qpc"] = Stopwatch.GetTimestamp() }); Save(); }
        void Error(string phase, Exception error)
        {
            errors.Add(new JsonObject { ["phase"] = phase, ["qpc"] = Stopwatch.GetTimestamp(),
                ["hresult"] = error.HResult, ["exception_type"] = error.GetType().FullName, ["error"] = error.ToString() });
        }
        Phase("read_actual_cwd");
        try
        {
            if (owner == null || !owner.IsLoaded || !owner.DispatcherQueue.HasThreadAccess
                || AutomationProperties.GetAutomationId(owner) != "member-card-cwd")
                throw new InvalidOperationException("The actual loaded cwd TextBlock was not found on its UI thread");
            var parent = VisualTreeHelper.GetParent(owner) as Grid
                ?? throw new InvalidOperationException("The actual cwd owner is not a direct child of its native field Grid");
            var column = Grid.GetColumn(owner);
            if (Grid.GetColumnSpan(owner) != 1 || column < 0 || column >= parent.ColumnDefinitions.Count)
                throw new InvalidOperationException("The actual cwd allocation is not one measured Grid column");
            var slot = LayoutInformation.GetLayoutSlot(owner);
            var availableWidth = parent.ColumnDefinitions[column].ActualWidth - owner.Margin.Left - owner.Margin.Right;
            if (!double.IsFinite(availableWidth) || availableWidth <= 0)
                throw new InvalidOperationException("The actual cwd Grid column has no finite positive available width");
            // The production InlineMono currently owns one real Run. Do not
            // flatten mixed formatting or guess a font from the parent/style.
            if (owner.Inlines.Count != 1 || owner.Inlines[0] is not Run run)
                throw new InvalidOperationException("The actual cwd text is not represented by one exact native Run");
            var text = run.Text;
            if (!string.Equals(owner.Text, text, StringComparison.Ordinal) || text.Length == 0)
                throw new InvalidOperationException("The actual cwd Run and its complete displayed TextBlock text disagree or are empty");
            var family = run.FontFamily.Source; var locale = owner.Language; var size = run.FontSize;
            var weight = run.FontWeight.Weight; var stretch = (uint)run.FontStretch; var style = (uint)run.FontStyle;
            if (string.IsNullOrWhiteSpace(family) || string.IsNullOrWhiteSpace(locale) || !double.IsFinite(size) || size <= 0)
                throw new InvalidOperationException("The actual cwd font family, language or size is not measurable");
            var bounds = owner.TransformToVisual(root).TransformBounds(new Windows.Foundation.Rect(0, 0, owner.ActualWidth, owner.ActualHeight));
            receipt["actual_source"] = new JsonObject
            {
                ["owner"] = Identity(owner), ["run"] = Identity(run), ["parent"] = Identity(parent),
                ["automation_id"] = AutomationProperties.GetAutomationId(owner), ["visual_ancestry"] = Ancestry(owner),
                ["is_loaded"] = owner.IsLoaded, ["visibility"] = owner.Visibility.ToString(), ["opacity"] = owner.Opacity,
                ["display_text"] = text, ["utf16_length"] = text.Length,
                ["utf16_le_base64"] = Convert.ToBase64String(Encoding.Unicode.GetBytes(text)),
                ["same_owner_run_text"] = true, ["window_bounds"] = Rect(bounds), ["layout_slot_in_parent"] = Rect(slot),
                ["grid_column"] = column, ["grid_column_actual_width"] = parent.ColumnDefinitions[column].ActualWidth,
                ["margin"] = new JsonArray(owner.Margin.Left, owner.Margin.Top, owner.Margin.Right, owner.Margin.Bottom),
                ["available_width"] = availableWidth,
                ["available_width_source"] = "Actual parent Grid.ColumnDefinitions[Grid.GetColumn(owner)].ActualWidth minus actual horizontal owner margins; no fixture width",
                ["font_request"] = new JsonObject { ["family"] = family, ["size"] = size, ["weight"] = weight,
                    ["style"] = run.FontStyle.ToString(), ["style_value"] = style, ["stretch"] = run.FontStretch.ToString(), ["stretch_value"] = stretch,
                    ["locale"] = locale, ["scope"] = "Actual Run properties, not proof of the production resolved glyph face" },
                ["parent_strut_configuration"] = new JsonObject { ["font_family"] = owner.FontFamily.Source,
                    ["font_size"] = owner.FontSize, ["line_height"] = owner.LineHeight,
                    ["line_stacking_strategy"] = owner.LineStackingStrategy.ToString(), ["baseline_offset"] = owner.BaselineOffset },
                ["text_wrapping"] = owner.TextWrapping.ToString(), ["is_text_selection_enabled"] = owner.IsTextSelectionEnabled
            };
            Phase("dwrite_candidate_started");
            try { receipt["dwrite_candidate"] = DWrite(text, family, size, weight, style, stretch, locale, availableWidth, root.ActualHeight); }
            catch (Exception error) { Error("dwrite_candidate", error); receipt["dwrite_candidate"] = new JsonObject { ["status"] = "failed" }; }
            Phase("dwrite_candidate_finished");
            try { receipt["icu_candidate"] = Icu(text, locale); }
            catch (Exception error) { Error("icu_candidate", error); receipt["icu_candidate"] = new JsonObject { ["status"] = "failed" }; }
            Phase("icu_candidate_finished");
            receipt["source_after"] = new JsonObject { ["owner"] = Identity(owner), ["run"] = Identity(run),
                ["same_parent_reference"] = ReferenceEquals(VisualTreeHelper.GetParent(owner), parent),
                ["same_run_reference"] = owner.Inlines.Count == 1 && ReferenceEquals(owner.Inlines[0], run),
                ["display_text"] = owner.Text, ["run_text"] = run.Text, ["is_loaded"] = owner.IsLoaded,
                ["window_bounds"] = Rect(owner.TransformToVisual(root).TransformBounds(new Windows.Foundation.Rect(0, 0, owner.ActualWidth, owner.ActualHeight))) };
            if (!ReferenceEquals(VisualTreeHelper.GetParent(owner), parent) || owner.Inlines.Count != 1
                || !ReferenceEquals(owner.Inlines[0], run) || owner.Text != text || run.Text != text)
                throw new InvalidOperationException("The actual source object/text changed during the independent candidate diagnostic");
            GC.KeepAlive(owner); GC.KeepAlive(run); GC.KeepAlive(parent);
        }
        catch (Exception error) { Error("actual_source", error); }
        receipt["completed"] = true; receipt["finished_qpc"] = Stopwatch.GetTimestamp();
        receipt["status"] = errors.Count == 0 ? "observed-candidates-only" : "failed";
        Save();
    }

    private static JsonObject Identity(DependencyObject value)
    {
        if (value is not WinRT.IWinRTObject native) throw new InvalidOperationException("Source object has no actual WinRT object reference");
        var pointer = native.NativeObject.GetRef();
        try { return new JsonObject { ["runtime_type"] = value.GetType().FullName,
            ["managed_reference_hash"] = RuntimeHelpers.GetHashCode(value), ["iunknown_identity"] = ComIdentity(pointer) }; }
        finally { Release(ref pointer); }
    }
    private static JsonArray Ancestry(DependencyObject owner)
    {
        var nodes = new JsonArray(); var seen = new HashSet<DependencyObject>(ReferenceEqualityComparer.Instance);
        for (DependencyObject? node = owner; node != null && seen.Add(node); node = VisualTreeHelper.GetParent(node))
        {
            var entry = Identity(node); entry["automation_id"] = AutomationProperties.GetAutomationId(node);
            if (node is FrameworkElement element) entry["name"] = element.Name;
            nodes.Add(entry);
        }
        return nodes;
    }
    private static JsonObject Rect(Windows.Foundation.Rect rect) => new()
    { ["x"] = rect.X, ["y"] = rect.Y, ["width"] = rect.Width, ["height"] = rect.Height };

    [StructLayout(LayoutKind.Sequential)] private struct ClusterMetrics
    { internal float Width; internal ushort Length, Flags; }

    private static T[] ReadArray<T>(IntPtr layout, int slot) where T : struct
    {
        var call = Method<GetArray>(layout, slot); var hr = call(layout, IntPtr.Zero, 0, out var count);
        if (hr < 0 && hr != unchecked((int)0x8007007A)) Check(hr);
        if (count == 0) return [];
        var buffer = Marshal.AllocHGlobal(checked((int)count * Marshal.SizeOf<T>()));
        try
        {
            Check(call(layout, buffer, count, out var actual));
            if (actual > count) throw new InvalidOperationException("DWrite returned more records than the actual allocated buffer");
            var values = new T[actual];
            for (var i = 0; i < values.Length; i++) values[i] = Marshal.PtrToStructure<T>(buffer + i * Marshal.SizeOf<T>());
            return values;
        }
        finally { Marshal.FreeHGlobal(buffer); }
    }
    private static JsonObject DWrite(string text, string families, double size, ushort weight, uint style, uint stretch,
        string locale, double width, double viewportHeight)
    {
        IntPtr factory = IntPtr.Zero, format = IntPtr.Zero, layout = IntPtr.Zero;
        try
        {
            var iid = new Guid("b859ee5a-d838-4b5b-a2e8-1adc7d93db48");
            Check(DWriteCreateFactory(0, ref iid, out factory));
            var family = families.Split(',')[0].Trim().Trim('"');
            Check(Method<CreateFormat>(factory, 15)(factory, family, IntPtr.Zero, weight, style, stretch, checked((float)size), locale, out format));
            Check(Method<SetUInt>(format, 5)(format, 2)); // DWRITE_WORD_WRAPPING_EMERGENCY_BREAK.
            Check(Method<CreateLayout>(factory, 18)(factory, text, checked((uint)text.Length), format, checked((float)width), checked((float)viewportHeight), out layout));
            var fallback = NativeLabelFallback.Apply(factory, layout, families);
            var result = new JsonObject { ["status"] = "observed", ["layout_com_identity"] = ComIdentity(layout),
                ["object_scope"] = "Independent unpainted candidate; this is not the TextBlock production layout",
                ["text"] = text, ["requested_family_list"] = families, ["requested_locale"] = locale,
                ["actual_word_wrapping"] = Method<GetUInt>(layout, 13)(layout),
                ["actual_font_size"] = Method<GetFloat>(layout, 25)(layout), ["actual_font_weight"] = Method<GetUInt>(layout, 22)(layout),
                ["requested_width"] = width, ["requested_height"] = viewportHeight, ["fallback_configuration"] = fallback,
                ["line_spacing"] = "Natural candidate DWrite spacing; production parent CSS strut is recorded separately, not simulated" };
            Check(Method<GetTextMetrics>(layout, 60)(layout, out var metrics));
            result["metrics"] = new JsonObject { ["width"] = metrics.Width, ["height"] = metrics.Height,
                ["layout_width"] = metrics.LayoutWidth, ["layout_height"] = metrics.LayoutHeight, ["line_count"] = metrics.LineCount };
            var lines = new JsonArray(); uint position = 0;
            foreach (var line in ReadArray<LineMetrics>(layout, 59))
            {
                lines.Add(new JsonObject { ["start_utf16"] = position, ["length_utf16"] = line.Length,
                    ["text"] = text.Substring(checked((int)position), checked((int)line.Length)),
                    ["trailing_whitespace_length"] = line.TrailingWhitespaceLength, ["newline_length"] = line.NewlineLength,
                    ["height"] = line.Height, ["baseline"] = line.Baseline, ["is_trimmed"] = line.IsTrimmed != 0 });
                position += line.Length;
            }
            result["line_metrics"] = lines;
            if (position != text.Length) throw new InvalidOperationException("Candidate line lengths do not cover the complete actual cwd string");
            var clusters = new JsonArray(); position = 0;
            foreach (var cluster in ReadArray<ClusterMetrics>(layout, 62))
            {
                clusters.Add(new JsonObject { ["start_utf16"] = position, ["length_utf16"] = cluster.Length,
                    ["text"] = text.Substring(checked((int)position), cluster.Length), ["width"] = cluster.Width,
                    ["raw_flags"] = cluster.Flags, ["can_wrap_line_after"] = (cluster.Flags & 1) != 0,
                    ["is_whitespace"] = (cluster.Flags & 2) != 0, ["is_newline"] = (cluster.Flags & 4) != 0,
                    ["is_soft_hyphen"] = (cluster.Flags & 8) != 0, ["is_right_to_left"] = (cluster.Flags & 16) != 0 });
                position += cluster.Length;
            }
            result["cluster_metrics"] = clusters;
            if (position != text.Length) throw new InvalidOperationException("Candidate cluster lengths do not cover the complete actual cwd string");
            var hit = Method<HitTestRange>(layout, 66); var hr = hit(layout, 0, (uint)text.Length, 0, 0, IntPtr.Zero, 0, out var count);
            if (hr < 0 && hr != unchecked((int)0x8007007A)) Check(hr);
            var buffer = Marshal.AllocHGlobal(checked((int)count * Marshal.SizeOf<HitTestMetrics>()));
            try
            {
                Check(hit(layout, 0, (uint)text.Length, 0, 0, buffer, count, out var actual));
                if (actual > count) throw new InvalidOperationException("Candidate HitTestTextRange exceeded its allocated buffer");
                var ranges = new JsonArray();
                for (var i = 0; i < actual; i++)
                {
                    var range = Marshal.PtrToStructure<HitTestMetrics>(buffer + checked((int)i * Marshal.SizeOf<HitTestMetrics>()));
                    ranges.Add(new JsonObject { ["start_utf16"] = range.TextPosition, ["length_utf16"] = range.Length,
                        ["left"] = range.Left, ["top"] = range.Top, ["width"] = range.Width, ["height"] = range.Height,
                        ["bidi_level"] = range.BidiLevel, ["is_text"] = range.IsText != 0, ["is_trimmed"] = range.IsTrimmed != 0 });
                }
                result["hit_test_ranges"] = ranges;
                result["hit_test_quantity"] = "Actual candidate text advance/selection rectangles, not painted glyph bounds";
            }
            finally { Marshal.FreeHGlobal(buffer); }
            return result;
        }
        finally { Release(ref layout); Release(ref format); Release(ref factory); }
    }

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate void IcuVersion([Out] byte[] version);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate IntPtr IcuOpen(int kind, IntPtr locale, IntPtr text, int length, ref int error);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate int IcuPosition(IntPtr iterator);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate void IcuClose(IntPtr iterator);
    private static T Export<T>(IntPtr library, string name) where T : Delegate =>
        Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(library, name));
    private static JsonObject Icu(string text, string locale)
    {
        IntPtr common = IntPtr.Zero, international = IntPtr.Zero, iterator = IntPtr.Zero;
        IntPtr textPointer = IntPtr.Zero, localePointer = IntPtr.Zero;
        IcuClose? close = null;
        try
        {
            var path = Path.Combine(Environment.SystemDirectory, "icu.dll"); var combined = NativeLibrary.TryLoad(path, out common);
            string commonPath, internationalPath;
            if (combined) { international = common; commonPath = internationalPath = path; }
            else
            {
                // Windows 10 1809 is still a supported app target. Its ICU C
                // API lives in the two OS DLLs; never download a replacement.
                commonPath = Path.Combine(Environment.SystemDirectory, "icuuc.dll");
                internationalPath = Path.Combine(Environment.SystemDirectory, "icuin.dll");
                common = NativeLibrary.Load(commonPath); international = NativeLibrary.Load(internationalPath);
            }
            var version = new byte[4]; var unicode = new byte[4];
            Export<IcuVersion>(common, "u_getVersion")(version); Export<IcuVersion>(common, "u_getUnicodeVersion")(unicode);
            var open = Export<IcuOpen>(international, "ubrk_open"); var first = Export<IcuPosition>(international, "ubrk_first");
            var next = Export<IcuPosition>(international, "ubrk_next"); var ruleStatus = Export<IcuPosition>(international, "ubrk_getRuleStatus");
            close = Export<IcuClose>(international, "ubrk_close");
            textPointer = Marshal.StringToHGlobalUni(text); localePointer = Marshal.StringToCoTaskMemUTF8(locale);
            var error = 0; iterator = open(2, localePointer, textPointer, text.Length, ref error); // UBRK_LINE.
            if (error > 0 || iterator == IntPtr.Zero) throw new InvalidOperationException("System ICU ubrk_open failed: " + error);
            var boundaries = new JsonArray(); var position = first(iterator); var previous = -1;
            for (var iteration = 0; position != -1; iteration++)
            {
                if (iteration > text.Length + 1 || position <= previous || position < 0 || position > text.Length)
                    throw new InvalidOperationException("System ICU returned non-progressing or out-of-source line boundaries");
                boundaries.Add(new JsonObject { ["offset_utf16"] = position, ["rule_status"] = ruleStatus(iterator) });
                previous = position; position = next(iterator);
            }
            if (previous != text.Length) throw new InvalidOperationException("System ICU did not reach the complete source string end");
            return new JsonObject { ["status"] = "observed", ["common_library"] = commonPath, ["international_library"] = internationalPath,
                ["common_file_version"] = FileVersionInfo.GetVersionInfo(commonPath).FileVersion,
                ["icu_version"] = string.Join(".", version), ["unicode_version"] = string.Join(".", unicode),
                ["requested_locale"] = locale, ["open_error_code"] = error, ["break_iterator_type"] = "UBRK_LINE",
                ["source_text"] = text, ["source_utf16_length"] = text.Length, ["boundaries"] = boundaries,
                ["scope"] = "Actual installed system ICU opportunities only; no line-width selection, rendering or Chromium equivalence asserted" };
        }
        finally
        {
            try { if (iterator != IntPtr.Zero) close!(iterator); }
            finally
            {
                if (textPointer != IntPtr.Zero) Marshal.FreeHGlobal(textPointer);
                if (localePointer != IntPtr.Zero) Marshal.FreeCoTaskMem(localePointer);
                if (international != IntPtr.Zero && international != common) NativeLibrary.Free(international);
                if (common != IntPtr.Zero) NativeLibrary.Free(common);
            }
        }
    }
}
