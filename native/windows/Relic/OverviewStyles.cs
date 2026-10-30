using Microsoft.UI;
using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Relic.Core;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    // The organization inspector uses the same blocks, inline rows and type
    // scale as renderOrgPane. These are native controls and real live data.
    private TextBlock OverviewText(string text, double size = 12.5, bool muted = false, ushort weight = 400, double lineHeight = 0)
        => new() { Text = text, FontFamily = new FontFamily(FontFamilies.UI), FontSize = size,
            FontWeight = new Windows.UI.Text.FontWeight { Weight = weight }, Foreground = muted ? Muted : Ink,
            TextWrapping = TextWrapping.Wrap, LineHeight = lineHeight > 0 ? lineHeight : size * 1.6,
            LineStackingStrategy = LineStackingStrategy.BlockLineHeight, IsTextSelectionEnabled = true };

    private StackPanel OverviewBlock()
    {
        var content = new StackPanel { Spacing = 8 };
        detail.Children.Add(new Border { Padding = new Thickness(16, 14, 16, 14), BorderBrush = Line,
            BorderThickness = new Thickness(0, 0, 0, 1), Child = content });
        return content;
    }

    private Grid OverviewHeading(UIElement label, UIElement? action = null)
    {
        var row = new Grid { ColumnSpacing = 8 };
        row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        ((FrameworkElement)label).VerticalAlignment = VerticalAlignment.Center; row.Children.Add(label);
        if (action is FrameworkElement control) { control.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(control, 1); row.Children.Add(control); }
        return row;
    }

    private Button OverviewLink(string text, Func<Task> action, string icon = "", bool iconFirst = false)
    {
        var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4, VerticalAlignment = VerticalAlignment.Center };
        var label = OverviewText(text, 12, true); label.TextWrapping = TextWrapping.NoWrap; label.IsTextSelectionEnabled = false;
        if (icon.Length > 0 && iconFirst) row.Children.Add(ReferenceIcon(icon, icon == "plus" ? 13 : 12));
        row.Children.Add(label);
        if (icon.Length > 0 && !iconFirst) row.Children.Add(ReferenceIcon(icon, 12));
        var button = QuietButton("", action); button.Content = row; button.Padding = new Thickness(0); button.MinHeight = 0;
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(button, label.Text);
        button.Foreground = Muted; button.CornerRadius = new CornerRadius(0); return button;
    }

    private OverviewChipView OverviewChip(string text, string kind = "")
    {
        var foreground = kind switch { "ok" => Paint("3E9B5E", "6CC287"), "warn" => Paint("B7791F", "E2B15A"), "bad" => Paint("C2412D", "EE8A78"), "sec" => Paint("7058B8", "A894E0"), _ => Paint("5A5853", "B8B5AE") };
        var background = kind switch { "ok" => OverviewAlpha(foreground, .14), "warn" => Paint("FBF3E2", "3A3020"), "bad" => Paint("FBEAE6", "3D2622"), "sec" => Paint("EFEBF8", "2E2A3D"), _ => Paint("EFEEEA", "262624") };
        var label = OverviewText(text, 11.5, lineHeight: 20); label.TextWrapping = TextWrapping.NoWrap; label.Foreground = foreground;
        return new OverviewChipView { Content = label, Foreground = foreground, FontSize = 11.5, Background = background, Padding = new Thickness(8, 1, 8, 1), CornerRadius = new CornerRadius(10), VerticalAlignment = VerticalAlignment.Center };
    }

    private static SolidColorBrush OverviewAlpha(SolidColorBrush brush, double alpha)
    {
        return new SolidColorBrush(brush.Color) { Opacity = alpha };
    }

    private OverviewBadgeView OverviewCount(int count)
    {
        var label = OverviewText(count.ToString(), 11, weight: 700, lineHeight: 18); label.Foreground = Paint("FFFFFF");
        label.HorizontalAlignment = HorizontalAlignment.Center;
        return new OverviewBadgeView { Content = label, Foreground = Paint("FFFFFF"), FontSize = 11, FontWeight = FontWeights.Bold, Background = Accent, MinWidth = 18, Height = 18, Padding = new Thickness(5, 0, 5, 0), CornerRadius = new CornerRadius(9) };
    }

    private UIElement OverviewAvatar(string name, bool state = false, int size = 20)
    {
        var member = snap.Rows("members").FirstOrDefault(m => m.Text("name") == name);
        var avatar = Avatar(member.Text("avatar"), Display(name), size);
        if (avatar is Border face)
        {
            face.CornerRadius = new CornerRadius(size == 20 ? 6 : 8);
            if (face.Child is TextBlock initial) { initial.FontSize = size == 20 ? 10 : 12; initial.FontWeight = new Windows.UI.Text.FontWeight { Weight = 650 }; }
        }
        var frame = new Grid { Width = size, Height = size }; frame.Children.Add(avatar);
        if (state && member.Text("state") is not ("" or "idle"))
        {
            var status = member.Text("state");
            var color = status switch { "working" or "running" => Paint("3E9B5E", "6CC287"), "waiting" or "starting" => Paint("B7791F", "E2B15A"), "error" => Paint("C2412D", "EE8A78"), "active" => Paint("75A782", "669572"), _ => Paint("B8B5AF", "5F5D58") };
            var dot = new Border { Width = 10, Height = 10, CornerRadius = new CornerRadius(5), BorderThickness = new Thickness(2), BorderBrush = Paint("FFFFFF", "1F1F1E"),
                Background = status == "vacant" ? new SolidColorBrush(Colors.Transparent) : color, HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Bottom,
                Margin = new Thickness(0, 0, -2, -2) };
            if (status == "vacant") dot.Child = new Ellipse { Stroke = color, StrokeThickness = 1.5 };
            frame.Children.Add(dot);
        }
        return frame;
    }

    private UIElement OverviewOrgBadge(JsonNode organization, bool subgroup)
    {
        uint hash = 7; foreach (var character in organization.Text("id").EnumerateRunes()) hash = unchecked(hash * 31 + (uint)character.Value);
        var hue = new[] { 18, 30, 42, 205, 222, 248, 272, 300, 330, 350, 190, 12 }[hash % 12];
        SolidColorBrush Hsl(double saturation, double lightness)
        {
            var chroma = (1 - Math.Abs(2 * lightness - 1)) * saturation; var x = chroma * (1 - Math.Abs(hue / 60d % 2 - 1)); var m = lightness - chroma / 2;
            var (r, g, b) = hue switch { < 60 => (chroma, x, 0d), < 120 => (x, chroma, 0d), < 180 => (0d, chroma, x), < 240 => (0d, x, chroma), < 300 => (x, 0d, chroma), _ => (chroma, 0d, x) };
            return new SolidColorBrush(Windows.UI.Color.FromArgb(255, (byte)Math.Round((r + m) * 255), (byte)Math.Round((g + m) * 255), (byte)Math.Round((b + m) * 255)));
        }
        var foreground = Hsl(.38, .34);
        var initial = OverviewText(organization.Text("name").Length > 0 ? System.Globalization.StringInfo.GetNextTextElement(organization.Text("name")).ToUpperInvariant() : "R", 11, weight: 700);
        initial.Foreground = foreground; initial.HorizontalAlignment = HorizontalAlignment.Center; initial.VerticalAlignment = VerticalAlignment.Center;
        var surface = new Border { Background = Hsl(.4, .9), CornerRadius = new CornerRadius(6), Child = initial };
        var outline = subgroup || organization.Text("kind") == "subgroup" ? new Rectangle { Stroke = foreground, StrokeThickness = 1.5, StrokeDashArray = new DoubleCollection { 2, 2 }, RadiusX = 6, RadiusY = 6 } : null;
        var cabinet = organization.Flag("cabinet") ? new Border { BorderBrush = Paint("7058B8", "A894E0"), BorderThickness = new Thickness(1.5), CornerRadius = new CornerRadius(9.5), Margin = new Thickness(-3.5), Child = new Border { BorderBrush = Paint("FFFFFF", "252523"), BorderThickness = new Thickness(2), CornerRadius = new CornerRadius(8) } } : null;
        return new NativeOrganizationAvatarPaint(surface, initial, outline, cabinet);
    }

    private Grid OverviewRowContent(UIElement? first, string title, string note, UIElement? last = null, bool struck = false, bool noteWrap = false)
    {
        var row = new Grid { ColumnSpacing = 9 };
        row.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        row.Children.Add(first ?? new Grid());
        var heading = OverviewText(title, 13, weight: 600); heading.TextWrapping = TextWrapping.NoWrap; heading.TextTrimming = TextTrimming.CharacterEllipsis;
        if (struck) heading.TextDecorations = Windows.UI.Text.TextDecorations.Strikethrough;
        var subtitle = OverviewText(note, 12, true); subtitle.TextWrapping = noteWrap ? TextWrapping.Wrap : TextWrapping.NoWrap; subtitle.TextTrimming = TextTrimming.CharacterEllipsis;
        var labels = new StackPanel(); labels.Children.Add(heading); labels.Children.Add(subtitle); labels.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(labels, 1); row.Children.Add(labels);
        var tail = last ?? new Grid(); Grid.SetColumn((FrameworkElement)tail, 2); row.Children.Add(tail);
        return row;
    }

    private Button OverviewRow(UIElement? first, string title, string note, Func<Task> action, UIElement? last = null, bool ended = false, bool struck = false)
    {
        var row = OverviewRowContent(first, title, note, last, struck);
        var button = QuietButton("", action); button.Content = row; button.MinHeight = 0; button.Padding = new Thickness(8, 6, 8, 6);
        button.Margin = new Thickness(-8, 0, -8, 0); button.CornerRadius = new CornerRadius(8); button.HorizontalAlignment = HorizontalAlignment.Stretch; button.HorizontalContentAlignment = HorizontalAlignment.Stretch;
        if (ended) button.Opacity = .55;
        return button;
    }

    private FrameworkElement OverviewSwitch(string label, bool enabled, bool value, Func<bool, Task> action)
    {
        var check = new NativeOverviewToggle(enabled, value, () => Accent, () => Paint("DEDBD4", "3A3936"));
        AutomationProperties.SetName(check, label);
        async void Changed(object sender, RoutedEventArgs args)
        {
            await Run(() => action(check.IsChecked == true));
        }
        check.Checked += Changed; check.Unchecked += Changed;
        var text = OverviewText(label); text.Foreground = Paint("5A5853", "B8B5AE"); text.VerticalAlignment = VerticalAlignment.Center;
        var row = new Grid { ColumnSpacing = 8 }; row.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        row.Children.Add(check); Grid.SetColumn(text, 1); row.Children.Add(text); text.Tapped += (_, _) => { if (check.IsEnabled) check.IsChecked = check.IsChecked != true; }; return row;
    }

    private Button OverviewAction(string label, Func<Task> action, bool primary = false)
    {
        var button = Button("", action); var text = OverviewText(label, 12, weight: 600); text.TextWrapping = TextWrapping.NoWrap; text.IsTextSelectionEnabled = false;
        button.Content = text; button.Height = 26; button.MinHeight = 0; button.Padding = new Thickness(9, 0, 9, 0); button.CornerRadius = new CornerRadius(7);
        button.BorderBrush = primary ? Ink : Paint("DEDBD4", "3A3936"); button.Background = primary ? Ink : Paint("FFFFFF", "252523");
        text.Foreground = primary ? Paint("FFFFFF", "1F1F1E") : Ink; return button;
    }

    private string OverviewRoleName(string name, string title) => Display(name) == title ? name : Display(name);
}

// Informational native tokens have a single label and no independent action.
// Keeping their production types explicit also lets accessibility inspection
// distinguish a status chip from a section card without guessing from wording.
public abstract class OverviewTokenView : ContentControl
{
    protected OverviewTokenView()
    {
        IsTabStop = false; MinWidth = MinHeight = 0; FontFamily = new FontFamily(FontFamilies.UI);
        Template = (ControlTemplate)XamlReader.Load("<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' TargetType='ContentControl'><ContentPresenter Content='{TemplateBinding Content}' Background='{TemplateBinding Background}' BorderBrush='{TemplateBinding BorderBrush}' BorderThickness='{TemplateBinding BorderThickness}' CornerRadius='{TemplateBinding CornerRadius}' Padding='{TemplateBinding Padding}' Foreground='{TemplateBinding Foreground}' FontFamily='{TemplateBinding FontFamily}' FontSize='{TemplateBinding FontSize}' FontWeight='{TemplateBinding FontWeight}'/></ControlTemplate>");
    }
}

public sealed class OverviewChipView : OverviewTokenView { }
public sealed class OverviewBadgeView : OverviewTokenView { }
