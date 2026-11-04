using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using Microsoft.UI.Xaml;
using Windows.Foundation;

namespace Relic;

public sealed partial class MainWindow
{
    private JsonArray capturePointerReceipts = new();

    // SetCursorPos alone changed the measured cursor in the hosted capture,
    // but produced no intermediate routed moves during the textarea drag.
    // Use the actual Windows input stream for every CI gesture instead.
    private async Task CaptureMovePointer(Point contentPoint)
    {
        if (!VisualCaptureEnabled && !PerformanceEnabled) throw new InvalidOperationException("CI capture input only");
        var origin = new CapturePoint();
        if (!ClientToScreen(WinRT.Interop.WindowNative.GetWindowHandle(this), ref origin))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Capture ClientToScreen failed");
        var scale = root.XamlRoot.RasterizationScale;
        await CaptureMoveScreenPointer(origin.x + (int)Math.Round(contentPoint.X * scale), origin.y + (int)Math.Round(contentPoint.Y * scale));
    }

    private async Task CaptureMoveScreenPointer(int x, int y)
    {
        if (!VisualCaptureEnabled && !PerformanceEnabled) throw new InvalidOperationException("CI capture input only");
        var left = GetSystemMetrics(76); var top = GetSystemMetrics(77);
        var width = GetSystemMetrics(78); var height = GetSystemMetrics(79);
        if (width <= 0 || height <= 0 || x < left || x >= left + width || y < top || y >= top + height)
            throw new InvalidOperationException($"Capture pointer target {x},{y} is outside actual desktop {left},{top},{width},{height}");
        var eventRecord = new JsonObject { ["operation"] = "SendInput absolute virtual-desktop mouse move",
            ["requested_screen_x"] = x, ["requested_screen_y"] = y,
            ["desktop"] = new JsonObject { ["x"] = left, ["y"] = top, ["width"] = width, ["height"] = height } };
        capturePointerReceipts.Add(eventRecord);
        SendCaptureMouse(new CaptureMouseInput
        {
            X = (int)Math.Floor((x - left + .5) * 65536 / width),
            Y = (int)Math.Floor((y - top + .5) * 65536 / height),
            Flags = 0x0001 | 0x2000 | 0x4000 | 0x8000,
        });
        // Give the real input queue a turn; do not invoke production handlers.
        await Task.Delay(30);
        var cursor = new CapturePoint();
        if (!GetCursorPos(ref cursor)) throw new InvalidOperationException("Capture could not observe the actual cursor after SendInput");
        eventRecord["observed_screen_x"] = cursor.x; eventRecord["observed_screen_y"] = cursor.y;
        if (cursor.x != x || cursor.y != y)
            throw new InvalidOperationException($"Actual cursor {cursor.x},{cursor.y} differs from requested {x},{y}");
    }

    private void CapturePointerButton(bool down)
    {
        if (!VisualCaptureEnabled && !PerformanceEnabled) throw new InvalidOperationException("CI capture input only");
        SendCaptureMouse(new CaptureMouseInput { Flags = down ? 0x0002u : 0x0004u });
        capturePointerReceipts.Add(new JsonObject { ["operation"] = down ? "SendInput left down" : "SendInput left up" });
    }

    private static void SendCaptureMouse(CaptureMouseInput mouse)
    {
        var inputs = new[] { new CaptureInput { Type = 0, Mouse = mouse } };
        if (SendInput(1, inputs, Marshal.SizeOf<CaptureInput>()) != 1)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Capture SendInput did not insert the requested event");
    }

    // MOUSEINPUT is the largest member of the INPUT union on x86 and x64.
    [StructLayout(LayoutKind.Sequential)] private struct CaptureMouseInput
    { public int X, Y; public uint Data, Flags, Time; public nuint ExtraInfo; }
    [StructLayout(LayoutKind.Sequential)] private struct CaptureInput
    { public uint Type; public CaptureMouseInput Mouse; }
    [DllImport("user32.dll", SetLastError = true)] private static extern uint SendInput(uint count, [In] CaptureInput[] inputs, int size);
    [DllImport("user32.dll")] private static extern int GetSystemMetrics(int index);
}
