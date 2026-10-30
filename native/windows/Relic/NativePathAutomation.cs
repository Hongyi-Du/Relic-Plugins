using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Automation.Provider;
using Microsoft.UI.Xaml.Automation.Text;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.Foundation;

namespace Relic;

public sealed partial class NativePathText
{
    private sealed class NativePathPeer(NativePathText owner) : FrameworkElementAutomationPeer(owner), ITextProvider
    {
        internal NativePathText TextOwner => owner;
        internal IRawElementProviderSimple Provider => ProviderFromPeer(this);
        protected override AutomationControlType GetAutomationControlTypeCore() => AutomationControlType.Text;
        protected override string GetClassNameCore() => nameof(NativePathText);
        protected override string GetNameCore() => owner.SourceText;
        protected override bool IsControlElementCore() => true;
        protected override bool IsContentElementCore() => true;
        protected override bool IsKeyboardFocusableCore() => owner.IsTabStop;
        protected override void SetFocusCore() => owner.Focus(FocusState.Programmatic);
        protected override IList<AutomationPeer> GetChildrenCore() => owner.fallback != null && CreatePeerForElement(owner.fallback) is { } child ? [child] : [];
        protected override object GetPatternCore(PatternInterface pattern) => pattern == PatternInterface.Text && owner.failure == null ? this : base.GetPatternCore(pattern);
        public ITextRangeProvider DocumentRange => new PathRange(this, 0, owner.SourceText.Length);
        public SupportedTextSelection SupportedTextSelection => SupportedTextSelection.Single;
        public ITextRangeProvider[] GetSelection() => [new PathRange(this, owner.SelectionStart, owner.SelectionEnd)];
        public ITextRangeProvider[] GetVisibleRanges() => owner.lines.Where(line => ScreenRanges(line.Start, line.End).Count > 0)
            .Select(line => (ITextRangeProvider)new PathRange(this, line.Start, line.End)).ToArray();
        public ITextRangeProvider RangeFromChild(IRawElementProviderSimple child) =>
            throw new ArgumentException("Path text has no embedded automation child", nameof(child));
        public ITextRangeProvider RangeFromPoint(Point screenLocation)
        {
            var box = GetBoundingRectangle(); var scale = owner.XamlRoot?.RasterizationScale ?? 1;
            var position = owner.PositionAt(new Point((screenLocation.X - box.X) / scale, (screenLocation.Y - box.Y) / scale));
            return new PathRange(this, position, position);
        }
        internal IReadOnlyList<Rect> ScreenRanges(int start, int end)
        {
            if (!owner.IsLoaded || IsOffscreen()) return [];
            var host = GetBoundingRectangle(); var scale = owner.XamlRoot?.RasterizationScale ?? 1;
            var localRanges = owner.LocalRanges(start, end);
            if (localRanges.Count == 0) return [];
            var clip = new Rect(0, 0, owner.ActualWidth, owner.ActualHeight);
            if (owner.textStyle.NormalWhitespace)
            {
                // Normal CSS text can visibly overflow its line viewport. Start
                // with the actual requested glyph ranges, then intersect the
                // real ancestor clips instead of imposing a new owner clip.
                var left = localRanges.Min(range => range.Left); var top = localRanges.Min(range => range.Top);
                var right = localRanges.Max(range => range.Right); var bottom = localRanges.Max(range => range.Bottom);
                clip = new Rect(left, top, right - left, bottom - top);
            }
            for (DependencyObject? ancestor = owner; ancestor != null; ancestor = VisualTreeHelper.GetParent(ancestor))
            {
                if (ancestor is not FrameworkElement element) continue;
                if (element.Visibility != Visibility.Visible) return [];
                if (element.Clip is RectangleGeometry geometry)
                    clip.Intersect(element.TransformToVisual(owner).TransformBounds(geometry.Rect));
                if (element is ScrollViewer)
                    clip.Intersect(element.TransformToVisual(owner).TransformBounds(new Rect(0, 0, element.ActualWidth, element.ActualHeight)));
            }
            var result = new List<Rect>();
            foreach (var local in localRanges)
            {
                var actual = local; actual.Intersect(clip);
                if (actual.Width <= 0 || actual.Height <= 0 || actual.IsEmpty) continue;
                result.Add(new Rect(host.X + actual.X * scale, host.Y + actual.Y * scale, actual.Width * scale, actual.Height * scale));
            }
            return result;
        }
        internal int[] Boundaries(TextUnit unit) => unit switch
        {
            TextUnit.Character => owner.boundaries?.Characters ?? [0, owner.SourceText.Length],
            TextUnit.Word => owner.boundaries?.Words ?? [0, owner.SourceText.Length],
            TextUnit.Line => owner.lines.Select(line => line.Start).Prepend(0).Append(owner.SourceText.Length).Distinct().ToArray(),
            _ => [0, owner.SourceText.Length]
        };
    }

    private sealed class PathRange(NativePathPeer peer, int first, int last) : ITextRangeProvider
    {
        private int start = first, end = last;
        private NativePathText Owner => peer.TextOwner;
        private PathRange SameOwner(ITextRangeProvider candidate) => candidate is PathRange range && ReferenceEquals(range.Owner, Owner)
            ? range : throw new ArgumentException("The range belongs to another text owner", nameof(candidate));
        private int Endpoint(TextPatternRangeEndpoint endpoint) => endpoint == TextPatternRangeEndpoint.Start ? start : end;
        private void SetEndpoint(TextPatternRangeEndpoint endpoint, int value)
        {
            value = Math.Clamp(value, 0, Owner.SourceText.Length);
            if (endpoint == TextPatternRangeEndpoint.Start) { start = value; end = Math.Max(end, start); }
            else { end = value; start = Math.Min(start, end); }
        }
        public ITextRangeProvider Clone() => new PathRange(peer, start, end);
        public bool Compare(ITextRangeProvider range) => range is PathRange other && ReferenceEquals(other.Owner, Owner) && other.start == start && other.end == end;
        public int CompareEndpoints(TextPatternRangeEndpoint endpoint, ITextRangeProvider targetRange, TextPatternRangeEndpoint targetEndpoint)
            => Endpoint(endpoint).CompareTo(SameOwner(targetRange).Endpoint(targetEndpoint));
        public void ExpandToEnclosingUnit(TextUnit unit)
        {
            var points = peer.Boundaries(unit);
            var index = Math.Clamp(points.TakeWhile(p => p <= start).Count() - 1, 0, Math.Max(0, points.Length - 2));
            start = points[index]; end = points[Math.Min(index + 1, points.Length - 1)];
        }
        public ITextRangeProvider FindAttribute(int attributeId, object value, bool backward)
            => Equals(GetAttributeValue(attributeId), value) ? Clone() : null!;
        public ITextRangeProvider FindText(string text, bool backward, bool ignoreCase)
        {
            if (string.IsNullOrEmpty(text)) throw new ArgumentException("Search text must be nonempty", nameof(text));
            var comparison = ignoreCase ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
            var content = Owner.SourceText[start..end]; var index = backward ? content.LastIndexOf(text, comparison) : content.IndexOf(text, comparison);
            return index < 0 ? null! : new PathRange(peer, start + index, start + index + text.Length);
        }
        public object GetAttributeValue(int attributeId) => attributeId switch
        {
            40004 => System.Globalization.CultureInfo.GetCultureInfo(Owner.locale).LCID,
            40005 => Owner.textStyle.Family.Split(',')[0].Trim().Trim('"'), // Actual configured request, not resolved glyph faces.
            40006 => Owner.textStyle.Size * 72 / 96, // UIA FontSize is in typographic points.
            40007 => (int)Owner.textStyle.Weight,
            40008 when Owner.Foreground is SolidColorBrush brush => brush.Color.R | brush.Color.G << 8 | brush.Color.B << 16,
            40013 => !Owner.IsLoaded || peer.IsOffscreen(),
            40014 or 40016 or 40017 => false,
            40015 => true,
            // Never return a fabricated value for an unsupported attribute.
            _ => throw new NotSupportedException("The path text provider does not measure attribute " + attributeId)
        };
        public void GetBoundingRectangles(out double[] returnValue) => returnValue = peer.ScreenRanges(start, end)
            .SelectMany(rect => new[] { rect.X, rect.Y, rect.Width, rect.Height }).ToArray();
        public IRawElementProviderSimple[] GetChildren() => [];
        public IRawElementProviderSimple GetEnclosingElement() => peer.Provider;
        public string GetText(int maxLength)
        {
            if (maxLength < -1) throw new ArgumentOutOfRangeException(nameof(maxLength));
            return Owner.SourceText.Substring(start, maxLength < 0 ? end - start : Math.Min(maxLength, end - start));
        }
        public int Move(TextUnit unit, int count)
        {
            if (count == 0) return 0;
            var degenerate = start == end;
            if (!degenerate) ExpandToEnclosingUnit(unit);
            var points = peer.Boundaries(unit);
            var next = NativePathLineBreaks.Move(points, start, count, out var moved);
            if (!degenerate && next == Owner.SourceText.Length && points.Length > 1)
            {
                next = points[^2]; moved = Array.IndexOf(points, next) - Array.IndexOf(points, start);
            }
            start = end = next;
            if (!degenerate) ExpandToEnclosingUnit(unit);
            return moved;
        }
        public void MoveEndpointByRange(TextPatternRangeEndpoint endpoint, ITextRangeProvider targetRange, TextPatternRangeEndpoint targetEndpoint)
            => SetEndpoint(endpoint, SameOwner(targetRange).Endpoint(targetEndpoint));
        public int MoveEndpointByUnit(TextPatternRangeEndpoint endpoint, TextUnit unit, int count)
        {
            var value = NativePathLineBreaks.Move(peer.Boundaries(unit), Endpoint(endpoint), count, out var moved);
            SetEndpoint(endpoint, value); return moved;
        }
        public void Select() { Owner.Focus(FocusState.Programmatic); Owner.SetSelection(start, end); }
        public void AddToSelection()
        {
            if (Owner.SelectionStart != Owner.SelectionEnd && (Owner.SelectionStart != start || Owner.SelectionEnd != end))
                throw new InvalidOperationException("Path text supports one continuous selection");
            Select();
        }
        public void RemoveFromSelection()
        {
            if (Owner.SelectionStart == start && Owner.SelectionEnd == end) Owner.SetSelection(start, start);
        }
        public void ScrollIntoView(bool alignToTop)
        {
            var bounds = Owner.LocalRanges(start, end);
            if (bounds.Count == 0) return;
            Owner.StartBringIntoView(new BringIntoViewOptions { TargetRect = alignToTop ? bounds[0] : bounds[^1],
                VerticalAlignmentRatio = alignToTop ? 0 : 1, AnimationDesired = false });
        }
    }
}
