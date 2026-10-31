using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Relic;

// The model stores factories, not XAML trees. Only viewport rows are built;
// recycling detaches the old subtree so fonts, images and subscriptions unload.
internal sealed class VirtualRows : Grid
{
    internal sealed record Row(Func<UIElement> Build, double Estimate);
    internal sealed class RowCollection(Action changed) : List<Row>
    {
        public void Add(UIElement element) => Add(() => element);
        public void Add(Func<UIElement> build, double estimate = 40) { base.Add(new Row(build, estimate)); changed(); }
        public new void Clear() { base.Clear(); changed(); }
    }
    internal new RowCollection Children { get; }
    private readonly ItemsRepeater repeater = new() { Layout = new StackLayout(), VerticalCacheLength = .5 };
    internal double Spacing { get => ((StackLayout)repeater.Layout).Spacing; set => ((StackLayout)repeater.Layout).Spacing = value; }
    internal int Realized => factory.Realized;
    internal static int PendingBuilds => RowFactory.PendingBuilds;
    internal string TraceName { get; set; } = "rows";
    private readonly RowFactory factory = new();
    private int revision, committed = -1;
    private bool commitQueued;
    private sealed record BringRequest(int Revision, int Index, FrameworkElement Element,
        double Alignment, double Offset, Func<bool>? IsCurrent, long AfterArrange);
    private BringRequest? pendingBring;
    private long arrangeRevision;
    private bool bringQueued;
    private readonly record struct EndGeometry(int Index, FrameworkElement? Element, double Offset, double Extent,
        double ViewportWidth, double ViewportHeight, double RowTop, double RowWidth, double RowHeight);
    private readonly record struct PreparedEnd(int Index, double ViewportWidth, double ViewportHeight,
        double RowWidth, double RowHeight, double ContentBottom);
    private sealed class FollowRequest(int revision, ScrollViewer viewport, Func<bool> isCurrent, Func<bool> isContentReady)
    {
        internal readonly int Revision = revision;
        internal readonly ScrollViewer Viewport = viewport;
        internal readonly Func<bool> IsCurrent = isCurrent;
        internal readonly Func<bool> IsContentReady = isContentReady;
        internal PreparedEnd? LastCorrected;
        internal double ViewportWidth = viewport.ViewportWidth, ViewportHeight = viewport.ViewportHeight;
        internal UIElement? LastAnchor;
        internal bool Settled, IsScrolling, RecoveryRequested;
    }
    private FollowRequest? followingLast;
    private bool followQueued;
    private int readinessQueued;
    private readonly Microsoft.UI.Dispatching.DispatcherQueue dispatcher;
    internal VirtualRows()
    {
        dispatcher = DispatcherQueue;
        Children = new(() =>
        {
            revision++;
            if (commitQueued) return;
            commitQueued = true;
            DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () => { commitQueued = false; Commit(); });
        });
        repeater.ItemTemplate = factory;
        base.Children.Add(repeater);
        Unloaded += (_, _) => StopFollowingLast();
    }
    internal void Commit()
    {
        if (committed == revision) return;
        using var timing = PerformanceTrace.Measure("rows.commit");
        committed = revision;
        StopFollowingLast();
        repeater.ItemsSource = Children.ToArray();
    }
    internal void FollowLastIntoView(ScrollViewer viewport, Func<bool> isCurrent, Func<bool> isContentReady)
    {
        Commit();
        StopFollowingLast();
        if (Children.Count == 0 || !isCurrent()) return;
        followingLast = new(committed, viewport, isCurrent, isContentReady);
        viewport.AnchorRequested += FollowAnchorRequested;
        viewport.ViewChanged += FollowViewChanged;
        viewport.SizeChanged += FollowViewportSizeChanged;
        PresentationPreparation.Completed += FollowPreparationCompleted;
        BringIndexIntoViewCore(Children.Count - 1, 1, -Padding.Bottom, isCurrent);
    }
    internal void StopFollowingLast()
    {
        pendingBring = null;
        if (followingLast is not { } follow) return;
        followingLast = null;
        follow.Viewport.AnchorRequested -= FollowAnchorRequested;
        follow.Viewport.ViewChanged -= FollowViewChanged;
        follow.Viewport.SizeChanged -= FollowViewportSizeChanged;
        PresentationPreparation.Completed -= FollowPreparationCompleted;
    }
    private void FollowPreparationCompleted()
    {
        // Completion may arrive on a worker, including canceled requests whose
        // old visual tree is gone. Coalesce onto the captured UI dispatcher.
        if (Interlocked.Exchange(ref readinessQueued, 1) != 0) return;
        if (!dispatcher.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Normal, () =>
        {
            Interlocked.Exchange(ref readinessQueued, 0);
            if (followingLast is not { } follow) return;
            if (!IsCurrent(follow)) { StopFollowingLast(); return; }
            if (!follow.IsContentReady()) return;
            // A decrement alone need not invalidate this chat. Request exactly
            // one real Arrange before checking its now-completed geometry.
            InvalidateArrange();
        })) Interlocked.Exchange(ref readinessQueued, 0);
    }
    private bool IsCurrent(FollowRequest follow) => ReferenceEquals(followingLast, follow)
        && follow.Revision == revision && follow.IsCurrent() && Children.Count > 0;
    private void FollowAnchorRequested(ScrollViewer sender, AnchorRequestedEventArgs args)
    {
        if (followingLast is not { } follow || !IsCurrent(follow)) { QueueFollowCheck(); return; }
        // An off-viewport anchor disturbs StackLayout's realization range and
        // can repeatedly recycle/rebuild the very row being followed. Only
        // preserve the real last row while it actually intersects this viewport.
        // Never create/measure an element from inside Arrange.
        if (repeater.TryGetElement(Children.Count - 1) is FrameworkElement { IsLoaded: true, ActualHeight: > 0 } last)
        {
            var bounds = last.TransformToVisual(sender).TransformBounds(new(0, 0, last.ActualWidth, last.ActualHeight));
            if (bounds.Top >= sender.ViewportHeight || bounds.Bottom <= 0) return;
            args.Anchor = last;
            if (!ReferenceEquals(follow.LastAnchor, last))
            { follow.LastAnchor = last; PerformanceTrace.Count(TraceName + ".follow.anchor", Children.Count - 1); }
        }
        else QueueFollowCheck();
    }
    private void FollowViewChanged(object? sender, ScrollViewerViewChangedEventArgs args)
    {
        if (followingLast is { } follow) follow.IsScrolling = args.IsIntermediate;
        if (!args.IsIntermediate) QueueFollowCheck();
    }
    private void FollowViewportSizeChanged(object sender, SizeChangedEventArgs args) => QueueFollowCheck();
    private EndGeometry ReadEndGeometry(FollowRequest follow)
    {
        var viewport = follow.Viewport; var index = Children.Count - 1;
        var last = repeater.TryGetElement(index) as FrameworkElement;
        if (last is not { IsLoaded: true }) last = null;
        var bounds = last?.TransformToVisual(viewport).TransformBounds(new(0, 0, last.ActualWidth, last.ActualHeight));
        return new(index, last, viewport.VerticalOffset, viewport.ScrollableHeight, viewport.ViewportWidth,
            viewport.ViewportHeight, bounds?.Top ?? 0, bounds?.Width ?? 0, bounds?.Height ?? 0);
    }
    private void QueueFollowCheck()
    {
        if (followingLast == null || followQueued) return;
        followQueued = true;
        if (!DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Normal, () =>
        {
            followQueued = false;
            if (followingLast is not { } follow) return;
            if (!IsCurrent(follow)) { StopFollowingLast(); return; }
            if (pendingBring != null || follow.IsScrolling || !follow.IsContentReady()) return;
            var geometry = ReadEndGeometry(follow);
            if (follow.ViewportWidth != geometry.ViewportWidth || follow.ViewportHeight != geometry.ViewportHeight)
            {
                follow.ViewportWidth = geometry.ViewportWidth; follow.ViewportHeight = geometry.ViewportHeight;
                follow.LastCorrected = null; follow.RecoveryRequested = false;
            }
            var atEnd = Math.Abs(geometry.Extent - geometry.Offset) <= 1 && geometry.Element != null
                && geometry.RowHeight > 0 && geometry.RowTop < geometry.ViewportHeight
                && geometry.RowTop + geometry.RowHeight > 0;
            if (atEnd)
            {
                if (!follow.Settled) PerformanceTrace.Count(TraceName + ".follow.settled", geometry.Index);
                follow.Settled = true;
                return;
            }
            // Only completed content/viewport geometry permits a correction.
            // Offset, estimated extent and recycled host identity are NOT new
            // content: scrolling changes those values itself, so using them as
            // repair triggers creates a self-sustaining realization loop.
            if (geometry.Element == null || geometry.RowHeight <= 0)
            {
                if (follow.RecoveryRequested) return;
                follow.RecoveryRequested = true;
            }
            else
            {
                var prepared = new PreparedEnd(geometry.Index, geometry.ViewportWidth, geometry.ViewportHeight,
                    geometry.RowWidth, geometry.RowHeight,
                    Math.Round((geometry.RowTop + geometry.RowHeight + geometry.Offset) * 64) / 64);
                // Content-space position also changes when an earlier message
                // finishes layout but this final row keeps the same size. Pure
                // scrolling changes RowTop and Offset in opposite directions.
                if (follow.LastCorrected == prepared) return;
                follow.LastCorrected = prepared;
            }
            follow.Settled = false;
            PerformanceTrace.Count(TraceName + ".follow.repair", geometry.Index);
            PerformanceTrace.Count(TraceName + ".follow.gap", geometry.Extent - geometry.Offset);
            BringIndexIntoViewCore(geometry.Index, 1, -Padding.Bottom, follow.IsCurrent);
        })) followQueued = false;
    }
    internal void BringLastIntoView(Func<bool>? isCurrent = null)
    {
        // Align the last row above the content's real bottom padding. Let the
        // ScrollViewer's bottom anchor preserve it as deferred rows settle;
        // repeated ChangeView(maximum) fights virtual extent estimation.
        BringIndexIntoView(Children.Count - 1, 1, -Padding.Bottom, isCurrent);
    }
    internal void BringIndexIntoView(int index, double alignment = .5, double offset = 0, Func<bool>? isCurrent = null)
    {
        StopFollowingLast();
        BringIndexIntoViewCore(index, alignment, offset, isCurrent);
    }
    private void BringIndexIntoViewCore(int index, double alignment, double offset, Func<bool>? isCurrent)
    {
        if (index < 0 || index >= Children.Count || isCurrent?.Invoke() == false) return;
        Commit();
        // GetOrCreateElement also resets the layout's suggested anchor even
        // when a row already exists. Reuse the real row for a size correction;
        // only a genuinely missing row needs new realization.
        var element = (FrameworkElement)(repeater.TryGetElement(index) ?? repeater.GetOrCreateElement(index));
        // GetOrCreateElement only suggests an anchor for the NEXT layout pass.
        // A dispatcher callback (even Low priority) can run before that pass,
        // when a distant row still has no position. Wait for actual Arrange,
        // without forcing the whole window through synchronous UpdateLayout.
        pendingBring = new(committed, index, element, alignment, offset, isCurrent, arrangeRevision);
        PerformanceTrace.Count(TraceName + ".bring.request", index);
        InvalidateArrange();
    }
    private void QueueArrangedBring()
    {
        if (bringQueued || pendingBring is not { } request || arrangeRevision <= request.AfterArrange) return;
        bringQueued = true;
        if (!DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Normal, () =>
        {
            bringQueued = false;
            if (!ReferenceEquals(pendingBring, request)) { QueueArrangedBring(); return; }
            if (request.Revision != revision || request.IsCurrent?.Invoke() == false)
            { pendingBring = null; return; }
            // Never scroll a recycled host that now belongs to another row.
            if (!ReferenceEquals(repeater.TryGetElement(request.Index), request.Element)
                || repeater.GetElementIndex(request.Element) != request.Index)
            {
                BringIndexIntoViewCore(request.Index, request.Alignment, request.Offset, request.IsCurrent);
                return;
            }
            if (!request.Element.IsLoaded || request.Element.ActualWidth <= 0 || request.Element.ActualHeight <= 0) return;
            pendingBring = null;
            PerformanceTrace.Count(TraceName + ".bring.arranged", request.Index);
            request.Element.StartBringIntoView(new BringIntoViewOptions
            { AnimationDesired = false, VerticalAlignmentRatio = request.Alignment, VerticalOffset = request.Offset });
        })) bringQueued = false;
    }
    internal bool MoveFocus(UIElement source, int delta, Func<UIElement, Control?> focusTarget)
    {
        DependencyObject? container = source;
        while (container != null && !ReferenceEquals(Microsoft.UI.Xaml.Media.VisualTreeHelper.GetParent(container), repeater))
            container = Microsoft.UI.Xaml.Media.VisualTreeHelper.GetParent(container);
        if (container is not UIElement current || delta == 0) return false;
        var index = repeater.GetElementIndex(current);
        for (index += Math.Sign(delta); index >= 0 && index < Children.Count; index += Math.Sign(delta))
        {
            var element = repeater.GetOrCreateElement(index);
            factory.BuildNow((Border)element);
            if (focusTarget(element) is not { IsEnabled: true } target) continue;
            target.StartBringIntoView(new BringIntoViewOptions { AnimationDesired = false });
            return target.Focus(FocusState.Keyboard);
        }
        return false;
    }
    protected override Windows.Foundation.Size MeasureOverride(Windows.Foundation.Size availableSize)
    {
        using var timing = PerformanceTrace.Measure(TraceName + ".measure");
        var result = base.MeasureOverride(availableSize);
        PerformanceTrace.Count(TraceName + ".realized", Realized);
        return result;
    }
    protected override Windows.Foundation.Size ArrangeOverride(Windows.Foundation.Size finalSize)
    {
        using var timing = PerformanceTrace.Measure(TraceName + ".arrange");
        var result = base.ArrangeOverride(finalSize);
        arrangeRevision++;
        QueueArrangedBring();
        QueueFollowCheck();
        return result;
    }
    private sealed class RowFactory : IElementFactory
    {
        private readonly Stack<Border> empty = new();
        private static readonly Queue<(RowFactory Owner, Border Host, Row Row)> pending = new();
        private static Microsoft.UI.Dispatching.DispatcherQueueTimer? pumpTimer;
        internal static int PendingBuilds;
        internal int Realized { get; private set; }
        public UIElement GetElement(ElementFactoryGetArgs args)
        {
            var host = empty.Count > 0 ? empty.Pop() : new Border { HorizontalAlignment = HorizontalAlignment.Stretch };
            var row = (Row)args.Data;
            host.Tag = row; host.MinHeight = row.Estimate; Realized++;
            pending.Enqueue((this, host, row)); Interlocked.Increment(ref PendingBuilds);
            if (pumpTimer == null)
            {
                pumpTimer = host.DispatcherQueue.CreateTimer();
                pumpTimer.Interval = TimeSpan.FromMilliseconds(16); pumpTimer.IsRepeating = true;
                pumpTimer.Tick += (_, _) => Pump();
            }
            if (!pumpTimer.IsRunning) pumpTimer.Start();
            return host;
        }
        private static void Pump()
        {
            // A cold row can create many native controls. Build one per UI
            // turn, outside MeasureOverride, instead of concentrating the
            // entire viewport in one uninterruptible layout pass.
            while (pending.TryDequeue(out var work))
            {
                try
                {
                    if (!ReferenceEquals(work.Host.Tag, work.Row)) continue;
                    // The UI-owned timer guarantees native control creation
                    // stays on the dispatcher even when realization originated
                    // in a native callback without a managed sync context.
                    work.Owner.BuildNow(work.Host);
                }
                finally { Interlocked.Decrement(ref PendingBuilds); PresentationPreparation.NotifyCompletion(); }
                break;
            }
            if (pending.Count == 0) pumpTimer!.Stop();
        }
        internal void BuildNow(Border host)
        {
            if (host.Child != null || host.Tag is not Row row) return;
            using var timing = PerformanceTrace.Measure("row.build");
            host.Child = row.Build(); host.MinHeight = 0;
        }
        public void RecycleElement(ElementFactoryRecycleArgs args)
        {
            using var timing = PerformanceTrace.Measure("row.recycle");
            var host = (Border)args.Element;
            host.Tag = null; host.Child = null; Realized--;
            if (empty.Count < 32) empty.Push(host);
        }
    }
}
