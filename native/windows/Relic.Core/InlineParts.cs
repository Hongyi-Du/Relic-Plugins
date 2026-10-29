using System.Text.RegularExpressions;

namespace Relic.Core;

public record InlinePart(string Kind, string Text, string Target = "");
public static class InlineParts
{
    // Match app.js inlineTokens, including its ASCII word boundaries and
    // ECMAScript whitespace (which differs from .NET's default \s).
    private const string JavaScriptSpace = @"\u0009-\u000D\u0020\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000\uFEFF";
    private static readonly Regex Tokens = new("""`(?<code>[^`\n]+)`|\*\*(?<bold>[^*\n]+)\*\*|(?<url>https?://[^\s<>)）\]]+)|(?<path>\b[A-Za-z]:[\\/][^\s<>"'|*?，。；：、（）)\]【】「」《》“”]+|(?<![\w./:\\])/(?!/)[^\s<>"'`|*?，。；：、（）)\]【】「」《》“”]+)""".Replace(@"\s", JavaScriptSpace), RegexOptions.Compiled | RegexOptions.ECMAScript);
    public static bool IsAbsolute(string value) => Regex.IsMatch(value, @"^(?:[A-Za-z]:[\\/]|/(?!/))") && !value.Contains('\n') && !value.Contains('\r');
    public static (string Path, int Line) PathTarget(string value)
    {
        var match = Regex.Match(value, @"^(.*?)(?::([0-9]+))?(?::[0-9]+)?$");
        return (match.Groups[1].Value, int.TryParse(match.Groups[2].Value, out var line) ? line : 0);
    }
    public static IEnumerable<InlinePart> Parse(string value)
    {
        int start = 0;
        foreach (Match match in Tokens.Matches(value))
        {
            if (match.Index > start) yield return new("text", value[start..match.Index]);
            if (match.Groups["code"].Success) yield return new("code", match.Groups["code"].Value);
            else if (match.Groups["bold"].Success) yield return new("bold", match.Groups["bold"].Value);
            else if (match.Groups["url"].Success) yield return new("url", match.Value, match.Value);
            else { var path = match.Value.TrimEnd('.', ',', ';', ':', '!', '?'); yield return new("path", path, path); if (path.Length < match.Length) yield return new("text", match.Value[path.Length..]); }
            start = match.Index + match.Length;
        }
        if (start < value.Length) yield return new("text", value[start..]);
    }
}
