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
        try
        {
            var package = new DataPackage(); package.SetText(value); Clipboard.SetContent(package);
            var notice = ShowToast(T("msg.copied")); lastClipboardCopy = new(++copySequence, value, true, null, notice.Id);
        }
        catch (Exception ex)
        {
            var notice = ShowToast(T("msg.copy_failed")); lastClipboardCopy = new(++copySequence, value, false, ex.Message, notice.Id);
        }
    }
    private UIElement Rich(string markdown, bool documentStyle = false)
    {
        var baseSize = documentStyle ? 13.5 : preferences.Text("font") == "large" ? 15.5 : preferences.Text("font") == "small" ? 13 : 14;
        var lineRatio = documentStyle ? 1.7 : 1.65; var content = new StackPanel();
        var blocks = new List<(FrameworkElement Element, double Before, double After, bool Paragraph)>();
        void Add(FrameworkElement element, double before = 0, double after = 8, bool paragraph = false) { blocks.Add((element, before, after, paragraph)); content.Children.Add(element); }
        RichTextBlock Inline(string value, double ratio = 1) => InlineText(value, baseSize * ratio, lineRatio, false);
        var lines = markdown.Replace("\r\n", "\n").Split('\n');
        for (var i = 0; i < lines.Length; i++)
        {
            var line = lines[i];
            if (line.TrimStart().StartsWith("```"))
            {
                var code = new List<string>(); while (++i < lines.Length && !lines[i].TrimStart().StartsWith("```")) code.Add(lines[i]);
                // Both .bubble pre code and .md pre code inherit .9em from
                // the code rule, while the pre owns the 1.55 line spacing.
                var source = string.Join("\n", code); var codeSize = documentStyle ? 12 : 12.5; var codeText = OverviewText(source, codeSize * .9, lineHeight: codeSize * 1.55); codeText.FontFamily = new FontFamily("Cascadia Code"); codeText.TextWrapping = TextWrapping.NoWrap;
                var codeScroll = new ScrollViewer { Content = codeText, HorizontalScrollMode = ScrollMode.Enabled, HorizontalScrollBarVisibility = ScrollBarVisibility.Auto, VerticalScrollMode = ScrollMode.Disabled, VerticalScrollBarVisibility = ScrollBarVisibility.Disabled };
                var codeBlock = new Border { Child = codeScroll, Background = Paint("F6F5F2", "232321"), Padding = new Thickness(11, 9, 11, 9), BorderThickness = new Thickness(1), BorderBrush = Line, CornerRadius = new CornerRadius(8) };
                MarkdownSemantic.RegisterFencedCode(codeBlock, codeScroll, codeText);
                Add(codeBlock, documentStyle ? 12 : 6, documentStyle ? 12 : 6); continue;
            }
            if (Regex.IsMatch(line, @"^\s*\|.*\|\s*$"))
            {
                var tableLines = new List<string> { line }; while (i + 1 < lines.Length && Regex.IsMatch(lines[i + 1], @"^\s*\|.*\|\s*$")) tableLines.Add(lines[++i]);
                bool Rule(string text) => Regex.IsMatch(text, @"^\s*\|?\s*:?-{2,}"); var hasHeading = tableLines.Count > 1 && Rule(tableLines[1]);
                var rows = tableLines.Where(text => !Rule(text)).Select(text => text.Trim().Trim('|').Split('|')).ToArray(); var table = new Grid { HorizontalAlignment = HorizontalAlignment.Left };
                for (var col = 0; col < rows.Select(row => row.Length).DefaultIfEmpty().Max(); col++) table.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
                for (var row = 0; row < rows.Length; row++)
                {
                    table.RowDefinitions.Add(new() { Height = GridLength.Auto });
                    for (var col = 0; col < rows[row].Length; col++)
                    {
                        var label = Inline(rows[row][col].Trim(), .93); label.FontWeight = row == 0 && hasHeading ? FontWeights.SemiBold : FontWeights.Normal;
                        var cell = new Border { Padding = new Thickness(8, 3, 8, 3), BorderThickness = new Thickness(col == 0 ? 1 : 0, row == 0 ? 1 : 0, 1, 1), BorderBrush = Paint("DEDBD4", "3A3936"), Child = label, Background = row == 0 && hasHeading ? OverviewAlpha(Ink, .04) : new SolidColorBrush(Colors.Transparent) };
                        Grid.SetRow(cell, row); Grid.SetColumn(cell, col); table.Children.Add(cell);
                    }
                }
                Add(new ScrollViewer { Content = table, HorizontalScrollMode = ScrollMode.Enabled, HorizontalScrollBarVisibility = ScrollBarVisibility.Auto, VerticalScrollMode = ScrollMode.Disabled, VerticalScrollBarVisibility = ScrollBarVisibility.Disabled }, 6, 6); continue;
            }
            var heading = Regex.Match(line, @"^(#{1,6})\s+(.+)");
            if (heading.Success) { var title = Inline(heading.Groups[2].Value, documentStyle ? 1.02 : 1); title.FontWeight = FontWeights.Bold; Add(title, documentStyle ? 10 : 8, 4); continue; }
            if (string.IsNullOrWhiteSpace(line)) continue;
            if (Regex.IsMatch(line, @"^\s*>"))
            {
                var quoteLines = new List<string> { Regex.Replace(line, @"^\s*>\s?", "") }; while (i + 1 < lines.Length && Regex.IsMatch(lines[i + 1], @"^\s*>")) quoteLines.Add(Regex.Replace(lines[++i], @"^\s*>\s?", ""));
                var quote = string.Join("\n", quoteLines); var author = Regex.Match(quote, @"^([^\n：:]{1,40})[：:]\s?([\s\S]*)$");
                var text = OverviewText("", baseSize * .92, lineHeight: baseSize * .92 * lineRatio); text.Foreground = Paint("5A5853", "B8B5AE");
                if (author.Success) { text.Inlines.Add(new Run { Text = T("chat.quote_from", ("name", author.Groups[1].Value)), FontWeight = FontWeights.SemiBold, Foreground = Ink }); text.Inlines.Add(new Run { Text = author.Groups[2].Value }); } else text.Text = quote;
                Add(new Border { BorderThickness = new Thickness(3, 0, 0, 0), BorderBrush = Paint("DEDBD4", "3A3936"), Padding = new Thickness(10, 2, 0, 2), Child = text }); continue;
            }
            var list = Regex.Match(line, @"^(\s*)([-*•+]|\d+[.)])\s+(.*)$");
            if (list.Success)
            {
                var ordered = char.IsDigit(list.Groups[2].Value[0]); var count = ordered && int.TryParse(list.Groups[2].Value.TrimEnd('.', ')'), out var startAt) ? startAt : 1; var items = new StackPanel();
                do
                {
                    var itemText = list.Groups[3].Value; var sub = list.Groups[1].Value.Length >= 2;
                    while (i + 1 < lines.Length && Regex.IsMatch(lines[i + 1], @"^\s{2,}\S") && !Regex.IsMatch(lines[i + 1], @"^\s*(?:>|\|.*\|\s*$|(?:[-*•+]|\d+[.)])\s+)")) itemText += "\n" + lines[++i].Trim();
                    var item = Inline(itemText); FrameworkElement row;
                    if (ordered)
                    {
                        var numbered = new Grid(); numbered.ColumnDefinitions.Add(new() { Width = new GridLength(22) }); numbered.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
                        var bullet = OverviewText(count++ + ".", baseSize, lineHeight: baseSize * lineRatio); bullet.TextAlignment = TextAlignment.Right; bullet.Margin = new Thickness(0, 0, 6, 0); numbered.Children.Add(bullet);
                        Grid.SetColumn(item, 1); numbered.Children.Add(item); row = numbered;
                    }
                    else row = new NativeListItemPanel(new NativeListMarker(FontFamilies.UI, baseSize, words.Language, Ink), item, baseSize * lineRatio, itemText.Length == 0);
                    row.Margin = new Thickness(sub ? 18 : 0, 0, 0, 0); items.Children.Add(row);
                    if (i + 1 >= lines.Length) break; list = Regex.Match(lines[i + 1], @"^(\s*)([-*•+]|\d+[.)])\s+(.*)$"); if (!list.Success) break; i++;
                } while (true);
                Add(items, 2, 8); continue;
            }
            var paragraphLines = new List<string> { line };
            while (i + 1 < lines.Length && !string.IsNullOrWhiteSpace(lines[i + 1]) && !Regex.IsMatch(lines[i + 1], @"^\s*(?:```|>|#{1,6}\s|[-*•+]\s|\d+[.)]\s|\|.*\|\s*$)")) paragraphLines.Add(lines[++i]);
            Add(Inline(string.Join("\n", paragraphLines)), paragraph: true);
        }
        // Normal HTML block margins collapse between adjacent runs. Express
        // that measured spacing through native layout margins, not blank rows.
        for (var index = 0; index < blocks.Count; index++)
        {
            var block = blocks[index]; var top = index == 0 ? block.Before : Math.Max(blocks[index - 1].After, block.Before);
            var bottom = index == blocks.Count - 1 && !block.Paragraph ? block.After : 0; block.Element.Margin = new Thickness(0, top, 0, bottom);
        }
        return content;
    }
    private RichTextBlock InlineText(string value, double size = 14, double lineRatio = 1.65, bool useFontPreference = true)
    {
        var fontSize = size * (useFontPreference ? preferences.Text("font") == "large" ? 15.5 / 14 : preferences.Text("font") == "small" ? 13d / 14 : 1 : 1);
        var text = new RichTextBlock { IsTextSelectionEnabled = true, Foreground = Ink, FontFamily = new FontFamily(FontFamilies.UI), FontSize = fontSize, TextWrapping = TextWrapping.Wrap,
            LineHeight = fontSize * lineRatio, LineStackingStrategy = LineStackingStrategy.BlockLineHeight };
        var paragraph = new Paragraph();
        Hyperlink Link(string targetText, bool path, bool code = false)
        {
            var link = new Hyperlink { Foreground = code ? Ink : Accent, UnderlineStyle = path ? UnderlineStyle.None : UnderlineStyle.Single }; link.Inlines.Add(new Run { Text = targetText });
            if (path) ToolTipService.SetToolTip(link, T("chat.path_preview"));
            link.Click += async (_, _) => await Run(async () =>
            {
                if (path) { var target = InlineParts.PathTarget(targetText); await OpenFile(target.Path, target.Line); }
                else if (Uri.TryCreate(targetText, UriKind.Absolute, out var uri) && uri.Scheme is "http" or "https") await Windows.System.Launcher.LaunchUriAsync(uri);
            });
            return link;
        }
        foreach (var part in InlineParts.Parse(value))
        {
            switch (part.Kind)
            {
                case "path": paragraph.Inlines.Add(Link(part.Text, true)); break;
                case "url": paragraph.Inlines.Add(Link(part.Text, false)); break;
                case "code":
                    // CSS `font: .9em var(--mono)` resets line-height to normal.
                    // Reusing the surrounding paragraph's 1.65 line box made
                    // the inline pill 25.1px tall instead of its natural height.
                    var code = new TextBlock { FontSize = fontSize * .9, FontFamily = new FontFamily("Cascadia Code"), Foreground = Ink,
                        IsTextSelectionEnabled = true };
                    UIElement codeContent = code;
                    if (InlineParts.IsAbsolute(part.Text))
                    {
                        code.Inlines.Add(Link(part.Text, true, true));
                        var decorated = new Grid(); decorated.Children.Add(code);
                        var underline = new Microsoft.UI.Xaml.Shapes.Line { Stroke = OverviewAlpha(Accent, .7), StrokeThickness = 1, StrokeDashArray = new DoubleCollection { 1, 1 }, IsHitTestVisible = false };
                        decorated.Children.Add(underline);
                        code.SizeChanged += (_, _) => { underline.X2 = code.ActualWidth; underline.Y1 = underline.Y2 = code.BaselineOffset + 1; };
                        codeContent = decorated;
                    }
                    else code.Text = part.Text;
                    paragraph.Inlines.Add(new InlineUIContainer { Child = new Border { Child = codeContent, Padding = new Thickness(5, 1, 5, 1), Background = OverviewAlpha(Ink, .07), CornerRadius = new CornerRadius(5) } }); break;
                case "bold": var bold = new Bold(); bold.Inlines.Add(new Run { Text = part.Text }); paragraph.Inlines.Add(bold); break;
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
        var dialog = new NativeContentDialog { XamlRoot = root.XamlRoot, Content = box }; Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(dialog, T("details.dialog"));
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
        // The details surface owns its header/body padding and viewport-sized box.
        // Apply zero template padding before realization so it is not shifted or clipped.
        try { await Draw(tab); await Dialog(dialog, contentOwnsPadding: true); } finally { root.SizeChanged -= Resize; }
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
        var content = new StackPanel { Spacing = 6 }; var header = new DetailsFilterRow { Spacing = 6 }; var icon = (ReferenceVectorIcon)ReferenceIcon("check", 14); icon.Foreground = Paint("3E9B5E", "6CC287"); icon.VerticalAlignment = VerticalAlignment.Center; header.Children.Add(icon); header.Children.Add(OverviewText(T("report.title"), 12.5, weight: 700)); if (task.Text("done_at").Length > 0) header.Children.Add(OverviewText(When(task.Text("done_at")), 12.5, true)); content.Children.Add(header); content.Children.Add(DetailsMarkdown(task.Text("report")));
        var background = Paint("FFFFFF", "252523").Color; var green = Paint("3E9B5E", "6CC287").Color;
        var blend = Windows.UI.Color.FromArgb(255, (byte)Math.Round(background.R * .94 + green.R * .06), (byte)Math.Round(background.G * .94 + green.G * .06), (byte)Math.Round(background.B * .94 + green.B * .06));
        return new Border { Child = content, BorderBrush = OverviewAlpha(Paint("3E9B5E", "6CC287"), .3), BorderThickness = new Thickness(1), Background = new SolidColorBrush(blend), Padding = new Thickness(12, 10, 12, 10), CornerRadius = new CornerRadius(10) };
    }
    private UIElement DetailsMarkdown(string value) => Rich(value, true);
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
        var header = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 5, HorizontalAlignment = HorizontalAlignment.Left };
        var chevron = (ReferenceVectorIcon)ReferenceIcon("chev", 13); chevron.Foreground = Paint("5A5853", "B8B5AE"); chevron.VerticalAlignment = VerticalAlignment.Center; header.Children.Add(chevron);
        var title = OverviewText(T("cc.code"), 12.5); title.IsTextSelectionEnabled = false; title.Foreground = Paint("5A5853", "B8B5AE"); header.Children.Add(title);
        var disclosure = DetailsDisclosure(header, body, headerAlignment: HorizontalAlignment.Left); Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(disclosure, T("cc.code"));
        disclosure.RegisterPropertyChangedCallback(Expander.IsExpandedProperty, (_, _) => { chevron.RenderTransformOrigin = new(.5, .5); chevron.RenderTransform = new RotateTransform { Angle = disclosure.IsExpanded ? 90 : 0 }; });
        return disclosure;
    }
    private static string TraceToolLabel(string value)
    {
        var title = Regex.Replace(value.Length > 0 ? value : "tool", "^mcp__plugin_relic_org__|^mcp__relic_org__", "Relic "); return Regex.Replace(title, "^mcp__", "");
    }
    private static bool TraceTruthy(JsonNode? value) => value is JsonObject or JsonArray || value is JsonValue scalar && !(scalar.TryGetValue<bool>(out var boolean) && !boolean || scalar.TryGetValue<double>(out var number) && number == 0 || scalar.TryGetValue<string>(out var text) && text.Length == 0);
    private static string TraceString(JsonNode? value)
    {
        if (value is JsonArray list) return string.Join(",", list.Select(item => item == null ? "" : TraceString(item)));
        if (value is JsonObject) return "[object Object]";
        return value.Text();
    }
    private static string TraceClip(string value, int length)
    {
        var text = Regex.Replace(value, "[\\u0009-\\u000d\\u0020\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000\\ufeff]+", " ").Trim(' '); return text.Length > length ? text[..(length - 1)] + "…" : text;
    }
    private static string TraceArgument(JsonNode? step)
    {
        var text = step.Text("text");
        try
        {
            var parsed = JsonNode.Parse(text); var selected = parsed is JsonObject values ? new[] { "command", "cmd", "file_path", "pattern", "url", "query", "description", "prompt", "path", "body" }.Select(key => values[key]).FirstOrDefault(TraceTruthy) : null;
            text = selected != null ? TraceString(selected) : parsed?.ToJsonString(new() { Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping }) ?? "null";
        }
        catch (System.Text.Json.JsonException) { }
        return TraceClip(text, 120);
    }
    private static string TraceClock(string at)
    {
        if (!DateTimeOffset.TryParse(at, out var stamp)) { if (!double.TryParse(at, out var seconds)) return ""; stamp = DateTimeOffset.FromUnixTimeSeconds((long)seconds); }
        return stamp.ToLocalTime().ToString("HH:mm", System.Globalization.CultureInfo.InvariantCulture);
    }
    private async Task Trace(StackPanel box, string who)
    {
        box.Children.Clear(); box.Spacing = 0; var targetOrg = org;
        var card = snap.Rows("members").FirstOrDefault(item => item.Text("name") == who); if (card == null) return;
        var title = OverviewText(T("trace.title", ("name", Display(who))), 16.38, weight: 700); title.Margin = new Thickness(0, 0, 0, 2); box.Children.Add(title);
        var session = card.Text("agent").Length > 0 ? "subagent " + card.Text("agent")[..Math.Min(12, card.Text("agent").Length)] + (card.Text("parent").Length > 0 ? T("trace.in_session", ("name", Display(card.Text("parent")))) : "") : card.Text("session").Length > 0 ? T("trace.session", ("id", card.Text("session")[..Math.Min(12, card.Text("session").Length)])) : "";
        var meta = OverviewText(string.Join(" · ", new[] { who, card.Text("harness_label"), card.Text("surface_label"), card.Text("model"), session }.Where(value => value.Length > 0)), 12.5, true); meta.Margin = new Thickness(0, 0, 0, 12); box.Children.Add(meta);
        var query = SettingsInput("", T("trace.search")); query.Height = 30; query.Padding = new Thickness(10, 3, 10, 3);
        var steps = new List<JsonNode?>(); var list = new StackPanel(); JsonNode? data = null; var selectedRole = "all";
        void Draw()
        {
            list.Children.Clear(); if (data.Flag("missing")) { list.Children.Add(DetailsEmpty(T("trace.no_session"))); return; }
            var selected = steps.Where(step => (selectedRole == "all" || (selectedRole == "talk" ? step.Text("role") is "user" or "assistant" : step.Text("role") is "tool_call" or "tool_result")) && step.Text("text").ToLowerInvariant().Contains(query.Text.ToLowerInvariant(), StringComparison.Ordinal)).ToArray();
            if (selected.Length == 0) list.Children.Add(DetailsEmpty(T(data == null ? "common.loading" : "trace.no_steps")));
            var actions = new StackPanel { Padding = new Thickness(0, 4, 0, 4) };
            foreach (var step in selected)
            {
                var label = step.Text("role") switch { "user" => T("trace.user"), "assistant" => T("common.reply"), "tool_call" => TraceToolLabel(step.Text("tool")), "tool_result" => T("common.result"), "thinking" => T("trace.thinking"), "context" => T("trace.injected"), _ => step.Text("role") };
                var header = new Grid { ColumnSpacing = 8, Padding = new Thickness(12, 3, 10, 3) };
                header.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); header.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); header.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); header.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
                header.Children.Add(new Border { Width = 7, Height = 7, CornerRadius = new CornerRadius(3.5), VerticalAlignment = VerticalAlignment.Center, Background = step.Flag("error") ? Paint("C2412D", "EE8A78") : step.Text("role") == "tool_result" ? Paint("3E9B5E", "6CC287") : Paint("B8B5AF", "5F5D58") });
                var tool = OverviewText(label, 12.5, weight: 600); tool.IsTextSelectionEnabled = false; tool.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(tool, 1); header.Children.Add(tool);
                var preview = OverviewText(step.Text("role") == "tool_call" ? TraceArgument(step) : TraceClip(step.Text("text"), 120), 11.5, true); preview.FontFamily = new FontFamily("Cascadia Code"); preview.IsTextSelectionEnabled = false; preview.TextWrapping = TextWrapping.NoWrap; preview.TextTrimming = TextTrimming.CharacterEllipsis; preview.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(preview, 2); header.Children.Add(preview);
                var clock = OverviewText(TraceClock(step.Text("at")), 11, true); clock.IsTextSelectionEnabled = false; clock.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(clock, 3); header.Children.Add(clock);
                var source = OverviewText(step.Text("text"), 11.5, lineHeight: 17.825); source.FontFamily = new FontFamily("Cascadia Code");
                var sourceScroll = Scroll(source); sourceScroll.MaxHeight = 344;
                var program = new Border { Child = sourceScroll, Padding = new Thickness(9, 7, 9, 7), Background = Paint("F6F5F2", "232321"), BorderBrush = Line, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(7), MaxHeight = 360 };
                var inner = new Border { Child = program, Padding = new Thickness(27, 2, 10, 8) };
                var expand = DetailsDisclosure(header, inner, step.Text("role") is "user" or "assistant");
                // Keep the existing full-step API for any abbreviated record;
                // the organization/member are captured before asynchronous work.
                var loading = false; var fullLoaded = !step.Flag("cut");
                expand.Expanding += async (_, _) =>
                {
                    if (loading || fullLoaded) return; loading = true;
                    try { await Run(async () => { var exact = await api!.Get(Client.Org(targetOrg, "/step?member=" + Client.Segment(who) + "&i=" + step.Text("i"))); source.Text = exact.Text("text"); fullLoaded = true; }); }
                    finally { loading = false; }
                };
                actions.Children.Add(expand);
            }
            if (selected.Length > 0) list.Children.Add(new Border { Child = actions, BorderBrush = Line, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(10), Background = Paint("FFFFFF", "1F1F1E") });
            if (data.Text("total") is not ("" or "0")) { var total = OverviewText(T("trace.total", ("n", data.Text("total"))) + (data.Text("path").Length > 0 ? " · " + data.Text("path") : ""), 12, true); total.Margin = new Thickness(0, 8, 0, 0); list.Children.Add(total); }
        }
        var role = DetailsTabs(new[] { ("all", T("common.all")), ("talk", T("trace.filter_talk")), ("tools", T("trace.filter_actions")) }, selectedRole, value => { selectedRole = value; Draw(); return Task.CompletedTask; }); role.VerticalAlignment = VerticalAlignment.Center;
        var filters = new DetailsFilterRow { Spacing = 8, Margin = new Thickness(0, 0, 0, 12) }; filters.Children.Add(role); filters.Children.Add(SettingsVoiceField(query, 220)); query.Padding = new Thickness(10, 3, preferences.Text("voice") == "off" ? 10 : 34, 3); box.Children.Add(filters);
        var fetching = false; Button? older = null;
        async Task Fetch(string before = "")
        {
            if (fetching) return; fetching = true;
            try { data = await api!.Get(Client.Org(targetOrg, "/transcript?member=" + Client.Segment(who) + "&limit=400" + (before.Length > 0 ? "&before=" + before : ""))); steps.InsertRange(0, data.Rows("steps")); if (older != null) older.Visibility = data.Text("start") is "" or "0" ? Visibility.Collapsed : Visibility.Visible; Draw(); }
            finally { fetching = false; }
        }
        older = Button("", () => Fetch(data.Text("start"))); older.Content = OverviewText(T("trace.load_older"), 12); ((TextBlock)older.Content).Foreground = Paint("5A5853", "B8B5AE"); older.Padding = new Thickness(12, 3, 12, 3); older.MinHeight = 0; older.CornerRadius = new CornerRadius(14); older.HorizontalAlignment = HorizontalAlignment.Center; older.Margin = new Thickness(0, 8, 0, 8); box.Children.Add(older); box.Children.Add(list);
        query.TextChanged += (_, _) => Draw(); await Fetch();
    }
}
