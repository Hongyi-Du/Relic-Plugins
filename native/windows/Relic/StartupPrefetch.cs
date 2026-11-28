using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Relic;

// A cold start reads the code of the modules shipped beside Relic.exe (WinUI,
// the .NET runtime, Relic itself) from disk a few pages at a time, whenever the
// UI thread first runs that code. In CI the first load's 213 ms UI stall held
// 130 reads from disk while the UI thread used 78 ms of CPU (run 41679770563),
// and a first settings dialog held the UI thread 815 ms on 39 ms of CPU (run
// 41676800421). A background thread asks Windows to read those modules in large
// reads instead (PrefetchVirtualMemory) and reads the resource indexes (*.pri)
// once. The pages wait in memory (not in the working set) until code needs them;
// pages already in memory cost nothing. The thread runs in background mode, so
// its reads give way to the UI thread's own.
internal static class StartupPrefetch
{
    private static readonly HashSet<IntPtr> prefetched = [];
    private static bool resourcesRead;

    // Safe to call again later: modules loaded since are prefetched then.
    internal static void Start()
    {
        new Thread(Prefetch) { IsBackground = true, Name = "Relic prefetch", Priority = ThreadPriority.BelowNormal }.Start();
    }

    private static void Prefetch()
    {
        using var timing = PerformanceTrace.Measure("startup.prefetch.worker");
        var background = SetThreadPriority(GetCurrentThread(), 0x00010000 /* THREAD_MODE_BACKGROUND_BEGIN */);
        try
        {
            var folder = AppContext.BaseDirectory;
            var ranges = new List<MemoryRange>();
            long bytes = 0;
            using (var process = Process.GetCurrentProcess())
                foreach (ProcessModule module in process.Modules)
                    using (module)
                    {
                        if (module.FileName is not { } file || !file.StartsWith(folder, StringComparison.OrdinalIgnoreCase)) continue;
                        lock (prefetched) if (!prefetched.Add(module.BaseAddress)) continue;
                        ranges.Add(new MemoryRange { Address = module.BaseAddress, Bytes = (nuint)module.ModuleMemorySize });
                        bytes += module.ModuleMemorySize;
                    }
            var entries = ranges.ToArray();
            var asked = entries.Length > 0 && PrefetchVirtualMemory(GetCurrentProcess(), (nuint)entries.Length, entries, 0);
            long read = 0;
            bool first;
            lock (prefetched) { first = !resourcesRead; resourcesRead = true; }
            if (first)
            {
                var buffer = new byte[1 << 20];
                foreach (var index in Directory.EnumerateFiles(folder, "*.pri"))
                {
                    using var stream = new FileStream(index, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete, 1, FileOptions.SequentialScan);
                    int count;
                    while ((count = stream.Read(buffer, 0, buffer.Length)) > 0) read += count;
                }
            }
            PerformanceTrace.Note("startup.prefetch", new { modules = entries.Length, bytes, asked, resources_read = read, background });
        }
        catch (Exception error) { PerformanceTrace.Note("startup.prefetch.error", error.Message); }
        finally { if (background) SetThreadPriority(GetCurrentThread(), 0x00020000 /* THREAD_MODE_BACKGROUND_END */); }
    }

    [StructLayout(LayoutKind.Sequential)] private struct MemoryRange { public IntPtr Address; public nuint Bytes; }
    [DllImport("kernel32.dll", SetLastError = true)] private static extern bool PrefetchVirtualMemory(IntPtr process, nuint count, MemoryRange[] ranges, uint flags);
    [DllImport("kernel32.dll")] private static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll")] private static extern IntPtr GetCurrentThread();
    [DllImport("kernel32.dll")] private static extern bool SetThreadPriority(IntPtr thread, int priority);
}
