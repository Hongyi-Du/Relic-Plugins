using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Documents;
using Microsoft.UI.Xaml.Media;
using Windows.Foundation;

namespace Relic;

public sealed partial class MainWindow
{
    private TextBlock WorkspaceText(string value, double size = 12.5, double lineHeight = 20, bool muted = false, ushort weight = 400)
        => OverviewText(value, size, muted, weight, lineHeight);

    private TextBlock WorkspaceLabel(string value, double size = 12.5, ushort weight = 400)
    {
        var label = WorkspaceText(value, size, size * 1.6, weight: weight); label.TextWrapping = TextWrapping.NoWrap; label.TextTrimming = TextTrimming.CharacterEllipsis;
        return label;
    }

    private FrameworkElement WorkspaceIcon(string name, double size)
    {
        var icon = (ReferenceVectorIcon)ReferenceIcon(name, size); icon.Foreground = Muted; icon.VerticalAlignment = VerticalAlignment.Center; return icon;
    }

    private StackPanel WorkspaceBlock(StackPanel parent, string? heading = null, UIElement? action = null)
    {
        var content = new StackPanel { Spacing = 8 };
        if (heading != null) content.Children.Add(OverviewHeading(WorkspaceText(heading, 12, 19.2, true), action));
        parent.Children.Add(new Border { Child = content, Padding = new Thickness(16, 14, 16, 14), BorderBrush = Line, BorderThickness = new Thickness(0, 0, 0, 1) });
        return content;
    }

    private TextBlock WorkspaceEmpty(string text) => WorkspaceText(text, 12.5, 20, true);
    private Border WorkspaceEmptyBlock(StackPanel parent, string text)
    {
        var block = new Border { Child = WorkspaceEmpty(text), Padding = new Thickness(16, 14, 16, 14), BorderBrush = Line, BorderThickness = new Thickness(0, 0, 0, 1) };
        parent.Children.Add(block); return block;
    }
    private TextBlock WorkspaceTreeEmpty(string text, int depth)
    {
        var label = WorkspaceEmpty(text); label.Margin = new Thickness(depth * 14 + 26, 0, 0, 0); return label;
    }

    private Button WorkspaceRow(UIElement content, Func<Task> action)
    {
        var button = QuietButton("", action); button.Content = content; button.Padding = new Thickness(6, 2, 6, 2); button.MinHeight = 26; button.CornerRadius = new CornerRadius(6);
        button.HorizontalAlignment = HorizontalAlignment.Stretch; button.HorizontalContentAlignment = HorizontalAlignment.Stretch; button.VerticalContentAlignment = VerticalAlignment.Center;
        button.FontSize = 12.5; return button;
    }

    private Grid WorkspaceFileRow(UIElement icon, FrameworkElement label, FrameworkElement? tail = null)
    {
        var row = new Grid { ColumnSpacing = 6 };
        row.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        if (tail != null) row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        ((FrameworkElement)icon).VerticalAlignment = VerticalAlignment.Center; row.Children.Add(icon);
        label.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(label, 1); row.Children.Add(label);
        if (tail != null) { tail.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(tail, 2); row.Children.Add(tail); }
        return row;
    }

    private static SolidColorBrush WorkspaceMix(SolidColorBrush foreground, SolidColorBrush background, double amount)
    {
        var a = foreground.Color; var b = background.Color;
        return new(Windows.UI.Color.FromArgb(255, (byte)Math.Round(a.R * amount + b.R * (1 - amount)), (byte)Math.Round(a.G * amount + b.G * (1 - amount)), (byte)Math.Round(a.B * amount + b.B * (1 - amount))));
    }

    private Border WorkspaceFileHeader(string name)
    {
        var row = new Grid { ColumnSpacing = 8 };
        row.ColumnDefinitions.Add(new() { Width = new GridLength(16) }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); row.ColumnDefinitions.Add(new() { Width = new GridLength(30) }); row.ColumnDefinitions.Add(new() { Width = new GridLength(30) });
        row.Children.Add(WorkspaceIcon("file", 16));
        var labels = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
        var title = WorkspaceLabel(name, 13, 650); title.LineHeight = 17.55;
        var path = WorkspaceLabel(filePath, 11); path.LineHeight = 13; path.FontFamily = new FontFamily("Cascadia Code"); path.Foreground = Muted; ToolTipService.SetToolTip(path, filePath);
        labels.Children.Add(title); labels.Children.Add(path); Grid.SetColumn(labels, 1); row.Children.Add(labels);
        var copy = IconButton("\uE8C8", "file.copy_path", () => { Copy(filePath); return Task.CompletedTask; }); copy.Content = WorkspaceIcon("copy", 15); Grid.SetColumn(copy, 2); row.Children.Add(copy);
        var open = IconButton("\uE8A7", "file.open_default", () => OpenDefault(filePath)); open.Content = WorkspaceIcon("open", 15); Grid.SetColumn(open, 3); row.Children.Add(open);
        var header = new Border { Child = row, Padding = new Thickness(14, 10, 8, 9), BorderBrush = Line, BorderThickness = new Thickness(0, 0, 0, 1), Background = Paint("F8F7F5", "191918") };
        Canvas.SetZIndex(header, 2); return header;
    }

    private static void WorkspaceStickyHeader(Border header)
    {
        ScrollViewer? scroll = null;
        var translation = new TranslateTransform(); header.RenderTransform = translation;
        void Move(object? sender, ScrollViewerViewChangedEventArgs e) { if (scroll != null) translation.Y = scroll.VerticalOffset; }
        header.Loaded += (_, _) =>
        {
            DependencyObject? current = VisualTreeHelper.GetParent(header);
            while (current != null && current is not ScrollViewer) current = VisualTreeHelper.GetParent(current);
            scroll = current as ScrollViewer;
            if (scroll != null) { translation.Y = scroll.VerticalOffset; scroll.ViewChanged += Move; }
        };
        header.Unloaded += (_, _) => { if (scroll != null) scroll.ViewChanged -= Move; scroll = null; };
    }

    private void DrawFileCode(string source, int selectedLine)
    {
        var lines = source.Replace("\r\n", "\n").Replace('\r', '\n').Split('\n'); var shown = lines.Take(6000).ToArray();
        var layout = new Grid { Padding = new Thickness(0, 0, 16, 0), MinHeight = shown.Length * 19.2 };
        layout.ColumnDefinitions.Add(new() { Width = new GridLength(60) }); layout.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        if (selectedLine > 0 && selectedLine <= shown.Length)
        {
            var highlight = new Border { Background = OverviewAlpha(Accent, .15), Height = 19.2, Margin = new Thickness(0, (selectedLine - 1) * 19.2, -16, 0), VerticalAlignment = VerticalAlignment.Top };
            Grid.SetColumnSpan(highlight, 2); layout.Children.Add(highlight);
        }
        var numbers = new StackPanel { Padding = new Thickness(0, 0, 14, 0) };
        for (var i = 0; i < shown.Length; i++)
        {
            var number = WorkspaceText((i + 1).ToString(System.Globalization.CultureInfo.InvariantCulture), 12, 19.2); number.FontFamily = new FontFamily("Cascadia Code"); number.Foreground = Paint("B8B5AF", "5F5D58"); number.TextAlignment = TextAlignment.Right; number.IsTextSelectionEnabled = false;
            number.Height = 19.2; numbers.Children.Add(number);
        }
        layout.Children.Add(numbers);
        // The real text document preserves source characters and selection
        // across lines. The separate line-number controls are not selectable.
        var code = new RichTextBlock { FontFamily = new FontFamily("Cascadia Code"), FontSize = 12, Foreground = Ink, TextWrapping = TextWrapping.NoWrap,
            LineHeight = 19.2, LineStackingStrategy = LineStackingStrategy.BlockLineHeight, IsTextSelectionEnabled = true };
        var paragraph = new Paragraph { Margin = new Thickness(0) };
        for (var i = 0; i < shown.Length; i++) { if (i > 0) paragraph.Inlines.Add(new LineBreak()); paragraph.Inlines.Add(new Run { Text = shown[i] }); }
        code.Blocks.Add(paragraph); code.SelectionChanged += (_, _) => { if (code.SelectedText.Length > 0) selectedRich = code; }; Grid.SetColumn(code, 1); layout.Children.Add(code);
        var scroll = new ScrollViewer { Content = layout, HorizontalScrollMode = ScrollMode.Enabled, HorizontalScrollBarVisibility = ScrollBarVisibility.Auto, VerticalScrollMode = ScrollMode.Disabled, VerticalScrollBarVisibility = ScrollBarVisibility.Disabled };
        scroll.SizeChanged += (_, _) => layout.MinWidth = Math.Max(0, scroll.ActualWidth);
        var surface = new Border { Child = scroll, Padding = new Thickness(0, 6, 0, 18), BorderBrush = Line, BorderThickness = new Thickness(0, 1, 0, 0), Background = Paint("FFFFFF", "1F1F1E") };
        detail.Children.Add(surface);
        if (selectedLine > 0 && selectedLine <= shown.Length) layout.Loaded += (_, _) => layout.StartBringIntoView(new BringIntoViewOptions { TargetRect = new Rect(0, (selectedLine - 1) * 19.2, 1, 19.2), VerticalAlignmentRatio = .5 });
        if (lines.Length > 6000) detail.Children.Add(new Border { Child = WorkspaceText(T("file.lines_shown", ("max", 6000), ("total", lines.Length)), 11.5, 18.4, true), Padding = new Thickness(14, 6, 14, 6) });
    }
}
