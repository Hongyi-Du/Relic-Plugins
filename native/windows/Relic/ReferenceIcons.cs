using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.RegularExpressions;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Windows.Foundation;
using NativePath = Microsoft.UI.Xaml.Shapes.Path;

namespace Relic;

public sealed partial class MainWindow
{
    // The production reference creates one stroked path per icon, with the exact
    // 24x24 viewBox and data below. These are actual native vector geometries,
    // not a font-glyph equivalence or a raster copy of the reference screenshot.
    private static readonly IReadOnlyDictionary<string, string> ReferenceIconPaths = new ReadOnlyDictionary<string, string>(new Dictionary<string, string>(StringComparer.Ordinal)
    {
        ["plus"] = "M12 5v14M5 12h14",
        ["search"] = "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4",
        ["up"] = "M12 19V5M5 12l7-7 7 7",
        ["panel"] = "M4 5h16v14H4zM15 5v14",
        ["card"] = "M4 6h16v12H4zM8 10h4M8 14h8",
        ["trace"] = "M4 6h10M4 12h16M4 18h12",
        ["stop"] = "M7 7h10v10H7z",
        ["x"] = "M6 6l12 12M18 6L6 18",
        ["bell"] = "M6 16V11a6 6 0 0 1 12 0v5l2 2H4l2-2zM10 20h4",
        ["cc"] = "M4 6h16v12H4zM4 7l8 6 8-6",
        ["gear"] = "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
        ["chev"] = "M9 6l6 6-6 6",
        ["down"] = "M6 9l6 6 6-6",
        ["edit"] = "M4 20h4L19 9l-4-4L4 16zM14 6l4 4",
        ["neworg"] = "M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z",
        ["hash"] = "M5 9h14M5 15h14M10 3L8 21M16 3l-2 18",
        ["mic"] = "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3",
        ["quote"] = "M7 7h4v4H8c0 2 1 3 3 3v2c-3 0-5-2-5-5zM14 7h4v4h-3c0 2 1 3 3 3v2c-3 0-5-2-5-5z",
        ["thread"] = "M4 5h16v10H9l-5 4z",
        ["copy"] = "M8 8h11v11H8zM5 16V5h11",
        ["user"] = "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 20c1.5-4 5-5 8-5s6.5 1 8 5",
        ["palette"] = "M12 3a9 9 0 1 0 0 18c1 0 1.5-.6 1.5-1.4 0-.9-.7-1.3-.7-2.1 0-.8.7-1.5 1.6-1.5H17a4 4 0 0 0 4-4c0-5-4-9-9-9zM7.5 11.5h.01M10 7.5h.01M15 7.5h.01",
        ["globe"] = "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c2.5 2.7 3.5 6 3.5 9s-1 6.3-3.5 9c-2.5-2.7-3.5-6-3.5-9s1-6.3 3.5-9z",
        ["plug"] = "M9 7V3M15 7V3M7 7h10v4a5 5 0 0 1-10 0zM12 16v5",
        ["info"] = "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v6M12 7.5h.01",
        ["folder"] = "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
        ["sec"] = "M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.4 6.8 19.1l1-5.8-4.3-4.1 5.9-.9z",
        ["check"] = "M5 12l5 5 9-10",
        ["file"] = "M6 3h8l4 4v14H6zM14 3v4h4",
        ["lang"] = "M4 5h8M8 3v2M6 5c0 4 3 7 6 8M10 5c-1 4-4 7-6 8M13 21l4-9 4 9M14.5 18h5",
        ["sparkle"] = "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z",
        ["back"] = "M15 6l-6 6 6 6",
        ["fwd"] = "M9 6l6 6-6 6",
        ["sidebar"] = "M4 5h16v14H4zM9 5v14",
        ["work"] = "M4 7h16v12H4zM9 7V5h6v2",
        ["download"] = "M12 4v11M7 10l5 5 5-5M5 20h14",
        ["open"] = "M14 4h6v6M20 4l-9 9M18 14v6H4V6h6",
        ["org"] = "M4 21V8l8-5 8 5v13M9 21v-6h6v6M8.5 11h.01M15.5 11h.01",
        ["minus"] = "M5 12h14",
        ["fit"] = "M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5",
        ["chart"] = "M9 3h6v5H9zM3 16h6v5H3zM15 16h6v5h-6zM12 8v4M6 16v-4h12v4",
    });

    public static IReadOnlyCollection<string> SupportedNames { get; } = ReferenceIconPaths.Keys.ToArray();

    public UIElement ReferenceIcon(string referenceName, double size = 16)
    {
        if (!ReferenceIconPaths.TryGetValue(referenceName, out var pathData))
            throw new ArgumentOutOfRangeException(nameof(referenceName), referenceName, "Unknown reference icon; no substitute glyph is permitted.");
        if (!double.IsFinite(size) || size <= 0)
            throw new ArgumentOutOfRangeException(nameof(size), "The rendered icon size must be finite and positive.");
        return new ReferenceVectorIcon(referenceName, pathData, size, Ink);
    }

    // Kept as a real UserControl so Foreground can follow the owning native
    // ContentPresenter's normal/hover/disabled state, just like currentColor.
    // Consumers may explicitly set Foreground before attaching it to override
    // this automatic brush inheritance (for example a violet plain-word icon).
    public sealed class ReferenceVectorIcon : UserControl
    {
        public string ReferenceName { get; }
        public string PathData { get; }
        public Canvas VectorCanvas { get; }
        public NativePath VectorPath { get; }
        public const double ViewBoxSize = 24;
        public const double ReferenceStrokeWidth = 1.7;
        private readonly Brush fallbackForeground;

        internal ReferenceVectorIcon(string name, string data, double size, Brush foreground)
        {
            ReferenceName = name;
            PathData = data;
            fallbackForeground = foreground;
            Width = Height = size;
            MinWidth = MinHeight = 0;
            Padding = new Thickness(0);
            BorderThickness = new Thickness(0);
            IsTabStop = false;
            IsHitTestVisible = false;
            UseLayoutRounding = false;
            Foreground = foreground;
            VectorPath = new NativePath
            {
                Width = ViewBoxSize, Height = ViewBoxSize,
                Data = ReferencePathParser.Parse(data),
                Fill = null,
                StrokeThickness = ReferenceStrokeWidth,
                StrokeStartLineCap = PenLineCap.Round,
                StrokeEndLineCap = PenLineCap.Round,
                StrokeDashCap = PenLineCap.Round,
                StrokeLineJoin = PenLineJoin.Round,
                StrokeMiterLimit = 4,
                Stretch = Stretch.None,
                UseLayoutRounding = false,
                IsHitTestVisible = false
            };
            VectorPath.SetBinding(Shape.StrokeProperty, new Binding { Source = this, Path = new PropertyPath(nameof(Foreground)), Mode = BindingMode.OneWay });
            VectorCanvas = new Canvas
            {
                Width = ViewBoxSize, Height = ViewBoxSize, UseLayoutRounding = false,
                Clip = new RectangleGeometry { Rect = new Rect(0, 0, ViewBoxSize, ViewBoxSize) }
            };
            VectorCanvas.Children.Add(VectorPath);
            Content = new Viewbox
            {
                Width = size, Height = size, Stretch = Stretch.Uniform,
                StretchDirection = StretchDirection.Both,
                HorizontalAlignment = HorizontalAlignment.Center,
                VerticalAlignment = VerticalAlignment.Center,
                UseLayoutRounding = false,
                Child = VectorCanvas
            };
            Loaded += (_, _) => InheritCurrentColor();
        }

        private void InheritCurrentColor()
        {
            if (!ReferenceEquals(ReadLocalValue(ForegroundProperty), fallbackForeground)) return;
            Control? owner = null;
            for (var parent = VisualTreeHelper.GetParent(this); parent != null; parent = VisualTreeHelper.GetParent(parent))
            {
                if (parent is ContentPresenter presenter)
                {
                    SetBinding(ForegroundProperty, new Binding { Source = presenter, Path = new PropertyPath(nameof(ContentPresenter.Foreground)), Mode = BindingMode.OneWay });
                    return;
                }
                owner ??= parent as Control;
            }
            if (owner != null)
                SetBinding(ForegroundProperty, new Binding { Source = owner, Path = new PropertyPath(nameof(Control.Foreground)), Mode = BindingMode.OneWay });
        }
    }

    // Parse the production SVG command grammar into native PathFigure/Segment
    // objects. Relative commands are resolved explicitly, including the SVG
    // implicit repetition and smooth-curve reflection rules. This avoids a font
    // replacement and avoids relying on a platform-specific SVG string parser.
    private sealed class ReferencePathParser
    {
        private static readonly Regex Token = new("[A-Za-z]|[+-]?(?:[0-9]*\\.[0-9]+|[0-9]+\\.?[0-9]*)(?:[eE][+-]?[0-9]+)?", RegexOptions.CultureInvariant);
        private readonly string[] tokens;
        private int position;
        private Point current, subpathStart, lastCubicControl, lastQuadraticControl;
        private char previousCommand;
        private PathFigure? figure;
        private readonly PathGeometry geometry = new() { FillRule = FillRule.Nonzero };

        private ReferencePathParser(string source)
        {
            var matches = Token.Matches(source);
            var end = 0;
            foreach (Match match in matches)
            {
                if (source[end..match.Index].Any(c => !char.IsWhiteSpace(c) && c != ','))
                    throw new FormatException("Invalid character in reference SVG path.");
                end = match.Index + match.Length;
            }
            if (source[end..].Any(c => !char.IsWhiteSpace(c) && c != ','))
                throw new FormatException("Invalid trailing character in reference SVG path.");
            tokens = matches.Select(m => m.Value).ToArray();
        }

        public static PathGeometry Parse(string source)
        {
            var reader = new ReferencePathParser(source);
            reader.Read();
            return reader.geometry;
        }

        private double Number()
        {
            if (position >= tokens.Length || char.IsLetter(tokens[position][0]))
                throw new FormatException("Missing coordinate in reference SVG path.");
            var value = double.Parse(tokens[position++], NumberStyles.Float, CultureInfo.InvariantCulture);
            if (!double.IsFinite(value)) throw new FormatException("Non-finite coordinate in reference SVG path.");
            return value;
        }

        private bool Flag()
        {
            var value = Number();
            if (value != 0 && value != 1) throw new FormatException("Invalid reference SVG arc flag.");
            return value == 1;
        }

        private Point Point(bool relative)
        {
            var x = Number(); var y = Number();
            return relative ? new Point(current.X + x, current.Y + y) : new Point(x, y);
        }

        private void LineTo(Point target)
        {
            figure!.Segments.Add(new LineSegment { Point = target });
            current = target;
        }

        private void Read()
        {
            char command = '\0';
            while (position < tokens.Length)
            {
                if (char.IsLetter(tokens[position][0])) command = tokens[position++][0];
                else if (command == '\0') throw new FormatException("Reference SVG path must begin with a command.");
                var relative = char.IsLower(command);
                var operation = char.ToUpperInvariant(command);
                if (operation != 'M' && figure == null) throw new FormatException("Reference SVG path must start with moveto.");
                switch (operation)
                {
                    case 'M':
                        current = Point(relative); subpathStart = current;
                        figure = new PathFigure { StartPoint = current, IsFilled = false, IsClosed = false };
                        geometry.Figures.Add(figure);
                        command = relative ? 'l' : 'L';
                        break;
                    case 'L': LineTo(Point(relative)); break;
                    case 'H': { var x = Number(); LineTo(new Point(relative ? current.X + x : x, current.Y)); break; }
                    case 'V': { var y = Number(); LineTo(new Point(current.X, relative ? current.Y + y : y)); break; }
                    case 'C':
                    {
                        var first = Point(relative); var second = Point(relative); var target = Point(relative);
                        figure!.Segments.Add(new BezierSegment { Point1 = first, Point2 = second, Point3 = target });
                        lastCubicControl = second; current = target;
                        break;
                    }
                    case 'S':
                    {
                        var first = previousCommand is 'C' or 'S' ? new Point(2 * current.X - lastCubicControl.X, 2 * current.Y - lastCubicControl.Y) : current;
                        var second = Point(relative); var target = Point(relative);
                        figure!.Segments.Add(new BezierSegment { Point1 = first, Point2 = second, Point3 = target });
                        lastCubicControl = second; current = target;
                        break;
                    }
                    case 'Q':
                    {
                        var control = Point(relative); var target = Point(relative);
                        figure!.Segments.Add(new QuadraticBezierSegment { Point1 = control, Point2 = target });
                        lastQuadraticControl = control; current = target;
                        break;
                    }
                    case 'T':
                    {
                        var control = previousCommand is 'Q' or 'T' ? new Point(2 * current.X - lastQuadraticControl.X, 2 * current.Y - lastQuadraticControl.Y) : current;
                        var target = Point(relative);
                        figure!.Segments.Add(new QuadraticBezierSegment { Point1 = control, Point2 = target });
                        lastQuadraticControl = control; current = target;
                        break;
                    }
                    case 'A':
                    {
                        var rx = Math.Abs(Number()); var ry = Math.Abs(Number()); var rotation = Number();
                        var large = Flag(); var clockwise = Flag(); var target = Point(relative);
                        if (rx == 0 || ry == 0) LineTo(target);
                        else if (target != current)
                        {
                            figure!.Segments.Add(new ArcSegment { Size = new Size(rx, ry), RotationAngle = rotation, IsLargeArc = large,
                                SweepDirection = clockwise ? SweepDirection.Clockwise : SweepDirection.Counterclockwise, Point = target });
                            current = target;
                        }
                        break;
                    }
                    case 'Z':
                        figure!.IsClosed = true; current = subpathStart; command = '\0';
                        break;
                    default: throw new FormatException("Unsupported reference SVG command: " + command);
                }
                previousCommand = operation;
            }
            if (geometry.Figures.Count == 0) throw new FormatException("Reference SVG path is empty.");
        }
    }
}
