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
        detail.Padding = new Thickness(0); detail.Spacing = 0;
        var o = snap["org"]; var members = snap.Rows("members"); var tasks = snap.Rows("tasks");
        var intro = OverviewBlock();
        var modes = new SelectorBar { Padding = new Thickness(0) }; var modeKeys = new Dictionary<SelectorBarItem, string>();
        foreach (var (id, key) in new[] { ("direct", "org.mode_direct"), ("transparent", "org.mode_transparent"), ("liaison", "org.mode_liaison") })
        {
            var label = OverviewText(T(key), 12); label.Foreground = viewMode == id ? Ink : Paint("5A5853", "B8B5AE"); label.TextWrapping = TextWrapping.NoWrap;
            var pick = new SelectorBarItem { Text = T(key), Tag = label, IsSelected = viewMode == id, Padding = new Thickness(9, 2, 9, 2), MinHeight = 0, CornerRadius = new CornerRadius(6),
                Margin = new Thickness(0, 0, id == "liaison" ? 0 : 2, 0), Background = viewMode == id ? Paint("FFFFFF", "252523") : new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.Transparent),
                Template = (ControlTemplate)Microsoft.UI.Xaml.Markup.XamlReader.Load("<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' TargetType='SelectorBarItem'><Border Background='{TemplateBinding Background}' Padding='{TemplateBinding Padding}' CornerRadius='{TemplateBinding CornerRadius}'><ContentPresenter Content='{TemplateBinding Tag}'/></Border></ControlTemplate>") };
            modeKeys.Add(pick, id); modes.Items.Add(pick);
        }
        modes.SelectionChanged += async (_, _) => { if (modes.SelectedItem == null || !modeKeys.TryGetValue(modes.SelectedItem, out var id) || viewMode == id) return; viewMode = id; SaveViewState(); if (id == "liaison" && o.Text("secretary").Length > 0) await Run(() => Select(org, o.Text("secretary"))); else DrawDetail(); };
        var modeGroup = new Border { Child = modes, Background = Paint("EFEEEA", "262624"), Padding = new Thickness(2), CornerRadius = new CornerRadius(8) };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(modeGroup, T("org.view_mode"));
        intro.Children.Add(OverviewHeading(OverviewText(T("org.heading"), 12, true), modeGroup));
        intro.Children.Add(OverviewText(o.Text("name"), 16, weight: 700, lineHeight: 21.6));
        var purpose = OverviewText(o.Text("purpose").Length > 0 ? o.Text("purpose") : T("org.no_purpose")); purpose.Foreground = Paint("5A5853", "B8B5AE");
        purpose.MaxLines = 3; purpose.TextTrimming = TextTrimming.CharacterEllipsis; ToolTipService.SetToolTip(purpose, T("org.click_expand"));
        purpose.Tapped += (_, _) => purpose.MaxLines = purpose.MaxLines == 0 ? 3 : 0; intro.Children.Add(purpose);
        var metadata = new ActionRow { Spacing = 6 };
        if (o.Flag("cabinet")) metadata.Children.Add(OverviewChip(T("org.cabinet_chip"), "sec"));
        metadata.Children.Add(OverviewChip(T(o.Text("kind") == "subgroup" ? "org.kind_subgroup" : "org.kind_formal")));
        var ended = o.Text("status") is not ("" or "active");
        if (ended) metadata.Children.Add(OverviewChip(T(o.Text("status") == "closed" ? "org.status_closed" : "org.status_dissolved"), "bad"));
        metadata.Children.Add(OverviewChip(T(o.Text("governance") == "peer" ? "org.gov_peer" : "org.gov_leader")));
        if (o.Text("leader").Length > 0) metadata.Children.Add(OverviewChip(T(o.Flag("cabinet") ? "org.secretary_general_chip" : "org.leader_chip", ("name", OverviewRoleName(o.Text("leader"), T("common.leader"))))));
        metadata.Children.Add(OverviewChip(T("common.members", ("n", members.Count))));
        if (o.Text("secretary").Length > 0) metadata.Children.Add(OverviewChip(T("org.secretary_chip", ("name", OverviewRoleName(o.Text("secretary"), T("common.secretary")))), "sec"));
        intro.Children.Add(metadata);
        if (ended) intro.Children.Add(OverviewText(T(o.Text("status") == "closed" ? "org.ended_closed" : "org.ended_dissolved"), 12, true, lineHeight: 18.6));
        intro.Children.Add(OverviewSwitch(T("org.auto_wake"), true, o.Flag("auto_wake"), on => Post("/auto_wake", new { on })));
        var decisions = snap.Rows("decisions"); var attention = OverviewBlock();
        attention.Children.Add(OverviewHeading(OverviewText(T("decision.title"), 12, true), decisions.Count > 0 ? OverviewCount(decisions.Count) : null));
        if (decisions.Count == 0) attention.Children.Add(OverviewText(T("decision.none"), muted: true));
        foreach (var decision in decisions) attention.Children.Add(Decision(decision!));
        Hierarchy(o!);
        var work = OverviewBlock(); var done = tasks.Where(t => t.Text("status") == "done").ToArray(); var open = tasks.Where(t => t.Text("status") is not ("done" or "dropped")).ToArray();
        work.Children.Add(OverviewHeading(OverviewLink(T("org.current_work"), () => Details("tasks"), "chev"), OverviewLink(T("org.done_count", ("n", done.Length)), () => Details("tasks", taskId: "done"), "chev")));
        if (tasks.Count == 0) work.Children.Add(OverviewText(T("org.no_tasks"), muted: true));
        else if (open.Length == 0) work.Children.Add(OverviewText(T("org.nothing_open", ("n", done.Length)), muted: true));
        foreach (var task in open.Take(8)) work.Children.Add(OverviewRow(task.Text("owner").Length > 0 ? OverviewAvatar(task.Text("owner")) : null, task.Text("title"), task.Text("id") + " · " + (task.Text("owner").Length > 0 ? Display(task.Text("owner")) : T("org.no_owner")), () => Details("tasks", taskId: task.Text("id")), OverviewChip(TaskState(task.Text("status")), task.Text("status") switch { "blocked" => "bad", "working" => "warn", _ => "" })));
        if (open.Length > 8) work.Children.Add(OverviewLink(T("common.more_items", ("n", open.Length - 8)), () => Details("tasks")));
        var recent = done.Where(t => t.Text("report").Length > 0).OrderByDescending(t => t.Text("done_at")).Take(3).ToArray();
        if (recent.Length > 0) { var label = OverviewText(T("org.recently_done"), 12, true); label.Margin = new Thickness(0, 4, 0, 0); work.Children.Add(label); }
        foreach (var task in recent) work.Children.Add(OverviewRow(task.Text("owner").Length > 0 ? OverviewAvatar(task.Text("owner")) : null, task.Text("title"), OverviewClip(System.Text.RegularExpressions.Regex.Replace(task.Text("report"), "[#*`>|_-]+", " "), 80), () => Details("tasks", taskId: task.Text("id")), OverviewChip(T("org.report"), "ok")));
        if (viewMode != "liaison")
        {
            var people = OverviewBlock(); people.Children.Add(OverviewHeading(OverviewText(T("org.members"), 12, true), OverviewLink(T("org.add"), AddMember, "plus", true)));
            foreach (var m in members)
            {
                var note = new List<string>(); if (m?["ex_officio"] != null) note.Add(T("card.ex_officio", ("org", m["ex_officio"].Text("org_name"))));
                note.Add(m.Text("doing").Length > 0 ? m.Text("doing") : m.Text("detail").Length > 0 ? m.Text("detail") : MemberState(m.Text("state")));
                people.Children.Add(OverviewRow(OverviewAvatar(m.Text("name"), true, 28), m.Flag("secretary") ? T("org.member_secretary", ("name", OverviewRoleName(m.Text("name"), T("common.secretary")))) : Display(m.Text("name")), string.Join(" · ", note.Where(s => s.Length > 0)), () => MemberCard(m.Text("name")), OverviewChip(MemberState(m.Text("state")), m.Text("state") switch { "running" or "working" => "ok", "waiting" => "warn", "error" => "bad", _ => "" })));
            }
            DrawOverviewProtocols();
            var eps = OverviewBlock(); eps.Children.Add(OverviewText(T("native.episodes"), 12, true)); var episodes = snap.Rows("episodes");
            if (episodes.Count == 0) eps.Children.Add(OverviewText(T("org.no_episodes"), muted: true));
            foreach (var episode in episodes.Where(e => e.Text("status") == "open").Concat(episodes.Where(e => e.Text("status") == "closed").Reverse().Take(3)))
            {
                var label = episode.Text("status") == "open" ? T("task.working") : episode.Text("outcome") switch { "success" => T("org.episode_success"), "partial" => T("org.episode_partial"), "cancelled" => T("org.episode_cancelled"), "failure" => T("common.failed"), _ => episode.Text("outcome") };
                var row = OverviewRowContent(OverviewChip(label, episode.Text("status") == "open" ? "warn" : episode.Text("outcome") == "success" ? "ok" : ""), episode.Text("id") + " " + episode.Text("title"), T("org.episode_reflections", ("reflections", episode.Text("reflections")), ("participants", episode.Text("participants"))), noteWrap: true);
                row.Padding = new Thickness(8, 6, 8, 6); row.Margin = new Thickness(-8, 0, -8, 0); eps.Children.Add(row);
            }
        }
        var footer = OverviewBlock(); if (viewMode == "liaison") footer.Children.Add(OverviewText(T("org.liaison_note"), muted: true));
        var details = Button("", () => Details()); var detailsRow = new Grid { ColumnSpacing = 6 }; detailsRow.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); detailsRow.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        detailsRow.Children.Add(ReferenceIcon("trace", 16)); var detailsText = OverviewText(T("org.details"), 13, weight: 600, lineHeight: 17.55); Grid.SetColumn(detailsText, 1); detailsRow.Children.Add(detailsText); details.Content = detailsRow; details.Padding = new Thickness(13, 6, 13, 6); details.MinHeight = 32; details.CornerRadius = new CornerRadius(9); details.HorizontalAlignment = HorizontalAlignment.Stretch; details.HorizontalContentAlignment = HorizontalAlignment.Center; footer.Children.Add(details);
    }
    private void DrawOverviewProtocols()
    {
        var protocols = snap.Rows("protocols"); var live = protocols.Where(p => p.Text("status") is "active" or "proposed").ToArray(); var inherited = snap.Rows("inherited_protocols"); var replaced = snap.Rows("replaced_protocols");
        var box = OverviewBlock(); box.Children.Add(OverviewHeading(OverviewLink(T("org.protocols"), () => Details("protocols"), "chev"), OverviewText(T("org.protocols_active", ("n", protocols.Count(p => p.Text("status") == "active"))), 12, true)));
        if (live.Length + inherited.Count + replaced.Count == 0) box.Children.Add(OverviewText(T("org.no_protocols"), muted: true));
        string Issued(JsonNode? by) => by.Flag("person") ? T("org.issued_by_person") : T("org.issued_by", ("name", by.Text("name")));
        void Row(JsonNode? p, IEnumerable<string> notes, bool ended = false) => box.Children.Add(OverviewRow(OverviewChip(T(p.Text("strength") == "strong" ? "common.strong" : "common.weak"), !ended && p.Text("strength") == "strong" ? "bad" : ""), p.Text("id") + " " + p.Text("title"), string.Join(" · ", notes.Where(n => n.Length > 0)), () => Details("protocols"), ended: ended, struck: ended));
        foreach (var p in live)
        {
            var notes = new List<string> { p?["issued_by"] != null ? Issued(p["issued_by"]) : p.Text("status") == "proposed" ? T("org.protocol_voting", ("n", p.Text("votes"))) : T("org.protocol_used", ("n", p.Text("uses"))) };
            if (p.Flag("replaces_above") && p?["supersedes"] != null) notes.Add(T("org.protocol_overrides", ("ref", p["supersedes"] is JsonObject reference ? T("org.protocol_ref", ("id", reference.Text("id")), ("org", reference.Text("org"))) : p.Text("supersedes"))));
            if (p.Flag("inherit")) notes.Add(T("org.protocol_inherits")); if (p.Flag("check")) notes.Add(T("org.protocol_check")); Row(p, notes);
        }
        foreach (var p in inherited) Row(p, new[] { T("org.inherited_from", ("name", p.Text("from"))), p?["issued_by"].Text("name").Length > 0 ? Issued(p["issued_by"]) : "", p.Flag("check") ? T("org.protocol_check") : "" });
        foreach (var p in replaced) Row(p, new[] { T(p.Text("how") == "retired" ? "org.protocol_retired" : "org.protocol_overridden", ("from", p.Text("from")), ("at", p.Text("at")), ("by", p.Text("by"))) }, true);
    }
    private static string OverviewClip(string value, int length) { var text = System.Text.RegularExpressions.Regex.Replace(value ?? "", @"\s+", " ").Trim(); return text.Length > length ? text[..(length - 1)] + "…" : text; }
    private void Hierarchy(JsonNode o)
    {
        var box = OverviewBlock(); box.Children.Add(OverviewHeading(OverviewText(T("org.hierarchy"), 12, true), OverviewLink(T("chart.title"), () => ShowChart(org), "chev")));
        var descendants = new HashSet<string> { org }; bool added;
        do { added = false; foreach (var child in orgs) if (descendants.Contains(child.Text("parent"))) added |= descendants.Add(child.Text("id")); } while (added);
        var above = o["parent"].Text("id"); var activeOrg = o.Text("status") is "" or "active";
        var parent = Choice(box, "org.parent_label", new[] { ("", T("org.parent_none")) }.Concat(orgs.Where(x => !descendants.Contains(x.Text("id")) && (x.Text("id") == above || x.Text("status") == "active" && (o.Text("kind") == "subgroup" || x.Text("kind") != "subgroup"))).Select(x => (x.Text("id"), x.Text("name")))));
        SetChoice(parent, above); parent.IsEnabled = activeOrg;
        CompactHierarchyChoice(box, parent, "org.parent_label");
        parent.SelectionChanged += async (_, _) => await Run(async () => { try { await Post("/parent", new { parent = Value(parent).Length > 0 ? Value(parent) : null }); } catch (Exception ex) { Note(T("org.parent_failed", ("error", ex.Message))); } });
        if (o.Text("governance") != "peer")
        {
            var options = snap.Rows("members").Select(m => (m.Text("name"), Display(m.Text("name"))));
            if (o.Text("leader").Length == 0) options = new[] { ("", T("org.leader_unset")) }.Concat(options);
            var leader = Choice(box, "common.leader", options); SetChoice(leader, o.Text("leader")); leader.IsEnabled = activeOrg && snap.Rows("members").Count > 0;
            if (o.Text("leader").Length == 0 && leader.Items.FirstOrDefault() is ComboBoxItem unset) unset.IsEnabled = false;
            CompactHierarchyChoice(box, leader, "common.leader");
            leader.SelectionChanged += async (_, _) => await Run(async () => { var name = Value(leader); if (name.Length == 0 || !await Confirm(T("org.leader_confirm", ("name", Display(name)), ("org", o.Text("name"))))) { DrawDetail(); return; } try { await Post("/leader", new { member = name }); Note(T("org.leader_changed", ("name", Display(name)))); } catch (Exception ex) { Note(T("org.leader_failed", ("error", ex.Message))); } });
        }
        if (o.Text("kind") == "subgroup") box.Children.Add(OverviewText(T("org.subgroup_note", ("name", orgs.FirstOrDefault(x => x.Text("id") == o.Text("home")).Text("name"))), 12, true, lineHeight: 18.6));
        else
        {
            box.Children.Add(OverviewSwitch(T("org.cabinet_toggle"), activeOrg, o.Flag("cabinet"), async on => { try { await Post("/cabinet", new { on }); } catch (Exception ex) { Note(T("org.cabinet_failed", ("error", ex.Message))); DrawDetail(); } }));
            var other = orgs.FirstOrDefault(x => x.Flag("cabinet") && x.Text("id") != org);
            box.Children.Add(OverviewText(o.Flag("cabinet") ? T("org.cabinet_on_hint") : other != null ? T("org.cabinet_elsewhere", ("name", other.Text("name"))) : T("org.cabinet_hint"), 12, true, lineHeight: 18.6));
        }
        box.Children.Add(OverviewText(T("org.parent_hint"), 12, true, lineHeight: 18.6));
        foreach (var (key, title) in new[] { ("children", "org.children"), ("subgroups", "org.subgroups") })
        {
            var children = o.Rows(key).Where(c => key != "children" || c.Text("kind") != "subgroup").ToArray();
            if (children.Length > 0) { var heading = OverviewText(T(title), 12, true); heading.Margin = new Thickness(0, 6, 0, 0); box.Children.Add(heading); }
            foreach (var child in children)
            {
                var open = child.Text("status") is "" or "active";
                var record = key == "subgroups" ? o.Rows("children").FirstOrDefault(c => c.Text("id") == child.Text("id")) : child;
                var stats = record == null ? "" : T("org.child_stats", ("decisions", record.Text("decisions")), ("blocked", record.Text("blocked")), ("working", record.Text("working")));
                var note = key == "children" ? stats : open ? string.Join(" · ", new[] { child.Text("leader").Length > 0 ? T("org.leader_chip", ("name", child.Text("leader"))) : "", stats }.Where(s => s.Length > 0))
                    : T(child.Text("status") == "closed" ? "org.status_closed" : "org.status_dissolved") + (child.Text("ended_at").Length > 0 ? " · " + ShortWhen(child.Text("ended_at")) : "");
                box.Children.Add(OverviewRow(OverviewOrgBadge(child!, key == "subgroups"), child.Text("name"), note, () => Select(child.Text("id")), ended: key == "subgroups" && !open));
            }
        }
        if (o.Text("kind") == "subgroup" && activeOrg) { var close = OverviewAction(T("org.close_group"), async () => { if (!await Confirm(T("org.close_group_confirm", ("name", o.Text("name"))))) return; try { await Post("/close", new { }); Note(T("org.group_closed", ("name", o.Text("name")))); } catch (Exception ex) { Note(T("org.close_group_failed", ("error", ex.Message))); } }); if (close.Content is TextBlock text) text.Foreground = Paint("C2412D", "EE8A78"); box.Children.Add(close); }
    }
    private void CompactHierarchyChoice(StackPanel box, ComboBox choice, string label)
    {
        box.Children.Remove(choice); choice.Header = null;
        var row = new Grid { ColumnSpacing = 10 }; row.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        choice.FontFamily = new Microsoft.UI.Xaml.Media.FontFamily(FontFamilies.UI); choice.FontSize = 14; choice.MinHeight = 0; choice.Height = 37; choice.Padding = new Thickness(10, 7, 10, 7); choice.CornerRadius = new CornerRadius(9); choice.BorderThickness = new Thickness(1); choice.BorderBrush = Paint("DEDBD4", "3A3936"); choice.Background = Paint("FFFFFF", "1F1F1E");
        foreach (var item in choice.Items.OfType<ComboBoxItem>()) if (item.Content is TextBlock text) { text.FontSize = 14; text.FontFamily = choice.FontFamily; text.Foreground = Ink; }
        var title = OverviewText(T(label)); title.Foreground = Paint("5A5853", "B8B5AE"); title.VerticalAlignment = VerticalAlignment.Center; row.Children.Add(title); Grid.SetColumn(choice, 1); row.Children.Add(choice); box.Children.Add(row);
    }
    private UIElement Decision(JsonNode d)
    {
        var card = new StackPanel { Spacing = 6 }; var actions = new ActionRow { Spacing = 6 }; var kind = d.Text("kind"); var who = Display(d.Text("member"));
        void Title(string value) => card.Children.Add(OverviewText(value, weight: 700));
        if (kind == "permission")
        {
            Title(T("decision.permission", ("name", who), ("what", d.Text("title"))));
            if (d.Text("detail").Length > 0) { var info = OverviewText(d.Text("detail"), muted: true); info.TextWrapping = TextWrapping.NoWrap; info.TextTrimming = TextTrimming.CharacterEllipsis; card.Children.Add(info); }
            foreach (var option in d.Rows("options")) actions.Children.Add(OverviewAction(option.Text("name").Length > 0 ? option.Text("name") : option.Text("kind"), async () => { await api!.Post("/api/permission/" + Client.Segment(d.Text("id")), new { option = option.Text("id") }); await Refresh(); }, option.Text("kind").StartsWith("allow", StringComparison.Ordinal)));
        }
        else if (kind is "approval" or "trajectory")
        {
            var requester = d.Text("requester").Length == 0 ? "-" : kind == "approval" && d.Text("requester_org").Length > 0 && d.Text("requester_org") != org ? T("common.member_of_org", ("member", d.Text("requester")), ("org", d.Text("requester_org_name").Length > 0 ? d.Text("requester_org_name") : d.Text("requester_org"))) : Display(d.Text("requester"));
            Title(kind == "approval" ? T("decision.approval", ("requester", requester), ("what", d.Text("label").Length > 0 ? d.Text("label") : d.Text("text").Length > 0 ? d.Text("text") : d.Text("request")), ("id", d.Text("id"))) : T("decision.trajectory", ("requester", requester), ("whose", d.Text("requester") == d.Text("member") ? T("decision.own_seat") : T("decision.member_seat", ("name", who))), ("which", d.Text("carrier") is "" or "0" ? T("decision.current_session") : T("decision.earlier_session", ("n", d.Text("carrier"))))));
            if (kind == "trajectory" || d.Text("reason").Length > 0) card.Children.Add(OverviewText(T("decision.reason", ("reason", d.Text("reason").Length > 0 ? d.Text("reason") : "—"))));
            if (kind == "approval")
            {
                var cabinet = orgs.FirstOrDefault(x => x.Flag("cabinet")); var sg = cabinet.Text("leader"); if (cabinet.Text("id") == org) sg = Display(sg);
                var note = d.Text("approver") == "human" ? T("decision.approval_human") : d.Text("approver") == "secretary-general" && sg.Length > 0 ? T("decision.approval_sg", ("name", sg)) : "";
                card.Children.Add(OverviewText(string.Join(" · ", new[] { ShortWhen(d.Text("at")), note }.Where(s => s.Length > 0)), 12, true));
            }
            foreach (var decision in new[] { "approve", "deny" }) actions.Children.Add(OverviewAction(decision == "deny" ? T("decision.deny") : kind == "trajectory" ? T("decision.approve_redacted") : T("decision.approve"), async () =>
            {
                foreach (var button in actions.Children.OfType<Button>()) button.IsEnabled = false;
                try
                {
                    var result = await api!.Post(Client.Org(kind == "approval" && d.Text("org").Length > 0 ? d.Text("org") : org, kind == "approval" ? "/request" : "/trajectory_answer"), new { request_id = d.Text("id"), decision });
                    if (kind == "approval") Note(result.Text("status") == "failed" ? T("decision.approval_failed", ("id", d.Text("id")), ("error", result.Text("error"))) : T(result.Text("status") == "denied" ? "decision.denied" : "decision.approved", ("id", d.Text("id")))); await Refresh();
                }
                finally { foreach (var button in actions.Children.OfType<Button>()) button.IsEnabled = true; }
            }, decision == "approve"));
        }
        else if (kind == "task")
        {
            Title(T("decision.task_blocked", ("id", d.Text("id")), ("title", d.Text("title")))); card.Children.Add(OverviewText(T("decision.task_owner", ("name", d.Text("member").Length > 0 ? who : "—")), muted: true));
            actions.Children.Add(OverviewAction(T("decision.view_task"), () => Details("tasks", taskId: d.Text("id")))); if (d.Text("member").Length > 0) actions.Children.Add(OverviewAction(T("decision.ask", ("name", who)), () => Select(org, d.Text("member"))));
        }
        else if (kind == "wake") { Title(T("decision.wake_failed", ("name", who))); card.Children.Add(OverviewText(OverviewClip(d.Text("error"), 140), muted: true)); actions.Children.Add(OverviewAction(T("decision.open_chat"), () => Select(org, d.Text("member")))); }
        else card.Children.Add(OverviewText(d.ToJsonString()));
        if (actions.Children.Count > 0) card.Children.Add(actions);
        return new Border { Child = card, Background = Paint("FBF3E2", "3A3020"), BorderBrush = OverviewAlpha(Paint("B7791F", "E2B15A"), .4), BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(10), Padding = new Thickness(10, 8, 10, 8) };
    }
    private string MemberState(string state) => state is "starting" or "running" or "working" or "waiting" or "error" or "vacant" or "idle" or "active" ? T(state switch { "starting" => "state.starting", "running" => "state.running", "working" => "state.working", "waiting" => "state.waiting", "error" => "state.error", "vacant" => "state.vacant", "idle" => "state.idle", _ => "state.active" }) : state;
    private string TaskState(string state) => T(state switch { "open" => "task.open", "working" => "task.working", "blocked" => "task.blocked", "done" => "task.done", "dropped" => "task.dropped", _ => "task." + state });
}
