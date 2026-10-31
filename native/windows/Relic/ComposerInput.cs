using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;
using Windows.ApplicationModel.DataTransfer;

namespace Relic;

// A real editable RichEdit document. TextBox does not expose paragraph spacing;
// keeping a TextBox and measuring a separate TextBlock would not change the
// actual input layout, caret, selection, or IME composition geometry.
public sealed class ComposerInput : RichEditBox
{
    private string value = "";
    private int pendingStart, pendingLength;
    private bool formatting, composing;
    private TextBlock? placeholder;
    private (string Family, double Size, ushort Weight, Windows.UI.Color Color)? appliedFormat;
    public bool IsDocumentReady { get; private set; }
    public string? InitializationFailure { get; private set; }
    public new event EventHandler? TextChanged;
    public event EventHandler<ComposerClipboardFailure>? ClipboardFailed;

    public ComposerInput()
    {
        AcceptsReturn = true; TextWrapping = TextWrapping.Wrap;
        MinWidth = 0; MinHeight = 26; MaxHeight = 260;
        Padding = new Thickness(0, 2, 0, 2); BorderThickness = new Thickness(0); CornerRadius = new CornerRadius(0);
        FontSize = 14; FontFamily = new FontFamily("Segoe UI Variable Text");
        Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent);
        UseLayoutRounding = false; UseSystemFocusVisuals = false;
        ClipboardCopyFormat = RichEditClipboardFormat.PlainText;
        DisabledFormattingAccelerators = DisabledFormattingAccelerators.All;
        Template = (ControlTemplate)XamlReader.Load("""
            <ControlTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" TargetType="RichEditBox">
              <Grid Background="{TemplateBinding Background}" UseLayoutRounding="False">
                <ScrollViewer x:Name="ContentElement" Padding="{TemplateBinding Padding}" Foreground="{TemplateBinding Foreground}"
                  HorizontalScrollMode="Disabled" HorizontalScrollBarVisibility="Disabled" VerticalScrollMode="Auto" VerticalScrollBarVisibility="Auto"
                  IsTabStop="False" ZoomMode="Disabled" AutomationProperties.AccessibilityView="Raw" UseLayoutRounding="False"/>
                <TextBlock x:Name="PlaceholderTextContentPresenter" Text="{TemplateBinding PlaceholderText}" Padding="{TemplateBinding Padding}"
                  FontFamily="{TemplateBinding FontFamily}" FontSize="{TemplateBinding FontSize}" FontWeight="{TemplateBinding FontWeight}"
                  Foreground="#757575" TextWrapping="{TemplateBinding TextWrapping}" LineStackingStrategy="BlockLineHeight"
                  VerticalAlignment="Top" IsHitTestVisible="False" UseLayoutRounding="False"/>
              </Grid>
            </ControlTemplate>
            """);
        Loaded += (_, _) => InitializeDocument();
        base.TextChanged += (_, _) => ReadChange();
        TextCompositionStarted += (_, _) => composing = true;
        TextCompositionEnded += (_, _) => { composing = false; ReadChange(); ApplyDocumentFormat(); };
        RegisterPropertyChangedCallback(FontSizeProperty, (_, _) => ApplyDocumentFormat());
        RegisterPropertyChangedCallback(FontFamilyProperty, (_, _) => ApplyDocumentFormat());
        RegisterPropertyChangedCallback(FontWeightProperty, (_, _) => ApplyDocumentFormat());
        RegisterPropertyChangedCallback(ForegroundProperty, (_, _) => ApplyDocumentFormat());
        CopyingToClipboard += (_, args) => { args.Handled = true; CopySelectionToClipboard(); };
        CuttingToClipboard += (_, args) => { args.Handled = true; CutSelectionToClipboard(); };
        Paste += async (_, args) => { args.Handled = true; await PastePlainText(); };
    }

    protected override void OnApplyTemplate()
    {
        base.OnApplyTemplate();
        placeholder = GetTemplateChild("PlaceholderTextContentPresenter") as TextBlock;
        if (placeholder != null) placeholder.LineHeight = FontSize * 1.6;
    }

    private static string Normalize(string text) => text.Replace("\r\n", "\n").Replace('\r', '\n');

    public string Text
    {
        get
        {
            if (!IsDocumentReady) return value;
            // Omit only RichEdit's undeletable final paragraph terminator.
            // TextGetOptions.UseLf preserves the user's actual trailing LFs.
            TextDocument.GetText(TextGetOptions.UseLf, out var text);
            return text;
        }
        set
        {
            var next = Normalize(value ?? "");
            if (Text == next) return;
            this.value = next; pendingStart = Math.Min(pendingStart, next.Length); pendingLength = 0;
            if (IsDocumentReady)
            {
                TextDocument.SetText(TextSetOptions.None, next);
                ApplyDocumentFormat(force: true);
                TextDocument.Selection.SetRange(pendingStart, pendingStart);
            }
            TextChanged?.Invoke(this, EventArgs.Empty);
        }
    }

    public int SelectionStart
    {
        get => IsDocumentReady ? Math.Clamp(TextDocument.Selection.StartPosition, 0, Text.Length) : pendingStart;
        set => Select(value, SelectionLength);
    }
    public int SelectionLength
    {
        get => IsDocumentReady ? Math.Clamp(TextDocument.Selection.EndPosition, SelectionStart, Text.Length) - SelectionStart : pendingLength;
        set => Select(SelectionStart, value);
    }
    public string SelectedText
    {
        get => Text.Substring(SelectionStart, SelectionLength);
        set
        {
            if (IsReadOnly) return;
            var next = Normalize(value ?? ""); var start = SelectionStart;
            if (IsDocumentReady)
            {
                var range = TextDocument.GetRange(start, start + SelectionLength);
                range.SetText(TextSetOptions.None, next);
                Select(start + next.Length, 0);
            }
            else { Text = Text[..start] + next + Text[(start + SelectionLength)..]; Select(start + next.Length, 0); }
        }
    }
    public void Select(int start, int length)
    {
        pendingStart = Math.Clamp(start, 0, Text.Length); pendingLength = Math.Clamp(length, 0, Text.Length - pendingStart);
        if (IsDocumentReady) TextDocument.Selection.SetRange(pendingStart, pendingStart + pendingLength);
    }
    public void SelectAll() => Select(0, Text.Length);
    public void Undo() { if (IsDocumentReady && TextDocument.CanUndo()) TextDocument.Undo(); }
    public void Redo() { if (IsDocumentReady && TextDocument.CanRedo()) TextDocument.Redo(); }
    public void CopySelectionToClipboard()
    {
        if (SelectionLength == 0) return;
        try { var package = new DataPackage(); package.SetText(SelectedText); Clipboard.SetContent(package); }
        catch (Exception ex) { ClipboardFailed?.Invoke(this, new("copy", ex)); }
    }
    public void CutSelectionToClipboard()
    {
        if (IsReadOnly || SelectionLength == 0) return;
        try { var package = new DataPackage(); package.SetText(SelectedText); Clipboard.SetContent(package); SelectedText = ""; }
        catch (Exception ex) { ClipboardFailed?.Invoke(this, new("copy", ex)); }
    }
    public async Task PastePlainText()
    {
        if (IsReadOnly) return;
        try
        {
            var clipboard = Clipboard.GetContent();
            if (!clipboard.Contains(StandardDataFormats.Text)) return;
            // Keep the actual range selected when paste was requested, even if
            // retrieving clipboard text yields to another UI event.
            var range = IsDocumentReady ? TextDocument.GetRange(SelectionStart, SelectionStart + SelectionLength) : null;
            var text = Normalize(await clipboard.GetTextAsync());
            if (range != null) { range.SetText(TextSetOptions.None, text); Select(range.EndPosition, 0); }
            else SelectedText = text;
        }
        catch (Exception ex) { ClipboardFailed?.Invoke(this, new("paste", ex)); }
    }

    private void InitializeDocument()
    {
        if (IsDocumentReady) return;
        try
        {
            TextDocument.SetText(TextSetOptions.None, value);
            IsDocumentReady = true; ApplyDocumentFormat(force: true); Select(pendingStart, pendingLength);
            TextDocument.GetText(TextGetOptions.UseLf, out var actual);
            if (actual != value) throw new InvalidOperationException("The editable document did not preserve its plain-text value.");
            InitializationFailure = null;
        }
        catch (Exception ex) { IsDocumentReady = false; InitializationFailure = ex.GetType().Name + ": " + ex.Message; }
    }
    private void ReadChange()
    {
        if (!IsDocumentReady || formatting) return;
        var actual = Text;
        if (actual == value) return;
        value = actual; TextChanged?.Invoke(this, EventArgs.Empty);
    }
    private void ApplyDocumentFormat(bool force = false)
    {
        if (placeholder != null) placeholder.LineHeight = FontSize * 1.6;
        if (!IsDocumentReady || formatting || composing) return;
        var color = Foreground is SolidColorBrush ink ? ink.Color : TextDocument.GetDefaultCharacterFormat().ForegroundColor;
        var requested = (FontFamily.Source, FontSize, FontWeight.Weight, color);
        // Refreshing a snapshot supplies a new SolidColorBrush with the same
        // color. Do not add formatting operations to the user's undo history.
        if (!force && appliedFormat == requested) return;
        formatting = true;
        try
        {
            var document = TextDocument;
            var characters = document.GetDefaultCharacterFormat();
            characters.Name = FontFamily.Source; characters.Size = (float)(FontSize * 72 / 96); characters.Weight = FontWeight.Weight;
            characters.ForegroundColor = color;
            document.SetDefaultCharacterFormat(characters);
            var paragraph = document.GetDefaultParagraphFormat(); paragraph.SpaceBefore = paragraph.SpaceAfter = 0; paragraph.SetIndents(0, 0, 0);
            // The SDK defines both character Size and linear line spacing in
            // points. Layout is in DIPs. This sets the real document, not a
            // separately measured surrogate and not the control's fixed Height.
            paragraph.SetLineSpacing(LineSpacingRule.Exactly, (float)(FontSize * 1.6 * 72 / 96));
            document.SetDefaultParagraphFormat(paragraph);
            var story = document.GetRange(0, int.MaxValue);
            story.CharacterFormat.SetClone(characters); story.ParagraphFormat.SetClone(paragraph);
            appliedFormat = requested;
        }
        finally { formatting = false; }
    }

    protected override AutomationPeer OnCreateAutomationPeer() => new ComposerInputAutomationPeer(this);
}

public sealed class ComposerInputAutomationPeer(ComposerInput owner) : RichEditBoxAutomationPeer(owner)
{
    protected override string GetClassNameCore() => nameof(ComposerInput);
}

public sealed record ComposerClipboardFailure(string Operation, Exception Error);

// Voice dictation uses the same selection/text contract for normal settings
// fields and the real RichEdit composer. It never writes to a hidden TextBox.
internal sealed class VoiceTextTarget
{
    private readonly TextBox? plain;
    private readonly ComposerInput? composer;
    public VoiceTextTarget(TextBox input) => plain = input;
    public VoiceTextTarget(ComposerInput input) => composer = input;
    public string Text { get => composer?.Text ?? plain!.Text; set { if (composer != null) composer.Text = value; else plain!.Text = value; } }
    public int SelectionStart { get => composer?.SelectionStart ?? plain!.SelectionStart; set { if (composer != null) composer.SelectionStart = value; else plain!.SelectionStart = value; } }
    public int SelectionLength => composer?.SelectionLength ?? plain!.SelectionLength;
    public bool Focus(FocusState state) => (composer as Control ?? plain!).Focus(state);
}
