using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Relic.Core;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using Windows.Graphics.Imaging;
using Windows.Storage.Streams;

namespace Relic;

public sealed partial class MainWindow
{
    private bool VisualCaptureEnabled => Environment.GetEnvironmentVariable("GITHUB_ACTIONS") == "true" && !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("RELIC_VISUAL_MANIFEST"));
    private bool visualCaptureStarted;
    private void VisualStartup(string stage)
    {
        if (!VisualCaptureEnabled) return;
        System.IO.File.WriteAllText(System.IO.Path.Combine(System.IO.Path.GetDirectoryName(Environment.GetEnvironmentVariable("RELIC_VISUAL_MANIFEST"))!, "current-case.txt"), "startup: " + stage);
        Console.WriteLine("Relic visual startup: " + stage);
    }
    private void VisualStartupFailed(Exception error)
    {
        if (!VisualCaptureEnabled || visualCaptureStarted) return;
        System.IO.File.WriteAllText(System.IO.Path.Combine(System.IO.Path.GetDirectoryName(Environment.GetEnvironmentVariable("RELIC_VISUAL_MANIFEST"))!, "complete.json"), System.Text.Json.JsonSerializer.Serialize(new { errors = new[] { error.ToString() }, count = 0 }));
    }

    private async Task CaptureVisuals()
    {
        visualCaptureStarted = true;
        var path = Environment.GetEnvironmentVariable("RELIC_VISUAL_MANIFEST")!;
        var failures = new List<string>(); var count = 0;
        try
        {
            var manifest = JsonNode.Parse(await System.IO.File.ReadAllTextAsync(path))!; var fixture = manifest["fixture"]!;
            foreach (var shot in manifest.Rows("cases"))
            {
                await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(System.IO.Path.GetDirectoryName(path)!, "current-case.txt"), shot.Text("id"));
                try
                {
                    if (visibleDialog != null) { visibleDialog.Hide(); if (visibleDialogTask != null) await visibleDialogTask; }
                    transientFlyout?.Hide(); foreach (var popup in Microsoft.UI.Xaml.Media.VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot)) popup.IsOpen = false;
                    await StopVoice(); plainTimer.Stop(); error.IsOpen = false;
                    AppWindow.ResizeClient(new(int.Parse(shot.Text("width")), int.Parse(shot.Text("height")))); AppWindow.Move(new(0, 0));
                    SetForegroundWindow(WinRT.Interop.WindowNative.GetWindowHandle(this));
                    // Previous menu cases leave the desktop pointer over the
                    // toolbar. Move it off-window so hover tooltips cannot mask
                    // an unrelated screen in the next capture.
                    SetCursorPos(1900, 1040);
                    sideWidth = 276; panelWidth = 320; fileWidth = 460; sideOpen = true; panelOpen = int.Parse(shot.Text("width")) > 1180;
                    pane = "overview"; threadId = ""; plainMode = false; digestOpen = false; folded.Clear(); search.Text = ""; editor.Text = ""; ClearQuote(); drafts.Clear(); recipientNames.Clear(); recipientNames.Add("all");
                    await Select(fixture.Text("org")); LayoutColumns();
                    var scene = shot.Text("scene"); Task? dialog = null;
                    if (scene.StartsWith("settings-")) dialog = SettingsScreen(scene[9..]);
                    else if (scene.StartsWith("file-")) await OpenFile(fixture["files"].Text(scene[5..]), scene == "file-code" ? 2 : 0);
                    else if (scene.StartsWith("menu-"))
                    {
                        var index = Array.IndexOf(new[] { "file", "edit", "view", "help" }, scene[5..]);
                        root.UpdateLayout(); await Task.Delay(150); CaptureClick(menu.Items[index]);
                    }
                    else switch (scene)
                    {
                        case "group": break;
                        case "private": await Select(fixture.Text("org"), fixture.Text("member")); break;
                        case "overview": await SetPane("overview"); break;
                        case "thread": await OpenThread(fixture.Text("thread")); break;
                        case "workspace": workspaceMember = fixture.Text("member"); await SetPane("workspace"); break;
                        case "copies": case "copy-rules": dialog = Copies(); break;
                        case "chart": dialog = Chart(); break;
                        case "new-org": dialog = CreateOrg(); break;
                        case "member-app": dialog = MemberDialog("app"); break;
                        case "member-host": dialog = MemberDialog("host"); break;
                        case "member-existing": dialog = MemberDialog("existing"); break;
                        case "member-card": dialog = MemberCard(fixture.Text("member")); break;
                        case "member-edit": dialog = MemberDialog("host", fixture.Text("member")); break;
                        case "forward": dialog = Forward("advisor"); break;
                        case "secretary": dialog = SecretarySetup(); break;
                        case "tasks": dialog = Details("tasks"); break;
                        case "task-report": dialog = Details("tasks", taskId: fixture.Text("task")); break;
                        case "protocols": dialog = Details("protocols"); break;
                        case "documents": dialog = Details("docs"); break;
                        case "trajectory": dialog = Details("trace", fixture.Text("member")); break;
                        case "shortcuts": dialog = Shortcuts(); break;
                        case "recipients": dialog = PickRecipients(); break;
                        case "quote": Quote(Display(fixture.Text("member")), fixture.Text("quote")); break;
                        case "mention": editor.Text = "@"; editor.SelectionStart = 1; MentionMenu(); break;
                        case "digest": digest = fixture["digest"]!.DeepClone(); digestOpen = true; DrawConversation(); break;
                        case "plain": foreach (var item in messages) plain[PlainKey(item.Text("id"))] = fixture.Text("plain"); plainMode = true; DrawConversation(); plainTimer.Stop(); break;
                        case "quick-start": org = ""; orgs.Clear(); snap = new JsonObject(); DrawToolbar(); DrawSidebar(); DrawConversation(); DrawDetail(); break;
                        default: throw new InvalidOperationException("Unimplemented visual scene: " + scene);
                    }
                    if (dialog != null) for (var waiting = 0; visibleDialog == null && !dialog.IsCompleted && waiting < 100; waiting++) await Task.Delay(100);
                    await Task.Delay(800); if (dialog?.IsFaulted == true) await dialog;
                    if (scene == "documents" && visibleDialog != null)
                    {
                        var list = CaptureDocumentList(visibleDialog) ?? throw new InvalidOperationException("Document list is missing");
                        if (list.Items.Count == 0) throw new InvalidOperationException("Document fixture is empty");
                        list.SelectedIndex = 0; await documentSelection;
                        if (error.IsOpen) throw new InvalidOperationException("Document selection failed");
                    }
                    if (scene == "copy-rules" && visibleDialog != null) ExpandCaptureRules(visibleDialog);
                    root.UpdateLayout(); await Task.Delay(250);
                    SetCursorPos(1900, 1040);
                    if ((scene.StartsWith("menu-") || scene is "mention" or "recipients" or "member-card") && Microsoft.UI.Xaml.Media.VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot).Count == 0)
                        throw new InvalidOperationException("The requested native popup is not open: " + scene);
                    if (Math.Abs(root.ActualWidth - int.Parse(shot.Text("width"))) > 1 || Math.Abs(root.ActualHeight - int.Parse(shot.Text("height"))) > 1)
                        throw new InvalidOperationException($"Viewport mismatch: actual {root.ActualWidth}x{root.ActualHeight}, requested {shot.Text("width")}x{shot.Text("height")}");
                    await CaptureClient(System.IO.Path.Combine(manifest.Text("output"), shot.Text("file")), int.Parse(shot.Text("width")), int.Parse(shot.Text("height")));
                    await CaptureElementEvidence(manifest.Text("output"), shot.Text("id"), int.Parse(shot.Text("width")), int.Parse(shot.Text("height")));
                    Console.WriteLine("Relic visual capture: " + shot.Text("file"));
                    count++;
                }
                catch (Exception ex) { failures.Add(shot.Text("id") + ": " + ex); }
            }
        }
        catch (Exception ex) { failures.Add(ex.ToString()); }
        await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(System.IO.Path.GetDirectoryName(path)!, "complete.json"), System.Text.Json.JsonSerializer.Serialize(new { errors = failures, count }));
    }

    private static void ExpandCaptureRules(DependencyObject parent)
    {
        if (parent is Expander expander) expander.IsExpanded = true;
        for (var index = 0; index < Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(parent); index++) ExpandCaptureRules(Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChild(parent, index));
    }
    private static ListView? CaptureDocumentList(DependencyObject parent)
    {
        if (parent is ListView list && list.Tag?.ToString() == "document-list") return list;
        for (var index = 0; index < Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(parent); index++)
            if (CaptureDocumentList(Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChild(parent, index)) is { } found) return found;
        return null;
    }

    private async Task CaptureClient(string path, int width, int height)
    {
        var handle = WinRT.Interop.WindowNative.GetWindowHandle(this);
        var dc = GetDC(0); var memory = CreateCompatibleDC(dc); var bitmap = CreateCompatibleBitmap(dc, width, height); var previous = SelectObject(memory, bitmap);
        try
        {
            // Native Flyouts and MenuBar popups have separate HWNDs. Capture the
            // actual CI desktop pixels within the client rectangle, including
            // those real overlays; PrintWindow alone silently omits them.
            var origin = new CapturePoint(); if (!ClientToScreen(handle, ref origin)) throw new InvalidOperationException("ClientToScreen failed");
            if (!BitBlt(memory, 0, 0, width, height, dc, origin.x, origin.y, 0x40CC0020)) throw new InvalidOperationException("Desktop window capture failed");
            var info = new BitmapInfo { size = 40, width = width, height = -height, planes = 1, bits = 32, imageSize = (uint)(width * height * 4) };
            var pixels = new byte[width * height * 4];
            if (GetDIBits(memory, bitmap, 0, (uint)height, pixels, ref info, 0) == 0) throw new InvalidOperationException("GetDIBits failed");
            if (pixels.Where((_, i) => i % 4 != 3).Distinct().Take(12).Count() < 12) throw new InvalidOperationException("Window capture is blank");
            using var output = new InMemoryRandomAccessStream(); var encoder = await BitmapEncoder.CreateAsync(BitmapEncoder.PngEncoderId, output);
            encoder.SetPixelData(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Ignore, (uint)width, (uint)height, 96, 96, pixels); await encoder.FlushAsync();
            using var reader = new DataReader(output.GetInputStreamAt(0)); await reader.LoadAsync((uint)output.Size); var encoded = new byte[(int)output.Size]; reader.ReadBytes(encoded); await System.IO.File.WriteAllBytesAsync(path, encoded);
        }
        finally { SelectObject(memory, previous); DeleteObject(bitmap); DeleteDC(memory); ReleaseDC(0, dc); }
    }
    private void CaptureClick(FrameworkElement element)
    {
        // Drive the real MenuBar using the CI desktop. Directly constructing a
        // WinUI MenuBarItemAutomationPeer can dereference an uninitialized native
        // expand/collapse provider on Windows App SDK 1.6.
        if (!VisualCaptureEnabled) throw new InvalidOperationException("CI capture input only");
        var point = element.TransformToVisual(root).TransformPoint(new(element.ActualWidth / 2, element.ActualHeight / 2));
        var origin = new CapturePoint(); ClientToScreen(WinRT.Interop.WindowNative.GetWindowHandle(this), ref origin);
        SetCursorPos(origin.x + (int)point.X, origin.y + (int)point.Y);
        mouse_event(0x0002, 0, 0, 0, 0); mouse_event(0x0004, 0, 0, 0, 0);
    }
    [StructLayout(LayoutKind.Sequential)] private struct BitmapInfo { public uint size; public int width, height; public ushort planes, bits; public uint compression, imageSize; public int xppm, yppm; public uint used, important; }
    [DllImport("user32.dll")] private static extern nint GetDC(nint handle);
    [DllImport("user32.dll")] private static extern int ReleaseDC(nint handle, nint dc);
    [StructLayout(LayoutKind.Sequential)] private struct CapturePoint { public int x, y; }
    [DllImport("user32.dll")] private static extern bool ClientToScreen(nint handle, ref CapturePoint point);
    [DllImport("user32.dll")] private static extern bool SetForegroundWindow(nint handle);
    [DllImport("user32.dll")] private static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] private static extern void mouse_event(uint flags, uint x, uint y, uint data, nuint extra);
    [DllImport("gdi32.dll")] private static extern bool BitBlt(nint target, int x, int y, int width, int height, nint source, int sourceX, int sourceY, uint operation);
    [DllImport("gdi32.dll")] private static extern nint CreateCompatibleDC(nint dc);
    [DllImport("gdi32.dll")] private static extern nint CreateCompatibleBitmap(nint dc, int width, int height);
    [DllImport("gdi32.dll")] private static extern nint SelectObject(nint dc, nint value);
    [DllImport("gdi32.dll")] private static extern bool DeleteObject(nint value);
    [DllImport("gdi32.dll")] private static extern bool DeleteDC(nint dc);
    [DllImport("gdi32.dll")] private static extern int GetDIBits(nint dc, nint bitmap, uint start, uint lines, byte[] bits, ref BitmapInfo info, uint usage);
}
