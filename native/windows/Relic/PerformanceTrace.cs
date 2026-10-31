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
