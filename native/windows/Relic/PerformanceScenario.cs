using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Relic.Core;
using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private bool PerformanceEnabled => Environment.GetEnvironmentVariable("GITHUB_ACTIONS") == "true"
        && !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("RELIC_PERF_MANIFEST"));
    private JsonNode? performanceManifest;
    private CancellationTokenSource? performanceCancellation;
    private Task? performanceProbe;
    private long performanceWorstTicks;
    private int performanceCommands;
    private string performanceAction = "initial organization load";
    private string PerformanceOutput => performanceManifest!.Text("output");

    private void StartPerformanceProbe()
    {
        if (!PerformanceEnabled) return;
        performanceManifest = JsonNode.Parse(System.IO.File.ReadAllText(Environment.GetEnvironmentVariable("RELIC_PERF_MANIFEST")!))!;
        System.IO.Directory.CreateDirectory(PerformanceOutput);
        performanceCancellation = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
        var token = performanceCancellation.Token;
        performanceProbe = Task.Run(async () =>
        {
            async Task Write(string name, object value)
            {
                var path = System.IO.Path.Combine(PerformanceOutput, name);
                System.IO.File.WriteAllText(path + ".tmp", JsonSerializer.Serialize(value));
                for (var attempt = 0; ; attempt++)
                {
                    try { System.IO.File.Move(path + ".tmp", path, true); break; }
                    catch (Exception error) when (attempt < 10 && error is System.IO.IOException or UnauthorizedAccessException)
                    {
                        // The external reader may momentarily hold the old
                        // Windows file without FILE_SHARE_DELETE. Retry this
                        // atomic replacement, never discard the measured max.
                        await Task.Delay(2, token);
                    }
                }
            }
            await Write("performance-ready.json", new { pid = Environment.ProcessId, unix_ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() });
            long sequence = 0, pings = 0;
            while (!token.IsCancellationRequested)
            {
                var sent = Stopwatch.GetTimestamp();
                var pendingSince = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
                var completed = new TaskCompletionSource<long>(TaskCreationOptions.RunContinuationsAsynchronously);
                if (!DispatcherQueue.TryEnqueue(DispatcherQueuePriority.Normal, () => completed.TrySetResult(Stopwatch.GetTimestamp()))) break;
                while (!token.IsCancellationRequested)
                {
                    await Task.WhenAny(completed.Task, Task.Delay(40, token));
                    var ticks = (completed.Task.IsCompletedSuccessfully ? completed.Task.Result : Stopwatch.GetTimestamp()) - sent;
                    var old = Interlocked.Read(ref performanceWorstTicks);
                    if (ticks > old) Interlocked.Exchange(ref performanceWorstTicks, ticks);
                    if (completed.Task.IsCompletedSuccessfully && ticks * 1000d / Stopwatch.Frequency > 5)
                        PerformanceTrace.Count("ui.dispatch", ticks * 1000d / Stopwatch.Frequency);
                    if (completed.Task.IsCompletedSuccessfully) pings++;
                    PerformanceTrace.RecordCollection();
                    await Write("heartbeat.json", new { unix_ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), sequence = ++sequence, pings,
                        max_ui_stall_ms = Interlocked.Read(ref performanceWorstTicks) * 1000d / Stopwatch.Frequency,
                        pending_since_unix_ms = completed.Task.IsCompletedSuccessfully ? 0 : pendingSince,
                        titlebar_layout_notifications = Interlocked.Read(ref titlebarLayoutNotifications),
                        titlebar_layout_measurements = Interlocked.Read(ref titlebarLayoutMeasurements),
                        action = Volatile.Read(ref performanceAction) });
                    foreach (var timing in PerformanceTrace.Drain())
                        System.IO.File.AppendAllText(System.IO.Path.Combine(PerformanceOutput, "timings.jsonl"), JsonSerializer.Serialize(timing) + "\n");
                    if (completed.Task.IsCompletedSuccessfully) break;
                }
                await Task.Delay(40, token);
            }
        }, token);
        _ = performanceProbe.ContinueWith(task => System.IO.File.WriteAllText(
            System.IO.Path.Combine(PerformanceOutput, "probe-error.txt"), task.Exception!.ToString()),
            CancellationToken.None, TaskContinuationOptions.OnlyOnFaulted, TaskScheduler.Default);
    }

    private async Task PerformanceYield()
    {
        var tick = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        DispatcherQueue.TryEnqueue(DispatcherQueuePriority.Low, () => tick.SetResult());
        await tick.Task;
        await Task.Delay(60);
    }

    private async Task<JsonObject> WaitForSettingsNavigationDraw(ContentDialog dialog)
    {
        var elapsed = Stopwatch.StartNew();
        JsonArray states = [];
        while (elapsed.Elapsed < TimeSpan.FromSeconds(15))
        {
            var navigation = new List<NativeSettingsNavigationLabel>();
            void Walk(DependencyObject node)
            {
                if (node is NativeSettingsNavigationLabel label) { navigation.Add(label); return; }
                for (var index = 0; index < Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(node); index++)
                    Walk(Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChild(node, index));
            }
            Walk(dialog);
            states = new JsonArray(navigation.Select(item => (JsonNode)(item.CurrentLabel?.DrawState()
                ?? new JsonObject { ["current_draw"] = false, ["failure"] = "Visible navigation owner has no label" })).ToArray());
            if (navigation.Count == 7 && navigation.All(item => item.IsLoaded && item.Visibility == Visibility.Visible
                && item.CurrentLabel is { HasCurrentDraw: true, ActualWidth: > 0, ActualHeight: > 0 }))
                return new JsonObject { ["source"] = "Seven actual mounted settings navigation labels after their production SurfaceImageSource EndDraw",
                    ["count"] = navigation.Count, ["elapsed_ms"] = elapsed.Elapsed.TotalMilliseconds,
                    ["labels"] = states, ["passed"] = true };
            await Task.Delay(20);
        }
        throw new TimeoutException("Settings navigation did not complete its actual text draw: " + states.ToJsonString());
    }

    private async Task ExerciseHistoryScroll(JsonNode step, JsonObject record)
    {
        if (!PerformanceEnabled) throw new InvalidOperationException("History interaction is CI-only");
        await Select(step.Text("org"));
        await WaitForMarkdown(); await PerformanceYield();
        var wheelEvents = 0; var rootWheelEvents = 0; var viewEvents = 0; var topEvents = 0;
        var diagnostics = new JsonObject(); var checkpoints = new JsonArray(); var inputEvents = new JsonArray();
        diagnostics["checkpoints"] = checkpoints; diagnostics["events"] = inputEvents;
        record["history_input_diagnostics"] = diagnostics;
        void Checkpoint(string stage)
        {
            var state = new JsonObject { ["stage"] = stage, ["unix_ms"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                ["wheel_events"] = wheelEvents, ["root_wheel_events"] = rootWheelEvents, ["view_events"] = viewEvents,
                ["top_events"] = topEvents, ["keep_latest"] = keepLatest, ["loading_older"] = loadingOlder,
                ["chat_more"] = chatMore, ["chat_pages"] = chatPages, ["latest_request"] = latestRequest,
                ["vertical_offset"] = chatScroll.VerticalOffset, ["scrollable_height"] = chatScroll.ScrollableHeight,
                ["viewport_width"] = chatScroll.ViewportWidth, ["viewport_height"] = chatScroll.ViewportHeight };
            checkpoints.Add(state);
            try
            {
                var window = WinRT.Interop.WindowNative.GetWindowHandle(this);
                state["window"] = window.ToInt64(); state["foreground_window"] = WholeWindowForeground().ToInt64();
                if (WholeWindowGetRect(window, out var windowBox)) state["window_rect_px"] = WholeWindowBox(windowBox);
                var viewport = chatScroll.TransformToVisual(root).TransformBounds(new(0, 0, chatScroll.ActualWidth, chatScroll.ActualHeight));
                state["scroll_viewport_root_dip"] = new JsonObject { ["x"] = viewport.X, ["y"] = viewport.Y,
                    ["width"] = viewport.Width, ["height"] = viewport.Height };
                var center = chatScroll.TransformToVisual(root).TransformPoint(new(chatScroll.ActualWidth / 2, chatScroll.ActualHeight / 2));
                state["capture_hover_root_dip"] = new JsonObject { ["x"] = center.X, ["y"] = center.Y };
                var cursor = new CapturePoint(); var origin = new CapturePoint();
                if (GetCursorPos(ref cursor) && ClientToScreen(window, ref origin))
                {
                    var scale = root.XamlRoot.RasterizationScale;
                    var point = new Windows.Foundation.Point((cursor.x - origin.x) / scale, (cursor.y - origin.y) / scale);
                    var hitWindow = HistoryWindowFromPoint(cursor);
                    state["pointer_screen_px"] = new JsonObject { ["x"] = cursor.x, ["y"] = cursor.y };
                    state["client_origin_px"] = new JsonObject { ["x"] = origin.x, ["y"] = origin.y };
                    state["pointer_root_dip"] = new JsonObject { ["x"] = point.X, ["y"] = point.Y };
                    state["rasterization_scale"] = scale; state["pointer_inside_viewport"] = viewport.Contains(point);
                    state["pointer_window"] = hitWindow.ToInt64();
                    state["pointer_root_window"] = HistoryGetAncestor(hitWindow, 2).ToInt64();
                    var hits = new JsonArray();
                    foreach (var hit in Microsoft.UI.Xaml.Media.VisualTreeHelper.FindElementsInHostCoordinates(point, root).Take(16))
                        hits.Add(new JsonObject { ["type"] = hit.GetType().FullName, ["is_chat_scroll"] = ReferenceEquals(hit, chatScroll),
                            ["automation_id"] = Microsoft.UI.Xaml.Automation.AutomationProperties.GetAutomationId(hit) });
                    state["hit_test_front_to_back"] = hits;
                }
            }
            catch (Exception error) { state["observation_error"] = error.ToString(); }
        }
        void ObserveWheel(string receiver, Microsoft.UI.Xaml.Input.PointerRoutedEventArgs args)
        {
            if (inputEvents.Count >= 16) return;
            var point = args.GetCurrentPoint(chatScroll);
            inputEvents.Add(new JsonObject { ["event"] = "PointerWheelChanged", ["receiver"] = receiver,
                ["delta"] = point.Properties.MouseWheelDelta, ["handled"] = args.Handled,
                ["source_type"] = args.OriginalSource?.GetType().FullName, ["x"] = point.Position.X, ["y"] = point.Position.Y,
                ["keep_latest"] = keepLatest, ["vertical_offset"] = chatScroll.VerticalOffset });
        }
        Microsoft.UI.Xaml.Input.PointerEventHandler wheel = (_, args) =>
        {
            if (args.GetCurrentPoint(chatScroll).Properties.MouseWheelDelta > 0) wheelEvents++;
            ObserveWheel("chatScroll", args);
        };
        Microsoft.UI.Xaml.Input.PointerEventHandler rootWheel = (_, args) => { rootWheelEvents++; ObserveWheel("root", args); };
        EventHandler<ScrollViewerViewChangedEventArgs> changed = (_, args) =>
        {
            if (args.IsIntermediate) return;
            viewEvents++;
            if (chatScroll.VerticalOffset < 32) topEvents++;
            if (inputEvents.Count < 16) inputEvents.Add(new JsonObject { ["event"] = "ViewChanged", ["vertical_offset"] = chatScroll.VerticalOffset,
                ["keep_latest"] = keepLatest, ["loading_older"] = loadingOlder });
        };
        chatScroll.AddHandler(UIElement.PointerWheelChangedEvent, wheel, true);
        root.AddHandler(UIElement.PointerWheelChangedEvent, rootWheel, true);
        chatScroll.ViewChanged += changed;
        var pages = new JsonArray();
        try
        {
            async Task Until(Func<bool> done, string failure)
            {
                var waiting = Stopwatch.StartNew();
                while (!done())
                {
                    if (error.IsOpen) throw new InvalidOperationException(error.Message);
                    if (waiting.Elapsed > TimeSpan.FromSeconds(15)) throw new TimeoutException(failure);
                    await Task.Delay(20);
                }
            }
            long[] MessageIds() => messages.Where(row => row.Text("type") == "message")
                .Select(row => long.TryParse(row.Text("id"), out var id) ? id : 0).Where(id => id > 0).Distinct().ToArray();
            async Task<JsonObject> Boundary(bool bottom)
            {
                var waiting = Stopwatch.StartNew(); var quiet = 0;
                while (quiet < 2)
                {
                    if (waiting.Elapsed > TimeSpan.FromSeconds(15))
                        throw new TimeoutException(bottom ? "Real history scroll did not reach the bottom" : "Real history scroll did not reach the top");
                    chatScroll.ChangeView(null, bottom ? chatScroll.ScrollableHeight : 0, null, true);
                    await PerformanceYield(); await WaitForMarkdown();
                    var gap = bottom ? chatScroll.ScrollableHeight - chatScroll.VerticalOffset : chatScroll.VerticalOffset;
                    quiet = Math.Abs(gap) <= 1 ? quiet + 1 : 0;
                }
                var repeater = Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChild(stream, 0) as ItemsRepeater
                    ?? throw new InvalidOperationException("History viewport has no real ItemsRepeater");
                var index = bottom ? stream.Children.Count - 1 : 0;
                var row = repeater.TryGetElement(index) as FrameworkElement;
                if (row is not { IsLoaded: true, ActualHeight: > 0 })
                    throw new InvalidOperationException("History boundary row was not realized: " + index);
                var bounds = row.TransformToVisual(chatScroll).TransformBounds(new(0, 0, row.ActualWidth, row.ActualHeight));
                if (bounds.Bottom <= 0 || bounds.Top >= chatScroll.ViewportHeight)
                    throw new InvalidOperationException("History boundary row is outside the actual viewport: " + index);
                return new JsonObject { ["vertical_offset"] = chatScroll.VerticalOffset,
                    ["scrollable_height"] = chatScroll.ScrollableHeight, ["viewport_height"] = chatScroll.ViewportHeight,
                    ["gap_dip"] = bottom ? chatScroll.ScrollableHeight - chatScroll.VerticalOffset : chatScroll.VerticalOffset,
                    ["realized_row_index"] = index, ["row_top"] = bounds.Top, ["row_bottom"] = bounds.Bottom,
                    ["row_visible"] = true };
            }

            // A real upward wheel cancels the production follow-latest state.
            // ChangeView only drives the visible ScrollViewer; its ViewChanged
            // handler must perform every page request without a business-method
            // fallback or a test-written keepLatest/loadingOlder state.
            capturePointerReceipts.Clear();
            Checkpoint("before_hover");
            diagnostics["set_foreground_returned"] = SetForegroundWindow(WinRT.Interop.WindowNative.GetWindowHandle(this));
            await CaptureHover(chatScroll);
            Checkpoint("after_hover_before_wheel");
            SendCaptureMouse(new CaptureMouseInput { Data = 120, Flags = 0x0800 });
            diagnostics["injected_wheel_delta"] = 120;
            await Until(() => wheelEvents > 0 && !keepLatest, "Real upward scroll did not leave follow-latest mode");
            Checkpoint("wheel_processed");
            await PerformanceYield();
            while (chatMore)
            {
                var beforeIds = MessageIds(); var beforePages = chatPages; var beforeViews = viewEvents;
                chatScroll.ChangeView(null, 0, null, true);
                await Until(() => chatPages > beforePages && !loadingOlder,
                    "History did not page through the production ScrollViewer.ViewChanged handler");
                await WaitForMarkdown(); await PerformanceYield();
                var afterIds = MessageIds();
                if (afterIds.Length <= beforeIds.Length || afterIds.Min() >= beforeIds.Min() || viewEvents <= beforeViews)
                    throw new InvalidOperationException("Real history scroll did not add an older message page");
                pages.Add(new JsonObject { ["before_pages"] = beforePages, ["after_pages"] = chatPages,
                    ["before_oldest_id"] = beforeIds.Min(), ["after_oldest_id"] = afterIds.Min(),
                    ["messages_added"] = afterIds.Length - beforeIds.Length, ["view_changed_events"] = viewEvents - beforeViews });
            }
            record["history_top"] = await Boundary(false);
            var ids = MessageIds();
            var oldest = ids.DefaultIfEmpty(0).Min();
            var expectedOldest = long.Parse(step.Text("first_message_id"));
            var fixture = performanceManifest!["fixture"].Rows("orgs").First(item => item.Text("id") == step.Text("org"));
            var expectedCount = int.Parse(fixture.Text("group_messages"));
            if (oldest != expectedOldest || ids.Length < expectedCount || topEvents == 0)
                throw new InvalidOperationException($"History coverage mismatch: oldest={oldest}/{expectedOldest}, messages={ids.Length}/{expectedCount}, top events={topEvents}");
            record["pages_loaded"] = chatPages; record["history_complete"] = !chatMore;
            record["oldest_message_id"] = oldest; record["message_count"] = ids.Length;
            record["expected_fixture_messages"] = expectedCount; record["history_pages"] = pages;
            record["upward_wheel_events"] = wheelEvents; record["top_view_changed_events"] = topEvents;
            record["history_bottom"] = await Boundary(true);
            record["history_scroll_source"] = "Actual upward pointer wheel and ScrollViewer.ViewChanged; no direct page load";
        }
        catch (Exception error)
        {
            diagnostics["failure"] = error.ToString();
            Checkpoint("failure");
            throw;
        }
        finally
        {
            chatScroll.RemoveHandler(UIElement.PointerWheelChangedEvent, wheel);
            root.RemoveHandler(UIElement.PointerWheelChangedEvent, rootWheel);
            chatScroll.ViewChanged -= changed;
            diagnostics["pointer_input"] = capturePointerReceipts.DeepClone();
            Checkpoint("finished");
            // Failed actions are not added to the success receipt. Preserve the
            // real input observations independently before propagating failure.
            await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(PerformanceOutput, "history-" + record.Text("id") + ".json"),
                record.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
        }
    }

    [System.Runtime.InteropServices.DllImport("user32.dll", EntryPoint = "WindowFromPoint")]
    private static extern nint HistoryWindowFromPoint(CapturePoint point);
    [System.Runtime.InteropServices.DllImport("user32.dll", EntryPoint = "GetAncestor")]
    private static extern nint HistoryGetAncestor(nint window, uint flags);

    private async Task RunPerformanceScenario()
    {
        var actions = new List<JsonObject>(); var errors = new List<string>();
        var randomActions = 0; double randomSeconds = 0;
        var pointerRandom = new Random(int.Parse(performanceManifest!.Text("seed")));
        async Task Execute(JsonNode step, bool random)
        {
            var kind = step.Text("kind");
            var target = step.Text("org") + step.Text("member") + step.Text("pane") + step.Text("name");
            Volatile.Write(ref performanceAction, (random ? "monkey " : "") + kind + ": " + target);
            var clock = Stopwatch.StartNew(); var record = new JsonObject {
                ["id"] = random ? "monkey-" + randomActions : step.Text("id"), ["kind"] = kind, ["target"] = target };
            switch (kind)
            {
                case "group": await Select(step.Text("org")); break;
                case "private": await Select(step.Text("org"), step.Text("member")); break;
                case "pane": await SetPane(step.Text("pane")); break;
                case "resize":
                    var monitor = CurrentWindowMonitor();
                    AppWindow.Resize(new(WindowSizing.Pixels(int.Parse(step.Text("width")), monitor.Scale),
                        WindowSizing.Pixels(int.Parse(step.Text("height")), monitor.Scale))); break;
                case "menu":
                    var index = Array.IndexOf(new[] { "file", "edit", "view", "help" }, step.Text("name"));
                    var menu = nativeMenus[index];
                    SetForegroundWindow(WinRT.Interop.WindowNative.GetWindowHandle(this));
                    capturePointerReceipts.Clear(); await CaptureClick(menu.Anchor);
                    await PerformanceYield();
                    if (!menu.Flyout.IsOpen) throw new InvalidOperationException("Production menu did not open");
                    menu.Flyout.Hide(); break;
                case "dialog":
                    var dialog = step.Text("name") switch { "settings" => Settings(), "about" => SettingsScreen("about"),
                        "neworg" => CreateOrg(), "member" => AddMember(), "tasks" => Details("tasks"),
                        "protocols" => Details("protocols"), _ => throw new InvalidOperationException("Unknown dialog") };
                    // Preparation can include several HTTP requests. Waiting on
                    // the dialog task before it has opened instead waits for a
                    // user dismissal forever. Also, Hide before Opened can be
                    // ignored while ContentDialog is still presenting.
                    var opening = Stopwatch.StartNew();
                    while (openedDialog == null && !dialog.IsCompleted && opening.Elapsed < TimeSpan.FromSeconds(20))
                        await Task.Delay(20);
                    if (openedDialog == null)
                    {
                        if (dialog.IsCompleted) await dialog; // Preserve a real preparation error.
                        throw new TimeoutException("Production dialog did not reach Opened: " + step.Text("name"));
                    }
                    var presented = openedDialog;
                    await WaitForMarkdown();
                    if (step.Text("name") is "settings" or "about")
                        record["navigation_text_ready"] = await WaitForSettingsNavigationDraw(presented);
                    await PerformanceYield(); presented.Hide();
                    await dialog.WaitAsync(TimeSpan.FromSeconds(10)); break;
                case "scroll-history":
                    await ExerciseHistoryScroll(step, record); break;
                default: throw new InvalidOperationException("Unknown performance action: " + kind);
            }
            await PerformanceYield(); await WaitForMarkdown();
            if (random)
            {
                // Seeded real pointer targets supplement the production command
                // deck. Count actual routed Click events, not sent input calls.
                SetForegroundWindow(WinRT.Interop.WindowNative.GetWindowHandle(this));
                var targetIndex = pointerRandom.Next(8);
                var targetName = new[] { "sidebar", "overview", "workspace", "files", "file-menu", "edit-menu", "view-menu", "help-menu" }[targetIndex];
                var button = targetIndex == 0 ? (Button)navigationButtons.Children[1]
                    : targetIndex < 4 ? (Button)((AppBarElementContainer)toolbar.PrimaryCommands[targetIndex + 2]).Content
                    : nativeMenus[targetIndex - 4].Anchor;
                var clicks = 0;
                RoutedEventHandler clicked = (_, _) => clicks++;
                capturePointerReceipts.Clear(); button.Click += clicked;
                try
                {
                    await CaptureClick(button); await PerformanceYield();
                    while (Volatile.Read(ref performanceCommands) > 0) await Task.Delay(20);
                    if (clicks == 0) throw new InvalidOperationException("Real random click was not handled: " + targetName);
                    if (targetIndex >= 4)
                    {
                        if (!nativeMenus[targetIndex - 4].Flyout.IsOpen) throw new InvalidOperationException("Real random menu did not open");
                        nativeMenus[targetIndex - 4].Flyout.Hide();
                    }
                    await WaitForMarkdown();
                }
                finally { button.Click -= clicked; }
                record["pointer_target"] = targetName; record["click_events"] = clicks;
                record["pointer_events"] = capturePointerReceipts.DeepClone();
            }
            if (error.IsOpen) throw new InvalidOperationException(error.Message);
            record["elapsed_ms"] = clock.Elapsed.TotalMilliseconds; record["passed"] = true;
            record["realized_chat_rows"] = stream.Realized;
            actions.Add(record);
        }
        try
        {
            await WaitForMarkdown();
            foreach (var step in performanceManifest!.Rows("plan")) await Execute(step!, false);
            var deck = performanceManifest.Rows("monkey");
            var timer = Stopwatch.StartNew();
            while (timer.Elapsed.TotalSeconds < int.Parse(performanceManifest.Text("seconds")))
            {
                await Execute(deck[randomActions % deck.Count]!, true);
                randomActions++; await Task.Delay(100);
            }
            randomSeconds = timer.Elapsed.TotalSeconds;
        }
        catch (Exception ex) { errors.Add(ex.ToString()); }
        finally
        {
            performanceCancellation!.Cancel();
            try { await performanceProbe!; } catch (OperationCanceledException) { }
            await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(PerformanceOutput, "performance-complete.json"),
                JsonSerializer.Serialize(new { actions, errors, max_ui_stall_ms = Interlocked.Read(ref performanceWorstTicks) * 1000d / Stopwatch.Frequency,
                    titlebar_layout_notifications = titlebarLayoutNotifications, titlebar_layout_measurements = titlebarLayoutMeasurements,
                    random_seconds = randomSeconds, random_actions = randomActions, seed = int.Parse(performanceManifest!.Text("seed")) }));
        }
    }
}
