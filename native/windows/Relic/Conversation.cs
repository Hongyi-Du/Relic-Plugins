using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Relic.Core;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Windows.System;

namespace Relic;

public sealed partial class MainWindow
{
    private JsonNode conversation = new JsonObject(), liveData = new JsonObject(), digest = new JsonObject(), threadData = new JsonObject();
    private readonly Dictionary<string, string> plain = new();
    private readonly HashSet<string> plainOne = new(), plainPending = new(), plainFailed = new();
    private readonly HashSet<string> recipientNames = new() { "all" };
    private bool plainMode, digestOpen, digestPending;
    private string quoteWho = "", quoteText = "", threadId = "", previousPane = "overview";
    private readonly TextBox threadEditor = new() { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = 80 };
    private Panel? threadEditorContainer;
    private Button? threadSendButton;
    private readonly TextBlock quoteLabel = new() { TextWrapping = TextWrapping.Wrap };
    private Button? recipientButton;
    private const int chatLimit = 1000;
    private bool chatMore, olderHistory;
    private readonly Dictionary<string, FrameworkElement> plainTargets = new();
    private readonly DispatcherTimer plainTimer = new() { Interval = TimeSpan.FromMilliseconds(300) };
    private readonly HashSet<TextBox> composing = new();
    private readonly Grid emptyConversation = new() { Visibility = Visibility.Collapsed, Padding = new Thickness(32) };
    private readonly Border conversationBanner = new() { Visibility = Visibility.Collapsed, Padding = new Thickness(20, 0, 20, 10) };
    private void UpdateSendState()
    {
        if (sendButton != null) { sendButton.IsEnabled = !string.IsNullOrWhiteSpace(editor.Text) || quoteText.Length > 0; sendButton.Opacity = sendButton.IsEnabled ? 1 : .35; }
        if (threadSendButton != null) threadSendButton.IsEnabled = !string.IsNullOrWhiteSpace(threadEditor.Text) || quoteText.Length > 0;
    }
    private string PlainKey(string id) => org + "/" + id;
    private void Quote(string who, string body)
    {
        quoteWho = who; quoteText = Regex.Replace(body, @"^(>.*\n?)+\n*", "").Trim();
        if (quoteText.Length > 1200) quoteText = quoteText[..1200] + "…";
        quoteLabel.Text = T("composer.quoting", ("who", who)) + "\n" + quoteText; quoteLabel.MaxLines = 3; quoteLabel.TextTrimming = TextTrimming.CharacterEllipsis; quoteRow.Visibility = Visibility.Visible; UpdateSendState(); SaveViewState();
        if (pane == "thread") { DrawDetail(); threadEditor.Focus(FocusState.Programmatic); } else editor.Focus(FocusState.Programmatic);
    }
    private string Quoted(string text)
    {
        if (quoteText.Length == 0) return text;
        var lines = quoteText.Split('\n'); lines[0] = T("sel.quote_line", ("who", quoteWho), ("text", lines[0]));
        return string.Join("\n", lines.Select(l => "> " + l)) + "\n\n" + text;
    }
    private void ClearQuote() { quoteWho = quoteText = quoteLabel.Text = ""; quoteRow.Visibility = Visibility.Collapsed; UpdateSendState(); }
    private Task PickRecipients()
    {
        var box = new StackPanel { Spacing = 2, Width = 270 };
        var options = new[] { ("all", T("composer.all_members")) }.Concat(snap.Rows("members").Select(m => (m.Text("name"), m.Text("display"))));
        var toggles = new List<CheckBox>(); bool changing = false;
        foreach (var (id, label) in options)
        {
            var check = new CheckBox { Content = Ellipsis(label), Tag = id, IsChecked = recipientNames.Contains(id), MinHeight = 34, HorizontalAlignment = HorizontalAlignment.Stretch };
            void Changed()
            {
                if (changing) return; changing = true;
                if (check.IsChecked == true) foreach (var other in toggles) if (other != check && (id == "all" || other.Tag?.ToString() == "all")) other.IsChecked = false;
                if (!toggles.Any(c => c.IsChecked == true)) toggles[0].IsChecked = true;
                recipientNames.Clear(); foreach (var selected in toggles.Where(c => c.IsChecked == true)) recipientNames.Add(selected.Tag!.ToString()!);
                UpdateRecipient(); SaveViewState(); changing = false;
            }
            check.Checked += (_, _) => Changed(); check.Unchecked += (_, _) => Changed();
            toggles.Add(check); box.Children.Add(check);
        }
        ShowPopover(box, recipientButton!, Microsoft.UI.Xaml.Controls.Primitives.FlyoutPlacementMode.TopEdgeAlignedLeft); return Task.CompletedTask;
    }
    private void UpdateRecipient()
    {
        if (recipientButton != null)
        {
            var label = T("composer.send_to", ("to", recipientNames.Contains("all") ? T("msg.everyone") : words.List(recipientNames.Select(Display))));
            var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 }; row.Children.Add(Ellipsis(label, 12.5));
            var arrow = ReferenceIcon("chev", 12); arrow.RenderTransformOrigin = new(.5, .5); arrow.RenderTransform = new Microsoft.UI.Xaml.Media.RotateTransform { Angle = 90 }; row.Children.Add(arrow);
            recipientButton.Content = row; recipientButton.Height = 28; recipientButton.CornerRadius = new CornerRadius(9); recipientButton.BorderBrush = Paint("DEDBD4", "3A3936"); recipientButton.BorderThickness = new Thickness(1); recipientButton.Padding = new Thickness(10, 0, 10, 0);
            recipientButton.MaxWidth = 230; ToolTipService.SetToolTip(recipientButton, label); recipientButton.Visibility = member.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
        }
    }
    private void MentionMenu()
    {
        var start = editor.SelectionStart; var text = editor.Text[..Math.Min(start, editor.Text.Length)]; var match = Regex.Match(text, @"(?:^|\s)@([^\s@]*)$");
        if (!match.Success) return;
        var choices = snap.Rows("members").Where(m => m.Text("name").Contains(match.Groups[1].Value, StringComparison.OrdinalIgnoreCase) || m.Text("display").Contains(match.Groups[1].Value, StringComparison.OrdinalIgnoreCase)).Take(10).ToArray();
        if (choices.Length == 0) return;
        var menu = new MenuFlyout();
        foreach (var m in choices)
        {
            var option = new MenuFlyoutItem { Text = m.Text("display") + " · @" + m.Text("name") };
            option.Click += (_, _) => { var at = text.LastIndexOf('@'); var inserted = "@" + m.Text("display") + " "; editor.Text = editor.Text[..at] + inserted + editor.Text[start..]; editor.SelectionStart = at + inserted.Length; recipientNames.Remove("all"); recipientNames.Add(m.Text("name")); UpdateRecipient(); SaveViewState(); editor.Focus(FocusState.Programmatic); };
            menu.Items.Add(option);
        }
        transientFlyout?.Hide(); transientFlyout = menu; menu.ShowAt(editor);
    }
    private void WireComposer()
    {
        plainTimer.Tick += async (_, _) => { plainTimer.Stop(); await Run(VisiblePlain); };
        chatScroll.ViewChanged += (_, _) => { if (plainMode && !plainTimer.IsEnabled) plainTimer.Start(); };
        foreach (var text in new[] { editor, threadEditor })
        {
            text.TextCompositionStarted += (_, _) => composing.Add(text);
            text.TextCompositionEnded += (_, _) => composing.Remove(text);
        }
        threadEditor.KeyDown += async (_, e) =>
        {
            var shift = (Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(VirtualKey.Shift) & Windows.UI.Core.CoreVirtualKeyStates.Down) != 0;
            if (e.Key == VirtualKey.Enter && !shift && !composing.Contains(threadEditor)) { e.Handled = true; await Run(SendThread); }
        };
        editor.KeyDown += async (_, e) =>
        {
            var shift = (Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(VirtualKey.Shift) & Windows.UI.Core.CoreVirtualKeyStates.Down) != 0;
            if (e.Key == VirtualKey.Enter && !shift && !composing.Contains(editor)) { e.Handled = true; await Run(Send); }
            if (e.Key == VirtualKey.Space && editor.Text[..Math.Min(editor.SelectionStart, editor.Text.Length)].EndsWith('@')) MentionMenu();
        };
        editor.TextChanged += (_, _) => { if (editor.Text[..Math.Min(editor.SelectionStart, editor.Text.Length)].EndsWith('@')) DispatcherQueue.TryEnqueue(MentionMenu); };
    }
    private IEnumerable<JsonNode?> ConversationItems()
    {
        if (member.Length == 0) return messages;
        var m = snap.Rows("members").FirstOrDefault(x => x.Text("name") == member);
        var output = new List<JsonNode?>(); var busy = liveData["status"].Text("state") is "running" or "starting" or "waiting";
        var cut = busy ? liveData.Rows("items").LastOrDefault(x => x.Flag("start")).Text("at") : "";
        JsonObject? actions = null;
        void Flush() { if (actions != null) { output.Add(actions); actions = null; } }
        foreach (var step in conversation.Rows("steps"))
        {
            if (cut.Length > 0 && string.CompareOrdinal(step.Text("at"), cut) >= 0) continue;
            var role = step.Text("role"); var text = step.Text("text"); var at = step.Text("at");
            if (role is "tool_call" or "tool_result") { actions ??= new JsonObject { ["type"] = "acts", ["at"] = at, ["member"] = member, ["steps"] = new JsonArray() }; actions.Rows("steps").Add(step?.DeepClone()); continue; }
            Flush();
            if (role is not ("user" or "assistant")) continue;
            var from = role == "assistant" ? member : "human"; var type = "message";
            if (role == "user")
            {
                if (text.StartsWith(Transcript.PersonPrefix)) text = Transcript.PersonText(text);
                else if (text.StartsWith("[Relic auto-wake]")) { type = "notice"; text = T("msg.auto_woken"); }
                else if (text.StartsWith("You now hold the seat")) { type = "notice"; text = T("msg.seat_briefing"); }
                else if (m.Text("agent").Length > 0) from = m.Text("parent").Length > 0 ? m.Text("parent") : member;
            }
            output.Add(new JsonObject { ["type"] = type, ["from"] = from, ["fromLabel"] = role == "user" && from != "human" ? T("msg.task_from", ("name", m.Text("parent").Length > 0 ? Display(m.Text("parent")) : T("msg.parent_session"))) : Display(from), ["to"] = new JsonArray(JsonValue.Create(role == "assistant" ? "human" : member)), ["body"] = text, ["text"] = text, ["at"] = at });
        }
        Flush();
        if (!m.Flag("embedded") || conversation.Rows("steps").Count == 0) output.AddRange(messages);
        return output.OrderBy(x => x.Text("at"));
    }
    private void DrawConversation()
    {
        chatHead.Children.Clear(); stream.Children.Clear(); plainTargets.Clear();
        conversationBanner.Child = null; conversationBanner.Visibility = Visibility.Collapsed;
        composerSurface.Visibility = org.Length == 0 ? Visibility.Collapsed : Visibility.Visible;
        emptyConversation.Children.Clear(); emptyConversation.Visibility = org.Length == 0 ? Visibility.Visible : Visibility.Collapsed; chatScroll.Visibility = org.Length == 0 ? Visibility.Collapsed : Visibility.Visible; UpdateSendState();
        if (org.Length == 0)
        {
            chatHead.Children.Add(Heading(Title, 17));
            var title = Heading(T("chat.no_orgs"), 20); title.TextAlignment = TextAlignment.Center;
            var hint = Quiet(T("chat.no_orgs_hint"), 13); hint.TextAlignment = TextAlignment.Center;
            var empty = Stack(title, hint); empty.Spacing = 18; empty.MaxWidth = 620; empty.HorizontalAlignment = HorizontalAlignment.Center; empty.VerticalAlignment = VerticalAlignment.Center; emptyConversation.Children.Add(empty); return;
        }
        var m = snap.Rows("members").FirstOrDefault(x => x.Text("name") == member);
        chatHead.ColumnDefinitions.Clear(); chatHead.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); chatHead.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); chatHead.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        var titles = new StackPanel { Spacing = 0, VerticalAlignment = VerticalAlignment.Center }; var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 2, VerticalAlignment = VerticalAlignment.Center };
        var portrait = member.Length == 0 ? ChatAvatar(false) : m.Flag("secretary") && m.Text("avatar").Length == 0 ? ChatAvatar(true) : SmallAvatar(m.Text("avatar"), Display(member), m.Text("state"), 28);
        chatHead.Children.Add(portrait); Grid.SetColumn(titles, 1); chatHead.Children.Add(titles); Grid.SetColumn(actions, 2); chatHead.Children.Add(actions);
        TextBlock HeaderLabel(string value)
        {
            var label = Ellipsis(value, 15); label.FontWeight = new Windows.UI.Text.FontWeight { Weight = 650 }; label.LineHeight = 19.5; label.LineStackingStrategy = LineStackingStrategy.BlockLineHeight; return label;
        }
        TextBlock HeaderMeta(string value)
        {
            var label = Ellipsis(value, 12); label.Foreground = Muted; label.LineHeight = 16.8; label.LineStackingStrategy = LineStackingStrategy.BlockLineHeight; return label;
        }
        if (member.Length == 0)
        {
            var heading = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 }; heading.Children.Add(HeaderLabel(T("common.group_chat")));
            var count = HeaderLabel(T("common.members", ("n", snap.Rows("members").Count))); count.FontWeight = Microsoft.UI.Text.FontWeights.Normal; count.Foreground = Muted; heading.Children.Add(count); titles.Children.Add(heading);
            titles.Children.Add(HeaderMeta(T(snap["org"].Flag("auto_wake") ? "chat.group_meta_on" : "chat.group_meta_off", ("org", snap["org"].Text("name")))));
            actions.Children.Add(ChipButton("lang", T(plainMode ? "chat.plain_on" : "common.plain_words"), T("chat.plain_title"), TogglePlain));
            actions.Children.Add(ChipButton("sparkle", T("chat.digest"), T("chat.digest_title"), ToggleDigest));
            actions.Children.Add(IconButton("\uE73A", "common.tasks", () => Details("tasks")));
            if (digestOpen) { var digestScroll = Scroll(DigestCard()); digestScroll.MaxHeight = Math.Min(230, root.ActualHeight * .3); var summary = Card(digestScroll); summary.Background = Paint("F3F0FA", "302A40"); summary.BorderBrush = Paint("D8CEE9", "4C405E"); conversationBanner.Child = summary; conversationBanner.Visibility = Visibility.Visible; }
        }
        else
        {
            var heading = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
            var roleName = Display(member) == T("common.secretary") ? member : Display(member);
            heading.Children.Add(HeaderLabel(m.Flag("secretary") ? T("chat.secretary_title", ("name", roleName)) : Display(member)));
            if (m.Text("display").Length > 0 && m.Text("display") != member) { var identifier = HeaderLabel(member); identifier.Foreground = Muted; identifier.FontWeight = Microsoft.UI.Text.FontWeights.Normal; identifier.FontFamily = new Microsoft.UI.Xaml.Media.FontFamily("Cascadia Code, Cascadia Mono, Consolas"); identifier.FontSize = 13.8; heading.Children.Add(identifier); }
            if (m.Flag("leader")) heading.Children.Add(Badge(T("common.leader"), true)); titles.Children.Add(heading);
            titles.Children.Add(HeaderMeta(string.Join(" · ", new[] { snap["org"].Text("name"), m.Text("harness_label"), m.Text("surface_label"), m.Text("model"), MemberState(m.Text("state")) }.Where(x => x.Length > 0))));
            if (m.Flag("embedded") && m.Text("state") is "running" or "waiting") actions.Children.Add(IconButton("\uE71A", "chat.stop_turn", () => Post("/cancel", new { member })));
            actions.Children.Add(IconButton("\uE77B", "chat.card", () => MemberCard(member)));
            actions.Children.Add(IconButton("\uE81C", "common.context_trace", () => Details("trace", member)));
            if (m.Text("surface") != "chat") actions.Children.Add(IconButton("\uE8B7", "chat.workspace", () => SetPane("workspace")));
            var banner = m.Flag("embedded") ? T("banner.embedded", ("harness", m.Text("harness_label"))) : m.Text("surface") == "subagent" ? m.Text("parent").Length > 0 ? T("banner.subagent_in", ("parent", Display(m.Text("parent")))) : T("banner.subagent") : !Delivery(m.Text("harness"), m.Text("surface")) ? m.Text("harness") == "chatgpt" ? T("member.chatgpt_unavailable") : T("member.desktop_manual") : m.Text("state") == "vacant" ? T("banner.vacant") : m.Flag("has_transcript") ? T("banner.transcript") : T("banner.inbox");
            conversationBanner.Child = Quiet(banner, 11); conversationBanner.Visibility = Visibility.Visible;
        }
        var atBottom = chatScroll.ScrollableHeight - chatScroll.VerticalOffset < 120;
        if (chatMore) stream.Children.Add(Button(T("trace.load_older"), LoadOlderMessages));
        var items = ConversationItems().ToArray();
        if (items.Length == 0) stream.Children.Add(Text(member.Length == 0 ? T("chat.empty_group") : T("chat.empty_private")));
        string day = ""; JsonNode? previous = null;
        foreach (var item in items)
        {
            var date = DateTimeOffset.TryParse(item.Text("at"), out var parsed) ? parsed.LocalDateTime.Date.ToString("yyyy-MM-dd") : "";
            if (date != day && date.Length > 0) { var label = Quiet(When(item.Text("at")), 11); label.TextAlignment = TextAlignment.Center; stream.Children.Add(label); day = date; previous = null; }
            else if (previous != null && DateTimeOffset.TryParse(previous.Text("at"), out var prior) && parsed - prior > TimeSpan.FromMinutes(20))
            { var label = Quiet(parsed.ToLocalTime().ToString("HH:mm"), 11); label.TextAlignment = TextAlignment.Center; stream.Children.Add(label); previous = null; }
            stream.Children.Add(Message(item!, false, Transcript.SameMessageGroup(previous, item!))); previous = item;
        }
        if (member.Length > 0) DrawLive(stream);
        if (atBottom) ScrollToLatest();
        UpdateRecipient(); editor.PlaceholderText = member.Length == 0 ? T("composer.group_placeholder") : T("composer.dm_placeholder", ("name", Display(member)));
        if (plainMode && member.Length == 0) plainTimer.Start();
    }
    private async Task LoadOlderMessages()
    {
        var selectedOrg = org; var selectedMember = member;
        var before = messages.FirstOrDefault(m => long.TryParse(m.Text("id"), out _)).Text("id");
        if (before.Length == 0) { chatMore = false; return; }
        var page = await api!.Get(PathFor("/chat?kind=" + (member.Length == 0 ? "group" : "private") + "&member=" + Client.Segment(member) + "&limit=1000&before=" + Client.Segment(before)));
        if (org != selectedOrg || member != selectedMember) return;
        var height = chatScroll.ScrollableHeight; var offset = chatScroll.VerticalOffset;
        olderHistory = true; messages = Transcript.MergeMessages(page.Rows("items"), messages); chatMore = page.Flag("more"); DrawConversation();
        DispatcherQueue.TryEnqueue(() => { stream.UpdateLayout(); chatScroll.ChangeView(null, offset + chatScroll.ScrollableHeight - height, null); });
    }
    private UIElement Message(JsonNode item, bool inThread, bool continued = false)
    {
        if (item.Text("type") == "notice") { var note = Quiet(item.Text("text"), 11); note.TextAlignment = TextAlignment.Center; return new Border { Child = note, HorizontalAlignment = HorizontalAlignment.Center, Margin = new Thickness(26, 0, 26, 0), Padding = new Thickness(9, 3, 9, 3), CornerRadius = new CornerRadius(12), Background = Paint("F8F7F5", "252523") }; }
        if (item.Text("type") == "acts") return ToolActions(item);
        if (item.Text("type") == "step")
        {
            var content = Text(item.Text("text")); var expand = new Expander { Header = item.Text("tool").Length > 0 ? item.Text("tool") : T("common.result"), Content = content, HorizontalAlignment = HorizontalAlignment.Stretch };
            expand.Expanding += async (_, _) => await Run(async () => { if (item.Flag("cut")) content.Text = (await api!.Get(PathFor("/step?member=" + Client.Segment(member) + "&i=" + item.Text("i")))).Text("text"); }); return expand;
        }
        var from = item.Text("from"); var body = item.Text("body"); if (body.Length == 0) body = item.Text("text");
        var mine = from == "human";
        var box = new StackPanel { Spacing = 6 };
        var column = new StackPanel { Spacing = 4, HorizontalAlignment = mine ? HorizontalAlignment.Right : HorizontalAlignment.Left };
        if (!continued)
        {
            var time = DateTimeOffset.TryParse(item.Text("at"), out var at) ? at.ToLocalTime().ToString("HH:mm") : "";
            var label = Text("", 12); label.HorizontalAlignment = mine ? HorizontalAlignment.Right : HorizontalAlignment.Left;
            label.Inlines.Add(new Microsoft.UI.Xaml.Documents.Run { Text = item.Text("fromLabel").Length > 0 ? item.Text("fromLabel") : Display(from), FontWeight = Microsoft.UI.Text.FontWeights.SemiBold });
            var names = item.Rows("to").Select(x => x.Text()).ToArray(); var everyone = names.Contains("all") || snap.Rows("members").Where(m => m.Text("name") != from).All(m => names.Contains(m.Text("name")));
            var to = !inThread && member.Length == 0 ? " " + T("msg.to", ("names", everyone ? T("msg.everyone") : words.List(names.Select(Display)))) : "";
            label.Inlines.Add(new Microsoft.UI.Xaml.Documents.Run { Text = to + "  " + time, Foreground = Muted }); column.Children.Add(label);
        }
        var key = PlainKey(item.Text("id")); var explainable = from != "human" && long.TryParse(item.Text("id"), out _);
        var showingPlain = explainable && (plainOne.Contains(key) || plainMode && member.Length == 0 && !inThread) && plain.ContainsKey(key);
        if (item.Text("type") == "receipt") box.Children.Add(new Expander { Header = T("msg.auto_receipt_to", ("names", words.List(item.Rows("to").Select(x => Display(x.Text()))))), Content = Text(body.Replace("[Relic auto-receipt]", "")) });
        else if (explainable && (plainOne.Contains(key) || plainMode && member.Length == 0 && !inThread) && plain.TryGetValue(key, out var explained))
        { var title = Heading(T("msg.plain"), 12); title.Foreground = Paint("7660C8", "BDB0EC"); box.Children.Add(title); box.Children.Add(Rich(explained)); box.Children.Add(new Expander { Header = T("msg.original"), Content = Rich(body), MinHeight = 28, Padding = new Thickness(8), HorizontalContentAlignment = HorizontalAlignment.Stretch }); }
        else
        {
            box.Children.Add(Rich(body));
            if (explainable && (plainMode && member.Length == 0 && !inThread || plainOne.Contains(key)))
            {
                box.Children.Add(Button(plainPending.Contains(key) ? T("plain.pending") : plainFailed.Contains(key) ? T("plain.retry") : T("plain.waiting"), () => RequestPlain([item.Text("id")])));
                if (!plainPending.Contains(key) && !plainFailed.Contains(key) && !inThread && member.Length == 0) plainTargets[item.Text("id")] = box;
            }
        }
        var after = new StackPanel { Spacing = 3, HorizontalAlignment = mine ? HorizontalAlignment.Right : HorizontalAlignment.Left };
        if (from == "human" && item.Rows("to").Count > 0)
        {
            var others = item.Rows("to").Where(x => x.Text() != "human").Select(x => x.Text()).ToArray(); var read = item.Rows("read_by").Count(x => others.Contains(x.Text()));
            var receipt = QuietButton("", () => Task.CompletedTask); receipt.Content = Quiet(others.Length == 1 ? read > 0 ? T("msg.read") : T("msg.unread") : T("msg.read_count", ("read", read), ("total", others.Length)), 11); receipt.Padding = new Thickness(0); receipt.MinHeight = 20;
            if (others.Length > 1) { var readers = new MenuFlyout(); foreach (var name in others) readers.Items.Add(new MenuFlyoutItem { Text = Display(name) + " · " + T(item.Rows("read_by").Any(x => x.Text() == name) ? "msg.read" : "msg.unread") }); receipt.Flyout = readers; }
            after.Children.Add(receipt);
        }
        var actions = new ActionRow { Spacing = 2 };
        if (explainable) actions.Children.Add(IconButton("\uE8D4", plainOne.Contains(key) ? "msg.hide_plain" : "common.plain_words", async () => { if (!plainOne.Remove(key)) { plainOne.Add(key); await RequestPlain([item.Text("id")]); } DrawConversation(); }));
        actions.Children.Add(IconButton("\uE8F2", "common.quote", () => { Quote(Display(from), body); return Task.CompletedTask; }));
        if (!inThread && long.TryParse(item.Text("id"), out _)) actions.Children.Add(IconButton("\uE97A", "msg.reply_in_thread", () => OpenThread(item.Text("id"))));
        actions.Children.Add(IconButton("\uE8C8", "common.copy", () => { Copy(body); return Task.CompletedTask; }));
        if (!inThread && item["thread"] != null) { var replies = QuietButton(T("thread.replies", ("n", item["thread"].Text("count"))) + " · " + T("thread.last_reply", ("when", ShortWhen(item["thread"].Text("last_at")))), () => OpenThread(item.Text("id"))); replies.Foreground = Accent; after.Children.Add(replies); }
        var secretary = from == snap["org"].Text("secretary");
        var bubble = new Border { Child = box, Padding = new Thickness(12, 9, 12, 9), CornerRadius = new CornerRadius(11), Background = mine ? Paint("F8ECE6", "453027") : Paint("F4F3F0", "2A2A28"), BorderBrush = secretary ? Paint("7660C8", "A899E1") : Line, BorderThickness = new Thickness(secretary ? 3 : 0, 0, 0, 0), MaxWidth = 680, HorizontalAlignment = mine ? HorizontalAlignment.Right : HorizontalAlignment.Left };
        if (showingPlain) { bubble.Background = Paint("F3F0FA", "302A40"); bubble.BorderBrush = Paint("D8CEE9", "4C405E"); bubble.BorderThickness = new Thickness(1); }
        column.Children.Add(bubble); if (after.Children.Count > 0) column.Children.Add(after);
        var message = new Grid { HorizontalAlignment = mine ? HorizontalAlignment.Right : HorizontalAlignment.Stretch };
        message.Children.Add(column); actions.HorizontalAlignment = HorizontalAlignment.Right; actions.VerticalAlignment = VerticalAlignment.Top; actions.Margin = new Thickness(0, -26, 0, 0); actions.Opacity = 0; message.Children.Add(actions);
        message.PointerEntered += (_, _) => actions.Opacity = 1; message.PointerExited += (_, _) => actions.Opacity = 0;
        message.GotFocus += (_, _) => actions.Opacity = 1;
        var outer = new Grid { ColumnSpacing = 8, HorizontalAlignment = HorizontalAlignment.Stretch };
        outer.ColumnDefinitions.Add(new() { Width = mine ? new GridLength(1, GridUnitType.Star) : GridLength.Auto }); outer.ColumnDefinitions.Add(new() { Width = mine ? GridLength.Auto : new GridLength(1, GridUnitType.Star) });
        var speaker = snap.Rows("members").FirstOrDefault(m => m.Text("name") == from);
        var avatar = QuietButton("", () => mine ? Settings() : MemberCard(from)); avatar.Content = SmallAvatar(mine ? preferences.Text("avatar") : speaker.Text("avatar"), Display(from), size: 30); avatar.Padding = new Thickness(0); avatar.VerticalAlignment = VerticalAlignment.Top; avatar.Opacity = continued ? 0 : 1;
        Grid.SetColumn(avatar, mine ? 1 : 0); Grid.SetColumn(message, mine ? 0 : 1); outer.Children.Add(avatar); outer.Children.Add(message); return outer;
    }
    private void DrawLive(StackPanel target)
    {
        var all = liveData.Rows("items").ToArray(); var busy = liveData["status"].Text("state") is "running" or "waiting" or "starting";
        var start = Array.FindLastIndex(all, i => i.Flag("start"));
        var current = busy ? all.Skip(Math.Max(start, 0)) : all.Where(i => i.Text("type") == "permission" && snap.Rows("decisions").Any(d => d.Text("id") == i.Text("id")));
        var actions = new StackPanel { Spacing = 8 }; string text = "";
        foreach (var item in current)
        {
            switch (item.Text("type"))
            {
                case "assistant": text = item.Text("text"); break;
                case "prompt": target.Children.Add(Rich(item.Text("text"))); break;
                case "tool": actions.Children.Add(new Expander { Header = item.Text("title") + " · " + (item.Text("status") switch { "pending" => T("live.pending"), "in_progress" => T("task.working"), "completed" => T("task.done"), "failed" => T("common.failed"), _ => item.Text("status") }), Content = Text(item.Text("text")), HorizontalAlignment = HorizontalAlignment.Stretch }); break;
                case "permission":
                    var permission = Stack(Text(T("perm.ask")), Text(item.Text("title")));
                    foreach (var option in item.Rows("options")) permission.Children.Add(Button(option.Text("name").Length > 0 ? option.Text("name") : option.Text("kind"), async () => { await api!.Post("/api/permission/" + Client.Segment(item.Text("id")), new { option = option.Text("id") }); await Refresh(); })); actions.Children.Add(permission); break;
                case "error": actions.Children.Add(Text(item.Text("text"))); break;
            }
        }
        if (actions.Children.Count > 0) target.Children.Add(new Expander { Header = T("live.turn_actions"), Content = actions, IsExpanded = true, HorizontalAlignment = HorizontalAlignment.Stretch });
        if (text.Length > 0) target.Children.Add(Rich(text)); else if (busy) target.Children.Add(Text(T("live.replying")));
    }
    private Task TogglePlain() { plainMode = !plainMode; DrawConversation(); if (plainMode) Note(T("plain.on_hint")); SaveViewState(); return Task.CompletedTask; }
    private async Task RequestPlain(string[] ids)
    {
        var selectedOrg = org;
        var fresh = ids.Where(id => !plainPending.Contains(PlainKey(id)) && !plain.ContainsKey(PlainKey(id))).Take(200).ToArray(); if (fresh.Length == 0) return;
        foreach (var id in fresh) { plainPending.Add(PlainKey(id)); plainFailed.Remove(PlainKey(id)); }
        try { var result = await api!.Post(Client.Org(selectedOrg, "/plain"), new { ids = fresh.Select(long.Parse).ToArray() }); GotPlain(result["items"], selectedOrg); }
        catch (Exception ex) { foreach (var id in fresh) { plainPending.Remove(selectedOrg + "/" + id); plainFailed.Add(selectedOrg + "/" + id); } if (org == selectedOrg) Note(T("plain.failed", ("error", ex.Message))); }
    }
    private async Task VisiblePlain()
    {
        if (!plainMode || member.Length > 0 || closing) return;
        var visible = new List<string>();
        foreach (var (id, view) in plainTargets)
        {
            if (!view.IsLoaded) continue;
            var point = view.TransformToVisual(chatScroll).TransformPoint(new(0, 0));
            if (point.Y < chatScroll.ActualHeight && point.Y + view.ActualHeight > 0) visible.Add(id);
        }
        await RequestPlain(visible.ToArray());
    }
    private void GotPlain(JsonNode? items, string? targetOrg = null)
    {
        if (items is not JsonObject results) return;
        targetOrg ??= org;
        foreach (var pair in results) { var key = targetOrg + "/" + pair.Key; plain[key] = pair.Value.Text(); plainPending.Remove(key); plainFailed.Remove(key); }
        if (targetOrg == org) DrawConversation();
    }
    private async Task ToggleDigest() { digestOpen = !digestOpen; SaveViewState(); if (digestOpen) await LoadDigest(false); DrawConversation(); }
    private async Task LoadDigest(bool refresh)
    {
        var selectedOrg = org;
        digestPending = true; DrawConversation();
        try { var result = await api!.Post(Client.Org(selectedOrg, "/digest"), new { refresh }); if (org != selectedOrg) return; if (result["digest"] != null) digest = result["digest"]!.DeepClone(); digestPending = result.Flag("pending"); if (refresh && !digestPending) Note(T("digest.up_to_date")); }
        catch (Exception ex) { if (org != selectedOrg) return; digestPending = false; Note(T("digest.failed", ("error", ex.Message))); }
        DrawConversation();
    }
    private UIElement DigestCard()
    {
        var card = Stack(TwoColumns(Heading(T("digest.title"), 14), IconButton("\uE711", "common.collapse", ToggleDigest))); card.Spacing = 6;
        if (digest.Text("text").Length > 0)
        {
            var newer = messages.Count(x => long.TryParse(x.Text("id"), out var id) && id > (long.TryParse(digest.Text("last_id"), out var last) ? last : 0));
            card.Children.Add(Quiet(T(newer > 0 ? "digest.read_newer" : "digest.read", ("n", digest.Text("count")), ("when", When(digest.Text("at"))), ("newer", newer)), 11)); card.Children.Add(Rich(digest.Text("text")));
        }
        else card.Children.Add(Text(digestPending ? T("digest.reading") : T("digest.none")));
        card.Children.Add(Button(digestPending ? T("digest.pending") : T("digest.update"), () => LoadDigest(true)));
        if (snap["org"].Text("secretary").Length > 0) { var ask = Button(T("digest.ask"), async () => { var sec = snap["org"].Text("secretary"); await api!.Post(PathFor("/send"), new { to = new[] { sec }, channel = "private", body = T("digest.ask_message") }); await Select(org, sec); }); ToolTipService.SetToolTip(ask, T("digest.ask_title")); card.Children.Add(ask); }
        InlineActions(card); return card;
    }
    private async Task OpenThread(string id)
    {
        var targetOrg = org;
        if (pane != "thread") previousPane = pane;
        threadId = id; pane = "thread"; threadEditor.Text = drafts.GetValueOrDefault(org + "/thread/" + id, "");
        threadData = new JsonObject(); panelOpen = true; LayoutColumns(); DrawDetail(); SaveViewState();
        var data = await api!.Get(PathFor("/thread?root=" + Client.Segment(id)));
        if (org != targetOrg || threadId != id || pane != "thread") return;
        threadData = data; DrawDetail();
    }
    private void DrawThread()
    {
        if (threadData["root"] == null) { detail.Children.Add(Text(threadData.Text("error").Length > 0 ? T("common.load_failed", ("error", threadData.Text("error"))) : T("common.loading"))); return; }
        detail.Children.Add(Message(threadData["root"]!, true));
        detail.Children.Add(Text(threadData.Rows("replies").Count > 0 ? T("thread.replies", ("n", threadData.Rows("replies").Count)) : T("thread.no_replies")));
        foreach (var reply in threadData.Rows("replies")) detail.Children.Add(Message(reply!, true));
        if (quoteText.Length > 0) { detail.Children.Add(Text(T("composer.quoting", ("who", quoteWho)) + quoteText)); detail.Children.Add(Button(T("composer.cancel_quote"), () => { ClearQuote(); DrawDetail(); SaveViewState(); return Task.CompletedTask; })); }
        threadEditor.PlaceholderText = T("thread.reply_placeholder"); threadEditor.BorderThickness = new Thickness(0);
        threadEditorContainer?.Children.Remove(threadEditor);
        var replyComposer = Stack(threadEditor); threadEditorContainer = replyComposer; var actions = new ActionRow { HorizontalAlignment = HorizontalAlignment.Right }; actions.Children.Add(Microphone(threadEditor));
        var send = IconButton("\uE74A", "common.send", SendThread); threadSendButton = send; send.IsEnabled = !string.IsNullOrWhiteSpace(threadEditor.Text) || quoteText.Length > 0; send.Background = Accent; send.Foreground = new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.White); actions.Children.Add(send); replyComposer.Children.Add(actions); detail.Children.Add(Card(replyComposer));
    }
    private async Task SendThread()
    {
        if (sendingThread || (string.IsNullOrWhiteSpace(threadEditor.Text) && quoteText.Length == 0) || composing.Contains(threadEditor) || threadId.Length == 0) return;
        sendingThread = true;
        try
        {
        await StopVoice();
        var selectedOrg = org; var rootId = threadId; var sent = threadEditor.Text;
        try { await api!.Post(PathFor("/send"), new { body = Quoted(sent.Trim()), reply_to = long.Parse(rootId), channel = member.Length == 0 ? "group" : "private" }); }
        catch (Exception ex) { Note(T("composer.send_failed", ("error", ex.Message))); return; }
        drafts[selectedOrg + "/thread/" + rootId] = "";
        if (org == selectedOrg && threadId == rootId) { if (threadEditor.Text == sent) threadEditor.Text = ""; ClearQuote(); await OpenThread(rootId); await Refresh(); }
        SaveViewState();
        }
        finally { sendingThread = false; }
    }
    private UIElement ToolActions(JsonNode group)
    {
        var pairs = Transcript.PairTools(group.Rows("steps"));
        var failed = pairs.Count(p => p.Result.Flag("error")); var content = new StackPanel { Spacing = 6 };
        var expand = new Expander { Header = T("step.actions", ("n", pairs.Count)) + (failed > 0 ? " · " + T("step.failed", ("n", failed)) : ""), Content = content, HorizontalAlignment = HorizontalAlignment.Stretch };
        expand.Expanding += (_, _) =>
        {
            if (content.Children.Count > 0) return;
            foreach (var (call, result) in pairs)
            {
                var body = new StackPanel { Spacing = 6 }; var tool = call.Text("tool").Replace("mcp__plugin_relic_org__", "Relic ").Replace("mcp__relic_org__", "Relic ").Replace("mcp__", "");
                var row = new Expander { Header = (tool.Length > 0 ? tool : T("common.result")) + " · " + (result.Flag("error") ? T("common.failed") : When((call ?? result).Text("at"))), Content = body, HorizontalAlignment = HorizontalAlignment.Stretch };
                row.Expanding += async (_, _) => await Run(async () =>
                {
                    if (body.Children.Count > 0) return;
                    foreach (var step in new[] { call, result }.Where(s => s != null))
                    {
                        var text = Text(step.Text("text"), 12); body.Children.Add(text);
                        if (step.Flag("cut")) { var full = await api!.Get(PathFor("/step?member=" + Client.Segment(group.Text("member")) + "&i=" + step.Text("i"))); text.Text = full.Text("text"); }
                    }
                }); content.Children.Add(row);
            }
        };
        return expand;
    }
}
