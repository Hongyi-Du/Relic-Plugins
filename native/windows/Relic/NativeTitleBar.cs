using Microsoft.UI;
using Microsoft.UI.Input;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Foundation;
using Windows.Graphics;

namespace Relic;

public sealed partial class MainWindow
{
    private InputNonClientPointerSource? titlebarInput;
    private XamlRoot? titlebarXamlRoot;
    private RectInt32[] titlebarInteractiveRects = [];
    private bool titlebarLayoutDirty = true;
    private long titlebarLayoutNotifications, titlebarLayoutMeasurements;

    private void ConfigureNativeTitleBar()
    {
        // WinUI owns dragging, double-click maximize/restore and the system
        // menu. Leave the overlapped frame and caption buttons with Windows,
        // including the maximize button's Snap Layouts behavior.
        SetTitleBar(titlebarRegion);
        titlebarInput = InputNonClientPointerSource.GetForWindowId(AppWindow.Id);
        titlebarRegion.Loaded += (_, _) =>
        {
            titlebarXamlRoot = titlebarRegion.XamlRoot;
            titlebarXamlRoot.Changed += NativeTitleBarRootChanged;
            titlebarLayoutDirty = true;
            PaintNativeCaptionButtons();
            UpdateNativeTitleBarLayout();
        };
        titlebarRegion.Unloaded += (_, _) =>
        {
            if (titlebarXamlRoot != null) titlebarXamlRoot.Changed -= NativeTitleBarRootChanged;
            titlebarXamlRoot = null;
        };
        // LayoutUpdated is global: scrolling or measuring a chat can raise it
        // thousands of times without moving a title-bar control. Recalculate
        // only after an actual owner size, DPI or command-content change.
        foreach (var owner in new FrameworkElement[] { titlebarRegion, navigationButtons, menu, toolbar })
            owner.SizeChanged += (_, _) => titlebarLayoutDirty = true;
        AppWindow.Changed += (_, args) =>
        {
            if (args.DidSizeChange || args.DidPresenterChange) titlebarLayoutDirty = true;
        };
        titlebarRegion.LayoutUpdated += (_, _) =>
        {
            titlebarLayoutNotifications++;
            if (titlebarLayoutDirty) UpdateNativeTitleBarLayout();
        };
        root.ActualThemeChanged += (_, _) => PaintNativeCaptionButtons();
        PaintNativeCaptionButtons();
    }

    private void NativeTitleBarRootChanged(XamlRoot sender, XamlRootChangedEventArgs args) => titlebarLayoutDirty = true;

    private void PaintNativeCaptionButtons()
    {
        var caption = AppWindow.TitleBar;
        caption.BackgroundColor = Paint("F8F7F5", "191918").Color;
        caption.ForegroundColor = Ink.Color;
        caption.InactiveBackgroundColor = caption.BackgroundColor;
        caption.InactiveForegroundColor = Muted.Color;
        caption.ButtonBackgroundColor = Colors.Transparent;
        caption.ButtonInactiveBackgroundColor = Colors.Transparent;
        caption.ButtonForegroundColor = Ink.Color;
        caption.ButtonInactiveForegroundColor = Muted.Color;
        caption.ButtonHoverBackgroundColor = Paint("EFEEEA", "262624").Color;
        caption.ButtonHoverForegroundColor = Ink.Color;
        caption.ButtonPressedBackgroundColor = Paint("E7E5DF", "2F2E2B").Color;
        caption.ButtonPressedForegroundColor = Ink.Color;
    }

    private void UpdateNativeTitleBarLayout()
    {
        if (closing || !titlebarRegion.IsLoaded || titlebarXamlRoot == null || titlebarInput == null) return;
        using var timing = PerformanceTrace.Measure("titlebar.layout");
        titlebarLayoutMeasurements++;
        var scale = titlebarXamlRoot.RasterizationScale;
        var caption = AppWindow.TitleBar;
        // AppWindow metrics are physical pixels; Grid padding is in DIPs.
        // Padding, rather than an outer margin, keeps our background under
        // the system buttons while keeping every app control out of them.
        var padding = new Thickness(caption.LeftInset / scale, 0, caption.RightInset / scale, 0);
        if (!titlebarRegion.Padding.Equals(padding))
        {
            titlebarRegion.Padding = padding;
            return; // Wait for the changed padding to arrange the controls.
        }

        var titleBounds = titlebarRegion.TransformToVisual(root).TransformBounds(
            new Rect(0, 0, titlebarRegion.ActualWidth, titlebarRegion.ActualHeight));
        var rects = new List<RectInt32>();
        var pendingButtons = false;
        void Include(Button button)
        {
            if (button.Visibility != Visibility.Visible) return;
            if (!button.IsLoaded || button.ActualWidth <= 0 || button.ActualHeight <= 0) { pendingButtons = true; return; }
            var bounds = button.TransformToVisual(root).TransformBounds(new Rect(0, 0, button.ActualWidth, button.ActualHeight));
            var left = Math.Max(bounds.Left, titleBounds.Left + padding.Left);
            var right = Math.Min(bounds.Right, titleBounds.Right - padding.Right);
            var top = Math.Max(bounds.Top, titleBounds.Top);
            var bottom = Math.Min(bounds.Bottom, titleBounds.Bottom);
            if (right <= left || bottom <= top) return;
            var x = (int)Math.Floor(left * scale);
            var y = (int)Math.Floor(top * scale);
            rects.Add(new RectInt32(x, y, (int)Math.Ceiling(right * scale) - x, (int)Math.Ceiling(bottom * scale) - y));
        }

        // These are the real existing button owners. Do not pass through the
        // whole toolbar's empty space: it must remain a draggable title bar.
        foreach (var button in navigationButtons.Children.OfType<Button>()) Include(button);
        foreach (var button in menu.Children.OfType<Button>()) Include(button);
        foreach (var item in toolbar.PrimaryCommands.OfType<AppBarElementContainer>())
            if (item.Content is Button button) Include(button);
        var next = rects.ToArray();
        titlebarLayoutDirty = pendingButtons;
        if (titlebarInteractiveRects.SequenceEqual(next)) return;
        titlebarInput.SetRegionRects(NonClientRegionKind.Passthrough, next);
        titlebarInteractiveRects = next;
    }
}
