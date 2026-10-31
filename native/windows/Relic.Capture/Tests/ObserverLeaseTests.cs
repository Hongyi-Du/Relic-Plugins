using System.Text.Json.Nodes;
using Xunit;

public sealed class ObserverLeaseTests
{
    private const string Ready = "observer.ready.json";
    private const string Release = "observer.release.json";
    private static readonly JsonObject Owners = new()
    {
        ["capture_instance_retained"] = true, ["retained_element_reference_count"] = 391
    };

    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    public void ReleaseRetainsOriginalCaptureExitCodeAndActualReceipt(int captureExitCode)
    {
        var io = new FakeIO { ElapsedSeconds = 6.25 };
        io.OnDelay = () => io.Files[Release] = "{\"case_id\":\"actual-case\",\"observer_pid\":123,\"action\":\"release\",\"status\":\"probes-failed\"}";
        var result = Hold(io, captureExitCode);
        Assert.Equal(captureExitCode, result.ExitCode);
        Assert.Equal("released", result.Receipt["status"]!.GetValue<string>());
        Assert.Empty(result.Receipt["errors"]!.AsArray());
        var ready = JsonNode.Parse(io.Files[Ready])!;
        Assert.Equal("actual-case", ready["case_id"]!.GetValue<string>());
        Assert.Equal(456, ready["app_pid"]!.GetValue<int>());
        Assert.Equal(123, ready["observer_pid"]!.GetValue<int>());
        Assert.Equal(captureExitCode, ready["exit_code"]!.GetValue<int>());
        Assert.Equal(6.25, ready["elapsed_seconds"]!.GetValue<double>());
        Assert.Equal(391, ready["retained_owners"]!["retained_element_reference_count"]!.GetValue<int>());
        Assert.Equal("probes-failed", result.Receipt["release"]!["status"]!.GetValue<string>());
        Assert.Equal(new[] { Ready }, io.AtomicWrites);
    }

    [Fact]
    public void DeadlineIncludesTimeAlreadySpentCapturing()
    {
        var io = new FakeIO { ElapsedSeconds = 74.95 };
        var result = Hold(io);
        Assert.Equal(1, result.ExitCode);
        Assert.Equal("failed", result.Receipt["status"]!.GetValue<string>());
        Assert.Equal(0, result.Receipt["capture_exit_code"]!.GetValue<int>());
        Assert.True(io.ElapsedSeconds >= 75);
        Assert.True(io.DelayedSeconds <= .050001, "A hold must not restart a new 75-second timeout.");
        Assert.Contains("original 75-second", result.Receipt["errors"]!.ToJsonString());
        Assert.True(io.Files.ContainsKey(Ready));
    }

    [Fact]
    public void AlreadyExpiredCapturePublishesOriginalReadyThenFailsWithoutWaiting()
    {
        var io = new FakeIO { ElapsedSeconds = 75.1 };
        var result = Hold(io, 1);
        Assert.Equal(1, result.ExitCode);
        Assert.Equal(1, JsonNode.Parse(io.Files[Ready])!["exit_code"]!.GetValue<int>());
        Assert.Equal(0, io.DelayedSeconds);
        Assert.NotEmpty(result.Receipt["errors"]!.AsArray());
    }

    [Theory]
    [InlineData("{\"case_id\":\"other-case\",\"observer_pid\":123}")]
    [InlineData("{\"case_id\":\"actual-case\",\"observer_pid\":999}")]
    [InlineData("{\"case_id\":\"actual-case\",\"observer_pid\":\"123\"}")]
    [InlineData("{\"case_id\":\"actual-case\"}")]
    [InlineData("not json")]
    [InlineData("[]")]
    public void InvalidReleaseIsPreservedAndFails(string raw)
    {
        var io = new FakeIO();
        io.OnDelay = () => io.Files[Release] = raw;
        var result = Hold(io);
        Assert.Equal(1, result.ExitCode);
        Assert.Equal(raw, result.Receipt["release_raw"]!.GetValue<string>());
        Assert.NotEmpty(result.Receipt["errors"]!.AsArray());
    }

    [Theory]
    [InlineData(Ready)]
    [InlineData(Release)]
    public void StaleEvidenceIsNotOverwrittenOrAccepted(string stalePath)
    {
        var io = new FakeIO();
        io.Files[stalePath] = "pre-existing evidence";
        var result = Hold(io);
        Assert.Equal(1, result.ExitCode);
        Assert.Equal("pre-existing evidence", io.Files[stalePath]);
        Assert.Empty(io.AtomicWrites);
    }

    [Fact]
    public void MatchingAckReadAfterDeadlineStillFails()
    {
        var io = new FakeIO { ElapsedSeconds = 74.9 };
        io.OnDelay = () => io.Files[Release] = "{\"case_id\":\"actual-case\",\"observer_pid\":123}";
        io.OnRead = () => io.ElapsedSeconds = 75.001;
        var result = Hold(io);
        Assert.Equal(1, result.ExitCode);
        Assert.NotNull(result.Receipt["release"]);
        Assert.Contains("read after", result.Receipt["errors"]!.ToJsonString());
    }

    [Fact]
    public void FailedReadyPublicationDoesNotWaitOrClaimReadiness()
    {
        var io = new FakeIO { FailAtomicWrite = true };
        var result = Hold(io, 1);
        Assert.Equal(1, result.ExitCode);
        Assert.Null(result.Receipt["ready"]);
        Assert.Equal(0, io.DelayedSeconds);
        Assert.NotEmpty(result.Receipt["errors"]!.AsArray());
    }

    [Theory]
    [InlineData(double.NaN)]
    [InlineData(-1)]
    public void InvalidClockCannotClaimABoundedLease(double elapsed)
    {
        var io = new FakeIO { ElapsedSeconds = elapsed };
        var result = Hold(io);
        Assert.Equal(1, result.ExitCode);
        Assert.Empty(io.AtomicWrites);
        Assert.NotEmpty(result.Receipt["errors"]!.AsArray());
    }

    [Fact]
    public void ReadyAndReleaseMustBeDifferentPaths()
    {
        var io = new FakeIO();
        var result = ObserverLease.Hold("actual-case", 456, 123, 0, Ready, Ready, Owners, io);
        Assert.Equal(1, result.ExitCode);
        Assert.Empty(io.AtomicWrites);
    }

    private static ObserverLeaseResult Hold(FakeIO io, int exitCode = 0) =>
        ObserverLease.Hold("actual-case", 456, 123, exitCode, Ready, Release, Owners, io);

    // No process, file, real clock, UIA, window or sleep is used by these tests.
    private sealed class FakeIO : IObserverLeaseIO
    {
        public double ElapsedSeconds { get; set; }
        public double DelayedSeconds { get; private set; }
        public Dictionary<string, string> Files { get; } = new(StringComparer.Ordinal);
        public List<string> AtomicWrites { get; } = new();
        public Action? OnDelay { get; set; }
        public Action? OnRead { get; set; }
        public bool FailAtomicWrite { get; set; }
        public bool Exists(string path) => Files.ContainsKey(path);
        public string ReadText(string path) { OnRead?.Invoke(); return Files[path]; }
        public void WriteAtomic(string path, string text)
        {
            if (FailAtomicWrite) throw new IOException("Simulated ready publication failure");
            Files.Add(path, text);
            AtomicWrites.Add(path);
        }
        public void Delay(TimeSpan duration)
        {
            var seconds = Math.Max(duration.TotalSeconds, .0000001);
            DelayedSeconds += seconds;
            ElapsedSeconds += seconds;
            OnDelay?.Invoke();
        }
    }
}
