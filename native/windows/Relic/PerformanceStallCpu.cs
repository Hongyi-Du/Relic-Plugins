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
    private static long uiThreadId;
    private static ulong[]? idle;
    private static double cyclesPerMs;

    // On the UI thread, once.
    internal static void CaptureUiThread()
    {
        if (uiThread != IntPtr.Zero) return;
        uiThreadId = GetCurrentThreadId();
        uiThread = OpenThread(0x0800 /* THREAD_QUERY_LIMITED_INFORMATION */, false, (uint)uiThreadId);
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

    internal static void Note(string action, double stallMs, Reading start, Reading end, Waits? waits)
    {
        var wall = (end.At - start.At) * 1000d / Stopwatch.Frequency;
        double Ms(ulong cycles) => cyclesPerMs > 0 ? Math.Round(cycles / cyclesPerMs, 1) : -1;
        PerformanceTrace.Note("ui.stall.cpu", new
        {
            action, stall_ms = Math.Round(stallMs, 1), window_ms = Math.Round(wall, 1),
            ui_cpu_ms = Ms(end.Ui - start.Ui), process_cpu_ms = Ms(end.Process - start.Process),
            idle_ms_all_processors = Ms(end.Idle - start.Idle), processors = Environment.ProcessorCount,
            mhz = Math.Round(cyclesPerMs / 1000),
            // "state/wait reason" of the UI thread, sampled every 40 ms from
            // 80 ms into the stall (KTHREAD_STATE 2 running, 1 ready, 5
            // waiting; KWAIT_REASON 2 or 9 page-in, 6 or 13 user request,
            // 17 LPC reply, 21 keyed event, 28 push lock, 37 alert by
            // thread id), and the process's hard faults over those samples.
            ui_states = waits?.States, hard_faults = waits?.HardFaults
        });
    }

    // The UI thread's state while a ping is pending, from one system snapshot
    // (it lists every process, so only while a stall is under way).
    internal sealed class Waits
    {
        internal readonly Dictionary<string, int> States = [];
        private uint? first;
        internal uint HardFaults { get; private set; }
        internal void Sample()
        {
            if (Snapshot() is not { } state) return;
            var key = state.State + "/" + state.WaitReason;
            States[key] = States.GetValueOrDefault(key) + 1;
            first ??= state.HardFaults;
            HardFaults = state.HardFaults - first.Value;
        }
    }

    private readonly record struct UiState(int State, int WaitReason, uint HardFaults);
    private static IntPtr snapshot;
    private static int snapshotLength;

    private static UiState? Snapshot()
    {
        try
        {
            for (var attempt = 0; attempt < 3; attempt++)
            {
                if (snapshot == IntPtr.Zero) { snapshotLength = 4 << 20; snapshot = Marshal.AllocHGlobal(snapshotLength); }
                var status = NtQuerySystemInformation(5 /* SystemProcessInformation */, snapshot, snapshotLength, out var needed);
                if (status == unchecked((int)0xC0000004)) // STATUS_INFO_LENGTH_MISMATCH
                {
                    Marshal.FreeHGlobal(snapshot); snapshot = IntPtr.Zero;
                    snapshotLength = Math.Max(needed + (1 << 20), snapshotLength * 2);
                    snapshot = Marshal.AllocHGlobal(snapshotLength); continue;
                }
                if (status != 0) return null;
                long process = Environment.ProcessId, offset = 0;
                while (true)
                {
                    // SYSTEM_PROCESS_INFORMATION (x64): HardFaultCount at 0x10,
                    // UniqueProcessId at 0x50, threads from 0x100, 0x50 bytes each
                    // with UniqueThread at 0x30, ThreadState 0x44, WaitReason 0x48.
                    var entry = snapshot + (nint)offset;
                    if ((long)Marshal.ReadIntPtr(entry, 0x50) == process)
                    {
                        var hardFaults = (uint)Marshal.ReadInt32(entry, 0x10);
                        var threads = Marshal.ReadInt32(entry, 4);
                        for (var index = 0; index < threads; index++)
                        {
                            var thread = entry + 0x100 + index * 0x50;
                            if ((long)Marshal.ReadIntPtr(thread, 0x30) == uiThreadId)
                                return new UiState(Marshal.ReadInt32(thread, 0x44), Marshal.ReadInt32(thread, 0x48), hardFaults);
                        }
                        return new UiState(-1, -1, hardFaults);
                    }
                    var next = Marshal.ReadInt32(entry, 0);
                    if (next == 0) return null;
                    offset += next;
                }
            }
        }
        catch (Exception) { }
        return null;
    }
    [DllImport("ntdll.dll")] private static extern int NtQuerySystemInformation(int informationClass, IntPtr information, int length, out int returned);

    [DllImport("kernel32.dll")] private static extern uint GetCurrentThreadId();
    [DllImport("kernel32.dll", SetLastError = true)] private static extern IntPtr OpenThread(uint access, bool inherit, uint id);
    [DllImport("kernel32.dll")] private static extern bool QueryThreadCycleTime(IntPtr thread, out ulong cycles);
    [DllImport("kernel32.dll")] private static extern bool QueryProcessCycleTime(IntPtr process, out ulong cycles);
    [DllImport("kernel32.dll")] private static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll")] private static extern bool QueryIdleProcessorCycleTime(ref uint bufferLength, [Out] ulong[] buffer);
}
