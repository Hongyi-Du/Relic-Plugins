using System.Text.RegularExpressions;

namespace Relic.Core;

public record InlinePart(string Kind, string Text, string Target = "");
public static class InlineParts
{
    private static readonly Regex Tokens = new("""\[(?<label>[^\]]+)\]\((?<target>[^\)]+)\)|`(?<code>[^`\n]+)`|\*\*(?<bold>[^*\n]+)\*\*|(?<!\*)\*(?<italic>[^*\n]+)\*(?!\*)|(?<url>https?://[^\s<>)）\]]+)|(?<path>\b[A-Za-z]:[\\/][^\s<>"'|*?，。；：、（）)\]【】「」《》“”]+|(?<![\w./:\\])/(?!/)[^\s<>"'`|*?，。；：、（）)\]【】「」《》“”]+)""", RegexOptions.Compiled);
    public static bool IsAbsolute(string value) => Regex.IsMatch(value, @"^(?:[A-Za-z]:[\\/]|/(?!/))") && !value.Contains('\n') && !value.Contains('\r');
    public static (string Path, int Line) PathTarget(string value)
    {
        var match = Regex.Match(value, @"^(.*?)(?::(\d+))?(?::\d+)?$");
        return (match.Groups[1].Value, int.TryParse(match.Groups[2].Value, out var line) ? line : 0);
    }
    public static IEnumerable<InlinePart> Parse(string value)
    {
        int start = 0;
        foreach (Match match in Tokens.Matches(value))
        {
            if (match.Index > start) yield return new("text", value[start..match.Index]);
            if (match.Groups["label"].Success) yield return new("link", match.Groups["label"].Value, match.Groups["target"].Value);
            else if (match.Groups["code"].Success) { var code = match.Groups["code"].Value; yield return IsAbsolute(code) ? new("link", code, code) : new("code", code); }
            else if (match.Groups["bold"].Success) yield return new("bold", match.Groups["bold"].Value);
            else if (match.Groups["italic"].Success) yield return new("italic", match.Groups["italic"].Value);
            else if (match.Groups["url"].Success) yield return new("link", match.Value, match.Value);
            else { var path = match.Value.TrimEnd('.', ',', ';', ':', '!', '?'); yield return new("link", path, path); if (path.Length < match.Length) yield return new("text", match.Value[path.Length..]); }
            start = match.Index + match.Length;
        }
        if (start < value.Length) yield return new("text", value[start..]);
    }
}
