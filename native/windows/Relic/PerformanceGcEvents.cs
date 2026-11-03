using System.Diagnostics.Tracing;

namespace Relic;

// CI-only evidence for collections: why each one started (the runtime's
// GCStart reason) and which types were allocated on the large object heap
// (sampled every ~100 KB by GCAllocationTick). Workstation GC raises few of
// these, so listening costs little next to the collections themselves.
internal sealed class PerformanceGcEvents : EventListener
{
    private static PerformanceGcEvents? listener;
    internal static void Start() => listener ??= new PerformanceGcEvents();

    protected override void OnEventSourceCreated(EventSource source)
    {
        if (source.Name == "Microsoft-Windows-DotNETRuntime")
            EnableEvents(source, EventLevel.Verbose, (EventKeywords)0x1 /* GC */);
    }

    protected override void OnEventWritten(EventWrittenEventArgs data)
    {
        try
        {
            if (data.EventName?.StartsWith("GCStart", StringComparison.Ordinal) == true)
                PerformanceTrace.Note("gc.start", new { depth = Value(data, "Depth"), reason = Value(data, "Reason"), type = Value(data, "Type") });
            else if (data.EventName?.StartsWith("GCAllocationTick", StringComparison.Ordinal) == true
                && Convert.ToInt32(Value(data, "AllocationKind")) == 1 /* large object heap */)
                PerformanceTrace.Note("gc.loh_tick", new { type = Value(data, "TypeName"), bytes = Value(data, "AllocationAmount64"), size = Value(data, "ObjectSize") });
        }
        catch (Exception) { /* Diagnostics never disturb the measured app. */ }
    }

    private static object? Value(EventWrittenEventArgs data, string name)
    {
        var index = data.PayloadNames?.IndexOf(name) ?? -1;
        return index >= 0 && data.Payload != null && index < data.Payload.Count ? data.Payload[index]?.ToString() : null;
    }
}
