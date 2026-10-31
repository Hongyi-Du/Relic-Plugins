using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

// This handshake retains the observer, not a snapshot of the provider. It does
// not query UIA or claim that a held provider supports an additional interface.
internal interface IObserverLeaseIO
{
    double ElapsedSeconds { get; }
    bool Exists(string path);
    string ReadText(string path);
    void WriteAtomic(string path, string text);
    void Delay(TimeSpan duration);
}

internal sealed class ObserverLeaseFiles(Stopwatch clock, double ageAtClockStart) : IObserverLeaseIO
{
    public double ElapsedSeconds => ageAtClockStart + clock.Elapsed.TotalSeconds;
    public bool Exists(string path) => File.Exists(path);
    public string ReadText(string path) => File.ReadAllText(path, Encoding.UTF8);
    public void Delay(TimeSpan duration) => Thread.Sleep(duration);

    public void WriteAtomic(string path, string text)
    {
        var target = Path.GetFullPath(path);
        Directory.CreateDirectory(Path.GetDirectoryName(target)!);
        var temporary = target + ".tmp-" + Guid.NewGuid().ToString("N");
        try
        {
            using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                var bytes = new UTF8Encoding(false).GetBytes(text);
                stream.Write(bytes);
                stream.Flush(flushToDisk: true);
            }
            // A pre-existing ready file is stale evidence, never overwritten.
            File.Move(temporary, target, overwrite: false);
        }
        finally
        {
            if (File.Exists(temporary)) File.Delete(temporary);
        }
    }
}

internal sealed record ObserverLeaseResult(int ExitCode, JsonObject Receipt);

internal static class ObserverLease
{
    internal const double TotalDeadlineSeconds = 75;

    internal static ObserverLeaseResult Hold(string caseId, int appPid, int observerPid, int captureExitCode,
        string readyPath, string releasePath, JsonObject retainedOwners, IObserverLeaseIO io,
        Action<string, string, JsonObject>? record = null)
    {
        var receipt = new JsonObject
        {
            ["schema_version"] = 1, ["case_id"] = caseId, ["app_pid"] = appPid,
            ["observer_pid"] = observerPid, ["capture_exit_code"] = captureExitCode,
            ["ready_path"] = readyPath, ["release_path"] = releasePath,
            ["total_deadline_seconds"] = TotalDeadlineSeconds,
            ["deadline_origin"] = "Actual observer process StartTime plus 75 seconds; elapsed measured with Stopwatch after Main entry",
            ["retained_owners"] = retainedOwners.DeepClone(), ["errors"] = new JsonArray(),
            ["status"] = "starting"
        };
        var errors = receipt["errors"]!.AsArray();
        try
        {
            if (string.IsNullOrWhiteSpace(caseId) || appPid <= 0 || observerPid <= 0 || captureExitCode is not (0 or 1))
                throw new InvalidDataException("A real case ID, positive process IDs and the original 0/1 capture exit code are required.");
            if (Path.GetFullPath(readyPath).Equals(Path.GetFullPath(releasePath), StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Ready and release paths must be distinct.");
            if (io.Exists(readyPath) || io.Exists(releasePath))
                throw new InvalidDataException("Ready/release evidence already exists before this observer publishes readiness.");

            var ready = new JsonObject
            {
                ["schema_version"] = 1, ["status"] = "ready", ["case_id"] = caseId,
                ["app_pid"] = appPid, ["observer_pid"] = observerPid,
                ["exit_code"] = captureExitCode, ["capture_exit_code"] = captureExitCode,
                ["uia_output_written"] = true, ["elapsed_seconds"] = Elapsed(io),
                ["total_deadline_seconds"] = TotalDeadlineSeconds,
                ["deadline_origin"] = receipt["deadline_origin"]!.DeepClone(),
                ["retained_owners"] = retainedOwners.DeepClone()
            };
            io.WriteAtomic(readyPath, ready.ToJsonString(new JsonSerializerOptions(JsonSerializerOptions.Default) { WriteIndented = true }));
            receipt["ready"] = ready;
            receipt["status"] = "holding";
            record?.Invoke("observer-hold", "ready", ready);

            while (true)
            {
                var elapsed = Elapsed(io);
                if (elapsed >= TotalDeadlineSeconds)
                    throw new TimeoutException("Observer release was not acknowledged within the original 75-second process deadline.");
                if (io.Exists(releasePath))
                {
                    var raw = io.ReadText(releasePath);
                    receipt["release_raw"] = raw;
                    var release = JsonNode.Parse(raw) as JsonObject
                        ?? throw new InvalidDataException("Observer release must be a JSON object.");
                    receipt["release"] = release.DeepClone();
                    if (release["case_id"] is not JsonValue caseValue || !caseValue.TryGetValue<string>(out var releasedCase) ||
                        !string.Equals(releasedCase, caseId, StringComparison.Ordinal) ||
                        release["observer_pid"] is not JsonValue pidValue || !pidValue.TryGetValue<int>(out var releasedPid) || releasedPid != observerPid)
                        throw new InvalidDataException("Observer release case_id/observer_pid do not identify this live observer.");
                    if (Elapsed(io) >= TotalDeadlineSeconds)
                        throw new TimeoutException("Observer release was read after the original 75-second process deadline.");
                    receipt["status"] = "released";
                    receipt["elapsed_seconds"] = Elapsed(io);
                    receipt["exit_code"] = captureExitCode;
                    record?.Invoke("observer-hold", "released", receipt);
                    return new ObserverLeaseResult(captureExitCode, receipt);
                }
                io.Delay(TimeSpan.FromSeconds(Math.Min(.025, TotalDeadlineSeconds - elapsed)));
            }
        }
        catch (Exception error)
        {
            errors.Add("UIA observer hold failed: " + error);
            receipt["status"] = "failed";
            receipt["exit_code"] = 1;
            // Preserve the original capture exit code and every received ack;
            // a hold failure must never replace prior provider errors.
            record?.Invoke("observer-hold", "failed", receipt);
            return new ObserverLeaseResult(1, receipt);
        }
    }

    private static double Elapsed(IObserverLeaseIO io)
    {
        var value = io.ElapsedSeconds;
        if (!double.IsFinite(value) || value < 0)
            throw new InvalidDataException("Observer process elapsed time was not measured as a finite nonnegative value.");
        return value;
    }
}
