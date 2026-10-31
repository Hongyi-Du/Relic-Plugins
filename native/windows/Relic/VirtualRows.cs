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
    internal VirtualRows()
    {
        Children = new(() =>
        {
            revision++;
            if (commitQueued) return;
            commitQueued = true;
            DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () => { commitQueued = false; Commit(); });
        });
        repeater.ItemTemplate = factory;
        base.Children.Add(repeater);
        Unloaded += (_, _) => pendingBring = null;
    }
    internal void Commit()
    {
        if (committed == revision) return;
        using var timing = PerformanceTrace.Measure("rows.commit");
        committed = revision;
        pendingBring = null;
        repeater.ItemsSource = Children.ToArray();
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
        if (index < 0 || index >= Children.Count || isCurrent?.Invoke() == false) return;
        Commit();
        var element = (FrameworkElement)repeater.GetOrCreateElement(index);
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
                BringIndexIntoView(request.Index, request.Alignment, request.Offset, request.IsCurrent);
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
                finally { Interlocked.Decrement(ref PendingBuilds); }
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
