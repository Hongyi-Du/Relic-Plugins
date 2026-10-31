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
    // The native visual tree can retain a COM Border after its original managed
    // wrapper becomes otherwise unreachable. Keep the registered wrapper alive
    // only while mounted, so a later tree walk observes the same registration.
    // Unloaded releases this hold; event closures retain the registration if the
    // same production block is subsequently mounted again.
    private static readonly Dictionary<Border, FencedCode> mountedFencedCodes = new();

    internal static Border RegisterFencedCode(Border container, ScrollViewer scroller, TextBlock text)
    {
        if (!ReferenceEquals(container.Child, scroller) || !ReferenceEquals(scroller.Content, text))
            throw new ArgumentException("Fenced code registration must identify its actual Border.Child and ScrollViewer.Content.");
        var content = new FencedCode(scroller, text);
        fencedCodes.Add(container, content);
        container.Loaded += (_, _) => mountedFencedCodes[container] = content;
        container.Unloaded += (_, _) => mountedFencedCodes.Remove(container);
        if (container.IsLoaded) mountedFencedCodes[container] = content;
        return container;
    }

    internal static bool TryGetFencedCode(Border container, out FencedCode? content) =>
        fencedCodes.TryGetValue(container, out content);
}
