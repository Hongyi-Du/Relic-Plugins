namespace Relic;

// A WinUI text provider returns RasterizedClient, not physical screen space.
// The actual owner->XamlRoot.Content transform is supplied by the live view.
// No accessibility bounding rectangle or clipped origin participates in it.
internal static class NativePathCoordinates
{
    internal readonly record struct Point(double X, double Y);
    internal readonly record struct Bounds(double X, double Y, double Width, double Height);

    internal static Bounds? ToRasterizedClient(Bounds local, Bounds clip,
        Func<Bounds, Bounds> ownerToRoot, double rasterizationScale)
    {
        RequireScale(rasterizationScale);
        RequireBounds(local); RequireBounds(clip);
        var left = Math.Max(local.X, clip.X); var top = Math.Max(local.Y, clip.Y);
        var right = Math.Min(local.X + local.Width, clip.X + clip.Width);
        var bottom = Math.Min(local.Y + local.Height, clip.Y + clip.Height);
        if (right <= left || bottom <= top) return null;
        var root = ownerToRoot(new Bounds(left, top, right - left, bottom - top));
        RequireBounds(root);
        var result = new Bounds(root.X * rasterizationScale, root.Y * rasterizationScale,
            root.Width * rasterizationScale, root.Height * rasterizationScale);
        RequireBounds(result);
        return result;
    }

    internal static Point ToOwner(Point rasterizedClient, Func<Point, Point> rootToOwner, double rasterizationScale)
    {
        RequireScale(rasterizationScale);
        RequirePoint(rasterizedClient);
        var result = rootToOwner(new Point(rasterizedClient.X / rasterizationScale,
            rasterizedClient.Y / rasterizationScale));
        RequirePoint(result);
        return result;
    }

    private static void RequireScale(double scale)
    {
        if (!double.IsFinite(scale) || scale <= 0)
            throw new InvalidOperationException("The actual XamlRoot rasterization scale is unavailable or invalid");
    }
    private static void RequirePoint(Point point)
    {
        if (!double.IsFinite(point.X) || !double.IsFinite(point.Y))
            throw new InvalidOperationException("The actual text-provider coordinate is nonfinite");
    }
    private static void RequireBounds(Bounds bounds)
    {
        RequirePoint(new Point(bounds.X, bounds.Y));
        if (!double.IsFinite(bounds.Width) || !double.IsFinite(bounds.Height) || bounds.Width < 0 || bounds.Height < 0)
            throw new InvalidOperationException("The actual text-provider range or clip is invalid");
    }
}
