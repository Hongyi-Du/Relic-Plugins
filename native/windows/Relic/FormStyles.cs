using Microsoft.UI;
using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Documents;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Relic.Core;
using Windows.System;

namespace Relic;

public sealed partial class MainWindow
{
    private TextBlock FormLabelText(string value)
    {
        var label = OverviewText(value, 12.5, lineHeight: 20); label.Foreground = Paint("5A5853", "B8B5AE"); return label;
    }
    private StackPanel FormLabel(string key, UIElement input)
    {
        var label = new StackPanel { Spacing = 5 }; label.Children.Add(FormLabelText(T(key))); label.Children.Add(input); return label;
    }
    private TextBox FormInput(string value, string placeholder, string automationId = "", bool multiline = false, bool mono = false)
    {
        var input = SettingsInput(value, placeholder, multiline: multiline, mono: mono, fontSize: mono ? 11.5 : 12.5);
        if (multiline) input.Height = mono ? 71.2 : 76;
        if (automationId.Length > 0) AutomationProperties.SetAutomationId(input, automationId);
        return input;
    }
    private ComboBox FormSelect(IEnumerable<(string Id, string Label)> options, string selected = "")
    {
        var select = new ComboBox { HorizontalAlignment = HorizontalAlignment.Stretch, MinWidth = 0, MinHeight = 0, Height = 34,
            FontSize = 12.5, FontFamily = new FontFamily(FontFamilies.UI), Foreground = Ink, Background = Paint("FFFFFF", "1F1F1E"),
            BorderBrush = Paint("DEDBD4", "3A3936"), BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(9), Padding = new Thickness(10, 7, 10, 7) };
        foreach (var (id, label) in options) select.Items.Add(new ComboBoxItem { Tag = id, Content = label, FontSize = 12.5 });
        SetChoice(select, selected); return select;
    }
    private Button FormAction(string label, Func<Task> action, bool primary = false)
    {
        var button = OverviewAction(label, action, primary); button.Height = 32; button.Padding = new Thickness(13, 0, 13, 0); button.CornerRadius = new CornerRadius(9);
        var text = (TextBlock)button.Content; text.FontSize = 13; text.FontWeight = primary ? FontWeights.SemiBold : FontWeights.Normal; text.LineHeight = 20.8;
        return button;
    }
    private StackPanel FormSwitch(string key, bool value, Action<bool> changed)
    {
        var toggle = (ToggleButton)SettingsToggle(T(key), value, on => { changed(on); return Task.CompletedTask; }); toggle.HorizontalAlignment = HorizontalAlignment.Left;
        var label = FormLabelText(T(key)); label.Tapped += (_, _) => toggle.IsChecked = toggle.IsChecked != true;
        var row = new StackPanel { Spacing = 5 }; row.Children.Add(toggle); row.Children.Add(label); return row;
    }
    private Border FormRadio(string group, string label, UIElement content, bool selected, bool enabled, Action choose)
    {
        var ring = new Ellipse { Width = 13, Height = 13, Stroke = selected ? Accent : Paint("8F8C86", "8A877F"), StrokeThickness = 1, Fill = Paint("FFFFFF", "1F1F1E") };
        var dot = new Ellipse { Width = 7, Height = 7, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center, Fill = Accent, Visibility = selected ? Visibility.Visible : Visibility.Collapsed };
        var mark = new Grid { Width = 13, Height = 13 }; mark.Children.Add(ring); mark.Children.Add(dot);
        var radio = new RadioButton { GroupName = group, IsChecked = selected, IsEnabled = enabled, Content = mark, Width = 13, Height = 13, MinWidth = 0, MinHeight = 0,
            Padding = new Thickness(0), Margin = new Thickness(5, 3, 3, 0), VerticalAlignment = VerticalAlignment.Center,
            Template = (ControlTemplate)XamlReader.Load("<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' TargetType='RadioButton'><ContentPresenter Content='{TemplateBinding Content}' Padding='0'/></ControlTemplate>") };
        AutomationProperties.SetName(radio, label);
        var row = new Grid { ColumnSpacing = 5 }; row.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        row.Children.Add(radio); Grid.SetColumn((FrameworkElement)content, 1); row.Children.Add(content);
        var frame = new Border { Child = row, BorderBrush = Paint("DEDBD4", "3A3936"), BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(10), Padding = new Thickness(11, 9, 11, 9), Opacity = enabled ? 1 : .5 };
        radio.Checked += (_, _) => { ring.Stroke = Accent; dot.Visibility = Visibility.Visible; choose(); };
        radio.Unchecked += (_, _) => { ring.Stroke = Paint("8F8C86", "8A877F"); dot.Visibility = Visibility.Collapsed; };
        frame.Tapped += (_, _) => { if (enabled) radio.IsChecked = true; };
        frame.PointerEntered += (_, _) => { if (enabled) frame.Background = Paint("F8F7F5", "191918"); };
        frame.PointerExited += (_, _) => frame.Background = new SolidColorBrush(Colors.Transparent);
        return frame;
    }
    private async Task FormDialog(ContentDialog dialog, StackPanel body, double width, Control? focus = null)
    {
        body.Width = Math.Min(width, Math.Max(0, root.ActualWidth - 32)); body.Padding = new Thickness(22); body.Spacing = 14;
        var scroll = Scroll(body); scroll.MaxHeight = Math.Max(0, root.ActualHeight - 60); dialog.Content = scroll;
        dialog.Opened += (_, _) =>
        {
            if (DialogPart<ContentPresenter>(dialog, "Content") is { } presenter) { presenter.Margin = new Thickness(0); presenter.Padding = new Thickness(0); }
            if (DialogPart<Border>(dialog, "BackgroundElement") is { } background) background.Padding = new Thickness(0);
            if (DialogPart<ScrollViewer>(dialog, "ContentScrollViewer") is { } outer) { outer.Padding = new Thickness(0); outer.VerticalScrollBarVisibility = ScrollBarVisibility.Disabled; }
            if (DialogPart<Grid>(dialog, "CommandSpace") is { } commands) commands.Visibility = Visibility.Collapsed;
            focus?.Focus(FocusState.Programmatic);
        };
        void Resize(object sender, SizeChangedEventArgs args) { body.Width = Math.Min(width, Math.Max(0, args.NewSize.Width - 32)); scroll.MaxHeight = Math.Max(0, args.NewSize.Height - 60); }
        root.SizeChanged += Resize;
        try { await Dialog(dialog); } finally { root.SizeChanged -= Resize; }
    }
    private void FormSuggestions(TextBox input, Func<IEnumerable<(string Value, string Label)>> options)
    {
        var list = new ListView { IsItemClickEnabled = true, SelectionMode = ListViewSelectionMode.Single, MaxHeight = 240, MinHeight = 0, Padding = new Thickness(0) };
        var border = new Border { Child = list, Padding = new Thickness(0), Background = Paint("FFFFFF", "252523"), BorderBrush = Paint("8F8C86", "8A877F"), BorderThickness = new Thickness(1) };
        var popup = new Popup { XamlRoot = root.XamlRoot, Child = border, IsLightDismissEnabled = true };
        var picking = false;
        void Accept()
        {
            if ((list.SelectedItem as ListViewItem)?.Tag is not string value) return;
            picking = true; input.Text = value; input.SelectionStart = value.Length; popup.IsOpen = false; input.Focus(FocusState.Programmatic); picking = false;
        }
        void Open(bool last = false)
        {
            list.Items.Clear();
            foreach (var (value, label) in options().Where(option => input.Text.Length == 0 || (option.Value + " " + option.Label).Contains(input.Text, StringComparison.OrdinalIgnoreCase)))
            {
                var lines = new StackPanel(); var primary = OverviewText(value, 13, lineHeight: 20.8); primary.TextWrapping = TextWrapping.NoWrap; lines.Children.Add(primary);
                if (label.Length > 0 && label != value) { var secondary = OverviewText(label, 12, true, lineHeight: 19.2); secondary.TextWrapping = TextWrapping.NoWrap; lines.Children.Add(secondary); }
                list.Items.Add(new ListViewItem { Tag = value, Content = lines, Padding = new Thickness(10, 4, 10, 4), MinHeight = 0, HorizontalContentAlignment = HorizontalAlignment.Stretch });
            }
            if (list.Items.Count == 0) { popup.IsOpen = false; return; }
            var point = input.TransformToVisual(root).TransformPoint(new(0, input.ActualHeight)); border.Width = input.ActualWidth;
            popup.HorizontalOffset = point.X; popup.VerticalOffset = point.Y; popup.IsOpen = true; list.SelectedIndex = last ? list.Items.Count - 1 : 0;
        }
        input.KeyDown += (_, args) =>
        {
            if (args.Key is VirtualKey.Down or VirtualKey.Up)
            {
                args.Handled = true;
                if (!popup.IsOpen) Open(args.Key == VirtualKey.Up);
                else list.SelectedIndex = Math.Clamp(list.SelectedIndex + (args.Key == VirtualKey.Down ? 1 : -1), 0, list.Items.Count - 1);
            }
            else if (popup.IsOpen && args.Key == VirtualKey.Enter) { args.Handled = true; Accept(); }
            else if (popup.IsOpen && args.Key == VirtualKey.Escape) { args.Handled = true; popup.IsOpen = false; }
        };
        list.ItemClick += (_, args) => { list.SelectedItem = args.ClickedItem; Accept(); };
        list.KeyDown += (_, args) => { if (args.Key == VirtualKey.Enter) { args.Handled = true; Accept(); } else if (args.Key == VirtualKey.Escape) { args.Handled = true; popup.IsOpen = false; input.Focus(FocusState.Programmatic); } };
        input.TextChanged += (_, _) => { if (!picking && input.FocusState != FocusState.Unfocused) Open(); };
        input.Unloaded += (_, _) => popup.IsOpen = false;
    }
}
