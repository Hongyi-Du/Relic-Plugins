using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Relic;

// The model stores factories, not XAML trees. Only viewport rows are built;
// recycling detaches the old subtree so fonts, images and subscriptions unload.
internal sealed class VirtualRows : Grid
{
    internal sealed class RowCollection(Action changed) : List<Func<UIElement>>
    {
        public void Add(UIElement element) => Add(() => element);
        public new void Add(Func<UIElement> build) { base.Add(build); changed(); }
        public new void Clear() { base.Clear(); changed(); }
    }
    internal new RowCollection Children { get; }
    private readonly ItemsRepeater repeater = new() { Layout = new StackLayout(), VerticalCacheLength = .5 };
    internal double Spacing { get => ((StackLayout)repeater.Layout).Spacing; set => ((StackLayout)repeater.Layout).Spacing = value; }
    internal int Realized => factory.Realized;
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
    private sealed record Row(Func<UIElement> Build);
    internal void Commit()
    {
        if (committed == revision) return;
        committed = revision;
        repeater.ItemsSource = Children.Select(build => new Row(build)).ToArray();
    }
    internal void BringLastIntoView()
    {
        if (Children.Count == 0) return;
        var last = repeater.GetOrCreateElement(Children.Count - 1) as FrameworkElement;
        UpdateLayout();
        last?.StartBringIntoView(new BringIntoViewOptions { AnimationDesired = false, VerticalAlignmentRatio = 1 });
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
        internal int Realized { get; private set; }
        public UIElement GetElement(ElementFactoryGetArgs args)
        {
            using var timing = PerformanceTrace.Measure("row.build");
            var host = empty.Count > 0 ? empty.Pop() : new Border { HorizontalAlignment = HorizontalAlignment.Stretch };
            host.Child = ((Row)args.Data).Build(); Realized++;
            return host;
        }
        public void RecycleElement(ElementFactoryRecycleArgs args)
        {
            var host = (Border)args.Element;
            host.Child = null; Realized--;
            if (empty.Count < 32) empty.Push(host);
        }
    }
}
