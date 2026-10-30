using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;

namespace Relic;

// These are the production objects that paint one avatar. Retaining the actual
// parts makes the decorative border's owner explicit without changing its paint,
// accessibility name, event routing, or layout.
public sealed class NativeAvatarPicture : PersonPicture
{
    internal UIElement Paint { get; }
    internal ControlTemplate PaintTemplate { get; }
    internal NativeReplyAvatarFrame? ReplyFrame { get; private set; }

    internal NativeAvatarPicture(string label, UIElement paint, int size)
    {
        Paint = paint;
        PaintTemplate = (ControlTemplate)XamlReader.Load("<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' TargetType='PersonPicture'><ContentPresenter Content='{TemplateBinding Tag}'/></ControlTemplate>");
        DisplayName = label; Tag = Paint; Width = Height = size; IsTabStop = false;
        Template = PaintTemplate;
    }

    internal bool HasCurrentPaint => ReferenceEquals(Tag, Paint) && ReferenceEquals(Template, PaintTemplate);

    internal Border WrapReply(Grid layout, Brush border)
    {
        ReplyFrame = new NativeReplyAvatarFrame(layout, this, border);
        return ReplyFrame.Surface;
    }
}

public sealed class NativeOrganizationAvatarPaint : Grid
{
    internal Border Surface { get; }
    internal TextBlock Initial { get; }
    internal Rectangle? SubgroupOutline { get; }
    internal Border? CabinetRing { get; }

    internal NativeOrganizationAvatarPaint(Border surface, TextBlock initial, Rectangle? subgroupOutline, Border? cabinetRing)
    {
        Width = Height = 22; Surface = surface; Initial = initial;
        SubgroupOutline = subgroupOutline; CabinetRing = cabinetRing;
        if (CabinetRing != null) Children.Add(CabinetRing);
        Children.Add(Surface);
        if (SubgroupOutline != null) Children.Add(SubgroupOutline);
    }

    internal bool HasCurrentParts => ReferenceEquals(Surface.Child, Initial)
        && Children.Count == 1 + (SubgroupOutline == null ? 0 : 1) + (CabinetRing == null ? 0 : 1)
        && ReferenceEquals(Children[CabinetRing == null ? 0 : 1], Surface)
        && (CabinetRing == null || ReferenceEquals(Children[0], CabinetRing))
        && (SubgroupOutline == null || ReferenceEquals(Children[Children.Count - 1], SubgroupOutline));
}

// Border itself is sealed. This production composition retains its actual
// native Border instead of introducing a new layout wrapper or template.
public sealed class NativeReplyAvatarFrame
{
    internal Border Surface { get; }
    internal Grid Layout { get; }
    internal NativeAvatarPicture Picture { get; }

    internal NativeReplyAvatarFrame(Grid layout, NativeAvatarPicture picture, Brush border)
    {
        Layout = layout; Picture = picture;
        Surface = new Border { Child = Layout, BorderThickness = new Thickness(2), BorderBrush = border,
            CornerRadius = new CornerRadius(6), Margin = new Thickness(0, 0, -4, 0) };
    }

    internal bool HasCurrentParts => ReferenceEquals(Surface.Child, Layout) && Layout.Children.Count == 1
        && ReferenceEquals(Layout.Children[0], Picture) && ReferenceEquals(Picture.ReplyFrame, this) && Picture.HasCurrentPaint;
}
