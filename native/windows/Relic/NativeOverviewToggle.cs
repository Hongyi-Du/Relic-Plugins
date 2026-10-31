using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;

namespace Relic;

// One native ToggleButton owns the switch behavior and its decorative parts.
// The thumb has no input handler or separate action; pointer input reaches the
// track/ToggleButton, while keyboard and UIA Toggle remain on the owner.
public sealed class NativeOverviewToggle : ToggleButton
{
    internal Border Track { get; }
    internal NativeShadowPanel ThumbShadow { get; }
    internal Border Thumb { get; }
    private readonly Func<Brush> onBrush;
    private readonly Func<Brush> offBrush;

    internal NativeOverviewToggle(bool enabled, bool value, Func<Brush> on, Func<Brush> off)
    {
        onBrush = on; offBrush = off;
        Thumb = new Border { Background = new SolidColorBrush(Microsoft.UI.Colors.White),
            CornerRadius = new CornerRadius(7), IsHitTestVisible = false };
        ThumbShadow = new NativeShadowPanel(Thumb)
            { Width = 14, Height = 14, HorizontalAlignment = HorizontalAlignment.Left };
        ThumbShadow.SetShadows([new NativeShadowLayer(0, 1, 2, Microsoft.UI.Colors.Black, .25f)]);
        Track = new Border { Width = 32, Height = 18, CornerRadius = new CornerRadius(9), Child = ThumbShadow };
        IsChecked = value; IsEnabled = enabled; Content = Track;
        Width = 32; Height = 18; MinWidth = MinHeight = 0; Padding = new Thickness(0);
        VerticalAlignment = VerticalAlignment.Center;
        Background = BorderBrush = new SolidColorBrush(Microsoft.UI.Colors.Transparent);
        BorderThickness = new Thickness(0);
        Template = (ControlTemplate)XamlReader.Load("<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' TargetType='ToggleButton'><ContentPresenter Content='{TemplateBinding Content}' Padding='0'/></ControlTemplate>");
        Checked += (_, _) => PaintParts(); Unchecked += (_, _) => PaintParts(); Indeterminate += (_, _) => PaintParts();
        PaintParts();
    }

    private void PaintParts()
    {
        var on = IsChecked == true;
        Track.Background = on ? onBrush() : offBrush();
        ThumbShadow.Margin = new Thickness(on ? 16 : 2, 2, 0, 2);
    }

    internal bool HasCurrentParts => ReferenceEquals(Content, Track)
        && ReferenceEquals(Track.Child, ThumbShadow) && ReferenceEquals(ThumbShadow.Surface, Thumb)
        && ThumbShadow.Children.Contains(Thumb) && Thumb.Child == null;
}
