using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Relic.Core;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private JsonNode platform = new JsonObject();
    private string Display(string name) => name == "human" ? (preferences.Text("name").Length > 0 ? preferences.Text("name") : T("common.you")) : snap.Rows("members").FirstOrDefault(m => m.Text("name") == name).Text("display") is { Length: > 0 } display ? display : name;
    private bool Delivery(string harness, string surface) => harness == "chatgpt" ? platform.Flag("chatgpt_delivery") : surface is "gui" or "desktop" ? harness switch { "codex" => platform.Flag("codex_desktop_wake"), "claude-code" => platform.Flag("claude_desktop_wake"), _ => true } : true;
    private static string HarnessTitle(string harness) => harness switch { "claude-code" => "Claude Code", "codex" => "Codex", "chatgpt" => "ChatGPT", "claude-chat" => "Claude", _ => harness };
    private string Identity(JsonNode c) => c.Text("state") == "vacant" ? (c.Text("harness_label").Length > 0 ? T("card.identity_vacant_harness", ("harness", c.Text("harness_label"))) : T("card.identity_vacant")) : c.Text("surface") switch
    {
        "subagent" => c.Text("parent").Length > 0 ? T("card.identity_subagent_parent", ("harness", c.Text("harness_label")), ("parent", Display(c.Text("parent")))) : T("card.identity_subagent", ("harness", c.Text("harness_label"))),
        "acp" => T("card.identity_acp", ("harness", c.Text("harness_label"))),
        "chat" => T("card.identity_chat", ("harness", c.Text("harness_label"))),
        _ => T("card.identity_session", ("where", c.Text("harness_label") + " " + c.Text("surface_label")))
    };
    private async Task MemberCard(string name, FrameworkElement? anchor = null)
    {
        var id = org; var c = await api!.Get(Client.Org(id, "/member/" + Client.Segment(name))); var editingName = false; var editingModel = false;
        var box = new StackPanel { Spacing = 12, Width = 302 };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(box, T("card.aria", ("name", Display(name))));
        Button Ghost(string label, Func<Task> action)
        {
            var button = OverviewAction(label, action); button.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.Transparent); button.BorderThickness = new Thickness(1); button.BorderBrush = new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.Transparent); return button;
        }
        TextBlock Mono(string text, double size = 11.5)
        {
            var label = OverviewText(text, size); label.FontFamily = new Microsoft.UI.Xaml.Media.FontFamily("Cascadia Code"); return label;
        }
        OverviewBadgeView Tag(string label)
        {
            var text = OverviewText(label, 10.5, weight: 600, lineHeight: 18); text.Foreground = Paint("5A5853", "B8B5AE");
            return new OverviewBadgeView { Content = text, FontSize = 10.5, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold, Foreground = text.Foreground, Background = Paint("EFEEEA", "262624"), Padding = new Thickness(6, 0, 6, 0), CornerRadius = new CornerRadius(5) };
        }
        async Task Reload()
        {
            await Refresh(); c = await api.Get(Client.Org(id, "/member/" + Client.Segment(name))); Fill();
        }
        void Fill()
        {
            box.Children.Clear();
            var face = new Grid { Width = 60, Height = 60 }; face.Children.Add(Avatar(c.Text("avatar"), Display(name), 60));
            if (c.Text("state") is not ("" or "idle"))
            {
                var state = c.Text("state"); var color = state switch { "working" or "running" => Paint("3E9B5E", "6CC287"), "waiting" or "starting" => Paint("B7791F", "E2B15A"), "error" => Paint("C2412D", "EE8A78"), "active" => Paint("75A782", "669572"), _ => Paint("B8B5AF", "5F5D58") };
                var dot = new Border { Width = 10, Height = 10, CornerRadius = new CornerRadius(5), BorderThickness = new Thickness(2), BorderBrush = Paint("FFFFFF", "1F1F1E"), Background = state == "vacant" ? new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.Transparent) : color,
                    HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Bottom, Margin = new Thickness(0, 0, -2, -2) };
                if (state == "vacant") dot.Child = new Microsoft.UI.Xaml.Shapes.Ellipse { Stroke = color, StrokeThickness = 1.5 }; face.Children.Add(dot);
            }
            var avatar = QuietButton("", async () => { transientFlyout?.Hide(); await ChangeAvatar(name); await MemberCard(name, anchor); }); avatar.Content = face; avatar.Padding = new Thickness(0); avatar.Width = avatar.Height = 60; avatar.CornerRadius = new CornerRadius(14); ToolTipService.SetToolTip(avatar, T("card.change_avatar"));
            var heading = new Grid { ColumnSpacing = 14 }; heading.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); heading.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); heading.Children.Add(avatar);
            var identity = new StackPanel { VerticalAlignment = VerticalAlignment.Center }; Grid.SetColumn(identity, 1); heading.Children.Add(identity);
            if (editingName)
            {
                var label = SettingsInput(c.Flag("display_custom") ? c.Text("display") : "", c.Text("display").Length > 0 ? c.Text("display") : T("card.new_name")); label.MaxLength = 40; label.Height = 32.4; label.CornerRadius = new CornerRadius(8); label.Padding = new Thickness(8, 4, 34, 4);
                async Task SaveName()
                {
                    var value = label.Text.Trim(); var result = await api.Post(Client.Org(id, "/rename"), new { member = name, name = value });
                    Note(value.Length > 0 ? T("card.renamed") + (result.Text("note").Length > 0 ? " " + result.Text("note") : "") : T("card.name_reset")); editingName = false; await Reload();
                }
                var rename = TwoColumns(SettingsVoiceField(label, double.NaN), OverviewAction(T("common.save"), SaveName, true)); rename.ColumnSpacing = 6; identity.Children.Add(rename);
                label.KeyDown += async (_, e) => { if (e.Key == Windows.System.VirtualKey.Enter) { e.Handled = true; await Run(SaveName); } else if (e.Key == Windows.System.VirtualKey.Escape) { e.Handled = true; editingName = false; Fill(); } };
                label.Loaded += (_, _) => label.Focus(FocusState.Programmatic);
            }
            else
            {
                var title = new ActionRow { Spacing = 6 }; var display = OverviewText(c.Text("display").Length > 0 ? c.Text("display") : name, 17, weight: 650, lineHeight: 22.1); display.Margin = new Thickness(0, .95, 0, .95); title.Children.Add(display);
                void AddTag(OverviewBadgeView tag) { tag.Margin = new Thickness(0, 3, 0, 3); title.Children.Add(tag); }
                if (c.Flag("leader")) AddTag(SidebarTag(T("common.leader"), false)); if (c.Flag("secretary")) AddTag(SidebarTag(T("common.secretary"), true)); if (c["ex_officio"] != null) AddTag(Tag(T("card.ex_officio_tag")));
                var editName = IconButton("\uE70F", "card.new_name", () => { editingName = true; Fill(); return Task.CompletedTask; }, T("card.rename_hint")); editName.Content = ReferenceIcon("edit", 14); editName.Width = editName.Height = 24; editName.Padding = new Thickness(5); title.Children.Add(editName); identity.Children.Add(title);
            }
            var identityLabel = Mono(name + (c.Flag("display_custom") ? "" : " · " + T("card.auto_named")), 12); identityLabel.Foreground = Muted; identity.Children.Add(identityLabel); box.Children.Add(heading);
            var kv = new Grid { ColumnSpacing = 12, RowSpacing = 7 }; kv.ColumnDefinitions.Add(new() { Width = new GridLength(52) }); kv.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
            void Row(string key, UIElement value)
            {
                var row = kv.RowDefinitions.Count; kv.RowDefinitions.Add(new() { Height = GridLength.Auto }); var term = OverviewText(T(key), 12.5, true); Grid.SetRow(term, row); kv.Children.Add(term);
                Grid.SetRow((FrameworkElement)value, row); Grid.SetColumn((FrameworkElement)value, 1); kv.Children.Add(value);
            }
            void TextRow(string key, string value) { if (value.Length > 0) Row(key, OverviewText(value)); }
            Button SeatLink(string label, Func<Task> action)
            {
                var button = QuietButton("", action); var text = OverviewText(label); text.Foreground = Accent; button.Content = text; button.Padding = new Thickness(0); button.MinHeight = 0; button.HorizontalAlignment = HorizontalAlignment.Left; button.CornerRadius = new CornerRadius(0); return button;
            }
            TextRow("common.role", c.Text("role").Length > 0 ? c.Text("role") : T("card.no_role")); TextRow("card.identity", Identity(c));
            if (c["ex_officio"] != null) Row("card.seat_origin", SeatLink(T("card.ex_officio", ("org", c["ex_officio"].Text("org_name"))), async () => { transientFlyout?.Hide(); await Select(c["ex_officio"].Text("org")); }));
            if (c.Rows("also_in").Count > 0)
            {
                var seats = new StackPanel { Spacing = 3 };
                foreach (var seat in c.Rows("also_in"))
                {
                    var button = SeatLink(T("card.also_in_item", ("org", seat.Text("org_name")), ("member", seat.Text("member"))), async () => { transientFlyout?.Hide(); await Select(seat.Text("org"), seat.Text("member")); });
                    if (seat.Text("role").Length > 0) ToolTipService.SetToolTip(button, seat.Text("role"));
                    if (seat.Flag("main")) { var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 }; var label = (UIElement)button.Content; button.Content = null; row.Children.Add(label); row.Children.Add(Tag(T("card.main_seat"))); button.Content = row; } seats.Children.Add(button);
                }
                Row("card.also_in", seats);
            }
            var modelCell = new StackPanel(); var modelLine = new ActionRow { Spacing = 3 }; var modelLabel = OverviewText((c.Text("model").Length > 0 ? c.Text("model") : T("common.default_model")) + (c.Text("effort").Length > 0 ? " · " + c.Text("effort") : "")); modelLabel.Margin = new Thickness(0, c.Flag("model_editable") ? 3 : 0, 0, 0); modelLine.Children.Add(modelLabel);
            if (c.Flag("model_editable")) modelLine.Children.Add(Ghost(T(editingModel ? "common.collapse" : "common.change"), () => { editingModel = !editingModel; Fill(); return Task.CompletedTask; })); modelCell.Children.Add(modelLine);
            if (!c.Flag("model_editable") && c.Text("model_note").Length > 0) { var hint = OverviewText(c.Text("model_note"), 11.5, true); hint.Margin = new Thickness(0, 2, 0, 0); modelCell.Children.Add(hint); }
            if (editingModel && c.Flag("model_editable"))
            {
                var modelFields = new StackPanel { Spacing = 6, Margin = new Thickness(0, 6, 0, 0) };
                ComboBox Select(string selected, string defaultText, IEnumerable<string> values)
                {
                    var choice = new ComboBox { HorizontalAlignment = HorizontalAlignment.Stretch, MinHeight = 0, FontSize = 12.5, FontFamily = new Microsoft.UI.Xaml.Media.FontFamily("Segoe UI Variable Text"), Padding = new Thickness(8, 4, 8, 4), BorderThickness = new Thickness(1), BorderBrush = Paint("DEDBD4", "3A3936"), Background = Paint("FFFFFF", "1F1F1E"), CornerRadius = new CornerRadius(8) };
                    choice.Items.Add(new ComboBoxItem { Content = defaultText, Tag = "" }); foreach (var value in values) choice.Items.Add(new ComboBoxItem { Content = value, Tag = value }); SetChoice(choice, selected); modelFields.Children.Add(choice); return choice;
                }
                var model = Select(c.Text("model"), T("common.default_model"), c.Rows("models").Select(x => x.Text())); var effort = Select(c.Text("effort"), T("common.default_effort"), c.Rows("efforts").Select(x => x.Text()));
                modelFields.Children.Add(OverviewText(c.Text("model_note"), 11.5, true)); modelFields.Children.Add(OverviewAction(T("card.save_model"), async () => { var result = await api.Post(Client.Org(id, "/model"), new { member = name, model = Value(model), effort = Value(effort) }); Note(result.Text("applied") == "now" ? T("card.model_switched") : T("card.model_next_turn")); editingModel = false; await Reload(); }, true)); modelCell.Children.Add(modelFields);
            }
            Row("common.model", modelCell);
            var status = new ActionRow { Spacing = 3 }; var stateLabel = MemberState(c.Text("state")); status.Children.Add(OverviewChip(stateLabel, c.Text("state") switch { "running" or "working" => "ok", "waiting" => "warn", "error" => "bad", _ => "" }));
            if (c.Text("detail").Length > 0 && c.Text("detail") != stateLabel) status.Children.Add(OverviewText(c.Text("detail"))); Row("common.status", status);
            if (c.Text("doing").Length > 0) TextRow("card.doing", c.Text("doing_at").Length > 0 ? T("card.doing_since", ("doing", c.Text("doing")), ("ago", Ago(c.Text("doing_at")))) : c.Text("doing"));
            var tasks = c.Rows("tasks").Where(t => t.Text("status") is not ("done" or "dropped")).ToArray();
            if (tasks.Length > 0) { var rows = new StackPanel(); foreach (var task in tasks) { var label = OverviewText(task.Text("id") + " " + task.Text("title")); label.TextWrapping = TextWrapping.NoWrap; label.TextTrimming = TextTrimming.CharacterEllipsis; rows.Children.Add(label); } Row("card.owns", rows); }
            else if (c.Rows("tasks").Count > 0) TextRow("card.owns", T("card.tasks_done", ("n", c.Rows("tasks").Count)));
            if (c.Text("agent").Length > 0)
            {
                var session = new TextBlock { FontSize = 12.5, FontFamily = new Microsoft.UI.Xaml.Media.FontFamily("Segoe UI Variable Text"), Foreground = Ink, TextWrapping = TextWrapping.Wrap, LineHeight = 20, LineStackingStrategy = LineStackingStrategy.BlockLineHeight };
                session.Inlines.Add(new Microsoft.UI.Xaml.Documents.Run { Text = "subagent " }); session.Inlines.Add(new Microsoft.UI.Xaml.Documents.Run { Text = c.Text("agent")[..Math.Min(12, c.Text("agent").Length)], FontSize = 11.5, FontFamily = new Microsoft.UI.Xaml.Media.FontFamily("Cascadia Code") });
                if (c.Text("parent").Length > 0) session.Inlines.Add(new Microsoft.UI.Xaml.Documents.Run { Text = T("card.in_parent_session", ("parent", Display(c.Text("parent")))) }); ToolTipService.SetToolTip(session, c.Text("agent")); Row("common.session", session);
            }
            else if (c.Text("session").Length > 0) { var session = Mono(c.Text("session")[..Math.Min(18, c.Text("session").Length)] + (c.Text("session").Length > 18 ? "…" : "")); ToolTipService.SetToolTip(session, c.Text("session")); Row("common.session", session); }
            if (c.Text("cwd").Length > 0) Row("card.folder", Mono(OverviewClip(c.Text("cwd"), 64)));
            TextRow("card.joined", c.Text("joined_at").Length > 0 ? When(c.Text("joined_at")) + (int.TryParse(c.Text("carriers"), out var carriers) && carriers > 1 ? " · " + T("card.session_nth", ("n", carriers)) : "") : "");
            if (c.Rows("recent").Count > 0)
            {
                var recent = new StackPanel(); foreach (var entry in c.Rows("recent").Take(4))
                {
                    var tool = System.Text.RegularExpressions.Regex.Replace(entry.Text("tool").Length > 0 ? entry.Text("tool") : "tool", "^mcp__plugin_relic_org__|^mcp__relic_org__", "Relic "); tool = System.Text.RegularExpressions.Regex.Replace(tool, "^mcp__", "");
                    var label = OverviewText(Ago(entry.Text("at")) + " " + tool + " " + OverviewClip(entry.Text("summary"), 50), 12.5, true); label.TextWrapping = TextWrapping.NoWrap; label.TextTrimming = TextTrimming.CharacterEllipsis; recent.Children.Add(label);
                }
                Row("card.recent", recent);
            }
            box.Children.Add(new Border { Child = kv, BorderBrush = Line, BorderThickness = new Thickness(0, 1, 0, 0), Padding = new Thickness(0, 12, 0, 0), Margin = new Thickness(0, 12.5, 0, 12.5) });
            Button Action(string label, Func<Task> action, bool primary = false)
            {
                var button = OverviewAction(label, action, primary); button.Height = 32; button.Padding = new Thickness(13, 0, 13, 0); button.CornerRadius = new CornerRadius(9); if (button.Content is TextBlock text) { text.FontSize = 13; text.LineHeight = 20.8; } button.HorizontalAlignment = HorizontalAlignment.Stretch; return button;
            }
            var message = Action(T("card.message"), async () => { transientFlyout?.Hide(); await Select(id, name); }, true); var trace = Action(T("common.context_trace"), async () => { transientFlyout?.Hide(); await Details("trace", name); });
            message.Measure(new(double.PositiveInfinity, double.PositiveInfinity)); trace.Measure(new(double.PositiveInfinity, double.PositiveInfinity));
            var actions = new Grid { ColumnSpacing = 8 }; actions.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star), MinWidth = message.DesiredSize.Width }); actions.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star), MinWidth = trace.DesiredSize.Width }); actions.Children.Add(message); Grid.SetColumn(trace, 1); actions.Children.Add(trace); box.Children.Add(actions);
            var seatActions = new ActionRow { Spacing = 6 };
            void SeatButton(string title, string hint, Func<Task> action) { var button = Ghost(title, action); ToolTipService.SetToolTip(button, T(hint)); seatActions.Children.Add(button); }
            var own = c.Text("surface") is not ("chat" or "subagent"); var hosted = own && !c.Flag("embedded") && (c["config"].Text("harness").Length > 0 || c.Text("surface") is "cli" or "desktop");
            if (own && (c.Flag("embedded") || hosted && Delivery(c.Text("harness"), c["config"].Text("surface").Length > 0 ? c["config"].Text("surface") : c.Text("surface")))) SeatButton(T("card.new_session"), "card.new_session_hint", () => SeatAction("fresh", name, c.Text("session").Length > 0 ? T("card.new_session_confirm", ("name", Display(name))) : ""));
            if (hosted) { if (c.Text("session").Length > 0) SeatButton(T("card.open_session"), "card.open_session_hint", () => SeatAction("open_session", name)); SeatButton(T("card.edit_setup"), "card.edit_setup_hint", async () => { transientFlyout?.Hide(); await MemberDialog(edit: name); }); }
            if (c.Text("harness") == "chatgpt") SeatButton(c.Text("waiting_replies") is "" or "0" ? T("card.forward_reply") : T("card.forward_reply_waiting", ("n", c.Text("waiting_replies"))), "card.forward_reply_hint", async () => { transientFlyout?.Hide(); await Forward(name); });
            if (c.Text("session").Length > 0) SeatButton(T("card.leave_seat"), "card.leave_seat_hint", () => SeatAction("unbind", name, T("card.leave_seat_confirm", ("name", Display(name)))));
            if (seatActions.Children.Count > 0) box.Children.Add(new Border { Child = seatActions, BorderBrush = Line, BorderThickness = new Thickness(0, 1, 0, 0), Padding = new Thickness(0, 10, 0, 0) });
        }
        Fill(); transientFlyout?.Hide(); box.RequestedTheme = root.RequestedTheme; foreach (var resource in root.Resources) box.Resources[resource.Key] = resource.Value;
        var scroll = Scroll(box); scroll.MaxHeight = Math.Max(0, root.ActualHeight - 62);
        var presenter = new Style(typeof(FlyoutPresenter)); presenter.Setters.Add(new Setter(Control.PaddingProperty, new Thickness(18))); presenter.Setters.Add(new Setter(Control.BorderThicknessProperty, new Thickness(1))); presenter.Setters.Add(new Setter(Control.BorderBrushProperty, Line)); presenter.Setters.Add(new Setter(Control.BackgroundProperty, Paint("FFFFFF", "252523"))); presenter.Setters.Add(new Setter(Control.CornerRadiusProperty, new CornerRadius(16))); presenter.Setters.Add(new Setter(FrameworkElement.MinWidthProperty, 0d)); presenter.Setters.Add(new Setter(FrameworkElement.MaxWidthProperty, 340d)); presenter.Setters.Add(new Setter(FrameworkElement.MaxHeightProperty, Math.Max(0, root.ActualHeight - 24)));
        var flyout = new Flyout { Content = scroll, Placement = Microsoft.UI.Xaml.Controls.Primitives.FlyoutPlacementMode.BottomEdgeAlignedRight, FlyoutPresenterStyle = presenter }; transientFlyout = flyout; flyout.ShowAt(anchor ?? chatHead);
    }
    private async Task SeatAction(string action, string who, string confirm = "")
    {
        if (confirm.Length > 0 && !await Confirm(confirm)) return;
        var route = action switch { "fresh" => "/fresh", "open_session" => "/open_session", "unbind" => "/unbind", _ => throw new ArgumentException(action) };
        await Post(route, new { member = who });
        Note(action switch { "fresh" => T("seat.fresh", ("name", Display(who))), "unbind" => T("seat.unbind", ("name", Display(who))), "open_session" => T("seat.open_session", ("name", Display(who))), _ => T("seat.done") });
    }
    private async Task Forward(string who)
    {
        var target = org; JsonNode info;
        try { info = await api!.Get(Client.Org(target, "/waiting") + "?member=" + Client.Segment(who)); }
        catch { info = new JsonObject(); }
        var first = info.Rows("waiting").FirstOrDefault();
        var dialog = new ContentDialog { XamlRoot = root.XamlRoot }; var panel = new StackPanel();
        panel.Children.Add(OverviewText(T("forward.title", ("name", Display(who))), 17, weight: 650));
        panel.Children.Add(OverviewText(first == null ? T("forward.how", ("name", Display(who))) : T("forward.waiting", ("name", Display(who)), ("n", info.Rows("waiting").Count), ("ids", string.Join(",", first.Rows("ids").Select(x => x.Text())))), 12.5, true));
        var form = new StackPanel { Spacing = 12 };
        var to = FormInput(string.Join(",", (first?.Rows("to") ?? info.Rows("members")).Select(x => x.Text())), T("forward.to_placeholder"));
        var body = FormInput("", T("forward.body_placeholder"), multiline: true); body.Height = 216;
        form.Children.Add(FormLabel("forward.to", SettingsVoiceField(to, double.NaN))); form.Children.Add(FormLabel("common.reply", body)); panel.Children.Add(form);
        var message = OverviewText("", 12.5); message.Foreground = Paint("C2412D", "EE8A78"); var errorBox = new Border { Child = message, Height = 0 }; panel.Children.Add(errorBox);
        var footer = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, HorizontalAlignment = HorizontalAlignment.Right };
        footer.Children.Add(FormAction(T("common.cancel"), () => { dialog.Hide(); return Task.CompletedTask; }));
        bool acknowledged = false, sent = false;
        footer.Children.Add(FormAction(T("common.send"), async () =>
        {
            try
            {
                if (string.IsNullOrWhiteSpace(body.Text)) throw new ArgumentException(T("forward.need_body"));
                if (body.Text.TrimStart().StartsWith("【Relic") && !acknowledged) { acknowledged = true; throw new ArgumentException(T("forward.not_reply", ("prefix", "【Relic"))); }
                await api!.Post(Client.Org(target, "/forward"), new { member = who, to = to.Text, body = body.Text.Trim() }); sent = true; dialog.Hide();
            }
            catch (Exception ex) { message.Text = ex.Message; errorBox.Height = double.NaN; }
        }, true)); panel.Children.Add(footer);
        await FormDialog(dialog, panel, 620, body);
        if (sent) { Note(T("forward.sent", ("name", Display(who)))); await Refresh(); }
    }
    private async Task SecretarySetup()
    {
        var target = org; var dialog = new ContentDialog { XamlRoot = root.XamlRoot };
        var body = new StackPanel(); body.Children.Add(OverviewText(T("secretary.setup_title"), 17, weight: 650));
        body.Children.Add(OverviewText(T("secretary.setup_intro"), 12.5, true));
        var choices = new StackPanel { Spacing = 6 };
        foreach (var m in snap.Rows("members").Where(m => m.Text("state") != "vacant" && m.Text("surface") is not ("subagent" or "chat")))
        {
            var row = new Grid { ColumnSpacing = 10 }; row.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
            var face = Avatar(m.Text("avatar"), Display(m.Text("name")), 28); ((FrameworkElement)face).VerticalAlignment = VerticalAlignment.Center; row.Children.Add(face);
            var labels = new StackPanel(); labels.Children.Add(OverviewText(T("secretary.make", ("name", Display(m.Text("name")))), 13, weight: 700));
            labels.Children.Add(OverviewText(string.Join(" · ", new[] { m.Text("harness_label"), m.Text("surface_label") }.Where(value => value.Length > 0)), 12, true)); Grid.SetColumn(labels, 1); row.Children.Add(labels);
            var choice = Button("", async () => { await api!.Post(Client.Org(target, "/secretary"), new { member = m.Text("name") }); dialog.Hide(); await Select(target, m.Text("name")); });
            choice.Content = row; choice.HorizontalAlignment = HorizontalAlignment.Stretch; choice.HorizontalContentAlignment = HorizontalAlignment.Stretch; choice.Padding = new Thickness(11, 9, 11, 9); choice.CornerRadius = new CornerRadius(10); choice.MinHeight = 0;
            choice.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.Transparent); choice.BorderBrush = Paint("DEDBD4", "3A3936"); choice.BorderThickness = new Thickness(1); choices.Children.Add(choice);
        }
        if (choices.Children.Count > 0) body.Children.Add(choices);
        var footer = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, HorizontalAlignment = HorizontalAlignment.Right };
        footer.Children.Add(FormAction(T("common.cancel"), () => { dialog.Hide(); return Task.CompletedTask; })); footer.Children.Add(FormAction(T("secretary.new_embedded"), async () => { dialog.Hide(); await MemberDialog(secretary: true); }, true)); body.Children.Add(footer);
        await FormDialog(dialog, body, 520);
    }
    private async Task MemberDialog(string mode = "app", string? edit = null, bool secretary = false)
    {
        if (org.Length == 0) return;
        var target = org; platform = await api!.Get("/api/platform"); var harnesses = await api.Get("/api/harnesses");
        JsonNode options;
        try { options = await api.Get("/api/seat-options"); }
        catch { options = new JsonObject { ["efforts"] = new JsonArray(""), ["claude_modes"] = new JsonArray("auto"), ["codex_sandboxes"] = new JsonArray("workspace-write"), ["claude_models"] = new JsonArray("") }; }
        var card = edit == null ? new JsonObject() : await api.Get(Client.Org(target, "/member/" + Client.Segment(edit))); var config = card["config"];
        var run = edit != null ? "host" : secretary ? "app" : mode;
        var name = FormInput(edit ?? (secretary ? "secretary" : ""), T("member.name_placeholder")); name.IsEnabled = edit == null;
        var role = FormInput(card.Text("role"), T(secretary ? "member.role_placeholder_secretary" : "member.role_placeholder"));
        var nameField = FormLabel("member.name_label", SettingsVoiceField(name, double.NaN)); var roleField = FormLabel("common.role", SettingsVoiceField(role, double.NaN));
        var appFields = new StackPanel { Spacing = 12 };
        var picked = harnesses.Rows().FirstOrDefault(h => h.Flag("available") && !h.Flag("later")).Text("id");
        var harnessChoice = new StackPanel { Spacing = 6 }; var harnessTitle = OverviewText(T("member.harness_label"), 12.5, true); harnessChoice.Children.Add(harnessTitle);
        var appRadios = new StackPanel { Spacing = 6 }; var appGroup = "member-app-" + Guid.NewGuid().ToString("N");
        foreach (var harness in harnesses.Rows().Where(h => !h.Flag("later")))
        {
            var labels = new StackPanel(); var heading = FormLabelText("");
            heading.Inlines.Add(new Microsoft.UI.Xaml.Documents.Run { Text = harness.Text("title"), FontWeight = Microsoft.UI.Text.FontWeights.Bold });
            heading.Inlines.Add(new Microsoft.UI.Xaml.Documents.Run { Text = " " + harness.Text("vendor"), Foreground = Muted }); labels.Children.Add(heading);
            labels.Children.Add(OverviewText(harness.Flag("available") ? T("member.connected", ("program", OverviewClip(harness.Text("program"), 48))) : harness.Text("problem"), 12, true, lineHeight: 19.2));
            appRadios.Children.Add(FormRadio(appGroup, harness.Text("title"), labels, harness.Text("id") == picked, harness.Flag("available"), () => picked = harness.Text("id")));
        }
        harnessChoice.Children.Add(appRadios);
        if (harnesses.Rows().Any(h => h.Flag("later")))
        {
            var later = new DetailsFilterRow { Spacing = 6 }; later.Children.Add(OverviewText(T("member.later_acp"), 12, true, lineHeight: 19.2));
            foreach (var harness in harnesses.Rows().Where(h => h.Flag("later"))) { var chip = OverviewChip(harness.Text("title")); ToolTipService.SetToolTip(chip, harness.Text("vendor") + " · " + harness.Text("launch")); later.Children.Add(chip); }
            harnessChoice.Children.Add(later);
        }
        appFields.Children.Add(harnessChoice);
        var appModel = FormInput("", T("member.model_placeholder")); var appFolder = FormInput("", T("member.folder_placeholder"));
        appFields.Children.Add(FormLabel("common.model", SettingsVoiceField(appModel, double.NaN))); appFields.Children.Add(FormLabel("common.work_folder", SettingsVoiceField(appFolder, double.NaN)));
        var makeSecretary = secretary; appFields.Children.Add(FormSwitch("member.make_secretary", makeSecretary, value => makeSecretary = value));
        var hostFields = new StackPanel { Spacing = 12 }; var hostKind = (config.Text("harness").Length > 0 ? config.Text("harness") : "claude-code") + "/" + (config.Text("surface") == "gui" ? "gui" : "cli");
        var hostModel = FormInput(config.Text("model"), T("member.model_placeholder"), "member-model");
        FormSuggestions(hostModel, () => options.Rows("claude_models").Select(value => (value.Text(), "")).Where(value => value.Item1.Length > 0));
        var effort = FormSelect(options.Rows("efforts").Select(value => (value.Text(), value.Text().Length > 0 ? value.Text() : T("common.default_effort"))), config.Text("effort"));
        var folder = FormInput(config.Text("folder"), T("member.host_folder_placeholder"));
        var environment = FormSelect(new[] { ("local", T("member.env_local")), ("worktree", T("member.env_worktree")) }, config.Text("environment"));
        var permission = FormSelect(Array.Empty<(string, string)>());
        void FillPermissions()
        {
            permission.Items.Clear(); foreach (var value in options.Rows(hostKind.StartsWith("codex") ? "codex_sandboxes" : "claude_modes")) permission.Items.Add(new ComboBoxItem { Content = value.Text(), Tag = value.Text(), FontSize = 12.5 }); SetChoice(permission, config.Text("permission"));
        }
        FillPermissions();
        var kinds = new Grid { ColumnSpacing = 6, RowSpacing = 6 }; kinds.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); kinds.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        var hostGroup = "member-host-" + Guid.NewGuid().ToString("N"); var hostIndex = 0;
        foreach (var harness in new[] { "claude-code", "codex" }) foreach (var surface in new[] { "cli", "gui" })
        {
            if (!Delivery(harness, surface)) continue;
            var key = harness + "/" + surface; var label = T(surface == "gui" ? "member.harness_gui" : "member.harness_cli", ("harness", HarnessTitle(harness)));
            var title = FormLabelText(label); title.FontWeight = Microsoft.UI.Text.FontWeights.Bold;
            var choice = FormRadio(hostGroup, label, title, key == hostKind, true, () => { hostKind = key; FillPermissions(); });
            if (hostIndex % 2 == 0) kinds.RowDefinitions.Add(new() { Height = GridLength.Auto }); Grid.SetRow(choice, hostIndex / 2); Grid.SetColumn(choice, hostIndex % 2); kinds.Children.Add(choice); hostIndex++;
        }
        var kindFields = new StackPanel { Spacing = 6 }; kindFields.Children.Add(OverviewText(T("member.where_run"), 12.5, true)); kindFields.Children.Add(kinds);
        if (!Delivery(config.Text("harness"), config.Text("surface"))) kindFields.Children.Add(OverviewText(T("member.choose_supported_host"), 14, true)); hostFields.Children.Add(kindFields);
        hostFields.Children.Add(FormLabel("common.model", SettingsVoiceField(hostModel, double.NaN))); hostFields.Children.Add(FormLabel("member.effort", effort)); PairFields(hostFields, (FrameworkElement)hostFields.Children[^2], (FrameworkElement)hostFields.Children[^1]);
        hostFields.Children.Add(FormLabel("member.work_folder", SettingsVoiceField(folder, double.NaN)));
        hostFields.Children.Add(FormLabel("member.environment", environment)); hostFields.Children.Add(FormLabel("member.permission", permission)); PairFields(hostFields, (FrameworkElement)hostFields.Children[^2], (FrameworkElement)hostFields.Children[^1]);
        var env = FormInput(config?["env"] is JsonObject variables ? string.Join("\n", variables.Select(value => value.Key + "=" + value.Value.Text())) : "", T("member.env_placeholder"), multiline: true, mono: true);
        hostFields.Children.Add(FormLabel("member.env_vars", env));
        var startNow = true; Button? submit = null;
        string SubmitLabel() => edit != null ? T("common.save") : run == "existing" ? T("member.bind") : run == "app" ? T(secretary ? "member.create_secretary" : "member.create_member") : T(startNow ? "member.create_start" : "member.create_seat_only");
        if (edit == null) hostFields.Children.Add(FormSwitch("member.start_now", startNow, value => { startNow = value; if (submit?.Content is TextBlock label) label.Text = SubmitLabel(); }));
        var find = FormInput("", T("member.session_search")); var seatName = FormInput("", T("member.seat_placeholder"), "member-seat-name");
        FormSuggestions(seatName, () => snap.Rows("members").Select(m => (m.Text("name"), m.Text("display").Length > 0 ? m.Text("display") : m.Text("name"))));
        var searchField = FormLabel("common.session", SettingsVoiceField(find, double.NaN)); var seatField = FormLabel("member.which_seat", SettingsVoiceField(seatName, double.NaN));
        JsonNode? sessions = null, chosen = null; var sessionRows = new StackPanel { Spacing = 4 };
        var sessionList = new Border { Child = Scroll(sessionRows), Padding = new Thickness(6), BorderBrush = Paint("DEDBD4", "3A3936"), BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(10), MaxHeight = 260 };
        void DrawSessions()
        {
            sessionRows.Children.Clear();
            if (sessions == null) { sessionRows.Children.Add(OverviewText(T("member.finding_sessions"), 14, true)); return; }
            var query = find.Text.Trim(); var rows = sessions.Rows("sessions").Where(s => (s.Text("harness") != "chatgpt" || platform.Flag("chatgpt_delivery")) && (s.Text("title") + " " + s.Text("cwd") + " " + s.Text("id")).Contains(query, StringComparison.OrdinalIgnoreCase)).Take(80).ToArray();
            if (rows.Length == 0) sessionRows.Children.Add(OverviewText(T(query.Length > 0 ? "member.no_match" : "member.no_sessions"), 14, true));
            foreach (var session in rows)
            {
                var row = new Grid { ColumnSpacing = 8 }; row.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); row.ColumnDefinitions.Add(new() { Width = new GridLength(150), MaxWidth = 150 }); row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
                var label = HarnessTitle(session.Text("harness")); if (session.Text("surface") is "gui" or "cli") label = T(session.Text("surface") == "gui" ? "member.harness_gui" : "member.harness_cli", ("harness", label)); row.Children.Add(OverviewChip(label));
                var title = OverviewText(session.Text("title").Length > 0 ? session.Text("title") : session.Text("id"), 12.5); title.TextWrapping = TextWrapping.NoWrap; title.TextTrimming = TextTrimming.CharacterEllipsis; title.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(title, 1); row.Children.Add(title);
                var cwd = OverviewText(OverviewClip(session.Text("cwd"), 40), 11.5, true); cwd.FontFamily = new Microsoft.UI.Xaml.Media.FontFamily("Cascadia Code"); cwd.TextWrapping = TextWrapping.NoWrap; cwd.TextTrimming = TextTrimming.CharacterEllipsis; cwd.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(cwd, 2); row.Children.Add(cwd);
                var updated = OverviewText(session.Text("updated").Length > 0 ? Ago(session.Text("updated")) : "", 12.5, true); updated.VerticalAlignment = VerticalAlignment.Center;
                if (!Delivery(session.Text("harness"), session.Text("surface")))
                {
                    var manual = OverviewChip(T("member.manual_delivery")); ToolTipService.SetToolTip(manual, T("member.desktop_manual")); Grid.SetColumn(manual, 3); row.Children.Add(manual);
                    row.RowDefinitions.Add(new() { Height = GridLength.Auto }); row.RowDefinitions.Add(new() { Height = GridLength.Auto }); row.RowSpacing = 8; Grid.SetRow(updated, 1);
                }
                else Grid.SetColumn(updated, 3);
                row.Children.Add(updated);
                var button = Button("", () => { chosen = session; DrawSessions(); return Task.CompletedTask; }); button.Content = row; button.Padding = new Thickness(8, 6, 8, 6); button.MinHeight = 0; button.CornerRadius = new CornerRadius(8); button.BorderThickness = new Thickness(0); button.HorizontalContentAlignment = HorizontalAlignment.Stretch; button.HorizontalAlignment = HorizontalAlignment.Stretch;
                button.Background = ReferenceEquals(chosen, session) ? OverviewAlpha(Accent, .14) : new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.Transparent); sessionRows.Children.Add(button);
            }
            if (sessions.Rows("problems").Count > 0) sessionRows.Children.Add(OverviewText(string.Join(T("member.problem_sep"), sessions.Rows("problems").Select(value => value.Text())), 11.5, true));
        }
        async Task LoadSessions()
        {
            if (sessions != null) return;
            try { sessions = await api.Get("/api/sessions"); } catch (Exception error) { sessions = new JsonObject { ["sessions"] = new JsonArray(), ["problems"] = new JsonArray(error.Message) }; } DrawSessions();
        }
        find.TextChanged += (_, _) => DrawSessions(); DrawSessions();
        var dialog = new ContentDialog { XamlRoot = root.XamlRoot }; var body = new StackPanel(); body.Children.Add(OverviewText(edit != null ? T("member.edit_title", ("name", card.Text("display").Length > 0 ? card.Text("display") : edit)) : secretary ? T("secretary.new_embedded") : T("common.add_member"), 17, weight: 650));
        var tabs = new Border(); body.Children.Add(tabs); var note = OverviewText("", 12.5, true); body.Children.Add(note); var fields = new StackPanel { Spacing = 12 }; body.Children.Add(fields);
        var errorLabel = OverviewText("", 12.5); errorLabel.Foreground = Paint("C2412D", "EE8A78"); var errorBox = new Border { Child = errorLabel, Height = 0 }; body.Children.Add(errorBox);
        var footer = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, HorizontalAlignment = HorizontalAlignment.Right }; body.Children.Add(footer);
        footer.Children.Add(FormAction(T("common.cancel"), () => { dialog.Hide(); return Task.CompletedTask; }));
        submit = FormAction(SubmitLabel(), async () =>
        {
            errorLabel.Text = ""; errorBox.Height = 0; submit!.IsEnabled = false;
            try
            {
                if (run == "existing")
                {
                    if (chosen == null) throw new ArgumentException(T("member.pick_session")); var seat = seatName.Text.Trim(); if (seat.Length == 0) throw new ArgumentException(T("member.need_seat_name"));
                    await api.Post(Client.Org(target, "/bind"), new { session = chosen, member = seat, role = role.Text.Trim() }); dialog.Hide(); Note(T("member.bound", ("name", seat))); await Select(target, seat); return;
                }
                var nameValue = name.Text.Trim(); if (nameValue.Length == 0) throw new ArgumentException(T("member.need_name"));
                if (run == "app")
                {
                    if (picked.Length == 0) throw new ArgumentException(T("member.need_harness"));
                    await api.Post(Client.Org(target, "/members"), new { name = nameValue, role = role.Text.Trim(), harness = picked, model = appModel.Text.Trim(), folder = appFolder.Text.Trim(), secretary = makeSecretary }); Note(T("member.starting", ("name", nameValue)));
                }
                else
                {
                    var pair = hostKind.Split('/'); if (pair.Length != 2 || !Delivery(pair[0], pair[1])) throw new ArgumentException(T("member.choose_supported_host"));
                    await api.Post(Client.Org(target, "/seat"), new { name = nameValue, role = role.Text.Trim(), harness = pair[0], surface = pair[1], model = hostModel.Text.Trim(), effort = Value(effort), folder = folder.Text.Trim(), environment = Value(environment), permission = Value(permission), env = env.Text, start = edit == null && startNow, edit = edit != null });
                    Note(edit != null ? T("member.edit_saved") : startNow ? T("member.starting_first", ("name", nameValue)) : T("member.seat_created"));
                }
                dialog.Hide(); if (edit == null) await Select(target, nameValue); else await Refresh();
            }
            catch (Exception error) { errorLabel.Text = error.Message; errorBox.Height = double.NaN; submit.IsEnabled = true; }
        }, true); footer.Children.Add(submit);
        async Task DrawMode(string value)
        {
            run = value; fields.Children.Clear();
            note.Text = edit != null ? T("member.edit_note") : value switch { "app" => T("member.note_app"), "host" => platform.Flag("codex_desktop_wake") && platform.Flag("claude_desktop_wake") ? T("member.note_host") : T("member.note_host_mac"), _ => T("member.note_existing") };
            ((TextBlock)roleField.Children[0]).Text = T(value == "existing" ? "member.role_new" : "common.role");
            if (value == "existing") { fields.Children.Add(searchField); fields.Children.Add(sessionList); fields.Children.Add(seatField); fields.Children.Add(roleField); await LoadSessions(); }
            else { fields.Children.Add(nameField); fields.Children.Add(roleField); fields.Children.Add(value == "app" ? appFields : hostFields); }
            ((TextBlock)submit.Content).Text = SubmitLabel();
        }
        if (edit == null && !secretary) tabs.Child = DetailsTabs(new[] { ("app", T("member.run_app")), ("host", T("member.run_host")), ("existing", T("member.run_existing")) }, run, DrawMode);
        await DrawMode(run); await FormDialog(dialog, body, 620, run == "existing" ? find : edit != null ? role : name);
    }
    private static void PairFields(StackPanel container, FrameworkElement first, FrameworkElement second)
    {
        var index = container.Children.IndexOf(first); container.Children.Remove(first); container.Children.Remove(second);
        var row = new Grid { ColumnSpacing = 12 }; row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        Grid.SetColumn(second, 1); row.Children.Add(first); row.Children.Add(second); container.Children.Insert(index, row);
    }
}
