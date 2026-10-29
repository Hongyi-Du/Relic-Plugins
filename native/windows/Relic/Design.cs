using Microsoft.UI;
using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Relic.Core;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private readonly Border sidebarSurface = new(), inspectorSurface = new(), composerSurface = new();
    private readonly Grid inspector = new(), paneHeader = new(), quoteRow = new();
    private Microsoft.UI.Xaml.Controls.Primitives.FlyoutBase? transientFlyout;
    private void ShowPopover(FrameworkElement content, FrameworkElement anchor, Microsoft.UI.Xaml.Controls.Primitives.FlyoutPlacementMode placement)
    {
        transientFlyout?.Hide(); content.RequestedTheme = root.RequestedTheme;
        foreach (var resource in root.Resources) content.Resources[resource.Key] = resource.Value;
        var scroll = Scroll(content); scroll.MaxHeight = Math.Max(320, root.ActualHeight - 120);
        var flyout = new Flyout { Content = scroll, Placement = placement }; transientFlyout = flyout; flyout.ShowAt(anchor);
    }
    private readonly StackPanel sidebarFooter = new() { Spacing = 4, Padding = new Thickness(12, 8, 12, 12) };
    private bool Dark => preferences.Text("theme") == "dark" || preferences.Text("theme") is "" or "system" && root.ActualTheme == ElementTheme.Dark;
    private SolidColorBrush Paint(string light, string dark = "")
    {
        var hex = Dark && dark.Length > 0 ? dark : light;
        return new(Windows.UI.Color.FromArgb(255, Convert.ToByte(hex.Substring(0, 2), 16), Convert.ToByte(hex.Substring(2, 2), 16), Convert.ToByte(hex.Substring(4, 2), 16)));
    }
    private SolidColorBrush Ink => Paint("1B1B1A", "ECEAE5");
    private SolidColorBrush Muted => Paint("8F8C86", "8A877F");
    private SolidColorBrush Line => Paint("ECEAE6", "2C2B29");
    private SolidColorBrush Accent => Paint(preferences.Text("accent") switch { "ink" => Dark ? "D9D6CF" : "3A3936", "indigo" => "5B61D6", "blue" => "2F6BD8", "rose" => "C4456C", "amber" => "B9821D", _ => "C8643F" });
    private TextBlock Quiet(string value, double size = 12) { var t = Text(value, size); t.Foreground = Muted; return t; }
    private TextBlock Ellipsis(string value, double size = 13)
    {
        var t = Text(value, size); t.TextWrapping = TextWrapping.NoWrap; t.TextTrimming = TextTrimming.CharacterEllipsis;
        ToolTipService.SetToolTip(t, value); return t;
    }
    private TextBlock Heading(string value, double size = 14) { var t = Text(value, size); t.FontWeight = FontWeights.SemiBold; return t; }
    private FrameworkElement Glyph(string glyph, double size = 16)
    {
        var name = glyph switch
        {
            "\uE700" => "sidebar", "\uE72B" => "back", "\uE72A" => "fwd", "\uE7BA" or "\uEA8F" => "bell", "\uE715" => "cc",
            "\uE8FD" => "org", "\uE8B7" => "work", "\uE8A5" => "file", "\uE721" => "search", "\uE713" => "gear",
            "\uE8D4" => "lang", "\uE945" => "sparkle", "\uE73A" => "check", "\uE71A" => "stop", "\uE81C" => "trace",
            "\uE8F2" => "quote", "\uE97A" => "thread", "\uE8C8" => "copy", "\uE711" => "x", "\uE74A" => "up", "\uE720" => "mic",
            "\uE8A7" => "open", "\uE738" => "minus", "\uE710" => "plus", "\uE9A6" => "fit", "\uE790" => "palette",
            "\uE774" => "globe", "\uE839" => "plug", "\uE946" => "info", "\uE70F" => "neworg", "\uE77B" => "user",
            "\uE76C" or "\uE70D" => "chev", _ => throw new ArgumentOutOfRangeException(nameof(glyph), glyph, "Icon has no reference vector")
        };
        var icon = (FrameworkElement)ReferenceIcon(name, size);
        if (glyph == "\uE70D") { icon.RenderTransformOrigin = new(.5, .5); icon.RenderTransform = new RotateTransform { Angle = 90 }; }
        return icon;
    }
    private Button IconButton(string glyph, string key, Func<Task> action, string? tooltip = null)
    {
        var b = Button("", action); b.Content = key == "chat.card" ? ReferenceIcon("card") : key == "card.new_name" ? ReferenceIcon("edit") : Glyph(glyph, glyph is "\uE720" or "\uE74A" ? 17 : 16); b.Width = 30; b.Height = 30;
        b.Padding = new Thickness(5); b.BorderThickness = new Thickness(0); b.Background = new SolidColorBrush(Colors.Transparent);
        AutomationProperties.SetName(b, tooltip ?? T(key)); ToolTipService.SetToolTip(b, tooltip ?? T(key)); return b;
    }
    private Button QuietButton(string label, Func<Task> action)
    {
        var b = Button(label, action); b.Background = new SolidColorBrush(Colors.Transparent); b.BorderThickness = new Thickness(0);
        b.Padding = new Thickness(6, 3, 6, 3); return b;
    }
    private Button ChipButton(string icon, string label, string tooltip, Func<Task> action)
    {
        var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6, VerticalAlignment = VerticalAlignment.Center };
        row.Children.Add(ReferenceIcon(icon, 15)); var text = Text(label, 12.5); text.TextWrapping = TextWrapping.NoWrap; row.Children.Add(text);
        var button = QuietButton("", action); button.Content = row; button.Height = 28; button.Padding = new Thickness(10, 0, 10, 0); button.CornerRadius = new CornerRadius(9);
        button.BorderBrush = Paint("DEDBD4", "3A3936"); button.BorderThickness = new Thickness(1); button.Foreground = Paint("5A5853", "B8B5AE"); text.Foreground = button.Foreground;
        ToolTipService.SetToolTip(button, tooltip); return button;
    }
    private Border ChatAvatar(bool secretary)
    {
        var glyph = (ReferenceVectorIcon)ReferenceIcon(secretary ? "sec" : "hash", secretary ? 16 : 14);
        glyph.Foreground = secretary ? Paint("7058B8", "A894E0") : Paint("5A5853", "B8B5AE");
        return new Border { Width = 28, Height = 28, CornerRadius = new CornerRadius(8), Background = secretary ? Paint("EFEBF8", "2E2A3D") : Paint("EFEEEA", "262624"), Child = glyph };
    }
    private Border Card(UIElement child, bool highlighted = false) => new()
    {
        Child = child, Padding = new Thickness(12), CornerRadius = new CornerRadius(10),
        Background = highlighted ? Paint("FBF3E2", "3A3020") : Paint("FFFFFF", "252523"),
        BorderBrush = highlighted ? Paint("E9D5AC", "66522C") : Line, BorderThickness = new Thickness(1)
    };
    private Border Badge(string text, bool accent = false) => new()
    {
        Child = new TextBlock { Text = text, FontSize = 11, Foreground = accent ? Accent : Paint("5A5853", "B8B5AE"), TextWrapping = TextWrapping.Wrap },
        Background = accent ? Paint("F9EEE8", "392B25") : Paint("F4F3F0", "2A2A28"), Padding = new Thickness(6, 2, 6, 2), CornerRadius = new CornerRadius(5), HorizontalAlignment = HorizontalAlignment.Left
    };
    private UIElement SmallAvatar(string url, string name, string state = "", int size = 26)
    {
        var box = new Grid { Width = size, Height = size };
        box.Children.Add(Avatar(url, name, size));
        if (state.Length > 0 && state != "idle") box.Children.Add(new Ellipse
        {
            Width = 7, Height = 7, HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Bottom,
            Stroke = Paint("F8F7F5", "191918"), StrokeThickness = 1.5,
            Fill = state switch { "working" or "running" or "active" => Paint("3E9B5E", "6CC287"), "waiting" => Paint("B7791F", "E2B15A"), "error" => Paint("C2412D", "EE8A78"), _ => Muted }
        });
        return box;
    }
    private void ThemeSurfaces()
    {
        root.Background = Paint("FFFFFF", "1F1F1E");
        sidebarSurface.Background = Paint("F8F7F5", "191918"); sidebarSurface.BorderBrush = Line;
        inspectorSurface.Background = Paint("F8F7F5", "191918"); inspectorSurface.BorderBrush = Line;
        composerSurface.Background = Paint("FFFFFF", "252523"); composerSurface.BorderBrush = Paint("DEDBD4", "3A3936");
        chatHead.BorderBrush = Line;
        menu.Background = Paint("F8F7F5", "191918"); toolbar.Background = Paint("F8F7F5", "191918"); navigationButtons.Background = Paint("F8F7F5", "191918");
        editor.Foreground = Ink; editor.Background = new SolidColorBrush(Colors.Transparent);
        root.Resources["AccentTextFillColorPrimaryBrush"] = Accent; root.Resources["AccentFillColorDefaultBrush"] = Accent;
        if (sendButton != null) { sendButton.Background = Ink; sendButton.Foreground = Paint("FFFFFF", "1F1F1E"); if (sendButton.Content is ReferenceVectorIcon glyph) glyph.Foreground = sendButton.Foreground; }
    }
    private void DrawPaneHeader()
    {
        paneHeader.Children.Clear(); paneHeader.ColumnDefinitions.Clear();
        paneHeader.Height = 44; paneHeader.Padding = new Thickness(8, 0, 6, 0); paneHeader.ColumnSpacing = 6;
        paneHeader.BorderThickness = new Thickness(0, 0, 0, 1); paneHeader.BorderBrush = Line;
        paneHeader.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        paneHeader.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        var tabs = new SelectorBar { Padding = new Thickness(0), VerticalAlignment = VerticalAlignment.Center };
        var destinations = new Dictionary<SelectorBarItem, string>();
        var choices = new List<(string, string, string)> { ("overview", "panel.overview", "org"), ("workspace", "panel.workspace", "work"), ("files", "common.file", "file") };
        if (threadId.Length > 0) choices.Add(("thread", "panel.thread", "thread"));
        foreach (var (id, key, iconName) in choices)
        {
            var selected = pane == id;
            var foreground = selected ? Ink : Paint("5A5853", "B8B5AE");
            var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 5, VerticalAlignment = VerticalAlignment.Center };
            var glyph = (ReferenceVectorIcon)ReferenceIcon(iconName, 15); glyph.Foreground = foreground; row.Children.Add(glyph);
            row.Children.Add(new TextBlock { Text = T(key), FontSize = 12.5, Foreground = foreground, FontWeight = selected ? FontWeights.SemiBold : FontWeights.Normal,
                LineHeight = 20, LineStackingStrategy = LineStackingStrategy.BlockLineHeight, TextWrapping = TextWrapping.NoWrap, VerticalAlignment = VerticalAlignment.Center });
            if (id == "thread")
            {
                var dismiss = IconButton("\uE711", "panel.close_thread", async () => { threadId = ""; await SetPane(previousPane); });
                dismiss.Content = ReferenceIcon("x", 12); dismiss.Width = dismiss.Height = 16; dismiss.MinHeight = 0;
                dismiss.Padding = new Thickness(0); dismiss.Margin = new Thickness(1, 0, -3, 0); dismiss.CornerRadius = new CornerRadius(4);
                row.Children.Add(dismiss);
            }
            var tab = new SelectorBarItem { Text = T(key), Tag = row, IsSelected = selected, Height = 28, Margin = new Thickness(0, 0, 2, 0),
                Style = (Style)Application.Current.Resources["RelicPaneTabStyle"] };
            destinations.Add(tab, id); tabs.Items.Add(tab);
        }
        tabs.SelectionChanged += async (_, _) => { if (tabs.SelectedItem != null && destinations.TryGetValue(tabs.SelectedItem, out var target) && pane != target) await Run(() => SetPane(target)); };
        paneHeader.Children.Add(new ScrollViewer { Content = tabs, HorizontalScrollMode = ScrollMode.Enabled, HorizontalScrollBarVisibility = ScrollBarVisibility.Hidden,
            VerticalScrollMode = ScrollMode.Disabled, VerticalScrollBarVisibility = ScrollBarVisibility.Disabled });
        var close = IconButton("\uE711", "panel.hide", TogglePanel, T("panel.hide_title"));
        AutomationProperties.SetName(close, T("panel.hide"));
        Grid.SetColumn(close, 1); close.VerticalAlignment = VerticalAlignment.Center; paneHeader.Children.Add(close);
    }
    private Grid TwoColumns(UIElement left, UIElement right)
    {
        var row = new Grid { ColumnSpacing = 8 };
        row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        row.Children.Add(left); Grid.SetColumn((FrameworkElement)right, 1); row.Children.Add(right); return row;
    }
    private void InlineActions(StackPanel content)
    {
        var buttons = content.Children.OfType<Button>().ToArray(); if (buttons.Length == 0) return;
        var row = new ActionRow(); foreach (var b in buttons) { content.Children.Remove(b); row.Children.Add(b); }
        content.Children.Add(row);
    }
    private void SegmentedPreference(StackPanel target, string title, string field, params (string, string)[] options)
    {
        var controls = new ActionRow { Spacing = 2 }; var toggles = new List<Microsoft.UI.Xaml.Controls.Primitives.ToggleButton>();
        foreach (var (value, label) in options)
        {
            var button = new Microsoft.UI.Xaml.Controls.Primitives.ToggleButton { Content = label, IsChecked = preferences.Text(field) == value, Tag = value, FontSize = 12, MinWidth = 0, MinHeight = 28, Padding = new Thickness(8, 4, 8, 4), CornerRadius = new CornerRadius(6) };
            button.Click += async (_, _) => await Run(async () => { foreach (var item in toggles) item.IsChecked = item == button; await SavePreferences(new JsonObject { [field] = value }); });
            controls.Children.Add(button); toggles.Add(button);
        }
        var heading = Heading(T(title), 13); heading.VerticalAlignment = VerticalAlignment.Center;
        target.Children.Add(new Border { Child = TwoColumns(heading, controls), Padding = new Thickness(0, 12, 0, 20), BorderThickness = new Thickness(0, 0, 0, 1), BorderBrush = Line });
    }
    private void AccentPreference(StackPanel target)
    {
        var controls = new ActionRow { Spacing = 8 };
        foreach (var (value, hex, label) in new[] { ("clay", "C8643F", "native.color_clay"), ("ink", "3A3936", "native.color_ink"), ("indigo", "5B61D6", "native.color_indigo"), ("blue", "2F6BD8", "native.color_blue"), ("rose", "C4456C", "native.color_rose"), ("amber", "B9821D", "native.color_amber") })
        {
            var b = Button("", () => SavePreferences(new JsonObject { ["accent"] = value })); b.Width = b.Height = 28; b.Padding = new Thickness(0); b.CornerRadius = new CornerRadius(14); b.Background = Paint(hex); b.BorderBrush = Ink; b.BorderThickness = new Thickness(preferences.Text("accent") == value ? 2 : 0);
            AutomationProperties.SetName(b, T("settings.accent") + " " + T(label)); ToolTipService.SetToolTip(b, T("settings.accent") + " " + T(label)); controls.Children.Add(b);
        }
        target.Children.Add(new Border { Child = TwoColumns(Stack(Heading(T("settings.accent"), 13), Quiet(T("settings.accent_hint"))), controls), Padding = new Thickness(0, 12, 0, 20), BorderThickness = new Thickness(0, 0, 0, 1), BorderBrush = Line });
    }
}

// Native panel for short action rows. Unlike a horizontal StackPanel it measures
// against the available width and moves actions to the next line when necessary.
public sealed class ActionRow : Panel
{
    public double Spacing { get; set; } = 6;
    protected override Windows.Foundation.Size MeasureOverride(Windows.Foundation.Size available)
    {
        double x = 0, y = 0, row = 0, widest = 0;
        foreach (var child in Children)
        {
            child.Measure(new(available.Width, double.PositiveInfinity)); var size = child.DesiredSize;
            if (x > 0 && x + size.Width > available.Width) { widest = Math.Max(widest, x); x = 0; y += row + Spacing; row = 0; }
            x += size.Width + Spacing; row = Math.Max(row, size.Height);
        }
        return new(Math.Min(available.Width, Math.Max(widest, Math.Max(0, x - Spacing))), y + row);
    }
    protected override Windows.Foundation.Size ArrangeOverride(Windows.Foundation.Size final)
    {
        double x = 0, y = 0, row = 0;
        foreach (var child in Children)
        {
            var size = child.DesiredSize;
            if (x > 0 && x + size.Width > final.Width) { x = 0; y += row + Spacing; row = 0; }
            child.Arrange(new(x, y, Math.Min(size.Width, final.Width), size.Height)); x += size.Width + Spacing; row = Math.Max(row, size.Height);
        }
        return final;
    }
}
