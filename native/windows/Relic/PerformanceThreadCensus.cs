using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Relic;

// CI-only evidence for the switch phase's thread-count check: which threads
// appear and disappear between censuses, named by their description and by
// the module and offset of their Win32 start address (.NET pool workers, the
// Windows thread pool in ntdll, WinUI, DirectWrite, ...), with when each was
// created (seconds after the process started) and the CPU it had used when
// last seen. Windows thread-pool threads left by startup work exit about 60 s
// later, inside the person profile's measured switches; the creation time
// ties them to that work.
internal static class PerformanceThreadCensus
{
    private sealed record Seen(string Name, double Created);
    private static Dictionary<int, Seen>? previous;
    private static readonly Dictionary<int, double> cpu = [];
    private static List<(string Name, long Start, long End)>? modules;
    private static DateTime processStart;

    internal static void Take()
    {
        try
        {
            using var process = Process.GetCurrentProcess();
            if (modules == null)
            {
                modules = process.Modules.Cast<ProcessModule>()
                    .Select(module => (System.IO.Path.GetFileName(module.FileName ?? module.ModuleName) ?? "",
                        (long)module.BaseAddress, (long)module.BaseAddress + module.ModuleMemorySize)).ToList();
                processStart = process.StartTime;
            }
            var current = new Dictionary<int, Seen>();
            foreach (ProcessThread thread in process.Threads)
            {
                var id = thread.Id;
                if (previous == null || !previous.TryGetValue(id, out var seen))
                {
                    double created = -1;
                    try { created = Math.Round((thread.StartTime - processStart).TotalSeconds, 1); } catch (Exception) { }
                    seen = new(Describe(id), created);
                }
                current[id] = seen;
                try { cpu[id] = Math.Round(thread.TotalProcessorTime.TotalMilliseconds); } catch (Exception) { }
                thread.Dispose();
            }
            string Label(int id, Seen seen) => seen.Name + " c=" + seen.Created + "s cpu=" + (cpu.TryGetValue(id, out var used) ? used : -1) + "ms";
            if (previous != null)
            {
                var appeared = current.Where(pair => !previous.ContainsKey(pair.Key)).Select(pair => Label(pair.Key, pair.Value)).ToArray();
                var gone = previous.Where(pair => !current.ContainsKey(pair.Key)).Select(pair => Label(pair.Key, pair.Value)).ToArray();
                foreach (var ended in previous.Keys.Where(thread => !current.ContainsKey(thread)).ToArray()) cpu.Remove(ended);
                if (appeared.Length > 0 || gone.Length > 0)
                    PerformanceTrace.Note("threads.census", new { count = current.Count, appeared, gone });
            }
            // Software rendering (no GPU on CI) runs its rasterizer on Windows thread-pool workers.
            else PerformanceTrace.Note("threads.census", new { count = current.Count,
                process_start_unix_ms = new DateTimeOffset(processStart.ToUniversalTime()).ToUnixTimeMilliseconds(),
                all = current.Select(pair => Label(pair.Key, pair.Value)).ToArray(),
                rendering = modules.Select(entry => entry.Name).Where(name => name.Contains("warp", StringComparison.OrdinalIgnoreCase)
                    || name.StartsWith("d3d", StringComparison.OrdinalIgnoreCase) || name.StartsWith("dxgi", StringComparison.OrdinalIgnoreCase)
                    || name.Contains("dwrite", StringComparison.OrdinalIgnoreCase)).ToArray() });
            previous = current;
        }
        catch (Exception error) { PerformanceTrace.Note("threads.census.error", error.Message); }
    }

    private static string Describe(int id)
    {
        var handle = OpenThread(0x0840 /* THREAD_QUERY_INFORMATION and _LIMITED_ */, false, (uint)id);
        if (handle == IntPtr.Zero) return "?";
        try
        {
            var name = "";
            if (GetThreadDescription(handle, out var text) >= 0 && text != IntPtr.Zero)
            {
                name = Marshal.PtrToStringUni(text) ?? "";
                LocalFree(text);
            }
            var module = "?";
            if (NtQueryInformationThread(handle, 9 /* ThreadQuerySetWin32StartAddress */, out var start, IntPtr.Size, IntPtr.Zero) == 0
                && modules != null)
            {
                var address = (long)start;
                var owner = modules.FirstOrDefault(entry => address >= entry.Start && address < entry.End);
                // The offset tells thread kinds apart within one module (a pool
                // worker from a timer or wait thread in ntdll).
                if (owner.Name != null) module = owner.Name + "+0x" + (address - owner.Start).ToString("x");
            }
            return (name.Length > 0 ? name : "unnamed") + " @" + module;
        }
        finally { CloseHandle(handle); }
    }

    [DllImport("kernel32.dll", SetLastError = true)] private static extern IntPtr OpenThread(uint access, bool inherit, uint id);
    [DllImport("kernel32.dll")] private static extern int GetThreadDescription(IntPtr thread, out IntPtr description);
    [DllImport("kernel32.dll")] private static extern IntPtr LocalFree(IntPtr memory);
    [DllImport("kernel32.dll")] private static extern bool CloseHandle(IntPtr handle);
    [DllImport("ntdll.dll")] private static extern int NtQueryInformationThread(IntPtr thread, int informationClass, out IntPtr information, int length, IntPtr returned);
}
