using Microsoft.UI;
using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Documents;
using Microsoft.UI.Xaml.Media;
using Relic.Core;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Windows.ApplicationModel.DataTransfer;

namespace Relic;

public sealed partial class MainWindow
{
    private RichTextBlock? selectedRich;
    private string When(string at)
    {
        if (!DateTimeOffset.TryParse(at, out var date)) { if (double.TryParse(at, out var seconds) && seconds > 0) date = DateTimeOffset.FromUnixTimeSeconds((long)seconds); else return at; }
        var local = date.ToLocalTime(); var delta = DateTimeOffset.Now - local;
        return local.ToString("g", System.Globalization.CultureInfo.GetCultureInfo(words.Language));
    }
    private string Ago(string at)
    {
        if (!DateTimeOffset.TryParse(at, out var date)) { if (double.TryParse(at, out var seconds)) date = DateTimeOffset.FromUnixTimeSeconds((long)seconds); else return at; }
        var elapsed = DateTimeOffset.Now - date;
        return elapsed.TotalMinutes < 1 ? T("time.just_now") : elapsed.TotalHours < 1 ? T("time.minutes_ago", ("n", (int)elapsed.TotalMinutes)) : elapsed.TotalDays < 1 ? T("time.hours_ago", ("n", (int)elapsed.TotalHours)) : Day(at);
    }
    private string Day(string at)
    {
        if (!DateTimeOffset.TryParse(at, out var date)) return When(at);
        var day = date.LocalDateTime.Date;
        return day == DateTime.Today ? T("time.today") : day == DateTime.Today.AddDays(-1) ? T("time.yesterday") : day.ToString("d", System.Globalization.CultureInfo.GetCultureInfo(words.Language));
    }
    private void Copy(string value)
    {
        try { var package = new DataPackage(); package.SetText(value); Clipboard.SetContent(package); Note(T("msg.copied")); }
        catch { Note(T("msg.copy_failed")); }
    }
    private UIElement Rich(string markdown)
    {
        var content = new StackPanel { Spacing = 6 };
        var lines = markdown.Replace("\r\n", "\n").Split('\n');
        for (var i = 0; i < lines.Length; i++)
        {
            var line = lines[i];
            if (line.TrimStart().StartsWith("```"))
            {
                var code = new List<string>(); var language = line.Trim()[3..];
                while (++i < lines.Length && !lines[i].TrimStart().StartsWith("```")) code.Add(lines[i]);
                var source = string.Join("\n", code); var codeText = Text(source, 12); codeText.FontFamily = new FontFamily("Consolas");
                var block = new Grid(); var codeScroll = Scroll(codeText); codeScroll.MaxHeight = 400; block.Children.Add(new Border { Child = codeScroll, Padding = new Thickness(12), BorderThickness = new Thickness(1), BorderBrush = Line, CornerRadius = new CornerRadius(8) });
                var copy = IconButton("\uE8C8", "common.copy", () => { Copy(source); return Task.CompletedTask; }); copy.HorizontalAlignment = HorizontalAlignment.Right; copy.VerticalAlignment = VerticalAlignment.Top; copy.Opacity = 0; block.Children.Add(copy);
                block.PointerEntered += (_, _) => copy.Opacity = 1; block.PointerExited += (_, _) => copy.Opacity = 0; block.GotFocus += (_, _) => copy.Opacity = 1;
                content.Children.Add(block); continue;
            }
            if (i + 1 < lines.Length && line.Contains('|') && Regex.IsMatch(lines[i + 1], @"^\s*\|?\s*:?-{3,}"))
            {
                var table = new Grid(); var rows = new List<string[]> { line.Trim().Trim('|').Split('|') }; i++;
                while (i + 1 < lines.Length && lines[i + 1].Contains('|')) rows.Add(lines[++i].Trim().Trim('|').Split('|'));
                for (var col = 0; col < rows.Max(r => r.Length); col++) table.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
                for (var row = 0; row < rows.Count; row++)
                {
                    table.RowDefinitions.Add(new() { Height = GridLength.Auto });
                    for (var col = 0; col < rows[row].Length; col++)
                    {
                        var cell = new Border { Padding = new Thickness(7), BorderThickness = new Thickness(.5), BorderBrush = new SolidColorBrush(Colors.Gray), Child = InlineText(rows[row][col].Trim(), row == 0 ? 15 : 14) };
                        Grid.SetRow(cell, row); Grid.SetColumn(cell, col); table.Children.Add(cell);
                    }
                }
                content.Children.Add(table); continue;
            }
            var heading = Regex.Match(line, @"^(#{1,6})\s+(.+)");
            if (heading.Success) { content.Children.Add(InlineText(heading.Groups[2].Value, Math.Max(14, 20 - heading.Groups[1].Length * 2))); continue; }
            if (string.IsNullOrWhiteSpace(line)) continue;
            if (Regex.IsMatch(line.Trim(), @"^(-{3,}|\*{3,}|_{3,})$")) { content.Children.Add(new Border { Height = 1, Background = new SolidColorBrush(Colors.Gray) }); continue; }
            if (line.StartsWith(">"))
            {
                content.Children.Add(new Border { BorderThickness = new Thickness(3, 0, 0, 0), BorderBrush = new SolidColorBrush(Colors.Gray), Padding = new Thickness(10, 2, 2, 2), Child = InlineText(Regex.Replace(line.TrimStart('>', ' '), @"^([^:：]+)[:：]\s*", match => T("chat.quote_from", ("name", match.Groups[1].Value)))) }); continue;
            }
            line = Regex.Replace(line, @"^\s*[-*+]\s+", "• "); content.Children.Add(InlineText(line));
        }
        return content;
    }
    private RichTextBlock InlineText(string value, double size = 14)
    {
        var text = new RichTextBlock { IsTextSelectionEnabled = true, FontSize = size * (preferences.Text("font") == "large" ? 1.18 : preferences.Text("font") == "small" ? .86 : 1), TextWrapping = TextWrapping.Wrap };
        var paragraph = new Paragraph();
        foreach (var part in InlineParts.Parse(value))
        {
            switch (part.Kind)
            {
                case "link":
                    var link = new Hyperlink(); link.Inlines.Add(new Run { Text = part.Text });
                    ToolTipService.SetToolTip(link, part.Target.StartsWith("http") ? part.Target : T("chat.path_preview"));
                    link.Click += async (_, _) => await Run(async () =>
                    {
                        if (Uri.TryCreate(part.Target, UriKind.Absolute, out var uri) && uri.Scheme is "http" or "https") await Windows.System.Launcher.LaunchUriAsync(uri);
                        else { var target = InlineParts.PathTarget(part.Target); await OpenFile(target.Path, target.Line); }
                    }); paragraph.Inlines.Add(link); break;
                case "code": paragraph.Inlines.Add(new Run { Text = part.Text, FontFamily = new FontFamily("Consolas") }); break;
                case "bold": var bold = new Bold(); bold.Inlines.Add(new Run { Text = part.Text }); paragraph.Inlines.Add(bold); break;
                case "italic": var italic = new Italic(); italic.Inlines.Add(new Run { Text = part.Text }); paragraph.Inlines.Add(italic); break;
                default: paragraph.Inlines.Add(new Run { Text = part.Text }); break;
            }
        }
        text.Blocks.Add(paragraph);
        text.SelectionChanged += (_, _) => { if (text.SelectedText.Length > 0) selectedRich = text; };
        var menu = new MenuFlyout();
        var copy = new MenuFlyoutItem { Text = T("common.copy") }; copy.Click += (_, _) => Copy(text.SelectedText.Length > 0 ? text.SelectedText : value); menu.Items.Add(copy);
        var quote = new MenuFlyoutItem { Text = T("common.quote") }; quote.Click += (_, _) => Quote(T("common.quote"), text.SelectedText.Length > 0 ? text.SelectedText : value); menu.Items.Add(quote); text.ContextFlyout = menu;
        return text;
    }
    private async Task Details(string tab = "trace", string? who = null, string? taskId = null)
    {
        if (org.Length == 0) return;
        var box = new StackPanel { Spacing = 16 }; var tabs = new SelectorBar(); var content = new StackPanel { Spacing = 12 };
        box.Children.Add(tabs); box.Children.Add(content);
        async Task Draw(string key)
        {
            content.Children.Clear();
            switch (key)
            {
                case "trace":
                    var pick = Choice(content, "org.members", snap.Rows("members").Select(m => (m.Text("name"), m.Text("display"))));
                    SetChoice(pick, who ?? member); var trace = new StackPanel { Spacing = 10 }; content.Children.Add(trace);
                    pick.SelectionChanged += async (_, _) => await Run(() => Trace(trace, Value(pick))); await Trace(trace, Value(pick)); break;
                case "tasks": DrawTasks(content, taskId); break;
                case "protocols":
                    if (snap.Rows("protocols").Count + snap.Rows("inherited_protocols").Count + snap.Rows("replaced_protocols").Count == 0) content.Children.Add(Text(T("details.no_protocols")));
                    foreach (var p in snap.Rows("protocols").Reverse()) content.Children.Add(Protocol(p!, false));
                    if (snap.Rows("inherited_protocols").Count > 0) content.Children.Add(Text(T("details.inherited_title"), 18));
                    foreach (var p in snap.Rows("inherited_protocols")) content.Children.Add(Protocol(p!, true));
                    if (snap.Rows("replaced_protocols").Count > 0) content.Children.Add(Text(T("details.replaced_title"), 18));
                    foreach (var p in snap.Rows("replaced_protocols")) content.Children.Add(Stack(Text(p.Text("id") + " " + p.Text("title")), Text(T(p.Text("how") == "retired" ? "org.protocol_retired" : "org.protocol_overridden", ("from", p.Text("from")), ("at", p.Text("at")), ("by", p.Text("by"))))));
                    break;
                case "docs":
                    if (snap.Rows("documents").Count == 0) content.Children.Add(Text(T("details.no_docs")));
                    var document = new StackPanel { Spacing = 8 };
                    foreach (var d in snap.Rows("documents")) content.Children.Add(Button(d.Text("key") + " · " + T("details.revision", ("n", d.Text("revision"))) + " · " + Display(d.Text("author")), async () =>
                    {
                        var doc = await api!.Get(PathFor("/document?key=" + Client.Segment(d.Text("key")))); document.Children.Clear();
                        document.Children.Add(Text(d.Text("key") + " · " + T("details.revision", ("n", doc.Text("revision"))), 20));
                        document.Children.Add(Text(T("details.written", ("name", Display(doc.Text("author"))), ("when", When(doc.Text("at")))), 12)); document.Children.Add(Rich(doc.Text("body")));
                    }));
                    content.Children.Add(document); break;
            }
        }
        foreach (var (key, label) in new[] { ("trace", "common.context_trace"), ("tasks", "common.tasks"), ("protocols", "details.tab_protocols"), ("docs", "details.tab_docs") }) tabs.Items.Add(new SelectorBarItem { Text = T(label), Tag = key, IsSelected = tab == key, FontSize = 13 });
        tabs.SelectionChanged += async (_, _) => { if (tabs.SelectedItem?.Tag is string key) await Run(() => Draw(key)); };
        await Draw(tab); await Show(T("details.dialog") + " · " + snap["org"].Text("name"), box);
    }
    private void DrawTasks(StackPanel box, string? focus)
    {
        var filters = Choice(box, "common.tasks", [("open", T("task.working")), ("blocked", T("task.blocked")), ("done", T("details.filter_done")), ("all", T("common.all"))]);
        SetChoice(filters, focus == "done" ? "done" : focus == null ? "open" : "all"); var list = new StackPanel { Spacing = 12 }; box.Children.Add(list);
        void Draw()
        {
            list.Children.Clear(); var filter = Value(filters);
            var tasks = snap.Rows("tasks").Where(t => filter == "all" || (filter == "open" ? t.Text("status") is not ("done" or "dropped") : t.Text("status") == filter)).Reverse().ToArray();
            if (tasks.Length == 0) list.Children.Add(Text(T("details.no_tasks")));
            foreach (var task in tasks)
            {
                var detail = Stack(Text(T("details.label_title") + " " + task.Text("title")), Text(T("details.label_created_by") + " " + Display(task.Text("created_by"))));
                if (task.Text("report").Length > 0) detail.Children.Add(Stack(Text(T("report.title") + " · " + When(task.Text("done_at")), 18), Rich(task.Text("report"))));
                detail.Children.Add(Text(T("details.label_evidence")));
                if (task.Rows("evidence").Count == 0) detail.Children.Add(Text(T("details.no_evidence"))); else foreach (var ev in task.Rows("evidence")) detail.Children.Add(Rich(ev.Text()));
                if (task.Text("owner").Length > 0) detail.Children.Add(Button(T("details.ask", ("name", Display(task.Text("owner")))), async () => { visibleDialog?.Hide(); await Select(org, task.Text("owner")); }));
                var header = Stack(Heading(task.Text("id") + " " + task.Text("title")), Quiet((task.Text("owner").Length > 0 ? Display(task.Text("owner")) : T("details.no_owner")) + " · " + T("task." + task.Text("status"))), Quiet(T("details.updated", ("when", When(task.Text("at")))) + (task.Text("report").Length > 0 ? " · " + T("details.has_report") : ""), 11)); header.Spacing = 4; header.MaxWidth = Math.Min(600, root.ActualWidth - 280);
                list.Children.Add(new Expander { IsExpanded = task.Text("id") == focus, HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch, Header = header, Content = detail });
            }
        }
        filters.SelectionChanged += (_, _) => Draw(); Draw();
    }
    private UIElement Protocol(JsonNode p, bool inherited)
    {
        var state = p.Text("status") switch { "active" => T("details.status_active"), "proposed" => T("details.status_proposed"), "rejected" => T("details.status_rejected"), "superseded" => T("details.status_superseded"), "retired" => T("details.status_retired"), "enacted" => T("details.status_enacted"), _ => p.Text("status") };
        var box = Stack(Text(T("details.protocol_head", ("id", p.Text("id")), ("title", p.Text("title")), ("kind", p.Text("strength") == "strong" ? T("details.strong_protocol") : T("details.weak_protocol")), ("status", state)), 17));
        if (inherited) box.Children.Add(Text(T("org.inherited_from", ("name", p.Text("from")))));
        if (p["issued_by"] != null) box.Children.Add(Text(p["issued_by"].Flag("person") ? T("org.issued_by_person") : T("org.issued_by", ("name", p["issued_by"].Text("name")))));
        if (p.Text("retire_target").Length > 0) box.Children.Add(Text(T("details.label_retires") + " " + p.Text("retire_target")));
        if (p.Text("supersedes").Length > 0) box.Children.Add(Text(T("details.label_supersedes") + " " + p.Text("supersedes")));
        if (p.Flag("inherit")) box.Children.Add(Text(T("org.protocol_inherits")));
        if (p.Flag("check")) box.Children.Add(Text(T("org.protocol_check")));
        if (p.Flag("replaces_above") && p["supersedes"] != null) box.Children.Add(Text(T("org.protocol_overrides", ("ref", p["supersedes"] is JsonObject reference ? T("org.protocol_ref", ("id", reference.Text("id")), ("org", reference.Text("org"))) : p.Text("supersedes")))));
        if (p.Text("trigger").Length > 0) box.Children.Add(Text(T("details.label_applies") + " " + p.Text("trigger")));
        box.Children.Add(Rich(p.Text("guidance")));
        if (p.Text("summary_for_person").Length > 0) box.Children.Add(Stack(Text(T("details.label_summary")), Rich(p.Text("summary_for_person"))));
        if (p.Rows("rules").Count > 0)
        {
            var rules = new JsonArray();
            foreach (var original in p.Rows("rules")) { var rule = original?.DeepClone(); if (rule is JsonObject obj && rule.Text("effect") == "check") { obj.Remove("code"); obj.Remove("examples"); obj.Remove("code_sha256"); } rules.Add(rule); }
            box.Children.Add(Text(rules.ToJsonString(new() { WriteIndented = true }), 12));
            if (p.Rows("rules").Any(r => r.Text("effect") == "check")) box.Children.Add(CheckRules(p.Rows("rules")));
        }
        box.Children.Add(Quiet(T("details.proposed_by", ("name", Display(p.Text("author")))) + " · " + T("details.votes", ("n", p.Text("votes"))) + " · " + T("details.uses", ("n", p.Text("uses"))) + (p.Flag("retired_by_person") ? " · " + T("details.retired_by_person") : ""), 12)); return Card(box);
    }
    private UIElement CheckRules(JsonArray rules)
    {
        var body = new StackPanel { Spacing = 10 };
        foreach (var rule in rules.Where(r => r.Text("effect") == "check"))
        {
            var scope = new List<string> { rule.Rows("tools").Count == 1 && rule.Rows("tools")[0].Text() == "Reply" ? T("cc.scope_reply") : string.Join(" / ", rule.Rows("tools").Select(x => x.Text())) };
            if (rule.Text("path_glob").Length > 0) scope.Add(T("cc.scope_path", ("glob", rule.Text("path_glob"))));
            if (rule.Rows("input_contains").Count > 0) scope.Add(T("cc.scope_contains", ("words", words.List(rule.Rows("input_contains").Select(x => x.Text())))));
            var who = rule.Rows("roles").Concat(rule.Rows("members")).ToArray(); var except = rule.Rows("except_roles").Concat(rule.Rows("except_members")).ToArray();
            if (who.Length > 0) scope.Add(T("cc.scope_who", ("names", words.List(who.Select(x => x.Text())))));
            if (except.Length > 0) scope.Add(T("cc.scope_except", ("names", words.List(except.Select(x => x.Text())))));
            body.Children.Add(Text(T("cc.scope", ("what", string.Join(" · ", scope)))));
            body.Children.Add(Text(rule.Text("on_error") == "deny" ? T("cc.on_error_deny") : T("cc.on_error_allow")));
            var code = Text(rule.Text("code"), 12); code.FontFamily = new FontFamily("Consolas"); body.Children.Add(code);
            if (rule.Text("code_sha256").Length > 0) body.Children.Add(Text("sha256 " + rule.Text("code_sha256"), 11));
            if (rule.Rows("examples").Count > 0) body.Children.Add(Text(T("cc.examples")));
            foreach (var example in rule.Rows("examples")) body.Children.Add(new Expander { Header = T(example.Text("expect") switch { "deny" => "cc.decision_deny", "review" => "cc.decision_review", _ => "cc.decision_allow" }) + " · " + example?["call"].Text("tool"), Content = Stack(Text(example?["call"]?.ToJsonString(new() { WriteIndented = true }) ?? ""), Text(example.Text("note"))), HorizontalAlignment = HorizontalAlignment.Stretch });
        }
        return new Expander { Header = T("cc.code"), Content = body, HorizontalAlignment = HorizontalAlignment.Stretch };
    }
    private async Task Trace(StackPanel box, string who)
    {
        box.Children.Clear(); if (who.Length == 0) return;
        var card = snap.Rows("members").FirstOrDefault(m => m.Text("name") == who);
        box.Children.Add(Text(T("trace.title", ("name", Display(who))), 20));
        box.Children.Add(Text(card.Text("harness_label") + " · " + card.Text("surface_label") + " · " + T("trace.session", ("id", card.Text("session"))) + (card.Text("parent").Length > 0 ? T("trace.in_session", ("name", Display(card.Text("parent")))) : ""), 12));
        var role = Choice(box, "common.context_trace", [("all", T("common.all")), ("talk", T("trace.filter_talk")), ("tools", T("trace.filter_actions"))]);
        var query = new TextBox { PlaceholderText = T("trace.search") }; box.Children.Add(query);
        var steps = new List<JsonNode?>(); var list = new StackPanel { Spacing = 8 }; JsonNode data = new JsonObject();
        void Draw()
        {
            list.Children.Clear(); if (data.Flag("missing")) { list.Children.Add(Text(T("trace.no_session"))); return; }
            var selected = steps.Where(s => (Value(role) == "all" || (Value(role) == "talk" ? s.Text("role") is "user" or "assistant" : s.Text("role") is "tool_call" or "tool_result")) && s.Text("text").Contains(query.Text, StringComparison.OrdinalIgnoreCase)).ToArray();
            if (selected.Length == 0) list.Children.Add(Text(T("trace.no_steps")));
            foreach (var step in selected)
            {
                var title = step.Text("role") switch { "user" => T("trace.user"), "assistant" => T("common.reply"), "tool_call" => step.Text("tool"), "tool_result" => T("common.result"), "thinking" => T("trace.thinking"), "context" => T("trace.injected"), _ => step.Text("role") };
                var full = Stack(Text(step.Text("text")));
                var expand = new Expander { Header = title + " · " + When(step.Text("at")), IsExpanded = step.Text("role") is "user" or "assistant", Content = full, HorizontalAlignment = HorizontalAlignment.Stretch };
                expand.Expanding += async (_, _) => await Run(async () => { var exact = await api!.Get(PathFor("/step?member=" + Client.Segment(who) + "&i=" + step.Text("i"))); full.Children.Clear(); full.Children.Add(Text(exact.Text("text"))); });
                list.Children.Add(expand);
            }
            list.Children.Add(Text(T("trace.total", ("n", data.Text("total"))) + " · " + data.Text("path"), 12));
        }
        Button? older = null;
        async Task Fetch(string before = "")
        {
            data = await api!.Get(PathFor("/transcript?member=" + Client.Segment(who) + "&limit=400" + (before.Length > 0 ? "&before=" + before : "")));
            steps.InsertRange(0, data.Rows("steps")); if (older != null) older.Visibility = data.Text("start") is "" or "0" ? Visibility.Collapsed : Visibility.Visible; Draw();
        }
        older = Button(T("trace.load_older"), () => Fetch(data.Text("start"))); box.Children.Add(older); box.Children.Add(list);
        role.SelectionChanged += (_, _) => Draw(); query.TextChanged += (_, _) => Draw(); await Fetch();
    }
}
