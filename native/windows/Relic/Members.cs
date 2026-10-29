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
    private async Task MemberCard(string name)
    {
        var id = org; var c = await api!.Get(Client.Org(id, "/member/" + Client.Segment(name)));
        var box = new StackPanel { Spacing = 10, Width = 350 }; Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(box, T("card.aria", ("name", Display(name))));
        var rename = new StackPanel { Spacing = 8, Visibility = Visibility.Collapsed };
        var label = Field(rename, "card.new_name"); label.MaxLength = 40; label.PlaceholderText = c.Text("display"); label.Text = c.Flag("display_custom") ? c.Text("display") : "";
        rename.Children.Add(Quiet(T("card.rename_hint"), 11));
        rename.Children.Add(Button(T("common.save"), async () => { var result = await api.Post(Client.Org(id, "/rename"), new { member = name, name = label.Text.Trim() }); Note((label.Text.Trim().Length > 0 ? T("card.renamed") : T("card.name_reset")) + " " + result.Text("note")); await Refresh(); await MemberCard(name); }));
        var avatar = QuietButton("", async () => { transientFlyout?.Hide(); await ChangeAvatar(name); await MemberCard(name); }); avatar.Content = Avatar(c.Text("avatar"), Display(name), 48); avatar.Padding = new Thickness(0); ToolTipService.SetToolTip(avatar, T("card.change_avatar"));
        var heading = new Grid { ColumnSpacing = 10 }; heading.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); heading.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); heading.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); heading.Children.Add(avatar);
        var identity = Stack(Heading(Display(name), 16), Quiet(name + (c.Flag("display_custom") ? "" : " · " + T("card.auto_named")), 11)); identity.Spacing = 3;
        var badges = new ActionRow { Spacing = 4 }; if (c.Flag("leader")) badges.Children.Add(Badge(T("common.leader"))); if (c.Flag("secretary")) badges.Children.Add(Badge(T("common.secretary"), true)); identity.Children.Add(badges); Grid.SetColumn(identity, 1); heading.Children.Add(identity);
        var editName = IconButton("\uE70F", "card.new_name", () => { rename.Visibility = rename.Visibility == Visibility.Visible ? Visibility.Collapsed : Visibility.Visible; return Task.CompletedTask; }); Grid.SetColumn(editName, 2); heading.Children.Add(editName); box.Children.Add(heading); box.Children.Add(rename); box.Children.Add(new Border { Height = 1, Background = Line, Margin = new Thickness(0, 6, 0, 6) });
        void Row(string key, string value)
        {
            if (value.Length == 0) return; var row = new Grid { ColumnSpacing = 10 }; row.ColumnDefinitions.Add(new() { Width = new GridLength(64) }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); row.Children.Add(Quiet(T(key), 12)); var text = Text(value, 12); text.MaxLines = 3; text.TextTrimming = TextTrimming.CharacterEllipsis; ToolTipService.SetToolTip(text, value); Grid.SetColumn(text, 1); row.Children.Add(text); box.Children.Add(row);
        }
        Row("common.role", c.Text("role").Length > 0 ? c.Text("role") : T("card.no_role")); Row("card.identity", Identity(c));
        if (c["ex_officio"] != null)
        {
            Row("card.seat_origin", T("card.ex_officio_tag"));
            box.Children.Add(Button(T("card.ex_officio", ("org", c["ex_officio"].Text("org_name"))), async () => { visibleDialog?.Hide(); await Select(c["ex_officio"].Text("org")); }));
        }
        if (c.Rows("also_in").Count > 0) box.Children.Add(Quiet(T("card.also_in"), 12));
        foreach (var seat in c.Rows("also_in")) box.Children.Add(QuietButton(T("card.also_in_item", ("org", seat.Text("org_name")), ("member", seat.Text("member"))) + (seat.Flag("main") ? " · " + T("card.main_seat") : ""), async () => { transientFlyout?.Hide(); await Select(seat.Text("org"), seat.Text("member")); }));
        Row("common.model", (c.Text("model").Length > 0 ? c.Text("model") : T("common.default_model")) + (c.Text("effort").Length > 0 ? " · " + c.Text("effort") : ""));
        if (c.Flag("model_editable"))
        {
            var modelFields = new StackPanel { Spacing = 8, Visibility = Visibility.Collapsed }; box.Children.Add(QuietButton(T("common.change") + " · " + T("common.model"), () => { modelFields.Visibility = modelFields.Visibility == Visibility.Visible ? Visibility.Collapsed : Visibility.Visible; return Task.CompletedTask; })); box.Children.Add(modelFields);
            var model = Choice(modelFields, "common.model", new[] { ("", T("common.default_model")) }.Concat(c.Rows("models").Select(x => (x.Text(), x.Text())))); SetChoice(model, c.Text("model"));
            var effort = Choice(modelFields, "member.effort", new[] { ("", T("common.default_effort")) }.Concat(c.Rows("efforts").Select(x => (x.Text(), x.Text())))); SetChoice(effort, c.Text("effort"));
            modelFields.Children.Add(Button(T("card.save_model"), async () => { var result = await api.Post(Client.Org(id, "/model"), new { member = name, model = Value(model), effort = Value(effort) }); Note(result.Text("applied") == "now" ? T("card.model_switched") : T("card.model_next_turn")); await Refresh(); }));
        }
        if (c.Text("model_note").Length > 0) box.Children.Add(Quiet(c.Text("model_note"), 11));
        var state = MemberState(c.Text("state")); Row("common.status", state + (c.Text("detail").Length > 0 && c.Text("detail") != state ? " · " + c.Text("detail") : ""));
        Row("card.doing", c.Text("doing_at").Length > 0 ? T("card.doing_since", ("doing", c.Text("doing")), ("ago", Ago(c.Text("doing_at")))) : c.Text("doing"));
        Row("card.owns", string.Join("\n", c.Rows("tasks").Where(t => t.Text("status") is not ("done" or "dropped")).Select(t => t.Text("id") + " " + t.Text("title"))));
        if (c.Rows("tasks").Count > 0 && c.Rows("tasks").All(t => t.Text("status") is "done" or "dropped")) Row("card.owns", T("card.tasks_done", ("n", c.Rows("tasks").Count)));
        Row("common.session", c.Text("session") + (c.Text("agent").Length > 0 ? " / " + c.Text("agent") : "") + (c.Text("parent").Length > 0 ? T("card.in_parent_session", ("parent", Display(c.Text("parent")))) : ""));
        Row("card.folder", c.Text("cwd")); Row("card.joined", c.Text("joined_at").Length > 0 ? When(c.Text("joined_at")) + (int.TryParse(c.Text("carriers"), out var carriers) && carriers > 1 ? " · " + T("card.session_nth", ("n", carriers)) : "") : "");
        Row("card.recent", string.Join("\n", c.Rows("recent").Take(4).Select(r => r.Text("tool") + " " + r.Text("summary"))));
        var actions = new ActionRow(); actions.Children.Add(Button(T("card.message"), async () => { transientFlyout?.Hide(); await Select(id, name); })); actions.Children.Add(Button(T("common.context_trace"), () => Details("trace", name))); box.Children.Add(actions);
        var seatActions = new ActionRow { Spacing = 4 }; box.Children.Add(seatActions);
        void SeatButton(string title, string hint, Func<Task> action) { var button = QuietButton(title, action); ToolTipService.SetToolTip(button, T(hint)); seatActions.Children.Add(button); }
        var own = c.Text("surface") is not ("chat" or "subagent"); var hosted = own && !c.Flag("embedded") && (c["config"].Text("harness").Length > 0 || c.Text("surface") is "cli" or "desktop");
        if (own && (c.Flag("embedded") || hosted && Delivery(c.Text("harness"), c["config"].Text("surface"))))
        {
            SeatButton(T("card.new_session"), "card.new_session_hint", () => SeatAction("fresh", name, c.Text("session").Length > 0 ? T("card.new_session_confirm", ("name", Display(name))) : ""));
        }
        if (hosted)
        {
            if (c.Text("session").Length > 0) SeatButton(T("card.open_session"), "card.open_session_hint", () => SeatAction("open_session", name));
            SeatButton(T("card.edit_setup"), "card.edit_setup_hint", () => MemberDialog(edit: name));
        }
        if (c.Text("harness") == "chatgpt")
        {
            SeatButton(c.Text("waiting_replies") is "" or "0" ? T("card.forward_reply") : T("card.forward_reply_waiting", ("n", c.Text("waiting_replies"))), "card.forward_reply_hint", () => Forward(name));
        }
        if (c.Text("session").Length > 0) SeatButton(T("card.leave_seat"), "card.leave_seat_hint", () => SeatAction("unbind", name, T("card.leave_seat_confirm", ("name", Display(name)))));
        ShowPopover(box, chatHead, Microsoft.UI.Xaml.Controls.Primitives.FlyoutPlacementMode.BottomEdgeAlignedRight);
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
