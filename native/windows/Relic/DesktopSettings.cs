using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Relic.Core;
using System.Text.Json.Nodes;
using System.Speech.Recognition;
using System.Text;
using Windows.Storage.Pickers;

namespace Relic;

public sealed partial class MainWindow
{
    private ContentDialog? visibleDialog;
    private Task<ContentDialogResult>? visibleDialogTask;
    private readonly Dictionary<string, TextBlock> installViews = new();
    private readonly Dictionary<string, ScrollViewer> installLogSurfaces = new();
    private readonly Dictionary<string, List<string>> installLines = new();
    private SpeechRecognitionEngine? speech;
    private Button? speechButton;

    private async Task Dialog(ContentDialog dialog, bool contentOwnsPadding = false)
    {
        transientFlyout?.Hide();
        if (visibleDialog != null)
        {
            visibleDialog.Hide();
            if (visibleDialogTask != null) await visibleDialogTask;
        }
        visibleDialog = dialog;
        dialog.RequestedTheme = root.ActualTheme;
        foreach (var resource in root.Resources) dialog.Resources[resource.Key] = resource.Value;
        dialog.Background = Paint("FFFFFF", "252523"); dialog.Foreground = Ink;
        dialog.BorderThickness = new Thickness(0); dialog.CornerRadius = new CornerRadius(16);
        dialog.Resources["ContentDialogMinWidth"] = 0d; dialog.Resources["ContentDialogMinHeight"] = 0d;
        dialog.Resources["ContentDialogMaxWidth"] = Math.Max(0d, root.ActualWidth - 32);
        dialog.Resources["ContentDialogMaxHeight"] = Math.Max(0d, root.ActualHeight - 60);
        // Self-contained forms/settings already own their reference padding.
        // Set the resource before template realization: changing it in Opened
        // leaves the template's static ContentDialogPadding at another 22px.
        dialog.Resources["ContentDialogPadding"] = new Thickness(contentOwnsPadding ? 0 : 22);
        dialog.Resources["ContentDialogTitleMargin"] = new Thickness(0, 0, 0, 14);
        dialog.Resources["ContentDialogSeparatorThickness"] = new Thickness(0);
        dialog.Resources["ContentDialogTopOverlay"] = dialog.Background;
        dialog.Resources["ContentDialogSmokeFill"] = new SolidColorBrush(Windows.UI.Color.FromArgb(255, 15, 14, 12)) { Opacity = .32 };
        dialog.Opened += (_, _) => StyleDialogParts(dialog);
        visibleDialogTask = dialog.ShowAsync().AsTask();
        if (await visibleDialogTask == ContentDialogResult.Primary) confirmedDialogs.Add(dialog);
        if (visibleDialog == dialog) { visibleDialog = null; visibleDialogTask = null; }
        await StopVoice();
    }
    private static T? DialogPart<T>(DependencyObject parent, string name) where T : FrameworkElement
    {
        if (parent is T current && current.Name == name) return current;
        for (var i = 0; i < VisualTreeHelper.GetChildrenCount(parent); i++)
            if (DialogPart<T>(VisualTreeHelper.GetChild(parent, i), name) is { } child) return child;
        return null;
    }
    private void StyleDialogParts(ContentDialog dialog)
    {
        if (dialog is NativeContentDialog native) native.ApplySurfaceBrushes();
        // Retain ContentDialog's native modal focus, validation deferrals and
        // button commands; restyle the actual template parts after realization.
        if (DialogPart<ContentControl>(dialog, "Title") is { } title)
        {
            title.FontSize = 17; title.FontWeight = new Windows.UI.Text.FontWeight { Weight = 650 };
            title.FontFamily = new FontFamily(FontFamilies.UI);
        }
        if (DialogPart<Grid>(dialog, "CommandSpace") is { } commands)
        {
            commands.Background = dialog.Background; commands.Padding = new Thickness(22, 6, 22, 22);
            commands.ColumnSpacing = 0; commands.ColumnDefinitions.Clear();
            commands.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
            var hasButton = false;
            foreach (var (name, text, primary) in new[] { ("CloseButton", dialog.CloseButtonText, false), ("SecondaryButton", dialog.SecondaryButtonText, false), ("PrimaryButton", dialog.PrimaryButtonText, true) })
            {
                if (DialogPart<Button>(commands, name) is not { } button) continue;
                if (string.IsNullOrEmpty(text)) { button.Visibility = Visibility.Collapsed; continue; }
                if (hasButton) commands.ColumnDefinitions.Add(new() { Width = new GridLength(8) });
                commands.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); hasButton = true;
                Grid.SetColumn(button, commands.ColumnDefinitions.Count - 1); button.MinWidth = 0; button.Height = 32; button.MinHeight = 0; button.Padding = new Thickness(13, 0, 13, 0);
                button.HorizontalAlignment = HorizontalAlignment.Right; button.CornerRadius = new CornerRadius(9); button.FontSize = 13; button.FontWeight = Microsoft.UI.Text.FontWeights.SemiBold;
                button.Background = primary ? Ink : Paint("FFFFFF", "252523"); button.Foreground = primary ? Paint("FFFFFF", "1F1F1E") : Ink;
                button.BorderBrush = primary ? Ink : Paint("DEDBD4", "3A3936"); button.BorderThickness = new Thickness(1);
            }
        }
    }
    private async Task<bool> Confirm(string message)
    {
        var dialog = new NativeContentDialog { XamlRoot = root.XamlRoot, Title = "Relic", Content = Text(message), PrimaryButtonText = T("common.save"), CloseButtonText = T("common.cancel") };
        await Dialog(dialog);
        return confirmedDialogs.Remove(dialog);
    }
    private readonly HashSet<ContentDialog> confirmedDialogs = new();
    private void Note(string message, int milliseconds = 3600) => ShowToast(message, milliseconds);
    private StackPanel Stack(params UIElement[] children)
    {
        var box = new StackPanel { Spacing = 10 }; foreach (var child in children) box.Children.Add(child); return box;
    }
    private static void SetChoice(ComboBox box, string value)
    {
        box.SelectedItem = box.Items.Cast<ComboBoxItem>().FirstOrDefault(x => x.Tag?.ToString() == value) ?? box.Items.Cast<object>().FirstOrDefault();
    }
    private void PreferenceChoice(StackPanel target, string title, string description, string field, params (string, string)[] options)
    {
        var choice = Choice(target, title, options);
        SetChoice(choice, preferences.Text(field));
        if (description.Length > 0) target.Children.Add(Text(T(description), 12));
        choice.SelectionChanged += async (_, _) => await Run(() => SavePreferences(new JsonObject { [field] = Value(choice) }));
    }
    private void PreferenceToggle(StackPanel target, string title, string hint, string field)
    {
        var toggle = SettingsToggle(T(title), preferences.Flag(field), value => SavePreferences(new JsonObject { [field] = value }));
        target.Children.Add(SettingRow(T(title), hint.Length > 0 ? T(hint) : "", toggle));
    }
    private FrameworkElement SettingsToggle(string title, bool value, Func<bool, Task> change)
    {
        var row = (Grid)OverviewSwitch(title, true, value, change); var toggle = (FrameworkElement)row.Children[0]; row.Children.RemoveAt(0); return toggle;
    }
    private Border SettingRow(string title, string hint, FrameworkElement control)
    {
        var labels = new StackPanel { Spacing = 2, VerticalAlignment = VerticalAlignment.Center }; labels.Children.Add(OverviewText(title, 13.5, weight: 600));
        if (hint.Length > 0) labels.Children.Add(OverviewText(hint, 12.5, true)); control.VerticalAlignment = VerticalAlignment.Center;
        var row = TwoColumns(labels, control); row.ColumnSpacing = 16;
        return new Border { Tag = "setting-row", Child = row, Padding = new Thickness(0, 14, 0, 14), BorderThickness = new Thickness(0, 0, 0, 1), BorderBrush = Line };
    }
    private TextBlock SettingsHeading(string label)
    {
        var title = OverviewText(label, 18, weight: 650); title.Margin = new Thickness(0, 0, 0, 8); return title;
    }
    private TextBox SettingsInput(string value, string placeholder, double width = double.NaN, bool multiline = false, bool mono = false, double fontSize = 14)
    {
        TextBox input = multiline ? new NativeTextarea { ResizeAccessibleName = T("panel.resize"), OwnerWindowHandle = WinRT.Interop.WindowNative.GetWindowHandle(this) } : new TextBox();
        input.Text = value; input.PlaceholderText = placeholder; input.Width = width; input.FontSize = fontSize;
        input.FontFamily = new FontFamily(mono ? "Cascadia Code" : FontFamilies.UI);
        input.AcceptsReturn = multiline; input.TextWrapping = multiline ? TextWrapping.Wrap : TextWrapping.NoWrap;
        input.Height = multiline ? 60.8 : fontSize * 1.6 + 16; input.MinHeight = 0;
        input.Padding = new Thickness(10, 7, 10, 7); input.BorderThickness = new Thickness(1); input.BorderBrush = Paint("DEDBD4", "3A3936");
        input.CornerRadius = new CornerRadius(9); input.Background = Paint("FFFFFF", "1F1F1E"); input.Foreground = Ink;
        input.Loaded += (_, _) =>
        {
            // Reference form fields have no clear-text action. The SDK's
            // focused/nonempty state otherwise inserts a DeleteButton over
            // the field's own microphone. Remove its production affordance,
            // rather than hiding the resulting extra element in capture.
            if (DialogPart<Button>(input, "DeleteButton") is not { } clear) return;
            clear.IsHitTestVisible = false; clear.IsTabStop = false;
            clear.MinWidth = clear.MinHeight = clear.Width = clear.Height = 0;
            clear.MaxWidth = clear.MaxHeight = 0; clear.Padding = new Thickness(0);
            clear.Template = (ControlTemplate)Microsoft.UI.Xaml.Markup.XamlReader.Load("<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' TargetType='Button'><Grid/></ControlTemplate>");
        };
        input.Resources["TextControlBorderThicknessFocused"] = new Thickness(1); return input;
    }
    private Grid SettingsVoiceField(TextBox input, double width, bool always = false)
    {
        var row = new Grid { Width = width }; input.Width = double.NaN; row.Children.Add(input);
        if (always || preferences.Text("voice") != "off")
        {
            input.Padding = new Thickness(10, 7, 34, 7); var mic = Microphone(input, always); mic.Width = mic.Height = 26; mic.MinHeight = 0; mic.Padding = new Thickness(4.5);
            mic.HorizontalAlignment = HorizontalAlignment.Right; mic.VerticalAlignment = VerticalAlignment.Center; mic.Margin = new Thickness(0, 0, 4, 0); row.Children.Add(mic);
        }
        return row;
    }
    private Border SettingsSegments(string field, Func<Task> redraw, params (string, string)[] choices)
    {
        var tabs = new SelectorBar { Padding = new Thickness(0) }; var values = new Dictionary<SelectorBarItem, string>();
        foreach (var (value, text) in choices)
        {
            var selected = preferences.Text(field) == value; var label = OverviewText(text, 12); label.TextWrapping = TextWrapping.NoWrap; label.IsTextSelectionEnabled = false; label.Foreground = selected ? Ink : Paint("5A5853", "B8B5AE");
            var surface = new Border { Child = label, Padding = new Thickness(9, 2, 9, 2), CornerRadius = new CornerRadius(6),
                Background = selected ? Paint("FFFFFF", "252523") : new SolidColorBrush(Microsoft.UI.Colors.Transparent) };
            UIElement content = surface;
            if (selected)
            {
                var raised = new NativeShadowPanel(surface);
                raised.SetShadows([new NativeShadowLayer(0, 1, 2, Windows.UI.Color.FromArgb(255, 20, 18, 15), .06f)]);
                content = raised;
            }
            var item = new SelectorBarItem { Text = text, Tag = content, IsSelected = selected, Padding = new Thickness(0), Margin = new Thickness(0, 0, value == choices[^1].Item1 ? 0 : 2, 0),
                CornerRadius = new CornerRadius(6), Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent),
                Template = (ControlTemplate)Microsoft.UI.Xaml.Markup.XamlReader.Load("<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' xmlns:x='http://schemas.microsoft.com/winfx/2006/xaml' TargetType='SelectorBarItem'><Grid x:Name='PART_ContainerRoot' Background='{TemplateBinding Background}' Padding='{TemplateBinding Padding}' CornerRadius='{TemplateBinding CornerRadius}'><ContentPresenter Content='{TemplateBinding Tag}'/></Grid></ControlTemplate>") };
            values.Add(item, value); tabs.Items.Add(item);
            if (selected) tabs.SelectedItem = item;
        }
        tabs.SelectionChanged += async (_, _) => { if (tabs.SelectedItem == null || !values.TryGetValue(tabs.SelectedItem, out var value) || value == preferences.Text(field)) return; await Run(async () => { await SavePreferences(new JsonObject { [field] = value }); await redraw(); }); };
        return new Border { Child = tabs, Padding = new Thickness(2), CornerRadius = new CornerRadius(8), Background = Paint("EFEEEA", "262624") };
    }
    private async Task SavePreferences(JsonObject changes)
    {
        try { await api!.Post("/api/prefs", changes); await LoadPreferences(); ApplyAppearance(); await Refresh(); }
        catch (Exception ex) { throw new InvalidOperationException(T("prefs.save_failed", ("error", ex.Message)), ex); }
    }
    private void ApplyAppearance()
    {
        root.Language = words.Language;
        root.RequestedTheme = preferences.Text("theme") switch { "dark" => ElementTheme.Dark, "light" => ElementTheme.Light, _ => ElementTheme.Default };
        var colors = new Dictionary<string, Windows.UI.Color>
        {
            ["clay"] = Windows.UI.Color.FromArgb(255, 200, 100, 63), ["ink"] = Windows.UI.Color.FromArgb(255, 58, 57, 54),
            ["indigo"] = Windows.UI.Color.FromArgb(255, 91, 97, 214), ["blue"] = Windows.UI.Color.FromArgb(255, 47, 107, 216),
            ["rose"] = Windows.UI.Color.FromArgb(255, 196, 69, 108), ["amber"] = Windows.UI.Color.FromArgb(255, 185, 130, 29)
        };
        var accent = colors.GetValueOrDefault(preferences.Text("accent"), colors["clay"]);
        root.Resources["SystemAccentColor"] = accent;
        root.Resources["AccentFillColorDefaultBrush"] = new SolidColorBrush(accent);
        // AccentButtonBackground is a StaticResource alias in WinUI's theme
        // dictionary, so overriding only its source brush leaves dialogs blue.
        foreach (var key in new[] { "AccentButtonBackground", "AccentButtonBackgroundPointerOver", "AccentButtonBackgroundPressed" }) root.Resources[key] = new SolidColorBrush(accent);
        foreach (var key in new[] { "ToggleButtonBackgroundChecked", "ToggleButtonBackgroundCheckedPointerOver", "ToggleButtonBackgroundCheckedPressed", "SelectorBarItemPillFill", "ListViewItemSelectionIndicatorBrush", "TextControlBorderBrushFocused", "TextControlBorderBrushPointerOver" }) root.Resources[key] = new SolidColorBrush(accent);
        foreach (var key in new[] { "CheckBoxCheckBackgroundFillChecked", "CheckBoxCheckBackgroundStrokeChecked", "ToggleSwitchFillOn" })
            foreach (var state in new[] { "", "PointerOver", "Pressed" }) root.Resources[key + state] = new SolidColorBrush(accent);
        stream.Spacing = 0; // Each message owns its density-dependent top margin; notices use their own 8px gap.
        side.Spacing = 2;
        editor.FontSize = preferences.Text("font") switch { "small" => 13, "large" => 15.5, _ => 14 };
        threadEditor.FontSize = editor.FontSize;
        ThemeSurfaces();
        if (visibleDialog != null) { visibleDialog.RequestedTheme = root.RequestedTheme; foreach (var resource in root.Resources) if (resource.Key is string key && !key.StartsWith("ContentDialog")) visibleDialog.Resources[resource.Key] = resource.Value; }
        foreach (var entry in microphoneButtons.ToArray()) { if (!entry.Button.TryGetTarget(out var mic)) { microphoneButtons.Remove(entry); continue; } Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(mic, T("common.voice_input")); ToolTipService.SetToolTip(mic, T("composer.voice_title")); mic.Visibility = entry.Always || preferences.Text("voice") != "off" ? Visibility.Visible : Visibility.Collapsed; }
    }
    private async Task SettingsScreen(string section = "profile")
    {
        var current = section;
        var body = new Grid { Width = Math.Min(920, root.ActualWidth - 40), Height = Math.Min(640, root.ActualHeight - 48), CornerRadius = new CornerRadius(16), Background = Paint("FFFFFF", "252523") };
        body.ColumnDefinitions.Add(new() { Width = new GridLength(220) }); body.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        var dialog = new NativeContentDialog { XamlRoot = root.XamlRoot, Content = body };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(dialog, T("common.settings"));
        var navigation = new StackPanel { Spacing = 2, Padding = new Thickness(10, 14, 10, 14) };
        var navTitle = OverviewText(T("common.settings"), 16, weight: 650); navTitle.Margin = new Thickness(10, 4, 10, 12); navigation.Children.Add(navTitle);
        var navigationSurface = new Border { Child = navigation, Background = Paint("F8F7F5", "191918"), BorderBrush = Line, BorderThickness = new Thickness(0, 0, 1, 0), CornerRadius = new CornerRadius(16, 0, 0, 16) }; body.Children.Add(navigationSurface);
        var pane = new Grid(); Grid.SetColumn(pane, 1); body.Children.Add(pane);
        var content = new StackPanel { Spacing = 6, Padding = new Thickness(28, 22, 28, 28) };
        var close = IconButton("\uE711", "common.close", () => { dialog.Hide(); return Task.CompletedTask; }); close.Content = ReferenceIcon("x", 18); close.Padding = new Thickness(0);
        close.HorizontalAlignment = HorizontalAlignment.Right; close.VerticalAlignment = VerticalAlignment.Top; close.Margin = new Thickness(0, 14, 14, 0); pane.Children.Add(close);
        // The close action precedes the pane heading/content in the reference
        // reading and keyboard order, while remaining above its scroll surface.
        Canvas.SetZIndex(close, 1); pane.Children.Add(Scroll(content));
        var tabs = new Dictionary<string, (SelectorBarItem Item, TextBlock Label, ReferenceVectorIcon Icon)>();
        var hoveredNavigationItems = new HashSet<SelectorBarItem>();
        void PaintNavigation()
        {
            navigationSurface.Background = Paint("F8F7F5", "191918"); navigationSurface.BorderBrush = Line; navTitle.Foreground = Ink;
            foreach (var tab in tabs.Values)
            {
                var selected = tab.Item.IsSelected; var hovered = hoveredNavigationItems.Contains(tab.Item);
                // Like .settings nav button.on, selection takes precedence over hover.
                tab.Item.Background = selected ? Paint("E7E5DF", "2F2E2B") : hovered ? Paint("EFEEEA", "262624") : new SolidColorBrush(Microsoft.UI.Colors.Transparent);
                tab.Label.FontWeight = selected ? Microsoft.UI.Text.FontWeights.SemiBold : Microsoft.UI.Text.FontWeights.Normal;
                tab.Label.Foreground = tab.Icon.Foreground = selected || hovered ? Ink : Paint("5A5853", "B8B5AE");
            }
        }
        body.ActualThemeChanged += (_, _) => PaintNavigation();
        var navigationBar = new SelectorBar
        {
            Padding = new Thickness(0), HorizontalAlignment = HorizontalAlignment.Stretch,
            Template = (ControlTemplate)Microsoft.UI.Xaml.Markup.XamlReader.Load("""
                <ControlTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" TargetType="SelectorBar">
                  <ItemsView x:Name="PART_ItemsView" ItemsSource="{TemplateBinding Items}" Padding="{TemplateBinding Padding}" HorizontalAlignment="Stretch" TabNavigation="{TemplateBinding TabNavigation}">
                    <ItemsView.Layout><StackLayout Orientation="Vertical" Spacing="2"/></ItemsView.Layout>
                  </ItemsView>
                </ControlTemplate>
                """)
        };
        navigation.Children.Add(navigationBar);
        navigationBar.Loaded += (_, _) =>
        {
            // SelectorBar's base OnApplyTemplate configures horizontal scroll
            // orientation. This production navigation uses a vertical layout.
            if (DialogPart<ItemsView>(navigationBar, "PART_ItemsView")?.ScrollView is { } navigationScroll)
                navigationScroll.ContentOrientation = ScrollingContentOrientation.Vertical;
        };
        async Task Draw(string key)
        {
            current = key; content.Children.Clear(); installViews.Clear(); installLogSurfaces.Clear(); body.Background = dialog.Background = Paint("FFFFFF", "252523");
            close.Foreground = Paint("5A5853", "B8B5AE");
            if (tabs.TryGetValue(key, out var selectedTab)) navigationBar.SelectedItem = selectedTab.Item;
            foreach (var (id, tab) in tabs) tab.Item.IsSelected = id == key;
            PaintNavigation();
            switch (key)
            {
                case "profile":
                    content.Children.Add(SettingsHeading(T("settings.profile")));
                    var avatarActions = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 }; avatarActions.Children.Add(Avatar(preferences.Text("avatar"), Display("human"), 60));
                    var change = OverviewAction(T("common.change"), async () => { await ChangeAvatar(); await Draw(key); }); change.VerticalAlignment = VerticalAlignment.Center; avatarActions.Children.Add(change);
                    if (preferences.Text("avatar").Length > 0) { var remove = OverviewAction(T("settings.remove"), async () => { await api!.Post("/api/avatar", new { data = "" }); await LoadPreferences(); await Draw(key); }); remove.VerticalAlignment = VerticalAlignment.Center; remove.Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent); remove.BorderThickness = new Thickness(0); avatarActions.Children.Add(remove); }
                    content.Children.Add(SettingRow(T("settings.avatar"), T("settings.avatar_hint"), avatarActions));
                    var name = SettingsInput(preferences.Text("name"), T("common.you"));
                    name.LostFocus += async (_, _) => { if (name.Text.Trim() != preferences.Text("name")) await Run(() => SavePreferences(new JsonObject { ["name"] = name.Text.Trim() })); };
                    name.KeyDown += async (_, e) => { if (e.Key == Windows.System.VirtualKey.Enter) { e.Handled = true; await Run(() => SavePreferences(new JsonObject { ["name"] = name.Text.Trim() })); } };
                    content.Children.Add(SettingRow(T("common.name"), T("settings.name_hint"), SettingsVoiceField(name, 220))); break;
                case "appearance":
                    content.Children.Add(SettingsHeading(T("settings.appearance")));
                    content.Children.Add(SettingRow(T("settings.theme"), "", SettingsSegments("theme", () => Draw(key), ("system", T("common.theme_system")), ("light", T("common.theme_light")), ("dark", T("common.theme_dark")))));
                    var colors = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
                    foreach (var (value, hex) in new[] { ("clay", "C8643F"), ("ink", "3A3936"), ("indigo", "5B61D6"), ("blue", "2F6BD8"), ("rose", "C4456C"), ("amber", "B9821D") })
                    {
                        var swatch = QuietButton("", async () => { await SavePreferences(new JsonObject { ["accent"] = value }); await Draw(key); }); swatch.Width = swatch.Height = 24; swatch.MinHeight = 0; swatch.Padding = new Thickness(0); swatch.CornerRadius = new CornerRadius(12); swatch.Background = Paint(hex); swatch.BorderThickness = new Thickness(2); swatch.BorderBrush = new SolidColorBrush(Microsoft.UI.Colors.Transparent); ToolTipService.SetToolTip(swatch, value); Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(swatch, value);
                        swatch.Style = (Style)Application.Current.Resources["RelicSwatchStyle"];
                        var ring = new Grid { Width = 24, Height = 24 }; if (preferences.Text("accent") == value) ring.Children.Add(new Border { Margin = new Thickness(-4), CornerRadius = new CornerRadius(16), BorderThickness = new Thickness(2), BorderBrush = Ink, Child = new Border { CornerRadius = new CornerRadius(14), BorderThickness = new Thickness(2), BorderBrush = Paint("FFFFFF", "1F1F1E") } }); ring.Children.Add(swatch); colors.Children.Add(ring);
                    }
                    content.Children.Add(SettingRow(T("settings.accent"), T("settings.accent_hint"), colors));
                    content.Children.Add(SettingRow(T("settings.font_size"), "", SettingsSegments("font", () => Draw(key), ("small", T("common.size_small")), ("medium", T("common.size_medium")), ("large", T("common.size_large")))));
                    content.Children.Add(SettingRow(T("settings.density"), "", SettingsSegments("density", () => Draw(key), ("comfortable", T("settings.density_comfortable")), ("compact", T("settings.density_compact"))))); break;
                case "language":
                    content.Children.Add(SettingsHeading(T("settings.language.title")));
                    var language = new ComboBox { Width = 200, Height = 37, MinHeight = 0, FontFamily = new FontFamily(FontFamilies.UI), FontSize = 14, Padding = new Thickness(10, 7, 10, 7), BorderThickness = new Thickness(1), BorderBrush = Paint("DEDBD4", "3A3936"), Background = Paint("FFFFFF", "1F1F1E"), CornerRadius = new CornerRadius(9) };
                    language.Items.Add(new ComboBoxItem { Content = T("settings.language.system", ("lang", System.Globalization.CultureInfo.CurrentUICulture.Name)), Tag = "" });
                    foreach (var item in words.Languages) language.Items.Add(new ComboBoxItem { Content = item.Text("name"), Tag = item.Text("code") });
                    var selectedLanguage = preferences.Text("lang"); if (selectedLanguage.Length > 0 && !words.Languages.Any(item => item.Text("code") == selectedLanguage)) language.Items.Add(new ComboBoxItem { Content = selectedLanguage, Tag = selectedLanguage }); SetChoice(language, selectedLanguage);
                    content.Children.Add(SettingRow(T("settings.language.label"), T("settings.language.hint"), language));
                    language.SelectionChanged += async (_, _) => await Run(async () => { await SavePreferences(new JsonObject { ["lang"] = Value(language) }); await SettingsScreen("language"); });
                    PreferenceToggle(content, "settings.auto_names.label", "settings.auto_names.hint", "auto_names"); break;
                case "voice":
                    content.Children.Add(SettingsHeading(T("common.voice_input")));
                    // These recognizer descriptions remain an explicit parity
                    // difference: the Windows App does not use Edge recognition.
                    content.Children.Add(SettingRow(T("common.voice_input"), T("settings.voice_hint"), SettingsSegments("voice", () => Draw(key), ("browser", T("native.voice_system")), ("off", T("settings.voice_off")))));
                    var sample = SettingsInput("", T("settings.voice_try_here"), multiline: true);
                    content.Children.Add(SettingRow(T("settings.voice_try"), T("native.voice_hint"), SettingsVoiceField(sample, 300, always: true)));
                    var voiceNote = OverviewText(T("settings.voice_wechat"), 12.5, true, lineHeight: 21.25); voiceNote.Margin = new Thickness(0, 10, 0, 0); content.Children.Add(voiceNote); break;
                case "notify":
                    content.Children.Add(SettingsHeading(T("settings.notify"))); PreferenceToggle(content, "settings.desktop_notify", "settings.desktop_notify_hint", "notify");
                    content.Children.Add(SettingRow(T("settings.notify_test"), "", OverviewAction(T("settings.notify_send_test"), () => { Notify(T("settings.notify_on")); return Task.CompletedTask; }))); break;
                case "harness": await HarnessSettings(content); break;
                case "about":
                    content.Children.Add(SettingsHeading(T("settings.about")));
                    content.Children.Add(SettingRow(T("settings.data_folder"), preferences.Text("data"), OverviewAction(T("common.open"), async () => { await api!.Post("/api/open", new { what = "data" }); })));
                    content.Children.Add(SettingRow(T("settings.logs"), T("settings.logs_hint"), OverviewAction(T("common.open"), async () => { await api!.Post("/api/open", new { what = "logs" }); })));
                    content.Children.Add(SettingRow(T("settings.local_server"), T("settings.local_server_hint", ("port", preferences.Text("port"))), OverviewChip("v" + preferences.Text("version"))));
                    // Browser Install versus an already-installed native app is
                    // unresolved; no exception or substitute is counted as parity.
                    content.Children.Add(SettingRow(T("settings.install_app"), T("settings.install_app_done"), OverviewChip(T("settings.installed"), "ok"))); break;
            }
            if (content.Children.LastOrDefault() is Border last && last.Tag?.ToString() == "setting-row") last.BorderThickness = new Thickness(0);
        }
        foreach (var (key, label, glyph) in new[] { ("profile", "settings.profile", "\uE77B"), ("appearance", "settings.appearance", "\uE790"), ("language", "settings.language.title", "\uE774"), ("voice", "common.voice_input", "\uE720"), ("notify", "settings.notify", "\uEA8F"), ("harness", "common.harness", "\uE839"), ("about", "settings.about", "\uE946") })
        {
            var labelRow = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10, VerticalAlignment = VerticalAlignment.Center }; var icon = (ReferenceVectorIcon)Glyph(glyph, 16); labelRow.Children.Add(icon); var text = OverviewText(T(label), 14); text.IsTextSelectionEnabled = false; text.TextWrapping = TextWrapping.NoWrap; labelRow.Children.Add(text);
            var tab = new SelectorBarItem { Text = T(label), Tag = labelRow, Height = 34, Padding = new Thickness(10, 0, 10, 0), CornerRadius = new CornerRadius(8), HorizontalAlignment = HorizontalAlignment.Stretch,
                Template = (ControlTemplate)Microsoft.UI.Xaml.Markup.XamlReader.Load("<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' xmlns:x='http://schemas.microsoft.com/winfx/2006/xaml' TargetType='SelectorBarItem'><Grid x:Name='PART_ContainerRoot' Background='{TemplateBinding Background}' Padding='{TemplateBinding Padding}' CornerRadius='{TemplateBinding CornerRadius}'><ContentPresenter Content='{TemplateBinding Tag}' VerticalAlignment='Center'/></Grid></ControlTemplate>") };
            navigationBar.Items.Add(tab); tabs.Add(key, (tab, text, icon));
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetAutomationId(tab, "settings-nav-" + key);
            tab.PointerEntered += (_, _) => { hoveredNavigationItems.Add(tab); PaintNavigation(); };
            tab.PointerExited += (_, _) => { hoveredNavigationItems.Remove(tab); PaintNavigation(); };
            navigationBar.SizeChanged += (_, args) => tab.Width = args.NewSize.Width;
        }
        // One real selection model owns all navigation rows. Seven independent
        // one-item SelectorBars let modal initial focus select Profile and
        // overwrite an explicitly requested Appearance/Language/etc. page.
        navigationBar.SelectionChanged += async (_, _) =>
        {
            var selected = tabs.FirstOrDefault(entry => ReferenceEquals(entry.Value.Item, navigationBar.SelectedItem));
            if (selected.Key != null && selected.Key != current) await Run(() => Draw(selected.Key));
        };
        dialog.Opened += (_, _) =>
        {
            dialog.Resources["ContentDialogPadding"] = new Thickness(0); dialog.Resources["ContentDialogTitleMargin"] = new Thickness(0);
            if (DialogPart<ContentPresenter>(dialog, "Content") is { } presenter) { presenter.Margin = new Thickness(0); presenter.Padding = new Thickness(0); }
            if (DialogPart<Border>(dialog, "BackgroundElement") is { } background) { background.Padding = new Thickness(0); background.CornerRadius = new CornerRadius(16); }
            if (DialogPart<ScrollViewer>(dialog, "ContentScrollViewer") is { } scroll) { scroll.Padding = new Thickness(0); scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Disabled; }
            if (DialogPart<Grid>(dialog, "CommandSpace") is { } commands) commands.Visibility = Visibility.Collapsed;
        };
        void Resize(object sender, SizeChangedEventArgs args)
        {
            body.Width = Math.Min(920, Math.Max(0, args.NewSize.Width - 40));
            body.Height = Math.Min(640, Math.Max(0, args.NewSize.Height - 48));
        }
        root.SizeChanged += Resize;
        try { await Draw(section); await Dialog(dialog, contentOwnsPadding: true); }
        finally { root.SizeChanged -= Resize; }
    }
    private async Task HarnessSettings(StackPanel content)
    {
        content.Children.Add(SettingsHeading(T("common.harness")));
        var intro = OverviewText(T("settings.harness_intro"), 12.5, true); intro.Margin = new Thickness(0, 0, 0, 12); content.Children.Add(intro);
        async Task SavePath(string key, string path)
        {
            var paths = preferences["paths"]?.DeepClone() as JsonObject ?? new JsonObject(); paths[key] = path.Trim();
            await SavePreferences(new JsonObject { ["paths"] = paths }); Note(T("settings.path_saved"));
            content.Children.Clear(); installViews.Clear(); installLogSurfaces.Clear(); await HarnessSettings(content);
        }
        foreach (var runtime in new[] { "node", "npm" })
        {
            // The reference's 20-character, .92em monospace path field keeps
            // its intrinsic width while the label takes the remaining space.
            var input = SettingsInput(preferences["paths"].Text(runtime), T("settings.auto_find"), 203, mono: true, fontSize: 12.88);
            var controls = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 }; controls.Children.Add(input);
            var save = OverviewAction(T("common.save"), () => SavePath(runtime, input.Text)); save.VerticalAlignment = VerticalAlignment.Center; controls.Children.Add(save);
            content.Children.Add(SettingRow(runtime == "node" ? "Node.js" : "npm", T("settings.runtime_path_hint"), controls));
        }
        // drawHarness exposes desktop transport controls only on macOS. The
        // Windows page therefore continues directly into the harness cards.
        var list = (await api!.Get("/api/harnesses")).Rows();
        foreach (var harness in list.Where(h => !h.Flag("later")))
        {
            var id = harness.Text("id"); var card = new StackPanel { Spacing = 10 };
            var log = OverviewText(string.Join("\n", installLines.GetValueOrDefault(id, [])), 11.5, lineHeight: 17.25); log.FontFamily = new FontFamily("Cascadia Code"); installViews[id] = log;
            var logSurface = Scroll(log); logSurface.Background = Paint("F6F5F2", "232321"); logSurface.Padding = new Thickness(8); logSurface.CornerRadius = new CornerRadius(8); logSurface.MaxHeight = 160;
            logSurface.Visibility = log.Text.Length == 0 ? Visibility.Collapsed : Visibility.Visible; installLogSurfaces[id] = logSurface;
            var install = OverviewAction(harness.Flag("adapter_installed") ? T("settings.reinstall_adapter") : T("settings.install_adapter"), async () =>
            {
                installLines[id] = ["$ " + harness.Text("install")]; log.Text = installLines[id][0]; logSurface.Visibility = Visibility.Visible;
                await api.Post("/api/harnesses/" + Client.Segment(id) + "/install", new { });
            });
            var title = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10, VerticalAlignment = VerticalAlignment.Center }; title.Children.Add(OverviewText(harness.Text("title"), 14, weight: 700)); title.Children.Add(OverviewText(harness.Text("vendor"), 14, true));
            var header = TwoColumns(title, install); header.ColumnSpacing = 10; card.Children.Add(header);
            var kv = new Grid { ColumnSpacing = 12, RowSpacing = 7, Margin = new Thickness(0, 12.5, 0, 12.5) };
            kv.ColumnDefinitions.Add(new() { Width = new GridLength(76) }); kv.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
            void Row(string label, UIElement value)
            {
                var row = kv.RowDefinitions.Count; kv.RowDefinitions.Add(new() { Height = GridLength.Auto });
                var term = OverviewText(label, 12.5, true); Grid.SetRow(term, row); kv.Children.Add(term);
                Grid.SetRow((FrameworkElement)value, row); Grid.SetColumn((FrameworkElement)value, 1); kv.Children.Add(value);
            }
            var status = OverviewChip(harness.Flag("available") ? T("settings.connected") : harness.Text("problem").Length > 0 ? harness.Text("problem") : T("settings.not_connected"), harness.Flag("available") ? "ok" : "bad"); status.HorizontalAlignment = HorizontalAlignment.Left; Row(T("common.status"), status);
            var program = SettingsInput(preferences["paths"].Text(id), harness.Text("program").Length > 0 ? harness.Text("program") : T("settings.auto_find"), mono: true, fontSize: 12);
            var save = OverviewAction(T("common.save"), () => SavePath(id, program.Text)); save.VerticalAlignment = VerticalAlignment.Top; var controls = TwoColumns(program, save); controls.ColumnSpacing = 6; Row(T("settings.program"), controls);
            Row(T("settings.adapter"), OverviewText(harness.Flag("adapter_installed") ? T("settings.adapter_version", ("adapter", harness.Text("adapter")), ("version", harness.Text("adapter_version"))) : T("settings.adapter_missing", ("adapter", harness.Text("adapter")))));
            Row("Node.js", OverviewText(harness.Text("node").Length > 0 ? harness.Text("node") : T("settings.not_found")));
            Row(T("settings.default_mode"), OverviewText(harness.Text("mode").Length > 0 ? harness.Text("mode") : harness.Text("note").Length > 0 ? T("settings.adapter_default_note", ("note", harness.Text("note"))) : T("settings.adapter_default")));
            if (harness.Rows("models").Count > 0) Row(T("settings.models"), OverviewText(string.Join(T("settings.models_sep"), harness.Rows("models").Select(x => x.Text()))));
            card.Children.Add(kv); card.Children.Add(logSurface);
            content.Children.Add(new Border { Child = card, BorderBrush = Line, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(12), Padding = new Thickness(14), Margin = new Thickness(0, 0, 0, 10) });
        }
        var laterHeading = OverviewText(T("settings.later"), 15, weight: 650); laterHeading.Margin = new Thickness(0, 12, 0, 8); content.Children.Add(laterHeading);
        var later = new StackPanel { Spacing = 6 };
        foreach (var harness in list.Where(h => h.Flag("later")))
        {
            var title = new TextBlock { FontFamily = new FontFamily(FontFamilies.UI), FontSize = 12.5, LineHeight = 20, LineStackingStrategy = LineStackingStrategy.BlockLineHeight, Foreground = Ink, TextWrapping = TextWrapping.Wrap };
            title.Inlines.Add(new Microsoft.UI.Xaml.Documents.Run { Text = harness.Text("title"), FontWeight = Microsoft.UI.Text.FontWeights.Bold });
            title.Inlines.Add(new Microsoft.UI.Xaml.Documents.Run { Text = " " + harness.Text("vendor"), Foreground = Muted });
            var launch = OverviewText(harness.Text("launch"), 11.5, true); launch.FontFamily = new FontFamily("Cascadia Code"); launch.HorizontalAlignment = HorizontalAlignment.Right;
            var row = TwoColumns(title, launch); row.ColumnSpacing = 10;
            var frame = new Grid(); frame.Children.Add(new Border { Child = row, Padding = new Thickness(11, 9, 11, 9), CornerRadius = new CornerRadius(10) });
            frame.Children.Add(new Microsoft.UI.Xaml.Shapes.Rectangle { Stroke = Paint("DEDBD4", "3A3936"), StrokeThickness = 1, RadiusX = 10, RadiusY = 10, StrokeDashArray = new DoubleCollection { 3, 3 }, IsHitTestVisible = false }); later.Children.Add(frame);
        }
        content.Children.Add(later); var laterHint = OverviewText(T("settings.later_hint"), 12, true); laterHint.Margin = new Thickness(0, 8, 0, 0); content.Children.Add(laterHint);
    }
    private void InstallEvent(JsonNode ev)
    {
        var id = ev.Text("id"); if (!installLines.TryGetValue(id, out var lines)) installLines[id] = lines = [];
        if (ev.Text("line").Length > 0) lines.Add(ev.Text("line"));
        if (ev["done"] != null)
        {
            lines.Add(ev.Text("done") == "0" ? T("settings.install_done") : T("settings.install_failed", ("code", ev.Text("done"))));
            Note(ev.Text("done") == "0" ? T("settings.adapter_installed") : T("settings.adapter_install_failed"));
        }
        if (installViews.TryGetValue(id, out var view)) view.Text = string.Join("\n", lines.TakeLast(200));
        if (installLogSurfaces.TryGetValue(id, out var surface)) { surface.Visibility = Visibility.Visible; surface.UpdateLayout(); surface.ChangeView(null, surface.ScrollableHeight, null, true); }
    }
    private UIElement Avatar(string url, string label, int size = 32) => SidebarPicture(label, AvatarPaint(url, label, size), size);
    private UIElement AvatarPaint(string url, string label, int size)
    {
        if (url.StartsWith("/api/avatar"))
        {
            var port = preferences.Text("port");
            var picture = new Image { Source = new BitmapImage(new Uri("http://127.0.0.1:" + port + url)), Width = size, Height = size, Stretch = Stretch.UniformToFill };
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(picture, label); return picture;
        }
        var identity = snap.Rows("members").FirstOrDefault(m => m.Text("display") == label || m.Text("name") == label).Text("name");
        if (identity.Length == 0) identity = orgs.FirstOrDefault(o => o.Text("name") == label).Text("id");
        if (identity.Length == 0) identity = label;
        uint hash = 7; foreach (var character in identity.EnumerateRunes()) hash = unchecked(hash * 31 + (uint)character.Value);
        var hue = new[] { 18, 30, 42, 205, 222, 248, 272, 300, 330, 350, 190, 12 }[hash % 12]; var human = label == Display("human");
        SolidColorBrush Hsl(double saturation, double lightness)
        {
            var chroma = (1 - Math.Abs(2 * lightness - 1)) * saturation; var x = chroma * (1 - Math.Abs(hue / 60d % 2 - 1)); var m = lightness - chroma / 2;
            var (r, g, b) = hue switch { < 60 => (chroma, x, 0d), < 120 => (x, chroma, 0d), < 180 => (0d, chroma, x), < 240 => (0d, x, chroma), < 300 => (x, 0d, chroma), _ => (chroma, 0d, x) };
            return new SolidColorBrush(Windows.UI.Color.FromArgb(255, (byte)Math.Round((r + m) * 255), (byte)Math.Round((g + m) * 255), (byte)Math.Round((b + m) * 255)));
        }
        return new Border { Width = size, Height = size, CornerRadius = new CornerRadius(size >= 60 ? 14 : size >= 36 ? 9 : size >= 28 ? 8 : 6), Background = human ? Paint("1B1B1A", "ECEAE5") : label == "#" ? Paint("EFEEEA", "2F2E2B") : Hsl(Dark ? .18 : .4, Dark ? .24 : .9), Child = new TextBlock { Text = label.Length > 0 ? System.Globalization.StringInfo.GetNextTextElement(label).ToUpperInvariant() : "R", Foreground = human ? Paint("FFFFFF", "1F1F1E") : Hsl(Dark ? .45 : .38, Dark ? .78 : .34), FontSize = size >= 60 ? 24 : size >= 36 ? 14 : size >= 28 ? 12 : 10, FontWeight = new Windows.UI.Text.FontWeight { Weight = 650 }, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center } };
    }
    private async Task ChangeAvatar(string? who = null)
    {
        var picker = new FileOpenPicker();
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(this));
        foreach (var type in new[] { ".png", ".jpg", ".jpeg", ".webp", ".gif" }) picker.FileTypeFilter.Add(type);
        var file = await picker.PickSingleFileAsync(); if (file == null) return;
        if ((await file.GetBasicPropertiesAsync()).Size > 2 * 1024 * 1024) throw new ArgumentException(T("card.image_too_large"));
        var bytes = await System.IO.File.ReadAllBytesAsync(file.Path);
        var mime = file.FileType.ToLowerInvariant() switch { ".jpg" or ".jpeg" => "image/jpeg", ".webp" => "image/webp", ".gif" => "image/gif", _ => "image/png" };
        var payload = new JsonObject { ["data"] = "data:" + mime + ";base64," + Convert.ToBase64String(bytes) };
        if (who != null) { payload["org"] = org; payload["member"] = who; }
        await api!.Post("/api/avatar", payload); await LoadPreferences(); await Refresh(); Note(T("card.avatar_changed"));
    }
    private readonly List<(WeakReference<Button> Button, bool Always)> microphoneButtons = new();
    private Button Microphone(TextBox target, bool always = false) => Microphone(new VoiceTextTarget(target), always);
    private Button Microphone(ComposerInput target, bool always = false) => Microphone(new VoiceTextTarget(target), always);
    private Button Microphone(VoiceTextTarget target, bool always)
    {
        Button? button = null;
        button = IconButton("\uE720", "common.voice_input", () => Voice(target, button!), T("composer.voice_title"));
        button.Width = button.Height = 32; button.CornerRadius = new CornerRadius(16);
        button.HorizontalContentAlignment = HorizontalAlignment.Center; button.VerticalContentAlignment = VerticalAlignment.Center; button.Padding = new Thickness(0);
        button.Foreground = Paint("5A5853", "B8B5AE");
        if (button.Content is ReferenceVectorIcon icon) icon.Foreground = button.Foreground;
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(button, T("common.voice_input"));
        button.Visibility = always || preferences.Text("voice") != "off" ? Visibility.Visible : Visibility.Collapsed;
        microphoneButtons.Add((new(button), always)); return button;
    }
    private Task StopVoice()
    {
        var current = speech; speech = null;
        if (current != null) { try { current.RecognizeAsyncCancel(); } catch (InvalidOperationException) { } current.Dispose(); }
        if (speechButton != null)
        {
            speechButton.Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent);
            speechButton.Foreground = Paint("5A5853", "B8B5AE");
            if (speechButton.Content is ReferenceVectorIcon icon) icon.Foreground = speechButton.Foreground;
        }
        speechButton = null;
        return Task.CompletedTask;
    }
    private async Task Voice(VoiceTextTarget target, Button button)
    {
        if (speech != null) { var same = speechButton == button; await StopVoice(); if (same) return; }
        if (preferences.Text("voice") == "off") { Note(T("composer.voice_off")); return; }
        try
        {
            var installed = SpeechRecognitionEngine.InstalledRecognizers().FirstOrDefault(r => r.Culture.Name.Equals(words.Language, StringComparison.OrdinalIgnoreCase));
            if (installed == null) { Note(T("native.voice_language_missing", ("language", words.Language))); return; }
            var recognizer = new SpeechRecognitionEngine(installed); speech = recognizer; speechButton = button;
            recognizer.LoadGrammar(new DictationGrammar());
            try { recognizer.SetInputToDefaultAudioDevice(); }
            catch (InvalidOperationException) { await StopVoice(); Note(T("composer.voice_no_mic")); return; }
            var before = target.Text[..target.SelectionStart]; var after = target.Text[(target.SelectionStart + target.SelectionLength)..]; var final = "";
            recognizer.SpeechRecognized += (_, e) => DispatcherQueue.TryEnqueue(() =>
            {
                if (speech != recognizer) return;
                final += e.Result.Text + (words.Language == "en-US" ? " " : ""); target.Text = before + final + after; target.SelectionStart = before.Length + final.Length;
            });
            recognizer.SpeechHypothesized += (_, e) => DispatcherQueue.TryEnqueue(() => { if (speech == recognizer) { target.Text = before + final + e.Result.Text + after; target.SelectionStart = before.Length + final.Length + e.Result.Text.Length; } });
            recognizer.SpeechRecognitionRejected += (_, _) => DispatcherQueue.TryEnqueue(() => { if (speech == recognizer) Note(T("composer.voice_no_speech")); });
            recognizer.RecognizeCompleted += (_, e) => DispatcherQueue.TryEnqueue(async () =>
            {
                if (speech != recognizer) return;
                if (e.Error is System.Net.WebException) Note(T("composer.voice_network"));
                else if (e.Error != null) Note(T("composer.voice_start_failed", ("error", e.Error.Message)));
                target.Text = before + final + after; await StopVoice(); target.Focus(FocusState.Programmatic);
            });
            recognizer.RecognizeAsync(RecognizeMode.Multiple);
            button.Foreground = Paint("C2412D", "EE8A78");
            var recording = Paint("C2412D", "EE8A78"); recording.Opacity = .14; button.Background = recording;
            if (button.Content is ReferenceVectorIcon icon) icon.Foreground = button.Foreground;
        }
        catch (UnauthorizedAccessException) { await StopVoice(); Note(T("native.speech_unavailable")); }
        catch (Exception ex) { await StopVoice(); Note(T("composer.voice_start_failed", ("error", ex.Message))); }
    }
}
