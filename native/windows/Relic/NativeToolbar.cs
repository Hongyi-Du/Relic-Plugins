using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace Relic;

// Retain the actual CommandBar command model, keyboard navigation and peers.
// Its stock theme's 48px compact minimum and reserved overflow column do not
// fit this app's 39px titlebar; local template-part values own that layout.
internal sealed class NativeToolbar : CommandBar
{
    public NativeToolbar() => DefaultStyleKey = typeof(CommandBar);

    protected override void OnApplyTemplate()
    {
        base.OnApplyTemplate();
        Height = MaxHeight = 39; MinHeight = 0;
        if (GetTemplateChild("ContentRoot") is Grid content)
        {
            content.Height = content.MaxHeight = 39; content.MinHeight = 0;
            if (content.ColumnDefinitions.Count > 1)
            {
                var overflow = content.ColumnDefinitions[1];
                overflow.MinWidth = 0; overflow.Width = new GridLength(0);
            }
        }
        if (GetTemplateChild("PrimaryItemsControl") is ItemsControl primary)
        {
            primary.Height = primary.MaxHeight = 39; primary.MinHeight = 0;
            primary.VerticalAlignment = VerticalAlignment.Top;
        }
    }
}
