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

// Selectable production path text. The source never gains hidden characters or
// line breaks: ICU/source ranges choose lines, and real NativeLabels draw them.
public sealed partial class NativePathText : UserControl
{
    internal sealed record PaintedLine(int Start, int End, bool Emergency, NativeLabel Label, double Y, double Height);
    private readonly Surface body;
    private readonly string locale;
    private readonly MenuFlyout selectionMenu;
    private readonly List<PaintedLine> lines = [];
    private readonly List<Rectangle> selectionPaint = [];
    private NativePathBoundaries? boundaries;
    private NativePathMeasurement? measured, strut;
    private NativePathPeer? peer;
    private double measuredWidth = double.NaN, desiredWidth, desiredHeight;
    private int anchor, caret;
    private bool dragging;
    private TextBlock? fallback;
    private string? failure;
    private JsonObject? layoutEvidence;
    private long layoutRevision;
    internal string SourceText { get; }
    internal IReadOnlyList<PaintedLine> PaintedLines => lines;
    internal int SelectionStart => Math.Min(anchor, caret);
    internal int SelectionEnd => Math.Max(anchor, caret);

    public NativePathText(string text, string locale, string copyLabel, string selectAllLabel)
    {
        SourceText = text; this.locale = locale;
        IsTabStop = true; UseLayoutRounding = false; Padding = new Thickness(0); BorderThickness = new Thickness(0);
        MinWidth = MinHeight = 0; HorizontalAlignment = HorizontalAlignment.Left; VerticalAlignment = VerticalAlignment.Top;
        HorizontalContentAlignment = HorizontalAlignment.Stretch; VerticalContentAlignment = VerticalAlignment.Top;
        FontFamily = new FontFamily(FontFamilies.UI); FontSize = 12.5;
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
        ["owner_identity"] = ProductionIdentity(this), ["layout_revision"] = layoutRevision,
        ["status"] = failure == null && layoutEvidence != null ? "laid-out" : "failed-or-not-laid-out",
        ["failure"] = failure, ["layout"] = layoutEvidence?.DeepClone(), ["selection_anchor"] = anchor, ["selection_caret"] = caret,
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
            ["complete_source_text"] = SourceText, ["actual_label_text"] = candidate.Text,
            ["source_slice_matches"] = SourceText[line.Start..line.End] == candidate.Text,
            ["same_retained_label_reference"] = ReferenceEquals(lines[index].Label, candidate),
            ["same_current_body_parent"] = ReferenceEquals(VisualTreeHelper.GetParent(candidate), body),
            ["same_content_body"] = ReferenceEquals(Content, body), ["label_is_loaded"] = candidate.IsLoaded,
            ["actual_line_y"] = line.Y, ["actual_line_height"] = line.Height,
            ["quantity"] = "Ownership and source mapping only; child layout/draw and final presentation require their own evidence"
        };
    }
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
            boundaries ??= NativePathIcu.Read(SourceText, locale);
            measured ??= NativePathMeasure.Shape(SourceText, "Cascadia Code", 11.5, 400, locale);
            strut ??= NativePathMeasure.Shape("", FontFamilies.UI, 12.5, 400, locale);
            var chosen = NativePathLineBreaks.Select(SourceText.Length, measured.Clusters, boundaries.Lines, boundaries.Characters, width);
            var parentAscent = strut.Baseline + (20 - strut.NaturalHeight) / 2;
            desiredWidth = desiredHeight = 0; var receiptLines = new JsonArray();
            foreach (var segment in chosen)
            {
                var label = new NativeLabel(SourceText[segment.Start..segment.End], "Cascadia Code", 11.5, 400, locale, 18.4)
                { Foreground = Foreground, IsHitTestVisible = false };
                body.Children.Add(label); label.Measure(new Size(width, double.PositiveInfinity));
                var baseline = label.FirstBaseline;
                if (!double.IsFinite(baseline) || baseline <= 0) throw new InvalidOperationException("Actual path line has no measured baseline");
                var (ascent, descent) = NativePathLineBreaks.LineBox(parentAscent, 20, baseline, label.DesiredSize.Height);
                var height = ascent + descent; var y = desiredHeight + ascent - baseline;
                lines.Add(new PaintedLine(segment.Start, segment.End, segment.Emergency, label, y, height));
                receiptLines.Add(new JsonObject { ["start_utf16"] = segment.Start, ["end_utf16"] = segment.End,
                    ["source_text"] = label.Text, ["emergency"] = segment.Emergency, ["label_y"] = y,
                    ["line_height"] = height, ["actual_line_baseline"] = baseline,
                    ["actual_line_desired_width"] = label.DesiredSize.Width, ["actual_line_desired_height"] = label.DesiredSize.Height });
                desiredHeight += height; desiredWidth = Math.Max(desiredWidth, label.DesiredSize.Width);
            }
            layoutEvidence = new JsonObject { ["available_width"] = width, ["icu"] = boundaries.Evidence.DeepClone(),
                ["source_measurement"] = measured.Evidence.DeepClone(), ["parent_strut_measurement"] = strut.Evidence.DeepClone(),
                ["parent_strut_size"] = 12.5, ["parent_strut_line_height"] = 20, ["inline_size"] = 11.5,
                ["inline_line_height"] = 18.4, ["lines"] = receiptLines };
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
            fallback = new TextBlock { FontFamily = new FontFamily(FontFamilies.UI), FontSize = 12.5, LineHeight = 20,
                LineStackingStrategy = LineStackingStrategy.MaxHeight, TextWrapping = TextWrapping.Wrap,
                IsTextSelectionEnabled = true, Foreground = Foreground };
            fallback.Inlines.Add(new Run { Text = SourceText, FontFamily = new FontFamily("Cascadia Code"), FontSize = 11.5 });
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
            foreach (var line in owner.lines) line.Label.Arrange(new Rect(0, line.Y, line.Label.DesiredSize.Width, line.Label.DesiredSize.Height));
            owner.ArrangeSelection(); return final;
        }
    }

    internal int PositionAt(Point point)
    {
        if (lines.Count == 0) return 0;
        var line = lines.MinBy(line => point.Y < line.Y ? line.Y - point.Y : Math.Max(0, point.Y - line.Y - line.Label.DesiredSize.Height))!;
        return line.Start + line.Label.PathPositionAt(point.X, point.Y - line.Y);
    }
    internal IReadOnlyList<Rect> LocalRanges(int start, int end)
    {
        var result = new List<Rect>();
        foreach (var line in lines)
        {
            var first = Math.Max(start, line.Start); var last = Math.Min(end, line.End);
            if (first >= last) continue;
            foreach (var rectangle in line.Label.PathRangeRectangles(first - line.Start, last - line.Start))
                result.Add(new Rect(rectangle.X, rectangle.Y + line.Y, rectangle.Width, rectangle.Height));
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
            var line = lines.FirstOrDefault(line => caret >= line.Start && caret < line.End) ?? lines.LastOrDefault();
            next = e.Key == VirtualKey.Home ? control ? 0 : line?.Start ?? 0 : control ? SourceText.Length : line?.End ?? SourceText.Length;
        }
        else if (e.Key is VirtualKey.Up or VirtualKey.Down)
        {
            var index = lines.FindIndex(line => caret >= line.Start && caret < line.End); if (index < 0) index = lines.Count - 1;
            if (index < 0) return;
            var line = lines[index]; var target = lines[Math.Clamp(index + (e.Key == VirtualKey.Up ? -1 : 1), 0, lines.Count - 1)];
            next = target.Start + target.Label.PathPositionAt(line.Label.PathPositionX(caret - line.Start), 0);
        }
        else return;
        SetSelection(shift ? anchor : next, next); e.Handled = true;
    }
}
