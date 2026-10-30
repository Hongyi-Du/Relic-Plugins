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
    private JsonObject? capturedMessageEvidence;
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
                capturePointerReceipts = new JsonArray();
                await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(System.IO.Path.GetDirectoryName(path)!, "current-case.txt"), shot.Text("id"));
                try
                {
                    if (visibleDialog != null) { visibleDialog.Hide(); if (visibleDialogTask != null) await visibleDialogTask; }
                    transientFlyout?.Hide(); foreach (var popup in Microsoft.UI.Xaml.Media.VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot)) popup.IsOpen = false;
                    // Complete the prior native overlay's queued unload/layout
                    // before resizing and selecting the next real scene.
                    var settled = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                    if (!DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () => { root.UpdateLayout(); settled.SetResult(); }))
                        throw new InvalidOperationException("Window dispatcher closed before the next capture scene");
                    await settled.Task;
                    await StopVoice(); plainTimer.Stop(); error.IsOpen = false;
                    var scene = shot.Text("scene");
                    var endpoint = fixture.Text("scene_endpoint");
                    if (endpoint.Length == 0) throw new InvalidOperationException("Visual fixture scene endpoint is missing");
                    var prepared = await api!.Post(endpoint, new { scene });
                    var isLive = scene is "live-busy" or "live-tool-output" or "live-typing";
                    if (prepared.Text("scene") != scene || prepared.Flag("live") != isLive || prepared.Text("org").Length == 0 || prepared.Text("member").Length == 0)
                        throw new InvalidOperationException("Visual fixture did not prepare the requested scene: " + scene);
                    await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(manifest.Text("output"), shot.Text("id") + ".scene-fixture.json"), prepared.ToJsonString());
                    AppWindow.ResizeClient(new(int.Parse(shot.Text("width")), int.Parse(shot.Text("height")))); AppWindow.Move(new(0, 0));
                    SetForegroundWindow(WinRT.Interop.WindowNative.GetWindowHandle(this));
                    // Previous menu cases leave the desktop pointer over the
                    // toolbar. Move it off-window so hover tooltips cannot mask
                    // an unrelated screen in the next capture.
                    await CaptureMoveScreenPointer(1900, 1040);
                    sideWidth = 276; panelWidth = 340; fileWidth = 520; sideOpen = true; panelOpen = int.Parse(shot.Text("width")) > 1180;
                    pane = "overview"; threadId = ""; plainMode = false; digestOpen = false; folded.Clear(); search.Text = ""; editor.Text = ""; ClearQuote(); drafts.Clear(); recipientNames.Clear(); recipientNames.Add("all");
                    if (isLive) await Refresh();
                    await Select(prepared.Text("org")); LayoutColumns();
                    Task? dialog = null;
                    Microsoft.UI.Xaml.Controls.Primitives.Popup? suggestionPopup = null;
                    Expander? liveTool = null;
                    if (scene.StartsWith("settings-")) dialog = SettingsScreen(scene[9..]);
                    else if (scene.StartsWith("file-")) await OpenFile(fixture["files"].Text(scene[5..]), scene == "file-code" ? 2 : 0);
                    else if (scene.StartsWith("menu-"))
                    {
                        var index = Array.IndexOf(new[] { "file", "edit", "view", "help" }, scene[5..]);
                        root.UpdateLayout(); await Task.Delay(150); await CaptureClick(nativeMenus[index].Anchor);
                    }
                    else switch (scene)
                    {
                        case "group": case "message-hover": case "message-copy-toast": break;
                        case "private": await Select(fixture.Text("org"), fixture.Text("member")); break;
                        case "live-busy": case "live-tool-output": case "live-typing":
                            await Select(prepared.Text("org"), prepared.Text("member"));
                            if (org != prepared.Text("org") || member != prepared.Text("member") || liveData["status"].Text("state") != prepared.Text("state") || liveData.Rows("items").Count == 0)
                                throw new InvalidOperationException("Prepared live state was not loaded through the production API: " + scene);
                            break;
                        case "overview": await SetPane("overview"); break;
                        case "thread": await OpenThread(fixture.Text("thread")); break;
                        case "workspace": workspaceMember = fixture.Text("member"); await SetPane("workspace"); break;
                        case "copies": case "copy-rules": dialog = Copies(); break;
                        case "chart": dialog = ShowChart(org); break;
                        case "new-org": case "new-org-textarea-resized": dialog = CreateOrg(); break;
                        case "member-app": dialog = MemberDialog("app"); break;
                        case "member-host": case "member-host-model-suggestions": dialog = MemberDialog("host"); break;
                        case "member-existing": case "member-existing-seat-suggestions": dialog = MemberDialog("existing"); break;
                        case "member-card": case "member-card-rename": case "member-card-model": case "member-card-avatar-hover":
                            dialog = MemberCard(fixture.Text("member")); break;
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
                    if (scene == "new-org-textarea-resized")
                    {
                        await CaptureTextareaScene();
                        await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(manifest.Text("output"), shot.Text("id") + ".scene-action.json"), capturedTextareaEvidence!.ToJsonString());
                    }
                    capturedMessageEvidence = null;
                    if (scene is "message-hover" or "message-copy-toast")
                    {
                        capturedMessageEvidence = await CaptureMessageScene(scene, fixture.Text("thread"));
                        await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(manifest.Text("output"), shot.Text("id") + ".scene-action.json"), capturedMessageEvidence.ToJsonString());
                    }
                    if (scene.StartsWith("member-card-"))
                    {
                        var controlId = scene == "member-card-avatar-hover" ? "member-card-avatar" : scene;
                        var control = CaptureCardControl(controlId) ?? throw new InvalidOperationException("Member card control missing: " + controlId);
                        var before = control.TransformToVisual(root).TransformBounds(new Windows.Foundation.Rect(0, 0, control.ActualWidth, control.ActualHeight));
                        if (scene == "member-card-avatar-hover") await CaptureHover(control); else await CaptureClick(control);
                        await Task.Delay(150); root.UpdateLayout();
                        var resultId = scene switch { "member-card-rename" => "member-card-name-input", "member-card-model" => "member-card-model-input", _ => "member-card-avatar-cover" };
                        var result = CaptureCardControl(resultId) ?? throw new InvalidOperationException("Member card action did not reveal its real control: " + resultId);
                        if (result.ActualWidth <= 0 || result.ActualHeight <= 0 || result.Visibility != Visibility.Visible || result.Opacity <= 0)
                            throw new InvalidOperationException("Member card action result is not visible: " + resultId);
                        await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(manifest.Text("output"), shot.Text("id") + ".scene-action.json"),
                            System.Text.Json.JsonSerializer.Serialize(new { action = scene == "member-card-avatar-hover" ? "native pointer hover" : "native pointer click", control_id = controlId,
                                control_bounds = new { x = before.X, y = before.Y, width = before.Width, height = before.Height }, result_id = resultId,
                                result_opacity = result.Opacity, focused = result is Control input ? input.FocusState.ToString() : null }));
                    }
                    if (scene == "live-tool-output")
                    {
                        var title = prepared["tool"].Text("title");
                        if (title.Length == 0) throw new InvalidOperationException("Live fixture did not return a tool title");
                        var matches = CaptureLiveTools(stream, title).ToArray();
                        if (matches.Length != 1) throw new InvalidOperationException("Expected one live tool disclosure for: " + title);
                        liveTool = matches[0];
                        var header = (FrameworkElement)liveTool.Header;
                        header.StartBringIntoView(new BringIntoViewOptions { AnimationDesired = false });
                        root.UpdateLayout(); await Task.Delay(150); await CaptureClick(header);
                        await Task.Delay(150); root.UpdateLayout();
                        if (!liveTool.IsExpanded) throw new InvalidOperationException("Real live tool disclosure did not open: " + title);
                        await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(manifest.Text("output"), shot.Text("id") + ".scene-action.json"),
                            System.Text.Json.JsonSerializer.Serialize(new { action = "click production Expander header", tool_title = title, open = liveTool.IsExpanded }));
                    }
                    if (scene is "member-host-model-suggestions" or "member-existing-seat-suggestions")
                    {
                        var inputId = scene == "member-host-model-suggestions" ? "member-model" : "member-seat-name";
                        suggestionPopup = await OpenCaptureSuggestions(inputId);
                    }
                    if (scene == "documents" && visibleDialog != null)
                    {
                        var list = CaptureDocumentList(visibleDialog) ?? throw new InvalidOperationException("Document list is missing");
                        if (list.Items.Count == 0) throw new InvalidOperationException("Document fixture is empty");
                        list.SelectedIndex = 0; await documentSelection;
                        if (error.IsOpen) throw new InvalidOperationException("Document selection failed");
                    }
                    if (scene == "copy-rules" && visibleDialog != null) ExpandCaptureRules(visibleDialog);
                    if (pane == "files" && workspaceCode is { IsLoaded: true } sourceCode)
                    {
                        for (var waiting = 0; !sourceCode.IsDocumentReady && sourceCode.InitializationFailure == null && waiting < 100; waiting++) await Task.Delay(50);
                        if (!sourceCode.IsDocumentReady) throw new InvalidOperationException("Native code document did not finish its real layout: " + (sourceCode.InitializationFailure ?? "timeout"));
                    }
                    foreach (var input in new[] { editor, threadEditor })
                        if (input.IsLoaded && !input.IsDocumentReady)
                            throw new InvalidOperationException("Native composer document did not initialize: " + (input.InitializationFailure ?? "not ready"));
                    root.UpdateLayout();
                    var animation = PrepareCaptureAnimation(scene);
                    await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(manifest.Text("output"), shot.Text("id") + ".animations.json"), System.Text.Json.JsonSerializer.Serialize(animation));
                    await Task.Delay(250);
                    if (suggestionPopup == null && scene is not ("member-card-avatar-hover" or "message-hover" or "message-copy-toast" or "new-org-textarea-resized")) await CaptureMoveScreenPointer(1900, 1040);
                    if ((scene.StartsWith("menu-") || scene.StartsWith("member-card") || scene is "mention" or "recipients") && Microsoft.UI.Xaml.Media.VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot).Count == 0)
                        throw new InvalidOperationException("The requested native popup is not open: " + scene);
                    if (Math.Abs(root.ActualWidth - int.Parse(shot.Text("width"))) > 1 || Math.Abs(root.ActualHeight - int.Parse(shot.Text("height"))) > 1)
                        throw new InvalidOperationException($"Viewport mismatch: actual {root.ActualWidth}x{root.ActualHeight}, requested {shot.Text("width")}x{shot.Text("height")}");
                    if (suggestionPopup is { IsOpen: false }) throw new InvalidOperationException("Suggestion popup closed before screenshot: " + scene);
                    if (liveTool != null && (!liveTool.IsExpanded || !liveTool.IsLoaded)) throw new InvalidOperationException("Live tool disclosure closed or unloaded before screenshot");
                    if (capturedMessageEvidence != null) capturedMessageEvidence["before_screenshot"] = CaptureMessageSceneState();
                    CaptureTextareaCheckpoint("before_screenshot");
                    await BeginNativeLabelCaptureAsync(shot.Text("id"));
                    await CaptureClient(System.IO.Path.Combine(manifest.Text("output"), shot.Text("file")), int.Parse(shot.Text("width")), int.Parse(shot.Text("height")));
                    CaptureTextareaCheckpoint("after_screenshot");
                    if (capturedMessageEvidence != null) capturedMessageEvidence["after_screenshot"] = CaptureMessageSceneState();
                    if (suggestionPopup is { IsOpen: false }) throw new InvalidOperationException("Suggestion popup closed before element extraction: " + scene);
                    if (capturedTextareaEvidence != null)
                        await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(manifest.Text("output"), shot.Text("id") + ".scene-action.json"), capturedTextareaEvidence.ToJsonString());
                    CheckpointNativeLabelCapture("before_element_extraction");
                    await CaptureElementEvidence(manifest.Text("output"), shot.Text("id"), int.Parse(shot.Text("width")), int.Parse(shot.Text("height")));
                    CheckpointNativeLabelCapture("after_element_extraction");
                    CaptureTextareaCheckpoint("after_extraction");
                    if (capturedMessageEvidence != null)
                    {
                        capturedMessageEvidence["after_extraction"] = CaptureMessageSceneState();
                        await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(manifest.Text("output"), shot.Text("id") + ".scene-action.json"), capturedMessageEvidence.ToJsonString());
                    }
                    RequireNativeLabelCaptureCompleted();
                    Console.WriteLine("Relic visual capture: " + shot.Text("file"));
                    count++;
                }
                catch (Exception ex)
                {
                    if (capturedTextareaEvidence != null) ((JsonArray)capturedTextareaEvidence["errors"]!).Add(ex.ToString());
                    failures.Add(shot.Text("id") + ": " + ex);
                    // Keep the actual failed state for inspection. This separate
                    // file is never the canonical scene or a successful receipt.
                    try
                    {
                        var diagnosticDirectory = System.IO.Path.Combine(manifest.Text("output"), "diagnostics");
                        System.IO.Directory.CreateDirectory(diagnosticDirectory);
                        await CaptureClient(System.IO.Path.Combine(diagnosticDirectory, shot.Text("id") + ".failed.png"),
                            int.Parse(shot.Text("width")), int.Parse(shot.Text("height")), observeNativeLabel: false);
                    }
                    catch (Exception captureError) { failures.Add(shot.Text("id") + ": failed-state PNG unavailable: " + captureError); }
                }
                finally
                {
                    await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(manifest.Text("output"), shot.Text("id") + ".pointer-input.json"), capturePointerReceipts.ToJsonString());
                    try
                    {
                        if (capturedNativeLabelEvidence != null)
                            await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(manifest.Text("output"), shot.Text("id") + ".native-label-frame.json"), capturedNativeLabelEvidence.ToJsonString());
                    }
                    finally { EndNativeLabelCapture(); }
                    var resumed = ResumeCapturedMessageToasts();
                    if (resumed.Count > 0) await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(manifest.Text("output"), shot.Text("id") + ".toast-resume.json"), resumed.ToJsonString());
                    capturedMessageEvidence = null;
                    try
                    {
                        if (capturedTextareaEvidence != null)
                            await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(manifest.Text("output"), shot.Text("id") + ".scene-action.json"), capturedTextareaEvidence.ToJsonString());
                    }
                    finally { EndTextareaCapture(); }
                }
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

    private static IEnumerable<Expander> CaptureLiveTools(DependencyObject parent, string title)
    {
        if (parent is Expander disclosure && disclosure.Header is FrameworkElement header && CaptureContainsText(header, title)) yield return disclosure;
        for (var index = 0; index < Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(parent); index++)
            foreach (var match in CaptureLiveTools(Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChild(parent, index), title)) yield return match;
    }

    private static bool CaptureContainsText(DependencyObject parent, string text)
    {
        if (parent is TextBlock label && label.Text == text) return true;
        for (var index = 0; index < Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(parent); index++)
            if (CaptureContainsText(Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChild(parent, index), text)) return true;
        return false;
    }
    private static ListView? CaptureDocumentList(DependencyObject parent)
    {
        if (parent is ListView list && list.Tag?.ToString() == "document-list") return list;
        for (var index = 0; index < Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(parent); index++)
            if (CaptureDocumentList(Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChild(parent, index)) is { } found) return found;
        return null;
    }

    private static TextBox? CaptureSuggestionInput(DependencyObject parent, string automationId)
    {
        if (parent is TextBox input && Microsoft.UI.Xaml.Automation.AutomationProperties.GetAutomationId(input) == automationId) return input;
        for (var index = 0; index < Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(parent); index++)
            if (CaptureSuggestionInput(Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChild(parent, index), automationId) is { } found) return found;
        return null;
    }

    private async Task<Microsoft.UI.Xaml.Controls.Primitives.Popup> OpenCaptureSuggestions(string automationId)
    {
        if (!VisualCaptureEnabled || visibleDialog == null) throw new InvalidOperationException("Suggestion capture needs the real CI member dialog");
        var input = CaptureSuggestionInput(visibleDialog, automationId) ?? throw new InvalidOperationException("Suggestion input is missing: " + automationId);
        await CaptureMoveScreenPointer(1900, 1040);
        var before = Microsoft.UI.Xaml.Media.VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot).ToHashSet();
        if (!input.Focus(FocusState.Keyboard)) throw new InvalidOperationException("Suggestion input could not receive focus: " + automationId);
        root.UpdateLayout(); await Task.Delay(100);
        // Send a real Down Arrow to the focused production TextBox. Its normal
        // keyboard handler, not the capture script, creates the suggestions.
        keybd_event(0x28, 0, 0, 0); keybd_event(0x28, 0, 0x0002, 0);
        await Task.Delay(250); root.UpdateLayout();
        var after = Microsoft.UI.Xaml.Media.VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot);
        return after.FirstOrDefault(popup => !before.Contains(popup) && popup.IsOpen)
            ?? throw new InvalidOperationException("The real suggestion popup did not open: " + automationId);
    }

    private async Task CaptureClient(string path, int width, int height, bool observeNativeLabel = true)
    {
        var handle = WinRT.Interop.WindowNative.GetWindowHandle(this);
        var dc = GetDC(0); var memory = CreateCompatibleDC(dc); var bitmap = CreateCompatibleBitmap(dc, width, height); var previous = SelectObject(memory, bitmap);
        try
        {
            // Native Flyouts and MenuBar popups have separate HWNDs. Capture the
            // actual CI desktop pixels within the client rectangle, including
            // those real overlays; PrintWindow alone silently omits them.
            var origin = new CapturePoint(); if (!ClientToScreen(handle, ref origin)) throw new InvalidOperationException("ClientToScreen failed");
            if (observeNativeLabel) CheckpointNativeLabelCapture("before_desktop_readback");
            if (!BitBlt(memory, 0, 0, width, height, dc, origin.x, origin.y, 0x40CC0020)) throw new InvalidOperationException("Desktop window capture failed");
            var info = new BitmapInfo { size = 40, width = width, height = -height, planes = 1, bits = 32, imageSize = (uint)(width * height * 4) };
            var pixels = new byte[width * height * 4];
            if (GetDIBits(memory, bitmap, 0, (uint)height, pixels, ref info, 0) == 0) throw new InvalidOperationException("GetDIBits failed");
            if (observeNativeLabel) CheckpointNativeLabelCapture("after_desktop_readback");
            if (pixels.Where((_, i) => i % 4 != 3).Distinct().Take(12).Count() < 12) throw new InvalidOperationException("Window capture is blank");
            using var output = new InMemoryRandomAccessStream(); var encoder = await BitmapEncoder.CreateAsync(BitmapEncoder.PngEncoderId, output);
            encoder.SetPixelData(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Ignore, (uint)width, (uint)height, 96, 96, pixels); await encoder.FlushAsync();
            using var reader = new DataReader(output.GetInputStreamAt(0)); await reader.LoadAsync((uint)output.Size); var encoded = new byte[(int)output.Size]; reader.ReadBytes(encoded); await System.IO.File.WriteAllBytesAsync(path, encoded);
        }
        finally { SelectObject(memory, previous); DeleteObject(bitmap); DeleteDC(memory); ReleaseDC(0, dc); }
    }
    private async Task CaptureClick(FrameworkElement element)
    {
        // Drive the production control through actual CI desktop input. Capture
        // never opens a substitute flyout or manufactures an automation peer.
        if (!VisualCaptureEnabled) throw new InvalidOperationException("CI capture input only");
        await CaptureHover(element);
        CapturePointerButton(true);
        try { await Task.Delay(40); }
        finally { CapturePointerButton(false); }
    }
    private FrameworkElement? CaptureCardControl(string automationId)
    {
        FrameworkElement? Find(DependencyObject parent)
        {
            if (parent is FrameworkElement element && Microsoft.UI.Xaml.Automation.AutomationProperties.GetAutomationId(element) == automationId) return element;
            for (var i = 0; i < Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(parent); i++)
                if (Find(Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChild(parent, i)) is { } child) return child;
            return null;
        }
        foreach (var popup in Microsoft.UI.Xaml.Media.VisualTreeHelper.GetOpenPopupsForXamlRoot(root.XamlRoot))
            if (popup.IsOpen && popup.Child != null && Find(popup.Child) is { } found) return found;
        return null;
    }
    private async Task CaptureHover(FrameworkElement element)
    {
        if (!VisualCaptureEnabled) throw new InvalidOperationException("CI capture input only");
        var point = element.TransformToVisual(root).TransformPoint(new(element.ActualWidth / 2, element.ActualHeight / 2));
        await CaptureMovePointer(point);
    }
    [StructLayout(LayoutKind.Sequential)] private struct BitmapInfo { public uint size; public int width, height; public ushort planes, bits; public uint compression, imageSize; public int xppm, yppm; public uint used, important; }
    [DllImport("user32.dll")] private static extern nint GetDC(nint handle);
    [DllImport("user32.dll")] private static extern int ReleaseDC(nint handle, nint dc);
    [StructLayout(LayoutKind.Sequential)] private struct CapturePoint { public int x, y; }
    [DllImport("user32.dll")] private static extern bool ClientToScreen(nint handle, ref CapturePoint point);
    [DllImport("user32.dll")] private static extern bool SetForegroundWindow(nint handle);
    [DllImport("user32.dll")] private static extern void keybd_event(byte key, byte scan, uint flags, nuint extra);
    [DllImport("gdi32.dll")] private static extern bool BitBlt(nint target, int x, int y, int width, int height, nint source, int sourceX, int sourceY, uint operation);
    [DllImport("gdi32.dll")] private static extern nint CreateCompatibleDC(nint dc);
    [DllImport("gdi32.dll")] private static extern nint CreateCompatibleBitmap(nint dc, int width, int height);
    [DllImport("gdi32.dll")] private static extern nint SelectObject(nint dc, nint value);
    [DllImport("gdi32.dll")] private static extern bool DeleteObject(nint value);
    [DllImport("gdi32.dll")] private static extern bool DeleteDC(nint dc);
    [DllImport("gdi32.dll")] private static extern int GetDIBits(nint dc, nint bitmap, uint start, uint lines, byte[] bits, ref BitmapInfo info, uint usage);
}
