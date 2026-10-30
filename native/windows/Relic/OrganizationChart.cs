using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Relic.Core;
using System.Text.Json.Nodes;
using Windows.Foundation;
using Windows.System;
using NativePath = Microsoft.UI.Xaml.Shapes.Path;

namespace Relic;

public sealed partial class MainWindow
{
    private bool chartClosed = true, chartLinks = true;
    private Func<Task>? refreshChart;

    // These are the production chart's layout constants (OC / OCZ in app.js).
    // The plane, including its native controls and paths, is transformed as one
    // surface. ScrollViewer zoom offsets cannot express the reference's centered
    // view when the content is smaller than the viewport.
    private const double ChartWidth = 236, ChartHeight = 80, ChartGapX = 22, ChartGapY = 46, ChartPad = 24, ChartBulge = 40;
    private sealed class ChartNode(JsonNode organization, int depth)
    {
        public JsonNode Organization { get; } = organization;
        public int Depth { get; } = depth;
        public List<ChartNode> Children { get; } = [];
    }

    private TextBlock ChartText(string value, double size, SolidColorBrush? foreground = null, ushort weight = 400)
    {
        var label = OverviewText(value, size, weight: weight, lineHeight: size * 1.6);
        label.Foreground = foreground ?? Ink; label.TextWrapping = TextWrapping.NoWrap;
        label.IsTextSelectionEnabled = false; label.UseLayoutRounding = false; return label;
    }

    private async Task ShowChart(string focus = "")
    {
        JsonNode data;
        try { data = await api!.Get("/api/orgchart"); }
        catch (Exception ex) { Note(T("chart.load_failed", ("error", ex.Message))); return; }
        var body = new Grid { Width = Math.Max(0, root.ActualWidth - 40), Height = Math.Max(0, root.ActualHeight - 56),
            Background = Paint("FFFFFF", "252523"), CornerRadius = new CornerRadius(16) };
        body.RowDefinitions.Add(new() { Height = GridLength.Auto }); body.RowDefinitions.Add(new() { Height = GridLength.Auto }); body.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        var dialog = new NativeContentDialog { XamlRoot = root.XamlRoot, Content = body };
        AutomationProperties.SetName(dialog, T("chart.title"));
        var bar = new ChartFlexPanel { Spacing = 12, RowSpacing = 6, GrowFirst = true };
        var heading = ChartText(T("chart.title"), 15.5, weight: 650); heading.MinWidth = 120; bar.Children.Add(heading);
        var header = new Grid(); header.Children.Add(new Border { Child = bar, Padding = new Thickness(16, 12, 54, 12), BorderBrush = Line, BorderThickness = new Thickness(0, 0, 0, 1) }); body.Children.Add(header);
        var zoomTools = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 2 };
        bar.Children.Add(zoomTools);
        var legend = new ChartFlexPanel { Spacing = 16, RowSpacing = 6, PushLast = true };
        var legendBorder = new Border { Child = legend, Padding = new Thickness(16, 8, 16, 8), BorderBrush = Line, BorderThickness = new Thickness(0, 0, 0, 1) };
        Grid.SetRow(legendBorder, 1); body.Children.Add(legendBorder);
        var viewport = new Grid { Background = Paint("F8F7F5", "191918") };
        var plane = new Canvas { HorizontalAlignment = HorizontalAlignment.Left, VerticalAlignment = VerticalAlignment.Top };
        var transform = new CompositeTransform(); plane.RenderTransform = transform;
        var listScroll = new ScrollViewer { HorizontalScrollBarVisibility = ScrollBarVisibility.Auto, VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            HorizontalScrollMode = ScrollMode.Enabled, VerticalScrollMode = ScrollMode.Enabled, ZoomMode = ZoomMode.Disabled, Visibility = Visibility.Collapsed };
        viewport.Children.Add(plane); viewport.Children.Add(listScroll);
        // A native focusable surface receives chart keyboard navigation. Its
        // empty template adds no painted button or additional text.
        var keyboardSurface = new ChartSurface { Content = viewport, HorizontalContentAlignment = HorizontalAlignment.Stretch, VerticalContentAlignment = VerticalAlignment.Stretch,
            Template = (ControlTemplate)XamlReader.Load("<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' TargetType='ContentControl'><ContentPresenter Content='{TemplateBinding Content}' HorizontalAlignment='Stretch' VerticalAlignment='Stretch'/></ControlTemplate>") };
        Grid.SetRow(keyboardSurface, 2); body.Children.Add(keyboardSurface);
        double viewX = 0, viewY = 0, viewScale = 1;
        string? autoFit = "focus";
        bool hasView = false, narrow = false, first = true, drawing = false;
        Rect allBounds = default; Rect? focusBounds = null;
        var positions = new Dictionary<string, Rect>(StringComparer.Ordinal);
        var controls = new Dictionary<string, ChartNodeButton>(StringComparer.Ordinal);
        var borders = new Dictionary<string, (Rectangle Shape, SolidColorBrush Normal)>(StringComparer.Ordinal);
        var sharedLines = new List<(string A, string B, NativePath Shape)>();
        long draggedAt = 0;
        var hint = ChartText(T("chart.pan_hint"), 12, Paint("B8B5AF", "5F5D58"));
        var percentage = ChartText("100%", 12, Paint("5A5853", "B8B5AE"));
        var actual = QuietButton("", () => { Zoom(1 / viewScale); return Task.CompletedTask; });
        actual.Content = percentage; actual.MinWidth = 50; actual.MinHeight = 0; actual.Height = 28; actual.CornerRadius = new CornerRadius(8);
        actual.Padding = new Thickness(6, 0, 6, 0); actual.HorizontalContentAlignment = HorizontalAlignment.Center;
        ToolTipService.SetToolTip(actual, T("chart.zoom_actual"));

        void ApplyView()
        {
            transform.ScaleX = transform.ScaleY = narrow ? 1 : viewScale;
            transform.TranslateX = narrow ? 0 : Math.Floor(viewX + .5); transform.TranslateY = narrow ? 0 : Math.Floor(viewY + .5);
            percentage.Text = Math.Floor(viewScale * 100 + .5) + "%";
        }
        void ClampView()
        {
            viewX = Math.Min(viewport.ActualWidth - 80, Math.Max(80 - plane.Width * viewScale, viewX));
            viewY = Math.Min(viewport.ActualHeight - 80, Math.Max(80 - plane.Height * viewScale, viewY));
        }
        void Fit(string target)
        {
            if (narrow || positions.Count == 0 || viewport.ActualWidth <= 0 || viewport.ActualHeight <= 0) return;
            var want = target == "focus" && focusBounds != null ? "focus" : "all";
            var bounds = want == "focus" ? focusBounds!.Value : allBounds;
            viewScale = Math.Max(.15, Math.Min(1, Math.Min((viewport.ActualWidth - 56) / bounds.Width, (viewport.ActualHeight - 56) / bounds.Height)));
            viewX = (viewport.ActualWidth - bounds.Width * viewScale) / 2 - bounds.X * viewScale;
            viewY = Math.Max(28, (viewport.ActualHeight - bounds.Height * viewScale) / 2) - bounds.Y * viewScale;
            autoFit = want; hasView = true; ApplyView();
        }
        void Zoom(double factor, double? px = null, double? py = null)
        {
            if (narrow || !hasView) return;
            var scale = Math.Clamp(viewScale * factor, .15, 2);
            if (Math.Abs(scale - viewScale) < .0001) return;
            var x = px ?? viewport.ActualWidth / 2; var y = py ?? viewport.ActualHeight / 2;
            viewX = x - (x - viewX) * scale / viewScale; viewY = y - (y - viewY) * scale / viewScale;
            viewScale = scale; autoFit = null; ClampView(); ApplyView();
        }
        void Pan(double dx, double dy)
        {
            if (narrow || !hasView) return;
            viewX += dx; viewY += dy; autoFit = null; ClampView(); ApplyView();
        }
        Button Tool(string glyph, string key, Action action)
        {
            var button = IconButton(glyph, key, () => { action(); return Task.CompletedTask; }, iconSize: 16);
            button.Width = button.Height = 28; button.MinHeight = 0; button.Padding = new Thickness(0); button.CornerRadius = new CornerRadius(8);
            button.Foreground = Paint("5A5853", "B8B5AE");
            return button;
        }
        zoomTools.Children.Add(Tool("\uE738", "chart.zoom_out", () => Zoom(1 / 1.25))); zoomTools.Children.Add(actual);
        zoomTools.Children.Add(Tool("\uE710", "chart.zoom_in", () => Zoom(1.25))); zoomTools.Children.Add(Tool("\uE9A6", "chart.fit", () => Fit("all")));
        bar.Children.Add(OverviewSwitch(T("chart.show_closed"), true, chartClosed, value => { chartClosed = value; SaveViewState(); Draw(); return Task.CompletedTask; }));
        bar.Children.Add(OverviewSwitch(T("chart.show_links"), true, chartLinks, value => { chartLinks = value; SaveViewState(); Draw(); return Task.CompletedTask; }));
        var close = IconButton("\uE711", "common.close", () => { dialog.Hide(); return Task.CompletedTask; }); close.Content = ReferenceIcon("x", 18); close.Padding = new Thickness(0);
        close.Foreground = Paint("5A5853", "B8B5AE"); close.CornerRadius = new CornerRadius(8);
        close.HorizontalAlignment = HorizontalAlignment.Right; close.VerticalAlignment = VerticalAlignment.Top; close.Margin = new Thickness(0, 9, 12, 0); header.Children.Add(close);
        foreach (var (kind, key) in new[] { ("", "org.kind_formal"), ("sub", "org.kind_subgroup"), ("cab", "org.cabinet_chip"), ("ended", "chart.legend_ended"), ("link", "chart.legend_shared") })
        {
            var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 };
            // In the captured 1x reference, 1.5px CSS borders resolve to 1px.
            // SVG edge/link strokes below retain their separate fractional widths.
            var swatch = new ChartLegendSwatch { Width = 18, Height = kind == "link" ? 1 : 12, VerticalAlignment = VerticalAlignment.Center };
            if (kind == "link") swatch.Children.Add(new Line { X1 = 0, X2 = 18, Y1 = .5, Y2 = .5, Stroke = Paint("7058B8", "A894E0"), StrokeThickness = 1, StrokeDashArray = new DoubleCollection { 4.5, 4.5 } });
            else swatch.Children.Add(new Rectangle { Width = 18, Height = 12, RadiusX = 4, RadiusY = 4, StrokeThickness = 1,
                Stroke = kind == "cab" ? Paint("7058B8", "A894E0") : kind == "ended" ? Paint("B8B5AF", "5F5D58") : Muted,
                Fill = kind == "cab" ? Paint("EFEBF8", "2E2A3D") : kind == "ended" ? Paint("EFEEEA", "262624") : Paint("FFFFFF", "252523"),
                StrokeDashArray = kind == "sub" ? new DoubleCollection { 4.5, 4.5 } : null });
            row.Children.Add(swatch); row.Children.Add(ChartText(T(key), 12, Muted)); legend.Children.Add(row);
        }
        legend.Children.Add(hint);

        void Highlight(string id, bool on)
        {
            foreach (var (a, b, line) in sharedLines)
            {
                var mine = a == id || b == id;
                line.Opacity = on ? mine ? 1 : .12 : .5; line.StrokeThickness = on && mine ? 2 : 1.2;
                line.StrokeDashArray = new DoubleCollection { 4 / line.StrokeThickness, 3 / line.StrokeThickness };
                if (mine && borders.TryGetValue(a == id ? b : a, out var peer)) peer.Shape.Stroke = on ? Paint("7058B8", "A894E0") : peer.Normal;
            }
        }
        void Draw()
        {
            if (drawing || viewport.ActualWidth <= 0) return;
            drawing = true;
            try
            {
                plane.Children.Clear(); positions.Clear(); controls.Clear(); borders.Clear(); sharedLines.Clear();
                var orgs = data.Rows("orgs").OfType<JsonNode>().Where(item => chartClosed || item.Text("status") == "active").ToArray();
                var byId = orgs.ToDictionary(item => item.Text("id"), StringComparer.Ordinal);
                var oldNarrow = narrow; narrow = viewport.ActualWidth < 620;
                zoomTools.Visibility = hint.Visibility = narrow ? Visibility.Collapsed : Visibility.Visible;
                if (oldNarrow != narrow)
                {
                    if (narrow) { viewport.Children.Remove(plane); listScroll.Content = plane; listScroll.Visibility = Visibility.Visible; }
                    else { listScroll.Content = null; listScroll.Visibility = Visibility.Collapsed; viewport.Children.Insert(0, plane); }
                }
                viewport.Clip = new RectangleGeometry { Rect = new Rect(0, 0, viewport.ActualWidth, viewport.ActualHeight) };
                if (orgs.Length == 0)
                {
                    plane.Width = viewport.ActualWidth; plane.Height = viewport.ActualHeight;
                    var empty = ChartText(T("chart.empty"), 12.5, Muted); Canvas.SetLeft(empty, 24); Canvas.SetTop(empty, 24); plane.Children.Add(empty);
                    transform.ScaleX = transform.ScaleY = 1; transform.TranslateX = transform.TranslateY = 0; return;
                }
                static int Rank(JsonNode item) => (item.Flag("cabinet") ? 0 : 4) + (item.Text("kind") == "subgroup" ? 2 : 0) + (item.Text("status") == "active" ? 0 : 1);
                var children = orgs.GroupBy(item => item.Text("parent") != item.Text("id") && byId.ContainsKey(item.Text("parent")) ? item.Text("parent") : "")
                    .ToDictionary(group => group.Key, group => group.OrderBy(Rank).ToArray(), StringComparer.Ordinal);
                var order = new List<ChartNode>(); var roots = new List<ChartNode>(); var seen = new HashSet<string>(StringComparer.Ordinal);
                ChartNode? Walk(JsonNode item, int depth)
                {
                    if (!seen.Add(item.Text("id"))) return null;
                    var result = new ChartNode(item, depth); order.Add(result);
                    foreach (var child in children.GetValueOrDefault(item.Text("id"), [])) if (Walk(child, depth + 1) is { } next) result.Children.Add(next);
                    return result;
                }
                foreach (var item in children.GetValueOrDefault("", []).Concat(orgs)) if (Walk(item, 0) is { } node) roots.Add(node);
                var elsewhere = new Dictionary<string, List<string>>(StringComparer.Ordinal);
                var pairs = new Dictionary<(string A, string B), List<string>>();
                foreach (var shared in data.Rows("shared"))
                {
                    var seats = shared.Rows("seats").Where(seat => byId.ContainsKey(seat.Text("org"))).ToArray();
                    if (seats.Length < 2) continue;
                    foreach (var seat in seats)
                    {
                        var id = seat.Text("org"); if (!elsewhere.ContainsKey(id)) elsewhere[id] = [];
                        elsewhere[id].Add(T("chart.shared_tip", ("member", seat.Text("member")), ("orgs", words.List(seats.Where(other => other.Text("org") != id).Select(other => byId[other.Text("org")].Text("name"))))));
                    }
                    for (var i = 0; i < seats.Length; i++) for (var j = i + 1; j < seats.Length; j++)
                    {
                        var a = seats[i]; var b = seats[j]; if (string.CompareOrdinal(a.Text("org"), b.Text("org")) > 0) (a, b) = (b, a);
                        var pair = (a.Text("org"), b.Text("org")); if (!pairs.ContainsKey(pair)) pairs[pair] = [];
                        pairs[pair].Add(T("chart.link_tip", ("member", a.Text("member") == b.Text("member") ? a.Text("member") : a.Text("member") + " / " + b.Text("member")), ("a", byId[pair.Item1].Text("name")), ("b", byId[pair.Item2].Text("name"))));
                    }
                }
                if (narrow)
                {
                    for (var i = 0; i < order.Count; i++) { var node = order[i]; var x = ChartPad + node.Depth * 20; positions[node.Organization.Text("id")] = new Rect(x, ChartPad + i * (ChartHeight + 12), Math.Max(170, viewport.ActualWidth - x - ChartPad - ChartBulge), ChartHeight); }
                    plane.Width = positions.Values.Max(point => point.Right) + ChartBulge + ChartPad; plane.Height = ChartPad * 2 + order.Count * (ChartHeight + 12) - 12;
                }
                else
                {
                    double slot = 0;
                    void Place(ChartNode node)
                    {
                        double x;
                        if (node.Children.Count == 0) { x = slot * (ChartWidth + ChartGapX); slot++; }
                        else { foreach (var child in node.Children) Place(child); x = (positions[node.Children[0].Organization.Text("id")].X + positions[node.Children[^1].Organization.Text("id")].X) / 2; }
                        positions[node.Organization.Text("id")] = new Rect(x, node.Depth * (ChartHeight + ChartGapY), ChartWidth, ChartHeight);
                    }
                    for (var i = 0; i < roots.Count; i++) { if (i > 0) slot += .4; Place(roots[i]); }
                    foreach (var id in positions.Keys.ToArray()) { var point = positions[id]; positions[id] = new Rect(point.X + ChartPad, point.Y + ChartPad, point.Width, point.Height); }
                    plane.Width = ChartPad * 2 + slot * (ChartWidth + ChartGapX) - ChartGapX + ChartBulge;
                    plane.Height = ChartPad * 2 + (order.Max(node => node.Depth) + 1) * (ChartHeight + ChartGapY) - ChartGapY;
                }
                foreach (var parent in order) foreach (var child in parent.Children)
                {
                    var p = positions[parent.Organization.Text("id")]; var c = positions[child.Organization.Text("id")];
                    var points = narrow ? new PointCollection { new(p.X + 12, p.Bottom), new(p.X + 12, c.Y + ChartHeight / 2), new(c.X, c.Y + ChartHeight / 2) }
                        : new PointCollection { new(p.X + ChartWidth / 2, p.Bottom), new(p.X + ChartWidth / 2, p.Bottom + ChartGapY / 2), new(c.X + ChartWidth / 2, p.Bottom + ChartGapY / 2), new(c.X + ChartWidth / 2, c.Y) };
                    var edge = new Polyline { Points = points, Stroke = Paint("B8B5AF", "5F5D58"), StrokeThickness = 1.4, IsHitTestVisible = false };
                    if (child.Organization.Text("status") != "active") { edge.Opacity = .7; edge.StrokeDashArray = new DoubleCollection { 3 / 1.4, 3 / 1.4 }; }
                    plane.Children.Add(edge);
                }
                if (chartLinks) foreach (var (pair, tips) in pairs)
                {
                    var a = positions[pair.A]; var b = positions[pair.B]; var ay = a.Y + ChartHeight / 2; var by = b.Y + ChartHeight / 2;
                    Point start, end, firstControl, secondControl;
                    if (!narrow && Math.Abs(a.X - b.X) >= ChartWidth)
                    {
                        var left = a.X < b.X ? a : b; var right = a.X < b.X ? b : a; var ly = a.X < b.X ? ay : by; var ry = a.X < b.X ? by : ay;
                        var mid = (left.Right + right.X) / 2; start = new(left.Right, ly); end = new(right.X, ry); firstControl = new(mid, ly); secondControl = new(mid, ry);
                    }
                    else { var outside = Math.Max(a.Right, b.Right) + ChartBulge * .8; start = new(a.Right, ay); end = new(b.Right, by); firstControl = new(outside, ay); secondControl = new(outside, by); }
                    var figure = new PathFigure { StartPoint = start }; figure.Segments.Add(new BezierSegment { Point1 = firstControl, Point2 = secondControl, Point3 = end }); var geometry = new PathGeometry(); geometry.Figures.Add(figure);
                    var line = new NativePath { Data = geometry, Stroke = Paint("7058B8", "A894E0"), StrokeThickness = 1.2, StrokeDashArray = new DoubleCollection { 4 / 1.2, 3 / 1.2 }, Opacity = .5 };
                    ToolTipService.SetToolTip(line, string.Join("\n", tips)); plane.Children.Add(line); sharedLines.Add((pair.A, pair.B, line));
                }
                foreach (var node in order)
                {
                    var item = node.Organization; var id = item.Text("id"); var point = positions[id]; var ended = item.Text("status") != "active";
                    SolidColorBrush Color(SolidColorBrush brush)
                    {
                        if (!ended) return brush;
                        var c = brush.Color; var gray = (byte)Math.Round(c.R * .2126 + c.G * .7152 + c.B * .0722); return new SolidColorBrush(Windows.UI.Color.FromArgb(c.A, gray, gray, gray)) { Opacity = brush.Opacity };
                    }
                    var who = item.Text("leader_display").Length > 0 ? item.Text("leader_display") : item.Text("leader");
                    var lead = item.Text("governance") == "peer" ? T("org.gov_peer") : item.Text("leader").Length == 0 ? T("chart.no_leader") : T(item.Flag("cabinet") ? "org.secretary_general_chip" : "org.leader_chip", ("name", who));
                    var here = elsewhere.GetValueOrDefault(id, []);
                    var label = new List<string> { item.Text("name") };
                    var ink2 = Color(Paint("5A5853", "B8B5AE"));
                    OverviewChipView Chip(string value, string kind = "", bool strong = false)
                    {
                        var ink = Color(kind == "cab" || kind == "sec" ? Paint("7058B8", "A894E0") : kind == "warn" ? Paint("B7791F", "E2B15A") : Paint("5A5853", "B8B5AE"));
                        var background = Color(kind == "cab" || kind == "sec" ? Paint("EFEBF8", "2E2A3D") : kind == "warn" ? Paint("FBF3E2", "3A3020") : Paint("EFEEEA", "262624"));
                        var text = ChartText(value, 10.5, ink, strong ? (ushort)600 : (ushort)400);
                        text.LineHeight = 20; // .oc-node .chip retains .chip's fixed line-height.
                        return new OverviewChipView { Content = text, Foreground = ink, FontSize = 10.5, Background = background,
                            Height = 20, Padding = new Thickness(6, 0, 6, 0), CornerRadius = new CornerRadius(10), VerticalAlignment = VerticalAlignment.Center, UseLayoutRounding = false };
                    }
                    var nameRow = new Grid { ColumnSpacing = 6, Height = 22, UseLayoutRounding = false };
                    nameRow.ColumnDefinitions.Add(new() { Width = new GridLength(22) }); nameRow.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
                    var badge = SidebarOrgFace(item); nameRow.Children.Add(badge);
                    var name = ChartText(item.Text("name"), 13, Color(Ink), 650); name.TextTrimming = TextTrimming.CharacterEllipsis; name.VerticalAlignment = VerticalAlignment.Center; Grid.SetColumn(name, 1); nameRow.Children.Add(name);
                    void NameChip(string value, string kind = "") { nameRow.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); var chip = Chip(value, kind, kind == "cab"); Grid.SetColumn(chip, nameRow.ColumnDefinitions.Count - 1); nameRow.Children.Add(chip); label.Add(value); }
                    if (item.Flag("cabinet")) NameChip(T("org.cabinet_chip"), "cab");
                    if (item.Text("kind") == "subgroup") NameChip(T("org.kind_subgroup"));
                    if (ended) NameChip(T(item.Text("status") == "closed" ? "org.status_closed" : "org.status_dissolved"));
                    var leadLine = ChartText(lead, 11.5, ink2); leadLine.TextTrimming = TextTrimming.CharacterEllipsis;
                    var counts = new Grid { ColumnSpacing = 6, Height = 20, UseLayoutRounding = false };
                    counts.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); counts.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); counts.ColumnDefinitions.Add(new() { Width = GridLength.Auto }); counts.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
                    var members = ChartText(T("common.members", ("n", item.Text("members"))), 11.5, ink2); members.TextTrimming = TextTrimming.CharacterEllipsis; members.VerticalAlignment = VerticalAlignment.Center; counts.Children.Add(members);
                    var decisions = Chip(T("chart.decisions", ("n", item.Text("decisions"))), int.TryParse(item.Text("decisions"), out var count) && count > 0 ? "warn" : ""); Grid.SetColumn(decisions, 1); counts.Children.Add(decisions);
                    if (here.Count > 0) { var shared = Chip(T("chart.shared", ("n", here.Count)), "sec"); Grid.SetColumn(shared, 2); counts.Children.Add(shared); }
                    var contents = new Grid { RowSpacing = 4, VerticalAlignment = VerticalAlignment.Center, UseLayoutRounding = false };
                    contents.RowDefinitions.Add(new() { Height = GridLength.Auto }); contents.RowDefinitions.Add(new() { Height = GridLength.Auto }); contents.RowDefinitions.Add(new() { Height = GridLength.Auto });
                    contents.Children.Add(nameRow); Grid.SetRow(leadLine, 1); contents.Children.Add(leadLine); Grid.SetRow(counts, 2); contents.Children.Add(counts);
                    var fill = item.Flag("cabinet") ? Paint("F3F0FA", "2C2937") : Paint("FFFFFF", "252523");
                    var stroke = Color(item.Flag("cabinet") ? Paint("7058B8", "A894E0") : Paint("DEDBD4", "3A3936"));
                    var button = new ChartNodeButton { Content = contents, Width = point.Width, Height = ChartHeight, IsCurrent = id == org, Background = Color(fill), Foreground = Color(Ink),
                        BorderThickness = new Thickness(1), BorderBrush = new SolidColorBrush(Colors.Transparent), Padding = new Thickness(11, 0, 11, 0), CornerRadius = new CornerRadius(12), UseLayoutRounding = false,
                        HorizontalContentAlignment = HorizontalAlignment.Stretch, VerticalContentAlignment = VerticalAlignment.Center, MinWidth = 0, MinHeight = 0,
                        Template = (ControlTemplate)XamlReader.Load("<ControlTemplate xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' TargetType='Button'><Border Background='{TemplateBinding Background}' BorderBrush='{TemplateBinding BorderBrush}' BorderThickness='{TemplateBinding BorderThickness}' CornerRadius='{TemplateBinding CornerRadius}' Padding='{TemplateBinding Padding}'><ContentPresenter Content='{TemplateBinding Content}' HorizontalAlignment='Stretch' VerticalAlignment='Center'/></Border></ControlTemplate>") };
                    label.Add(lead); label.Add(members.Text); label.Add(T("chart.decisions", ("n", item.Text("decisions")))); if (here.Count > 0) label.Add(T("chart.shared", ("n", here.Count)));
                    AutomationProperties.SetName(button, string.Join(" ", label));
                    ToolTipService.SetToolTip(button, string.Join("\n", new[] { T("chart.open_hint", ("name", item.Text("name"))), lead, item.Text("purpose") }.Concat(here).Where(value => value.Length > 0)));
                    button.Click += async (_, _) => { if (Environment.TickCount64 - draggedAt < 500) return; dialog.Hide(); if (id != org) await Run(() => Select(id)); };
                    var surface = new Grid { Width = point.Width, Height = ChartHeight, Opacity = ended ? .5 : 1 };
                    if (id == org) surface.Children.Add(new Border { Margin = new Thickness(-3), CornerRadius = new CornerRadius(15), BorderThickness = new Thickness(3), BorderBrush = Color(OverviewAlpha(Accent, .4)), IsHitTestVisible = false });
                    NativeShadowPanel? raised = null;
                    if (button.IsCurrent) surface.Children.Add(button);
                    else
                    {
                        raised = new NativeShadowPanel(new Border { Child = button, CornerRadius = new CornerRadius(12), UseLayoutRounding = false }) { UseLayoutRounding = false };
                        surface.Children.Add(raised);
                    }
                    void UpdateShadow(bool active)
                    {
                        // The later .cur rule replaces both normal and active
                        // shadows with the existing 3px accent ring.
                        if (raised == null) return;
                        var normal = Color(Paint("14120F")).Color;
                        var activeColor = Dark ? Colors.Black : normal;
                        raised.SetShadows(active
                            ? [new NativeShadowLayer(0, 10, 32, activeColor, Dark ? .5f : .14f), new NativeShadowLayer(0, 2, 6, activeColor, Dark ? .3f : .06f)]
                            : [new NativeShadowLayer(0, 1, 2, normal, .06f)]);
                    }
                    UpdateShadow(false);
                    var border = new Rectangle { Stroke = stroke, StrokeThickness = 1, RadiusX = 12, RadiusY = 12, IsHitTestVisible = false };
                    // Preserve the existing native 4.5px dash lengths while fixing
                    // border width. CSS border dash segments/phase remain unmeasured.
                    if (item.Text("kind") == "subgroup") border.StrokeDashArray = new DoubleCollection { 4.5, 4.5 };
                    surface.Children.Add(border); controls[id] = button; borders[id] = (border, stroke);
                    var hovered = false;
                    void UpdateInteraction()
                    {
                        var active = hovered || button.FocusState == FocusState.Keyboard;
                        border.Stroke = active ? Color(Muted) : stroke;
                        Canvas.SetZIndex(surface, active ? 2 : 0);
                        Highlight(id, active); UpdateShadow(active);
                    }
                    button.PointerEntered += (_, _) => { hovered = true; UpdateInteraction(); };
                    button.PointerExited += (_, _) => { hovered = false; UpdateInteraction(); };
                    button.GotFocus += (_, _) => UpdateInteraction();
                    button.LostFocus += (_, _) => UpdateInteraction();
                    button.ActualThemeChanged += (_, _) => UpdateShadow(hovered || button.FocusState == FocusState.Keyboard);
                    if (ended) Grayscale(badge);
                    Canvas.SetLeft(surface, point.X); Canvas.SetTop(surface, point.Y); plane.Children.Add(surface);
                }
                Rect Bounds(IEnumerable<ChartNode> nodes, double bulge)
                {
                    var points = nodes.Select(node => positions[node.Organization.Text("id")]).ToArray(); var x = points.Min(point => point.X); var y = points.Min(point => point.Y);
                    return new Rect(x, y, points.Max(point => point.Right) - x + bulge, points.Max(point => point.Bottom) - y);
                }
                IEnumerable<ChartNode> Below(ChartNode node) { yield return node; foreach (var child in node.Children) foreach (var descendant in Below(child)) yield return descendant; }
                allBounds = Bounds(order, sharedLines.Count > 0 ? ChartBulge * .8 : 0);
                var from = order.FirstOrDefault(node => node.Organization.Text("id") == focus);
                focusBounds = from != null ? Bounds(Below(from), from.Children.Count > 0 && sharedLines.Count > 0 ? ChartBulge * .8 : 0) : null;
                if (narrow)
                {
                    ApplyView();
                    if (first && positions.TryGetValue(focus.Length > 0 ? focus : org, out var current)) listScroll.ChangeView(null, Math.Max(0, current.Y + ChartHeight / 2 - viewport.ActualHeight / 2), null, true);
                }
                else if (!hasView || autoFit != null) Fit(autoFit ?? "focus");
                else { ClampView(); ApplyView(); }
                first = false;
            }
            finally { drawing = false; }
        }

        // Pointer tracking keeps the same four-pixel drag threshold and prevents
        // the click which ends a drag from changing the selected organization.
        var pointers = new Dictionary<uint, Point>();
        (uint Id, Point Start, double X, double Y, bool Moved)? drag = null;
        (double Distance, double Scale)? pinch = null;
        viewport.AddHandler(UIElement.PointerPressedEvent, new PointerEventHandler((_, e) =>
        {
            if (narrow || !hasView) return;
            var point = e.GetCurrentPoint(viewport);
            if (point.PointerDeviceType == Microsoft.UI.Input.PointerDeviceType.Mouse && !point.Properties.IsLeftButtonPressed) return;
            var source = e.OriginalSource as DependencyObject;
            while (source != null && source is not ChartNodeButton && source != viewport) source = VisualTreeHelper.GetParent(source);
            if (source is not ChartNodeButton) keyboardSurface.Focus(FocusState.Pointer);
            pointers[e.Pointer.PointerId] = point.Position;
            if (pointers.Count == 1) drag = (e.Pointer.PointerId, point.Position, viewX, viewY, false);
            else if (pointers.Count == 2) { var p = pointers.Values.ToArray(); pinch = (Math.Max(1, Math.Sqrt(Math.Pow(p[0].X - p[1].X, 2) + Math.Pow(p[0].Y - p[1].Y, 2))), viewScale); drag = null; }
        }), true);
        viewport.AddHandler(UIElement.PointerMovedEvent, new PointerEventHandler((_, e) =>
        {
            if (narrow || !pointers.ContainsKey(e.Pointer.PointerId)) return;
            pointers[e.Pointer.PointerId] = e.GetCurrentPoint(viewport).Position;
            if (pinch is { } zoom && pointers.Count == 2)
            {
                var p = pointers.Values.ToArray(); var distance = Math.Sqrt(Math.Pow(p[0].X - p[1].X, 2) + Math.Pow(p[0].Y - p[1].Y, 2));
                Zoom(zoom.Scale * distance / zoom.Distance / viewScale, (p[0].X + p[1].X) / 2, (p[0].Y + p[1].Y) / 2); return;
            }
            if (drag is not { } moving || moving.Id != e.Pointer.PointerId) return;
            var point = pointers[e.Pointer.PointerId]; var dx = point.X - moving.Start.X; var dy = point.Y - moving.Start.Y;
            if (!moving.Moved && Math.Sqrt(dx * dx + dy * dy) < 4) return;
            if (!moving.Moved) viewport.CapturePointer(e.Pointer);
            drag = (moving.Id, moving.Start, moving.X, moving.Y, true); viewX = moving.X + dx; viewY = moving.Y + dy; autoFit = null; ClampView(); ApplyView(); e.Handled = true;
        }), true);
        void EndPointer(object sender, PointerRoutedEventArgs e)
        {
            pointers.Remove(e.Pointer.PointerId); if (pointers.Count < 2) pinch = null;
            if (drag is { } moving && moving.Id == e.Pointer.PointerId) { if (moving.Moved) draggedAt = Environment.TickCount64; drag = null; }
            viewport.ReleasePointerCapture(e.Pointer);
        }
        viewport.AddHandler(UIElement.PointerReleasedEvent, new PointerEventHandler(EndPointer), true);
        viewport.AddHandler(UIElement.PointerCanceledEvent, new PointerEventHandler(EndPointer), true);
        viewport.AddHandler(UIElement.PointerWheelChangedEvent, new PointerEventHandler((_, e) =>
        {
            if (narrow) return; var point = e.GetCurrentPoint(viewport); Zoom(Math.Exp(point.Properties.MouseWheelDelta * .0015), point.Position.X, point.Position.Y); e.Handled = true;
        }), true);
        viewport.DoubleTapped += (_, e) =>
        {
            var source = e.OriginalSource as DependencyObject;
            while (source != null && source != viewport) { if (source is ChartNodeButton) return; source = VisualTreeHelper.GetParent(source); }
            if (!narrow) Fit("all");
        };
        keyboardSurface.KeyDown += (_, e) =>
        {
            if (narrow || !ReferenceEquals(e.OriginalSource, keyboardSurface)) return;
            Func<VirtualKey, Windows.UI.Core.CoreVirtualKeyStates> keys = Microsoft.UI.Input.InputKeyboardSource.GetKeyStateForCurrentThread;
            if ((keys(VirtualKey.Control) & Windows.UI.Core.CoreVirtualKeyStates.Down) != 0 || (keys(VirtualKey.Menu) & Windows.UI.Core.CoreVirtualKeyStates.Down) != 0 || (keys(VirtualKey.LeftWindows) & Windows.UI.Core.CoreVirtualKeyStates.Down) != 0 || (keys(VirtualKey.RightWindows) & Windows.UI.Core.CoreVirtualKeyStates.Down) != 0) return;
            switch (e.Key)
            {
                case VirtualKey.Add: case (VirtualKey)187: Zoom(1.25); break;
                case VirtualKey.Subtract: case (VirtualKey)189: Zoom(1 / 1.25); break;
                case VirtualKey.Number0: Fit("all"); break;
                case VirtualKey.Left: Pan(60, 0); break; case VirtualKey.Right: Pan(-60, 0); break;
                case VirtualKey.Up: Pan(0, 60); break; case VirtualKey.Down: Pan(0, -60); break;
                default: return;
            }
            e.Handled = true;
        };
        viewport.SizeChanged += (_, _) => Draw(); viewport.Loaded += (_, _) => Draw();
        void Resize(object sender, SizeChangedEventArgs e) { body.Width = Math.Max(0, e.NewSize.Width - 40); body.Height = Math.Max(0, e.NewSize.Height - 56); }
        root.SizeChanged += Resize;
        dialog.Opened += (_, _) =>
        {
            dialog.Resources["ContentDialogPadding"] = new Thickness(0); dialog.Resources["ContentDialogTitleMargin"] = new Thickness(0);
            dialog.Resources["ContentDialogMaxHeight"] = body.Height;
            if (DialogPart<ContentPresenter>(dialog, "Content") is { } presenter) { presenter.Margin = new Thickness(0); presenter.Padding = new Thickness(0); }
            if (DialogPart<Border>(dialog, "BackgroundElement") is { } background) { background.Padding = new Thickness(0); background.CornerRadius = new CornerRadius(16); background.MaxHeight = body.Height; }
            if (DialogPart<ScrollViewer>(dialog, "ContentScrollViewer") is { } scroll) { scroll.Padding = new Thickness(0); scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Disabled; scroll.HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled; scroll.MaxHeight = body.Height; }
            if (DialogPart<Grid>(dialog, "CommandSpace") is { } commands) commands.Visibility = Visibility.Collapsed;
            body.UpdateLayout(); Draw();
        };
        refreshChart = async () => { data = await api!.Get("/api/orgchart"); Draw(); };
        try { await Dialog(dialog, contentOwnsPadding: true); }
        finally { root.SizeChanged -= Resize; refreshChart = null; }
    }

    private static void Grayscale(DependencyObject element)
    {
        SolidColorBrush? Gray(Brush? brush)
        {
            if (brush is not SolidColorBrush solid) return null;
            var c = solid.Color; var gray = (byte)Math.Round(c.R * .2126 + c.G * .7152 + c.B * .0722);
            return new SolidColorBrush(Windows.UI.Color.FromArgb(c.A, gray, gray, gray)) { Opacity = solid.Opacity };
        }
        if (element is TextBlock text && Gray(text.Foreground) is { } ink) text.Foreground = ink;
        if (element is Border border) { if (Gray(border.Background) is { } fill) border.Background = fill; if (Gray(border.BorderBrush) is { } stroke) border.BorderBrush = stroke; if (border.Child != null) Grayscale(border.Child); }
        else if (element is Panel panel) { if (Gray(panel.Background) is { } fill) panel.Background = fill; foreach (var child in panel.Children) Grayscale(child); }
        else if (element is Shape shape) { if (Gray(shape.Fill) is { } fill) shape.Fill = fill; if (Gray(shape.Stroke) is { } stroke) shape.Stroke = stroke; }
    }
}

// Actual production types identify semantic chart controls for accessibility
// capture; they contain native elements rather than a picture of the chart.
public sealed class ChartNodeButton : Button { public bool IsCurrent { get; init; } }
public sealed class ChartLegendSwatch : Grid { }
public sealed class ChartSurface : ContentControl { public ChartSurface() { IsTabStop = true; } }

// CSS flex rows used by the reference toolbar and legend. The first title grows
// in its row; the final hint consumes the free space before it. Items wrap with
// a separate row gap and remain vertically centered in each line.
public sealed class ChartFlexPanel : Panel
{
    public double Spacing { get; init; }
    public double RowSpacing { get; init; }
    public bool GrowFirst { get; init; }
    public bool PushLast { get; init; }
    private List<List<UIElement>> Lines(double width)
    {
        var rows = new List<List<UIElement>>(); var line = new List<UIElement>(); double used = 0;
        foreach (var child in Children.Where(child => child.Visibility == Visibility.Visible))
        {
            var itemWidth = GrowFirst && child == Children[0] ? 120 : child.DesiredSize.Width;
            if (line.Count > 0 && used + Spacing + itemWidth > width) { rows.Add(line); line = []; used = 0; }
            used += (line.Count > 0 ? Spacing : 0) + itemWidth; line.Add(child);
        }
        if (line.Count > 0) rows.Add(line); return rows;
    }
    protected override Size MeasureOverride(Size available)
    {
        foreach (var child in Children) child.Measure(new Size(double.PositiveInfinity, double.PositiveInfinity));
        var lines = Lines(available.Width);
        var height = lines.Sum(line => line.Max(child => child.DesiredSize.Height)) + Math.Max(0, lines.Count - 1) * RowSpacing;
        var width = double.IsFinite(available.Width) ? available.Width : lines.Select(line => line.Sum(child => child.DesiredSize.Width) + (line.Count - 1) * Spacing).DefaultIfEmpty(0).Max();
        return new Size(width, height);
    }
    protected override Size ArrangeOverride(Size final)
    {
        double y = 0;
        foreach (var line in Lines(final.Width))
        {
            var rowHeight = line.Max(child => child.DesiredSize.Height);
            var used = line.Sum(child => GrowFirst && child == Children[0] ? 120 : child.DesiredSize.Width) + (line.Count - 1) * Spacing;
            var free = Math.Max(0, final.Width - used); double x = 0;
            foreach (var child in line)
            {
                var width = GrowFirst && child == Children[0] ? 120 + free : child.DesiredSize.Width;
                if (PushLast && child == Children[^1]) x += free;
                child.Arrange(new Rect(x, y + (rowHeight - child.DesiredSize.Height) / 2, width, child.DesiredSize.Height)); x += width + Spacing;
            }
            y += rowHeight + RowSpacing;
        }
        return final;
    }
}
