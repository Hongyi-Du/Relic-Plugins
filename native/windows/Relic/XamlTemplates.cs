using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Markup;

namespace Relic;

// Parsing a template string costs UI-thread time on every call. A parsed
// template is a shareable factory, so each distinct string is parsed once
// per UI thread and reused by every control that asks for it.
internal static class XamlTemplates
{
    [ThreadStatic] private static Dictionary<string, FrameworkTemplate>? parsed;

    internal static T Load<T>(string xaml) where T : FrameworkTemplate
    {
        parsed ??= new(StringComparer.Ordinal);
        if (parsed.TryGetValue(xaml, out var known)) return (T)known;
        var template = (T)XamlReader.Load(xaml);
        // Templates are built from a fixed set of strings; the bound only
        // guards against an unexpected stream of distinct ones.
        if (parsed.Count < 512) parsed[xaml] = template;
        return template;
    }
}
