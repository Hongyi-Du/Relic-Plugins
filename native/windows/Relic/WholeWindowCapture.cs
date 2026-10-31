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
                await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(manifestDirectory, "current-case.txt"), id);
                try
                {
                    if (shot.Text("scene") != "group") throw new InvalidOperationException("Whole-window capture supports the real group scene only");
                    var width = int.Parse(shot.Text("width")); var height = int.Parse(shot.Text("height"));
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
                    sideWidth = 276; panelWidth = 340; sideOpen = true; panelOpen = width > 1180;
                    pane = "overview"; threadId = ""; plainMode = false; digestOpen = false;
                    folded.Clear(); search.Text = ""; editor.Text = ""; ClearQuote();
                    await Select(prepared.Text("org")); LayoutColumns(); root.UpdateLayout();
                    var handle = WinRT.Interop.WindowNative.GetWindowHandle(this);
                    SetForegroundWindow(handle);
                    await CaptureMoveScreenPointer(1900, 1040);
                    await Task.Delay(350); root.UpdateLayout();
                    if (error.IsOpen) throw new InvalidOperationException("Production UI reported: " + error.Message);
                    if (!editor.IsDocumentReady) throw new InvalidOperationException("Native composer did not initialize: " + editor.InitializationFailure);
                    if (WholeWindowForeground() != handle) throw new InvalidOperationException("Relic is not the foreground window for desktop capture");
                    var restoredWindow = await VerifyWholeWindowActions(actions);
                    await CaptureMoveScreenPointer(1900, 1040);
                    await Task.Delay(150); root.UpdateLayout();
                    var receipt = await CaptureWholeWindowPixels(System.IO.Path.Combine(output, shot.Text("file")), width, height);
                    receipt["case_id"] = id;
                    receipt["language"] = words.Language;
                    receipt["theme"] = root.ActualTheme.ToString().ToLowerInvariant();
                    receipt["actual_actions"] = actions.DeepClone();
                    receipt["restored_window_screen"] = WholeWindowBox(restoredWindow);
                    await System.IO.File.WriteAllTextAsync(System.IO.Path.Combine(output, id + ".window-chrome.json"), receipt.ToJsonString());
                    count++;
                    Console.WriteLine("Relic whole-window capture: " + shot.Text("file"));
                }
                catch (Exception ex) { failures.Add(id + ": " + ex); }
                finally
                {
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
        var menuAction = new JsonObject { ["action"] = "real pointer click File menu twice", ["before_open"] = entry.Flyout.IsOpen };
        actions.Add(menuAction);
        await CaptureClick(entry.Anchor); await Task.Delay(150);
        menuAction["after_first_open"] = entry.Flyout.IsOpen;
        menuAction["same_open_menu"] = ReferenceEquals(openNativeMenu, entry);
        if (!entry.Flyout.IsOpen || !ReferenceEquals(openNativeMenu, entry)) throw new InvalidOperationException("Real menu click did not open its production flyout");
        await CaptureClick(entry.Anchor); await Task.Delay(150);
        menuAction["after_second_open"] = entry.Flyout.IsOpen;
        if (entry.Flyout.IsOpen || openNativeMenu != null) throw new InvalidOperationException("Real second menu click did not close its production flyout");
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
        if (!ClientToScreen(handle, ref origin) || !WholeWindowGetRect(handle, out var window))
            throw new InvalidOperationException("Title gesture could not bind actual client/window coordinates");
        var captionResult = WholeWindowDwmRect(handle, 5, out var caption, Marshal.SizeOf<WholeWindowRect>());
        var screenX = origin.x + clientX; var screenY = origin.y + clientY;
        var windowX = screenX - window.left; var windowY = screenY - window.top;
        if (captionResult < 0 || caption.right <= caption.left || caption.bottom <= caption.top
            || windowX >= caption.left && windowX < caption.right && windowY >= caption.top && windowY < caption.bottom)
            throw new InvalidOperationException("Title gesture could not exclude the actual system caption buttons");
        var doubleClickTime = WholeWindowDoubleClickTime();
        var interval = (int)Math.Clamp(doubleClickTime / 4, 1u, 50u);
        var record = new JsonObject { ["action"] = "real title-area double click " + action,
            ["before_state"] = presenter.State.ToString(), ["scale"] = scale,
            ["client_dip"] = new JsonObject { ["x"] = point.X, ["y"] = point.Y },
            ["screen_pixel"] = new JsonObject { ["x"] = screenX, ["y"] = screenY },
            ["caption_buttons_window"] = WholeWindowBox(caption), ["system_double_click_time_ms"] = doubleClickTime,
            ["inter_click_delay_ms"] = interval, ["outside_passthrough_and_caption"] = true };
        actions.Add(record);
        await CaptureMoveScreenPointer(screenX, screenY);
        for (var click = 0; click < 2; click++)
        {
            CapturePointerButton(true);
            try { await Task.Delay(10); }
            finally { CapturePointerButton(false); }
            if (click == 0) await Task.Delay(interval);
        }
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
        if (captionResult < 0 || caption.right <= caption.left || caption.bottom <= caption.top)
            throw new InvalidOperationException($"System caption-button bounds unavailable: HRESULT 0x{captionResult:X8}");
        var receipt = new JsonObject
        {
            ["source"] = "CI desktop BitBlt of actual GetWindowRect, including system caption buttons",
            ["requested_window_size"] = new JsonObject { ["width"] = requestedWidth, ["height"] = requestedHeight },
            ["window_screen"] = WholeWindowBox(window),
            ["client_screen"] = WholeWindowBox(new() { left = origin.x, top = origin.y,
                right = origin.x + client.right - client.left, bottom = origin.y + client.bottom - client.top }),
            ["caption_buttons_window"] = WholeWindowBox(caption), ["caption_buttons_hresult"] = captionResult,
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
    [DllImport("user32.dll", EntryPoint = "GetWindowRect", SetLastError = true)] private static extern bool WholeWindowGetRect(nint window, out WholeWindowRect rect);
    [DllImport("user32.dll", EntryPoint = "GetClientRect", SetLastError = true)] private static extern bool WholeWindowGetClientRect(nint window, out WholeWindowRect rect);
    [DllImport("user32.dll", EntryPoint = "GetForegroundWindow")] private static extern nint WholeWindowForeground();
    [DllImport("user32.dll", EntryPoint = "GetDpiForWindow")] private static extern uint WholeWindowDpi(nint window);
    [DllImport("user32.dll", EntryPoint = "GetDoubleClickTime")] private static extern uint WholeWindowDoubleClickTime();
    [DllImport("dwmapi.dll", EntryPoint = "DwmGetWindowAttribute")] private static extern int WholeWindowDwmRect(nint window, int attribute, out WholeWindowRect value, int size);
    [DllImport("dwmapi.dll", EntryPoint = "DwmFlush")] private static extern int WholeWindowDwmFlush();
}
