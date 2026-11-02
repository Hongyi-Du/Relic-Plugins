using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Documents;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Relic.Core;
using System.Diagnostics;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private bool MeasuresChatOpening => performanceManifest?.Text("phase") is "open-every-chat" or "switch-chats";

    // Read-only traversal of actual mounted controls. It never realizes a chat
    // message, changes selection, or repairs a conversation scroll position.
    private static IEnumerable<FrameworkElement> PerformanceElements(DependencyObject owner)
    {
        if (owner is FrameworkElement element) yield return element;
        for (var index = 0; index < VisualTreeHelper.GetChildrenCount(owner); index++)
            foreach (var child in PerformanceElements(VisualTreeHelper.GetChild(owner, index))) yield return child;
    }

    private async Task<NativeSidebarRow> PrepareSidebarClick(string key, string automationId)
    {
        var index = side.Children.FindIndex(row => row.Key == key);
        if (index < 0) throw new InvalidOperationException("Production sidebar has no row: " + key);
        ScrollViewer? viewport = null;
        for (DependencyObject? parent = side; parent != null; parent = VisualTreeHelper.GetParent(parent))
            if (parent is ScrollViewer scroll) { viewport = scroll; break; }
        if (viewport == null) throw new InvalidOperationException("Production sidebar has no actual scrolling viewport");
        // Reach an offscreen target with real user input. Never call the
        // product's offscreen GetOrCreate/bring helpers from this preparation.
        // This remains separate from the one-second click-to-content deadline.
        var elapsed = Stopwatch.StartNew();
        var scrolling = false;
        EventHandler<ScrollViewerViewChangedEventArgs> changed = (_, args) => scrolling = args.IsIntermediate;
        viewport.ViewChanged += changed;
        try
        {
            while (elapsed.Elapsed < TimeSpan.FromSeconds(15))
            {
                var row = VisibleSidebarClickTarget(automationId);
                if (row != null)
                {
                    // A native scroll or activation refresh can move/recycle
                    // the row while input is queued. Retain it only after the
                    // real scroll ends and the actual pointer still hits it.
                    await CaptureHover(row);
                    if (!scrolling && ReferenceEquals(row, VisibleSidebarClickTarget(automationId))
                        && SidebarPointerHits(row).Flag("target_hit")) return row;
                    await Task.Delay(16);
                    continue;
                }
                if (scrolling) { await Task.Delay(16); continue; }
                index = side.Children.FindIndex(candidate => candidate.Key == key);
                if (index < 0) throw new InvalidOperationException("Production sidebar removed its click target: " + key);
                var direction = 0; var distance = 0;
                var actualTarget = PerformanceElements(side).OfType<NativeSidebarRow>()
                    .FirstOrDefault(candidate => AutomationProperties.GetAutomationId(candidate) == automationId);
                if (actualTarget is { IsLoaded: true, ActualHeight: > 0 })
                {
                    var bounds = actualTarget.TransformToVisual(viewport).TransformBounds(new(0, 0, actualTarget.ActualWidth, actualTarget.ActualHeight));
                    var center = bounds.Top + bounds.Height / 2;
                    if (center < 0) direction = 1;
                    else if (center >= viewport.ViewportHeight) direction = -1;
                }
                if (direction == 0)
                {
                    // Read only existing realized hosts, including placeholders.
                    // Their real geometry and model order determine the wheel
                    // direction; no estimated pixel offset selects a target.
                    var visibleIndices = new List<int>();
                    foreach (var host in PerformanceElements(side).OfType<Border>())
                    {
                        if (host is not { IsLoaded: true, ActualHeight: > 0, Tag: VirtualRows.Row model }) continue;
                        var bounds = host.TransformToVisual(viewport).TransformBounds(new(0, 0, host.ActualWidth, host.ActualHeight));
                        if (bounds.Bottom <= 0 || bounds.Top >= viewport.ViewportHeight) continue;
                        var visibleIndex = side.Children.FindIndex(candidate => ReferenceEquals(candidate, model)
                            || model.Key != null && candidate.Key == model.Key);
                        if (visibleIndex >= 0) visibleIndices.Add(visibleIndex);
                    }
                    if (visibleIndices.Count > 0)
                    {
                        var first = visibleIndices.Min(); var last = visibleIndices.Max();
                        if (index < first) { direction = 1; distance = first - index; }
                        else if (index > last) { direction = -1; distance = index - last; }
                    }
                }
                if (direction == 0) { await Task.Delay(16); continue; }
                await CaptureHover(viewport);
                var delta = direction * (distance > 8 ? 360 : 120);
                capturePointerReceipts.Add(new JsonObject { ["operation"] = "SendInput sidebar pointer wheel",
                    ["delta"] = delta, ["target_index"] = index, ["offset_before"] = viewport.VerticalOffset });
                SendCaptureMouse(new CaptureMouseInput { Data = unchecked((uint)delta), Flags = 0x0800 });
                await Task.Delay(80);
            }
            throw new TimeoutException("Production sidebar did not reveal its actual click target through real wheel input: " + automationId);
        }
        finally { viewport.ViewChanged -= changed; }
    }

    private NativeSidebarRow? VisibleSidebarClickTarget(string automationId)
    {
        var row = PerformanceElements(side).OfType<NativeSidebarRow>()
            .FirstOrDefault(item => AutomationProperties.GetAutomationId(item) == automationId);
        if (row is not { IsLoaded: true, ActualWidth: > 0, ActualHeight: > 0 }) return null;
        var rect = row.TransformToVisual(root).TransformBounds(new(0, 0, row.ActualWidth, row.ActualHeight));
        var viewport = treeRegion.TransformToVisual(root).TransformBounds(new(0, 0, treeRegion.ActualWidth, treeRegion.ActualHeight));
        var middle = rect.Top + rect.Height / 2;
        return middle >= viewport.Top && middle < viewport.Bottom && rect.Left >= 0 && rect.Right <= root.ActualWidth ? row : null;
    }

    private JsonObject SidebarPointerHits(NativeSidebarRow row)
    {
        var cursor = new CapturePoint(); var origin = new CapturePoint();
        if (!GetCursorPos(ref cursor) || !ClientToScreen(WinRT.Interop.WindowNative.GetWindowHandle(this), ref origin))
            throw new InvalidOperationException("Cannot observe the actual sidebar click pointer");
        var scale = root.XamlRoot.RasterizationScale;
        var point = new Windows.Foundation.Point((cursor.x - origin.x) / scale, (cursor.y - origin.y) / scale);
        var hits = VisualTreeHelper.FindElementsInHostCoordinates(point, root, false).Take(12).ToArray();
        var targetHit = false;
        for (DependencyObject? node = hits.FirstOrDefault(); node != null; node = VisualTreeHelper.GetParent(node))
            if (ReferenceEquals(node, row)) { targetHit = true; break; }
        return new JsonObject { ["target_hit"] = targetHit, ["pointer_x"] = point.X, ["pointer_y"] = point.Y,
            ["foreground_hwnd"] = WholeWindowForeground().ToInt64(), ["target_loaded"] = row.IsLoaded,
            ["hits"] = new JsonArray(hits.Select(hit => (JsonNode)new JsonObject {
                ["type"] = hit.GetType().Name, ["automation_id"] = AutomationProperties.GetAutomationId(hit),
                ["same_target"] = ReferenceEquals(hit, row) }).ToArray()) };
    }

    private static ListView PerformanceListFor(NativeSidebarRow row)
    {
        for (DependencyObject? node = row; node != null; node = VisualTreeHelper.GetParent(node))
            if (node is ListView list) return list;
        throw new InvalidOperationException("Actual sidebar row has no owning ListView");
    }

    private readonly record struct ExpectedChat(string ItemId, string ItemKind, string MessageId, bool Empty);

    private async Task<ExpectedChat> ExpectedLatestMessage(string organization, string who)
    {
        // Independent expectation from the server, before clicking. This does
        // not select a view or populate the client's conversation model.
        var page = await api!.Get(Client.Org(organization, "/chat?kind=" + (who.Length == 0 ? "group" : "private")
            + "&member=" + Client.Segment(who) + "&limit=1"));
        var rows = page.Rows("items");
        return new(rows.LastOrDefault().Text("id"), rows.LastOrDefault().Text("type"),
            rows.LastOrDefault(item => long.TryParse(item.Text("id"), out _)).Text("id"), rows.Count == 0);
    }

    private JsonObject ObserveOpenedChat(string organization, string who, ExpectedChat expected)
    {
        var expectedId = expected.ItemId; var expectedEmpty = expected.Empty;
        var selected = org == organization && member == who && renderedView == organization + "/" + who;
        var actualLast = messages.LastOrDefault().Text("id");
        var messageLoaded = expected.MessageId.Length == 0 || messages.Any(item => item.Text("id") == expected.MessageId);
        var result = new JsonObject { ["selected_org"] = org, ["selected_member"] = member,
            ["rendered_view"] = renderedView, ["expected_message_id"] = expected.MessageId,
            ["expected_item_id"] = expectedId, ["expected_item_kind"] = expected.ItemKind,
            ["actual_latest_item_id"] = actualLast, ["actual_latest_item_kind"] = messages.LastOrDefault().Text("type"),
            ["latest_message_loaded"] = messageLoaded, ["expected_empty"] = expectedEmpty,
            ["selected"] = selected, ["content_ready"] = ConversationContentReady(), ["latest_visible"] = false };
        if (!selected || !ConversationContentReady()) return result;
        var rowKey = (expected.ItemKind == "message" ? "message:" : "item:") + expectedId;
        var index = expectedEmpty ? stream.Children.Count - 1 : stream.Children.FindIndex(row => row.Key == rowKey);
        var host = index >= 0 ? stream.TryGetRealizedRow(index) : null;
        if (host is not { IsLoaded: true, Child: not null, ActualHeight: > 0 }) return result;
        var bounds = host.TransformToVisual(chatScroll).TransformBounds(new(0, 0, host.ActualWidth, host.ActualHeight));
        var visible = bounds.Bottom > 0 && bounds.Top < chatScroll.ViewportHeight;
        result["row_key"] = (host.Tag as VirtualRows.Row)?.Key;
        result["row_top"] = bounds.Top; result["row_bottom"] = bounds.Bottom;
        result["bottom_gap_dip"] = chatScroll.ScrollableHeight - chatScroll.VerticalOffset;
        result["row_visible"] = visible;
        if (!visible || Math.Abs(chatScroll.ScrollableHeight - chatScroll.VerticalOffset) > 1) return result;

        var mounted = PerformanceElements(host.Child).Where(element => element.IsLoaded && element.Visibility == Visibility.Visible
            && element.Opacity > 0 && element.ActualWidth > 0 && element.ActualHeight > 0).ToArray();
        var visibleLabels = mounted.OfType<NativeLabel>().Where(label =>
        {
            var rect = label.TransformToVisual(chatScroll).TransformBounds(new(0, 0, label.ActualWidth, label.ActualHeight));
            return rect.Bottom > 0 && rect.Top < chatScroll.ViewportHeight;
        }).ToArray();
        result["native_labels_current"] = visibleLabels.All(label => label.HasCurrentDraw);
        if (!visibleLabels.All(label => label.HasCurrentDraw)) return result;
        if (expectedEmpty)
        {
            var empty = mounted.OfType<TextBlock>().Any(text => text.Text == T(who.Length == 0 ? "chat.empty_group" : "chat.empty_private"));
            result["empty_label_visible"] = empty;
            result["latest_visible"] = messages.Count == 0 && empty;
        }
        else
        {
            var itemPrefix = expected.ItemKind == "message" ? "message" : "chat-item";
            var message = mounted.FirstOrDefault(element => AutomationProperties.GetAutomationId(element) == itemPrefix + "/" + expectedId);
            var body = mounted.FirstOrDefault(element => AutomationProperties.GetAutomationId(element) == itemPrefix + "-body/" + expectedId);
            var visibleBodyText = body == null ? [] : PerformanceElements(body).Where(element =>
            {
                if (!element.IsLoaded || element.Visibility != Visibility.Visible || element.Opacity <= 0
                    || element.ActualWidth <= 0 || element.ActualHeight <= 0) return false;
                var rect = element.TransformToVisual(chatScroll).TransformBounds(new(0, 0, element.ActualWidth, element.ActualHeight));
                return rect.Bottom > 0 && rect.Top < chatScroll.ViewportHeight && rect.Right > 0 && rect.Left < chatScroll.ViewportWidth;
            }).ToArray();
            // Restrict evidence to the real message or notice body. Names, dates, avatars,
            // hover actions and delivery receipts cannot stand in for a body.
            // A NativePathText line is witnessed by its actual drawn NativeLabel.
            var paintedBody = visibleBodyText.Any(element => element switch
            {
                NativeLabel label => !string.IsNullOrWhiteSpace(label.Text) && label.HasCurrentDraw,
                RichTextBlock rich => rich.Blocks.OfType<Paragraph>().Any(paragraph => PerformanceInlineText(paragraph.Inlines)),
                TextBlock text => !string.IsNullOrWhiteSpace(text.Text) || PerformanceInlineText(text.Inlines),
                _ => false
            });
            result["message_control_present"] = message != null;
            result["body_control_present"] = body != null;
            result["body_text_present"] = paintedBody;
            result["latest_visible"] = actualLast == expectedId && messages.LastOrDefault().Text("type") == expected.ItemKind
                && messageLoaded && message != null && paintedBody;
        }
        return result;
    }

    private static bool PerformanceInlineText(InlineCollection inlines) => inlines.Any(inline => inline switch
    {
        Run run => !string.IsNullOrWhiteSpace(run.Text),
        Span span => PerformanceInlineText(span.Inlines),
        _ => false
    });

    private async Task<JsonObject> ClickChatRow(string organization, string who, bool organizationRow, JsonNode? expectedAction = null)
    {
        var preparing = Stopwatch.StartNew();
        var fromFixture = expectedAction?["latest_message_id"] != null || expectedAction?["expected_empty"] != null;
        var expected = fromFixture ? new ExpectedChat(expectedAction.Text("latest_item_id"), expectedAction.Text("latest_item_kind"),
            expectedAction.Text("latest_message_id"), expectedAction.Flag("expected_empty"))
            : await ExpectedLatestMessage(organization, who);
        var key = organizationRow ? "org:" + organization : "chat:" + organization + "/" + who;
        var id = organizationRow ? "sidebar-org/" + organization : "sidebar-chat/" + organization + "/" + who;
        // Activation must finish before the target is retained. A real first
        // click may activate the window, and previously activation rebuilt
        // the sidebar between mouse-down and mouse-up.
        var windowHandle = WinRT.Interop.WindowNative.GetWindowHandle(this);
        if (WholeWindowForeground() != windowHandle)
        {
            SetForegroundWindow(windowHandle);
            var activation = Stopwatch.StartNew();
            while (WholeWindowForeground() != windowHandle)
            {
                if (activation.Elapsed > TimeSpan.FromSeconds(5))
                    throw new TimeoutException("Windows did not foreground the actual sidebar click window");
                await Task.Delay(16);
            }
            await PerformanceYield();
        }
        capturePointerReceipts.Clear();
        var row = await PrepareSidebarClick(key, id);
        var list = PerformanceListFor(row); var clicks = 0;
        long handlerAt = 0;
        var itemClicks = new JsonArray();
        var routed = new JsonArray();
        void RecordPointer(string kind, PointerRoutedEventArgs args) => routed.Add(new JsonObject {
            ["kind"] = kind, ["handled"] = args.Handled, ["target_loaded"] = row.IsLoaded,
            ["original_source_type"] = args.OriginalSource?.GetType().Name,
            ["original_source_id"] = args.OriginalSource is DependencyObject source ? AutomationProperties.GetAutomationId(source) : "" });
        PointerEventHandler pressed = (_, args) => RecordPointer("pressed", args);
        PointerEventHandler released = (_, args) => RecordPointer("released", args);
        var unloaded = 0; RoutedEventHandler rowUnloaded = (_, _) => unloaded++;
        ItemClickEventHandler clicked = (_, args) =>
        {
            // For an explicit ListViewItem, WinUI returns its Content in
            // ClickedItem. Observe that actual event/object; never synthesize
            // a click or treat pointer-down alone as successful navigation.
            var sameContent = ReferenceEquals(args.ClickedItem, row.Content);
            itemClicks.Add(new JsonObject { ["type"] = args.ClickedItem?.GetType().FullName,
                ["same_row_content"] = sameContent, ["same_row"] = ReferenceEquals(args.ClickedItem, row),
                ["content_automation_id"] = args.ClickedItem is DependencyObject content ? AutomationProperties.GetAutomationId(content) : "" });
            if (sameContent) { clicks++; handlerAt = Stopwatch.GetTimestamp(); }
        };
        long frames = 0;
        EventHandler<object> rendered = (_, _) => frames++;
        list.ItemClick += clicked; CompositionTarget.Rendering += rendered;
        row.AddHandler(UIElement.PointerPressedEvent, pressed, true);
        row.AddHandler(UIElement.PointerReleasedEvent, released, true); row.Unloaded += rowUnloaded;
        var receipt = new JsonObject { ["target"] = id, ["expectation_source"] = fromFixture
            ? "Independent server-view fixture tail and latest numeric message identities" : "Independent real chat API limit=1 before pointer input" };
        try
        {
            receipt["input_target"] = SidebarPointerHits(row);
            receipt["preparation_ms"] = preparing.Elapsed.TotalMilliseconds;
            var started = Stopwatch.GetTimestamp();
            receipt["input_unix_ms"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            CapturePointerButton(true);
            try { await Task.Delay(40); } finally { CapturePointerButton(false); }
            long readyFrame = -1;
            JsonObject observation = new();
            // Opening has a hard one-second acceptance deadline. Retain the
            // failed observation then test the next real click, rather than
            // spending fifteen seconds on an already-failed opening and
            // delaying every remaining core-flow result.
            while (Stopwatch.GetElapsedTime(started) < TimeSpan.FromSeconds(1))
            {
                observation = ObserveOpenedChat(organization, who, expected);
                if (clicks > 0 && observation.Flag("latest_visible"))
                {
                    if (readyFrame >= 0 && frames > readyFrame) break;
                    if (readyFrame < 0) readyFrame = frames;
                }
                else readyFrame = -1;
                await Task.Delay(8);
            }
            var openMs = Stopwatch.GetElapsedTime(started).TotalMilliseconds;
            receipt["open_ms"] = openMs;
            receipt["click_events"] = clicks;
            receipt["input_to_handler_ms"] = handlerAt == 0 ? null : Stopwatch.GetElapsedTime(started, handlerAt).TotalMilliseconds;
            receipt["latest_visible"] = readyFrame >= 0 && frames > readyFrame && observation.Flag("latest_visible");
            receipt["observation"] = observation;
            receipt["pointer_events"] = capturePointerReceipts.DeepClone();
            receipt["routed_pointer_events"] = routed; receipt["target_unloads"] = unloaded;
            receipt["native_item_clicks"] = itemClicks;
            receipt["passed"] = clicks > 0 && receipt.Flag("latest_visible") && openMs <= 1000;
            return receipt;
        }
        finally
        {
            list.ItemClick -= clicked; CompositionTarget.Rendering -= rendered;
            row.RemoveHandler(UIElement.PointerPressedEvent, pressed);
            row.RemoveHandler(UIElement.PointerReleasedEvent, released); row.Unloaded -= rowUnloaded;
        }
    }

    private async Task ExerciseOpenChat(JsonNode step, JsonObject record)
    {
        var organization = step.Text("org"); var who = step.Text("kind") == "private" ? step.Text("member") : "";
        var navigations = new JsonArray(); record["navigation_clicks"] = navigations;
        if (step.Text("kind") == "organization")
        {
            var organizationClick = await ClickChatRow(organization, "", true, step); navigations.Add(organizationClick);
            foreach (var field in new[] { "open_ms", "click_events", "latest_visible", "preparation_ms", "input_unix_ms" }) record[field] = organizationClick[field]?.DeepClone();
            if (!organizationClick.Flag("passed"))
                throw new InvalidOperationException("Organization row did not open its actual latest group messages within 1000 ms: " + organization);
            return;
        }
        if (org != organization)
        {
            var opening = await ClickChatRow(organization, "", true, who.Length == 0 ? step : null); navigations.Add(opening);
            if (!opening.Flag("passed"))
            {
                record["open_ms"] = opening["open_ms"]?.DeepClone(); record["click_events"] = opening["click_events"]?.DeepClone();
                record["latest_visible"] = opening["latest_visible"]?.DeepClone();
                throw new InvalidOperationException("Organization click did not open its latest group messages within 1000 ms: " + organization);
            }
        }
        // The organization row and group-chat row are distinct controls. Even
        // after selecting another organization, click its actual group row;
        // an organization-only success cannot satisfy group-row coverage.
        var opened = await ClickChatRow(organization, who, false, step); navigations.Add(opened);
        foreach (var field in new[] { "open_ms", "click_events", "latest_visible", "preparation_ms", "input_unix_ms" }) record[field] = opened[field]?.DeepClone();
        if (!opened.Flag("passed")) throw new InvalidOperationException("Chat click did not show its actual latest messages within 1000 ms: " + organization + "/" + who);
    }

    private async Task ExerciseIdle(JsonNode step, JsonObject record)
    {
        await WaitForMarkdown();
        var settling = Stopwatch.StartNew();
        while (!stream.IsLastPositionSettled)
        {
            if (settling.Elapsed > TimeSpan.FromSeconds(15)) throw new TimeoutException("Conversation did not settle before idle CPU measurement");
            await Task.Delay(16);
        }
        Volatile.Write(ref performanceAction, "idle-measure");
        record["idle_started_unix_ms"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        var idle = Stopwatch.StartNew();
        var seconds = Math.Max(12, int.TryParse(step.Text("seconds"), out var requested) ? requested : 12);
        await Task.Delay(TimeSpan.FromSeconds(seconds));
        record["idle_seconds"] = idle.Elapsed.TotalSeconds;
        record["idle_finished_unix_ms"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
    }
}
