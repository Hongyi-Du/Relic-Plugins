using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Relic.Core;

namespace Relic;

// The native SelectorBarItem remains the accessible and interactive control.
// Its label uses the same production DirectWrite layout for measure and paint,
// with the actual natural baseline centered in the requested CSS line height.
internal sealed class NativeSettingsNavigationLabel : Grid
{
    private readonly string text, locale;
    private bool? renderedSelected;
    internal NativeLabel? CurrentLabel { get; private set; }

    internal NativeSettingsNavigationLabel(string text, string locale)
    {
        this.text = text; this.locale = locale;
        UseLayoutRounding = false; IsHitTestVisible = false;
        VerticalAlignment = VerticalAlignment.Center;
        AutomationProperties.SetAccessibilityView(this, AccessibilityView.Raw);
    }

    internal void ApplyState(bool selected, Brush foreground)
    {
        if (CurrentLabel == null || renderedSelected != selected)
        {
            // Font weight is part of NativeLabel's immutable production layout.
            // Replace only on actual selection changes; hovering recolors the
            // same mounted label and cannot create a second visible text node.
            var label = new NativeLabel(text, FontFamilies.UI, 14, selected ? (ushort)600 : (ushort)400,
                locale, 14 * 1.6) { Foreground = foreground };
            Children.Clear(); Children.Add(label);
            CurrentLabel = label; renderedSelected = selected;
        }
        else CurrentLabel.Foreground = foreground;
    }
}
