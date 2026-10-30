using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using System.Text.Json.Nodes;

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
            ["checkpoints"] = new JsonArray(), ["errors"] = new JsonArray() };
        settingsHoverEntered = (_, _) => settingsHoverObserved = true;
        settingsHoverExited = (_, _) => settingsHoverObserved = false;
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
        var hit = VisualTreeHelper.FindElementsInHostCoordinates(point, root, false).Any(value => ReferenceEquals(value, target));
        var bounds = target.TransformToVisual(root).TransformBounds(new Windows.Foundation.Rect(0, 0, target.ActualWidth, target.ActualHeight));
        var state = new JsonObject
        {
            ["automation_id"] = AutomationProperties.GetAutomationId(target), ["selected"] = target.IsSelected,
            ["appearance_selected"] = settingsHoverSelected!.IsSelected, ["is_loaded"] = target.IsLoaded,
            ["hover_observed"] = settingsHoverObserved, ["pointer_hit_test_contains_target"] = hit,
            ["pointer_x"] = point.X, ["pointer_y"] = point.Y,
            ["bounds"] = new JsonObject { ["x"] = bounds.X, ["y"] = bounds.Y, ["width"] = bounds.Width, ["height"] = bounds.Height },
            ["background"] = (target.Background as SolidColorBrush)?.Color.ToString()
        };
        ((JsonArray)settingsHoverEvidence["checkpoints"]!).Add(new JsonObject { ["stage"] = stage, ["state"] = state });
        if (!settingsHoverObserved || !hit || !target.IsLoaded || target.IsSelected || !settingsHoverSelected.IsSelected)
            throw new InvalidOperationException("The actual unselected settings navigation hover was not retained: " + stage);
        if (settingsHoverBaseline == null) settingsHoverBaseline = state.DeepClone().AsObject();
        else if (!JsonNode.DeepEquals(settingsHoverBaseline, state))
            throw new InvalidOperationException("Actual settings navigation hover changed during " + stage);
    }

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
