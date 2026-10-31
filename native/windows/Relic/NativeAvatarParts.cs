using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using System.Text.Json.Nodes;

namespace Relic;

// These are the production objects that paint one avatar. Retaining the actual
// parts makes the decorative border's owner explicit without changing its paint,
// accessibility name, event routing, or layout.
// PersonPicture must remain the native runtime class. Deriving it in the
// current WinUI projection makes its native Style target appear as Control.
// This non-UI composition retains that real instance and its real paint.
public sealed class NativeAvatarPicture
{
    internal PersonPicture Picture { get; }
    internal UIElement Paint { get; }
    internal ControlTemplate PaintTemplate { get; }
    internal NativeReplyAvatarFrame? ReplyFrame { get; private set; }

    internal NativeAvatarPicture(string label, UIElement paint, int size)
    {
        Paint = paint;
        PaintTemplate = (ControlTemplate)XamlReader.Load("<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' TargetType='PersonPicture'><ContentPresenter Content='{TemplateBinding Tag}'/></ControlTemplate>");
        Picture = new PersonPicture { DisplayName = label, Tag = Paint, Width = size, Height = size,
            // The retained paint owns any real avatar border/ring. This native
            // host is borderless, including its otherwise inherited SDK value.
            BorderThickness = new Thickness(0), IsTabStop = false, Template = PaintTemplate };
        NativeAvatarLifetimeHolder.Attach(this);
    }

    internal bool HasCurrentPaint => ReferenceEquals(Picture.Tag, Paint) && ReferenceEquals(Picture.Template, PaintTemplate);

    internal Border WrapReply(Grid layout, Brush border)
    {
        ReplyFrame = new NativeReplyAvatarFrame(layout, this, border);
        return ReplyFrame.Surface;
    }
}

// Native XAML owns this DependencyObject through the actual PersonPicture's
// property store. A managed weak key does not provide that lifetime guarantee.
// This is not a visual, a global root, or an alternate Tag/template payload.
// RegisterAttached accepts an object-valued property; the stored value is a
// real DependencyObject with WinRT identity, not an arbitrary managed payload.
// https://learn.microsoft.com/windows/apps/develop/platform/xaml/custom-attached-properties
// https://learn.microsoft.com/windows/windows-app-sdk/api/winrt/microsoft.ui.xaml.dependencyproperty.registerattached
public sealed class NativeAvatarLifetimeHolder : DependencyObject
{
    private static readonly DependencyProperty CompositionLifetimeProperty = DependencyProperty.RegisterAttached(
        "CompositionLifetime", typeof(object), typeof(NativeAvatarLifetimeHolder), new PropertyMetadata(null));
    internal NativeAvatarPicture Composition { get; }

    private NativeAvatarLifetimeHolder(NativeAvatarPicture composition) => Composition = composition;

    internal static void Attach(NativeAvatarPicture composition)
    {
        var picture = composition.Picture;
        picture.SetValue(CompositionLifetimeProperty, new NativeAvatarLifetimeHolder(composition));
        var observed = Read(picture);
        if (!observed.IsBound || !ReferenceEquals(observed.Composition, composition))
            throw new InvalidOperationException("The avatar's native property did not retain its actual composition: " + observed.Status);
    }

    internal static NativeAvatarLifetimeLookup Read(PersonPicture picture)
    {
        object? value = null, local = null;
        var api = "DependencyObject.GetValue";
        try
        {
            value = picture.GetValue(CompositionLifetimeProperty);
            api = "DependencyObject.ReadLocalValue";
            local = picture.ReadLocalValue(CompositionLifetimeProperty);
            var localUnset = ReferenceEquals(local, DependencyProperty.UnsetValue);
            var sameValue = ReferenceEquals(value, local);
            var holder = value as NativeAvatarLifetimeHolder;
            var composition = holder?.Composition;
            var sameOwner = composition != null && ReferenceEquals(composition.Picture, picture);
            var currentPaint = composition?.HasCurrentPaint;
            var status = value == null ? "absent" : holder == null ? "wrong-holder"
                : localUnset || !sameValue ? "local-value-mismatch" : !sameOwner ? "wrong-owner"
                : currentPaint != true ? "detached-paint-or-template" : "bound";
            return new(status, composition, value?.GetType().FullName, local?.GetType().FullName,
                localUnset, sameValue, sameOwner, currentPaint, null, null, null);
        }
        catch (Exception error)
        {
            return new("lookup-failed", null, value?.GetType().FullName, local?.GetType().FullName,
                null, null, null, null, api, error.HResult, error.ToString());
        }
    }
}

internal sealed record NativeAvatarLifetimeLookup(string Status, NativeAvatarPicture? Composition,
    string? ValueType, string? LocalValueType, bool? LocalValueIsUnset, bool? ValueSameAsLocal,
    bool? CompositionPictureIsOwner, bool? CurrentPaintAndTemplate, string? FailureApi, int? HResult, string? Error)
{
    internal bool IsBound => Status == "bound";
    internal JsonObject Evidence() => new()
    {
        ["source"] = "Actual PersonPicture private attached DependencyProperty lifetime holder",
        ["status"] = Status, ["value_runtime_type"] = ValueType, ["local_value_runtime_type"] = LocalValueType,
        ["local_value_is_unset"] = LocalValueIsUnset, ["value_same_as_local"] = ValueSameAsLocal,
        ["composition_runtime_type"] = Composition?.GetType().FullName,
        ["composition_picture_is_owner"] = CompositionPictureIsOwner,
        ["current_paint_and_template"] = CurrentPaintAndTemplate,
        ["failure_api"] = FailureApi, ["hresult"] = HResult, ["error"] = Error,
        ["observed_at_utc"] = DateTimeOffset.UtcNow.ToString("O"),
        ["lookup_modified_metadata"] = false
    };
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
        && ReferenceEquals(Layout.Children[0], Picture.Picture) && ReferenceEquals(Picture.ReplyFrame, this) && Picture.HasCurrentPaint;
}

public sealed partial class MainWindow
{
    private Border WrapReplyAvatar(Grid layout, Brush border)
    {
        var picture = layout.Children.OfType<PersonPicture>().Single();
        var lookup = NativeAvatarLifetimeHolder.Read(picture);
        if (!lookup.IsBound || lookup.Composition == null)
            throw new InvalidOperationException("The reply avatar has no bound native-owned production composition: " + lookup.Status);
        return lookup.Composition.WrapReply(layout, border);
    }
}
