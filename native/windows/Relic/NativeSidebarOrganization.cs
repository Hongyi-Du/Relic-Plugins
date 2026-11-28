namespace Relic;

// These values are read from the same live organization, folded set and search
// used to render the tree. Searching reveals matches without changing the set.
// PersistedFolded already applies the organization's default: one with
// organizations below it, or the open one, starts unfolded; any other starts
// folded and lists its members only once the person unfolds it.
internal readonly record struct NativeSidebarOrganizationState(bool CanExpand, bool PersistedFolded, bool SearchActive)
{
    internal bool Expanded => CanExpand && (SearchActive || !PersistedFolded);
    internal bool HidesDescendants => !SearchActive && PersistedFolded;
}

internal sealed class NativeSidebarOrganization(Func<NativeSidebarOrganizationState> read, Action<bool> setFolded)
{
    internal NativeSidebarOrganizationState Current => read();

    // The row stays mounted while only the rows under it change: its arrow
    // follows the new state through this, set by the row as it is built.
    internal Action? Changed { get; set; }

    internal void TogglePersisted()
    {
        var current = Current;
        if (!current.CanExpand) throw new InvalidOperationException("A leaf organization cannot be folded");
        setFolded(!current.PersistedFolded);
        Changed?.Invoke();
    }

    internal void SetExpanded(bool expanded)
    {
        var current = Current;
        if (!current.CanExpand) throw new InvalidOperationException("A leaf organization cannot be expanded or collapsed");
        if (current.PersistedFolded == expanded) { setFolded(!expanded); Changed?.Invoke(); }
    }
}
