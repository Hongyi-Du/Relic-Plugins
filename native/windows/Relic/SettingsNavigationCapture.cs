using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using System.Text.Json.Nodes;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

namespace Relic;

public sealed partial class MainWindow
{
    private SelectorBarItem? settingsHoverTarget, settingsHoverSelected;
    private JsonObject? settingsHoverEvidence, settingsHoverBaseline;
    private PointerEventHandler? settingsHoverEntered, settingsHoverExited;
    private bool settingsHoverObserved;

    private async Task BeginSettingsNavigationCapture()
    {
        settingsHoverTarget = CaptureCardControl("settings-nav-notify") as SelectorBarItem
            ?? throw new InvalidOperationException("The production notification navigation item is missing");
        settingsHoverSelected = CaptureCardControl("settings-nav-appearance") as SelectorBarItem
            ?? throw new InvalidOperationException("The production appearance navigation item is missing");
        settingsHoverEvidence = new JsonObject { ["action"] = "actual pointer hover on unselected notification navigation",
            ["checkpoints"] = new JsonArray(), ["pointer_events"] = new JsonArray(), ["errors"] = new JsonArray() };
        void PointerEvent(string kind, bool hovered)
        {
            settingsHoverObserved = hovered;
            ((JsonArray)settingsHoverEvidence["pointer_events"]!).Add(new JsonObject
            { ["kind"] = kind, ["qpc"] = Stopwatch.GetTimestamp(), ["input_host"] = ObserveSettingsInputHost() });
        }
        settingsHoverEntered = (_, _) => PointerEvent("PointerEntered", true);
        settingsHoverExited = (_, _) => PointerEvent("PointerExited", false);
        settingsHoverTarget.PointerEntered += settingsHoverEntered;
        settingsHoverTarget.PointerExited += settingsHoverExited;
        await CaptureHover(settingsHoverTarget);
        await Task.Delay(150); root.UpdateLayout();
        CheckpointSettingsNavigationCapture("after_action");
    }

    private void CheckpointSettingsNavigationCapture(string stage)
    {
        if (settingsHoverEvidence == null) return;
        var target = settingsHoverTarget!;
        var cursor = new CapturePoint(); var origin = new CapturePoint();
        if (!GetCursorPos(ref cursor) || !ClientToScreen(WinRT.Interop.WindowNative.GetWindowHandle(this), ref origin))
            throw new InvalidOperationException("Cannot measure the settings hover pointer");
        var scale = root.XamlRoot.RasterizationScale;
        var point = new Windows.Foundation.Point((cursor.x - origin.x) / scale, (cursor.y - origin.y) / scale);
        // The settings item is in the ContentDialog's popup tree, not under
        // the main window content Grid. Host coordinates stay window-relative;
        // use the retained actual item as the subtree for this hit test.
        var hitElements = VisualTreeHelper.FindElementsInHostCoordinates(point, target, false).ToArray();
        var hit = hitElements.Any(value => ReferenceEquals(value, target));
        var bounds = target.TransformToVisual(root).TransformBounds(new Windows.Foundation.Rect(0, 0, target.ActualWidth, target.ActualHeight));
        var state = new JsonObject
        {
            ["automation_id"] = AutomationProperties.GetAutomationId(target), ["selected"] = target.IsSelected,
            ["appearance_selected"] = settingsHoverSelected!.IsSelected, ["is_loaded"] = target.IsLoaded,
            ["hover_observed"] = settingsHoverObserved, ["pointer_hit_test_contains_target"] = hit,
            ["hit_test_subtree"] = "retained actual notification SelectorBarItem",
            ["hit_test_objects"] = new JsonArray(hitElements.Select(value => (JsonNode)new JsonObject
                { ["runtime_type"] = value.GetType().FullName, ["same_target_reference"] = ReferenceEquals(value, target) }).ToArray()),
            ["pointer_x"] = point.X, ["pointer_y"] = point.Y,
            ["bounds"] = new JsonObject { ["x"] = bounds.X, ["y"] = bounds.Y, ["width"] = bounds.Width, ["height"] = bounds.Height },
            ["background"] = (target.Background as SolidColorBrush)?.Color.ToString()
        };
        ((JsonArray)settingsHoverEvidence["checkpoints"]!).Add(new JsonObject { ["stage"] = stage,
            ["qpc"] = Stopwatch.GetTimestamp(), ["state"] = state, ["input_host"] = ObserveSettingsInputHost() });
        if (!settingsHoverObserved || !hit || !target.IsLoaded || target.IsSelected || !settingsHoverSelected.IsSelected)
            throw new InvalidOperationException("The actual unselected settings navigation hover was not retained: " + stage);
        if (settingsHoverBaseline == null) settingsHoverBaseline = state.DeepClone().AsObject();
        else if (!JsonNode.DeepEquals(settingsHoverBaseline, state))
            throw new InvalidOperationException("Actual settings navigation hover changed during " + stage);
    }

    // Existing hover capture loses its hit target with an unchanged pointer and
    // unchanged XAML bounds during UIA reads. Record the actual receiving HWND
    // at the event/checkpoint; do not infer focus, move the pointer or reactivate
    // a window to repair the scene. These diagnostics do not alter state checks.
    private JsonObject ObserveSettingsInputHost()
    {
        JsonObject Window(IntPtr handle)
        {
            var title = new StringBuilder(256);
            var length = SettingsGetClassName(handle, title, title.Capacity);
            var thread = SettingsGetWindowThreadProcessId(handle, out var process);
            return new JsonObject { ["hwnd"] = handle.ToString("x"), ["process_id"] = process,
                ["thread_id"] = thread, ["class_name"] = length > 0 ? title.ToString() : null,
                ["root_owner_hwnd"] = SettingsGetAncestor(handle, 3).ToString("x") };
        }
        var cursor = new CapturePoint(); var observed = GetCursorPos(ref cursor);
        return new JsonObject
        {
            ["source"] = "Actual Win32 foreground/window-at-cursor and retained XAML input state",
            ["window"] = Window(WinRT.Interop.WindowNative.GetWindowHandle(this)),
            ["foreground"] = Window(SettingsGetForegroundWindow()),
            ["cursor_observed"] = observed, ["screen_x"] = observed ? cursor.x : null,
            ["screen_y"] = observed ? cursor.y : null,
            ["window_at_cursor"] = observed ? Window(SettingsWindowFromPoint(cursor)) : null,
            ["activation_state_active"] = active, ["root_hit_test_visible"] = root.IsHitTestVisible,
            ["target_hit_test_visible"] = settingsHoverTarget?.IsHitTestVisible,
            ["target_enabled"] = settingsHoverTarget?.IsEnabled,
            ["open_popup_count"] = VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot).Count
        };
    }
    [DllImport("user32.dll", EntryPoint = "GetForegroundWindow", ExactSpelling = true)]
    private static extern IntPtr SettingsGetForegroundWindow();
    [DllImport("user32.dll", EntryPoint = "WindowFromPoint", ExactSpelling = true)]
    private static extern IntPtr SettingsWindowFromPoint(CapturePoint point);
    [DllImport("user32.dll", EntryPoint = "GetWindowThreadProcessId", ExactSpelling = true)]
    private static extern uint SettingsGetWindowThreadProcessId(IntPtr window, out uint process);
    [DllImport("user32.dll", EntryPoint = "GetAncestor", ExactSpelling = true)]
    private static extern IntPtr SettingsGetAncestor(IntPtr window, uint flags);
    [DllImport("user32.dll", EntryPoint = "GetClassNameW", ExactSpelling = true, CharSet = CharSet.Unicode)]
    private static extern int SettingsGetClassName(IntPtr window, StringBuilder text, int count);

    private void EndSettingsNavigationCapture()
    {
        if (settingsHoverTarget != null)
        {
            if (settingsHoverEntered != null) settingsHoverTarget.PointerEntered -= settingsHoverEntered;
            if (settingsHoverExited != null) settingsHoverTarget.PointerExited -= settingsHoverExited;
        }
        settingsHoverTarget = settingsHoverSelected = null;
        settingsHoverEntered = settingsHoverExited = null;
        settingsHoverEvidence = settingsHoverBaseline = null; settingsHoverObserved = false;
    }
}
