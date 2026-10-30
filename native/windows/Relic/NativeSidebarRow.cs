using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Automation.Provider;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;

namespace Relic;

// A real ListViewItem retains the list's selection/name behavior. Additional
// organization and unread state comes from the same production objects that
// draw its arrow and badge, not from a capture label or expected reference row.
internal sealed class NativeSidebarRow : ListViewItem
{
    private NativeSidebarOrganization? organization;
    private UIElement? boundContent;
    private OverviewBadgeView? unreadBadge;
    private bool chat;
    private Func<bool, string>? itemStatus;
    private readonly List<(DependencyObject Owner, DependencyProperty Property, long Token)> observers = [];
    private string? lastItemStatus;

    internal OverviewBadgeView? BoundUnreadBadge => unreadBadge;
    internal NativeSidebarOrganizationState? OrganizationState => organization?.Current;

    internal NativeSidebarRow()
    {
        Loaded += (_, _) => { WatchBadge(); NotifyItemStatus(); };
        Unloaded += (_, _) => StopWatching();
    }

    internal void BindOrganization(NativeSidebarOrganization source)
    {
        organization = source; boundContent = Content as UIElement;
    }

    internal void BindChat(OverviewBadgeView? badge, Func<bool, string> status)
    {
        chat = true; boundContent = Content as UIElement; unreadBadge = badge; itemStatus = status;
        if (IsLoaded) { WatchBadge(); NotifyItemStatus(); }
    }

    private (bool? Unread, bool ContentMatches, bool ReachesOwner, bool Visible, JsonArray Path) ReadBadge()
    {
        var contentMatches = boundContent != null && ReferenceEquals(Content, boundContent);
        var path = new JsonArray();
        if (!chat || !contentMatches) return (null, contentMatches, false, false, path);
        // This particular chat row never created an unread badge. Role/leader
        // badges are different actual objects and do not mark messages unread.
        if (unreadBadge == null) return (false, true, false, false, path);
        var visible = true;
        for (DependencyObject? current = unreadBadge; current != null; current = VisualTreeHelper.GetParent(current))
        {
            if (current is UIElement element) visible &= element.Visibility == Visibility.Visible && element.Opacity > 0;
            path.Add(new JsonObject { ["type"] = current.GetType().FullName,
                ["reference_hash"] = RuntimeHelpers.GetHashCode(current), ["is_owner"] = ReferenceEquals(current, this) });
            if (ReferenceEquals(current, this)) return (visible, true, true, visible, path);
        }
        // A formerly bound badge outside this row is unknown, not a read badge.
        return (null, true, false, visible, path);
    }

    internal bool? Unread => ReadBadge().Unread;
    private string? CurrentItemStatus => Unread is { } unread ? itemStatus?.Invoke(unread) : null;

    internal JsonObject CaptureSidebarState()
    {
        var current = OrganizationState; var badge = ReadBadge();
        return new JsonObject
        {
            ["source"] = "Actual NativeSidebarRow organization binding and retained unread badge object",
            ["row_kind"] = organization != null ? "organization" : chat ? "chat" : "unbound",
            ["expanded"] = current?.Expanded, ["unread"] = badge.Unread,
            ["organization"] = current is { } state ? new JsonObject
            {
                ["source"] = "Same live folded/query/CanExpand getters used by the production tree and arrow",
                ["can_expand"] = state.CanExpand, ["persisted_folded"] = state.PersistedFolded,
                ["search_active"] = state.SearchActive, ["expanded"] = state.Expanded,
                ["provider_state"] = !state.CanExpand ? "LeafNode" : state.Expanded ? "Expanded" : "Collapsed"
            } : null,
            ["chat_badge"] = chat ? new JsonObject
            {
                ["source"] = "Actual badge reference retained when constructing this chat row",
                ["same_content_reference"] = badge.ContentMatches, ["badge_present"] = unreadBadge != null,
                ["badge_reference_hash"] = unreadBadge == null ? null : RuntimeHelpers.GetHashCode(unreadBadge),
                ["badge_is_loaded"] = unreadBadge?.IsLoaded,
                ["badge_visibility"] = unreadBadge?.Visibility.ToString(), ["badge_opacity"] = unreadBadge?.Opacity,
                ["actual_parent_path"] = badge.Path, ["path_reaches_same_row_object"] = badge.ReachesOwner,
                ["visible_through_owner"] = unreadBadge == null ? null : badge.Visible,
                ["item_status"] = badge.Unread is { } unread ? itemStatus?.Invoke(unread) : null
            } : null
        };
    }

    private void WatchBadge()
    {
        StopWatching();
        if (unreadBadge == null) return;
        for (DependencyObject? current = unreadBadge; current != null; current = VisualTreeHelper.GetParent(current))
        {
            if (current is UIElement)
                foreach (var property in new[] { UIElement.VisibilityProperty, UIElement.OpacityProperty })
                    observers.Add((current, property, current.RegisterPropertyChangedCallback(property, (_, _) => NotifyItemStatus())));
            if (ReferenceEquals(current, this)) break;
        }
    }

    private void StopWatching()
    {
        foreach (var (owner, property, token) in observers) owner.UnregisterPropertyChangedCallback(property, token);
        observers.Clear();
    }

    private void NotifyItemStatus()
    {
        var status = CurrentItemStatus;
        if (status == lastItemStatus) return;
        var previous = lastItemStatus; lastItemStatus = status;
        if (FrameworkElementAutomationPeer.FromElement(this) is { } peer)
            peer.RaisePropertyChangedEvent(AutomationElementIdentifiers.ItemStatusProperty, previous ?? "", status ?? "");
    }

    protected override AutomationPeer OnCreateAutomationPeer() => new SidebarPeer(this);

    private sealed class SidebarPeer(NativeSidebarRow owner) : ListViewItemAutomationPeer(owner), IExpandCollapseProvider
    {
        protected override string GetClassNameCore() => nameof(NativeSidebarRow);
        protected override string GetItemStatusCore() => owner.CurrentItemStatus ?? base.GetItemStatusCore();
        protected override object GetPatternCore(PatternInterface pattern) =>
            pattern == PatternInterface.ExpandCollapse && owner.organization != null ? this : base.GetPatternCore(pattern);
        public ExpandCollapseState ExpandCollapseState => owner.OrganizationState is not { } state || !state.CanExpand
            ? ExpandCollapseState.LeafNode : state.Expanded ? ExpandCollapseState.Expanded : ExpandCollapseState.Collapsed;
        public void Expand() => Change(true);
        public void Collapse() => Change(false);
        private void Change(bool expanded)
        {
            // Public UI Automation disabled-element HRESULT, also used by the
            // WinUI providers. There is no WinUI ElementNotEnabledException.
            if (!owner.IsEnabled) throw new COMException("The organization row is disabled", unchecked((int)0x80040200));
            var source = owner.organization ?? throw new InvalidOperationException("This row is not an organization");
            var before = ExpandCollapseState;
            source.SetExpanded(expanded);
            var after = ExpandCollapseState;
            if (before != after) RaisePropertyChangedEvent(ExpandCollapsePatternIdentifiers.ExpandCollapseStateProperty, before, after);
        }
    }
}
