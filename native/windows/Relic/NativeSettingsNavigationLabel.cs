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
    private SolidColorBrush? renderedForeground;
    internal NativeLabel? CurrentLabel { get; private set; }

    internal NativeSettingsNavigationLabel(string text, string locale)
    {
        this.text = text; this.locale = locale;
        UseLayoutRounding = false; IsHitTestVisible = false;
        VerticalAlignment = VerticalAlignment.Center;
        AutomationProperties.SetAccessibilityView(this, AccessibilityView.Raw);
        Loaded += (_, _) => ApplyForeground();
    }

    internal void ApplyState(bool selected, SolidColorBrush foreground)
    {
        // Keep the actual production brush alive with its owner. A repeated
        // state notification must not replace every navigation label's paint
        // with a new but identical brush and queue seven unrelated redraws.
        if (renderedForeground == null || !renderedForeground.Color.Equals(foreground.Color)
            || renderedForeground.Opacity != foreground.Opacity) renderedForeground = foreground;
        if (CurrentLabel == null || renderedSelected != selected)
        {
            // Font weight is part of NativeLabel's immutable production layout.
            // Replace only on actual selection changes; hovering recolors the
            // same mounted label and cannot create a second visible text node.
            var label = new NativeLabel(text, FontFamilies.UI, 14, selected ? (ushort)600 : (ushort)400,
                locale, 14 * 1.6) { Foreground = renderedForeground };
            label.Loaded += (_, _) => { if (ReferenceEquals(CurrentLabel, label)) ApplyForeground(); };
            Children.Clear(); Children.Add(label);
            CurrentLabel = label; renderedSelected = selected;
        }
        else ApplyForeground();
    }

    private void ApplyForeground()
    {
        if (CurrentLabel == null || renderedForeground == null) return;
        // The modal/ItemsView can realize this subtree after the first state
        // paint. Restore an absent local foreground at that real lifecycle
        // boundary, without replacing a current equivalent brush on hover.
        if (CurrentLabel.Foreground is not SolidColorBrush actual || !actual.Color.Equals(renderedForeground.Color)
            || actual.Opacity != renderedForeground.Opacity) CurrentLabel.Foreground = renderedForeground;
    }
}
