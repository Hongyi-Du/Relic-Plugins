using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

// Append and flush before crossing provider boundaries. If the CI supervisor
// terminates an unresponsive provider query, completed measurements and the
// last started stage remain readable without pretending this is a full capture.
internal sealed class CaptureProgress : IDisposable
{
    private readonly StreamWriter writer;
    private readonly Stopwatch clock = Stopwatch.StartNew();
    private long sequence;
    public string Path { get; }

    public CaptureProgress(string outputPath)
    {
        Path = outputPath + ".progress.jsonl";
        Directory.CreateDirectory(System.IO.Path.GetDirectoryName(System.IO.Path.GetFullPath(Path))!);
        writer = new StreamWriter(new FileStream(Path, FileMode.Create, FileAccess.Write, FileShare.Read),
            new UTF8Encoding(false)) { AutoFlush = true };
        Record("capture", "started");
    }

    public void Record(string stage, string status, JsonObject? detail = null)
    {
        var entry = new JsonObject
        {
            ["sequence"] = ++sequence, ["elapsed_ms"] = clock.Elapsed.TotalMilliseconds,
            ["stage"] = stage, ["status"] = status, ["detail"] = detail?.DeepClone()
        };
        var numericErrors = new JsonArray();
        NumericEvidence.Sanitize(entry, numericErrors);
        if (numericErrors.Count > 0) entry["serialization_diagnostics"] = numericErrors;
        writer.WriteLine(entry.ToJsonString(new JsonSerializerOptions(JsonSerializerOptions.Default)));
    }

    public T Measure<T>(string stage, Func<T> read, JsonObject? detail = null)
    {
        Record(stage, "started", detail);
        var watch = Stopwatch.StartNew();
        try
        {
            var value = read();
            var completed = detail?.DeepClone().AsObject() ?? new JsonObject();
            completed["duration_ms"] = watch.Elapsed.TotalMilliseconds;
            Record(stage, "completed", completed);
            return value;
        }
        catch (Exception error)
        {
            var failed = detail?.DeepClone().AsObject() ?? new JsonObject();
            failed["duration_ms"] = watch.Elapsed.TotalMilliseconds;
            failed["error"] = error.ToString();
            Record(stage, "failed", failed);
            throw;
        }
    }

    public JsonObject Summary() => new()
    {
        ["path"] = Path, ["records"] = sequence, ["elapsed_ms"] = clock.Elapsed.TotalMilliseconds,
        ["format"] = "append-only JSONL; partial evidence is not a completed capture"
    };

    public void Dispose() => writer.Dispose();
}
