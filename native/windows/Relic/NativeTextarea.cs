using Microsoft.UI.Input;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Windows.Foundation;

namespace Relic;

// The platform TextBox remains the editor, including its IME, selection,
// placeholder, clipboard and ScrollViewer. A production Thumb adds resizing
// to that same template; capture never assigns the size itself.
public sealed class NativeTextarea : TextBox
{
    private double initialWidth, initialHeight, fallbackX, fallbackY;
    private Point? initialPointer;
    public NativeTextareaResizeGrip? ResizeGrip { get; private set; }
    public string ResizeAccessibleName { get; set; } = "";
    public nint OwnerWindowHandle { get; set; }
    public string? ResizeTemplateFailure { get; private set; }
    public long ResizeSequence { get; private set; }
    public long ResizeDeltaCount { get; private set; }
    public bool IsResizing { get; private set; }
    public event Action<NativeTextareaResizeEvent>? ResizeObserved;

    public NativeTextarea()
    {
        DefaultStyleKey = typeof(TextBox);
        AcceptsReturn = true;
        TextWrapping = TextWrapping.Wrap;
        ScrollViewer.SetVerticalScrollMode(this, ScrollMode.Auto);
        ScrollViewer.SetVerticalScrollBarVisibility(this, ScrollBarVisibility.Auto);
        ScrollViewer.SetHorizontalScrollMode(this, ScrollMode.Disabled);
        ScrollViewer.SetHorizontalScrollBarVisibility(this, ScrollBarVisibility.Disabled);
        IsEnabledChanged += (_, _) => { if (ResizeGrip != null) ResizeGrip.Handle.IsEnabled = IsEnabled; };
        ActualThemeChanged += (_, _) => UpdateGripPaint();
    }

    protected override void OnApplyTemplate()
    {
        if (ResizeGrip is { } previous && VisualTreeHelper.GetParent(previous) is Panel oldParent)
            oldParent.Children.Remove(previous);
        ResizeGrip = null;
        base.OnApplyTemplate();
        ResizeTemplateFailure = null;
        if (GetTemplateChild("BorderElement") is not FrameworkElement border || VisualTreeHelper.GetParent(border) is not Grid grid)
        {
            ResizeTemplateFailure = "The actual TextBox template has no BorderElement parent Grid for the production resize Thumb.";
            return;
        }
        var grip = new NativeTextareaResizeGrip
        {
            Width = 14, Height = 14, MinWidth = 0, MinHeight = 0,
            HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Bottom,
            Margin = new Thickness(0, 0, 1, 1),
        };
        grip.Handle.IsEnabled = IsEnabled;
        AutomationProperties.SetAutomationId(grip.Handle, "textarea-resize-handle");
        AutomationProperties.SetName(grip.Handle, ResizeAccessibleName);
        AutomationProperties.SetLabeledBy(grip.Handle, this);
        Grid.SetRow(grip, Grid.GetRow(border)); Grid.SetColumn(grip, Grid.GetColumn(border));
        Grid.SetRowSpan(grip, Grid.GetRowSpan(border)); Grid.SetColumnSpan(grip, Grid.GetColumnSpan(border));
        Canvas.SetZIndex(grip, 10);
        grip.Handle.DragStarted += (_, _) =>
        {
            IsResizing = true; ResizeSequence++;
            initialWidth = ActualWidth; initialHeight = ActualHeight; fallbackX = fallbackY = 0;
            initialPointer = MouseInRoot();
            Observe("drag-started", 0, 0, initialWidth, initialHeight, false, "actual Thumb DragStarted");
        };
        grip.Handle.DragDelta += (_, args) =>
        {
            if (!IsResizing) return;
            fallbackX += args.HorizontalChange; fallbackY += args.VerticalChange;
            var currentPointer = MouseInRoot();
            var hasRootPointer = initialPointer.HasValue && currentPointer.HasValue;
            var dx = hasRootPointer ? currentPointer!.Value.X - initialPointer!.Value.X : fallbackX;
            var dy = hasRootPointer ? currentPointer!.Value.Y - initialPointer!.Value.Y : fallbackY;
            var minimumHeight = Math.Max(MinHeight, Padding.Top + Padding.Bottom + BorderThickness.Top + BorderThickness.Bottom + FontSize * 1.6);
            var minimumWidth = Math.Max(MinWidth, Padding.Left + Padding.Right + BorderThickness.Left + BorderThickness.Right + 20);
            var requestedHeight = Math.Clamp(initialHeight + dy, minimumHeight, Math.Max(minimumHeight, MaxHeight));
            var requestedWidth = Math.Clamp(initialWidth + dx, minimumWidth, Math.Max(minimumWidth, MaxWidth));
            // Preserve stretch while a purely vertical gesture has not asked
            // for a horizontal change. Root-space input avoids dialog-centering
            // feedback when the resized form itself moves during the drag.
            if (dx != 0) Width = requestedWidth;
            Height = requestedHeight;
            ResizeDeltaCount++;
            Observe("drag-delta", args.HorizontalChange, args.VerticalChange, requestedWidth, requestedHeight, false,
                hasRootPointer ? "actual Win32 cursor mapped to window/root coordinates" : "actual Thumb DragDelta accumulation");
        };
        grip.Handle.DragCompleted += (_, args) =>
        {
            IsResizing = false;
            Observe("drag-completed", args.HorizontalChange, args.VerticalChange, ActualWidth, ActualHeight, args.Canceled, "actual Thumb DragCompleted");
        };
        ResizeGrip = grip;
        UpdateGripPaint();
        grid.Children.Add(grip);
    }

    private void UpdateGripPaint()
    {
        if (ResizeGrip != null) ResizeGrip.Handle.Foreground = new SolidColorBrush(ActualTheme == ElementTheme.Dark
            ? Windows.UI.Color.FromArgb(255, 138, 135, 127) : Windows.UI.Color.FromArgb(255, 143, 140, 134));
    }

    private void Observe(string kind, double dx, double dy, double requestedWidth, double requestedHeight, bool canceled, string source) =>
        ResizeObserved?.Invoke(new(kind, Stopwatch.GetTimestamp(), ResizeSequence, ResizeDeltaCount, dx, dy,
            ActualWidth, ActualHeight, requestedWidth, requestedHeight, canceled, source));

    private Point? MouseInRoot()
    {
        // Thumb can move when a centered dialog grows. Read the mouse in the
        // stationary window coordinate space, not relative to the moving grip.
        if (OwnerWindowHandle == 0 || ResizeGrip?.PointerDevice is not (null or "Mouse")) return null;
        var point = new NativePoint();
        if (!GetCursorPos(ref point) || !ScreenToClient(OwnerWindowHandle, ref point)) return null;
        var scale = XamlRoot?.RasterizationScale ?? 1;
        return new Point(point.X / scale, point.Y / scale);
    }
    [StructLayout(LayoutKind.Sequential)] private struct NativePoint { public int X, Y; }
    [DllImport("user32.dll")] private static extern bool GetCursorPos(ref NativePoint point);
    [DllImport("user32.dll")] private static extern bool ScreenToClient(nint window, ref NativePoint point);
}

public sealed record NativeTextareaResizeEvent(string Kind, long Timestamp, long Sequence, long DeltaCount,
    double HorizontalChange, double VerticalChange, double ActualWidth, double ActualHeight,
    double RequestedWidth, double RequestedHeight, bool Canceled, string Source);

public sealed class NativeTextareaResizeGrip : Grid
{
    public Thumb Handle { get; }
    public Point? PointerInRoot { get; private set; }
    public uint? ActualPointerId { get; private set; }
    public bool IsPointerOverGrip { get; private set; }
    public string? PointerDevice { get; private set; }

    public NativeTextareaResizeGrip()
    {
        ProtectedCursor = InputSystemCursor.Create(InputSystemCursorShape.SizeNorthwestSoutheast);
        Handle = new Thumb { MinWidth = 0, MinHeight = 0, IsTabStop = false,
            Template = (ControlTemplate)XamlReader.Load("""
          <ControlTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" TargetType="Thumb">
            <Grid Background="Transparent" UseLayoutRounding="False">
              <Path Data="M3,12 L12,3 M7,12 L12,7 M11,12 L12,11" Stroke="{TemplateBinding Foreground}"
                    StrokeThickness="1" StrokeStartLineCap="Flat" StrokeEndLineCap="Flat" StrokeLineJoin="Miter"
                    IsHitTestVisible="False" UseLayoutRounding="False"/>
            </Grid>
          </ControlTemplate>
          """) };
        Children.Add(Handle);
        foreach (var routedEvent in new[] { UIElement.PointerPressedEvent, UIElement.PointerMovedEvent, UIElement.PointerReleasedEvent })
            Handle.AddHandler(routedEvent, new PointerEventHandler((_, args) => ReadPointer(args)), true);
        Handle.PointerEntered += (_, args) => { ReadPointer(args); IsPointerOverGrip = true; };
        Handle.PointerExited += (_, args) => { ReadPointer(args); IsPointerOverGrip = false; };
    }

    private void ReadPointer(PointerRoutedEventArgs args)
    {
        if (XamlRoot?.Content is UIElement content) PointerInRoot = args.GetCurrentPoint(content).Position;
        ActualPointerId = args.Pointer.PointerId;
        PointerDevice = args.Pointer.PointerDeviceType.ToString();
    }
}
