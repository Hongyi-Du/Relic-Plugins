using System.Globalization;
using System.Text.Json.Nodes;

namespace Relic.Core;

// Inputs are a captured, read-only server response and copied local state.
// Preparing a timeline must not read a window, mutable preferences or controls.
public sealed record ConversationPresentationInput(
    string Organization, string Member, JsonArray Messages, JsonNode Snapshot,
    JsonNode Transcript, JsonNode Live, ConversationPresentationWords Words,
    DateTime Today, bool PlainMode, IReadOnlySet<string> PlainOne,
    IReadOnlyDictionary<string, string> Plain, IReadOnlySet<string> PlainFailed,
    IReadOnlyDictionary<string, string> MessageIdentities);

public sealed record ConversationPresentationWords(string Language, string Today, string Yesterday,
    string HumanName, string AutoWoken, string SeatBriefing, string ParentSession, string TaskFrom);

public sealed record ConversationPresentationRow(JsonNode Item, string Key, string? Separator,
    bool Continued, double Estimate, string Identity);

public static class ConversationPresentation
{
    public static IReadOnlyList<ConversationPresentationRow> Prepare(ConversationPresentationInput input,
        CancellationToken cancellation = default)
    {
        cancellation.ThrowIfCancellationRequested();
        var rows = new List<ConversationPresentationRow>();
        string day = ""; JsonNode? previous = null; var ordinal = 0;
        foreach (var item in Items(input, cancellation))
        {
            cancellation.ThrowIfCancellationRequested();
            var id = item.Text("id"); var type = item.Text("type"); var at = item.Text("at");
            var key = id.Length > 0 ? (type == "message" ? "message:" : "item:") + id
                : "transcript:" + at + ":" + type + ":" + ordinal;
            ordinal++;
            var date = DateTimeOffset.TryParse(at, out var parsed) ? parsed.LocalDateTime.Date.ToString("yyyy-MM-dd") : "";
            string? separator = null;
            if (date != day && date.Length > 0)
            {
                separator = When(parsed, input.Words, input.Today); day = date; previous = null;
            }
            else if (previous != null && DateTimeOffset.TryParse(previous.Text("at"), out var prior)
                && parsed - prior > TimeSpan.FromMinutes(20))
            { separator = parsed.ToLocalTime().ToString("HH:mm"); previous = null; }
            var continued = Transcript.SameMessageGroup(previous, item!);
            var estimateText = item.Text("body").Length >= item.Text("text").Length ? item.Text("body") : item.Text("text");
            var estimate = type == "message" ? EstimateMessageHeight(estimateText) : 40;
            var plainKey = input.Organization + "/" + id;
            var identity = (input.MessageIdentities.GetValueOrDefault(id) ?? item!.ToJsonString())
                + "/" + continued + "/" + input.PlainMode + "/" + input.PlainOne.Contains(plainKey)
                + "/" + input.Plain.GetValueOrDefault(plainKey) + "/" + input.PlainFailed.Contains(plainKey);
            rows.Add(new(item!, key, separator, continued, estimate, identity));
            if (type != "acts") previous = item;
        }
        cancellation.ThrowIfCancellationRequested();
        return rows.AsReadOnly();
    }

    // The height a message row is laid out at until it is built; the list
    // places unbuilt rows by it and estimates the rest from what it has placed.
    // Counting characters only put a six-line message at 101 px for its 171 px,
    // and two hundred such rows a page left the list thousands of pixels off.
    // Lines as rendered at the chat's usual width: a wide (CJK) character
    // takes about two narrow ones, about 110 narrow ones fit a line, every
    // non-empty source line starts a new one and a blank one is a paragraph
    // gap; a table row or code line is one line. (171 px and 2010 px rows of
    // the synthetic CI data come out at 172 and 2047.)
    public static double EstimateMessageHeight(string body)
    {
        double height = 64; var fenced = false;
        foreach (var raw in body.Split('\n'))
        {
            var line = raw.TrimEnd('\r'); var trimmed = line.Trim();
            if (trimmed.StartsWith("```", StringComparison.Ordinal)) { fenced = !fenced; height += 12; continue; }
            if (fenced) { height += 20; continue; }
            if (trimmed.Length == 0) { height += 8; continue; }
            if (trimmed.StartsWith('|')) { height += 30; continue; }
            var width = 0;
            foreach (var rune in line.EnumerateRunes()) width += Wide(rune.Value) ? 2 : 1;
            height += Math.Max(1, Math.Ceiling(width / 110d)) * 23;
        }
        return Math.Clamp(height, 64, 4000);
    }
    private static bool Wide(int value) => value is (>= 0x1100 and <= 0x115F) or (>= 0x2E80 and <= 0xA4CF)
        or (>= 0xAC00 and <= 0xD7A3) or (>= 0xF900 and <= 0xFAFF) or (>= 0xFE30 and <= 0xFE4F)
        or (>= 0xFF00 and <= 0xFF60) or (>= 0xFFE0 and <= 0xFFE6) or (>= 0x1F300 and <= 0x1F64F) or (>= 0x20000 and <= 0x3FFFD);

    private static string When(DateTimeOffset date, ConversationPresentationWords words, DateTime today)
    {
        var day = date.LocalDateTime.Date;
        var culture = CultureInfo.GetCultureInfo(words.Language);
        var label = day == today ? words.Today : day == today.AddDays(-1) ? words.Yesterday
            : day.ToString(day.Year == today.Year ? culture.DateTimeFormat.MonthDayPattern
                : words.Language == "zh-CN" ? "yyyy年M月d日" : "MMMM d, yyyy", culture);
        return label + " " + date.ToLocalTime().ToString("HH:mm", CultureInfo.InvariantCulture);
    }

    private static IEnumerable<JsonNode?> Items(ConversationPresentationInput input, CancellationToken cancellation)
    {
        if (input.Member.Length == 0) return input.Messages;
        var members = input.Snapshot.Rows("members");
        var m = members.FirstOrDefault(row => row.Text("name") == input.Member);
        string Display(string name) => name == "human" ? input.Words.HumanName
            : members.FirstOrDefault(row => row.Text("name") == name).Text("display") is { Length: > 0 } display ? display : name;
        var output = new List<JsonNode?>();
        var busy = input.Live["status"].Text("state") is "running" or "starting" or "waiting";
        var cut = busy ? input.Live.Rows("items").LastOrDefault(row => row.Flag("start")).Text("at") : "";
        JsonObject? actions = null;
        void Flush() { if (actions != null) { output.Add(actions); actions = null; } }
        foreach (var step in input.Transcript.Rows("steps"))
        {
            cancellation.ThrowIfCancellationRequested();
            if (cut.Length > 0 && string.CompareOrdinal(step.Text("at"), cut) >= 0) continue;
            var role = step.Text("role"); var text = step.Text("text"); var at = step.Text("at");
            if (role is "tool_call" or "tool_result")
            {
                actions ??= new JsonObject { ["type"] = "acts", ["at"] = at, ["member"] = input.Member, ["steps"] = new JsonArray() };
                actions.Rows("steps").Add(step?.DeepClone()); continue;
            }
            Flush();
            if (role is not ("user" or "assistant")) continue;
            var from = role == "assistant" ? input.Member : "human"; var type = "message";
            if (role == "user")
            {
                if (text.StartsWith(Transcript.PersonPrefix)) text = Transcript.PersonText(text);
                else if (text.StartsWith("[Relic auto-wake]")) { type = "notice"; text = input.Words.AutoWoken; }
                else if (text.StartsWith("You now hold the seat")) { type = "notice"; text = input.Words.SeatBriefing; }
                else if (m.Text("agent").Length > 0) from = m.Text("parent").Length > 0 ? m.Text("parent") : input.Member;
            }
            var fromLabel = role == "user" && from != "human"
                ? input.Words.TaskFrom.Replace("{name}", m.Text("parent").Length > 0 ? Display(m.Text("parent")) : input.Words.ParentSession)
                : Display(from);
            output.Add(new JsonObject { ["type"] = type, ["from"] = from, ["fromLabel"] = fromLabel,
                ["to"] = new JsonArray(JsonValue.Create(role == "assistant" ? "human" : input.Member)),
                ["body"] = text, ["text"] = text, ["at"] = at });
        }
        Flush();
        if (!m.Flag("embedded") || input.Transcript.Rows("steps").Count == 0) output.AddRange(input.Messages);
        return output.OrderBy(row => row.Text("at"));
    }
}
