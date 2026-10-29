using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Microsoft.Windows.AppNotifications;
using Microsoft.Windows.AppNotifications.Builder;
using Relic.Core;
using System.Text.Json.Nodes;
using Windows.System;

namespace Relic;

public sealed class MainWindow : Window
{
    private readonly ServerHost host = new();
    private readonly CancellationTokenSource lifetime = new();
    private readonly Words words = new();
    private Client? api;
    private JsonArray orgs = new(), messages = new(), copies = new();
    private JsonNode snap = new JsonObject(), preferences = new JsonObject();
    private string org = "", member = "", pane = "overview";
    private readonly HashSet<string> folded = new();
    private readonly Dictionary<string, string> drafts = new();
    private readonly Grid root = new();
    private readonly StackPanel side = new() { Spacing = 6 }, stream = new() { Spacing = 14 }, detail = new() { Spacing = 12 };
    private readonly TextBox editor = new() { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = 70, MaxHeight = 180 };
    private readonly TextBox search = new();
    private readonly ComboBox recipients = new();
    private readonly InfoBar error = new() { Severity = InfoBarSeverity.Error, IsClosable = true };
    private readonly ScrollViewer chatScroll;
    private readonly StackPanel chatHead = new() { Orientation = Orientation.Horizontal, Spacing = 10 };
    private readonly MenuBar menu = new();
    private readonly DispatcherTimer refreshTimer = new() { Interval = TimeSpan.FromMilliseconds(350) };
    private bool refreshing, pending, closing, ready;
    private string lastDecisionIds = "";

    private string T(string key, params (string, object)[] args) => words.T(key, args);
    private string PathFor(string action = "") => Client.Org(org, action);
    private static TextBlock Text(string value, double size = 14) => new() { Text = value, TextWrapping = TextWrapping.Wrap, FontSize = size, IsTextSelectionEnabled = true };
    private Button Button(string label, Func<Task> action)
    {
        var button = new Button { Content = label, HorizontalAlignment = HorizontalAlignment.Stretch };
        button.Click += async (_, _) => { button.IsEnabled = false; await Run(action); button.IsEnabled = true; };
        return button;
    }
    private static ScrollViewer Scroll(UIElement content) => new() { Content = content, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
    private async Task Run(Func<Task> action)
    {
        try { await action(); }
        catch (OperationCanceledException) when (lifetime.IsCancellationRequested) { }
        catch (Exception ex) { error.Message = ex.Message; error.IsOpen = true; }
    }

    public MainWindow()
    {
        Title = "Relic";
        AppWindow.Resize(new Windows.Graphics.SizeInt32(1480, 940));
        root.RowDefinitions.Add(new() { Height = GridLength.Auto });
        root.RowDefinitions.Add(new() { Height = GridLength.Auto });
        root.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        root.Children.Add(menu); Grid.SetRow(error, 1); root.Children.Add(error);
        var columns = new Grid { ColumnSpacing = 16, Padding = new Thickness(12) };
        columns.ColumnDefinitions.Add(new() { Width = new GridLength(260) });
        columns.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star), MinWidth = 300 });
        columns.ColumnDefinitions.Add(new() { Width = new GridLength(370) });
        var sideScroll = Scroll(side); columns.Children.Add(sideScroll);
        var chat = new Grid { RowSpacing = 12 };
        chat.RowDefinitions.Add(new() { Height = GridLength.Auto });
        chat.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        chat.RowDefinitions.Add(new() { Height = GridLength.Auto });
        chat.Children.Add(chatHead);
        chatScroll = Scroll(stream); Grid.SetRow(chatScroll, 1); chat.Children.Add(chatScroll);
        var compose = new StackPanel { Spacing = 6 };
        compose.Children.Add(recipients); compose.Children.Add(editor);
        var send = Button("↵", Send); compose.Children.Add(send);
        Grid.SetRow(compose, 2); chat.Children.Add(compose);
        Grid.SetColumn(chat, 1); columns.Children.Add(chat);
        var right = Scroll(detail); Grid.SetColumn(right, 2); columns.Children.Add(right);
        Grid.SetRow(columns, 2); root.Children.Add(columns); Content = root;
        search.TextChanged += (_, _) => { if (ready) DrawSide(); };
        editor.TextChanged += (_, _) => drafts[org + "/" + member] = editor.Text;
        AddShortcut(VirtualKey.Enter, VirtualKeyModifiers.Control, Send);
        AddShortcut(VirtualKey.N, VirtualKeyModifiers.Control, CreateOrg);
        AddShortcut((VirtualKey)188, VirtualKeyModifiers.Control, Settings);
        AddShortcut(VirtualKey.F, VirtualKeyModifiers.Control, () => { search.Focus(FocusState.Keyboard); return Task.CompletedTask; });
        refreshTimer.Tick += async (_, _) => { refreshTimer.Stop(); await Run(Refresh); };
        Closed += async (_, e) =>
        {
            if (closing) return;
            e.Handled = true; closing = true; ready = false; lifetime.Cancel(); refreshTimer.Stop();
            await host.DisposeAsync(); api?.Dispose(); Close();
        };
        root.Loaded += async (_, _) =>
        {
            if (api != null) return;
            await Run(async () =>
            {
                var engine = Environment.GetEnvironmentVariable("RELIC_ENGINE_ROOT") ?? AppContext.BaseDirectory;
                api = await host.Start(engine, Environment.GetEnvironmentVariable("RELIC_PYTHON") ?? "python");
                preferences = await api.Get("/api/prefs");
                var language = Words.Normalize(preferences.Text("lang").Length > 0 ? preferences.Text("lang") : System.Globalization.CultureInfo.CurrentUICulture.Name);
                await api.Post("/api/prefs", new { lang = language });
                words.Load(await api.Get("/api/i18n?lang=" + language));
                ready = true; send.Content = T("common.send"); search.PlaceholderText = T("page.search");
                DrawMenu(); await Refresh();
                _ = api.Events(_ => { DispatcherQueue.TryEnqueue(Schedule); return Task.CompletedTask; }, lifetime.Token);
            });
        };
    }

    private void AddShortcut(VirtualKey key, VirtualKeyModifiers modifiers, Func<Task> action)
    {
        var accelerator = new KeyboardAccelerator { Key = key, Modifiers = modifiers };
        accelerator.Invoked += async (_, e) => { e.Handled = true; if (ready) await Run(action); };
        root.KeyboardAccelerators.Add(accelerator);
    }
    private void Schedule() { pending = true; if (!refreshTimer.IsEnabled) refreshTimer.Start(); }
    private async Task Refresh()
    {
        if (api == null || closing) return;
        if (refreshing) { pending = true; return; }
        refreshing = true; pending = false;
        try
        {
            var selectedOrg = org; var selectedMember = member;
            orgs = (await api.Get("/api/orgs")).Rows();
            copies = (await api.Get("/api/cc")).Rows("items");
            if (org.Length == 0 && orgs.Count > 0) { org = orgs[0].Text("id"); selectedOrg = org; }
            if (org.Length > 0)
            {
                var snapshot = await api.Get(PathFor());
                var chat = await api.Get(PathFor("/chat?kind=" + (member.Length == 0 ? "group" : "private") + "&member=" + Client.Segment(member)));
                if (org != selectedOrg || member != selectedMember) { pending = true; return; }
                snap = snapshot; messages = chat.Rows("items");
                if (member.Length > 0)
                {
                    var live = await api.Get(PathFor("/live?member=" + Client.Segment(member)));
                    foreach (var item in live.Rows("items")) messages.Add(item?.DeepClone());
                }
                var ids = string.Join(",", snap.Rows("decisions").Select(d => d.Text("id")));
                if (lastDecisionIds.Length > 0 && ids != lastDecisionIds && preferences.Flag("notify")) Notify(T("appbar.decisions", ("n", snap.Rows("decisions").Count)));
                lastDecisionIds = ids;
            }
            DrawSide(); DrawChat(); DrawDetail();
        }
        finally { refreshing = false; if (pending) Schedule(); }
    }
    private async Task Select(string id, string who = "")
    {
        org = id; member = who; editor.Text = drafts.GetValueOrDefault(org + "/" + member, "");
        await Refresh();
    }
    private void DrawMenu()
    {
        menu.Items.Clear();
        var file = new MenuBarItem { Title = T("common.file") };
        foreach (var (key, action) in new (string, Func<Task>)[] { ("common.new_org", CreateOrg), ("common.add_member", AddMember), ("cc.title", Copies), ("chart.title", Chart), ("common.settings", Settings) })
        { var item = new MenuFlyoutItem { Text = T(key) }; item.Click += async (_, _) => await Run(action); file.Items.Add(item); }
        menu.Items.Add(file);
    }
    private void DrawSide()
    {
        side.Children.Clear(); side.Children.Add(Button(T("common.new_org"), CreateOrg)); side.Children.Add(search);
        var seen = new HashSet<string>();
        void Node(JsonNode? o, int depth)
        {
            var id = o.Text("id"); if (!seen.Add(id)) return;
            var children = orgs.Where(n => n.Text("parent") == id).ToArray();
            var row = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(Math.Min(depth, 8) * 12, 0, 0, 0) };
            row.Children.Add(Button(folded.Contains(id) ? "▸" : "▾", () => { if (!folded.Add(id)) folded.Remove(id); DrawSide(); return Task.CompletedTask; }));
            row.Children.Add(Button(o.Text("name") + (id == org ? " •" : ""), () => Select(id))); side.Children.Add(row);
            if (folded.Contains(id)) return;
            if (id == org)
            {
                side.Children.Add(Button("# " + T("common.group_chat"), () => Select(id)));
                foreach (var m in snap.Rows("members"))
                {
                    var name = m.Text("name");
                    side.Children.Add(Button("@ " + m.Text("display") + " · " + T("state." + m.Text("state")), () => Select(id, name)));
                }
                side.Children.Add(Button("+ " + T("common.add_member"), AddMember));
            }
            foreach (var child in children) Node(child, depth + 1);
        }
        var query = search.Text.Trim();
        if (query.Length > 0)
            foreach (var item in orgs.Where(x => x.Text("name").Contains(query, StringComparison.OrdinalIgnoreCase)))
                side.Children.Add(Button(item.Text("name"), () => Select(item.Text("id"))));
        else
        {
            foreach (var item in orgs.Where(x => x.Text("parent").Length == 0 || !orgs.Any(p => p.Text("id") == x.Text("parent")))) Node(item, 0);
            foreach (var item in orgs.Where(x => !seen.Contains(x.Text("id"))).ToArray()) Node(item, 0);
        }
        side.Children.Add(Button(T("cc.title"), Copies)); side.Children.Add(Button(T("chart.title"), Chart)); side.Children.Add(Button(T("common.settings"), Settings));
    }
    private void DrawChat()
    {
        chatHead.Children.Clear(); chatHead.Children.Add(Text(snap["org"].Text("name") + " · " + (member.Length == 0 ? T("common.group_chat") : member), 20));
        if (member.Length > 0) chatHead.Children.Add(Button(T("common.cancel"), () => Post("/cancel", new { member })));
        var atBottom = chatScroll.ScrollableHeight - chatScroll.VerticalOffset < 100;
        stream.Children.Clear();
        foreach (var item in messages)
        {
            var block = new StackPanel { Spacing = 4 };
            block.Children.Add(Text(item.Text("from") + "  " + item.Text("at"), 12));
            var body = item.Text("body"); if (body.Length == 0) body = item.Text("text");
            if (body.Length == 0) body = item.Text("title");
            block.Children.Add(Text(body)); stream.Children.Add(block);
        }
        if (atBottom) stream.Loaded += ToBottom;
        var selected = (recipients.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "all";
        recipients.Items.Clear(); recipients.Items.Add(new ComboBoxItem { Content = T("composer.all_members"), Tag = "all" });
        foreach (var m in snap.Rows("members")) recipients.Items.Add(new ComboBoxItem { Content = "@" + m.Text("display"), Tag = m.Text("name") });
        recipients.SelectedItem = recipients.Items.Cast<ComboBoxItem>().FirstOrDefault(x => x.Tag?.ToString() == selected) ?? recipients.Items[0];
        recipients.Visibility = member.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
        editor.PlaceholderText = member.Length == 0 ? T("composer.group_placeholder") : T("composer.dm_placeholder", ("name", member));
    }
    private void ToBottom(object sender, RoutedEventArgs e) { stream.Loaded -= ToBottom; chatScroll.ChangeView(null, chatScroll.ScrollableHeight, null); }
    private async Task Send()
    {
        if (api == null || org.Length == 0 || string.IsNullOrWhiteSpace(editor.Text)) return;
        var body = editor.Text; var destination = PathFor("/send"); var key = org + "/" + member;
        var payload = Composer.Message(body, member, [(recipients.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "all"], snap.Rows("members"));
        await api.Post(destination, payload);
        drafts[key] = ""; if (key == org + "/" + member && editor.Text == body) editor.Text = "";
        await Refresh(); chatScroll.ChangeView(null, chatScroll.ScrollableHeight, null);
    }
    private async Task Post(string action, object value) { await api!.Post(PathFor(action), value); await Refresh(); }

    private void DrawDetail()
    {
        detail.Children.Clear();
        var tabs = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4 };
        foreach (var (id, key) in new[] { ("overview", "panel.overview"), ("workspace", "panel.workspace"), ("files", "common.file") })
            tabs.Children.Add(Button(T(key), async () => { pane = id; DrawDetail(); if (id != "overview") await Workspace(); }));
        detail.Children.Add(tabs);
        if (pane != "overview") return;
        detail.Children.Add(Text(snap["org"].Text("purpose"), 16));
        detail.Children.Add(Text(T("appbar.decisions", ("n", snap.Rows("decisions").Count)), 18));
        foreach (var d in snap.Rows("decisions"))
        {
            var card = new StackPanel { Spacing = 6 };
            card.Children.Add(Text(string.Join("\n", new[] { d.Text("label"), d.Text("title"), d.Text("text"), d.Text("reason"), d.Text("error") }.Where(s => s.Length > 0))));
            if (d.Text("kind") == "permission")
                foreach (var option in d.Rows("options")) card.Children.Add(Button(option.Text("name"), async () => { await api!.Post("/api/permission/" + Client.Segment(d.Text("id")), new { option = option.Text("id") }); await Refresh(); }));
            else if (d.Text("kind") is "approval" or "trajectory")
                foreach (var decision in new[] { "approve", "deny" }) card.Children.Add(Button(T("decision." + decision), async () =>
                {
                    var result = await api!.Post(Client.Org(d.Text("org").Length > 0 ? d.Text("org") : org, d.Text("kind") == "approval" ? "/request" : "/trajectory_answer"), new { request_id = d.Text("id"), decision });
                    if (result.Text("status") == "failed") throw new InvalidOperationException(result.Text("error"));
                    await Refresh();
                }));
            else if (d.Text("member").Length > 0) card.Children.Add(Button(T("decision.open_chat"), () => Select(org, d.Text("member"))));
            detail.Children.Add(card);
        }
        detail.Children.Add(Text(T("org.members"), 18));
        foreach (var m in snap.Rows("members")) detail.Children.Add(Button(m.Text("display") + " · " + T("state." + m.Text("state")) + "\n" + m.Text("role") + "\n" + m.Text("doing"), () => Select(org, m.Text("name"))));
        detail.Children.Add(Text(T("common.tasks"), 18));
        foreach (var task in snap.Rows("tasks")) detail.Children.Add(Text(task.Text("id") + " " + task.Text("title") + "\n" + task.Text("owner") + " · " + T("task." + task.Text("status")) + "\n" + task.Text("report")));
        detail.Children.Add(Text(T("org.protocols"), 18)); detail.Children.Add(Button(T("org.add"), IssueProtocol));
        foreach (var key in new[] { "protocols", "inherited_protocols", "replaced_protocols" })
            foreach (var p in snap.Rows(key))
            {
                var content = new StackPanel { Spacing = 5 };
                content.Children.Add(Text(p.Text("guidance") + "\n" + p.Text("summary_for_person")));
                if (p.Text("from").Length > 0) content.Children.Add(Text(T("org.inherited_from", ("name", p.Text("from")))));
                if (p?["issued_by"] != null) content.Children.Add(Text(p["issued_by"].Flag("person") ? T("org.issued_by_person") : T("org.issued_by", ("name", p["issued_by"].Text("name")))));
                foreach (var rule in p.Rows("rules")) content.Children.Add(Text(rule?.ToJsonString(new() { WriteIndented = true }) ?? ""));
                detail.Children.Add(new Expander { Header = p.Text("id") + " " + p.Text("title") + " · " + p.Text("status"), Content = content, HorizontalAlignment = HorizontalAlignment.Stretch });
            }
    }

    private async Task Workspace()
    {
        if (org.Length == 0) return;
        var ws = await api!.Get(PathFor("/workspace?member=" + Client.Segment(member)));
        detail.Children.Add(Text(ws.Text("folder")));
        if (ws.Text("folder").Length > 0) await Files(ws.Text("folder"));
    }
    private async Task Files(string path)
    {
        var list = await api!.Get("/api/fs/list?path=" + Client.Segment(path));
        foreach (var entry in list.Rows("entries")) detail.Children.Add(Button(entry.Text("name"), async () =>
        {
            if (entry.Flag("dir")) { DrawDetail(); await Files(entry.Text("path")); }
            else { var file = await api.Get("/api/fs/read?path=" + Client.Segment(entry.Text("path"))); await Show(entry.Text("name"), Text(file.Text("text"))); }
        }));
    }

    private async Task Show(string title, UIElement content)
    {
        var dialog = new ContentDialog { XamlRoot = root.XamlRoot, Title = title, Content = Scroll(content), CloseButtonText = T("common.close") };
        await dialog.ShowAsync();
    }
    private async Task Form(string title, StackPanel form, Func<Task> submit)
    {
        var message = Text(""); form.Children.Add(message);
        var dialog = new ContentDialog { XamlRoot = root.XamlRoot, Title = title, Content = Scroll(form), PrimaryButtonText = T("common.save"), CloseButtonText = T("common.cancel") };
        dialog.PrimaryButtonClick += async (_, e) =>
        {
            var hold = e.GetDeferral();
            try { await submit(); }
            catch (Exception ex) { message.Text = ex.Message; e.Cancel = true; }
            finally { hold.Complete(); }
        };
        await dialog.ShowAsync();
    }
    private TextBox Field(StackPanel form, string key, bool multiline = false)
    {
        var field = new TextBox { Header = T(key), AcceptsReturn = multiline, TextWrapping = TextWrapping.Wrap };
        form.Children.Add(field); return field;
    }
    private ComboBox Choice(StackPanel form, string label, IEnumerable<(string, string)> options)
    {
        var box = new ComboBox { Header = T(label), HorizontalAlignment = HorizontalAlignment.Stretch };
        foreach (var (id, title) in options) box.Items.Add(new ComboBoxItem { Content = title, Tag = id });
        box.SelectedIndex = box.Items.Count > 0 ? 0 : -1; form.Children.Add(box); return box;
    }
    private static string Value(ComboBox box) => (box.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "";
    private async Task CreateOrg()
    {
        var form = new StackPanel { Spacing = 10 };
        var name = Field(form, "common.name"); var purpose = Field(form, "neworg.purpose", true);
        var governance = Choice(form, "neworg.governance", [("leader", T("neworg.gov_leader")), ("peer", T("neworg.gov_peer"))]);
        await Form(T("common.new_org"), form, async () =>
        {
            if (string.IsNullOrWhiteSpace(name.Text)) throw new ArgumentException(T("neworg.need_name"));
            var result = await api!.Post("/api/orgs", new { name = name.Text.Trim(), purpose = purpose.Text, governance = Value(governance) });
            await Select(result.Text("org_id"));
        });
    }
    private async Task AddMember()
    {
        if (org.Length == 0) return;
        var harnesses = await api!.Get("/api/harnesses"); var sessions = await api.Get("/api/sessions"); var options = await api.Get("/api/seat-options");
        var form = new StackPanel { Spacing = 10 };
        var mode = Choice(form, "member.where_run", [("app", T("member.run_app")), ("host", T("member.run_host")), ("existing", T("member.run_existing"))]);
        var name = Field(form, "member.name_label"); var role = Field(form, "common.role");
        var appFields = new StackPanel { Spacing = 8 }; form.Children.Add(appFields);
        var harness = Choice(appFields, "common.harness", harnesses.Rows().Where(h => h.Flag("available") && !h.Flag("later")).Select(h => (h.Text("id"), h.Text("title"))));
        var secretary = new CheckBox { Content = T("member.make_secretary") }; appFields.Children.Add(secretary);
        var hostFields = new StackPanel { Spacing = 8, Visibility = Visibility.Collapsed }; form.Children.Add(hostFields);
        var hostHarness = Choice(hostFields, "member.where_run", [("claude-code", "Claude Code"), ("codex", "Codex")]);
        var effort = Choice(hostFields, "member.effort", options.Rows("efforts").Select(x => (x.Text(), x.Text().Length == 0 ? T("common.default_effort") : x.Text())));
        var environment = Choice(hostFields, "member.environment", [("local", T("member.env_local")), ("worktree", T("member.env_worktree"))]);
        var permission = Choice(hostFields, "member.permission", options.Rows("claude_modes").Select(x => (x.Text(), x.Text())));
        hostHarness.SelectionChanged += (_, _) => { permission.Items.Clear(); foreach (var p in options.Rows(Value(hostHarness) == "codex" ? "codex_sandboxes" : "claude_modes")) permission.Items.Add(new ComboBoxItem { Content = p.Text(), Tag = p.Text() }); permission.SelectedIndex = 0; };
        var env = Field(hostFields, "member.env_vars", true); var start = new CheckBox { Content = T("member.start_now"), IsChecked = true }; hostFields.Children.Add(start);
        var existing = new StackPanel { Spacing = 8, Visibility = Visibility.Collapsed }; form.Children.Add(existing);
        var sessionList = sessions.Rows("sessions").Where(s => s.Text("harness") != "chatgpt").ToArray();
        var session = Choice(existing, "common.session", sessionList.Select((s, i) => (i.ToString(), s.Text("title") + " · " + s.Text("cwd"))));
        foreach (var problem in sessions.Rows("problems")) existing.Children.Add(Text(problem.Text()));
        var model = Field(form, "common.model"); var folder = Field(form, "common.work_folder");
        mode.SelectionChanged += (_, _) => { appFields.Visibility = Value(mode) == "app" ? Visibility.Visible : Visibility.Collapsed; hostFields.Visibility = Value(mode) == "host" ? Visibility.Visible : Visibility.Collapsed; existing.Visibility = Value(mode) == "existing" ? Visibility.Visible : Visibility.Collapsed; };
        var target = org;
        await Form(T("common.add_member"), form, async () =>
        {
            if (string.IsNullOrWhiteSpace(name.Text)) throw new ArgumentException(T("member.need_name"));
            if (Value(mode) == "existing")
            {
                if (session.SelectedIndex < 0) throw new ArgumentException(T("member.pick_session"));
                await api.Post(Client.Org(target, "/bind"), new { member = name.Text.Trim(), role = role.Text, session = sessionList[int.Parse(Value(session))] });
            }
            else if (Value(mode) == "app")
            {
                if (Value(harness).Length == 0) throw new ArgumentException(T("member.need_harness"));
                await api.Post(Client.Org(target, "/members"), new { name = name.Text.Trim(), role = role.Text, harness = Value(harness), model = model.Text, folder = folder.Text, secretary = secretary.IsChecked == true });
            }
            else await api.Post(Client.Org(target, "/seat"), new { name = name.Text.Trim(), role = role.Text, harness = Value(hostHarness), surface = "cli", model = model.Text, folder = folder.Text, effort = Value(effort), environment = Value(environment), permission = Value(permission), env = env.Text, start = start.IsChecked == true });
            await Select(target, name.Text.Trim());
        });
    }
    private async Task IssueProtocol()
    {
        var form = new StackPanel { Spacing = 10 }; var title = Field(form, "common.name"); var guidance = Field(form, "org.protocols", true);
        await Form(T("org.protocols"), form, () => Post("/protocols", new { title = title.Text, guidance = guidance.Text, strength = "weak" }));
    }
    private async Task Copies()
    {
        var content = new StackPanel { Spacing = 16 }; content.Children.Add(Text(T("cc.intro")));
        foreach (var c in copies)
        {
            content.Children.Add(Text(c.Text("org_name") + " · " + c.Text("title"), 18)); content.Children.Add(Text(c.Text("summary_for_person")));
            content.Children.Add(Text(c.Text("author_display") + " · " + c.Text("status")));
            content.Children.Add(Button(T("cc.ack"), async () => { await api!.Post("/api/cc/" + c.Text("id") + "/read", new { }); await Refresh(); }));
            if (c.Text("status") == "active")
            {
                var confirm = new CheckBox { Content = T("cc.retire_confirm", ("id", c.Text("protocol_id")), ("title", c.Text("title")), ("org", c.Text("org_name"))) }; content.Children.Add(confirm);
                content.Children.Add(Button(T("cc.retire"), async () => { if (confirm.IsChecked != true) return; await api!.Post("/api/cc/" + c.Text("id") + "/retire", new { }); await Refresh(); }));
            }
        }
        await Show(T("cc.title"), content);
    }
    private async Task Settings()
    {
        var form = new StackPanel { Spacing = 12 };
        var lang = Choice(form, "settings.language.title", [("zh-CN", "简体中文"), ("en-US", "English")]); lang.SelectedIndex = words.Language == "zh-CN" ? 0 : 1;
        var notify = new CheckBox { Content = T("settings.notify"), IsChecked = preferences.Flag("notify") }; form.Children.Add(notify);
        await Form(T("common.settings"), form, async () =>
        {
            preferences = await api!.Post("/api/prefs", new { lang = Value(lang), notify = notify.IsChecked == true });
            words.Load(await api.Get("/api/i18n?lang=" + Value(lang))); DrawMenu(); await Refresh();
        });
    }
    private void Notify(string message)
    {
        try { AppNotificationManager.Default.Show(new AppNotificationBuilder().AddText("Relic").AddText(message).BuildNotification()); }
        catch (Exception ex) { error.Message = T("settings.notify_denied") + " " + ex.Message; error.IsOpen = true; }
    }
    private async Task Chart()
    {
        var data = await api!.Get("/api/orgchart"); var nodes = data.Rows("orgs");
        var canvas = new Canvas { Width = Math.Max(800, nodes.Count * 240), Height = Math.Max(500, nodes.Count * 120), Background = new SolidColorBrush(Colors.Transparent) };
        var positions = new Dictionary<string, (double X, double Y)>(); int index = 0;
        foreach (var node in nodes)
        {
            int depth = 0; var parent = node.Text("parent"); var visited = new HashSet<string>();
            while (parent.Length > 0 && visited.Add(parent)) { depth++; parent = nodes.FirstOrDefault(n => n.Text("id") == parent).Text("parent"); }
            positions[node.Text("id")] = (depth * 240 + 20, index++ * 110 + 20);
        }
        foreach (var node in nodes)
        {
            var point = positions[node.Text("id")];
            if (positions.TryGetValue(node.Text("parent"), out var parent)) canvas.Children.Add(new Line { X1 = parent.X + 205, Y1 = parent.Y + 35, X2 = point.X, Y2 = point.Y + 35, Stroke = new SolidColorBrush(Colors.Gray), StrokeThickness = 2 });
            var button = Button(node.Text("name") + "\n" + node.Text("leader_display") + " · " + T("chart.decisions", ("n", node.Text("decisions"))), () => Select(node.Text("id")));
            button.Width = 205; button.Height = 90; Canvas.SetLeft(button, point.X); Canvas.SetTop(button, point.Y); canvas.Children.Add(button);
        }
        var scroll = new ScrollViewer { Content = canvas, ZoomMode = ZoomMode.Enabled, MinZoomFactor = .2f, MaxZoomFactor = 3, HorizontalScrollBarVisibility = ScrollBarVisibility.Auto, Height = 500, Width = 800 };
        canvas.ManipulationMode = ManipulationModes.TranslateX | ManipulationModes.TranslateY;
        canvas.ManipulationDelta += (_, e) => scroll.ChangeView(scroll.HorizontalOffset - e.Delta.Translation.X, scroll.VerticalOffset - e.Delta.Translation.Y, null);
        var content = new StackPanel { Spacing = 8 }; content.Children.Add(scroll);
        var bar = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        bar.Children.Add(Button(T("chart.zoom_in"), () => { scroll.ChangeView(null, null, Math.Min(3, scroll.ZoomFactor * 1.2f)); return Task.CompletedTask; }));
        bar.Children.Add(Button(T("chart.zoom_out"), () => { scroll.ChangeView(null, null, Math.Max(.2f, scroll.ZoomFactor / 1.2f)); return Task.CompletedTask; }));
        bar.Children.Add(Button(T("chart.fit"), () => { scroll.ChangeView(0, 0, Math.Clamp((float)(500 / canvas.Height), .2f, 1)); return Task.CompletedTask; })); content.Children.Add(bar);
        foreach (var shared in data.Rows("shared")) content.Children.Add(Text(T("chart.legend_shared") + " · " + string.Join(" ↔ ", shared.Rows("seats").Select(s => s.Text("org") + "/" + s.Text("member")))));
        await Show(T("chart.title"), content);
    }
}
