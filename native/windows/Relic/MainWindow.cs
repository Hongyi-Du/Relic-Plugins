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
    // The organization the current snapshot belongs to.
    private string snapOrg = "";
    private string org = "", member = "", pane = "overview";
    private readonly HashSet<string> folded = new();
    private readonly Dictionary<string, string> drafts = new();
    private readonly NativeWindowLayout root = new();
    private readonly NativeRegionGrid titlebarRegion = new(), treeRegion = new(), chatRegion = new();
    private readonly NativeRegionGrid composerRegion = new() { Padding = new Thickness(0, 6, 0, 16) };
    private readonly VirtualRows side = new() { TraceName = "sidebar", Spacing = 2, Padding = new Thickness(8) };
    private readonly VirtualRows detail = new() { TraceName = "inspector", Spacing = 14, Padding = new Thickness(16) };
    private readonly NativeChatList stream = new() { TraceName = "conversation", ContentPadding = new Thickness(20, 8, 20, 24), ContentMaxWidth = 920, HorizontalAlignment = HorizontalAlignment.Stretch };
    private readonly ComposerInput editor = new();
    private readonly TextBox search = new();
    private readonly StackPanel sideTools = new() { Padding = new Thickness(8, 10, 8, 6) };
    private readonly Grid searchSurface = new();
    private readonly System.Runtime.CompilerServices.ConditionalWeakTable<TextBox, Grid> fieldSurfaces = new();

    private readonly InfoBar error = new() { Severity = InfoBarSeverity.Error, IsClosable = true };
    private ScrollViewer chatScroll = null!;
    private readonly TaskCompletionSource<ScrollViewer> chatViewportReady = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly Grid chatHead = new() { Height = 56, Padding = new Thickness(20, 0, 14, 0), ColumnSpacing = 12, BorderThickness = new Thickness(0, 0, 0, 1) };
    private readonly StackPanel menu = new() { Orientation = Orientation.Horizontal };
    private readonly TextBlock appTitle = new() { FontSize = 12.5, TextWrapping = TextWrapping.NoWrap, TextTrimming = TextTrimming.CharacterEllipsis, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center, IsHitTestVisible = false };
    private Button? sendButton;
    private readonly DispatcherTimer refreshTimer = new() { Interval = TimeSpan.FromMilliseconds(350) };
    // Other organizations' changes only touch their sidebar rows: read the organization list at most this often.
    private readonly DispatcherTimer sidebarTimer = new() { Interval = TimeSpan.FromMilliseconds(1500) };
    private bool refreshing, pending, closing, ready, sending, sendingThread;
    // An organization snapshot read by a refresh a click made stale (see Refresh).
    private (string Org, Task<JsonNode>? Request, long At) handedSnapshot;
    private TaskCompletionSource? refreshCompletion;
    private string renderedView = "";
    private bool sidebarStructureChanged;
    private long presentationVersion, renderedPresentationVersion;
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
        Activated += (_, e) =>
        {
            var wasActive = active;
            active = e.WindowActivationState != WindowActivationState.Deactivated;
            if (active && !wasActive && ready)
            {
                // Pointer activation is part of the user's click. Replacing
                // the sidebar here destroys its pressed item before release.
                // The selected chat already suppresses its unread badge;
                // normal coalesced refresh handles actual data changes.
                MarkSeen(); SaveViewState(); Schedule();
            }
        };
        root.RowDefinitions.Add(new() { Height = GridLength.Auto });
        root.RowDefinitions.Add(new() { Height = GridLength.Auto });
        root.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        var top = titlebarRegion; top.Height = 40; top.BorderThickness = new Thickness(0, 0, 0, 1); top.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); top.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); top.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); top.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        void PaintToolbarSurface() { top.BorderBrush = Line; top.Background = Paint("F8F7F5", "191918"); }
        top.Loaded += (_, _) => PaintToolbarSurface();
        root.ActualThemeChanged += (_, _) =>
        {
            PaintToolbarSurface(); presentationVersion++; toolbarState = null;
            if (ready) { ThemeSurfaces(); Schedule(); }
        };
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
        // The native ListView owns the only scrolling viewport. Nesting it in
        // another ScrollViewer would give it infinite height and disable recycling.
        stream.PositionEnded += LoadOlderAfterRestore;
        stream.ViewportReady += viewport =>
        {
            chatScroll = viewport;
            chatScroll.Style = (Style)Application.Current.Resources["RelicScrollViewerStyle"];
            chatScroll.IsTabStop = true;
            WireConversationScroll();
            chatViewportReady.TrySetResult(viewport);
        };
        Grid.SetRow(stream, 2); chat.Children.Add(stream);
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
        root.SizeChanged += (_, _) => { LayoutFeedback.Note("root.size", root.ActualWidth, root.ActualHeight); appTitle.MaxWidth = root.ActualWidth * .4; LayoutColumns(); };
        root.LayoutUpdated += (_, _) => LayoutFeedback.LayoutPass(DispatcherQueue);
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
        // A refresh that started after the request covered it (it clears
        // pending). Refreshing again read the chat just opened a second time:
        // a click made a refresh stale, it asked for this one, and that one
        // was in flight at the next click, which made it stale in turn.
        refreshTimer.Tick += async (_, _) => { refreshTimer.Stop(); if (!pending) return; await Run(Refresh); };
        sidebarTimer.Tick += async (_, _) => { sidebarTimer.Stop(); await Run(RefreshSidebar); };
        Closed += async (_, e) =>
        {
            if (closing) return;
            e.Handled = true; SaveViewState(); SaveWindowPlacement(); placementTimer.Stop(); closing = true; ready = false; lifetime.Cancel(); refreshTimer.Stop(); sidebarTimer.Stop(); plainTimer.Stop();
            await viewStateWriter.DisposeAsync(); await windowStateWriter.DisposeAsync();
            await StopVoice(); await host.DisposeAsync(); api?.Dispose(); Close();
        };
        root.Loaded += async (_, _) =>
        {
            if (api != null) return;
            await Run(async () =>
            {
                await chatViewportReady.Task;
                VisualStartup("starting engine host");
                var engine = Environment.GetEnvironmentVariable("RELIC_ENGINE_ROOT") ?? AppContext.BaseDirectory;
                api = await host.Start(engine, Environment.GetEnvironmentVariable("RELIC_PYTHON") ?? "python");
                VisualStartup("loading preferences and capabilities");
                preferences = await api.Get("/api/prefs");
                platform = await api.Get("/api/platform");
                var language = Words.Normalize(preferences.Text("lang").Length > 0 ? preferences.Text("lang") : System.Globalization.CultureInfo.CurrentUICulture.Name);
                await api.Post("/api/prefs", new { lang = language });
                words.Load(await api.Get("/api/i18n?lang=" + language));
                StartupFontWarmup.WarmWords(words.Characters(), words.Language, (float)(root.XamlRoot?.RasterizationScale ?? 1));
                LoadViewState();
                if (root.ActualWidth <= ResponsiveLayout.InspectorOverlayWidth) panelOpen = false;
                ready = true; LayoutColumns();
                VisualStartup("registering native notifications");
                AppNotificationManager.Default.NotificationInvoked += (_, _) => DispatcherQueue.TryEnqueue(Activate);
                try { AppNotificationManager.Default.Register(); }
                catch { notificationsAvailable = false; Note(T("settings.notify_unsupported")); }
                VisualStartup("loading organization and conversation");
                // The first chat and sidebar are the first text-heavy layout:
                // let the font warm-up finish first (see StartupFontWarmup.Ready).
                using (PerformanceTrace.Measure("startup.fonts.wait")) await StartupFontWarmup.Ready(TimeSpan.FromSeconds(2.5));
                ApplyAppearance(); DrawMenu(); StartPerformanceProbe(); await Refresh();
                // Modules the first load brought in are read ahead too.
                StartupPrefetch.Start();
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
                        Route(ev);
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
    private void ScheduleSidebar() { if (!sidebarTimer.IsEnabled) sidebarTimer.Start(); }
    // The server announces a change of any organization about once a second while its members work (each tool call is
    // activity). Only a change of the open organization needs the open chat and inspector read again; another
    // organization's change can only alter its sidebar row. A reconnect or an unknown event still reads everything.
    private void Route(JsonNode ev)
    {
        var target = ev.Text("org");
        switch (ev.Text("type"))
        {
            case "orgs":
                ScheduleSidebar();
                return;
            case "live":
                if (target.Length > 0 && target != org) return;  // another organization's streamed output
                Schedule();
                return;
            case "digest":
                // The event carries the digest (or why it failed) itself, taken
                // above. Only the open group chat's card shows it: redraw that
                // card. A whole refresh read the open chat again 350 ms after
                // every organization switch, while it was still being drawn.
                if (target == org) RedrawDigest();
                return;
            case "org" or "decision" or "plain":
                if (target.Length > 0 && target != org) { ScheduleSidebar(); return; }
                Schedule();
                return;
            default:
                Schedule();
                return;
        }
    }
    // Another organization changed: read the organization list only and redraw the sidebar when it differs.
    private async Task RefreshSidebar()
    {
        if (api == null || closing) return;
        MonitorTick();
        if (refreshing) { ScheduleSidebar(); return; }
        var fresh = (await api.Get("/api/orgs")).Rows();
        if (closing) return;
        var current = orgs;
        if (await Task.Run(() => JsonNode.DeepEquals(current, fresh), lifetime.Token)) return;
        if (refreshing || !ReferenceEquals(orgs, current)) { ScheduleSidebar(); return; }
        orgs = fresh;
        using (PerformanceTrace.Measure("DrawSide")) DrawSide();
    }
    // What a message row shows of the members: who they are and how they look, never what they are doing now. A
    // working member's state changes every few seconds and must not rebuild every row of the open chat.
    private static readonly string[] memberLooks = ["name", "display", "label", "title", "avatar", "avatar_url", "color",
        "role", "leader", "secretary", "harness", "kind"];
    private static string MemberPresentationIdentity(JsonNode? snapshot)
    {
        var identity = new System.Text.StringBuilder();
        foreach (var member in snapshot.Rows("members"))
        {
            foreach (var key in memberLooks) identity.Append(member?[key]?.ToJsonString() ?? "").Append('\u001f');
            identity.Append('\u001e');
        }
        return identity.ToString();
    }
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
            // These reads have no dependency on one another. Keep one bounded
            // refresh in flight, but do not serialize its HTTP round trips.
            // CI records how long each read takes, so a slow endpoint shows up.
            var timed = PerformanceEnabled;
            Task<JsonNode> Timed(string name, Task<JsonNode> request)
            {
                if (!timed) return request;
                var started = System.Diagnostics.Stopwatch.GetTimestamp();
                _ = request.ContinueWith(_ => PerformanceTrace.Count("http." + name,
                    System.Diagnostics.Stopwatch.GetElapsedTime(started).TotalMilliseconds), TaskScheduler.Default);
                return request;
            }
            var organizationsRequest = Timed("orgs", api.Get("/api/orgs"));
            var copiesRequest = Timed("cc", api.Get("/api/cc"));
            // The selected chat's snapshot and messages do not depend on those
            // two reads either. Start them together instead of a second round
            // trip; only an organization that no longer exists asks again below.
            string ChatPath() => PathFor("/chat?kind=" + (member.Length == 0 ? "group" : "private") + "&member=" + Client.Segment(member) + "&limit=" + chatLimit);
            string ConvoPath() => PathFor("/convo?member=" + Client.Segment(member) + "&limit=" + chatLimit);
            string LivePath() => PathFor("/live?member=" + Client.Segment(member));
            var requestedOrg = org; var requestedMember = member;
            Task<JsonNode>? earlySnapshot = null, earlyChat = null, earlyTranscript = null, earlyLive = null;
            // A discarded early read must not surface later as an unobserved fault.
            static void Observe(Task<JsonNode>? early)
            {
                if (early != null) _ = early.ContinueWith(task => _ = task.Exception, CancellationToken.None,
                    TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
            }
            if (org.Length > 0)
            {
                // A refresh that a click just made stale hands over its read of
                // this organization's snapshot (see below): the same read, a
                // moment old, that the server is already computing.
                var handed = handedSnapshot; handedSnapshot = default;
                var useHanded = handed.Request is { IsFaulted: false, IsCanceled: false } && handed.Org == org
                    && System.Diagnostics.Stopwatch.GetElapsedTime(handed.At).TotalMilliseconds < 300;
                if (useHanded && timed) PerformanceTrace.Count("refresh.snapshot.handed", 1);
                earlySnapshot = useHanded ? handed.Request! : Timed("snapshot", api.Get(PathFor()));
                earlyChat = Timed("chat", api.Get(ChatPath()));
                Observe(earlySnapshot); Observe(earlyChat);
                // A member's transcript and live state otherwise wait for the new
                // snapshot to say they exist. The snapshot already loaded for this
                // organization says the same in nearly every case; start them now
                // and confirm against the new snapshot below.
                if (member.Length > 0 && snapOrg == org)
                {
                    var known = snap.Rows("members").FirstOrDefault(x => x.Text("name") == member);
                    if (known.Flag("has_transcript")) earlyTranscript = Timed("convo", api.Get(ConvoPath()));
                    if (known.Flag("embedded")) earlyLive = Timed("live", api.Get(LivePath()));
                    Observe(earlyTranscript); Observe(earlyLive);
                }
            }
            try { await Task.WhenAll(organizationsRequest, copiesRequest); }
            catch (Exception ex)
            {
                if (organizationsRequest.IsFaulted)
                    throw new InvalidOperationException(T("boot.load_orgs_failed", ("error", ex.Message)), ex);
                throw;
            }
            orgs = (await organizationsRequest).Rows();
            var newCopy = copyInbox.Update(await copiesRequest);
            CopyNotifications(newCopy); DrawCopies();
            if (org.Length > 0 && !orgs.Any(x => x.Text("id") == org)) { org = ""; member = ""; }
            if (org.Length == 0 && orgs.Count > 0) { org = orgs[0].Text("id"); selectedOrg = org; }
            // A click while this refresh was in flight makes everything below
            // stale. Leave now rather than after the selected organization's
            // snapshot (several hundred ms for a large one): the click's own
            // refresh is waiting for this one to finish.
            if (org != selectedOrg || member != selectedMember)
            {
                if (timed) PerformanceTrace.Count("refresh.stale.after_orgs", 1);
                // The click reads its organization next. When that is this one,
                // its snapshot is the one already being computed: two at once
                // made both twice as slow (over a second for the largest).
                if (earlySnapshot != null) handedSnapshot = (requestedOrg, earlySnapshot, System.Diagnostics.Stopwatch.GetTimestamp());
                pending = true; return;
            }
            if (org.Length > 0)
            {
                var reuse = earlySnapshot != null && org == requestedOrg && member == requestedMember;
                var snapshotRequest = reuse ? earlySnapshot! : Timed("snapshot", api.Get(PathFor()));
                var chatRequest = reuse ? earlyChat! : Timed("chat", api.Get(ChatPath()));
                await Task.WhenAll(snapshotRequest, chatRequest);
                var snapshot = await snapshotRequest;
                var chat = await chatRequest;
                if (org != selectedOrg || member != selectedMember)
                {
                    // The click waited for this read; hand the snapshot over (see above).
                    handedSnapshot = (selectedOrg, snapshotRequest, System.Diagnostics.Stopwatch.GetTimestamp());
                    pending = true; return;
                }
                snap = snapshot; snapOrg = org;
                var loadedMessages = messages;
                // While the person reads (not following the latest message) or an
                // older page loads, keep the rows already shown and add the new
                // ones. Replacing them with the newest window dropped its oldest
                // message when a new one arrived: the message the person was
                // reading at the top vanished, then came back above the next page.
                var keepShown = olderHistory || (loadingOlder || !keepLatest)
                    && ReachesShown(loadedMessages, chat.Rows("items"), chat.Flag("more"));
                var mergedMessages = keepShown ? await Task.Run(() => Transcript.MergeMessages(loadedMessages, chat.Rows("items")), lifetime.Token) : chat.Rows("items");
                // An older page can arrive while the merge runs on a worker;
                // committing the merge of the list as it was dropped that page.
                while (org == selectedOrg && member == selectedMember && !ReferenceEquals(messages, loadedMessages))
                {
                    loadedMessages = messages;
                    mergedMessages = keepShown ? await Task.Run(() => Transcript.MergeMessages(loadedMessages, chat.Rows("items")), lifetime.Token) : chat.Rows("items");
                }
                if (org != selectedOrg || member != selectedMember) { pending = true; return; }
                messages = mergedMessages;
                if (!olderHistory) chatMore = chat.Flag("more");
                if (member.Length > 0)
                {
                    var m = snap.Rows("members").FirstOrDefault(x => x.Text("name") == member);
                    var transcriptRequest = !m.Flag("has_transcript") ? Task.FromResult<JsonNode>(new JsonObject())
                        : reuse && earlyTranscript != null ? earlyTranscript : Timed("convo", api.Get(ConvoPath()));
                    var liveRequest = !m.Flag("embedded") ? Task.FromResult<JsonNode>(new JsonObject())
                        : reuse && earlyLive != null ? earlyLive : Timed("live", api.Get(LivePath()));
                    await Task.WhenAll(transcriptRequest, liveRequest);
                    if (org != selectedOrg || member != selectedMember) { pending = true; return; }
                    conversation = await transcriptRequest;
                    liveData = await liveRequest;
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
            var changes = await Task.Run(() =>
            {
                // The current conversation uses its snapshot (including member
                // names, avatars and header state), not other organizations'
                // summaries. Keep those independent sidebar updates out of it.
                var snapshotChanged = !JsonNode.DeepEquals(oldSnap, nextSnap);
                var chatChanged = snapshotChanged || !JsonNode.DeepEquals(oldMessages, nextMessages)
                    || !JsonNode.DeepEquals(oldConversation, nextConversation) || !JsonNode.DeepEquals(oldLive, nextLive);
                return (
                    Side: !JsonNode.DeepEquals(oldOrgs, nextOrgs) || snapshotChanged,
                    Chat: chatChanged,
                    Detail: snapshotChanged || !JsonNode.DeepEquals(oldThread, nextThread),
                    Identities: chatChanged ? MessagePresentationIdentities(nextMessages) : null,
                    MemberIdentity: snapshotChanged ? MemberPresentationIdentity(nextSnap) : null);
            }, lifetime.Token);
            if (org != selectedOrg || member != selectedMember) { pending = true; return; }
            if (changes.Identities != null) messagePresentationIdentities = changes.Identities;
            if (changes.MemberIdentity != null) memberPresentationIdentity = changes.MemberIdentity;
            var viewChanged = renderedView != org + "/" + member;
            var organizationChanged = !renderedView.StartsWith(org + "/", StringComparison.Ordinal);
            var currentPresentation = presentationVersion;
            var presentationChanged = currentPresentation != renderedPresentationVersion;
            using (PerformanceTrace.Measure("DrawMenu")) if (viewChanged || presentationChanged) DrawMenu();
            using (PerformanceTrace.Measure("DrawToolbar")) if (changes.Side || changes.Chat || changes.Detail || newCopy != null || viewChanged || presentationChanged) DrawToolbar();
            using (PerformanceTrace.Measure("DrawSide"))
            {
                if (changes.Side || organizationChanged || sidebarStructureChanged || presentationChanged) { DrawSide(); sidebarStructureChanged = false; }
                else if (viewChanged) UpdateSidebarSelection();
            }
            if ((changes.Chat || viewChanged || presentationChanged) && !await DrawConversationAsync())
            { if (timed) PerformanceTrace.Count("refresh.draw_superseded", 1); pending = true; return; }
            // Overview is organization data. A private-chat selection changes
            // its sidebar highlight, not its member/task/protocol controls.
            var detailChanged = changes.Detail || organizationChanged || presentationChanged || (viewChanged && pane != "overview");
            renderedView = org + "/" + member;
            renderedPresentationVersion = currentPresentation;
            // The chat comes first. The inspector fills in once the chat has settled, apart from this refresh, so its
            // rows never sit in front of the chat the person asked for and the next click never waits for them.
            if (detailChanged) _ = Run(() => DrawDetailAfterChat(selectedOrg, selectedMember, changes.Detail));
        }
        finally { refreshing = false; completed.TrySetResult(); if (pending) Schedule(); MonitorTick(); }
    }
    private int detailRequest;
    private async Task DrawDetailAfterChat(string selectedOrg, string selectedMember, bool detailData)
    {
        var request = ++detailRequest;
        var waited = System.Diagnostics.Stopwatch.StartNew();
        await YieldPresentation();  // at least one frame between the chat and the inspector
        while (!closing && request == detailRequest && waited.Elapsed < TimeSpan.FromSeconds(1)
            && !(ConversationContentReady() && (!keepLatest || stream.IsLastPositionSettled)))
            await YieldPresentation();
        // Let the ready chat present itself first. The inspector's text
        // preparation began in the same turn the chat became ready, and the
        // chat counted as still preparing past its one-second open.
        if (ConversationContentReady()) { await YieldPresentation(); await YieldPresentation(); }
        if (closing || request != detailRequest || org != selectedOrg || member != selectedMember) return;
        using (PerformanceTrace.Measure("DrawDetail")) DrawDetail();
        if (pane == "workspace" && detailData) await Workspace();
        if (refreshChart != null && detailData) await refreshChart();
    }
    private async Task Select(string id, string who = "", bool fromHistory = false)
    {
        conversationPreparation?.Cancel();
        transientFlyout?.Hide();
        await StopVoice();
        RememberChat(); var different = org != id; org = id; member = who; conversation = new JsonObject(); liveData = new JsonObject(); messages = new JsonArray();
        olderHistory = false; chatPages = 1;
        if (different) { digest = new JsonObject(); threadId = ""; if (pane == "thread") pane = previousPane; directory = ""; workspaceMember = ""; }
        RestoreChat(); if (!fromHistory) PushHistory();
        var reveal = id; var ancestors = new HashSet<string>();
        while (reveal.Length > 0 && ancestors.Add(reveal)) { sidebarStructureChanged |= folded.Remove(reveal); reveal = orgs.FirstOrDefault(o => o.Text("id") == reveal).Text("parent"); }
        // A narrow window shows the inspector over the chat; opening a chat brings the chat itself to the front.
        if (root.ActualWidth <= ResponsiveLayout.InspectorOverlayWidth) panelOpen = false;
        SaveViewState();
        LayoutColumns();
        // A selected chat opens at its latest message. Its first draw starts that one scroll intent; a second request
        // here would restart positioning that is already under way.
        keepLatest = true; followInputGeneration = conversationScrollInput.Generation;
        // Anchor the bottom edge while the chat is filled (see NativeChatList).
        if (chatScroll != null) chatScroll.VerticalAnchorRatio = 1;
        var requested = latestRequest;
        await Refresh();
        if (org != id || member != who) return;
        if (renderedView != id + "/" + who) await Refresh();
        if (org != id || member != who) return;
        if (different && digestOpen) await LoadDigest(false);
        if (latestRequest == requested) ScrollToLatest();
    }
    private void DrawMenu() => BuildMenus();
    private async Task YieldPresentation()
    {
        // A 1 ms normal-priority continuation still batches all three panes
        // into one native layout frame. Let pending presentation work run
        // before constructing the next pane, while input remains dispatchable.
        var presented = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        if (!DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low,
            () => presented.TrySetResult())) return;
        await presented.Task;
        await Task.Delay(16, lifetime.Token);
    }
    private async Task LoadPreferences()
    {
        conversationPreparation?.Cancel();
        preferences = await api!.Get("/api/prefs");
        var language = Words.Normalize(preferences.Text("lang"));
        if (language != words.Language) { plain.Clear(); plainPending.Clear(); plainFailed.Clear(); digest = new JsonObject(); }
        words.Load(await api.Get("/api/i18n?lang=" + language));
        StartupFontWarmup.WarmWords(words.Characters(), words.Language, (float)(root.XamlRoot?.RasterizationScale ?? 1));
        // The reference sets document.documentElement.lang with its word list.
        // Native text shaping/fallback must use that same selected language,
        // including an already-open settings dialog outside the main tree.
        root.Language = words.Language;
        if (visibleDialog != null) visibleDialog.Language = words.Language;
        presentationVersion++; toolbarState = null;
        ApplyAppearance(); DrawMenu();
    }
    private void DrawSide() => DrawSidebar();
    private void ScrollToLatest()
    {
        // Retain the actual final-row anchor through deferred Markdown/font
        // layout and virtual extent changes. NativeChatList reacts to real layout
        // changes, and a later user/history scroll cancels this single intent.
        keepLatest = true; followInputGeneration = conversationScrollInput.Generation;
        chatScroll.VerticalAnchorRatio = 1;
        var request = ++latestRequest;
        PerformanceTrace.Count("conversation.latest.request", request);
        var selectedOrg = org; var selectedMember = member;
        bool IsCurrent() => !closing && keepLatest && request == latestRequest
            && org == selectedOrg && member == selectedMember;
        bool IsContentReady() => ConversationContentReady();
        stream.FollowLastIntoView(chatScroll, IsCurrent, IsContentReady);
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

    // Whether a chat's newest page still reaches back to the messages shown
    // (or holds the chat's start), so adding it to them leaves no gap. After a
    // long absence it may not; the page then replaces them, as when following.
    private static bool ReachesShown(JsonArray shown, JsonArray newest, bool more)
    {
        long? shownNewest = null, pageOldest = null;
        foreach (var row in shown)
            if (long.TryParse(row.Text("id"), out var id) && (shownNewest == null || id > shownNewest)) shownNewest = id;
        foreach (var row in newest)
            if (long.TryParse(row.Text("id"), out var id) && (pageOldest == null || id < pageOldest)) pageOldest = id;
        return !more || shownNewest == null || pageOldest == null || pageOldest <= shownNewest;
    }
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
        field.HeaderTemplate = XamlTemplates.Load<DataTemplate>("<DataTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation'><TextBlock Text='{Binding}' FontSize='12.5' LineHeight='20' LineStackingStrategy='BlockLineHeight' Foreground='{ThemeResource RelicControlSecondary}'/></DataTemplate>");
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
