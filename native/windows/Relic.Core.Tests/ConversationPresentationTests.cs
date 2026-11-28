using System.Globalization;
using System.Text.Json.Nodes;
using Relic.Core;
using Xunit;

namespace Relic.Core.Tests;

public sealed class ConversationPresentationTests
{
    private static readonly DateTime Today = new(2026, 10, 30);
    private static string At(int minutes, int days = 0) => new DateTimeOffset(
        DateTime.SpecifyKind(Today.AddDays(days).AddHours(12).AddMinutes(minutes), DateTimeKind.Local)).ToString("O");
    private static JsonObject Message(string id, int minutes, string body = "body", int days = 0) => new()
    {
        ["id"] = id, ["type"] = "message", ["from"] = "agent", ["to"] = new JsonArray("human"),
        ["at"] = At(minutes, days), ["body"] = body
    };
    private static ConversationPresentationInput Input(JsonArray messages) => new("org", "", messages,
        new JsonObject(), new JsonObject(), new JsonObject(),
        new("en-US", "Today", "Yesterday", "You", "Auto-woken", "Seat briefing", "Parent", "Task from {name}"),
        Today, false, new HashSet<string>(), new Dictionary<string, string>(), new HashSet<string>(),
        new Dictionary<string, string>());

    [Fact]
    public void KeepsOrderAndGroupBoundariesWhilePreparingSeparatorsAndIdentities()
    {
        var first = Message("1", 0); var second = Message("2", 1); var gap = Message("3", 23);
        var yesterday = Message("4", 0, days: -1);
        var input = Input(new(first, second, gap, yesterday)) with
        {
            PlainMode = true, PlainOne = new HashSet<string> { "org/2" },
            Plain = new Dictionary<string, string> { ["org/2"] = "plain text" },
            MessageIdentities = new Dictionary<string, string> { ["2"] = "cached body" }
        };
        var rows = ConversationPresentation.Prepare(input);
        Assert.Equal(new[] { "message:1", "message:2", "message:3", "message:4" }, rows.Select(row => row.Key));
        Assert.Equal("Today 12:00", rows[0].Separator);
        Assert.Null(rows[1].Separator); Assert.True(rows[1].Continued);
        Assert.Equal("12:23", rows[2].Separator); Assert.False(rows[2].Continued);
        Assert.Equal("Yesterday 12:00", rows[3].Separator);
        Assert.Equal("cached body/True/True/True/plain text/False", rows[1].Identity);
        Assert.Same(second, rows[1].Item);
        Assert.Equal(64 + 23, rows[0].Estimate);
    }

    [Fact]
    public void DoesNotLimitHistoryOrMutateServerResponses()
    {
        var messages = new JsonArray(Enumerable.Range(0, 5500)
            .Select(index => (JsonNode)Message(index.ToString(), index, index == 5499 ? new string('x', 11251) : "body")).ToArray());
        var input = Input(messages); var before = messages.ToJsonString();
        var rows = ConversationPresentation.Prepare(input);
        Assert.Equal(5500, rows.Count); Assert.Equal("message:5499", rows[^1].Key);
        Assert.Equal(64 + 103 * 23, rows[^1].Estimate); Assert.Equal(before, messages.ToJsonString());
    }

    [Fact]
    public void PrivateTranscriptRetainsToolGroupingPersonTextAndLiveCutoff()
    {
        JsonObject Step(string role, int minute, string text) => new() { ["role"] = role, ["at"] = At(minute), ["text"] = text };
        var steps = new JsonArray(
            Step("user", 0, Transcript.PersonPrefix + "\nhello\n\nReply in this conversation; transport"),
            Step("tool_call", 1, "call"), Step("tool_result", 2, "result"),
            Step("assistant", 3, "reply"), Step("user", 4, "parent task"),
            Step("user", 5, "[Relic auto-wake] transport"), Step("assistant", 6, "live duplicate"));
        var input = Input(new(Message("store", 0))) with
        {
            Member = "worker",
            Snapshot = new JsonObject { ["members"] = new JsonArray(
                new JsonObject { ["name"] = "worker", ["display"] = "Worker", ["embedded"] = true, ["agent"] = "a", ["parent"] = "boss" },
                new JsonObject { ["name"] = "boss", ["display"] = "Boss" }) },
            Transcript = new JsonObject { ["steps"] = steps },
            Live = new JsonObject { ["status"] = new JsonObject { ["state"] = "running" },
                ["items"] = new JsonArray(new JsonObject { ["start"] = true, ["at"] = At(6) }) }
        };
        var before = steps.ToJsonString(); var rows = ConversationPresentation.Prepare(input);
        Assert.Equal(5, rows.Count);
        Assert.Equal("hello", rows[0].Item.Text("body")); Assert.Equal("You", rows[0].Item.Text("fromLabel"));
        Assert.Equal("acts", rows[1].Item.Text("type")); Assert.Equal(2, rows[1].Item.Rows("steps").Count);
        Assert.Equal("Worker", rows[2].Item.Text("fromLabel"));
        Assert.Equal("boss", rows[3].Item.Text("from")); Assert.Equal("Task from Boss", rows[3].Item.Text("fromLabel"));
        Assert.Equal("notice", rows[4].Item.Text("type")); Assert.Equal("Auto-woken", rows[4].Item.Text("text"));
        Assert.DoesNotContain(rows, row => row.Key == "message:store" || row.Item.Text("body") == "live duplicate");
        Assert.Equal(before, steps.ToJsonString());
    }

    [Fact]
    public void CapturedLanguageControlsRelativeAndCalendarDates()
    {
        var input = Input(new(Message("1", 0), Message("2", 0, days: -1), Message("3", 0, days: -10)));
        var english = ConversationPresentation.Prepare(input);
        var chinese = ConversationPresentation.Prepare(input with
        { Words = input.Words with { Language = "zh-CN", Today = "今天", Yesterday = "昨天" } });
        Assert.Equal("Today 12:00", english[0].Separator); Assert.Equal("今天 12:00", chinese[0].Separator);
        Assert.Equal("昨天 12:00", chinese[1].Separator);
        var culture = CultureInfo.GetCultureInfo("zh-CN");
        Assert.Equal(Today.AddDays(-10).ToString(culture.DateTimeFormat.MonthDayPattern, culture) + " 12:00", chinese[2].Separator);
        Assert.Equal("Today 12:00", english[0].Separator);
    }

    [Fact]
    public void CanceledNavigationDoesNotPrepareAResult()
    {
        using var cancellation = new CancellationTokenSource(); cancellation.Cancel();
        Assert.ThrowsAny<OperationCanceledException>(() => ConversationPresentation.Prepare(Input(new(Message("1", 0))), cancellation.Token));
    }
}
