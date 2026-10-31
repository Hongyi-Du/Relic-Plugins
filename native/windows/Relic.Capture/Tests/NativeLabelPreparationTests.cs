using Xunit;
using static Relic.NativeLabelInterop;

namespace Relic.Capture.Tests;

public sealed class NativeLabelPreparationTests
{
    [Theory]
    [InlineData("秘书处 · 当前组织", false, false, false, 96f)]
    [InlineData("Project 👩🏽‍💻 العربية — newest reply", false, true, false, 72f)]
    [InlineData("A long ordinary message header with several words", true, false, true, 80f)]
    public async Task WorkerReturnsTheActualLayoutWithUnchangedMetrics(string text, bool wrap, bool ellipsis, bool primary, float width)
    {
        if (!OperatingSystem.IsWindows()) return;
        var request = new NativeLabelLayoutRequest(text, "Arial, Microsoft YaHei UI, Segoe UI Emoji", "zh-CN",
            13, 400, 20.8f, width, wrap ? 1000000 : 20.8f, wrap, primary, ellipsis);
        using var direct = NativeLabelPreparation.Prepare(request, CancellationToken.None);
        using var prepared = await NativeLabelPreparation.PrepareAsync(request, CancellationToken.None);
        Assert.NotEqual(IntPtr.Zero, prepared.Layout);
        Assert.Equal(direct.Metrics.WidthIncludingTrailingWhitespace, prepared.Metrics.WidthIncludingTrailingWhitespace);
        Assert.Equal(direct.Metrics.Height, prepared.Metrics.Height);
        Assert.Equal(direct.Metrics.LineCount, prepared.Metrics.LineCount);
        Assert.Equal(direct.ResolvedLineHeight, prepared.ResolvedLineHeight);
        Assert.Equal(direct.Lines.Select(line => (line.Length, line.Height, line.Baseline, line.IsTrimmed)),
            prepared.Lines.Select(line => (line.Length, line.Height, line.Baseline, line.IsTrimmed)));
        // Query the object after worker handoff, as the UI does. This must be
        // the same prepared layout, not a separate metrics-only approximation.
        Check(Method<GetTextMetrics>(prepared.Layout, 60)(prepared.Layout, out var actual));
        Assert.Equal(prepared.Metrics.WidthIncludingTrailingWhitespace, actual.WidthIncludingTrailingWhitespace);
        Check(Method<GetTrimming>(prepared.Layout, 17)(prepared.Layout, out var trimming, out var sign));
        try
        {
            Assert.Equal(ellipsis ? 1u : 0u, trimming.Granularity);
            Assert.Equal(ellipsis, sign != IntPtr.Zero);
            if (ellipsis) Assert.Equal(ComIdentity(prepared.TrimmingSign), ComIdentity(sign));
        }
        finally { Release(ref sign); }
    }

    private sealed class OwnedResult : IDisposable
    {
        internal bool Disposed;
        public void Dispose() => Disposed = true;
    }

    [Fact]
    public async Task CancellationDisposesTheUnclaimedResultAndWorkerContinues()
    {
        using var cancellation = new CancellationTokenSource();
        var result = new OwnedResult();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(async () =>
            await NativeLabelPreparation.RunAsync(_ => { cancellation.Cancel(); return result; }, cancellation.Token));
        Assert.True(result.Disposed);
        Assert.Equal(42, await NativeLabelPreparation.RunAsync(_ => 42, CancellationToken.None));
    }

    [Fact]
    public async Task SharedQueueRunsOnePreparationAtATime()
    {
        var active = 0; var maximum = 0;
        var jobs = Enumerable.Range(0, 32).Select(index => NativeLabelPreparation.RunAsync(_ =>
        {
            var current = Interlocked.Increment(ref active);
            int previous;
            do { previous = Volatile.Read(ref maximum); }
            while (current > previous && Interlocked.CompareExchange(ref maximum, current, previous) != previous);
            Thread.SpinWait(1000);
            Interlocked.Decrement(ref active);
            return index;
        }, CancellationToken.None)).ToArray();
        Assert.Equal(Enumerable.Range(0, 32), await Task.WhenAll(jobs));
        Assert.Equal(1, maximum);
    }
}
