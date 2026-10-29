using Microsoft.UI.Xaml;
using Microsoft.UI.Text;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Documents;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using System.Runtime.InteropServices.WindowsRuntime;
using Windows.Foundation;

namespace Relic;

public sealed partial class MainWindow
{
    private WorkspaceCodeView? workspaceCode;

    private bool EditWorkspaceCode(string action)
    {
        if (workspaceCode is not { IsLoaded: true, IsDocumentReady: true } code || pane != "files") return false;
        var focused = Microsoft.UI.Xaml.Input.FocusManager.GetFocusedElement(root.XamlRoot);
        var selection = code.TextDocument.Selection;
        var selected = code.ReadSelectedSourceText();
        if (!ReferenceEquals(focused, code) && (action is not ("copy" or "quote") || selected.Length == 0)) return false;
        switch (action)
        {
            case "copy": if (selected.Length > 0) Copy(selected); return true;
            case "quote": if (selected.Length > 0) Quote(T("common.quote"), selected); else Note(T("appmenu.quote_need_selection")); return true;
            case "all": selection.SetRange(0, code.SourceText.Length); return true;
            // The file preview is read-only. Editing shortcuts must not be
            // redirected to the composer while focus is inside this document.
            case "cut": case "paste": case "undo": case "redo": return true;
            default: return false;
        }
    }
    private TextBlock WorkspaceText(string value, double size = 12.5, double lineHeight = 20, bool muted = false, ushort weight = 400)
        => OverviewText(value, size, muted, weight, lineHeight);

    private TextBlock WorkspaceLabel(string value, double size = 12.5, ushort weight = 400)
    {
        var label = WorkspaceText(value, size, size * 1.6, weight: weight); label.TextWrapping = TextWrapping.NoWrap; label.TextTrimming = TextTrimming.CharacterEllipsis;
        return label;
    }

    private FrameworkElement WorkspaceIcon(string name, double size)
    {
        var icon = (ReferenceVectorIcon)ReferenceIcon(name, size); icon.Foreground = Muted; icon.VerticalAlignment = VerticalAlignment.Center; return icon;
    }

    private StackPanel WorkspaceBlock(StackPanel parent, string? heading = null, UIElement? action = null)
    {
        var content = new StackPanel { Spacing = 8 };
        if (heading != null) content.Children.Add(OverviewHeading(WorkspaceText(heading, 12, 19.2, true), action));
        parent.Children.Add(new Border { Child = content, Padding = new Thickness(16, 14, 16, 14), BorderBrush = Line, BorderThickness = new Thickness(0, 0, 0, 1) });
        return content;
    }

    private TextBlock WorkspaceEmpty(string text) => WorkspaceText(text, 12.5, 20, true);
    private Border WorkspaceEmptyBlock(StackPanel parent, string text)
    {
        var block = new Border { Child = WorkspaceEmpty(text), Padding = new Thickness(16, 14, 16, 14), BorderBrush = Line, BorderThickness = new Thickness(0, 0, 0, 1) };
        parent.Children.Add(block); return block;
    }
    private TextBlock WorkspaceTreeEmpty(string text, int depth)
    {
        var label = WorkspaceEmpty(text); label.Margin = new Thickness(depth * 14 + 26, 0, 0, 0); return label;
    }

    private Button WorkspaceRow(UIElement content, Func<Task> action)
    {
        var button = QuietButton("", action); button.Content = content; button.Padding = new Thickness(6, 2, 6, 2); button.MinHeight = 26; button.CornerRadius = new CornerRadius(6);
        button.HorizontalAlignment = HorizontalAlignment.Stretch; button.HorizontalContentAlignment = HorizontalAlignment.Stretch; button.VerticalContentAlignment = VerticalAlignment.Center;
        button.FontSize = 12.5; return button;
    }

    private Grid WorkspaceFileRow(UIElement icon, FrameworkElement label, FrameworkElement? tail = null)
    {
        var row = new Grid { ColumnSpacing = 6 };
        row.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        if (tail != null) row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        ((FrameworkElement)icon).VerticalAlignment = VerticalAlignment.Center; row.Children.Add(icon);
        label.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(label, 1); row.Children.Add(label);
        if (tail != null) { tail.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(tail, 2); row.Children.Add(tail); }
        return row;
    }

    private static SolidColorBrush WorkspaceMix(SolidColorBrush foreground, SolidColorBrush background, double amount)
    {
        var a = foreground.Color; var b = background.Color;
        return new(Windows.UI.Color.FromArgb(255, (byte)Math.Round(a.R * amount + b.R * (1 - amount)), (byte)Math.Round(a.G * amount + b.G * (1 - amount)), (byte)Math.Round(a.B * amount + b.B * (1 - amount))));
    }

    private void WorkspaceCheckerboard(Border surface)
    {
        // This bitmap is the actual native background brush of the image,
        // including its transparent cells. It is not an evidence-only replica.
        int previousWidth = 0, previousHeight = 0; double previousScale = 0;
        XamlRoot? owner = null;
        void Paint()
        {
            var width = surface.ActualWidth - surface.BorderThickness.Left - surface.BorderThickness.Right;
            var height = surface.ActualHeight - surface.BorderThickness.Top - surface.BorderThickness.Bottom;
            var scale = surface.XamlRoot?.RasterizationScale ?? 1;
            if (width <= 0 || height <= 0 || scale <= 0) return;
            var pixelsWide = (int)Math.Ceiling(width * scale); var pixelsHigh = (int)Math.Ceiling(height * scale);
            if (pixelsWide == previousWidth && pixelsHigh == previousHeight && scale == previousScale) return;
            previousWidth = pixelsWide; previousHeight = pixelsHigh; previousScale = scale;
            var bitmap = new WriteableBitmap(pixelsWide, pixelsHigh);
            var pixels = new byte[checked(pixelsWide * pixelsHigh * 4)];
            var ink = Ink.Color; var alpha = (byte)Math.Round(ink.A * Ink.Opacity * .06);
            var blue = (byte)Math.Round(ink.B * alpha / 255d); var green = (byte)Math.Round(ink.G * alpha / 255d); var red = (byte)Math.Round(ink.R * alpha / 255d);
            for (var y = 0; y < pixelsHigh; y++)
                for (var x = 0; x < pixelsWide; x++)
                {
                    // repeating-conic-gradient starts at the top ray: NE and
                    // SW cells are painted, NW and SE remain transparent.
                    if (((int)(x * width / pixelsWide / 8) + (int)(y * height / pixelsHigh / 8)) % 2 == 0) continue;
                    var offset = (y * pixelsWide + x) * 4;
                    pixels[offset] = blue; pixels[offset + 1] = green; pixels[offset + 2] = red; pixels[offset + 3] = alpha;
                }
            using (var target = bitmap.PixelBuffer.AsStream()) target.Write(pixels, 0, pixels.Length);
            bitmap.Invalidate();
            surface.Background = new ImageBrush { ImageSource = bitmap, Stretch = Stretch.Fill, AlignmentX = AlignmentX.Left, AlignmentY = AlignmentY.Top };
        }
        void RootChanged(XamlRoot sender, XamlRootChangedEventArgs args) => Paint();
        surface.SizeChanged += (_, _) => Paint();
        surface.Loaded += (_, _) => { owner = surface.XamlRoot; if (owner != null) owner.Changed += RootChanged; Paint(); };
        surface.Unloaded += (_, _) => { if (owner != null) owner.Changed -= RootChanged; owner = null; };
    }

    private Border WorkspaceFileHeader(string name)
    {
        var row = new Grid { ColumnSpacing = 8 };
        row.ColumnDefinitions.Add(new() { Width = new GridLength(16) }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); row.ColumnDefinitions.Add(new() { Width = new GridLength(30) }); row.ColumnDefinitions.Add(new() { Width = new GridLength(30) });
        row.Children.Add(WorkspaceIcon("file", 16));
        var labels = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
        var title = WorkspaceLabel(name, 13, 650); title.LineHeight = 17.55;
        var path = WorkspaceLabel(filePath, 11); path.LineHeight = 13; path.FontFamily = new FontFamily("Cascadia Code"); path.Foreground = Muted; ToolTipService.SetToolTip(path, filePath);
        labels.Children.Add(title); labels.Children.Add(path); Grid.SetColumn(labels, 1); row.Children.Add(labels);
        var copy = IconButton("\uE8C8", "file.copy_path", () => { Copy(filePath); return Task.CompletedTask; }); copy.Content = WorkspaceIcon("copy", 15); Grid.SetColumn(copy, 2); row.Children.Add(copy);
        var open = IconButton("\uE8A7", "file.open_default", () => OpenDefault(filePath)); open.Content = WorkspaceIcon("open", 15); Grid.SetColumn(open, 3); row.Children.Add(open);
        var header = new Border { Child = row, Padding = new Thickness(14, 10, 8, 9), BorderBrush = Line, BorderThickness = new Thickness(0, 0, 0, 1), Background = Paint("F8F7F5", "191918") };
        Canvas.SetZIndex(header, 2); return header;
    }

    private static void WorkspaceStickyHeader(Border header)
    {
        ScrollViewer? scroll = null;
        var translation = new TranslateTransform(); header.RenderTransform = translation;
        void Move(object? sender, ScrollViewerViewChangedEventArgs e) { if (scroll != null) translation.Y = scroll.VerticalOffset; }
        header.Loaded += (_, _) =>
        {
            DependencyObject? current = VisualTreeHelper.GetParent(header);
            while (current != null && current is not ScrollViewer) current = VisualTreeHelper.GetParent(current);
            scroll = current as ScrollViewer;
            if (scroll != null) { translation.Y = scroll.VerticalOffset; scroll.ViewChanged += Move; }
        };
        header.Unloaded += (_, _) => { if (scroll != null) scroll.ViewChanged -= Move; scroll = null; };
    }

    private void DrawFileCode(string source, int selectedLine)
    {
        var lines = source.Replace("\r\n", "\n").Replace('\r', '\n').Split('\n'); var shown = lines.Take(6000).ToArray();
        var layout = new Grid { Padding = new Thickness(0, 0, 16, 0), MinHeight = shown.Length * 19.2 };
        layout.ColumnDefinitions.Add(new() { Width = new GridLength(60) }); layout.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        Border? highlight = null;
        if (selectedLine > 0 && selectedLine <= shown.Length)
        {
            highlight = new Border { Background = OverviewAlpha(Accent, .15), Height = 0, Margin = new Thickness(0, 0, -16, 0), VerticalAlignment = VerticalAlignment.Top };
            Grid.SetColumnSpan(highlight, 2); layout.Children.Add(highlight);
        }
        var numbers = new Canvas { Width = 60, IsHitTestVisible = false };
        var numberLabels = new List<TextBlock>();
        for (var i = 0; i < shown.Length; i++)
        {
            var number = WorkspaceText((i + 1).ToString(System.Globalization.CultureInfo.InvariantCulture), 12, 19.2); number.FontFamily = new FontFamily("Cascadia Code"); number.Foreground = Paint("B8B5AF", "5F5D58"); number.TextAlignment = TextAlignment.Right; number.IsTextSelectionEnabled = false;
            number.Height = 19.2; number.Width = 46; number.Opacity = 0; numbers.Children.Add(number); numberLabels.Add(number);
        }
        layout.Children.Add(numbers);
        var code = new WorkspaceCodeView(string.Join("\n", shown)) { FontFamily = new FontFamily("Cascadia Code"), FontSize = 12, Foreground = Ink };
        workspaceCode = code; Grid.SetColumn(code, 1); layout.Children.Add(code);
        var menu = new MenuFlyout();
        var copy = new MenuFlyoutItem { Text = T("common.copy") };
        copy.Click += (_, _) => { var value = code.ReadSelectedSourceText(); Copy(value.Length > 0 ? value : code.ReadSourceText()); }; menu.Items.Add(copy);
        var quote = new MenuFlyoutItem { Text = T("common.quote") };
        quote.Click += (_, _) => { var value = code.ReadSelectedSourceText(); Quote(T("common.quote"), value.Length > 0 ? value : code.ReadSourceText()); }; menu.Items.Add(quote); code.ContextFlyout = menu;
        var scroll = new ScrollViewer { Content = layout, HorizontalScrollMode = ScrollMode.Enabled, HorizontalScrollBarVisibility = ScrollBarVisibility.Auto, VerticalScrollMode = ScrollMode.Disabled, VerticalScrollBarVisibility = ScrollBarVisibility.Disabled };
        scroll.SizeChanged += (_, _) => layout.MinWidth = Math.Max(0, scroll.ActualWidth);
        var surface = new Border { Child = scroll, Padding = new Thickness(0, 6, 0, 18), BorderBrush = Line, BorderThickness = new Thickness(0, 1, 0, 0), Background = Paint("FFFFFF", "1F1F1E") };
        detail.Children.Add(surface);
        code.DocumentArranged += (_, _) =>
        {
            var rowTops = new double[shown.Length]; var rowBaselines = new double[shown.Length]; var start = 0;
            for (var i = 0; i < shown.Length; i++)
            {
                var range = code.TextDocument.GetRange(start, start + shown[i].Length);
                range.GetText(TextGetOptions.UseLf | TextGetOptions.AllowFinalEop, out var lineText);
                if (lineText != shown[i]) throw new InvalidOperationException("The native document line positions do not match the source range.");
                range.GetPoint(HorizontalCharacterAlignment.Left, VerticalCharacterAlignment.Top, PointOptions.Start | PointOptions.ClientCoordinates | PointOptions.AllowOffClient, out var top);
                range.GetPoint(HorizontalCharacterAlignment.Left, VerticalCharacterAlignment.Baseline, PointOptions.Start | PointOptions.ClientCoordinates | PointOptions.AllowOffClient, out var baseline);
                if (!double.IsFinite(top.Y) || !double.IsFinite(baseline.Y) || !double.IsFinite(numberLabels[i].BaselineOffset)) throw new InvalidOperationException("The native document returned no finite line baseline.");
                rowTops[i] = top.Y; rowBaselines[i] = baseline.Y; start += shown[i].Length + 1;
            }
            for (var i = 0; i < shown.Length; i++)
            {
                // Position each real line number at the baseline of the same
                // production document, rather than predicting row offsets.
                Canvas.SetTop(numberLabels[i], rowBaselines[i] - numberLabels[i].BaselineOffset); numberLabels[i].Opacity = 1;
            }
            numbers.Height = code.ActualHeight;
            if (highlight != null)
            {
                var row = selectedLine - 1;
                var height = row + 1 < shown.Length ? rowTops[row + 1] - rowTops[row] : row > 0 ? rowTops[row] - rowTops[row - 1] : code.TextDocument.GetDefaultParagraphFormat().LineSpacing * 96 / 72;
                highlight.Margin = new Thickness(0, rowTops[row], -16, 0); highlight.Height = Math.Max(0, height);
                layout.StartBringIntoView(new BringIntoViewOptions { TargetRect = new Rect(0, rowTops[row], 1, highlight.Height), VerticalAlignmentRatio = .5 });
            }
        };
        if (lines.Length > 6000) detail.Children.Add(new Border { Child = WorkspaceText(T("file.lines_shown", ("max", 6000), ("total", lines.Length)), 11.5, 18.4, true), Padding = new Thickness(14, 6, 14, 6) });
    }
}

// A real read-only RichEdit document supplies native keyboard/selection/UIA and
// real tab stops. The source contains the original tabs throughout its lifetime;
// only line endings are normalized, as in the reference code viewer.
public sealed class WorkspaceCodeView : RichEditBox
{
    public string SourceText { get; }
    public bool IsDocumentReady { get; private set; }
    public string? InitializationFailure { get; private set; }
    public double? SpaceAdvance { get; private set; }
    public event EventHandler? DocumentArranged;
    private bool initializing;

    public WorkspaceCodeView(string source)
    {
        SourceText = source; IsReadOnly = true; AcceptsReturn = true; IsSpellCheckEnabled = false; IsTextPredictionEnabled = false; ClipboardCopyFormat = RichEditClipboardFormat.PlainText;
        TextWrapping = TextWrapping.NoWrap; Padding = new Thickness(0); BorderThickness = new Thickness(0); MinWidth = 0; MinHeight = 0;
        Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent); UseSystemFocusVisuals = false; Opacity = 0;
        SelectionFlyout = null;
        Template = (ControlTemplate)XamlReader.Load("""
            <ControlTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" TargetType="RichEditBox">
              <ScrollViewer x:Name="ContentElement" Padding="{TemplateBinding Padding}" Margin="{TemplateBinding BorderThickness}" Foreground="{TemplateBinding Foreground}"
                HorizontalScrollMode="Disabled" VerticalScrollMode="Disabled" HorizontalScrollBarVisibility="Disabled" VerticalScrollBarVisibility="Disabled"
                IsTabStop="False" ZoomMode="Disabled" AutomationProperties.AccessibilityView="Raw"/>
            </ControlTemplate>
            """);
        Loaded += async (_, _) => await InitializeDocument();
        CopyingToClipboard += (_, args) =>
        {
            // The native story includes an undeletable final paragraph mark.
            // Copy the selected source range, including actual trailing LF,
            // without copying an extra implementation-only story terminator.
            var selected = ReadSelectedSourceText();
            if (selected.Length > 0)
            {
                var package = new Windows.ApplicationModel.DataTransfer.DataPackage(); package.SetText(selected);
                Windows.ApplicationModel.DataTransfer.Clipboard.SetContent(package);
            }
            args.Handled = true;
        };
    }

    public string ReadSourceText()
    {
        TextDocument.GetRange(0, SourceText.Length).GetText(TextGetOptions.UseLf | TextGetOptions.AllowFinalEop, out var value);
        return value;
    }

    public string ReadSelectedSourceText()
    {
        var selected = TextDocument.Selection;
        var start = Math.Clamp(selected.StartPosition, 0, SourceText.Length); var end = Math.Clamp(selected.EndPosition, start, SourceText.Length);
        TextDocument.GetRange(start, end).GetText(TextGetOptions.UseLf | TextGetOptions.AllowFinalEop, out var value);
        return value;
    }

    private Task LayoutTurn()
    {
        var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        if (!DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () => { UpdateLayout(); completion.SetResult(); })) completion.SetCanceled();
        return completion.Task;
    }

    private async Task InitializeDocument()
    {
        if (initializing || IsDocumentReady) return;
        initializing = true;
        try
        {
            InitializationFailure = null;
            var document = TextDocument;
            var characters = document.GetDefaultCharacterFormat(); characters.Name = FontFamily.Source; characters.Size = (float)(FontSize * 72 / 96); document.SetDefaultCharacterFormat(characters);
            var paragraph = document.GetDefaultParagraphFormat(); paragraph.SpaceBefore = 0; paragraph.SpaceAfter = 0; paragraph.SetIndents(0, 0, 0); paragraph.ClearAllTabs();
            paragraph.SetLineSpacing(LineSpacingRule.Exactly, 14.4f); document.SetDefaultParagraphFormat(paragraph);
            // Measure in this very document after its real native layout has
            // completed. Nothing from this initialization is font evidence.
            document.SetText(TextSetOptions.None, " "); await LayoutTurn();
            if (!IsLoaded) return;
            document.GetRange(0, 1).GetRect(PointOptions.ClientCoordinates | PointOptions.AllowOffClient, out var space, out _);
            if (!double.IsFinite(space.Width) || space.Width <= 0) throw new InvalidOperationException("The native document returned no space advance.");
            SpaceAdvance = space.Width;
            // TOM's default-tab and line-spacing dimensions are points; XAML
            // client layout is in DIPs (96/inch), so convert by 72/96.
            document.DefaultTabStop = (float)(space.Width * 4 * 72 / 96);
            document.SetText(TextSetOptions.None, SourceText); document.Selection.SetRange(0, 0); document.CaretType = CaretType.Null;
            await LayoutTurn(); if (!IsLoaded) return;
            // Bound the comparison to the original UTF-16 source range. TOM
            // stores each normalized LF as one CR and has a separate final EOP;
            // AllowFinalEop preserves any real final newline inside this range.
            var rendered = ReadSourceText();
            if (rendered != SourceText) throw new InvalidOperationException("The native document did not preserve the source text.");
            DocumentArranged?.Invoke(this, EventArgs.Empty); IsDocumentReady = true; Opacity = 1;
        }
        catch (Exception ex)
        {
            InitializationFailure = ex.GetType().Name + ": " + ex.Message;
            // Keep the actual source usable if the native layout API fails.
            // Capture observes the failure and must not label this ready.
            if (IsLoaded)
            {
                try { TextDocument.SetText(TextSetOptions.None, SourceText); }
                catch (Exception restore) { InitializationFailure += "; source restore: " + restore.GetType().Name + ": " + restore.Message; }
                Opacity = 1;
            }
        }
        finally { initializing = false; }
    }

    protected override AutomationPeer OnCreateAutomationPeer() => new WorkspaceCodeViewAutomationPeer(this);
}

public sealed class WorkspaceCodeViewAutomationPeer(WorkspaceCodeView owner) : RichEditBoxAutomationPeer(owner)
{
    protected override AutomationControlType GetAutomationControlTypeCore() => AutomationControlType.Document;
    protected override string GetClassNameCore() => nameof(WorkspaceCodeView);
}
