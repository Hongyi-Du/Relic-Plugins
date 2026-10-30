using Microsoft.UI.Composition;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Hosting;
using Microsoft.UI.Xaml.Media;
using Relic.Core;
using System.Diagnostics;
using System.Numerics;
using System.Text.Json.Nodes;
using Windows.ApplicationModel.DataTransfer;
using Windows.Foundation;

namespace Relic;

public sealed partial class MainWindow
{
    private readonly List<ToastLifetime> activeToasts = new();
    private readonly List<ToastLifetime> pausedMessageToasts = new();
    private readonly List<MessageInteraction> messageInteractions = new();
    private long noticeSequence, copySequence;
    private ClipboardCopyReceipt? lastClipboardCopy;
    private MessageInteraction? capturedMessage;
    private ToastLifetime? capturedMessageToast;

    private ToastLifetime ShowToast(string message, int milliseconds = 3600)
    {
        var notice = new NativeToastNotice(message);
        var popup = new Popup { XamlRoot = root.XamlRoot, Child = notice, IsLightDismissEnabled = false };
        var lifetime = new ToastLifetime(++noticeSequence, message, milliseconds, popup, DispatcherQueue);
        void Appearance()
        {
            notice.RequestedTheme = root.RequestedTheme;
            notice.Surface.Background = Ink; notice.Label.Foreground = Paint("FFFFFF", "1F1F1E");
            notice.SetShadows(Dark
                ? [new(0, 10, 32, Windows.UI.Color.FromArgb(255, 0, 0, 0), .5f), new(0, 2, 6, Windows.UI.Color.FromArgb(255, 0, 0, 0), .3f)]
                : [new(0, 10, 32, Windows.UI.Color.FromArgb(255, 20, 18, 15), .14f), new(0, 2, 6, Windows.UI.Color.FromArgb(255, 20, 18, 15), .06f)]);
        }
        void Position()
        {
            notice.MaxWidth = Math.Max(0, Math.Min(560, root.ActualWidth - 40));
            notice.Measure(new Size(notice.MaxWidth, double.PositiveInfinity));
            popup.HorizontalOffset = (root.ActualWidth - notice.DesiredSize.Width) / 2;
            popup.VerticalOffset = Math.Max(0, root.ActualHeight - 28 - notice.DesiredSize.Height);
        }
        SizeChangedEventHandler resize = (_, _) => Position();
        TypedEventHandler<FrameworkElement, object> theme = (_, _) => { Appearance(); Position(); };
        root.SizeChanged += resize; root.ActualThemeChanged += theme;
        notice.SizeChanged += resize;
        popup.Closed += (_, _) =>
        {
            lifetime.Close(); activeToasts.Remove(lifetime); pausedMessageToasts.Remove(lifetime);
            root.SizeChanged -= resize; root.ActualThemeChanged -= theme; notice.SizeChanged -= resize;
        };
        notice.Loaded += (_, _) =>
        {
            Position();
            var peer = FrameworkElementAutomationPeer.FromElement(notice) ?? FrameworkElementAutomationPeer.CreatePeerForElement(notice);
            peer?.RaiseAutomationEvent(AutomationEvents.LiveRegionChanged);
        };
        Appearance(); Position(); activeToasts.Add(lifetime); popup.IsOpen = true; lifetime.Start();
        return lifetime;
    }

    private sealed record ClipboardCopyReceipt(long Sequence, string Value, bool Success, string? Error, long ToastId);
    private sealed record MessageInteraction(string Id, string Body, FrameworkElement Row, MessageHoverSurface Actions, Button Copy);

    // Actual desktop pointer and button actions, only called by the CI capture
    // workflow. The production hover handlers and copy callback do all UI work.
    private async Task<JsonObject> CaptureMessageScene(string scene, string messageId)
    {
        if (!VisualCaptureEnabled) throw new InvalidOperationException("CI capture input only");
        if (scene is not ("message-hover" or "message-copy-toast")) throw new ArgumentOutOfRangeException(nameof(scene));
        var candidates = messageInteractions.Where(item => item.Id == messageId && item.Row.IsLoaded &&
            item.Row.Visibility == Visibility.Visible && item.Row.ActualWidth > 0 && item.Row.ActualHeight > 0).ToArray();
        if (candidates.Length != 1) throw new InvalidOperationException("Expected one loaded production message for " + messageId);
        var target = candidates[0];
        var rowBounds = target.Row.TransformToVisual(root).TransformBounds(new Rect(0, 0, target.Row.ActualWidth, target.Row.ActualHeight));
        var viewport = chatScroll.TransformToVisual(root).TransformBounds(new Rect(0, 0, chatScroll.ActualWidth, chatScroll.ActualHeight));
        if (rowBounds.Left < viewport.Left || rowBounds.Right > viewport.Right || rowBounds.Top < viewport.Top || rowBounds.Bottom > viewport.Bottom)
            throw new InvalidOperationException("Requested message is not fully visible in the actual conversation viewport.");
        CaptureHover(target.Row); await Task.Delay(200); root.UpdateLayout();
        if (target.Actions.Visibility != Visibility.Visible || !target.Copy.IsLoaded || target.Copy.ActualWidth <= 0)
            throw new InvalidOperationException("Actual native pointer hover did not expose the message actions.");
        capturedMessage = target; capturedMessageToast = null;
        JsonObject Bounds(FrameworkElement element)
        {
            var box = element.TransformToVisual(root).TransformBounds(new Rect(0, 0, element.ActualWidth, element.ActualHeight));
            return new() { ["x"] = box.X, ["y"] = box.Y, ["width"] = box.Width, ["height"] = box.Height };
        }
        var receipt = new JsonObject { ["action"] = "native pointer motion at actual production message bounds", ["message_id"] = messageId,
            ["message_bounds"] = Bounds(target.Row), ["copy_bounds"] = Bounds(target.Copy), ["coordinate_space"] = "content-window",
            ["message_automation_id"] = AutomationProperties.GetAutomationId(target.Row), ["copy_automation_id"] = AutomationProperties.GetAutomationId(target.Copy),
            ["actions_visibility"] = target.Actions.Visibility.ToString() };
        if (scene == "message-copy-toast")
        {
            var previousCopy = copySequence;
            CaptureClick(target.Copy); await Task.Delay(150); root.UpdateLayout();
            var clipboard = Clipboard.GetContent();
            var text = clipboard.Contains(StandardDataFormats.Text) ? await clipboard.GetTextAsync() : null;
            var copied = lastClipboardCopy;
            if (copied == null || copied.Sequence <= previousCopy || !copied.Success || copied.Value != target.Body || text != target.Body)
                throw new InvalidOperationException("Actual copy button did not write this message to the clipboard.");
            var notice = activeToasts.SingleOrDefault(item => item.Id == copied.ToastId && item.Message == T("msg.copied") && item.Popup.IsOpen);
            if (notice == null) throw new InvalidOperationException("Actual copy did not show its localized production toast.");
            var paused = notice.Pause(); pausedMessageToasts.Add(notice);
            capturedMessageToast = notice;
            receipt["action"] = "native pointer hover then mouse down/up on the actual message Copy button";
            receipt["clipboard"] = text; receipt["copy_sequence"] = copied.Sequence;
            receipt["toast_id"] = notice.Id; receipt["toast_text"] = notice.Message;
            receipt["toast_timer"] = paused;
            receipt["toast_bounds"] = Bounds((FrameworkElement)notice.Popup.Child);
        }
        return receipt;
    }

    private JsonObject CaptureMessageSceneState()
    {
        if (!VisualCaptureEnabled) throw new InvalidOperationException("CI capture observation only");
        var target = capturedMessage ?? throw new InvalidOperationException("No real message interaction has been captured.");
        var cursor = new CapturePoint(); var origin = new CapturePoint();
        if (!GetCursorPos(ref cursor) || !ClientToScreen(WinRT.Interop.WindowNative.GetWindowHandle(this), ref origin))
            throw new InvalidOperationException("Could not read the actual pointer position for message hover.");
        var point = new Point(cursor.x - origin.x, cursor.y - origin.y);
        bool WithinRow(DependencyObject element)
        {
            for (DependencyObject? current = element; current != null; current = VisualTreeHelper.GetParent(current))
                if (ReferenceEquals(current, target.Row)) return true;
            return false;
        }
        var actualHits = VisualTreeHelper.FindElementsInHostCoordinates(point, root).ToArray();
        var hovered = actualHits.Any(WithinRow);
        if (!target.Row.IsLoaded || !hovered || target.Actions.Visibility != Visibility.Visible || !target.Copy.IsLoaded)
            throw new InvalidOperationException("The actual pointer/message/action-toolbar state was lost during capture.");
        var state = new JsonObject { ["source"] = "Actual desktop cursor, XAML hit testing, production toolbar visibility and production toast timer",
            ["message_id"] = target.Id, ["message_is_loaded"] = target.Row.IsLoaded,
            ["pointer_x"] = point.X, ["pointer_y"] = point.Y, ["pointer_hits_message"] = hovered,
            ["toolbar_visibility"] = target.Actions.Visibility.ToString(), ["copy_is_loaded"] = target.Copy.IsLoaded,
            ["copy_automation_id"] = AutomationProperties.GetAutomationId(target.Copy) };
        if (capturedMessageToast is { } notice)
        {
            if (!activeToasts.Contains(notice) || !notice.Popup.IsOpen || !notice.IsPaused || notice.IsRunning ||
                notice.Popup.Child is not NativeToastNotice actualNotice || actualNotice.Label.Text != notice.Message)
                throw new InvalidOperationException("The original copied-message toast or its paused actual timer was lost during capture.");
            state["toast_id"] = notice.Id; state["toast_text"] = actualNotice.Label.Text;
            state["toast_timer"] = notice.State();
        }
        return state;
    }

    private JsonArray ResumeCapturedMessageToasts()
    {
        if (!VisualCaptureEnabled) throw new InvalidOperationException("CI capture timer control only");
        var receipt = new JsonArray();
        foreach (var notice in pausedMessageToasts.ToArray()) receipt.Add(notice.Resume());
        pausedMessageToasts.Clear(); capturedMessage = null; capturedMessageToast = null; return receipt;
    }

    private sealed class ToastLifetime(long id, string message, int milliseconds, Popup popup, DispatcherQueue queue)
    {
        private readonly DispatcherQueueTimer timer = queue.CreateTimer();
        private TimeSpan remaining = TimeSpan.FromMilliseconds(milliseconds);
        private long started;
        private bool paused, closed;
        public long Id => id;
        public string Message => message;
        public Popup Popup => popup;
        public bool IsPaused => paused;
        public bool IsRunning => timer.IsRunning;
        public void Start()
        {
            timer.IsRepeating = false;
            timer.Tick += (_, _) => { if (!paused && !closed) { remaining = TimeSpan.Zero; popup.IsOpen = false; } };
            Restart();
        }
        private void Restart()
        {
            if (closed || !popup.IsOpen) return;
            if (remaining <= TimeSpan.Zero) { popup.IsOpen = false; return; }
            started = Stopwatch.GetTimestamp(); timer.Interval = remaining; timer.Start();
        }
        private TimeSpan Remaining => timer.IsRunning ? TimeSpan.FromTicks(Math.Max(0, remaining.Ticks - Stopwatch.GetElapsedTime(started).Ticks)) : remaining;
        public JsonObject State() => new()
        {
            ["toast_id"] = Id, ["duration_ms"] = milliseconds, ["remaining_ms"] = Remaining.TotalMilliseconds,
            ["interval_ms"] = timer.Interval.TotalMilliseconds, ["timer_is_running"] = timer.IsRunning,
            ["popup_is_open"] = popup.IsOpen, ["paused"] = paused, ["closed"] = closed
        };
        public JsonObject Pause()
        {
            var running = timer.IsRunning; var actualRemaining = Remaining;
            timer.Stop(); remaining = actualRemaining; paused = true;
            return new() { ["source"] = "Actual production DispatcherQueueTimer.Stop with monotonic elapsed time",
                ["toast_id"] = Id, ["duration_ms"] = milliseconds, ["elapsed_ms"] = milliseconds - remaining.TotalMilliseconds,
                ["remaining_ms"] = remaining.TotalMilliseconds, ["timer_was_running"] = running, ["timer_is_running"] = timer.IsRunning,
                ["popup_is_open"] = popup.IsOpen, ["paused"] = paused };
        }
        public JsonObject Resume()
        {
            var before = remaining.TotalMilliseconds; paused = false; Restart();
            return new() { ["source"] = "Actual production DispatcherQueueTimer restarted with its preserved remaining interval",
                ["toast_id"] = Id, ["remaining_ms_before_resume"] = before, ["interval_ms"] = timer.Interval.TotalMilliseconds,
                ["timer_is_running"] = timer.IsRunning, ["popup_is_open"] = popup.IsOpen, ["closed"] = closed };
        }
        public void Close() { timer.Stop(); closed = true; }
    }
}

public readonly record struct NativeShadowLayer(float X, float Y, float Blur, Windows.UI.Color Color, float Opacity);

// Real compositor shadows behind a real XAML Border. The mask is a rounded
// rectangle used by this production renderer, not screenshot-derived geometry.
public class NativeShadowPanel : Grid
{
    private readonly Grid shadowHost = new() { IsHitTestVisible = false };
    private NativeShadowLayer[] layers = [];
    private ContainerVisual? shadows;
    private readonly List<DropShadow> renderedShadows = new();
    public Border Surface { get; }
    public IReadOnlyList<DropShadow> RenderedShadows => renderedShadows;
    public NativeShadowPanel(Border surface)
    {
        Surface = surface; Children.Add(shadowHost); Children.Add(surface);
        Loaded += (_, _) => DrawShadows(); SizeChanged += (_, _) => DrawShadows();
        Unloaded += (_, _) => { ElementCompositionPreview.SetElementChildVisual(shadowHost, null); shadows = null; renderedShadows.Clear(); };
    }
    public void SetShadows(NativeShadowLayer[] values) { layers = values; if (IsLoaded) DrawShadows(); }
    private void DrawShadows()
    {
        if (ActualWidth <= 0 || ActualHeight <= 0) return;
        var compositor = ElementCompositionPreview.GetElementVisual(this).Compositor;
        shadows = compositor.CreateContainerVisual(); renderedShadows.Clear();
        var size = new Vector2((float)ActualWidth, (float)ActualHeight);
        // CSS lists its foremost shadow first; compositor children paint in order.
        foreach (var layer in layers.Reverse())
        {
            var geometry = compositor.CreateRoundedRectangleGeometry(); geometry.Size = size;
            geometry.CornerRadius = new Vector2((float)Surface.CornerRadius.TopLeft);
            var maskVisual = compositor.CreateSpriteVisual(); maskVisual.Size = size;
            maskVisual.Brush = compositor.CreateColorBrush(Microsoft.UI.Colors.White);
            maskVisual.Clip = compositor.CreateGeometricClip(geometry);
            var mask = compositor.CreateVisualSurface(); mask.SourceVisual = maskVisual; mask.SourceSize = size;
            var shadow = compositor.CreateDropShadow(); shadow.Mask = compositor.CreateSurfaceBrush(mask);
            shadow.Color = layer.Color; shadow.Opacity = layer.Opacity; shadow.BlurRadius = layer.Blur; shadow.Offset = new Vector3(layer.X, layer.Y, 0);
            var visual = compositor.CreateSpriteVisual(); visual.Size = size; visual.Shadow = shadow;
            shadows.Children.InsertAtTop(visual); renderedShadows.Add(shadow);
        }
        ElementCompositionPreview.SetElementChildVisual(shadowHost, shadows);
    }
}

public sealed class NativeToastNotice : NativeShadowPanel
{
    public TextBlock Label { get; }
    public NativeToastNotice(string message) : base(new Border { Padding = new Thickness(16, 9, 16, 9), CornerRadius = new CornerRadius(10) })
    {
        Label = new TextBlock { Text = message, FontFamily = new FontFamily(FontFamilies.UI), FontSize = 13,
            FontWeight = Microsoft.UI.Text.FontWeights.Normal, LineHeight = 20.8, LineStackingStrategy = LineStackingStrategy.BlockLineHeight,
            TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true };
        Surface.Child = Label;
        AutomationProperties.SetLiveSetting(this, AutomationLiveSetting.Polite);
        AutomationProperties.SetName(this, message);
        AutomationProperties.SetAutomationId(this, "relic-toast");
    }
    protected override AutomationPeer OnCreateAutomationPeer() => new NativeToastAutomationPeer(this);
}

public sealed class NativeToastAutomationPeer(NativeToastNotice owner) : FrameworkElementAutomationPeer(owner)
{
    protected override string GetClassNameCore() => nameof(NativeToastNotice);
    protected override AutomationControlType GetAutomationControlTypeCore() => AutomationControlType.StatusBar;
    protected override bool IsControlElementCore() => true;
}

public sealed class MessageHoverSurface : NativeShadowPanel
{
    public MessageHoverSurface(Border surface) : base(surface) { }
}
