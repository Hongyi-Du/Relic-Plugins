using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;

// Read-only observations of the observer itself. The executable manifest sets
// PMv2 before managed/module initialization; this helper does not switch either
// the thread or process context, and never transforms a provider rectangle.
internal static class ObserverDpiAwareness
{
    internal static readonly nint PerMonitorV2 = new(-4);

    internal interface IApi
    {
        uint GetCurrentThreadId();
        nint GetThreadDpiAwarenessContext();
        int GetAwarenessFromDpiAwarenessContext(nint context);
        bool AreDpiAwarenessContextsEqual(nint first, nint second);
    }

    internal static JsonObject Read(string stage) => Read(stage, new NativeApi());

    internal static JsonObject Read(string stage, IApi api)
    {
        var calls = new JsonArray(); var errors = new JsonArray();
        var receipt = new JsonObject
        {
            ["source"] = "Actual observer-thread user32 DPI-awareness getters; no context setter",
            ["stage"] = stage, ["qpc"] = Stopwatch.GetTimestamp(), ["qpc_frequency"] = Stopwatch.Frequency,
            ["observer_pid"] = Environment.ProcessId, ["managed_thread_id"] = Environment.CurrentManagedThreadId,
            ["thread_context"] = null, ["awareness"] = null, ["equals_per_monitor_v2"] = null,
            ["calls"] = calls, ["errors"] = errors
        };
        T? Call<T>(string name, Func<T> read, Func<T, JsonNode?> value)
        {
            var call = new JsonObject { ["api"] = name };
            calls.Add(call);
            try
            {
                var actual = read(); call["status"] = "returned"; call["value"] = value(actual);
                return actual;
            }
            catch (Exception error)
            {
                call["status"] = "failed";
                call["exception_type"] = error.GetType().FullName;
                call["hresult"] = error.HResult;
                call["hresult_hex"] = "0x" + unchecked((uint)error.HResult).ToString("X8", CultureInfo.InvariantCulture);
                call["message"] = error.Message;
                errors.Add(name + ": " + error.GetType().Name + ": " + error.Message);
                return default;
            }
        }
        // These getters do not document GetLastError. Preserve their returned
        // values/exceptions, rather than attaching an unrelated last-error slot.
        var nativeThread = Call("GetCurrentThreadId", api.GetCurrentThreadId, value => JsonValue.Create(value));
        receipt["native_thread_id"] = nativeThread == 0 ? null : JsonValue.Create(nativeThread);
        if (nativeThread == 0) errors.Add("Actual observer native thread ID is unavailable.");
        var context = Call("GetThreadDpiAwarenessContext", api.GetThreadDpiAwarenessContext,
            value => JsonValue.Create("0x" + unchecked((ulong)value.ToInt64()).ToString("X", CultureInfo.InvariantCulture)));
        if (context == 0)
        {
            errors.Add("GetThreadDpiAwarenessContext did not provide a usable context; awareness remains unknown.");
        }
        else
        {
            receipt["thread_context"] = "0x" + unchecked((ulong)context.ToInt64()).ToString("X", CultureInfo.InvariantCulture);
            var awarenessCallCount = calls.Count;
            var awareness = Call("GetAwarenessFromDpiAwarenessContext", () => api.GetAwarenessFromDpiAwarenessContext(context),
                value => JsonValue.Create(value));
            if (calls[awarenessCallCount]!["status"]!.GetValue<string>() == "returned")
            {
                receipt["awareness"] = awareness;
                if (awareness is < 0 or > 2) errors.Add("The actual thread context has invalid DPI_AWARENESS.");
            }
            var equalityCallCount = calls.Count;
            var equal = Call("AreDpiAwarenessContextsEqual", () => api.AreDpiAwarenessContextsEqual(context, PerMonitorV2),
                value => JsonValue.Create(value));
            calls[equalityCallCount]!["compared_to"] = "DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2";
            if (calls[equalityCallCount]!["status"]!.GetValue<string>() == "returned")
                receipt["equals_per_monitor_v2"] = equal;
            // Awareness=2 alone also describes PMv1. Only the real equality API
            // can confirm PMv2; opaque context handles cannot be bit-compared.
            if (receipt["awareness"]?.GetValue<int>() != 2 || receipt["equals_per_monitor_v2"]?.GetValue<bool>() != true)
                errors.Add("Actual observer thread is not confirmed PerMonitorV2 as declared by its manifest.");
        }
        receipt["status"] = errors.Count == 0 ? "measured-per-monitor-v2" : "failed";
        return receipt;
    }

    private sealed class NativeApi : IApi
    {
        public uint GetCurrentThreadId() => NativeGetCurrentThreadId();
        public nint GetThreadDpiAwarenessContext() => NativeGetThreadDpiAwarenessContext();
        public int GetAwarenessFromDpiAwarenessContext(nint context) => NativeGetAwarenessFromDpiAwarenessContext(context);
        public bool AreDpiAwarenessContextsEqual(nint first, nint second) => NativeAreDpiAwarenessContextsEqual(first, second);
        [DllImport("kernel32.dll", EntryPoint = "GetCurrentThreadId")]
        private static extern uint NativeGetCurrentThreadId();
        [DllImport("user32.dll", EntryPoint = "GetThreadDpiAwarenessContext")]
        private static extern nint NativeGetThreadDpiAwarenessContext();
        [DllImport("user32.dll", EntryPoint = "GetAwarenessFromDpiAwarenessContext")]
        private static extern int NativeGetAwarenessFromDpiAwarenessContext(nint context);
        [DllImport("user32.dll", EntryPoint = "AreDpiAwarenessContextsEqual")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool NativeAreDpiAwarenessContextsEqual(nint first, nint second);
    }
}
