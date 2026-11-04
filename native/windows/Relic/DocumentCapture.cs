using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using System.IO.Compression;
using System.Runtime.InteropServices.WindowsRuntime;
using System.Text.Json.Nodes;
using Windows.Foundation;

namespace Relic;

public sealed partial class MainWindow
{
    private static JsonObject CaptureComposerDocument(ComposerInput input, string id, JsonArray errors, UIElement captureRoot, bool visible)
    {
        var document = input.TextDocument; var text = input.Text;
        document.GetText(TextGetOptions.AllowFinalEop, out var story);
        document.GetText(TextGetOptions.UseLf, out var value);
        var paragraph = document.GetDefaultParagraphFormat(); var selection = document.Selection;
        var raw = new JsonObject
        {
            ["ready"] = input.IsDocumentReady, ["initialization_error"] = input.InitializationFailure,
            ["whole_story"] = story, ["value_use_lf_without_final_eop"] = value,
            ["selection_start"] = selection.StartPosition, ["selection_end"] = selection.EndPosition,
            ["line_spacing_points"] = paragraph.LineSpacing, ["line_spacing_rule"] = paragraph.LineSpacingRule.ToString(),
            ["space_before_points"] = paragraph.SpaceBefore, ["space_after_points"] = paragraph.SpaceAfter,
            ["source"] = "Live editable RichEditTextDocument; actual plain text, paragraph properties, selection and per-range GetRect"
        };
        var ranges = new JsonArray(); var boxes = new JsonArray(); var local = new JsonArray(); var runs = new JsonArray();
        raw["character_ranges"] = ranges;
        var incomplete = !input.IsDocumentReady || input.InitializationFailure != null || value != text;
        if (visible && incomplete) errors.Add(id + ": editable document is not initialized or its public value differs from the native document: " + input.InitializationFailure);
        var transform = input.TransformToVisual(captureRoot); var lineYs = new HashSet<double>();
        if (visible && input.IsDocumentReady)
        {
            // Query the actual document, without creating another layout or
            // changing its selection. UTF-16 surrogate pairs stay one range.
            var offset = 0;
            while (offset < text.Length)
            {
                var length = System.Globalization.StringInfo.GetNextTextElement(text, offset).Length;
                var range = document.GetRange(offset, offset + length);
                range.GetText(TextGetOptions.UseLf | TextGetOptions.AllowFinalEop, out var actualText);
                range.GetRect(PointOptions.ClientCoordinates | PointOptions.AllowOffClient, out var box, out var hit);
                var actual = transform.TransformBounds(box);
                var complete = actualText == text.Substring(offset, length) && CaptureRectFinite(box) && CaptureRectFinite(actual);
                var evidence = new JsonObject { ["start"] = range.StartPosition, ["end"] = range.EndPosition, ["text"] = actualText,
                    ["local_bounds"] = CaptureBox(box), ["bounds"] = CaptureBox(actual), ["hit"] = hit, ["complete"] = complete };
                ranges.Add(evidence);
                if (!complete) { incomplete = true; errors.Add(id + ": editable range text/geometry failed at " + offset); }
                if (actualText is not ("\n" or "\r"))
                {
                    var format = range.CharacterFormat; var color = format.ForegroundColor;
                    var runBoxes = new JsonArray();
                    if (complete && actual.Width > 0 && actual.Height > 0)
                    {
                        boxes.Add(CaptureBox(actual)); local.Add(CaptureBox(box)); runBoxes.Add(CaptureBox(actual)); lineYs.Add(box.Y);
                    }
                    else { incomplete = true; complete = false; errors.Add(id + ": nonempty editable range has no actual rectangle at " + offset); }
                    runs.Add(new JsonObject { ["type"] = "RichEditTextRange", ["text"] = actualText,
                        ["start_offset"] = range.StartPosition, ["end_offset"] = range.EndPosition,
                        ["bounds"] = runBoxes, ["local_bounds"] = CaptureBox(box), ["geometry_complete"] = complete,
                        ["bounds_measurement"] = "Actual live RichEditTextRange.GetRect; text-range bounds, not glyph ink bounds",
                        ["coordinate_space"] = "content-window", ["font_size"] = format.Size * 96d / 72d,
                        ["font_weight"] = format.Weight, ["font_family"] = format.Name,
                        ["foreground"] = new JsonArray(color.R, color.G, color.B, color.A),
                        ["font_evidence_quantity"] = "Actual TOM CharacterFormat properties; physical glyph/fallback face remains unknown" });
                }
                offset += length;
            }
            // Include the native final insertion line (empty composer or an
            // actual trailing newline) without inventing a text glyph for it.
            var caret = document.GetRange(text.Length, text.Length);
            caret.GetRect(PointOptions.ClientCoordinates | PointOptions.AllowOffClient, out var caretBox, out var caretHit);
            raw["final_insertion_range"] = new JsonObject { ["position"] = caret.StartPosition, ["local_bounds"] = CaptureBox(caretBox), ["bounds"] = CaptureBox(transform.TransformBounds(caretBox)), ["hit"] = caretHit };
            if (CaptureRectFinite(caretBox) && caretBox.Height > 0) lineYs.Add(caretBox.Y);
            else { incomplete = true; errors.Add(id + ": actual final editable insertion line has no rectangle"); }
        }
        return new JsonObject { ["wrap"] = input.TextWrapping == TextWrapping.NoWrap ? "none" : "character", ["truncation"] = "none",
            ["line_count"] = visible && !incomplete ? lineYs.Count : null, ["character_boxes"] = boxes, ["local_character_boxes"] = local,
            ["character_boxes_coordinate_space"] = "content-window", ["text_geometry_status"] = visible ? "measured-or-explicit-error" : "not-visible",
            ["rich_text_runs"] = runs, ["document_evidence"] = raw, ["placeholder"] = input.PlaceholderText };
    }

    private static JsonObject CaptureImageBrush(ImageBrush brush)
    {
        JsonObject? Transform(Transform? transform)
        {
            if (transform == null) return null;
            var zero = transform.TransformPoint(new(0, 0)); var x = transform.TransformPoint(new(1, 0)); var y = transform.TransformPoint(new(0, 1));
            return new() { ["type"] = transform.GetType().FullName, ["m11"] = x.X - zero.X, ["m12"] = x.Y - zero.Y,
                ["m21"] = y.X - zero.X, ["m22"] = y.Y - zero.Y, ["offset_x"] = zero.X, ["offset_y"] = zero.Y };
        }
        var image = new JsonObject { ["type"] = brush.ImageSource?.GetType().FullName, ["stretch"] = brush.Stretch.ToString(),
            ["alignment_x"] = brush.AlignmentX.ToString(), ["alignment_y"] = brush.AlignmentY.ToString(),
            ["transform"] = Transform(brush.Transform), ["relative_transform"] = Transform(brush.RelativeTransform),
            ["source"] = "Actual live ImageBrush.ImageSource and brush placement properties" };
        if (brush.ImageSource is WriteableBitmap bitmap)
        {
            var bytes = new byte[bitmap.PixelBuffer.Length];
            using (var pixels = bitmap.PixelBuffer.AsStream()) pixels.ReadExactly(bytes);
            using var encoded = new System.IO.MemoryStream();
            using (var compressor = new ZLibStream(encoded, CompressionLevel.SmallestSize, leaveOpen: true)) compressor.Write(bytes);
            image["pixel_width"] = bitmap.PixelWidth; image["pixel_height"] = bitmap.PixelHeight;
            image["pixel_buffer_length"] = bytes.Length; image["pixel_format"] = "BGRA8-premultiplied";
            image["pixel_buffer_encoding"] = "base64-zlib"; image["pixel_buffer"] = Convert.ToBase64String(encoded.ToArray());
        }
        else if (brush.ImageSource is BitmapImage bitmapImage)
        {
            image["pixel_width"] = bitmapImage.PixelWidth; image["pixel_height"] = bitmapImage.PixelHeight;
            image["uri"] = bitmapImage.UriSource?.ToString(); image["pixel_buffer"] = null;
        }
        return image;
    }

    private static JsonObject CaptureCodeDocument(WorkspaceCodeView code, string id, JsonArray errors, UIElement captureRoot, bool visible)
    {
        var boxes = new JsonArray(); var local = new JsonArray(); var runs = new JsonArray();
        var document = code.TextDocument; var raw = new JsonObject { ["ready"] = code.IsDocumentReady, ["initialization_error"] = code.InitializationFailure,
            ["default_tab_stop_points"] = document.DefaultTabStop, ["source_range_start"] = 0, ["source_range_end"] = code.SourceText.Length,
            ["source"] = "Live read-only RichEditTextDocument; range text, GetRect and CharacterFormat" };
        document.GetText(TextGetOptions.AllowFinalEop, out var story); raw["whole_story"] = story;
        document.GetText(TextGetOptions.AllowFinalEop | TextGetOptions.UseLf, out var storyLf); raw["whole_story_use_lf"] = storyLf;
        var source = document.GetRange(0, code.SourceText.Length); source.GetText(TextGetOptions.UseLf | TextGetOptions.AllowFinalEop, out var text);
        raw["source_range_text"] = text; raw["actual_source_range_start"] = source.StartPosition; raw["actual_source_range_end"] = source.EndPosition;
        var incomplete = !code.IsDocumentReady || code.InitializationFailure != null;
        if (visible && incomplete) errors.Add(id + ": native source document initialization is incomplete: " + code.InitializationFailure);
        var transform = code.TransformToVisual(captureRoot); var offset = 0; var lines = 0;
        if (visible)
        {
            foreach (var line in text.Split('\n'))
            {
                var range = document.GetRange(offset, offset + line.Length);
                range.GetText(TextGetOptions.UseLf | TextGetOptions.AllowFinalEop, out var measuredText);
                range.GetRect(PointOptions.ClientCoordinates | PointOptions.AllowOffClient, out var box, out var hit);
                var actual = transform.TransformBounds(box); var complete = measuredText == line && CaptureRectFinite(box) && CaptureRectFinite(actual);
                raw["range_coordinate_space"] = "RichEditBox client DIPs transformed by actual TransformToVisual(content-root)";
                if (!complete) { incomplete = true; errors.Add(id + ": actual source range text/geometry failed at " + offset); }
                if (line.Length > 0)
                {
                    var format = range.CharacterFormat; var color = format.ForegroundColor;
                    var runBoxes = new JsonArray();
                    if (complete && actual.Width > 0 && actual.Height > 0) { boxes.Add(CaptureBox(actual)); local.Add(CaptureBox(box)); runBoxes.Add(CaptureBox(actual)); lines++; }
                    else { incomplete = true; complete = false; errors.Add(id + ": nonempty source range has no measured rectangle at " + offset); }
                    runs.Add(new JsonObject { ["type"] = "RichEditTextRange", ["text"] = measuredText, ["start_offset"] = range.StartPosition, ["end_offset"] = range.EndPosition,
                        ["bounds"] = runBoxes, ["local_bounds"] = CaptureBox(box), ["bounds_measurement"] = "Actual RichEditTextRange.GetRect, not glyph ink bounds",
                        ["coordinate_space"] = "content-window", ["geometry_complete"] = complete, ["hit"] = hit,
                        ["font_size"] = format.Size * 96d / 72d, ["font_weight"] = format.Weight, ["font_family"] = format.Name,
                        ["foreground"] = new JsonArray(color.R, color.G, color.B, color.A),
                        ["font_evidence_quantity"] = "Actual TOM CharacterFormat properties; physical glyph/fallback face remains unknown" });
                }
                offset += line.Length + 1;
            }
        }
        return new JsonObject { ["wrap"] = code.TextWrapping == TextWrapping.NoWrap ? "none" : "character", ["truncation"] = "none",
            ["line_count"] = visible && !incomplete ? lines : null, ["character_boxes"] = boxes, ["local_character_boxes"] = local,
            ["character_boxes_coordinate_space"] = "content-window", ["text_geometry_status"] = visible ? "measured-or-explicit-error" : "not-visible",
            ["rich_text_runs"] = runs, ["document_evidence"] = raw, ["placeholder"] = null };
    }
}
