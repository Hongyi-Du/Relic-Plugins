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
    private readonly StackPanel side = new() { Spacing = 2, Padding = new Thickness(8) }, stream = new() { Spacing = 14, Padding = new Thickness(24, 16, 24, 16) }, detail = new() { Spacing = 14, Padding = new Thickness(16) };
    private readonly TextBox editor = new() { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = 60, MaxHeight = 180, BorderThickness = new Thickness(0), Padding = new Thickness(2, 4, 2, 8) };
    private readonly TextBox search = new();

    private readonly InfoBar error = new() { Severity = InfoBarSeverity.Error, IsClosable = true };
    private readonly ScrollViewer chatScroll;
    private readonly Grid chatHead = new() { Padding = new Thickness(20, 12, 20, 12), ColumnSpacing = 10 };
    private readonly MenuBar menu = new();
    private Button? sendButton;
    private readonly DispatcherTimer refreshTimer = new() { Interval = TimeSpan.FromMilliseconds(350) };
    private bool refreshing, pending, closing, ready, sending, sendingThread;
    private readonly Dictionary<string, HashSet<string>> lastDecisions = new();
    private readonly Dictionary<string, string> lastMessages = new();
    private bool active = true;
    private bool notificationsAvailable = true;

    private string T(string key, params (string, object)[] args) => words.T(key, args);
    private string PathFor(string action = "") => Client.Org(org, action);
    private TextBlock Text(string value, double size = 14) => new() { Text = value, Foreground = Ink, TextWrapping = TextWrapping.Wrap, FontSize = size * (preferences.Text("font") == "large" ? 1.107 : preferences.Text("font") == "small" ? .929 : 1), IsTextSelectionEnabled = true };
    private Button Button(string label, Func<Task> action)
    {
        var button = new Button { Content = new TextBlock { Text = label, TextWrapping = TextWrapping.Wrap, FontSize = 13 }, HorizontalAlignment = HorizontalAlignment.Left, HorizontalContentAlignment = HorizontalAlignment.Left, Padding = new Thickness(10, 5, 10, 5), MinWidth = 0, MinHeight = 28, CornerRadius = new CornerRadius(6) };
        button.Click += async (_, _) => { button.IsEnabled = false; await Run(action); button.IsEnabled = true; };
        return button;
    }
    private static ScrollViewer Scroll(UIElement content) => new() { Content = content, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, HorizontalScrollMode = ScrollMode.Disabled };
    private async Task Run(Func<Task> action)
    {
        try { await action(); }
        catch (OperationCanceledException) when (lifetime.IsCancellationRequested) { }
        catch (Exception ex) { error.Severity = InfoBarSeverity.Error; error.Message = ex.Message; error.IsOpen = true; }
    }

    public MainWindow()
    {
        Title = "Relic";
        SystemBackdrop = new MicaBackdrop();
        Activated += (_, e) => { active = e.WindowActivationState != WindowActivationState.Deactivated; if (active && ready) { MarkSeen(); SaveViewState(); DrawSide(); } };
        AppWindow.Resize(new Windows.Graphics.SizeInt32(1440, 900));
        root.RowDefinitions.Add(new() { Height = GridLength.Auto });
        root.RowDefinitions.Add(new() { Height = GridLength.Auto });
        root.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        var top = new Grid { Height = 40 }; top.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); top.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); top.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        top.Children.Add(navigationButtons); Grid.SetColumn(menu, 1); top.Children.Add(menu); Grid.SetColumn(toolbar, 2); top.Children.Add(toolbar); root.Children.Add(top); Grid.SetRow(error, 1); root.Children.Add(error);
        root.Resources["ContentDialogMaxWidth"] = 1100d;

        columns.ColumnDefinitions.Add(new() { Width = new GridLength(276) });
        columns.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star), MinWidth = 300 });
        columns.ColumnDefinitions.Add(new() { Width = new GridLength(320) });
        var sideLayout = new Grid(); sideLayout.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) }); sideLayout.RowDefinitions.Add(new() { Height = GridLength.Auto });
        sideLayout.Children.Add(Scroll(side)); Grid.SetRow(sidebarFooter, 1); sideLayout.Children.Add(sidebarFooter);
        sidebarSurface.Child = sideLayout; sidebarSurface.BorderThickness = new Thickness(0, 0, 1, 0); columns.Children.Add(sidebarSurface);
        var chat = new Grid();
        chat.RowDefinitions.Add(new() { Height = GridLength.Auto });
        chat.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        chat.RowDefinitions.Add(new() { Height = GridLength.Auto });
        chat.Children.Add(chatHead);
        chatScroll = Scroll(stream); Grid.SetRow(chatScroll, 1); chat.Children.Add(chatScroll);
        var compose = new StackPanel { Spacing = 4 };
        quoteRow.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); quoteRow.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); quoteRow.Children.Add(quoteLabel); quoteRow.Visibility = Visibility.Collapsed;
        var cancelQuote = IconButton("\uE711", "composer.cancel_quote", () => { ClearQuote(); SaveViewState(); return Task.CompletedTask; }); Grid.SetColumn(cancelQuote, 1); quoteRow.Children.Add(cancelQuote); compose.Children.Add(quoteRow); compose.Children.Add(editor);
        recipientButton = QuietButton("", PickRecipients); var composeActions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 }; composeActions.Children.Add(Microphone(editor));
        sendButton = IconButton("\uE74A", "common.send", Send); sendButton.Background = Accent; sendButton.Foreground = new SolidColorBrush(Colors.White); sendButton.CornerRadius = new CornerRadius(8); composeActions.Children.Add(sendButton);
        compose.Children.Add(TwoColumns(recipientButton, composeActions));
        composerSurface.Child = compose; composerSurface.Padding = new Thickness(12, 8, 12, 8); composerSurface.Margin = new Thickness(20, 10, 20, 18); composerSurface.CornerRadius = new CornerRadius(14); composerSurface.BorderThickness = new Thickness(1);
        Grid.SetRow(composerSurface, 2); chat.Children.Add(composerSurface);
        Grid.SetColumn(chat, 1); columns.Children.Add(chat);
        inspector.RowDefinitions.Add(new() { Height = GridLength.Auto }); inspector.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) }); inspector.Children.Add(paneHeader);
        var right = Scroll(detail); Grid.SetRow(right, 1); inspector.Children.Add(right); inspectorSurface.Child = inspector; inspectorSurface.BorderThickness = new Thickness(1, 0, 0, 0); Grid.SetColumn(inspectorSurface, 2); columns.Children.Add(inspectorSurface);
        Grid.SetRow(columns, 2); root.Children.Add(columns); Content = root; Resizers(); WireComposer(); NavigationShortcuts();
        root.SizeChanged += (_, _) => LayoutColumns();
        root.GotFocus += (_, e) => { if (e.OriginalSource is TextBox box) { editing = box; selectedRich = null; } };
        threadEditor.TextChanged += (_, _) => { drafts[org + "/thread/" + threadId] = threadEditor.Text; SaveViewState(); };
        search.TextChanged += (_, _) => { if (ready) DrawSide(); };
        editor.TextChanged += (_, _) => { drafts[org + "/" + member] = editor.Text; SaveViewState(); };
        AddShortcut(VirtualKey.Enter, VirtualKeyModifiers.Control, () => pane == "thread" && threadEditor.FocusState != FocusState.Unfocused ? SendThread() : Send());
        AddShortcut(VirtualKey.N, VirtualKeyModifiers.Control, CreateOrg);
        AddShortcut((VirtualKey)188, VirtualKeyModifiers.Control, Settings);
        AddShortcut(VirtualKey.F, VirtualKeyModifiers.Control, () => { search.Focus(FocusState.Keyboard); return Task.CompletedTask; });
        refreshTimer.Tick += async (_, _) => { refreshTimer.Stop(); await Run(Refresh); };
        Closed += async (_, e) =>
        {
            if (closing) return;
            e.Handled = true; SaveViewState(); closing = true; ready = false; lifetime.Cancel(); refreshTimer.Stop(); plainTimer.Stop();
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
                platform = await api.Get("/api/platform");
                var language = Words.Normalize(preferences.Text("lang").Length > 0 ? preferences.Text("lang") : System.Globalization.CultureInfo.CurrentUICulture.Name);
                await api.Post("/api/prefs", new { lang = language });
                words.Load(await api.Get("/api/i18n?lang=" + language));
                LoadViewState(); ready = true; LayoutColumns();
                AppNotificationManager.Default.NotificationInvoked += (_, _) => DispatcherQueue.TryEnqueue(Activate);
                try { AppNotificationManager.Default.Register(); }
                catch { notificationsAvailable = false; Note(T("settings.notify_unsupported")); }
                ApplyAppearance(); DrawMenu(); await Refresh();
                if (VisualCaptureEnabled) { _ = CaptureVisuals(); return; }
                _ = api.Events(ev =>
                {
                    DispatcherQueue.TryEnqueue(async () =>
                    {
                        if (ev.Text("type") == "prefs") await Run(LoadPreferences);
                        if (ev.Text("type") == "install") InstallEvent(ev);
                        if (ev.Text("type") == "plain")
                        {
                            GotPlain(ev["items"], ev.Text("org"));
                            foreach (var id in ev.Rows("ids")) { var key = ev.Text("org") + "/" + id.Text(); if (!plain.ContainsKey(key)) { plainPending.Remove(key); plainFailed.Add(key); } }
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
            try { orgs = (await api.Get("/api/orgs")).Rows(); }
            catch (Exception ex) { throw new InvalidOperationException(T("boot.load_orgs_failed", ("error", ex.Message)), ex); }
            copies = (await api.Get("/api/cc")).Rows("items");
            CopyNotifications(); DrawCopies();
            if (org.Length > 0 && !orgs.Any(x => x.Text("id") == org)) { org = ""; member = ""; }
            if (org.Length == 0 && orgs.Count > 0) { org = orgs[0].Text("id"); selectedOrg = org; }
            if (org.Length > 0)
            {
                var snapshot = await api.Get(PathFor());
                var chat = await api.Get(PathFor("/chat?kind=" + (member.Length == 0 ? "group" : "private") + "&member=" + Client.Segment(member) + "&limit=" + chatLimit));
                if (org != selectedOrg || member != selectedMember) { pending = true; return; }
                snap = snapshot;
                messages = olderHistory ? Transcript.MergeMessages(messages, chat.Rows("items")) : chat.Rows("items");
                if (!olderHistory) chatMore = chat.Flag("more");
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
            DrawMenu(); DrawToolbar(); DrawSide(); DrawChat(); DrawDetail();
            if (pane == "workspace") await Workspace();
            if (refreshChart != null) await refreshChart();
        }
        finally { refreshing = false; if (pending) Schedule(); }
    }
    private async Task Select(string id, string who = "", bool fromHistory = false)
    {
        await StopVoice();
        RememberChat(); var different = org != id; org = id; member = who; conversation = new JsonObject(); liveData = new JsonObject(); messages = new JsonArray();
        olderHistory = false;
        if (different) { digest = new JsonObject(); threadId = ""; if (pane == "thread") pane = previousPane; directory = ""; workspaceMember = ""; }
        RestoreChat(); if (!fromHistory) PushHistory();
        var reveal = id; var ancestors = new HashSet<string>();
        while (reveal.Length > 0 && ancestors.Add(reveal)) { folded.Remove(reveal); reveal = orgs.FirstOrDefault(o => o.Text("id") == reveal).Text("parent"); }
        SaveViewState();
        await Refresh();
        if (different && digestOpen) await LoadDigest(false);
        ScrollToLatest();
    }
    private void DrawMenu() => BuildMenus();
    private async Task LoadPreferences()
    {
        preferences = await api!.Get("/api/prefs");
        var language = Words.Normalize(preferences.Text("lang"));
        if (language != words.Language) { plain.Clear(); plainPending.Clear(); plainFailed.Clear(); digest = new JsonObject(); }
        words.Load(await api.Get("/api/i18n?lang=" + language)); ApplyAppearance(); DrawMenu();
    }
    private void DrawSide() => DrawSidebar();
    private void DrawChat() => DrawConversation();
    private void ScrollToLatest() => DispatcherQueue.TryEnqueue(async () => { await Task.Delay(40); stream.UpdateLayout(); chatScroll.ChangeView(null, chatScroll.ScrollableHeight, null, true); });
    private void ToBottom(object sender, RoutedEventArgs e) { stream.Loaded -= ToBottom; chatScroll.ChangeView(null, chatScroll.ScrollableHeight, null); }
    private async Task Send()
    {
        if (sending || api == null || org.Length == 0 || composing.Contains(editor) || (string.IsNullOrWhiteSpace(editor.Text) && quoteText.Length == 0)) return;
        sending = true;
        try
        {
        await StopVoice();
        var body = editor.Text; var destination = PathFor("/send"); var key = org + "/" + member;
        var payload = Composer.Message(Quoted(body.Trim()), member, recipientNames.ToArray(), snap.Rows("members"));
        try { await api.Post(destination, payload); } catch (Exception ex) { Note(T("composer.send_failed", ("error", ex.Message))); return; }
        drafts[key] = ""; if (key == org + "/" + member && editor.Text == body) { editor.Text = ""; ClearQuote(); recipientNames.Clear(); recipientNames.Add("all"); SaveViewState(); }
        await Refresh(); chatScroll.ChangeView(null, chatScroll.ScrollableHeight, null);
        }
        finally { sending = false; }
    }
    private async Task Post(string action, object value) { await api!.Post(PathFor(action), value); await Refresh(); }

    private void DrawDetail()
    {
        detail.Children.Clear();
        DrawPaneHeader();
        if (pane == "thread") detail.Children.Add(Text(T("panel.thread"), 18));
        switch (pane)
        {
            case "thread": DrawThread(); break;
            case "workspace": detail.Children.Add(workspaceBody); break;
            case "files": DrawFile(); break;
            default: DrawOverview(); break;
        }
    }
    private async Task Show(string title, UIElement content, double width = 720)
    {
        var dialog = new ContentDialog { XamlRoot = root.XamlRoot };
        var requested = content is FrameworkElement element && !double.IsNaN(element.Width) ? element.Width : width;
        var layout = new Grid { RowSpacing = 20, Width = Math.Min(requested, Math.Max(400, root.ActualWidth - 160)) }; layout.RowDefinitions.Add(new() { Height = GridLength.Auto }); layout.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        layout.Children.Add(TwoColumns(Heading(title, 18), IconButton("\uE711", "common.close", () => { dialog.Hide(); return Task.CompletedTask; })));
        var scroll = Scroll(content); scroll.MaxHeight = Math.Max(320, root.ActualHeight - 180); Grid.SetRow(scroll, 1); layout.Children.Add(scroll); dialog.Content = layout;
        await Dialog(dialog);
    }
    private async Task Form(string title, StackPanel form, Func<Task> submit, string? submitText = null)
    {
        form.Width = Math.Min(572, Math.Max(400, root.ActualWidth - 160));
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
        var field = new TextBox { Header = T(key), AcceptsReturn = multiline, TextWrapping = TextWrapping.Wrap, FontSize = 13, MinHeight = multiline ? 100 : 32, MaxHeight = multiline ? 220 : double.PositiveInfinity };
        var row = new Grid { ColumnSpacing = 4 }; row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); row.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); row.Children.Add(field);
        if (preferences.Text("voice") != "off") { var mic = Microphone(field); mic.VerticalAlignment = VerticalAlignment.Bottom; Grid.SetColumn(mic, 1); row.Children.Add(mic); }
        form.Children.Add(row); return field;
    }
    private ComboBox Choice(StackPanel form, string label, IEnumerable<(string, string)> options)
    {
        var box = new ComboBox { Header = T(label), HorizontalAlignment = HorizontalAlignment.Stretch, FontSize = 13, MinHeight = 32 };
        foreach (var (id, title) in options) { var option = new ComboBoxItem { Content = Ellipsis(title), Tag = id }; ToolTipService.SetToolTip(option, title); box.Items.Add(option); }
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
        var strength = Choice(form, "native.protocol_strength", [("weak", T("common.weak")), ("strong", T("common.strong"))]);
        var strong = new StackPanel { Spacing = 8, Visibility = Visibility.Collapsed }; form.Children.Add(strong);
        var rules = Field(strong, "native.protocol_rules", true); rules.Text = "[]"; strong.Children.Add(Text(T("native.protocol_rules_hint"), 12));
        var summary = Field(strong, "details.label_summary", true);
        strength.SelectionChanged += (_, _) => { strong.Visibility = Value(strength) == "strong" ? Visibility.Visible : Visibility.Collapsed; trigger.IsEnabled = guidance.IsEnabled = Value(strength) == "weak"; };
        var inherit = new CheckBox { Content = T("org.protocol_inherits") }; form.Children.Add(inherit);
        await Form(T("org.protocols"), form, () => Post("/protocols", new { title = title.Text, rationale = rationale.Text, trigger = trigger.Text, guidance = guidance.Text, strength = Value(strength), rules = Value(strength) == "strong" ? JsonNode.Parse(rules.Text)?.AsArray() : new JsonArray(), summary_for_person = summary.Text, inherit = inherit.IsChecked == true }));
    }
    private Task Copies() => ShowCopies();
    private Task Settings() => SettingsScreen();
    private void Notify(string message)
    {
        if (!notificationsAvailable) { Note(T("settings.notify_unsupported")); return; }
        try { AppNotificationManager.Default.Show(new AppNotificationBuilder().AddText("Relic").AddText(message).BuildNotification()); }
        catch (Exception ex) { error.Message = T("settings.notify_denied") + " " + ex.Message; error.IsOpen = true; }
    }
    private Task Chart() => ShowChart();
}
