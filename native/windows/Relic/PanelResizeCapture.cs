using System.Text.Json.Nodes;
#if WINDOWS
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Windows.Foundation;
#endif

namespace Relic;

// Linked into the existing no-UI test project. This class only classifies the
// actual observer receipt; it cannot open/close a ToolTip or alter capture state.
internal static class PanelResizeToolTipReadiness
{
    internal static string? Observe(JsonObject state)
    {
        static bool? Flag(JsonNode? value) => value is JsonValue flag && flag.TryGetValue<bool>(out var result) ? result : null;
        static int? Index(JsonNode? value) => value is JsonValue index && index.TryGetValue<int>(out var result) && result >= 0 ? result : null;
        static bool Positive(JsonNode? value) => value is JsonValue number && number.TryGetValue<double>(out var result) && double.IsFinite(result) && result > 0;
        if (state["owned_tooltip"] is not JsonObject tip
            || Flag(tip["same_tooltip_instance"]) != true || Flag(tip["attached_same_tooltip_object"]) != true
            || Flag(tip["is_open"]) is not bool open
            || tip["actual_popup_indices"] is not JsonArray indices || state["open_popups"] is not JsonArray popups)
            return null;
        var owned = new List<int>();
        foreach (var item in popups)
        {
            if (item is not JsonObject popup || Flag(popup["child_same_owned_tooltip_object"]) is not bool same)
                return null;
            if (!same) continue;
            if (Flag(popup["is_open"]) != true || Index(popup["capture_popup_index"]) is not int index)
                return null;
            owned.Add(index);
        }
        if (!open) return indices.Count == 0 && owned.Count == 0 ? "closed" : null;
        return indices.Count == 1 && owned.Count == 1 && Index(indices[0]) == owned[0]
            && Flag(tip["is_loaded"]) == true && tip["visibility"]?.ToString() == "Visible"
            && Positive(tip["opacity"]) && tip["bounds"] is JsonObject bounds
            && Positive(bounds["width"]) && Positive(bounds["height"]) ? "open" : null;
    }
}

#if WINDOWS
public sealed partial class MainWindow
{
    private Thumb? capturedPanelResize;
    private ToolTip? capturedPanelResizeToolTip;
    private JsonObject? capturedPanelResizeEvidence, capturedPanelResizeBaseline;
    private bool capturedPanelResizePointerOver;
    private DragStartedEventHandler? panelResizeStartedObserver;
    private DragDeltaEventHandler? panelResizeDeltaObserver;
    private DragCompletedEventHandler? panelResizeCompletedObserver;
    private readonly List<(RoutedEvent Event, PointerEventHandler Handler)> panelResizePointerObservers = new();
    private RoutedEventHandler? panelResizeToolTipOpenedObserver, panelResizeToolTipClosedObserver;
    private readonly List<Popup> panelResizeObservedPopups = new();

    private async Task CapturePanelResizeScene(string scene)
    {
        if (!VisualCaptureEnabled || scene is not ("panel-resize-hover" or "panel-resized"))
            throw new InvalidOperationException("Panel resize input capture requires an actual CI resize scene");
        EndPanelResizeCapture();
        capturedPanelResizeEvidence = new JsonObject
        {
            ["scene"] = scene, ["source"] = "Production MainWindow.panelResize Thumb; real SendInput and routed pointer/drag observations",
            ["errors"] = new JsonArray(), ["pointer_events"] = new JsonArray(),
            ["drag_events"] = new JsonArray(), ["tooltip_events"] = new JsonArray(), ["checkpoints"] = new JsonArray(),
            ["phases"] = new JsonArray(),
            ["qpc_frequency"] = Stopwatch.Frequency,
            ["desired_capture_state"] = "idle-hover-with-measured-owned-production-tooltip-state",
            ["observed_capture_state"] = "unresolved",
            ["tooltip_free_reference_equivalence_claimed"] = false,
            ["parity_scope"] = "Readiness requires idle hover and an observed open or closed production ToolTip, not a prescribed opening. Open popups remain captured visible elements requiring their own reference counterparts; all later state and event-count changes still fail continuity."
        };
        // At the narrow size the production pane starts closed. Open it through
        // the actual overview toolbar control, never by assigning panelOpen.
        if (!panelOpen || pane != "overview")
        {
            var accessibleName = T("appbar.pane_shortcut", ("pane", T("panel.overview")), ("key", "Alt+1"));
            var buttons = toolbar.PrimaryCommands.OfType<AppBarElementContainer>().Select(item => item.Content)
                .OfType<Button>().Where(button => AutomationProperties.GetName(button) == accessibleName).ToArray();
            if (buttons.Length != 1) throw new InvalidOperationException("No unique actual overview toolbar control for opening the resize pane");
            capturedPanelResizeEvidence["open_control"] = new JsonObject
            {
                ["accessible_name"] = AutomationProperties.GetName(buttons[0]),
                ["bounds"] = PanelResizeBox(buttons[0]), ["action"] = "actual pointer click"
            };
            await CaptureClick(buttons[0]); await Task.Delay(150); root.UpdateLayout();
        }
        if (!panelOpen || pane != "overview" || panelResize is not { IsLoaded: true } handle)
            throw new InvalidOperationException("The actual overview resize Thumb is not loaded and open");
        capturedPanelResize = handle;
        if (!paneResizeToolTips.TryGetValue(handle, out var tooltip)
            || !ReferenceEquals(ToolTipService.GetToolTip(handle), tooltip))
            throw new InvalidOperationException("The production resize Thumb has no identically bound retained ToolTip");
        capturedPanelResizeToolTip = tooltip;
        ObservePanelResizeEvents(handle);
        ObservePanelResizeToolTipEvents(handle, tooltip);
        root.UpdateLayout();
        var before = ObservePanelResizeState(); capturedPanelResizeEvidence["before"] = before;
        var paneBefore = inspectorSurface.TransformToVisual(root).TransformBounds(new Rect(0, 0, inspectorSurface.ActualWidth, inspectorSurface.ActualHeight));
        var handleBefore = handle.TransformToVisual(root).TransformBounds(new Rect(0, 0, handle.ActualWidth, handle.ActualHeight));
        if (handleBefore.Width <= 0 || handleBefore.Height <= 0 || handle.Visibility != Visibility.Visible || !handle.IsEnabled)
            throw new InvalidOperationException("The production panel resize Thumb has no usable visible bounds");
        var start = new Point(handleBefore.X + handleBefore.Width / 2, handleBefore.Y + handleBefore.Height / 2);
        capturedPanelResizeEvidence["action"] = new JsonObject
        {
            ["kind"] = scene == "panel-resized" ? "pointer-down, eight leftward moves, pointer-up" : "pointer hover",
            ["start"] = new JsonObject { ["x"] = start.X, ["y"] = start.Y },
            ["requested_delta_x"] = scene == "panel-resized" ? -64 : 0,
            ["requested_delta_y"] = 0, ["requested_move_steps"] = scene == "panel-resized" ? 8 : 1,
            ["units"] = "window DIPs; actual screen input and cursor are recorded separately"
        };
        await CaptureMovePointer(start);
        await Task.Delay(100); root.UpdateLayout();
        await AwaitPanelResizeHover("initial-hover");
        capturedPanelResizeEvidence["hover"] = ObservePanelResizeState();
        RequirePanelResizeHover();
        if (scene == "panel-resized")
        {
            CapturePointerButton(true);
            try
            {
                await Task.Delay(40);
                for (var step = 1; step <= 8; step++)
                {
                    await CaptureMovePointer(new Point(start.X - 64d * step / 8, start.Y));
                    await Task.Delay(25);
                }
            }
            finally { CapturePointerButton(false); }
        }
        await Task.Delay(150); root.UpdateLayout();
        await AwaitPanelResizeHover("after-action-hover");
        var after = ObservePanelResizeState(); capturedPanelResizeEvidence["after"] = after;
        var tooltipState = PanelResizeToolTipReadiness.Observe(after);
        capturedPanelResizeEvidence["observed_capture_state"] = tooltipState != null
            ? "idle-hover-with-owned-production-tooltip-" + tooltipState : "unresolved";
        var paneAfter = inspectorSurface.TransformToVisual(root).TransformBounds(new Rect(0, 0, inspectorSurface.ActualWidth, inspectorSurface.ActualHeight));
        var delta = new JsonObject { ["x"] = paneAfter.X - paneBefore.X, ["y"] = paneAfter.Y - paneBefore.Y,
            ["width"] = paneAfter.Width - paneBefore.Width, ["height"] = paneAfter.Height - paneBefore.Height };
        capturedPanelResizeEvidence["actual_pane_geometry_delta"] = delta;
        var dragEvents = ((JsonArray)capturedPanelResizeEvidence["drag_events"]!).OfType<JsonObject>().ToArray();
        if (scene == "panel-resized")
        {
            if (paneAfter.X - paneBefore.X != -64 || paneAfter.Width - paneBefore.Width != 64
                || paneAfter.Y != paneBefore.Y || paneAfter.Height != paneBefore.Height)
                throw new InvalidOperationException("Actual production panel drag did not move its left edge -64 DIP and increase width +64 DIP with stable top/height");
            if (dragEvents.Count(item => item["kind"]?.ToString() == "drag-started") != 1
                || dragEvents.Count(item => item["kind"]?.ToString() == "drag-delta") == 0
                || dragEvents.Count(item => item["kind"]?.ToString() == "drag-completed") != 1
                || dragEvents.Any(item => item["canceled"]?.GetValue<bool>() == true))
                throw new InvalidOperationException("The real resize gesture did not complete one uncanceled production Thumb drag");
        }
        else if (dragEvents.Length != 0 || !paneAfter.Equals(paneBefore))
            throw new InvalidOperationException("Hover unexpectedly dragged or changed the actual pane geometry");
        RequirePanelResizeHover();
        CapturePanelResizeCheckpoint("after_action");
    }

    private void ObservePanelResizeEvents(Thumb handle)
    {
        void Drag(string kind, double dx, double dy, bool? canceled = null)
        {
            ((JsonArray)capturedPanelResizeEvidence!["drag_events"]!).Add(new JsonObject
            {
                ["kind"] = kind, ["qpc"] = Stopwatch.GetTimestamp(), ["horizontal_change"] = dx,
                ["vertical_change"] = dy, ["canceled"] = canceled, ["is_dragging"] = handle.IsDragging,
                ["handle_bounds"] = PanelResizeBox(handle), ["pane_bounds"] = PanelResizeBox(inspectorSurface),
                ["actual_panel_width_state"] = panelWidth
            });
        }
        panelResizeStartedObserver = (_, args) => Drag("drag-started", args.HorizontalOffset, args.VerticalOffset);
        panelResizeDeltaObserver = (_, args) => Drag("drag-delta", args.HorizontalChange, args.VerticalChange);
        panelResizeCompletedObserver = (_, args) => Drag("drag-completed", args.HorizontalChange, args.VerticalChange, args.Canceled);
        handle.DragStarted += panelResizeStartedObserver; handle.DragDelta += panelResizeDeltaObserver; handle.DragCompleted += panelResizeCompletedObserver;
        foreach (var (kind, routedEvent) in new[]
        {
            ("pointer-entered", UIElement.PointerEnteredEvent), ("pointer-exited", UIElement.PointerExitedEvent),
            ("pointer-pressed", UIElement.PointerPressedEvent), ("pointer-moved", UIElement.PointerMovedEvent),
            ("pointer-released", UIElement.PointerReleasedEvent), ("pointer-canceled", UIElement.PointerCanceledEvent),
            ("pointer-capture-lost", UIElement.PointerCaptureLostEvent)
        })
        {
            PointerEventHandler observer = (_, args) =>
            {
                var observedQpc = Stopwatch.GetTimestamp();
                if (kind == "pointer-entered") capturedPanelResizePointerOver = true;
                if (kind is "pointer-exited" or "pointer-canceled") capturedPanelResizePointerOver = false;
                var point = args.GetCurrentPoint(root);
                ((JsonArray)capturedPanelResizeEvidence!["pointer_events"]!).Add(new JsonObject
                {
                    ["kind"] = kind, ["source"] = "actual PointerRoutedEventArgs on production panel Thumb",
                    ["qpc"] = observedQpc, ["is_generated"] = args.IsGenerated,
                    ["timestamp"] = JsonValue.Create(point.Timestamp), ["pointer_id"] = args.Pointer.PointerId,
                    ["device"] = args.Pointer.PointerDeviceType.ToString(), ["x"] = point.Position.X, ["y"] = point.Position.Y,
                    ["position_source"] = "actual PointerRoutedEventArgs.GetCurrentPoint(root).Position; root-relative DIPs",
                    ["left_button_pressed"] = point.Properties.IsLeftButtonPressed, ["original_source_type"] = args.OriginalSource?.GetType().FullName
                });
            };
            handle.AddHandler(routedEvent, observer, true); panelResizePointerObservers.Add((routedEvent, observer));
        }
    }

    private void RecordPanelResizePhase(string stage)
    {
        if (!VisualCaptureEnabled || capturedPanelResizeEvidence == null) return;
        // Diagnostic only. A generated event is still counted by the unchanged
        // continuity gate; this does not establish or reset any baseline.
        ((JsonArray)capturedPanelResizeEvidence["phases"]!).Add(new JsonObject
        {
            ["stage"] = stage, ["qpc"] = Stopwatch.GetTimestamp(),
            ["pointer_event_count"] = ((JsonArray)capturedPanelResizeEvidence["pointer_events"]!).Count,
            ["drag_event_count"] = ((JsonArray)capturedPanelResizeEvidence["drag_events"]!).Count,
            ["tooltip_event_count"] = ((JsonArray)capturedPanelResizeEvidence["tooltip_events"]!).Count
        });
    }

    private void ObservePanelResizeToolTipEvents(Thumb handle, ToolTip tooltip)
    {
        void Record(string kind, object sender)
        {
            ((JsonArray)capturedPanelResizeEvidence!["tooltip_events"]!).Add(new JsonObject
            {
                ["kind"] = kind, ["qpc"] = Stopwatch.GetTimestamp(),
                ["source"] = "Opened/Closed event on the retained production ToolTip passed to ToolTipService for this actual Thumb",
                ["sender_same_tooltip_object"] = ReferenceEquals(sender, tooltip),
                ["same_thumb_object"] = ReferenceEquals(handle, panelResize),
                ["production_map_same_tooltip_object"] = paneResizeToolTips.TryGetValue(handle, out var current) && ReferenceEquals(current, tooltip),
                ["attached_same_tooltip_object"] = ReferenceEquals(ToolTipService.GetToolTip(handle), tooltip),
                ["is_open"] = tooltip.IsOpen, ["is_loaded"] = tooltip.IsLoaded
            });
        }
        panelResizeToolTipOpenedObserver = (sender, _) => Record("opened", sender);
        panelResizeToolTipClosedObserver = (sender, _) => Record("closed", sender);
        tooltip.Opened += panelResizeToolTipOpenedObserver;
        tooltip.Closed += panelResizeToolTipClosedObserver;
    }

    private int ObservePanelResizePopupIdentity(Popup popup)
    {
        var index = panelResizeObservedPopups.FindIndex(value => ReferenceEquals(value, popup));
        if (index >= 0) return index;
        panelResizeObservedPopups.Add(popup);
        return panelResizeObservedPopups.Count - 1;
    }

    private JsonObject PanelResizeBox(FrameworkElement element)
    {
        var box = element.TransformToVisual(root).TransformBounds(new Rect(0, 0, element.ActualWidth, element.ActualHeight));
        return new JsonObject { ["x"] = box.X, ["y"] = box.Y, ["width"] = box.Width, ["height"] = box.Height };
    }

    private JsonObject ObservePanelResizeState()
    {
        if (!VisualCaptureEnabled || capturedPanelResize is not { IsLoaded: true } handle || !ReferenceEquals(handle, panelResize))
            throw new InvalidOperationException("The observed production resize Thumb changed or unloaded");
        if (VisualTreeHelper.GetParent(chatHead) is not FrameworkElement conversation)
            throw new InvalidOperationException("The production conversation region has no current layout parent");
        var states = new JsonArray(); var paintedParts = new JsonArray();
        void Walk(DependencyObject value)
        {
            if (value is FrameworkElement element)
            {
                foreach (var group in VisualStateManager.GetVisualStateGroups(element))
                    states.Add(new JsonObject { ["owner"] = element.Name, ["group"] = group.Name, ["current_state"] = group.CurrentState?.Name });
                if (element is Panel panel && panel.Background is SolidColorBrush brush)
                    paintedParts.Add(new JsonObject { ["name"] = element.Name, ["type"] = element.GetType().FullName,
                        ["bounds"] = PanelResizeBox(element), ["opacity"] = element.Opacity,
                        ["background_rgba8"] = new JsonArray(brush.Color.R, brush.Color.G, brush.Color.B, brush.Color.A), ["brush_opacity"] = brush.Opacity });
            }
            for (var index = 0; index < VisualTreeHelper.GetChildrenCount(value); index++) Walk(VisualTreeHelper.GetChild(value, index));
        }
        Walk(handle);
        var cursor = new CapturePoint(); var origin = new CapturePoint();
        if (!GetCursorPos(ref cursor) || !ClientToScreen(WinRT.Interop.WindowNative.GetWindowHandle(this), ref origin))
            throw new InvalidOperationException("Panel resize cursor measurement failed");
        var scale = root.XamlRoot.RasterizationScale;
        var location = new Point((cursor.x - origin.x) / scale, (cursor.y - origin.y) / scale);
        var hits = VisualTreeHelper.FindElementsInHostCoordinates(location, root, true).ToArray();
        var popups = new JsonArray(); var ownedPopups = new JsonArray();
        foreach (var popup in VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot).Where(value => value.IsOpen))
        {
            var popupIndex = ObservePanelResizePopupIdentity(popup);
            var owned = capturedPanelResizeToolTip != null && ReferenceEquals(popup.Child, capturedPanelResizeToolTip);
            if (owned) ownedPopups.Add(popupIndex);
            popups.Add(new JsonObject { ["capture_popup_index"] = popupIndex,
                ["child_same_owned_tooltip_object"] = owned,
                ["child_type"] = popup.Child?.GetType().FullName, ["is_open"] = popup.IsOpen,
                ["bounds"] = popup.Child is FrameworkElement child ? PanelResizeBox(child) : null });
        }
        var tip = capturedPanelResizeToolTip;
        var ownedToolTip = new JsonObject
        {
            ["source"] = "Retained production ToolTip + ToolTipService.GetToolTip(actual Thumb) + current Popup.Child ReferenceEquals",
            ["same_tooltip_instance"] = tip != null && paneResizeToolTips.TryGetValue(handle, out var currentTip) && ReferenceEquals(tip, currentTip),
            ["attached_same_tooltip_object"] = tip != null && ReferenceEquals(ToolTipService.GetToolTip(handle), tip),
            ["is_open"] = tip?.IsOpen, ["is_loaded"] = tip?.IsLoaded,
            ["visibility"] = tip?.Visibility.ToString(), ["opacity"] = tip?.Opacity,
            ["content"] = tip?.Content is string text ? text : null,
            ["content_type"] = tip?.Content?.GetType().FullName,
            ["actual_popup_indices"] = ownedPopups,
            ["bounds"] = tip is { IsLoaded: true, IsOpen: true } ? PanelResizeBox(tip) : null
        };
        return new JsonObject
        {
            ["same_thumb_instance"] = true, ["pane"] = pane, ["panel_open"] = panelOpen,
            ["actual_panel_width_state"] = panelWidth, ["actual_file_width_state"] = fileWidth,
            ["sidebar"] = PanelResizeBox(sidebarSurface), ["conversation"] = PanelResizeBox(conversation), ["pane_bounds"] = PanelResizeBox(inspectorSurface),
            ["columns"] = new JsonArray(columns.ColumnDefinitions.Select(column => (JsonNode?)JsonValue.Create(column.ActualWidth)).ToArray()),
            ["handle"] = new JsonObject { ["bounds"] = PanelResizeBox(handle), ["automation_id"] = AutomationProperties.GetAutomationId(handle),
                ["accessible_name"] = AutomationProperties.GetName(handle), ["visibility"] = handle.Visibility.ToString(), ["enabled"] = handle.IsEnabled,
                ["dragging"] = handle.IsDragging, ["focus_state"] = handle.FocusState.ToString(), ["hover_observed_by_events"] = capturedPanelResizePointerOver,
                ["pointer_hit_test_contains_handle"] = hits.Any(hit => ReferenceEquals(hit, handle)), ["visual_states"] = states, ["painted_template_parts"] = paintedParts },
            ["pointer"] = new JsonObject { ["x"] = location.X, ["y"] = location.Y, ["screen_x"] = cursor.x, ["screen_y"] = cursor.y,
                ["rasterization_scale"] = scale, ["left_button_pressed"] = (PanelResizeAsyncKeyState(1) & 0x8000) != 0 },
            ["open_popups"] = popups, ["owned_tooltip"] = ownedToolTip
        };
    }

    private static bool IsObservedPanelResizeHover(JsonObject state)
    {
        var handle = state["handle"]!;
        return handle["hover_observed_by_events"]?.GetValue<bool>() == true
            && handle["pointer_hit_test_contains_handle"]?.GetValue<bool>() == true
            && handle["dragging"]?.GetValue<bool>() == false && state["pointer"]!["left_button_pressed"]?.GetValue<bool>() == false
            && handle["visual_states"]!.AsArray().OfType<JsonObject>().Any(item => item["group"]?.ToString() == "CommonStates" && item["current_state"]?.ToString() == "PointerOver");
    }

    private async Task AwaitPanelResizeHover(string phase)
    {
        // Pointer release/capture-lost and the layout caused by a real drag are
        // queued independently. Wait for their observed result; do not create
        // another input event, assign a visual state or move the cursor again.
        // The final phase requires a measured ToolTip state, not an opening.
        // CaptureLost normally cancels an unopened tip after a real drag.
        var observations = new JsonArray();
        var requireMeasuredToolTip = phase == "after-action-hover";
        var wait = new JsonObject { ["phase"] = phase, ["deadline_ms"] = 1000,
            ["observations"] = observations, ["completed"] = false,
            ["requires_owned_tooltip_open"] = false, ["requires_measured_owned_tooltip_state"] = requireMeasuredToolTip };
        if (capturedPanelResizeEvidence!["hover_waits"] is not JsonArray waits)
            capturedPanelResizeEvidence["hover_waits"] = waits = new JsonArray();
        waits.Add(wait);
        var timer = Stopwatch.StartNew();
        while (true)
        {
            root.UpdateLayout();
            var state = ObservePanelResizeState();
            var elapsed = timer.Elapsed.TotalMilliseconds;
            observations.Add(new JsonObject { ["elapsed_ms"] = elapsed, ["qpc"] = Stopwatch.GetTimestamp(), ["state"] = state });
            if (elapsed <= 1000 && IsObservedPanelResizeHover(state) && (!requireMeasuredToolTip || PanelResizeToolTipReadiness.Observe(state) != null))
            { wait["completed"] = true; return; }
            if (elapsed >= 1000)
                throw new InvalidOperationException("Actual panel resize hover/measured owned ToolTip state did not settle within its existing deadline: " + phase);
            await Task.Delay(25);
        }
    }

    private void RequirePanelResizeHover()
    {
        if (!IsObservedPanelResizeHover(ObservePanelResizeState()))
            throw new InvalidOperationException("The actual pointer, hit test and production Thumb state do not establish an idle hover");
    }

    private void CapturePanelResizeCheckpoint(string stage)
    {
        if (capturedPanelResizeEvidence == null) return;
        var state = ObservePanelResizeState();
        var current = new JsonObject { ["stage"] = stage, ["qpc"] = Stopwatch.GetTimestamp(), ["state"] = state,
            ["pointer_event_count"] = ((JsonArray)capturedPanelResizeEvidence["pointer_events"]!).Count,
            ["drag_event_count"] = ((JsonArray)capturedPanelResizeEvidence["drag_events"]!).Count,
            ["tooltip_event_count"] = ((JsonArray)capturedPanelResizeEvidence["tooltip_events"]!).Count };
        ((JsonArray)capturedPanelResizeEvidence["checkpoints"]!).Add(current);
        if (!IsObservedPanelResizeHover(state) || PanelResizeToolTipReadiness.Observe(state) == null)
            throw new InvalidOperationException("Actual panel resize capture lacks idle hover or a measured owned ToolTip state: " + stage);
        if (capturedPanelResizeBaseline == null) capturedPanelResizeBaseline = current.DeepClone().AsObject();
        else if (!JsonNode.DeepEquals(state, capturedPanelResizeBaseline["state"])
            || current["pointer_event_count"]!.GetValue<int>() != capturedPanelResizeBaseline["pointer_event_count"]!.GetValue<int>()
            || current["drag_event_count"]!.GetValue<int>() != capturedPanelResizeBaseline["drag_event_count"]!.GetValue<int>()
            || current["tooltip_event_count"]!.GetValue<int>() != capturedPanelResizeBaseline["tooltip_event_count"]!.GetValue<int>())
            throw new InvalidOperationException("Actual pane, Thumb, pointer, popup or drag state changed during " + stage);
    }

    private void EndPanelResizeCapture()
    {
        if (capturedPanelResizeToolTip is { } tooltip)
        {
            if (panelResizeToolTipOpenedObserver != null) tooltip.Opened -= panelResizeToolTipOpenedObserver;
            if (panelResizeToolTipClosedObserver != null) tooltip.Closed -= panelResizeToolTipClosedObserver;
        }
        if (capturedPanelResize is { } handle)
        {
            if (panelResizeStartedObserver != null) handle.DragStarted -= panelResizeStartedObserver;
            if (panelResizeDeltaObserver != null) handle.DragDelta -= panelResizeDeltaObserver;
            if (panelResizeCompletedObserver != null) handle.DragCompleted -= panelResizeCompletedObserver;
            foreach (var (routedEvent, handler) in panelResizePointerObservers) handle.RemoveHandler(routedEvent, handler);
        }
        panelResizePointerObservers.Clear(); panelResizeStartedObserver = null; panelResizeDeltaObserver = null; panelResizeCompletedObserver = null;
        panelResizeToolTipOpenedObserver = panelResizeToolTipClosedObserver = null;
        capturedPanelResizeToolTip = null; panelResizeObservedPopups.Clear();
        capturedPanelResize = null; capturedPanelResizeEvidence = capturedPanelResizeBaseline = null; capturedPanelResizePointerOver = false;
    }

    [DllImport("user32.dll", EntryPoint = "GetAsyncKeyState")]
    private static extern short PanelResizeAsyncKeyState(int key);
}
#endif
