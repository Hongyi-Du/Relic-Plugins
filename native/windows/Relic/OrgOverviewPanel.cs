using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Relic.Core;
using System.Globalization;
using System.Text.Json.Nodes;

namespace Relic;

// The overview (toolbar): every organization on one page, in the order of the organization tree, from the Relic App's
// /api/overview: what each one is doing, its open tasks, who is working, and what can start its members on their own
// (auto-wake, Codex automations, the Claude app's scheduled tasks). The person adjusts from here: auto-wake for an
// organization or a seat, pausing or resuming an automation, stopping or resuming a member's session (the monitor's
// Stop and Resume), and opening a chat. Refreshes every 5 s while open; reads nothing while closed.
//
// Each card is a run of rows in a VirtualRows list (its header, what it does, each task, each member, its end), built
// only around the view (CI measured 255-460 ms when every expanded card was built at once, and keeping every row
// built or realized made a full UI Automation read hold the UI thread for half a second). A row's key is "<which
// row>|<what it shows>": the list remembers each row's built height by the first part and lays rows out at those
// heights (KnownHeights), so the list's height does not depend on which rows are realized, a row a refresh
// replaces keeps its height while it is built, and a refresh replaces only the rows whose content changed. At the
// bottom the view holds its bottom edge; elsewhere the first visible row keeps its place. Times are clock times, so
// a row does not change just because a minute passed.
public sealed partial class MainWindow
{
    private JsonNode orgOverviewData = new JsonObject();
    private string orgOverviewDrawn = "", orgOverviewLatest = "", orgOverviewError = "", orgOverviewArmed = "";
    private long orgOverviewDrawnAt, orgOverviewArmedAt;
    private bool orgOverviewTimerWired, orgOverviewPointerOver, orgOverviewPending;
    private readonly DispatcherTimer orgOverviewTimer = new() { Interval = TimeSpan.FromSeconds(5) };
    private VirtualRows? orgOverviewBody;
    private readonly Dictionary<string, bool> orgOverviewOpen = new();
    private readonly HashSet<string> orgOverviewEverything = new();  // organizations showing every task and member
    private readonly Dictionary<string, string> orgOverviewOrgNames = new();
    private const int OrgOverviewTaskRows = 8, OrgOverviewMemberRows = 40;
    private static readonly string OrgOverviewFolded = ((char)0xE76C).ToString(), OrgOverviewUnfolded = ((char)0xE70D).ToString();

    private async Task OpenOrgOverview()
    {
        if (api == null) return;
        if (!orgOverviewTimerWired)
        {
            orgOverviewTimerWired = true;
            orgOverviewTimer.Tick += (_, _) => { if (orgOverviewBody != null) _ = ReadOrgOverview(); };
        }
        // Transparent, not null: the whole list reports the pointer, so a refresh can wait while it is over the rows.
        var body = new VirtualRows { TraceName = "org-overview", InPlace = true, CacheLength = 1, RememberHeights = true, KnownHeights = true,
            Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent) };
        AutomationProperties.SetAutomationId(body, "org-overview");
        body.PointerEntered += (_, _) => orgOverviewPointerOver = true;
        body.PointerExited += (_, _) =>
        {
            orgOverviewPointerOver = false;
            if (orgOverviewPending && orgOverviewBody == body) { orgOverviewPending = false; orgOverviewDrawn = orgOverviewLatest; DrawOrgOverview(); }
        };
        var anchored = false;
        Action? look = null;
        body.Loaded += (_, _) =>
        {
            DependencyObject? node = body;
            while (node != null && node is not ScrollViewer) node = VisualTreeHelper.GetParent(node);
            if (anchored || node is not ScrollViewer scroll) return;
            anchored = true;
            // At the bottom the view keeps its bottom edge where it is, so the last row stays in view while rows above
            // it change height; elsewhere the first visible row keeps its place. Rows built for the first time can come
            // out taller or shorter than estimated, and a refresh can change a row's height, so a move headed for the
            // end pins the view there until the person scrolls away: whenever the list's height has changed and no row is
            // waiting to be built, a view that is no longer at the end is scrolled there again, as a second jump by the
            // person would.
            var pinned = false; var aiming = false; var pressed = false; var ours = false;
            var repairs = 0; var queued = 0; long stepAt = 0, repairedAt = 0, aimedAt = 0; double lastMax = 0, lastOffset = 0, lastExtent = 0;
            var retry = body.DispatcherQueue.CreateTimer();
            retry.Interval = TimeSpan.FromMilliseconds(260); retry.IsRepeating = false;
            bool Current() => orgOverviewBody == body && pinned;
            // The person is moving the view: a pointer is held on the scroll bar or panning, or an animated move (the
            // wheel, the keyboard, a touchpad) reported an intermediate view just now.
            bool Moving() => pressed || Environment.TickCount64 - stepAt < 250;
            void ToEnd()
            {
                if (!Current() || VirtualRows.PendingBuilds > 0) return;
                if (Moving()) { if (!retry.IsRunning) retry.Start(); return; }
                if (scroll.ScrollableHeight - scroll.VerticalOffset <= 1) return;
                // At most 12 in a burst (repairs less than 2 s apart), so a list that kept changing could not make it loop.
                if (Environment.TickCount64 - repairedAt > 2000) repairs = 0;
                if (++repairs > 12) return;
                repairedAt = Environment.TickCount64; ours = true;
                scroll.ChangeView(null, scroll.ScrollableHeight, null, true);
            }
            void Anchor()
            {
                // Rows built after a long scroll change the list's height before this runs, so the view can be short
                // of the new maximum: it also arrived when it reached the maximum it was scrolled to, or when a jump of
                // more than a screen stopped within a screen of the end.
                var offset = scroll.VerticalOffset; var max = scroll.ScrollableHeight; var screen = scroll.ViewportHeight;
                var extent = scroll.ExtentHeight;
                var exact = max > 0 && offset >= max - 2;
                var bottom = exact || (max > 0 && ((lastMax > 0 && offset >= lastMax - 2)
                    || (offset - lastOffset > screen && max - offset < screen)));
                // A move headed for the end aims there until the view is exactly at the end (for at most 3 s): the small
                // correction that ends a jump comes while its own animation is still reporting, and is not the person.
                if (aiming && Environment.TickCount64 - aimedAt > 3000) aiming = false;
                // Off the end while pinned, and not by the person: a move headed for the end has not landed there, a
                // scroll to the end has not landed yet, or the list's height changed under the view near the end.
                // Anything else is the person leaving.
                var stay = pinned && !bottom && !pressed
                    && (aiming || (!Moving() && (ours || (max - offset < screen && Math.Abs(extent - lastExtent) > .5))));
                lastMax = max; lastOffset = offset; lastExtent = extent; ours = false;
                pinned = bottom || stay;
                if (exact || !pinned) aiming = false;
                scroll.VerticalAnchorRatio = pinned ? 1 : 0;
                if (pinned) ToEnd();
            }
            // The target of a move is known before it lands: one headed for the end (a jump, a drag, the wheel) pins
            // the view at once.
            scroll.ViewChanging += (_, args) =>
            {
                var max = scroll.ScrollableHeight; var target = args.FinalView.VerticalOffset;
                if (max > 0 && target >= max - 2) { if (!aiming) aimedAt = Environment.TickCount64; aiming = pinned = true; }
                else if (max - target >= scroll.ViewportHeight) aiming = false;  // headed a screen or more away from the end
            };
            // When rows were built (raised for every row built anywhere, possibly on a worker), the list or the window
            // changed size, or the person let go: look once, at low priority, after the layout that places the built
            // rows. (Waiting for the next LayoutUpdated instead left the view 10 DIP short: once the list is still, no
            // further layout pass comes.)
            look = () =>
            {
                if (Interlocked.Exchange(ref queued, 1) != 0) return;
                if (!body.DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () => { queued = 0; ToEnd(); }))
                    queued = 0;
            };
            retry.Tick += (_, _) => look?.Invoke();
            PresentationPreparation.Completed += look;
            body.SizeChanged += (_, _) => look?.Invoke();
            scroll.SizeChanged += (_, _) => look?.Invoke();
            scroll.AddHandler(UIElement.PointerPressedEvent, new PointerEventHandler((_, _) => pressed = true), true);
            scroll.AddHandler(UIElement.PointerReleasedEvent, new PointerEventHandler((_, _) => { pressed = false; look?.Invoke(); }), true);
            scroll.AddHandler(UIElement.PointerCaptureLostEvent, new PointerEventHandler((_, _) => { pressed = false; look?.Invoke(); }), true);
            scroll.ViewChanged += (_, args) => { if (args.IsIntermediate) stepAt = Environment.TickCount64; else Anchor(); };
            Anchor();
        };
        orgOverviewBody = body; orgOverviewPointerOver = orgOverviewPending = false; orgOverviewDrawn = "";
        DrawOrgOverview();
        orgOverviewTimer.Start();
        _ = ReadOrgOverview();
        try { await Show(T("ov.title"), body, 1100); }
        // A panel opened meanwhile (the dialog that replaced this one) keeps its own list and timer.
        finally
        {
            if (orgOverviewBody == body) { orgOverviewTimer.Stop(); orgOverviewBody = null; }
            if (look != null) PresentationPreparation.Completed -= look;
            body.Children.Clear();  // rows still waiting to be built are dropped with their hosts
        }
    }

    // Draws again only when something it shows changed. A redraw replaces the changed rows, and a click pressed on one
    // in between would be lost, so while the pointer is over the panel a change waits until it leaves (at most 30 s).
    // The person's own changes redraw at once.
    private async Task ReadOrgOverview(bool redraw = false)
    {
        if (api == null) return;
        try
        {
            var data = await api.Get("/api/overview", lifetime.Token);
            orgOverviewError = "";
            var shown = data.DeepClone();
            if (shown is JsonObject stamped) stamped.Remove("at");
            var text = shown.ToJsonString();
            orgOverviewData = data; orgOverviewLatest = text;
            if (orgOverviewBody == null || (!redraw && text == orgOverviewDrawn)) return;
            if (!redraw && orgOverviewPointerOver && Environment.TickCount64 - orgOverviewDrawnAt < 30000) { orgOverviewPending = true; return; }
            orgOverviewPending = false; orgOverviewDrawn = text;
            DrawOrgOverview();
        }
        catch (Exception ex)
        {
            if (orgOverviewData["orgs"] is JsonArray) return;  // keep showing the last good read
            orgOverviewError = ex.Message;
            DrawOrgOverview();
        }
    }

    private void DrawOrgOverview()
    {
        var body = orgOverviewBody;
        if (body == null) return;
        orgOverviewDrawnAt = Environment.TickCount64;
        var rows = new List<VirtualRows.Row>();
        // Today's date is part of every key: a clock time shown without its date stays right only on the same day.
        var day = DateTime.Today.ToString("yyyyMMdd", CultureInfo.InvariantCulture);
        void Add(string key, double estimate, Func<UIElement> build) => rows.Add(new VirtualRows.Row(build, estimate, key + "#" + day));
        Add("intro", 40, () => OrgOverviewTop(Quiet(T("ov.intro"), 12.5)));
        if (orgOverviewData["orgs"] is not JsonArray orgs)
        {
            var wait = orgOverviewError.Length > 0 ? T("common.load_failed", ("error", orgOverviewError)) : T("common.loading");
            Add("wait|" + wait, 30, () => OrgOverviewTop(Quiet(wait)));
            body.Reconcile(rows);
            return;
        }
        var totals = orgOverviewData["totals"];
        var summary = new List<string>
        {
            T("ov.sum_orgs", ("n", (int)Num(totals, "orgs"))), T("ov.sum_working", ("n", (int)Num(totals, "working")))
        };
        if (Num(totals, "stopped") > 0) summary.Add(T("ov.sum_stopped", ("n", (int)Num(totals, "stopped"))));
        summary.Add(T("ov.sum_tasks", ("n", (int)Num(totals, "open_tasks"))));
        summary.Add(T("ov.sum_wake", ("on", (int)Num(totals, "orgs_auto_wake")), ("n", (int)Num(totals, "orgs"))));
        summary.Add(T("mon.codex_automations", ("on", (int)Num(totals, "automations_on")), ("n", (int)Num(totals, "automations"))));
        summary.Add(T("ov.sum_claude", ("on", (int)Num(totals, "claude_tasks_on")), ("n", (int)Num(totals, "claude_tasks"))));
        var line = string.Join(" · ", summary);
        Add("summary|" + line, 30, () => OrgOverviewTop(Heading(line, 13.5)));
        if (orgOverviewData.Flag("stopped_all")) Add("stopped-all", 30, () => OrgOverviewTop(OrgOverviewWarning(T("ov.stopped_all"))));
        if (orgOverviewData.Flag("scanning")) Add("scanning", 26, () => OrgOverviewTop(Quiet(T("ov.scanning"))));
        Add("fold-all", 42, () =>
        {
            var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
            actions.Children.Add(Button(T("ov.expand_all"), () => OrgOverviewFold(true)));
            actions.Children.Add(Button(T("ov.collapse_all"), () => OrgOverviewFold(false)));
            return OrgOverviewTop(actions);
        });
        orgOverviewOrgNames.Clear();
        foreach (var o in orgs) orgOverviewOrgNames[o.Text("id")] = o.Text("name");
        foreach (var o in orgs) OrgOverviewCard(Add, o);
        OrgOverviewSchedules(Add);
        body.Reconcile(rows);
    }

    private Task OrgOverviewFold(bool open)
    {
        foreach (var o in orgOverviewData.Rows("orgs")) orgOverviewOpen[o.Text("id")] = open;
        DrawOrgOverview();
        return Task.CompletedTask;
    }

    private TextBlock OrgOverviewWarning(string text)
    {
        var warning = Text(text, 12.5); warning.Foreground = Paint("B26A00", "E0A030"); return warning;
    }

    private static Border OrgOverviewTop(UIElement child) => new() { Child = child, Margin = new Thickness(0, 0, 0, 10) };

    // One piece of an organization's card: the pieces in a run draw one bordered card, its first piece with the top
    // edge and corners, its last with the bottom ones. Indented by the organization's depth in the tree.
    private Border OrgOverviewPart(UIElement child, double depth, bool accent, bool top = false, bool bottom = false, double indent = 40)
        => new()
        {
            Child = child,
            Margin = new Thickness(Math.Min(6, depth) * 22, 0, 0, bottom ? 10 : 0),
            Padding = new Thickness(top || bottom ? 12 : 12 + indent, top ? 12 : bottom ? 0 : 3, 12, bottom ? 8 : 3),
            Background = Paint("FFFFFF", "252523"), BorderBrush = accent ? Accent : Line,
            BorderThickness = new Thickness(1, top ? 1 : 0, 1, bottom ? 1 : 0),
            CornerRadius = new CornerRadius(top ? 10 : 0, top ? 10 : 0, bottom ? 10 : 0, bottom ? 10 : 0)
        };

    private static string OrgOverviewWhen(double epochSeconds)
    {
        var at = DateTimeOffset.FromUnixTimeSeconds((long)epochSeconds).ToLocalTime();
        return at.Date == DateTime.Today ? at.ToString("HH:mm", CultureInfo.InvariantCulture) : at.ToString("M/d HH:mm", CultureInfo.InvariantCulture);
    }

    private static string OrgOverviewHash(params string?[] parts) => string.Join("\u001f", parts).GetHashCode().ToString(CultureInfo.InvariantCulture);

    // ---------------- one organization: its rows ----------------
    private void OrgOverviewCard(Action<string, double, Func<UIElement>> add, JsonNode? o)
    {
        var id = o.Text("id");
        var counts = o?["counts"];
        var working = (int)Num(counts, "working");
        var openTasks = (int)Num(counts, "open_tasks");
        if (!orgOverviewOpen.TryGetValue(id, out var open)) open = orgOverviewOpen[id] = working > 0 || openTasks > 0;
        var depth = Num(o, "depth");
        var accent = working > 0;
        var look = (accent ? "a" : "n") + depth.ToString(CultureInfo.InvariantCulture);  // shown by every row of the card
        var names = new Dictionary<string, string>();
        foreach (var m in o.Rows("members")) names[m.Text("name")] = m.Text("display").Length > 0 ? m.Text("display") : m.Text("name");
        string Who(string name)
        {
            if (name == "human") return preferences.Text("name").Length > 0 ? preferences.Text("name") : T("common.you");
            if (names.TryGetValue(name, out var display)) return display;
            // a member of another organization: "<org id>/<member>"
            var slash = name.IndexOf('/');
            return slash > 0 && orgOverviewOrgNames.TryGetValue(name[..slash], out var place)
                ? T("common.member_of_org", ("member", name[(slash + 1)..]), ("org", place)) : name;
        }

        var head = OrgOverviewHash(o.Text("name"), o.Text("kind"), o.Text("cabinet"), o.Text("auto_wake"), o.Text("starts_itself"),
            counts?.ToJsonString(), open ? "open" : "folded");
        add("head:" + id + "|" + look + ":" + head, o.Flag("starts_itself") ? 66 : 88, () => OrgOverviewPart(OrgOverviewHeader(o, id, open, working, openTasks), depth, accent, top: true));
        if (open)
        {
            var doing = OrgOverviewHash(o.Text("purpose"), o?["latest_message"]?.ToJsonString(), o?["latest_action"]?.ToJsonString(),
                string.Join(",", names.Select(pair => pair.Key + "=" + pair.Value)));
            add("doing:" + id + "|" + look + ":" + doing, 110, () => OrgOverviewPart(OrgOverviewDoing(o, Who), depth, accent));
            var tasks = o.Rows("tasks");
            var done = (int)Num(o, "done");
            add("tasks:" + id + "|" + look + ":" + tasks.Count + ":" + done, 34, () =>
            {
                var heading = TwoColumns(Heading(T("ov.tasks", ("n", tasks.Count)), 13), Quiet(done > 0 ? T("ov.done_tasks", ("n", done)) : "", 12));
                heading.Margin = new Thickness(0, 8, 0, 0);
                return OrgOverviewPart(heading, depth, accent);
            });
            if (tasks.Count == 0) add("no-tasks:" + id + "|" + look, 26, () => OrgOverviewPart(Quiet(T("ov.no_open_tasks"), 12.5), depth, accent));
            var everything = orgOverviewEverything.Contains(id);
            foreach (var task in everything ? tasks : tasks.Take(OrgOverviewTaskRows))
            {
                var owner = task.Text("owner").Length > 0 ? Who(task.Text("owner")) : T("ov.unassigned");
                add("task:" + id + ":" + task.Text("id") + "|" + look + ":" + OrgOverviewHash(task?.ToJsonString(), owner), 28,
                    () => OrgOverviewPart(OrgOverviewTask(task, owner), depth, accent));
            }
            if (!everything && tasks.Count > OrgOverviewTaskRows)
                add("more-tasks:" + id + "|" + look + ":" + tasks.Count, 34, () => OrgOverviewPart(QuietButton(T("common.more_items", ("n", tasks.Count - OrgOverviewTaskRows)), () => OrgOverviewShowAll(id)), depth, accent));
            var members = o.Rows("members");
            add("members:" + id + "|" + look + ":" + members.Count, 34, () =>
            {
                var heading = Heading(T("ov.members", ("n", members.Count)), 13); heading.Margin = new Thickness(0, 8, 0, 0);
                return OrgOverviewPart(heading, depth, accent);
            });
            foreach (var m in everything ? members : members.Take(OrgOverviewMemberRows))
                add("member:" + id + ":" + m.Text("name") + "|" + look + ":" + OrgOverviewHash(m?.ToJsonString()), 66 + 22 * m.Rows("automations").Count,
                    () => OrgOverviewPart(OrgOverviewMember(m, id), depth, accent));
            if (!everything && members.Count > OrgOverviewMemberRows)
                add("more-members:" + id + "|" + look + ":" + members.Count, 34, () => OrgOverviewPart(QuietButton(T("common.more_items", ("n", members.Count - OrgOverviewMemberRows)), () => OrgOverviewShowAll(id)), depth, accent));
        }
        add("end:" + id + "|" + look, 18, () => OrgOverviewPart(new Border(), depth, accent, bottom: true));
    }

    private Grid OrgOverviewHeader(JsonNode? o, string id, bool open, int working, int openTasks)
    {
        var counts = o?["counts"];
        var header = new Grid { ColumnSpacing = 10 };
        header.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        header.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        header.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        header.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        var fold = IconButton(open ? OrgOverviewUnfolded : OrgOverviewFolded, "common.collapse", () =>
        {
            orgOverviewOpen[id] = !open; DrawOrgOverview(); return Task.CompletedTask;
        }, open ? T("common.collapse") : T("ov.expand"), 14);
        fold.VerticalAlignment = VerticalAlignment.Top;
        AutomationProperties.SetAutomationId(fold, "ov-fold-" + id);
        header.Children.Add(fold);
        var titles = new StackPanel { Spacing = 3 };
        var heading = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        var title = Heading(o.Text("name"), 15); title.TextWrapping = TextWrapping.NoWrap; title.TextTrimming = TextTrimming.CharacterEllipsis;
        heading.Children.Add(title);
        if (o.Flag("cabinet")) heading.Children.Add(Badge(T("org.cabinet_chip"), true));
        else if (o.Text("kind") == "subgroup") heading.Children.Add(Badge(T("org.kind_subgroup")));
        titles.Children.Add(heading);
        var facts = new List<string> { T("common.members", ("n", (int)Num(counts, "members"))) };
        facts.Add(working > 0 ? T("ov.sum_working", ("n", working)) : T("ov.org_idle"));
        if (Num(counts, "elsewhere") > 0) facts.Add(T("ov.org_elsewhere", ("n", (int)Num(counts, "elsewhere"))));
        if (Num(counts, "stopped") > 0) facts.Add(T("ov.sum_stopped", ("n", (int)Num(counts, "stopped"))));
        facts.Add(openTasks > 0 ? T("ov.sum_tasks", ("n", openTasks)) : T("ov.no_open_tasks"));
        if (Num(counts, "automations") > 0)
            facts.Add(T("mon.codex_automations", ("on", (int)Num(counts, "automations_on")), ("n", (int)Num(counts, "automations"))));
        titles.Children.Add(Quiet(string.Join(" · ", facts), 12.5));
        if (!o.Flag("starts_itself")) titles.Children.Add(OrgOverviewWarning(T("ov.nothing_starts_org")));
        Grid.SetColumn(titles, 1); header.Children.Add(titles);
        var wake = OverviewSwitch(T("ov.auto_wake"), true, o.Flag("auto_wake"), on =>
            OrgOverviewChange(Client.Org(id, "/auto_wake"), new { on }, T(on ? "ov.wake_set_on" : "ov.wake_set_off")));
        wake.VerticalAlignment = VerticalAlignment.Top; wake.Margin = new Thickness(0, 4, 0, 0);
        OrgOverviewName(wake, "ov-wake-" + id, T("ov.org_wake_name", ("org", o.Text("name"))));
        Grid.SetColumn(wake, 2); header.Children.Add(wake);
        var group = OverviewAction(T("common.group_chat"), () => OrgOverviewJump(id, ""));
        group.VerticalAlignment = VerticalAlignment.Top;
        AutomationProperties.SetAutomationId(group, "ov-group-" + id);
        Grid.SetColumn(group, 3); header.Children.Add(group);
        return header;
    }

    private StackPanel OrgOverviewDoing(JsonNode? o, Func<string, string> who)
    {
        var section = new StackPanel { Spacing = 4, Margin = new Thickness(0, 4, 0, 0) };
        section.Children.Add(Heading(T("ov.doing"), 13));
        if (o.Text("purpose").Length > 0) section.Children.Add(OrgOverviewLine(T("ov.purpose", ("text", o.Text("purpose"))), 2));
        var message = o?["latest_message"];
        var act = o?["latest_action"];
        if (message is JsonObject)
            section.Children.Add(OrgOverviewLine(T("ov.latest_message", ("who", who(message.Text("from"))), ("when", OrgOverviewWhen(Num(message, "at"))),
                ("text", message.Text("body"))), 2));
        if (act is JsonObject)
            section.Children.Add(OrgOverviewLine(T("ov.latest_action", ("who", who(act.Text("member"))), ("when", OrgOverviewWhen(Num(act, "at"))),
                ("text", (act.Text("tool") + " " + act.Text("summary")).Trim())), 1));
        if (message is not JsonObject && act is not JsonObject) section.Children.Add(Quiet(T("ov.no_activity"), 12.5));
        return section;
    }

    private TextBlock OrgOverviewLine(string text, int lines)
    {
        var block = Text(text, 12.5); block.MaxLines = lines; block.TextTrimming = TextTrimming.CharacterEllipsis;
        ToolTipService.SetToolTip(block, text);
        return block;
    }

    private Grid OrgOverviewTask(JsonNode? task, string owner)
    {
        var row = new Grid { ColumnSpacing = 10 };
        row.ColumnDefinitions.Add(new() { Width = new GridLength(42) });
        row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        row.ColumnDefinitions.Add(new() { Width = new GridLength(64) });
        row.Children.Add(Quiet(task.Text("id"), 12.5));
        var name = Text(task.Text("title"), 12.5); name.MaxLines = 2; name.TextTrimming = TextTrimming.CharacterEllipsis;
        ToolTipService.SetToolTip(name, task.Text("title"));
        Grid.SetColumn(name, 1); row.Children.Add(name);
        var who = Quiet(owner, 12.5);
        Grid.SetColumn(who, 2); row.Children.Add(who);
        var status = task.Text("status");
        var state = Text(status switch { "working" => T("task.working"), "blocked" => T("task.blocked"), _ => T("task.open") }, 12.5);
        state.Foreground = status switch { "working" => Paint("1E8E3E", "4CC26A"), "blocked" => Paint("C9372C", "E66767"), _ => Muted };
        Grid.SetColumn(state, 3); row.Children.Add(state);
        return row;
    }

    private Task OrgOverviewShowAll(string id)
    {
        orgOverviewEverything.Add(id); DrawOrgOverview(); return Task.CompletedTask;
    }

    // ---------------- one member ----------------
    private UIElement OrgOverviewMember(JsonNode? m, string org)
    {
        var name = m.Text("name");
        var state = m.Text("state");
        var row = new Grid
        {
            ColumnSpacing = 12, Padding = new Thickness(10, 8, 10, 8), CornerRadius = new CornerRadius(10),
            BorderThickness = new Thickness(1), BorderBrush = state == "working" ? Accent : Line
        };
        row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        row.Children.Add(new Microsoft.UI.Xaml.Shapes.Ellipse
        {
            Width = 9, Height = 9, VerticalAlignment = VerticalAlignment.Top, Margin = new Thickness(0, 6, 0, 0),
            Fill = state switch
            {
                "working" => Paint("1E8E3E", "4CC26A"), "elsewhere" => Paint("8CC79C", "3D7A50"), "stopped" => Paint("C9372C", "E66767"),
                "vacant" => Paint("E4E2DC", "3A3936"), _ => Paint("B4B2A9", "5F5E5A")
            }
        });
        var main = new StackPanel { Spacing = 3 };
        var heading = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        var display = m.Text("display").Length > 0 ? m.Text("display") : name;
        var title = Heading(display, 13.5); title.TextWrapping = TextWrapping.NoWrap; title.TextTrimming = TextTrimming.CharacterEllipsis;
        heading.Children.Add(title);
        if (display != name) heading.Children.Add(Quiet(name, 12));
        var harness = m.Text("harness");
        if (harness.Length > 0) heading.Children.Add(Badge(harness == "codex" ? "Codex" : harness == "claude-code" ? "Claude" : harness));
        if (m.Flag("leader")) heading.Children.Add(Badge(T("common.leader")));
        if (m.Flag("secretary")) heading.Children.Add(Badge(T("common.secretary")));
        heading.Children.Add(Quiet(state switch
        {
            "working" => T("mon.state_working"), "stopped" => T("mon.state_stopped"), "vacant" => T("state.vacant"),
            "elsewhere" => T("ov.state_elsewhere", ("org", (m?["working_in"]).Text("org_name"))), _ => T("mon.state_idle")
        }, 12.5));
        main.Children.Add(heading);
        // One line for when it last acted and what can start it; the note that nothing can is part of that line.
        var meta = new List<string>();
        var last = Num(m, "last_at");
        if (last > 0) meta.Add(T("mon.last_active", ("when", OrgOverviewWhen(last))));
        if (m.Flag("released")) meta.Add(T("mon.state_released"));
        var wake = m.Text("wake");
        if (wake != "vacant")
            meta.Add(wake switch { "on" => T("ov.wake_on"), "off" => T("mon.wake_off"), "org_off" => T("ov.wake_org_off"), _ => T("ov.wake_cannot") });
        var nothing = !m.Flag("starts_itself") && wake != "vacant";
        if (meta.Count > 0 || nothing)
        {
            var facts = Quiet(string.Join(" · ", meta), 12);
            if (nothing)
                facts.Inlines.Add(new Microsoft.UI.Xaml.Documents.Run { Text = (meta.Count > 0 ? " · " : "") + T("ov.nothing_starts"), Foreground = Paint("B26A00", "E0A030") });
            main.Children.Add(facts);
        }
        if (m.Text("doing").Length > 0) main.Children.Add(OrgOverviewLine(T("ov.doing_now", ("text", m.Text("doing"))), 1));
        foreach (var automation in m.Rows("automations")) main.Children.Add(OrgOverviewAutomation(automation));
        Grid.SetColumn(main, 1); row.Children.Add(main);

        // The seat's switch and its buttons on one line, so a member takes two or three lines.
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Top };
        if (wake != "vacant")
        {
            var toggle = OverviewSwitch(T("ov.auto_wake"), true, m.Flag("auto_wake"), on =>
                OrgOverviewChange(Client.Org(org, "/seat_auto_wake"), new { member = name, on }, T(on ? "ov.wake_set_on" : "ov.wake_set_off")));
            OrgOverviewName(toggle, "ov-wake-" + org + "-" + name, T("ov.seat_wake_name", ("member", display)));
            toggle.Margin = new Thickness(0, 0, 6, 0); toggle.VerticalAlignment = VerticalAlignment.Center;
            buttons.Children.Add(toggle);
        }
        var key = m.Text("session");
        if (m.Flag("stopped") && key.Length > 0)
        {
            var resume = OverviewAction(T("mon.resume"), () => OrgOverviewMonitor("resume", key));
            AutomationProperties.SetAutomationId(resume, "ov-resume-" + org + "-" + name);
            buttons.Children.Add(resume);
        }
        else if (m.Flag("can_stop") && key.Length > 0)
        {
            Button? stop = null;
            stop = OverviewAction(T("mon.stop"), async () =>
            {
                if (orgOverviewArmed != key || Environment.TickCount64 - orgOverviewArmedAt > 4000)
                {
                    orgOverviewArmed = key; orgOverviewArmedAt = Environment.TickCount64;
                    if (stop?.Content is TextBlock label) label.Text = T("ov.stop_sure");
                    return;
                }
                orgOverviewArmed = "";
                await OrgOverviewMonitor("stop", key);
            });
            ToolTipService.SetToolTip(stop, T("ov.stop_hint"));
            AutomationProperties.SetAutomationId(stop, "ov-stop-" + org + "-" + name);
            buttons.Children.Add(stop);
        }
        var chat = OverviewAction(T("ov.open_chat"), () => OrgOverviewJump(org, name));
        AutomationProperties.SetAutomationId(chat, "ov-chat-" + org + "-" + name);
        buttons.Children.Add(chat);
        Grid.SetColumn(buttons, 2); row.Children.Add(buttons);
        return row;
    }

    private UIElement OrgOverviewAutomation(JsonNode? automation)
    {
        var id = automation.Text("id");
        var paused = automation.Text("status") == "PAUSED";
        var line = Text(T("ov.automation", ("name", automation.Text("name")), ("schedule", automation.Text("schedule")),
            ("state", paused ? T("mon.paused") : T("mon.active"))), 12);
        line.Foreground = paused ? Muted : Ink; line.VerticalAlignment = VerticalAlignment.Center;
        var action = OverviewAction(paused ? T("mon.resume") : T("ov.pause"), () =>
            OrgOverviewChange("/api/monitor/automation", new { id, status = paused ? "ACTIVE" : "PAUSED" },
                T(paused ? "ov.automation_resumed" : "ov.automation_paused", ("name", automation.Text("name")))));
        AutomationProperties.SetAutomationId(action, "ov-auto-" + id);
        action.VerticalAlignment = VerticalAlignment.Center;
        // The button right after its line (the text wraps before it when long), not at the far edge of the row.
        var row = new Grid { ColumnSpacing = 10, HorizontalAlignment = HorizontalAlignment.Left };
        row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        row.Children.Add(line); Grid.SetColumn(action, 1); row.Children.Add(action);
        return row;
    }

    // ---------------- what starts sessions without a seat ----------------
    private void OrgOverviewSchedules(Action<string, double, Func<UIElement>> add)
    {
        var loose = orgOverviewData.Rows("automations");
        add("loose", 30, () => { var h = Heading(T("ov.loose"), 14); h.Margin = new Thickness(0, 6, 0, 0); return h; });
        add("loose-hint", 26, () => OrgOverviewTop(Quiet(T("ov.loose_hint"), 12.5)));
        if (loose.Count == 0) add("loose-none", 26, () => OrgOverviewTop(Quiet(T("ov.none"), 12.5)));
        foreach (var automation in loose)
            add("loose:" + automation.Text("id") + "|" + OrgOverviewHash(automation?.ToJsonString()), 34, () => OrgOverviewTop(OrgOverviewAutomation(automation)));
        var tasks = orgOverviewData.Rows("claude_tasks");
        add("claude", 30, () => { var h = Heading(T("ov.claude_tasks"), 14); h.Margin = new Thickness(0, 6, 0, 0); return h; });
        add("claude-hint", 26, () => OrgOverviewTop(Quiet(T("ov.claude_hint"), 12.5)));
        if (tasks.Count == 0) add("claude-none", 26, () => OrgOverviewTop(Quiet(T("ov.none"), 12.5)));
        foreach (var task in tasks)
        {
            add("claude:" + task.Text("id") + "|" + OrgOverviewHash(task?.ToJsonString()), 70, () =>
            {
                var enabled = task?["enabled"]?.ToString();
                var parts = new List<string> { task.Text("name") };
                if (task.Text("schedule").Length > 0) parts.Add(task.Text("schedule"));
                parts.Add(enabled == "true" ? T("mon.active") : enabled == "false" ? T("ov.off") : T("ov.switch_unknown"));
                var item = new StackPanel { Spacing = 2 };
                item.Children.Add(Text(string.Join(" · ", parts), 12.5));
                if (task.Text("description").Length > 0) item.Children.Add(OrgOverviewLine(task.Text("description"), 2));
                if (task.Text("cwd").Length > 0) item.Children.Add(Quiet(task.Text("cwd"), 12));
                return OrgOverviewTop(item);
            });
        }
    }

    // ---------------- actions ----------------
    private async Task OrgOverviewChange(string path, object body, string done)
    {
        try
        {
            await api!.Post(path, body);
            Note(done);
        }
        catch (Exception ex) { Note(T("ov.action_failed", ("error", ex.Message))); }
        await ReadOrgOverview(redraw: true);
    }

    private async Task OrgOverviewMonitor(string action, string key)
    {
        try { await MonitorAction(action, key); }
        catch (Exception ex) { Note(T("ov.action_failed", ("error", ex.Message))); }
        await ReadOrgOverview(redraw: true);
    }

    private async Task OrgOverviewJump(string id, string member)
    {
        visibleDialog?.Hide();
        await Select(id, member);
    }

    private static void OrgOverviewName(FrameworkElement row, string automationId, string name)
    {
        if (row is not Grid grid || grid.Children.Count == 0 || grid.Children[0] is not FrameworkElement toggle) return;
        AutomationProperties.SetAutomationId(toggle, automationId);
        AutomationProperties.SetName(toggle, name);
    }
}
