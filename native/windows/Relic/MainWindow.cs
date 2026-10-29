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

public sealed partial class MainWindow : Window
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

    private readonly InfoBar error = new() { Severity = InfoBarSeverity.Error, IsClosable = true };
    private readonly ScrollViewer chatScroll;
    private readonly StackPanel chatHead = new() { Orientation = Orientation.Horizontal, Spacing = 10 };
    private readonly MenuBar menu = new();
    private Button? sendButton;
    private readonly DispatcherTimer refreshTimer = new() { Interval = TimeSpan.FromMilliseconds(350) };
    private bool refreshing, pending, closing, ready;
    private readonly Dictionary<string, HashSet<string>> lastDecisions = new();
    private readonly Dictionary<string, string> lastMessages = new();
    private bool active = true;

    private string T(string key, params (string, object)[] args) => words.T(key, args);
    private string PathFor(string action = "") => Client.Org(org, action);
    private TextBlock Text(string value, double size = 14) => new() { Text = value, TextWrapping = TextWrapping.Wrap, FontSize = size * (preferences.Text("font") == "large" ? 1.18 : preferences.Text("font") == "small" ? .86 : 1), IsTextSelectionEnabled = true };
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
        catch (Exception ex) { error.Severity = InfoBarSeverity.Error; error.Message = ex.Message; error.IsOpen = true; }
    }

    public MainWindow()
    {
        Title = "Relic";
        Activated += (_, e) => active = e.WindowActivationState != WindowActivationState.Deactivated;
        AppWindow.Resize(new Windows.Graphics.SizeInt32(1480, 940));
        root.RowDefinitions.Add(new() { Height = GridLength.Auto });
        root.RowDefinitions.Add(new() { Height = GridLength.Auto });
        root.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        root.Children.Add(menu); Grid.SetRow(error, 1); root.Children.Add(error);

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
        recipientButton = Button("", PickRecipients); compose.Children.Add(recipientButton); compose.Children.Add(quoteLabel); compose.Children.Add(Button("×", () => { ClearQuote(); SaveViewState(); return Task.CompletedTask; })); compose.Children.Add(editor); compose.Children.Add(Microphone(editor));
        sendButton = Button("↵", Send); compose.Children.Add(sendButton);
        Grid.SetRow(compose, 2); chat.Children.Add(compose);
        Grid.SetColumn(chat, 1); columns.Children.Add(chat);
        var right = Scroll(detail); Grid.SetColumn(right, 2); columns.Children.Add(right);
        Grid.SetRow(columns, 2); root.Children.Add(columns); Content = root; Resizers(); WireComposer(); NavigationShortcuts();
        root.GotFocus += (_, e) => { if (e.OriginalSource is TextBox box) editing = box; };
        threadEditor.TextChanged += (_, _) => { drafts[org + "/thread/" + threadId] = threadEditor.Text; SaveViewState(); };
        search.TextChanged += (_, _) => { if (ready) DrawSide(); };
        editor.TextChanged += (_, _) => { drafts[org + "/" + member] = editor.Text; SaveViewState(); };
        AddShortcut(VirtualKey.Enter, VirtualKeyModifiers.Control, Send);
        AddShortcut(VirtualKey.N, VirtualKeyModifiers.Control, CreateOrg);
        AddShortcut((VirtualKey)188, VirtualKeyModifiers.Control, Settings);
        AddShortcut(VirtualKey.F, VirtualKeyModifiers.Control, () => { search.Focus(FocusState.Keyboard); return Task.CompletedTask; });
        refreshTimer.Tick += async (_, _) => { refreshTimer.Stop(); await Run(Refresh); };
        Closed += async (_, e) =>
        {
            if (closing) return;
            e.Handled = true; SaveViewState(); closing = true; ready = false; lifetime.Cancel(); refreshTimer.Stop();
            await StopVoice(); await host.DisposeAsync(); api?.Dispose(); Close();
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
                LoadViewState(); ready = true; LayoutColumns();
                AppNotificationManager.Default.NotificationInvoked += (_, _) => DispatcherQueue.TryEnqueue(Activate);
                AppNotificationManager.Default.Register();
                ApplyAppearance(); DrawMenu(); await Refresh();
                _ = api.Events(ev =>
                {
                    DispatcherQueue.TryEnqueue(async () =>
                    {
                        if (ev.Text("type") == "prefs") await Run(LoadPreferences);
                        if (ev.Text("type") == "install") InstallEvent(ev);
                        if (ev.Text("org") == org && ev.Text("type") == "plain")
                        {
                            GotPlain(ev["items"]);
                            foreach (var id in ev.Rows("ids")) if (!plain.ContainsKey(PlainKey(id.Text()))) { plainPending.Remove(PlainKey(id.Text())); if (ev.Text("error").Length > 0) plainFailed.Add(PlainKey(id.Text())); }
                        }
                        if (ev.Text("org") == org && ev.Text("type") == "digest") { digestPending = false; if (ev["digest"] != null) digest = ev["digest"]!.DeepClone(); if (ev.Text("error").Length > 0) Note(T("digest.failed", ("error", ev.Text("error")))); }
                        Schedule();
                    });
                    return Task.CompletedTask;
                }, lifetime.Token);
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
            if (org.Length > 0 && !orgs.Any(x => x.Text("id") == org)) { org = ""; member = ""; }
            if (org.Length == 0 && orgs.Count > 0) { org = orgs[0].Text("id"); selectedOrg = org; }
            if (org.Length > 0)
            {
                var snapshot = await api.Get(PathFor());
                var chat = await api.Get(PathFor("/chat?kind=" + (member.Length == 0 ? "group" : "private") + "&member=" + Client.Segment(member) + "&limit=" + chatLimit));
                if (org != selectedOrg || member != selectedMember) { pending = true; return; }
                snap = snapshot; messages = chat.Rows("items"); chatMore = chat.Flag("more");
                if (member.Length > 0)
                {
                    var m = snap.Rows("members").FirstOrDefault(x => x.Text("name") == member);
                    conversation = m.Flag("has_transcript") ? await api.Get(PathFor("/convo?member=" + Client.Segment(member) + "&limit=" + chatLimit)) : new JsonObject();
                    liveData = m.Flag("embedded") ? await api.Get(PathFor("/live?member=" + Client.Segment(member))) : new JsonObject();
                }
                else { conversation = new JsonObject(); liveData = new JsonObject(); }
                if (org != selectedOrg || member != selectedMember) { pending = true; return; }
                if (pane == "thread" && threadId.Length > 0) threadData = await api.Get(PathFor("/thread?root=" + Client.Segment(threadId)));
                var ids = snap.Rows("decisions").Select(d => d.Text("kind") + ":" + d.Text("id") + ":" + d.Text("member")).ToHashSet();
                if (!active && preferences.Flag("notify") && lastDecisions.TryGetValue(org, out var previous) && ids.Except(previous).Any()) Notify(T("notify.decisions", ("n", ids.Count)));
                lastDecisions[org] = ids;
                if (snap["chats"] is JsonObject heads)
                    foreach (var head in heads)
                    {
                        var key = org + "/" + head.Key; var id = head.Value?["last"].Text("id") ?? "";
                        if (!active && preferences.Flag("notify") && lastMessages.TryGetValue(key, out var old) && old != id && head.Value?["last"].Text("from") != "human") Notify(T("notify.new_messages"));
                        lastMessages[key] = id;
                    }
            }
            if (active) MarkSeen();
            DrawMenu(); DrawSide(); DrawChat(); DrawDetail();
            if (pane == "workspace") await Workspace();
        }
        finally { refreshing = false; if (pending) Schedule(); }
    }
    private async Task Select(string id, string who = "", bool fromHistory = false)
    {
        RememberChat(); var different = org != id; org = id; member = who; conversation = new JsonObject(); liveData = new JsonObject(); messages = new JsonArray();
        if (different) { digest = new JsonObject(); threadId = ""; if (pane == "thread") pane = previousPane; directory = ""; workspaceMember = ""; }
        RestoreChat(); if (!fromHistory) PushHistory(); folded.Remove(id); SaveViewState();
        await Refresh();
    }
    private void DrawMenu() => BuildMenus();
    private async Task LoadPreferences()
    {
        preferences = await api!.Get("/api/prefs");
        var language = Words.Normalize(preferences.Text("lang"));
        words.Load(await api.Get("/api/i18n?lang=" + language)); DrawMenu();
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
        }
        side.Children.Add(Button(T("cc.title"), Copies)); side.Children.Add(Button(T("chart.title"), Chart)); side.Children.Add(Button(T("common.settings"), Settings));
    }
    private void DrawChat() => DrawConversation();
    private void ToBottom(object sender, RoutedEventArgs e) { stream.Loaded -= ToBottom; chatScroll.ChangeView(null, chatScroll.ScrollableHeight, null); }
    private async Task Send()
    {
        if (api == null || org.Length == 0 || string.IsNullOrWhiteSpace(editor.Text)) return;
        var body = editor.Text; var destination = PathFor("/send"); var key = org + "/" + member;
        var payload = Composer.Message(Quoted(body), member, recipientNames.ToArray(), snap.Rows("members"));
        await api.Post(destination, payload);
        drafts[key] = ""; if (key == org + "/" + member && editor.Text == body) { editor.Text = ""; ClearQuote(); recipientNames.Clear(); recipientNames.Add("all"); SaveViewState(); }
        await Refresh(); chatScroll.ChangeView(null, chatScroll.ScrollableHeight, null);
    }
    private async Task Post(string action, object value) { await api!.Post(PathFor(action), value); await Refresh(); }

    private void DrawDetail()
    {
        detail.Children.Clear();
        var tabs = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4 };
        foreach (var (id, key) in new[] { ("overview", "panel.overview"), ("workspace", "panel.workspace"), ("files", "common.file") })
            tabs.Children.Add(Button(T(key), () => SetPane(id)));
        detail.Children.Add(tabs);
        switch (pane)
        {
            case "thread": DrawThread(); break;
            case "workspace": detail.Children.Add(workspaceBody); break;
            case "files": DrawFile(); break;
            default: DrawOverview(); break;
        }
    }
    private async Task Show(string title, UIElement content)
    {
        var dialog = new ContentDialog { XamlRoot = root.XamlRoot, Title = title, Content = Scroll(content), CloseButtonText = T("common.close") };
        await Dialog(dialog);
    }
    private async Task Form(string title, StackPanel form, Func<Task> submit, string? submitText = null)
    {
        var message = Text(""); form.Children.Add(message);
        var dialog = new ContentDialog { XamlRoot = root.XamlRoot, Title = title, Content = Scroll(form), PrimaryButtonText = submitText ?? T("common.save"), CloseButtonText = T("common.cancel") };
        dialog.PrimaryButtonClick += async (_, e) =>
        {
            var hold = e.GetDeferral();
            try { await submit(); }
            catch (Exception ex) { message.Text = ex.Message; e.Cancel = true; }
            finally { hold.Complete(); }
        };
        await Dialog(dialog);
    }
    private TextBox Field(StackPanel form, string key, bool multiline = false)
    {
        var field = new TextBox { Header = T(key), AcceptsReturn = multiline, TextWrapping = TextWrapping.Wrap };
        form.Children.Add(field); if (preferences.Text("voice") != "off") form.Children.Add(Microphone(field)); return field;
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
        name.PlaceholderText = T("neworg.name_placeholder"); purpose.PlaceholderText = T("neworg.purpose_placeholder");
        var governance = Choice(form, "neworg.governance", [("leader", T("neworg.gov_leader")), ("peer", T("neworg.gov_peer"))]);
        var created = false;
        await Form(T("common.new_org"), form, async () =>
        {
            if (string.IsNullOrWhiteSpace(name.Text)) throw new ArgumentException(T("neworg.need_name"));
            var result = await api!.Post("/api/orgs", new { name = name.Text.Trim(), purpose = purpose.Text, governance = Value(governance) });
            await Select(result.Text("org_id"));
            created = true;
        }, T("neworg.create"));
        if (created) await MemberDialog(secretary: true);
    }
    private Task AddMember() => MemberDialog();
    private async Task IssueProtocol()
    {
        var form = new StackPanel { Spacing = 10 };
        var title = Field(form, "native.protocol_title"); var rationale = Field(form, "native.protocol_rationale", true);
        var trigger = Field(form, "native.protocol_trigger"); var guidance = Field(form, "native.protocol_guidance", true);
        var inherit = new CheckBox { Content = T("org.protocol_inherits") }; form.Children.Add(inherit);
        await Form(T("org.protocols"), form, () => Post("/protocols", new { title = title.Text, rationale = rationale.Text, trigger = trigger.Text, guidance = guidance.Text, strength = "weak", inherit = inherit.IsChecked == true }));
    }
    private async Task Copies()
    {
        var content = new StackPanel { Spacing = 16 }; content.Children.Add(Text(T("cc.intro")));
        foreach (var c in copies)
        {
            content.Children.Add(Text(c.Text("org_name") + " · " + c.Text("title"), 18)); content.Children.Add(Text(c.Text("summary")));
            content.Children.Add(Text(c.Text("author_display") + " · " + c.Text("status")));
            var stats = c?["stats"];
            content.Children.Add(Text(stats.Text("total") is "" or "0" ? T("cc.stats_none") : T("cc.stats", ("n", stats.Text("total")), ("allow", stats.Text("allow")), ("deny", stats.Text("deny")), ("review", stats.Text("review")), ("error", stats.Text("error")))));
            var rules = new StackPanel { Spacing = 8 };
            foreach (var rule in c.Rows("rules")) rules.Children.Add(Text(rule?.ToJsonString(new() { WriteIndented = true }) ?? ""));
            content.Children.Add(new Expander { Header = T("cc.code"), Content = rules });
            content.Children.Add(Button(T("cc.ack"), async () => { await api!.Post("/api/cc/" + c.Text("id") + "/read", new { }); await Refresh(); }));
            if (c.Text("status") == "active" && c.Text("org_status") is "" or "active")
            {
                var confirm = new CheckBox { Content = T("cc.retire_confirm", ("id", c.Text("protocol_id")), ("title", c.Text("title")), ("org", c.Text("org_name"))) }; content.Children.Add(confirm);
                content.Children.Add(Button(T("cc.retire"), async () => { if (confirm.IsChecked != true) return; await api!.Post("/api/cc/" + c.Text("id") + "/retire", new { }); await Refresh(); }));
            }
        }
        await Show(T("cc.title"), content);
    }
    private Task Settings() => SettingsScreen();
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
