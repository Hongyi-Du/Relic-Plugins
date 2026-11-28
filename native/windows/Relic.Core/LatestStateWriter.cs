using System.Text.Json.Nodes;
using System.Threading.Channels;

namespace Relic.Core;

/// <summary>
/// Persists one state file without doing serialization or file I/O on the caller.
/// There is one worker and at most one waiting snapshot; a newer waiting snapshot
/// replaces the older one. Use a separate instance for each state file.
/// </summary>
public sealed class LatestStateWriter : IAsyncDisposable
{
    private sealed record Snapshot(long Version, string Path, JsonNode Value);

    private readonly object sync = new();
    private readonly Channel<Snapshot> snapshots = Channel.CreateBounded<Snapshot>(new BoundedChannelOptions(1)
    {
        SingleReader = true,
        SingleWriter = false,
        AllowSynchronousContinuations = false,
        FullMode = BoundedChannelFullMode.DropOldest
    });
    private readonly Func<string, string, Task> write;
    private readonly Task worker;
    private TaskCompletionSource<bool> progress = NewProgress();
    private long queuedVersion, completedVersion;
    private bool closing;

    public LatestStateWriter(Func<string, string, Task>? write = null)
    {
        this.write = write ?? WriteFile;
        worker = Task.Run(Consume);
    }

    /// <summary>
    /// Transfers ownership of a complete snapshot. The caller must not mutate
    /// the node or any of its children after this call.
    /// </summary>
    public void Queue(string path, JsonNode snapshot)
    {
        ArgumentException.ThrowIfNullOrEmpty(path);
        ArgumentNullException.ThrowIfNull(snapshot);
        lock (sync)
        {
            ObjectDisposedException.ThrowIf(closing, this);
            snapshots.Writer.TryWrite(new(++queuedVersion, path, snapshot));
        }
    }

    /// <summary>
    /// Waits for the latest snapshot queued before this call to be attempted.
    /// A newer snapshot may replace it while another write is still in progress.
    /// Expected file access failures remain best effort, as with normal writes.
    /// </summary>
    public async Task FlushAsync()
    {
        long target;
        lock (sync) target = queuedVersion;
        while (true)
        {
            Task changed;
            lock (sync)
            {
                if (completedVersion >= target) return;
                changed = progress.Task;
            }
            if (await Task.WhenAny(changed, worker).ConfigureAwait(false) == worker)
            {
                // Propagate an unexpected programming error instead of leaving
                // a flush waiting indefinitely on a stopped worker.
                await worker.ConfigureAwait(false);
                return;
            }
        }
    }

    public ValueTask DisposeAsync()
    {
        lock (sync)
        {
            if (!closing)
            {
                closing = true;
                snapshots.Writer.TryComplete();
            }
        }
        // Completing the channel drains its final waiting snapshot, including
        // when a previous write is still in progress. Repeated disposal is safe.
        return new ValueTask(worker);
    }

    private async Task Consume()
    {
        await foreach (var snapshot in snapshots.Reader.ReadAllAsync().ConfigureAwait(false))
        {
            try
            {
                var json = snapshot.Value.ToJsonString();
                await write(snapshot.Path, json).ConfigureAwait(false);
            }
            catch (Exception error) when (error is IOException or UnauthorizedAccessException) { }

            TaskCompletionSource<bool> changed;
            lock (sync)
            {
                completedVersion = snapshot.Version;
                changed = progress;
                progress = NewProgress();
            }
            changed.TrySetResult(true);
        }
    }

    private static TaskCompletionSource<bool> NewProgress() => new(TaskCreationOptions.RunContinuationsAsynchronously);

    private static async Task WriteFile(string path, string json)
    {
        var directory = Path.GetDirectoryName(path);
        if (!string.IsNullOrEmpty(directory)) Directory.CreateDirectory(directory);
        var temporary = path + ".tmp";
        await File.WriteAllTextAsync(temporary, json).ConfigureAwait(false);
        File.Move(temporary, path, overwrite: true);
    }
}
