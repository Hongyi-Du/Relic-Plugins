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
        var scroll = new ScrollViewer { ZoomMode = ZoomMode.Enabled, MinZoomFactor = .15f, MaxZoomFactor = 2, HorizontalScrollBarVisibility = ScrollBarVisibility.Auto, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, Height = Math.Min(600, root.ActualHeight - 220), Width = Math.Min(860, root.ActualWidth - 180), IsTabStop = true };
        var canvas = new Canvas { Background = new SolidColorBrush(Colors.Transparent), ManipulationMode = ManipulationModes.TranslateX | ManipulationModes.TranslateY }; scroll.Content = canvas;
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
            var width = values.Max(p => p.X) + 250 - left; var height = values.Max(p => p.Y) + 150 - top;
            var zoom = Math.Clamp((float)Math.Min(scroll.Width / width, scroll.Height / height), .15f, 1);
            scroll.ChangeView(Math.Max(0, (left + width / 2) * zoom - scroll.Width / 2), Math.Max(0, (top + height / 2) * zoom - scroll.Height / 2), zoom);
        }
        void Zoom(float amount, double? x = null, double? y = null)
        {
            var zoom = Math.Clamp(scroll.ZoomFactor * amount, .15f, 2); var ratio = zoom / scroll.ZoomFactor;
            var px = x ?? scroll.Width / 2; var py = y ?? scroll.Height / 2;
            scroll.ChangeView((scroll.HorizontalOffset + px) * ratio - px, (scroll.VerticalOffset + py) * ratio - py, zoom, true);
        }
        bar.Children.Add(Button(T("chart.zoom_out"), () => { Zoom(.8f); return Task.CompletedTask; }));
        bar.Children.Add(Button(T("chart.zoom_actual"), () => { scroll.ChangeView(null, null, 1); return Task.CompletedTask; }));
        bar.Children.Add(Button(T("chart.zoom_in"), () => { Zoom(1.25f); return Task.CompletedTask; }));
        bar.Children.Add(Button(T("chart.fit"), () => { Fit(true); return Task.CompletedTask; })); bar.Children.Add(closed); bar.Children.Add(links);
        content.Children.Add(Text(T("org.kind_formal") + " · " + T("org.kind_subgroup") + " · " + T("org.cabinet_chip") + " · " + T("chart.legend_ended") + " · " + T("chart.legend_shared"), 12));
        content.Children.Add(Text(T("chart.pan_hint"), 12)); content.Children.Add(scroll);
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
                positions[id] = (childPoints.Length > 0 ? (childPoints.Min() + childPoints.Max()) / 2 : 30 + slot++ * 260, 30 + depth * 170);
            }
            foreach (var node in nodes.Where(n => !nodes.Any(p => p.Text("id") == n.Text("parent"))).Concat(nodes)) Place(node, 0);
            canvas.Width = positions.Values.Max(p => p.X) + 320; canvas.Height = positions.Values.Max(p => p.Y) + 170;
            foreach (var node in nodes)
            {
                if (!positions.TryGetValue(node.Text("parent"), out var parent)) continue;
                var point = positions[node.Text("id")];
                var edge = new Polyline { Stroke = new SolidColorBrush(Colors.Gray), StrokeThickness = 2, Points = new PointCollection { new(parent.X + 115, parent.Y + 120), new(parent.X + 115, parent.Y + 140), new(point.X + 115, parent.Y + 140), new(point.X + 115, point.Y) } };
                if (node.Text("status") != "active") edge.StrokeDashArray = new DoubleCollection { 4, 4 }; canvas.Children.Add(edge);
            }
            var sharedLines = new List<(string A, string B, Line Shape)>(); var tips = new Dictionary<string, List<string>>();
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
                    var line = new Line { X1 = p.X + 230, Y1 = p.Y + 60, X2 = q.X + 230, Y2 = q.Y + 60, Stroke = new SolidColorBrush(Colors.CornflowerBlue), StrokeThickness = 2, StrokeDashArray = new DoubleCollection { 5, 3 } };
                    ToolTipService.SetToolTip(line, T("chart.link_tip", ("member", seats[i].Text("member")), ("a", nodes.FirstOrDefault(n => n.Text("id") == a).Text("name")), ("b", nodes.FirstOrDefault(n => n.Text("id") == b).Text("name")))); canvas.Children.Add(line); sharedLines.Add((a, b, line));
                }
            }
            foreach (var node in nodes)
            {
                var id = node.Text("id"); var point = positions[id]; var lead = node.Text("governance") == "peer" ? T("org.gov_peer") : node.Text("leader").Length == 0 ? T("chart.no_leader") : T(node.Flag("cabinet") ? "org.secretary_general_chip" : "org.leader_chip", ("name", node.Text("leader_display").Length > 0 ? node.Text("leader_display") : node.Text("leader")));
                var label = node.Text("name") + "\n" + lead + "\n" + T("common.members", ("n", node.Text("members"))) + " · " + T("chart.decisions", ("n", node.Text("decisions")));
                if (node.Flag("cabinet")) label += "\n" + T("org.cabinet_chip"); if (node.Text("kind") == "subgroup") label += " · " + T("org.kind_subgroup");
                if (tips.ContainsKey(id)) label += "\n" + T("chart.shared", ("n", tips[id].Count));
                var button = Button(label, async () => { visibleDialog?.Hide(); await Select(id); }); button.Width = 230; button.Height = 130; button.Opacity = node.Text("status") == "active" ? 1 : .55;
                ToolTipService.SetToolTip(button, T("chart.open_hint", ("name", node.Text("name"))) + "\n" + node.Text("purpose") + "\n" + string.Join("\n", tips.GetValueOrDefault(id, [])));
                void Highlight(bool on) { foreach (var (a, b, line) in sharedLines) { line.Opacity = on && a != id && b != id ? .15 : 1; line.StrokeThickness = on && (a == id || b == id) ? 4 : 2; } }
                button.PointerEntered += (_, _) => Highlight(true); button.PointerExited += (_, _) => Highlight(false); button.GotFocus += (_, _) => Highlight(true); button.LostFocus += (_, _) => Highlight(false);
                Canvas.SetLeft(button, point.X); Canvas.SetTop(button, point.Y); canvas.Children.Add(button);
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
