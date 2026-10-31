using System.Collections.Concurrent;
using System.Diagnostics;

namespace Relic;

internal static class PerformanceTrace
{
    private static readonly bool Enabled = Environment.GetEnvironmentVariable("GITHUB_ACTIONS") == "true"
        && !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("RELIC_PERF_MANIFEST"));
    private static readonly ConcurrentQueue<object> records = new();
    internal static Scope Measure(string name) => new Scope(name);
    internal static void Count(string name, double value)
    {
        if (Enabled) records.Enqueue(new { name, value, unix_ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() });
    }
    internal static object[] Drain()
    {
        var batch = new List<object>();
        while (records.TryDequeue(out var record)) batch.Add(record);
        return batch.ToArray();
    }
    private static long lastCollection;
    internal static void RecordCollection()
    {
        if (!Enabled) return;
        var info = GC.GetGCMemoryInfo();
        if (info.Index == lastCollection) return;
        lastCollection = info.Index;
        records.Enqueue(new { name = "gc.collection", index = info.Index,
            generation = info.Generation, concurrent = info.Concurrent,
            pauses_ms = info.PauseDurations.ToArray().Select(pause => pause.TotalMilliseconds).ToArray(),
            heap_bytes = info.HeapSizeBytes, finalizers_pending = info.FinalizationPendingCount,
            unix_ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() });
    }
    internal readonly struct Scope(string name) : IDisposable
    {
        private readonly long start = Enabled ? Stopwatch.GetTimestamp() : 0;
        public void Dispose()
        {
            if (start == 0) return;
            var ms = Stopwatch.GetElapsedTime(start).TotalMilliseconds;
            if (ms > 5) Count(name, ms);
        }
    }
}
