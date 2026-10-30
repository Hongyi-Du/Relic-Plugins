using Microsoft.UI.Xaml.Controls;
using System.Runtime.CompilerServices;

namespace Relic;

// Production content identity, retained independently of capture. A painted
// Border is not sufficient to identify fenced Markdown: only Rich's actual
// fenced-code construction registers this exact container and its content.
internal static class MarkdownSemantic
{
    internal sealed record FencedCode(ScrollViewer Scroller, TextBlock Text);

    private static readonly ConditionalWeakTable<Border, FencedCode> fencedCodes = new();

    internal static Border RegisterFencedCode(Border container, ScrollViewer scroller, TextBlock text)
    {
        if (!ReferenceEquals(container.Child, scroller) || !ReferenceEquals(scroller.Content, text))
            throw new ArgumentException("Fenced code registration must identify its actual Border.Child and ScrollViewer.Content.");
        fencedCodes.Add(container, new FencedCode(scroller, text));
        return container;
    }

    internal static bool TryGetFencedCode(Border container, out FencedCode? content) =>
        fencedCodes.TryGetValue(container, out content);
}
