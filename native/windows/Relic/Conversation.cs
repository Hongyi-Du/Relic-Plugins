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
    private readonly ComposerInput threadEditor = new();
    private Panel? threadEditorContainer;
    private Button? threadSendButton;
    private readonly TextBlock quoteLabel = new() { TextWrapping = TextWrapping.Wrap };
    private Button? recipientButton;
    private MenuFlyout? mentionPopup;
    private readonly List<(MenuFlyoutItem Item, Action Pick)> mentionChoices = new();
    private int mentionIndex;
    private bool pickingMention;
    private const int chatLimit = 1000;
    private bool chatMore, olderHistory;
    private readonly Dictionary<string, FrameworkElement> plainTargets = new();
    private readonly DispatcherTimer plainTimer = new() { Interval = TimeSpan.FromMilliseconds(300) };
    private readonly HashSet<ComposerInput> composing = new();
    private readonly Grid emptyConversation = new() { Visibility = Visibility.Collapsed, Padding = new Thickness(30), Margin = new Thickness(20, 8, 20, 0), VerticalAlignment = VerticalAlignment.Top };
    private readonly Border conversationBanner = new() { Visibility = Visibility.Collapsed, Padding = new Thickness(20, 0, 20, 10) };
    private void UpdateSendState()
    {
        if (sendButton != null) { sendButton.IsEnabled = !string.IsNullOrWhiteSpace(editor.Text) || quoteText.Length > 0; sendButton.Opacity = sendButton.IsEnabled ? 1 : .35; }
        if (threadSendButton != null) { threadSendButton.IsEnabled = !string.IsNullOrWhiteSpace(threadEditor.Text) || quoteText.Length > 0; threadSendButton.Opacity = threadSendButton.IsEnabled ? 1 : .35; }
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
        var menu = ComposerMenu();
        var options = new[] { ("all", T("composer.all_members")) }.Concat(snap.Rows("members").Select(m => (m.Text("name"), Display(m.Text("name")))));
        foreach (var (id, label) in options)
        {
            var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10, VerticalAlignment = VerticalAlignment.Center };
            var check = new CheckBox { Style = (Style)Application.Current.Resources["RelicComposerCheckStyle"], IsChecked = recipientNames.Contains(id), Margin = new Thickness(4, 3, 3, 3), VerticalAlignment = VerticalAlignment.Center, IsHitTestVisible = false, IsTabStop = false };
            row.Children.Add(check);
            if (id == "all")
            {
                var glyph = (ReferenceVectorIcon)ReferenceIcon("hash", 17); glyph.Foreground = Paint("5A5853", "B8B5AE");
                row.Children.Add(new Border { Width = 20, Height = 20, CornerRadius = new CornerRadius(6), Background = Paint("EFEEEA", "262624"), Child = glyph });
            }
            else row.Children.Add(Avatar(snap.Rows("members").FirstOrDefault(m => m.Text("name") == id).Text("avatar"), label, 20));
            row.Children.Add(ComposerMenuLabel(label));
            if (id != "all" && id != label) row.Children.Add(ComposerMenuLabel(id, true));
            var avatarText = id == "all" || snap.Rows("members").FirstOrDefault(m => m.Text("name") == id).Text("avatar").Length > 0 ? "" : label[..1].ToUpperInvariant() + " ";
            var item = new MenuFlyoutItem { Text = avatarText + label + (id == "all" || id == label ? "" : " " + id), Tag = row, Style = (Style)Application.Current.Resources["RelicComposerMenuItemStyle"] };
            void Pick()
            {
                if (id == "all") { recipientNames.Clear(); recipientNames.Add("all"); }
                else { recipientNames.Remove("all"); if (!recipientNames.Add(id)) recipientNames.Remove(id); if (recipientNames.Count == 0) recipientNames.Add("all"); }
                menu.Hide(); UpdateRecipient(); SaveViewState();
            }
            item.Click += (_, _) => Pick(); menu.Items.Add(item);
        }
        OpenComposerMenu(menu, recipientButton!); return Task.CompletedTask;
    }
    private TextBlock ComposerMenuLabel(string value, bool secondary = false)
    {
        var text = new TextBlock { Text = value, FontSize = secondary ? 11.96 : 13, FontFamily = new Microsoft.UI.Xaml.Media.FontFamily(secondary ? "Cascadia Code" : "Segoe UI Variable Text"), Foreground = secondary ? Muted : Ink,
            LineHeight = secondary ? 19.136 : 20.8, LineStackingStrategy = LineStackingStrategy.BlockLineHeight, TextWrapping = TextWrapping.NoWrap, VerticalAlignment = VerticalAlignment.Center };
        return text;
    }
    private MenuFlyout ComposerMenu()
    {
        var style = new Style(typeof(MenuFlyoutPresenter));
        style.Setters.Add(new Setter(Control.BackgroundProperty, Paint("FFFFFF", "252523")));
        style.Setters.Add(new Setter(Control.BorderBrushProperty, Paint("DEDBD4", "3A3936")));
        style.Setters.Add(new Setter(Control.BorderThicknessProperty, new Thickness(1)));
        style.Setters.Add(new Setter(Control.CornerRadiusProperty, new CornerRadius(12)));
        style.Setters.Add(new Setter(Control.PaddingProperty, new Thickness(6)));
        style.Setters.Add(new Setter(FrameworkElement.MinWidthProperty, 220d));
        style.Setters.Add(new Setter(FrameworkElement.MaxHeightProperty, root.ActualHeight * .6));
        return new MenuFlyout { MenuFlyoutPresenterStyle = style };
    }
    private void OpenComposerMenu(MenuFlyout menu, FrameworkElement anchor)
    {
        transientFlyout?.Hide(); transientFlyout = menu;
        menu.ShowAt(anchor, new Microsoft.UI.Xaml.Controls.Primitives.FlyoutShowOptions { Placement = Microsoft.UI.Xaml.Controls.Primitives.FlyoutPlacementMode.TopEdgeAlignedLeft, ShowMode = Microsoft.UI.Xaml.Controls.Primitives.FlyoutShowMode.Transient });
    }
    private void UpdateRecipient()
    {
        if (recipientButton != null)
        {
            var target = recipientNames.Contains("all") ? T("msg.everyone") : words.List(recipientNames.Select(Display));
            if (target.Length > 24) target = target[..23] + "…";
            var label = T("composer.send_to", ("to", target));
            // The compound content (label + chevron) does not supply a Button
            // peer name. Keep the actual accessible label in sync with each
            // recipient/language update, just like the visible chip text.
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(recipientButton, label);
            // The chip's label is button content, not selectable conversation
            // text. Its pointer input belongs to the real recipient Button.
            var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 5, VerticalAlignment = VerticalAlignment.Center, IsHitTestVisible = false };
            var text = Ellipsis(label, 12.5); text.IsTextSelectionEnabled = false; text.Foreground = Paint("5A5853", "B8B5AE"); row.Children.Add(text);
            var arrow = (ReferenceVectorIcon)ReferenceIcon("down", 14); arrow.Foreground = text.Foreground; row.Children.Add(arrow);
            recipientButton.Content = row; recipientButton.Height = 28; recipientButton.CornerRadius = new CornerRadius(14); recipientButton.BorderBrush = Paint("DEDBD4", "3A3936"); recipientButton.BorderThickness = new Thickness(1); recipientButton.Padding = new Thickness(11, 0, 11, 0);
            recipientButton.Background = Paint("FFFFFF", "252523"); recipientButton.Margin = new Thickness(0, 0, 4, 0);
            recipientButton.MaxWidth = 230; ToolTipService.SetToolTip(recipientButton, label); recipientButton.Visibility = member.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
        }
    }
    private void MentionMenu()
    {
        mentionPopup?.Hide(); mentionPopup = null; mentionChoices.Clear(); mentionIndex = 0;
        if (pickingMention || member.Length > 0 || org.Length == 0) return;
        var start = editor.SelectionStart; var text = editor.Text[..Math.Min(start, editor.Text.Length)]; var match = Regex.Match(text, @"(?:^|\s)@([^\s@]*)$");
        if (!match.Success) return;
        var choices = snap.Rows("members").Where(m => m.Text("name").StartsWith(match.Groups[1].Value, StringComparison.OrdinalIgnoreCase) || m.Text("display").StartsWith(match.Groups[1].Value, StringComparison.OrdinalIgnoreCase)).Take(8).ToArray();
        if (choices.Length == 0) return;
        var menu = ComposerMenu();
        foreach (var m in choices)
        {
            var label = Display(m.Text("name")); var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10, VerticalAlignment = VerticalAlignment.Center };
            row.Children.Add(Avatar(m.Text("avatar"), label, 20)); row.Children.Add(ComposerMenuLabel(label)); row.Children.Add(ComposerMenuLabel(m.Text("name"), true));
            var option = new MenuFlyoutItem { Text = (m.Text("avatar").Length > 0 ? "" : label[..1].ToUpperInvariant() + " ") + label + " " + m.Text("name"), Tag = row, Style = (Style)Application.Current.Resources["RelicComposerMenuItemStyle"], Background = menu.Items.Count == 0 ? Paint("EFEEEA", "262624") : new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.Transparent) };
            void Pick()
            {
                pickingMention = true;
                try { var at = text.LastIndexOf('@'); var inserted = "@" + label + " "; editor.Text = editor.Text[..at] + inserted + editor.Text[start..]; editor.SelectionStart = at + inserted.Length; recipientNames.Remove("all"); recipientNames.Add(m.Text("name")); menu.Hide(); UpdateRecipient(); SaveViewState(); editor.Focus(FocusState.Programmatic); }
                finally { pickingMention = false; }
            }
            option.Click += (_, _) => Pick(); mentionChoices.Add((option, Pick));
            menu.Items.Add(option);
        }
        mentionPopup = menu; menu.Closed += (_, _) => { if (ReferenceEquals(mentionPopup, menu)) { mentionPopup = null; mentionChoices.Clear(); } }; OpenComposerMenu(menu, editor);
    }
    private bool MentionKey(VirtualKey key)
    {
        if (mentionPopup == null || mentionChoices.Count == 0) return false;
        if (key is VirtualKey.Up or VirtualKey.Down)
        {
            mentionIndex = (mentionIndex + (key == VirtualKey.Down ? 1 : -1) + mentionChoices.Count) % mentionChoices.Count;
            for (var i = 0; i < mentionChoices.Count; i++) mentionChoices[i].Item.Background = i == mentionIndex ? Paint("EFEEEA", "262624") : new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.Transparent);
            return true;
        }
        if (key is VirtualKey.Enter or VirtualKey.Tab) { mentionChoices[mentionIndex].Pick(); return true; }
        if (key == VirtualKey.Escape) { mentionPopup.Hide(); return true; }
        return false;
    }
    private void WireComposer()
    {
        plainTimer.Tick += async (_, _) => { plainTimer.Stop(); await Run(VisiblePlain); };
        chatScroll.ViewChanged += (_, _) => { if (plainMode && !plainTimer.IsEnabled) plainTimer.Start(); };
        foreach (var text in new[] { editor, threadEditor })
        {
            text.TextCompositionStarted += (_, _) => composing.Add(text);
            text.TextCompositionEnded += (_, _) => composing.Remove(text);
            text.ClipboardFailed += (_, failure) => Note(T(failure.Operation == "paste" ? "appmenu.paste_failed" : "msg.copy_failed"));
        }
        threadEditor.KeyDown += async (_, e) =>
        {
            var shift = (Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(VirtualKey.Shift) & Windows.UI.Core.CoreVirtualKeyStates.Down) != 0;
            if (e.Key == VirtualKey.Enter && !shift && !composing.Contains(threadEditor)) { e.Handled = true; await Run(SendThread); }
        };
        editor.KeyDown += async (_, e) =>
        {
            if (!composing.Contains(editor) && MentionKey(e.Key)) { e.Handled = true; return; }
            var shift = (Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(VirtualKey.Shift) & Windows.UI.Core.CoreVirtualKeyStates.Down) != 0;
            if (e.Key == VirtualKey.Enter && !shift && !composing.Contains(editor)) { e.Handled = true; await Run(Send); }
        };
        editor.TextChanged += (_, _) => { if (!pickingMention && !composing.Contains(editor)) DispatcherQueue.TryEnqueue(MentionMenu); };
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
        conversationBanner.Child = null; conversationBanner.Visibility = Visibility.Collapsed; conversationBanner.MaxWidth = double.PositiveInfinity;
        composerRegion.Visibility = org.Length == 0 ? Visibility.Collapsed : Visibility.Visible;
        emptyConversation.Children.Clear(); emptyConversation.Visibility = org.Length == 0 ? Visibility.Visible : Visibility.Collapsed; chatScroll.Visibility = org.Length == 0 ? Visibility.Collapsed : Visibility.Visible; UpdateSendState();
        if (org.Length == 0)
        {
            chatHead.ColumnDefinitions.Clear();
            var header = Heading(T("common.app_name"), 15); header.FontWeight = new Windows.UI.Text.FontWeight { Weight = 650 };
            header.LineHeight = 19.5; header.LineStackingStrategy = LineStackingStrategy.BlockLineHeight; header.VerticalAlignment = VerticalAlignment.Center;
            chatHead.Children.Add(header);
            var title = Heading(T("chat.no_orgs"), 18); title.FontWeight = new Windows.UI.Text.FontWeight { Weight = 650 }; title.TextAlignment = TextAlignment.Center;
            title.LineHeight = 28.8; title.LineStackingStrategy = LineStackingStrategy.BlockLineHeight;
            var hint = Quiet(T("chat.no_orgs_hint"), 14); hint.TextAlignment = TextAlignment.Center;
            hint.LineHeight = hint.FontSize * 1.6; hint.LineStackingStrategy = LineStackingStrategy.BlockLineHeight;
            // The reference keeps its ordinary stream inset and a 70vh
            // placeholder, including the paragraph's real block margins.
            var empty = Stack(title, hint); empty.Spacing = 14; empty.Margin = new Thickness(0, 0, 0, 14);
            empty.HorizontalAlignment = HorizontalAlignment.Center; empty.VerticalAlignment = VerticalAlignment.Center;
            emptyConversation.Height = root.ActualHeight * .7; emptyConversation.Children.Add(empty); return;
        }
        var m = snap.Rows("members").FirstOrDefault(x => x.Text("name") == member);
        chatHead.ColumnDefinitions.Clear(); chatHead.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); chatHead.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); chatHead.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        var titles = new StackPanel { Spacing = 0, VerticalAlignment = VerticalAlignment.Center }; var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 2, VerticalAlignment = VerticalAlignment.Center };
        UIElement portrait = member.Length == 0 ? SidebarPicture("", ChatAvatar(false), 28) : m.Flag("secretary") && m.Text("avatar").Length == 0 ? SidebarPicture("", ChatAvatar(true), 28) : SmallAvatar(m.Text("avatar"), Display(member), size: 28);
        if (member.Length > 0 && m.Text("state") is not ("" or "idle"))
        {
            // Both secAvatar and avatar(dot:true) own the same 10px state dot.
            // The chat's background surrounds it; the sidebar's surface does not.
            var state = m.Text("state");
            var color = state switch
            {
                "working" or "running" => Paint("3E9B5E", "6CC287"), "active" => Paint("75A782", "669572"),
                "waiting" or "starting" => Paint("B7791F", "E2B15A"), "error" => Paint("C2412D", "EE8A78"),
                "vacant" => Paint("B8B5AF", "5F5D58"), _ => OverviewAlpha(Muted, 0)
            };
            var frame = new Grid { Width = 28, Height = 28, VerticalAlignment = VerticalAlignment.Center, UseLayoutRounding = false };
            if (portrait is FrameworkElement face) face.UseLayoutRounding = false;
            frame.Children.Add(portrait);
            FrameworkElement dot = state == "vacant"
                ? new NativeStateDotView(Paint("FFFFFF", "1F1F1E"), color)
                : new Microsoft.UI.Xaml.Shapes.Ellipse { Width = 10, Height = 10, Stroke = Paint("FFFFFF", "1F1F1E"), StrokeThickness = 2, Fill = color, UseLayoutRounding = false };
            // CSS right:-2px; bottom:-2px positions the 10px border box beyond
            // the 28px avatar, without changing the avatar's layout footprint.
            dot.Margin = new Thickness(0, 0, -2, -2); dot.HorizontalAlignment = HorizontalAlignment.Right; dot.VerticalAlignment = VerticalAlignment.Bottom;
            frame.Children.Add(dot); portrait = frame;
        }
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
            actions.Children.Add(ChipButton("lang", T(plainMode ? "chat.plain_on" : "common.plain_words"), T("chat.plain_title"), TogglePlain, plainMode));
            actions.Children.Add(ChipButton("sparkle", T("chat.digest"), T("chat.digest_title"), ToggleDigest, digestOpen));
            var tasks = IconButton("\uE73A", "common.tasks", () => Details("tasks"));
            var tasksIcon = (ReferenceVectorIcon)ReferenceIcon("check", 18);
            tasks.Foreground = Paint("5A5853", "B8B5AE"); tasksIcon.Foreground = tasks.Foreground;
            tasks.Content = tasksIcon; tasks.Padding = new Thickness(0); tasks.CornerRadius = new CornerRadius(8);
            tasks.HorizontalContentAlignment = HorizontalAlignment.Center; tasks.VerticalContentAlignment = VerticalAlignment.Center;
            actions.Children.Add(tasks);
            if (digestOpen) { conversationBanner.Padding = new Thickness(20, 10, 20, 0); conversationBanner.MaxWidth = 920; conversationBanner.Child = DigestCard(); conversationBanner.Visibility = Visibility.Visible; }
        }
        else
        {
            var heading = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
            var roleName = Display(member) == T("common.secretary") ? member : Display(member);
            heading.Children.Add(HeaderLabel(m.Flag("secretary") ? T("chat.secretary_title", ("name", roleName)) : Display(member)));
            if (m.Text("display").Length > 0 && m.Text("display") != member) { var identifier = HeaderLabel(member); identifier.Foreground = Muted; identifier.FontWeight = Microsoft.UI.Text.FontWeights.Normal; identifier.FontFamily = new Microsoft.UI.Xaml.Media.FontFamily("Cascadia Code"); identifier.FontSize = 13.8; heading.Children.Add(identifier); }
            if (m.Flag("leader")) heading.Children.Add(SidebarTag(T("common.leader"), false)); titles.Children.Add(heading);
            titles.Children.Add(HeaderMeta(string.Join(" · ", new[] { snap["org"].Text("name"), m.Text("harness_label"), m.Text("surface_label"), m.Text("model"), MemberState(m.Text("state")) }.Where(x => x.Length > 0))));
            if (m.Flag("embedded") && m.Text("state") is "running" or "waiting") actions.Children.Add(IconButton("\uE71A", "chat.stop_turn", () => Post("/cancel", new { member })));
            Button? card = null; card = IconButton("\uE77B", "chat.card", () => MemberCard(member, card)); actions.Children.Add(card);
            actions.Children.Add(IconButton("\uE81C", "common.context_trace", () => Details("trace", member)));
            if (m.Text("surface") != "chat") actions.Children.Add(IconButton("\uE8B7", "chat.workspace", () => SetPane("workspace")));
            var banner = m.Flag("embedded") ? T("banner.embedded", ("harness", m.Text("harness_label"))) : m.Text("surface") == "subagent" ? m.Text("parent").Length > 0 ? T("banner.subagent_in", ("parent", Display(m.Text("parent")))) : T("banner.subagent") : !Delivery(m.Text("harness"), m.Text("surface")) ? m.Text("harness") == "chatgpt" ? T("member.chatgpt_unavailable") : T("member.desktop_manual") : m.Text("state") == "vacant" ? T("banner.vacant") : m.Flag("has_transcript") ? T("banner.transcript") : T("banner.inbox");
            var amberBanner = !m.Flag("embedded") && (m.Text("surface") == "subagent"
                || !Delivery(m.Text("harness"), m.Text("surface")) || m.Text("state") == "vacant");
            // renderBanner uses the same centered 880px content width as the
            // stream, with a real information icon and wrapping text inside
            // the card. Keeping this as a small, bare caption removed both
            // visible elements and the banner's contribution to chat layout.
            var bannerInk = Paint("5A5853", "B8B5AE");
            var bannerIcon = (ReferenceVectorIcon)ReferenceIcon("info", 15);
            bannerIcon.Foreground = bannerInk; bannerIcon.VerticalAlignment = VerticalAlignment.Top;
            var bannerText = NativePathText.Banner(banner, words.Language, T("common.copy"), T("appmenu.select_all"));
            bannerText.Foreground = bannerInk;
            var bannerContent = new NativeBannerLayout(bannerIcon, bannerText, 8);
            conversationBanner.Padding = new Thickness(20, 10, 20, 0); conversationBanner.MaxWidth = 920;
            conversationBanner.Child = new Border { Child = bannerContent, Padding = new Thickness(12, 8, 12, 8),
                CornerRadius = new CornerRadius(10), BorderThickness = new Thickness(1), UseLayoutRounding = false,
                Background = amberBanner ? Paint("FBF3E2", "3A3020") : Paint("F8F7F5", "191918"),
                BorderBrush = amberBanner ? OverviewAlpha(Paint("B7791F", "E2B15A"), .3) : Line };
            conversationBanner.Visibility = Visibility.Visible;
        }
        var atBottom = chatScroll.ScrollableHeight - chatScroll.VerticalOffset < 120;
        if (chatMore) stream.Children.Add(Button(T("trace.load_older"), LoadOlderMessages));
        var items = ConversationItems().ToArray();
        if (items.Length == 0) stream.Children.Add(Text(member.Length == 0 ? T("chat.empty_group") : T("chat.empty_private")));
        string day = ""; JsonNode? previous = null;
        foreach (var item in items)
        {
            var date = DateTimeOffset.TryParse(item.Text("at"), out var parsed) ? parsed.LocalDateTime.Date.ToString("yyyy-MM-dd") : "";
            string? separatorText = null;
            if (date != day && date.Length > 0) { separatorText = When(item.Text("at")); day = date; previous = null; }
            else if (previous != null && DateTimeOffset.TryParse(previous.Text("at"), out var prior) && parsed - prior > TimeSpan.FromMinutes(20))
            { separatorText = parsed.ToLocalTime().ToString("HH:mm"); previous = null; }
            TextBlock? separator = null;
            if (separatorText != null)
            {
                separator = OverviewText(separatorText, 11.5, true); separator.TextAlignment = TextAlignment.Center;
                // .day uses normal word wrapping, without overflow-wrap:anywhere.
                separator.TextWrapping = TextWrapping.WrapWholeWords;
                separator.Margin = new Thickness(0, 18, 0, 8); stream.Children.Add(separator);
            }
            var rendered = Message(item!, false, Transcript.SameMessageGroup(previous, item!));
            if (separator != null && rendered is FrameworkElement next)
            {
                // Adjacent block margins collapse in .stream-inner, whereas a
                // StackPanel adds them. Retain only the separator's remainder;
                // this also preserves the larger 8px gap in compact density.
                var margin = separator.Margin;
                separator.Margin = new Thickness(margin.Left, margin.Top, margin.Right,
                    Math.Max(0, margin.Bottom - Math.Max(0, next.Margin.Top)));
            }
            try { stream.Children.Add(rendered); }
            catch (System.Runtime.InteropServices.COMException ex)
            {
                throw new InvalidOperationException($"Could not attach rendered conversation item: type={item.Text("type")}, id={item.Text("id")}, control={rendered.GetType().Name}, parent={Microsoft.UI.Xaml.Media.VisualTreeHelper.GetParent(rendered)?.GetType().Name ?? "none"}, dialogOpen={visibleDialog != null}", ex);
            }
            if (item.Text("type") != "acts") previous = item;
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
        if (item.Text("type") == "notice")
        {
            var note = NativePathText.Notice(item.Text("text"), words.Language, T("common.copy"), T("appmenu.select_all"));
            note.Foreground = Muted;
            var layout = new CenteredFractionLayout { Fraction = .86, Margin = new Thickness(0, 8, 0, 0) };
            layout.Children.Add(new Border { Child = note, Padding = new Thickness(10, 2, 10, 2), CornerRadius = new CornerRadius(10), Background = Paint("F8F7F5", "191918") }); return layout;
        }
        if (item.Text("type") == "acts") return ToolActions(item);
        if (item.Text("type") == "receipt") return AutoReceipt(item, inThread);
        if (item.Text("type") == "step")
        {
            var content = Text(item.Text("text")); var expand = new Expander { Header = item.Text("tool").Length > 0 ? item.Text("tool") : T("common.result"), Content = content, HorizontalAlignment = HorizontalAlignment.Stretch };
            expand.Expanding += async (_, _) => await Run(async () => { if (item.Flag("cut")) content.Text = (await api!.Get(PathFor("/step?member=" + Client.Segment(member) + "&i=" + item.Text("i")))).Text("text"); }); return expand;
        }
        var from = item.Text("from"); var body = item.Text("body"); if (body.Length == 0) body = item.Text("text");
        var mine = from == "human";
        var box = new StackPanel { Spacing = 0 }; UIElement? originalAfter = null; UIElement? pendingAfter = null;
        var column = new StackPanel { Spacing = 4, HorizontalAlignment = mine ? HorizontalAlignment.Right : HorizontalAlignment.Left };
        if (!continued)
        {
            var time = DateTimeOffset.TryParse(item.Text("at"), out var at) ? at.ToLocalTime().ToString("HH:mm") : "";
            var label = new MessageHeaderRow { Spacing = 6, HorizontalAlignment = mine ? HorizontalAlignment.Right : HorizontalAlignment.Left };
            NativeLabel Who(string value, double size, bool bold = false, bool mono = false)
            {
                return new NativeLabel(value, mono ? "Cascadia Code" : FontFamilies.UI,
                    size, (ushort)(bold ? 600 : 400), words.Language, size * 1.3, accessibleText: true, wrapWholeWords: true, primaryFontLineSpacing: true)
                { Foreground = bold ? Paint("5A5853", "B8B5AE") : Muted, VerticalAlignment = VerticalAlignment.Bottom };
            }
            label.Children.Add(Who(item.Text("fromLabel").Length > 0 ? item.Text("fromLabel") : Display(from), 12.5, true));
            if (!inThread && member.Length == 0 && snap.Rows("members").Any(m => m.Text("name") == from))
                label.Children.Add(Who(from, 11, mono: true));
            var names = item.Rows("to").Select(x => x.Text()).ToArray(); var everyone = names.Contains("all") || snap.Rows("members").Where(m => m.Text("name") != from).All(m => names.Contains(m.Text("name")));
            if (!inThread && member.Length == 0) label.Children.Add(Who(T("msg.to", ("names", everyone ? T("msg.everyone") : words.List(names.Select(Display)))), 12));
            label.Children.Add(Who(time, 12)); column.Children.Add(label);
        }
        var key = PlainKey(item.Text("id")); var explainable = from != "human" && long.TryParse(item.Text("id"), out _);
        var showingPlain = explainable && (plainOne.Contains(key) || plainMode && member.Length == 0 && !inThread) && plain.ContainsKey(key);
        if (explainable && (plainOne.Contains(key) || plainMode && member.Length == 0 && !inThread) && plain.TryGetValue(key, out var explained))
        {
            var title = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4, Margin = new Thickness(0, 0, 0, 3) };
            var icon = (ReferenceVectorIcon)ReferenceIcon("lang", 13); icon.Foreground = Paint("7058B8", "A894E0"); icon.VerticalAlignment = VerticalAlignment.Center; title.Children.Add(icon);
            var label = OverviewText(T("msg.plain"), 11, weight: 650); label.Foreground = Paint("7058B8", "A894E0"); title.Children.Add(label); box.Children.Add(title); box.Children.Add(Rich(explained));
            var originalLabel = OverviewText(T("msg.original"), 11.5, true); originalLabel.IsTextSelectionEnabled = false;
            var marker = OverviewText("▸ ", 11.5, true); marker.IsTextSelectionEnabled = false;
            var summary = new StackPanel { Orientation = Orientation.Horizontal, Padding = new Thickness(2, 0, 2, 0), HorizontalAlignment = HorizontalAlignment.Left }; summary.Children.Add(marker); summary.Children.Add(originalLabel);
            var original = new Border { Child = Rich(body), Background = Paint("F4F3F0", "2A2A28"), Padding = new Thickness(13, 9, 13, 9), CornerRadius = new CornerRadius(4, 14, 14, 14), Margin = new Thickness(0, 4, 0, 0) };
            if (from == snap["org"].Text("secretary") && member.Length == 0) NativeInsetShadow.Attach(original, Paint("7058B8", "A894E0"));
            var originalLayout = new MessageBubbleLayout { MaxWidth = 720, HorizontalAlignment = HorizontalAlignment.Left }; originalLayout.Children.Add(original);
            var disclosure = DetailsDisclosure(summary, originalLayout); disclosure.HorizontalAlignment = HorizontalAlignment.Left;
            disclosure.RegisterPropertyChangedCallback(Expander.IsExpandedProperty, (_, _) => marker.Text = disclosure.IsExpanded ? "▾ " : "▸ "); originalAfter = disclosure;
        }
        else
        {
            box.Children.Add(Rich(body));
            if (explainable && (plainMode && member.Length == 0 && !inThread || plainOne.Contains(key)))
            {
                pendingAfter = PlainStatus(key, item.Text("id"));
                if (!plainPending.Contains(key) && !plainFailed.Contains(key) && !inThread && member.Length == 0) plainTargets[item.Text("id")] = box;
            }
        }
        var after = new StackPanel { Spacing = 4, HorizontalAlignment = mine ? HorizontalAlignment.Right : HorizontalAlignment.Left };
        if (originalAfter != null) after.Children.Add(originalAfter);
        if (pendingAfter != null) after.Children.Add(pendingAfter);
        // Session transcript turns have recipients but no delivery receipts.
        // An absent read_by is unknown, whereas an actual empty receipt array
        // means nobody has read the Relic message yet (renderItem's contract).
        if (from == "human" && item["read_by"] is JsonArray && item["to"] is JsonArray)
        {
            var others = item.Rows("to").Where(x => x.Text() != "human").Select(x => x.Text()).ToArray(); var read = item.Rows("read_by").Count(x => others.Contains(x.Text()));
            var receipt = Quiet(others.Length == 1 ? read > 0 ? T("msg.read") : T("msg.unread") : T("msg.read_count", ("read", read), ("total", others.Length)), 11);
            // .read sits outside the bubble's emergency-wrap policy.
            receipt.TextWrapping = TextWrapping.WrapWholeWords;
            receipt.LineHeight = 17.6; receipt.LineStackingStrategy = LineStackingStrategy.BlockLineHeight;
            // .msg.mine .body uses justify-items:end for each child, including
            // this receipt independently of the wider thread button below it.
            receipt.HorizontalAlignment = HorizontalAlignment.Right;
            if (others.Length > 1) { var readers = new MenuFlyout(); foreach (var name in others) readers.Items.Add(new MenuFlyoutItem { Text = Display(name) + " · " + T(item.Rows("read_by").Any(x => x.Text() == name) ? "msg.read" : "msg.unread") }); receipt.ContextFlyout = readers; }
            after.Children.Add(receipt);
        }
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 2 };
        Button Action(string iconName, string label, string tip, Func<Task> handler)
        {
            var button = QuietButton("", handler); button.Padding = new Thickness(8, 0, 8, 0); button.Height = 26; button.MinHeight = 0; button.MinWidth = 0; button.CornerRadius = new CornerRadius(6); button.FontSize = 12; button.FontWeight = Microsoft.UI.Text.FontWeights.Normal; button.Foreground = Paint("5A5853", "B8B5AE");
            var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4, VerticalAlignment = VerticalAlignment.Center }; var icon = (ReferenceVectorIcon)ReferenceIcon(iconName, 14); icon.Foreground = button.Foreground; icon.VerticalAlignment = VerticalAlignment.Center; row.Children.Add(icon);
            TextBlock? text = null;
            if (label.Length > 0) { text = OverviewText(label, 12, lineHeight: 19.2); text.Foreground = button.Foreground; text.IsTextSelectionEnabled = false; text.TextWrapping = TextWrapping.NoWrap; text.VerticalAlignment = VerticalAlignment.Center; row.Children.Add(text); }
            void InkState(bool hover) { button.Foreground = hover ? Ink : Paint("5A5853", "B8B5AE"); icon.Foreground = button.Foreground; if (text != null) text.Foreground = button.Foreground; }
            button.PointerEntered += (_, _) => InkState(true); button.PointerExited += (_, _) => InkState(false);
            button.Content = row; ToolTipService.SetToolTip(button, tip); Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(button, label.Length > 0 ? label : tip); actions.Children.Add(button); return button;
        }
        if (explainable && !(plainMode && member.Length == 0 && !inThread)) Action("lang", T(plainOne.Contains(key) ? "msg.original" : "msg.plain"), T(plainOne.Contains(key) ? "msg.hide_plain" : "common.plain_words"), async () => { if (!plainOne.Remove(key)) { plainOne.Add(key); await RequestPlain([item.Text("id")]); } DrawConversation(); });
        Action("quote", T("common.quote"), T("common.quote"), () => { Quote(item.Text("fromLabel").Length > 0 ? item.Text("fromLabel") : Display(from), body); return Task.CompletedTask; });
        if (!inThread && long.TryParse(item.Text("id"), out _)) Action("thread", T("common.reply"), T("msg.reply_in_thread"), () => OpenThread(item.Text("id")));
        var copy = Action("copy", "", T("common.copy"), () => { Copy(body); return Task.CompletedTask; });
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetAutomationId(copy, "message-copy/" + item.Text("id"));
        if (!inThread && item["thread"] != null)
        {
            var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6, VerticalAlignment = VerticalAlignment.Center, IsHitTestVisible = false };
            var faces = new StackPanel { Orientation = Orientation.Horizontal };
            var replyNameParts = new List<string>();
            foreach (var person in item["thread"].Rows("people").Take(3))
            {
                var replyingMember = snap.Rows("members").FirstOrDefault(m => m.Text("name") == person.Text());
                var replyAvatar = SmallAvatar(replyingMember.Text("avatar"), Display(person.Text()), size: 20);
                // PersonPicture's template displays this actual paint content.
                // Text avatars contribute their visible initials; images add no alt text.
                if (replyAvatar is Grid avatarLayout)
                    foreach (var picture in avatarLayout.Children.OfType<PersonPicture>())
                        if (picture.Tag is Border { Child: TextBlock initials } && initials.Text.Length > 0)
                            replyNameParts.Add(initials.Text);
                var replyLayout = (Grid)replyAvatar;
                faces.Children.Add(WrapReplyAvatar(replyLayout, Paint("FFFFFF", "1F1F1E")));
            }
            row.Children.Add(faces);
            var count = Text(T("thread.replies", ("n", item["thread"].Text("count"))), 12.5); count.IsTextSelectionEnabled = false; count.FontWeight = Microsoft.UI.Text.FontWeights.SemiBold; count.Foreground = Accent; row.Children.Add(count);
            var lastReply = Quiet(T("thread.last_reply", ("when", ShortWhen(item["thread"].Text("last_at")))), 12.5); lastReply.IsTextSelectionEnabled = false; row.Children.Add(lastReply);
            var replies = QuietButton("", () => OpenThread(item.Text("id"))); replies.Content = row; replies.Padding = new Thickness(4, 3, 8, 3); replies.CornerRadius = new CornerRadius(8); after.Children.Add(replies);
            replyNameParts.Add(count.Text); replyNameParts.Add(lastReply.Text);
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(replies, string.Join(" ", replyNameParts.Where(part => part.Length > 0)));
        }
        var secretary = from == snap["org"].Text("secretary");
        var bubble = new Border { Child = box, Padding = new Thickness(13, 9, 13, 9), CornerRadius = mine ? new CornerRadius(14, 4, 14, 14) : new CornerRadius(4, 14, 14, 14), Background = mine ? MessageTint() : Paint("F4F3F0", "2A2A28"), BorderBrush = secretary ? Paint("7058B8", "A894E0") : Line, BorderThickness = new Thickness(0), HorizontalAlignment = HorizontalAlignment.Stretch };
        if (showingPlain) { bubble.Background = Paint("EFEBF8", "2E2A3D"); bubble.BorderBrush = OverviewAlpha(Paint("7058B8", "A894E0"), .22); bubble.BorderThickness = new Thickness(1); bubble.Padding = new Thickness(13, 9, 13, 9); }
        // .bubble.plain changes the real border but does not reset .msg.sec's
        // inset shadow. The painter uses its actual inner padding-edge contour.
        if (secretary && member.Length == 0) NativeInsetShadow.Attach(bubble, Paint("7058B8", "A894E0"));
        var bubbleLayout = new MessageBubbleLayout { MaxWidth = 720, HorizontalAlignment = mine ? HorizontalAlignment.Right : HorizontalAlignment.Left }; bubbleLayout.Children.Add(bubble);
        column.Children.Add(bubbleLayout); if (after.Children.Count > 0) column.Children.Add(after);
        var message = new Grid { HorizontalAlignment = mine ? HorizontalAlignment.Right : HorizontalAlignment.Stretch };
        message.Children.Add(column);
        var outer = new Grid { ColumnSpacing = 10, Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.Transparent), HorizontalAlignment = HorizontalAlignment.Stretch, Margin = new Thickness(0, continued ? 4 : preferences.Text("density") == "compact" ? 7 : 14, 0, 0) };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetAutomationId(outer, "message/" + item.Text("id"));
        outer.ColumnDefinitions.Add(new() { Width = mine ? new GridLength(1, GridUnitType.Star) : GridLength.Auto }); outer.ColumnDefinitions.Add(new() { Width = mine ? GridLength.Auto : new GridLength(1, GridUnitType.Star) });
        var speaker = snap.Rows("members").FirstOrDefault(m => m.Text("name") == from);
        var avatar = (FrameworkElement)Avatar(mine ? preferences.Text("avatar") : speaker.Text("avatar"), Display(from), inThread ? 30 : 36); avatar.VerticalAlignment = VerticalAlignment.Top; avatar.Opacity = continued ? 0 : 1; if (continued) avatar.Height = 0;
        ToolTipService.SetToolTip(avatar, Display(from)); if (!mine && speaker != null) avatar.Tapped += async (_, e) => { e.Handled = true; await Run(() => MemberCard(from, avatar)); };
        Grid.SetColumn(avatar, mine ? 1 : 0); Grid.SetColumn(message, mine ? 0 : 1); outer.Children.Add(avatar); outer.Children.Add(message);
        var actionSurface = new MessageHoverSurface(new Border { Child = actions, Background = Paint("FFFFFF", "252523"), BorderBrush = Paint("DEDBD4", "3A3936"), BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(8), Padding = new Thickness(2) })
        { VerticalAlignment = VerticalAlignment.Top, HorizontalAlignment = mine ? HorizontalAlignment.Left : HorizontalAlignment.Right,
            Margin = mine ? new Thickness(8, -12, 0, 0) : new Thickness(0, -12, 8, 0), Visibility = Visibility.Collapsed };
        actionSurface.SetShadows([new(0, 1, 2, Windows.UI.Color.FromArgb(255, 20, 18, 15), .06f)]);
        Grid.SetColumnSpan(actionSurface, 2); outer.Children.Add(actionSurface);
        outer.PointerEntered += (_, _) => actionSurface.Visibility = Visibility.Visible; outer.PointerExited += (_, _) => actionSurface.Visibility = Visibility.Collapsed;
        var interaction = new MessageInteraction(item.Text("id"), body, outer, actionSurface, copy);
        outer.Loaded += (_, _) => { if (!messageInteractions.Contains(interaction)) messageInteractions.Add(interaction); };
        outer.Unloaded += (_, _) => messageInteractions.Remove(interaction);
        return outer;
    }
    private Microsoft.UI.Xaml.Media.SolidColorBrush MessageTint()
    {
        var foreground = Accent.Color; var background = Paint("FFFFFF", "1F1F1E").Color; var mix = Dark ? .24 : .12;
        byte Channel(byte a, byte b) => (byte)Math.Round(a * mix + b * (1 - mix));
        return new Microsoft.UI.Xaml.Media.SolidColorBrush(Windows.UI.Color.FromArgb(255, Channel(foreground.R, background.R), Channel(foreground.G, background.G), Channel(foreground.B, background.B)));
    }
    private void DrawLive(StackPanel target)
    {
        if (member.Length == 0) return;
        var all = liveData.Rows("items").OrderBy(i => long.TryParse(i.Text("seq"), System.Globalization.NumberStyles.Integer, System.Globalization.CultureInfo.InvariantCulture, out var seq) ? seq : 0).ToArray();
        var state = liveData["status"].Text("state"); var busy = state is "running" or "waiting" or "starting";
        var start = Array.FindLastIndex(all, i => i.Flag("start"));
        var current = (busy ? all.Skip(Math.Max(start, 0)) : all.Where(i => i.Text("type") == "permission" && snap.Rows("decisions").Any(d => d.Text("kind") == "permission" && d.Text("id") == i.Text("id")))).ToArray();
        if (current.Length == 0) return;
        var who = member; var speaker = snap.Rows("members").FirstOrDefault(m => m.Text("name") == who);
        var prompt = current.FirstOrDefault(i => i.Text("type") == "prompt");
        if (prompt != null && speaker.Flag("embedded") && speaker.Flag("has_transcript")) target.Children.Add(LivePrompt(prompt.Text("text")));
        var actions = new StackPanel { Padding = new Thickness(0, 4, 0, 4) }; string text = "";
        foreach (var item in current)
        {
            switch (item.Text("type"))
            {
                case "assistant": text = item.Text("text"); break;
                case "tool": actions.Children.Add(LiveToolStep(item)); break;
                case "permission": actions.Children.Add(LivePermissionCard(item)); break;
                case "error": actions.Children.Add(LiveErrorNotice(item.Text("text"))); break;
            }
        }
        var column = new StackPanel { Spacing = 4 };
        var header = new ActionRow { Spacing = 6 };
        header.Children.Add(ConversationMetadata(Display(who), 12.5, true));
        header.Children.Add(ConversationMetadata(state == "running" ? T("live.replying") : MemberState(state)));
        column.Children.Add(header);
        if (actions.Children.Count > 0) column.Children.Add(LiveActions(actions));
        if (text.Length > 0) column.Children.Add(LiveBubble(text)); else if (state == "running") column.Children.Add(LiveTyping());
        var portrait = (FrameworkElement)Avatar(speaker.Text("avatar"), Display(who), 36); ToolTipService.SetToolTip(portrait, Display(who));
        if (speaker != null) portrait.Tapped += async (_, e) => { e.Handled = true; await Run(() => MemberCard(who, portrait)); };
        target.Children.Add(ConversationRow(column, portrait));
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
    private async Task ToggleDigest() { digestOpen = !digestOpen; SaveViewState(); if (digestOpen && digest.Text("text").Length == 0 && !digestPending) await LoadDigest(false); DrawConversation(); }
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
        var hasDigest = digest.Text("text").Length > 0;
        var card = new StackPanel { Spacing = 6, Padding = new Thickness(14, 10, 14, 12) };
        var header = new Grid { ColumnSpacing = 8 };
        for (var i = 0; i < 6; i++) header.ColumnDefinitions.Add(new() { Width = i == 2 ? new GridLength(1, GridUnitType.Star) : GridLength.Auto });
        void Add(UIElement child, int column) { Grid.SetColumn((FrameworkElement)child, column); ((FrameworkElement)child).VerticalAlignment = VerticalAlignment.Center; header.Children.Add(child); }
        var icon = (ReferenceVectorIcon)ReferenceIcon("sparkle", 15); icon.Foreground = Paint("7058B8", "A894E0"); Add(icon, 0); Add(OverviewText(T("digest.title"), 13.5, weight: 700), 1);
        if (hasDigest)
        {
            var newer = messages.Count(x => long.TryParse(x.Text("id"), out var id) && id > (long.TryParse(digest.Text("last_id"), out var last) ? last : 0));
            Add(OverviewText(T(newer > 0 ? "digest.read_newer" : "digest.read", ("n", digest.Text("count")), ("when", Ago(digest.Text("at"))), ("newer", newer)), 12.5, true), 2);
        }
        Button Ghost(string label, Func<Task> action)
        {
            var button = OverviewAction(label, action); button.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.Transparent); button.BorderBrush = button.Background; return button;
        }
        Add(digestPending ? PendingLabel(T("digest.pending")) : Ghost(T(hasDigest ? "digest.update" : "chat.digest"), () => LoadDigest(true)), 3);
        if (snap["org"].Text("secretary").Length > 0)
        {
            var ask = Ghost(T("digest.ask"), async () => { var sec = snap["org"].Text("secretary"); await api!.Post(PathFor("/send"), new { to = new[] { sec }, channel = "private", body = T("digest.ask_message") }); await Select(org, sec); }); ToolTipService.SetToolTip(ask, T("digest.ask_title")); Add(ask, 4);
        }
        var close = IconButton("\uE711", "common.collapse", ToggleDigest); close.Width = close.Height = 24; close.Content = ReferenceIcon("x", 14); Add(close, 5); card.Children.Add(header);
        card.Children.Add(hasDigest ? DetailsMarkdown(digest.Text("text")) : OverviewText(T(digestPending ? "digest.reading" : "digest.none"), 12.5, true));
        var scroll = Scroll(card); scroll.MaxHeight = root.ActualHeight * .4 - 2;
        return new Border { Child = scroll, Background = Paint("EFEBF8", "2E2A3D"), BorderBrush = OverviewAlpha(Paint("7058B8", "A894E0"), .28), BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(12) };
    }
    private UIElement PendingLabel(string value)
    {
        var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 };
        row.Children.Add(new ProgressRing { IsActive = true, Width = 10, Height = 10, MinWidth = 0, MinHeight = 0, Foreground = Paint("7058B8", "A894E0"), VerticalAlignment = VerticalAlignment.Center }); row.Children.Add(OverviewText(value, 11.5, true)); return row;
    }
    private UIElement PlainStatus(string key, string id)
    {
        if (plainPending.Contains(key)) return PendingLabel(T("plain.pending"));
        if (!plainFailed.Contains(key)) return OverviewText(T("plain.waiting"), 11.5, true);
        var retry = QuietButton("", () => RequestPlain([id])); retry.Padding = new Thickness(0); retry.MinHeight = 0;
        var label = OverviewText(T("plain.retry"), 11.5); label.Foreground = Paint("C2412D", "EE8A78"); label.IsTextSelectionEnabled = false; retry.Content = label; return retry;
    }
    private async Task OpenThread(string id)
    {
        var targetOrg = org;
        if (pane != "thread") previousPane = pane;
        threadId = id; pane = "thread"; threadEditor.Text = drafts.GetValueOrDefault(org + "/thread/" + id, "");
        threadData = new JsonObject(); panelOpen = true; LayoutColumns(); DrawToolbar(); DrawDetail(); SaveViewState();
        var data = await api!.Get(PathFor("/thread?root=" + Client.Segment(id)));
        if (org != targetOrg || threadId != id || pane != "thread") return;
        threadData = data; DrawDetail();
    }
    private void DrawThread()
    {
        detail.Padding = new Thickness(0); detail.Spacing = 0;
        if (threadData["root"] == null) { detail.Children.Add(new Border { Padding = new Thickness(16, 14, 16, 14), Child = OverviewText(threadData.Text("error").Length > 0 ? T("common.load_failed", ("error", threadData.Text("error"))) : T("common.loading"), 14, true) }); return; }
        detail.Children.Add(new Border { Child = Message(threadData["root"]!, true), Padding = new Thickness(16, 4, 16, 10), BorderBrush = Line, BorderThickness = new Thickness(0, 0, 0, 1) });
        detail.Children.Add(new Border { Padding = new Thickness(16, 10, 16, 0), Child = OverviewText(threadData.Rows("replies").Count > 0 ? T("thread.replies", ("n", threadData.Rows("replies").Count)) : T("thread.no_replies"), 12, true) });
        var replies = new StackPanel { Padding = new Thickness(16, 0, 16, 16) }; JsonNode? previous = null;
        foreach (var reply in threadData.Rows("replies")) { replies.Children.Add(Message(reply!, true, Transcript.SameMessageGroup(previous, reply!))); previous = reply; }
        detail.Children.Add(replies);
        var replyComposer = new StackPanel { Spacing = 6 };
        if (quoteText.Length > 0)
        {
            var text = OverviewText(T("composer.quoting", ("who", quoteWho)) + "\n" + quoteText, 12.5); text.MaxLines = 3; text.TextTrimming = TextTrimming.CharacterEllipsis; text.Foreground = Paint("5A5853", "B8B5AE");
            var cancel = IconButton("\uE711", "composer.cancel_quote", () => { ClearQuote(); DrawDetail(); SaveViewState(); return Task.CompletedTask; }); cancel.Width = cancel.Height = 22; cancel.Content = ReferenceIcon("x", 14); cancel.VerticalAlignment = VerticalAlignment.Top;
            replyComposer.Children.Add(new Border { Child = TwoColumns(text, cancel), Background = Paint("F8F7F5", "191918"), BorderBrush = Accent, BorderThickness = new Thickness(3, 0, 0, 0), Padding = new Thickness(10, 6, 8, 6), CornerRadius = new CornerRadius(10) });
        }
        threadEditor.PlaceholderText = T("thread.reply_placeholder"); threadEditor.BorderThickness = new Thickness(0); threadEditor.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.Transparent); threadEditor.Foreground = Ink; threadEditor.FontSize = editor.FontSize;
        threadEditor.MinHeight = 26; threadEditor.MaxHeight = 260; threadEditor.Padding = new Thickness(0, 2, 0, 2); threadEditor.CornerRadius = new CornerRadius(0);
        threadEditorContainer?.Children.Remove(threadEditor);
        replyComposer.Children.Add(threadEditor); threadEditorContainer = replyComposer;
        var actions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6, HorizontalAlignment = HorizontalAlignment.Right };
        var microphone = Microphone(threadEditor); microphone.Width = microphone.Height = 32; microphone.CornerRadius = new CornerRadius(16); actions.Children.Add(microphone);
        var send = IconButton("\uE74A", "common.send", SendThread, T("composer.send_title")); threadSendButton = send; send.Width = send.Height = 32; send.CornerRadius = new CornerRadius(16); send.Background = Ink; send.Foreground = Paint("FFFFFF", "1F1F1E"); if (send.Content is ReferenceVectorIcon glyph) glyph.Foreground = send.Foreground;
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(send, T("common.send")); actions.Children.Add(send); replyComposer.Children.Add(actions); UpdateSendState();
        detail.Children.Add(new Border { Child = replyComposer, Margin = new Thickness(12, 10, 12, 14), Padding = new Thickness(14, 10, 10, 8), BorderThickness = new Thickness(1), BorderBrush = Paint("DEDBD4", "3A3936"), CornerRadius = new CornerRadius(18), Background = Paint("FFFFFF", "252523") });
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
        return ConversationActions(group);
    }
}

// CSS grid's fit-content behavior keeps a wrapping bubble at the constrained
// preferred width. RichTextBlock.DesiredSize alone shrinks it to the longest
// already-wrapped line, moving the bubble edge even when line breaks match.
public sealed class MessageBubbleLayout : Panel
{
    protected override Windows.Foundation.Size MeasureOverride(Windows.Foundation.Size availableSize)
    {
        if (Children.Count == 0) return default;
        var child = Children[0];
        child.Measure(new Windows.Foundation.Size(double.PositiveInfinity, double.PositiveInfinity));
        var width = Math.Min(child.DesiredSize.Width, availableSize.Width);
        child.Measure(new Windows.Foundation.Size(width, double.PositiveInfinity));
        return new Windows.Foundation.Size(width, child.DesiredSize.Height);
    }
    protected override Windows.Foundation.Size ArrangeOverride(Windows.Foundation.Size finalSize)
    {
        if (Children.Count > 0) Children[0].Arrange(new Windows.Foundation.Rect(0, 0, finalSize.Width, finalSize.Height));
        return finalSize;
    }
}

// Percentage widths are resolved against the current native measure pass,
// including resizing and the responsive inspector overlay. Reading an older
// ActualWidth while building controls would preserve the previous scene's size.
public sealed class CenteredFractionLayout : Panel
{
    public double Fraction { get; set; } = 1;
    private double childWidth;
    protected override Windows.Foundation.Size MeasureOverride(Windows.Foundation.Size availableSize)
    {
        if (Children.Count == 0) return default;
        var child = Children[0]; child.Measure(new Windows.Foundation.Size(double.PositiveInfinity, double.PositiveInfinity));
        childWidth = Math.Min(child.DesiredSize.Width, availableSize.Width * Fraction);
        child.Measure(new Windows.Foundation.Size(childWidth, double.PositiveInfinity));
        return new Windows.Foundation.Size(double.IsFinite(availableSize.Width) ? availableSize.Width : childWidth, child.DesiredSize.Height);
    }
    protected override Windows.Foundation.Size ArrangeOverride(Windows.Foundation.Size finalSize)
    {
        if (Children.Count > 0) Children[0].Arrange(new Windows.Foundation.Rect((finalSize.Width - childWidth) / 2, 0, childWidth, finalSize.Height));
        return finalSize;
    }
}
