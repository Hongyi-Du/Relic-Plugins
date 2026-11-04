using Relic;
using Xunit;

namespace Relic.Core.Tests;

public sealed class NativeSidebarOrganizationTests
{
    private sealed class Tree
    {
        internal readonly HashSet<string> Folded = [];
        internal string Active = "secretariat";
        internal bool HasChildren;
        internal string Query = "";
        internal int Saves;
        internal readonly NativeSidebarOrganization Row;

        internal Tree()
        {
            Row = new NativeSidebarOrganization(
                () => new NativeSidebarOrganizationState(Active == "secretariat" || HasChildren,
                    Folded.Contains("secretariat"), Query.Trim().Length > 0),
                value => { if (value) Folded.Add("secretariat"); else Folded.Remove("secretariat"); Saves++; });
        }
    }

    [Fact]
    public void PointerToggleUsesLivePersistedFoldedStateAndSavesEachChange()
    {
        var tree = new Tree();
        Assert.True(tree.Row.Current.Expanded);
        tree.Row.TogglePersisted();
        Assert.False(tree.Row.Current.Expanded);
        Assert.True(tree.Row.Current.HidesDescendants);
        Assert.Contains("secretariat", tree.Folded);
        tree.Row.TogglePersisted();
        Assert.True(tree.Row.Current.Expanded);
        Assert.Empty(tree.Folded);
        Assert.Equal(2, tree.Saves);
    }

    [Fact]
    public void SearchingRevealsChildrenWhilePointerToggleStillTogglesPersistedState()
    {
        var tree = new Tree { Query = "review" };
        tree.Row.TogglePersisted();
        Assert.Contains("secretariat", tree.Folded);
        Assert.True(tree.Row.Current.Expanded);
        Assert.False(tree.Row.Current.HidesDescendants);
        tree.Row.TogglePersisted();
        Assert.Empty(tree.Folded);
        Assert.True(tree.Row.Current.Expanded);
        Assert.Equal(2, tree.Saves);
    }

    [Fact]
    public void EndingSearchRestoresTheActualPersistedCollapse()
    {
        var tree = new Tree { Query = "review" };
        tree.Folded.Add("secretariat");
        Assert.True(tree.Row.Current.Expanded);
        tree.Query = "   ";
        Assert.False(tree.Row.Current.Expanded);
        Assert.True(tree.Row.Current.HidesDescendants);
        Assert.Equal(0, tree.Saves);
    }

    [Fact]
    public void ProviderExpandAndCollapseAreIdempotentInsteadOfToggles()
    {
        var tree = new Tree();
        tree.Row.SetExpanded(true);
        Assert.Equal(0, tree.Saves);
        tree.Row.SetExpanded(false);
        tree.Row.SetExpanded(false);
        Assert.Equal(1, tree.Saves);
        Assert.False(tree.Row.Current.Expanded);
        tree.Row.SetExpanded(true);
        tree.Row.SetExpanded(true);
        Assert.Equal(2, tree.Saves);
        Assert.True(tree.Row.Current.Expanded);
    }

    [Fact]
    public void ProviderCollapseDuringSearchReportsActualExpandedState()
    {
        var tree = new Tree { Query = "review" };
        tree.Row.SetExpanded(false);
        Assert.Contains("secretariat", tree.Folded);
        Assert.True(tree.Row.Current.Expanded);
        tree.Row.SetExpanded(false);
        Assert.Equal(1, tree.Saves);
        tree.Query = "";
        Assert.False(tree.Row.Current.Expanded);
    }

    [Fact]
    public void LeafRowsDoNotAcceptExpansionActionsEvenDuringSearch()
    {
        var tree = new Tree { Active = "another-org", Query = "review" };
        Assert.False(tree.Row.Current.CanExpand);
        Assert.False(tree.Row.Current.Expanded);
        Assert.Throws<InvalidOperationException>(() => tree.Row.SetExpanded(true));
        Assert.Throws<InvalidOperationException>(() => tree.Row.SetExpanded(false));
        Assert.Throws<InvalidOperationException>(() => tree.Row.TogglePersisted());
        Assert.Equal(0, tree.Saves);
        Assert.Empty(tree.Folded);
    }

    [Fact]
    public void ExpansionCapabilityReadsCurrentSelectionAndChildren()
    {
        var tree = new Tree { Active = "another-org" };
        Assert.False(tree.Row.Current.CanExpand);
        tree.HasChildren = true;
        Assert.True(tree.Row.Current.CanExpand);
        tree.Row.SetExpanded(false);
        Assert.False(tree.Row.Current.Expanded);
        tree.HasChildren = false;
        Assert.False(tree.Row.Current.CanExpand);
        tree.Active = "secretariat";
        Assert.True(tree.Row.Current.CanExpand);
        Assert.False(tree.Row.Current.Expanded);
    }
}
