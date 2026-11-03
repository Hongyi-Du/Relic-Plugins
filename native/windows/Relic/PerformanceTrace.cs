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
    internal static Dictionary<string, int> AliveCounts() => Enabled ? Alive() : [];
    // The tracked objects of each kind still alive, for a CI description of
    // what outlived full collections. The lists themselves stay weak.
    internal static Dictionary<string, List<object>> AliveObjects()
    {
        var alive = new Dictionary<string, List<object>>();
        if (!Enabled) return alive;
        lock (tracked)
            foreach (var (kind, list) in tracked)
                alive[kind] = list.Select(entry => entry.Target).OfType<object>().ToList();
        return alive;
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
            native = NativeMemory(), alive = Alive(), unix_ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() });
    }

    // Private bytes grew about 0.27 MB per chat switch while the GC committed
    // only a quarter of that. Split the rest: the process heaps (native
    // allocations by XAML, DirectWrite, COM...) against other committed
    // private memory (GC regions, graphics surfaces, stacks) and mappings.
    // Bytes the process heaps hold for live allocations (CI-only probes).
    internal static long HeapAllocated()
    {
        var count = GetProcessHeaps(0, null);
        var heaps = new IntPtr[count + 8];
        count = Math.Min(GetProcessHeaps((uint)heaps.Length, heaps), (uint)heaps.Length);
        long allocated = 0;
        for (var index = 0; index < count; index++)
        {
            var summary = new HeapSummaryInfo { Size = (uint)System.Runtime.InteropServices.Marshal.SizeOf<HeapSummaryInfo>() };
            if (HeapSummary(heaps[index], 0, ref summary)) allocated += (long)(ulong)summary.Allocated;
        }
        return allocated;
    }
    private static object NativeMemory()
    {
        try
        {
            var count = GetProcessHeaps(0, null);
            var heaps = new IntPtr[count + 8];
            count = Math.Min(GetProcessHeaps((uint)heaps.Length, heaps), (uint)heaps.Length);
            ulong heapCommitted = 0, heapAllocated = 0;
            for (var index = 0; index < count; index++)
            {
                var summary = new HeapSummaryInfo { Size = (uint)System.Runtime.InteropServices.Marshal.SizeOf<HeapSummaryInfo>() };
                if (HeapSummary(heaps[index], 0, ref summary))
                { heapCommitted += (ulong)summary.Committed; heapAllocated += (ulong)summary.Allocated; }
            }
            ulong privateCommitted = 0, mappedCommitted = 0, imageCommitted = 0; var regions = 0;
            var address = IntPtr.Zero; var size = (UIntPtr)System.Runtime.InteropServices.Marshal.SizeOf<RegionInfo>();
            while (VirtualQuery(address, out var region, size) != UIntPtr.Zero && regions++ < 200_000)
            {
                if (region.State == 0x1000) // MEM_COMMIT
                {
                    var bytes = (ulong)region.RegionSize;
                    if (region.Type == 0x20000) privateCommitted += bytes;
                    else if (region.Type == 0x40000) mappedCommitted += bytes;
                    else if (region.Type == 0x1000000) imageCommitted += bytes;
                }
                var next = (long)region.BaseAddress + (long)(ulong)region.RegionSize;
                if (next <= (long)address) break;
                address = (IntPtr)next;
            }
            return new { heaps = count, heap_committed = heapCommitted, heap_allocated = heapAllocated,
                private_committed = privateCommitted, mapped_committed = mappedCommitted, image_committed = imageCommitted, regions };
        }
        catch (Exception error) { return new { error = error.Message }; }
    }
    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
    private struct HeapSummaryInfo { public uint Size; public UIntPtr Allocated, Committed, Reserved, MaxReserve; }
    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
    private struct RegionInfo
    {
        public IntPtr BaseAddress, AllocationBase; public uint AllocationProtect; public ushort PartitionId;
        public UIntPtr RegionSize; public uint State, Protect, Type;
    }
    [System.Runtime.InteropServices.DllImport("kernel32.dll")] private static extern uint GetProcessHeaps(uint count, IntPtr[]? heaps);
    [System.Runtime.InteropServices.DllImport("kernel32.dll")] private static extern bool HeapSummary(IntPtr heap, uint flags, ref HeapSummaryInfo summary);
    [System.Runtime.InteropServices.DllImport("kernel32.dll")] private static extern UIntPtr VirtualQuery(IntPtr address, out RegionInfo info, UIntPtr length);
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
