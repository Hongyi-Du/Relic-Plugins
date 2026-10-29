using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Relic.Core;

public static class Transcript
{
    public const string PersonPrefix = "[Relic App] The person (human) writes to you directly:";
    public static string PersonText(string text) => text.StartsWith(PersonPrefix)
        ? Regex.Replace(text[PersonPrefix.Length..], @"\n\nReply in this conversation;[\s\S]*$", "").Trim() : text;

    // Parallel tool calls precede their results. Match the oldest outstanding call,
    // retaining orphan results rather than dropping evidence from the transcript.
    public static IReadOnlyList<(JsonNode? Call, JsonNode? Result)> PairTools(IEnumerable<JsonNode?> steps)
    {
        var rows = new List<(JsonNode? Call, JsonNode? Result)>(); var waiting = new Queue<int>();
        foreach (var step in steps)
            if (step.Text("role") == "tool_call") { waiting.Enqueue(rows.Count); rows.Add((step, null)); }
            else if (waiting.TryDequeue(out var index)) rows[index] = (rows[index].Call, step);
            else rows.Add((null, step));
        return rows;
    }
    public static bool SameMessageGroup(JsonNode? previous, JsonNode current)
    {
        if (previous == null || previous.Text("type") != "message" || current.Text("type") != "message" || previous["thread"] != null || previous.Text("from") != current.Text("from")) return false;
        if (!JsonNode.DeepEquals(previous["to"], current["to"])) return false;
        return DateTimeOffset.TryParse(previous.Text("at"), out var first) && DateTimeOffset.TryParse(current.Text("at"), out var last) && last >= first && last - first < TimeSpan.FromMinutes(3);
    }
}
