using System.Diagnostics;
using System.Reflection;
using System.Text;
using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Documents;
using Microsoft.UI.Xaml.Media;
using Windows.Foundation;

namespace Relic;

public sealed partial class MainWindow
{
    private TextRangeFrameObserver? textRangeFrameObserver;
    private JsonObject? capturedTextRangeFrameEvidence;

    private void BeginTextRangeFrameCapture(string caseId)
    {
        if (!VisualCaptureEnabled) throw new InvalidOperationException("Text range frame observation is CI-only");
        EndTextRangeFrameCapture();
        textRangeFrameObserver = new TextRangeFrameObserver(root, caseId, WinRT.Interop.WindowNative.GetWindowHandle(this));
        capturedTextRangeFrameEvidence = textRangeFrameObserver.Receipt;
        textRangeFrameObserver.Checkpoint("begin_before_desktop_readback");
    }
    private void CheckpointTextRangeFrameCapture(string stage) => textRangeFrameObserver?.Checkpoint(stage);
    private void BindTextRangeFrameOwners(IReadOnlyDictionary<DependencyObject, string> ids) => textRangeFrameObserver?.Bind(ids);
    private void RegisterTextRangeFrameIdentityPeer(DependencyObject owner, AutomationPeer peer)
    { if (owner is TextBlock text) textRangeFrameObserver?.IdentityPeer(text, peer); }
    private JsonObject? ObserveTextRangeFrameProvider(TextBlock owner, AutomationPeer? peer, string stage) =>
        textRangeFrameObserver?.ObserveProvider(owner, peer, stage);
    private void EndTextRangeFrameCapture()
    { textRangeFrameObserver?.Dispose(); textRangeFrameObserver = null; }

    // Source/layout inputs of the actual TextBlock objects, not glyph ink or a
    // compositor presentation proof. No native rectangle is replaced here.
    private sealed class TextRangeFrameObserver : IDisposable
    {
        private readonly FrameworkElement root;
        private readonly IntPtr hwnd;
        private readonly TextBlock[] owners;
        private readonly Dictionary<DependencyObject, int> ids = new(ReferenceEqualityComparer.Instance);
        private readonly Dictionary<DependencyObject, List<(string Name, DependencyProperty Property)>> properties = new(ReferenceEqualityComparer.Instance);
        private readonly Dictionary<TextBlock, string> xamlIds = new(ReferenceEqualityComparer.Instance);
        private readonly Dictionary<TextBlock, (AutomationPeer Peer, AutomationPeer? Events)> identityPeers = new(ReferenceEqualityComparer.Instance);
        private readonly Dictionary<TextBlock, JsonObject> lastStates = new(ReferenceEqualityComparer.Instance);
        private readonly Dictionary<Run, RunTextBindingObserver> runBindings = new(ReferenceEqualityComparer.Instance);
        private readonly List<Action> detach = [];
        private readonly JsonArray changes = [], checkpoints = [], errors = [], unavailableProperties = [];
        private readonly JsonArray runBindingReceipts = [];
        private long revision;
        private bool reading, disposed;
        internal JsonObject Receipt { get; }

        internal TextRangeFrameObserver(FrameworkElement root, string caseId, IntPtr hwnd)
        {
            this.root = root; this.hwnd = hwnd; owners = CurrentOwners();
            Receipt = new JsonObject
            {
                ["source"] = "Actual retained TextBlock input objects observed around desktop readback and provider calls",
                ["case_id"] = caseId, ["app_pid"] = Environment.ProcessId, ["hwnd"] = hwnd.ToInt64(),
                ["qpc_frequency"] = Stopwatch.Frequency, ["started_qpc"] = Stopwatch.GetTimestamp(),
                ["owners"] = new JsonArray(), ["checkpoints"] = checkpoints, ["changes"] = changes, ["errors"] = errors,
                ["unavailable_property_observers"] = unavailableProperties,
                ["run_text_bindings"] = runBindingReceipts,
                ["continuity_proven"] = false, ["canonical_geometry_supplied"] = false,
                ["final_png_contribution_proven"] = false,
                ["scope"] = "Measured source/layout/ancestor inputs and observable revisions; not glyph ink, visibility, or final composed pixels",
                ["limitations"] = new JsonArray("Composition-only animations and unsupported dependency-property values are not certified by this observer",
                    "Run.Text binding notifications do not observe InlineCollection insertion, removal, replacement or reordering")
            };
            reading = true;
            try { foreach (var owner in owners) lastStates[owner] = State(owner); }
            catch (Exception ex) { errors.Add(ex.ToString()); }
            finally { reading = false; }
            root.LayoutUpdated += LayoutChanged;
            detach.Add(() => root.LayoutUpdated -= LayoutChanged);
        }

        private TextBlock[] CurrentOwners()
        {
            var result = new List<TextBlock>(); var seen = new HashSet<DependencyObject>(ReferenceEqualityComparer.Instance);
            void Walk(DependencyObject value)
            {
                if (!seen.Add(value)) return;
                if (value is TextBlock text) result.Add(text);
                for (var i = 0; i < VisualTreeHelper.GetChildrenCount(value); i++) Walk(VisualTreeHelper.GetChild(value, i));
            }
            Walk(root);
            foreach (var popup in VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot))
                if (popup.IsOpen && popup.Child != null) Walk(popup.Child);
            return result.ToArray();
        }

        private void Changed(DependencyObject value, string reason)
        {
            if (disposed) return;
            revision++;
            if (changes.Count < 4096) changes.Add(new JsonObject
            { ["revision"] = revision, ["qpc"] = Stopwatch.GetTimestamp(), ["object_id"] = ids.GetValueOrDefault(value, -1), ["reason"] = reason });
            else Receipt["change_journal_overflow"] = true;
        }

        private int Track(DependencyObject value)
        {
            if (ids.TryGetValue(value, out var known)) return known;
            var id = ids.Count; ids.Add(value, id); properties[value] = [];
            var names = new List<string>();
            if (value is UIElement) names.AddRange(["Visibility", "Opacity", "Clip", "RenderTransform", "RenderTransformOrigin", "Projection", "Transform3D"]);
            if (value is FrameworkElement) names.AddRange(["Width", "Height", "MinWidth", "MaxWidth", "MinHeight", "MaxHeight", "Margin", "HorizontalAlignment", "VerticalAlignment", "FlowDirection", "Language"]);
            if (value is TextBlock) names.AddRange(["Text", "FontFamily", "FontSize", "FontWeight", "FontStyle", "FontStretch", "CharacterSpacing", "LineHeight", "LineStackingStrategy", "TextWrapping", "TextTrimming", "TextAlignment", "MaxLines", "Padding"]);
            if (value is TextElement) names.AddRange(["FontFamily", "FontSize", "FontWeight", "FontStyle", "FontStretch", "CharacterSpacing", "Language"]);
            if (value is Run) names.Add("Text");
            if (value is Border or Control or StackPanel or Grid) names.Add("Padding");
            if (value is Geometry) names.Add("Transform");
            if (value is RectangleGeometry) names.Add("Rect");
            if (value is Transform)
                names.AddRange(value.GetType().GetProperties(BindingFlags.Public | BindingFlags.Static | BindingFlags.FlattenHierarchy)
                    .Where(p => p.PropertyType == typeof(DependencyProperty) && p.Name.EndsWith("Property")).Select(p => p.Name[..^8]));
            foreach (var name in names.Distinct())
            {
                try
                {
                    var property = value.GetType().GetProperty(name + "Property", BindingFlags.Public | BindingFlags.Static | BindingFlags.FlattenHierarchy);
                    if (property?.GetValue(null) is not DependencyProperty dp)
                    {
                        unavailableProperties.Add(new JsonObject { ["object_id"] = id, ["type"] = value.GetType().FullName,
                            ["property"] = name, ["reason"] = "No reflected public dependency-property observer available" });
                        continue;
                    }
                    var token = value.RegisterPropertyChangedCallback(dp, (sender, _) => Changed(sender, name));
                    properties[value].Add((name, dp)); detach.Add(() => value.UnregisterPropertyChangedCallback(dp, token));
                }
                catch (Exception ex) { errors.Add(value.GetType().FullName + "." + name + ": " + ex); }
            }
            if (value is Run retainedRun)
            {
                var observer = new RunTextBindingObserver(retainedRun, id,
                    () => Changed(retainedRun, "Run.Text.OneWayBinding"),
                    reason => errors.Add("Run object " + id + ": " + reason));
                runBindings.Add(retainedRun, observer); runBindingReceipts.Add(observer.Receipt);
                // Retain failed installations too, so every allocated target and
                // registered callback is detached by the ordinary frame cleanup.
                detach.Add(observer.Dispose); observer.Install();
            }
            if (value is FrameworkElement element)
            {
                SizeChangedEventHandler handler = (_, e) => { if (e.NewSize != e.PreviousSize) Changed(element, "SizeChanged"); };
                element.SizeChanged += handler; detach.Add(() => element.SizeChanged -= handler);
            }
            if (value is ScrollViewer viewer)
            {
                var previous = (viewer.HorizontalOffset, viewer.VerticalOffset, viewer.ZoomFactor);
                EventHandler<ScrollViewerViewChangedEventArgs> handler = (_, _) =>
                {
                    var current = (viewer.HorizontalOffset, viewer.VerticalOffset, viewer.ZoomFactor);
                    if (current != previous) { Changed(viewer, "ScrollViewer.ViewChanged"); previous = current; }
                };
                viewer.ViewChanged += handler; detach.Add(() => viewer.ViewChanged -= handler);
            }
            return id;
        }

        private JsonNode? Value(object? value, HashSet<DependencyObject> inputs)
        {
            if (value == null) return null;
            if (value is FontFamily family) return new JsonObject { ["family_source"] = family.Source };
            if (value is DependencyObject dependency) { inputs.Add(dependency); return new JsonObject { ["object_id"] = Track(dependency), ["type"] = dependency.GetType().FullName }; }
            if (value is string text) return new JsonObject { ["value"] = text, ["utf16_le_base64"] = Convert.ToBase64String(Encoding.Unicode.GetBytes(text)) };
            if (value is double number) return double.IsFinite(number) ? JsonValue.Create(number) : JsonValue.Create(number.ToString(System.Globalization.CultureInfo.InvariantCulture));
            if (value is float scalar) return float.IsFinite(scalar) ? JsonValue.Create(scalar) : JsonValue.Create(scalar.ToString(System.Globalization.CultureInfo.InvariantCulture));
            if (value is bool flag) return JsonValue.Create(flag);
            if (value is int integer) return JsonValue.Create(integer);
            if (value is uint unsigned) return JsonValue.Create(unsigned);
            if (value is Enum) return JsonValue.Create(value.ToString());
            if (value is Windows.UI.Text.FontWeight weight) return JsonValue.Create(weight.Weight);
            if (value is Point point) return new JsonArray(point.X, point.Y);
            if (value is Rect rect) return new JsonArray(rect.X, rect.Y, rect.Width, rect.Height);
            if (value is Thickness thickness) return new JsonArray(thickness.Left, thickness.Top, thickness.Right, thickness.Bottom);
            if (value is Matrix matrix) return new JsonArray(matrix.M11, matrix.M12, matrix.M21, matrix.M22, matrix.OffsetX, matrix.OffsetY);
            return new JsonObject { ["unsupported_type"] = value.GetType().FullName, ["display_value"] = value.ToString(), ["measured"] = false };
        }

        private JsonObject State(TextBlock owner)
        {
            var inputs = new HashSet<DependencyObject>(ReferenceEqualityComparer.Instance); var ancestry = new JsonArray();
            for (DependencyObject? value = owner; value != null; value = VisualTreeHelper.GetParent(value))
            {
                if (!inputs.Add(value)) break;
                ancestry.Add(Track(value)); if (ReferenceEquals(value, root)) break;
            }
            var inlines = new JsonArray();
            void InlineChildren(IEnumerable<Inline> values)
            {
                foreach (var value in values)
                { inputs.Add(value); inlines.Add(Track(value)); if (value is Span span) InlineChildren(span.Inlines); }
            }
            InlineChildren(owner.Inlines);
            var states = new JsonArray(); var observed = new HashSet<DependencyObject>(ReferenceEqualityComparer.Instance);
            while (inputs.Except(observed).FirstOrDefault() is { } value)
            {
                observed.Add(value); var id = Track(value); var props = new JsonObject();
                foreach (var (name, property) in properties[value]) props[name] = Value(value.GetValue(property), inputs);
                var record = new JsonObject { ["object_id"] = id, ["type"] = value.GetType().FullName, ["properties"] = props };
                if (value is FrameworkElement element)
                {
                    var transform = element.TransformToVisual(root); var p = transform.TransformPoint(new Point());
                    var x = transform.TransformPoint(new Point(1, 0)); var y = transform.TransformPoint(new Point(0, 1));
                    record["layout"] = new JsonObject { ["is_loaded"] = element.IsLoaded, ["width"] = element.ActualWidth, ["height"] = element.ActualHeight,
                        ["transform_to_root"] = new JsonArray(x.X - p.X, x.Y - p.Y, y.X - p.X, y.Y - p.Y, p.X, p.Y) };
                }
                if (value is ScrollViewer viewer) record["scroll"] = new JsonArray(viewer.HorizontalOffset, viewer.VerticalOffset, viewer.ZoomFactor, viewer.ViewportWidth, viewer.ViewportHeight);
                if (value is TextBlock block) record["is_text_trimmed"] = block.IsTextTrimmed;
                if (value is Run run)
                {
                    record["run_text"] = RunTextBindingJournal.Text(run.Text);
                    var observation = runBindings[run].Inspect();
                    record["run_text_binding"] = observation;
                    record["run_text_change_notifications_available"] = properties[value].Any(property => property.Name == "Text")
                        || observation["channel_available"]?.GetValue<bool>() == true;
                }
                if (value is Geometry geometry && geometry is not RectangleGeometry) record["unsupported_clip_geometry"] = true;
                if (value is TransformGroup) record["unobserved_transform_collection_mutations"] = true;
                states.Add(record);
            }
            var origin = new CapturePoint(); if (!ClientToScreen(hwnd, ref origin)) throw new InvalidOperationException("Text frame ClientToScreen failed");
            return new JsonObject { ["owner_object_id"] = Track(owner), ["ancestry"] = ancestry, ["inline_objects"] = inlines,
                ["objects"] = states, ["client_origin"] = new JsonArray(origin.x, origin.y), ["rasterization_scale"] = root.XamlRoot.RasterizationScale,
                ["root_size"] = new JsonArray(root.ActualWidth, root.ActualHeight) };
        }

        private void LayoutChanged(object? sender, object args)
        {
            if (reading || disposed) return;
            reading = true;
            try
            {
                foreach (var owner in owners)
                {
                    var current = State(owner);
                    if (lastStates.TryGetValue(owner, out var previous) && !JsonNode.DeepEquals(previous, current)) Changed(owner, "LayoutUpdated.input-signature");
                    lastStates[owner] = current;
                }
            }
            catch (Exception ex) { errors.Add(ex.ToString()); }
            finally { reading = false; }
        }

        internal void Checkpoint(string stage)
        {
            var checkpoint = new JsonObject { ["stage"] = stage, ["started_qpc"] = Stopwatch.GetTimestamp(), ["revision"] = revision };
            checkpoints.Add(checkpoint); reading = true;
            try
            {
                var current = CurrentOwners(); checkpoint["same_owner_references"] = owners.Length == current.Length && owners.Zip(current).All(pair => ReferenceEquals(pair.First, pair.Second));
                var states = new JsonArray(); foreach (var owner in owners) states.Add(State(owner)); checkpoint["owners"] = states;
            }
            catch (Exception ex) { checkpoint["error"] = ex.ToString(); errors.Add(ex.ToString()); }
            finally { reading = false; checkpoint["completed_qpc"] = Stopwatch.GetTimestamp(); checkpoint["revision_after"] = revision; }
        }

        internal void Bind(IReadOnlyDictionary<DependencyObject, string> renderIds)
        {
            var result = new JsonArray(); Receipt["owners"] = result;
            foreach (var owner in owners)
            {
                var found = renderIds.TryGetValue(owner, out var id); if (found) xamlIds[owner] = id!;
                result.Add(new JsonObject { ["owner_object_id"] = Track(owner), ["xaml_id"] = id, ["same_object_reference"] = found,
                    ["type"] = owner.GetType().FullName });
            }
        }
        internal void IdentityPeer(TextBlock owner, AutomationPeer peer)
        {
            if (!owners.Contains(owner, ReferenceEqualityComparer.Instance)) return;
            try { identityPeers[owner] = (peer, peer.EventsSource); }
            catch (Exception ex) { errors.Add("Identity peer EventsSource: " + ex); }
        }
        internal JsonObject ObserveProvider(TextBlock owner, AutomationPeer? peer, string stage)
        {
            reading = true;
            var record = new JsonObject { ["stage"] = stage, ["qpc"] = Stopwatch.GetTimestamp(), ["revision"] = revision,
                ["owner_object_id"] = ids.GetValueOrDefault(owner, -1), ["xaml_id"] = xamlIds.GetValueOrDefault(owner),
                ["same_retained_owner"] = owners.Contains(owner, ReferenceEqualityComparer.Instance) };
            try
            {
                var bound = identityPeers.TryGetValue(owner, out var identity);
                record["same_identity_peer"] = bound && ReferenceEquals(identity.Peer, peer);
                record["same_identity_events_source"] = bound && peer != null && ReferenceEquals(identity.Events, peer.EventsSource);
                record["state"] = State(owner);
            }
            catch (Exception ex) { record["error"] = ex.ToString(); errors.Add(ex.ToString()); }
            finally { reading = false; record["completed_qpc"] = Stopwatch.GetTimestamp(); record["revision_after"] = revision; }
            return record;
        }
        public void Dispose()
        {
            if (disposed) return; disposed = true;
            for (var i = detach.Count - 1; i >= 0; i--) try { detach[i](); } catch (Exception ex) { errors.Add("Detach: " + ex); }
            Receipt["ended_qpc"] = Stopwatch.GetTimestamp(); Receipt["final_revision"] = revision; Receipt["disposed"] = true;
        }
    }
}
