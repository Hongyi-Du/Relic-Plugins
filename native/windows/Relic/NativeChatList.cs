using System.Collections.ObjectModel;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace Relic;

// The ListView owns both virtualization and its one native scrolling viewport.
// Row factories remain data until a real ListView container enters that viewport.
internal sealed class NativeChatList : Grid
{
    private sealed class Entry(VirtualRows.Row row, string? identity)
    {
        internal VirtualRows.Row Row = row;
        internal string? Identity = identity;
        internal int Version;
    }
    private sealed record Mounted(Entry Entry, int Version);
    private sealed record BuildWork(Border Host, Entry Entry, int Version);
    private enum PositionKind { Latest, Reading, First }
    private sealed class Position(PositionKind kind, string? key, double top,
        Func<bool> isCurrent, Func<bool> isReady, string view, long inputGeneration)
    {
        internal readonly PositionKind Kind = kind;
        internal readonly string? Key = key;
        internal readonly double Top = top;
        internal readonly Func<bool> IsCurrent = isCurrent, IsReady = isReady;
        internal readonly string View = view;
        internal readonly long InputGeneration = inputGeneration;
        internal readonly TaskCompletionSource<bool> Completion = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal Entry? RequestedEntry;
        internal int Corrections;
        internal bool Settled;
        internal bool CorrectionPending, CorrectionCompleted;
        internal (double Width, double Height, double RowWidth, double RowHeight, double ContentTop)? LastGeometry;
    }

    private readonly ListView list = new()
    {
        SelectionMode = ListViewSelectionMode.None, IsItemClickEnabled = false,
        HorizontalAlignment = HorizontalAlignment.Stretch, VerticalAlignment = VerticalAlignment.Stretch,
        HorizontalContentAlignment = HorizontalAlignment.Stretch,
        Padding = new Thickness(0), BorderThickness = new Thickness(0), UseLayoutRounding = false,
        IsTabStop = false
    };
    private readonly ObservableCollection<Entry> entries = [];
    private readonly Dictionary<Border, Mounted> mounted = [];
    private readonly Dictionary<string, string> identities = [];
    private readonly Queue<BuildWork> builds = [];
    private readonly DispatcherTimer pump = new() { Interval = TimeSpan.FromMilliseconds(16) };
    private readonly Microsoft.UI.Dispatching.DispatcherQueue dispatcher;
    private Position? position;
    private int revision, committed = -1, completionQueued;
    private bool commitQueued, checkQueued, listening;
    private string committedView = "";
    private string committedPresentationContext = "";
    private double spacing;
    private Thickness contentPadding;
    private double contentMaxWidth = 920;
    private static int pendingBuilds;

    internal new VirtualRows.RowCollection Children { get; }
    internal event Action? ItemsReplacing;
    internal event Action<ScrollViewer>? ViewportReady;
    internal ScrollViewer? Viewport { get; private set; }
    internal string ViewIdentity { get; set; } = "";
    internal string PresentationContext { get; set; } = "";
    internal string TraceName { get; set; } = "conversation";
    internal int Realized => mounted.Count;
    internal static int PendingBuilds => Volatile.Read(ref pendingBuilds);
    internal bool ReadingAnchorRestorePending => position is { Kind: PositionKind.Reading or PositionKind.First };
    internal Func<long> CaptureSeekInputGeneration { get; set; } = static () => 0;
    internal long? PendingSeekInputGeneration => position is { } intent && intent.IsCurrent()
        && intent.View == ViewIdentity && !(intent.Kind == PositionKind.Latest && IsLastPositionSettled)
        ? intent.InputGeneration : null;
    internal Thickness ContentPadding
    {
        get => contentPadding;
        set { contentPadding = value; ConfigurePresenter(); }
    }
    internal double ContentMaxWidth
    {
        get => contentMaxWidth;
        set { contentMaxWidth = value; ConfigurePresenter(); }
    }
    internal double Spacing
    {
        get => spacing;
        set
        {
            spacing = value;
            foreach (var host in mounted.Keys) host.Margin = new Thickness(0, 0, 0, spacing);
        }
    }

    internal NativeChatList()
    {
        dispatcher = DispatcherQueue;
        Children = new(() =>
        {
            revision++;
            if (commitQueued) return;
            commitQueued = true;
            dispatcher.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () =>
            { commitQueued = false; Commit(); });
        });
        list.ItemTemplate = XamlTemplates.Load<DataTemplate>(
            "<DataTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation'>" +
            "<Border HorizontalAlignment='Stretch' UseLayoutRounding='False'/></DataTemplate>");
        list.ItemsPanel = XamlTemplates.Load<ItemsPanelTemplate>(
            "<ItemsPanelTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation'>" +
            "<ItemsStackPanel ItemsUpdatingScrollMode='KeepItemsInView' CacheLength='0.5'/></ItemsPanelTemplate>");
        var itemStyle = new Style(typeof(ListViewItem));
        itemStyle.Setters.Add(new Setter(Control.PaddingProperty, new Thickness(0)));
        itemStyle.Setters.Add(new Setter(FrameworkElement.MinHeightProperty, 0d));
        itemStyle.Setters.Add(new Setter(Control.HorizontalContentAlignmentProperty, HorizontalAlignment.Stretch));
        itemStyle.Setters.Add(new Setter(Control.VerticalContentAlignmentProperty, VerticalAlignment.Top));
        itemStyle.Setters.Add(new Setter(UIElement.IsTabStopProperty, false));
        list.ItemContainerStyle = itemStyle;
        foreach (var key in new[] { "ListViewItemBackground", "ListViewItemBackgroundPointerOver", "ListViewItemBackgroundPressed" })
            list.Resources[key] = new SolidColorBrush(Microsoft.UI.Colors.Transparent);
        ScrollViewer.SetHorizontalScrollMode(list, ScrollMode.Disabled);
        ScrollViewer.SetHorizontalScrollBarVisibility(list, ScrollBarVisibility.Disabled);
        ScrollViewer.SetVerticalScrollBarVisibility(list, ScrollBarVisibility.Auto);
        list.ItemsSource = entries;
        list.ContainerContentChanging += ContainerChanging;
        list.Loaded += (_, _) => BindViewport();
        list.LayoutUpdated += (_, _) => { if (position != null) QueuePositionCheck(); };
        base.Children.Add(list);
        pump.Tick += (_, _) => BuildNext();
        Loaded += (_, _) =>
        {
            if (!listening) { PresentationPreparation.Completed += PreparationCompleted; listening = true; }
            BindViewport();
        };
        Unloaded += (_, _) =>
        {
            StopFollowingLast();
            if (listening) { PresentationPreparation.Completed -= PreparationCompleted; listening = false; }
            pump.Stop();
            while (builds.TryDequeue(out _)) Interlocked.Decrement(ref pendingBuilds);
            foreach (var host in mounted.Keys.ToArray()) Release(host);
        };
    }

    private static T? Find<T>(DependencyObject root) where T : DependencyObject
    {
        if (root is T match) return match;
        for (var index = 0; index < VisualTreeHelper.GetChildrenCount(root); index++)
            if (Find<T>(VisualTreeHelper.GetChild(root, index)) is { } child) return child;
        return null;
    }

    private void BindViewport()
    {
        ConfigurePresenter();
        var viewport = Find<ScrollViewer>(list);
        if (viewport == null || ReferenceEquals(viewport, Viewport)) return;
        if (Viewport != null)
        {
            Viewport.ViewChanged -= ViewChanged;
            Viewport.SizeChanged -= ViewSizeChanged;
        }
        Viewport = viewport; viewport.IsTabStop = true;
        viewport.ViewChanged += ViewChanged; viewport.SizeChanged += ViewSizeChanged;
        ViewportReady?.Invoke(viewport);
        QueuePositionCheck();
    }

    private void ConfigurePresenter()
    {
        if (Find<ItemsPresenter>(list) is not { } presenter) return;
        presenter.Padding = contentPadding; presenter.MaxWidth = contentMaxWidth;
        presenter.HorizontalAlignment = HorizontalAlignment.Center;
    }

    // Optional per-draw identity: unchanged content can keep its actual subtree.
    // The caller owns semantic versions; factory delegate identity is not a diff.
    internal void SetPresentationIdentity(string key, string identity) => identities[key] = identity;

    internal void Commit()
    {
        if (committed == revision && committedView == ViewIdentity && committedPresentationContext == PresentationContext) return;
        using var timing = PerformanceTrace.Measure("conversation.list.commit");
        ItemsReplacing?.Invoke();
        var sameView = committedView == ViewIdentity;
        var samePresentation = committedPresentationContext == PresentationContext;
        if (!sameView) StopFollowingLast();
        Dictionary<string, Entry> previous = sameView ? entries.Where(entry => entry.Row.Key != null)
            .GroupBy(entry => entry.Row.Key!).ToDictionary(group => group.Key, group => group.First()) : [];
        var next = new List<Entry>(Children.Count);
        var changed = new HashSet<Entry>();
        foreach (var row in Children)
        {
            var identity = row.Key != null && identities.TryGetValue(row.Key, out var value) ? value : null;
            if (row.Key != null && previous.Remove(row.Key, out var retained))
            {
                var unchanged = samePresentation && identity != null && retained.Identity == identity;
                retained.Row = row; retained.Identity = identity;
                if (!unchanged) { retained.Version++; changed.Add(retained); }
                next.Add(retained);
            }
            else next.Add(new Entry(row, identity));
        }
        identities.Clear();
        committed = revision; committedView = ViewIdentity; committedPresentationContext = PresentationContext;
        if (!sameView) entries.Clear();
        var wanted = next.ToHashSet();
        for (var index = entries.Count - 1; index >= 0; index--)
            if (!wanted.Contains(entries[index])) entries.RemoveAt(index);
        var existing = entries.ToHashSet();
        for (var index = 0; index < next.Count; index++)
        {
            var entry = next[index];
            if (index < entries.Count && ReferenceEquals(entries[index], entry)) continue;
            if (existing.Contains(entry)) entries.Move(entries.IndexOf(entry), index);
            else { entries.Insert(index, entry); existing.Add(entry); }
        }
        foreach (var (host, binding) in mounted.ToArray())
        {
            if (!wanted.Contains(binding.Entry)) { Release(host); continue; }
            host.Tag = binding.Entry.Row;
            if (changed.Contains(binding.Entry)) QueueBuild(host, binding.Entry);
        }
        ConfigurePresenter(); QueuePositionCheck();
    }

    private void ContainerChanging(ListViewBase sender, ContainerContentChangingEventArgs args)
    {
        if (args.ItemContainer.ContentTemplateRoot is not Border host)
        {
            if (!args.InRecycleQueue && args.Phase == 0) args.RegisterUpdateCallback(ContainerChanging);
            return;
        }
        args.Handled = true;
        if (args.InRecycleQueue) { Release(host); return; }
        if (args.Item is not Entry entry) return;
        QueueBuild(host, entry);
    }

    private void QueueBuild(Border host, Entry entry)
    {
        if (mounted.TryGetValue(host, out var old) && ReferenceEquals(old.Entry, entry) && old.Version == entry.Version) return;
        if (!mounted.ContainsKey(host)) host.SizeChanged += HostSizeChanged;
        mounted[host] = new(entry, entry.Version);
        host.Child = null; host.Tag = entry.Row; host.MinHeight = entry.Row.Estimate;
        host.Margin = new Thickness(0, 0, 0, spacing);
        builds.Enqueue(new(host, entry, entry.Version)); Interlocked.Increment(ref pendingBuilds);
        if (!pump.IsEnabled) pump.Start();
    }

    private void Release(Border host)
    {
        mounted.Remove(host); host.SizeChanged -= HostSizeChanged;
        host.Tag = null; host.Child = null;
    }

    private void BuildNext()
    {
        var started = System.Diagnostics.Stopwatch.GetTimestamp();
        var built = 0;
        while (builds.TryDequeue(out var work))
        {
            var valid = mounted.TryGetValue(work.Host, out var binding)
                && ReferenceEquals(binding.Entry, work.Entry) && binding.Version == work.Version;
            try
            {
                if (!valid) continue;
                using var timing = PerformanceTrace.Measure("conversation.list.row.build");
                work.Host.Child = work.Entry.Row.Build(); work.Host.MinHeight = 0;
                built++;
            }
            finally { Interlocked.Decrement(ref pendingBuilds); PresentationPreparation.NotifyCompletion(); }
            // Bound both elapsed construction and count. Cheap event rows do
            // not each need an entire frame; rich rows retain an input yield.
            // A 12 ms budget still leaves each frame far below the 250 ms limit,
            // and the visible tail of a chat is built in one or two frames.
            if (built >= 8 || System.Diagnostics.Stopwatch.GetElapsedTime(started).TotalMilliseconds >= 12) break;
        }
        if (builds.Count == 0) pump.Stop();
        QueuePositionCheck();
    }

    internal Border? TryGetRealizedRow(int index)
    {
        if (index < 0 || index >= entries.Count) return null;
        return (list.ContainerFromIndex(index) as ListViewItem)?.ContentTemplateRoot as Border;
    }

    internal VirtualRows.ReadingAnchor? ReadVisibleAnchor(ScrollViewer viewport)
    {
        VirtualRows.ReadingAnchor? first = null;
        foreach (var (host, binding) in mounted)
        {
            if (binding.Entry.Row.Key is not { } key || !ReadyHost(host)) continue;
            // Paging controls and date separators may disappear when older
            // data arrives. Preserve a real timeline item the person reads.
            if (!key.StartsWith("message:", StringComparison.Ordinal)
                && !key.StartsWith("item:", StringComparison.Ordinal)
                && !key.StartsWith("transcript:", StringComparison.Ordinal)) continue;
            var bounds = Bounds(host, viewport);
            if (bounds.Bottom <= 0 || bounds.Top >= viewport.ViewportHeight) continue;
            if (first == null || bounds.Top < first.ViewportTop) first = new(key, bounds.Top);
        }
        return first;
    }

    internal VirtualRows.ReadingAnchor? ReadAnchor(ScrollViewer viewport, string key)
    {
        var index = entries.ToList().FindIndex(entry => entry.Row.Key == key);
        var host = TryGetRealizedRow(index);
        if (host == null || !ReadyHost(host)) return null;
        var bounds = Bounds(host, viewport);
        return bounds.Bottom > 0 && bounds.Top < viewport.ViewportHeight ? new(key, bounds.Top) : null;
    }

    private static bool ReadyHost(Border host) => host is { IsLoaded: true, Child: not null, ActualHeight: > 0, ActualWidth: > 0 };
    private static Windows.Foundation.Rect Bounds(FrameworkElement host, ScrollViewer viewport) =>
        host.TransformToVisual(viewport).TransformBounds(new(0, 0, host.ActualWidth, host.ActualHeight));

    internal void FollowLastIntoView(ScrollViewer viewport, Func<bool> isCurrent, Func<bool> isContentReady)
        => StartPosition(PositionKind.Latest, null, 0, isCurrent, isContentReady);

    internal Task<bool> RestoreReadingAnchorAsync(VirtualRows.ReadingAnchor anchor, ScrollViewer viewport,
        Func<bool> isCurrent, Func<bool> isContentReady)
        => StartPosition(PositionKind.Reading, anchor.Key, anchor.ViewportTop, isCurrent, isContentReady);

    internal Task<bool> RestoreFirstIntoViewAsync(ScrollViewer viewport, Func<bool> isCurrent, Func<bool> isContentReady)
        => StartPosition(PositionKind.First, null, contentPadding.Top, isCurrent, isContentReady);

    private Task<bool> StartPosition(PositionKind kind, string? key, double top, Func<bool> isCurrent, Func<bool> isReady)
    {
        Commit(); StopFollowingLast();
        if (entries.Count == 0 || !isCurrent()) return Task.FromResult(false);
        position = new(kind, key, top, isCurrent, isReady, ViewIdentity, CaptureSeekInputGeneration());
        if (list.ItemsPanelRoot is ItemsStackPanel panel)
            panel.ItemsUpdatingScrollMode = kind == PositionKind.Latest ? ItemsUpdatingScrollMode.KeepLastItemInView : ItemsUpdatingScrollMode.KeepItemsInView;
        QueuePositionCheck();
        return position.Completion.Task;
    }

    internal void StopFollowingLast()
    {
        position?.Completion.TrySetResult(false); position = null;
        if (list.ItemsPanelRoot is ItemsStackPanel panel) panel.ItemsUpdatingScrollMode = ItemsUpdatingScrollMode.KeepItemsInView;
    }

    private void HostSizeChanged(object sender, SizeChangedEventArgs args) => QueuePositionCheck();
    private void ViewChanged(object? sender, ScrollViewerViewChangedEventArgs args)
    {
        if (args.IsIntermediate) return;
        if (position is { CorrectionPending: true } intent)
        {
            intent.CorrectionPending = false;
            intent.CorrectionCompleted = true;
        }
        QueuePositionCheck();
    }
    private void ViewSizeChanged(object sender, SizeChangedEventArgs args)
    {
        if (position is { Kind: PositionKind.Latest } follow) { follow.Corrections = 0; follow.LastGeometry = null; follow.Settled = false; }
        QueuePositionCheck();
    }
    private void PreparationCompleted()
    {
        if (Interlocked.Exchange(ref completionQueued, 1) != 0) return;
        if (!dispatcher.TryEnqueue(() => { Interlocked.Exchange(ref completionQueued, 0); QueuePositionCheck(); }))
            Interlocked.Exchange(ref completionQueued, 0);
    }
    private void QueuePositionCheck()
    {
        if (position == null || checkQueued) return;
        checkQueued = true;
        if (!dispatcher.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () =>
            { checkQueued = false; CheckPosition(); })) checkQueued = false;
    }

    // CI-only evidence of how a position intent ended; Count is a no-op otherwise.
    private void TracePosition(Position intent, string step) =>
        PerformanceTrace.Count(TraceName + ".position." + intent.Kind.ToString().ToLowerInvariant() + "." + step, intent.Corrections);

    private void CheckPosition()
    {
        if (position is not { } intent || Viewport is not { } viewport) return;
        if (!intent.IsCurrent() || intent.View != ViewIdentity) { TracePosition(intent, "stale"); StopFollowingLast(); return; }
        var index = intent.Kind == PositionKind.Latest ? entries.Count - 1
            : intent.Kind == PositionKind.First ? 0 : entries.ToList().FindIndex(entry => entry.Row.Key == intent.Key);
        if (index < 0 || index >= entries.Count) { StopFollowingLast(); return; }
        var entry = entries[index];
        if (!ReferenceEquals(intent.RequestedEntry, entry))
        {
            // ItemsSource changes are not yet reflected in the native panel
            // merely because the observable collection accepted them. WinUI
            // requires current layout before ScrollIntoView after a batch of
            // insertions. Otherwise it can silently leave the old offset and
            // never realize the requested reading row. Update only once for
            // this new target; the ListView still virtualizes its containers.
            // https://learn.microsoft.com/windows/windows-app-sdk/api/winrt/microsoft.ui.xaml.controls.listviewbase.scrollintoview
            using (PerformanceTrace.Measure("conversation.list.layout_before_seek")) list.UpdateLayout();
            if (!ReferenceEquals(position, intent) || !intent.IsCurrent()) return;
            intent.RequestedEntry = entry; intent.Corrections = 0; intent.LastGeometry = null; intent.Settled = false;
            intent.CorrectionPending = false; intent.CorrectionCompleted = false;
            // The platform realizes the target; this does not construct or
            // manually position an off-viewport item in an ItemsRepeater.
            var existing = TryGetRealizedRow(index);
            var existingBounds = existing is { IsLoaded: true } ? Bounds(existing, viewport) : default;
            if (existing == null || existingBounds.Bottom <= 0 || existingBounds.Top >= viewport.ViewportHeight)
            {
                TracePosition(intent, "seek");
                list.ScrollIntoView(entry, intent.Kind == PositionKind.Latest ? ScrollIntoViewAlignment.Default : ScrollIntoViewAlignment.Leading);
                return;
            }
        }
        // LayoutUpdated can repeat while ChangeView is still in flight. Only
        // its final ViewChanged permits evaluating that correction's result.
        if (intent.CorrectionPending) return;
        // This check runs at low priority and can come before the layout pass
        // that applies rows built since the last one. Judging the anchor from
        // their old estimated heights settled it early and let it drift. Bring
        // layout up to date first; the next frame would do the same work.
        using (PerformanceTrace.Measure(TraceName + ".list.layout_before_check")) list.UpdateLayout();
        if (!ReferenceEquals(position, intent) || !intent.IsCurrent()) return;
        var host = TryGetRealizedRow(index);
        if (host == null || !ReadyHost(host) || !intent.IsReady()) return;
        var bounds = Bounds(host, viewport);
        var visible = bounds.Bottom > 0 && bounds.Top < viewport.ViewportHeight;
        var settled = intent.Kind == PositionKind.Latest
            ? visible && Math.Abs(viewport.ScrollableHeight - viewport.VerticalOffset) <= 1
            : visible && Math.Abs(bounds.Top - intent.Top) <= 1 && (intent.Kind != PositionKind.First || viewport.VerticalOffset <= 1);
        if (settled)
        {
            intent.Settled = true; TracePosition(intent, "settled"); intent.Completion.TrySetResult(true);
            if (intent.Kind != PositionKind.Latest) position = null;
            return;
        }
        intent.Settled = false;
        var geometry = (viewport.ViewportWidth, viewport.ViewportHeight, host.ActualWidth, host.ActualHeight,
            Math.Round((bounds.Top + viewport.VerticalOffset) * 64) / 64);
        if (intent.LastGeometry == geometry)
        {
            // The actual view change finished but this prepared geometry still
            // cannot restore the reading position. Release the pending page;
            // waiting for a geometry change that never comes is not a retry.
            if (intent.CorrectionCompleted && intent.Kind != PositionKind.Latest)
            { TracePosition(intent, "failed.same_geometry"); intent.Completion.TrySetResult(false); position = null; }
            return;
        }
        if (intent.Corrections >= 3)
        {
            // A failed reading restoration must release the in-flight page,
            // so the person can still navigate and request another page. The
            // caller and CI retain the actual anchor evidence; false is not
            // a successful restore. Follow-latest remains visibly unsettled.
            if (intent.Kind != PositionKind.Latest)
            { TracePosition(intent, "failed.corrections"); intent.Completion.TrySetResult(false); position = null; }
            return;
        }
        intent.LastGeometry = geometry; intent.Corrections++;
        // Deferred text can change a realized row's height. Correct only after
        // that actual content has prepared, and at most three times per intent.
        // A failure remains observable; no idle retry loop conceals it.
        var offset = intent.Kind == PositionKind.Latest ? viewport.ScrollableHeight
            : intent.Kind == PositionKind.First ? 0 : viewport.VerticalOffset + bounds.Top - intent.Top;
        var clamped = Math.Clamp(offset, 0, viewport.ScrollableHeight);
        if (intent.Kind == PositionKind.Reading && Math.Abs(offset - clamped) > 1)
        {
            // No legal viewport offset can preserve this prepared anchor to
            // the existing one-DIP tolerance. Do not await an impossible move.
            TracePosition(intent, "failed.out_of_range"); intent.Completion.TrySetResult(false); position = null; return;
        }
        intent.CorrectionPending = true; intent.CorrectionCompleted = false;
        TracePosition(intent, "correct");
        if (!viewport.ChangeView(null, clamped, null, true))
        {
            intent.CorrectionPending = false; intent.CorrectionCompleted = true;
            // No final ViewChanged is required when the view did not change.
            // Latest remains unsettled; a failed history restore must finish.
            if (intent.Kind != PositionKind.Latest)
            { intent.Completion.TrySetResult(false); position = null; }
        }
    }

    internal bool IsLastPositionSettled
    {
        get
        {
            if (position is not { Kind: PositionKind.Latest, Settled: true } follow || Viewport is not { } viewport
                || !follow.IsCurrent() || !follow.IsReady() || follow.View != ViewIdentity) return false;
            var host = TryGetRealizedRow(entries.Count - 1);
            if (host == null || !ReadyHost(host)) return false;
            var bounds = Bounds(host, viewport);
            return bounds.Bottom > 0 && bounds.Top < viewport.ViewportHeight
                && Math.Abs(viewport.ScrollableHeight - viewport.VerticalOffset) <= 1;
        }
    }

    internal object ReadScrollState(ScrollViewer viewport)
    {
        var host = TryGetRealizedRow(entries.Count - 1);
        var bounds = host is { IsLoaded: true } ? Bounds(host, viewport) : (Windows.Foundation.Rect?)null;
        var targetIndex = position == null ? -1 : position.Kind == PositionKind.Latest ? entries.Count - 1
            : position.Kind == PositionKind.First ? 0 : entries.ToList().FindIndex(entry => entry.Row.Key == position.Key);
        var target = TryGetRealizedRow(targetIndex);
        return new { implementation = "ListView/ItemsStackPanel", revision, committed, realized = Realized,
            pending_builds = PendingBuilds, offset = viewport.VerticalOffset, maximum = viewport.ScrollableHeight,
            intent = position?.Kind.ToString(), corrections = position?.Corrections, settled = position?.Settled ?? false,
            requested_key = position?.RequestedEntry?.Row.Key, target_index = targetIndex,
            target_loaded = target?.IsLoaded ?? false, target_prepared = target != null && ReadyHost(target),
            correction_pending = position?.CorrectionPending ?? false,
            correction_completed = position?.CorrectionCompleted ?? false,
            content_ready = position?.IsReady(),
            last_row = new { loaded = host?.IsLoaded ?? false, child_ready = host?.Child != null, top = bounds?.Top, bottom = bounds?.Bottom } };
    }
}
