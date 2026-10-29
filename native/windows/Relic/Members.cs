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
        var info = await api!.Get(PathFor("/waiting") + "?member=" + Client.Segment(who)); var first = info.Rows("waiting").FirstOrDefault();
        var form = Stack(Text(first == null ? T("forward.how", ("name", Display(who))) : T("forward.waiting", ("name", Display(who)), ("n", info.Rows("waiting").Count), ("ids", string.Join(",", first.Rows("ids").Select(x => x.Text()))))));
        var to = Field(form, "forward.to"); to.PlaceholderText = T("forward.to_placeholder"); to.Text = string.Join(",", (first?.Rows("to") ?? info.Rows("members")).Select(x => x.Text()));
        var body = Field(form, "common.reply", true); body.MinHeight = 150; body.PlaceholderText = T("forward.body_placeholder"); bool acknowledged = false;
        await Form(T("forward.title", ("name", Display(who))), form, async () =>
        {
            if (string.IsNullOrWhiteSpace(body.Text)) throw new ArgumentException(T("forward.need_body"));
            if (body.Text.TrimStart().StartsWith("【Relic") && !acknowledged) { acknowledged = true; throw new ArgumentException(T("forward.not_reply", ("prefix", "【Relic"))); }
            await Post("/forward", new { member = who, to = to.Text, body = body.Text.Trim() }); Note(T("forward.sent", ("name", Display(who))));
        }, T("common.send"));
    }
    private async Task SecretarySetup()
    {
        var content = Stack(Quiet(T("secretary.setup_intro"), 12)); content.Width = Math.Min(572, root.ActualWidth - 160);
        foreach (var m in snap.Rows("members").Where(m => m.Text("state") != "vacant" && m.Text("surface") is not ("subagent" or "chat")))
        {
            var choice = Button("", async () => { await Post("/secretary", new { member = m.Text("name") }); visibleDialog?.Hide(); await Select(org, m.Text("name")); }); choice.HorizontalAlignment = HorizontalAlignment.Stretch; choice.Padding = new Thickness(12);
            var row = new Grid { ColumnSpacing = 10 }; row.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); row.Children.Add(SmallAvatar(m.Text("avatar"), Display(m.Text("name")), m.Text("state"), 32)); var labels = Stack(Heading(T("secretary.make", ("name", m.Text("display"))), 13), Quiet(m.Text("harness_label") + " · " + m.Text("surface_label"), 11)); labels.Spacing = 4; Grid.SetColumn(labels, 1); row.Children.Add(labels); choice.Content = row; content.Children.Add(choice);
        }
        content.Children.Add(Button(T("secretary.new_embedded"), () => MemberDialog(secretary: true)));
        await Show(T("secretary.setup_title"), content);
    }
    private async Task MemberDialog(string mode = "app", string? edit = null, bool secretary = false)
    {
        if (org.Length == 0) return;
        var target = org; platform = await api!.Get("/api/platform");
        var harnesses = await api.Get("/api/harnesses"); var sessions = await api.Get("/api/sessions"); var options = await api.Get("/api/seat-options");
        var card = edit == null ? new JsonObject() : await api.Get(Client.Org(target, "/member/" + Client.Segment(edit))); var config = card["config"];
        var form = new StackPanel { Spacing = 10, MinWidth = 480 };
        var run = Choice(form, "member.where_run", [("app", T("member.run_app")), ("host", T("member.run_host")), ("existing", T("member.run_existing"))]); SetChoice(run, edit != null ? "host" : mode);
        run.Visibility = edit != null || secretary ? Visibility.Collapsed : Visibility.Visible;
        var note = Text(""); form.Children.Add(note);
        var name = Field(form, "member.name_label"); name.Text = edit ?? (secretary ? "secretary" : ""); name.IsReadOnly = edit != null; name.PlaceholderText = T("member.name_placeholder");
        var role = Field(form, "common.role"); role.Text = card.Text("role"); role.PlaceholderText = secretary ? T("member.role_placeholder_secretary") : T("member.role_placeholder");
        var nameSurface = FieldSurface(name); var roleSurface = FieldSurface(role);
        var appFields = new StackPanel { Spacing = 8 }; form.Children.Add(appFields);
        var harness = Choice(appFields, "common.harness", harnesses.Rows().Where(h => h.Flag("available") && !h.Flag("later")).Select(h => (h.Text("id"), h.Text("title"))));
        harness.PlaceholderText = T("member.need_harness"); ToolTipService.SetToolTip(harness, T("member.need_harness"));
        foreach (var h in harnesses.Rows().Where(h => !h.Flag("later"))) appFields.Children.Add(Text(h.Text("title") + " · " + (h.Flag("available") ? T("member.connected", ("program", h.Text("program"))) : h.Text("problem")), 12));
        if (harnesses.Rows().Any(h => h.Flag("later"))) appFields.Children.Add(Text(T("member.later_acp") + "\n" + string.Join(" · ", harnesses.Rows().Where(h => h.Flag("later")).Select(h => h.Text("title"))), 12));
        var appModel = Field(appFields, "common.model"); appModel.PlaceholderText = T("member.model_placeholder");
        var appFolder = Field(appFields, "common.work_folder"); appFolder.PlaceholderText = T("member.folder_placeholder");
        var sec = new CheckBox { Content = T("member.make_secretary"), IsChecked = secretary }; appFields.Children.Add(sec);
        var hostFields = new StackPanel { Spacing = 8 }; form.Children.Add(hostFields);
        var kinds = new List<(string, string)>();
        foreach (var h in new[] { "claude-code", "codex" }) foreach (var s in new[] { "cli", "gui" }) if (Delivery(h, s)) kinds.Add((h + "/" + s, T(s == "gui" ? "member.harness_gui" : "member.harness_cli", ("harness", HarnessTitle(h)))));
        var hostKind = Choice(hostFields, "member.where_run", kinds); SetChoice(hostKind, (config.Text("harness").Length > 0 ? config.Text("harness") : "claude-code") + "/" + (config.Text("surface") == "gui" ? "gui" : "cli"));
        var hostModel = Field(hostFields, "common.model"); hostModel.Text = config.Text("model"); hostModel.PlaceholderText = T("member.model_placeholder");
        var effort = Choice(hostFields, "member.effort", options.Rows("efforts").Select(x => (x.Text(), x.Text().Length > 0 ? x.Text() : T("common.default_effort")))); SetChoice(effort, config.Text("effort"));
        PairFields(hostFields, FieldSurface(hostModel), effort);
        var folder = Field(hostFields, "member.work_folder"); folder.Text = config.Text("folder"); folder.PlaceholderText = T("member.host_folder_placeholder");
        var environment = Choice(hostFields, "member.environment", [("local", T("member.env_local")), ("worktree", T("member.env_worktree"))]); SetChoice(environment, config.Text("environment"));
        var permission = Choice(hostFields, "member.permission", []);
        void FillPermissions() { permission.Items.Clear(); foreach (var p in options.Rows(Value(hostKind).StartsWith("codex") ? "codex_sandboxes" : "claude_modes")) permission.Items.Add(new ComboBoxItem { Content = p.Text(), Tag = p.Text() }); SetChoice(permission, config.Text("permission")); }
        FillPermissions(); hostKind.SelectionChanged += (_, _) => FillPermissions();
        PairFields(hostFields, environment, permission);
        var env = Field(hostFields, "member.env_vars", true); env.PlaceholderText = T("member.env_placeholder"); env.Text = config?["env"] is JsonObject variables ? string.Join("\n", variables.Select(v => v.Key + "=" + v.Value.Text())) : "";
        var start = new CheckBox { Content = T("member.start_now"), IsChecked = true, Visibility = edit == null ? Visibility.Visible : Visibility.Collapsed }; hostFields.Children.Add(start);
        var existing = new StackPanel { Spacing = 8 }; form.Children.Add(existing);
        var find = new TextBox { PlaceholderText = T("member.session_search") }; existing.Children.Add(find);
        var list = new ListView { MaxHeight = 240, SelectionMode = ListViewSelectionMode.Single }; existing.Children.Add(list); var empty = Text(T("member.finding_sessions")); existing.Children.Add(empty);
        var found = sessions.Rows("sessions").Where(s => s.Text("harness") != "chatgpt" || platform.Flag("chatgpt_delivery")).ToArray();
        void FindSessions()
        {
            var previous = (list.SelectedItem as ListViewItem)?.Tag as JsonNode;
            list.Items.Clear();
            foreach (var s in found.Where(s => (s.Text("title") + " " + s.Text("cwd") + " " + s.Text("id")).Contains(find.Text, StringComparison.OrdinalIgnoreCase)))
                list.Items.Add(new ListViewItem { Tag = s, Content = HarnessTitle(s.Text("harness")) + " · " + (s.Text("title").Length > 0 ? s.Text("title") : s.Text("id")) + "\n" + s.Text("cwd") + (Delivery(s.Text("harness"), s.Text("surface")) ? "" : "\n" + T("member.manual_delivery") + " · " + T("member.desktop_manual")) });
            list.SelectedItem = list.Items.Cast<ListViewItem>().FirstOrDefault(i => ReferenceEquals(i.Tag, previous));
            empty.Text = list.Items.Count == 0 ? T(find.Text.Trim().Length > 0 ? "member.no_match" : "member.no_sessions") : "";
        }
        FindSessions(); find.TextChanged += (_, _) => FindSessions();
        if (sessions.Rows("problems").Count > 0) existing.Children.Add(Quiet(string.Join(T("member.problem_sep"), sessions.Rows("problems").Select(p => p.Text())), 12));
        var modes = new SelectorBar { Visibility = run.Visibility };
        foreach (var (id, label) in new[] { ("app", "member.run_app"), ("host", "member.run_host"), ("existing", "member.run_existing") }) modes.Items.Add(new SelectorBarItem { Text = T(label), Tag = id, IsSelected = Value(run) == id, FontSize = 13 });
        modes.SelectionChanged += (_, _) => { if (modes.SelectedItem?.Tag is string value) SetChoice(run, value); };
        form.Children.Clear(); form.Children.Add(modes); form.Children.Add(note); var fields = new StackPanel { Spacing = 10 }; form.Children.Add(fields);
        void DrawMode()
        {
            var value = Value(run); note.Text = edit != null ? T("member.edit_note") : value switch { "app" => T("member.note_app"), "host" => platform.Flag("codex_desktop_wake") && platform.Flag("claude_desktop_wake") ? T("member.note_host") : T("member.note_host_mac"), _ => T("member.note_existing") };
            appFields.Visibility = value == "app" ? Visibility.Visible : Visibility.Collapsed; hostFields.Visibility = value == "host" ? Visibility.Visible : Visibility.Collapsed; existing.Visibility = value == "existing" ? Visibility.Visible : Visibility.Collapsed;
            name.Header = value == "existing" ? T("member.which_seat") : T("member.name_label"); name.PlaceholderText = value == "existing" ? T("member.seat_placeholder") : T("member.name_placeholder");
            role.Header = value == "existing" ? T("member.role_new") : T("common.role");
            fields.Children.Clear();
            if (value == "existing") fields.Children.Add(existing);
            fields.Children.Add(nameSurface); fields.Children.Add(roleSurface);
            if (value == "app") fields.Children.Add(appFields); else if (value == "host") fields.Children.Add(hostFields);
            if (visibleDialog != null) visibleDialog.PrimaryButtonText = SubmitLabel();
        }
        string SubmitLabel() => edit != null ? T("common.save") : Value(run) == "existing" ? T("member.bind") : Value(run) == "app" ? T(secretary ? "member.create_secretary" : "member.create_member") : T(start.IsChecked == true ? "member.create_start" : "member.create_seat_only");
        run.SelectionChanged += (_, _) => DrawMode(); start.Checked += (_, _) => DrawMode(); start.Unchecked += (_, _) => DrawMode(); DrawMode();
        await Form(edit != null ? T("member.edit_title", ("name", card.Text("display"))) : secretary ? T("secretary.new_embedded") : T("common.add_member"), form, async () =>
        {
            var seat = name.Text.Trim(); if (seat.Length == 0) throw new ArgumentException(Value(run) == "existing" ? T("member.need_seat_name") : T("member.need_name"));
            switch (Value(run))
            {
                case "existing":
                    if ((list.SelectedItem as ListViewItem)?.Tag is not JsonNode chosen) throw new ArgumentException(T("member.pick_session"));
                    await api.Post(Client.Org(target, "/bind"), new { session = chosen, member = seat, role = role.Text.Trim() }); Note(T("member.bound", ("name", seat))); break;
                case "app":
                    if (Value(harness).Length == 0) throw new ArgumentException(T("member.need_harness"));
                    await api.Post(Client.Org(target, "/members"), new { name = seat, role = role.Text.Trim(), harness = Value(harness), model = appModel.Text.Trim(), folder = appFolder.Text.Trim(), secretary = sec.IsChecked == true }); Note(T("member.starting", ("name", seat))); break;
                default:
                    var parts = Value(hostKind).Split('/'); if (parts.Length != 2 || !Delivery(parts[0], parts[1])) throw new ArgumentException(T("member.choose_supported_host"));
                    await api.Post(Client.Org(target, "/seat"), new { name = seat, role = role.Text.Trim(), harness = parts[0], surface = parts[1], model = hostModel.Text.Trim(), effort = Value(effort), folder = folder.Text.Trim(), environment = Value(environment), permission = Value(permission), env = env.Text, start = edit == null && start.IsChecked == true, edit = edit != null });
                    Note(edit != null ? T("member.edit_saved") : start.IsChecked == true ? T("member.starting_first", ("name", seat)) : T("member.seat_created")); break;
            }
            await Select(target, seat);
        }, SubmitLabel(), width: 620);
    }
    private static void PairFields(StackPanel container, FrameworkElement first, FrameworkElement second)
    {
        var index = container.Children.IndexOf(first); container.Children.Remove(first); container.Children.Remove(second);
        var row = new Grid { ColumnSpacing = 12 }; row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        Grid.SetColumn(second, 1); row.Children.Add(first); row.Children.Add(second); container.Children.Insert(index, row);
    }
}
