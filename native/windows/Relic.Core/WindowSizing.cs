namespace Relic.Core;

public readonly record struct PixelSize(int Width, int Height);
public readonly record struct PixelRect(int X, int Y, int Width, int Height);
public sealed record WindowMonitor(string Id, PixelRect WorkArea, double Scale);
public sealed record SavedWindowPlacement(string MonitorId, double OffsetX, double OffsetY,
    double Width, double Height, bool Maximized);
public sealed record WindowPlacement(PixelRect Bounds, bool Maximized, bool Restored);

// All saved values are DIPs relative to the selected monitor's work area.
// Only this boundary converts them to the physical pixels AppWindow expects.
public static class WindowSizing
{
    public static int Pixels(double dips, double scale) => checked((int)Math.Round(dips * scale, MidpointRounding.AwayFromZero));

    public static PixelSize Minimum(WindowMonitor monitor) => new(
        Math.Min(Pixels(960, monitor.Scale), monitor.WorkArea.Width),
        Math.Min(Pixels(640, monitor.Scale), monitor.WorkArea.Height));

    public static PixelRect Default(WindowMonitor monitor)
    {
        var work = monitor.WorkArea; var minimum = Minimum(monitor);
        // Near the minimum screen size, the usable minimum takes precedence
        // over the 85% preference, while never exceeding the work area.
        var width = Math.Max(minimum.Width, Math.Min(Pixels(1440, monitor.Scale), Pixels(work.Width, .85)));
        var height = Math.Max(minimum.Height, Math.Min(Pixels(900, monitor.Scale), Pixels(work.Height, .85)));
        return new(work.X + (work.Width - width) / 2, work.Y + (work.Height - height) / 2, width, height);
    }

    public static WindowPlacement Restore(SavedWindowPlacement? saved, IReadOnlyList<WindowMonitor> monitors, WindowMonitor fallback)
    {
        var monitor = saved == null ? null : monitors.FirstOrDefault(m => m.Id == saved.MonitorId);
        if (saved == null || monitor == null || !double.IsFinite(saved.Width) || !double.IsFinite(saved.Height)
            || !double.IsFinite(saved.OffsetX) || !double.IsFinite(saved.OffsetY) || saved.Width <= 0 || saved.Height <= 0
            || saved.Width * monitor.Scale > monitor.WorkArea.Width || saved.Height * monitor.Scale > monitor.WorkArea.Height
            || Math.Abs(saved.OffsetX) > int.MaxValue / monitor.Scale || Math.Abs(saved.OffsetY) > int.MaxValue / monitor.Scale)
            return new(Default(fallback), false, false);
        var work = monitor.WorkArea; var minimum = Minimum(monitor);
        var width = Math.Max(minimum.Width, Pixels(saved.Width, monitor.Scale));
        var height = Math.Max(minimum.Height, Pixels(saved.Height, monitor.Scale));
        var x = work.X + Math.Clamp(Pixels(saved.OffsetX, monitor.Scale), 0, work.Width - width);
        var y = work.Y + Math.Clamp(Pixels(saved.OffsetY, monitor.Scale), 0, work.Height - height);
        return new(new(x, y, width, height), saved.Maximized, true);
    }

    public static SavedWindowPlacement Save(PixelRect normalBounds, WindowMonitor monitor, bool maximized) => new(
        monitor.Id, (normalBounds.X - monitor.WorkArea.X) / monitor.Scale, (normalBounds.Y - monitor.WorkArea.Y) / monitor.Scale,
        normalBounds.Width / monitor.Scale, normalBounds.Height / monitor.Scale, maximized);
}

public static class ResponsiveLayout
{
    public const double InspectorOverlayWidth = 1180;
    public const double CompactSidebarWidth = 820;
    public const double HiddenTitleWidth = 900;
    public static double SidebarWidth(double viewport, double preferred) =>
        Math.Min(viewport, viewport <= CompactSidebarWidth && preferred == 276 ? 236 : preferred);
    public static double InspectorWidth(double viewport, double preferred) => viewport <= InspectorOverlayWidth
        ? Math.Min(preferred, Math.Max(0, viewport - 48))
        : Math.Clamp(preferred, 280, Math.Max(280, viewport * .6));
}
