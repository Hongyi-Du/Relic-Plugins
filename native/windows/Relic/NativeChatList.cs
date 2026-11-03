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
        internal long ConfirmAfter;
        internal bool Settled;
        internal bool CorrectionPending, CorrectionCompleted;
        // Where the last correction asked the viewport to go. A ViewChanged
        // from an earlier scroll can arrive before that correction lands.
        internal double? CorrectionTarget;
        // When the last correction was asked for (see CheckPosition).
        internal long CorrectionAt;
        internal readonly long StartedAt = System.Diagnostics.Stopwatch.GetTimestamp();
        // The seek went to a row above the reading row (see SeekIndex), and
        // whether the reading row itself was then sought as a fallback.
        internal bool SeekedAbove, SeekedRow;
        internal int SeekIndex = -1, Walks, Reseeks;
        internal long SeekAt;
        // The row the seek went to has been seen near the view: the seek's
        // own view change has happened (see SeekLanded).
        internal bool SeekLanded;
        // CI evidence: what the last check that did nothing waited for.
        internal string? Waiting;
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
    private ObservableCollection<Entry> entries = [];
    private readonly Dictionary<Border, Mounted> mounted = [];
    private readonly HashSet<Border> placing = [];
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
    internal event Action? PositionEnded;
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
            if (list.Header is FrameworkElement top) top.Margin = new Thickness(0, 0, 0, spacing);
        }
    }

    // Content above the rows that is not one of them: the "load older" control.
    // The list header is not an item, so the message being read, not this
    // control, is the reading anchor when an older page goes in above it.
    internal FrameworkElement? TopContent
    {
        get => list.Header as FrameworkElement;
        set
        {
            if (value != null) value.Margin = new Thickness(0, 0, 0, spacing);
            if (ReferenceEquals(list.Header, value)) return;
            if (list.Header is FrameworkElement old)
            {
                old.SizeChanged -= HeaderSizeChanged;
                // Removing it moves the rows below it up by its whole slot.
                if (old.IsLoaded) KeepRowsOnScreen(old, -(old.ActualHeight + old.Margin.Top + old.Margin.Bottom));
            }
            if (value != null) value.SizeChanged += HeaderSizeChanged;
            list.Header = value;
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
        // Rows are not scroll anchor candidates. During a far scroll the
        // ScrollViewer could pick a row whose container the panel then recycled
        // for another item, and shifted the view by that item's position (a
        // scroll to the top stopped 272 px down). Naming the row being read as
        // the anchor fed back into the panel's estimates instead (a restore
        // grew the extent to 1.2 million px and never settled). Rows that
        // change height above the viewport are offset in KeepRowsOnScreen.
        list.ItemTemplate = XamlTemplates.Load<DataTemplate>(
            "<DataTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation'>" +
            "<Border HorizontalAlignment='Stretch' UseLayoutRounding='False'/></DataTemplate>");
        // KeepScrollOffset turns off the panel's own "maintain viewport" tracking.
        // That tracking generates from a remembered row index; once the index fell
        // outside the realized rows (a long chat, an older page, a far scroll),
        // ContainerManager::PlaceInValidElements failed fast (E_UNEXPECTED,
        // 0xC000027B) and took the app down. The ScrollViewer's anchoring and the
        // position intents below keep the latest row and the reading row in place.
        list.ItemsPanel = XamlTemplates.Load<ItemsPanelTemplate>(
            "<ItemsPanelTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation'>" +
            "<ItemsStackPanel ItemsUpdatingScrollMode='KeepScrollOffset' CacheLength='0.5'/></ItemsPanelTemplate>");
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
        list.LayoutUpdated += (_, _) => { ApplyPendingShift(); if (position != null) QueuePositionCheck(); };
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

    // Set by the conversation for a touch or touchpad pan it attributed to the
    // person. The ScrollViewer also raises DirectManipulationStarted for the
    // list's own scrolls, so that event alone cannot say whose gesture it is.
    private bool userPanning;
    internal bool UserPanning
    {
        get => userPanning;
        set { userPanning = value; if (value) pendingShift = 0; }
    }
    private double pendingShift;

    // ItemsStackPanel's KeepItemsInView did this itself (and failed fast, see
    // the panel template): a row that starts above the viewport and is built or
    // changes height moves every row below it by the same amount. That includes
    // a row cut by the top edge: its own top stays put, so the message under it,
    // the one being read, moved (a restored position slid up 72 px when the row
    // above it finished building). Move the view with it, in the same layout,
    // so what the person reads stays put. Not while following the latest
    // message (the bottom edge is anchored then), and not during a touch or
    // touchpad pan, where a ChangeView would end the person's own gesture.
    private void KeepRowsOnScreen(FrameworkElement element, double delta)
    {
        if (Math.Abs(delta) < .25 || userPanning || Viewport is not { } viewport || !element.IsLoaded
            || position is { Kind: PositionKind.Latest }) return;
        if (Bounds(element, viewport).Top < 0) pendingShift += delta;
    }

    private void ApplyPendingShift()
    {
        if (pendingShift == 0 || Viewport is not { } viewport) return;
        var shift = pendingShift; pendingShift = 0;
        if (userPanning) return;
        // A seek's own view change is still pending: a ChangeView now would
        // replace it, and the seek repositions every row anyway.
        if (position is { SeekedAbove: true, SeekLanded: false, SeekedRow: false }) return;
        PerformanceTrace.Count(TraceName + ".list.keep_rows_on_screen", shift);
        RequestOffset(viewport, RequestedOffset(viewport) + shift);
        // A correction still on its way moves with the rows too.
        if (position is { CorrectionPending: true } pending) pending.CorrectionTarget = requestedOffset;
    }

    // Where this list's own last ChangeView asked the view to go, until the
    // view gets there. VerticalOffset still shows the old place meanwhile, and
    // a second ChangeView computed from it replaced the first: a row shift
    // during a reading correction lost the correction, its final ViewChanged
    // never came, and the restore (and every older page after it) waited forever.
    private double? requestedOffset;
    private long requestedAt;
    private double RequestedOffset(ScrollViewer viewport)
    {
        if (requestedOffset is { } requested
            && System.Diagnostics.Stopwatch.GetElapsedTime(requestedAt).TotalMilliseconds < 250) return requested;
        requestedOffset = null;
        return viewport.VerticalOffset;
    }
    private bool RequestOffset(ScrollViewer viewport, double offset)
    {
        var target = Math.Clamp(offset, 0, viewport.ScrollableHeight);
        requestedOffset = target; requestedAt = System.Diagnostics.Stopwatch.GetTimestamp();
        if (viewport.ChangeView(null, target, null, true)) return true;
        requestedOffset = null;
        return false;
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
        // Another chat is cleared and filled row by row; its latest-row intent
        // asks for the last row before the first layout. Older pages are
        // inserted row by row above the rows on screen, and the reading intent
        // brings the message being read back to where it was.
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
        // A container placed for another item: its next size change is that
        // placement, not a row on the page growing (see KeepRowsOnScreen).
        if (old == null || !ReferenceEquals(old.Entry, entry)) placing.Add(host);
        mounted[host] = new(entry, entry.Version);
        host.Child = null; host.Tag = entry.Row; host.MinHeight = entry.Row.Estimate;
        host.Margin = new Thickness(0, 0, 0, spacing);
        builds.Enqueue(new(host, entry, entry.Version)); Interlocked.Increment(ref pendingBuilds);
        if (!pump.IsEnabled) pump.Start();
    }

    private void Release(Border host)
    {
        mounted.Remove(host); placing.Remove(host); host.SizeChanged -= HostSizeChanged;
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
                PerformanceTrace.Track("ChatRow", work.Host.Child);
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
        var intent = position = new(kind, key, top, isCurrent, isReady, ViewIdentity, CaptureSeekInputGeneration());
        // A chat that was just filled starts at its top. Ask for its last row
        // before the first layout, so the panel realizes the newest rows rather
        // than building the oldest ones first and seeking afterwards.
        // The usual check still runs afterwards and seeks again if this did not land.
        if (kind == PositionKind.Latest && TryGetRealizedRow(entries.Count - 1) == null)
        {
            TracePosition(intent, "seek_early");
            list.ScrollIntoView(entries[^1], ScrollIntoViewAlignment.Default);
        }
        QueuePositionCheck();
        return intent.Completion.Task;
    }

    internal void StopFollowingLast()
    {
        if (position is { } ended)
        {
            if (ended.Kind != PositionKind.Latest) TracePosition(ended, "cleared");
            EndPosition(ended, false);
        }
    }

    private void HostSizeChanged(object sender, SizeChangedEventArgs args)
    {
        // A row that changed height moves the bottom; following it again is
        // not a repeat of the previous correction.
        var placed = sender is Border placedHost && placing.Remove(placedHost);
        if (position is { Kind: PositionKind.Latest } follow) { follow.Corrections = 0; follow.LastGeometry = null; }
        else if (!placed && sender is Border host && args.PreviousSize.Height > 0)
            KeepRowsOnScreen(host, args.NewSize.Height - args.PreviousSize.Height);
        QueuePositionCheck();
    }
    private void HeaderSizeChanged(object sender, SizeChangedEventArgs args)
    {
        // The header sits above every row: it appearing or changing height
        // moves the rows on screen when the view is below it. Appearing, it
        // also brings its margin.
        if (sender is not FrameworkElement header) return;
        var delta = args.NewSize.Height - args.PreviousSize.Height;
        if (args.PreviousSize.Height == 0) delta += header.Margin.Top + header.Margin.Bottom;
        KeepRowsOnScreen(header, delta);
    }
    private void ViewChanged(object? sender, ScrollViewerViewChangedEventArgs args)
    {
        if (args.IsIntermediate) return;
        // The last request landing ends it; an earlier view change's
        // ViewChanged can arrive while the last request is still on its way.
        // A view change ending elsewhere well after the request (the person's
        // wheel, another ChangeView) replaced it.
        if (requestedOffset is { } requested && sender is ScrollViewer viewport
            && (Math.Abs(viewport.VerticalOffset - requested) <= 1
                || System.Diagnostics.Stopwatch.GetElapsedTime(requestedAt).TotalMilliseconds > 100)) requestedOffset = null;
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
    private Microsoft.UI.Dispatching.DispatcherQueueTimer? confirmTimer;
    // One check after the confirmation delay, in case nothing else (a build,
    // a size or view change) asks for one before then.
    private void ScheduleConfirmation()
    {
        if (confirmTimer == null)
        {
            confirmTimer = dispatcher.CreateTimer();
            confirmTimer.Interval = TimeSpan.FromMilliseconds(130); confirmTimer.IsRepeating = false;
            confirmTimer.Tick += (_, _) => QueuePositionCheck();
        }
        confirmTimer.Stop(); confirmTimer.Start();
    }

    private void QueuePositionCheck()
    {
        if (position == null || checkQueued) return;
        checkQueued = true;
        if (!dispatcher.TryEnqueue(Microsoft.UI.Dispatching.DispatcherQueuePriority.Low, () =>
            { checkQueued = false; CheckPosition(); })) checkQueued = false;
    }

    // A reading row goes back below the rows above it (its old place on screen
    // is usually some way down). Seeking the row itself put it at the top, and
    // each correction then scrolled up into rows the panel had only estimated;
    // the panel's estimate correction moved the rows with the view and undid
    // the scroll (five corrections of 406 px left the row where it was). Seek
    // a row above it instead, by our own height estimates, so the corrections
    // scroll down through rows that are already placed. The margin covers rows
    // above that turn out shorter than estimated.
    private int SeekIndex(Position intent, int index, double margin)
    {
        if (intent.Kind != PositionKind.Reading || margin <= 0) return index;
        var seek = index; var above = 0d;
        while (seek > 0 && above < margin) { seek--; above += entries[seek].Row.Estimate + spacing; }
        return seek;
    }

    // Whether the row a seek went to is realized near the view, which means
    // the seek's view change has happened. Once seen, it stays landed: walking
    // down from there takes that row out of the view on purpose.
    private bool SeekLanded(Position intent, ScrollViewer viewport)
    {
        if (intent.SeekLanded) return true;
        if (TryGetRealizedRow(intent.SeekIndex) is not { IsLoaded: true } row) return false;
        var bounds = Bounds(row, viewport);
        return intent.SeekLanded = bounds.Bottom > -viewport.ViewportHeight && bounds.Top < viewport.ViewportHeight;
    }

    // The top, on screen, of the first realized row at or above this one.
    private double FirstRealizedTop(ScrollViewer viewport, int index)
    {
        var first = TryGetRealizedRow(index);
        var i = index - 1;
        while (i >= 0 && TryGetRealizedRow(i) is { IsLoaded: true } earlier) { first = earlier; i--; }
        return first is { IsLoaded: true } ? Bounds(first, viewport).Top : double.NegativeInfinity;
    }

    // Whether every realized row from `from` down to the reading row has been
    // built. An unbuilt row still has its estimated height: a walk judged 13 ms
    // after the seek, before the rows above the reading row were built, put it
    // 378 px above its place once they turned out shorter, and every upward
    // correction from there was absorbed.
    private bool RowsBuilt(int from, int index)
    {
        for (var i = Math.Max(0, from); i < index; i++)
            if (TryGetRealizedRow(i) is { IsLoaded: true, Child: null }) return false;
        return true;
    }

    // A restore waits for events (layout, a built row, a finished view
    // change). Check again shortly in case none comes, and give up on a
    // restore that has not settled after a few seconds, so an older page or
    // the next chat is never blocked behind it. Following the latest message
    // never times out and never polls: it lasts while the person reads there.
    private bool RestoreTimedOut(Position intent)
    {
        if (intent.Kind == PositionKind.Latest) return false;
        if (System.Diagnostics.Stopwatch.GetElapsedTime(intent.StartedAt).TotalSeconds < 4) { ScheduleConfirmation(); return false; }
        PerformanceTrace.Note(TraceName + ".position.timeout", new { waiting = intent.Waiting, key = intent.Key,
            seek = intent.SeekIndex, intent.Walks, intent.Reseeks, intent.Corrections, intent.SeekLanded, intent.CorrectionPending });
        TracePosition(intent, "failed.timeout"); EndPosition(intent, false);
        return true;
    }

    // CI-only evidence of how a position intent ended; Count is a no-op otherwise.
    private void TracePosition(Position intent, string step)
    {
        intent.Waiting = null;
        PerformanceTrace.Count(TraceName + ".position." + intent.Kind.ToString().ToLowerInvariant() + "." + step, intent.Corrections);
    }

    // CI evidence of what a check that did nothing was waiting for, once per
    // change: a restore that timed out showed no step after its correction.
    private void TraceWait(Position intent, string reason)
    {
        if (intent.Kind == PositionKind.Latest || intent.Waiting == reason) return;
        TracePosition(intent, "wait." + reason);
        intent.Waiting = reason;
    }

    // Which part of the content a restore is still waiting for.
    private static string ContentWait() =>
        PendingBuilds > 0 ? "content.chat_rows" : VirtualRows.PendingBuilds > 0 ? "content.other_rows"
        : NativeLabel.PendingPreparations > 0 ? "content.labels" : NativePathText.PendingPreparations > 0 ? "content.path_text"
        : NativeGlyphWarmup.PendingPreparations > 0 ? "content.glyphs" : "content.markdown_or_model";

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
            intent.CorrectionPending = false; intent.CorrectionCompleted = false; intent.CorrectionTarget = null;
            intent.SeekedAbove = false; intent.SeekedRow = false; intent.SeekIndex = -1; intent.Walks = 0; intent.SeekLanded = false;
            // The platform realizes the target; this does not construct or
            // manually position an off-viewport item in an ItemsRepeater.
            var existing = TryGetRealizedRow(index);
            var existingBounds = existing is { IsLoaded: true } ? Bounds(existing, viewport) : default;
            if (existing == null || existingBounds.Bottom <= 0 || existingBounds.Top >= viewport.ViewportHeight)
            {
                // A row cut by the top edge (Top <= 0) is sought itself: its
                // correction goes down.
                var seekIndex = SeekIndex(intent, index, intent.Top > 0 ? intent.Top + 240 : 0);
                intent.SeekedAbove = seekIndex != index; intent.SeekIndex = seekIndex;
                intent.SeekAt = System.Diagnostics.Stopwatch.GetTimestamp();
                TracePosition(intent, intent.SeekedAbove ? "seek_above" : "seek");
                list.ScrollIntoView(entries[seekIndex], intent.Kind == PositionKind.Latest ? ScrollIntoViewAlignment.Default : ScrollIntoViewAlignment.Leading);
                RestoreTimedOut(intent);
                return;
            }
        }
        // LayoutUpdated can repeat while ChangeView is still in flight. Only
        // its final ViewChanged permits evaluating that correction's result.
        // If it never comes (another view change replaced the correction),
        // judge where the view is after a while instead of waiting forever.
        if (intent.CorrectionPending)
        {
            if (System.Diagnostics.Stopwatch.GetElapsedTime(intent.CorrectionAt).TotalMilliseconds < 400)
            { if (intent.Kind != PositionKind.Latest) { ScheduleConfirmation(); TraceWait(intent, "correction"); } return; }
            TracePosition(intent, "correction_unfinished");
            intent.CorrectionPending = false; intent.CorrectionCompleted = true;
        }
        if (RestoreTimedOut(intent)) return;
        // This check runs at low priority and can come before the layout pass
        // that applies rows built since the last one. Judging the anchor from
        // their old estimated heights settled it early and let it drift. Bring
        // layout up to date first; the next frame would do the same work.
        using (PerformanceTrace.Measure(TraceName + ".list.layout_before_check")) list.UpdateLayout();
        if (!ReferenceEquals(position, intent) || !intent.IsCurrent()) return;
        var host = TryGetRealizedRow(index);
        if (intent.SeekedAbove && !intent.SeekedRow && !SeekLanded(intent, viewport))
        {
            // ScrollIntoView places the row it went to (and the rows after it)
            // at their new place at once, but the view moves there in a later
            // pass: until then their bounds against the old view are thousands
            // of pixels off, and every judgement from them (a walk down 8 ms
            // after the seek, re-seeks, then absorbed upward corrections) was
            // wrong. Wait for the move; seek the reading row itself only if it
            // never comes.
            if (System.Diagnostics.Stopwatch.GetElapsedTime(intent.SeekAt).TotalMilliseconds < 1000) { TraceWait(intent, "seek_unlanded"); return; }
            intent.SeekedRow = true; TracePosition(intent, "seek_row.unlanded");
            list.ScrollIntoView(entry, ScrollIntoViewAlignment.Leading);
            return;
        }
        if (host == null && intent.SeekedAbove && !intent.SeekedRow)
        {
            // The seek above lands over more than one layout pass: the row it
            // went to is placed first, the rows below it later. Seeking the
            // reading row itself as soon as it was missing (once in the same
            // pass as the seek) put it above the view, and the upward
            // corrections were absorbed again. Only when the rows before it
            // reach past the bottom of the view were they taller than estimated:
            // then walk down past them (a correction down lands).
            // The rows realized must be the ones from the seek on: right after
            // the seek the panel still holds the rows of the view before it (once
            // the list's first rows, and the walk went down from there).
            // Judge them only once they are built: until then they have their
            // estimated heights (see RowsBuilt).
            var built = RowsBuilt(intent.SeekIndex, index);
            Border? last = null;
            for (var i = index - 1; built && i >= Math.Max(0, intent.SeekIndex) && last == null; i--)
                if (TryGetRealizedRow(i) is { IsLoaded: true } realized) last = realized;
            if (last != null && intent.Walks < 8 && Bounds(last, viewport) is var lastBounds
                && lastBounds.Bottom >= viewport.ViewportHeight && lastBounds.Bottom > Math.Max(intent.Top, 0) + 1)
            {
                intent.Walks++; TracePosition(intent, "walk_down");
                RequestOffset(viewport, viewport.VerticalOffset + lastBounds.Bottom - Math.Max(intent.Top, 0));
                return;
            }
            if (System.Diagnostics.Stopwatch.GetElapsedTime(intent.SeekAt).TotalMilliseconds < 1000)
            { TraceWait(intent, !built ? "rows_unbuilt" : "row_unrealized"); return; }
            intent.SeekedRow = true; TracePosition(intent, "seek_row");
            list.ScrollIntoView(entry, ScrollIntoViewAlignment.Leading);
            return;
        }
        if (host == null) { TraceWait(intent, "row_unrealized"); return; }
        if (!ReadyHost(host)) { TraceWait(intent, host.Child == null ? "row_unbuilt" : "row_unmeasured"); return; }
        if (!intent.IsReady()) { TraceWait(intent, ContentWait()); return; }
        // Rows between the seek and the reading row that are still unbuilt will
        // change height and move it: correct only from built rows.
        if (intent.Kind == PositionKind.Reading && !RowsBuilt(intent.SeekIndex >= 0 ? intent.SeekIndex : index, index))
        { TraceWait(intent, "rows_unbuilt"); return; }
        var bounds = Bounds(host, viewport);
        var visible = bounds.Bottom > 0 && bounds.Top < viewport.ViewportHeight;
        // A restored reading position aims within half a pixel, inside the 1 px
        // the person (and CI) would notice. Opening at the first row only needs
        // the top: nothing above it can move it, and waiting would delay the open.
        var settled = intent.Kind switch
        {
            PositionKind.Latest => visible && Math.Abs(viewport.ScrollableHeight - viewport.VerticalOffset) <= 1,
            // The first row sits below the list header (the "load older" control)
            // when there is one; being scrolled to the top is the target.
            PositionKind.First => visible && viewport.VerticalOffset <= 1,
            _ => visible && Math.Abs(bounds.Top - intent.Top) <= .5,
        };
        if (settled)
        {
            if (intent.Kind == PositionKind.Reading)
            {
                // Rows realized by the last view change can still build and
                // resize after this check. Hold the restored position until it
                // is still in place a few frames later, so late layout cannot
                // move it after the restore reported success.
                var now = System.Diagnostics.Stopwatch.GetTimestamp();
                if (intent.ConfirmAfter == 0)
                {
                    intent.ConfirmAfter = now + System.Diagnostics.Stopwatch.Frequency / 8;
                    TracePosition(intent, "confirming"); ScheduleConfirmation(); return;
                }
                if (now < intent.ConfirmAfter) return;
            }
            intent.Settled = true; TracePosition(intent, "settled");
            if (intent.Kind != PositionKind.Latest) EndPosition(intent, true);
            else intent.Completion.TrySetResult(true);
            return;
        }
        intent.Settled = false; intent.ConfirmAfter = 0;
        var geometry = (viewport.ViewportWidth, viewport.ViewportHeight, host.ActualWidth, host.ActualHeight,
            Math.Round((bounds.Top + viewport.VerticalOffset) * 64) / 64);
        // The row has not moved, so only the viewport can still be wrong. If it
        // is not where the last correction asked, that correction has not landed
        // yet (an earlier scroll's ViewChanged ended the wait): ask again below.
        var landed = intent.CorrectionTarget is not { } target || Math.Abs(viewport.VerticalOffset - target) <= 1;
        if (intent.LastGeometry == geometry && (landed || intent.Kind == PositionKind.Latest))
        {
            // The actual view change finished but this prepared geometry still
            // cannot restore the reading position. Release the pending page;
            // waiting for a geometry change that never comes is not a retry.
            if (intent.CorrectionCompleted && intent.Kind != PositionKind.Latest)
            { TracePosition(intent, "failed.same_geometry"); EndPosition(intent, false); }
            else TraceWait(intent, "same_geometry");
            return;
        }
        if (!landed) TracePosition(intent, "not_landed");
        // Three corrections reach the target; two more cover drift found while
        // confirming it. Each one still needs a changed geometry.
        if (intent.Corrections >= (intent.Kind == PositionKind.Reading ? 5 : 3))
        {
            // A failed reading restoration must release the in-flight page,
            // so the person can still navigate and request another page. The
            // caller and CI retain the actual anchor evidence; false is not
            // a successful restore. Follow-latest remains visibly unsettled.
            if (intent.Kind != PositionKind.Latest)
            { TracePosition(intent, "failed.corrections"); EndPosition(intent, false); }
            return;
        }
        // An upward correction that uncovers rows above the realized ones is
        // absorbed: the panel places them by estimate and moves the rows with
        // the view (five corrections of 406 px once left the row where it
        // was). Seek a row above again instead, further up each time; the
        // corrections from there go down, and those land.
        var rise = intent.Kind == PositionKind.Reading ? intent.Top - bounds.Top : 0;
        if (rise > 1 && intent.Reseeks < 2 && FirstRealizedTop(viewport, index) + rise > 0)
        {
            intent.Reseeks++;
            var reseek = SeekIndex(intent, index, Math.Max(intent.Top, 0) + 240 * (intent.Reseeks + 1));
            intent.SeekedAbove = reseek != index; intent.SeekIndex = reseek; intent.SeekedRow = false; intent.Walks = 0; intent.SeekLanded = false;
            intent.SeekAt = System.Diagnostics.Stopwatch.GetTimestamp(); intent.LastGeometry = null;
            TracePosition(intent, "reseek_above");
            list.ScrollIntoView(entries[reseek], ScrollIntoViewAlignment.Leading);
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
            TracePosition(intent, "failed.out_of_range"); EndPosition(intent, false); return;
        }
        intent.CorrectionPending = true; intent.CorrectionCompleted = false; intent.CorrectionTarget = clamped;
        intent.CorrectionAt = System.Diagnostics.Stopwatch.GetTimestamp();
        TracePosition(intent, "correct");
        if (intent.Kind == PositionKind.Reading)
            PerformanceTrace.Note(TraceName + ".position.reading.detail", new { corrections = intent.Corrections,
                offset = viewport.VerticalOffset, target = clamped, maximum = viewport.ScrollableHeight,
                top = bounds.Top, height = bounds.Height, want = intent.Top, key = intent.Key, realized = mounted.Count,
                pending = PendingBuilds, index, seek = intent.SeekIndex, first_cache = (list.ItemsPanelRoot as ItemsStackPanel)?.FirstCacheIndex,
                first_visible = (list.ItemsPanelRoot as ItemsStackPanel)?.FirstVisibleIndex });
        if (!RequestOffset(viewport, clamped))
        {
            intent.CorrectionPending = false; intent.CorrectionCompleted = true;
            // No final ViewChanged is required when the view did not change.
            // Latest remains unsettled; a failed history restore must finish.
            if (intent.Kind != PositionKind.Latest)
            { TracePosition(intent, "failed.change_view"); EndPosition(intent, false); }
        }
    }

    // Ends a reading or first-row restore. Code that waited for it to finish
    // (a scroll to the top that could not load older messages meanwhile)
    // can act once the list holds no restore.
    private void EndPosition(Position intent, bool restored)
    {
        intent.Completion.TrySetResult(restored);
        if (ReferenceEquals(position, intent)) position = null;
        if (intent.Kind != PositionKind.Latest) PositionEnded?.Invoke();
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
