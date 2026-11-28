using System.Collections.Generic;
using System.Diagnostics;
using Microsoft.UI.Dispatching;

namespace Relic;

// What the code that reacts to layout did most recently: row height
// corrections and view shifts in the chat list, MaxWidth updates in the
// sidebar and the copies cards, list markers snapping again, and how many
// layout passes the current dispatcher turn has needed. When layout never
// settles, WinUI gives up after 250 passes in one turn and ends the app
// (0xC000027B with AG_E_LAYOUT_CYCLE); its own record of which code kept
// invalidating stays in memory that a crash dump does not keep. This ring
// names it in the crash record (App.CaptureFailure). Numbers and the role of
// the code only, never message text. Every caller runs on the UI thread.
internal static class LayoutFeedback
{
    private const int Capacity = 600;
    private static readonly (long At, long Turn, int Pass, string? Source, double A, double B)[] ring =
        new (long, long, int, string?, double, double)[Capacity];
    private static int next, count, passes;
    private static long turn;
    private static bool resetQueued;
    internal static int MostPasses { get; private set; }
    // Changes once the dispatcher turn's layout has settled: a panel that may
    // redo work while arranging can limit itself to once per turn.
    internal static long Turn => turn;

    internal static void Note(string source, double a = double.NaN, double b = double.NaN)
    {
        ring[next] = (Stopwatch.GetTimestamp(), turn, passes, source, a, b);
        next = (next + 1) % Capacity;
        if (count < Capacity) count++;
    }

    // From the window root's LayoutUpdated. WinUI runs every pass of one turn
    // before any queued work, so the low-priority reset runs only once the
    // turn's layout has settled (or the app has ended).
    internal static void LayoutPass(DispatcherQueue queue)
    {
        passes++;
        if (passes > MostPasses) MostPasses = passes;
        if (passes is 20 or 60 or 120 or 200 or 240) Note("layout:passes", passes);
        if (resetQueued) return;
        resetQueued = true;
        queue.TryEnqueue(DispatcherQueuePriority.Low, () => { resetQueued = false; passes = 0; turn++; });
    }

    internal static object Snapshot(int last = 400)
    {
        var now = Stopwatch.GetTimestamp();
        var entries = new List<object>();
        for (var i = System.Math.Min(last, count); i >= 1; i--)
        {
            var (at, inTurn, pass, source, a, b) = ring[(next - i + Capacity) % Capacity];
            if (source == null) continue;
            entries.Add(new
            {
                ms_ago = System.Math.Round(Stopwatch.GetElapsedTime(at, now).TotalMilliseconds, 1),
                turn = inTurn, pass, source,
                a = double.IsNaN(a) ? (double?)null : System.Math.Round(a, 3),
                b = double.IsNaN(b) ? (double?)null : System.Math.Round(b, 3)
            });
        }
        return new { most_passes_in_a_turn = MostPasses, passes_in_this_turn = passes, turn, entries };
    }
}
