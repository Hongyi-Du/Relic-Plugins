using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Animation;
using Microsoft.UI.Xaml.Shapes;
using Relic.Core;
using System.Text.Json.Nodes;
using Windows.UI.ViewManagement;

namespace Relic;

public sealed partial class MainWindow
{
    private UIElement LiveBubble(string text, bool mine = false)
    {
        var bubble = new Border { Child = Rich(text), Padding = new Thickness(13, 9, 13, 9),
            CornerRadius = mine ? new CornerRadius(14, 4, 14, 14) : new CornerRadius(4, 14, 14, 14),
            Background = mine ? MessageTint() : Paint("F4F3F0", "2A2A28") };
        var layout = new MessageBubbleLayout { MaxWidth = 720, HorizontalAlignment = mine ? HorizontalAlignment.Right : HorizontalAlignment.Left };
        layout.Children.Add(bubble); return layout;
    }

    private UIElement LivePrompt(string text)
    {
        var row = new Grid { ColumnSpacing = 10, Margin = new Thickness(0, preferences.Text("density") == "compact" ? 7 : 14, 0, 0) };
        row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); row.ColumnDefinitions.Add(new() { Width = new GridLength(36) });
        var portrait = (FrameworkElement)Avatar(preferences.Text("avatar"), Display("human"), 36); portrait.VerticalAlignment = VerticalAlignment.Top;
        ToolTipService.SetToolTip(portrait, Display("human")); Grid.SetColumn(portrait, 1); row.Children.Add(portrait);
        row.Children.Add(LiveBubble(text, true)); return row;
    }

    private UIElement LiveActions(StackPanel actions)
    {
        var header = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, Padding = new Thickness(10, 6, 10, 6) };
        var rotation = new RotateTransform { Angle = 90 };
        var chevron = (ReferenceVectorIcon)ReferenceIcon("chev", 13); chevron.Foreground = Muted; chevron.VerticalAlignment = VerticalAlignment.Center;
        chevron.RenderTransformOrigin = new(.5, .5); chevron.RenderTransform = rotation; header.Children.Add(chevron);
        var label = OverviewText(T("live.turn_actions"), 12.5, weight: 600); label.Foreground = Paint("5A5853", "B8B5AE"); label.IsTextSelectionEnabled = false; header.Children.Add(label);
        var disclosure = DetailsDisclosure(header, new Border { Child = actions, BorderBrush = Line, BorderThickness = new Thickness(0, 1, 0, 0) }, true);
        disclosure.RegisterPropertyChangedCallback(Expander.IsExpandedProperty, (_, _) => rotation.Angle = disclosure.IsExpanded ? 90 : 0);
        var width = new LiveWidthLimit { Limit = 720 };
        width.Children.Add(new Border { Child = disclosure, Background = Paint("FFFFFF", "1F1F1E"), BorderBrush = Line, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(10) }); return width;
    }

    private UIElement LiveToolStep(JsonNode? item)
    {
        var state = item.Text("status");
        var header = new Grid { ColumnSpacing = 8, Padding = new Thickness(12, 3, 10, 3) };
        header.ColumnDefinitions.Add(new() { Width = new GridLength(7) }); header.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); header.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        header.Children.Add(new Ellipse { Width = 7, Height = 7, VerticalAlignment = VerticalAlignment.Center, Fill = state == "completed" ? Paint("3E9B5E", "6CC287") : state == "failed" ? Paint("C2412D", "EE8A78") : Paint("B8B5AF", "5F5D58") });
        var title = OverviewText(TraceClip(item.Text("title"), 60), 12.5, weight: 600); title.TextWrapping = TextWrapping.NoWrap; title.IsTextSelectionEnabled = false; title.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(title, 1); header.Children.Add(title);
        var status = OverviewText(state switch { "pending" => T("live.pending"), "in_progress" => T("task.working"), "completed" => T("task.done"), "failed" => T("common.failed"), _ => state }, 11, true);
        status.TextWrapping = TextWrapping.NoWrap; status.IsTextSelectionEnabled = false; status.HorizontalAlignment = HorizontalAlignment.Right; status.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(status, 2); header.Children.Add(status);
        var source = new StackPanel { Padding = item.Text("text").Length > 0 ? new Thickness(27, 2, 10, 8) : new Thickness(0) };
        if (item.Text("text").Length > 0)
        {
            var text = OverviewText(item.Text("text"), 11.5, lineHeight: 17.825); text.FontFamily = new FontFamily("Cascadia Code");
            var scroll = Scroll(text); scroll.MaxHeight = 344;
            source.Children.Add(new Border { Child = scroll, Background = Paint("F6F5F2", "232321"), BorderBrush = Line, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(7), Padding = new Thickness(9, 7, 9, 7), MaxHeight = 360 });
        }
        header.PointerEntered += (_, _) => header.Background = Paint("F8F7F5", "191918");
        header.PointerExited += (_, _) => header.Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent);
        return DetailsDisclosure(header, source);
    }

    private UIElement LivePermissionCard(JsonNode? item)
    {
        var content = new StackPanel { Spacing = 8 };
        var heading = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 };
        var bell = (ReferenceVectorIcon)ReferenceIcon("bell", 14); bell.Foreground = Paint("B7791F", "E2B15A"); bell.VerticalAlignment = VerticalAlignment.Center; heading.Children.Add(bell);
        var label = OverviewText(T("perm.ask"), 12, weight: 700); label.Foreground = bell.Foreground; heading.Children.Add(label); content.Children.Add(heading);
        content.Children.Add(OverviewText(item.Text("title"), 12.5));
        var choices = new ActionRow { Spacing = 6 };
        foreach (var option in item.Rows("options"))
        {
            var id = item.Text("id"); var choice = option.Text("id");
            var button = OverviewAction(option.Text("name").Length > 0 ? option.Text("name") : option.Text("kind"), async () =>
            {
                try { await api!.Post("/api/permission/" + Client.Segment(id), new { option = choice }); await Refresh(); }
                catch (Exception ex) { Note(ex.Message); }
            }, option.Text("kind").StartsWith("allow", StringComparison.Ordinal));
            button.BorderThickness = new Thickness(1); choices.Children.Add(button);
        }
        content.Children.Add(choices);
        var width = new LiveWidthLimit { Limit = 620 };
        width.Children.Add(new Border { Child = content, Padding = new Thickness(12, 10, 12, 10), CornerRadius = new CornerRadius(12),
            Background = Paint("FBF3E2", "3A3020"), BorderBrush = OverviewAlpha(Paint("B7791F", "E2B15A"), .45), BorderThickness = new Thickness(1) }); return width;
    }

    private UIElement LiveErrorNotice(string value)
    {
        var text = OverviewText(value, 12); text.Foreground = Paint("C2412D", "EE8A78"); text.TextAlignment = TextAlignment.Center;
        var layout = new CenteredFractionLayout { Fraction = .86, Margin = new Thickness(0, 8, 0, 8) };
        layout.Children.Add(new Border { Child = text, Padding = new Thickness(10, 2, 10, 2), CornerRadius = new CornerRadius(10), Background = Paint("F8F7F5", "191918") }); return layout;
    }

    private UIElement LiveTyping()
    {
        var dots = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4, Padding = new Thickness(2, 6, 2, 6), HorizontalAlignment = HorizontalAlignment.Left };
        var settings = new UISettings(); var animation = new Storyboard();
        for (var i = 0; i < 3; i++)
        {
            var dot = new Ellipse { Width = 6, Height = 6, Fill = Muted }; dots.Children.Add(dot);
            var blink = new DoubleAnimationUsingKeyFrames { Duration = TimeSpan.FromSeconds(1.2), BeginTime = TimeSpan.FromSeconds(i * .2), RepeatBehavior = RepeatBehavior.Forever };
            foreach (var (at, opacity) in new[] { (0d, .25), (.48, 1d), (.96, .25), (1.2, .25) })
                blink.KeyFrames.Add(new SplineDoubleKeyFrame { KeyTime = KeyTime.FromTimeSpan(TimeSpan.FromSeconds(at)), Value = opacity, KeySpline = new KeySpline { ControlPoint1 = new(.25, .1), ControlPoint2 = new(.25, 1) } });
            Storyboard.SetTarget(blink, dot); Storyboard.SetTargetProperty(blink, "Opacity"); animation.Children.Add(blink);
        }
        void UpdateMotion()
        {
            animation.Stop(); foreach (UIElement dot in dots.Children) dot.Opacity = 1;
            if (dots.IsLoaded && settings.AnimationsEnabled) animation.Begin();
        }
        var canObserveMotion = Windows.Foundation.Metadata.ApiInformation.IsEventPresent("Windows.UI.ViewManagement.UISettings", "AnimationsEnabledChanged");
        void MotionChanged(UISettings sender, UISettingsAnimationsEnabledChangedEventArgs args) => dots.DispatcherQueue.TryEnqueue(UpdateMotion);
        dots.Loaded += (_, _) => { if (OperatingSystem.IsWindowsVersionAtLeast(10, 0, 19041) && canObserveMotion) settings.AnimationsEnabledChanged += MotionChanged; UpdateMotion(); };
        dots.Unloaded += (_, _) => { if (OperatingSystem.IsWindowsVersionAtLeast(10, 0, 19041) && canObserveMotion) settings.AnimationsEnabledChanged -= MotionChanged; animation.Stop(); };
        return dots;
    }
}

// Block cards fill their available width, capped and left-aligned just like the
// reference. Measure uses this pass's width so resized scenes cannot retain a
// previous window's dimensions.
public sealed class LiveWidthLimit : Panel
{
    public double Limit { get; init; }
    protected override Windows.Foundation.Size MeasureOverride(Windows.Foundation.Size available)
    {
        if (Children.Count == 0) return default;
        var width = Math.Min(Limit, available.Width); Children[0].Measure(new(width, double.PositiveInfinity));
        return new(width, Children[0].DesiredSize.Height);
    }
    protected override Windows.Foundation.Size ArrangeOverride(Windows.Foundation.Size final)
    {
        if (Children.Count > 0) Children[0].Arrange(new(0, 0, Math.Min(Limit, final.Width), final.Height));
        return final;
    }
}
