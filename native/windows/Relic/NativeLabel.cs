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
    private readonly float fontSize, lineHeight;
    private readonly uint weight;
    private readonly bool characterEllipsis, accessibleText;
    private IntPtr format, layout, surfaceInterop, trimmingSign;
    private SurfaceImageSource? surface;
    private ContentPresenter? presenter;
    private SolidColorBrush? foreground;
    private long foregroundToken, brushColorToken, brushOpacityToken;
    private XamlRoot? observedRoot;
    private float layoutWidth = -1, layoutHeight = -1;
    private double arrangedWidth, arrangedHeight, scale;
    private int pixelWidth, pixelHeight;
    private bool queued, rendering;
    private long layoutRevision, surfaceRevision, drawOrdinal;
    private JsonObject? receipt;
    private NativeLabelReadback? readback;
    private JsonObject? fallbackConfiguration;
    private string? failure;

    public NativeLabel(string text, string familyList, double fontSize, ushort fontWeight, string locale, double lineHeight,
        bool characterEllipsis = false, bool accessibleText = false)
    {
        this.text = text; this.familyList = familyList; this.fontSize = checked((float)fontSize);
        weight = fontWeight; this.locale = locale; this.lineHeight = checked((float)lineHeight);
        this.characterEllipsis = characterEllipsis; this.accessibleText = accessibleText;
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
        ["current_layout_revision"] = layoutRevision, ["current_surface_revision"] = surfaceRevision,
        ["current_draw_ordinal"] = drawOrdinal,
        ["current_submission"] = new JsonObject { ["source"] = "Actual NativeLabel state at receipt capture",
            ["is_loaded"] = IsLoaded, ["queued"] = queued, ["rendering"] = rendering,
            ["surface_binding_same_com_identity"] = ProductionSurfaceBindingMatches() },
        ["last_failure"] = failure, ["draw"] = receipt?.DeepClone(),
        ["surface_readback"] = readback?.Snapshot(),
        ["presentation_frame"] = null,
        ["coverage_complete"] = false,
        ["coverage_reason"] = "Submitted style and glyph callbacks are recorded; final PNG contribution, visible glyph ownership and equivalent text-line geometry remain unmeasured. Only successful EndDraw records describe submitted pixels; font identity comes from the actual renderer callback, never the fallback configuration."
    };

    private void Attach()
    {
        DetachSubscriptions();
        observedRoot = XamlRoot; if (observedRoot != null) observedRoot.Changed += RootChanged;
        DependencyObject? parent = VisualTreeHelper.GetParent(this);
        while (parent != null && parent is not ContentPresenter) parent = VisualTreeHelper.GetParent(parent);
        presenter = parent as ContentPresenter;
        if (presenter != null)
            foregroundToken = presenter.RegisterPropertyChangedCallback(ContentPresenter.ForegroundProperty, (_, _) => ObserveForeground());
        ObserveForeground(); InvalidateMeasure(); QueueDraw();
    }
    private void RootChanged(XamlRoot sender, XamlRootChangedEventArgs args)
    {
        // A rasterization-scale change changes the actual image's pixel/DIP
        // placement too, not just the surface allocation used by the renderer.
        if (sender.RasterizationScale != scale) InvalidateArrange();
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
    private void DetachSubscriptions()
    {
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
        DetachSubscriptions(); Release(ref surfaceInterop); surface = null; image.Source = null;
        Release(ref layout); Release(ref trimmingSign); Release(ref format); layoutWidth = layoutHeight = -1;
        pixelWidth = pixelHeight = 0; fallbackConfiguration = null; InvalidateDraw();
    }
    private void InvalidateDraw() { receipt = null; }

    private void EnsureLayout(float width, float height)
    {
        if (layout == IntPtr.Zero)
        {
            try
            {
                // CreateTextFormat accepts one family. The remaining ordered list
                // is installed on this exact layout through IDWriteTextLayout2.
                // No precomputed coverage is used as drawn-font evidence.
                var family = familyList.Split(',')[0].Trim().Trim('"');
                if (family.Length == 0) throw new InvalidOperationException("NativeLabel requires an explicit primary font family");
                var factory = NativeLabelDevice.Shared.WriteFactory;
                Check(Method<CreateFormat>(factory, 15)(factory, family, IntPtr.Zero, weight, 0, 5, fontSize, locale, out format));
                Check(Method<SetUInt>(format, 5)(format, 1)); // DWRITE_WORD_WRAPPING_NO_WRAP.
                Check(Method<CreateLayout>(factory, 18)(factory, text, checked((uint)text.Length), format, width, Math.Max(height, 1000), out layout));
                fallbackConfiguration = NativeLabelFallback.Apply(factory, layout, familyList);
                // Uniform CSS line height, with the actual natural line's baseline
                // centered in its leading. This is the production layout's line,
                // not a second layout or a reference-derived font measurement.
                var lines = ReadLines();
                if (lines.Length > 0)
                {
                    var baseline = lines[0].Baseline + (lineHeight - lines[0].Height) / 2;
                    Check(Method<SetLineSpacing>(layout, 10)(layout, 1, lineHeight, baseline));
                }
                if (characterEllipsis) trimmingSign = ApplyCharacterEllipsis(factory, layout);
                layoutWidth = width; layoutHeight = Math.Max(height, 1000); layoutRevision++; InvalidateDraw();
            }
            catch
            {
                Release(ref layout); Release(ref trimmingSign); Release(ref format); fallbackConfiguration = null;
                layoutWidth = layoutHeight = -1; throw;
            }
        }
        if (layoutWidth != width) { Check(Method<SetFloat>(layout, 28)(layout, width)); layoutWidth = width; layoutRevision++; InvalidateDraw(); }
        if (layoutHeight != height) { Check(Method<SetFloat>(layout, 29)(layout, height)); layoutHeight = height; layoutRevision++; InvalidateDraw(); }
    }
    private LineMetrics[] ReadLines()
    {
        var first = Method<GetArray>(layout, 59)(layout, IntPtr.Zero, 0, out var count);
        if (first < 0 && first != unchecked((int)0x8007007A)) Check(first);
        if (count == 0) return Array.Empty<LineMetrics>();
        var pointer = Marshal.AllocHGlobal(checked((int)count * Marshal.SizeOf<LineMetrics>()));
        try
        {
            Check(Method<GetArray>(layout, 59)(layout, pointer, count, out var actual)); var result = new LineMetrics[actual];
            for (var i = 0; i < result.Length; i++) result[i] = Marshal.PtrToStructure<LineMetrics>(pointer + i * Marshal.SizeOf<LineMetrics>());
            return result;
        }
        finally { Marshal.FreeHGlobal(pointer); }
    }
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
        try
        {
            EnsureLayout((float)(double.IsFinite(availableSize.Width) ? Math.Max(0, availableSize.Width) : 1000000), lineHeight);
            Check(Method<GetTextMetrics>(layout, 60)(layout, out var metrics));
            var desiredWidth = (double)metrics.WidthIncludingTrailingWhitespace;
            if (characterEllipsis && double.IsFinite(availableSize.Width)) desiredWidth = Math.Min(desiredWidth, Math.Max(0, availableSize.Width));
            image.Measure(new LayoutSize(desiredWidth, lineHeight));
            return new LayoutSize(desiredWidth, lineHeight);
        }
        catch (Exception ex) { failure = ex.ToString(); InvalidateDraw(); return new LayoutSize(0, lineHeight); }
    }
    protected override LayoutSize ArrangeOverride(LayoutSize finalSize)
    {
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
        if (queued || rendering || !IsLoaded) return; queued = true;
        if (!DispatcherQueue.TryEnqueue(() => { queued = false; if (IsLoaded) Render(); })) queued = false;
    }
    private void EnsureSurface(int width, int height)
    {
        if (surfaceInterop != IntPtr.Zero && pixelWidth == width && pixelHeight == height) return;
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
        rendering = true; InvalidateDraw(); readback = null; IntPtr context = IntPtr.Zero, brush = IntPtr.Zero;
        var began = false; var clipped = false;
        try
        {
            if (foreground == null) throw new NotSupportedException("NativeLabel requires an actual explicit or ContentPresenter SolidColorBrush foreground");
            scale = XamlRoot?.RasterizationScale ?? 1;
            EnsureLayout((float)arrangedWidth, (float)arrangedHeight);
            EnsureSurface(checked((int)Math.Ceiling(arrangedWidth * scale)), checked((int)Math.Ceiling(arrangedHeight * scale)));
            var update = new NativeLabelInterop.Rect { Right = pixelWidth, Bottom = pixelHeight }; var iid = DeviceContext;
            Check(Method<BeginSurface>(surfaceInterop, 4)(surfaceInterop, ref update, ref iid, out context, out var offset)); began = true;
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
            var trimming = ReadTrimming();
            using var renderer = new NativeLabelRenderer(context, brush, (float)scale, transform, trimmingSign);
            drawOrdinal++;
            var drawResult = Method<DrawLayout>(layout, 58)(layout, IntPtr.Zero, renderer.Pointer, 0, 0);
            if (renderer.CallbackFailure != null) throw new InvalidOperationException(renderer.CallbackFailure);
            Check(drawResult);
            Check(Method<GetTextMetrics>(layout, 60)(layout, out var metrics));
            var lines = new JsonArray(); foreach (var line in ReadLines())
                lines.Add(new JsonObject { ["length_utf16"] = line.Length, ["trailing_whitespace_utf16"] = line.TrailingWhitespaceLength,
                    ["newline_utf16"] = line.NewlineLength, ["height"] = line.Height, ["baseline"] = line.Baseline, ["is_trimmed"] = line.IsTrimmed != 0 });
            var hitTest = ReadHitTestBounds();
            Method<VoidCall>(context, 46)(context); clipped = false;
            // Read only the pixels written by this original production draw.
            // No second Draw/layout/target is substituted. Production sessions
            // never allocate staging storage or perform GPU/CPU readback.
            if (NativeLabelReadback.Enabled)
                readback = NativeLabelReadback.Observe(context, offset, pixelWidth, pixelHeight, layoutRevision, surfaceRevision, drawOrdinal);
            // BeginDraw/EndDraw belong to the XAML surface, not the shared D2D
            // context. A run callback alone is never treated as committed paint.
            var endResult = Method<EndSurface>(surfaceInterop, 5)(surfaceInterop); began = false;
            readback?.ObserveEndDraw(endResult); Check(endResult);
            receipt = new JsonObject
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
            failure = null;
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
