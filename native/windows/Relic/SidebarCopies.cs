using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Documents;
using Microsoft.UI.Xaml.Media;
using Relic.Core;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private readonly CommandBar toolbar = new() { DefaultLabelPosition = CommandBarDefaultLabelPosition.Collapsed, IsOpen = false, OverflowButtonVisibility = CommandBarOverflowButtonVisibility.Collapsed, Height = 40 };
    private readonly StackPanel navigationButtons = new() { Orientation = Orientation.Horizontal, Spacing = 2, Padding = new Thickness(6, 4, 2, 4) };
    private StackPanel? copiesBody;
    private readonly HashSet<string> expandedCopies = [];
    private HashSet<string>? knownCopies;
    private void DrawToolbar()
    {
        toolbar.PrimaryCommands.Clear();
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(toolbar, T("page.titlebar"));
        void Action(string glyph, string label, string tip, Func<Task> action, bool enabled = true, int badge = 0, bool selected = false, bool alert = false)
        {
            var b = QuietButton("", action); var content = new Grid(); content.Children.Add(Glyph(glyph)); b.Content = content; b.IsEnabled = enabled; b.Width = 30; b.Height = 28; b.Padding = new Thickness(0); b.CornerRadius = new CornerRadius(7); b.Foreground = alert ? Paint("B7791F", "E2B15A") : Paint("5A5853", "B8B5AE");
            if (selected) b.Background = Paint("E7E5DF", "2F2E2B");
            if (badge > 0) content.Children.Add(new Border { MinWidth = 15, Height = 15, Padding = new Thickness(4, 0, 4, 0), CornerRadius = new CornerRadius(8), Background = Paint("C2412D", "EE8A78"), HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Top, Child = new TextBlock { Text = badge.ToString(), FontSize = 10, FontWeight = Microsoft.UI.Text.FontWeights.Bold, Foreground = Paint("FFFFFF"), LineHeight = 15, LineStackingStrategy = LineStackingStrategy.BlockLineHeight, HorizontalAlignment = HorizontalAlignment.Center } });
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(b, tip);
            ToolTipService.SetToolTip(b, tip); toolbar.PrimaryCommands.Add(new AppBarElementContainer { Content = b });
        }
        navigationButtons.Children.Clear(); var brand = new Border { Width = 20, Height = 20, Margin = new Thickness(5, 0, 7, 0), CornerRadius = new CornerRadius(5), Background = Ink, Child = new TextBlock { Text = "R", FontSize = 12, FontWeight = Microsoft.UI.Text.FontWeights.Bold, Foreground = Paint("FFFFFF", "1B1B1A"), HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center } }; ToolTipService.SetToolTip(brand, T("page.titlebar")); navigationButtons.Children.Add(brand); navigationButtons.Children.Add(IconButton("\uE700", "appmenu.sidebar", ToggleSide, T(sideOpen ? "appbar.hide_sidebar" : "appbar.show_sidebar")));
        var back = IconButton("\uE72B", "appbar.back", () => Navigate(-1)); back.IsEnabled = historyIndex > 0; navigationButtons.Children.Add(back);
        var forward = IconButton("\uE72A", "appbar.forward", () => Navigate(1)); forward.IsEnabled = historyIndex + 1 < history.Count; navigationButtons.Children.Add(forward);
        appTitle.Text = org.Length == 0 ? "Relic" : snap["org"].Text("name") + " · " + (member.Length == 0 ? T("common.group_chat") : member == snap["org"].Text("secretary") ? T("common.secretary") : Display(member)); appTitle.Foreground = Muted; toolbar.Content = null; ToolTipService.SetToolTip(appTitle, appTitle.Text);
        var count = snap.Rows("decisions").Count;
        Action("\uE7BA", T("decision.title"), T(count > 0 ? "appbar.decisions" : "appbar.no_decisions", ("n", count)), () => SetPane("overview"), badge: count, alert: count > 0);
        var unread = copies.Count(c => !c.Flag("read"));
        Action("\uE715", T("cc.title"), T(unread > 0 ? "appbar.cc" : "appbar.cc_none", ("n", unread)), Copies, badge: unread);
        toolbar.PrimaryCommands.Add(new AppBarElementContainer { Content = new Border { Width = 1, Height = 16, Background = Paint("DEDBD4", "3A3936"), Margin = new Thickness(4, 0, 4, 0) } });
        int i = 1;
        foreach (var (id, key, glyph) in new[] { ("overview", "panel.overview", "\uE8FD"), ("workspace", "panel.workspace", "\uE8B7"), ("files", "common.file", "\uE8A5") })
            Action(glyph, T(key), T("appbar.pane_shortcut", ("pane", T(key)), ("key", "Alt+" + i++)), () => pane == id && panelOpen ? TogglePanel() : SetPane(id), selected: panelOpen && pane == id);
    }
    private void DrawSidebar()
    {
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(sidebarSurface, T("page.side"));
        searchSurface.Children.Clear(); searchSurface.ColumnDefinitions.Clear(); side.Children.Clear(); sideTools.Children.Clear(); sidebarFooter.Children.Clear();
        side.Padding = new Thickness(8, 4, 8, 12); side.Spacing = 0;
        var create = QuietButton("", CreateOrg); create.HorizontalAlignment = HorizontalAlignment.Stretch; create.Height = 34; create.MinHeight = 0; create.Padding = new Thickness(10, 0, 10, 0); create.CornerRadius = new CornerRadius(8);
        var createLabel = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10, VerticalAlignment = VerticalAlignment.Center }; var createIcon = (ReferenceVectorIcon)Glyph("\uE70F", 17); createIcon.Foreground = Paint("5A5853", "B8B5AE"); createLabel.Children.Add(createIcon); var createText = OverviewText(T("common.new_org"), 14); createText.IsTextSelectionEnabled = false; createLabel.Children.Add(createText); create.Content = createLabel; sideTools.Children.Add(create);
        searchSurface.Margin = new Thickness(0, 2, 0, 0); searchSurface.Height = 34; searchSurface.Padding = new Thickness(10, 0, 10, 0); searchSurface.ColumnSpacing = 8; searchSurface.CornerRadius = new CornerRadius(8); searchSurface.Background = Paint("EFEEEA", "262624");
        searchSurface.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); searchSurface.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); searchSurface.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        var searchIcon = (ReferenceVectorIcon)Glyph("\uE721", 15); searchIcon.Foreground = Muted; searchIcon.VerticalAlignment = VerticalAlignment.Center; searchIcon.IsHitTestVisible = false; searchSurface.Children.Add(searchIcon);
        search.Margin = new Thickness(0); search.MinHeight = 0; search.Height = 22.4; search.VerticalAlignment = VerticalAlignment.Center; search.FontSize = 14; search.Padding = new Thickness(0); search.BorderThickness = new Thickness(0); search.Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.Transparent); Grid.SetColumn(search, 1); searchSurface.Children.Add(search);
        var searchMic = Microphone(search); searchMic.Foreground = Paint("5A5853", "B8B5AE"); searchMic.Width = searchMic.Height = 32; searchMic.MinHeight = 0; searchMic.Padding = new Thickness(0); searchMic.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(searchMic, 2); searchSurface.Children.Add(searchMic); sideTools.Children.Add(searchSurface);
        var caption = TwoColumns(OverviewText(T("page.tree"), 12, true), OverviewText(orgs.Count > 0 ? orgs.Count.ToString() : "", 12, true)); caption.Margin = new Thickness(10, 14, 10, 6); side.Children.Add(caption);
        var tree = new StackPanel(); side.Children.Add(tree);
        var template = (ControlTemplate)Microsoft.UI.Xaml.Markup.XamlReader.Load("<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' TargetType='ListViewItem'><ContentPresenter Content='{TemplateBinding Content}' Background='{TemplateBinding Background}' Padding='{TemplateBinding Padding}' CornerRadius='{TemplateBinding CornerRadius}' HorizontalContentAlignment='Stretch' VerticalContentAlignment='Center'/></ControlTemplate>");
        ListView Rows()
        {
            var list = new ListView { SelectionMode = ListViewSelectionMode.Single, IsItemClickEnabled = true, HorizontalContentAlignment = HorizontalAlignment.Stretch, Padding = new Thickness(0), BorderThickness = new Thickness(0) };
            ScrollViewer.SetHorizontalScrollBarVisibility(list, ScrollBarVisibility.Disabled); ScrollViewer.SetVerticalScrollBarVisibility(list, ScrollBarVisibility.Disabled);
            list.ItemClick += async (_, e) => { if (e.ClickedItem is ListViewItem item && item.Tag is Func<Task> action) await Run(action); }; return list;
        }
        void Add(ListView list, UIElement content, Func<Task> action, bool selected, int indent = 0, bool chat = false)
        {
            var background = selected ? Paint("E7E5DF", "2F2E2B") : new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.Transparent);
            var row = new ListViewItem { Content = content, Tag = action, Template = template, Padding = new Thickness(8 + indent, 6, 8, 6), Margin = new Thickness(0, 0, 0, chat ? 1 : 0),
                MinHeight = chat ? 0 : 34, HorizontalContentAlignment = HorizontalAlignment.Stretch, CornerRadius = new CornerRadius(8), Background = background };
            row.PointerEntered += (_, _) => row.Background = selected ? background : Paint("EFEEEA", "262624"); row.PointerExited += (_, _) => row.Background = background;
            list.Items.Add(row); if (selected) list.SelectedItem = row;
        }
        var visited = new HashSet<string>(); var query = search.Text.Trim(); bool Match(string value) => value.Contains(query, StringComparison.OrdinalIgnoreCase);
        void Chat(ListView list, string who, string title, string subtitle, string avatar, string state = "", bool secretarySetup = false)
        {
            var key = who.Length == 0 ? "group" : "member:" + who; var id = org; var secretary = secretarySetup || who.Length > 0 && who == snap["org"].Text("secretary");
            var row = new Grid { ColumnSpacing = 9 }; row.ColumnDefinitions.Add(new() { Width = new GridLength(30) }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
            var face = SidebarFace(who, avatar, state, secretary); face.VerticalAlignment = VerticalAlignment.Center; row.Children.Add(face);
            var text = new StackPanel { Spacing = 0, VerticalAlignment = VerticalAlignment.Center };
            var heading = new Grid { ColumnSpacing = 6 }; heading.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); heading.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); heading.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
            var name = OverviewText(title, 13.3, weight: 550, lineHeight: 17.955); name.IsTextSelectionEnabled = false; name.TextWrapping = TextWrapping.NoWrap; name.TextTrimming = TextTrimming.CharacterEllipsis; heading.Children.Add(name);
            OverviewBadgeView? tag = null;
            if (secretary && !secretarySetup) tag = SidebarTag(OverviewRoleName(who, T("common.secretary")), true);
            else if (snap.Rows("members").FirstOrDefault(m => m.Text("name") == who).Flag("leader")) tag = SidebarTag(T("common.leader"), false);
            if (tag != null) { Grid.SetColumn(tag, 1); heading.Children.Add(tag); }
            heading.SizeChanged += (_, args) => { tag?.Measure(new Windows.Foundation.Size(double.PositiveInfinity, double.PositiveInfinity)); name.MaxWidth = Math.Max(0, args.NewSize.Width - (tag?.DesiredSize.Width + 6 ?? 0)); };
            text.Children.Add(heading);
            if (subtitle.Length > 0) { var sub = OverviewText(subtitle, 12, true, lineHeight: 16.2); sub.IsTextSelectionEnabled = false; sub.TextWrapping = TextWrapping.NoWrap; sub.TextTrimming = TextTrimming.CharacterEllipsis; text.Children.Add(sub); }
            Grid.SetColumn(text, 1); row.Children.Add(text);
            if (!secretary && who.Length > 0) { var record = snap.Rows("members").FirstOrDefault(m => m.Text("name") == who); ToolTipService.SetToolTip(row, who + (record.Text("role").Length > 0 ? " · " + record.Text("role") : "")); }
            var info = new StackPanel { Spacing = 3, HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Top, Padding = new Thickness(0, 1, 0, 0) };
            var head = snap["chats"]?[key]; var at = head?["last"].Text("at") ?? "";
            if (!secretary && who.Length > 0 && head == null) at = snap.Rows("members").FirstOrDefault(m => m.Text("name") == who).Text("doing_at");
            if (at.Length > 0) { var clock = OverviewText(ShortWhen(at), 11, true); clock.IsTextSelectionEnabled = false; info.Children.Add(clock); }
            var selected = !secretarySetup && who == member; var unread = selected || secretarySetup ? 0 : Unread(key);
            if (unread > 0)
            {
                var count = OverviewCount(unread); if (unread > 99 && count.Content is TextBlock countText) countText.Text = "99+"; count.HorizontalAlignment = HorizontalAlignment.Right; info.Children.Add(count);
            }
            Grid.SetColumn(info, 2); row.Children.Add(info); Add(list, row, secretarySetup ? SecretarySetup : () => Select(id, who), selected, chat: true);
        }
        void Node(JsonNode? item, int depth)
        {
            var id = item.Text("id"); if (!visited.Add(id)) return;
            var selected = id == org; var members = selected ? snap.Rows("members").Where(m => Match(m.Text("name")) || Match(m.Text("display")) || Match(m.Text("role"))).ToArray() : [];
            var orgMatch = Match(item.Text("name")) || Match(item.Text("purpose")); var children = orgs.Where(o => o.Text("parent") == id).ToArray(); var foldable = selected || children.Length > 0; var collapsed = query.Length == 0 && folded.Contains(id);
            if (query.Length == 0 || orgMatch || members.Length > 0)
            {
                void Fold() { if (!folded.Add(id)) folded.Remove(id); SaveViewState(); DrawSidebar(); }
                var row = new Grid { ColumnSpacing = 8 }; row.ColumnDefinitions.Add(new() { Width = new GridLength(14) }); row.ColumnDefinitions.Add(new() { Width = new GridLength(22) }); row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
                var arrow = (ReferenceVectorIcon)ReferenceIcon("chev", 14); arrow.Foreground = Muted; if (foldable && !collapsed) { arrow.RenderTransformOrigin = new(.5, .5); arrow.RenderTransform = new Microsoft.UI.Xaml.Media.RotateTransform { Angle = 90 }; }
                var arrowHit = new Border { Child = arrow, Padding = new Thickness(3), Margin = new Thickness(-3), CornerRadius = new CornerRadius(5), VerticalAlignment = VerticalAlignment.Center, Background = new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.Transparent) };
                arrowHit.PointerPressed += (_, e) => { if (foldable && e.GetCurrentPoint(arrowHit).Properties.IsLeftButtonPressed) { e.Handled = true; Fold(); } }; row.Children.Add(arrowHit);
                var badge = SidebarOrgFace(item!); badge.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(badge, 1); row.Children.Add(badge);
                var label = OverviewText(item.Text("name"), 13.44, weight: 600, lineHeight: 18.144); label.IsTextSelectionEnabled = false; label.MaxLines = 2; label.TextTrimming = TextTrimming.CharacterEllipsis; label.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(label, 2); row.Children.Add(label); ToolTipService.SetToolTip(row, item.Text("name") + (item.Text("purpose").Length > 0 ? "\n" + item.Text("purpose") : ""));
                if (!selected && item.Text("last_at").Length > 0) { var time = OverviewText(ShortWhen(item.Text("last_at")), 11.5, true); time.IsTextSelectionEnabled = false; time.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(time, 3); row.Children.Add(time); }
                var context = new MenuFlyout(); var chart = new MenuFlyoutItem { Text = T("appmenu.org_chart") }; chart.Click += async (_, _) => await Run(() => ShowChart(id)); context.Items.Add(chart); row.ContextFlyout = context;
                if (item.Text("status") is not ("" or "active")) row.Opacity = .55;
                var organizationRows = Rows(); Add(organizationRows, row, () => { if (selected) { Fold(); return Task.CompletedTask; } return Select(id); }, selected, depth * 16); tree.Children.Add(organizationRows);
                if (selected && !collapsed)
                {
                    var kids = new StackPanel(); var chats = Rows(); kids.Children.Add(chats);
                    if (orgMatch || Match(T("common.group_chat"))) Chat(chats, "", T("common.group_chat"), LastLine("group").Length > 0 ? LastLine("group") : T("side.group_sub"), "");
                    var secretary = snap["org"].Text("secretary"); var sec = snap.Rows("members").FirstOrDefault(m => m.Text("name") == secretary);
                    if (query.Length == 0 || Match(T("common.secretary")) || sec != null && members.Contains(sec))
                    {
                        if (secretary.Length == 0) Chat(chats, "", T("side.set_secretary"), T("side.secretary_hint"), "", secretarySetup: true);
                        else Chat(chats, secretary, T("common.secretary"), LastLine("member:" + secretary).Length > 0 ? LastLine("member:" + secretary) : sec.Text("doing").Length > 0 ? sec.Text("doing") : sec.Text("detail"), sec.Text("avatar"), sec.Text("state"));
                    }
                    foreach (var m in members.Where(m => !m.Flag("secretary"))) Chat(chats, m.Text("name"), Display(m.Text("name")), m.Text("doing").Length > 0 ? T("side.doing", ("doing", m.Text("doing"))) : LastLine("member:" + m.Text("name")).Length > 0 ? LastLine("member:" + m.Text("name")) : m.Text("role").Length > 0 ? m.Text("role") : MemberState(m.Text("state")), m.Text("avatar"), m.Text("state"));
                    var add = QuietButton("", AddMember); add.Foreground = Muted; add.HorizontalAlignment = HorizontalAlignment.Stretch; add.Padding = new Thickness(8, 6, 8, 6); add.MinHeight = 0; add.CornerRadius = new CornerRadius(8);
                    var addContent = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 }; addContent.Children.Add(ReferenceIcon("plus", 14)); var addText = OverviewText(T("common.add_member"), 12.5, true); addText.IsTextSelectionEnabled = false; addContent.Children.Add(addText); add.Content = addContent; kids.Children.Add(add);
                    tree.Children.Add(new Border { Child = kids, BorderThickness = new Thickness(1, 0, 0, 0), BorderBrush = Paint("DEDBD4", "3A3936"), Padding = new Thickness(14, 2, 0, 8), Margin = new Thickness(10, 0, 0, 0) });
                }
            }
            if (collapsed) return; foreach (var child in children) Node(child, depth + 1);
        }
        foreach (var item in orgs.Where(o => o.Text("parent").Length == 0 || !orgs.Any(p => p.Text("id") == o.Text("parent")))) Node(item, 0);
        if (orgs.Count == 0) side.Children.Add(new Border { Padding = new Thickness(10, 8, 10, 8), Child = OverviewText(T("side.no_orgs"), muted: true) });
        sidebarFooter.Padding = new Thickness(8); sidebarFooter.Spacing = 0; sidebarFooter.BorderBrush = Line; sidebarFooter.BorderThickness = new Thickness(0, 1, 0, 0);
        var profile = QuietButton("", Settings); profile.Padding = new Thickness(8, 6, 8, 6); profile.CornerRadius = new CornerRadius(8); profile.HorizontalAlignment = HorizontalAlignment.Stretch; ToolTipService.SetToolTip(profile, T("page.me")); Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(profile, T("page.me"));
        var identity = new Grid { ColumnSpacing = 10 }; identity.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); identity.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); var human = SidebarFace("human", preferences.Text("avatar"), "", false); human.VerticalAlignment = VerticalAlignment.Center; identity.Children.Add(human);
        var labels = new StackPanel(); var nameLabel = OverviewText(Display("human"), 13.3, weight: 600); nameLabel.TextWrapping = TextWrapping.NoWrap; nameLabel.TextTrimming = TextTrimming.CharacterEllipsis; labels.Children.Add(nameLabel); var profileLabel = OverviewText(T("side.profile"), 11.5, true); profileLabel.TextWrapping = TextWrapping.NoWrap; profileLabel.TextTrimming = TextTrimming.CharacterEllipsis; labels.Children.Add(profileLabel); Grid.SetColumn(labels, 1); identity.Children.Add(labels); profile.Content = identity;
        var settings = IconButton("\uE713", "common.settings", Settings); settings.Content = ReferenceIcon("gear", 18); settings.VerticalAlignment = VerticalAlignment.Center; var footer = TwoColumns(profile, settings); footer.ColumnSpacing = 4; sidebarFooter.Children.Add(footer);
    }
    private OverviewBadgeView SidebarTag(string text, bool secretary)
    {
        var label = OverviewText(text, 10.5, weight: 600, lineHeight: 18); label.IsTextSelectionEnabled = false; label.TextWrapping = TextWrapping.NoWrap; label.Foreground = secretary ? Paint("7058B8", "A894E0") : Accent;
        return new OverviewBadgeView { Content = label, FontSize = 10.5, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold, Foreground = label.Foreground, Background = secretary ? Paint("EFEBF8", "2E2A3D") : OverviewAlpha(Accent, .13), Padding = new Thickness(6, 0, 6, 0), CornerRadius = new CornerRadius(5), VerticalAlignment = VerticalAlignment.Center };
    }
    private PersonPicture SidebarOrgFace(JsonNode organization)
    {
        var badge = OverviewOrgBadge(organization, organization.Text("kind") == "subgroup");
        return SidebarPicture(organization.Text("name"), badge, 22);
    }
    private Grid SidebarFace(string who, string url, string state, bool secretary)
    {
        var label = who.Length > 0 ? Display(who) : T("common.group_chat");
        var painted = who.Length == 0 && !secretary ? ChatAvatar(false) : secretary && url.Length == 0 ? ChatAvatar(true) : AvatarPaint(url, label, 28);
        if (painted is Border face) { face.CornerRadius = new CornerRadius(8); if (face.Child is TextBlock initial) { initial.FontSize = 12; initial.FontWeight = new Windows.UI.Text.FontWeight { Weight = 650 }; } }
        var result = new Grid { Width = 28, Height = 28 }; result.Children.Add(SidebarPicture(label, painted, 28));
        if (state is not ("" or "idle"))
        {
            var color = state switch { "working" or "running" => Paint("3E9B5E", "6CC287"), "active" => Paint("75A782", "669572"), "waiting" or "starting" => Paint("B7791F", "E2B15A"), "error" => Paint("C2412D", "EE8A78"), _ => Paint("B8B5AF", "5F5D58") };
            var dot = new Microsoft.UI.Xaml.Shapes.Ellipse { Width = 10, Height = 10, Margin = new Thickness(0, 0, -2, -2), HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Bottom, Stroke = Paint("F8F7F5", "191918"), StrokeThickness = 2, Fill = state == "vacant" ? new Microsoft.UI.Xaml.Media.SolidColorBrush(Microsoft.UI.Colors.Transparent) : color }; result.Children.Add(dot);
            if (state == "vacant") result.Children.Add(new Microsoft.UI.Xaml.Shapes.Ellipse { Width = 6, Height = 6, HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Bottom, Stroke = color, StrokeThickness = 1.5 });
        }
        return result;
    }
    private PersonPicture SidebarPicture(string label, UIElement paint, int size) => new()
    {
        DisplayName = label, Tag = paint, Width = size, Height = size, IsTabStop = false,
        Template = (ControlTemplate)Microsoft.UI.Xaml.Markup.XamlReader.Load("<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' TargetType='PersonPicture'><ContentPresenter Content='{TemplateBinding Tag}'/></ControlTemplate>")
    };
    private async Task ShowCopies()
    {
        expandedCopies.Clear();
        copiesBody = new StackPanel { Spacing = 12, Padding = new Thickness(22), Width = Math.Min(760, root.ActualWidth - 32) };
        var body = copiesBody; DrawCopies();
        var scroll = Scroll(body); scroll.MaxHeight = root.ActualHeight - 56;
        var dialog = new ContentDialog { XamlRoot = root.XamlRoot, Content = scroll };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(dialog, T("cc.title"));
        dialog.Opened += (_, _) =>
        {
            dialog.Resources["ContentDialogPadding"] = new Thickness(0); dialog.Resources["ContentDialogMaxHeight"] = root.ActualHeight - 56;
            if (DialogPart<ContentPresenter>(dialog, "Content") is { } presenter) { presenter.Margin = new Thickness(0); presenter.Padding = new Thickness(0); }
            if (DialogPart<Border>(dialog, "BackgroundElement") is { } background) background.Padding = new Thickness(0);
            if (DialogPart<ScrollViewer>(dialog, "ContentScrollViewer") is { } wrapper) { wrapper.Padding = new Thickness(0); wrapper.VerticalScrollBarVisibility = ScrollBarVisibility.Disabled; }
            if (DialogPart<Grid>(dialog, "CommandSpace") is { } commands) commands.Visibility = Visibility.Collapsed;
        };
        await Dialog(dialog); if (copiesBody == body) copiesBody = null;
    }
    private void CopyNotifications()
    {
        var unread = copies.Where(c => !c.Flag("read")).Select(c => c.Text("id")).ToHashSet();
        if (!active && preferences.Flag("notify") && knownCopies != null && unread.Except(knownCopies).Any()) Notify(T("cc.notify", ("n", unread.Count)));
        knownCopies = unread;
    }
    private void DrawCopies()
    {
        if (copiesBody == null) return; var content = copiesBody; content.Children.Clear();
        var heading = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8, VerticalAlignment = VerticalAlignment.Center };
        var symbol = (ReferenceVectorIcon)ReferenceIcon("cc", 18); symbol.Foreground = Paint("5A5853", "B8B5AE"); heading.Children.Add(symbol);
        heading.Children.Add(OverviewText(T("cc.title"), 17, weight: 650));
        var unread = copies.Count(c => !c.Flag("read")); if (unread > 0) heading.Children.Add(OverviewCount(unread));
        var close = IconButton("\uE711", "common.close", () => { visibleDialog?.Hide(); return Task.CompletedTask; }); close.Width = close.Height = 30;
        content.Children.Add(OverviewHeading(heading, close));
        var intro = OverviewText(T("cc.intro"), 13, lineHeight: 22.1); intro.Foreground = Paint("5A5853", "B8B5AE"); content.Children.Add(intro);
        var list = new StackPanel { Spacing = 10 }; content.Children.Add(list);
        if (copies.Count == 0) list.Children.Add(new Border { Padding = new Thickness(10, 8, 10, 8), Child = OverviewText(T("cc.empty"), 14, true) });
        foreach (var c in copies)
        {
            var card = new StackPanel { Spacing = 8 }; var live = c.Text("status") == "active" && c.Text("org_status") is "" or "active";
            var badges = new ActionRow { Spacing = 6, HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Top };
            if (!c.Flag("read"))
            {
                var badge = OverviewChip(T("cc.unread")); badge.Background = OverviewAlpha(Accent, .13); badge.Foreground = Accent;
                if (badge.Content is TextBlock label) label.Foreground = Accent; badges.Children.Add(badge);
            }
            if (c.Text("supersedes").Length > 0) badges.Children.Add(OverviewChip(T("cc.revision")));
            var stateStyle = c.Text("org_status") is not ("" or "active") ? "" : c.Text("status") == "active" ? "ok" : c.Text("status") == "retired" && c.Text("retired_by") == "human" ? "bad" : "";
            badges.Children.Add(OverviewChip(CopyState(c!), stateStyle));
            var top = new Grid { ColumnSpacing = 10 }; top.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); top.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); top.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
            var organization = orgs.FirstOrDefault(o => o.Text("id") == c.Text("org")) ?? new JsonObject { ["id"] = c.Text("org"), ["name"] = c.Text("org_name") };
            var avatar = SidebarOrgFace(organization!); avatar.VerticalAlignment = VerticalAlignment.Top; avatar.Margin = new Thickness(0, 2, 0, 0); top.Children.Add(avatar);
            var titles = new StackPanel(); var orgName = OverviewText(c.Text("org_name"), 12, true, lineHeight: 16.8); orgName.TextWrapping = TextWrapping.NoWrap; orgName.TextTrimming = TextTrimming.CharacterEllipsis; titles.Children.Add(orgName);
            var title = new RichTextBlock { FontFamily = new FontFamily("Segoe UI Variable Text"), FontSize = 14, FontWeight = new Windows.UI.Text.FontWeight { Weight = 650 }, Foreground = Ink, TextWrapping = TextWrapping.Wrap, LineHeight = 19.6, LineStackingStrategy = LineStackingStrategy.BlockLineHeight, IsTextSelectionEnabled = true };
            var paragraph = new Paragraph(); paragraph.Inlines.Add(new Run { Text = c.Text("protocol_id"), FontFamily = new FontFamily("Cascadia Code"), FontSize = 12.88, FontWeight = Microsoft.UI.Text.FontWeights.SemiBold, Foreground = Paint("5A5853", "B8B5AE") }); paragraph.Inlines.Add(new Run { Text = " " + c.Text("title") }); title.Blocks.Add(paragraph); titles.Children.Add(title);
            Grid.SetColumn(titles, 1); top.Children.Add(titles); Grid.SetColumn(badges, 2); top.Children.Add(badges);
            top.SizeChanged += (_, args) => badges.MaxWidth = args.NewSize.Width * .45; card.Children.Add(top);
            card.Children.Add(new Border { Child = Rich(c.Text("summary")), Background = live ? Paint("F8F7F5", "191918") : Paint("FFFFFF", "1F1F1E"), BorderBrush = Line, BorderThickness = new Thickness(1), Padding = new Thickness(12, 8, 12, 8), CornerRadius = new CornerRadius(10), Opacity = live ? 1 : .8 });
            var metadata = new List<string> { T(c?["issued_by"].Text("member").Length > 0 ? "cc.issued_by" : "cc.proposed_by", ("name", c.Text("author_display"))) };
            if (c.Rows("approved_display").Count > 0) metadata.Add(T("cc.approved_by", ("names", words.List(c.Rows("approved_display").Select(n => n.Text())))));
            if (c.Text("activated_at").Length > 0) metadata.Add(T("cc.effective", ("when", When(c.Text("activated_at")))));
            if (c.Text("supersedes").Length > 0) metadata.Add(T("cc.replaces", ("id", c.Text("supersedes")))); card.Children.Add(OverviewText(string.Join(" · ", metadata), 12, true));
            var stats = c?["stats"];
            string Count(string key) => stats.Text(key).Length > 0 ? stats.Text(key) : "0";
            card.Children.Add(OverviewText(stats.Text("total") is "" or "0" ? T("cc.stats_none") : T("cc.stats", ("n", Count("total")), ("allow", Count("allow")), ("deny", Count("deny")), ("review", Count("review")), ("error", Count("error"))), 12, true));
            if (c.Rows("rules").Any(r => r.Text("effect") == "check"))
            {
                var rules = CheckRules(c.Rows("rules"));
                if (rules is Expander disclosure) { disclosure.IsExpanded = expandedCopies.Contains(c.Text("id")); disclosure.Expanding += (_, _) => expandedCopies.Add(c.Text("id")); disclosure.Collapsed += (_, _) => expandedCopies.Remove(c.Text("id")); }
                card.Children.Add(rules);
            }
            var actions = new ActionRow { Spacing = 6 };
            if (!c.Flag("read"))
            {
                var ack = OverviewAction(T("cc.ack"), async () => { await api!.Post("/api/cc/" + c.Text("id") + "/read", new { }); await Refresh(); });
                var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6, VerticalAlignment = VerticalAlignment.Center }; row.Children.Add(ReferenceIcon("check", 14));
                if (ack.Content is UIElement label) { ack.Content = null; row.Children.Add(label); } ack.Content = row; actions.Children.Add(ack);
            }
            if (live)
            {
                var retire = OverviewAction(T("cc.retire"), async () =>
            {
                if (!await Confirm(T("cc.retire_confirm", ("id", c.Text("protocol_id")), ("title", c.Text("title")), ("org", c.Text("org_name"))))) return;
                try { await api!.Post("/api/cc/" + c.Text("id") + "/retire", new { }); await Refresh(); Note(T("cc.retired", ("id", c.Text("protocol_id")), ("title", c.Text("title")))); await ShowCopies(); }
                catch (Exception ex) { Note(T("cc.retire_failed", ("error", ex.Message))); }
                }); if (retire.Content is TextBlock label) label.Foreground = Paint("C2412D", "EE8A78"); actions.Children.Add(retire);
            }
            if (actions.Children.Count > 0) card.Children.Add(actions);
            var surface = new Border { Child = card, Background = live ? Paint("FFFFFF", "252523") : Paint("F8F7F5", "191918"), BorderBrush = Line, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(12), Padding = new Thickness(14, 12, 14, 12) };
            if (!c.Flag("read"))
            {
                var a = Accent.Color; var b = Line.Color;
                surface.BorderBrush = new SolidColorBrush(Windows.UI.Color.FromArgb(255, (byte)Math.Round(a.R * .45 + b.R * .55), (byte)Math.Round(a.G * .45 + b.G * .55), (byte)Math.Round(a.B * .45 + b.B * .55)));
                surface.Padding = new Thickness(0); surface.Child = null;
                surface.Child = new Border { Child = card, BorderBrush = Accent, BorderThickness = new Thickness(3, 0, 0, 0), CornerRadius = new CornerRadius(11), Padding = new Thickness(11, 12, 14, 12) };
            }
            list.Children.Add(surface);
        }
    }
    private string CopyState(JsonNode c) => c.Text("org_status") is not ("" or "active") ? T("cc.status_ended") : c.Text("status") == "active" ? T("cc.status_active") : c.Text("status") == "retired" && c.Text("retired_by") == "human" ? T("cc.status_retired_person") : c.Text("status") == "superseded" ? T("cc.status_superseded", ("id", c.Text("superseded_by"))) : T("cc.status_retired");
}
