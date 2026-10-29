using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Relic.Core;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private readonly StackPanel toolbar = new() { Orientation = Orientation.Horizontal, Spacing = 8 };
    private StackPanel? copiesBody;
    private HashSet<string>? knownCopies;
    private void DrawToolbar()
    {
        toolbar.Children.Clear();
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(toolbar, T("page.titlebar"));
        toolbar.Children.Add(Button(sideOpen ? T("appbar.hide_sidebar") : T("appbar.show_sidebar"), ToggleSide));
        toolbar.Children.Add(Button(T("appbar.back"), () => Navigate(-1))); toolbar.Children.Add(Button(T("appbar.forward"), () => Navigate(1)));
        toolbar.Children.Add(Text(snap["org"].Text("name"), 18));
        var count = snap.Rows("decisions").Count;
        toolbar.Children.Add(Button(count > 0 ? T("appbar.decisions", ("n", count)) : T("appbar.no_decisions"), () => SetPane("overview")));
        var unread = copies.Count(c => !c.Flag("read"));
        toolbar.Children.Add(Button(unread > 0 ? T("appbar.cc", ("n", unread)) : T("appbar.cc_none"), Copies));
        int i = 1;
        foreach (var (id, label) in new[] { ("overview", "panel.overview"), ("workspace", "panel.workspace"), ("files", "common.file") })
        {
            var button = Button(T(label), () => pane == id && panelOpen ? TogglePanel() : SetPane(id)); ToolTipService.SetToolTip(button, T("appbar.pane_shortcut", ("pane", T(label)), ("key", "Alt+" + i++))); toolbar.Children.Add(button);
        }
    }
    private void DrawSidebar()
    {
        side.Children.Clear(); side.Children.Add(Button(T("common.new_org"), CreateOrg)); side.Children.Add(search); side.Children.Add(Text(T("page.tree") + " · " + orgs.Count, 12));
        var visited = new HashSet<string>(); var query = search.Text.Trim();
        bool Match(string value) => value.Contains(query, StringComparison.OrdinalIgnoreCase);
        void Chat(string who, string title, string subtitle, string avatar, string state = "")
        {
            var key = who.Length == 0 ? "group" : "member:" + who;
            var selected = who == member; var id = org;
            var content = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
            content.Children.Add(Avatar(avatar, who.Length == 0 ? "#" : title));
            content.Children.Add(Stack(Text(title + (selected ? " •" : Unread(key))), Text(subtitle, 12), Text(MemberState(state), 11)));
            var button = Button("", () => Select(id, who)); button.Content = content; side.Children.Add(button);
        }
        void Node(JsonNode? item, int depth)
        {
            var id = item.Text("id"); if (!visited.Add(id)) return;
            var selected = id == org; var members = selected ? snap.Rows("members").Where(m => Match(m.Text("name")) || Match(m.Text("display")) || Match(m.Text("role"))).ToArray() : [];
            var orgMatch = Match(item.Text("name")) || Match(item.Text("purpose")); var children = orgs.Where(o => o.Text("parent") == id).ToArray();
            if (query.Length == 0 || orgMatch || members.Length > 0)
            {
                var row = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(Math.Min(depth, 10) * 12, 0, 0, 0) };
                if (selected || children.Length > 0) row.Children.Add(Button(folded.Contains(id) ? "▸" : "▾", () => { if (!folded.Add(id)) folded.Remove(id); SaveViewState(); DrawSidebar(); return Task.CompletedTask; }));
                var button = Button(item.Text("name") + (item.Text("status") is "closed" or "dissolved" ? " · " + T(item.Text("status") == "closed" ? "org.status_closed" : "org.status_dissolved") : ""), () => Select(id));
                ToolTipService.SetToolTip(button, item.Text("purpose")); var context = new MenuFlyout(); var chart = new MenuFlyoutItem { Text = T("appmenu.org_chart") }; chart.Click += async (_, _) => await Run(() => ShowChart(id)); context.Items.Add(chart); button.ContextFlyout = context; row.Children.Add(button); side.Children.Add(row);
                if (selected && (!folded.Contains(id) || query.Length > 0))
                {
                    if (orgMatch || Match(T("common.group_chat"))) Chat("", T("common.group_chat"), LastLine("group").Length > 0 ? LastLine("group") : T("side.group_sub"), "");
                    var secretary = snap["org"].Text("secretary"); var sec = snap.Rows("members").FirstOrDefault(m => m.Text("name") == secretary);
                    if (secretary.Length == 0) side.Children.Add(Button(T("side.set_secretary") + "\n" + T("side.secretary_hint"), SecretarySetup));
                    else if (orgMatch || members.Contains(sec)) Chat(secretary, T("common.secretary") + " · " + Display(secretary), LastLine("member:" + secretary), sec.Text("avatar"), sec.Text("state"));
                    foreach (var m in (orgMatch ? snap.Rows("members").ToArray() : members).Where(m => !m.Flag("secretary")))
                        Chat(m.Text("name"), Display(m.Text("name")) + (m.Flag("leader") ? " · " + T("common.leader") : ""), m.Text("doing").Length > 0 ? T("side.doing", ("doing", m.Text("doing"))) : LastLine("member:" + m.Text("name")), m.Text("avatar"), m.Text("state"));
                    side.Children.Add(Button("+ " + T("common.add_member"), AddMember));
                }
            }
            if (folded.Contains(id) && query.Length == 0) return;
            foreach (var child in children) Node(child, depth + 1);
        }
        foreach (var item in orgs.Where(o => o.Text("parent").Length == 0 || !orgs.Any(p => p.Text("id") == o.Text("parent")))) Node(item, 0);
        // Corrupt cyclic references remain navigable rather than disappearing.
        foreach (var item in orgs) if (!visited.Contains(item.Text("id")) && !orgs.Any(o => folded.Contains(o.Text("id")))) Node(item, 0);
        if (orgs.Count == 0) side.Children.Add(Text(T("side.no_orgs")));
        var me = Button(Display("human") + " · " + T("side.profile"), Settings); ToolTipService.SetToolTip(me, T("page.me")); side.Children.Add(me);
        side.Children.Add(Button(T("chart.title"), Chart));
    }
    private async Task ShowCopies()
    {
        copiesBody = new StackPanel { Spacing = 16 }; var body = copiesBody; DrawCopies();
        await Show(T("cc.title"), body); if (copiesBody == body) copiesBody = null;
    }
    private void CopyNotifications()
    {
        var unread = copies.Where(c => !c.Flag("read")).Select(c => c.Text("id")).ToHashSet();
        if (!active && preferences.Flag("notify") && knownCopies != null && unread.Except(knownCopies).Any()) Notify(T("cc.notify", ("n", unread.Count)));
        knownCopies = unread;
    }
    private void DrawCopies()
    {
        if (copiesBody == null) return; var content = copiesBody; content.Children.Clear(); content.Children.Add(Text(T("cc.intro")));
        if (copies.Count == 0) content.Children.Add(Text(T("cc.empty")));
        foreach (var c in copies)
        {
            var card = new StackPanel { Spacing = 8 }; var live = c.Text("status") == "active" && c.Text("org_status") is "" or "active";
            card.Children.Add(Text(c.Text("org_name") + " · " + c.Text("protocol_id") + " " + c.Text("title"), 18));
            card.Children.Add(Text((c.Flag("read") ? "" : T("cc.unread") + " · ") + (c.Text("supersedes").Length > 0 ? T("cc.revision") + " · " : "") + CopyState(c!)));
            card.Children.Add(Rich(c.Text("summary")));
            card.Children.Add(Text(T(c?["issued_by"].Text("member").Length > 0 ? "cc.issued_by" : "cc.proposed_by", ("name", c.Text("author_display"))), 12));
            if (c.Rows("approved_display").Count > 0) card.Children.Add(Text(T("cc.approved_by", ("names", words.List(c.Rows("approved_display").Select(n => n.Text())))), 12));
            if (c.Text("activated_at").Length > 0) card.Children.Add(Text(T("cc.effective", ("when", When(c.Text("activated_at")))), 12));
            if (c.Text("supersedes").Length > 0) card.Children.Add(Text(T("cc.replaces", ("id", c.Text("supersedes"))), 12));
            var stats = c?["stats"];
            card.Children.Add(Text(stats.Text("total") is "" or "0" ? T("cc.stats_none") : T("cc.stats", ("n", stats.Text("total")), ("allow", stats.Text("allow")), ("deny", stats.Text("deny")), ("review", stats.Text("review")), ("error", stats.Text("error")))));
            if (c.Rows("rules").Any(r => r.Text("effect") == "check")) card.Children.Add(CheckRules(c.Rows("rules")));
            if (!c.Flag("read")) card.Children.Add(Button(T("cc.ack"), async () => { await api!.Post("/api/cc/" + c.Text("id") + "/read", new { }); await Refresh(); }));
            if (live) card.Children.Add(Button(T("cc.retire"), async () =>
            {
                if (!await Confirm(T("cc.retire_confirm", ("id", c.Text("protocol_id")), ("title", c.Text("title")), ("org", c.Text("org_name"))))) return;
                try { await api!.Post("/api/cc/" + c.Text("id") + "/retire", new { }); await Refresh(); Note(T("cc.retired", ("id", c.Text("protocol_id")), ("title", c.Text("title")))); await ShowCopies(); }
                catch (Exception ex) { Note(T("cc.retire_failed", ("error", ex.Message))); }
            }));
            content.Children.Add(card);
        }
    }
    private string CopyState(JsonNode c) => c.Text("org_status") is not ("" or "active") ? T("cc.status_ended") : c.Text("status") == "active" ? T("cc.status_active") : c.Text("status") == "retired" && c.Text("retired_by") == "human" ? T("cc.status_retired_person") : c.Text("status") == "superseded" ? T("cc.status_superseded", ("id", c.Text("superseded_by"))) : T("cc.status_retired");
}
