using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;

namespace Relic;

public sealed partial class MainWindow
{
    private void StyleNativeMenuBar()
    {
        // app.css .ab-menus has a single 4px leading margin, not the WinUI
        // default's 4px margin on both sides of every MenuBarItem.
        menu.MinHeight = 0; menu.Height = 28; menu.VerticalAlignment = VerticalAlignment.Center;
        menu.Margin = new Thickness(4, 0, 0, 1); menu.UseLayoutRounding = false;
    }

    private MenuBarItem NativeMenuGroup(string title)
    {
        var group = new MenuBarItem { Title = title, Height = 28, MinHeight = 0, MinWidth = 0, Margin = new Thickness(0),
            Padding = new Thickness(9, 0, 9, 0), FontSize = 13, FontFamily = new FontFamily("Segoe UI Variable Text"),
            FontWeight = Microsoft.UI.Text.FontWeights.Normal, Foreground = Paint("5A5853", "B8B5AE"),
            Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent), BorderThickness = new Thickness(0),
            CornerRadius = new CornerRadius(7), UseLayoutRounding = false };
        group.Resources["NativeMenuActiveBackground"] = Paint("EFEEEA", "262624");
        group.Resources["NativeMenuActiveForeground"] = Ink;
        // ContentButton is required by MenuBarItem: WinUI attaches its native
        // MenuBarItemFlyout, hover switching and keyboard handling to this part.
        group.Template = (ControlTemplate)XamlReader.Load("""
            <ControlTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" TargetType="MenuBarItem">
              <Grid x:Name="ContentRoot" Background="{TemplateBinding Background}" CornerRadius="{TemplateBinding CornerRadius}">
                <VisualStateManager.VisualStateGroups>
                  <VisualStateGroup x:Name="CommonStates">
                    <VisualState x:Name="Normal"/>
                    <VisualState x:Name="PointerOver"><VisualState.Setters><Setter Target="ContentRoot.Background" Value="{ThemeResource NativeMenuActiveBackground}"/><Setter Target="ContentButton.Foreground" Value="{ThemeResource NativeMenuActiveForeground}"/></VisualState.Setters></VisualState>
                    <VisualState x:Name="Pressed"><VisualState.Setters><Setter Target="ContentRoot.Background" Value="{ThemeResource NativeMenuActiveBackground}"/><Setter Target="ContentButton.Foreground" Value="{ThemeResource NativeMenuActiveForeground}"/></VisualState.Setters></VisualState>
                    <VisualState x:Name="Selected"><VisualState.Setters><Setter Target="ContentRoot.Background" Value="{ThemeResource NativeMenuActiveBackground}"/><Setter Target="ContentButton.Foreground" Value="{ThemeResource NativeMenuActiveForeground}"/></VisualState.Setters></VisualState>
                  </VisualStateGroup>
                </VisualStateManager.VisualStateGroups>
                <Button x:Name="ContentButton" Content="{TemplateBinding Title}" Padding="{TemplateBinding Padding}" FontFamily="{TemplateBinding FontFamily}" FontSize="{TemplateBinding FontSize}" FontWeight="{TemplateBinding FontWeight}" Foreground="{TemplateBinding Foreground}" BorderThickness="0" MinHeight="0" MinWidth="0" IsTabStop="False" AutomationProperties.AccessibilityView="Raw" VerticalAlignment="Stretch">
                  <Button.Template><ControlTemplate TargetType="Button"><ContentPresenter Content="{TemplateBinding Content}" Padding="{TemplateBinding Padding}" FontFamily="{TemplateBinding FontFamily}" FontSize="{TemplateBinding FontSize}" FontWeight="{TemplateBinding FontWeight}" Foreground="{TemplateBinding Foreground}" VerticalContentAlignment="Center" HorizontalContentAlignment="Center"/></ControlTemplate></Button.Template>
                </Button>
              </Grid>
            </ControlTemplate>
            """);
        group.Loaded += (_, _) =>
        {
            if (DialogPart<Button>(group, "ContentButton")?.ContextFlyout is not MenuFlyout flyout) return;
            void PresenterStyle()
            {
                var style = new Style(typeof(MenuFlyoutPresenter));
                style.Setters.Add(new Setter(Control.BackgroundProperty, Paint("FFFFFF", "252523")));
                style.Setters.Add(new Setter(Control.ForegroundProperty, Ink));
                style.Setters.Add(new Setter(Control.BorderBrushProperty, Paint("DEDBD4", "3A3936")));
                style.Setters.Add(new Setter(Control.BorderThicknessProperty, new Thickness(1)));
                style.Setters.Add(new Setter(Control.CornerRadiusProperty, new CornerRadius(12)));
                style.Setters.Add(new Setter(Control.PaddingProperty, new Thickness(6)));
                style.Setters.Add(new Setter(FrameworkElement.MinWidthProperty, 250d));
                style.Setters.Add(new Setter(FrameworkElement.MaxHeightProperty, root.ActualHeight * .6));
                style.Setters.Add(new Setter(UIElement.UseLayoutRoundingProperty, false));
                flyout.MenuFlyoutPresenterStyle = style;
            }
            PresenterStyle();
            flyout.Opening += (_, _) => PresenterStyle();
            flyout.Opened += (_, _) =>
            {
                // Match openAppMenu's anchor-bottom + 4px, retaining the real
                // native popup and its light-dismiss/keyboard lifetime.
                var first = group.Items.FirstOrDefault(); if (first == null) return;
                foreach (var popup in VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot))
                {
                    DependencyObject? current = first;
                    while (current != null && !ReferenceEquals(current, popup.Child)) current = VisualTreeHelper.GetParent(current);
                    if (current == null) continue;
                    var anchor = group.TransformToVisual(root).TransformPoint(new(0, group.ActualHeight));
                    popup.HorizontalOffset = Math.Max(4, Math.Min(anchor.X, root.ActualWidth - 270));
                    popup.VerticalOffset = anchor.Y + 4; break;
                }
            };
        };
        return group;
    }

    private Style NativeMenuItemStyle(bool hasShortcut)
    {
        var style = new Style(typeof(MenuFlyoutItem)) { BasedOn = (Style)Application.Current.Resources["RelicMenuItemStyle"] };
        style.Setters.Add(new Setter(Control.BorderThicknessProperty, new Thickness(0)));
        style.Setters.Add(new Setter(Control.ForegroundProperty, Ink));
        style.Setters.Add(new Setter(Control.FontWeightProperty, Microsoft.UI.Text.FontWeights.Normal));
        style.Setters.Add(new Setter(FrameworkElement.MarginProperty, new Thickness(0)));
        style.Setters.Add(new Setter(UIElement.UseLayoutRoundingProperty, false));
        // A missing kbd is absent from the reference flex row, including its
        // gap; keeping an empty third Grid column changes intrinsic width.
        var shortcutColumn = hasShortcut ? "<ColumnDefinition Width='Auto'/>" : "";
        var shortcutLabel = hasShortcut ? "<TextBlock Grid.Column='2' Text='{TemplateBinding KeyboardAcceleratorTextOverride}' FontFamily='Cascadia Code' FontSize='11' Foreground='{ThemeResource RelicControlMuted}' VerticalAlignment='Center'/>" : "";
        style.Setters.Add(new Setter(Control.TemplateProperty, (ControlTemplate)XamlReader.Load($$"""
            <ControlTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" TargetType="MenuFlyoutItem">
              <Grid x:Name="MenuRow" Padding="{TemplateBinding Padding}" ColumnSpacing="10" Background="Transparent" CornerRadius="{TemplateBinding CornerRadius}">
                <Grid.ColumnDefinitions><ColumnDefinition Width="14"/><ColumnDefinition Width="*"/>{{shortcutColumn}}</Grid.ColumnDefinitions>
                <ContentPresenter Content="{TemplateBinding Tag}" VerticalAlignment="Center"/>
                <TextBlock x:Name="MenuLabel" Grid.Column="1" Text="{TemplateBinding Text}" FontFamily="{TemplateBinding FontFamily}" FontSize="{TemplateBinding FontSize}" FontWeight="{TemplateBinding FontWeight}" Foreground="{TemplateBinding Foreground}" LineHeight="20.8" LineStackingStrategy="BlockLineHeight" TextWrapping="NoWrap" VerticalAlignment="Center"/>
                {{shortcutLabel}}
                <VisualStateManager.VisualStateGroups><VisualStateGroup x:Name="CommonStates">
                  <VisualState x:Name="Normal"/>
                  <VisualState x:Name="PointerOver"><VisualState.Setters><Setter Target="MenuRow.Background" Value="{ThemeResource RelicControlHover}"/></VisualState.Setters></VisualState>
                  <VisualState x:Name="Pressed"><VisualState.Setters><Setter Target="MenuRow.Background" Value="{ThemeResource RelicControlHover}"/></VisualState.Setters></VisualState>
                  <VisualState x:Name="Disabled"><VisualState.Setters><Setter Target="MenuLabel.Foreground" Value="{ThemeResource RelicControlDisabled}"/></VisualState.Setters></VisualState>
                </VisualStateGroup></VisualStateManager.VisualStateGroups>
              </Grid>
            </ControlTemplate>
            """)));
        return style;
    }

    private MenuFlyoutSeparator NativeMenuSeparator() => new()
    {
        Height = 1, MinHeight = 0, Margin = new Thickness(6, 4, 6, 4), Background = Line, UseLayoutRounding = false,
        Template = (ControlTemplate)XamlReader.Load("<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' TargetType='MenuFlyoutSeparator'><Border Height='1' Background='{TemplateBinding Background}'/></ControlTemplate>")
    };

    private OverviewChipView NativeShortcutCap(string key) => new()
    {
        Content = new TextBlock { Text = key, FontFamily = new FontFamily("Cascadia Code"), FontSize = 11.5, Foreground = Ink,
            TextWrapping = TextWrapping.NoWrap },
        FontFamily = new FontFamily("Cascadia Code"), FontSize = 11.5, Foreground = Ink,
        Background = Paint("EFEEEA", "262624"), BorderBrush = Paint("DEDBD4", "3A3936"),
        BorderThickness = new Thickness(1, 1, 1, 2), Padding = new Thickness(6, 1, 6, 1), CornerRadius = new CornerRadius(5),
        HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Center, UseLayoutRounding = false
    };

    private Button NativeShortcutConfirm(string text)
    {
        var label = OverviewText(text, 13, weight: 600); label.Foreground = Paint("FFFFFF", "1F1F1E"); label.IsTextSelectionEnabled = false; label.TextWrapping = TextWrapping.NoWrap;
        var button = new Button { Content = label, Height = 32, MinHeight = 0, MinWidth = 0, Padding = new Thickness(13, 0, 13, 0),
            Background = Ink, BorderBrush = Ink, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(9),
            Foreground = label.Foreground, FontSize = 13, FontFamily = label.FontFamily, FontWeight = label.FontWeight,
            HorizontalAlignment = HorizontalAlignment.Right, HorizontalContentAlignment = HorizontalAlignment.Center,
            Template = (ControlTemplate)XamlReader.Load("<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' TargetType='Button'><ContentPresenter Content='{TemplateBinding Content}' Background='{TemplateBinding Background}' BorderBrush='{TemplateBinding BorderBrush}' BorderThickness='{TemplateBinding BorderThickness}' CornerRadius='{TemplateBinding CornerRadius}' Padding='{TemplateBinding Padding}' HorizontalContentAlignment='Center' VerticalContentAlignment='Center'/></ControlTemplate>") };
        AutomationProperties.SetName(button, text); return button;
    }
}
