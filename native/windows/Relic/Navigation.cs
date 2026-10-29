using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Automation;
using Relic.Core;
using System.Text.Json;
using System.Text.Json.Nodes;
using Windows.ApplicationModel.DataTransfer;
using Windows.System;

namespace Relic;

public sealed partial class MainWindow
{
    private readonly Grid columns = new();
    private bool sideOpen = true, panelOpen = true;
    private double sideWidth = 276, panelWidth = 340, fileWidth = 520;
    private Thumb? panelResize;
    private string viewMode = "direct";
    private readonly List<(string Org, string Member)> history = new();
    private int historyIndex = -1;
    private readonly Dictionary<string, string> seenMessages = new();
    private JsonObject chatStates = new();
    private string StatePath => System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Relic", "native-ui.json");
    private void SaveViewState()
    {
        if (!ready) return;
        RememberChat();
        var state = new JsonObject { ["org"] = org, ["member"] = member, ["pane"] = pane == "thread" ? previousPane : pane,
            ["plain"] = plainMode, ["digest"] = digestOpen, ["side"] = sideOpen, ["panel"] = panelOpen,
            ["sideWidth"] = sideWidth, ["panelWidth"] = panelWidth, ["fileWidth"] = fileWidth, ["mode"] = viewMode, ["chartClosed"] = chartClosed, ["chartLinks"] = chartLinks,
            ["folded"] = JsonSerializer.SerializeToNode(folded), ["drafts"] = JsonSerializer.SerializeToNode(drafts),
            ["seen"] = JsonSerializer.SerializeToNode(seenMessages), ["chats"] = chatStates.DeepClone() };
        try { System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(StatePath)!); System.IO.File.WriteAllText(StatePath + ".tmp", state.ToJsonString()); System.IO.File.Move(StatePath + ".tmp", StatePath, true); }
        catch (System.IO.IOException) { } catch (UnauthorizedAccessException) { }
    }
    private void RememberChat()
    {
        if (org.Length == 0) return;
        chatStates[org + "/" + member] = new JsonObject { ["recipients"] = JsonSerializer.SerializeToNode(recipientNames), ["quoteWho"] = quoteWho, ["quoteText"] = quoteText };
    }
    private void RestoreChat()
    {
        var state = chatStates[org + "/" + member]; recipientNames.Clear();
        foreach (var name in state.Rows("recipients")) recipientNames.Add(name.Text());
        if (recipientNames.Count == 0) recipientNames.Add("all");
        ClearQuote(); if (state.Text("quoteText").Length > 0) Quote(state.Text("quoteWho"), state.Text("quoteText"));
        editor.Text = drafts.GetValueOrDefault(org + "/" + member, "");
    }
    private void LoadViewState()
    {
        try
        {
            if (!System.IO.File.Exists(StatePath)) return;
            var state = JsonNode.Parse(System.IO.File.ReadAllText(StatePath))!;
            org = state.Text("org"); member = state.Text("member"); pane = state.Text("pane"); if (pane.Length == 0) pane = "overview";
            plainMode = state.Flag("plain"); digestOpen = state.Flag("digest"); sideOpen = state["side"] == null || state.Flag("side"); panelOpen = state["panel"] == null || state.Flag("panel");
            if (double.TryParse(state.Text("sideWidth"), out var sw)) sideWidth = Math.Clamp(sw, 180, 460);
            if (double.TryParse(state.Text("panelWidth"), out var pw)) panelWidth = Math.Clamp(pw, 280, 900);
            if (double.TryParse(state.Text("fileWidth"), out var fw)) fileWidth = Math.Clamp(fw, 280, 900);
            chartClosed = state["chartClosed"] == null || state.Flag("chartClosed"); chartLinks = state["chartLinks"] == null || state.Flag("chartLinks");
            viewMode = state.Text("mode");
            foreach (var id in state.Rows("folded")) folded.Add(id.Text());
            if (state["drafts"] is JsonObject saved) foreach (var pair in saved) drafts[pair.Key] = pair.Value.Text();
            if (state["seen"] is JsonObject seen) foreach (var pair in seen) seenMessages[pair.Key] = pair.Value.Text();
            if (state["chats"] is JsonObject chats) chatStates = chats.DeepClone().AsObject();
            RestoreChat();
        }
        catch (Exception ex) when (ex is System.IO.IOException or JsonException or UnauthorizedAccessException) { }
    }
    private void LayoutColumns()
    {
        if (columns.ColumnDefinitions.Count < 3) return;
        var available = root.ActualWidth > 0 ? root.ActualWidth : 1440;
        var leftWidth = sideOpen ? Math.Clamp(sideWidth, 200, Math.Max(200, available - 620)) : 0;
        var overlay = available <= 1180;
        var desiredPaneWidth = pane == "files" ? fileWidth : panelWidth;
        var actualPaneWidth = overlay ? Math.Min(desiredPaneWidth, available - 48) : Math.Clamp(desiredPaneWidth, 280, Math.Max(280, available - leftWidth - 320));
        columns.ColumnDefinitions[0].Width = new GridLength(leftWidth);
        columns.ColumnDefinitions[2].Width = new GridLength(panelOpen && !overlay ? actualPaneWidth : 0);
        Grid.SetColumn(inspectorSurface, overlay ? 0 : 2); Grid.SetColumnSpan(inspectorSurface, overlay ? 3 : 1);
        inspectorSurface.Width = overlay ? actualPaneWidth : double.NaN; inspectorSurface.HorizontalAlignment = overlay ? HorizontalAlignment.Right : HorizontalAlignment.Stretch;
        Canvas.SetZIndex(inspectorSurface, overlay ? 25 : 0);
        if (panelResize != null)
        {
            Grid.SetColumn(panelResize, overlay ? 0 : 2); Grid.SetColumnSpan(panelResize, overlay ? 3 : 1);
            panelResize.HorizontalAlignment = overlay ? HorizontalAlignment.Right : HorizontalAlignment.Left;
            panelResize.Margin = overlay ? new Thickness(0, 0, actualPaneWidth - 3, 0) : new Thickness(0);
            Canvas.SetZIndex(panelResize, 26); panelResize.Visibility = panelOpen ? Visibility.Visible : Visibility.Collapsed;
        }
        foreach (var child in columns.Children.OfType<FrameworkElement>())
            if (ReferenceEquals(child, inspectorSurface) || ReferenceEquals(child, panelResize)) continue;
            else if (Grid.GetColumn(child) == 0) child.Visibility = sideOpen ? Visibility.Visible : Visibility.Collapsed;
            else if (Grid.GetColumn(child) == 2) child.Visibility = panelOpen ? Visibility.Visible : Visibility.Collapsed;
        inspectorSurface.Visibility = panelOpen ? Visibility.Visible : Visibility.Collapsed;
    }
    private Task ToggleSide() { sideOpen = !sideOpen; LayoutColumns(); SaveViewState(); return Task.CompletedTask; }
    private Task TogglePanel() { panelOpen = !panelOpen; LayoutColumns(); SaveViewState(); return Task.CompletedTask; }
    private async Task SetPane(string value)
    {
        pane = value; panelOpen = true; LayoutColumns(); DrawDetail(); SaveViewState();
        if (pane == "workspace") await Workspace();
    }
    private void Resizers()
    {
        for (int i = 0; i < 2; i++)
        {
            var left = i == 0; var thumb = new Thumb { Width = 5, HorizontalAlignment = left ? HorizontalAlignment.Right : HorizontalAlignment.Left,
                Style = (Style)Application.Current.Resources["RelicResizeThumbStyle"] };
            if (!left) panelResize = thumb;
            thumb.Loaded += (_, _) => ToolTipService.SetToolTip(thumb, T("panel.resize"));
            Grid.SetColumn(thumb, left ? 0 : 2); columns.Children.Add(thumb);
            thumb.DragDelta += (_, e) => { if (left) sideWidth = Math.Clamp(sideWidth + e.HorizontalChange, 180, 460); else if (pane == "files") fileWidth = Math.Clamp(fileWidth - e.HorizontalChange, 280, Math.Max(280, root.ActualWidth * .6)); else panelWidth = Math.Clamp(panelWidth - e.HorizontalChange, 280, Math.Max(280, root.ActualWidth * .6)); LayoutColumns(); };
            thumb.DragCompleted += (_, _) => SaveViewState();
        }
        root.SizeChanged += (_, _) => LayoutColumns();
    }
    private void PushHistory()
    {
        if (historyIndex >= 0 && history[historyIndex] == (org, member)) return;
        if (historyIndex + 1 < history.Count) history.RemoveRange(historyIndex + 1, history.Count - historyIndex - 1);
        history.Add((org, member)); historyIndex = history.Count - 1;
    }
    private async Task Navigate(int offset)
    {
        var target = historyIndex + offset; if (target < 0 || target >= history.Count) return;
        historyIndex = target; await Select(history[target].Org, history[target].Member, true);
    }
    private void MarkSeen()
    {
        var key = member.Length == 0 ? "group" : "member:" + member;
        seenMessages[org + "/" + key] = snap["chats"]?[key]?["last"].Text("id") ?? "";
    }
    private int Unread(string key)
    {
        var id = snap["chats"]?[key]?["last"].Text("id") ?? "";
        if (!long.TryParse(seenMessages.GetValueOrDefault(org + "/" + key), out var seen)) seen = 0;
        var count = snap["chats"]?[key].Rows("ids").Count(row => row is JsonArray ids && ids.Count > 1 && ids[1].Text() != "human" && long.TryParse(ids[0].Text(), out var number) && number > seen) ?? 0;
        return count;
    }
    private string LastLine(string key)
    {
        var last = snap["chats"]?[key]?["last"]; if (last == null) return "";
        var body = System.Text.RegularExpressions.Regex.Replace(last.Text("body"), @"^\[Relic auto-receipt\]\s*", "");
        body = System.Text.RegularExpressions.Regex.Replace(body, @"^>.*\n+", "", System.Text.RegularExpressions.RegexOptions.Multiline);
        return T(last.Text("type") == "receipt" ? "side.last_receipt" : "side.last_line", ("name", Display(last.Text("from"))), ("text", OverviewClip(body, 70)));
    }
    private Task FocusSearch() { sideOpen = true; LayoutColumns(); search.Focus(FocusState.Keyboard); search.SelectAll(); return Task.CompletedTask; }
    private void NavigationShortcuts()
    {
        AddShortcut(VirtualKey.K, VirtualKeyModifiers.Control, FocusSearch);
        AddShortcut(VirtualKey.B, VirtualKeyModifiers.Control, ToggleSide);
        AddShortcut(VirtualKey.B, VirtualKeyModifiers.Control | VirtualKeyModifiers.Menu, TogglePanel);
        AddShortcut(VirtualKey.Left, VirtualKeyModifiers.Menu, () => Navigate(-1)); AddShortcut(VirtualKey.Right, VirtualKeyModifiers.Menu, () => Navigate(1));
        AddShortcut(VirtualKey.L, VirtualKeyModifiers.Control | VirtualKeyModifiers.Shift, async () => { await Select(org); await TogglePlain(); });
        AddShortcut(VirtualKey.R, VirtualKeyModifiers.Control, Refresh);
        foreach (var (key, value) in new[] { (VirtualKey.Number1, "overview"), (VirtualKey.Number2, "workspace"), (VirtualKey.Number3, "files") })
            AddShortcut(key, VirtualKeyModifiers.Menu, () => pane == value && panelOpen ? TogglePanel() : SetPane(value));
        AddShortcut(VirtualKey.Escape, VirtualKeyModifiers.None, async () => { visibleDialog?.Hide(); transientFlyout?.Hide(); await StopVoice(); });
    }
    private TextBox? editing;
    private void BuildMenus()
    {
        menu.Items.Clear();
        AutomationProperties.SetName(menu, T("appbar.menus"));
        StyleNativeMenuBar();
        MenuBarItem Group(string title) { var group = NativeMenuGroup(T(title)); menu.Items.Add(group); return group; }
        void Item(MenuBarItem group, string text, Func<Task> action, bool enabled = true, string shortcut = "", bool check = false)
        {
            var item = new MenuFlyoutItem { Text = text, IsEnabled = enabled, KeyboardAcceleratorTextOverride = shortcut, Style = NativeMenuItemStyle(shortcut.Length > 0) };
            if (check) { var glyph = (ReferenceVectorIcon)ReferenceIcon("check", 14); glyph.Foreground = Accent; item.Tag = glyph; }
            item.Click += async (_, _) => { await Run(action); BuildMenus(); DrawToolbar(); }; group.Items.Add(item);
        }
        var file = Group("common.file");
        Item(file, T("appmenu.new_org"), CreateOrg); Item(file, T("appmenu.add_member"), AddMember, org.Length > 0);
        Item(file, T("appmenu.add_existing"), () => MemberDialog("existing"), org.Length > 0);
        var secretary = snap["org"].Text("secretary");
        Item(file, T(secretary.Length > 0 ? "appmenu.open_secretary" : "appmenu.set_up_secretary"), () => secretary.Length > 0 ? Select(org, secretary) : SecretarySetup(), org.Length > 0);
        file.Items.Add(NativeMenuSeparator());
        Item(file, T("appmenu.org_details"), () => Details(), org.Length > 0);
        Item(file, T("appmenu.open_data"), async () => { await api!.Post("/api/open", new { what = "data" }); });
        Item(file, T("appmenu.open_logs"), async () => { await api!.Post("/api/open", new { what = "logs" }); });
        file.Items.Add(NativeMenuSeparator()); Item(file, T("appmenu.settings"), Settings, shortcut: "Ctrl+,");
        var edit = Group("appmenu.edit");
        foreach (var (key, action) in new[] { ("appmenu.undo", "undo"), ("appmenu.redo", "redo"), ("appmenu.cut", "cut"), ("common.copy", "copy"), ("appmenu.paste", "paste"), ("appmenu.select_all", "all"), ("appmenu.quote_selection", "quote") })
        {
            if (action is "cut" or "quote") edit.Items.Add(NativeMenuSeparator());
            Item(edit, T(key), () => Edit(action), shortcut: action switch { "undo" => "Ctrl+Z", "redo" => "Ctrl+Y", "cut" => "Ctrl+X", "copy" => "Ctrl+C", "paste" => "Ctrl+V", "all" => "Ctrl+A", _ => "" });
        }
        Item(edit, T("page.search"), FocusSearch, shortcut: "Ctrl+K");
        var view = Group("appmenu.view"); Item(view, T("appmenu.sidebar"), ToggleSide, shortcut: "Ctrl+B", check: sideOpen); Item(view, T("page.panel"), TogglePanel, shortcut: "Ctrl+Alt+B", check: panelOpen);
        view.Items.Add(NativeMenuSeparator());
        int paneNumber = 0;
        foreach (var (id, key) in new[] { ("overview", "panel.overview"), ("workspace", "panel.workspace"), ("files", "common.file") }) Item(view, T("appmenu.pane", ("pane", T(key))), () => SetPane(id), shortcut: "Alt+" + ++paneNumber, check: panelOpen && pane == id);
        view.Items.Add(NativeMenuSeparator()); Item(view, T("appmenu.org_chart"), Chart, orgs.Count > 0);
        view.Items.Add(NativeMenuSeparator()); Item(view, T("appmenu.plain_group"), async () => { await Select(org); await TogglePlain(); }, org.Length > 0, shortcut: "Ctrl+Shift+L", check: plainMode); Item(view, T("appmenu.group_digest"), async () => { await Select(org); await ToggleDigest(); }, org.Length > 0, check: digestOpen);
        view.Items.Add(NativeMenuSeparator());
        foreach (var (value, key) in new[] { ("system", "common.theme_system"), ("light", "common.theme_light"), ("dark", "common.theme_dark") }) Item(view, T("appmenu.theme", ("theme", T(key))), () => SavePreferences(new() { ["theme"] = value }), check: preferences.Text("theme") == value);
        foreach (var (value, key) in new[] { ("small", "common.size_small"), ("medium", "common.size_medium"), ("large", "common.size_large") }) Item(view, T("appmenu.font_size", ("size", T(key))), () => SavePreferences(new() { ["font"] = value }), check: preferences.Text("font") == value);
        view.Items.Add(NativeMenuSeparator()); Item(view, T("appmenu.reload"), Refresh, shortcut: "Ctrl+R");
        var help = Group("appmenu.help"); Item(help, T("shortcuts.title"), Shortcuts); Item(help, T("common.voice_input"), () => SettingsScreen("voice")); Item(help, T("common.harness"), () => SettingsScreen("harness")); help.Items.Add(NativeMenuSeparator()); Item(help, T("appmenu.about"), () => SettingsScreen("about"));
        if (sendButton != null) { AutomationProperties.SetName(sendButton, T("common.send")); ToolTipService.SetToolTip(sendButton, T("composer.send_title")); }
        search.PlaceholderText = T("page.search"); AutomationProperties.SetName(search, T("page.search")); AutomationProperties.SetName(side, T("page.side")); AutomationProperties.SetName(stream, T("page.chat")); AutomationProperties.SetName(detail, T("page.panel"));
    }
    private async Task Edit(string action)
    {
        if (selectedRich?.SelectedText.Length > 0 && action is "copy" or "quote")
        {
            if (action == "copy") Copy(selectedRich.SelectedText); else Quote(T("common.quote"), selectedRich.SelectedText);
            return;
        }
        if (editing == null) { Note(T(action == "quote" ? "appmenu.quote_need_selection" : "appmenu.paste_need_field")); return; }
        editing.Focus(FocusState.Programmatic);
        switch (action)
        {
            case "undo": editing.Undo(); break; case "redo": editing.Redo(); break;
            case "cut": editing.CutSelectionToClipboard(); break; case "copy": editing.CopySelectionToClipboard(); break;
            case "paste": try { var clipboard = Clipboard.GetContent(); if (clipboard.Contains(StandardDataFormats.Text)) editing.SelectedText = await clipboard.GetTextAsync(); } catch { Note(T("appmenu.paste_failed")); } break;
            case "all": editing.SelectAll(); break;
            case "quote": if (editing.SelectedText.Length == 0) Note(T("appmenu.quote_need_selection")); else Quote(T("common.quote"), editing.SelectedText); break;
        }
    }
    private Task Shortcuts()
    {
        var box = new StackPanel { Width = Math.Min(520, Math.Max(0, root.ActualWidth - 32)), Padding = new Thickness(22), Spacing = 14, UseLayoutRounding = false };
        var title = OverviewText(T("shortcuts.title"), 17, weight: 650); title.IsTextSelectionEnabled = false; box.Children.Add(title);
        var keys = new Grid { ColumnSpacing = 16, RowSpacing = 9, Margin = new Thickness(0, 4, 0, 0) };
        keys.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); keys.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        foreach (var (key, text) in new[] { ("Ctrl+B", "shortcuts.toggle_sidebar"), ("Ctrl+Alt+B", "shortcuts.toggle_panel"), ("Alt+1 / 2 / 3", "shortcuts.panes"), ("Alt+← / Alt+→", "shortcuts.back_forward"), ("Ctrl+K", "page.search"), ("Ctrl+Shift+L", "appmenu.plain_group"), ("Ctrl+,", "common.settings"), ("Enter / Shift+Enter", "shortcuts.send_newline"), ("@", "shortcuts.mention"), ("Esc", "shortcuts.close") })
        {
            var row = keys.RowDefinitions.Count; keys.RowDefinitions.Add(new() { Height = GridLength.Auto });
            var cap = NativeShortcutCap(key); Grid.SetRow(cap, row); keys.Children.Add(cap);
            var label = OverviewText(T(text), 13); label.Foreground = Paint("5A5853", "B8B5AE"); label.IsTextSelectionEnabled = false; label.VerticalAlignment = VerticalAlignment.Center;
            Grid.SetColumn(label, 1); Grid.SetRow(label, row); keys.Children.Add(label);
        }
        box.Children.Add(keys);
        var dialog = new ContentDialog { XamlRoot = root.XamlRoot, Content = box };
        AutomationProperties.SetName(dialog, T("shortcuts.title"));
        var ok = NativeShortcutConfirm(T("shortcuts.ok")); ok.Click += (_, _) => dialog.Hide(); box.Children.Add(ok);
        dialog.Opened += (_, _) =>
        {
            if (DialogPart<ContentPresenter>(dialog, "Content") is { } presenter) { presenter.Margin = new Thickness(0); presenter.Padding = new Thickness(0); }
            if (DialogPart<Border>(dialog, "BackgroundElement") is { } background) background.Padding = new Thickness(0);
            if (DialogPart<ScrollViewer>(dialog, "ContentScrollViewer") is { } scroll) scroll.Padding = new Thickness(0);
            if (DialogPart<Grid>(dialog, "CommandSpace") is { } commands) commands.Visibility = Visibility.Collapsed;
        };
        return Dialog(dialog);
    }
}
