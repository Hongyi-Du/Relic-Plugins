using System.Collections.Concurrent;
using System.Diagnostics;

namespace Relic;

internal static class PerformanceTrace
{
    private static readonly bool Enabled = Environment.GetEnvironmentVariable("GITHUB_ACTIONS") == "true"
        && !string.IsNullOrEmpty(Environment.GetEnvironmentVariable("RELIC_PERF_MANIFEST"));
    private static readonly ConcurrentQueue<object> records = new();
    internal static Scope Measure(string name) => new Scope(name);
    // Set while the idle phase measures: record every timed scope, not only
    // those over 5 ms, to see any of our own work that runs while idle.
    internal static volatile bool RecordAll;
    internal static void Count(string name, double value)
    {
        if (Enabled) records.Enqueue(new { name, value, unix_ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() });
    }
    // A structured CI-only record, for evidence a single number cannot carry.
    internal static void Note(string name, object detail)
    {
        if (Enabled) records.Enqueue(new { name, detail, unix_ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() });
    }
    // CI-only: how many objects of a kind are still alive (not yet collected),
    // reported with each memory checkpoint. Weak references only, so tracking
    // never keeps anything alive; counts include garbage the GC has not
    // reached yet, which the frequent gen2 collections here keep small.
    private static readonly Dictionary<string, List<WeakReference>> tracked = [];
    private static int trackedAdds;
    internal static void Track(string kind, object instance)
    {
        if (!Enabled) return;
        lock (tracked)
        {
            if (!tracked.TryGetValue(kind, out var list)) tracked[kind] = list = [];
            list.Add(new WeakReference(instance));
            if (++trackedAdds % 4096 == 0) foreach (var entries in tracked.Values) entries.RemoveAll(entry => !entry.IsAlive);
        }
    }
    private static Dictionary<string, int> Alive()
    {
        lock (tracked)
        {
            var alive = new Dictionary<string, int>();
            foreach (var (kind, list) in tracked) { list.RemoveAll(entry => !entry.IsAlive); alive[kind] = list.Count; }
            return alive;
        }
    }

    // Where the process's memory is at one point of a scenario: the managed
    // heap (and how much of it is free space), what the GC has committed, and
    // the process totals, so growth can be told apart as managed or native.
    internal static void Memory(string at)
    {
        if (!Enabled) return;
        var info = GC.GetGCMemoryInfo(GCKind.Any);
        using var process = Process.GetCurrentProcess();
        records.Enqueue(new { name = "memory.checkpoint", at, gc_index = info.Index,
            heap_bytes = info.HeapSizeBytes, fragmented_bytes = info.FragmentedBytes, committed_bytes = info.TotalCommittedBytes,
            generations = info.GenerationInfo.ToArray().Select(generation => new { size = generation.SizeAfterBytes,
                fragmentation = generation.FragmentationAfterBytes }).ToArray(),
            live_bytes = GC.GetTotalMemory(false), allocated_bytes = GC.GetTotalAllocatedBytes(),
            working_set = process.WorkingSet64, private_bytes = process.PrivateMemorySize64,
            alive = Alive(), unix_ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() });
    }
    internal static object[] Drain()
    {
        var batch = new List<object>();
        while (records.TryDequeue(out var record)) batch.Add(record);
        return batch.ToArray();
    }
    private static long lastCollection;
    private static int lastCount = -1;
    internal static void RecordCollection()
    {
        if (!Enabled) return;
        // GetGCMemoryInfo allocates; only read it after a collection happened.
        var count = GC.CollectionCount(0);
        if (count == lastCount) return;
        lastCount = count;
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
            if (ms > 5 || RecordAll) Count(name, ms);
        }
    }
}
