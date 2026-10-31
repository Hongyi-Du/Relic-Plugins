using Relic.Core;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Nodes;
using Windows.Graphics.Imaging;
using Windows.Storage.Streams;

namespace Relic;

public sealed partial class MainWindow
{
    private bool WholeWindowCaptureEnabled => VisualCaptureEnabled
        && Environment.GetEnvironmentVariable("RELIC_TITLEBAR_CAPTURE") == "1";

    private async Task CaptureWholeWindowVisuals()
    {
        var manifestPath = Environment.GetEnvironmentVariable("RELIC_VISUAL_MANIFEST")!;
        var manifestDirectory = System.IO.Path.GetDirectoryName(manifestPath)!;
        var failures = new List<string>(); var count = 0;
        try
        {
            var manifest = JsonNode.Parse(await System.IO.File.ReadAllTextAsync(manifestPath))!;
            var fixture = manifest["fixture"]!;
            var output = manifest.Text("output"); System.IO.Directory.CreateDirectory(output);
            foreach (var shot in manifest.Rows("cases"))
            {
                var id = shot.Text("id");
                var actions = new JsonArray(); capturePointerReceipts = new JsonArray();
                JsonObject? receipt = null;
                await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(manifestDirectory, "current-case.txt"), id);
                try
                {
                    if (shot.Text("scene") != "group") throw new InvalidOperationException("Whole-window capture supports the real group scene only");
                    var width = int.Parse(shot.Text("width")); var height = int.Parse(shot.Text("height"));
                    var monitor = CurrentWindowMonitor();
                    var logicalSizing = manifest.Text("window_units") == "dip";
                    var initialWindow = new PixelRect(AppWindow.Position.X, AppWindow.Position.Y, AppWindow.Size.Width, AppWindow.Size.Height);
                    if (logicalSizing)
                    {
                        width = WindowSizing.Pixels(width, monitor.Scale);
                        height = WindowSizing.Pixels(height, monitor.Scale);
                    }
                    var endpoint = fixture.Text("scene_endpoint");
                    if (endpoint.Length == 0) throw new InvalidOperationException("Visual fixture scene endpoint is missing");
                    var prepared = await api!.Post(endpoint, new { scene = "group" });
                    if (prepared.Text("scene") != "group" || prepared.Text("org").Length == 0)
                        throw new InvalidOperationException("The fixture did not prepare the group scene");
                    await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(output, id + ".scene-fixture.json"), prepared.ToJsonString());

                    // Requested dimensions describe the actual top-level window,
                    // including its system caption and resize border, not XAML.
                    AppWindow.Resize(new Windows.Graphics.SizeInt32(width, height));
                    AppWindow.Move(new Windows.Graphics.PointInt32(24, 24));
                    sideWidth = 276; panelWidth = 340; sideOpen = true; panelOpen = width / monitor.Scale > ResponsiveLayout.InspectorOverlayWidth;
                    pane = "overview"; threadId = ""; plainMode = false; digestOpen = false;
                    folded.Clear(); search.Text = ""; editor.Text = ""; ClearQuote();
                    await Select(prepared.Text("org")); LayoutColumns(); root.UpdateLayout();
                    var handle = WinRT.Interop.WindowNative.GetWindowHandle(this);
                    SetForegroundWindow(handle);
                    await CaptureMoveScreenPointer(monitor.WorkArea.X + monitor.WorkArea.Width - 10,
                        monitor.WorkArea.Y + monitor.WorkArea.Height - 10);
                    await WaitForMarkdown(); await Task.Delay(350); root.UpdateLayout();
                    if (error.IsOpen) throw new InvalidOperationException("Production UI reported: " + error.Message);
                    if (!editor.IsDocumentReady) throw new InvalidOperationException("Native composer did not initialize: " + editor.InitializationFailure);
                    if (WholeWindowForeground() != handle) throw new InvalidOperationException("Relic is not the foreground window for desktop capture");
                    // Preserve the normal loaded window before interaction checks.
                    // A later action failure must leave its original image available.
                    receipt = await CaptureWholeWindowPixels(System.IO.Path.Combine(output, shot.Text("file")), width, height);
                    receipt["case_id"] = id;
                    receipt["language"] = words.Language;
                    receipt["theme"] = root.ActualTheme.ToString().ToLowerInvariant();
                    receipt["image_before_actions"] = true;
                    receipt["sizing"] = JsonSerializer.SerializeToNode(new {
                        units = logicalSizing ? "dip" : "physical-pixel", dpi = windowDpi,
                        monitor, initial_window = initialWindow, startup_placement = startupPlacement,
                        default_window = WindowSizing.Default(monitor), minimum = WindowSizing.Minimum(monitor),
                        logical_width = AppWindow.Size.Width / monitor.Scale, logical_height = AppWindow.Size.Height / monitor.Scale,
                        content_width = root.ActualWidth, content_height = root.ActualHeight,
                        inspector_overlay = root.ActualWidth <= ResponsiveLayout.InspectorOverlayWidth,
                        inspector_open = panelOpen, sidebar_width = sidebarSurface.ActualWidth });
                    receipt["actions_passed"] = false;
                    receipt["original_window_screen"] = receipt["window_screen"]!.DeepClone();
                    await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(output, id + ".window-chrome.json"), receipt.ToJsonString());
                    var restoredWindow = await VerifyWholeWindowActions(actions);
                    receipt["actual_actions"] = actions.DeepClone();
                    receipt["restored_window_screen"] = WholeWindowBox(restoredWindow);
                    receipt["actions_passed"] = true;
                    await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(output, id + ".window-chrome.json"), receipt.ToJsonString());
                    count++;
                    Console.WriteLine("Relic whole-window capture: " + shot.Text("file"));
                }
                catch (Exception ex) { failures.Add(id + ": " + ex); }
                finally
                {
                    if (receipt != null)
                    {
                        receipt["actual_actions"] = actions.DeepClone();
                        await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(output, id + ".window-chrome.json"), receipt.ToJsonString());
                    }
                    await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(output, id + ".window-actions.json"),
                        new JsonObject { ["actual_actions"] = actions, ["pointer_input"] = capturePointerReceipts.DeepClone() }.ToJsonString());
                }
            }
        }
        catch (Exception ex) { failures.Add(ex.ToString()); }
        await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(manifestDirectory, "complete.json"),
            JsonSerializer.Serialize(new { mode = "whole-window", errors = failures, count }));
    }

    private async Task<WholeWindowRect> VerifyWholeWindowActions(JsonArray actions)
    {
        var handle = WinRT.Interop.WindowNative.GetWindowHandle(this);
        if (!WholeWindowGetRect(handle, out var original)) throw new Win32Exception(Marshal.GetLastWin32Error());
        var presenter = AppWindow.Presenter as OverlappedPresenter
            ?? throw new InvalidOperationException("Title-bar actions require the production overlapped presenter");
        if (presenter.State != OverlappedPresenterState.Restored) throw new InvalidOperationException("Initial window is not restored");
        var entry = nativeMenus.FirstOrDefault() ?? throw new InvalidOperationException("Production File menu is missing");
        var menuAction = new JsonObject { ["action"] = "real pointer click File menu, then keyboard Escape", ["before_open"] = entry.Flyout.IsOpen };
        actions.Add(menuAction);
        await CaptureClick(entry.Anchor); await Task.Delay(150);
        menuAction["after_first_open"] = entry.Flyout.IsOpen;
        menuAction["same_open_menu"] = ReferenceEquals(openNativeMenu, entry);
        if (!entry.Flyout.IsOpen || !ReferenceEquals(openNativeMenu, entry)) throw new InvalidOperationException("Real menu click did not open its production flyout");
        // The menu anchor receives pass-through pointer input. Re-clicking it
        // can light-dismiss the flyout before the same click opens it again.
        // Verify the production Escape interaction instead of assuming a toggle.
        WholeWindowEscapeKey(true);
        try { await Task.Delay(10); }
        finally { WholeWindowEscapeKey(false); }
        await Task.Delay(150);
        menuAction["after_escape_open"] = entry.Flyout.IsOpen;
        menuAction["after_escape_active_menu"] = openNativeMenu != null;
        if (entry.Flyout.IsOpen || openNativeMenu != null) throw new InvalidOperationException("Real Escape key did not close its production flyout");
        menuAction["passed"] = true;

        var originalSide = sideOpen; var originalVisibility = sidebarSurface.Visibility;
        var sideAction = new JsonObject { ["action"] = "real pointer click sidebar button twice",
            ["before_open"] = originalSide, ["before_visibility"] = originalVisibility.ToString() };
        actions.Add(sideAction);
        Button SideButton() => navigationButtons.Children.Count > 1 && navigationButtons.Children[1] is Button button
            ? button : throw new InvalidOperationException("Production sidebar button is missing");
        await CaptureClick(SideButton()); await Task.Delay(150); root.UpdateLayout();
        sideAction["after_first_open"] = sideOpen; sideAction["after_first_visibility"] = sidebarSurface.Visibility.ToString();
        if (sideOpen == originalSide || sidebarSurface.Visibility == originalVisibility)
            throw new InvalidOperationException("Real sidebar click did not change sidebar state and visibility");
        await CaptureClick(SideButton()); await Task.Delay(150); root.UpdateLayout();
        sideAction["after_second_open"] = sideOpen; sideAction["after_second_visibility"] = sidebarSurface.Visibility.ToString();
        if (sideOpen != originalSide || sidebarSurface.Visibility != originalVisibility)
            throw new InvalidOperationException("Real second sidebar click did not restore sidebar state");
        sideAction["passed"] = true;

        await DoubleClickWholeWindowTitle(actions, "maximize", presenter, OverlappedPresenterState.Maximized);
        await DoubleClickWholeWindowTitle(actions, "restore", presenter, OverlappedPresenterState.Restored);
        if (!WholeWindowGetRect(handle, out var restored)) throw new Win32Exception(Marshal.GetLastWin32Error());
        var restoration = new JsonObject { ["action"] = "verify real window restoration",
            ["original_window_screen"] = WholeWindowBox(original), ["restored_window_screen"] = WholeWindowBox(restored),
            ["passed"] = original.Equals(restored) };
        actions.Add(restoration);
        if (!original.Equals(restored)) throw new InvalidOperationException("Double-click restore did not return the original window rectangle");
        return restored;
    }

    private void WholeWindowEscapeKey(bool down)
    {
        if (!WholeWindowCaptureEnabled) throw new InvalidOperationException("Whole-window input is CI-only");
        var input = new WholeWindowInput { type = 1, data = new WholeWindowInputData
            { keyboard = new WholeWindowKeyboardInput { virtualKey = 0x1B, flags = down ? 0u : 0x0002u } } };
        var inserted = WholeWindowSendInput(1, [input], Marshal.SizeOf<WholeWindowInput>());
        var errorCode = Marshal.GetLastWin32Error();
        capturePointerReceipts.Add(new JsonObject { ["operation"] = down ? "SendInput Escape down" : "SendInput Escape up",
            ["virtual_key"] = 0x1B, ["inserted_events"] = inserted });
        if (inserted != 1) throw new Win32Exception(errorCode, "Could not insert real Escape keyboard input");
    }

    private async Task DoubleClickWholeWindowTitle(JsonArray actions, string action, OverlappedPresenter presenter, OverlappedPresenterState expected)
    {
        root.UpdateLayout();
        if (!appTitle.IsLoaded || appTitle.IsHitTestVisible || appTitle.ActualWidth <= 0 || appTitle.ActualHeight <= 0)
            throw new InvalidOperationException("Production title label does not provide a noninteractive drag point");
        var bounds = appTitle.TransformToVisual(root).TransformBounds(new Windows.Foundation.Rect(0, 0, appTitle.ActualWidth, appTitle.ActualHeight));
        var point = new Windows.Foundation.Point(bounds.X + bounds.Width / 2, bounds.Y + bounds.Height / 2);
        var title = titlebarRegion.TransformToVisual(root).TransformBounds(new Windows.Foundation.Rect(0, 0, titlebarRegion.ActualWidth, titlebarRegion.ActualHeight));
        if (!title.Contains(point)) throw new InvalidOperationException("Actual title center is outside the production title bar");
        var scale = root.XamlRoot.RasterizationScale;
        var clientX = (int)Math.Round(point.X * scale); var clientY = (int)Math.Round(point.Y * scale);
        if (titlebarInteractiveRects.Any(rect => clientX >= rect.X && clientX < rect.X + rect.Width && clientY >= rect.Y && clientY < rect.Y + rect.Height))
            throw new InvalidOperationException("Actual title center overlaps a production passthrough button");
        var handle = WinRT.Interop.WindowNative.GetWindowHandle(this); var origin = new CapturePoint();
        if (!ClientToScreen(handle, ref origin) || !WholeWindowGetRect(handle, out var window)
            || !WholeWindowGetClientRect(handle, out var client))
            throw new InvalidOperationException("Title gesture could not bind actual client/window coordinates");
        var captionResult = WholeWindowDwmRect(handle, 5, out var caption, Marshal.SizeOf<WholeWindowRect>());
        var screenX = origin.x + clientX; var screenY = origin.y + clientY;
        var windowX = screenX - window.left; var windowY = screenY - window.top;
        var captionUsable = captionResult >= 0 && caption.right > caption.left && caption.bottom > caption.top;
        var overlapsDwmCaption = captionUsable && windowX >= caption.left && windowX < caption.right
            && windowY >= caption.top && windowY < caption.bottom;
        // Insets are physical-pixel widths of the system-reserved title-bar areas.
        // With extended content the DWM caption rectangle may be empty, so use
        // the actual AppWindow reservation, not a guessed button width.
        var leftInset = AppWindow.TitleBar.LeftInset; var rightInset = AppWindow.TitleBar.RightInset;
        var titleHeight = AppWindow.TitleBar.Height; var clientWidth = client.right - client.left;
        var validInsets = ExtendsContentIntoTitleBar && leftInset >= 0 && rightInset >= 0
            && leftInset + rightInset > 0 && leftInset + rightInset < clientWidth && titleHeight > 0;
        var outsideCaptionStrips = validInsets && clientX >= leftInset && clientX < clientWidth - rightInset;
        var doubleClickTime = WholeWindowDoubleClickTime();
        var record = new JsonObject { ["action"] = "real title-area double click " + action,
            ["before_state"] = presenter.State.ToString(), ["scale"] = scale,
            ["client_dip"] = new JsonObject { ["x"] = point.X, ["y"] = point.Y },
            ["screen_pixel"] = new JsonObject { ["x"] = screenX, ["y"] = screenY },
            ["caption_buttons_window"] = WholeWindowBox(caption), ["caption_buttons_hresult"] = captionResult,
            ["caption_buttons_usable"] = captionUsable, ["overlaps_dwm_caption"] = overlapsDwmCaption,
            ["caption_safety"] = new JsonObject { ["source"] = "actual AppWindow title-bar insets and GetClientRect",
                ["client_width_pixel"] = clientWidth, ["titlebar_height_pixel"] = titleHeight,
                ["left_inset_pixel"] = leftInset, ["right_inset_pixel"] = rightInset,
                ["titlebar_client_dip"] = new JsonObject { ["x"] = title.X, ["y"] = title.Y,
                    ["width"] = title.Width, ["height"] = title.Height },
                ["valid_reserved_strips"] = validInsets, ["outside_reserved_strips"] = outsideCaptionStrips },
            ["system_double_click_time_ms"] = doubleClickTime,
            ["outside_passthrough_and_caption"] = outsideCaptionStrips && !overlapsDwmCaption };
        actions.Add(record);
        if (!outsideCaptionStrips || overlapsDwmCaption)
            throw new InvalidOperationException("Title gesture could not exclude the actual system caption-button reserved areas");
        await CaptureMoveScreenPointer(screenX, screenY);
        record["actual_nonclient_hit_test"] = (long)WholeWindowSendMessage(handle, 0x0084, 0,
            (nint)((screenY << 16) | (screenX & 0xffff)));
        // Queue the complete gesture before yielding to the UI dispatcher.
        // A caption down event enters Windows' modal move loop; scheduling its
        // release through that same UI dispatcher can split a double click.
        var inputs = new[] { 0x0002u, 0x0004u, 0x0002u, 0x0004u }
            .Select(flags => new CaptureInput { Type = 0, Mouse = new CaptureMouseInput { Flags = flags } }).ToArray();
        var inserted = SendInput((uint)inputs.Length, inputs, Marshal.SizeOf<CaptureInput>());
        record["inserted_double_click_events"] = inserted;
        if (inserted != inputs.Length) throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not insert the complete real double click");
        await Task.Delay(350); root.UpdateLayout();
        record["after_state"] = presenter.State.ToString(); record["passed"] = presenter.State == expected;
        if (presenter.State != expected) throw new InvalidOperationException("Real title double click did not " + action + " the window");
    }

    private async Task<JsonObject> CaptureWholeWindowPixels(string path, int requestedWidth, int requestedHeight)
    {
        if (!WholeWindowCaptureEnabled) throw new InvalidOperationException("Whole-window desktop capture is CI-only");
        var handle = WinRT.Interop.WindowNative.GetWindowHandle(this);
        if (!WholeWindowGetRect(handle, out var window) || !WholeWindowGetClientRect(handle, out var client))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not read actual window/client rectangle");
        var origin = new CapturePoint();
        if (!ClientToScreen(handle, ref origin)) throw new InvalidOperationException("ClientToScreen failed");
        var width = window.right - window.left; var height = window.bottom - window.top;
        if (width != requestedWidth || height != requestedHeight)
            throw new InvalidOperationException($"Whole-window size mismatch: {width}x{height}, requested {requestedWidth}x{requestedHeight}");
        // DWMWA_CAPTION_BUTTON_BOUNDS is window-relative; extended frame bounds
        // are screen-relative. GetWindowRect intentionally retains resize borders.
        var captionResult = WholeWindowDwmRect(handle, 5, out var caption, Marshal.SizeOf<WholeWindowRect>());
        var frameResult = WholeWindowDwmRect(handle, 9, out var frame, Marshal.SizeOf<WholeWindowRect>());
        var receipt = new JsonObject
        {
            ["source"] = "CI desktop BitBlt of actual GetWindowRect, including system caption buttons",
            ["requested_window_size"] = new JsonObject { ["width"] = requestedWidth, ["height"] = requestedHeight },
            ["window_screen"] = WholeWindowBox(window),
            ["client_screen"] = WholeWindowBox(new() { left = origin.x, top = origin.y,
                right = origin.x + client.right - client.left, bottom = origin.y + client.bottom - client.top }),
            ["caption_buttons_window"] = WholeWindowBox(caption), ["caption_buttons_hresult"] = captionResult,
            ["caption_buttons_usable"] = captionResult >= 0 && caption.right > caption.left && caption.bottom > caption.top,
            ["extended_frame_screen"] = frameResult >= 0 ? WholeWindowBox(frame) : null,
            ["extended_frame_hresult"] = frameResult, ["dpi"] = WholeWindowDpi(handle),
            ["extends_content_into_title_bar"] = ExtendsContentIntoTitleBar,
            ["appwindow_titlebar_height"] = AppWindow.TitleBar.Height,
            ["appwindow_titlebar_left_inset"] = AppWindow.TitleBar.LeftInset,
            ["appwindow_titlebar_right_inset"] = AppWindow.TitleBar.RightInset,
            ["client_xaml_size"] = new JsonObject { ["width"] = root.ActualWidth, ["height"] = root.ActualHeight },
            ["png_width"] = width, ["png_height"] = height
        };
        var flushResult = WholeWindowDwmFlush(); receipt["dwm_flush_hresult"] = flushResult;
        if (flushResult < 0) Marshal.ThrowExceptionForHR(flushResult);
        var dc = GetDC(0); if (dc == 0) throw new InvalidOperationException("Desktop DC unavailable");
        nint memory = 0, bitmap = 0, previous = 0;
        try
        {
            memory = CreateCompatibleDC(dc); bitmap = CreateCompatibleBitmap(dc, width, height);
            if (memory == 0 || bitmap == 0) throw new InvalidOperationException("Desktop capture bitmap allocation failed");
            previous = SelectObject(memory, bitmap);
            if (previous == 0 || previous == -1) throw new InvalidOperationException("Could not select desktop capture bitmap");
            if (!BitBlt(memory, 0, 0, width, height, dc, window.left, window.top, 0x40CC0020))
                throw new InvalidOperationException("Whole-window desktop BitBlt failed");
            SelectObject(memory, previous); previous = 0;
            var info = new BitmapInfo { size = 40, width = width, height = -height, planes = 1, bits = 32, imageSize = checked((uint)(width * height * 4)) };
            var pixels = new byte[checked(width * height * 4)];
            if (GetDIBits(memory, bitmap, 0, (uint)height, pixels, ref info, 0) != height)
                throw new InvalidOperationException("Whole-window GetDIBits did not return every scan line");
            if (!WholeWindowGetRect(handle, out var after) || !window.Equals(after))
                throw new InvalidOperationException("Window moved or resized during desktop readback");
            if (pixels.Where((_, i) => i % 4 != 3).Distinct().Take(12).Count() < 12)
                throw new InvalidOperationException("Whole-window capture is blank");
            using var output = new InMemoryRandomAccessStream();
            var encoder = await BitmapEncoder.CreateAsync(BitmapEncoder.PngEncoderId, output);
            encoder.SetPixelData(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Ignore, (uint)width, (uint)height, 96, 96, pixels);
            await encoder.FlushAsync();
            using var reader = new DataReader(output.GetInputStreamAt(0)); await reader.LoadAsync((uint)output.Size);
            var encoded = new byte[(int)output.Size]; reader.ReadBytes(encoded);
            await System.IO.File.WriteAllBytesAsync(path, encoded);
        }
        finally
        {
            if (previous != 0 && previous != -1) SelectObject(memory, previous);
            if (bitmap != 0) DeleteObject(bitmap);
            if (memory != 0) DeleteDC(memory);
            ReleaseDC(0, dc);
        }
        return receipt;
    }

    private static JsonObject WholeWindowBox(WholeWindowRect box) => new()
    { ["x"] = box.left, ["y"] = box.top, ["width"] = box.right - box.left, ["height"] = box.bottom - box.top };
    [StructLayout(LayoutKind.Sequential)] private struct WholeWindowRect { public int left, top, right, bottom; }
    [StructLayout(LayoutKind.Sequential)] private struct WholeWindowKeyboardInput
    { public ushort virtualKey, scanCode; public uint flags, time; public nuint extraInfo; }
    [StructLayout(LayoutKind.Explicit)] private struct WholeWindowInputData
    {
        [FieldOffset(0)] public CaptureMouseInput mouse;
        [FieldOffset(0)] public WholeWindowKeyboardInput keyboard;
    }
    [StructLayout(LayoutKind.Sequential)] private struct WholeWindowInput { public uint type; public WholeWindowInputData data; }
    [DllImport("user32.dll", EntryPoint = "SendInput", SetLastError = true)] private static extern uint WholeWindowSendInput(uint count, [In] WholeWindowInput[] inputs, int size);
    [DllImport("user32.dll", EntryPoint = "GetWindowRect", SetLastError = true)] private static extern bool WholeWindowGetRect(nint window, out WholeWindowRect rect);
    [DllImport("user32.dll", EntryPoint = "GetClientRect", SetLastError = true)] private static extern bool WholeWindowGetClientRect(nint window, out WholeWindowRect rect);
    [DllImport("user32.dll", EntryPoint = "GetForegroundWindow")] private static extern nint WholeWindowForeground();
    [DllImport("user32.dll", EntryPoint = "GetDpiForWindow")] private static extern uint WholeWindowDpi(nint window);
    [DllImport("user32.dll", EntryPoint = "GetDoubleClickTime")] private static extern uint WholeWindowDoubleClickTime();
    [DllImport("user32.dll", EntryPoint = "SendMessageW")] private static extern nint WholeWindowSendMessage(nint window, uint message, nuint wparam, nint lparam);
    [DllImport("dwmapi.dll", EntryPoint = "DwmGetWindowAttribute")] private static extern int WholeWindowDwmRect(nint window, int attribute, out WholeWindowRect value, int size);
    [DllImport("dwmapi.dll", EntryPoint = "DwmFlush")] private static extern int WholeWindowDwmFlush();
}
