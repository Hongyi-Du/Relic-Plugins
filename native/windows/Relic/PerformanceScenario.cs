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
            void Write(string name, object value)
            {
                var path = System.IO.Path.Combine(PerformanceOutput, name);
                System.IO.File.WriteAllText(path + ".tmp", JsonSerializer.Serialize(value));
                System.IO.File.Move(path + ".tmp", path, true);
            }
            Write("performance-ready.json", new { pid = Environment.ProcessId, unix_ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() });
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
                    if (completed.Task.IsCompletedSuccessfully) pings++;
                    Write("heartbeat.json", new { unix_ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), sequence = ++sequence, pings,
                        max_ui_stall_ms = Interlocked.Read(ref performanceWorstTicks) * 1000d / Stopwatch.Frequency,
                        pending_since_unix_ms = completed.Task.IsCompletedSuccessfully ? 0 : pendingSince,
                        action = Volatile.Read(ref performanceAction) });
                    foreach (var timing in PerformanceTrace.Drain())
                        System.IO.File.AppendAllText(System.IO.Path.Combine(PerformanceOutput, "timings.jsonl"), JsonSerializer.Serialize(timing) + "\n");
                    if (completed.Task.IsCompletedSuccessfully) break;
                }
                await Task.Delay(40, token);
            }
        }, token);
    }

    private async Task PerformanceYield()
    {
        var tick = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        DispatcherQueue.TryEnqueue(DispatcherQueuePriority.Low, () => tick.SetResult());
        await tick.Task;
        await Task.Delay(60);
    }

    private async Task RunPerformanceScenario()
    {
        var actions = new List<JsonObject>(); var errors = new List<string>();
        var randomActions = 0; double randomSeconds = 0;
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
                        "neworg" => CreateOrg(), "member" => AddMember(), _ => throw new InvalidOperationException("Unknown dialog") };
                    for (var attempt = 0; visibleDialog == null && !dialog.IsCompleted && attempt < 100; attempt++) await Task.Delay(20);
                    if (visibleDialog == null) { await dialog; throw new InvalidOperationException("Production dialog did not open"); }
                    await WaitForMarkdown(); await PerformanceYield(); visibleDialog.Hide(); await dialog; break;
                case "scroll-history":
                    await Select(step.Text("org"));
                    while (chatMore)
                    {
                        var before = messages.Count;
                        chatScroll.ChangeView(null, 0, null, true);
                        await PerformanceYield();
                        while (loadingOlder) await Task.Delay(20);
                        if (messages.Count == before && chatMore) await LoadOlderMessages();
                        await WaitForMarkdown();
                        if (messages.Count <= before && chatMore) throw new InvalidOperationException("History pagination did not progress");
                    }
                    record["pages_loaded"] = chatPages; record["history_complete"] = !chatMore;
                    record["oldest_message_id"] = messages.Where(row => row.Text("type") == "message")
                        .Select(row => long.TryParse(row.Text("id"), out var id) ? id : long.MaxValue).DefaultIfEmpty(0).Min();
                    ScrollToLatest(); break;
                default: throw new InvalidOperationException("Unknown performance action: " + kind);
            }
            await PerformanceYield(); await WaitForMarkdown();
            if (random)
            {
                // Exercise actual pointer/hover/routed click paths as well as
                // the seeded production command deck, without destructive acts.
                SetForegroundWindow(WinRT.Interop.WindowNative.GetWindowHandle(this));
                var wasOpen = sideOpen; capturePointerReceipts.Clear();
                await CaptureClick((FrameworkElement)navigationButtons.Children[1]); await PerformanceYield();
                if (sideOpen == wasOpen) throw new InvalidOperationException("Real sidebar click was not handled");
                await CaptureClick((FrameworkElement)navigationButtons.Children[1]); await PerformanceYield();
                if (sideOpen != wasOpen) throw new InvalidOperationException("Real sidebar second click was not handled");
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
                    random_seconds = randomSeconds, random_actions = randomActions, seed = int.Parse(performanceManifest!.Text("seed")) }));
        }
    }
}
