using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using System.Text.Json;
using System.Text.Json.Nodes;
using Windows.Foundation;

namespace Relic;

public sealed partial class MainWindow
{
    private NativeTextarea? capturedTextarea;
    private JsonObject? capturedTextareaEvidence, capturedTextareaBaseline;
    private Action<NativeTextareaResizeEvent>? textareaDragObserver;
    private readonly List<(RoutedEvent Event, PointerEventHandler Handler)> textareaPointerObservers = new();

    private async Task CaptureTextareaScene()
    {
        if (!VisualCaptureEnabled || visibleDialog == null) throw new InvalidOperationException("Textarea input capture requires the actual CI new-organization dialog.");
        capturedTextarea = CaptureSuggestionInput(visibleDialog, "new-org-purpose") as NativeTextarea
            ?? throw new InvalidOperationException("The production new-organization purpose is not a NativeTextarea.");
        var input = capturedTextarea;
        capturedTextareaEvidence = new JsonObject
        {
            ["source"] = "actual native TextBox/Thumb + Win32 mouse move/down/up + routed pointer/drag events",
            ["scene"] = "new-org-textarea-resized", ["automation_id"] = AutomationProperties.GetAutomationId(input),
            ["errors"] = new JsonArray(), ["pointer_events"] = new JsonArray(), ["drag_events"] = new JsonArray(), ["checkpoints"] = new JsonArray(),
        };
        root.UpdateLayout();
        if (input.ResizeTemplateFailure != null || input.ResizeGrip is not { IsLoaded: true } grip || !grip.Handle.IsLoaded)
            throw new InvalidOperationException("Actual textarea resize Thumb did not load: " + input.ResizeTemplateFailure);
        var before = ObserveTextareaState();
        capturedTextareaEvidence["before"] = before;
        var beforeSequence = input.ResizeSequence; var beforeDeltas = input.ResizeDeltaCount;
        var beforeText = input.Text; var beforePlaceholder = input.PlaceholderText;
        var box = input.TransformToVisual(root).TransformBounds(new Rect(0, 0, input.ActualWidth, input.ActualHeight));
        if (box.Width <= 6 || box.Height <= 6) throw new InvalidOperationException("Actual textarea has no usable corner for the shared gesture.");
        var start = new Point(box.Right - 3, box.Bottom - 3); var end = new Point(start.X, start.Y + 64);
        capturedTextareaEvidence["action"] = new JsonObject
        {
            ["start"] = new JsonObject { ["x"] = start.X, ["y"] = start.Y }, ["end"] = new JsonObject { ["x"] = end.X, ["y"] = end.Y },
            ["delta"] = new JsonObject { ["x"] = 0, ["y"] = 64 }, ["steps"] = 8, ["units"] = "window device-independent pixels",
            ["quantity"] = "requested pointer path derived from actual owner bounds; not measured resize-handle geometry",
        };
        textareaDragObserver = record => ((JsonArray)capturedTextareaEvidence["drag_events"]!).Add(JsonSerializer.SerializeToNode(record));
        input.ResizeObserved += textareaDragObserver;
        foreach (var (kind, routedEvent) in new[] { ("pointer-pressed", UIElement.PointerPressedEvent), ("pointer-moved", UIElement.PointerMovedEvent),
                     ("pointer-released", UIElement.PointerReleasedEvent), ("pointer-canceled", UIElement.PointerCanceledEvent) })
        {
            PointerEventHandler observer = (_, args) =>
            {
                var actual = args.GetCurrentPoint(root);
                ((JsonArray)capturedTextareaEvidence["pointer_events"]!).Add(new JsonObject
                {
                    ["kind"] = kind, ["source"] = "actual PointerRoutedEventArgs", ["pointer_id"] = args.Pointer.PointerId,
                    ["pointer_device"] = args.Pointer.PointerDeviceType.ToString(), ["timestamp"] = JsonValue.Create(actual.Timestamp),
                    ["x"] = actual.Position.X, ["y"] = actual.Position.Y, ["left_button_pressed"] = actual.Properties.IsLeftButtonPressed,
                    ["original_source_type"] = args.OriginalSource?.GetType().Name,
                });
            };
            input.AddHandler(routedEvent, observer, true); textareaPointerObservers.Add((routedEvent, observer));
        }
        await CaptureMovePointer(start);
        CapturePointerButton(true);
        try
        {
            await Task.Delay(40);
            for (var step = 1; step <= 8; step++)
            {
                await CaptureMovePointer(new Point(start.X, start.Y + 64d * step / 8));
                await Task.Delay(25);
            }
        }
        finally { CapturePointerButton(false); }
        await Task.Delay(150); root.UpdateLayout();
        var after = ObserveTextareaState(); capturedTextareaEvidence["after"] = after;
        var finalBox = input.TransformToVisual(root).TransformBounds(new Rect(0, 0, input.ActualWidth, input.ActualHeight));
        capturedTextareaEvidence["geometry_delta"] = new JsonObject
        { ["x"] = finalBox.X - box.X, ["y"] = finalBox.Y - box.Y, ["width"] = finalBox.Width - box.Width, ["height"] = finalBox.Height - box.Height };
        if (input.ResizeSequence <= beforeSequence || input.ResizeDeltaCount <= beforeDeltas || input.IsResizing || finalBox.Height <= box.Height)
            throw new InvalidOperationException("The real corner gesture did not complete a production Thumb drag that increased textarea height.");
        if (input.Text != beforeText || input.PlaceholderText != beforePlaceholder)
            throw new InvalidOperationException("Actual textarea resizing changed its text or placeholder.");
        capturedTextareaBaseline = null;
        CaptureTextareaCheckpoint("after_action");
    }

    private JsonObject ObserveTextareaState()
    {
        if (!VisualCaptureEnabled || capturedTextarea is not { } input) throw new InvalidOperationException("No actual CI textarea is being observed.");
        if (!input.IsLoaded || input.Visibility != Visibility.Visible || input.ResizeGrip is not { IsLoaded: true } grip)
            throw new InvalidOperationException("The actual resized textarea or grip unloaded during capture.");
        if (visibleDialog == null || !ReferenceEquals(input, CaptureSuggestionInput(visibleDialog, "new-org-purpose")))
            throw new InvalidOperationException("The actual captured textarea instance was replaced.");
        JsonObject Bounds(FrameworkElement element) => CaptureBox(element.TransformToVisual(root).TransformBounds(new Rect(0, 0, element.ActualWidth, element.ActualHeight)));
        JsonNode? Finite(double value) => double.IsFinite(value) ? JsonValue.Create(value) : null;
        JsonObject? Brush(SolidColorBrush? brush) => brush == null ? null : new JsonObject
        {
            ["quantity"] = "actual WinUI SolidColorBrush components and independent opacity", ["red"] = brush.Color.R,
            ["green"] = brush.Color.G, ["blue"] = brush.Color.B, ["alpha_byte"] = brush.Color.A, ["opacity"] = brush.Opacity,
        };
        var cursor = new CapturePoint(); var origin = new CapturePoint();
        if (!GetCursorPos(ref cursor) || !ClientToScreen(WinRT.Interop.WindowNative.GetWindowHandle(this), ref origin))
            throw new InvalidOperationException("Actual textarea capture cursor measurement failed.");
        var scale = root.XamlRoot.RasterizationScale;
        return new JsonObject
        {
            ["identity"] = AutomationProperties.GetAutomationId(input), ["same_instance"] = true,
            ["bounds"] = Bounds(input), ["value"] = input.Text, ["placeholder"] = input.PlaceholderText,
            ["accepts_return"] = input.AcceptsReturn, ["readonly"] = input.IsReadOnly, ["enabled"] = input.IsEnabled,
            ["focus_state"] = input.FocusState.ToString(), ["selection_start"] = input.SelectionStart, ["selection_length"] = input.SelectionLength,
            ["width_property"] = Finite(input.Width), ["height_property"] = Finite(input.Height), ["background"] = Brush(input.Background as SolidColorBrush),
            ["foreground"] = Brush(input.Foreground as SolidColorBrush), ["border"] = Brush(input.BorderBrush as SolidColorBrush),
            ["font_family"] = input.FontFamily.Source, ["font_size"] = input.FontSize,
            ["resize_sequence"] = input.ResizeSequence, ["resize_delta_count"] = input.ResizeDeltaCount, ["is_resizing"] = input.IsResizing,
            ["grip"] = new JsonObject
            {
                ["kind"] = "resize-handle", ["source"] = "actual production Thumb and vector template; independent of reference grip gaps",
                ["bounds"] = Bounds(grip.Handle), ["enabled"] = grip.Handle.IsEnabled, ["visibility"] = grip.Handle.Visibility.ToString(),
                ["hovered"] = grip.IsPointerOverGrip, ["dragging"] = grip.Handle.IsDragging, ["focus_state"] = grip.Handle.FocusState.ToString(),
                ["foreground"] = Brush(grip.Handle.Foreground as SolidColorBrush), ["automation_id"] = AutomationProperties.GetAutomationId(grip.Handle),
            },
            ["pointer"] = new JsonObject { ["x"] = (cursor.x - origin.x) / scale, ["y"] = (cursor.y - origin.y) / scale, ["rasterization_scale"] = scale },
        };
    }

    private void CaptureTextareaCheckpoint(string stage)
    {
        if (capturedTextareaEvidence == null) return;
        var state = ObserveTextareaState();
        var receipt = new JsonObject { ["stage"] = stage, ["state"] = state, ["pointer_event_count"] = ((JsonArray)capturedTextareaEvidence["pointer_events"]!).Count,
            ["drag_event_count"] = ((JsonArray)capturedTextareaEvidence["drag_events"]!).Count };
        ((JsonArray)capturedTextareaEvidence["checkpoints"]!).Add(receipt);
        if (capturedTextareaBaseline == null) capturedTextareaBaseline = (JsonObject)receipt.DeepClone();
        else if (!JsonNode.DeepEquals(state, capturedTextareaBaseline["state"])
                 || receipt["pointer_event_count"]!.GetValue<int>() != capturedTextareaBaseline["pointer_event_count"]!.GetValue<int>()
                 || receipt["drag_event_count"]!.GetValue<int>() != capturedTextareaBaseline["drag_event_count"]!.GetValue<int>())
            throw new InvalidOperationException("Actual textarea identity, geometry, text, style, state or pointer/drag evidence changed during " + stage);
    }

    private void EndTextareaCapture()
    {
        if (capturedTextarea is { } input)
        {
            if (textareaDragObserver != null) input.ResizeObserved -= textareaDragObserver;
            foreach (var (routedEvent, observer) in textareaPointerObservers) input.RemoveHandler(routedEvent, observer);
        }
        textareaPointerObservers.Clear(); textareaDragObserver = null;
        capturedTextarea = null; capturedTextareaEvidence = capturedTextareaBaseline = null;
    }
}
