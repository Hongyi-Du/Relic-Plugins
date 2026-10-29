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
    private readonly Dictionary<string, List<string>> installLines = new();
    private SpeechRecognitionEngine? speech;
    private Button? speechButton;

    private async Task Dialog(ContentDialog dialog)
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
        dialog.Resources["ContentDialogPadding"] = new Thickness(22);
        dialog.Resources["ContentDialogTitleMargin"] = new Thickness(0, 0, 0, 14);
        dialog.Resources["ContentDialogSeparatorThickness"] = new Thickness(0);
        dialog.Resources["ContentDialogTopOverlay"] = dialog.Background;
        dialog.Resources["ContentDialogSmokeFill"] = new SolidColorBrush(Windows.UI.Color.FromArgb(82, 15, 14, 12));
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
        // Retain ContentDialog's native modal focus, validation deferrals and
        // button commands; restyle the actual template parts after realization.
        if (DialogPart<ContentControl>(dialog, "Title") is { } title)
        {
            title.FontSize = 17; title.FontWeight = new Windows.UI.Text.FontWeight { Weight = 650 };
            title.FontFamily = new FontFamily("Segoe UI Variable Text");
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
        var dialog = new ContentDialog { XamlRoot = root.XamlRoot, Title = "Relic", Content = Text(message), PrimaryButtonText = T("common.save"), CloseButtonText = T("common.cancel") };
        await Dialog(dialog);
        return confirmedDialogs.Remove(dialog);
    }
    private readonly HashSet<ContentDialog> confirmedDialogs = new();
    private void Note(string message) { error.Message = message; error.Severity = InfoBarSeverity.Informational; error.IsOpen = true; }
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
        var toggle = new ToggleSwitch { IsOn = preferences.Flag(field), OnContent = "", OffContent = "", MinWidth = 42 };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(toggle, T(title));
        target.Children.Add(SettingRow(T(title), hint.Length > 0 ? T(hint) : "", toggle));
        toggle.Toggled += async (_, _) => await Run(() => SavePreferences(new JsonObject { [field] = toggle.IsOn }));
    }
    private Border SettingRow(string title, string hint, FrameworkElement control)
    {
        var labels = Stack(Heading(title, 13)); labels.Spacing = 5; labels.VerticalAlignment = VerticalAlignment.Center;
        if (hint.Length > 0) labels.Children.Add(Quiet(hint, 12)); control.VerticalAlignment = VerticalAlignment.Center;
        return new Border { Child = TwoColumns(labels, control), Padding = new Thickness(0, 10, 0, 18), BorderThickness = new Thickness(0, 0, 0, 1), BorderBrush = Line };
    }
    private async Task SavePreferences(JsonObject changes)
    {
        try { await api!.Post("/api/prefs", changes); await LoadPreferences(); ApplyAppearance(); await Refresh(); }
        catch (Exception ex) { throw new InvalidOperationException(T("prefs.save_failed", ("error", ex.Message)), ex); }
    }
    private void ApplyAppearance()
    {
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
        ThemeSurfaces();
        if (visibleDialog != null) { visibleDialog.RequestedTheme = root.RequestedTheme; foreach (var resource in root.Resources) if (resource.Key is string key && !key.StartsWith("ContentDialog")) visibleDialog.Resources[resource.Key] = resource.Value; }
        foreach (var weak in microphoneButtons.ToArray()) { if (!weak.TryGetTarget(out var mic)) { microphoneButtons.Remove(weak); continue; } Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(mic, T("common.voice_input")); ToolTipService.SetToolTip(mic, T("composer.voice_title")); }
    }
    private async Task SettingsScreen(string section = "profile")
    {
        var body = new Grid { Width = Math.Min(860, Math.Max(600, root.ActualWidth - 180)), Height = Math.Min(570, root.ActualHeight - 180), ColumnSpacing = 28 };
        body.ColumnDefinitions.Add(new() { Width = new GridLength(180) }); body.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        var navigation = new ListView { SelectionMode = ListViewSelectionMode.Single, HorizontalContentAlignment = HorizontalAlignment.Stretch };
        var content = new StackPanel { Spacing = 20, Padding = new Thickness(0, 6, 8, 20) }; body.Children.Add(navigation); var contentScroll = Scroll(content); Grid.SetColumn(contentScroll, 1); body.Children.Add(contentScroll);
        async Task Draw(string key)
        {
            content.Children.Clear(); installViews.Clear();
            switch (key)
            {
                case "profile":
                    content.Children.Add(Heading(T("settings.profile"), 20));
                    var avatarActions = new ActionRow { Spacing = 10 }; avatarActions.Children.Add(Avatar(preferences.Text("avatar"), Display("human"), 56));
                    avatarActions.Children.Add(Button(T("common.change"), async () => { await ChangeAvatar(); await Draw(key); }));
                    if (preferences.Text("avatar").Length > 0) avatarActions.Children.Add(Button(T("settings.remove"), async () => { await api!.Post("/api/avatar", new { data = "" }); await LoadPreferences(); await Draw(key); }));
                    content.Children.Add(SettingRow(T("settings.avatar"), T("settings.avatar_hint"), avatarActions));
                    var name = new TextBox { Text = preferences.Text("name"), PlaceholderText = T("common.you"), FontSize = 13, MinWidth = 170 };
                    var nameActions = TwoColumns(name, Microphone(name)); nameActions.Width = 240;
                    name.LostFocus += async (_, _) => { if (name.Text.Trim() != preferences.Text("name")) await Run(() => SavePreferences(new JsonObject { ["name"] = name.Text.Trim() })); };
                    name.KeyDown += async (_, e) => { if (e.Key == Windows.System.VirtualKey.Enter) { e.Handled = true; await Run(() => SavePreferences(new JsonObject { ["name"] = name.Text.Trim() })); } };
                    content.Children.Add(SettingRow(T("common.name"), T("settings.name_hint"), nameActions));
                    break;
                case "appearance":
                    content.Children.Add(Text(T("settings.appearance"), 20));
                    SegmentedPreference(content, "settings.theme", "theme", ("system", T("common.theme_system")), ("light", T("common.theme_light")), ("dark", T("common.theme_dark")));
                    AccentPreference(content);
                    SegmentedPreference(content, "settings.font_size", "font", ("small", T("common.size_small")), ("medium", T("common.size_medium")), ("large", T("common.size_large")));
                    SegmentedPreference(content, "settings.density", "density", ("comfortable", T("settings.density_comfortable")), ("compact", T("settings.density_compact")));
                    break;
                case "language":
                    content.Children.Add(Heading(T("settings.language.title"), 20));
                    var language = new ComboBox { MinWidth = 180, FontSize = 13 }; foreach (var item in words.Languages) language.Items.Add(new ComboBoxItem { Content = item.Text("name"), Tag = item.Text("code") }); SetChoice(language, words.Language);
                    content.Children.Add(SettingRow(T("settings.language.label"), T("settings.language.hint"), language));
                    content.Children.Add(Button(T("settings.language.system", ("lang", System.Globalization.CultureInfo.CurrentUICulture.Name)), async () => { await SavePreferences(new() { ["lang"] = Words.Normalize(System.Globalization.CultureInfo.CurrentUICulture.Name) }); await SettingsScreen("language"); }));
                    language.SelectionChanged += async (_, _) => await Run(async () => { await SavePreferences(new JsonObject { ["lang"] = Value(language) }); await SettingsScreen("language"); });
                    PreferenceToggle(content, "settings.auto_names.label", "settings.auto_names.hint", "auto_names");
                    break;
                case "voice":
                    content.Children.Add(Heading(T("common.voice_input"), 20));
                    SegmentedPreference(content, "common.voice_input", "voice", ("browser", T("native.voice_system")), ("off", T("settings.voice_off")));
                    var sample = new TextBox { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = 80, Width = 210, FontSize = 13, PlaceholderText = T("settings.voice_try_here") };
                    content.Children.Add(SettingRow(T("settings.voice_try"), T("native.voice_hint"), TwoColumns(sample, Microphone(sample))));
                    break;
                case "notify":
                    content.Children.Add(Heading(T("settings.notify"), 20));
                    PreferenceToggle(content, "settings.desktop_notify", "settings.desktop_notify_hint", "notify");
                    content.Children.Add(SettingRow(T("settings.notify_test"), "", Button(T("settings.notify_send_test"), () => { Notify(T("settings.notify_on")); return Task.CompletedTask; })));
                    break;
                case "harness": await HarnessSettings(content); break;
                case "about":
                    content.Children.Add(Heading(T("settings.about"), 20));
                    content.Children.Add(SettingRow(T("settings.data_folder"), preferences.Text("data"), Button(T("common.open"), async () => { await api!.Post("/api/open", new { what = "data" }); })));
                    content.Children.Add(SettingRow(T("settings.logs"), T("settings.logs_hint"), Button(T("common.open"), async () => { await api!.Post("/api/open", new { what = "logs" }); })));
                    content.Children.Add(SettingRow(T("settings.local_server"), T("settings.local_server_hint", ("port", preferences.Text("port"))), Badge("v" + preferences.Text("version"))));
                    content.Children.Add(SettingRow(T("settings.install_app"), T("settings.install_app_done"), Badge(T("settings.installed"))));
                    break;
            }
        }
        foreach (var (key, label, glyph) in new[] { ("profile", "settings.profile", "\uE77B"), ("appearance", "settings.appearance", "\uE790"), ("language", "settings.language.title", "\uE774"), ("voice", "common.voice_input", "\uE720"), ("notify", "settings.notify", "\uEA8F"), ("harness", "common.harness", "\uE839"), ("about", "settings.about", "\uE946") })
        {
            var labelRow = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 }; labelRow.Children.Add(Glyph(glyph, 14)); labelRow.Children.Add(Text(T(label), 13));
            navigation.Items.Add(new ListViewItem { Content = labelRow, Tag = key, IsSelected = key == section, Padding = new Thickness(10, 8, 10, 8), CornerRadius = new CornerRadius(6) });
        }
        navigation.SelectionChanged += async (_, _) => { if (navigation.SelectedItem is ListViewItem item) await Run(() => Draw(item.Tag.ToString()!)); };
        await Draw(section); await Show(T("common.settings"), body);
    }
    private async Task HarnessSettings(StackPanel content)
    {
        content.Children.Add(Text(T("common.harness"), 20)); content.Children.Add(Text(T("settings.harness_intro")));
        async Task SavePath(string key, string path)
        {
            var paths = preferences["paths"]?.DeepClone() as JsonObject ?? new JsonObject(); paths[key] = path.Trim();
            await SavePreferences(new JsonObject { ["paths"] = paths }); Note(T("settings.path_saved"));
        }
        foreach (var runtime in new[] { "node", "npm" })
        {
            var input = new TextBox { Text = preferences["paths"].Text(runtime), PlaceholderText = T("settings.auto_find"), FontSize = 13, MinWidth = 140 };
            var controls = TwoColumns(input, Button(T("common.save"), () => SavePath(runtime, input.Text))); controls.Width = 260;
            content.Children.Add(new Border { Child = TwoColumns(Stack(Heading(runtime == "node" ? "Node.js" : "npm", 13), Quiet(T("settings.runtime_path_hint"), 11)), controls), Padding = new Thickness(0, 8, 0, 16), BorderThickness = new Thickness(0, 0, 0, 1), BorderBrush = Line });
        }
        var platform = await api!.Get("/api/platform");
        var connections = Stack(Quiet(T("settings.desktop_probe_hint"), 12));
        foreach (var connection in new[] { "desktop_transport", "claude_desktop" }) if (platform[connection].Text("reason").Length > 0) connections.Children.Add(Text(platform[connection].Text("reason"), 12));
        if (!platform.Flag("claude_desktop_wake")) connections.Children.Add(Text(T("settings.claude_desktop_hint")));
        connections.Children.Add(Button(T("settings.desktop_probe"), async () => { var result = await api.Post("/api/platform", new { probe = true }); var reasons = new[] { result["desktop_transport"].Text("reason"), result["claude_desktop"].Text("reason") }.Where(value => value.Length > 0); Note(string.Join("\n", reasons.DefaultIfEmpty(T(result.Flag("codex_desktop_wake") ? "settings.connected" : "settings.not_connected")))); }));
        content.Children.Add(new Expander { Header = T("settings.desktop_connections"), Content = connections, HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch });
        var list = (await api.Get("/api/harnesses")).Rows();
        foreach (var harness in list.Where(h => !h.Flag("later")))
        {
            var id = harness.Text("id");
            var card = new StackPanel { Spacing = 10 };
            var log = Text(string.Join("\n", installLines.GetValueOrDefault(id, []))); installViews[id] = log; log.Visibility = log.Text.Length == 0 ? Visibility.Collapsed : Visibility.Visible;
            var install = Button(harness.Flag("adapter_installed") ? T("settings.reinstall_adapter") : T("settings.install_adapter"), async () =>
            { installLines[id] = ["$ " + harness.Text("install")]; log.Text = installLines[id][0]; log.Visibility = Visibility.Visible; await api.Post("/api/harnesses/" + Client.Segment(id) + "/install", new { }); });
            card.Children.Add(TwoColumns(Stack(Heading(harness.Text("title"), 14), Quiet(harness.Text("vendor"), 11)), install));
            card.Children.Add(Badge(harness.Flag("available") ? T("settings.connected") : harness.Text("problem").Length > 0 ? harness.Text("problem") : T("settings.not_connected"), !harness.Flag("available")));
            var program = new TextBox { Header = T("settings.program"), Text = preferences["paths"].Text(id), PlaceholderText = harness.Text("program").Length > 0 ? harness.Text("program") : T("settings.auto_find"), FontSize = 13 };
            var save = Button(T("common.save"), () => SavePath(id, program.Text)); save.VerticalAlignment = VerticalAlignment.Bottom; card.Children.Add(TwoColumns(program, save));
            card.Children.Add(Quiet(T("settings.adapter") + " · " + (harness.Flag("adapter_installed") ? T("settings.adapter_version", ("adapter", harness.Text("adapter")), ("version", harness.Text("adapter_version"))) : T("settings.adapter_missing", ("adapter", harness.Text("adapter")))), 12));
            card.Children.Add(Quiet("Node.js · " + (harness.Text("node").Length > 0 ? harness.Text("node") : T("settings.not_found")), 12));
            card.Children.Add(Quiet(T("settings.default_mode") + " · " + (harness.Text("mode").Length > 0 ? harness.Text("mode") : harness.Text("note").Length > 0 ? T("settings.adapter_default_note", ("note", harness.Text("note"))) : T("settings.adapter_default")), 12));
            if (harness.Rows("models").Count > 0) card.Children.Add(Text(T("settings.models") + " · " + string.Join(T("settings.models_sep"), harness.Rows("models").Select(x => x.Text()))));
            card.Children.Add(log); content.Children.Add(Card(card));
        }
        content.Children.Add(Text(T("settings.later"), 18));
        foreach (var h in list.Where(h => h.Flag("later"))) content.Children.Add(Text(h.Text("title") + " · " + h.Text("vendor") + "\n" + h.Text("launch")));
        content.Children.Add(Text(T("settings.later_hint"), 12));
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
    }
    private UIElement Avatar(string url, string label, int size = 32)
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
    private readonly List<WeakReference<Button>> microphoneButtons = new();
    private Button Microphone(TextBox target)
    {
        Button? button = null;
        button = IconButton("\uE720", "common.voice_input", () => Voice(target, button!), T("composer.voice_title"));
        microphoneButtons.Add(new(button)); return button;
    }
    private Task StopVoice()
    {
        var current = speech; speech = null;
        if (current != null) { try { current.RecognizeAsyncCancel(); } catch (InvalidOperationException) { } current.Dispose(); }
        if (speechButton != null) { speechButton.Content = Glyph("\uE720"); speechButton.Foreground = Ink; } speechButton = null;
        return Task.CompletedTask;
    }
    private async Task Voice(TextBox target, Button button)
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
            recognizer.RecognizeAsync(RecognizeMode.Multiple); button.Content = T("common.cancel");
        }
        catch (UnauthorizedAccessException) { await StopVoice(); Note(T("native.speech_unavailable")); }
        catch (Exception ex) { await StopVoice(); Note(T("composer.voice_start_failed", ("error", ex.Message))); }
    }
}
