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
            var bodyLength = Math.Max(item.Text("body").Length, item.Text("text").Length);
            var estimate = type == "message" ? Math.Clamp(64 + bodyLength / 70d * 23, 64, 2100) : 40;
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
