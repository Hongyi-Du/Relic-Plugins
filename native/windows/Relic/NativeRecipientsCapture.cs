using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private async Task CaptureRecipientsScene(string output, string caseId)
    {
        if (!VisualCaptureEnabled) throw new InvalidOperationException("CI capture input only");
        var button = recipientButton ?? throw new InvalidOperationException("The production recipient button is missing");
        var identities = new Dictionary<object, string>(ReferenceEqualityComparer.Instance);
        string? Identity(object? value)
        {
            if (value == null) return null;
            if (!identities.TryGetValue(value, out var id)) identities[value] = id = "retained-object-" + identities.Count;
            return id;
        }
        JsonObject Bounds(FrameworkElement element)
        {
            var box = element.TransformToVisual(root).TransformBounds(new Windows.Foundation.Rect(0, 0, element.ActualWidth, element.ActualHeight));
            return new JsonObject { ["x"] = box.X, ["y"] = box.Y, ["width"] = box.Width, ["height"] = box.Height };
        }
        bool Contains(DependencyObject parent, DependencyObject item)
        {
            if (ReferenceEquals(parent, item)) return true;
            for (var index = 0; index < VisualTreeHelper.GetChildrenCount(parent); index++)
                if (Contains(VisualTreeHelper.GetChild(parent, index), item)) return true;
            return false;
        }
        var clicks = new JsonArray(); var pointerEvents = new JsonArray(); var completedClick = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var receipt = new JsonObject { ["case_id"] = caseId, ["action"] = "actual native pointer click on production recipientButton",
            ["identity_quantity"] = "Retained process-local object ReferenceEquals identities; not UIA RuntimeIds or final-frame claims",
            ["button_object"] = Identity(button), ["click_events"] = clicks, ["pointer_events"] = pointerEvents, ["errors"] = new JsonArray() };
        var beforeFlyout = transientFlyout;
        var beforeItems = (beforeFlyout as MenuFlyout)?.Items.ToArray() ?? [];
        var beforePopups = VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot).ToArray();
        JsonObject Snapshot()
        {
            JsonObject? pointer = null;
            var cursor = new CapturePoint(); var origin = new CapturePoint();
            if (GetCursorPos(ref cursor) && ClientToScreen(WinRT.Interop.WindowNative.GetWindowHandle(this), ref origin))
            {
                var scale = root.XamlRoot.RasterizationScale;
                var location = new Windows.Foundation.Point((cursor.x - origin.x) / scale, (cursor.y - origin.y) / scale);
                var hits = VisualTreeHelper.FindElementsInHostCoordinates(location, root, true).ToArray();
                pointer = new JsonObject { ["screen_x"] = cursor.x, ["screen_y"] = cursor.y,
                    ["window_x"] = location.X, ["window_y"] = location.Y,
                    ["hit_test_contains_retained_button"] = hits.Any(hit => ReferenceEquals(hit, button)),
                    ["hits"] = new JsonArray(hits.Select(hit => (JsonNode?)new JsonObject {
                        ["object"] = Identity(hit), ["type"] = hit.GetType().FullName,
                        ["name"] = AutomationProperties.GetName(hit) }).ToArray()) };
            }
            var current = transientFlyout;
            var popups = VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot).ToArray();
            var popupRows = new JsonArray();
            foreach (var popup in popups)
                popupRows.Add(new JsonObject { ["object"] = Identity(popup), ["is_open"] = popup.IsOpen,
                    ["same_object_in_before"] = beforePopups.Any(value => ReferenceEquals(value, popup)),
                    ["child_object"] = Identity(popup.Child), ["child_runtime_type"] = popup.Child?.GetType().FullName,
                    ["child_bounds"] = popup.Child is FrameworkElement child ? Bounds(child) : null });
            var menuRows = new JsonArray();
            if (current is MenuFlyout menu)
                for (var index = 0; index < menu.Items.Count; index++)
                {
                    var item = menu.Items[index];
                    menuRows.Add(new JsonObject { ["index"] = index, ["object"] = Identity(item),
                        ["runtime_type"] = item.GetType().FullName, ["text"] = item is MenuFlyoutItem action ? action.Text : null,
                        ["same_object_in_before"] = beforeItems.Any(value => ReferenceEquals(value, item)),
                        ["is_loaded"] = item.IsLoaded, ["visibility"] = item.Visibility.ToString(),
                        ["is_enabled"] = item.IsEnabled,
                        ["open_popup_owners"] = new JsonArray(popups.Where(popup => popup.IsOpen && popup.Child != null
                            && Contains(popup.Child, item)).Select(popup => (JsonNode?)JsonValue.Create(Identity(popup))).ToArray()) });
                }
            return new JsonObject { ["observed_at_utc"] = DateTimeOffset.UtcNow.ToString("O"),
                ["button_is_current_reference"] = ReferenceEquals(button, recipientButton),
                ["button_name"] = AutomationProperties.GetName(button), ["button_bounds"] = Bounds(button),
                ["button_is_loaded"] = button.IsLoaded, ["button_is_enabled"] = button.IsEnabled,
                ["button_visibility"] = button.Visibility.ToString(), ["button_opacity"] = button.Opacity, ["pointer"] = pointer,
                ["transient_flyout_object"] = Identity(current), ["transient_flyout_runtime_type"] = current?.GetType().FullName,
                ["transient_flyout_same_as_before"] = ReferenceEquals(current, beforeFlyout),
                ["menu_items"] = menuRows, ["open_popups"] = popupRows };
        }
        RoutedEventHandler observedClick = (sender, args) =>
        {
            var same = ReferenceEquals(sender, button);
            clicks.Add(new JsonObject { ["observed_at_utc"] = DateTimeOffset.UtcNow.ToString("O"),
                ["sender_object"] = Identity(sender), ["sender_is_retained_button"] = same,
                ["button_is_current_reference"] = ReferenceEquals(button, recipientButton),
                ["original_source_object"] = Identity(args.OriginalSource),
                ["original_source_runtime_type"] = args.OriginalSource?.GetType().FullName });
            if (same) completedClick.TrySetResult();
        };
        var pointerObservers = new List<(RoutedEvent Event, PointerEventHandler Handler)>();
        foreach (var (kind, routedEvent) in new[] { ("pressed", UIElement.PointerPressedEvent), ("released", UIElement.PointerReleasedEvent) })
        {
            PointerEventHandler observer = (sender, args) =>
            {
                var point = args.GetCurrentPoint(root);
                pointerEvents.Add(new JsonObject { ["kind"] = kind, ["observed_at_utc"] = DateTimeOffset.UtcNow.ToString("O"),
                    ["sender_is_retained_button"] = ReferenceEquals(sender, button), ["handled"] = args.Handled,
                    ["original_source_object"] = Identity(args.OriginalSource), ["original_source_type"] = args.OriginalSource?.GetType().FullName,
                    ["x"] = point.Position.X, ["y"] = point.Position.Y, ["left_pressed"] = point.Properties.IsLeftButtonPressed });
            };
            button.AddHandler(routedEvent, observer, true); pointerObservers.Add((routedEvent, observer));
        }
        button.Click += observedClick;
        try
        {
            root.UpdateLayout(); receipt["before"] = Snapshot();
            if (!button.IsLoaded || !button.IsEnabled || button.Visibility != Visibility.Visible
                || button.Opacity <= 0 || button.ActualWidth <= 0 || button.ActualHeight <= 0)
                throw new InvalidOperationException("The actual recipient button is not available for pointer input");
            await CaptureClick(button);
            await completedClick.Task.WaitAsync(TimeSpan.FromSeconds(3));
            // Await the real menu's visual attachment. No menu instance, model
            // selection, or production callback is manufactured by capture.
            var attached = false;
            for (var attempt = 0; attempt < 50; attempt++)
            {
                root.UpdateLayout();
                if (transientFlyout is MenuFlyout menu && !ReferenceEquals(menu, beforeFlyout) && menu.Items.Count > 0)
                    attached = VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot).Any(popup => popup.IsOpen
                        && !beforePopups.Any(previous => ReferenceEquals(previous, popup)) && popup.Child != null
                        && menu.Items.Any(item => Contains(popup.Child, item)));
                if (attached) break;
                await Task.Delay(50);
            }
            receipt["after"] = Snapshot();
            if (!attached || !ReferenceEquals(button, recipientButton))
                throw new InvalidOperationException("The real recipient click did not attach its current MenuFlyout items to a new open popup");
            receipt["status"] = "observed";
        }
        catch (Exception error)
        {
            receipt["status"] = "failed"; ((JsonArray)receipt["errors"]!).Add(error.ToString());
            if (receipt["after"] == null)
                try { receipt["after"] = Snapshot(); }
                catch (Exception snapshotError) { ((JsonArray)receipt["errors"]!).Add(snapshotError.ToString()); }
            throw;
        }
        finally
        {
            button.Click -= observedClick;
            foreach (var (routedEvent, observer) in pointerObservers) button.RemoveHandler(routedEvent, observer);
            await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(output, caseId + ".scene-action.json"), receipt.ToJsonString());
        }
    }
}
