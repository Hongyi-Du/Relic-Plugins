using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Documents;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;
using Windows.ApplicationModel.DataTransfer;
using Windows.Foundation;
using Windows.System;
using Windows.UI.Core;

namespace Relic;

// Selectable production text. The original path constructor keeps its existing
// inline/strut layout. Notices opt into normal whitespace and centered lines;
// their original source is retained separately from the mapped paint string.
public sealed partial class NativePathText : UserControl
{
    internal sealed record PaintedLine(int Start, int End, int PaintStart, int PaintEnd,
        bool Emergency, NativeLabel Label, double Y, double Height)
    { internal double X { get; set; } }
    private readonly Surface body;
    private readonly string locale;
    private readonly NativeSelectableTextStyle textStyle;
    private readonly NativeTextSourceMap sourceMap;
    private readonly MenuFlyout selectionMenu;
    private readonly List<PaintedLine> lines = [];
    private readonly List<Rectangle> selectionPaint = [];
    private NativePathBoundaries? boundaries;
    private NativePathBoundaries? paintBoundaries;
    private NativePathMeasurement? measured, strut;
    private NativePathPeer? peer;
    private double measuredWidth = double.NaN, desiredWidth, desiredHeight;
    private int anchor, caret;
    private bool dragging;
    private TextBlock? fallback;
    private string? failure;
    private JsonObject? layoutEvidence;
    private NativeBannerFlex.Intrinsic? bannerIntrinsic;
    private string? bannerIntrinsicFailure;
    private JsonObject? bannerIntrinsicEvidence, bannerAllocationEvidence;
    private long layoutRevision;
    internal string SourceText { get; }
    internal IReadOnlyList<PaintedLine> PaintedLines => lines;
    internal int SelectionStart => Math.Min(anchor, caret);
    internal int SelectionEnd => Math.Max(anchor, caret);

    public NativePathText(string text, string locale, string copyLabel, string selectAllLabel)
        : this(text, locale, copyLabel, selectAllLabel, NativeSelectableTextStyle.Path(FontFamilies.UI)) { }

    internal static NativePathText Notice(string text, string locale, string copyLabel, string selectAllLabel) =>
        new(text, locale, copyLabel, selectAllLabel, NativeSelectableTextStyle.Notice(FontFamilies.UI));

    internal static NativePathText Banner(string text, string locale, string copyLabel, string selectAllLabel) =>
        new(text, locale, copyLabel, selectAllLabel, NativeSelectableTextStyle.Banner(FontFamilies.UI));

    private void EnsureSourceMeasurement()
    {
        boundaries ??= NativePathIcu.Read(SourceText, locale);
        paintBoundaries ??= sourceMap.Paint == SourceText ? boundaries : NativePathIcu.Read(sourceMap.Paint, locale);
        measured ??= NativePathMeasure.Shape(sourceMap.Paint, textStyle.Family, textStyle.Size, textStyle.Weight, locale,
            measureIntrinsicWidths: textStyle.Kind == "banner");
    }

    internal bool TryGetBannerIntrinsic(out NativeBannerFlex.Intrinsic intrinsic)
    {
        if (textStyle.Kind != "banner") throw new InvalidOperationException("Only a banner participates in this flex layout");
        if (bannerIntrinsic is { } cached) { intrinsic = cached; return true; }
        if (bannerIntrinsicFailure != null) { intrinsic = default; return false; }
        try
        {
            EnsureSourceMeasurement();
            var actual = measured!.IntrinsicWidths ?? throw new InvalidOperationException("Production source layout has no intrinsic measurements");
            intrinsic = NativeBannerFlex.NormalText(sourceMap.Paint, measured.Clusters, paintBoundaries!.Lines, paintBoundaries.Characters);
            bannerIntrinsicEvidence = new JsonObject
            {
                ["source"] = "Actual source layout clusters and ICU boundaries used by the production normal-whitespace line selector",
                ["status"] = "measured", ["paint_text"] = sourceMap.Paint,
                ["source_measurement"] = measured.Evidence.DeepClone(), ["paint_icu"] = paintBoundaries.Evidence.DeepClone(),
                ["normal_max_content_width"] = intrinsic.Natural, ["normal_min_content_width"] = intrinsic.Minimum,
                ["directwrite_minimum_width"] = actual.MinimumWidth,
                ["normal_minus_directwrite_minimum"] = intrinsic.Minimum - actual.MinimumWidth,
                ["quantity"] = "Intrinsic widths consumed by production flex; not per-line draw geometry or final presentation"
            };
            bannerIntrinsic = intrinsic; return true;
        }
        catch (Exception error)
        {
            bannerIntrinsicFailure = error.ToString();
            bannerIntrinsicEvidence = new JsonObject { ["status"] = "failed", ["error"] = bannerIntrinsicFailure,
                ["hresult"] = error.HResult, ["source_measurement"] = measured?.Evidence.DeepClone(),
                ["fallback"] = "Original fixed icon and remaining-width selectable TextBlock layout" };
            intrinsic = default; return false;
        }
    }

    internal void ObserveBannerAllocation(double available, double gap, double iconBase,
        NativeBannerFlex.Allocation allocation, bool measuredFlex)
    {
        bannerAllocationEvidence = new JsonObject
        {
            ["source"] = "Actual NativeBannerLayout production measure and arrange allocation",
            ["available_width"] = double.IsFinite(available) ? JsonValue.Create(available) : null,
            ["unconstrained_width"] = double.IsPositiveInfinity(available), ["gap"] = gap, ["icon_flex_basis"] = iconBase,
            ["icon_width"] = allocation.Icon, ["text_width"] = allocation.Text,
            ["mode"] = measuredFlex ? "two-items-flex-0-1-auto" : "original-fixed-icon-fallback"
        };
    }

    private NativePathText(string text, string locale, string copyLabel, string selectAllLabel, NativeSelectableTextStyle style)
    {
        SourceText = text; this.locale = locale; textStyle = style;
        sourceMap = NativeTextSourceMap.Create(text, style.NormalWhitespace);
        IsTabStop = true; UseLayoutRounding = false; Padding = new Thickness(0); BorderThickness = new Thickness(0);
        MinWidth = MinHeight = 0; HorizontalAlignment = style.Center ? HorizontalAlignment.Stretch : HorizontalAlignment.Left;
        VerticalAlignment = VerticalAlignment.Top;
        HorizontalContentAlignment = HorizontalAlignment.Stretch; VerticalContentAlignment = VerticalAlignment.Top;
        FontFamily = new FontFamily(style.StrutFamily ?? style.Family); FontSize = style.StrutFamily != null ? style.StrutSize : style.Size;
        FontWeight = Microsoft.UI.Text.FontWeights.Normal;
        AutomationProperties.SetName(this, text);
        body = new Surface(this) { Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent), UseLayoutRounding = false };
        AutomationProperties.SetAccessibilityView(body, AccessibilityView.Raw); Content = body;
        RegisterPropertyChangedCallback(ForegroundProperty, (_, _) =>
        {
            foreach (var line in lines) line.Label.Foreground = Foreground;
            if (fallback != null) fallback.Foreground = Foreground;
        });
        PointerPressed += Pressed; PointerMoved += Moved;
        PointerReleased += (_, e) => { if (dragging) { dragging = false; ReleasePointerCapture(e.Pointer); e.Handled = true; } };
        PointerCaptureLost += (_, _) => dragging = false;
        KeyDown += Key;
        DoubleTapped += (_, e) =>
        {
            if (boundaries == null || fallback != null) return;
            var position = PositionAt(e.GetPosition(body)); var points = boundaries.Words;
            var first = points.LastOrDefault(p => p <= position); var last = points.FirstOrDefault(p => p > position, SourceText.Length);
            SetSelection(first, last); e.Handled = true;
        };
        selectionMenu = new MenuFlyout(); var menu = selectionMenu; var copy = new MenuFlyoutItem { Text = copyLabel }; var all = new MenuFlyoutItem { Text = selectAllLabel };
        copy.Click += (_, _) => Copy(); all.Click += (_, _) => SetSelection(0, SourceText.Length);
        menu.Opening += (_, _) => copy.IsEnabled = SelectionEnd > SelectionStart;
        menu.Items.Add(copy); menu.Items.Add(all); ContextFlyout = menu;
    }

    protected override AutomationPeer OnCreateAutomationPeer() => peer ??= new NativePathPeer(this);
    internal JsonObject CaptureProductionPathReceipt() => new()
    {
        ["source"] = "Actual NativePathText production line selection and actual child line objects",
        ["source_text"] = SourceText, ["source_utf16_length"] = SourceText.Length,
        ["text_style"] = StyleReceipt(), ["source_to_paint"] = SourceMapReceipt(),
        ["arranged_lines"] = new JsonArray(lines.Select(line => (JsonNode)new JsonObject
        { ["start_utf16"] = line.Start, ["end_utf16"] = line.End,
            ["paint_start_utf16"] = line.PaintStart, ["paint_end_utf16"] = line.PaintEnd,
            ["actual_line_x"] = line.X, ["actual_line_y"] = line.Y,
            ["actual_label_width"] = line.Label.ActualWidth, ["actual_label_height"] = line.Label.ActualHeight }).ToArray()),
        ["owner_identity"] = ProductionIdentity(this), ["layout_revision"] = layoutRevision,
        ["status"] = failure == null && layoutEvidence != null ? "laid-out" : "failed-or-not-laid-out",
        ["failure"] = failure, ["layout"] = layoutEvidence?.DeepClone(), ["selection_anchor"] = anchor, ["selection_caret"] = caret,
        ["banner_intrinsic"] = bannerIntrinsicEvidence?.DeepClone(), ["banner_allocation"] = bannerAllocationEvidence?.DeepClone(),
        ["glyph_face_inferred"] = false, ["final_png_identity_proven"] = false
    };
    internal bool OwnsProductionLine(NativeLabel candidate) => lines.Any(line => ReferenceEquals(line.Label, candidate));
    internal JsonObject CaptureProductionLineBinding(NativeLabel candidate)
    {
        var index = lines.FindIndex(line => ReferenceEquals(line.Label, candidate));
        if (index < 0) throw new ArgumentException("The actual label is not a retained production line", nameof(candidate));
        var line = lines[index];
        return new JsonObject
        {
            ["source"] = "Actual NativePathText retained NativeLabel object identity and unchanged source interval",
            ["owner_identity"] = ProductionIdentity(this), ["label_identity"] = ProductionIdentity(candidate),
            ["layout_revision"] = layoutRevision, ["line_index"] = index, ["line_count"] = lines.Count,
            ["start_utf16"] = line.Start, ["end_utf16"] = line.End,
            ["paint_start_utf16"] = line.PaintStart, ["paint_end_utf16"] = line.PaintEnd,
            ["complete_source_text"] = SourceText, ["actual_label_text"] = candidate.Text,
            ["source_slice_matches"] = SourceText[line.Start..line.End] == candidate.Text,
            ["paint_slice_matches"] = sourceMap.Paint[line.PaintStart..line.PaintEnd] == candidate.Text,
            ["source_to_paint"] = SourceMapReceipt(), ["text_style"] = StyleReceipt(),
            ["same_retained_label_reference"] = ReferenceEquals(lines[index].Label, candidate),
            ["same_current_body_parent"] = ReferenceEquals(VisualTreeHelper.GetParent(candidate), body),
            ["same_content_body"] = ReferenceEquals(Content, body), ["label_is_loaded"] = candidate.IsLoaded,
            ["actual_line_x"] = line.X, ["actual_line_y"] = line.Y, ["actual_line_height"] = line.Height,
            ["quantity"] = "Ownership and source mapping only; child layout/draw and final presentation require their own evidence"
        };
    }
    private JsonObject StyleReceipt() => new()
    {
        ["kind"] = textStyle.Kind, ["configured_family_list"] = textStyle.Family,
        ["size"] = textStyle.Size, ["weight"] = textStyle.Weight, ["line_height"] = textStyle.LineHeight,
        ["alignment"] = textStyle.Center ? "center" : "left",
        ["white_space"] = textStyle.NormalWhitespace ? "normal" : "preserve-source",
        ["wrap_policy"] = textStyle.NormalWhitespace ? "normal-boundaries-with-word-overflow" : "normal-then-emergency",
        ["strut_family"] = textStyle.StrutFamily, ["strut_size"] = textStyle.StrutSize,
        ["strut_line_height"] = textStyle.StrutLineHeight
    };
    private JsonObject SourceMapReceipt() => new()
    {
        ["source"] = "Actual production UTF16 source-to-paint mapping",
        ["source_text"] = sourceMap.Source, ["paint_text"] = sourceMap.Paint,
        ["normal_whitespace"] = textStyle.NormalWhitespace,
        ["spans"] = new JsonArray(sourceMap.Spans.Select(span => (JsonNode)new JsonObject
        { ["paint_start_utf16"] = span.PaintStart, ["paint_end_utf16"] = span.PaintStart + 1,
            ["source_start_utf16"] = span.SourceStart, ["source_end_utf16"] = span.SourceEnd }).ToArray())
    };
    private static JsonObject ProductionIdentity(DependencyObject value)
    {
        if (value is not WinRT.IWinRTObject native) throw new InvalidOperationException("Production object has no native WinRT identity");
        var pointer = native.NativeObject.GetRef();
        try { return new JsonObject { ["runtime_type"] = value.GetType().FullName,
            ["managed_reference_hash"] = RuntimeHelpers.GetHashCode(value), ["iunknown_identity"] = NativeLabelInterop.ComIdentity(pointer) }; }
        finally { NativeLabelInterop.Release(ref pointer); }
    }

    private void Reflow(double width)
    {
        width = double.IsFinite(width) ? Math.Max(0, width) : double.MaxValue;
        if (width == measuredWidth) return;
        measuredWidth = width; layoutRevision++;
        foreach (var line in lines) line.Label.DisposePathLine();
        body.Children.Clear(); lines.Clear(); selectionPaint.Clear(); fallback = null; failure = null;
        try
        {
            if (bannerIntrinsicFailure != null) throw new InvalidOperationException(bannerIntrinsicFailure);
            EnsureSourceMeasurement();
            if (textStyle.StrutFamily != null)
                strut ??= NativePathMeasure.Shape("", textStyle.StrutFamily, textStyle.StrutSize, 400, locale);
            var chosen = textStyle.NormalWhitespace
                ? NativeSelectableTextLayout.NoticeLines(sourceMap.Paint, measured!.Clusters, paintBoundaries!.Lines, paintBoundaries.Characters, width)
                : NativePathLineBreaks.Select(SourceText.Length, measured!.Clusters, boundaries!.Lines, boundaries.Characters, width)
                    .Select(line => new NativeSelectableTextLayout.Line(line.Start, line.End, line.Emergency)).ToArray();
            var parentAscent = strut != null ? strut.Baseline + (textStyle.StrutLineHeight - strut.NaturalHeight) / 2 : 0;
            desiredWidth = desiredHeight = 0; var receiptLines = new JsonArray();
            foreach (var segment in chosen)
            {
                var label = new NativeLabel(sourceMap.Paint[segment.Start..segment.End], textStyle.Family,
                    textStyle.Size, textStyle.Weight, locale, textStyle.LineHeight)
                { Foreground = Foreground, IsHitTestVisible = false };
                body.Children.Add(label); label.Measure(new Size(textStyle.NormalWhitespace ? double.PositiveInfinity : width, double.PositiveInfinity));
                var baseline = label.FirstBaseline;
                if (!double.IsFinite(baseline) || baseline <= 0) throw new InvalidOperationException("Actual path line has no measured baseline");
                var (ascent, descent) = strut != null
                    ? NativePathLineBreaks.LineBox(parentAscent, textStyle.StrutLineHeight, baseline, label.DesiredSize.Height)
                    : (baseline, label.DesiredSize.Height - baseline);
                var height = ascent + descent; var y = desiredHeight + ascent - baseline;
                var sourceStart = sourceMap.SourceStart(segment.Start); var sourceEnd = sourceMap.SourceEnd(segment.End);
                lines.Add(new PaintedLine(sourceStart, sourceEnd, segment.Start, segment.End, segment.Emergency, label, y, height));
                receiptLines.Add(new JsonObject { ["start_utf16"] = sourceStart, ["end_utf16"] = sourceEnd,
                    ["source_text"] = SourceText[sourceStart..sourceEnd], ["paint_text"] = label.Text,
                    ["paint_start_utf16"] = segment.Start, ["paint_end_utf16"] = segment.End,
                    ["emergency"] = segment.Emergency, ["label_y"] = y,
                    ["line_height"] = height, ["actual_line_baseline"] = baseline,
                    ["actual_line_desired_width"] = label.DesiredSize.Width, ["actual_line_desired_height"] = label.DesiredSize.Height });
                desiredHeight += height; desiredWidth = Math.Max(desiredWidth, label.DesiredSize.Width);
            }
            // The normal text viewport keeps its available width. An overlong
            // indivisible word is arranged at its actual width inside it, so a
            // framework desired-size clip does not silently truncate that word.
            if (textStyle.NormalWhitespace) desiredWidth = Math.Min(desiredWidth, width);
            layoutEvidence = new JsonObject { ["available_width"] = width, ["icu"] = boundaries!.Evidence.DeepClone(),
                ["paint_icu"] = paintBoundaries!.Evidence.DeepClone(), ["source_measurement"] = measured.Evidence.DeepClone(),
                ["parent_strut_measurement"] = strut?.Evidence.DeepClone(), ["text_style"] = StyleReceipt(),
                ["parent_strut_size"] = textStyle.StrutSize, ["parent_strut_line_height"] = textStyle.StrutLineHeight,
                ["inline_size"] = textStyle.Size, ["inline_line_height"] = textStyle.LineHeight, ["lines"] = receiptLines };
            ContextFlyout = selectionMenu;
            UpdateSelectionPaint();
        }
        catch (Exception error)
        {
            // Preserve readable/selectable production content if this OS lacks
            // ICU or a supported measurable layout; the receipt retains failure.
            failure = error.ToString(); layoutEvidence = null;
            foreach (var line in body.Children.OfType<NativeLabel>()) line.DisposePathLine();
            lines.Clear(); selectionPaint.Clear(); body.Children.Clear(); ContextFlyout = null;
            fallback = new TextBlock { FontFamily = new FontFamily(textStyle.StrutFamily ?? textStyle.Family),
                FontSize = textStyle.StrutFamily != null ? textStyle.StrutSize : textStyle.Size,
                LineHeight = textStyle.StrutFamily != null ? textStyle.StrutLineHeight : textStyle.LineHeight,
                LineStackingStrategy = textStyle.Kind == "banner" ? LineStackingStrategy.BlockLineHeight : LineStackingStrategy.MaxHeight,
                TextWrapping = textStyle.Kind == "banner" ? TextWrapping.WrapWholeWords : TextWrapping.Wrap,
                TextAlignment = textStyle.Center ? TextAlignment.Center : TextAlignment.Left,
                IsTextSelectionEnabled = true, Foreground = Foreground };
            if (textStyle.Kind == "banner") fallback.Language = locale;
            fallback.Inlines.Add(new Run { Text = SourceText, FontFamily = new FontFamily(textStyle.Family), FontSize = textStyle.Size });
            body.Children.Add(fallback); fallback.Measure(new Size(width, double.PositiveInfinity));
            desiredWidth = fallback.DesiredSize.Width; desiredHeight = fallback.DesiredSize.Height;
        }
    }

    private sealed class Surface(NativePathText owner) : Panel
    {
        protected override Size MeasureOverride(Size available)
        { owner.Reflow(available.Width); return new Size(owner.desiredWidth, owner.desiredHeight); }
        protected override Size ArrangeOverride(Size final)
        {
            if (owner.fallback != null) owner.fallback.Arrange(new Rect(0, 0, final.Width, final.Height));
            foreach (var line in owner.lines)
            {
                line.X = NativeSelectableTextLayout.LineX(final.Width, line.Label.DesiredSize.Width, owner.textStyle.Center);
                line.Label.Arrange(new Rect(line.X, line.Y, line.Label.DesiredSize.Width, line.Label.DesiredSize.Height));
            }
            owner.ArrangeSelection(); return final;
        }
    }

    internal int PositionAt(Point point)
    {
        if (lines.Count == 0) return 0;
        var line = lines.MinBy(line => point.Y < line.Y ? line.Y - point.Y : Math.Max(0, point.Y - line.Y - line.Label.DesiredSize.Height))!;
        var paintPosition = line.PaintStart + line.Label.PathPositionAt(
            NativeSelectableTextLayout.LocalX(point.X, line.X), point.Y - line.Y);
        return sourceMap.SourceHit(paintPosition, line.PaintStart, line.PaintEnd);
    }
    internal IReadOnlyList<Rect> LocalRanges(int start, int end)
    {
        var result = new List<Rect>();
        var painted = sourceMap.PaintRange(start, end);
        foreach (var line in lines)
        {
            var first = Math.Max(painted.Start, line.PaintStart); var last = Math.Min(painted.End, line.PaintEnd);
            if (first >= last) continue;
            foreach (var rectangle in line.Label.PathRangeRectangles(first - line.PaintStart, last - line.PaintStart))
                result.Add(new Rect(NativeSelectableTextLayout.OwnerX(rectangle.X, line.X), rectangle.Y + line.Y, rectangle.Width, rectangle.Height));
        }
        return result;
    }
    internal void SetSelection(int first, int last)
    {
        anchor = Math.Clamp(first, 0, SourceText.Length); caret = Math.Clamp(last, 0, SourceText.Length);
        UpdateSelectionPaint(); body.InvalidateArrange();
        peer?.RaiseAutomationEvent(AutomationEvents.TextPatternOnTextSelectionChanged);
    }
    private void UpdateSelectionPaint()
    {
        foreach (var rectangle in selectionPaint) body.Children.Remove(rectangle);
        selectionPaint.Clear();
        foreach (var _ in LocalRanges(SelectionStart, SelectionEnd))
        {
            var rectangle = new Rectangle { Fill = new SolidColorBrush(Windows.UI.Color.FromArgb(90, 75, 125, 205)), IsHitTestVisible = false };
            AutomationProperties.SetAccessibilityView(rectangle, AccessibilityView.Raw);
            body.Children.Insert(0, rectangle); selectionPaint.Add(rectangle);
        }
    }
    private void ArrangeSelection()
    {
        var boxes = LocalRanges(SelectionStart, SelectionEnd);
        for (var i = 0; i < Math.Min(boxes.Count, selectionPaint.Count); i++)
        { selectionPaint[i].Measure(new Size(boxes[i].Width, boxes[i].Height)); selectionPaint[i].Arrange(boxes[i]); }
    }
    private static bool Down(VirtualKey key) => (Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread(key) & CoreVirtualKeyStates.Down) != 0;
    private void Pressed(object sender, PointerRoutedEventArgs e)
    {
        if (fallback != null || !e.GetCurrentPoint(this).Properties.IsLeftButtonPressed) return;
        Focus(FocusState.Pointer); var position = PositionAt(e.GetCurrentPoint(body).Position);
        SetSelection(Down(VirtualKey.Shift) ? anchor : position, position); dragging = CapturePointer(e.Pointer); e.Handled = true;
    }
    private void Moved(object sender, PointerRoutedEventArgs e)
    { if (dragging) { SetSelection(anchor, PositionAt(e.GetCurrentPoint(body).Position)); e.Handled = true; } }
    private void Copy()
    {
        if (SelectionEnd <= SelectionStart) return;
        var data = new DataPackage(); data.SetText(SourceText[SelectionStart..SelectionEnd]); Clipboard.SetContent(data);
    }
    private void Key(object sender, KeyRoutedEventArgs e)
    {
        if (boundaries == null || fallback != null) return;
        var control = Down(VirtualKey.Control); var shift = Down(VirtualKey.Shift); var next = caret;
        if (control && e.Key == VirtualKey.C) { Copy(); e.Handled = true; return; }
        if (control && e.Key == VirtualKey.A) { SetSelection(0, SourceText.Length); e.Handled = true; return; }
        if (e.Key is VirtualKey.Left or VirtualKey.Right)
        {
            if (!shift && !control && SelectionStart != SelectionEnd) next = e.Key == VirtualKey.Left ? SelectionStart : SelectionEnd;
            else next = NativePathLineBreaks.Move(control ? boundaries.Words : boundaries.Characters, caret, e.Key == VirtualKey.Left ? -1 : 1, out _);
        }
        else if (e.Key is VirtualKey.Home or VirtualKey.End)
        {
            var line = LineAtSourceCaret();
            next = e.Key == VirtualKey.Home ? control ? 0 : line?.Start ?? 0 : control ? SourceText.Length : line?.End ?? SourceText.Length;
        }
        else if (e.Key is VirtualKey.Up or VirtualKey.Down)
        {
            var current = LineAtSourceCaret(); var index = current != null ? lines.IndexOf(current) : -1;
            if (index < 0) return;
            var line = lines[index]; var target = lines[Math.Clamp(index + (e.Key == VirtualKey.Up ? -1 : 1), 0, lines.Count - 1)];
            var currentPaint = Math.Clamp(sourceMap.PaintPosition(caret), line.PaintStart, line.PaintEnd);
            var ownerX = NativeSelectableTextLayout.OwnerX(line.Label.PathPositionX(currentPaint - line.PaintStart), line.X);
            var nextPaint = target.PaintStart + target.Label.PathPositionAt(NativeSelectableTextLayout.LocalX(ownerX, target.X), 0);
            next = sourceMap.SourceHit(nextPaint, target.PaintStart, target.PaintEnd);
        }
        else return;
        SetSelection(shift ? anchor : next, next); e.Handled = true;
    }
    private PaintedLine? LineAtSourceCaret() =>
        lines.FirstOrDefault(line => caret >= line.Start && caret < line.End)
        ?? lines.FirstOrDefault(line => line.Start >= caret) ?? lines.LastOrDefault();
}
