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
    }
    internal void Commit()
    {
        if (committed == revision) return;
        committed = revision;
        repeater.ItemsSource = Children.ToArray();
    }
    internal void BringLastIntoView()
    {
        BringIndexIntoView(Children.Count - 1, 1);
    }
    internal void BringIndexIntoView(int index, double alignment = .5)
    {
        if (index < 0 || index >= Children.Count) return;
        var last = repeater.GetOrCreateElement(index) as FrameworkElement;
        // Let the normal frame measure the new anchor. UpdateLayout here
        // recursively measured every dirty pane inside the chat command.
        DispatcherQueue.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low,
            () => last?.StartBringIntoView(new BringIntoViewOptions { AnimationDesired = false, VerticalAlignmentRatio = alignment }));
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
    private sealed class RowFactory : IElementFactory
    {
        private readonly Stack<Border> empty = new();
        private readonly Queue<(Border Host, Row Row)> pending = new();
        private bool pumping;
        internal static int PendingBuilds;
        internal int Realized { get; private set; }
        public UIElement GetElement(ElementFactoryGetArgs args)
        {
            var host = empty.Count > 0 ? empty.Pop() : new Border { HorizontalAlignment = HorizontalAlignment.Stretch };
            var row = (Row)args.Data;
            host.Tag = row; host.MinHeight = row.Estimate; Realized++;
            pending.Enqueue((host, row)); Interlocked.Increment(ref PendingBuilds);
            if (!pumping) { pumping = true; Pump(); }
            return host;
        }
        private async void Pump()
        {
            // A cold row can create many native controls. Build one per UI
            // turn, outside MeasureOverride, instead of concentrating the
            // entire viewport in one uninterruptible layout pass.
            while (pending.TryDequeue(out var work))
            {
                await Task.Delay(1);
                try
                {
                    if (!ReferenceEquals(work.Host.Tag, work.Row)) continue;
                    BuildNow(work.Host);
                }
                finally { Interlocked.Decrement(ref PendingBuilds); }
            }
            pumping = false;
        }
        internal void BuildNow(Border host)
        {
            if (host.Child != null || host.Tag is not Row row) return;
            using var timing = PerformanceTrace.Measure("row.build");
            host.Child = row.Build(); host.MinHeight = 0;
        }
        public void RecycleElement(ElementFactoryRecycleArgs args)
        {
            var host = (Border)args.Element;
            host.Tag = null; host.Child = null; Realized--;
            if (empty.Count < 32) empty.Push(host);
        }
    }
}
