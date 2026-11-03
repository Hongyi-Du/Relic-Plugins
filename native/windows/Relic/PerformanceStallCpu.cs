using System.Diagnostics;
using System.Runtime.InteropServices;

namespace Relic;

// CI-only evidence for long UI stalls: while the UI thread did not answer a
// probe ping, did it compute, wait, or wait for a CPU? Simple settings rows
// measured 60-388 ms each and the first window layout 206 ms with nothing of
// ours timed inside. Read at each ping and again when a slow one answers: the
// UI thread's own cycles, the whole process's, and every processor's idle
// cycles. UI cycles near the stall's length mean work on the UI thread; few UI
// cycles with idle processors mean it waited (a lock, I/O, another process);
// few UI cycles with busy processors mean other threads had the CPUs.
internal static class PerformanceStallCpu
{
    internal readonly record struct Reading(long At, ulong Ui, ulong Process, ulong Idle);

    private static IntPtr uiThread;
    private static ulong[]? idle;
    private static double cyclesPerMs;

    // On the UI thread, once.
    internal static void CaptureUiThread()
    {
        if (uiThread != IntPtr.Zero) return;
        uiThread = OpenThread(0x0800 /* THREAD_QUERY_LIMITED_INFORMATION */, false, GetCurrentThreadId());
        try
        {
            // Cycle counts run at the processor's nominal clock.
            var mhz = Microsoft.Win32.Registry.GetValue(@"HKEY_LOCAL_MACHINE\HARDWARE\DESCRIPTION\System\CentralProcessor\0", "~MHz", 0);
            cyclesPerMs = Convert.ToDouble(mhz) * 1000;
        }
        catch (Exception) { cyclesPerMs = 0; }
    }

    internal static Reading Read()
    {
        ulong ui = 0, process = 0, sum = 0;
        if (uiThread != IntPtr.Zero) QueryThreadCycleTime(uiThread, out ui);
        QueryProcessCycleTime(GetCurrentProcess(), out process);
        idle ??= new ulong[Environment.ProcessorCount];
        var length = (uint)(idle.Length * sizeof(ulong));
        if (QueryIdleProcessorCycleTime(ref length, idle)) foreach (var value in idle) sum += value;
        return new(Stopwatch.GetTimestamp(), ui, process, sum);
    }

    internal static void Note(string action, double stallMs, Reading start, Reading end)
    {
        var wall = (end.At - start.At) * 1000d / Stopwatch.Frequency;
        double Ms(ulong cycles) => cyclesPerMs > 0 ? Math.Round(cycles / cyclesPerMs, 1) : -1;
        PerformanceTrace.Note("ui.stall.cpu", new
        {
            action, stall_ms = Math.Round(stallMs, 1), window_ms = Math.Round(wall, 1),
            ui_cpu_ms = Ms(end.Ui - start.Ui), process_cpu_ms = Ms(end.Process - start.Process),
            idle_ms_all_processors = Ms(end.Idle - start.Idle), processors = Environment.ProcessorCount,
            mhz = Math.Round(cyclesPerMs / 1000)
        });
    }

    [DllImport("kernel32.dll")] private static extern uint GetCurrentThreadId();
    [DllImport("kernel32.dll", SetLastError = true)] private static extern IntPtr OpenThread(uint access, bool inherit, uint id);
    [DllImport("kernel32.dll")] private static extern bool QueryThreadCycleTime(IntPtr thread, out ulong cycles);
    [DllImport("kernel32.dll")] private static extern bool QueryProcessCycleTime(IntPtr process, out ulong cycles);
    [DllImport("kernel32.dll")] private static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll")] private static extern bool QueryIdleProcessorCycleTime(ref uint bufferLength, [Out] ulong[] buffer);
}
