using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;
using Windows.Foundation;

namespace Relic;

public sealed partial class MainWindow
{
    private Border DetailsTabs(IEnumerable<(string Id, string Label)> choices, string selected, Func<string, Task> change, bool top = false)
    {
        var tabs = new SelectorBar { Padding = new Thickness(0), HorizontalAlignment = HorizontalAlignment.Left };
        var values = new Dictionary<SelectorBarItem, string>();
        foreach (var (id, title) in choices)
        {
            var label = OverviewText(title, top ? 12.5 : 12, weight: (ushort)(top && id == selected ? 600 : 400));
            label.IsTextSelectionEnabled = false; label.TextWrapping = TextWrapping.NoWrap; label.Foreground = id == selected ? Ink : Paint("5A5853", "B8B5AE");
            var item = new SelectorBarItem { Text = title, Tag = label, IsSelected = id == selected, MinWidth = 0, MinHeight = 0,
                Padding = top ? new Thickness(12, 4, 12, 4) : new Thickness(9, 2, 9, 2), Margin = new Thickness(0, 0, 2, 0), CornerRadius = new CornerRadius(top ? 7 : 6),
                Background = id == selected ? Paint("FFFFFF", "252523") : new SolidColorBrush(Microsoft.UI.Colors.Transparent),
                Template = (ControlTemplate)XamlReader.Load("<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' xmlns:x='http://schemas.microsoft.com/winfx/2006/xaml' TargetType='SelectorBarItem'><Grid x:Name='PART_ContainerRoot' Background='{TemplateBinding Background}' Padding='{TemplateBinding Padding}' CornerRadius='{TemplateBinding CornerRadius}'><ContentPresenter Content='{TemplateBinding Tag}'/></Grid></ControlTemplate>") };
            values.Add(item, id); tabs.Items.Add(item);
        }
        if (tabs.Items.Count > 0) tabs.Items[^1].Margin = new Thickness(0);
        tabs.SelectionChanged += async (_, _) =>
        {
            if (tabs.SelectedItem == null || !values.TryGetValue(tabs.SelectedItem, out var value)) return;
            foreach (var (item, id) in values)
            {
                item.Background = id == value ? Paint("FFFFFF", "252523") : new SolidColorBrush(Microsoft.UI.Colors.Transparent);
                if (item.Tag is TextBlock label) { label.Foreground = id == value ? Ink : Paint("5A5853", "B8B5AE"); label.FontWeight = new Windows.UI.Text.FontWeight { Weight = (ushort)(top && id == value ? 600 : 400) }; }
            }
            await Run(() => change(value));
        };
        return new Border { Child = tabs, Padding = new Thickness(2), CornerRadius = new CornerRadius(top ? 9 : 8), Background = Paint("EFEEEA", "262624"), HorizontalAlignment = HorizontalAlignment.Left };
    }

    private Expander DetailsDisclosure(UIElement header, UIElement content, bool expanded = false)
    {
        // Keep the real WinUI Expander parts and its two-way header binding.
        // Its ExpandCollapse provider and the CI capture therefore operate on
        // the same production control as mouse and keyboard interaction.
        var template = (ControlTemplate)XamlReader.Load("""
            <ControlTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" TargetType="Expander">
              <Grid>
                <Grid.RowDefinitions><RowDefinition x:Name="Row0" Height="Auto"/><RowDefinition x:Name="Row1" Height="Auto"/></Grid.RowDefinitions>
                <VisualStateManager.VisualStateGroups>
                  <VisualStateGroup x:Name="ExpandStates">
                    <VisualState x:Name="ExpandDown"><VisualState.Setters><Setter Target="ExpanderContent.Visibility" Value="Visible"/></VisualState.Setters></VisualState>
                    <VisualState x:Name="ExpandUp"><VisualState.Setters><Setter Target="ExpanderContent.Visibility" Value="Visible"/></VisualState.Setters></VisualState>
                    <VisualState x:Name="CollapseUp"><VisualState.Setters><Setter Target="ExpanderContent.Visibility" Value="Collapsed"/></VisualState.Setters></VisualState>
                    <VisualState x:Name="CollapseDown"><VisualState.Setters><Setter Target="ExpanderContent.Visibility" Value="Collapsed"/></VisualState.Setters></VisualState>
                  </VisualStateGroup>
                  <VisualStateGroup x:Name="ExpandDirectionStates"><VisualState x:Name="Down"/><VisualState x:Name="Up"/></VisualStateGroup>
                </VisualStateManager.VisualStateGroups>
                <ToggleButton x:Name="ExpanderHeader" AutomationProperties.AutomationId="ExpanderToggleButton" Content="{TemplateBinding Header}" IsChecked="{Binding IsExpanded, Mode=TwoWay, RelativeSource={RelativeSource TemplatedParent}}" Padding="0" BorderThickness="0" MinWidth="0" MinHeight="0" HorizontalAlignment="Stretch" HorizontalContentAlignment="Stretch">
                  <ToggleButton.Template><ControlTemplate TargetType="ToggleButton"><ContentPresenter Content="{TemplateBinding Content}" Background="Transparent" HorizontalContentAlignment="Stretch"/></ControlTemplate></ToggleButton.Template>
                </ToggleButton>
                <Border x:Name="ExpanderContentClip" Grid.Row="1"><Border x:Name="ExpanderContent" Visibility="Collapsed"><Border.RenderTransform><CompositeTransform/></Border.RenderTransform><ContentPresenter Content="{TemplateBinding Content}" HorizontalContentAlignment="Stretch"/></Border></Border>
              </Grid>
            </ControlTemplate>
            """);
        return new Expander { Header = header, Content = content, Template = template, IsExpanded = expanded, MinHeight = 0, MinWidth = 0,
            Padding = new Thickness(0), BorderThickness = new Thickness(0), Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent), HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch };
    }

    private Border DetailsCard(UIElement content) => new() { Child = content, Background = Paint("FFFFFF", "252523"), BorderBrush = Line, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(12), Margin = new Thickness(0, 0, 0, 8) };
    private TextBlock DetailsEmpty(string label) => OverviewText(label, 12.5, true);
    private Border DetailsCode(string source, bool pre = false)
    {
        var text = OverviewText(source, 12.5, lineHeight: 20.625); text.FontFamily = new FontFamily("Cascadia Code");
        return new Border { Child = text, Padding = new Thickness(14), Background = Paint("F6F5F2", "232321"), BorderBrush = Line, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(10), Margin = pre ? new Thickness(0, 12.5, 0, 12.5) : new Thickness(0) };
    }
    private TextBlock DetailsLabeled(string label, string value)
    {
        var text = OverviewText("", 13); text.Inlines.Add(new Microsoft.UI.Xaml.Documents.Run { Text = label, Foreground = Muted }); text.Inlines.Add(new Microsoft.UI.Xaml.Documents.Run { Text = value }); return text;
    }
    private ListViewItem DetailsListRow(string id, UIElement avatar, string title, string subtitle, bool selected = false)
    {
        var row = new Grid { ColumnSpacing = 9 }; row.ColumnDefinitions.Add(new() { Width = new GridLength(30) }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        ((FrameworkElement)avatar).VerticalAlignment = VerticalAlignment.Center; row.Children.Add(avatar);
        var labels = new StackPanel(); var name = OverviewText(title, 13.3, weight: 550, lineHeight: 17.955); name.TextWrapping = TextWrapping.NoWrap; name.TextTrimming = TextTrimming.CharacterEllipsis; labels.Children.Add(name);
        var note = OverviewText(subtitle, 12, true, lineHeight: 16.2); note.TextWrapping = TextWrapping.NoWrap; note.TextTrimming = TextTrimming.CharacterEllipsis; labels.Children.Add(note); Grid.SetColumn(labels, 1); row.Children.Add(labels);
        return new ListViewItem { Tag = id, Content = row, Padding = new Thickness(8, 6, 8, 6), MinHeight = 0, MinWidth = 0, CornerRadius = new CornerRadius(8), HorizontalContentAlignment = HorizontalAlignment.Stretch,
            Background = selected ? Paint("E7E5DF", "2F2E2B") : new SolidColorBrush(Microsoft.UI.Colors.Transparent),
            Template = (ControlTemplate)XamlReader.Load("<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' TargetType='ListViewItem'><ContentPresenter Content='{TemplateBinding Content}' Padding='{TemplateBinding Padding}' Background='{TemplateBinding Background}' CornerRadius='{TemplateBinding CornerRadius}' HorizontalContentAlignment='Stretch'/></ControlTemplate>") };
    }
}

// The reference's filter row wraps at its real available width and centers
// controls of different heights on each line (27.2px segments, 30px input).
public sealed class DetailsFilterRow : Panel
{
    public double Spacing { get; set; } = 8;
    protected override Size MeasureOverride(Size availableSize)
    {
        double x = 0, y = 0, height = 0, width = 0;
        foreach (var child in Children)
        {
            child.Measure(new(availableSize.Width, double.PositiveInfinity)); var size = child.DesiredSize;
            if (x > 0 && x + Spacing + size.Width > availableSize.Width) { width = Math.Max(width, x); x = 0; y += height + Spacing; height = 0; }
            x += (x > 0 ? Spacing : 0) + size.Width; height = Math.Max(height, size.Height);
        }
        return new(Math.Min(availableSize.Width, Math.Max(width, x)), y + height);
    }
    protected override Size ArrangeOverride(Size finalSize)
    {
        var row = new List<UIElement>(); double x = 0, y = 0, height = 0;
        void Flush()
        {
            double left = 0;
            foreach (var child in row) { var size = child.DesiredSize; child.Arrange(new(left, y + (height - size.Height) / 2, Math.Min(size.Width, finalSize.Width), size.Height)); left += size.Width + Spacing; }
            row.Clear(); y += height + Spacing; x = height = 0;
        }
        foreach (var child in Children)
        {
            var size = child.DesiredSize; if (x > 0 && x + Spacing + size.Width > finalSize.Width) Flush();
            x += (x > 0 ? Spacing : 0) + size.Width; height = Math.Max(height, size.Height); row.Add(child);
        }
        if (row.Count > 0) Flush(); return finalSize;
    }
}
