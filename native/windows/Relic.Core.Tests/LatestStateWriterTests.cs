using System.Text.Json.Nodes;
using Relic.Core;
using Xunit;

namespace Relic.Core.Tests;

public sealed class LatestStateWriterTests
{
    [Fact]
    public async Task SlowWriteKeepsOnlyLatestWaitingSnapshotAndWritesSerially()
    {
        var started = Signal(); var release = Signal();
        var writes = new List<(string Path, int Value)>();
        var active = 0; var peak = 0;
        await using var writer = new LatestStateWriter(async (path, json) =>
        {
            var count = Interlocked.Increment(ref active);
            peak = Math.Max(peak, count);
            try
            {
                var value = JsonNode.Parse(json)!["value"]!.GetValue<int>();
                if (value == 0) { started.TrySetResult(true); await release.Task; }
                writes.Add((path, value));
            }
            finally { Interlocked.Decrement(ref active); }
        });
        try
        {
            writer.Queue("state.json", State(0));
            await Bounded(started.Task);
            for (var value = 1; value <= 1000; value++) writer.Queue("state.json", State(value));
            var flush = writer.FlushAsync();
            Assert.False(flush.IsCompleted);
            release.TrySetResult(true);
            await Bounded(flush);
            Assert.Equal(new[] { ("state.json", 0), ("state.json", 1000) }, writes);
            Assert.Equal(1, peak);
        }
        finally { release.TrySetResult(true); }
    }

    [Fact]
    public async Task DisposeDrainsLastSnapshotAndRejectsFurtherQueueing()
    {
        var started = Signal(); var release = Signal();
        var writes = new List<int>();
        await using var writer = new LatestStateWriter(async (_, json) =>
        {
            var value = JsonNode.Parse(json)!["value"]!.GetValue<int>();
            if (value == 1) { started.TrySetResult(true); await release.Task; }
            writes.Add(value);
        });
        try
        {
            writer.Queue("window.json", State(1));
            await Bounded(started.Task);
            writer.Queue("window.json", State(2));
            writer.Queue("window.json", State(3));
            var dispose = writer.DisposeAsync().AsTask();
            Assert.False(dispose.IsCompleted);
            Assert.Throws<ObjectDisposedException>(() => writer.Queue("window.json", State(4)));
            release.TrySetResult(true);
            await Bounded(dispose);
            await Bounded(writer.FlushAsync());
            Assert.Equal(new[] { 1, 3 }, writes);
        }
        finally { release.TrySetResult(true); }
    }

    [Fact]
    public async Task ExpectedFileFailuresDoNotStopSubsequentWritesOrFlush()
    {
        var attempts = new List<int>();
        await using var writer = new LatestStateWriter((_, json) =>
        {
            var value = JsonNode.Parse(json)!["value"]!.GetValue<int>();
            attempts.Add(value);
            return value switch
            {
                1 => Task.FromException(new IOException("Temporary write failure")),
                2 => Task.FromException(new UnauthorizedAccessException("Temporary access failure")),
                _ => Task.CompletedTask
            };
        });
        for (var value = 1; value <= 3; value++)
        {
            writer.Queue("state.json", State(value));
            await Bounded(writer.FlushAsync());
        }
        Assert.Equal(new[] { 1, 2, 3 }, attempts);
    }

    private static JsonObject State(int value) => new() { ["value"] = value };
    private static TaskCompletionSource<bool> Signal() => new(TaskCreationOptions.RunContinuationsAsynchronously);
    private static Task Bounded(Task task) => task.WaitAsync(TimeSpan.FromSeconds(10));
}
