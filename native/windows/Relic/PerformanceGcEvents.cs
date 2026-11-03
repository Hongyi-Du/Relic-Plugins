using System.Diagnostics.Tracing;

namespace Relic;

// CI-only evidence for collections: why each one started (the runtime's
// GCStart reason: 0 small allocation, 1 induced, 4 large allocation,
// 7 induced but not forced, as GC.AddMemoryPressure and XAML's reference
// tracker request). Informational GC events are few; allocation sampling,
// which needs the verbose level, is left off so it cannot slow the app.
internal sealed class PerformanceGcEvents : EventListener
{
    private static PerformanceGcEvents? listener;
    internal static void Start() => listener ??= new PerformanceGcEvents();

    protected override void OnEventSourceCreated(EventSource source)
    {
        if (source.Name == "Microsoft-Windows-DotNETRuntime")
            EnableEvents(source, EventLevel.Informational, (EventKeywords)0x1 /* GC */);
    }

    protected override void OnEventWritten(EventWrittenEventArgs data)
    {
        try
        {
            if (data.EventName?.StartsWith("GCStart", StringComparison.Ordinal) == true)
                PerformanceTrace.Note("gc.start", new { depth = Value(data, "Depth"), reason = Value(data, "Reason"), type = Value(data, "Type") });
        }
        catch (Exception) { /* Diagnostics never disturb the measured app. */ }
    }

    private static object? Value(EventWrittenEventArgs data, string name)
    {
        var index = data.PayloadNames?.IndexOf(name) ?? -1;
        return index >= 0 && data.Payload != null && index < data.Payload.Count ? data.Payload[index]?.ToString() : null;
    }
}
