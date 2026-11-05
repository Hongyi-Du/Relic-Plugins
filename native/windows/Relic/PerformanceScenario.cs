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

    private readonly object performanceTraceFile = new();
    // Appends the trace records gathered so far. Also right before idle is
    // measured: serializing the backlog of the last draw took the probe's
    // worker 70 M cycles in the first measured second of the large profile.
    private void FlushPerformanceTrace()
    {
        lock (performanceTraceFile)
        {
            var batch = PerformanceTrace.Drain();
            if (batch.Length > 0)
                System.IO.File.AppendAllText(System.IO.Path.Combine(PerformanceOutput, "timings.jsonl"),
                    string.Join("\n", batch.Select(timing => JsonSerializer.Serialize(timing))) + "\n");
        }
    }

    private void StartPerformanceProbe()
    {
        if (!PerformanceEnabled) return;
        performanceManifest = JsonNode.Parse(System.IO.File.ReadAllText(Environment.GetEnvironmentVariable("RELIC_PERF_MANIFEST")!))!;
        System.IO.Directory.CreateDirectory(PerformanceOutput);
        performanceCancellation = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
        var token = performanceCancellation.Token;
        PerformanceStallCpu.CaptureUiThread();
        var probeDone = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        performanceProbe = probeDone.Task;
        // A thread of its own that sleeps between pings. On the thread pool
        // each 40 ms ping woke the timer thread, a pool worker and the UI
        // thread, and the probe alone used about 1% of a core while the app
        // sat idle. The cadence and what each ping measures are unchanged.
        new Thread(() =>
        {
            try { Probe(); probeDone.TrySetResult(); }
            catch (Exception error) { probeDone.TrySetException(error); }
        }) { IsBackground = true, Name = "Relic CI UI probe" }.Start();
        void Probe()
        {
            void Write(string name, object value)
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
                        Thread.Sleep(2);
                    }
                }
            }
            Write("performance-ready.json", new { pid = Environment.ProcessId, unix_ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), phases_version = 2 });
            long sequence = 0, pings = 0, lastCensus = 0, lastIdleSample = 0;
            long lastPublished = 0, publishedWorst = -1, pendingSince = 0;
            string? publishedAction = null;
            var publishedPending = false;
            Task<long>? activeProbe = null;
            void Publish(bool force)
            {
                var worst = Interlocked.Read(ref performanceWorstTicks);
                var action = Volatile.Read(ref performanceAction);
                var pending = activeProbe is { IsCompletedSuccessfully: false } ? pendingSince : 0;
                // Probe the UI at the original 40 ms cadence. Only healthy
                // file publication is batched: every 500 ms is well inside the
                // harness's 2 s staleness limit and keeps the probe's own file
                // writes out of the measured idle CPU. A pending probe, its
                // recovery, a new maximum or an action change is still
                // published on the very next observation.
                // While idle is measured, every second is still half the
                // staleness limit, and the write is the probe's largest cost.
                if (!force && pending == 0 && !publishedPending && worst <= publishedWorst && action == publishedAction
                    && Stopwatch.GetElapsedTime(lastPublished).TotalMilliseconds < (action == "idle-measure" ? 1000 : 500)) return;
                Write("heartbeat.json", new { unix_ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), sequence = ++sequence, pings,
                    max_ui_stall_ms = worst * 1000d / Stopwatch.Frequency,
                    pending_since_unix_ms = pending,
                    titlebar_layout_notifications = Interlocked.Read(ref titlebarLayoutNotifications),
                    titlebar_layout_measurements = Interlocked.Read(ref titlebarLayoutMeasurements),
                    action });
                FlushPerformanceTrace();
                lastPublished = Stopwatch.GetTimestamp(); publishedWorst = worst;
                publishedAction = action; publishedPending = pending != 0;
            }
            try
            {
                while (!token.IsCancellationRequested)
                {
                    var sent = Stopwatch.GetTimestamp();
                    pendingSince = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
                    // Not while idle is measured: three more system calls a ping.
                    var cpuAtSend = Volatile.Read(ref performanceAction) == "idle-measure" ? default : PerformanceStallCpu.Read();
                    PerformanceStallCpu.Waits? waits = null;
                    var completed = new TaskCompletionSource<long>(TaskCreationOptions.RunContinuationsAsynchronously);
                    if (!DispatcherQueue.TryEnqueue(DispatcherQueuePriority.Normal, () =>
                    {
                        completed.TrySetResult(Stopwatch.GetTimestamp());
                    })) break;
                    activeProbe = completed.Task;
                    while (!token.IsCancellationRequested)
                    {
                        // One timer per wait. A ping usually completes within a
                        // millisecond; racing it against a fresh 40 ms delay
                        // left that timer to fire for nothing, and a second
                        // delay followed, so the probe woke twice as often as it
                        // measured (idle too). The latency is the ping's own
                        // completion time either way.
                        if (token.WaitHandle.WaitOne(40)) break;
                        var ticks = (completed.Task.IsCompletedSuccessfully ? completed.Task.Result : Stopwatch.GetTimestamp()) - sent;
                        if (!completed.Task.IsCompletedSuccessfully && cpuAtSend.At != 0 && ticks * 1000d / Stopwatch.Frequency >= 80)
                            (waits ??= new()).Sample();
                        var old = Interlocked.Read(ref performanceWorstTicks);
                        if (ticks > old) Interlocked.Exchange(ref performanceWorstTicks, ticks);
                        if (completed.Task.IsCompletedSuccessfully && ticks * 1000d / Stopwatch.Frequency > 5)
                            PerformanceTrace.Count("ui.dispatch", ticks * 1000d / Stopwatch.Frequency);
                        if (completed.Task.IsCompletedSuccessfully) pings++;
                        PerformanceTrace.RecordCollection();
                        Publish(false);
                        if (completed.Task.IsCompletedSuccessfully)
                        {
                            var stall = ticks * 1000d / Stopwatch.Frequency;
                            if (stall > 100 && cpuAtSend.At != 0)
                                PerformanceStallCpu.Note(Volatile.Read(ref performanceAction), stall, cpuAtSend, PerformanceStallCpu.Read(), waits);
                            break;
                        }
                    }
                    // Only while switching chats: the census enumerates threads,
                    // and the idle phase measures the process's own CPU.
                    if (Volatile.Read(ref performanceAction).StartsWith("switch", StringComparison.Ordinal)
                        && Stopwatch.GetElapsedTime(lastCensus).TotalMilliseconds >= 2000)
                    { lastCensus = Stopwatch.GetTimestamp(); PerformanceThreadCensus.Take(); }
                    // While idle, once a second: which threads used CPU (cached
                    // handles only, no thread enumeration), and every timed piece
                    // of our own work however short. Two runs of the same code
                    // measured 0.5% and 2.3% idle CPU.
                    var idleNow = Volatile.Read(ref performanceAction) == "idle-measure";
                    PerformanceTrace.RecordAll = idleNow;
                    if (idleNow && Stopwatch.GetElapsedTime(lastIdleSample).TotalMilliseconds >= 1000)
                    { lastIdleSample = Stopwatch.GetTimestamp(); PerformanceThreadCensus.SampleCycles(); }
                }
            }
            finally { Publish(true); }
        }
        _ = performanceProbe.ContinueWith(task => System.IO.File.WriteAllText(
            System.IO.Path.Combine(PerformanceOutput, "probe-error.txt"), task.Exception!.ToString()),
            CancellationToken.None, TaskContinuationOptions.OnlyOnFaulted, TaskScheduler.Default);
    }

    // CI-only, after the measured switches: which redraw leaves native memory
    // behind. Private bytes grew about 0.27 MB per switch, most of it live
    // allocations in the process heaps, while live labels and chat rows stayed
    // flat. Each experiment repeats one production redraw and reads the heaps'
    // live bytes after full collections. Those run off the UI thread, so the
    // finalizers that release UI objects back on the UI thread can run.
    private async Task ProbeNativeLeaks()
    {
        Volatile.Write(ref performanceAction, "leak-probe");
        async Task<long> Settled()
        {
            for (var pass = 0; pass < 3; pass++)
            {
                await Task.Run(() => { GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect(); });
                await PerformanceYield();
            }
            return PerformanceTrace.HeapAllocated();
        }
        async Task Measure(string name, int count, Func<int, Task> step)
        {
            var before = await Settled(); var managedBefore = GC.GetTotalMemory(false);
            var clock = Stopwatch.StartNew();
            for (var index = 0; index < count; index++) { await step(index); await PerformanceYield(); }
            var after = await Settled(); var managedAfter = GC.GetTotalMemory(false);
            PerformanceTrace.Note("leak.probe", new { name, count, heap_before = before, heap_after = after,
                heap_per_step = (after - before) / (double)count, managed_per_step = (managedAfter - managedBefore) / (double)count,
                ms = Math.Round(clock.Elapsed.TotalMilliseconds), alive = PerformanceTrace.AliveCounts() });
        }
        await Measure("baseline", 12, _ => Task.CompletedTask);
        await Measure("toolbar", 12, _ => { DrawToolbar(); return Task.CompletedTask; });
        await Measure("sidebar", 12, _ => { DrawSide(); return Task.CompletedTask; });
        await Measure("detail", 12, _ => { DrawDetail(); return Task.CompletedTask; });
        // The inspector redraw left about 0.4 MB per call. Single controls it
        // builds, each mounted for a frame and removed again.
        async Task Mount(Func<FrameworkElement> make)
        {
            var element = make(); inspector.Children.Add(element);
            await PerformanceYield();
            inspector.Children.Remove(element);
        }
        await Measure("shadow", 12, step => Mount(() =>
        {
            var panel = new NativeShadowPanel(new Border { Width = 80, Height = 24, CornerRadius = new CornerRadius(6) });
            panel.SetShadows([new NativeShadowLayer(0, 1, 2, Windows.UI.Color.FromArgb(255, 20, 18, 15), .06f)]);
            return panel;
        }));
        await Measure("selectorbar", 12, step => Mount(() =>
        {
            var bar = new SelectorBar();
            foreach (var text in new[] { "A", "B", "C" }) bar.Items.Add(new SelectorBarItem { Text = text });
            return bar;
        }));
        await Measure("tabs", 12, step => Mount(() => DetailsTabs(new[] { ("a", "A"), ("b", "B"), ("c", "C") }, "a", value => Task.CompletedTask)));
        await Measure("toggle", 12, step => Mount(() => OverviewSwitch("x", true, false, value => Task.CompletedTask)));
        var homeOrg = org; var homeMember = member;
        var otherOrg = orgs.Select(item => item.Text("id")).FirstOrDefault(id => id.Length > 0 && id != homeOrg) ?? homeOrg;
        await Measure("switch", 12, async index =>
        {
            if (index % 2 == 0) await Select(otherOrg); else await Select(homeOrg, homeMember);
            await WaitForMarkdown();
        });
        await Settled();
        PerformanceTrace.Note("leak.survivors", DescribeSurvivors());
        // The sidebar's organization rows outlived full collections after
        // being replaced. Mount and remove one part of such a row at a time
        // and count which of them survive.
        async Task Parts(string name, Func<FrameworkElement> make, Func<FrameworkElement, Task>? mounted = null)
        {
            var made = new List<WeakReference>();
            for (var index = 0; index < 12; index++)
            {
                var element = make(); made.Add(new WeakReference(element));
                inspector.Children.Add(element); await PerformanceYield();
                if (mounted != null) { await mounted(element); await PerformanceYield(); }
                inspector.Children.Remove(element); await PerformanceYield();
            }
            await Settled();
            PerformanceTrace.Note("leak.parts", new { name, made = made.Count, alive = made.Count(entry => entry.IsAlive) });
        }
        ListView SidebarList(UIElement content, Action<NativeSidebarRow>? decorate = null)
        {
            var list = new ListView { SelectionMode = ListViewSelectionMode.Single, IsItemClickEnabled = true, Padding = new Thickness(0),
                BorderThickness = new Thickness(0), Template = sidebarListTemplate!, ItemsPanel = sidebarItemsPanel! };
            var row = new NativeSidebarRow { Content = content, Template = sidebarItemTemplate! };
            decorate?.Invoke(row); list.Items.Add(row);
            return list;
        }
        var probeOrg = orgs.FirstOrDefault() ?? new JsonObject { ["id"] = "probe", ["name"] = "Probe" };
        await Parts("text", () => SidebarText("Probe"));
        await Parts("avatar", () => SidebarPicture("Probe", new Border { Width = 22, Height = 22 }, 22));
        await Parts("org_face", () => SidebarOrgFace(probeOrg!));
        await Parts("list_row", () => SidebarList(SidebarText("Probe")));
        await Parts("list_row_name", () => SidebarList(SidebarText("Probe"), row => BindSidebarRowName(row, (UIElement)row.Content)));
        await Parts("list_row_flyout", () =>
        {
            var content = SidebarText("Probe"); var menu = new MenuFlyout(); menu.Items.Add(new MenuFlyoutItem { Text = "Probe" });
            content.ContextFlyout = menu; return SidebarList(content);
        });
        await Parts("list_row_tooltip", () => { var content = SidebarText("Probe"); SidebarToolTip(content, "Probe"); return SidebarList(content); });
        await Parts("list_row_avatar", () => SidebarList(SidebarOrgFace(probeOrg!)));
        // None of those parts survived alone, yet replaced organization rows
        // did. Release one suspect registration at a time and count the
        // detached rows still alive before and after.
        static bool Attached(DependencyObject element, DependencyObject root)
        {
            for (var parent = Microsoft.UI.Xaml.Media.VisualTreeHelper.GetParent(element); parent != null;
                parent = Microsoft.UI.Xaml.Media.VisualTreeHelper.GetParent(parent))
                if (ReferenceEquals(parent, root)) return true;
            return false;
        }
        int DetachedSidebarRows() => PerformanceTrace.AliveObjects().TryGetValue("VirtualRow.sidebar", out var alive)
            ? alive.OfType<FrameworkElement>().Count(element => !Attached(element, root)) : 0;
        async Task Release(string name, Action release)
        {
            await Settled(); var before = DetachedSidebarRows();
            release(); await PerformanceYield(); await Settled(); var after = DetachedSidebarRows();
            PerformanceTrace.Note("leak.release", new { name, before, after, selection_updates = sidebarSelectionUpdates.Count,
                message_interactions = messageInteractions.Count, typing = liveTypingAnimations.Count,
                microphones = microphoneButtons.Count, menu_bindings = menuStateBindings.Count });
        }
        await Release("none", () => { });
        await Release("selection_updates", UpdateSidebarSelection);
        await Release("sidebar_redraw", DrawSide);
        await Release("sidebar_cleared", () => { side.Children.Clear(); side.Commit(); });
        DrawSide();
        // Each redraw (and the clear) kept exactly one more row, with or
        // without the pointer on it. Rows that were selected, focused or
        // clicked before their removal, as the opened organization's row is:
        static ListViewItem FirstItem(FrameworkElement element) => (ListViewItem)((ListView)element).Items[0];
        FrameworkElement ProbeList() { var list = SidebarList(SidebarText("Probe")); list.Width = 200; list.Height = 34; return list; }
        await Parts("list_row_selected", () => { var list = ProbeList(); ((ListView)list).SelectedItem = FirstItem(list); return list; });
        await Parts("list_row_focused", ProbeList, element => { FirstItem(element).Focus(FocusState.Programmatic); return Task.CompletedTask; });
        await Parts("list_row_clicked", ProbeList, async element =>
        {
            await CaptureHover(element); CapturePointerButton(true);
            try { await Task.Delay(40); } finally { CapturePointerButton(false); }
        });
        // Selected only before mounting, none survived; the sidebar selects
        // its row once the row is loaded.
        await Parts("list_row_selected_live", ProbeList, element => { ((ListView)element).SelectedItem = FirstItem(element); return Task.CompletedTask; });
        await Parts("list_row_selected_live_released", ProbeList, async element =>
        {
            ((ListView)element).SelectedItem = FirstItem(element); await PerformanceYield();
            ReleaseSidebarRow(element);
        });
        await CaptureHover(chatScroll); await PerformanceYield();
    }

    // CI-only: the tracked rows that outlived full collections while out of
    // the window's tree, grouped by what they are, to find what holds them.
    private JsonObject DescribeSurvivors()
    {
        var result = new JsonObject();
        foreach (var (kind, objects) in PerformanceTrace.AliveObjects())
        {
            var groups = new Dictionary<string, int>(); var attached = 0;
            foreach (var item in objects)
            {
                if (item is not FrameworkElement element) continue;
                DependencyObject top = element; var depth = 0; var inRoot = false;
                for (var parent = Microsoft.UI.Xaml.Media.VisualTreeHelper.GetParent(element); parent != null;
                    parent = Microsoft.UI.Xaml.Media.VisualTreeHelper.GetParent(parent))
                { inRoot |= ReferenceEquals(parent, root); top = parent; depth++; }
                if (inRoot) { attached++; continue; }
                var (text, watching, sidebarRows) = SurvivorContent(element);
                var key = element.GetType().Name + " parent=" + (Microsoft.UI.Xaml.Media.VisualTreeHelper.GetParent(element)?.GetType().Name ?? "none")
                    + " top=" + top.GetType().Name + " depth=" + depth + " loaded=" + element.IsLoaded
                    + " id=" + Microsoft.UI.Xaml.Automation.AutomationProperties.GetAutomationId(element)
                    + " rows=" + sidebarRows + " watching=" + watching
                    + " selected=" + (element is ListView { SelectedItem: not null })
                    + " focus=" + ((element as ListView)?.Items.FirstOrDefault() as Control)?.FocusState + " text=" + text;
                groups[key] = groups.GetValueOrDefault(key) + 1;
            }
            var detached = new JsonObject();
            foreach (var (key, count) in groups.OrderByDescending(group => group.Value).Take(12)) detached[key] = count;
            result[kind] = new JsonObject { ["alive"] = objects.Count, ["attached"] = attached, ["detached"] = detached };
        }
        return result;
    }

    // The first text in an element's subtree, and how many sidebar rows it
    // holds with property callbacks still registered.
    private static (string Text, int Watching, int SidebarRows) SurvivorContent(DependencyObject node)
    {
        var queue = new Queue<DependencyObject>(); queue.Enqueue(node);
        string? text = null; var watching = 0; var rows = 0; var seen = 0;
        while (queue.Count > 0 && seen++ < 400)
        {
            var current = queue.Dequeue();
            if (current is NativeSidebarRow row) { rows++; watching += row.Watching; }
            text ??= current switch { TextBlock block when block.Text.Length > 0 => block.Text,
                NativeLabel label when label.Text.Length > 0 => label.Text, _ => null };
            for (var index = 0; index < Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(current); index++)
                queue.Enqueue(Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChild(current, index));
        }
        text ??= "";
        return (text.Length > 32 ? text[..32] : text, watching, rows);
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
            if (navigation.Count == 8 && navigation.All(item => item.IsLoaded && item.Visibility == Visibility.Visible
                && item.CurrentLabel is { HasCurrentDraw: true, ActualWidth: > 0, ActualHeight: > 0 }))
                return new JsonObject { ["source"] = "Eight actual mounted settings navigation labels after their production SurfaceImageSource EndDraw",
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
        var wheelEvents = 0; var rootWheelEvents = 0; var viewEvents = 0; var topEvents = 0; var topWheelEvents = 0; var endKeyEvents = 0;
        var expectedAnchorPage = -1;
        VirtualRows.ReadingAnchor? expectedReadingAnchor = null;
        var observedAnchorCases = 0;
        void ObserveReadingAnchor()
        {
            if (expectedAnchorPage == chatPages && loadingOlder && chatScroll.VerticalOffset < 32)
                expectedReadingAnchor ??= stream.ReadVisibleAnchor(chatScroll);
        }
        void ObserveItemsReplacing()
        {
            // A far scroll may initially expose only unmaterialized hosts.
            // Observe the actual old content immediately before its replacement,
            // without creating a row or steering the product's scroll state.
            if (expectedAnchorPage >= 0 && chatPages == expectedAnchorPage + 1 && loadingOlder)
                expectedReadingAnchor ??= stream.ReadVisibleAnchor(chatScroll);
        }
        var diagnostics = new JsonObject(); var checkpoints = new JsonArray(); var inputEvents = new JsonArray();
        diagnostics["checkpoints"] = checkpoints; diagnostics["events"] = inputEvents;
        record["history_input_diagnostics"] = diagnostics;
        void Checkpoint(string stage)
        {
            var state = new JsonObject { ["stage"] = stage, ["unix_ms"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                ["wheel_events"] = wheelEvents, ["root_wheel_events"] = rootWheelEvents, ["view_events"] = viewEvents,
                ["top_events"] = topEvents, ["top_wheel_events"] = topWheelEvents, ["end_key_events"] = endKeyEvents,
                ["keep_latest"] = keepLatest, ["loading_older"] = loadingOlder,
                ["chat_more"] = chatMore, ["chat_pages"] = chatPages, ["latest_request"] = latestRequest,
                ["vertical_offset"] = chatScroll.VerticalOffset, ["scrollable_height"] = chatScroll.ScrollableHeight,
                ["viewport_width"] = chatScroll.ViewportWidth, ["viewport_height"] = chatScroll.ViewportHeight,
                ["native_positioning"] = System.Text.Json.JsonSerializer.SerializeToNode(stream.ReadScrollState(chatScroll)),
                ["pending_conversation_model"] = PendingConversationPreparation,
                ["pending_glyphs"] = NativeGlyphWarmup.PendingPreparations,
                ["pending_chat_rows"] = NativeChatList.PendingBuilds, ["pending_other_rows"] = VirtualRows.PendingBuilds,
                ["pending_path_text"] = NativePathText.PendingPreparations, ["pending_labels"] = NativeLabel.PendingPreparations,
                ["pending_markdown"] = PendingMarkdown };
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
            if (args.GetCurrentPoint(chatScroll).Properties.MouseWheelDelta > 0)
            {
                wheelEvents++;
                if (chatScroll.VerticalOffset < 32) topWheelEvents++;
            }
            ObserveWheel("chatScroll", args);
            ObserveReadingAnchor();
        };
        Microsoft.UI.Xaml.Input.PointerEventHandler rootWheel = (_, args) => { rootWheelEvents++; ObserveWheel("root", args); };
        Microsoft.UI.Xaml.Input.KeyEventHandler endKey = (_, args) =>
        {
            if (args.Key != Windows.System.VirtualKey.End) return;
            endKeyEvents++;
            diagnostics["end_key_event"] = new JsonObject { ["key"] = args.Key.ToString(), ["handled"] = args.Handled,
                ["source_type"] = args.OriginalSource?.GetType().FullName,
                ["source_is_chat_scroll"] = ReferenceEquals(args.OriginalSource, chatScroll) };
        };
        EventHandler<ScrollViewerViewChangedEventArgs> changed = (_, args) =>
        {
            if (args.IsIntermediate) return;
            viewEvents++;
            if (chatScroll.VerticalOffset < 32) topEvents++;
            ObserveReadingAnchor();
            if (inputEvents.Count < 16) inputEvents.Add(new JsonObject { ["event"] = "ViewChanged", ["vertical_offset"] = chatScroll.VerticalOffset,
                ["keep_latest"] = keepLatest, ["loading_older"] = loadingOlder });
        };
        chatScroll.AddHandler(UIElement.PointerWheelChangedEvent, wheel, true);
        root.AddHandler(UIElement.PointerWheelChangedEvent, rootWheel, true);
        chatScroll.AddHandler(UIElement.KeyDownEvent, endKey, true);
        chatScroll.ViewChanged += changed;
        stream.ItemsReplacing += ObserveItemsReplacing;
        var pages = new JsonArray();
        record["history_pages"] = pages;
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
                if (bottom)
                {
                    // End is actual user intent. Repeated numeric ChangeView(max)
                    // cannot distinguish that intent from virtual extent repair.
                    if (!chatScroll.Focus(FocusState.Programmatic))
                        throw new InvalidOperationException("Could not focus the real conversation scroll control");
                    await PerformanceYield();
                    var focused = Microsoft.UI.Xaml.Input.FocusManager.GetFocusedElement(root.XamlRoot);
                    diagnostics["end_key_focus"] = new JsonObject { ["type"] = focused?.GetType().FullName,
                        ["is_chat_scroll"] = ReferenceEquals(focused, chatScroll) };
                    if (!ReferenceEquals(focused, chatScroll))
                        throw new InvalidOperationException("Conversation focus was redirected away from the scroll control");
                    var beforeKeys = endKeyEvents;
                    var inputs = new[] { false, true }.Select(up => new WholeWindowInput { type = 1,
                        data = new WholeWindowInputData { keyboard = new WholeWindowKeyboardInput
                            { virtualKey = 0x23, flags = 0x0001u | (up ? 0x0002u : 0u) } } }).ToArray();
                    var inserted = WholeWindowSendInput((uint)inputs.Length, inputs,
                        System.Runtime.InteropServices.Marshal.SizeOf<WholeWindowInput>());
                    diagnostics["end_key_input"] = new JsonObject { ["operation"] = "SendInput End down/up to focused conversation",
                        ["virtual_key"] = 0x23, ["inserted_events"] = inserted };
                    if (inserted != inputs.Length) throw new System.ComponentModel.Win32Exception(
                        System.Runtime.InteropServices.Marshal.GetLastWin32Error(), "Could not insert actual End input");
                    await Until(() => endKeyEvents > beforeKeys && keepLatest,
                        "Actual End input did not activate production follow-latest behavior");
                }
                var waiting = Stopwatch.StartNew(); var quiet = 0;
                JsonObject? observation = null;
                while (quiet < 2)
                {
                    if (waiting.Elapsed > TimeSpan.FromSeconds(15))
                        throw new TimeoutException(bottom ? "Real history scroll did not reach the bottom" : "Real history scroll did not reach the top");
                    if (!bottom) chatScroll.ChangeView(null, 0, null, true);
                    await PerformanceYield(); await WaitForMarkdown();
                    var gap = bottom ? chatScroll.ScrollableHeight - chatScroll.VerticalOffset : chatScroll.VerticalOffset;
                    var index = bottom ? stream.Children.Count - 1 : 0;
                    var row = stream.TryGetRealizedRow(index);
                    var realized = row is { IsLoaded: true, Child: not null, ActualHeight: > 0 };
                    var bounds = realized ? row!.TransformToVisual(chatScroll).TransformBounds(new(0, 0, row.ActualWidth, row.ActualHeight))
                        : default;
                    var visible = realized && bounds.Bottom > 0 && bounds.Top < chatScroll.ViewportHeight;
                    observation = new JsonObject { ["vertical_offset"] = chatScroll.VerticalOffset,
                        ["scrollable_height"] = chatScroll.ScrollableHeight, ["viewport_height"] = chatScroll.ViewportHeight,
                        ["native_positioning"] = System.Text.Json.JsonSerializer.SerializeToNode(stream.ReadScrollState(chatScroll)),
                        ["gap_dip"] = gap, ["realized_row_index"] = index, ["row_realized"] = realized,
                        ["row_top"] = realized ? bounds.Top : null, ["row_bottom"] = realized ? bounds.Bottom : null,
                        ["row_visible"] = visible, ["elapsed_ms"] = waiting.Elapsed.TotalMilliseconds };
                    diagnostics[bottom ? "bottom_boundary_observation" : "top_boundary_observation"] = observation.DeepClone();
                    // A numeric boundary and empty preparation queues do not
                    // prove that the next virtual realization has occurred.
                    // Require the actual drawn row in the same bounded wait.
                    quiet = Math.Abs(gap) <= 1 && visible ? quiet + 1 : 0;
                }
                return observation!;
            }

            // A real upward wheel cancels the production follow-latest state.
            // ChangeView and real wheel input only drive the visible ScrollViewer;
            // its production handlers must perform every page request without a business-method
            // fallback or a test-written keepLatest/loadingOlder state.
            capturePointerReceipts.Clear();
            Checkpoint("before_initial_latest");
            var initialLatestQuiet = 0;
            await Until(() =>
            {
                // Observe the product's automatic arrival at the latest row;
                // do not repair its initial scroll position from this scenario.
                var index = stream.Children.Count - 1;
                var row = index >= 0 ? stream.TryGetRealizedRow(index) : null;
                var visible = false;
                var observation = new JsonObject { ["source"] = "Passive observation before any history input",
                    ["vertical_offset"] = chatScroll.VerticalOffset, ["scrollable_height"] = chatScroll.ScrollableHeight,
                    ["viewport_height"] = chatScroll.ViewportHeight, ["keep_latest"] = keepLatest,
                    ["gap_dip"] = chatScroll.ScrollableHeight - chatScroll.VerticalOffset,
                    ["realized_row_index"] = index, ["row_realized"] = row is { IsLoaded: true, ActualHeight: > 0 } };
                if (row is { IsLoaded: true, ActualHeight: > 0 })
                {
                    var bounds = row.TransformToVisual(chatScroll).TransformBounds(new(0, 0, row.ActualWidth, row.ActualHeight));
                    visible = bounds.Bottom > 0 && bounds.Top < chatScroll.ViewportHeight;
                    observation["row_top"] = bounds.Top; observation["row_bottom"] = bounds.Bottom;
                }
                observation["row_visible"] = visible;
                diagnostics["initial_latest_observation"] = observation;
                initialLatestQuiet = keepLatest && visible && chatScroll.ViewportHeight > 0
                    && Math.Abs(chatScroll.ScrollableHeight - chatScroll.VerticalOffset) <= 1 ? initialLatestQuiet + 1 : 0;
                return initialLatestQuiet >= 2;
            }, "Production conversation did not automatically reach its latest row before history input");
            record["history_initial_latest"] = diagnostics["initial_latest_observation"]!.DeepClone();
            Checkpoint("initial_latest_ready");
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
                var beforeIds = MessageIds(); var beforePages = chatPages; var beforeViews = viewEvents; var beforeWheels = wheelEvents;
                expectedAnchorPage = beforePages; expectedReadingAnchor = null;
                var alreadyAtTop = chatScroll.VerticalOffset <= 1;
                if (alreadyAtTop)
                {
                    // At the upper boundary ChangeView(0) cannot emit a new
                    // position event. Exercise the real user's upward wheel.
                    await CaptureHover(chatScroll);
                    SendCaptureMouse(new CaptureMouseInput { Data = 120, Flags = 0x0800 });
                }
                else chatScroll.ChangeView(null, 0, null, true);
                await Until(() => chatPages > beforePages && !loadingOlder,
                    "History did not page through the production ScrollViewer input handlers");
                await WaitForMarkdown(); await PerformanceYield();
                if (keepLatest) throw new InvalidOperationException("History layout reactivated follow-latest without user end input");
                await Until(() => !stream.ReadingAnchorRestorePending,
                    "History did not finish restoring the real reading anchor");
                JsonObject anchorObservation;
                if (expectedReadingAnchor is { } expectedAnchor)
                {
                    var actualAnchor = stream.ReadAnchor(chatScroll, expectedAnchor.Key);
                    diagnostics["reading_anchor_comparison"] = new JsonObject { ["key"] = expectedAnchor.Key,
                        ["before_viewport_top"] = expectedAnchor.ViewportTop, ["after_viewport_top"] = actualAnchor?.ViewportTop,
                        ["page"] = chatPages };
                    if (actualAnchor is not { } restoredAnchor || Math.Abs(restoredAnchor.ViewportTop - expectedAnchor.ViewportTop) > 1)
                        throw new InvalidOperationException("History insertion moved the visible reading message: " + expectedAnchor.Key);
                    observedAnchorCases++;
                    anchorObservation = new JsonObject { ["observed"] = true, ["key"] = expectedAnchor.Key,
                        ["before_viewport_top"] = expectedAnchor.ViewportTop, ["after_viewport_top"] = restoredAnchor.ViewportTop,
                        ["source"] = "Actual old message during scroll or immediately before ItemsSource replacement" };
                }
                else anchorObservation = new JsonObject { ["observed"] = false,
                    ["reason"] = "No drawn message intersected the viewport before replacement; placeholders are not reading anchors" };
                expectedAnchorPage = -1;
                var afterIds = MessageIds();
                if (afterIds.Length <= beforeIds.Length || afterIds.Min() >= beforeIds.Min()
                    || (viewEvents <= beforeViews && wheelEvents <= beforeWheels))
                    throw new InvalidOperationException("Real history scroll did not add an older message page");
                pages.Add(new JsonObject { ["before_pages"] = beforePages, ["after_pages"] = chatPages,
                    ["before_oldest_id"] = beforeIds.Min(), ["after_oldest_id"] = afterIds.Min(),
                    ["messages_added"] = afterIds.Length - beforeIds.Length, ["view_changed_events"] = viewEvents - beforeViews,
                    ["upward_wheel_events"] = wheelEvents - beforeWheels,
                    ["reading_anchor"] = anchorObservation,
                    ["input"] = alreadyAtTop ? "Actual upward pointer wheel at the top boundary" : "ScrollViewer.ChangeView to the top" });
            }
            record["history_top"] = await Boundary(false);
            record["observed_reading_anchor_cases"] = observedAnchorCases;
            record["no_drawn_anchor_pages"] = pages.OfType<JsonObject>()
                .Count(page => page["reading_anchor"]?["observed"]?.GetValue<bool>() == false);
            // The four fixed history scenarios each require a real preservation
            // case. Random cold jumps may have no drawn old content to compare;
            // report that absence separately, never as a matched anchor.
            if (!record.Text("id").StartsWith("monkey-", StringComparison.Ordinal) && observedAnchorCases == 0)
                throw new InvalidOperationException("History scenario did not observe any real message position across page insertion");
            var ids = MessageIds();
            var oldest = ids.DefaultIfEmpty(0).Min();
            var expectedOldest = long.Parse(step.Text("first_message_id"));
            var fixture = performanceManifest!["fixture"].Rows("orgs").First(item => item.Text("id") == step.Text("org"));
            var expectedCount = int.Parse(fixture.Text("group_messages"));
            if (oldest != expectedOldest || ids.Length < expectedCount || (topEvents == 0 && topWheelEvents == 0))
                throw new InvalidOperationException($"History coverage mismatch: oldest={oldest}/{expectedOldest}, messages={ids.Length}/{expectedCount}, top view/wheel events={topEvents}/{topWheelEvents}");
            record["pages_loaded"] = chatPages; record["history_complete"] = !chatMore;
            record["oldest_message_id"] = oldest; record["message_count"] = ids.Length;
            record["expected_fixture_messages"] = expectedCount;
            record["upward_wheel_events"] = wheelEvents; record["top_view_changed_events"] = topEvents;
            record["top_upward_wheel_events"] = topWheelEvents;
            record["history_bottom"] = await Boundary(true);
            record["end_key_events"] = endKeyEvents;
            record["history_scroll_source"] = "Actual upward pointer wheel, ScrollViewer top input and actual End key; no direct page load or bottom repair";
        }
        catch (Exception error)
        {
            diagnostics["failure"] = error.ToString();
            Checkpoint("failure");
            diagnostics["failure_window_capture_started_unix_ms"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            try
            {
                var window = WinRT.Interop.WindowNative.GetWindowHandle(this);
                if (!WholeWindowGetRect(window, out var box))
                    throw new InvalidOperationException("Could not read the failed history window rectangle");
                var file = "history-" + record.Text("id") + "-failure.png";
                var capture = await CaptureWholeWindowPixels(System.IO.Path.Combine(PerformanceOutput, file),
                    box.right - box.left, box.bottom - box.top);
                capture["file"] = file;
                diagnostics["failure_window_capture"] = capture;
            }
            catch (Exception captureError) { diagnostics["failure_window_capture_error"] = captureError.ToString(); }
            finally { diagnostics["failure_window_capture_finished_unix_ms"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(); }
            throw;
        }
        finally
        {
            chatScroll.RemoveHandler(UIElement.PointerWheelChangedEvent, wheel);
            root.RemoveHandler(UIElement.PointerWheelChangedEvent, rootWheel);
            chatScroll.RemoveHandler(UIElement.KeyDownEvent, endKey);
            chatScroll.ViewChanged -= changed;
            stream.ItemsReplacing -= ObserveItemsReplacing;
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
        var phase = performanceManifest!.Text("phase");
        var pointerRandom = new Random(int.Parse(performanceManifest!.Text("seed")));
        async Task Execute(JsonNode step, bool random)
        {
            var kind = step.Text("kind");
            var target = step.Text("org") + step.Text("member") + step.Text("pane") + step.Text("name");
            var actionLabel = phase == "switch-chats" ? step.Flag("warmup") ? "switch-warmup:" + step.Text("id") : "switch:" + step.Text("switch_index")
                : phase == "open-every-chat" ? "open-every-chat:" + step.Text("id")
                : (random ? "monkey " : "") + kind + ": " + target;
            Volatile.Write(ref performanceAction, actionLabel);
            // The person profile's first 50 measured switches use about 30 MB
            // less than the later ones; record where the growth is.
            if (phase == "switch-chats" && !step.Flag("warmup") && int.TryParse(step.Text("switch_index"), out var switchIndex)
                && switchIndex % 25 == 0) PerformanceTrace.Memory(actionLabel);
            var clock = Stopwatch.StartNew(); var record = new JsonObject {
                ["id"] = random ? "monkey-" + randomActions : step.Text("id"), ["kind"] = kind, ["target"] = target,
                ["warmup"] = step.Flag("warmup"), ["switch_index"] = step["switch_index"]?.DeepClone(),
                ["started_unix_ms"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() };
            try
            {
            switch (kind)
            {
                case "organization":
                    if (!MeasuresChatOpening) throw new InvalidOperationException("Organization-row action belongs to the real-click phases");
                    await ExerciseOpenChat(step, record);
                    break;
                case "group":
                    if (MeasuresChatOpening) await ExerciseOpenChat(step, record);
                    else await Select(step.Text("org"));
                    break;
                case "private":
                    if (MeasuresChatOpening) await ExerciseOpenChat(step, record);
                    else await Select(step.Text("org"), step.Text("member"));
                    break;
                case "idle": await ExerciseIdle(step, record); break;
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
                        "protocols" => Details("protocols"), "overview" => OpenOrgOverview(),
                        _ => throw new InvalidOperationException("Unknown dialog") };
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
                    if (clicks == 0)
                    {
                        // Which title-bar rects Windows let through, against the
                        // button's own bounds (physical pixels).
                        var bounds = button.TransformToVisual(root).TransformBounds(new(0, 0, button.ActualWidth, button.ActualHeight));
                        var scale = root.XamlRoot.RasterizationScale;
                        var actual = titlebarInput?.GetRegionRects(Microsoft.UI.Input.NonClientRegionKind.Passthrough) ?? [];
                        record["titlebar_passthrough"] = new JsonArray(actual.Select(rect => (JsonNode)$"{rect.X},{rect.Y},{rect.Width},{rect.Height}").ToArray());
                        record["titlebar_cached"] = new JsonArray(titlebarInteractiveRects.Select(rect => (JsonNode)$"{rect.X},{rect.Y},{rect.Width},{rect.Height}").ToArray());
                        record["button_px"] = $"{bounds.X * scale:F0},{bounds.Y * scale:F0},{bounds.Width * scale:F0},{bounds.Height * scale:F0}";
                        throw new InvalidOperationException("Real random click was not handled: " + targetName);
                    }
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
            record["passed"] = true;
            }
            catch (Exception failure)
            {
                record["passed"] = false; record["error"] = failure.ToString();
                throw;
            }
            finally
            {
                record["elapsed_ms"] = clock.Elapsed.TotalMilliseconds;
                record["finished_unix_ms"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
                record["realized_chat_rows"] = stream.Realized;
                actions.Add(record);
                // Preserve completed and failed action evidence even if the
                // external watchdog stops a later action in this phase.
                await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(PerformanceOutput, "performance-actions.json"),
                    JsonSerializer.Serialize(new { phase, actions, errors, random_seconds = randomSeconds, random_actions = randomActions }));
            }
        }
        try
        {
            await WaitForMarkdown();
            foreach (var step in performanceManifest!.Rows("plan"))
            {
                try { await Execute(step!, false); }
                catch (Exception failure)
                {
                    errors.Add(step.Text("id") + ": " + failure);
                    // Separate phases run in separate owned processes. Within
                    // chat opening, retain every reachable click's result too.
                    if (!MeasuresChatOpening) throw;
                }
            }
            // After the measured switches only; its samples carry their own
            // action name, so no switch block includes them.
            if (phase == "switch-chats")
            {
                try { await ProbeNativeLeaks(); }
                catch (Exception failure) { PerformanceTrace.Note("leak.probe.error", failure.ToString()); }
            }
            if (phase.Length == 0 || phase == "monkey")
            {
            var deck = performanceManifest.Rows("monkey");
            var timer = Stopwatch.StartNew();
            while (timer.Elapsed.TotalSeconds < int.Parse(performanceManifest.Text("seconds")))
            {
                await Execute(deck[randomActions % deck.Count]!, true);
                randomActions++; await Task.Delay(100);
            }
            randomSeconds = timer.Elapsed.TotalSeconds;
            }
        }
        catch (Exception ex) { errors.Add(ex.ToString()); }
        finally
        {
            performanceCancellation!.Cancel();
            try { await performanceProbe!; } catch (OperationCanceledException) { }
            await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(PerformanceOutput, "performance-complete.json"),
                JsonSerializer.Serialize(new { phase, actions, errors, max_ui_stall_ms = Interlocked.Read(ref performanceWorstTicks) * 1000d / Stopwatch.Frequency,
                    titlebar_layout_notifications = titlebarLayoutNotifications, titlebar_layout_measurements = titlebarLayoutMeasurements,
                    random_seconds = randomSeconds, random_actions = randomActions, seed = int.Parse(performanceManifest!.Text("seed")) }));
        }
    }
}
