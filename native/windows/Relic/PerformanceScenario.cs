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
        var actions = new List<object>(); var errors = new List<string>();
        var randomActions = 0; double randomSeconds = 0;
        async Task Action(string kind, string target, Func<Task> operation)
        {
            Volatile.Write(ref performanceAction, kind + ": " + target);
            var clock = Stopwatch.StartNew();
            await operation(); await PerformanceYield();
            if (error.IsOpen) throw new InvalidOperationException(error.Message);
            actions.Add(new { kind, target, elapsed_ms = clock.Elapsed.TotalMilliseconds, passed = true });
        }
        Task Menu()
        {
            var entry = nativeMenus.First();
            entry.Flyout.ShowAt(entry.Anchor);
            return Task.Delay(80).ContinueWith(_ => DispatcherQueue.TryEnqueue(() => entry.Flyout.Hide()));
        }
        async Task Dialog()
        {
            var task = Settings(); await Task.Delay(100);
            if (visibleDialog == null) throw new InvalidOperationException("Settings dialog did not open");
            visibleDialog.Hide(); await task;
        }
        async Task Resize(int width)
        {
            var monitor = CurrentWindowMonitor();
            AppWindow.Resize(new(WindowSizing.Pixels(width, monitor.Scale), WindowSizing.Pixels(700, monitor.Scale)));
            await PerformanceYield();
        }
        async Task ScrollTop()
        {
            chatScroll.ChangeView(null, 0, null, true); await PerformanceYield();
            if (chatMore) await LoadOlderMessages();
        }
        try
        {
            var organizations = performanceManifest!["fixture"].Rows("orgs");
            foreach (var organization in organizations)
            {
                var id = organization.Text("id");
                await Action("organization", id, () => Select(id));
                foreach (var person in organization.Rows("members"))
                {
                    var name = person.Text();
                    await Action("private-chat", id + "/" + name, () => Select(id, name));
                }
                await Action("group-chat", id, () => Select(id));
                foreach (var tab in new[] { "overview", "workspace", "files" }) await Action("pane", tab, () => SetPane(tab));
                await Action("pane", "overview", () => SetPane("overview"));
                await Action("menu", "File", Menu);
                await Action("dialog", "Settings", Dialog);
                foreach (var width in new[] { 1440, 1180, 1024, 960, 1440 }) await Action("resize", width.ToString(), () => Resize(width));
                await Action("scroll-history", id, ScrollTop);
            }
            var random = new Random(int.Parse(performanceManifest.Text("seed")));
            var seconds = int.Parse(performanceManifest.Text("seconds"));
            var timer = Stopwatch.StartNew();
            while (timer.Elapsed.TotalSeconds < seconds)
            {
                var organization = organizations[random.Next(organizations.Count)]!;
                switch (random.Next(8))
                {
                    case 0: await Action("random-group", organization.Text("id"), () => Select(organization.Text("id"))); break;
                    case 1:
                        var people = organization.Rows("members"); var name = people[random.Next(people.Count)].Text();
                        await Action("random-private", name, () => Select(organization.Text("id"), name)); break;
                    case 2: await Action("random-pane", "overview", () => SetPane("overview")); break;
                    case 3: await Action("random-sidebar", "toggle", ToggleSide); break;
                    case 4: await Action("random-inspector", "toggle", TogglePanel); break;
                    case 5: await Action("random-menu", "File", Menu); break;
                    case 6: await Action("random-resize", "breakpoints", () => Resize(new[] { 960, 1024, 1180, 1440 }[random.Next(4)])); break;
                    case 7: await Action("random-scroll", "history", ScrollTop); break;
                }
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
