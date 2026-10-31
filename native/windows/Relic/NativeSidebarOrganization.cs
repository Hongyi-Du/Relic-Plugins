namespace Relic;

// These values are read from the same live organization, folded set and search
// used to render the tree. Searching reveals matches without changing the set.
internal readonly record struct NativeSidebarOrganizationState(bool CanExpand, bool PersistedFolded, bool SearchActive)
{
    internal bool Expanded => CanExpand && (SearchActive || !PersistedFolded);
    internal bool HidesDescendants => !SearchActive && PersistedFolded;
}

internal sealed class NativeSidebarOrganization(Func<NativeSidebarOrganizationState> read, Action<bool> setFolded)
{
    internal NativeSidebarOrganizationState Current => read();

    internal void TogglePersisted()
    {
        var current = Current;
        if (!current.CanExpand) throw new InvalidOperationException("A leaf organization cannot be folded");
        setFolded(!current.PersistedFolded);
    }

    internal void SetExpanded(bool expanded)
    {
        var current = Current;
        if (!current.CanExpand) throw new InvalidOperationException("A leaf organization cannot be expanded or collapsed");
        if (current.PersistedFolded == expanded) setFolded(!expanded);
    }
}
