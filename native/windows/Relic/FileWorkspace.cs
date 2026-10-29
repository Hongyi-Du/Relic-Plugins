using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Relic.Core;
using System.Text.Json.Nodes;
using Windows.System;

namespace Relic;

public sealed partial class MainWindow
{
    private string workspaceMember = "", directory = "", filePath = "", fileMode = "preview";
    private int fileLine, workspaceEpoch;
    private JsonNode fileData = new JsonObject();
    private readonly StackPanel workspaceBody = new() { Spacing = 10 };
    private async Task Workspace()
    {
        var epoch = ++workspaceEpoch; var selectedOrg = org;
        workspaceBody.Children.Clear();
        if (org.Length == 0) return;
        var candidates = snap.Rows("members").Where(m => m.Text("harness") != "chatgpt").ToArray();
        if (!candidates.Any(m => m.Text("name") == workspaceMember)) workspaceMember = candidates.FirstOrDefault(m => m.Text("name") == member).Text("name");
        if (workspaceMember.Length == 0) workspaceMember = candidates.FirstOrDefault().Text("name");
        if (workspaceMember.Length == 0) { workspaceBody.Children.Add(Text(T("work.no_members"))); return; }
        workspaceBody.Children.Add(Quiet(T("work.whose"), 11)); var people = new ActionRow();
        foreach (var candidate in candidates) { var pick = QuietButton(candidate.Text("display"), async () => { workspaceMember = candidate.Text("name"); directory = ""; await Workspace(); }); pick.BorderThickness = new Thickness(1); pick.BorderBrush = candidate.Text("name") == workspaceMember ? Accent : Line; pick.CornerRadius = new CornerRadius(14); people.Children.Add(pick); } workspaceBody.Children.Add(people);
        var ws = await api!.Get(PathFor("/workspace?member=" + Client.Segment(workspaceMember)));
        if (epoch != workspaceEpoch || org != selectedOrg || pane != "workspace") return;
        var folder = ws.Text("folder");
        if (folder.Length == 0) { workspaceBody.Children.Add(Text(T("work.no_folder", ("name", Display(workspaceMember))))); return; }
        workspaceBody.Children.Add(TwoColumns(Quiet(T("member.work_folder"), 11), IconButton("\uE8A7", "work.open_in_explorer", () => OpenDefault(folder, true)))); workspaceBody.Children.Add(Quiet(folder, 12));
        if (!ws.Flag("exists")) { workspaceBody.Children.Add(Text(T("work.folder_missing"))); return; }
        var git = ws["git"];
        if (git != null)
        {
            workspaceBody.Children.Add(Quiet(T("work.git_changes") + " · " + git.Text("branch"), 12));
            if (git.Rows("changes").Count == 0) workspaceBody.Children.Add(Text(T("work.no_changes")));
            foreach (var change in git.Rows("changes")) workspaceBody.Children.Add(QuietButton(change.Text("status") + "  " + change.Text("path"), () => OpenFile(System.IO.Path.Combine(git.Text("root"), change.Text("path")))));
        }
        if (ws.Rows("recent").Count > 0)
        {
            workspaceBody.Children.Add(Quiet(T("work.recent_files"), 12));
            foreach (var recent in ws.Rows("recent")) { var recentFile = QuietButton(System.IO.Path.GetFileName(recent.Text("path")) + " · " + recent.Text("tool"), () => OpenFile(recent.Text("path"))); ToolTipService.SetToolTip(recentFile, recent.Text("path") + " · " + When(recent.Text("at"))); workspaceBody.Children.Add(recentFile); }
        }
        workspaceBody.Children.Add(Quiet(T("work.files"), 12));
        await Files(directory.Length > 0 ? directory : folder, epoch);
    }
    private async Task Files(string path, int epoch)
    {
        var list = await api!.Get("/api/fs/list?path=" + Client.Segment(path));
        if (epoch != workspaceEpoch || pane != "workspace") return;
        directory = list.Text("path");
        if (list.Text("parent").Length > 0) { var parent = QuietButton("↑  " + System.IO.Path.GetFileName(list.Text("parent")), async () => { directory = list.Text("parent"); await Workspace(); }); ToolTipService.SetToolTip(parent, list.Text("parent")); workspaceBody.Children.Add(parent); }
        if (list.Rows("entries").Count == 0) workspaceBody.Children.Add(Text(T("work.empty_dir")));
        foreach (var entry in list.Rows("entries")) workspaceBody.Children.Add(FileEntry(entry!, epoch));
        workspaceBody.Children.Add(Text(T("work.file_count", ("n", list.Rows("entries").Count)), 12));
        if (list.Flag("more")) workspaceBody.Children.Add(Text(T("work.list_limit"), 12));
    }
    private UIElement FileEntry(JsonNode entry, int epoch)
    {
        if (!entry.Flag("dir")) { var file = QuietButton("", () => OpenFile(entry.Text("path"))); var row = new Grid { ColumnSpacing = 8 }; row.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); row.Children.Add(Glyph("\uE8A5", 13)); var name = Ellipsis(entry.Text("name")); Grid.SetColumn(name, 1); row.Children.Add(name); file.Content = row; file.HorizontalAlignment = HorizontalAlignment.Stretch; file.HorizontalContentAlignment = HorizontalAlignment.Stretch; ToolTipService.SetToolTip(file, entry.Text("path") + " · " + Bytes(entry.Text("size"))); return file; }
        var children = new StackPanel { Spacing = 3, Margin = new Thickness(12, 0, 0, 0) };
        var folder = new Expander { Header = entry.Text("name"), Content = children, HorizontalAlignment = HorizontalAlignment.Stretch };
        folder.Expanding += async (_, _) => await Run(async () =>
        {
            if (children.Children.Count > 0 || epoch != workspaceEpoch) return;
            var data = await api!.Get("/api/fs/list?path=" + Client.Segment(entry.Text("path")));
            foreach (var child in data.Rows("entries")) children.Children.Add(FileEntry(child!, epoch));
            if (data.Rows("entries").Count == 0) children.Children.Add(Text(T("work.empty_dir")));
            if (data.Flag("more")) children.Children.Add(Text(T("work.list_limit")));
        }); return folder;
    }
    private static string Bytes(string value) => double.TryParse(value, out var size) ? size < 1024 ? $"{size:0} B" : size < 1048576 ? $"{size / 1024:0.#} KB" : $"{size / 1048576:0.#} MB" : value;
    private async Task OpenFile(string path, int line = 0)
    {
        try
        {
            var data = await api!.Get("/api/fs/read?path=" + Client.Segment(path));
            filePath = path; fileLine = line; fileData = data; pane = "files"; panelOpen = true; LayoutColumns(); DrawDetail(); SaveViewState();
        }
        catch (Exception ex) { Note(T("file.open_failed", ("error", ex.Message))); }
    }
    private async Task OpenDefault(string path, bool folder = false)
    {
        try
        {
            await api!.Post("/api/fs/open", new { path });
        }
        catch (Exception ex) { Note(T("file.open_failed", ("error", ex.Message))); }
    }
    private void DrawFile()
    {
        if (filePath.Length == 0) { detail.Children.Add(Text(T("file.empty"))); return; }
        var actions = new ActionRow { Spacing = 2 }; actions.Children.Add(IconButton("\uE8C8", "file.copy_path", () => { Copy(filePath); return Task.CompletedTask; })); actions.Children.Add(IconButton("\uE8A7", "file.open_default", () => OpenDefault(filePath)));
        var name = Stack(Heading(fileData.Text("name"), 14), Ellipsis(filePath, 11)); name.Spacing = 2; detail.Children.Add(TwoColumns(name, actions));
        var information = Quiet(Bytes(fileData.Text("size")) + " · " + T("file.modified", ("when", Ago(fileData.Text("mtime")))), 11); detail.Children.Add(information);
        if (fileData.Flag("truncated")) detail.Children.Add(Text(T("file.truncated")));
        if (fileData.Text("kind") == "image")
        {
            var url = fileData.Text("url");
            if (url.Length == 0) url = "/api/fs/raw?path=" + Client.Segment(filePath);
            detail.Children.Add(new Image { Source = new BitmapImage(new Uri("http://127.0.0.1:" + preferences.Text("port") + url)), Stretch = Stretch.Uniform }); return;
        }
        if (fileData.Text("kind") == "binary") { detail.Children.Add(Text(T("file.binary"))); return; }
        if (fileData.Text("kind") == "markdown")
        {
            var modes = new SelectorBar { HorizontalAlignment = HorizontalAlignment.Right }; foreach (var (id, key) in new[] { ("preview", "file.preview"), ("source", "file.source") }) modes.Items.Add(new SelectorBarItem { Text = T(key), Tag = id, IsSelected = fileMode == id, FontSize = 12 });
            modes.SelectionChanged += (_, _) => { if (modes.SelectedItem?.Tag is string value && fileMode != value) { fileMode = value; DrawDetail(); } }; detail.Children.Remove(information); detail.Children.Add(TwoColumns(information, modes));
            if (fileMode == "preview") { detail.Children.Add(Card(Rich(fileData.Text("text")))); return; }
        }
        var text = fileData.Text("text");
        if (fileData.Text("kind") == "json") { try { text = JsonNode.Parse(text)?.ToJsonString(new() { WriteIndented = true }) ?? text; } catch { } }
        var lines = text.Replace("\r\n", "\n").Split('\n');
        var source = new StackPanel();
        for (int i = 0; i < Math.Min(6000, lines.Length); i++)
        {
            var row = Text($"{i + 1,5}  {lines[i]}", 12); row.FontFamily = new FontFamily("Consolas");
            if (i + 1 == fileLine) { row.Foreground = new SolidColorBrush(Colors.DarkOrange); row.Loaded += (_, _) => row.StartBringIntoView(); }
            source.Children.Add(row);
        }
        detail.Children.Add(source);
        if (lines.Length > 6000) detail.Children.Add(Text(T("file.lines_shown", ("max", 6000), ("total", lines.Length))));
    }
}
