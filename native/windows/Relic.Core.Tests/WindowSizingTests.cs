using Relic.Core;
using Xunit;

namespace Relic.Core.Tests;

public class WindowSizingTests
{
    [Theory]
    [InlineData(1, 1440, 900, 960, 640)]
    [InlineData(1.25, 1800, 1125, 1200, 800)]
    [InlineData(1.5, 2160, 1350, 1440, 960)]
    [InlineData(2, 2880, 1800, 1920, 1280)]
    public void DefaultAndMinimumConvertDipsToPhysicalPixels(double scale, int w, int h, int minW, int minH)
    {
        var monitor = new WindowMonitor("display", new(200, -400, 4000, 3000), scale);
        Assert.Equal(new PixelRect(200 + (4000 - w) / 2, -400 + (3000 - h) / 2, w, h), WindowSizing.Default(monitor));
        Assert.Equal(new PixelSize(minW, minH), WindowSizing.Minimum(monitor));
    }

    [Fact]
    public void Persons4K150PercentScreenOpensCenteredWithoutMaximizing()
    {
        var monitor = new WindowMonitor("4k", new(0, 0, 3840, 2088), 1.5);
        var placement = WindowSizing.Restore(null, [monitor], monitor);
        Assert.Equal(new PixelRect(840, 369, 2160, 1350), placement.Bounds);
        Assert.False(placement.Maximized); Assert.False(placement.Restored);
    }

    [Theory]
    [InlineData(1920, 1040, 1, 1440, 884, 960, 640)]
    [InlineData(1366, 728, 1, 1161, 640, 960, 640)]
    [InlineData(1024, 700, 1, 960, 640, 960, 640)]
    [InlineData(1280, 720, 2, 1280, 720, 1280, 720)]
    [InlineData(3840, 2088, 2, 2880, 1775, 1920, 1280)]
    public void WorkAreaLimitsAndMinimumBothApply(int w, int h, double scale, int dw, int dh, int mw, int mh)
    {
        var monitor = new WindowMonitor("small", new(0, 40, w, h), scale);
        var bounds = WindowSizing.Default(monitor);
        Assert.Equal(new PixelSize(dw, dh), new(bounds.Width, bounds.Height));
        Assert.Equal(new PixelSize(mw, mh), WindowSizing.Minimum(monitor));
        Assert.InRange(bounds.Y, 40, 40 + h - dh);
    }

    [Fact]
    public void SavedDipsSurviveScaleAndMonitorOriginChanges()
    {
        var old = new WindowMonitor("second", new(-2560, 0, 2560, 1440), 1.25);
        var saved = WindowSizing.Save(new(-2435, 100, 1500, 1000), old, true);
        var moved = new WindowMonitor("second", new(3840, -100, 3840, 2088), 1.5);
        var restored = WindowSizing.Restore(saved, [moved], moved);
        Assert.Equal(new PixelRect(3990, 20, 1800, 1200), restored.Bounds);
        Assert.True(restored.Maximized); Assert.True(restored.Restored);
    }

    [Fact]
    public void PartiallyOffscreenPlacementClampsAndTinySavedSizeUsesMinimum()
    {
        var monitor = new WindowMonitor("screen", new(100, 50, 1920, 1040), 1);
        var restored = WindowSizing.Restore(new("screen", -300, 1000, 700, 400, false), [monitor], monitor);
        Assert.Equal(new PixelRect(100, 450, 960, 640), restored.Bounds);
    }

    [Theory]
    [InlineData("disconnected", 1200, 800)]
    [InlineData("screen", 4000, 800)]
    [InlineData("screen", 1200, 3000)]
    [InlineData("screen", -1, 800)]
    [InlineData("screen", double.NaN, 800)]
    public void UnrestorablePlacementFallsBackToNormalDefault(string id, double w, double h)
    {
        var monitor = new WindowMonitor("screen", new(0, 0, 1920, 1040), 1);
        var restored = WindowSizing.Restore(new(id, 0, 0, w, h, true), [monitor], monitor);
        Assert.Equal(WindowSizing.Default(monitor), restored.Bounds);
        Assert.False(restored.Maximized); Assert.False(restored.Restored);
    }

    [Theory]
    [InlineData(1440, 276, 340)]
    [InlineData(1180, 276, 340)]
    [InlineData(820, 236, 340)]
    [InlineData(400, 236, 352)]
    public void ReflowUsesReferenceBreakpoints(double viewport, double side, double panel)
    {
        Assert.Equal(side, ResponsiveLayout.SidebarWidth(viewport, 276));
        Assert.Equal(panel, ResponsiveLayout.InspectorWidth(viewport, viewport == 400 ? 520 : 340));
        Assert.Equal(300, ResponsiveLayout.SidebarWidth(viewport, 300));
    }
}
