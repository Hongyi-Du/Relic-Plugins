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
    private DateTimeOffset ViewNow => VisualCaptureEnabled && DateTimeOffset.TryParse(Environment.GetEnvironmentVariable("RELIC_VISUAL_NOW"), out var captured) ? captured : DateTimeOffset.Now;
    private DateTime ViewToday => ViewNow.LocalDateTime.Date;
    private string When(string at)
    {
        if (!DateTimeOffset.TryParse(at, out var date)) { if (double.TryParse(at, out var seconds) && seconds > 0) date = DateTimeOffset.FromUnixTimeSeconds((long)seconds); else return at; }
        return Day(date.ToString("O")) + " " + date.ToLocalTime().ToString("HH:mm", System.Globalization.CultureInfo.InvariantCulture);
    }
    private string Ago(string at)
    {
        if (!DateTimeOffset.TryParse(at, out var date)) { if (double.TryParse(at, out var seconds)) date = DateTimeOffset.FromUnixTimeSeconds((long)seconds); else return at; }
        var elapsed = ViewNow - date;
        return elapsed.TotalMinutes < 1 ? T("time.just_now") : elapsed.TotalHours < 1 ? T("time.minutes_ago", ("n", (int)elapsed.TotalMinutes)) : elapsed.TotalDays < 1 ? T("time.hours_ago", ("n", (int)elapsed.TotalHours)) : Day(at);
    }
    private string Day(string at)
    {
        if (!DateTimeOffset.TryParse(at, out var date)) return "";
        var day = date.LocalDateTime.Date;
        var culture = System.Globalization.CultureInfo.GetCultureInfo(words.Language);
        return day == ViewToday ? T("time.today") : day == ViewToday.AddDays(-1) ? T("time.yesterday") :
            day.ToString(day.Year == ViewToday.Year ? culture.DateTimeFormat.MonthDayPattern : words.Language == "zh-CN" ? "yyyy年M月d日" : "MMMM d, yyyy", culture);
    }
    private string ShortWhen(string at)
    {
        if (!DateTimeOffset.TryParse(at, out var date)) return "";
        var local = date.LocalDateTime;
        return local.Date == ViewToday ? local.ToString("HH:mm", System.Globalization.CultureInfo.InvariantCulture) :
            local.Date == ViewToday.AddDays(-1) ? T("time.yesterday") : local.ToString("M/d", System.Globalization.CultureInfo.InvariantCulture);
    }
    private void Copy(string value)
    {
        try { var package = new DataPackage(); package.SetText(value); Clipboard.SetContent(package); Note(T("msg.copied")); }
        catch { Note(T("msg.copy_failed")); }
    }
    private UIElement Rich(string markdown)
    {
        var content = new StackPanel { Spacing = 8 };
        var lines = markdown.Replace("\r\n", "\n").Split('\n');
        for (var i = 0; i < lines.Length; i++)
        {
            var line = lines[i];
            if (line.TrimStart().StartsWith("```"))
            {
                var code = new List<string>(); var language = line.Trim()[3..];
                while (++i < lines.Length && !lines[i].TrimStart().StartsWith("```")) code.Add(lines[i]);
                var source = string.Join("\n", code); var codeText = Text(source, 12.5); codeText.FontFamily = new FontFamily("Cascadia Code"); codeText.TextWrapping = TextWrapping.NoWrap;
                codeText.LineHeight = 19.375; codeText.LineStackingStrategy = LineStackingStrategy.BlockLineHeight;
                var block = new Grid(); var codeScroll = new ScrollViewer { Content = codeText, HorizontalScrollMode = ScrollMode.Enabled, HorizontalScrollBarVisibility = ScrollBarVisibility.Auto, VerticalScrollMode = ScrollMode.Disabled, VerticalScrollBarVisibility = ScrollBarVisibility.Disabled };
                block.Children.Add(new Border { Child = codeScroll, Background = Paint("F6F5F2", "232321"), Padding = new Thickness(11, 9, 11, 9), BorderThickness = new Thickness(1), BorderBrush = Line, CornerRadius = new CornerRadius(8) });
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
                        var label = InlineText(rows[row][col].Trim(), 13.02); label.FontWeight = row == 0 ? FontWeights.SemiBold : FontWeights.Normal;
                        var shade = Ink.Color; shade.A = 10;
                        var cell = new Border { Padding = new Thickness(8, 3, 8, 3), BorderThickness = new Thickness(col == 0 ? 1 : 0, row == 0 ? 1 : 0, 1, 1), BorderBrush = Paint("DEDBD4", "3A3936"), Child = label, Background = row == 0 ? new SolidColorBrush(shade) : new SolidColorBrush(Colors.Transparent) };
                        Grid.SetRow(cell, row); Grid.SetColumn(cell, col); table.Children.Add(cell);
                    }
                }
                content.Children.Add(table); continue;
            }
            var heading = Regex.Match(line, @"^(#{1,6})\s+(.+)");
            if (heading.Success) { var title = InlineText(heading.Groups[2].Value); title.FontWeight = FontWeights.Bold; title.Margin = new Thickness(0, 0, 0, -4); content.Children.Add(title); continue; }
            if (string.IsNullOrWhiteSpace(line)) continue;
            if (line.StartsWith(">"))
            {
                content.Children.Add(new Border { BorderThickness = new Thickness(3, 0, 0, 0), BorderBrush = Paint("DEDBD4", "3A3936"), Padding = new Thickness(10, 2, 0, 2), Child = InlineText(Regex.Replace(line.TrimStart('>', ' '), @"^([^:：]+)[:：]\s*", match => T("chat.quote_from", ("name", match.Groups[1].Value))), 12.88) }); continue;
            }
            var list = Regex.Match(line, @"^(\s*)([-*•+]|\d+[.)])\s+(.*)$");
            if (list.Success)
            {
                var items = new StackPanel { Spacing = 0, Margin = new Thickness(0, 2, 0, 0) };
                do
                {
                    var marker = char.IsDigit(list.Groups[2].Value[0]) ? list.Groups[2].Value.TrimEnd(')') + (list.Groups[2].Value.EndsWith(')') ? "." : "") : "•";
                    var row = new Grid { Margin = new Thickness(list.Groups[1].Value.Length >= 2 ? 18 : 0, 0, 0, 0) };
                    row.ColumnDefinitions.Add(new() { Width = new GridLength(22) }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
                    var bullet = Text(marker); bullet.LineHeight = 23.1; bullet.LineStackingStrategy = LineStackingStrategy.BlockLineHeight; row.Children.Add(bullet);
                    var item = InlineText(list.Groups[3].Value); Grid.SetColumn(item, 1); row.Children.Add(item); items.Children.Add(row);
                    if (i + 1 >= lines.Length) break;
                    list = Regex.Match(lines[i + 1], @"^(\s*)([-*•+]|\d+[.)])\s+(.*)$"); if (!list.Success) break; i++;
                } while (true);
                content.Children.Add(items); continue;
            }
            var paragraphLines = new List<string> { line };
            while (i + 1 < lines.Length && !string.IsNullOrWhiteSpace(lines[i + 1]) && !Regex.IsMatch(lines[i + 1], @"^\s*(?:```|>|#{1,6}\s|[-*•+]\s|\d+[.)]\s|\|)")) paragraphLines.Add(lines[++i]);
            content.Children.Add(InlineText(string.Join("\n", paragraphLines)));
        }
        return content;
    }
    private RichTextBlock InlineText(string value, double size = 14)
    {
        var fontSize = size * (preferences.Text("font") == "large" ? 15.5 / 14 : preferences.Text("font") == "small" ? 13d / 14 : 1);
        var text = new RichTextBlock { IsTextSelectionEnabled = true, Foreground = Ink, FontSize = fontSize, TextWrapping = TextWrapping.Wrap,
            LineHeight = fontSize * 1.65, LineStackingStrategy = LineStackingStrategy.BlockLineHeight };
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
                case "code":
                    var shade = Ink.Color; shade.A = 18;
                    var code = new TextBlock { Text = part.Text, FontSize = fontSize * .9, FontFamily = new FontFamily("Cascadia Code"), Foreground = Ink,
                        LineHeight = fontSize * 1.65, LineStackingStrategy = LineStackingStrategy.BlockLineHeight, IsTextSelectionEnabled = true };
                    paragraph.Inlines.Add(new InlineUIContainer { Child = new Border { Child = code, Padding = new Thickness(5, 1, 5, 1), Background = new SolidColorBrush(shade), CornerRadius = new CornerRadius(5) } }); break;
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
    private Task documentSelection = Task.CompletedTask;
    private async Task Details(string tab = "trace", string? who = null, string? taskId = null)
    {
        if (org.Length == 0) return;
        var box = new Grid { Width = Math.Min(1120, root.ActualWidth - 96), Height = Math.Max(380, root.ActualHeight - 190), RowSpacing = 16 }; var tabs = new SelectorBar(); var content = new StackPanel { Spacing = 12 };
        box.RowDefinitions.Add(new() { Height = GridLength.Auto }); box.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) }); box.Children.Add(tabs); var bodyScroll = Scroll(content); Grid.SetRow(bodyScroll, 1); box.Children.Add(bodyScroll);
        async Task Draw(string key)
        {
            content.Children.Clear();
            switch (key)
            {
                case "trace":
                    var traceColumns = new Grid { ColumnSpacing = 22 };
                    traceColumns.ColumnDefinitions.Add(new() { Width = new GridLength(220) }); traceColumns.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
                    var pick = new ListView { SelectionMode = ListViewSelectionMode.Single, HorizontalContentAlignment = HorizontalAlignment.Stretch };
                    var traceHost = new Grid(); Grid.SetColumn(traceHost, 1); traceColumns.Children.Add(pick); traceColumns.Children.Add(traceHost); content.Children.Add(traceColumns);
                    foreach (var m in snap.Rows("members"))
                    {
                        var row = new Grid { ColumnSpacing = 8 }; row.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
                        row.Children.Add(SmallAvatar(m.Text("avatar"), m.Text("display").Length > 0 ? m.Text("display") : m.Text("name")));
                        var label = Stack(Ellipsis(Display(m.Text("name"))), Quiet(m.Text("harness_label") + " · " + m.Text("surface_label"), 11)); label.Spacing = 2; Grid.SetColumn(label, 1); row.Children.Add(label);
                        pick.Items.Add(new ListViewItem { Tag = m.Text("name"), Content = row, Padding = new Thickness(8, 6, 8, 6), CornerRadius = new CornerRadius(7), HorizontalContentAlignment = HorizontalAlignment.Stretch });
                    }
                    async Task SelectTrace(string name)
                    {
                        // Give each selection its own container, so a late HTTP
                        // response cannot overwrite the newly selected member.
                        var trace = new StackPanel { Spacing = 8 }; traceHost.Children.Clear(); traceHost.Children.Add(trace); await Trace(trace, name);
                    }
                    pick.SelectedItem = pick.Items.OfType<ListViewItem>().FirstOrDefault(i => i.Tag?.ToString() == (who ?? member)) ?? pick.Items.FirstOrDefault();
                    pick.SelectionChanged += async (_, _) => { if ((pick.SelectedItem as ListViewItem)?.Tag is string name) await Run(() => SelectTrace(name)); };
                    if ((pick.SelectedItem as ListViewItem)?.Tag is string initial) await SelectTrace(initial);
                    break;
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
                    var documents = new Grid { ColumnSpacing = 22 };
                    documents.ColumnDefinitions.Add(new() { Width = new GridLength(220) }); documents.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
                    var document = new StackPanel { Spacing = 8 }; Grid.SetColumn(document, 1); documents.Children.Add(document);
                    var documentList = new ListView { Tag = "document-list", SelectionMode = ListViewSelectionMode.Single, HorizontalContentAlignment = HorizontalAlignment.Stretch };
                    foreach (var d in snap.Rows("documents"))
                    {
                        var label = Stack(Heading(d.Text("key")), Quiet(T("details.revision", ("n", d.Text("revision"))) + " · " + Display(d.Text("author")), 12)); label.Spacing = 3;
                        documentList.Items.Add(new ListViewItem { Tag = d.Text("key"), Content = label, Padding = new Thickness(10, 8, 10, 8), HorizontalContentAlignment = HorizontalAlignment.Stretch, CornerRadius = new CornerRadius(7) });
                    }
                    async Task LoadDocument(string key)
                    {
                        var doc = await api!.Get(PathFor("/document?key=" + Client.Segment(key)));
                        if ((documentList.SelectedItem as ListViewItem)?.Tag?.ToString() != key) return;
                        document.Children.Clear();
                        document.Children.Add(Heading(key + " · " + T("details.revision", ("n", doc.Text("revision"))), 20));
                        document.Children.Add(Quiet(T("details.written", ("name", Display(doc.Text("author"))), ("when", When(doc.Text("at")))), 12.5));
                        var source = Text(doc.Text("body"), 12.5); source.FontFamily = new FontFamily("Cascadia Code"); source.LineHeight = 12.5 * 1.65;
                        document.Children.Add(new Border { Child = source, Background = Paint("F6F5F2", "232321"), BorderBrush = Line, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(10), Padding = new Thickness(14) });
                    }
                    documentList.SelectionChanged += (_, _) => { if ((documentList.SelectedItem as ListViewItem)?.Tag is string key) documentSelection = Run(() => LoadDocument(key)); };
                    documents.Children.Add(documentList); content.Children.Add(documents); break;
            }
        }
        foreach (var (key, label) in new[] { ("trace", "common.context_trace"), ("tasks", "common.tasks"), ("protocols", "details.tab_protocols"), ("docs", "details.tab_docs") }) tabs.Items.Add(new SelectorBarItem { Text = T(label), Tag = key, IsSelected = tab == key, FontSize = 13 });
        tabs.SelectionChanged += async (_, _) => { if (tabs.SelectedItem?.Tag is string key) await Run(() => Draw(key)); };
        await Draw(tab); await Show(T("details.dialog") + " · " + snap["org"].Text("name"), box);
    }
    private void DrawTasks(StackPanel box, string? focus)
    {
        var filters = new SelectorBar(); var selected = focus == "done" ? "done" : focus == null ? "open" : "all";
        foreach (var (id, key) in new[] { ("open", "task.working"), ("blocked", "task.blocked"), ("done", "details.filter_done"), ("all", "common.all") })
        {
            var count = snap.Rows("tasks").Count(t => id == "all" || (id == "open" ? t.Text("status") is not ("done" or "dropped") : t.Text("status") == id));
            filters.Items.Add(new SelectorBarItem { Text = T(key) + " " + count, Tag = id, IsSelected = selected == id, FontSize = 12 });
        }
        box.Children.Add(filters);
        var list = new StackPanel { Spacing = 10 }; box.Children.Add(list);
        void Draw()
        {
            list.Children.Clear(); var filter = filters.SelectedItem?.Tag?.ToString() ?? selected;
            var tasks = snap.Rows("tasks").Where(t => filter == "all" || (filter == "open" ? t.Text("status") is not ("done" or "dropped") : t.Text("status") == filter)).Reverse().ToArray();
            if (tasks.Length == 0) list.Children.Add(Text(T("details.no_tasks")));
            foreach (var task in tasks)
            {
                var detail = Stack(Text(T("details.label_title") + " " + task.Text("title")), Text(T("details.label_created_by") + " " + Display(task.Text("created_by"))));
                if (task.Text("report").Length > 0) detail.Children.Add(new Border { Child = Stack(Heading(T("report.title") + " · " + When(task.Text("done_at")), 13), Rich(task.Text("report"))), Background = Paint("F2F8F4", "223129"), BorderBrush = Paint("C9E4D4", "345343"), BorderThickness = new Thickness(1), Padding = new Thickness(10), CornerRadius = new CornerRadius(8) });
                detail.Children.Add(Text(T("details.label_evidence")));
                if (task.Rows("evidence").Count == 0) detail.Children.Add(Text(T("details.no_evidence"))); else foreach (var ev in task.Rows("evidence")) detail.Children.Add(Rich(ev.Text()));
                if (task.Text("owner").Length > 0) detail.Children.Add(Button(T("details.ask", ("name", Display(task.Text("owner")))), async () => { visibleDialog?.Hide(); await Select(org, task.Text("owner")); }));
                var header = new Grid { ColumnSpacing = 10, Width = Math.Min(1000, root.ActualWidth - 250), HorizontalAlignment = HorizontalAlignment.Left };
                header.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); header.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); header.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
                var owner = snap.Rows("members").FirstOrDefault(m => m.Text("name") == task.Text("owner")); header.Children.Add(SmallAvatar(owner.Text("avatar"), Display(task.Text("owner"))));
                var labels = Stack(Heading(task.Text("title")), Quiet(task.Text("id") + " · " + (task.Text("owner").Length > 0 ? Display(task.Text("owner")) : T("details.no_owner")) + " · " + T("details.updated", ("when", When(task.Text("at")))), 11)); labels.Spacing = 3; Grid.SetColumn(labels, 1); header.Children.Add(labels);
                var badges = new ActionRow { Spacing = 4, VerticalAlignment = VerticalAlignment.Center }; if (task.Text("report").Length > 0) badges.Children.Add(Badge(T("details.has_report"), true));
                var status = Badge(T("task." + task.Text("status")), task.Text("status") == "blocked");
                if (task.Text("status") == "done") { status.Background = Paint("EAF5EE", "263B2D"); ((TextBlock)status.Child).Foreground = Paint("387A50", "83C49B"); }
                badges.Children.Add(status); Grid.SetColumn(badges, 2); header.Children.Add(badges);
                list.Children.Add(new Expander { IsExpanded = task.Text("id") == focus, MinHeight = 36, Padding = new Thickness(12), HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch, Header = header, Content = detail });
            }
        }
        filters.SelectionChanged += (_, _) => Draw(); Draw();
    }
    private UIElement Protocol(JsonNode p, bool inherited)
    {
        var state = p.Text("status") switch { "active" => T("details.status_active"), "proposed" => T("details.status_proposed"), "rejected" => T("details.status_rejected"), "superseded" => T("details.status_superseded"), "retired" => T("details.status_retired"), "enacted" => T("details.status_enacted"), _ => p.Text("status") };
        var box = Stack(Heading(T("details.protocol_head", ("id", p.Text("id")), ("title", p.Text("title")), ("kind", p.Text("strength") == "strong" ? T("details.strong_protocol") : T("details.weak_protocol")), ("status", state)), 14)); box.Spacing = 8;
        if (inherited) box.Children.Add(Badge(T("org.inherited_from", ("name", p.Text("from")))));
        if (p["issued_by"] != null) box.Children.Add(Badge(p["issued_by"].Flag("person") ? T("org.issued_by_person") : T("org.issued_by", ("name", p["issued_by"].Text("name"))), p["issued_by"].Flag("person")));
        if (p.Text("retire_target").Length > 0) box.Children.Add(Text(T("details.label_retires") + " " + p.Text("retire_target")));
        if (p.Text("supersedes").Length > 0) box.Children.Add(Text(T("details.label_supersedes") + " " + p.Text("supersedes")));
        var attributes = new ActionRow { Spacing = 5 };
        if (p.Flag("inherit")) attributes.Children.Add(Badge(T("org.protocol_inherits")));
        if (p.Flag("check")) attributes.Children.Add(Badge(T("org.protocol_check")));
        if (attributes.Children.Count > 0) box.Children.Add(attributes);
        if (p.Flag("replaces_above") && p["supersedes"] != null) box.Children.Add(Text(T("org.protocol_overrides", ("ref", p["supersedes"] is JsonObject reference ? T("org.protocol_ref", ("id", reference.Text("id")), ("org", reference.Text("org"))) : p.Text("supersedes")))));
        if (p.Text("trigger").Length > 0) box.Children.Add(InlineText(T("details.label_applies") + " **" + p.Text("trigger") + "**", 13));
        box.Children.Add(Rich(p.Text("guidance")));
        if (p.Text("summary_for_person").Length > 0) box.Children.Add(new Border { Child = Stack(Quiet(T("details.label_summary")), Rich(p.Text("summary_for_person"))), Background = Paint("F8F7F5", "2A2A28"), Padding = new Thickness(10), CornerRadius = new CornerRadius(8) });
        if (p.Rows("rules").Count > 0)
        {
            var rules = new JsonArray();
            foreach (var original in p.Rows("rules")) { var rule = original?.DeepClone(); if (rule is JsonObject obj && rule.Text("effect") == "check") { obj.Remove("code"); obj.Remove("examples"); obj.Remove("code_sha256"); } rules.Add(rule); }
            var display = p.Text("rules_display");
            if (display.Length == 0) display = rules.ToJsonString(new() { WriteIndented = true, Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping });
            box.Children.Add(Rich("```json\n" + display + "\n```"));
            if (p.Rows("rules").Any(r => r.Text("effect") == "check")) box.Children.Add(CheckRules(p.Rows("rules")));
        }
        box.Children.Add(Quiet(T("details.proposed_by", ("name", Display(p.Text("author")))) + " · " + T("details.votes", ("n", p.Text("votes"))) + " · " + T("details.uses", ("n", p.Text("uses"))) + (p.Flag("retired_by_person") ? " · " + T("details.retired_by_person") : ""), 12)); return Card(box);
    }
    private UIElement CheckRules(JsonArray rules)
    {
        var body = new StackPanel { Spacing = 0 };
        foreach (var rule in rules.Where(r => r.Text("effect") == "check"))
        {
            var block = new StackPanel { Spacing = 6, Margin = new Thickness(0, 8, 0, 0) }; body.Children.Add(block);
            var scope = new List<string> { rule.Rows("tools").Count == 1 && rule.Rows("tools")[0].Text() == "Reply" ? T("cc.scope_reply") : string.Join(" / ", rule.Rows("tools").Select(x => x.Text())) };
            if (rule.Text("path_glob").Length > 0) scope.Add(T("cc.scope_path", ("glob", rule.Text("path_glob"))));
            if (rule.Rows("input_contains").Count > 0) scope.Add(T("cc.scope_contains", ("words", words.List(rule.Rows("input_contains").Select(x => x.Text())))));
            var who = rule.Rows("roles").Concat(rule.Rows("members")).ToArray(); var except = rule.Rows("except_roles").Concat(rule.Rows("except_members")).ToArray();
            if (who.Length > 0) scope.Add(T("cc.scope_who", ("names", words.List(who.Select(x => x.Text())))));
            if (except.Length > 0) scope.Add(T("cc.scope_except", ("names", words.List(except.Select(x => x.Text())))));
            block.Children.Add(OverviewText(T("cc.scope", ("what", string.Join(" · ", scope))), 12, true));
            block.Children.Add(OverviewText(rule.Text("on_error") == "deny" ? T("cc.on_error_deny") : T("cc.on_error_allow"), 12, true));
            var program = OverviewText(rule.Text("code"), 12, lineHeight: 18.6); program.FontFamily = new FontFamily("Cascadia Code"); program.TextWrapping = TextWrapping.NoWrap;
            var codeScroll = new ScrollViewer { Content = program, HorizontalScrollMode = ScrollMode.Enabled, HorizontalScrollBarVisibility = ScrollBarVisibility.Auto, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, MaxHeight = 322 };
            block.Children.Add(new Border { Child = codeScroll, Padding = new Thickness(10, 8, 10, 8), BorderThickness = new Thickness(1), BorderBrush = Line, CornerRadius = new CornerRadius(8), Background = Paint("F6F5F2", "232321") });
            if (rule.Text("code_sha256").Length > 0) { var sha = OverviewText("sha256 " + rule.Text("code_sha256")[..Math.Min(16, rule.Text("code_sha256").Length)] + "…", 12, true); sha.FontFamily = new FontFamily("Cascadia Code"); block.Children.Add(sha); }
            if (rule.Rows("examples").Count > 0)
            {
                var examples = new StackPanel { Spacing = 4 }; examples.Children.Add(OverviewText(T("cc.examples"), 12, true)); block.Children.Add(examples);
                foreach (var example in rule.Rows("examples"))
                {
                    var row = new Grid { ColumnSpacing = 8, RowSpacing = 2 }; row.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
                    row.RowDefinitions.Add(new() { Height = GridLength.Auto }); row.RowDefinitions.Add(new() { Height = GridLength.Auto });
                    var decision = example.Text("expect"); row.Children.Add(OverviewChip(decision switch { "allow" => T("cc.decision_allow"), "deny" => T("cc.decision_deny"), "review" => T("cc.decision_review"), _ => decision }, decision switch { "allow" => "ok", "deny" => "bad", "review" => "warn", _ => "" }));
                    var call = example?["call"];
                    var display = example.Text("call_display");
                    if (example?["call_display"] == null)
                    {
                        var input = call?["input"]; var argument = input.Text("command"); if (argument.Length == 0) argument = input.Text("file_path"); if (argument.Length == 0) argument = input.Text("path");
                        if (argument.Length == 0 && input is JsonObject fields && fields.Count > 0) argument = input.ToJsonString(new() { Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping });
                        display = Regex.Replace(string.Join(" ", new[] { call.Text("tool"), argument }.Where(value => value.Length > 0)), @"\s+", " ").Trim(); if (display.Length > 160) display = display[..159] + "…";
                    }
                    var command = OverviewText(display, 11.5); command.Foreground = Paint("5A5853", "B8B5AE"); command.FontFamily = new FontFamily("Cascadia Code"); command.TextWrapping = TextWrapping.NoWrap; command.TextTrimming = TextTrimming.CharacterEllipsis;
                    ToolTipService.SetToolTip(command, example.Text("call_json").Length > 0 ? example.Text("call_json") : call?.ToJsonString(new() { WriteIndented = true, Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping }) ?? "{}");
                    Grid.SetColumn(command, 1); row.Children.Add(command);
                    if (example.Text("note").Length > 0) { var note = OverviewText(example.Text("note"), 12, true); Grid.SetColumn(note, 1); Grid.SetRow(note, 1); row.Children.Add(note); }
                    examples.Children.Add(row);
                }
            }
        }
        return new Expander { Header = T("cc.code"), Content = body, HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch };
    }
    private async Task Trace(StackPanel box, string who)
    {
        box.Children.Clear(); if (who.Length == 0) return;
        var card = snap.Rows("members").FirstOrDefault(m => m.Text("name") == who);
        box.Children.Add(Heading(T("trace.title", ("name", Display(who))), 15));
        box.Children.Add(Quiet(card.Text("harness_label") + " · " + card.Text("surface_label") + " · " + T("trace.session", ("id", card.Text("session"))) + (card.Text("parent").Length > 0 ? T("trace.in_session", ("name", Display(card.Text("parent")))) : ""), 12));
        var role = new SelectorBar();
        foreach (var (id, key) in new[] { ("all", "common.all"), ("talk", "trace.filter_talk"), ("tools", "trace.filter_actions") }) role.Items.Add(new SelectorBarItem { Text = T(key), Tag = id, IsSelected = id == "all", FontSize = 12, Padding = new Thickness(6, 4, 6, 4) });
        var query = new TextBox { PlaceholderText = T("trace.search"), FontSize = 12, MinHeight = 30, Width = 220, VerticalAlignment = VerticalAlignment.Center };
        var filters = new ActionRow { Spacing = 10 }; filters.Children.Add(role); filters.Children.Add(query); box.Children.Add(filters);
        var steps = new List<JsonNode?>(); var list = new StackPanel { Spacing = 3 }; JsonNode data = new JsonObject();
        void Draw()
        {
            list.Children.Clear(); if (data.Flag("missing")) { list.Children.Add(Text(T("trace.no_session"))); return; }
            var filter = role.SelectedItem?.Tag?.ToString() ?? "all";
            var selected = steps.Where(s => (filter == "all" || (filter == "talk" ? s.Text("role") is "user" or "assistant" : s.Text("role") is "tool_call" or "tool_result")) && s.Text("text").Contains(query.Text, StringComparison.OrdinalIgnoreCase)).ToArray();
            if (selected.Length == 0) list.Children.Add(Text(T("trace.no_steps")));
            foreach (var step in selected)
            {
                var title = step.Text("role") switch { "user" => T("trace.user"), "assistant" => T("common.reply"), "tool_call" => step.Text("tool"), "tool_result" => T("common.result"), "thinking" => T("trace.thinking"), "context" => T("trace.injected"), _ => step.Text("role") };
                var full = Stack(Text(step.Text("text"), 12)); full.HorizontalAlignment = HorizontalAlignment.Stretch;
                var preview = step.Text("text").Replace('\n', ' '); if (preview.Length > 100) preview = preview[..100] + "…";
                var clock = DateTimeOffset.TryParse(step.Text("at"), out var stamp) ? stamp.ToLocalTime().ToString("HH:mm") : "";
                var header = Stack(TwoColumns(Heading(title, 12), Quiet(clock, 11)), Quiet(preview, 11)); header.Spacing = 1; header.HorizontalAlignment = HorizontalAlignment.Left; header.MaxWidth = Math.Max(240, Math.Min(720, root.ActualWidth - 440));
                header.Children.OfType<TextBlock>().Last().MaxLines = 1; header.Children.OfType<TextBlock>().Last().TextTrimming = TextTrimming.CharacterEllipsis;
                ToolTipService.SetToolTip(header, When(step.Text("at")) + "\n" + preview);
                var expand = new Expander { Header = header, MinHeight = 28, Padding = new Thickness(10, 6, 10, 6), Background = Paint("F8F7F5", "2A2A28"), IsExpanded = step.Text("role") is "user" or "assistant", Content = full, HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch };
                expand.Expanding += async (_, _) => await Run(async () => { var exact = await api!.Get(PathFor("/step?member=" + Client.Segment(who) + "&i=" + step.Text("i"))); full.Children.Clear(); full.Children.Add(Text(exact.Text("text"), 12)); });
                list.Children.Add(expand);
            }
            list.Children.Add(Quiet(T("trace.total", ("n", data.Text("total"))) + " · " + data.Text("path"), 11));
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
