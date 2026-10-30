using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Relic.Core;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private TextBlock ConversationMetadata(string text, double size = 12, bool strong = false)
    {
        var label = OverviewText(text, size, !strong, strong ? (ushort)600 : (ushort)400, size * 1.3);
        if (strong) label.Foreground = Paint("5A5853", "B8B5AE");
        label.VerticalAlignment = VerticalAlignment.Bottom;
        return label;
    }

    private Grid ConversationRow(UIElement content, UIElement? avatar, bool continued = false, bool inThread = false)
    {
        var row = new Grid { ColumnSpacing = 10, Margin = new Thickness(0, continued ? 4 : preferences.Text("density") == "compact" ? 7 : 14, 0, 0) };
        row.ColumnDefinitions.Add(new() { Width = new GridLength(inThread ? 30 : 36) });
        row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        if (avatar != null) { ((FrameworkElement)avatar).VerticalAlignment = VerticalAlignment.Top; row.Children.Add(avatar); }
        Grid.SetColumn((FrameworkElement)content, 1); row.Children.Add(content); return row;
    }

    private UIElement AutoReceipt(JsonNode item, bool inThread)
    {
        var from = item.Text("from"); var speaker = snap.Rows("members").FirstOrDefault(m => m.Text("name") == from);
        var portrait = (FrameworkElement)Avatar(speaker.Text("avatar"), Display(from), inThread ? 30 : 36);
        ToolTipService.SetToolTip(portrait, Display(from));
        if (speaker != null) portrait.Tapped += async (_, e) => { e.Handled = true; await Run(() => MemberCard(from, portrait)); };
        var body = System.Text.RegularExpressions.Regex.Replace(item.Text("body"), @"^\[Relic auto-receipt\]\s*", "");
        var column = new StackPanel { Spacing = 4, HorizontalAlignment = HorizontalAlignment.Left };
        var who = new ActionRow { Spacing = 6 };
        who.Children.Add(ConversationMetadata(Display(from), 12.5, true));
        who.Children.Add(ConversationMetadata(T("msg.auto_receipt_to", ("names", words.List(item.Rows("to").Select(x => Display(x.Text())))))));
        who.Children.Add(ConversationMetadata(TraceClock(item.Text("at")))); column.Children.Add(who);
        var header = new StackPanel { Orientation = Orientation.Horizontal };
        var marker = OverviewText("▸ ", 12.5, true); header.Children.Add(marker);
        header.Children.Add(OverviewText(TraceClip(body, 90), 12.5, true));
        var original = OverviewText(body, 12, lineHeight: 18.6); original.Foreground = Paint("5A5853", "B8B5AE"); original.Margin = new Thickness(0, 6, 0, 0);
        var disclosure = DetailsDisclosure(header, original);
        disclosure.RegisterPropertyChangedCallback(Expander.IsExpandedProperty, (_, _) => marker.Text = disclosure.IsExpanded ? "▾ " : "▸ ");
        var card = new Border { Child = disclosure, Background = Paint("F8F7F5", "191918"), BorderBrush = Line, BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(10), Padding = new Thickness(10, 6, 10, 6) };
        var layout = new MessageBubbleLayout { MaxWidth = 640, HorizontalAlignment = HorizontalAlignment.Left }; layout.Children.Add(card); column.Children.Add(layout);
        return ConversationRow(column, portrait, inThread: inThread);
    }

    private UIElement ConversationStep(string targetOrg, string targetMember, JsonNode? call, JsonNode? result)
    {
        var header = new Grid { Padding = new Thickness(12, 3, 10, 3), ColumnSpacing = 8 };
        for (var i = 0; i < 4; i++) header.ColumnDefinitions.Add(new() { Width = i == 2 ? new GridLength(1, GridUnitType.Star) : GridLength.Auto });
        header.Children.Add(new Border { Width = 7, Height = 7, CornerRadius = new CornerRadius(3.5), VerticalAlignment = VerticalAlignment.Center,
            Background = result == null ? Paint("B8B5AF", "5F5D58") : result.Flag("error") ? Paint("C2412D", "EE8A78") : Paint("3E9B5E", "6CC287") });
        void Add(FrameworkElement child, int column) { child.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(child, column); header.Children.Add(child); }
        Add(OverviewText(call == null ? T("common.result") : TraceToolLabel(call.Text("tool")), 12.5, weight: 600), 1);
        var argument = OverviewText(call == null ? TraceClip(result.Text("text"), 120) : TraceArgument(call), 11.5, true);
        argument.FontFamily = new FontFamily("Cascadia Code"); argument.TextWrapping = TextWrapping.NoWrap; argument.TextTrimming = TextTrimming.CharacterEllipsis; Add(argument, 2);
        var clock = OverviewText(TraceClock((call ?? result).Text("at")), 11, true);
        clock.TextWrapping = TextWrapping.WrapWholeWords; Add(clock, 3);
        var sources = new StackPanel { Spacing = 6, Padding = new Thickness(27, 2, 10, 8) };
        var disclosure = DetailsDisclosure(header, sources);
        disclosure.Expanding += async (_, _) =>
        {
            if (sources.Children.Count > 0) return;
            foreach (var step in new[] { call, result }.Where(s => s != null))
            {
                var text = OverviewText(step.Text("text"), 11.5, lineHeight: 17.825); text.FontFamily = new FontFamily("Cascadia Code");
                var scroll = Scroll(text); scroll.MaxHeight = 344;
                sources.Children.Add(new Border { Child = scroll, Background = Paint("F6F5F2", "232321"), BorderBrush = Line, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(7), Padding = new Thickness(9, 7, 9, 7), MaxHeight = 360 });
                if (step.Flag("cut") && step?["i"] != null && targetMember.Length > 0)
                {
                    try { var full = await api!.Get(Client.Org(targetOrg, "/step?member=" + Client.Segment(targetMember) + "&i=" + step.Text("i"))); if (full.Text("text").Length > 0) text.Text = full.Text("text"); }
                    catch (Exception) { /* Keep the abbreviated source, matching the reference disclosure. */ }
                }
            }
        };
        return disclosure;
    }

    private UIElement ConversationActions(JsonNode group)
    {
        var pairs = Transcript.PairTools(group.Rows("steps")); var targetOrg = org; var targetMember = group.Text("member");
        var counts = pairs.Where(pair => pair.Call != null).GroupBy(pair => TraceToolLabel(pair.Call.Text("tool"))).OrderByDescending(names => names.Count()).Take(4);
        var summary = string.Join(" · ", counts.Select(names => names.Key + (names.Count() > 1 ? " ×" + names.Count() : "")));
        var failed = pairs.Count(pair => pair.Result.Flag("error"));
        var header = new Grid { Padding = new Thickness(10, 6, 10, 6), ColumnSpacing = 8 };
        for (var i = 0; i < 5; i++) header.ColumnDefinitions.Add(new() { Width = i == 2 ? new GridLength(1, GridUnitType.Star) : GridLength.Auto });
        void Add(FrameworkElement child, int column) { child.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(child, column); header.Children.Add(child); }
        var chevron = (ReferenceVectorIcon)ReferenceIcon("chev", 13); chevron.Foreground = Muted; chevron.RenderTransformOrigin = new(.5, .5); Add(chevron, 0);
        var title = OverviewText(T("step.actions", ("n", pairs.Count)), 12.5, weight: 600); title.Foreground = Paint("5A5853", "B8B5AE"); Add(title, 1);
        var preview = OverviewText(summary, 12.5, true); preview.TextWrapping = TextWrapping.NoWrap; preview.TextTrimming = TextTrimming.CharacterEllipsis; Add(preview, 2);
        if (failed > 0) Add(OverviewChip(T("step.failed", ("n", failed)), "bad"), 3);
        // Summary metadata inherits normal CSS wrapping; an unbreakable clock
        // must not be split by WinUI's default Wrap emergency behavior.
        var clock = OverviewText(TraceClock(group.Text("at")), 12.5, true);
        clock.TextWrapping = TextWrapping.WrapWholeWords; Add(clock, 4);
        var rows = new StackPanel { Padding = new Thickness(0, 4, 0, 4) };
        var inner = new Border { Child = rows, BorderThickness = new Thickness(0, 1, 0, 0), BorderBrush = Line };
        var disclosure = DetailsDisclosure(header, inner);
        disclosure.RegisterPropertyChangedCallback(Expander.IsExpandedProperty, (_, _) => chevron.RenderTransform = new RotateTransform { Angle = disclosure.IsExpanded ? 90 : 0 });
        disclosure.Expanding += (_, _) => { if (rows.Children.Count == 0) foreach (var (call, result) in pairs) rows.Children.Add(ConversationStep(targetOrg, targetMember, call, result)); };
        var card = new Border { Child = disclosure, Background = Paint("FFFFFF", "1F1F1E"), BorderBrush = Line, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(10) };
        // A capped Stretch child centers itself in a wider Grid column. The
        // reference action block instead fills up to 720px from the body's left.
        var width = new LiveWidthLimit { Limit = 720 }; width.Children.Add(card);
        return ConversationRow(width, null, continued: true);
    }
}
