using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Relic.Core;
using System.Text.Json.Nodes;
using Windows.Globalization;
using Windows.Media.SpeechRecognition;
using Windows.Storage.Pickers;

namespace Relic;

public sealed partial class MainWindow
{
    private ContentDialog? visibleDialog;
    private Task<ContentDialogResult>? visibleDialogTask;
    private readonly Dictionary<string, TextBlock> installViews = new();
    private readonly Dictionary<string, List<string>> installLines = new();
    private SpeechRecognizer? speech;
    private Button? speechButton;

    private async Task Dialog(ContentDialog dialog)
    {
        if (visibleDialog != null)
        {
            visibleDialog.Hide();
            if (visibleDialogTask != null) await visibleDialogTask;
        }
        visibleDialog = dialog;
        visibleDialogTask = dialog.ShowAsync().AsTask();
        if (await visibleDialogTask == ContentDialogResult.Primary) confirmedDialogs.Add(dialog);
        if (visibleDialog == dialog) { visibleDialog = null; visibleDialogTask = null; }
        await StopVoice();
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
        var toggle = new ToggleSwitch { Header = T(title), IsOn = preferences.Flag(field) };
        target.Children.Add(toggle); if (hint.Length > 0) target.Children.Add(Text(T(hint), 12));
        toggle.Toggled += async (_, _) => await Run(() => SavePreferences(new JsonObject { [field] = toggle.IsOn }));
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
        stream.Spacing = preferences.Text("density") == "compact" ? 8 : 16;
        side.Spacing = preferences.Text("density") == "compact" ? 3 : 8;
        editor.FontSize = preferences.Text("font") switch { "small" => 12, "large" => 17, _ => 14 };
    }
    private async Task SettingsScreen(string section = "profile")
    {
        var body = new StackPanel { Spacing = 12, MinWidth = 520 };
        var navigation = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4 };
        var content = new StackPanel { Spacing = 12 }; body.Children.Add(navigation); body.Children.Add(content);
        async Task Draw(string key)
        {
            content.Children.Clear(); installViews.Clear();
            switch (key)
            {
                case "profile":
                    content.Children.Add(Text(T("settings.profile"), 20));
                    content.Children.Add(Avatar(preferences.Text("avatar"), T("common.you"), 56));
                    content.Children.Add(Text(T("settings.avatar_hint"), 12));
                    content.Children.Add(Button(T("settings.avatar") + " · " + T("common.change"), async () => { await ChangeAvatar(); await Draw(key); }));
                    content.Children.Add(Button(T("settings.remove"), async () => { await api!.Post("/api/avatar", new { data = "" }); await LoadPreferences(); await Draw(key); }));
                    var name = Field(content, "common.name"); name.Text = preferences.Text("name"); name.PlaceholderText = T("common.you");
                    content.Children.Add(Text(T("settings.name_hint"), 12));
                    content.Children.Add(Button(T("common.save"), () => SavePreferences(new JsonObject { ["name"] = name.Text.Trim() })));
                    break;
                case "appearance":
                    content.Children.Add(Text(T("settings.appearance"), 20));
                    PreferenceChoice(content, "settings.theme", "", "theme", ("system", T("common.theme_system")), ("light", T("common.theme_light")), ("dark", T("common.theme_dark")));
                    PreferenceChoice(content, "settings.accent", "settings.accent_hint", "accent", ("clay", "clay"), ("ink", "ink"), ("indigo", "indigo"), ("blue", "blue"), ("rose", "rose"), ("amber", "amber"));
                    PreferenceChoice(content, "settings.font_size", "", "font", ("small", T("common.size_small")), ("medium", T("common.size_medium")), ("large", T("common.size_large")));
                    PreferenceChoice(content, "settings.density", "", "density", ("comfortable", T("settings.density_comfortable")), ("compact", T("settings.density_compact")));
                    break;
                case "language":
                    content.Children.Add(Text(T("settings.language.title"), 20));
                    var language = Choice(content, "settings.language.label", [("zh-CN", "简体中文"), ("en-US", "English")]); SetChoice(language, words.Language);
                    content.Children.Add(Text(T("settings.language.hint"), 12));
                    content.Children.Add(Button(T("settings.language.system"), async () => { await SavePreferences(new() { ["lang"] = Words.Normalize(System.Globalization.CultureInfo.CurrentUICulture.Name) }); await Draw(key); }));
                    language.SelectionChanged += async (_, _) => await Run(async () => { await SavePreferences(new JsonObject { ["lang"] = Value(language) }); await Draw(key); });
                    PreferenceToggle(content, "settings.auto_names.label", "settings.auto_names.hint", "auto_names");
                    break;
                case "voice":
                    content.Children.Add(Text(T("common.voice_input"), 20));
                    PreferenceChoice(content, "common.voice_input", "native.voice_hint", "voice", ("browser", T("native.voice_system")), ("off", T("settings.voice_off")));
                    var sample = Field(content, "settings.voice_try", true); sample.PlaceholderText = T("settings.voice_try_here");
                    content.Children.Add(Microphone(sample));
                    break;
                case "notify":
                    content.Children.Add(Text(T("settings.notify"), 20));
                    PreferenceToggle(content, "settings.desktop_notify", "settings.desktop_notify_hint", "notify");
                    content.Children.Add(Text(T("settings.notify_test")));
                    content.Children.Add(Button(T("settings.notify_send_test"), () => { Notify(T("settings.notify_on")); return Task.CompletedTask; }));
                    break;
                case "harness": await HarnessSettings(content); break;
                case "about":
                    content.Children.Add(Text(T("settings.about"), 20));
                    content.Children.Add(Text(T("settings.data_folder") + "\n" + preferences.Text("data")));
                    content.Children.Add(Button(T("common.open"), async () => { await api!.Post("/api/open", new { what = "data" }); }));
                    content.Children.Add(Text(T("settings.logs") + "\n" + T("settings.logs_hint")));
                    content.Children.Add(Button(T("common.open"), async () => { await api!.Post("/api/open", new { what = "logs" }); }));
                    content.Children.Add(Text(T("settings.local_server") + "\n" + T("settings.local_server_hint", ("port", preferences.Text("port"))) + "\nv" + preferences.Text("version")));
                    content.Children.Add(Text(T("settings.install_app") + " · " + T("settings.installed") + "\n" + T("settings.install_app_done")));
                    break;
            }
        }
        foreach (var (key, label) in new[] { ("profile", "settings.profile"), ("appearance", "settings.appearance"), ("language", "settings.language.title"), ("voice", "common.voice_input"), ("notify", "settings.notify"), ("harness", "common.harness"), ("about", "settings.about") })
            navigation.Children.Add(Button(T(label), () => Draw(key)));
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
            var input = new TextBox { Header = runtime == "node" ? "Node.js" : "npm", Text = preferences["paths"].Text(runtime), PlaceholderText = T("settings.auto_find") };
            content.Children.Add(input); content.Children.Add(Text(T("settings.runtime_path_hint"), 12));
            content.Children.Add(Button(T("common.save"), () => SavePath(runtime, input.Text)));
        }
        var platform = await api!.Get("/api/platform");
        var connections = Stack(Text(T("settings.desktop_connections")), Text(platform.Text("desktop_transport")), Text(platform.Text("claude_desktop")));
        if (!platform.Flag("claude_desktop_wake")) connections.Children.Add(Text(T("settings.claude_desktop_hint")));
        connections.Children.Add(Button(T("settings.desktop_probe"), async () => { var result = await api.Post("/api/platform", new { probe = true }); Note(result.ToJsonString()); }));
        content.Children.Add(new Expander { Header = T("settings.desktop_probe_hint"), Content = connections });
        var list = (await api.Get("/api/harnesses")).Rows();
        foreach (var harness in list.Where(h => !h.Flag("later")))
        {
            var id = harness.Text("id");
            var card = Stack(Text(harness.Text("title") + " · " + harness.Text("vendor"), 18));
            card.Children.Add(Text(T("common.status") + " · " + (harness.Flag("available") ? T("settings.connected") : harness.Text("problem").Length > 0 ? harness.Text("problem") : T("settings.not_connected"))));
            var program = new TextBox { Header = T("settings.program"), Text = preferences["paths"].Text(id), PlaceholderText = harness.Text("program").Length > 0 ? harness.Text("program") : T("settings.auto_find") };
            card.Children.Add(program); card.Children.Add(Button(T("common.save"), () => SavePath(id, program.Text)));
            card.Children.Add(Text(T("settings.adapter") + " · " + (harness.Flag("adapter_installed") ? T("settings.adapter_version", ("adapter", harness.Text("adapter")), ("version", harness.Text("adapter_version"))) : T("settings.adapter_missing", ("adapter", harness.Text("adapter"))))));
            card.Children.Add(Text("Node.js · " + (harness.Text("node").Length > 0 ? harness.Text("node") : T("settings.not_found"))));
            card.Children.Add(Text(T("settings.default_mode") + " · " + (harness.Text("mode").Length > 0 ? harness.Text("mode") : harness.Text("note").Length > 0 ? T("settings.adapter_default_note", ("note", harness.Text("note"))) : T("settings.adapter_default"))));
            if (harness.Rows("models").Count > 0) card.Children.Add(Text(T("settings.models") + " · " + string.Join(T("settings.models_sep"), harness.Rows("models").Select(x => x.Text()))));
            var log = Text(string.Join("\n", installLines.GetValueOrDefault(id, []))); installViews[id] = log;
            card.Children.Add(Button(harness.Flag("adapter_installed") ? T("settings.reinstall_adapter") : T("settings.install_adapter"), async () =>
            { installLines[id] = ["$ " + harness.Text("install")]; log.Text = installLines[id][0]; await api.Post("/api/harnesses/" + Client.Segment(id) + "/install", new { }); }));
            card.Children.Add(log); content.Children.Add(card);
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
        return new Border { Width = size, Height = size, CornerRadius = new CornerRadius(size / 2), Background = new SolidColorBrush(Microsoft.UI.Colors.DimGray), Child = new TextBlock { Text = label.Length > 0 ? label[..1].ToUpperInvariant() : "R", Foreground = new SolidColorBrush(Microsoft.UI.Colors.White), HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center } };
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
    private Button Microphone(TextBox target)
    {
        Button? button = null;
        button = Button(T("composer.voice_title"), () => Voice(target, button!));
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(button, T("common.voice_input")); return button;
    }
    private async Task StopVoice()
    {
        var current = speech; speech = null;
        if (current != null) { try { await current.ContinuousRecognitionSession.StopAsync(); } catch { } current.Dispose(); }
        if (speechButton != null) speechButton.Content = T("composer.voice_title"); speechButton = null;
    }
    private async Task Voice(TextBox target, Button button)
    {
        if (speech != null) { var same = speechButton == button; await StopVoice(); if (same) return; }
        if (preferences.Text("voice") == "off") { Note(T("composer.voice_off")); return; }
        try
        {
            var recognizer = new SpeechRecognizer(new Language(words.Language)); speech = recognizer; speechButton = button;
            recognizer.Constraints.Add(new SpeechRecognitionTopicConstraint(SpeechRecognitionScenario.Dictation, "Relic"));
            var result = await recognizer.CompileConstraintsAsync();
            if (result.Status != SpeechRecognitionResultStatus.Success) throw new InvalidOperationException(T("composer.voice_no_mic"));
            var before = target.Text[..target.SelectionStart]; var after = target.Text[(target.SelectionStart + target.SelectionLength)..]; var final = "";
            recognizer.ContinuousRecognitionSession.ResultGenerated += (_, e) => DispatcherQueue.TryEnqueue(() =>
            {
                if (speech != recognizer || e.Result.Status != SpeechRecognitionResultStatus.Success) return;
                final += e.Result.Text + " "; target.Text = before + final + after; target.SelectionStart = before.Length + final.Length;
            });
            recognizer.HypothesisGenerated += (_, e) => DispatcherQueue.TryEnqueue(() => { if (speech == recognizer) target.Text = before + final + e.Hypothesis.Text + after; });
            recognizer.ContinuousRecognitionSession.Completed += (_, e) => DispatcherQueue.TryEnqueue(async () =>
            {
                if (speech != recognizer) return;
                if (e.Status != SpeechRecognitionResultStatus.Success) Note(e.Status == SpeechRecognitionResultStatus.AudioQualityFailure ? T("composer.voice_no_speech") : T("composer.voice_network"));
                target.Text = before + final + after; await StopVoice(); target.Focus(FocusState.Programmatic);
            });
            await recognizer.ContinuousRecognitionSession.StartAsync(); button.Content = T("common.cancel");
        }
        catch (UnauthorizedAccessException) { await StopVoice(); Note(T("native.speech_unavailable")); }
        catch (Exception ex) { await StopVoice(); Note(T("composer.voice_start_failed", ("error", ex.Message))); }
    }
}
