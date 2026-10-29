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
    private readonly TextBlock quoteLabel = new() { TextWrapping = TextWrapping.Wrap };
    private Button? recipientButton;
    private int chatLimit = 1000;
    private bool chatMore;
    private readonly Dictionary<string, FrameworkElement> plainTargets = new();
    private readonly DispatcherTimer plainTimer = new() { Interval = TimeSpan.FromMilliseconds(300) };
    private readonly HashSet<TextBox> composing = new();
    private string PlainKey(string id) => org + "/" + id;
    private void Quote(string who, string body)
    {
        quoteWho = who; quoteText = Regex.Replace(body, @"^(>.*\n?)+\n*", "").Trim();
        if (quoteText.Length > 1200) quoteText = quoteText[..1200] + "…";
        quoteLabel.Text = T("composer.quoting", ("who", who)) + "\n" + quoteText; SaveViewState();
        if (pane == "thread") { DrawDetail(); threadEditor.Focus(FocusState.Programmatic); } else editor.Focus(FocusState.Programmatic);
    }
    private string Quoted(string text)
    {
        if (quoteText.Length == 0) return text;
        var lines = quoteText.Split('\n'); lines[0] = T("sel.quote_line", ("who", quoteWho), ("text", lines[0]));
        return string.Join("\n", lines.Select(l => "> " + l)) + "\n\n" + text;
    }
    private void ClearQuote() { quoteWho = quoteText = quoteLabel.Text = ""; }
    private async Task PickRecipients()
    {
        var box = new StackPanel { Spacing = 8 };
        var options = new[] { ("all", T("composer.all_members")) }.Concat(snap.Rows("members").Select(m => (m.Text("name"), m.Text("display"))));
        var toggles = new List<CheckBox>();
        foreach (var (id, label) in options)
        {
            var check = new CheckBox { Content = label, Tag = id, IsChecked = recipientNames.Contains(id) };
            check.Checked += (_, _) => { foreach (var other in toggles) if (other != check && (id == "all" || other.Tag?.ToString() == "all")) other.IsChecked = false; };
            toggles.Add(check); box.Children.Add(check);
        }
        await Form(T("composer.send_to", ("to", "")), box, () =>
        {
            recipientNames.Clear(); foreach (var check in toggles.Where(c => c.IsChecked == true)) recipientNames.Add(check.Tag!.ToString()!);
            if (recipientNames.Count == 0) recipientNames.Add("all"); UpdateRecipient(); SaveViewState(); return Task.CompletedTask;
        });
    }
    private void UpdateRecipient()
    {
        if (recipientButton != null) { recipientButton.Content = T("composer.send_to", ("to", recipientNames.Contains("all") ? T("msg.everyone") : words.List(recipientNames.Select(Display)))); recipientButton.Visibility = member.Length == 0 ? Visibility.Visible : Visibility.Collapsed; }
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
        menu.ShowAt(editor);
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
        if (org.Length == 0)
        {
            stream.Children.Add(Text(T("chat.no_orgs"), 24)); stream.Children.Add(Text(T("chat.no_orgs_hint")));
            stream.Children.Add(Button(T("common.new_org"), CreateOrg)); return;
        }
        var m = snap.Rows("members").FirstOrDefault(x => x.Text("name") == member);
        if (member.Length == 0)
        {
            chatHead.Children.Add(Stack(Text(T("common.group_chat") + " · " + T("common.members", ("n", snap.Rows("members").Count)), 20), Text(T(snap["org"].Flag("auto_wake") ? "chat.group_meta_on" : "chat.group_meta_off", ("org", snap["org"].Text("name"))), 12)));
            var plainButton = Button(plainMode ? T("chat.plain_on") : T("common.plain_words"), TogglePlain); ToolTipService.SetToolTip(plainButton, T("chat.plain_title")); chatHead.Children.Add(plainButton);
            var digestButton = Button(T("chat.digest"), ToggleDigest); ToolTipService.SetToolTip(digestButton, T("chat.digest_title")); chatHead.Children.Add(digestButton); chatHead.Children.Add(Button(T("common.tasks"), () => Details("tasks")));
            if (digestOpen) stream.Children.Add(DigestCard());
        }
        else
        {
            chatHead.Children.Add(Avatar(m.Text("avatar"), Display(member)));
            chatHead.Children.Add(Stack(Text(m.Flag("secretary") ? T("chat.secretary_title", ("name", Display(member))) : Display(member), 20), Text(m.Text("harness_label") + " · " + m.Text("surface_label") + " · " + m.Text("model") + " · " + T("state." + m.Text("state")), 12)));
            if (m.Flag("embedded") && m.Text("state") is "running" or "waiting") chatHead.Children.Add(Button(T("chat.stop_turn"), () => Post("/cancel", new { member })));
            chatHead.Children.Add(Button(T("chat.card"), () => MemberCard(member))); chatHead.Children.Add(Button(T("common.context_trace"), () => Details("trace", member)));
            chatHead.Children.Add(Button(T("chat.workspace"), async () => { pane = "workspace"; DrawDetail(); await Workspace(); }));
            var banner = m.Flag("embedded") ? T("banner.embedded", ("harness", m.Text("harness_label"))) : m.Text("surface") == "subagent" ? m.Text("parent").Length > 0 ? T("banner.subagent_in", ("parent", Display(m.Text("parent")))) : T("banner.subagent") : !Delivery(m.Text("harness"), m.Text("surface")) ? m.Text("harness") == "chatgpt" ? T("member.chatgpt_unavailable") : T("member.desktop_manual") : m.Text("state") == "vacant" ? T("banner.vacant") : m.Flag("has_transcript") ? T("banner.transcript") : T("banner.inbox");
            stream.Children.Add(Text(banner, 12));
        }
        var atBottom = chatScroll.ScrollableHeight - chatScroll.VerticalOffset < 120;
        if (chatMore || conversation.Flag("more")) stream.Children.Add(Button(T("trace.load_older"), async () => { chatLimit += 1000; await Refresh(); }));
        var items = ConversationItems().ToArray();
        if (items.Length == 0) stream.Children.Add(Text(member.Length == 0 ? T("chat.empty_group") : T("chat.empty_private")));
        string day = ""; JsonNode? previous = null;
        foreach (var item in items)
        {
            var date = item.Text("at").Split('T')[0]; if (date != day && date.Length > 0) { stream.Children.Add(Text(Day(item.Text("at")), 12)); day = date; }
            stream.Children.Add(Message(item!, false, Transcript.SameMessageGroup(previous, item!))); previous = item;
        }
        if (member.Length > 0) DrawLive(stream);
        if (atBottom) DispatcherQueue.TryEnqueue(() => chatScroll.ChangeView(null, chatScroll.ScrollableHeight, null));
        UpdateRecipient(); editor.PlaceholderText = member.Length == 0 ? T("composer.group_placeholder") : T("composer.dm_placeholder", ("name", Display(member)));
        if (plainMode && member.Length == 0) plainTimer.Start();
    }
    private UIElement Message(JsonNode item, bool inThread, bool continued = false)
    {
        if (item.Text("type") == "notice") return Text(item.Text("text"), 12);
        if (item.Text("type") == "acts") return ToolActions(item);
        if (item.Text("type") == "step")
        {
            var content = Text(item.Text("text")); var expand = new Expander { Header = item.Text("tool").Length > 0 ? item.Text("tool") : T("common.result"), Content = content, HorizontalAlignment = HorizontalAlignment.Stretch };
            expand.Expanding += async (_, _) => await Run(async () => { if (item.Flag("cut")) content.Text = (await api!.Get(PathFor("/step?member=" + Client.Segment(member) + "&i=" + item.Text("i")))).Text("text"); }); return expand;
        }
        var from = item.Text("from"); var body = item.Text("body"); if (body.Length == 0) body = item.Text("text");
        var box = new StackPanel { Spacing = 6 };
        if (!continued)
        {
            var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 };
            var speaker = snap.Rows("members").FirstOrDefault(m => m.Text("name") == from);
            var avatar = Button("", () => from == "human" ? Settings() : MemberCard(from)); avatar.Content = Avatar(from == "human" ? preferences.Text("avatar") : speaker.Text("avatar"), Display(from)); row.Children.Add(avatar);
            row.Children.Add(Text((item.Text("fromLabel").Length > 0 ? item.Text("fromLabel") : Display(from)) + " · " + When(item.Text("at")), 12)); box.Children.Add(row);
        }
        if (!inThread && member.Length == 0) box.Children.Add(Text(T("msg.to", ("names", words.List(item.Rows("to").Select(x => Display(x.Text()))))), 12));
        var key = PlainKey(item.Text("id")); var explainable = from != "human" && long.TryParse(item.Text("id"), out _);
        if (item.Text("type") == "receipt") box.Children.Add(new Expander { Header = T("msg.auto_receipt_to", ("names", words.List(item.Rows("to").Select(x => Display(x.Text()))))), Content = Text(body.Replace("[Relic auto-receipt]", "")) });
        else if (explainable && (plainOne.Contains(key) || plainMode && member.Length == 0 && !inThread) && plain.TryGetValue(key, out var explained))
        { box.Children.Add(Text(T("msg.plain"), 12)); box.Children.Add(Rich(explained)); box.Children.Add(new Expander { Header = T("msg.original"), Content = Rich(body) }); }
        else
        {
            box.Children.Add(Rich(body));
            if (explainable && (plainMode && member.Length == 0 && !inThread || plainOne.Contains(key)))
            {
                box.Children.Add(Button(plainPending.Contains(key) ? T("plain.pending") : plainFailed.Contains(key) ? T("plain.retry") : T("plain.waiting"), () => RequestPlain([item.Text("id")])));
                if (!plainPending.Contains(key) && !plainFailed.Contains(key) && !inThread && member.Length == 0) plainTargets[item.Text("id")] = box;
            }
        }
        if (from == "human" && item.Rows("to").Count > 0)
        {
            var others = item.Rows("to").Where(x => x.Text() != "human").Select(x => x.Text()).ToArray(); var read = item.Rows("read_by").Count(x => others.Contains(x.Text()));
            box.Children.Add(Text(others.Length == 1 ? read > 0 ? T("msg.read") : T("msg.unread") : T("msg.read_count", ("read", read), ("total", others.Length)), 12));
            if (others.Length > 1) box.Children.Add(new Expander { Header = T("msg.read_count", ("read", read), ("total", others.Length)), Content = Text(string.Join("\n", others.Select(name => Display(name) + " · " + T(item.Rows("read_by").Any(x => x.Text() == name) ? "msg.read" : "msg.unread")))) });
        }
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 5 };
        if (explainable) actions.Children.Add(Button(plainOne.Contains(key) ? T("msg.hide_plain") : T("common.plain_words"), async () => { if (!plainOne.Remove(key)) { plainOne.Add(key); await RequestPlain([item.Text("id")]); } DrawConversation(); }));
        actions.Children.Add(Button(T("common.quote"), () => { Quote(Display(from), body); return Task.CompletedTask; }));
        if (!inThread && long.TryParse(item.Text("id"), out _)) actions.Children.Add(Button(T("msg.reply_in_thread"), () => OpenThread(item.Text("id"))));
        actions.Children.Add(Button(T("common.copy"), () => { Copy(body); return Task.CompletedTask; })); box.Children.Add(actions);
        if (!inThread && item["thread"] != null) box.Children.Add(Button(T("thread.replies", ("n", item["thread"].Text("count"))) + " · " + T("thread.last_reply", ("when", When(item["thread"].Text("last_at")))), () => OpenThread(item.Text("id"))));
        return box;
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
        var card = Stack(Text(T("digest.title"), 18));
        if (digest.Text("text").Length > 0)
        {
            var newer = messages.Count(x => long.TryParse(x.Text("id"), out var id) && id > (long.TryParse(digest.Text("last_id"), out var last) ? last : 0));
            card.Children.Add(Text(T(newer > 0 ? "digest.read_newer" : "digest.read", ("n", digest.Text("count")), ("when", digest.Text("at")), ("newer", newer)), 12)); card.Children.Add(Rich(digest.Text("text")));
        }
        else card.Children.Add(Text(digestPending ? T("digest.reading") : T("digest.none")));
        card.Children.Add(Button(digestPending ? T("digest.pending") : T("digest.update"), () => LoadDigest(true)));
        if (snap["org"].Text("secretary").Length > 0) { var ask = Button(T("digest.ask"), async () => { var sec = snap["org"].Text("secretary"); await api!.Post(PathFor("/send"), new { to = new[] { sec }, channel = "private", body = T("digest.ask_message") }); await Select(org, sec); }); ToolTipService.SetToolTip(ask, T("digest.ask_title")); card.Children.Add(ask); }
        card.Children.Add(Button(T("common.collapse"), ToggleDigest)); return card;
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
        detail.Children.Add(Button(T("common.close"), () => { threadId = ""; pane = previousPane; LayoutColumns(); DrawDetail(); SaveViewState(); return Task.CompletedTask; }));
        if (threadData["root"] == null) { detail.Children.Add(Text(threadData.Text("error").Length > 0 ? T("common.load_failed", ("error", threadData.Text("error"))) : T("common.loading"))); return; }
        detail.Children.Add(Message(threadData["root"]!, true));
        detail.Children.Add(Text(threadData.Rows("replies").Count > 0 ? T("thread.replies", ("n", threadData.Rows("replies").Count)) : T("thread.no_replies")));
        foreach (var reply in threadData.Rows("replies")) detail.Children.Add(Message(reply!, true));
        if (quoteText.Length > 0) { detail.Children.Add(Text(T("composer.quoting", ("who", quoteWho)) + quoteText)); detail.Children.Add(Button(T("composer.cancel_quote"), () => { ClearQuote(); DrawDetail(); SaveViewState(); return Task.CompletedTask; })); }
        threadEditor.PlaceholderText = T("thread.reply_placeholder"); detail.Children.Add(threadEditor); detail.Children.Add(Microphone(threadEditor));
        detail.Children.Add(Button(T("common.send"), SendThread));
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
