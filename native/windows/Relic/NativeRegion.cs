using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;

namespace Relic;

// These are navigable application regions, not anonymous layout wrappers.
// Their real peers expose the same localized section names to assistive tools.
internal sealed class NativeRegionGrid : Grid
{
    protected override AutomationPeer OnCreateAutomationPeer() => new RegionPeer(this);

    private sealed class RegionPeer(NativeRegionGrid owner) : FrameworkElementAutomationPeer(owner)
    {
        protected override AutomationControlType GetAutomationControlTypeCore() => AutomationControlType.Group;
        protected override string GetClassNameCore() => nameof(NativeRegionGrid);
        protected override string GetNameCore() => AutomationProperties.GetName(owner);
        protected override bool IsControlElementCore() => true;
        protected override bool IsContentElementCore() => true;
    }
}

