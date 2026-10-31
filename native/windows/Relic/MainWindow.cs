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
    private JsonArray orgs = new(), messages = new();
    private readonly CopyInbox copyInbox = new();
    private JsonArray copies => copyInbox.Items;
    private JsonNode snap = new JsonObject(), preferences = new JsonObject();
    private string org = "", member = "", pane = "overview";
    private readonly HashSet<string> folded = new();
    private readonly Dictionary<string, string> drafts = new();
    private readonly NativeWindowLayout root = new();
    private readonly NativeRegionGrid titlebarRegion = new(), treeRegion = new(), chatRegion = new();
    private readonly NativeRegionGrid composerRegion = new() { Padding = new Thickness(0, 6, 0, 16) };
    private readonly VirtualRows side = new() { TraceName = "sidebar", Spacing = 2, Padding = new Thickness(8) };
    private readonly VirtualRows detail = new() { TraceName = "inspector", Spacing = 14, Padding = new Thickness(16) };
    private readonly VirtualRows stream = new() { TraceName = "conversation", Padding = new Thickness(20, 8, 20, 24), MaxWidth = 920, HorizontalAlignment = HorizontalAlignment.Stretch };
    private readonly ComposerInput editor = new();
    private readonly TextBox search = new();
    private readonly StackPanel sideTools = new() { Padding = new Thickness(8, 10, 8, 6) };
    private readonly Grid searchSurface = new();
    private readonly System.Runtime.CompilerServices.ConditionalWeakTable<TextBox, Grid> fieldSurfaces = new();

    private readonly InfoBar error = new() { Severity = InfoBarSeverity.Error, IsClosable = true };
    private readonly ScrollViewer chatScroll;
    private readonly Grid chatHead = new() { Height = 56, Padding = new Thickness(20, 0, 14, 0), ColumnSpacing = 12, BorderThickness = new Thickness(0, 0, 0, 1) };
    private readonly StackPanel menu = new() { Orientation = Orientation.Horizontal };
    private readonly TextBlock appTitle = new() { FontSize = 12.5, TextWrapping = TextWrapping.NoWrap, TextTrimming = TextTrimming.CharacterEllipsis, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center, IsHitTestVisible = false };
    private Button? sendButton;
    private readonly DispatcherTimer refreshTimer = new() { Interval = TimeSpan.FromMilliseconds(350) };
    private bool refreshing, pending, closing, ready, sending, sendingThread;
    private TaskCompletionSource? refreshCompletion;
    private string renderedView = "";
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
        if (label.Length > 0) Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(button, label);
        button.Click += async (_, _) => { button.IsEnabled = false; await Run(action); button.IsEnabled = true; if (button == sendButton) UpdateSendState(); };
        return button;
    }
    private static ScrollViewer Scroll(UIElement content) => new() { Content = content, Style = (Style)Application.Current.Resources["RelicScrollViewerStyle"], VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, HorizontalScrollMode = ScrollMode.Disabled };
    private async Task Run(Func<Task> action)
    {
        if (PerformanceEnabled) Interlocked.Increment(ref performanceCommands);
        try { await action(); }
        catch (OperationCanceledException) when (lifetime.IsCancellationRequested) { }
        catch (Exception ex) { VisualStartupFailed(ex); error.Severity = InfoBarSeverity.Error; error.Message = ex.Message; error.IsOpen = true; }
        finally { if (PerformanceEnabled) Interlocked.Decrement(ref performanceCommands); }
    }

    public MainWindow()
    {
        VisualStartup("constructing window");
        Title = "Relic";
        ExtendsContentIntoTitleBar = true;
        // Global accelerators belong to the window. Their automatic tooltip
        // must not appear over unrelated controls; menus and buttons supply
        // their own localized shortcut labels/tooltips.
        root.KeyboardAcceleratorPlacementMode = KeyboardAcceleratorPlacementMode.Hidden;
        SystemBackdrop = new MicaBackdrop();
        Activated += (_, e) => { active = e.WindowActivationState != WindowActivationState.Deactivated; if (active && ready) { MarkSeen(); SaveViewState(); DrawSide(); } };
        root.RowDefinitions.Add(new() { Height = GridLength.Auto });
        root.RowDefinitions.Add(new() { Height = GridLength.Auto });
        root.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        var top = titlebarRegion; top.Height = 40; top.BorderThickness = new Thickness(0, 0, 0, 1); top.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); top.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); top.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); top.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        void PaintToolbarSurface() { top.BorderBrush = Line; top.Background = Paint("F8F7F5", "191918"); }
        top.Loaded += (_, _) => PaintToolbarSurface(); root.ActualThemeChanged += (_, _) => PaintToolbarSurface();
        top.Children.Add(navigationButtons); Grid.SetColumn(menu, 1); top.Children.Add(menu); Grid.SetColumn(toolbar, 3); top.Children.Add(toolbar); root.Children.Add(top); Grid.SetRow(error, 1); root.Children.Add(error);
        // Only the title gives up space as the window narrows. Navigation,
        // menus and commands stay outside the system caption-button inset.
        Grid.SetColumn(appTitle, 2); top.Children.Add(appTitle);
        root.Resources["ContentDialogMaxWidth"] = 1100d;

        columns.ColumnDefinitions.Add(new() { Width = new GridLength(276) });
        columns.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star), MinWidth = 0 });
        columns.ColumnDefinitions.Add(new() { Width = new GridLength(340) });
        var sideLayout = new Grid(); sideLayout.RowDefinitions.Add(new() { Height = GridLength.Auto }); sideLayout.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) }); sideLayout.RowDefinitions.Add(new() { Height = GridLength.Auto });
        sideLayout.Children.Add(sideTools); var treeScroll = Scroll(side); treeRegion.Children.Add(treeScroll); Grid.SetRow(treeRegion, 1); sideLayout.Children.Add(treeRegion); Grid.SetRow(sidebarFooter, 2); sideLayout.Children.Add(sidebarFooter);
        sidebarSurface.Child = sideLayout; sidebarSurface.BorderThickness = new Thickness(0, 0, 1, 0); columns.Children.Add(sidebarSurface);
        var chat = chatRegion;
        chat.RowDefinitions.Add(new() { Height = GridLength.Auto });
        chat.RowDefinitions.Add(new() { Height = GridLength.Auto });
        chat.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        chat.RowDefinitions.Add(new() { Height = GridLength.Auto });
        chat.Children.Add(chatHead);
        Grid.SetRow(conversationBanner, 1); chat.Children.Add(conversationBanner);
        chatScroll = Scroll(stream); Grid.SetRow(chatScroll, 2); chat.Children.Add(chatScroll);
        Grid.SetRow(emptyConversation, 2); chat.Children.Add(emptyConversation);
        var compose = new StackPanel { Spacing = 6 };
        quoteRow.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); quoteRow.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); quoteRow.Children.Add(quoteLabel); quoteRow.Visibility = Visibility.Collapsed;
        var cancelQuote = IconButton("\uE711", "composer.cancel_quote", () => { ClearQuote(); SaveViewState(); return Task.CompletedTask; }, iconSize: 14);
        cancelQuote.Width = cancelQuote.Height = 22; cancelQuote.VerticalAlignment = VerticalAlignment.Top;
        Grid.SetColumn(cancelQuote, 1); quoteRow.Children.Add(cancelQuote); compose.Children.Add(quoteRow); compose.Children.Add(editor);
        recipientButton = QuietButton("", PickRecipients); var composeActions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 }; composeActions.Children.Add(Microphone(editor));
        sendButton = IconButton("\uE74A", "common.send", Send); sendButton.Background = Ink; sendButton.Foreground = Paint("FFFFFF", "1F1F1E"); sendButton.Width = sendButton.Height = 32; sendButton.CornerRadius = new CornerRadius(16); sendButton.HorizontalContentAlignment = HorizontalAlignment.Center; sendButton.VerticalContentAlignment = VerticalAlignment.Center; sendButton.Padding = new Thickness(0); composeActions.Children.Add(sendButton);
        compose.Children.Add(TwoColumns(recipientButton, composeActions));
        composerSurface.Child = compose; composerSurface.Padding = new Thickness(14, 10, 10, 8); composerSurface.CornerRadius = new CornerRadius(18); composerSurface.BorderThickness = new Thickness(1);
        // Keep the shadow mask on the actual border box; outer spacing belongs
        // to the wrapper so growing text and quotes resize both together.
        var composerShadow = new NativeShadowPanel(composerSurface) { Margin = new Thickness(20, 0, 20, 0), MaxWidth = 880 };
        composerShadow.SetShadows([new NativeShadowLayer(0, 1, 2, Windows.UI.Color.FromArgb(255, 20, 18, 15), .06f)]);
        composerRegion.Children.Add(composerShadow); Grid.SetRow(composerRegion, 3); chat.Children.Add(composerRegion);
        Grid.SetColumn(chat, 1); columns.Children.Add(chat);
        inspector.RowDefinitions.Add(new() { Height = GridLength.Auto }); inspector.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) }); inspector.Children.Add(paneHeader);
        var right = Scroll(detail); Grid.SetRow(right, 1); inspector.Children.Add(right); inspectorSurface.Children.Add(inspector); inspectorSurface.BorderThickness = new Thickness(1, 0, 0, 0); Grid.SetColumn(inspectorSurface, 2); columns.Children.Add(inspectorSurface);
        Grid.SetRow(columns, 2); root.Children.Add(columns); Content = root; Resizers(); WireComposer(); NavigationShortcuts();
        ConfigureNativeTitleBar();
        root.SizeChanged += (_, _) => { appTitle.MaxWidth = root.ActualWidth * .4; LayoutColumns(); };
        root.GotFocus += (_, e) =>
        {
            if (e.OriginalSource is TextBox box) { editing = box; editingComposer = null; selectedRich = null; }
            else if (e.OriginalSource is ComposerInput composer) { editingComposer = composer; editing = null; selectedRich = null; }
        };
        threadEditor.TextChanged += (_, _) => { drafts[org + "/thread/" + threadId] = threadEditor.Text; UpdateSendState(); SaveViewState(); };
        search.TextChanged += (_, _) => { if (ready) DrawSide(); };
        editor.TextChanged += (_, _) => { drafts[org + "/" + member] = editor.Text; UpdateSendState(); SaveViewState(); };
        AddShortcut(VirtualKey.Enter, VirtualKeyModifiers.Control, () => pane == "thread" && threadEditor.FocusState != FocusState.Unfocused ? SendThread() : Send());
        AddShortcut(VirtualKey.N, VirtualKeyModifiers.Control, CreateOrg);
        AddShortcut((VirtualKey)188, VirtualKeyModifiers.Control, Settings);
        AddShortcut(VirtualKey.F, VirtualKeyModifiers.Control, () => { search.Focus(FocusState.Keyboard); return Task.CompletedTask; });
        refreshTimer.Tick += async (_, _) => { refreshTimer.Stop(); await Run(Refresh); };
        Closed += async (_, e) =>
        {
            if (closing) return;
            e.Handled = true; SaveViewState(); SaveWindowPlacement(); placementTimer.Stop(); closing = true; ready = false; lifetime.Cancel(); refreshTimer.Stop(); plainTimer.Stop();
            await viewStateWriter.DisposeAsync(); await windowStateWriter.DisposeAsync();
            await StopVoice(); await host.DisposeAsync(); api?.Dispose(); Close();
        };
        root.Loaded += async (_, _) =>
        {
            if (api != null) return;
            await Run(async () =>
            {
                VisualStartup("starting engine host");
                var engine = Environment.GetEnvironmentVariable("RELIC_ENGINE_ROOT") ?? AppContext.BaseDirectory;
                api = await host.Start(engine, Environment.GetEnvironmentVariable("RELIC_PYTHON") ?? "python");
                VisualStartup("loading preferences and capabilities");
                preferences = await api.Get("/api/prefs");
                platform = await api.Get("/api/platform");
                var language = Words.Normalize(preferences.Text("lang").Length > 0 ? preferences.Text("lang") : System.Globalization.CultureInfo.CurrentUICulture.Name);
                await api.Post("/api/prefs", new { lang = language });
                words.Load(await api.Get("/api/i18n?lang=" + language));
                LoadViewState();
                if (root.ActualWidth <= ResponsiveLayout.InspectorOverlayWidth) panelOpen = false;
                ready = true; LayoutColumns();
                VisualStartup("registering native notifications");
                AppNotificationManager.Default.NotificationInvoked += (_, _) => DispatcherQueue.TryEnqueue(Activate);
                try { AppNotificationManager.Default.Register(); }
                catch { notificationsAvailable = false; Note(T("settings.notify_unsupported")); }
                VisualStartup("loading organization and conversation");
                ApplyAppearance(); DrawMenu(); StartPerformanceProbe(); await Refresh();
                // The successfully opened startup conversation is the first
                // navigation entry, so the first later selection can go back.
                if (org.Length > 0) PushHistory();
                if (VisualCaptureEnabled) { _ = CaptureVisuals(); return; }
                if (PerformanceEnabled) _ = RunPerformanceScenario();
                _ = Task.Run(() => api.Events(ev =>
                {
                    var handled = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                    if (!DispatcherQueue.TryEnqueue(async () =>
                    {
                        try
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
                        }
                        finally { handled.TrySetResult(); }
                    })) handled.TrySetCanceled(lifetime.Token);
                    // Backpressure: never queue an unbounded number of UI
                    // callbacks. The refresh timer coalesces handled hints.
                    return handled.Task;
                }, lifetime.Token), lifetime.Token);
            });
        };
        ConfigureWindowPlacement();
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
        if (refreshing) { pending = true; if (refreshCompletion != null) await refreshCompletion.Task; return; }
        refreshing = true; pending = false;
        var completed = refreshCompletion = new(TaskCreationOptions.RunContinuationsAsynchronously);
        try
        {
            var selectedOrg = org; var selectedMember = member;
            var oldOrgs = orgs; var oldSnap = snap; var oldMessages = messages;
            var oldConversation = conversation; var oldLive = liveData; var oldThread = threadData;
            try { orgs = (await api.Get("/api/orgs")).Rows(); }
            catch (Exception ex) { throw new InvalidOperationException(T("boot.load_orgs_failed", ("error", ex.Message)), ex); }
            var newCopy = copyInbox.Update(await api.Get("/api/cc"));
            CopyNotifications(newCopy); DrawCopies();
            if (org.Length > 0 && !orgs.Any(x => x.Text("id") == org)) { org = ""; member = ""; }
            if (org.Length == 0 && orgs.Count > 0) { org = orgs[0].Text("id"); selectedOrg = org; }
            if (org.Length > 0)
            {
                var snapshot = await api.Get(PathFor());
                var chat = await api.Get(PathFor("/chat?kind=" + (member.Length == 0 ? "group" : "private") + "&member=" + Client.Segment(member) + "&limit=" + chatLimit));
                if (org != selectedOrg || member != selectedMember) { pending = true; return; }
                snap = snapshot;
                var loadedMessages = messages;
                var mergedMessages = olderHistory ? await Task.Run(() => Transcript.MergeMessages(loadedMessages, chat.Rows("items")), lifetime.Token) : chat.Rows("items");
                if (org != selectedOrg || member != selectedMember) { pending = true; return; }
                messages = mergedMessages;
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
            var nextOrgs = orgs; var nextSnap = snap; var nextMessages = messages;
            var nextConversation = conversation; var nextLive = liveData; var nextThread = threadData;
            var changes = await Task.Run(() => (
                Side: !JsonNode.DeepEquals(oldOrgs, nextOrgs) || !JsonNode.DeepEquals(oldSnap, nextSnap),
                Chat: !JsonNode.DeepEquals(oldMessages, nextMessages) || !JsonNode.DeepEquals(oldConversation, nextConversation)
                    || !JsonNode.DeepEquals(oldLive, nextLive),
                Detail: !JsonNode.DeepEquals(oldSnap, nextSnap) || !JsonNode.DeepEquals(oldThread, nextThread)), lifetime.Token);
            if (org != selectedOrg || member != selectedMember) { pending = true; return; }
            var viewChanged = renderedView != org + "/" + member;
            using (PerformanceTrace.Measure("DrawMenu")) if (viewChanged) DrawMenu();
            using (PerformanceTrace.Measure("DrawToolbar")) if (changes.Side || changes.Chat || changes.Detail || newCopy != null || viewChanged) DrawToolbar();
            using (PerformanceTrace.Measure("DrawSide")) if (changes.Side || viewChanged) DrawSide();
            await Task.Delay(1, lifetime.Token);
            if (org != selectedOrg || member != selectedMember) { pending = true; return; }
            using (PerformanceTrace.Measure("DrawChat")) if (changes.Chat || changes.Side || viewChanged) DrawChat();
            await Task.Delay(1, lifetime.Token);
            if (org != selectedOrg || member != selectedMember) { pending = true; return; }
            using (PerformanceTrace.Measure("DrawDetail")) if (changes.Detail || viewChanged) DrawDetail();
            renderedView = org + "/" + member;
            if (pane == "workspace" && changes.Detail) await Workspace();
            if (refreshChart != null && changes.Detail) await refreshChart();
        }
        finally { refreshing = false; completed.TrySetResult(); if (pending) Schedule(); }
    }
    private async Task Select(string id, string who = "", bool fromHistory = false)
    {
        transientFlyout?.Hide();
        await StopVoice();
        RememberChat(); var different = org != id; org = id; member = who; conversation = new JsonObject(); liveData = new JsonObject(); messages = new JsonArray();
        olderHistory = false; chatPages = 1;
        if (different) { digest = new JsonObject(); threadId = ""; if (pane == "thread") pane = previousPane; directory = ""; workspaceMember = ""; }
        RestoreChat(); if (!fromHistory) PushHistory();
        var reveal = id; var ancestors = new HashSet<string>();
        while (reveal.Length > 0 && ancestors.Add(reveal)) { folded.Remove(reveal); reveal = orgs.FirstOrDefault(o => o.Text("id") == reveal).Text("parent"); }
        SaveViewState();
        LayoutColumns();
        await Refresh();
        if (org != id || member != who) return;
        if (renderedView != id + "/" + who) await Refresh();
        if (org != id || member != who) return;
        if (different && digestOpen) await LoadDigest(false);
        ScrollToLatest();
    }
    private void DrawMenu() => BuildMenus();
    private async Task LoadPreferences()
    {
        preferences = await api!.Get("/api/prefs");
        var language = Words.Normalize(preferences.Text("lang"));
        if (language != words.Language) { plain.Clear(); plainPending.Clear(); plainFailed.Clear(); digest = new JsonObject(); }
        words.Load(await api.Get("/api/i18n?lang=" + language));
        // The reference sets document.documentElement.lang with its word list.
        // Native text shaping/fallback must use that same selected language,
        // including an already-open settings dialog outside the main tree.
        root.Language = words.Language;
        if (visibleDialog != null) visibleDialog.Language = words.Language;
        ApplyAppearance(); DrawMenu();
    }
    private void DrawSide() => DrawSidebar();
    private void DrawChat() => DrawConversation();
    private void ScrollToLatest()
    {
        // Finish this conversation's current layout before choosing its end.
        // A queued delay can outlive the action that requested the scroll: for
        // example, opening a file then narrows the chat and wraps a message.
        // Scrolling that later layout would move the reader past the position
        // retained when they opened the file (or started reading history).
        keepLatest = true;
        var request = ++latestRequest;
        stream.BringLastIntoView();
        _ = SettleLatest();
        async Task SettleLatest()
        {
            try
            {
                await WaitForMarkdown();
                if (!closing && keepLatest && request == latestRequest) stream.BringLastIntoView();
            }
            catch (TimeoutException) { /* Loading continues; never override a later user scroll. */ }
        }
    }
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
        detail.Padding = new Thickness(16); detail.Spacing = 14;
        paneHeader.Visibility = Visibility.Visible;
        DrawPaneHeader();
        if (org.Length == 0 && pane != "files") return;
        switch (pane)
        {
            case "thread": DrawThread(); break;
            case "workspace": DrawWorkspace(); break;
            case "files": DrawFile(); break;
            default: DrawOverview(); break;
        }
    }
    private async Task Show(string title, UIElement content, double width = 720)
    {
        var dialog = new NativeContentDialog { XamlRoot = root.XamlRoot };
        var requested = content is FrameworkElement element && !double.IsNaN(element.Width) ? element.Width : width;
        var layout = new Grid { RowSpacing = 20, Width = Math.Min(requested, Math.Max(400, root.ActualWidth - 96)) }; layout.RowDefinitions.Add(new() { Height = GridLength.Auto }); layout.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        layout.Children.Add(TwoColumns(Heading(title, 18), IconButton("\uE711", "common.close", () => { dialog.Hide(); return Task.CompletedTask; })));
        var scroll = Scroll(content); scroll.MaxHeight = Math.Max(320, root.ActualHeight - 180); Grid.SetRow(scroll, 1); layout.Children.Add(scroll); dialog.Content = layout;
        await Dialog(dialog);
    }
    private async Task Form(string title, StackPanel form, Func<Task> submit, string? submitText = null, double width = 520)
    {
        form.Width = Math.Max(0, Math.Min(width, root.ActualWidth - 32) - 44);
        form.Padding = new Thickness(0); form.Spacing = 12;
        var message = Text("", 12.5); message.Foreground = Paint("C2412D", "EE8A78"); message.Visibility = Visibility.Collapsed; form.Children.Add(message);
        var dialog = new NativeContentDialog { XamlRoot = root.XamlRoot, Title = title, Content = Scroll(form), PrimaryButtonText = submitText ?? T("common.save"), CloseButtonText = T("common.cancel"), DefaultButton = ContentDialogButton.Primary };
        dialog.PrimaryButtonClick += async (_, e) =>
        {
            var hold = e.GetDeferral();
            try { await submit(); }
            catch (Exception ex) { message.Text = ex.Message; message.Visibility = Visibility.Visible; e.Cancel = true; }
            finally { hold.Complete(); }
        };
        await Dialog(dialog);
    }
    private TextBox Field(StackPanel form, string key, bool multiline = false)
    {
        var voice = preferences.Text("voice") != "off";
        var field = new TextBox { Header = T(key), AcceptsReturn = multiline, TextWrapping = TextWrapping.Wrap, FontSize = 13,
            Height = multiline ? 101 : 61, MinHeight = 0, BorderThickness = new Thickness(1), BorderBrush = Paint("DEDBD4", "3A3936"), Background = Paint("FFFFFF", "1F1F1E"),
            CornerRadius = new CornerRadius(9), Padding = new Thickness(10, 7, voice ? 34 : 10, 7) };
        field.HeaderTemplate = (DataTemplate)Microsoft.UI.Xaml.Markup.XamlReader.Load("<DataTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation'><TextBlock Text='{Binding}' FontSize='12.5' LineHeight='20' LineStackingStrategy='BlockLineHeight' Foreground='{ThemeResource RelicControlSecondary}'/></DataTemplate>");
        field.Resources["TextControlHeaderMargin"] = new Thickness(0, 0, 0, 5);
        field.Resources["TextControlBorderThicknessFocused"] = new Thickness(1);
        var row = new Grid(); row.Children.Add(field);
        if (voice) { var mic = Microphone(field); mic.Width = mic.Height = 26; mic.MinHeight = 0; mic.Padding = new Thickness(4.5); mic.VerticalAlignment = VerticalAlignment.Bottom; mic.HorizontalAlignment = HorizontalAlignment.Right; mic.Margin = new Thickness(0, 0, 4, multiline ? 25 : 5); row.Children.Add(mic); }
        fieldSurfaces.Add(field, row); form.Children.Add(row); return field;
    }
    private FrameworkElement FieldSurface(TextBox field) => fieldSurfaces.TryGetValue(field, out var row) ? row : field;
    private ComboBox Choice(StackPanel form, string label, IEnumerable<(string, string)> options)
    {
        var box = new ComboBox { Header = T(label), HorizontalAlignment = HorizontalAlignment.Stretch, FontSize = 13, MinHeight = 32 };
        foreach (var (id, title) in options) { var option = new ComboBoxItem { Content = Ellipsis(title), Tag = id }; ToolTipService.SetToolTip(option, title); box.Items.Add(option); }
        box.SelectedIndex = box.Items.Count > 0 ? 0 : -1; form.Children.Add(box); return box;
    }
    private static string Value(ComboBox box) => (box.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "";
    private async Task CreateOrg()
    {
        var dialog = new NativeContentDialog { XamlRoot = root.XamlRoot }; var body = new StackPanel();
        body.Children.Add(OverviewText(T("common.new_org"), 17, weight: 650));
        var form = new StackPanel { Spacing = 12 };
        var name = FormInput("", T("neworg.name_placeholder")); var purpose = FormInput("", T("neworg.purpose_placeholder"), "new-org-purpose", multiline: true);
        form.Children.Add(FormLabel("common.name", SettingsVoiceField(name, double.NaN), name));
        form.Children.Add(FormLabel("neworg.purpose", SettingsVoiceField(purpose, double.NaN), purpose));
        var governance = FormSelect([("leader", T("neworg.gov_leader")), ("peer", T("neworg.gov_peer"))], "leader");
        form.Children.Add(FormLabel("neworg.governance", governance, governance)); body.Children.Add(form);
        var message = OverviewText("", 12.5); message.Foreground = Paint("C2412D", "EE8A78");
        var errorBox = new Border { Child = message, Height = 0 }; body.Children.Add(errorBox);
        var footer = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, HorizontalAlignment = HorizontalAlignment.Right };
        footer.Children.Add(FormAction(T("common.cancel"), () => { dialog.Hide(); return Task.CompletedTask; }));
        string? created = null;
        footer.Children.Add(FormAction(T("neworg.create"), async () =>
        {
            try
            {
                if (string.IsNullOrWhiteSpace(name.Text)) throw new ArgumentException(T("neworg.need_name"));
                var result = await api!.Post("/api/orgs", new { name = name.Text.Trim(), purpose = purpose.Text.Trim(), governance = Value(governance) });
                created = result.Text("org_id"); dialog.Hide();
            }
            catch (Exception ex) { message.Text = ex.Message; errorBox.Height = double.NaN; }
        }, true)); body.Children.Add(footer);
        await FormDialog(dialog, body, 520, name);
        if (created != null) { await Select(created); await MemberDialog(secretary: true); }
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
    private void Notify(string message, string title = "Relic")
    {
        if (!notificationsAvailable) { Note(T("settings.notify_unsupported")); return; }
        try { AppNotificationManager.Default.Show(new AppNotificationBuilder().AddText(title).AddText(message).BuildNotification()); }
        catch (Exception ex) { error.Message = T("settings.notify_denied") + " " + ex.Message; error.IsOpen = true; }
    }
    private Task Chart() => ShowChart();
}
