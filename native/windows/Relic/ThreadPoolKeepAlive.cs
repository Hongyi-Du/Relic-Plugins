namespace Relic;

// Keeps a fixed set of thread-pool workers alive between bursts of work.
// .NET 8 retires a worker after 20 s without work, so every burst (opening or
// switching chats starts several reads and parses at once) created workers
// that exited 20 s later, and the next burst paid for creating them again.
// .NET 9 adds ThreadPool.ThreadsToKeepAlive for this; on .NET 8 a worker's
// timeout starts over whenever it runs an item.
internal static class ThreadPoolKeepAlive
{
    private static Timer? timer;

    internal static void Start(int workers)
    {
        if (workers <= 0 || timer != null) return;
        // Well inside the 20 s timeout, and rare enough to cost nothing measurable.
        timer = new Timer(_ => Touch(workers), null, TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(8));
    }

    private static void Touch(int workers)
    {
        // Each item waits briefly for the others, so the items run on distinct
        // workers instead of one worker taking them all in turn. Nothing waits
        // for the items, and nothing disposes the event under them.
        var started = new CountdownEvent(workers);
        for (var index = 0; index < workers; index++)
            ThreadPool.UnsafeQueueUserWorkItem(static state =>
            {
                var gate = (CountdownEvent)state!;
                gate.Signal();
                gate.Wait(TimeSpan.FromMilliseconds(250));
            }, started);
    }
}
