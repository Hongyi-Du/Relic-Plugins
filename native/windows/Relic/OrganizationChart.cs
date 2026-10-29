using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Relic.Core;
using System.Text.Json.Nodes;
using Windows.System;

namespace Relic;

public sealed partial class MainWindow
{
    private bool chartClosed = true, chartLinks = true;
    private Func<Task>? refreshChart;
    private async Task ShowChart(string focus = "")
    {
        JsonNode data;
        try { data = await api!.Get("/api/orgchart"); } catch (Exception ex) { Note(T("chart.load_failed", ("error", ex.Message))); return; }
        var content = new StackPanel { Spacing = 10 }; var bar = new ActionRow { Spacing = 6 }; content.Children.Add(bar);
        var closed = new CheckBox { Content = T("chart.show_closed"), IsChecked = chartClosed }; var links = new CheckBox { Content = T("chart.show_links"), IsChecked = chartLinks };
        var scroll = new ScrollViewer { ZoomMode = ZoomMode.Enabled, MinZoomFactor = .15f, MaxZoomFactor = 2, HorizontalScrollBarVisibility = ScrollBarVisibility.Auto, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, Height = Math.Max(300, root.ActualHeight - 280), Width = Math.Min(1280, root.ActualWidth - 96), IsTabStop = true };
        var canvas = new Canvas { Background = Paint("F8F7F5", "191918"), ManipulationMode = ManipulationModes.TranslateX | ManipulationModes.TranslateY }; scroll.Background = canvas.Background; scroll.Content = canvas;
        content.Width = scroll.Width;
        var positions = new Dictionary<string, (double X, double Y)>();
        void Fit(bool all)
        {
            var values = positions.Values.ToArray();
            if (!all && positions.ContainsKey(focus.Length > 0 ? focus : org))
            {
                var ids = new HashSet<string> { focus.Length > 0 ? focus : org };
                bool added; do { added = false; foreach (var node in data.Rows("orgs")) if (ids.Contains(node.Text("parent"))) added |= ids.Add(node.Text("id")); } while (added);
                values = positions.Where(p => ids.Contains(p.Key)).Select(p => p.Value).ToArray();
            }
            if (values.Length == 0) return;
            var left = values.Min(p => p.X) - 20; var top = values.Min(p => p.Y) - 20;
            var width = values.Max(p => p.X) + 256 - left; var height = values.Max(p => p.Y) + 114 - top;
            var zoom = Math.Clamp((float)Math.Min(scroll.Width / width, scroll.Height / height), .15f, 1);
            scroll.ChangeView(Math.Max(0, (left + width / 2) * zoom - scroll.Width / 2), Math.Max(0, (top + height / 2) * zoom - scroll.Height / 2), zoom);
        }
        void Zoom(float amount, double? x = null, double? y = null)
        {
            var zoom = Math.Clamp(scroll.ZoomFactor * amount, .15f, 2); var ratio = zoom / scroll.ZoomFactor;
            var px = x ?? scroll.Width / 2; var py = y ?? scroll.Height / 2;
            scroll.ChangeView((scroll.HorizontalOffset + px) * ratio - px, (scroll.VerticalOffset + py) * ratio - py, zoom, true);
        }
        bar.Children.Add(IconButton("\uE738", "chart.zoom_out", () => { Zoom(.8f); return Task.CompletedTask; }));
        var actual = QuietButton("100%", () => { scroll.ChangeView(null, null, 1); return Task.CompletedTask; }); ToolTipService.SetToolTip(actual, T("chart.zoom_actual")); bar.Children.Add(actual); scroll.ViewChanged += (_, _) => actual.Content = Text(Math.Round(scroll.ZoomFactor * 100) + "%", 12);
        bar.Children.Add(IconButton("\uE710", "chart.zoom_in", () => { Zoom(1.25f); return Task.CompletedTask; }));
        bar.Children.Add(IconButton("\uE9A6", "chart.fit", () => { Fit(true); return Task.CompletedTask; })); bar.Children.Add(closed); bar.Children.Add(links);
        content.Children.Add(Quiet(T("org.kind_formal") + " · " + T("org.kind_subgroup") + " · " + T("org.cabinet_chip") + " · " + T("chart.legend_ended") + " · " + T("chart.legend_shared"), 11));
        content.Children.Add(Quiet(T("chart.pan_hint"), 11)); content.Children.Add(scroll);
        void Draw()
        {
            canvas.Children.Clear(); positions.Clear();
            var nodes = data.Rows("orgs").Where(o => chartClosed || o.Text("status") == "active").ToArray();
            if (nodes.Length == 0) { canvas.Width = 600; canvas.Height = 300; canvas.Children.Add(Text(T("chart.empty"))); return; }
            var seen = new HashSet<string>(); int slot = 0;
            void Place(JsonNode? node, int depth)
            {
                var id = node.Text("id"); if (!seen.Add(id)) return;
                var children = nodes.Where(n => n.Text("parent") == id && !seen.Contains(n.Text("id"))).ToArray();
                foreach (var child in children) Place(child, depth + 1);
                var childPoints = children.Where(c => positions.ContainsKey(c.Text("id"))).Select(c => positions[c.Text("id")].X).ToArray();
                positions[id] = (childPoints.Length > 0 ? (childPoints.Min() + childPoints.Max()) / 2 : 30 + slot++ * 270, 30 + depth * 138);
            }
            foreach (var node in nodes.Where(n => !nodes.Any(p => p.Text("id") == n.Text("parent"))).Concat(nodes)) Place(node, 0);
            canvas.Width = positions.Values.Max(p => p.X) + 320; canvas.Height = positions.Values.Max(p => p.Y) + 124;
            foreach (var node in nodes)
            {
                if (!positions.TryGetValue(node.Text("parent"), out var parent)) continue;
                var point = positions[node.Text("id")];
                var edge = new Polyline { Stroke = Muted, StrokeThickness = 1, Points = new PointCollection { new(parent.X + 118, parent.Y + 94), new(parent.X + 118, parent.Y + 116), new(point.X + 118, parent.Y + 116), new(point.X + 118, point.Y) } };
                if (node.Text("status") != "active") edge.StrokeDashArray = new DoubleCollection { 4, 4 }; canvas.Children.Add(edge);
            }
            var sharedLines = new List<(string A, string B, Shape Shape)>(); var tips = new Dictionary<string, List<string>>();
            foreach (var shared in data.Rows("shared"))
            {
                var seats = shared.Rows("seats").Where(s => positions.ContainsKey(s.Text("org"))).ToArray();
                foreach (var seat in seats)
                {
                    var id = seat.Text("org"); if (!tips.ContainsKey(id)) tips[id] = [];
                    tips[id].Add(T("chart.shared_tip", ("member", seat.Text("member")), ("orgs", words.List(seats.Where(s => s.Text("org") != id).Select(s => nodes.FirstOrDefault(n => n.Text("id") == s.Text("org")).Text("name"))))));
                }
                if (!chartLinks) continue;
                for (int i = 0; i < seats.Length; i++) for (int j = i + 1; j < seats.Length; j++)
                {
                    var a = seats[i].Text("org"); var b = seats[j].Text("org"); var p = positions[a]; var q = positions[b];
                    var figure = new PathFigure { StartPoint = new(p.X + 236, p.Y + 47) }; figure.Segments.Add(new BezierSegment { Point1 = new(p.X + 282, p.Y + 47), Point2 = new(q.X + 282, q.Y + 47), Point3 = new(q.X + 236, q.Y + 47) }); var geometry = new PathGeometry(); geometry.Figures.Add(figure);
                    var line = new Microsoft.UI.Xaml.Shapes.Path { Data = geometry, Stroke = Paint("A899D2", "8E7BBA"), StrokeThickness = 1, StrokeDashArray = new DoubleCollection { 4, 3 } };
                    ToolTipService.SetToolTip(line, T("chart.link_tip", ("member", seats[i].Text("member")), ("a", nodes.FirstOrDefault(n => n.Text("id") == a).Text("name")), ("b", nodes.FirstOrDefault(n => n.Text("id") == b).Text("name")))); canvas.Children.Add(line); sharedLines.Add((a, b, line));
                }
            }
            foreach (var node in nodes)
            {
                var id = node.Text("id"); var point = positions[id]; var lead = node.Text("governance") == "peer" ? T("org.gov_peer") : node.Text("leader").Length == 0 ? T("chart.no_leader") : T(node.Flag("cabinet") ? "org.secretary_general_chip" : "org.leader_chip", ("name", node.Text("leader_display").Length > 0 ? node.Text("leader_display") : node.Text("leader")));
                var label = node.Text("name") + "\n" + lead + "\n" + T("common.members", ("n", node.Text("members"))) + " · " + T("chart.decisions", ("n", node.Text("decisions")));
                if (node.Flag("cabinet")) label += "\n" + T("org.cabinet_chip"); if (node.Text("kind") == "subgroup") label += " · " + T("org.kind_subgroup");
                if (tips.ContainsKey(id)) label += "\n" + T("chart.shared", ("n", tips[id].Count));
                var button = Button("", async () => { visibleDialog?.Hide(); await Select(id); }); button.Width = 236; button.Height = 94; button.Opacity = node.Text("status") == "active" ? 1 : .55; button.CornerRadius = new CornerRadius(11); button.Padding = new Thickness(10); button.HorizontalContentAlignment = HorizontalAlignment.Stretch; button.Background = Paint("FFFFFF", "252523"); button.BorderBrush = id == org ? Accent : Line; button.BorderThickness = new Thickness(id == org ? 2 : 1);
                var badges = new ActionRow { Spacing = 4 }; badges.Children.Add(Badge(T("common.members", ("n", node.Text("members"))))); badges.Children.Add(Badge(T("chart.decisions", ("n", node.Text("decisions"))), node.Text("decisions") != "0")); if (tips.ContainsKey(id)) badges.Children.Add(Badge(T("chart.shared", ("n", tips[id].Count))));
                var title = Ellipsis(node.Text("name"), 13); title.FontWeight = Microsoft.UI.Text.FontWeights.SemiBold; UIElement nodeTitle = node.Text("kind") == "subgroup" ? TwoColumns(title, Badge(T("org.kind_subgroup"))) : node.Flag("cabinet") ? TwoColumns(title, Badge(T("org.cabinet_chip"), true)) : title; var nodeContent = Stack(nodeTitle, Ellipsis(lead, 11), badges); nodeContent.Spacing = 4; button.Content = nodeContent; Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(button, label);
                ToolTipService.SetToolTip(button, T("chart.open_hint", ("name", node.Text("name"))) + "\n" + node.Text("purpose") + "\n" + string.Join("\n", tips.GetValueOrDefault(id, [])));
                void Highlight(bool on) { foreach (var (a, b, line) in sharedLines) { line.Opacity = on && a != id && b != id ? .15 : 1; line.StrokeThickness = on && (a == id || b == id) ? 2 : 1; } }
                button.PointerEntered += (_, _) => Highlight(true); button.PointerExited += (_, _) => Highlight(false); button.GotFocus += (_, _) => Highlight(true); button.LostFocus += (_, _) => Highlight(false);
                var nodeSurface = new Grid { Width = 236, Height = 94 }; nodeSurface.Children.Add(button);
                if (node.Text("kind") == "subgroup") { button.BorderThickness = new Thickness(0); nodeSurface.Children.Add(new Rectangle { RadiusX = 11, RadiusY = 11, Stroke = id == org ? Accent : Paint("D2CEC6", "514E48"), StrokeThickness = id == org ? 2 : 1, StrokeDashArray = new DoubleCollection { 4, 3 }, IsHitTestVisible = false }); }
                Canvas.SetLeft(nodeSurface, point.X); Canvas.SetTop(nodeSurface, point.Y); canvas.Children.Add(nodeSurface);
            }
        }
        closed.Checked += (_, _) => { chartClosed = true; Draw(); }; closed.Unchecked += (_, _) => { chartClosed = false; Draw(); };
        links.Checked += (_, _) => { chartLinks = true; Draw(); }; links.Unchecked += (_, _) => { chartLinks = false; Draw(); };
        canvas.ManipulationDelta += (_, e) => scroll.ChangeView(scroll.HorizontalOffset - e.Delta.Translation.X, scroll.VerticalOffset - e.Delta.Translation.Y, null);
        canvas.PointerWheelChanged += (_, e) => { var point = e.GetCurrentPoint(scroll); Zoom(point.Properties.MouseWheelDelta > 0 ? 1.15f : 1 / 1.15f, point.Position.X, point.Position.Y); e.Handled = true; };
        canvas.DoubleTapped += (_, e) => { if (ReferenceEquals(e.OriginalSource, canvas)) Fit(true); };
        scroll.KeyDown += (_, e) =>
        {
            switch (e.Key)
            {
                case VirtualKey.Add: Zoom(1.25f); break; case VirtualKey.Subtract: Zoom(.8f); break; case VirtualKey.Number0: Fit(true); break;
                case VirtualKey.Left: scroll.ChangeView(scroll.HorizontalOffset - 60, null, null); break; case VirtualKey.Right: scroll.ChangeView(scroll.HorizontalOffset + 60, null, null); break;
                case VirtualKey.Up: scroll.ChangeView(null, scroll.VerticalOffset - 60, null); break; case VirtualKey.Down: scroll.ChangeView(null, scroll.VerticalOffset + 60, null); break;
                default: return;
            }
            e.Handled = true;
        };
        Draw(); scroll.Loaded += (_, _) => Fit(focus.Length == 0);
        refreshChart = async () => { data = await api!.Get("/api/orgchart"); Draw(); };
        try { await Show(T("chart.title"), content); } finally { refreshChart = null; }
    }
}
