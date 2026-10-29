using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Relic.Core;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private void DrawOverview()
    {
        if (org.Length == 0) return;
        var o = snap["org"]; var members = snap.Rows("members"); var tasks = snap.Rows("tasks");
        var modes = new ActionRow { Spacing = 2 };
        foreach (var (id, key) in new[] { ("direct", "org.mode_direct"), ("transparent", "org.mode_transparent"), ("liaison", "org.mode_liaison") })
        {
            var pick = new Microsoft.UI.Xaml.Controls.Primitives.ToggleButton { Content = T(key), IsChecked = viewMode == id, Padding = new Thickness(5, 3, 5, 3), MinWidth = 0, MinHeight = 24, FontSize = 11, CornerRadius = new CornerRadius(5) };
            ToolTipService.SetToolTip(pick, T("org.view_mode")); pick.Click += async (_, _) => { viewMode = id; SaveViewState(); if (id == "liaison" && o.Text("secretary").Length > 0) await Run(() => Select(org, o.Text("secretary"))); else DrawDetail(); }; modes.Children.Add(pick);
        }
        detail.Children.Add(TwoColumns(Quiet(T("org.heading"), 11), modes)); detail.Children.Add(Heading(o.Text("name"), 17));
        var purpose = Text(o.Text("purpose").Length > 0 ? o.Text("purpose") : T("org.no_purpose"), 13); purpose.MaxLines = 3; purpose.TextTrimming = TextTrimming.CharacterEllipsis; ToolTipService.SetToolTip(purpose, T("org.click_expand"));
        var purposeButton = QuietButton("", () => { purpose.MaxLines = purpose.MaxLines == 0 ? 3 : 0; return Task.CompletedTask; }); purposeButton.Content = purpose; purposeButton.HorizontalAlignment = HorizontalAlignment.Stretch; purposeButton.Padding = new Thickness(0); detail.Children.Add(purposeButton);
        var metadata = new ActionRow { Spacing = 4 };
        metadata.Children.Add(Badge(T(o.Text("kind") == "subgroup" ? "org.kind_subgroup" : "org.kind_formal"))); metadata.Children.Add(Badge(T(o.Text("governance") == "peer" ? "org.gov_peer" : "org.gov_leader"))); metadata.Children.Add(Badge(T("common.members", ("n", members.Count))));
        if (o.Flag("cabinet")) metadata.Children.Add(Badge(T("org.cabinet_chip"), true));
        if (o.Text("leader").Length > 0) metadata.Children.Add(Badge(T(o.Flag("cabinet") ? "org.secretary_general_chip" : "org.leader_chip", ("name", Display(o.Text("leader"))))));
        if (o.Text("secretary").Length > 0) { var secretary = QuietButton("", () => Select(org, o.Text("secretary"))); secretary.Padding = new Thickness(0); secretary.Content = Badge(T("org.secretary_chip", ("name", Display(o.Text("secretary")))), true); metadata.Children.Add(secretary); }
        detail.Children.Add(metadata);
        if (o.Text("status") is "closed" or "dissolved") detail.Children.Add(Text(T(o.Text("status") == "closed" ? "org.ended_closed" : "org.ended_dissolved")));
        var wake = new ToggleSwitch { IsOn = o.Flag("auto_wake"), OnContent = "", OffContent = "", MinWidth = 42 }; Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(wake, T("org.auto_wake"));
        var wakeRow = new Grid { ColumnSpacing = 8 }; wakeRow.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); wakeRow.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); wakeRow.Children.Add(wake); var wakeText = Text(T("org.auto_wake"), 12); Grid.SetColumn(wakeText, 1); wakeText.VerticalAlignment = VerticalAlignment.Center; wakeRow.Children.Add(wakeText); detail.Children.Add(wakeRow);
        wake.Toggled += async (_, _) => await Run(() => Post("/auto_wake", new { on = wake.IsOn }));
        detail.Children.Add(Heading(T("decision.title")));
        if (snap.Rows("decisions").Count == 0) detail.Children.Add(Quiet(T("decision.none")));
        foreach (var decision in snap.Rows("decisions")) detail.Children.Add(Decision(decision!));
        var start = detail.Children.Count; Hierarchy(o!); var hierarchy = new StackPanel { Spacing = 10 };
        while (detail.Children.Count > start) { var child = detail.Children[start]; detail.Children.RemoveAt(start); hierarchy.Children.Add(child); }
        detail.Children.Add(new Expander { Header = T("org.hierarchy"), Content = hierarchy, HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch });
        detail.Children.Add(Button(T("org.current_work"), () => Details("tasks")));
        detail.Children.Add(Button(T("org.done_count", ("n", tasks.Count(t => t.Text("status") == "done"))), () => Details("tasks", taskId: "done")));
        if (tasks.Count == 0) detail.Children.Add(Text(T("org.no_tasks")));
        var open = tasks.Where(t => t.Text("status") is not ("done" or "dropped")).ToArray();
        if (tasks.Count > 0 && open.Length == 0) detail.Children.Add(Text(T("org.nothing_open", ("n", tasks.Count(t => t.Text("status") == "done")))));
        foreach (var task in open.Take(8)) detail.Children.Add(Button(task.Text("id") + " " + task.Text("title") + " · " + (task.Text("owner").Length > 0 ? Display(task.Text("owner")) : T("org.no_owner")) + " · " + TaskState(task.Text("status")), () => Details("tasks", taskId: task.Text("id"))));
        if (open.Length > 8) detail.Children.Add(Button(T("common.more_items", ("n", open.Length - 8)), () => Details("tasks")));
        var done = tasks.Where(t => t.Text("status") == "done" && t.Text("report").Length > 0).OrderByDescending(t => t.Text("done_at")).Take(3).ToArray();
        if (done.Length > 0) detail.Children.Add(Text(T("org.recently_done"), 18));
        foreach (var task in done) detail.Children.Add(Button(task.Text("title") + " · " + T("org.report") + "\n" + task.Text("report"), () => Details("tasks", taskId: task.Text("id"))));
        if (viewMode != "liaison")
        {
            detail.Children.Add(Text(T("org.members"), 18)); detail.Children.Add(Button(T("org.add"), AddMember));
            foreach (var m in members) detail.Children.Add(Button((m.Flag("secretary") ? T("org.member_secretary", ("name", Display(m.Text("name")))) : Display(m.Text("name"))) + " · " + MemberState(m.Text("state")) + "\n" + (m.Text("doing").Length > 0 ? m.Text("doing") : m.Text("detail")), () => MemberCard(m.Text("name"))));
            detail.Children.Add(Button(T("org.protocols"), () => Details("protocols"))); detail.Children.Add(Button(T("org.add"), IssueProtocol));
            detail.Children.Add(Text(T("org.protocols_active", ("n", snap.Rows("protocols").Count(p => p.Text("status") == "active"))), 12));
            var protocols = snap.Rows("protocols").Where(p => p.Text("status") is "active" or "proposed").Concat(snap.Rows("inherited_protocols")).Concat(snap.Rows("replaced_protocols")).ToArray();
            if (protocols.Length == 0) detail.Children.Add(Text(T("org.no_protocols")));
            foreach (var p in protocols) detail.Children.Add(Button(p.Text("id") + " " + p.Text("title") + " · " + T(p.Text("strength") == "strong" ? "common.strong" : "common.weak") + "\n" + (p.Text("from").Length > 0 ? T("org.inherited_from", ("name", p.Text("from"))) : p.Text("status") == "proposed" ? T("org.protocol_voting", ("n", p.Text("votes"))) : T("org.protocol_used", ("n", p.Text("uses")))), () => Details("protocols")));
            detail.Children.Add(Text(T("native.episodes"), 18));
            var episodes = snap.Rows("episodes"); if (episodes.Count == 0) detail.Children.Add(Text(T("org.no_episodes")));
            foreach (var e in episodes.Where(e => e.Text("status") == "open").Concat(episodes.Where(e => e.Text("status") == "closed").Reverse().Take(3)))
                detail.Children.Add(Text(e.Text("id") + " " + e.Text("title") + " · " + T(e.Text("status") == "open" ? "task.working" : e.Text("outcome") switch { "success" => "org.episode_success", "partial" => "org.episode_partial", "cancelled" => "org.episode_cancelled", _ => "common.failed" }) + "\n" + T("org.episode_reflections", ("reflections", e.Text("reflections")), ("participants", e.Text("participants")))));
        }
        else detail.Children.Add(Text(T("org.liaison_note")));
        detail.Children.Add(Button(T("org.details"), () => Details()));
    }
    private void Hierarchy(JsonNode o)
    {
        detail.Children.Add(Button(T("org.hierarchy") + " · " + T("chart.title"), Chart));
        var descendants = new HashSet<string> { org }; bool added;
        do { added = false; foreach (var child in orgs) if (descendants.Contains(child.Text("parent"))) added |= descendants.Add(child.Text("id")); } while (added);
        var above = o["parent"].Text("id"); var activeOrg = o.Text("status") is "" or "active";
        var parent = Choice(detail, "org.parent_label", new[] { ("", T("org.parent_none")) }.Concat(orgs.Where(x => !descendants.Contains(x.Text("id")) && (x.Text("id") == above || x.Text("status") == "active" && (o.Text("kind") == "subgroup" || x.Text("kind") != "subgroup"))).Select(x => (x.Text("id"), x.Text("name")))));
        SetChoice(parent, above); parent.IsEnabled = activeOrg;
        parent.SelectionChanged += async (_, _) => await Run(async () => { try { await Post("/parent", new { parent = Value(parent).Length > 0 ? Value(parent) : null }); } catch (Exception ex) { Note(T("org.parent_failed", ("error", ex.Message))); } });
        if (o.Text("governance") != "peer")
        {
            var leader = Choice(detail, "common.leader", new[] { ("", T("org.leader_unset")) }.Concat(snap.Rows("members").Select(m => (m.Text("name"), Display(m.Text("name")))))); SetChoice(leader, o.Text("leader")); leader.IsEnabled = activeOrg && snap.Rows("members").Count > 0;
            leader.SelectionChanged += async (_, _) => await Run(async () => { var name = Value(leader); if (name.Length == 0 || !await Confirm(T("org.leader_confirm", ("name", Display(name)), ("org", o.Text("name"))))) { DrawDetail(); return; } try { await Post("/leader", new { member = name }); Note(T("org.leader_changed", ("name", Display(name)))); } catch (Exception ex) { Note(T("org.leader_failed", ("error", ex.Message))); } });
        }
        if (o.Text("kind") == "subgroup") detail.Children.Add(Text(T("org.subgroup_note", ("name", orgs.FirstOrDefault(x => x.Text("id") == o.Text("home")).Text("name")))));
        else
        {
            var cabinet = new ToggleSwitch { Header = T("org.cabinet_toggle"), IsOn = o.Flag("cabinet"), IsEnabled = activeOrg }; detail.Children.Add(cabinet);
            var other = orgs.FirstOrDefault(x => x.Flag("cabinet") && x.Text("id") != org);
            detail.Children.Add(Text(o.Flag("cabinet") ? T("org.cabinet_on_hint") : other != null ? T("org.cabinet_elsewhere", ("name", other.Text("name"))) : T("org.cabinet_hint"), 12));
            cabinet.Toggled += async (_, _) => await Run(async () => { try { await Post("/cabinet", new { on = cabinet.IsOn }); } catch (Exception ex) { Note(T("org.cabinet_failed", ("error", ex.Message))); } });
        }
        detail.Children.Add(Text(T("org.parent_hint"), 12));
        foreach (var (key, title) in new[] { ("children", "org.children"), ("subgroups", "org.subgroups") })
        {
            if (o.Rows(key).Count > 0) detail.Children.Add(Text(T(title), 16));
            foreach (var child in o.Rows(key).Where(c => key != "children" || c.Text("kind") != "subgroup")) detail.Children.Add(Button(child.Text("name") + "\n" + (child.Text("status") is "closed" or "dissolved" ? T(child.Text("status") == "closed" ? "org.status_closed" : "org.status_dissolved") : T("org.child_stats", ("decisions", child.Text("decisions")), ("blocked", child.Text("blocked")), ("working", child.Text("working")))), () => Select(child.Text("id"))));
        }
        if (o.Text("kind") == "subgroup" && activeOrg) detail.Children.Add(Button(T("org.close_group"), async () => { if (!await Confirm(T("org.close_group_confirm", ("name", o.Text("name"))))) return; try { await Post("/close", new { }); Note(T("org.group_closed", ("name", o.Text("name")))); } catch (Exception ex) { Note(T("org.close_group_failed", ("error", ex.Message))); } }));
    }
    private UIElement Decision(JsonNode d)
    {
        var card = new StackPanel { Spacing = 6 }; var kind = d.Text("kind"); var who = Display(d.Text("member"));
        if (kind == "permission")
        {
            card.Children.Add(Text(T("decision.permission", ("name", who), ("what", d.Text("title"))))); card.Children.Add(Text(d.Text("detail")));
            foreach (var option in d.Rows("options")) card.Children.Add(Button(option.Text("name").Length > 0 ? option.Text("name") : option.Text("kind"), async () => { await api!.Post("/api/permission/" + Client.Segment(d.Text("id")), new { option = option.Text("id") }); await Refresh(); }));
        }
        else if (kind is "approval" or "trajectory")
        {
            var requester = d.Text("requester_org").Length > 0 && d.Text("requester_org") != org ? T("common.member_of_org", ("member", d.Text("requester")), ("org", d.Text("requester_org_name"))) : Display(d.Text("requester"));
            card.Children.Add(Text(kind == "approval" ? T("decision.approval", ("requester", requester), ("what", d.Text("label").Length > 0 ? d.Text("label") : d.Text("text")), ("id", d.Text("id"))) : T("decision.trajectory", ("requester", requester), ("whose", d.Text("requester") == d.Text("member") ? T("decision.own_seat") : T("decision.member_seat", ("name", who))), ("which", d.Text("carrier") is "" or "0" ? T("decision.current_session") : T("decision.earlier_session", ("n", d.Text("carrier")))))));
            card.Children.Add(Text(T("decision.reason", ("reason", d.Text("reason")))));
            if (kind == "approval") card.Children.Add(Text(d.Text("approver") == "human" ? T("decision.approval_human") : T("decision.approval_sg", ("name", orgs.FirstOrDefault(o => o.Flag("cabinet")).Text("leader"))), 12));
            foreach (var decision in new[] { "approve", "deny" }) card.Children.Add(Button(decision == "deny" ? T("decision.deny") : kind == "trajectory" ? T("decision.approve_redacted") : T("decision.approve"), async () =>
            {
                var result = await api!.Post(Client.Org(d.Text("org").Length > 0 ? d.Text("org") : org, kind == "approval" ? "/request" : "/trajectory_answer"), new { request_id = d.Text("id"), decision });
                Note(result.Text("status") == "failed" ? T("decision.approval_failed", ("id", d.Text("id")), ("error", result.Text("error"))) : T(decision == "approve" ? "decision.approved" : "decision.denied", ("id", d.Text("id")))); await Refresh();
            }));
        }
        else if (kind == "task") { card.Children.Add(Text(T("decision.task_blocked", ("id", d.Text("id")), ("title", d.Text("title"))))); card.Children.Add(Text(T("decision.task_owner", ("name", who)))); card.Children.Add(Button(T("decision.view_task"), () => Details("tasks", taskId: d.Text("id")))); if (d.Text("member").Length > 0) card.Children.Add(Button(T("decision.ask", ("name", who)), () => Select(org, d.Text("member")))); }
        else if (kind == "wake") { card.Children.Add(Text(T("decision.wake_failed", ("name", who)))); card.Children.Add(Text(d.Text("error"))); card.Children.Add(Button(T("decision.open_chat"), () => Select(org, d.Text("member")))); }
        else card.Children.Add(Text(d.ToJsonString()));
        InlineActions(card); if (card.Children.FirstOrDefault() is TextBlock title) title.FontWeight = Microsoft.UI.Text.FontWeights.SemiBold;
        return Card(card, true);
    }
    private string MemberState(string state) => state is "starting" or "running" or "working" or "waiting" or "error" or "vacant" or "idle" or "active" ? T(state switch { "starting" => "state.starting", "running" => "state.running", "working" => "state.working", "waiting" => "state.waiting", "error" => "state.error", "vacant" => "state.vacant", "idle" => "state.idle", _ => "state.active" }) : state;
    private string TaskState(string state) => T(state switch { "open" => "task.open", "working" => "task.working", "blocked" => "task.blocked", "done" => "task.done", "dropped" => "task.dropped", _ => "task." + state });
}
