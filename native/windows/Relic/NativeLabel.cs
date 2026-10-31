using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using Windows.Foundation;
using static Relic.NativeLabelInterop;
using LayoutSize = Windows.Foundation.Size;
using LayoutRect = Windows.Foundation.Rect;

namespace Relic;

// A genuine production label: DirectWrite shapes the one layout used for XAML
// measure/arrange, and that layout draws directly into the visible XAML image.
// This first control deliberately has no editing/selection or vertical-text API.
// Menu labels keep their containing native Button as the accessible control;
// standalone preview labels expose a real, read-only Text automation peer.
public sealed class NativeLabel : Panel
{
    private readonly Image image;
    private readonly string text, familyList, locale;
    private readonly float baseFontSize, baseLineHeight;
    private readonly bool scaleText;
    private readonly Windows.UI.ViewManagement.UISettings textSettings = CreateTextSettings();
    private double textScale;
    private float fontSize => (float)(baseFontSize * textScale);
    private float lineHeight => (float)(baseLineHeight * textScale);
    private readonly uint weight;
    private readonly bool characterEllipsis, accessibleText, wrapWholeWords, primaryFontLineSpacing;
    private IntPtr format, layout, surfaceInterop, trimmingSign;
    private SurfaceImageSource? surface;
    private ContentPresenter? presenter;
    private SolidColorBrush? foreground;
    private long foregroundToken, brushColorToken, brushOpacityToken;
    private XamlRoot? observedRoot;
    private float layoutWidth = -1, layoutHeight = -1, resolvedLineHeight;
    private double arrangedWidth, arrangedHeight, scale;
    private int pixelWidth, pixelHeight;
    private bool queued, rendering, drawDirty = true;
    private long layoutRevision, surfaceRevision, drawOrdinal;
    private JsonObject? receipt;
    private NativeLabelReadback? readback;
    private JsonObject? fallbackConfiguration;
    private JsonObject? lineSpacingConfiguration;
    private string? failure;
    private CancellationTokenSource? preparation;
    private Exception? preparationError;
    private bool preparationRetired;
    private static int pendingPreparations;
    private long attachCount, detachCount, preparationsStarted, preparationsApplied;
    internal static int PendingPreparations => Volatile.Read(ref pendingPreparations);
    internal bool IsLayoutPrepared => layout != IntPtr.Zero;
    internal bool HasCurrentDraw => IsLoaded && layout != IntPtr.Zero && surfaceInterop != IntPtr.Zero
        && surface != null && image.Source != null && image.ActualWidth > 0 && image.ActualHeight > 0
        && !drawDirty && !queued && !rendering && failure == null && drawOrdinal > 0;
    internal Exception? LayoutPreparationError => preparationError;
    internal event Action? LayoutPrepared;
    internal JsonObject DrawState() => new()
    {
        ["text"] = text, ["is_loaded"] = IsLoaded, ["layout_prepared"] = IsLayoutPrepared,
        ["preparation_pending"] = preparation != null, ["preparation_retired"] = preparationRetired,
        ["queued"] = queued, ["rendering"] = rendering, ["draw_dirty"] = drawDirty,
        ["layout_revision"] = layoutRevision, ["surface_revision"] = surfaceRevision,
        ["draw_ordinal"] = drawOrdinal, ["surface_width"] = pixelWidth, ["surface_height"] = pixelHeight,
        ["width"] = ActualWidth, ["height"] = ActualHeight, ["current_draw"] = HasCurrentDraw,
        ["attach_count"] = attachCount, ["detach_count"] = detachCount,
        ["preparations_started"] = preparationsStarted, ["preparations_applied"] = preparationsApplied,
        ["failure"] = failure
    };

    private static Windows.UI.ViewManagement.UISettings CreateTextSettings()
    {
        using var timing = PerformanceTrace.Measure("NativeLabel.UISettings.create");
        return new();
    }

    public NativeLabel(string text, string familyList, double fontSize, ushort fontWeight, string locale, double lineHeight,
        bool characterEllipsis = false, bool accessibleText = false, bool wrapWholeWords = false, bool primaryFontLineSpacing = false,
        bool scaleText = true)
    {
        using var timing = PerformanceTrace.Measure("NativeLabel.construct");
        this.text = text; this.familyList = familyList; baseFontSize = checked((float)fontSize);
        weight = fontWeight; this.locale = locale; baseLineHeight = checked((float)lineHeight);
        this.scaleText = scaleText; textScale = scaleText ? textSettings.TextScaleFactor : 1;
        resolvedLineHeight = this.lineHeight;
        this.characterEllipsis = characterEllipsis; this.accessibleText = accessibleText;
        this.wrapWholeWords = wrapWholeWords;
        this.primaryFontLineSpacing = primaryFontLineSpacing;
        if (characterEllipsis && wrapWholeWords) throw new ArgumentException("Whole-word labels cannot also request single-line character ellipsis");
        UseLayoutRounding = false; IsHitTestVisible = accessibleText;
        AutomationProperties.SetAccessibilityView(this, accessibleText ? AccessibilityView.Content : AccessibilityView.Raw);
        if (accessibleText) AutomationProperties.SetName(this, text);
        image = new Image { Stretch = Stretch.Fill, HorizontalAlignment = HorizontalAlignment.Stretch,
            VerticalAlignment = VerticalAlignment.Stretch, IsHitTestVisible = false, UseLayoutRounding = false };
        AutomationProperties.SetAccessibilityView(image, AccessibilityView.Raw);
        Children.Add(image);
        Loaded += (_, _) => Attach(); Unloaded += (_, _) => Detach();
    }

    internal string Text => text;
    internal void DisposePathLine() => Detach();
    // Used by the production selectable path owner. All hit tests use this
    // exact per-line layout, the same object that supplies production Draw.
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int HitPoint(IntPtr self, float x, float y, out int trailing, out int inside, out HitTestMetrics hit);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)] private delegate int HitPosition(IntPtr self, uint position, int trailing, out float x, out float y, out HitTestMetrics hit);
    internal int PathPositionAt(double x, double y)
    {
        if (layout == IntPtr.Zero) throw new InvalidOperationException("The production line has not been measured");
        Check(Method<HitPoint>(layout, 64)(layout, (float)x, (float)y, out var trailing, out _, out var hit));
        return Math.Clamp(checked((int)(hit.TextPosition + (trailing != 0 ? hit.Length : 0))), 0, text.Length);
    }
    internal double PathPositionX(int position)
    {
        if (layout == IntPtr.Zero) throw new InvalidOperationException("The production line has not been measured");
        Check(Method<HitPosition>(layout, 65)(layout, checked((uint)Math.Clamp(position, 0, text.Length)), 0, out var x, out _, out _));
        return x;
    }
    internal IReadOnlyList<LayoutRect> PathRangeRectangles(int start, int end)
    {
        if (layout == IntPtr.Zero) throw new InvalidOperationException("The production line has not been measured");
        if (start < 0 || end < start || end > text.Length) throw new ArgumentOutOfRangeException(nameof(start));
        if (start == end) return [];
        var hit = Method<HitTestRange>(layout, 66);
        var first = hit(layout, (uint)start, (uint)(end - start), 0, 0, IntPtr.Zero, 0, out var count);
        if (first < 0 && first != unchecked((int)0x8007007A)) Check(first);
        var buffer = Marshal.AllocHGlobal(checked((int)count * Marshal.SizeOf<HitTestMetrics>()));
        try
        {
            Check(hit(layout, (uint)start, (uint)(end - start), 0, 0, buffer, count, out var actual));
            if (actual > count) throw new InvalidOperationException("DirectWrite range exceeded its actual buffer");
            var result = new List<LayoutRect>();
            for (var i = 0; i < actual; i++)
            {
                var range = Marshal.PtrToStructure<HitTestMetrics>(buffer + checked((int)i * Marshal.SizeOf<HitTestMetrics>()));
                result.Add(new LayoutRect(range.Left, range.Top, range.Width, range.Height));
            }
            return result;
        }
        finally { Marshal.FreeHGlobal(buffer); }
    }
    // Read the first baseline from the very layout used by production Draw.
    // No font fallback estimate or second shaping pass supplies row alignment.
    internal double FirstBaseline
    {
        get
        {
            if (layout == IntPtr.Zero) return double.NaN;
            var lines = ReadLines();
            return lines.Length > 0 ? lines[0].Baseline : double.NaN;
        }
    }
    // An explicit brush is needed for a preview inside a ListViewItem: its
    // muted color must not inherit the row's default text foreground. Menus
    // leave this unset and keep observing their real ContentPresenter states.
    public static readonly DependencyProperty ForegroundProperty = DependencyProperty.Register(nameof(Foreground),
        typeof(Brush), typeof(NativeLabel), new PropertyMetadata(null, (owner, _) => ((NativeLabel)owner).ObserveForeground()));
    public Brush? Foreground { get => (Brush?)GetValue(ForegroundProperty); set => SetValue(ForegroundProperty, value); }
    protected override AutomationPeer OnCreateAutomationPeer() => accessibleText ? new TextPeer(this) : base.OnCreateAutomationPeer();
    private sealed class TextPeer(NativeLabel owner) : FrameworkElementAutomationPeer(owner)
    {
        protected override AutomationControlType GetAutomationControlTypeCore() => AutomationControlType.Text;
        protected override string GetClassNameCore() => nameof(NativeLabel);
        protected override string GetNameCore() => owner.Text;
        protected override bool IsControlElementCore() => true;
        protected override bool IsContentElementCore() => true;
        // The child Image is this peer's paint surface, never separate content.
        protected override IList<AutomationPeer> GetChildrenCore() => new List<AutomationPeer>();
    }
    // The CI caller guards this request. It invokes the same production paint
    // path, with unchanged text/style/layout inputs; no synthetic frame is made.
    internal void RequestCaptureRedraw() { InvalidateDraw(); InvalidateArrange(); QueueDraw(); }

    internal JsonObject WriteCaptureReadback(string outputDirectory, string caseId, int labelIndex)
    {
        if (!NativeLabelReadback.Enabled) throw new InvalidOperationException("NativeLabel readback export is CI-only");
        if (readback == null) return new JsonObject
        {
            ["status"] = "not-measured", ["reason"] = "No actual production surface readback exists for this label",
            ["current_layout_revision"] = layoutRevision, ["current_surface_revision"] = surfaceRevision,
            ["current_draw_ordinal"] = drawOrdinal, ["presentation_identity_proven"] = false
        };
        var isCurrent = readback.LayoutRevision == layoutRevision && readback.SurfaceRevision == surfaceRevision
            && readback.DrawOrdinal == drawOrdinal && receipt != null && failure == null && !queued && !rendering
            && receipt["surface_end_draw_succeeded"]?.GetValue<bool>() == true && ProductionSurfaceBindingMatches();
        return readback.Write(outputDirectory, caseId, labelIndex, isCurrent);
    }

    internal bool OwnsProductionImage(Image candidate) => ReferenceEquals(image, candidate);
    internal JsonObject CaptureProductionImageBinding(Image candidate)
    {
        var sameImage = OwnsProductionImage(candidate);
        return new JsonObject
        {
            ["source"] = "actual NativeLabel production Image object identity and SurfaceImageSource COM binding",
            ["same_image_object"] = sameImage,
            ["surface_binding_same_com_identity"] = sameImage && ProductionSurfaceBindingMatches(),
            ["source_type"] = candidate.Source?.GetType().FullName,
            ["layout_revision"] = layoutRevision, ["surface_revision"] = surfaceRevision, ["draw_ordinal"] = drawOrdinal,
            ["quantity"] = "Ownership of the actual text paint surface; not independent image content or proof of final presentation"
        };
    }

    private bool ProductionSurfaceBindingMatches()
    {
        if (surface == null || image.Source == null) return false;
        var bound = WinRT.MarshalInspectable<object>.FromManaged(image.Source);
        var produced = WinRT.MarshalInspectable<object>.FromManaged(surface);
        IntPtr boundIdentity = IntPtr.Zero, producedIdentity = IntPtr.Zero;
        try
        {
            var unknown = new Guid("00000000-0000-0000-c000-000000000046");
            boundIdentity = Query(bound, unknown); producedIdentity = Query(produced, unknown);
            return boundIdentity == producedIdentity;
        }
        finally { Release(ref boundIdentity); Release(ref producedIdentity); Release(ref bound); Release(ref produced); }
    }

    internal JsonObject ObserveCaptureVersion(UIElement windowContent)
    {
        if (!IsLoaded || queued || rendering || failure != null || receipt == null
            || receipt["layout_revision"]?.GetValue<long>() != layoutRevision
            || receipt["surface_revision"]?.GetValue<long>() != surfaceRevision
            || receipt["draw_ordinal"]?.GetValue<long>() != drawOrdinal
            || receipt["surface_end_draw_succeeded"]?.GetValue<bool>() != true)
            throw new InvalidOperationException("NativeLabel has no current, idle, successfully submitted production draw: " + text + "; " + failure);
        if (surface == null || image.Source == null) throw new InvalidOperationException("NativeLabel has no bound production surface: " + text);
        // The property's projection can be a different managed wrapper. Compare
        // actual COM identity, not a presumed Image.Source wrapper identity.
        if (!ProductionSurfaceBindingMatches()) throw new InvalidOperationException("NativeLabel Image.Source is not the surface whose draw was recorded: " + text);
        var transform = TransformToVisual(windowContent);
        var origin = transform.TransformPoint(new Windows.Foundation.Point(0, 0));
        var horizontal = transform.TransformPoint(new Windows.Foundation.Point(1, 0));
        var vertical = transform.TransformPoint(new Windows.Foundation.Point(0, 1));
        var bounds = transform.TransformBounds(new LayoutRect(0, 0, ActualWidth, ActualHeight));
        var ancestorState = new JsonArray(); DependencyObject? current = this;
        while (current != null)
        {
            if (current is UIElement ui)
            {
                JsonObject? clip = null;
                if (ui.Clip is RectangleGeometry rectangle)
                {
                    var r = rectangle.Rect;
                    var g = rectangle.Transform;
                    var p0 = g?.TransformPoint(new Windows.Foundation.Point(0, 0)) ?? new Windows.Foundation.Point(0, 0);
                    var px = g?.TransformPoint(new Windows.Foundation.Point(1, 0)) ?? new Windows.Foundation.Point(1, 0);
                    var py = g?.TransformPoint(new Windows.Foundation.Point(0, 1)) ?? new Windows.Foundation.Point(0, 1);
                    clip = new JsonObject { ["type"] = "RectangleGeometry", ["x"] = r.X, ["y"] = r.Y, ["width"] = r.Width, ["height"] = r.Height,
                        ["transform"] = new JsonArray(px.X - p0.X, px.Y - p0.Y, py.X - p0.X, py.Y - p0.Y, p0.X, p0.Y) };
                }
                else if (ui.Clip != null) throw new NotSupportedException("NativeLabel capture cannot establish stability for clip type " + ui.Clip.GetType().FullName);
                ancestorState.Add(new JsonObject { ["type"] = current.GetType().FullName, ["visibility"] = ui.Visibility.ToString(), ["opacity"] = ui.Opacity, ["clip"] = clip });
            }
            if (ReferenceEquals(current, windowContent)) break;
            current = VisualTreeHelper.GetParent(current);
        }
        return new JsonObject
        {
            ["text"] = text, ["layout_revision"] = layoutRevision, ["surface_revision"] = surfaceRevision, ["draw_ordinal"] = drawOrdinal,
            ["surface_binding_same_com_identity"] = true, ["queued"] = queued, ["rendering"] = rendering,
            ["bounds"] = new JsonObject { ["x"] = bounds.X, ["y"] = bounds.Y, ["width"] = bounds.Width, ["height"] = bounds.Height },
            ["transform"] = new JsonArray(horizontal.X - origin.X, horizontal.Y - origin.Y, vertical.X - origin.X, vertical.Y - origin.Y, origin.X, origin.Y),
            ["image_width"] = image.ActualWidth, ["image_height"] = image.ActualHeight, ["image_stretch"] = image.Stretch.ToString(),
            ["rasterization_scale"] = XamlRoot?.RasterizationScale, ["ancestors"] = ancestorState
        };
    }
    internal JsonObject CaptureProductionReceipt() => new()
    {
        ["source"] = "NativeLabel production SurfaceImageSource / DirectWrite renderer",
        ["text"] = text, ["requested_family_list"] = familyList, ["requested_size"] = fontSize,
        ["requested_weight"] = weight, ["requested_locale"] = locale, ["requested_line_height"] = lineHeight,
        ["requested_character_ellipsis"] = characterEllipsis, ["accessible_full_text"] = accessibleText,
        ["applied_font_fallback"] = fallbackConfiguration?.DeepClone(),
        ["applied_line_spacing"] = lineSpacingConfiguration?.DeepClone(),
        ["current_layout_revision"] = layoutRevision, ["current_surface_revision"] = surfaceRevision,
        ["current_draw_ordinal"] = drawOrdinal,
        ["current_submission"] = new JsonObject { ["source"] = "Actual NativeLabel state at receipt capture",
            ["is_loaded"] = IsLoaded, ["queued"] = queued, ["rendering"] = rendering,
            ["draw_dirty"] = drawDirty, ["layout_prepared"] = IsLayoutPrepared,
            ["preparation_pending"] = preparation != null, ["preparation_retired"] = preparationRetired,
            ["root_subscription_present"] = observedRoot != null,
            ["attach_count"] = attachCount, ["detach_count"] = detachCount,
            ["preparations_started"] = preparationsStarted, ["preparations_applied"] = preparationsApplied,
            ["surface_binding_same_com_identity"] = ProductionSurfaceBindingMatches() },
        ["foreground_resolution"] = ObserveForegroundBinding(),
        ["last_failure"] = failure, ["draw"] = receipt?.DeepClone(),
        ["surface_readback"] = readback?.Snapshot(),
        ["presentation_frame"] = null,
        ["coverage_complete"] = false,
        ["coverage_reason"] = "Submitted style and glyph callbacks are recorded; final PNG contribution, visible glyph ownership and equivalent text-line geometry remain unmeasured. Only successful EndDraw records describe submitted pixels; font identity comes from the actual renderer callback, never the fallback configuration."
    };

    private void Attach()
    {
        using var timing = PerformanceTrace.Measure("NativeLabel.attach");
        attachCount++;
        preparationRetired = false;
        DetachSubscriptions();
        if (scaleText) { textSettings.TextScaleFactorChanged += TextScaleChanged; RefreshTextScale(); }
        observedRoot = XamlRoot; if (observedRoot != null) observedRoot.Changed += RootChanged;
        DependencyObject? parent = VisualTreeHelper.GetParent(this);
        while (parent != null && parent is not ContentPresenter) parent = VisualTreeHelper.GetParent(parent);
        presenter = parent as ContentPresenter;
        if (presenter != null)
            foregroundToken = presenter.RegisterPropertyChangedCallback(ContentPresenter.ForegroundProperty, (_, _) => ObserveForeground());
        ObserveForeground(); InvalidateMeasure(); QueueDraw();
    }
    private void TextScaleChanged(Windows.UI.ViewManagement.UISettings sender, object args) =>
        DispatcherQueue.TryEnqueue(RefreshTextScale);
    private void RefreshTextScale()
    {
        var value = scaleText ? textSettings.TextScaleFactor : 1;
        if (value == textScale) return;
        textScale = value;
        preparation?.Cancel(); preparationError = null;
        Release(ref layout); Release(ref trimmingSign); Release(ref format);
        layoutWidth = layoutHeight = -1; resolvedLineHeight = lineHeight;
        InvalidateMeasure(); InvalidateDraw(); QueueDraw();
    }
    private void RootChanged(XamlRoot sender, XamlRootChangedEventArgs args)
    {
        // A rasterization-scale change changes the actual image's pixel/DIP
        // placement too, not just the surface allocation used by the renderer.
        // Size changes are handled by this label's own measure/arrange. Do not
        // redraw every label merely because another part of the root changed.
        if (sender.RasterizationScale == scale) return;
        InvalidateArrange();
        InvalidateDraw(); QueueDraw();
    }
    private void ObserveForeground()
    {
        if (foreground != null)
        {
            foreground.UnregisterPropertyChangedCallback(SolidColorBrush.ColorProperty, brushColorToken);
            foreground.UnregisterPropertyChangedCallback(Brush.OpacityProperty, brushOpacityToken);
        }
        foreground = (Foreground ?? presenter?.Foreground) as SolidColorBrush;
        if (foreground != null)
        {
            brushColorToken = foreground.RegisterPropertyChangedCallback(SolidColorBrush.ColorProperty, (_, _) => { InvalidateDraw(); QueueDraw(); });
            brushOpacityToken = foreground.RegisterPropertyChangedCallback(Brush.OpacityProperty, (_, _) => { InvalidateDraw(); QueueDraw(); });
        }
        InvalidateDraw(); QueueDraw();
    }
    private JsonObject ObserveForegroundBinding()
    {
        static JsonObject? BrushObservation(Brush? value) => value == null ? null : new JsonObject
        {
            ["type"] = value.GetType().FullName, ["opacity"] = value.Opacity,
            ["rgba8"] = value is SolidColorBrush color ? new JsonArray(color.Color.R, color.Color.G, color.Color.B, color.Color.A) : null
        };
        var local = Foreground; var inherited = presenter?.Foreground; var effective = local ?? inherited;
        return new JsonObject
        {
            ["source"] = "Actual NativeLabel Foreground, retained ContentPresenter and subscribed brush",
            ["explicit"] = BrushObservation(local), ["presenter"] = BrushObservation(inherited),
            ["subscribed"] = BrushObservation(foreground), ["same_effective_brush_reference"] = ReferenceEquals(effective, foreground),
            ["presenter_loaded"] = presenter?.IsLoaded, ["label_loaded"] = IsLoaded
        };
    }
    private void DetachSubscriptions()
    {
        textSettings.TextScaleFactorChanged -= TextScaleChanged;
        if (observedRoot != null) { observedRoot.Changed -= RootChanged; observedRoot = null; }
        if (presenter != null) { presenter.UnregisterPropertyChangedCallback(ContentPresenter.ForegroundProperty, foregroundToken); presenter = null; }
        if (foreground != null)
        {
            foreground.UnregisterPropertyChangedCallback(SolidColorBrush.ColorProperty, brushColorToken);
            foreground.UnregisterPropertyChangedCallback(Brush.OpacityProperty, brushOpacityToken); foreground = null;
        }
    }
    private void Detach()
    {
        using var timing = PerformanceTrace.Measure("NativeLabel.detach");
        detachCount++;
        preparationRetired = true; preparation?.Cancel(); preparationError = null;
        DetachSubscriptions(); Release(ref surfaceInterop); surface = null; image.Source = null;
        Release(ref layout); Release(ref trimmingSign); Release(ref format); layoutWidth = layoutHeight = -1;
        pixelWidth = pixelHeight = 0; fallbackConfiguration = null; lineSpacingConfiguration = null;
        resolvedLineHeight = lineHeight; InvalidateDraw();
    }
    private void InvalidateDraw() { receipt = null; drawDirty = true; QueueDraw(); }

    private void EnsureMountedState()
    {
        // SelectorBar/ContentPresenter can reparent a measured child before its
        // deferred lifecycle events settle. A currently mounted label that is
        // being measured/arranged must not remain in its retired state with all
        // foreground/root subscriptions cleared by a previous Unloaded event.
        if (IsLoaded && (preparationRetired || observedRoot == null)) Attach();
    }

    private void StartPreparation(float width, float height)
    {
        if (preparation != null || preparationRetired || preparationError != null || layout != IntPtr.Zero) return;
        var cancellation = preparation = new CancellationTokenSource();
        preparationsStarted++;
        var dispatcher = DispatcherQueue;
        var requested = new NativeLabelLayoutRequest(text, familyList, locale, fontSize, weight, lineHeight,
            width, height, wrapWholeWords, primaryFontLineSpacing, characterEllipsis);
        Interlocked.Increment(ref pendingPreparations);
        _ = Prepare();
        async Task Prepare()
        {
            NativeLabelPreparedLayout? prepared = null;
            Exception? error = null;
            try { prepared = await NativeLabelPreparation.PrepareAsync(requested, cancellation.Token).ConfigureAwait(false); }
            catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { }
            catch (Exception failure) { error = failure; }
            if (!dispatcher.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Normal, () =>
            {
                try
                {
                    if (ReferenceEquals(preparation, cancellation)) preparation = null;
                    if (!cancellation.IsCancellationRequested && !preparationRetired)
                    {
                        preparationError = error;
                        failure = error?.ToString();
                        if (prepared != null)
                        {
                            format = prepared.Format; prepared.Format = IntPtr.Zero;
                            layout = prepared.Layout; prepared.Layout = IntPtr.Zero;
                            trimmingSign = prepared.TrimmingSign; prepared.TrimmingSign = IntPtr.Zero;
                            layoutWidth = prepared.Width; layoutHeight = prepared.Height;
                            resolvedLineHeight = prepared.ResolvedLineHeight;
                            fallbackConfiguration = prepared.Fallback; lineSpacingConfiguration = prepared.LineSpacing;
                            preparationsApplied++;
                            layoutRevision++; InvalidateDraw();
                        }
                        InvalidateMeasure(); InvalidateArrange(); QueueDraw();
                        LayoutPrepared?.Invoke();
                    }
                    else if (!preparationRetired)
                    {
                        // A scale change or a reload superseded this request.
                        // Start the next request only after its predecessor ends.
                        InvalidateMeasure(); InvalidateArrange();
                    }
                }
                finally
                {
                    prepared?.Dispose(); cancellation.Dispose();
                    Interlocked.Decrement(ref pendingPreparations);
                }
            }))
            {
                prepared?.Dispose(); cancellation.Dispose();
                Interlocked.Decrement(ref pendingPreparations);
            }
        }
    }

    private bool EnsureLayout(float width, float height)
    {
        if (layout == IntPtr.Zero)
        {
            StartPreparation(width, height);
            if (preparationError != null) throw new InvalidOperationException("Native label layout preparation failed", preparationError);
            return false;
        }
        // Only a fully shaped layout reaches this branch. The worker no longer
        // accesses it; subsequent width/height mutations belong solely to UI.
        if (layoutWidth != width) { Check(Method<SetFloat>(layout, 28)(layout, width)); layoutWidth = width; layoutRevision++; InvalidateDraw(); }
        if (layoutHeight != height) { Check(Method<SetFloat>(layout, 29)(layout, height)); layoutHeight = height; layoutRevision++; InvalidateDraw(); }
        return true;
    }
    private LineMetrics[] ReadLines() => NativeLabelPreparation.ReadLines(layout);
    private JsonArray ReadHitTestBounds()
    {
        var result = new JsonArray(); if (text.Length == 0) return result;
        var first = Method<HitTestRange>(layout, 66)(layout, 0, checked((uint)text.Length), 0, 0, IntPtr.Zero, 0, out var count);
        if (first < 0 && first != unchecked((int)0x8007007A)) Check(first);
        if (count == 0) return result;
        var pointer = Marshal.AllocHGlobal(checked((int)count * Marshal.SizeOf<HitTestMetrics>()));
        try
        {
            Check(Method<HitTestRange>(layout, 66)(layout, 0, checked((uint)text.Length), 0, 0, pointer, count, out var actual));
            for (uint i = 0; i < actual; i++)
            {
                var h = Marshal.PtrToStructure<HitTestMetrics>(pointer + checked((int)i * Marshal.SizeOf<HitTestMetrics>()));
                result.Add(new JsonObject { ["text_position_utf16"] = h.TextPosition, ["text_length_utf16"] = h.Length,
                    ["left"] = h.Left, ["top"] = h.Top, ["width"] = h.Width, ["height"] = h.Height,
                    ["bidi_level"] = h.BidiLevel, ["is_text"] = h.IsText != 0, ["is_trimmed"] = h.IsTrimmed != 0 });
            }
        }
        finally { Marshal.FreeHGlobal(pointer); }
        return result;
    }
    private JsonObject ReadTrimming()
    {
        Check(Method<GetTrimming>(layout, 17)(layout, out var options, out var actualSign));
        try
        {
            var configuredIdentity = trimmingSign == IntPtr.Zero ? null : ComIdentity(trimmingSign);
            var actualIdentity = actualSign == IntPtr.Zero ? null : ComIdentity(actualSign);
            JsonObject? metrics = null;
            if (actualSign != IntPtr.Zero)
            {
                // IDWriteInlineObject::GetMetrics slot 4 returns HRESULT and
                // writes an explicit 16-byte output, never a struct return.
                Check(Method<GetInlineMetrics>(actualSign, 4)(actualSign, out var value));
                metrics = new JsonObject { ["width"] = value.Width, ["height"] = value.Height,
                    ["baseline"] = value.Baseline, ["supports_sideways"] = value.SupportsSideways != 0,
                    ["quantity"] = "Actual inline object layout metrics; not glyph ink bounds" };
            }
            return new JsonObject
            {
                ["source"] = "GetTrimming on the same IDWriteTextLayout used for the production Draw",
                ["requested_character_ellipsis"] = characterEllipsis, ["granularity"] = options.Granularity,
                ["delimiter"] = options.Delimiter, ["delimiter_count"] = options.DelimiterCount,
                ["configured_sign_com_identity"] = configuredIdentity, ["layout_sign_com_identity"] = actualIdentity,
                ["same_sign_com_identity"] = actualIdentity != null && actualIdentity == configuredIdentity,
                ["inline_metrics"] = metrics
            };
        }
        finally { Release(ref actualSign); }
    }
    protected override LayoutSize MeasureOverride(LayoutSize availableSize)
    {
        using var timing = PerformanceTrace.Measure("NativeLabel.measure");
        EnsureMountedState();
        try
        {
            if (!EnsureLayout((float)(double.IsFinite(availableSize.Width) ? Math.Max(0, availableSize.Width) : 1000000), wrapWholeWords ? 1000000 : lineHeight))
            {
                // Reserve a small text-shaped box without invoking another
                // font engine. Actual DirectWrite metrics replace it on handoff.
                var estimatedWidth = text.Length * (double)fontSize * .55;
                if (double.IsFinite(availableSize.Width)) estimatedWidth = Math.Min(estimatedWidth, Math.Max(0, availableSize.Width));
                var placeholder = new LayoutSize(estimatedWidth, lineHeight);
                image.Measure(placeholder); return placeholder;
            }
            Check(Method<GetTextMetrics>(layout, 60)(layout, out var metrics));
            var desiredWidth = (double)metrics.WidthIncludingTrailingWhitespace;
            if (characterEllipsis && double.IsFinite(availableSize.Width)) desiredWidth = Math.Min(desiredWidth, Math.Max(0, availableSize.Width));
            var desiredHeight = wrapWholeWords ? Math.Max(resolvedLineHeight, metrics.Height) : resolvedLineHeight;
            image.Measure(new LayoutSize(desiredWidth, desiredHeight));
            return new LayoutSize(desiredWidth, desiredHeight);
        }
        catch (Exception ex) { failure = ex.ToString(); InvalidateDraw(); return new LayoutSize(0, lineHeight); }
    }
    protected override LayoutSize ArrangeOverride(LayoutSize finalSize)
    {
        using var timing = PerformanceTrace.Measure("NativeLabel.arrange");
        EnsureMountedState();
        arrangedWidth = finalSize.Width; arrangedHeight = finalSize.Height;
        // Fractional DIP dimensions keep native geometry. Whole surface pixels
        // occupy exactly pixels / rasterizationScale DIPs, without squeezing the
        // ceiling pixel into the label's fractional content width.
        scale = XamlRoot?.RasterizationScale ?? 1;
        var width = Math.Ceiling(arrangedWidth * scale) / scale; var height = Math.Ceiling(arrangedHeight * scale) / scale;
        image.Arrange(new LayoutRect(0, 0, width, height));
        Clip = new RectangleGeometry { Rect = new LayoutRect(0, 0, arrangedWidth, arrangedHeight) };
        try { EnsureLayout((float)arrangedWidth, (float)arrangedHeight); QueueDraw(); }
        catch (Exception ex) { failure = ex.ToString(); InvalidateDraw(); }
        return finalSize;
    }
    private void QueueDraw()
    {
        if (queued || rendering || !drawDirty || !IsLoaded) return; queued = true;
        // At most one submission per realized label is queued. Visible text is
        // foreground work: low-priority callbacks can remain pending throughout
        // modal layout/observation while the label displays only its placeholder.
        // Font discovery and first shaping remain on the bounded worker.
        if (!DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Normal,
            () => { queued = false; if (IsLoaded && drawDirty) Render(); })) queued = false;
    }
    private void EnsureSurface(int width, int height)
    {
        if (surfaceInterop != IntPtr.Zero && pixelWidth == width && pixelHeight == height) return;
        using var timing = PerformanceTrace.Measure("NativeLabel.surface.create");
        Release(ref surfaceInterop); surface = new SurfaceImageSource(width, height, false);
        // CsWinRT returns the real projected object's native IInspectable.
        var inspectable = WinRT.MarshalInspectable<object>.FromManaged(surface);
        try
        {
            surfaceInterop = Query(inspectable, SurfaceWithD2D);
            Check(Method<SetDevice>(surfaceInterop, 3)(surfaceInterop, NativeLabelDevice.Shared.Device));
        }
        catch { Release(ref surfaceInterop); pixelWidth = pixelHeight = 0; throw; }
        finally { Release(ref inspectable); }
        pixelWidth = width; pixelHeight = height; surfaceRevision++; image.Source = surface;
    }
    private void Render()
    {
        if (rendering || arrangedWidth <= 0 || arrangedHeight <= 0 || layout == IntPtr.Zero) return;
        using var timing = PerformanceTrace.Measure("NativeLabel.render");
        rendering = true; InvalidateDraw(); readback = null; IntPtr context = IntPtr.Zero, brush = IntPtr.Zero;
        var began = false; var clipped = false;
        try
        {
            // A reparent/unload can retire subscriptions before a queued draw.
            // Resolve the current production property again at paint time;
            // never draw from a detached cached brush or invent a fallback.
            if (!ReferenceEquals(foreground, (Foreground ?? presenter?.Foreground) as SolidColorBrush)) ObserveForeground();
            if (foreground == null) throw new NotSupportedException("NativeLabel requires an actual explicit or ContentPresenter SolidColorBrush foreground; " + ObserveForegroundBinding().ToJsonString());
            scale = XamlRoot?.RasterizationScale ?? 1;
            if (!EnsureLayout((float)arrangedWidth, (float)arrangedHeight)) return;
            EnsureSurface(checked((int)Math.Ceiling(arrangedWidth * scale)), checked((int)Math.Ceiling(arrangedHeight * scale)));
            var update = new NativeLabelInterop.Rect { Right = pixelWidth, Bottom = pixelHeight }; var iid = DeviceContext;
            NativeLabelInterop.Point offset;
            using (PerformanceTrace.Measure("NativeLabel.surface.BeginDraw"))
                Check(Method<BeginSurface>(surfaceInterop, 4)(surfaceInterop, ref update, ref iid, out context, out offset));
            began = true;
            var transform = new NativeLabelInterop.Matrix { M11 = 1, M22 = 1, Dx = (float)(offset.X / scale), Dy = (float)(offset.Y / scale) };
            Method<SetDpi>(context, 51)(context, (float)(96 * scale), (float)(96 * scale));
            Method<SetTransform>(context, 30)(context, ref transform);
            Method<SetEnum>(context, 80)(context, 0); // D2D1_UNIT_MODE_DIPS.
            Method<SetEnum>(context, 78)(context, 0); // D2D1_PRIMITIVE_BLEND_SOURCE_OVER.
            Method<SetEnum>(context, 32)(context, 0); // D2D1_ANTIALIAS_MODE_PER_PRIMITIVE.
            Method<SetEnum>(context, 34)(context, 2); // Grayscale text AA on a transparent surface.
            var clip = new RectF { Right = (float)(pixelWidth / scale), Bottom = (float)(pixelHeight / scale) };
            Method<PushClip>(context, 45)(context, ref clip, 0); clipped = true;
            var clear = new ColorF(); Method<Clear>(context, 47)(context, ref clear);
            var color = foreground.Color;
            var paint = new ColorF { R = color.R / 255f, G = color.G / 255f, B = color.B / 255f, A = (float)(color.A / 255d * foreground.Opacity) };
            Check(Method<CreateBrush>(context, 8)(context, ref paint, IntPtr.Zero, out brush));
            var trimming = CaptureDiagnostics ? ReadTrimming() : null;
            using var renderer = new NativeLabelRenderer(context, brush, (float)scale, transform, trimmingSign);
            drawOrdinal++;
            int drawResult;
            using (PerformanceTrace.Measure("NativeLabel.DirectWrite.Draw"))
                drawResult = Method<DrawLayout>(layout, 58)(layout, IntPtr.Zero, renderer.Pointer, 0, 0);
            if (renderer.CallbackFailure != null) throw new InvalidOperationException(renderer.CallbackFailure);
            Check(drawResult);
            TextMetrics metrics = default; JsonArray? lines = null, hitTest = null;
            if (CaptureDiagnostics)
            {
                Check(Method<GetTextMetrics>(layout, 60)(layout, out metrics));
                lines = new JsonArray(); foreach (var line in ReadLines())
                    lines.Add(new JsonObject { ["length_utf16"] = line.Length, ["trailing_whitespace_utf16"] = line.TrailingWhitespaceLength,
                        ["newline_utf16"] = line.NewlineLength, ["height"] = line.Height, ["baseline"] = line.Baseline, ["is_trimmed"] = line.IsTrimmed != 0 });
                hitTest = ReadHitTestBounds();
            }
            Method<VoidCall>(context, 46)(context); clipped = false;
            // Read only the pixels written by this original production draw.
            // No second Draw/layout/target is substituted. Production sessions
            // never allocate staging storage or perform GPU/CPU readback.
            if (NativeLabelReadback.Enabled)
                readback = NativeLabelReadback.Observe(context, offset, pixelWidth, pixelHeight, layoutRevision, surfaceRevision, drawOrdinal);
            // BeginDraw/EndDraw belong to the XAML surface, not the shared D2D
            // context. A run callback alone is never treated as committed paint.
            int endResult;
            using (PerformanceTrace.Measure("NativeLabel.surface.EndDraw"))
                endResult = Method<EndSurface>(surfaceInterop, 5)(surfaceInterop);
            began = false;
            readback?.ObserveEndDraw(endResult); Check(endResult);
            if (CaptureDiagnostics) receipt = new JsonObject
            {
                ["layout_revision"] = layoutRevision, ["surface_revision"] = surfaceRevision, ["draw_ordinal"] = drawOrdinal,
                ["layout_com_identity"] = ComIdentity(layout),
                ["actual_text_format"] = new JsonObject
                {
                    ["source"] = "IDWriteTextFormat getters on the same production IDWriteTextLayout passed to Draw",
                    ["font_size"] = Method<GetFloat>(layout, 25)(layout),
                    ["font_weight"] = Method<GetUInt>(layout, 22)(layout),
                    ["word_wrapping"] = Method<GetUInt>(layout, 13)(layout)
                },
                ["draw_hresult"] = drawResult, ["surface_end_draw_hresult"] = endResult, ["surface_end_draw_succeeded"] = true,
                ["submitted_at_utc"] = DateTimeOffset.UtcNow.ToString("O"), ["presented_frame_id"] = null,
                ["driver"] = NativeLabelDevice.Shared.Driver, ["pixels_per_dip"] = scale,
                ["surface_pixels"] = new JsonObject { ["width"] = pixelWidth, ["height"] = pixelHeight },
                ["image_actual_dip"] = new JsonObject { ["width"] = image.ActualWidth, ["height"] = image.ActualHeight, ["stretch"] = image.Stretch.ToString() },
                ["surface_begin_draw_offset_pixels"] = new JsonObject { ["x"] = offset.X, ["y"] = offset.Y },
                ["d2d_transform"] = Transform(transform), ["d2d_clip_dip"] = Box(clip),
                ["xaml_clip_dip"] = new JsonObject { ["x"] = 0, ["y"] = 0, ["width"] = arrangedWidth, ["height"] = arrangedHeight },
                ["text_antialias_mode"] = "grayscale", ["pixel_snapping_disabled"] = false,
                ["unit_mode"] = "DIPS", ["primitive_blend"] = "SOURCE_OVER",
                ["brush_srgb_unpremultiplied_0_1"] = new JsonArray(paint.R, paint.G, paint.B, paint.A),
                ["brush_input_srgb_unpremultiplied_0_255"] = new JsonArray(color.R, color.G, color.B, color.A * foreground.Opacity),
                ["presenter_brush_color_rgba8"] = new JsonArray(color.R, color.G, color.B, color.A),
                ["presenter_brush_opacity"] = foreground.Opacity,
                ["foreground_source"] = Foreground != null ? "NativeLabel.Foreground" : "ContentPresenter.Foreground",
                ["layout_metrics"] = new JsonObject { ["left"] = metrics.Left, ["top"] = metrics.Top, ["width"] = metrics.Width,
                    ["width_including_trailing_whitespace"] = metrics.WidthIncludingTrailingWhitespace, ["height"] = metrics.Height,
                    ["layout_width"] = metrics.LayoutWidth, ["layout_height"] = metrics.LayoutHeight, ["line_count"] = metrics.LineCount },
                ["line_metrics"] = lines, ["hit_test_range_metrics"] = hitTest,
                ["trimming"] = trimming, ["inline_object_draws"] = renderer.InlineDraws.DeepClone(),
                ["hit_test_quantity"] = "DirectWrite HitTestTextRange advance/selection rectangles, not DOM Range ink/font bounds",
                ["glyph_runs"] = renderer.Runs.DeepClone(), ["limitations"] = renderer.Limitations.DeepClone()
            };
            failure = null; drawDirty = false;
        }
        catch (Exception ex) { failure = ex.ToString(); InvalidateDraw(); }
        finally
        {
            if (clipped && context != IntPtr.Zero) Method<VoidCall>(context, 46)(context);
            if (began)
            {
                var end = Method<EndSurface>(surfaceInterop, 5)(surfaceInterop);
                readback?.ObserveEndDraw(end);
                if (end < 0) failure += "\nSurface EndDraw failed: 0x" + end.ToString("x8");
            }
            Release(ref brush); Release(ref context); rendering = false;
        }
    }
}
