using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;
using Windows.System;

namespace Relic;

public sealed partial class MainWindow
{
    private sealed class NativeMenuEntry(Button anchor, MenuFlyout flyout)
    {
        public Button Anchor { get; } = anchor;
        public MenuFlyout Flyout { get; } = flyout;
        public bool FocusOnOpen { get; set; }
        public bool FocusLast { get; set; }
    }
    private readonly List<NativeMenuEntry> nativeMenus = new();
    private NativeMenuEntry? openNativeMenu;
    private Control? nativeMenuReturnFocus;
    private bool nativeMenuKeyboardMode, nativeMenuAltPending;

    private void StyleNativeMenuBar()
    {
        // app.css .ab-menus has a single 4px leading margin.
        menu.MinHeight = 0; menu.Height = 28; menu.VerticalAlignment = VerticalAlignment.Center;
        menu.Margin = new Thickness(4, 0, 0, 1); menu.UseLayoutRounding = false;
    }

    private MenuFlyout NativeMenuGroup(string title)
    {
        var anchor = new Button { Content = title, Height = 28, MinHeight = 0, MinWidth = 0, Margin = new Thickness(0),
            Padding = new Thickness(9, 0, 9, 0), FontSize = 13, FontFamily = new FontFamily(FontFamilies.UI),
            FontWeight = Microsoft.UI.Text.FontWeights.Normal, Foreground = Paint("5A5853", "B8B5AE"),
            Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent), BorderThickness = new Thickness(0),
            CornerRadius = new CornerRadius(7), UseLayoutRounding = false, AllowFocusOnInteraction = false };
        AutomationProperties.SetName(anchor, title);
        // One real Button owns one label and one painted surface. No nested
        // MenuBarItem/ContentButton pair or rewritten automation role is used.
        anchor.Template = (ControlTemplate)XamlReader.Load("""
            <ControlTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" TargetType="Button">
              <ContentPresenter x:Name="ContentRoot" Content="{TemplateBinding Content}" Padding="{TemplateBinding Padding}" FontFamily="{TemplateBinding FontFamily}" FontSize="{TemplateBinding FontSize}" FontWeight="{TemplateBinding FontWeight}" Foreground="{TemplateBinding Foreground}" Background="{TemplateBinding Background}" CornerRadius="{TemplateBinding CornerRadius}" VerticalContentAlignment="Center" HorizontalContentAlignment="Center">
                <VisualStateManager.VisualStateGroups>
                  <VisualStateGroup x:Name="CommonStates">
                    <VisualState x:Name="Normal"/>
                    <VisualState x:Name="PointerOver"><VisualState.Setters><Setter Target="ContentRoot.Background" Value="{ThemeResource RelicControlHover}"/><Setter Target="ContentRoot.Foreground" Value="{ThemeResource RelicControlInk}"/></VisualState.Setters></VisualState>
                    <VisualState x:Name="Pressed"><VisualState.Setters><Setter Target="ContentRoot.Background" Value="{ThemeResource RelicControlHover}"/><Setter Target="ContentRoot.Foreground" Value="{ThemeResource RelicControlInk}"/></VisualState.Setters></VisualState>
                  </VisualStateGroup>
                </VisualStateManager.VisualStateGroups>
              </ContentPresenter>
            </ControlTemplate>
            """);
        var flyout = new MenuFlyout { OverlayInputPassThroughElement = menu };
        var entry = new NativeMenuEntry(anchor, flyout);
        nativeMenus.Add(entry); menu.Children.Add(anchor);
        anchor.Click += (_, _) =>
        {
            if (ReferenceEquals(openNativeMenu, entry)) CloseNativeMenu();
            else OpenNativeMenu(entry, anchor.FocusState == FocusState.Keyboard);
        };
        anchor.PointerEntered += (_, _) =>
        {
            if (openNativeMenu != null && !ReferenceEquals(openNativeMenu, entry)) OpenNativeMenu(entry, false);
        };
        anchor.LostFocus += (_, _) =>
        {
            if (openNativeMenu == null && !nativeMenus.Any(item => ReferenceEquals(item.Anchor, FocusManager.GetFocusedElement(root.XamlRoot))))
                nativeMenuKeyboardMode = false;
        };
        anchor.PreviewKeyDown += (_, e) => NativeMenuAnchorKey(entry, e);
        // Style the real MenuFlyout before its presenter is created.
        var style = new Style(typeof(MenuFlyoutPresenter));
        style.Setters.Add(new Setter(Control.BackgroundProperty, Paint("FFFFFF", "252523")));
        style.Setters.Add(new Setter(Control.ForegroundProperty, Ink));
        style.Setters.Add(new Setter(Control.BorderBrushProperty, Paint("DEDBD4", "3A3936")));
        style.Setters.Add(new Setter(Control.BorderThicknessProperty, new Thickness(1)));
        style.Setters.Add(new Setter(Control.CornerRadiusProperty, new CornerRadius(12)));
        style.Setters.Add(new Setter(Control.PaddingProperty, new Thickness(6)));
        style.Setters.Add(new Setter(FrameworkElement.MinWidthProperty, 250d));
        style.Setters.Add(new Setter(FrameworkElement.MaxHeightProperty, root.ActualHeight * .6));
        style.Setters.Add(new Setter(FrameworkElement.RequestedThemeProperty, root.ActualTheme));
        style.Setters.Add(new Setter(UIElement.UseLayoutRoundingProperty, false));
        flyout.MenuFlyoutPresenterStyle = style;
        MenuFlyoutPresenter? keyboardPresenter = null;
        flyout.Opened += (_, _) =>
        {
            var first = flyout.Items.FirstOrDefault(); if (first == null) return;
            foreach (var popup in VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot))
            {
                DependencyObject? current = first;
                MenuFlyoutPresenter? presenter = null;
                while (current != null && !ReferenceEquals(current, popup.Child))
                {
                    if (current is MenuFlyoutPresenter found) presenter = found;
                    current = VisualTreeHelper.GetParent(current);
                }
                if (current == null) continue;
                presenter ??= popup.Child as MenuFlyoutPresenter;
                if (presenter != null)
                {
                    presenter.MaxHeight = root.ActualHeight * .6;
                    presenter.RequestedTheme = root.ActualTheme;
                    if (!ReferenceEquals(keyboardPresenter, presenter))
                    {
                        keyboardPresenter = presenter;
                        presenter.PreviewKeyDown += (_, e) =>
                        {
                            NativeMenuRootKeyDown(presenter, e);
                            if (e.Handled) return;
                            if (e.Key is VirtualKey.Left or VirtualKey.Right)
                            { SwitchNativeMenu(entry, e.Key == VirtualKey.Left ? -1 : 1, true); e.Handled = true; }
                            else if (e.Key == VirtualKey.Escape)
                            { CloseNativeMenu(); nativeMenuKeyboardMode = true; anchor.Focus(FocusState.Keyboard); e.Handled = true; }
                            // The real MenuFlyout retains Up/Down/Home/End,
                            // Enter/Space activation, type-ahead and light dismiss.
                        };
                        presenter.PreviewKeyUp += NativeMenuRootKeyUp;
                    }
                }
                var point = anchor.TransformToVisual(root).TransformPoint(new(0, anchor.ActualHeight));
                popup.HorizontalOffset = Math.Max(4, Math.Min(point.X, root.ActualWidth - 270));
                popup.VerticalOffset = point.Y + 4; break;
            }
            if (entry.FocusOnOpen) FocusNativeMenuItem(entry, entry.FocusLast);
        };
        flyout.Closed += (_, _) =>
        {
            if (ReferenceEquals(openNativeMenu, entry)) { openNativeMenu = null; nativeMenuKeyboardMode = false; }
            if (ReferenceEquals(transientFlyout, flyout)) transientFlyout = null;
            PaintNativeMenuAnchors();
        };
        return flyout;
    }

    private void PaintNativeMenuAnchors()
    {
        foreach (var entry in nativeMenus)
        {
            var opened = ReferenceEquals(openNativeMenu, entry);
            entry.Anchor.Background = opened ? Paint("EFEEEA", "262624") : new SolidColorBrush(Microsoft.UI.Colors.Transparent);
            entry.Anchor.Foreground = opened ? Ink : Paint("5A5853", "B8B5AE");
        }
    }

    private void RememberNativeMenuFocus()
    {
        if (openNativeMenu != null || nativeMenuKeyboardMode) return;
        var focused = FocusManager.GetFocusedElement(root.XamlRoot) as Control;
        if (focused != null && !nativeMenus.Any(entry => ReferenceEquals(entry.Anchor, focused))) nativeMenuReturnFocus = focused;
    }

    private void OpenNativeMenu(NativeMenuEntry entry, bool keyboard, bool last = false)
    {
        if (ReferenceEquals(openNativeMenu, entry)) { if (keyboard) FocusNativeMenuItem(entry, last); return; }
        RememberNativeMenuFocus();
        var previous = openNativeMenu;
        openNativeMenu = entry; nativeMenuKeyboardMode = keyboard;
        entry.FocusOnOpen = keyboard; entry.FocusLast = last;
        previous?.Flyout.Hide();
        if (!ReferenceEquals(transientFlyout, previous?.Flyout)) transientFlyout?.Hide();
        transientFlyout = entry.Flyout;
        PaintNativeMenuAnchors();
        entry.Flyout.ShowAt(entry.Anchor, new FlyoutShowOptions { Placement = FlyoutPlacementMode.BottomEdgeAlignedLeft,
            ShowMode = keyboard ? FlyoutShowMode.Standard : FlyoutShowMode.Transient });
    }

    private void CloseNativeMenu(bool restoreFocus = false)
    {
        var previous = openNativeMenu;
        var wasActive = previous != null || nativeMenuKeyboardMode;
        openNativeMenu = null; nativeMenuKeyboardMode = false;
        previous?.Flyout.Hide();
        PaintNativeMenuAnchors();
        if (restoreFocus && wasActive && nativeMenuReturnFocus is { IsLoaded: true } target) target.Focus(FocusState.Keyboard);
    }

    private static void FocusNativeMenuItem(NativeMenuEntry entry, bool last)
    {
        var items = entry.Flyout.Items.Where(item => item is not MenuFlyoutSeparator && item.IsEnabled && item.Visibility == Visibility.Visible).ToArray();
        if (items.Length > 0) (last ? items[^1] : items[0]).Focus(FocusState.Keyboard);
    }

    private void SwitchNativeMenu(NativeMenuEntry entry, int step, bool open)
    {
        var index = nativeMenus.IndexOf(entry);
        if (index < 0 || nativeMenus.Count == 0) return;
        var next = nativeMenus[(index + step + nativeMenus.Count) % nativeMenus.Count];
        nativeMenuKeyboardMode = true;
        if (open) OpenNativeMenu(next, true);
        else next.Anchor.Focus(FocusState.Keyboard);
    }

    private void NativeMenuAnchorKey(NativeMenuEntry entry, KeyRoutedEventArgs e)
    {
        if (e.Handled || e.KeyStatus.IsMenuKeyDown) return;
        if (e.Key is VirtualKey.Left or VirtualKey.Right)
        { SwitchNativeMenu(entry, e.Key == VirtualKey.Left ? -1 : 1, openNativeMenu != null); e.Handled = true; }
        else if (e.Key is VirtualKey.Down or VirtualKey.Up)
        { OpenNativeMenu(entry, true, e.Key == VirtualKey.Up); e.Handled = true; }
        else if (e.Key == VirtualKey.Escape)
        { CloseNativeMenu(true); e.Handled = true; }
    }

    private void ToggleNativeMenuFocus()
    {
        if (nativeMenus.Count == 0) return;
        if (openNativeMenu != null || nativeMenuKeyboardMode) { CloseNativeMenu(true); return; }
        RememberNativeMenuFocus(); nativeMenuKeyboardMode = true;
        nativeMenus[0].Anchor.Focus(FocusState.Keyboard);
    }

    private static bool NativeMenuKeyPressed(VirtualKey key) =>
        (Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(key) & Windows.UI.Core.CoreVirtualKeyStates.Down) != 0;

    private void NativeMenuRootKeyDown(object sender, KeyRoutedEventArgs e)
    {
        if (e.Handled) return;
        if (e.Key == VirtualKey.Menu) { nativeMenuAltPending = !NativeMenuKeyPressed(VirtualKey.Control); return; }
        nativeMenuAltPending = false;
        if (e.KeyStatus.IsMenuKeyDown && !NativeMenuKeyPressed(VirtualKey.Control))
        {
            var index = Array.IndexOf(new[] { VirtualKey.F, VirtualKey.E, VirtualKey.V, VirtualKey.H }, e.Key);
            if (index >= 0 && index < nativeMenus.Count) { OpenNativeMenu(nativeMenus[index], true); e.Handled = true; return; }
        }
        if (e.Key == VirtualKey.F10 && !NativeMenuKeyPressed(VirtualKey.Shift) && !NativeMenuKeyPressed(VirtualKey.Control))
        { ToggleNativeMenuFocus(); e.Handled = true; return; }
        // A pointer-opened transient menu does not steal the editor's focus.
        // Its first arrow key explicitly enters the actual native item list.
        if (ReferenceEquals(sender, root) && openNativeMenu != null && (e.Key is VirtualKey.Down or VirtualKey.Up))
        { FocusNativeMenuItem(openNativeMenu, e.Key == VirtualKey.Up); nativeMenuKeyboardMode = true; e.Handled = true; }
    }

    private void NativeMenuRootKeyUp(object sender, KeyRoutedEventArgs e)
    {
        if (e.Key != VirtualKey.Menu || !nativeMenuAltPending) return;
        nativeMenuAltPending = false; ToggleNativeMenuFocus(); e.Handled = true;
    }

    private void WireNativeMenus()
    {
        root.PreviewKeyDown += NativeMenuRootKeyDown;
        root.PreviewKeyUp += NativeMenuRootKeyUp;
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
        // WinUI queries this named TextBlock while measuring accelerator text.
        // A row with no shortcut has neither the block nor its flex-row gap.
        var shortcutLabel = hasShortcut ? "<TextBlock x:Name='KeyboardAcceleratorTextBlock' Grid.Column='2' Text='{TemplateBinding KeyboardAcceleratorTextOverride}' FontFamily='Cascadia Code' FontSize='11' FontWeight='Normal' Foreground='{ThemeResource RelicControlMuted}' VerticalAlignment='Center'/>" : "";
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
