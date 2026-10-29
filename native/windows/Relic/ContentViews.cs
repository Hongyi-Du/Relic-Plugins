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
        var box = new Grid { Width = Math.Min(1180, root.ActualWidth - 40), Height = Math.Max(0, root.ActualHeight - 56), Background = Paint("FFFFFF", "252523"), CornerRadius = new CornerRadius(16) };
        box.RowDefinitions.Add(new() { Height = GridLength.Auto }); box.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        var dialog = new ContentDialog { XamlRoot = root.XamlRoot, Content = box }; Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(dialog, T("details.dialog"));
        var bar = new Grid { Padding = new Thickness(16, 12, 16, 12), ColumnSpacing = 12, BorderBrush = Line, BorderThickness = new Thickness(0, 0, 0, 1) };
        bar.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); bar.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); bar.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        var title = OverviewText(snap["org"].Text("name"), 15.5, weight: 650); title.VerticalAlignment = VerticalAlignment.Center; bar.Children.Add(title); box.Children.Add(bar);
        var content = new Grid(); Grid.SetRow(content, 1); box.Children.Add(content); var current = who ?? member;
        if (current.Length == 0) current = snap.Rows("members").FirstOrDefault().Text("name");
        async Task Draw(string key)
        {
            content.Children.Clear(); content.ColumnDefinitions.Clear();
            var twoColumns = key is "trace" or "docs";
            if (twoColumns) content.ColumnDefinitions.Add(new() { Width = new GridLength(250) });
            content.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
            var right = new StackPanel { Spacing = 0, Padding = new Thickness(20, 16, 20, 16) }; var rightScroll = Scroll(right); if (twoColumns) Grid.SetColumn(rightScroll, 1); content.Children.Add(rightScroll);
            ListView LeftList(string tag)
            {
                var list = new ListView { Tag = tag, Padding = new Thickness(8), BorderBrush = Line, BorderThickness = new Thickness(0, 0, 1, 0), Background = Paint("F8F7F5", "191918"), SelectionMode = ListViewSelectionMode.Single, HorizontalContentAlignment = HorizontalAlignment.Stretch };
                content.Children.Add(list); return list;
            }
            switch (key)
            {
                case "trace":
                    var pick = LeftList("trace-members");
                    foreach (var m in snap.Rows("members")) pick.Items.Add(DetailsListRow(m.Text("name"), OverviewAvatar(m.Text("name"), true, 28), Display(m.Text("name")), string.Join(" · ", new[] { m.Text("harness_label"), m.Text("surface_label") }.Where(value => value.Length > 0)), m.Text("name") == current));
                    pick.SelectedItem = pick.Items.OfType<ListViewItem>().FirstOrDefault(item => item.Tag?.ToString() == current) ?? pick.Items.FirstOrDefault();
                    async Task SelectTrace(string name)
                    {
                        current = name; foreach (var item in pick.Items.OfType<ListViewItem>()) item.Background = item.Tag?.ToString() == name ? Paint("E7E5DF", "2F2E2B") : new SolidColorBrush(Colors.Transparent);
                        // A late response stays in its detached selection container.
                        var trace = new StackPanel(); right.Children.Clear(); right.Children.Add(trace); await Trace(trace, name);
                    }
                    pick.SelectionChanged += async (_, _) => { if ((pick.SelectedItem as ListViewItem)?.Tag is string name) await Run(() => SelectTrace(name)); };
                    if ((pick.SelectedItem as ListViewItem)?.Tag is string initial) await SelectTrace(initial);
                    break;
                case "tasks": DrawTasks(right, taskId); break;
                case "protocols":
                    if (snap.Rows("protocols").Count + snap.Rows("inherited_protocols").Count + snap.Rows("replaced_protocols").Count == 0) right.Children.Add(DetailsEmpty(T("details.no_protocols")));
                    foreach (var p in snap.Rows("protocols").Reverse()) right.Children.Add(Protocol(p!, false));
                    void Section(string label) { var heading = OverviewText(T(label), 13, weight: 650); heading.Foreground = Paint("5A5853", "B8B5AE"); heading.Margin = new Thickness(0, 18, 0, 8); right.Children.Add(heading); }
                    if (snap.Rows("inherited_protocols").Count > 0) Section("details.inherited_title");
                    foreach (var p in snap.Rows("inherited_protocols")) right.Children.Add(Protocol(p!, true));
                    if (snap.Rows("replaced_protocols").Count > 0) Section("details.replaced_title");
                    foreach (var p in snap.Rows("replaced_protocols"))
                    {
                        var name = OverviewText(p.Text("id") + " " + p.Text("title"), 13, weight: 700); name.TextDecorations = Windows.UI.Text.TextDecorations.Strikethrough;
                        var inner = new StackPanel { Spacing = 8, Padding = new Thickness(14, 10, 14, 12) }; inner.Children.Add(name); inner.Children.Add(OverviewText(T(p.Text("how") == "retired" ? "org.protocol_retired" : "org.protocol_overridden", ("from", p.Text("from")), ("at", p.Text("at")), ("by", p.Text("by"))), 13, true));
                        var card = DetailsCard(inner); card.Opacity = .6; right.Children.Add(card);
                    }
                    break;
                case "docs":
                    var documents = LeftList("document-list");
                    if (snap.Rows("documents").Count == 0) right.Children.Add(DetailsEmpty(T("details.no_docs")));
                    foreach (var d in snap.Rows("documents"))
                    {
                        var folder = new Border { Width = 28, Height = 28, Background = Paint("EFEEEA", "262624"), CornerRadius = new CornerRadius(8), Child = ReferenceIcon("folder", 14) };
                        ((FrameworkElement)folder.Child).HorizontalAlignment = HorizontalAlignment.Center; ((FrameworkElement)folder.Child).VerticalAlignment = VerticalAlignment.Center;
                        documents.Items.Add(DetailsListRow(d.Text("key"), SidebarPicture("", folder, 28), d.Text("key"), T("details.revision", ("n", d.Text("revision"))) + " · " + Display(d.Text("author"))));
                    }
                    async Task LoadDocument(string documentKey)
                    {
                        var doc = await api!.Get(PathFor("/document?key=" + Client.Segment(documentKey)));
                        if ((documents.SelectedItem as ListViewItem)?.Tag?.ToString() != documentKey) return;
                        right.Children.Clear(); var heading = OverviewText(documentKey + " · " + T("details.revision", ("n", doc.Text("revision"))), 16.38, weight: 700); heading.Margin = new Thickness(0, 0, 0, 4); right.Children.Add(heading);
                        var written = OverviewText(T("details.written", ("name", Display(doc.Text("author"))), ("when", When(doc.Text("at")))), 12.5, true); written.Margin = new Thickness(0, 0, 0, 10); right.Children.Add(written); right.Children.Add(DetailsCode(doc.Text("body")));
                    }
                    documents.SelectionChanged += (_, _) => { if ((documents.SelectedItem as ListViewItem)?.Tag is string documentKey) documentSelection = Run(() => LoadDocument(documentKey)); }; break;
            }
        }
        var tabs = DetailsTabs(new[] { ("trace", T("common.context_trace")), ("tasks", T("common.tasks")), ("protocols", T("details.tab_protocols")), ("docs", T("details.tab_docs")) }, tab, Draw, true); Grid.SetColumn(tabs, 1); bar.Children.Add(tabs);
        var close = IconButton("\uE711", "common.close", () => { dialog.Hide(); return Task.CompletedTask; }); close.Content = ReferenceIcon("x", 18); close.Padding = new Thickness(6); Grid.SetColumn(close, 2); bar.Children.Add(close);
        void Resize(object sender, SizeChangedEventArgs args) { box.Width = Math.Min(1180, Math.Max(0, args.NewSize.Width - 40)); box.Height = Math.Max(0, args.NewSize.Height - 56); }
        root.SizeChanged += Resize;
        dialog.Opened += (_, _) =>
        {
            dialog.Resources["ContentDialogPadding"] = new Thickness(0); dialog.Resources["ContentDialogTitleMargin"] = new Thickness(0); dialog.Resources["ContentDialogMaxHeight"] = box.Height;
            if (DialogPart<ContentPresenter>(dialog, "Content") is { } presenter) { presenter.Margin = new Thickness(0); presenter.Padding = new Thickness(0); }
            if (DialogPart<Border>(dialog, "BackgroundElement") is { } background) { background.Padding = new Thickness(0); background.CornerRadius = new CornerRadius(16); background.MaxHeight = box.Height; }
            if (DialogPart<ScrollViewer>(dialog, "ContentScrollViewer") is { } scroll) { scroll.Padding = new Thickness(0); scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Disabled; scroll.HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled; scroll.MaxHeight = box.Height; }
            if (DialogPart<Grid>(dialog, "CommandSpace") is { } commands) commands.Visibility = Visibility.Collapsed;
        };
        try { await Draw(tab); await Dialog(dialog); } finally { root.SizeChanged -= Resize; }
    }
    private void DrawTasks(StackPanel box, string? focus)
    {
        var selected = focus == "done" ? "done" : focus == null ? "open" : "all"; var list = new StackPanel();
        var choices = new[] { ("open", "task.working"), ("blocked", "task.blocked"), ("done", "details.filter_done"), ("all", "common.all") }.Select(pair => (pair.Item1, T(pair.Item2) + " " + snap.Rows("tasks").Count(task => pair.Item1 == "all" || (pair.Item1 == "open" ? task.Text("status") is not ("done" or "dropped") : task.Text("status") == pair.Item1))));
        void Draw()
        {
            list.Children.Clear(); var tasks = snap.Rows("tasks").Where(task => selected == "all" || (selected == "open" ? task.Text("status") is not ("done" or "dropped") : task.Text("status") == selected)).Reverse().ToArray();
            if (tasks.Length == 0) list.Children.Add(DetailsEmpty(T("details.no_tasks")));
            foreach (var task in tasks)
            {
                var inner = new StackPanel { Spacing = 8, Padding = new Thickness(14, 10, 14, 12) }; inner.Children.Add(DetailsLabeled(T("details.label_title"), task.Text("title")));
                if (task.Text("created_by").Length > 0) inner.Children.Add(DetailsLabeled(T("details.label_created_by"), Display(task.Text("created_by"))));
                if (task.Text("status") == "done" && task.Text("report").Length > 0) inner.Children.Add(DetailsReport(task!));
                var evidence = new StackPanel(); evidence.Children.Add(DetailsLabeled(T("details.label_evidence"), task.Rows("evidence").Count == 0 ? T("details.no_evidence") : ""));
                foreach (var ev in task.Rows("evidence"))
                {
                    var row = new Grid(); row.ColumnDefinitions.Add(new() { Width = new GridLength(18) }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); row.Children.Add(OverviewText("•", 13)); var text = InlineText(ev.Text(), 13); text.LineHeight = 20.8; Grid.SetColumn(text, 1); row.Children.Add(text); evidence.Children.Add(row);
                }
                inner.Children.Add(evidence);
                if (task.Text("owner").Length > 0) { var ask = OverviewAction(T("details.ask", ("name", Display(task.Text("owner")))), async () => { visibleDialog?.Hide(); await Select(org, task.Text("owner")); }); ask.HorizontalAlignment = HorizontalAlignment.Left; inner.Children.Add(ask); }
                var header = new Grid { ColumnSpacing = 10 }; header.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); header.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); header.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
                if (task.Text("owner").Length > 0) { var owner = snap.Rows("members").FirstOrDefault(m => m.Text("name") == task.Text("owner")); var picture = (FrameworkElement)Avatar(owner.Text("avatar"), Display(task.Text("owner")), 28); picture.VerticalAlignment = VerticalAlignment.Center; header.Children.Add(picture); }
                var labels = new StackPanel(); var name = OverviewText(task.Text("title"), 14, weight: 600); name.TextWrapping = TextWrapping.NoWrap; name.TextTrimming = TextTrimming.CharacterEllipsis; labels.Children.Add(name);
                labels.Children.Add(OverviewText(task.Text("id") + " · " + (task.Text("owner").Length > 0 ? Display(task.Text("owner")) : T("details.no_owner")) + (task.Text("at").Length > 0 ? " · " + T("details.updated", ("when", When(task.Text("at")))) : ""), 12, true)); Grid.SetColumn(labels, 1); header.Children.Add(labels);
                var chips = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4, VerticalAlignment = VerticalAlignment.Center };
                if (task.Text("status") == "done" && task.Text("report").Length > 0) { var reportChip = OverviewChip(T("details.has_report")); reportChip.Foreground = Accent; reportChip.Background = OverviewAlpha(Accent, .12); if (reportChip.Content is TextBlock text) text.Foreground = Accent; chips.Children.Add(reportChip); }
                var state = task.Text("status"); var stateText = state is "open" or "working" or "blocked" or "done" or "dropped" ? T("task." + state) : state; chips.Children.Add(OverviewChip(stateText, state switch { "done" => "ok", "blocked" => "bad", "working" => "warn", _ => "" })); Grid.SetColumn(chips, 2); header.Children.Add(chips);
                var headerFrame = new Border { Child = header, Padding = new Thickness(12, 10, 12, 10), BorderBrush = Line, BorderThickness = new Thickness(0, 0, 0, task.Text("id") == focus ? 1 : 0) };
                var disclosure = DetailsDisclosure(headerFrame, inner, task.Text("id") == focus); disclosure.RegisterPropertyChangedCallback(Expander.IsExpandedProperty, (_, _) => headerFrame.BorderThickness = new Thickness(0, 0, 0, disclosure.IsExpanded ? 1 : 0)); list.Children.Add(DetailsCard(disclosure));
                if (task.Text("id") == focus) disclosure.Loaded += (_, _) => disclosure.StartBringIntoView(new BringIntoViewOptions { VerticalAlignmentRatio = .5, AnimationDesired = false });
            }
        }
        var filters = DetailsTabs(choices, selected, value => { selected = value; Draw(); return Task.CompletedTask; }); filters.Margin = new Thickness(0, 0, 0, 12); box.Children.Add(filters); box.Children.Add(list); Draw();
    }
    private UIElement DetailsReport(JsonNode task)
    {
        var content = new StackPanel { Spacing = 6 }; var header = new ActionRow { Spacing = 6 }; var icon = (ReferenceVectorIcon)ReferenceIcon("check", 14); icon.Foreground = Paint("3E9B5E", "6CC287"); icon.VerticalAlignment = VerticalAlignment.Center; header.Children.Add(icon); header.Children.Add(OverviewText(T("report.title"), 12.5, weight: 700)); if (task.Text("done_at").Length > 0) header.Children.Add(OverviewText(When(task.Text("done_at")), 12.5, true)); content.Children.Add(header); content.Children.Add(DetailsMarkdown(task.Text("report")));
        var background = Paint("FFFFFF", "252523").Color; var green = Paint("3E9B5E", "6CC287").Color;
        var blend = Windows.UI.Color.FromArgb(255, (byte)Math.Round(background.R * .94 + green.R * .06), (byte)Math.Round(background.G * .94 + green.G * .06), (byte)Math.Round(background.B * .94 + green.B * .06));
        return new Border { Child = content, BorderBrush = OverviewAlpha(Paint("3E9B5E", "6CC287"), .3), BorderThickness = new Thickness(1), Background = new SolidColorBrush(blend), Padding = new Thickness(12, 10, 12, 10), CornerRadius = new CornerRadius(10) };
    }
    private UIElement DetailsMarkdown(string value)
    {
        var body = Rich(value);
        void Style(DependencyObject element)
        {
            if (element is RichTextBlock text) { text.FontSize = 13.5; text.LineHeight = 22.95; }
            if (element is Panel panel) foreach (var child in panel.Children) Style(child);
            else if (element is Border border && border.Child != null) Style(border.Child);
        }
        Style(body); return body;
    }
    private UIElement Protocol(JsonNode p, bool inherited)
    {
        var state = inherited ? T("details.status_active") : p.Text("status") switch { "active" => T("details.status_active"), "proposed" => T("details.status_proposed"), "rejected" => T("details.status_rejected"), "superseded" => T("details.status_superseded"), "retired" => T("details.status_retired"), "enacted" => T("details.status_enacted"), _ => p.Text("status") };
        var box = new StackPanel { Spacing = 8, Padding = new Thickness(14, 10, 14, 12) }; box.Children.Add(OverviewText(T("details.protocol_head", ("id", p.Text("id")), ("title", p.Text("title")), ("kind", p.Text("strength") == "strong" ? T("details.strong_protocol") : T("details.weak_protocol")), ("status", state)), 13, weight: 700));
        string ProtocolName(string reference)
        {
            var split = reference.Split('/', 2); if (split.Length < 2) return reference; var above = orgs.FirstOrDefault(o => o.Text("id") == split[0]); return T("org.protocol_ref", ("org", above.Text("name").Length > 0 ? above.Text("name") : split[0]), ("id", split[1]));
        }
        if (inherited)
        {
            var origin = T("org.inherited_from", ("name", p.Text("from"))); if (p["issued_by"].Text("name").Length > 0) origin += " · " + (p["issued_by"].Flag("person") ? T("org.issued_by_person") : T("org.issued_by", ("name", p["issued_by"].Text("name")))); box.Children.Add(OverviewText(origin, 13, true));
        }
        else
        {
            if (p.Text("retire_target").Length > 0) box.Children.Add(DetailsLabeled(T("details.label_retires"), ProtocolName(p.Text("retire_target"))));
            if (p.Text("supersedes").Length > 0) box.Children.Add(DetailsLabeled(T("details.label_supersedes"), ProtocolName(p.Text("supersedes"))));
            if (p.Flag("inherit")) box.Children.Add(OverviewText(T("org.protocol_inherits"), 13, true));
        }
        if (p.Text("trigger").Length > 0) box.Children.Add(DetailsLabeled(T("details.label_applies"), p.Text("trigger")));
        if (p.Text("guidance").Length > 0) box.Children.Add(OverviewText(p.Text("guidance"), 13));
        if (p.Text("summary_for_person").Length > 0)
        {
            var summary = new StackPanel { Spacing = 2 }; summary.Children.Add(OverviewText(T("details.label_summary"), 13.5, true, lineHeight: 22.95)); summary.Children.Add(DetailsMarkdown(p.Text("summary_for_person")));
            box.Children.Add(new Border { Child = summary, Background = Paint("F8F7F5", "191918"), BorderBrush = Line, BorderThickness = new Thickness(1), Padding = new Thickness(12, 8, 12, 8), CornerRadius = new CornerRadius(10) });
        }
        if (p.Rows("rules").Count > 0)
        {
            var display = p.Text("rules_display");
            if (display.Length == 0) { var rules = new JsonArray(); foreach (var original in p.Rows("rules")) { var rule = original?.DeepClone(); if (rule is JsonObject fields && rule.Text("effect") == "check") { fields.Remove("code"); fields.Remove("examples"); fields.Remove("code_sha256"); } rules.Add(rule); } display = rules.ToJsonString(new() { WriteIndented = true, Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping }); }
            box.Children.Add(DetailsCode(display, true)); if (p.Rows("rules").Any(rule => rule.Text("effect") == "check")) box.Children.Add(CheckRules(p.Rows("rules")));
        }
        if (!inherited) box.Children.Add(OverviewText(T("details.proposed_by", ("name", Display(p.Text("author")))) + " · " + T("details.votes", ("n", p.Text("votes"))) + " · " + T("details.uses", ("n", p.Text("uses"))) + (p.Flag("retired_by_person") ? " · " + T("details.retired_by_person") : ""), 13, true)); return DetailsCard(box);
    }
    private UIElement CheckRules(JsonArray rules)
    {
        var body = new StackPanel { Spacing = 0 };
        foreach (var rule in rules.Where(r => r.Text("effect") == "check"))
        {
            var block = new StackPanel { Spacing = 6, Margin = new Thickness(0, 8, 0, 0) }; body.Children.Add(block);
            var scope = new List<string> { rule.Rows("tools").Count == 1 && rule.Rows("tools")[0].Text() == "Reply" ? T("cc.scope_reply") : string.Join(" / ", rule.Rows("tools").Select(x => x.Text())) };
            if (rule.Text("path_glob").Length > 0) scope.Add(T("cc.scope_path", ("glob", rule.Text("path_glob"))));
            if (rule.Rows("input_contains").Count > 0) scope.Add(T("cc.scope_contains", ("words", string.Join(",", rule.Rows("input_contains").Select(x => x.Text())))));
            var who = rule.Rows("roles").Concat(rule.Rows("members")).ToArray(); var except = rule.Rows("except_roles").Concat(rule.Rows("except_members")).ToArray();
            if (who.Length > 0) scope.Add(T("cc.scope_who", ("names", string.Join(",", who.Select(x => x.Text())))));
            if (except.Length > 0) scope.Add(T("cc.scope_except", ("names", string.Join(",", except.Select(x => x.Text())))));
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
        var header = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 5, HorizontalAlignment = HorizontalAlignment.Left };
        var chevron = (ReferenceVectorIcon)ReferenceIcon("chev", 13); chevron.Foreground = Paint("5A5853", "B8B5AE"); chevron.VerticalAlignment = VerticalAlignment.Center; header.Children.Add(chevron);
        var title = OverviewText(T("cc.code"), 12.5); title.IsTextSelectionEnabled = false; title.Foreground = Paint("5A5853", "B8B5AE"); header.Children.Add(title);
        var disclosure = DetailsDisclosure(header, body); Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(disclosure, T("cc.code"));
        disclosure.RegisterPropertyChangedCallback(Expander.IsExpandedProperty, (_, _) => { chevron.RenderTransformOrigin = new(.5, .5); chevron.RenderTransform = new RotateTransform { Angle = disclosure.IsExpanded ? 90 : 0 }; });
        return disclosure;
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
