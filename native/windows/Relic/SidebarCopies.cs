using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Relic.Core;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private readonly CommandBar toolbar = new() { DefaultLabelPosition = CommandBarDefaultLabelPosition.Collapsed, IsOpen = false, OverflowButtonVisibility = CommandBarOverflowButtonVisibility.Collapsed, Height = 40 };
    private StackPanel? copiesBody;
    private HashSet<string>? knownCopies;
    private void DrawToolbar()
    {
        toolbar.PrimaryCommands.Clear();
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(toolbar, T("page.titlebar"));
        void Action(string glyph, string label, string tip, Func<Task> action, bool enabled = true)
        {
            var b = new AppBarButton { Icon = Glyph(glyph), Label = label, IsEnabled = enabled, Width = 38, Height = 36, IsCompact = true };
            ToolTipService.SetToolTip(b, tip); b.Click += async (_, _) => await Run(action); toolbar.PrimaryCommands.Add(b);
        }
        Action("\uE700", T("appmenu.sidebar"), T(sideOpen ? "appbar.hide_sidebar" : "appbar.show_sidebar"), ToggleSide);
        Action("\uE72B", T("appbar.back"), T("appbar.back"), () => Navigate(-1), historyIndex > 0);
        Action("\uE72A", T("appbar.forward"), T("appbar.forward"), () => Navigate(1), historyIndex + 1 < history.Count);
        var title = Ellipsis(snap["org"].Text("name"), 13); title.Margin = new Thickness(16, 8, 16, 0); title.Foreground = Muted; toolbar.Content = title;
        var count = snap.Rows("decisions").Count;
        Action("\uE7BA", T("decision.title"), T(count > 0 ? "appbar.decisions" : "appbar.no_decisions", ("n", count)), () => SetPane("overview"));
        var unread = copies.Count(c => !c.Flag("read"));
        Action("\uE715", T("cc.title"), T(unread > 0 ? "appbar.cc" : "appbar.cc_none", ("n", unread)), Copies);
        int i = 1;
        foreach (var (id, key, glyph) in new[] { ("overview", "panel.overview", "\uE8FD"), ("workspace", "panel.workspace", "\uE8B7"), ("files", "common.file", "\uE8A5") })
            Action(glyph, T(key), T("appbar.pane_shortcut", ("pane", T(key)), ("key", "Alt+" + i++)), () => pane == id && panelOpen ? TogglePanel() : SetPane(id));
    }
    private void DrawSidebar()
    {
        side.Children.Clear(); sidebarFooter.Children.Clear();
        var create = QuietButton(T("common.new_org"), CreateOrg); create.HorizontalAlignment = HorizontalAlignment.Stretch;
        side.Children.Add(create); search.Margin = new Thickness(2, 6, 2, 12); search.MinHeight = 30; search.FontSize = 12; side.Children.Add(search);
        var caption = Quiet(T("page.tree"), 11); caption.Margin = new Thickness(8, 6, 8, 8); side.Children.Add(caption);
        var list = new ListView { SelectionMode = ListViewSelectionMode.None, IsItemClickEnabled = true, HorizontalContentAlignment = HorizontalAlignment.Stretch, Padding = new Thickness(0) };
        list.ItemClick += async (_, e) => { if (e.ClickedItem is ListViewItem item && item.Tag is Func<Task> action) await Run(action); };
        side.Children.Add(list);
        var visited = new HashSet<string>(); var query = search.Text.Trim();
        bool Match(string value) => value.Contains(query, StringComparison.OrdinalIgnoreCase);
        void Add(UIElement content, Func<Task> action, bool selected, int indent = 0)
        {
            var item = new ListViewItem { Content = content, Tag = action, Padding = new Thickness(8 + indent, 6, 8, 6), Margin = new Thickness(0, 1, 0, 1), MinHeight = 30, HorizontalContentAlignment = HorizontalAlignment.Stretch, CornerRadius = new CornerRadius(7), Background = selected ? Paint("E7E5DF", "2F2E2B") : new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.Transparent) };
            list.Items.Add(item);
        }
        void Chat(string who, string title, string subtitle, string avatar, string state = "")
        {
            var key = who.Length == 0 ? "group" : "member:" + who; var id = org;
            var row = new Grid { ColumnSpacing = 8 }; row.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
            row.Children.Add(SmallAvatar(avatar, who.Length == 0 ? "#" : title, state));
            var text = new StackPanel { Spacing = 1 }; text.Children.Add(Ellipsis(title + Unread(key), 13));
            if (subtitle.Length > 0) { var sub = Ellipsis(subtitle, 11); sub.Foreground = Muted; text.Children.Add(sub); }
            Grid.SetColumn(text, 1); row.Children.Add(text); ToolTipService.SetToolTip(row, title + "\n" + subtitle + (state.Length > 0 ? "\n" + MemberState(state) : ""));
            Add(row, () => Select(id, who), who == member, 14);
        }
        void Node(JsonNode? item, int depth)
        {
            var id = item.Text("id"); if (!visited.Add(id)) return;
            var selected = id == org; var members = selected ? snap.Rows("members").Where(m => Match(m.Text("name")) || Match(m.Text("display")) || Match(m.Text("role"))).ToArray() : [];
            var orgMatch = Match(item.Text("name")) || Match(item.Text("purpose")); var children = orgs.Where(o => o.Text("parent") == id).ToArray();
            if (query.Length == 0 || orgMatch || members.Length > 0)
            {
                var row = new Grid { ColumnSpacing = 4 }; row.ColumnDefinitions.Add(new() { Width = new GridLength(20) }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
                if (selected || children.Length > 0)
                {
                    var fold = IconButton(folded.Contains(id) ? "\uE76C" : "\uE70D", "page.tree", () => { if (!folded.Add(id)) folded.Remove(id); SaveViewState(); DrawSidebar(); return Task.CompletedTask; }); fold.Width = 20; fold.Height = 22; fold.Padding = new Thickness(2); row.Children.Add(fold);
                }
                var label = Ellipsis(item.Text("name")); label.FontWeight = Microsoft.UI.Text.FontWeights.SemiBold; Grid.SetColumn(label, 1); row.Children.Add(label); ToolTipService.SetToolTip(row, item.Text("purpose"));
                var context = new MenuFlyout(); var chart = new MenuFlyoutItem { Text = T("appmenu.org_chart") }; chart.Click += async (_, _) => await Run(() => ShowChart(id)); context.Items.Add(chart); row.ContextFlyout = context;
                Add(row, () => Select(id), false, Math.Min(depth, 8) * 10);
                if (selected && (!folded.Contains(id) || query.Length > 0))
                {
                    if (orgMatch || Match(T("common.group_chat"))) Chat("", T("common.group_chat"), LastLine("group").Length > 0 ? LastLine("group") : T("side.group_sub"), "");
                    var secretary = snap["org"].Text("secretary"); var sec = snap.Rows("members").FirstOrDefault(m => m.Text("name") == secretary);
                    if (secretary.Length == 0) Add(Quiet(T("side.set_secretary")), SecretarySetup, false, 14);
                    else if (orgMatch || members.Contains(sec)) Chat(secretary, T("common.secretary") + " · " + Display(secretary), LastLine("member:" + secretary), sec.Text("avatar"), sec.Text("state"));
                    foreach (var m in (orgMatch ? snap.Rows("members").ToArray() : members).Where(m => !m.Flag("secretary")))
                        Chat(m.Text("name"), Display(m.Text("name")), m.Text("doing").Length > 0 ? T("side.doing", ("doing", m.Text("doing"))) : LastLine("member:" + m.Text("name")), m.Text("avatar"), m.Text("state"));
                    Add(Quiet("+ " + T("common.add_member")), AddMember, false, 20);
                }
            }
            if (folded.Contains(id) && query.Length == 0) return;
            foreach (var child in children) Node(child, depth + 1);
        }
        foreach (var item in orgs.Where(o => o.Text("parent").Length == 0 || !orgs.Any(p => p.Text("id") == o.Text("parent")))) Node(item, 0);
        foreach (var item in orgs) if (!visited.Contains(item.Text("id")) && !orgs.Any(o => folded.Contains(o.Text("id")))) Node(item, 0);
        if (orgs.Count == 0) side.Children.Add(Quiet(T("side.no_orgs")));
        var profile = QuietButton(Display("human"), Settings); ToolTipService.SetToolTip(profile, T("side.profile"));
        sidebarFooter.Children.Add(TwoColumns(profile, IconButton("\uE713", "common.settings", Settings)));
        sidebarFooter.Children.Add(QuietButton(T("chart.title"), Chart));
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
            content.Children.Add(Card(card));
        }
    }
    private string CopyState(JsonNode c) => c.Text("org_status") is not ("" or "active") ? T("cc.status_ended") : c.Text("status") == "active" ? T("cc.status_active") : c.Text("status") == "retired" && c.Text("retired_by") == "human" ? T("cc.status_retired_person") : c.Text("status") == "superseded" ? T("cc.status_superseded", ("id", c.Text("superseded_by"))) : T("cc.status_retired");
}
