using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Documents;
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
        // This is the same real virtual row navigation used by keyboard input.
        // Preparing the click target is reported separately from opening time.
        side.BringIndexIntoView(index);
        var elapsed = Stopwatch.StartNew();
        while (elapsed.Elapsed < TimeSpan.FromSeconds(15))
        {
            var row = PerformanceElements(side).OfType<NativeSidebarRow>()
                .FirstOrDefault(item => AutomationProperties.GetAutomationId(item) == automationId);
            if (row is { IsLoaded: true, ActualWidth: > 0, ActualHeight: > 0 })
            {
                var rect = row.TransformToVisual(root).TransformBounds(new(0, 0, row.ActualWidth, row.ActualHeight));
                var viewport = treeRegion.TransformToVisual(root).TransformBounds(new(0, 0, treeRegion.ActualWidth, treeRegion.ActualHeight));
                var middle = rect.Top + rect.Height / 2;
                if (middle >= viewport.Top && middle < viewport.Bottom && rect.Left >= 0 && rect.Right <= root.ActualWidth)
                    return row;
            }
            await Task.Delay(16);
        }
        throw new TimeoutException("Production sidebar did not reveal its actual click target: " + automationId);
    }

    private static ListView PerformanceListFor(NativeSidebarRow row)
    {
        for (DependencyObject? node = row; node != null; node = VisualTreeHelper.GetParent(node))
            if (node is ListView list) return list;
        throw new InvalidOperationException("Actual sidebar row has no owning ListView");
    }

    private async Task<(string Id, bool Empty)> ExpectedLatestMessage(string organization, string who)
    {
        // Independent expectation from the server, before clicking. This does
        // not select a view or populate the client's conversation model.
        var page = await api!.Get(Client.Org(organization, "/chat?kind=" + (who.Length == 0 ? "group" : "private")
            + "&member=" + Client.Segment(who) + "&limit=1"));
        var rows = page.Rows("items");
        return (rows.LastOrDefault().Text("id"), rows.Count == 0);
    }

    private JsonObject ObserveOpenedChat(string organization, string who, string expectedId, bool expectedEmpty)
    {
        var selected = org == organization && member == who && renderedView == organization + "/" + who;
        var actualLast = messages.LastOrDefault().Text("id");
        var result = new JsonObject { ["selected_org"] = org, ["selected_member"] = member,
            ["rendered_view"] = renderedView, ["expected_message_id"] = expectedId,
            ["actual_latest_message_id"] = actualLast, ["expected_empty"] = expectedEmpty,
            ["selected"] = selected, ["content_ready"] = ConversationContentReady(), ["latest_visible"] = false };
        if (!selected || !ConversationContentReady()) return result;
        var repeater = VisualTreeHelper.GetChild(stream, 0) as ItemsRepeater;
        var index = expectedEmpty ? stream.Children.Count - 1 : stream.Children.FindIndex(row => row.Key == "message:" + expectedId);
        var host = index >= 0 ? repeater?.TryGetElement(index) as Border : null;
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
            var message = mounted.FirstOrDefault(element => AutomationProperties.GetAutomationId(element) == "message/" + expectedId);
            var body = mounted.FirstOrDefault(element => AutomationProperties.GetAutomationId(element) == "message-body/" + expectedId);
            var visibleBodyText = body == null ? [] : PerformanceElements(body).Where(element =>
            {
                if (!element.IsLoaded || element.Visibility != Visibility.Visible || element.Opacity <= 0
                    || element.ActualWidth <= 0 || element.ActualHeight <= 0) return false;
                var rect = element.TransformToVisual(chatScroll).TransformBounds(new(0, 0, element.ActualWidth, element.ActualHeight));
                return rect.Bottom > 0 && rect.Top < chatScroll.ViewportHeight && rect.Right > 0 && rect.Left < chatScroll.ViewportWidth;
            }).ToArray();
            // Restrict evidence to the real bubble body. Names, dates, avatars,
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
            result["latest_visible"] = actualLast == expectedId && message != null && paintedBody;
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
        var expected = fromFixture ? (Id: expectedAction.Text("latest_message_id"), Empty: expectedAction.Flag("expected_empty"))
            : await ExpectedLatestMessage(organization, who);
        var key = organizationRow ? "org:" + organization : "chat:" + organization + "/" + who;
        var id = organizationRow ? "sidebar-org/" + organization : "sidebar-chat/" + organization + "/" + who;
        var row = await PrepareSidebarClick(key, id);
        var list = PerformanceListFor(row); var clicks = 0;
        long handlerAt = 0;
        ItemClickEventHandler clicked = (_, args) =>
        {
            if (ReferenceEquals(args.ClickedItem, row)) { clicks++; handlerAt = Stopwatch.GetTimestamp(); }
        };
        long frames = 0;
        EventHandler<object> rendered = (_, _) => frames++;
        list.ItemClick += clicked; CompositionTarget.Rendering += rendered;
        var receipt = new JsonObject { ["target"] = id, ["expectation_source"] = fromFixture
            ? "Independent synthetic fixture latest message identity" : "Independent real chat API limit=1 before pointer input" };
        try
        {
            SetForegroundWindow(WinRT.Interop.WindowNative.GetWindowHandle(this));
            capturePointerReceipts.Clear(); await CaptureHover(row);
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
                observation = ObserveOpenedChat(organization, who, expected.Id, expected.Empty);
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
            receipt["passed"] = clicks > 0 && receipt.Flag("latest_visible") && openMs <= 1000;
            return receipt;
        }
        finally { list.ItemClick -= clicked; CompositionTarget.Rendering -= rendered; }
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
