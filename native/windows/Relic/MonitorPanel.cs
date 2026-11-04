using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Relic.Core;
using System.Globalization;
using System.Text.Json.Nodes;

namespace Relic;

// The monitor (toolbar): who is working on this computer and what it costs, from the Relic App's /api/monitor; Stop
// and Resume for one session or all of them; and the token statistics by session, agent or organization from
// /api/usage, drawn as per-period stacked bars and cumulative lines.
public sealed partial class MainWindow
{
    private JsonNode monitorData = new JsonObject();
    private JsonNode usageData = new JsonObject();
    private long monitorReadAt, stopAllArmedAt;
    private bool monitorTimerWired;
    private readonly DispatcherTimer monitorTimer = new() { Interval = TimeSpan.FromSeconds(5) };
    private StackPanel? monitorLive, monitorUsage;
    private string usageSpan = "7d", usageGroup = "agent", usageOrg = "", usageAgent = "";
    private const int ChartSeries = 7;  // named series in a chart; the rest are summed into one gray series
    private static readonly (string Light, string Dark)[] seriesColors =
    [
        ("2A78D6", "3987E5"), ("EB6834", "D95926"), ("1BAF7A", "199E70"), ("EDA100", "C98500"),
        ("E87BA4", "D55181"), ("008300", "008300"), ("6250D6", "9085E9"), ("8F8C86", "8A877F")
    ];

    private static double Num(JsonNode? node, string key) =>
        double.TryParse(node.Text(key), NumberStyles.Float, CultureInfo.InvariantCulture, out var value) ? value : 0;

    private int MonitorWorking => monitorData.Rows("agents").Concat(monitorData.Rows("others"))
        .Count(agent => agent.Flag("working") && !(agent?["stopped"] is JsonObject stopped && !stopped.Flag("released")));

    // The toolbar count follows the refreshes that already run while members work (each change of an organization
    // announces itself), at most every 15 s. An idle app reads nothing; an older Relic App without the monitor leaves
    // the button quiet.
    private void MonitorTick()
    {
        if (api == null || closing || Environment.TickCount64 - monitorReadAt < 15000) return;
        monitorReadAt = Environment.TickCount64;
        _ = ReadMonitor();
    }
    private Task ReadMonitorNow() { monitorReadAt = Environment.TickCount64; return ReadMonitor(); }
    private async Task ReadMonitor()
    {
        if (api == null) return;
        try
        {
            var data = await api.Get("/api/monitor", lifetime.Token);
            var before = MonitorWorking;
            monitorData = data;
            if (MonitorWorking != before) DrawToolbar();
            if (monitorLive != null) DrawMonitor();
        }
        catch (Exception) { }
    }

    private async Task OpenMonitor()
    {
        if (api == null) return;
        if (!monitorTimerWired)
        {
            monitorTimerWired = true;
            monitorTimer.Tick += (_, _) => { if (monitorLive != null) _ = ReadMonitorNow(); };
        }
        var panel = new StackPanel { Spacing = 18 };
        monitorLive = new StackPanel { Spacing = 10 };
        monitorUsage = new StackPanel { Spacing = 10 };
        panel.Children.Add(monitorLive);
        panel.Children.Add(monitorUsage);
        DrawMonitor();
        DrawUsage();
        monitorTimer.Start();
        _ = ReadMonitorNow();
        _ = ReadUsage();
        try { await Show(T("mon.title"), panel, 900); }
        finally { monitorTimer.Stop(); monitorLive = null; monitorUsage = null; }
    }

    private string FormatTokens(double n)
    {
        n = Math.Round(Math.Max(0, n));
        var invariant = CultureInfo.InvariantCulture;
        if (words.Language.StartsWith("zh", StringComparison.OrdinalIgnoreCase))
        {
            if (n >= 1e8) return (n / 1e8).ToString(n >= 1e10 ? "0" : "0.#", invariant) + T("mon.unit_1e8");
            if (n >= 1e4) return (n / 1e4).ToString(n >= 1e6 ? "0" : "0.#", invariant) + T("mon.unit_1e4");
            return n.ToString("0", invariant);
        }
        if (n >= 1e9) return (n / 1e9).ToString("0.#", invariant) + "B";
        if (n >= 1e6) return (n / 1e6).ToString("0.#", invariant) + "M";
        if (n >= 1e3) return (n / 1e3).ToString("0.#", invariant) + "K";
        return n.ToString("0", invariant);
    }
    private string Ago(double epochSeconds)
    {
        var seconds = Math.Max(0, DateTimeOffset.UtcNow.ToUnixTimeSeconds() - epochSeconds);
        if (seconds < 60) return T("time.just_now");
        if (seconds < 3600) return T("time.minutes_ago", ("n", (int)(seconds / 60)));
        return T("time.hours_ago", ("n", (int)(seconds / 3600)));
    }

    // ---------------- who is working ----------------
    private void DrawMonitor()
    {
        var live = monitorLive;
        if (live == null) return;
        live.Children.Clear();
        live.Children.Add(Quiet(T("mon.intro"), 12.5));
        var totals = monitorData["totals"];
        var cards = new Grid { ColumnSpacing = 12 };
        cards.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        cards.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        var claude = MonitorTotal("Claude", totals?["claude"], null);
        var codex = MonitorTotal("Codex", totals?["codex"], monitorData["plans"]?["codex"]);
        Grid.SetColumn(codex, 1);
        cards.Children.Add(claude); cards.Children.Add(codex);
        live.Children.Add(cards);
        var agents = monitorData.Rows("agents"); var others = monitorData.Rows("others");
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        var armed = Environment.TickCount64 - stopAllArmedAt < 4000;
        actions.Children.Add(Button(T(armed ? "mon.stop_all_sure" : "mon.stop_all"), MonitorStopAll));
        if (monitorData["stopped_all"] is JsonObject || agents.Concat(others).Any(agent => agent?["stopped"] is JsonObject))
            actions.Children.Add(Button(T("mon.resume_all"), MonitorResumeAll));
        live.Children.Add(actions);
        live.Children.Add(Heading(T("mon.relic_agents"), 14));
        if (agents.Count == 0) live.Children.Add(Quiet(T("mon.no_agents")));
        foreach (var agent in agents) live.Children.Add(MonitorRow(agent));
        if (others.Count > 0)
        {
            live.Children.Add(Heading(T("mon.other_sessions"), 14));
            live.Children.Add(Quiet(T("mon.other_hint")));
            foreach (var agent in others) live.Children.Add(MonitorRow(agent));
        }
        MonitorSchedules(live);
    }

    private Border MonitorTotal(string name, JsonNode? totals, JsonNode? plan)
    {
        var body = new StackPanel { Spacing = 4 };
        var working = (int)Num(totals, "working");
        body.Children.Add(TwoColumns(Heading(name, 14), Quiet(working > 0 ? T("mon.n_working", ("n", working)) : T("mon.none_working"))));
        var big = Text(FormatTokens(Num(totals, "five_hours")), 22); big.FontWeight = FontWeights.SemiBold;
        body.Children.Add(big);
        body.Children.Add(Quiet(T("mon.in_five_hours")));
        var rate = Num(totals, "rate");
        body.Children.Add(Quiet(T("mon.hour_day", ("hour", FormatTokens(Num(totals, "hour"))), ("day", FormatTokens(Num(totals, "day"))))
            + (rate > 0 ? " · " + T("mon.rate", ("n", FormatTokens(rate))) : "")));
        if (plan is JsonObject) body.Children.Add(Quiet(PlanLine(plan)));
        else if (name == "Claude") body.Children.Add(Quiet(T("mon.claude_plan_hint")));
        return Card(body);
    }

    private string PlanLine(JsonNode plan)
    {
        var parts = new List<string>();
        foreach (var window in new[] { plan["primary"], plan["secondary"] })
        {
            if (window is not JsonObject) continue;
            var minutes = Num(window, "window_minutes");
            var name = minutes == 300 ? T("mon.window_5h") : minutes == 10080 ? T("mon.window_week")
                : T("mon.window_hours", ("n", (int)Math.Round(minutes / 60)));
            var reset = Num(window, "resets_at");
            var when = reset > 0 ? DateTimeOffset.FromUnixTimeSeconds((long)reset).ToLocalTime().ToString("M/d HH:mm", CultureInfo.InvariantCulture) : "";
            parts.Add(T("mon.plan_used", ("window", name), ("pct", (int)Math.Round(Num(window, "used_percent"))), ("reset", when)));
        }
        return string.Join(" · ", parts);
    }

    private UIElement MonitorRow(JsonNode? agent)
    {
        var stopped = agent?["stopped"] as JsonObject;
        var state = stopped != null ? (stopped.Flag("released") ? "released" : "stopped") : agent.Flag("working") ? "working" : "idle";
        var row = new Grid
        {
            ColumnSpacing = 12, Padding = new Thickness(10, 8, 10, 8), CornerRadius = new CornerRadius(10),
            BorderThickness = new Thickness(1), BorderBrush = state == "working" ? Accent : Line
        };
        row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        var color = state switch
        {
            "working" => Paint("1E8E3E", "4CC26A"), "stopped" => Paint("C9372C", "E66767"),
            "released" => Paint("B26A00", "E0A030"), _ => Paint("B4B2A9", "5F5E5A")
        };
        row.Children.Add(new Microsoft.UI.Xaml.Shapes.Ellipse
        {
            Width = 9, Height = 9, Fill = color, VerticalAlignment = VerticalAlignment.Top, Margin = new Thickness(0, 6, 0, 0)
        });
        var main = new StackPanel { Spacing = 3 };
        var heading = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        var title = Heading(agent.Text("title"), 13.5); title.TextWrapping = TextWrapping.NoWrap; title.TextTrimming = TextTrimming.CharacterEllipsis;
        heading.Children.Add(title);
        heading.Children.Add(Badge(agent.Text("harness") == "codex" ? "Codex" : "Claude"));
        heading.Children.Add(Quiet(state switch
        {
            "working" => T("mon.state_working"), "stopped" => T("mon.state_stopped"),
            "released" => T("mon.state_released"), _ => T("mon.state_idle")
        }));
        main.Children.Add(heading);
        var seats = agent.Rows("seats");
        if (seats.Count > 0) main.Children.Add(Quiet(string.Join("   ", seats.Select(seat => seat.Text("org_name") + " · " + seat.Text("member")))));
        var meta = new List<string>();
        var last = Num(agent, "last_active");
        if (last > 0) meta.Add(T("mon.last_active", ("when", Ago(last))));
        var rate = Num(agent, "rate");
        if (rate > 0) meta.Add(T("mon.rate", ("n", FormatTokens(rate))));
        var subagents = (int)Num(agent, "subagents");
        if (subagents > 0) meta.Add(T("mon.subagents", ("n", subagents)));
        var automations = agent.Rows("automations").Count;
        if (automations > 0) meta.Add(T("mon.automations", ("n", automations)));
        if (seats.Any(seat => !seat.Flag("auto_wake") || !seat.Flag("org_auto_wake"))) meta.Add(T("mon.wake_off"));
        if (meta.Count > 0) main.Children.Add(Quiet(string.Join(" · ", meta)));
        if (state == "working" && !agent.Flag("can_interrupt")) main.Children.Add(Quiet(T("mon.codex_note")));
        if (state == "stopped") main.Children.Add(Quiet(T("mon.stopped_note")));
        Grid.SetColumn(main, 1); row.Children.Add(main);
        var tokens = new Grid { ColumnSpacing = 14, VerticalAlignment = VerticalAlignment.Center };
        var spans = new[] { ("hour", T("mon.span_hour")), ("five_hours", T("mon.span_five_hours")), ("day", T("mon.span_day")) };
        for (var i = 0; i < spans.Length; i++)
        {
            tokens.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
            var cell = new StackPanel { HorizontalAlignment = HorizontalAlignment.Right };
            var caption = Quiet(spans[i].Item2, 11); caption.HorizontalAlignment = HorizontalAlignment.Right;
            cell.Children.Add(caption);
            var value = Heading(FormatTokens(Num(agent?["tokens"]?[spans[i].Item1], "total")), 13); value.HorizontalAlignment = HorizontalAlignment.Right;
            cell.Children.Add(value);
            Grid.SetColumn(cell, i); tokens.Children.Add(cell);
        }
        Grid.SetColumn(tokens, 2); row.Children.Add(tokens);
        var key = agent.Text("key");
        var action = stopped != null ? Button(T("mon.resume"), () => MonitorAction("resume", key))
            : Button(T("mon.stop"), () => MonitorAction("stop", key));
        action.VerticalAlignment = VerticalAlignment.Center;
        Grid.SetColumn(action, 3); row.Children.Add(action);
        return row;
    }

    private void MonitorSchedules(StackPanel live)
    {
        live.Children.Add(Heading(T("mon.schedules"), 14));
        live.Children.Add(Quiet(T("mon.schedules_hint")));
        var automations = monitorData.Rows("automations");
        var on = automations.Count(automation => automation.Text("status") != "PAUSED");
        live.Children.Add(Text(T("mon.codex_automations", ("on", on), ("n", automations.Count)), 13));
        foreach (var automation in automations)
            live.Children.Add(Quiet((automation.Text("status") == "PAUSED" ? T("mon.paused") : T("mon.active"))
                + " · " + automation.Text("name") + " · " + automation.Text("rrule")));
        var orgs = monitorData.Rows("orgs");
        var awake = orgs.Where(o => o.Flag("auto_wake")).Select(o => o.Text("name")).ToList();
        var asleep = orgs.Where(o => !o.Flag("auto_wake")).Select(o => o.Text("name")).ToList();
        if (awake.Count > 0) live.Children.Add(Quiet(T("mon.org_wake_on", ("names", words.List(awake)))));
        if (asleep.Count > 0) live.Children.Add(Quiet(T("mon.org_wake_off", ("names", words.List(asleep)))));
        var tasks = monitorData.Rows("claude_tasks").Count;
        if (tasks > 0) live.Children.Add(Quiet(T("mon.claude_tasks", ("n", tasks))));
    }

    private async Task MonitorAction(string action, string key)
    {
        var result = await api!.Post("/api/monitor/" + action, new { key });
        Note(action == "stop"
            ? T("mon.stopped_one", ("killed", result.Rows("killed").Count), ("wake", result.Rows("wake_off").Count),
                ("autos", (result["paused"] as JsonObject)?.Count ?? 0))
            : T("mon.resumed"));
        await ReadMonitorNow();
    }
    private async Task MonitorStopAll()
    {
        if (Environment.TickCount64 - stopAllArmedAt > 4000) { stopAllArmedAt = Environment.TickCount64; DrawMonitor(); return; }
        stopAllArmedAt = 0;
        var result = await api!.Post("/api/monitor/stop", new { all = true });
        Note(T("mon.stopped_all", ("n", result.Rows("stopped").Count), ("orgs", result.Rows("orgs").Count), ("autos", result.Rows("paused").Count)));
        await ReadMonitorNow();
    }
    private async Task MonitorResumeAll()
    {
        await api!.Post("/api/monitor/resume", new { all = true });
        Note(T("mon.resumed_all"));
        await ReadMonitorNow();
    }

    // ---------------- token statistics ----------------
    private async Task ReadUsage()
    {
        if (api == null) return;
        var path = "/api/usage?span=" + usageSpan + "&group=" + usageGroup
            + (usageOrg.Length > 0 ? "&org=" + Client.Segment(usageOrg) : "")
            + (usageAgent.Length > 0 ? "&agent=" + Client.Segment(usageAgent) : "");
        try { usageData = await api.Get(path, lifetime.Token); }
        catch (Exception) { usageData = new JsonObject { ["failed"] = true }; }
        DrawUsage();
    }

    private ComboBox UsageChoice(IEnumerable<(string Value, string Label)> choices, string current, Action<string> set)
    {
        var box = new ComboBox { MinWidth = 120 };
        var values = new List<string>();
        foreach (var (value, label) in choices) { box.Items.Add(label); values.Add(value); }
        box.SelectedIndex = Math.Max(0, values.IndexOf(current));
        box.SelectionChanged += (_, _) =>
        {
            var index = box.SelectedIndex;
            if (index < 0 || index >= values.Count || values[index] == current) return;
            set(values[index]);
            _ = ReadUsage();
        };
        return box;
    }

    private string SeriesName(JsonNode? series)
    {
        if (series.Text("key") == "*") return T("mon.other_series", ("n", (int)Num(series, "count")));
        var label = series.Text("label");
        return label.Length > 0 ? label : T("mon.unseated");
    }

    private void DrawUsage()
    {
        var section = monitorUsage;
        if (section == null) return;
        section.Children.Clear();
        section.Children.Add(Heading(T("mon.usage"), 16));
        var filters = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        filters.Children.Add(UsageChoice(new[] { ("today", T("mon.span_today")), ("24h", T("mon.span_24h")), ("7d", T("mon.span_7d")),
            ("30d", T("mon.span_30d")), ("90d", T("mon.span_90d")) }, usageSpan, value => usageSpan = value));
        filters.Children.Add(UsageChoice(new[] { ("session", T("mon.by_session")), ("agent", T("mon.by_agent")), ("org", T("mon.by_org")) },
            usageGroup, value => usageGroup = value));
        var orgChoices = new List<(string, string)> { ("", T("mon.all_orgs")) };
        foreach (var o in usageData["filters"].Rows("orgs")) orgChoices.Add((o.Text("id"), o.Text("name")));
        orgChoices.Add(("-", T("mon.unseated")));
        filters.Children.Add(UsageChoice(orgChoices, usageOrg, value => { usageOrg = value; usageAgent = ""; }));
        var agentChoices = new List<(string, string)> { ("", T("mon.all_agents")) };
        foreach (var a in usageData["filters"].Rows("agents"))
            if (usageOrg.Length == 0 || usageOrg == "-" || a.Text("org") == usageOrg) agentChoices.Add((a.Text("key"), a.Text("label")));
        filters.Children.Add(UsageChoice(agentChoices, usageAgent, value => usageAgent = value));
        section.Children.Add(filters);
        var starts = usageData.Rows("starts").Select(start => Num(start, "")).ToList();
        if (starts.Count == 0)
        {
            section.Children.Add(Quiet(usageData.Flag("failed") || usageData["span"] != null ? T("mon.usage_none") : T("common.loading")));
            return;
        }
        section.Children.Add(Text(T("mon.usage_total", ("n", FormatTokens(Num(usageData, "total")))), 13));
        var hourly = usageData.Text("bucket") == "hour";
        var labels = starts.Select(start => DateTimeOffset.FromUnixTimeSeconds((long)start).ToLocalTime()
            .ToString(hourly ? "HH" : "M/d", CultureInfo.InvariantCulture)).ToList();
        var series = usageData.Rows("series").ToList();
        var lines = new List<(string Name, double[] Values, double Total, Brush Color)>();
        double[] Fit(JsonNode? s)
        {
            var values = new double[labels.Count];
            var raw = s.Rows("values");
            for (var i = 0; i < Math.Min(values.Length, raw.Count); i++) values[i] = Num(raw[i], "");
            return values;
        }
        foreach (var s in series.Take(ChartSeries))
            lines.Add((SeriesName(s), Fit(s), Num(s?["total"], "total"), Paint(seriesColors[lines.Count].Light, seriesColors[lines.Count].Dark)));
        var rest = series.Skip(ChartSeries).ToList();
        if (rest.Count > 0)
        {
            var sum = new double[labels.Count];
            double restTotal = 0; var count = 0;
            foreach (var s in rest)
            {
                var values = Fit(s);
                for (var i = 0; i < sum.Length; i++) sum[i] += values[i];
                restTotal += Num(s?["total"], "total");
                count += s.Text("key") == "*" ? (int)Num(s, "count") : 1;
            }
            lines.Add((T("mon.other_series", ("n", count)), sum, restTotal, Paint(seriesColors[^1].Light, seriesColors[^1].Dark)));
        }
        section.Children.Add(Quiet(T("mon.chart_bars"), 12));
        section.Children.Add(StackedBars(labels, lines));
        section.Children.Add(Quiet(T("mon.chart_lines"), 12));
        section.Children.Add(CumulativeLines(labels, lines));
        var legend = new StackPanel { Spacing = 4 };
        foreach (var line in lines)
        {
            var item = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
            item.Children.Add(new Border { Width = 10, Height = 10, CornerRadius = new CornerRadius(2), Background = line.Color, VerticalAlignment = VerticalAlignment.Center });
            item.Children.Add(Text(line.Name + "  " + FormatTokens(line.Total), 12.5));
            legend.Children.Add(item);
        }
        section.Children.Add(legend);
    }

    private void ChartAxes(Canvas canvas, double left, double top, double width, double height, double max)
    {
        foreach (var fraction in new[] { 0.0, 0.5, 1.0 })
        {
            var y = top + height * (1 - fraction);
            canvas.Children.Add(new Microsoft.UI.Xaml.Shapes.Line { X1 = left, X2 = left + width, Y1 = y, Y2 = y, Stroke = Line, StrokeThickness = 1 });
            var label = Quiet(FormatTokens(max * fraction), 11);
            label.Width = left - 8; label.TextAlignment = TextAlignment.Right;
            Canvas.SetLeft(label, 0); Canvas.SetTop(label, y - 8); canvas.Children.Add(label);
        }
    }
    private void ChartLabels(Canvas canvas, IReadOnlyList<string> labels, double left, double y, double slot)
    {
        var step = Math.Max(1, (int)Math.Ceiling(labels.Count / 8.0));
        for (var i = 0; i < labels.Count; i += step)
        {
            var label = Quiet(labels[i], 11); label.Width = Math.Max(slot * step, 32); label.TextAlignment = TextAlignment.Center;
            Canvas.SetLeft(label, left + slot * i + slot / 2 - label.Width / 2); Canvas.SetTop(label, y); canvas.Children.Add(label);
        }
    }

    private FrameworkElement StackedBars(IReadOnlyList<string> labels, IReadOnlyList<(string Name, double[] Values, double Total, Brush Color)> lines)
    {
        const double height = 210, left = 64, bottom = 22, top = 8;
        var canvas = new Canvas { Height = height, HorizontalAlignment = HorizontalAlignment.Stretch };
        void Draw()
        {
            canvas.Children.Clear();
            var width = canvas.ActualWidth; var n = labels.Count;
            if (width <= 0 || n == 0) return;
            var totals = new double[n];
            foreach (var line in lines) for (var i = 0; i < n; i++) totals[i] += line.Values[i];
            var max = Math.Max(1, totals.Max());
            var plotWidth = Math.Max(10, width - left - 6); var plotHeight = height - bottom - top;
            ChartAxes(canvas, left, top, plotWidth, plotHeight, max);
            var slot = plotWidth / n; var bar = Math.Max(2, Math.Min(24, slot * 0.6));
            for (var i = 0; i < n; i++)
            {
                var x = left + slot * i + (slot - bar) / 2; var y = top + plotHeight;
                foreach (var line in lines)
                {
                    if (line.Values[i] <= 0) continue;
                    var h = plotHeight * line.Values[i] / max;
                    var rect = new Microsoft.UI.Xaml.Shapes.Rectangle { Width = bar, Height = Math.Max(0.5, h), Fill = line.Color };
                    Canvas.SetLeft(rect, x); Canvas.SetTop(rect, y - h); canvas.Children.Add(rect);
                    y -= h;
                }
            }
            ChartLabels(canvas, labels, left, top + plotHeight + 4, slot);
        }
        canvas.SizeChanged += (_, _) => Draw();
        canvas.Loaded += (_, _) => Draw();
        return canvas;
    }

    private FrameworkElement CumulativeLines(IReadOnlyList<string> labels, IReadOnlyList<(string Name, double[] Values, double Total, Brush Color)> lines)
    {
        const double height = 210, left = 64, bottom = 22, top = 8;
        var canvas = new Canvas { Height = height, HorizontalAlignment = HorizontalAlignment.Stretch };
        void Draw()
        {
            canvas.Children.Clear();
            var width = canvas.ActualWidth; var n = labels.Count;
            if (width <= 0 || n == 0 || lines.Count == 0) return;
            var running = lines.Select(line => { double sum = 0; return line.Values.Select(v => sum += v).ToArray(); }).ToList();
            var max = Math.Max(1, running.Max(values => values.Length > 0 ? values[^1] : 0));
            var plotWidth = Math.Max(10, width - left - 6); var plotHeight = height - bottom - top;
            ChartAxes(canvas, left, top, plotWidth, plotHeight, max);
            var slot = plotWidth / n;
            for (var s = 0; s < lines.Count; s++)
            {
                var points = new PointCollection();
                for (var i = 0; i < n && i < running[s].Length; i++)
                    points.Add(new Windows.Foundation.Point(left + slot * i + slot / 2, top + plotHeight * (1 - running[s][i] / max)));
                var polyline = new Microsoft.UI.Xaml.Shapes.Polyline
                {
                    Points = points, Stroke = lines[s].Color, StrokeThickness = 2, StrokeLineJoin = PenLineJoin.Round
                };
                if (s % 2 == 1) polyline.StrokeDashArray = new DoubleCollection { 5, 3 };
                canvas.Children.Add(polyline);
            }
            ChartLabels(canvas, labels, left, top + plotHeight + 4, slot);
        }
        canvas.SizeChanged += (_, _) => Draw();
        canvas.Loaded += (_, _) => Draw();
        return canvas;
    }
}
