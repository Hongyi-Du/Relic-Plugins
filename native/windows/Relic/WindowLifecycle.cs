using Microsoft.UI;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Relic.Core;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text.Json;

namespace Relic;

public sealed partial class MainWindow
{
    private readonly DispatcherTimer placementTimer = new() { Interval = TimeSpan.FromMilliseconds(350) };
    private readonly LatestStateWriter windowStateWriter = new();
    private WindowSubclass? placementSubclass;
    private SavedWindowPlacement? normalPlacement;
    private bool applyingPlacement;
    private uint windowDpi;
    private WindowPlacement? startupPlacement;
    private string WindowStatePath => System.IO.Path.Combine(System.IO.Path.GetDirectoryName(StatePath)!, "window.json");

    private void ConfigureWindowPlacement()
    {
        var handle = WinRT.Interop.WindowNative.GetWindowHandle(this);
        windowDpi = NativeWindowDpi(handle);
        placementSubclass = WindowPlacementMessage;
        if (!SetWindowSubclass(handle, placementSubclass, 0x52454c49, 0))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not register window size handling");
        var current = CurrentWindowMonitor();
        // This Windows App SDK vector view supports Count/GetAt but its
        // IReadOnlyList projection does not expose IEnumerable on all builds.
        // Index it directly; LINQ enumeration otherwise aborts startup with
        // E_NOINTERFACE before any window is shown (CI d67957a).
        var displays = DisplayArea.FindAll();
        var monitors = new List<WindowMonitor>();
        for (var index = 0; index < displays.Count; index++) monitors.Add(DescribeMonitor(displays[index]));
        SavedWindowPlacement? saved = null;
        try
        {
            if (System.IO.File.Exists(WindowStatePath))
                saved = JsonSerializer.Deserialize<SavedWindowPlacement>(System.IO.File.ReadAllText(WindowStatePath));
        }
        catch (Exception error) when (error is System.IO.IOException or UnauthorizedAccessException or JsonException) { }
        startupPlacement = WindowSizing.Restore(saved, monitors, current);
        applyingPlacement = true;
        try
        {
            var bounds = startupPlacement.Bounds;
            AppWindow.MoveAndResize(new(bounds.X, bounds.Y, bounds.Width, bounds.Height));
            normalPlacement = WindowSizing.Save(bounds, CurrentWindowMonitor(), startupPlacement.Maximized);
            if (startupPlacement.Maximized && AppWindow.Presenter is OverlappedPresenter presenter) presenter.Maximize();
        }
        finally { applyingPlacement = false; }
        placementTimer.Tick += (_, _) => { placementTimer.Stop(); SaveWindowPlacement(); };
        AppWindow.Changed += (_, args) =>
        {
            if (applyingPlacement || closing || !(args.DidPositionChange || args.DidSizeChange || args.DidPresenterChange)) return;
            placementTimer.Stop(); placementTimer.Start();
        };
    }

    private WindowMonitor CurrentWindowMonitor() => DescribeMonitor(
        DisplayArea.GetFromWindowId(AppWindow.Id, DisplayAreaFallback.Nearest),
        (windowDpi != 0 ? windowDpi : NativeWindowDpi(WinRT.Interop.WindowNative.GetWindowHandle(this))) / 96d);

    private static WindowMonitor DescribeMonitor(DisplayArea area, double? windowScale = null)
    {
        var monitor = Win32Interop.GetMonitorFromDisplayId(area.DisplayId);
        var info = new MonitorInfo { Size = Marshal.SizeOf<MonitorInfo>(), Device = "" };
        if (!GetMonitorInfo(monitor, ref info)) throw new Win32Exception(Marshal.GetLastWin32Error());
        var scale = windowScale;
        if (scale == null)
        {
            Marshal.ThrowExceptionForHR(GetDpiForMonitor(monitor, 0, out var dpi, out _));
            scale = dpi / 96d;
        }
        var work = area.WorkArea;
        return new(info.Device, new(work.X, work.Y, work.Width, work.Height), scale.Value);
    }

    private void SaveWindowPlacement()
    {
        if (applyingPlacement || normalPlacement == null || AppWindow.Presenter is not OverlappedPresenter presenter
            || presenter.State == OverlappedPresenterState.Minimized) return;
        if (presenter.State == OverlappedPresenterState.Restored)
        {
            var position = AppWindow.Position; var size = AppWindow.Size;
            normalPlacement = WindowSizing.Save(new(position.X, position.Y, size.Width, size.Height), CurrentWindowMonitor(), false);
        }
        else normalPlacement = normalPlacement with { Maximized = true };
        windowStateWriter.Queue(WindowStatePath, JsonSerializer.SerializeToNode(normalPlacement)!);
    }

    private nint WindowPlacementMessage(nint handle, uint message, nuint wparam, nint lparam, nuint id, nuint data)
    {
        if (message == 0x0024) // WM_GETMINMAXINFO uses physical screen pixels.
        {
            var result = DefSubclassProc(handle, message, wparam, lparam);
            var info = Marshal.PtrToStructure<MinMaxInfo>(lparam);
            var minimum = WindowSizing.Minimum(CurrentWindowMonitor());
            info.MinTrackSize = new() { X = minimum.Width, Y = minimum.Height };
            Marshal.StructureToPtr(info, lparam, false);
            return result;
        }
        if (message == 0x02e0) // WM_DPICHANGED
        {
            windowDpi = (uint)(wparam & 0xffff);
            var suggested = Marshal.PtrToStructure<WindowRect>(lparam);
            // Let WinUI update its XamlRoot/rasterization first, then honor the
            // OS-provided rectangle. Never reapply startup dimensions on a DPI
            // change: that would discard the person's chosen logical size.
            var result = DefSubclassProc(handle, message, wparam, lparam);
            if (!applyingPlacement)
                SetWindowPos(handle, 0, suggested.Left, suggested.Top, suggested.Right - suggested.Left,
                    suggested.Bottom - suggested.Top, 0x0014); // NOZORDER | NOACTIVATE
            return result;
        }
        if (message == 0x0082) RemoveWindowSubclass(handle, placementSubclass!, id); // WM_NCDESTROY
        return DefSubclassProc(handle, message, wparam, lparam);
    }

    [StructLayout(LayoutKind.Sequential)] private struct WindowPoint { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] private struct WindowRect { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] private struct MinMaxInfo
    { public WindowPoint Reserved, MaxSize, MaxPosition, MinTrackSize, MaxTrackSize; }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] private struct MonitorInfo
    {
        public int Size; public WindowRect Monitor, Work; public uint Flags;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string Device;
    }
    private delegate nint WindowSubclass(nint handle, uint message, nuint wparam, nint lparam, nuint id, nuint data);
    [DllImport("comctl32.dll", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetWindowSubclass(nint handle, WindowSubclass callback, nuint id, nuint data);
    [DllImport("comctl32.dll")] private static extern nint DefSubclassProc(nint handle, uint message, nuint wparam, nint lparam);
    [DllImport("comctl32.dll")] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool RemoveWindowSubclass(nint handle, WindowSubclass callback, nuint id);
    [DllImport("user32.dll", EntryPoint = "GetDpiForWindow")] private static extern uint NativeWindowDpi(nint handle);
    [DllImport("user32.dll", EntryPoint = "GetMonitorInfoW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool GetMonitorInfo(nint handle, ref MonitorInfo info);
    [DllImport("shcore.dll")] private static extern int GetDpiForMonitor(nint monitor, int type, out uint x, out uint y);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetWindowPos(nint handle, nint after, int x, int y, int width, int height, uint flags);
}
