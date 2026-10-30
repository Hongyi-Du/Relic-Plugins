using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Documents;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Relic.Core;
using System.Globalization;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private string workspaceMember = "", directory = "", filePath = "", fileMode = "preview", workspaceIdentity = "";
    private int fileLine, workspaceEpoch, fileEpoch;
    private JsonNode? fileData;
    private readonly StackPanel workspaceBody = new() { Spacing = 0 };
    private readonly HashSet<string> workspaceOpenFolders = new(StringComparer.OrdinalIgnoreCase);
    private static readonly HashSet<string> WorkspaceHiddenDirectories = new(StringComparer.Ordinal) { ".git", "node_modules", "__pycache__", ".venv", ".mypy_cache", ".pytest_cache" };

    private void DrawWorkspace()
    {
        detail.Padding = new Thickness(0); detail.Spacing = 0; detail.Children.Add(workspaceBody);
    }

    private async Task Workspace()
    {
        var epoch = ++workspaceEpoch; var selectedOrg = org;
        workspaceBody.Children.Clear();
        if (org.Length == 0) return;
        var candidates = snap.Rows("members").Where(m => m.Text("surface") != "chat").ToArray();
        if (!candidates.Any(m => m.Text("name") == workspaceMember))
            workspaceMember = candidates.FirstOrDefault(m => m.Text("name") == member).Text("name");
        if (workspaceMember.Length == 0) workspaceMember = candidates.FirstOrDefault().Text("name");
        var identity = org + "/" + workspaceMember;
        if (workspaceIdentity != identity) { workspaceIdentity = identity; workspaceOpenFolders.Clear(); }
        var picker = WorkspaceBlock(workspaceBody, T("work.whose"));
        var people = new ActionRow { Spacing = 5 };
        foreach (var candidate in candidates)
        {
            var id = candidate.Text("name"); var label = candidate.Text("display").Length > 0 ? candidate.Text("display") : id;
            var selected = id == workspaceMember;
            var contents = new Grid { ColumnSpacing = 6 };
            contents.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); contents.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
            contents.Children.Add(Avatar(candidate.Text("avatar"), label, 20));
            var name = WorkspaceLabel(label, 12.5, weight: selected ? (ushort)600 : (ushort)400); name.Foreground = selected ? Ink : Paint("5A5853", "B8B5AE"); name.VerticalAlignment = VerticalAlignment.Center;
            Grid.SetColumn(name, 1); contents.Children.Add(name);
            var pick = WorkspaceRow(contents, async () => { workspaceMember = id; directory = ""; await Workspace(); });
            pick.Height = 28; pick.Padding = new Thickness(3, 0, 10, 0); pick.CornerRadius = new CornerRadius(14); pick.BorderThickness = new Thickness(1);
            pick.BorderBrush = selected ? OverviewAlpha(Accent, .5) : Paint("DEDBD4", "3A3936");
            pick.Background = selected ? WorkspaceMix(Accent, Paint("FFFFFF", "252523"), .1) : Paint("FFFFFF", "252523");
            pick.HorizontalAlignment = HorizontalAlignment.Left;
            ToolTipService.SetToolTip(pick, id + (candidate.Text("role").Length > 0 ? " · " + candidate.Text("role") : ""));
            people.Children.Add(pick);
        }
        picker.Children.Add(people);
        if (workspaceMember.Length == 0) { WorkspaceEmptyBlock(workspaceBody, T("work.no_members")); return; }
        var loading = WorkspaceEmptyBlock(workspaceBody, T("common.loading"));
        JsonNode ws;
        try { ws = await api!.Get(PathFor("/workspace?member=" + Client.Segment(workspaceMember))); }
        catch (Exception ex)
        {
            if (epoch != workspaceEpoch || org != selectedOrg || pane != "workspace") return;
            workspaceBody.Children.Remove(loading); WorkspaceEmptyBlock(workspaceBody, T("common.load_failed", ("error", ex.Message))); return;
        }
        if (epoch != workspaceEpoch || org != selectedOrg || pane != "workspace") return;
        workspaceBody.Children.Remove(loading);
        var folder = ws.Text("folder");
        if (folder.Length == 0) { WorkspaceEmptyBlock(workspaceBody, T("work.no_folder", ("name", Display(workspaceMember)))); return; }
        var folderBlock = WorkspaceBlock(workspaceBody, T("common.work_folder"), OverviewLink(T("work.open_in_explorer"), () => OpenDefault(folder, true), "open", true));
        var folderName = WorkspaceText(folder, 12, 18.6); folderName.FontFamily = new FontFamily("Cascadia Code"); folderName.Foreground = Paint("5A5853", "B8B5AE");
        folderBlock.Children.Add(folderName);
        if (!ws.Flag("exists")) { folderBlock.Children.Add(WorkspaceEmpty(T("work.folder_missing"))); return; }
        var git = ws["git"]; var basePath = (git.Text("root").Length > 0 ? git.Text("root") : folder).Replace('\\', '/').TrimEnd('/');
        string Relative(string path)
        {
            var normalized = path.Replace('\\', '/');
            return normalized.StartsWith(basePath + "/", StringComparison.OrdinalIgnoreCase) ? normalized[(basePath.Length + 1)..] : path;
        }
        if (git != null)
        {
            var changes = git.Rows("changes");
            var block = WorkspaceBlock(workspaceBody, T("work.git_changes") + (git.Text("branch").Length > 0 ? " · " + git.Text("branch") : ""), changes.Count > 0 ? WorkspaceText(T("work.file_count", ("n", changes.Count)), 12, 19.2, true) : null);
            if (changes.Count == 0) block.Children.Add(WorkspaceEmpty(T("work.no_changes")));
            foreach (var change in changes.Take(60))
            {
                var status = change.Text("status"); var code = status == "??" ? "U" : status.Length > 0 ? status[..1] : "";
                var badge = WorkspaceText(code, 11, 17.6, weight: 600); badge.FontFamily = new FontFamily("Cascadia Code"); badge.Width = 18; badge.TextAlignment = TextAlignment.Center;
                badge.Foreground = code is "M" or "R" ? Paint("B7791F", "E2B15A") : code is "A" or "U" ? Paint("3E9B5E", "6CC287") : code == "D" ? Paint("C2412D", "EE8A78") : Ink;
                ToolTipService.SetToolTip(badge, status);
                var path = change.Text("path"); var title = WorkspaceLabel(Relative(path));
                if (status.Contains('D')) { title.Foreground = Muted; title.TextDecorations = Windows.UI.Text.TextDecorations.Strikethrough; }
                var row = WorkspaceRow(WorkspaceFileRow(badge, title), () => OpenFile(path)); row.IsEnabled = !status.Contains('D');
                ToolTipService.SetToolTip(row, path); block.Children.Add(row);
            }
            if (changes.Count > 60) block.Children.Add(WorkspaceEmpty(T("common.more_items", ("n", changes.Count - 60))));
        }
        if (ws.Rows("recent").Count > 0)
        {
            var block = WorkspaceBlock(workspaceBody, T("work.recent_files"));
            foreach (var recent in ws.Rows("recent").Take(15))
            {
                var path = recent.Text("path"); var shown = Relative(path).Replace('\\', '/'); var cut = shown.LastIndexOf('/');
                var label = WorkspaceLabel(""); label.Inlines.Add(new Run { Text = shown[(cut + 1)..] });
                if (cut > 0) label.Inlines.Add(new Run { Text = "  " + shown[..cut], Foreground = Paint("B8B5AF", "5F5D58") });
                var when = WorkspaceText(Ago(recent.Text("at")), 11, 17.6, true); when.Margin = new Thickness(8, 0, 0, 0);
                var row = WorkspaceRow(WorkspaceFileRow(WorkspaceIcon("file", 14), label, when), () => OpenFile(path)); ToolTipService.SetToolTip(row, path); block.Children.Add(row);
            }
        }
        var files = WorkspaceBlock(workspaceBody, T("work.files"));
        var tree = new StackPanel { Margin = new Thickness(-6, 0, -6, 0) }; files.Children.Add(tree); directory = folder;
        await FillWorkspaceTree(tree, folder, 0, epoch);
    }

    private async Task FillWorkspaceTree(StackPanel target, string path, int depth, int epoch)
    {
        JsonNode data;
        try { data = await api!.Get("/api/fs/list?path=" + Client.Segment(path)); }
        catch (Exception ex) { if (epoch == workspaceEpoch) target.Children.Add(WorkspaceTreeEmpty(ex.Message, depth)); return; }
        if (epoch != workspaceEpoch || pane != "workspace") return;
        var entries = data.Rows("entries").Where(entry => !(entry.Flag("dir") && WorkspaceHiddenDirectories.Contains(entry.Text("name")))).ToArray();
        if (entries.Length == 0) target.Children.Add(WorkspaceTreeEmpty(T("work.empty_dir"), depth));
        foreach (var entry in entries)
        {
            var pathName = entry.Text("path"); var isFolder = entry.Flag("dir");
            var children = new StackPanel { Visibility = workspaceOpenFolders.Contains(pathName) ? Visibility.Visible : Visibility.Collapsed };
            var loaded = false;
            var chevron = isFolder ? WorkspaceIcon("chev", 12) : new Grid { Width = 12 };
            if (isFolder) { chevron.RenderTransformOrigin = new(.5, .5); chevron.RenderTransform = new RotateTransform { Angle = children.Visibility == Visibility.Visible ? 90 : 0 }; }
            var icons = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6, VerticalAlignment = VerticalAlignment.Center };
            icons.Children.Add(chevron); icons.Children.Add(WorkspaceIcon(isFolder ? "folder" : "file", 14));
            var row = WorkspaceRow(WorkspaceFileRow(icons, WorkspaceLabel(entry.Text("name"))), async () =>
            {
                if (!isFolder) { await OpenFile(pathName); return; }
                if (epoch != workspaceEpoch) return;
                var open = children.Visibility != Visibility.Visible; children.Visibility = open ? Visibility.Visible : Visibility.Collapsed;
                ((RotateTransform)chevron.RenderTransform).Angle = open ? 90 : 0;
                if (open) workspaceOpenFolders.Add(pathName); else workspaceOpenFolders.Remove(pathName);
                if (open && !loaded) { loaded = true; await FillWorkspaceTree(children, pathName, depth + 1, epoch); }
            });
            row.Padding = new Thickness(depth * 14 + 4, 2, 6, 2); ToolTipService.SetToolTip(row, pathName); target.Children.Add(row);
            if (isFolder)
            {
                target.Children.Add(children);
                if (children.Visibility == Visibility.Visible) { loaded = true; await FillWorkspaceTree(children, pathName, depth + 1, epoch); }
            }
        }
        if (data.Flag("more")) target.Children.Add(WorkspaceTreeEmpty(T("work.list_limit"), depth));
    }

    private static string Bytes(string value) => double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out var size)
        ? size < 1024 ? size.ToString("0.################", CultureInfo.InvariantCulture) + " B" : size < 1048576 ? (size / 1024).ToString("0.0", CultureInfo.InvariantCulture) + " KB" : (size / 1048576).ToString("0.0", CultureInfo.InvariantCulture) + " MB" : value;

    private async Task OpenFile(string path, int line = 0)
    {
        var epoch = ++fileEpoch;
        filePath = path; fileLine = line; fileMode = "preview"; fileData = null; pane = "files"; panelOpen = true;
        LayoutColumns(); DrawDetail(); DrawToolbar(); SaveViewState();
        JsonNode data;
        try { data = await api!.Get("/api/fs/read?path=" + Client.Segment(path)); }
        catch (Exception ex) { data = new JsonObject { ["error"] = ex.Message }; }
        if (epoch != fileEpoch || filePath != path) return;
        fileData = data;
        if (pane == "files" && panelOpen) DrawDetail();
    }

    private async Task OpenDefault(string path, bool folder = false)
    {
        try { await api!.Post("/api/fs/open", new { path }); }
        catch (Exception ex) { Note(ex.Message); }
    }

    private void DrawFile()
    {
        detail.Padding = new Thickness(0); detail.Spacing = 0;
        if (filePath.Length == 0) { WorkspaceEmptyBlock(detail, T("file.empty")); return; }
        var name = filePath.Replace('\\', '/').Split('/').Last();
        var header = WorkspaceFileHeader(name); detail.Children.Add(header); WorkspaceStickyHeader(header);
        if (fileData == null) { WorkspaceEmptyBlock(detail, T("common.loading")); return; }
        if (fileData.Text("error").Length > 0) { WorkspaceEmptyBlock(detail, T("file.open_failed", ("error", fileData.Text("error")))); return; }
        var meta = new Grid { ColumnSpacing = 10, Padding = new Thickness(14, 6, 14, 6) };
        meta.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); meta.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        meta.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); meta.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        meta.Children.Add(WorkspaceText(Bytes(fileData.Text("size")), 11.5, 18.4, true));
        var modifiedAt = fileData.Text("mtime");
        if (double.TryParse(modifiedAt, NumberStyles.Float, CultureInfo.InvariantCulture, out var seconds)) modifiedAt = DateTimeOffset.FromUnixTimeMilliseconds((long)(seconds * 1000)).ToString("O", CultureInfo.InvariantCulture);
        var modified = WorkspaceText(T("file.modified", ("when", Ago(modifiedAt))), 11.5, 18.4, true); Grid.SetColumn(modified, 1); meta.Children.Add(modified);
        if (fileData.Flag("truncated")) { var notice = WorkspaceText(T("file.truncated"), 11.5, 18.4, true); Grid.SetColumn(notice, 2); meta.Children.Add(notice); }
        detail.Children.Add(meta);
        if (fileData.Text("kind") == "image")
        {
            var url = fileData.Text("url"); if (url.Length == 0) url = "/api/fs/raw?path=" + Client.Segment(filePath);
            var bitmap = new BitmapImage(new Uri("http://127.0.0.1:" + preferences.Text("port") + url));
            var preview = new Image { Source = bitmap, Stretch = Stretch.Uniform, HorizontalAlignment = HorizontalAlignment.Center };
            AutomationProperties.SetName(preview, name);
            var surface = new Border { Child = preview, BorderBrush = Line, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(8), HorizontalAlignment = HorizontalAlignment.Center };
            WorkspaceCheckerboard(surface);
            var frame = new Grid { Padding = new Thickness(16) }; frame.Children.Add(surface);
            void FitImage() { if (bitmap.PixelWidth > 0 && frame.ActualWidth > 0) surface.Width = Math.Min(bitmap.PixelWidth + 2, Math.Max(0, frame.ActualWidth - 32)); }
            bitmap.ImageOpened += (_, _) => FitImage(); frame.SizeChanged += (_, _) => FitImage(); detail.Children.Add(frame); return;
        }
        if (fileData.Text("kind") == "binary") { WorkspaceEmptyBlock(detail, T("file.binary")); return; }
        if (fileData.Text("kind") == "markdown")
        {
            var modes = DetailsTabs(new[] { ("preview", T("file.preview")), ("source", T("file.source")) }, fileMode, value => { fileMode = value; DrawDetail(); return Task.CompletedTask; });
            modes.HorizontalAlignment = HorizontalAlignment.Right; Grid.SetColumn(modes, 3); meta.Children.Add(modes);
            if (fileMode == "preview") { detail.Children.Add(new Border { Child = Rich(fileData.Text("text"), true), Padding = new Thickness(18, 12, 18, 24), Background = Paint("FFFFFF", "1F1F1E"), BorderBrush = Line, BorderThickness = new Thickness(0, 1, 0, 0) }); return; }
        }
        var text = fileData.Text("text");
        if (fileData.Text("kind") == "json" && fileData["display_text"] != null) text = fileData.Text("display_text");
        DrawFileCode(text, fileLine);
    }
}
