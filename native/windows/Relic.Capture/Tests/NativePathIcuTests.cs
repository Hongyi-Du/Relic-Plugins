using Xunit;

namespace Relic.Capture.Tests;

public sealed class NativePathIcuTests
{
    [Theory]
    [InlineData("", "en-US")]
    [InlineData("A path with spaces/README.md", "en-US")]
    [InlineData("秘书处：检查工作区、消息和协议。", "zh-CN")]
    [InlineData("A 👩‍💻 e\u0301\n第二行", "zh-CN")]
    public async Task WorkerPreservesActualSystemWordCharacterAndLineBoundaries(string text, string locale)
    {
        if (!OperatingSystem.IsWindows()) return;
        var expected = Relic.NativePathIcu.Read(text, locale);
        var actual = await Relic.NativePathIcu.ReadAsync(text, locale).WaitAsync(TimeSpan.FromSeconds(10));
        Assert.Equal(expected.Lines, actual.Lines);
        Assert.Equal(expected.Characters, actual.Characters);
        Assert.Equal(expected.Words, actual.Words);
        Assert.Equal(0, actual.Characters[0]);
        Assert.Equal(text.Length, actual.Characters[^1]);
    }

    [Fact]
    public async Task CancelledRequestDoesNotStopLaterIndependentWork()
    {
        if (!OperatingSystem.IsWindows()) return;
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Relic.NativePathIcu.ReadAsync("cancelled", "en-US", cancellation.Token));
        var texts = Enumerable.Range(0, 32).Select(index => "独立消息 " + index + " 👩‍💻").ToArray();
        var values = await Task.WhenAll(texts.Select(text => Relic.NativePathIcu.ReadAsync(text, "zh-CN")))
            .WaitAsync(TimeSpan.FromSeconds(10));
        for (var index = 0; index < texts.Length; index++)
        {
            var expected = Relic.NativePathIcu.Read(texts[index], "zh-CN");
            Assert.Equal(expected.Lines, values[index].Lines);
            Assert.Equal(expected.Characters, values[index].Characters);
            Assert.Equal(expected.Words, values[index].Words);
        }
    }
}
