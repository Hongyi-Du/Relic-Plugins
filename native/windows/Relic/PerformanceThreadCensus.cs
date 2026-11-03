using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Relic;

// CI-only evidence for the switch phase's thread-count check: which threads
// appear and disappear between censuses, named by their description and by
// the module that contains their Win32 start address (.NET pool workers, the
// Windows thread pool in ntdll, WinUI, DirectWrite, ...).
internal static class PerformanceThreadCensus
{
    private static Dictionary<int, string>? previous;
    private static List<(string Name, long Start, long End)>? modules;

    internal static void Take()
    {
        try
        {
            using var process = Process.GetCurrentProcess();
            modules ??= process.Modules.Cast<ProcessModule>()
                .Select(module => (System.IO.Path.GetFileName(module.FileName ?? module.ModuleName) ?? "",
                    (long)module.BaseAddress, (long)module.BaseAddress + module.ModuleMemorySize)).ToList();
            var current = new Dictionary<int, string>();
            foreach (ProcessThread thread in process.Threads)
            {
                var id = thread.Id;
                current[id] = previous != null && previous.TryGetValue(id, out var known) ? known : Describe(id);
                thread.Dispose();
            }
            if (previous != null)
            {
                var appeared = current.Where(pair => !previous.ContainsKey(pair.Key)).Select(pair => pair.Value).ToArray();
                var gone = previous.Where(pair => !current.ContainsKey(pair.Key)).Select(pair => pair.Value).ToArray();
                if (appeared.Length > 0 || gone.Length > 0)
                    PerformanceTrace.Note("threads.census", new { count = current.Count, appeared, gone });
            }
            else PerformanceTrace.Note("threads.census", new { count = current.Count, all = current.Values.ToArray() });
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
                module = modules.FirstOrDefault(entry => address >= entry.Start && address < entry.End).Name ?? "?";
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
