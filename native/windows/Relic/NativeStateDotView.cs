using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;

namespace Relic;

// One production status indicator with two actual paint layers. The inner
// ring is not a second state indicator or an independently interactive item.
internal sealed class NativeStateDotView : Grid
{
    internal Ellipse Surround { get; }
    internal Ellipse VacancyRing { get; }

    internal NativeStateDotView(Brush surround, Brush vacancy)
    {
        Width = Height = 10;
        UseLayoutRounding = false;
        Surround = new Ellipse
        {
            Width = 10, Height = 10, Stroke = surround, StrokeThickness = 2,
            Fill = new SolidColorBrush(Colors.Transparent), UseLayoutRounding = false,
            HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center
        };
        VacancyRing = new Ellipse
        {
            Width = 6, Height = 6, Stroke = vacancy, StrokeThickness = 1.5, UseLayoutRounding = false,
            HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center
        };
        Children.Add(Surround);
        Children.Add(VacancyRing);
    }

    internal bool HasCurrentPaintChildren => Children.Count == 2
        && ReferenceEquals(Children[0], Surround) && ReferenceEquals(Children[1], VacancyRing);

    internal IEnumerable<(string Role, Ellipse Paint)> OwnedPaintLayers()
    {
        yield return (nameof(Surround), Surround);
        yield return (nameof(VacancyRing), VacancyRing);
    }
}
