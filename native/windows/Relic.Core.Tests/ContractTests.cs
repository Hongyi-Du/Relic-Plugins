using System.Net;
using System.Text.Json;
using System.Text.Json.Nodes;
using Relic.Core;
using Xunit;

public class ContractTests
{
    [Fact] public void TranslationLoadingNeverExposesAnInternalKey()
    {
        var words = new Words();
        Assert.Equal("", words.T("composer.voice_title"));
        words.Load(JsonNode.Parse("{\"lang\":\"en-US\",\"strings\":{\"composer.voice_title\":\"Voice input\"}}")!);
        Assert.Equal("Voice input", words.T("composer.voice_title"));
        Assert.Equal("", words.T("missing.key"));
    }
    [Fact] public void HistoryPaginationRetainsOlderNoticesAndRefreshesExistingMessages()
    {
        var older = JsonNode.Parse("[{\"id\":\"e1\",\"type\":\"notice\",\"at\":\"2026-01-01\"},{\"id\":1,\"type\":\"message\",\"at\":\"2026-01-01\",\"body\":\"old\"}]")!.AsArray();
        var latest = JsonNode.Parse("[{\"id\":1,\"type\":\"message\",\"at\":\"2026-01-01\",\"body\":\"new\"},{\"id\":2,\"at\":\"2026-01-02\"}]")!.AsArray();
        var merged = Transcript.MergeMessages(older, latest);
        Assert.Equal(3, merged.Count); Assert.Equal("e1", merged[0].Text("id")); Assert.Equal("new", merged[1].Text("body"));
        Assert.Equal("old", older[1].Text("body"));
    }
    [Fact] public void ListsUseTheSharedLanguageTemplates()
    {
        var words = new Words();
        words.Load(JsonNode.Parse("{\"lang\":\"en-US\",\"strings\":{\"list.pair\":\"{a} and {b}\",\"list.middle\":\"{a}, {b}\",\"list.end\":\"{a}, and {b}\"}}")!);
        Assert.Equal("A and B", words.List(["A", "B"])); Assert.Equal("A, B, and C", words.List(["A", "B", "C"]));
        words.Load(JsonNode.Parse("{\"lang\":\"zh-CN\",\"strings\":{\"list.pair\":\"{a}、{b}\",\"list.middle\":\"{a}、{b}\",\"list.end\":\"{a}、{b}\"}}")!);
        Assert.Equal("甲、乙、丙", words.List(["甲", "乙", "丙"]));
    }
    [Fact] public async Task RejectedReplacementIdentityDoesNotRepeatTheWrite()
    {
        int writes = 0;
        using var client = new Client(39321, "old", new Handler(request =>
        {
            if (request.RequestUri!.AbsolutePath == "/api/lifecycle") return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{\"app\":\"relic\",\"state\":\"running\",\"pid\":11,\"instance\":\"unexpected\"}") });
            writes++; return Task.FromResult(new HttpResponseMessage(HttpStatusCode.Forbidden) { Content = new StringContent("{\"error\":\"missing token\"}") });
        }), () => JsonNode.Parse("{\"port\":39321,\"token\":\"new\",\"pid\":11,\"instance\":\"expected\"}"));
        await Assert.ThrowsAsync<HttpRequestException>(() => client.Post("/api/org/o/send", new { body = "hello" }));
        Assert.Equal(1, writes);
    }
    [Fact] public void InlinePathsRespectUrlsPunctuationAndLineNumbers()
    {
        var parts = InlineParts.Parse("See /tmp/a.py:12:3， and `C:\\work folder\\x.py:4` https://example.com/a/b.").ToArray();
        var links = parts.Where(p => p.Kind == "link").ToArray(); Assert.Equal(3, links.Length);
        Assert.Equal(("/tmp/a.py", 12), InlineParts.PathTarget(links[0].Target));
        Assert.Equal(("C:\\work folder\\x.py", 4), InlineParts.PathTarget(links[1].Target));
        Assert.Equal("https://example.com/a/b.", links[2].Target);
        Assert.Contains(parts, p => p.Kind == "text" && p.Text.Contains('，'));
    }
    [Fact] public async Task TokenRotationRequiresMatchingAuthenticatedLifecycle()
    {
        var writes = 0; var record = JsonNode.Parse("{\"port\":39321,\"token\":\"new\",\"pid\":11,\"instance\":\"i\"}");
        using var client = new Client(39321, "old", new Handler(request =>
        {
            if (request.RequestUri!.AbsolutePath == "/api/lifecycle") return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{\"app\":\"relic\",\"state\":\"running\",\"pid\":11,\"instance\":\"i\"}") });
            writes++;
            return Task.FromResult(request.Headers.GetValues("X-Relic-Token").Single() == "old"
                ? new HttpResponseMessage(HttpStatusCode.Forbidden) { Content = new StringContent("{\"error\":\"missing token\"}") }
                : new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{\"id\":2}") });
        }), () => record);
        Assert.Equal("2", (await client.Post("/api/org/o/send", new { body = "hello" })).Text("id")); Assert.Equal(2, writes);
    }
    [Fact] public void TranscriptPairsParallelCallsWithOldestWaitingResult()
    {
        var steps = JsonNode.Parse("[{\"role\":\"tool_result\",\"text\":\"orphan\"},{\"role\":\"tool_call\",\"tool\":\"A\"},{\"role\":\"tool_call\",\"tool\":\"B\"},{\"role\":\"tool_result\",\"text\":\"first\"},{\"role\":\"tool_result\",\"text\":\"second\",\"error\":true}]")!.AsArray();
        var pairs = Transcript.PairTools(steps);
        Assert.Equal(3, pairs.Count); Assert.Null(pairs[0].Call);
        Assert.Equal("first", pairs[1].Result.Text("text")); Assert.Equal("A", pairs[1].Call.Text("tool"));
        Assert.Equal("second", pairs[2].Result.Text("text")); Assert.True(pairs[2].Result.Flag("error"));
    }
    [Fact] public void PersonPromptDoesNotExposeTransportInstructions()
    {
        Assert.Equal("hello", Transcript.PersonText(Transcript.PersonPrefix + "\nhello\n\nReply in this conversation; transport suffix"));
        Assert.Equal("ordinary content", Transcript.PersonText("ordinary content"));
    }
    [Fact] public void ThreadRootAndRecipientChangesBreakMessageGrouping()
    {
        var first = JsonNode.Parse("{\"type\":\"message\",\"from\":\"a\",\"to\":[\"human\"],\"at\":\"2026-01-01T10:00:00Z\"}")!;
        var next = first.DeepClone(); next["at"] = "2026-01-01T10:01:00Z";
        Assert.True(Transcript.SameMessageGroup(first, next));
        first["thread"] = new JsonObject { ["count"] = 1 }; Assert.False(Transcript.SameMessageGroup(first, next));
        first.AsObject().Remove("thread"); next["to"] = new JsonArray("other"); Assert.False(Transcript.SameMessageGroup(first, next));
    }
    private sealed class Handler(Func<HttpRequestMessage, Task<HttpResponseMessage>> reply) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => reply(request);
    }
    [Fact] public async Task WritesCarryTokenAndKeepUnicodeAndPrivateRecipient()
    {
        using var client = new Client(39321, "test-token", new Handler(async request =>
        {
            Assert.Equal("127.0.0.1", request.RequestUri!.Host);
            Assert.Equal("test-token", request.Headers.GetValues("X-Relic-Token").Single());
            Assert.Equal(HttpMethod.Post, request.Method);
            var body = JsonNode.Parse(await request.Content!.ReadAsStringAsync())!;
            Assert.Equal("private", body.Text("channel"));
            Assert.Equal("你好", body.Text("body"));
            Assert.Equal("analyst", body.Rows("to")[0].Text());
            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{\"id\":42}") };
        }));
        var result = await client.Post(Client.Org("org space", "/send"), Composer.Message("你好", "analyst", ["all"], new()));
        Assert.Equal("42", result.Text("id"));
    }
    [Fact] public void MentionsDoNotChangeGroupChannel()
    {
        var members = JsonNode.Parse("[{\"name\":\"ana\",\"display\":\"分析员\"}]")!.AsArray();
        var value = JsonSerializer.SerializeToNode(Composer.Message("@分析员 请看", "", ["all"], members))!;
        Assert.Equal("group", value.Text("channel")); Assert.Equal("ana", value.Rows("to")[0].Text());
    }
    [Fact] public async Task ErrorsAreNotMistakenForSuccessfulApprovals()
    {
        using var client = new Client(39321, "fixture", new Handler(_ => Task.FromResult(new HttpResponseMessage(HttpStatusCode.Forbidden) { Content = new StringContent("{\"error\":\"missing token\"}") })));
        var error = await Assert.ThrowsAsync<HttpRequestException>(() => client.Post("/api/org/o/request", new { request_id = "r1", decision = "approve" }));
        Assert.Equal("missing token", error.Message);
    }
    [Fact] public async Task EventsIgnoreHeartbeatsAndDispatchCompleteFrames()
    {
        using var cancel = new CancellationTokenSource();
        using var client = new Client(39321, "fixture", new Handler(_ => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(": relic\n\ndata: {\"type\":\"org\",\"org\":\"o\"}\n\n") })));
        var received = new List<string>();
        try { await client.Events(node => { received.Add(node.Text("type")); cancel.Cancel(); return Task.CompletedTask; }, cancel.Token); }
        catch (OperationCanceledException) { }
        Assert.Equal(new[] { "org" }, received);
    }
    [Theory]
    [InlineData("zh-TW", "zh-CN")][InlineData("zh-Hant", "zh-CN")][InlineData("ja-JP", "en-US")][InlineData("en-GB", "en-US")]
    public void OnlyTwoUiLanguages(string input, string expected) => Assert.Equal(expected, Words.Normalize(input));
    [Fact] public void SharedWordListsSupportPluralAndSubstitution()
    {
        var words = new Words();
        words.Load(JsonNode.Parse("{\"lang\":\"en-US\",\"strings\":{\"count\":{\"one\":\"{n} item\",\"other\":\"{n} items\"}}}")!);
        Assert.Equal("1 item", words.T("count", ("n", 1))); Assert.Equal("2 items", words.T("count", ("n", 2)));
    }
}
