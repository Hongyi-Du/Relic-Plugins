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
        var select = Choice(workspaceBody, "work.whose", candidates.Select(m => (m.Text("name"), m.Text("display")))); SetChoice(select, workspaceMember);
        select.SelectionChanged += async (_, _) => { workspaceMember = Value(select); directory = ""; await Run(Workspace); };
        var ws = await api!.Get(PathFor("/workspace?member=" + Client.Segment(workspaceMember)));
        if (epoch != workspaceEpoch || org != selectedOrg || pane != "workspace") return;
        var folder = ws.Text("folder");
        if (folder.Length == 0) { workspaceBody.Children.Add(Text(T("work.no_folder", ("name", Display(workspaceMember))))); return; }
        workspaceBody.Children.Add(Text(folder));
        workspaceBody.Children.Add(Button(T("work.open_in_explorer"), () => OpenDefault(folder, true)));
        if (!ws.Flag("exists")) { workspaceBody.Children.Add(Text(T("work.folder_missing"))); return; }
        var git = ws["git"];
        if (git != null)
        {
            workspaceBody.Children.Add(Text(T("work.git_changes") + " · " + git.Text("branch"), 18));
            if (git.Rows("changes").Count == 0) workspaceBody.Children.Add(Text(T("work.no_changes")));
            foreach (var change in git.Rows("changes")) workspaceBody.Children.Add(Button(change.Text("status") + "  " + change.Text("path"), () => OpenFile(System.IO.Path.Combine(git.Text("root"), change.Text("path")))));
        }
        if (ws.Rows("recent").Count > 0)
        {
            workspaceBody.Children.Add(Text(T("work.recent_files"), 18));
            foreach (var recent in ws.Rows("recent")) workspaceBody.Children.Add(Button(recent.Text("path") + " · " + recent.Text("tool") + " · " + When(recent.Text("at")), () => OpenFile(recent.Text("path"))));
        }
        workspaceBody.Children.Add(Text(T("work.files"), 18));
        await Files(directory.Length > 0 ? directory : folder, epoch);
    }
    private async Task Files(string path, int epoch)
    {
        var list = await api!.Get("/api/fs/list?path=" + Client.Segment(path));
        if (epoch != workspaceEpoch || pane != "workspace") return;
        directory = list.Text("path"); workspaceBody.Children.Add(Text(directory, 12));
        if (list.Text("parent").Length > 0) workspaceBody.Children.Add(Button("↑ " + list.Text("parent"), async () => { directory = list.Text("parent"); await Workspace(); }));
        if (list.Rows("entries").Count == 0) workspaceBody.Children.Add(Text(T("work.empty_dir")));
        foreach (var entry in list.Rows("entries")) workspaceBody.Children.Add(FileEntry(entry!, epoch));
        workspaceBody.Children.Add(Text(T("work.file_count", ("n", list.Rows("entries").Count)), 12));
        if (list.Flag("more")) workspaceBody.Children.Add(Text(T("work.list_limit"), 12));
    }
    private UIElement FileEntry(JsonNode entry, int epoch)
    {
        if (!entry.Flag("dir")) return Button(entry.Text("name") + " · " + Bytes(entry.Text("size")), () => OpenFile(entry.Text("path")));
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
            filePath = path; fileLine = line; fileData = data; pane = "files"; DrawDetail(); SaveViewState();
        }
        catch (Exception ex) { Note(T("file.open_failed", ("error", ex.Message))); }
    }
    private async Task OpenDefault(string path, bool folder = false)
    {
        try
        {
            // Only a direct person action reaches the system shell.
            var opened = folder ? await Launcher.LaunchFolderAsync(await Windows.Storage.StorageFolder.GetFolderFromPathAsync(path))
                : await Launcher.LaunchFileAsync(await Windows.Storage.StorageFile.GetFileFromPathAsync(path));
            if (!opened) Note(T("file.open_failed", ("error", path)));
        }
        catch (Exception ex) { Note(T("file.open_failed", ("error", ex.Message))); }
    }
    private void DrawFile()
    {
        if (filePath.Length == 0) { detail.Children.Add(Text(T("file.empty"))); return; }
        detail.Children.Add(Text(fileData.Text("name"), 20)); detail.Children.Add(Text(filePath, 12));
        detail.Children.Add(Button(T("file.copy_path"), () => { Copy(filePath); return Task.CompletedTask; }));
        detail.Children.Add(Button(T("file.open_default"), () => OpenDefault(filePath)));
        detail.Children.Add(Text(Bytes(fileData.Text("size")) + " · " + T("file.modified", ("when", When(fileData.Text("mtime")))), 12));
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
            var mode = Choice(detail, "file.preview", [("preview", T("file.preview")), ("source", T("file.source"))]); SetChoice(mode, fileMode);
            mode.SelectionChanged += (_, _) => { fileMode = Value(mode); DrawDetail(); };
            if (fileMode == "preview") { detail.Children.Add(Rich(fileData.Text("text"))); return; }
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
