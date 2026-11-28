using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using System.Threading.Channels;

namespace Relic;

internal sealed record NativePathBoundaries(int[] Lines, int[] Characters, int[] Words, JsonObject Evidence);

internal static class NativePathIcu
{
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate IntPtr Open(int type, IntPtr locale, IntPtr text, int length, ref int error);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate int Position(IntPtr iterator);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate void Close(IntPtr iterator);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate void Version([Out] byte[] version);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] private delegate IntPtr Locale(IntPtr iterator, int type, ref int error);

    // The system module and its immutable exports live for the process. Loading
    // and freeing ICU for every label repeatedly tears down its shared caches.
    // Each Read still owns separate iterators and unmodified UTF16 buffers.
    private static readonly Lazy<SystemLibrary> library = new(() => new SystemLibrary(), LazyThreadSafetyMode.ExecutionAndPublication);
    private static readonly Lazy<BoundaryWorker> worker = new(() => new BoundaryWorker(), LazyThreadSafetyMode.ExecutionAndPublication);

    private sealed class SystemLibrary
    {
        internal readonly IntPtr Common, International;
        internal readonly string Path, IcuVersion, UnicodeVersion;
        internal readonly Open Open;
        internal readonly Position First, Next;
        internal readonly Close Close;
        internal readonly Locale GetLocale;

        internal SystemLibrary()
        {
            IntPtr common = IntPtr.Zero, international = IntPtr.Zero;
            try
            {
                var folder = Environment.GetFolderPath(Environment.SpecialFolder.System);
                Path = System.IO.Path.Combine(folder, "icu.dll");
                if (NativeLibrary.TryLoad(Path, out common)) international = common;
                else
                {
                    Path = System.IO.Path.Combine(folder, "icuuc.dll"); common = NativeLibrary.Load(Path);
                    international = NativeLibrary.Load(System.IO.Path.Combine(folder, "icuin.dll"));
                }
                static T Export<T>(IntPtr module, string name) where T : Delegate => Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(module, name));
                var version = new byte[4]; var unicode = new byte[4];
                Export<Version>(common, "u_getVersion")(version); Export<Version>(common, "u_getUnicodeVersion")(unicode);
                IcuVersion = string.Join(".", version); UnicodeVersion = string.Join(".", unicode);
                Open = Export<Open>(international, "ubrk_open"); First = Export<Position>(international, "ubrk_first");
                Next = Export<Position>(international, "ubrk_next"); Close = Export<Close>(international, "ubrk_close");
                GetLocale = Export<Locale>(international, "ubrk_getLocaleByType");
                Common = common; International = international;
            }
            catch
            {
                if (international != IntPtr.Zero && international != common) NativeLibrary.Free(international);
                if (common != IntPtr.Zero) NativeLibrary.Free(common);
                throw;
            }
            // Successful handles intentionally have no finalizer/Dispose:
            // both synchronous callers and the one worker may use these exports.
        }
    }

    private sealed record Work(string Text, string Locale, CancellationToken Cancellation,
        TaskCompletionSource<NativePathBoundaries> Completion);

    private sealed class BoundaryWorker
    {
        private readonly Channel<Work> queue = Channel.CreateBounded<Work>(new BoundedChannelOptions(128)
        {
            SingleReader = true, SingleWriter = false, FullMode = BoundedChannelFullMode.Wait,
            AllowSynchronousContinuations = false
        });
        private readonly Task consumer;
        internal BoundaryWorker() => consumer = Task.Run(Consume);

        internal async Task<NativePathBoundaries> Enqueue(string text, string locale, CancellationToken cancellation)
        {
            cancellation.ThrowIfCancellationRequested();
            var completion = new TaskCompletionSource<NativePathBoundaries>(TaskCreationOptions.RunContinuationsAsynchronously);
            await queue.Writer.WriteAsync(new(text, locale, cancellation, completion), cancellation).ConfigureAwait(false);
            return await completion.Task.WaitAsync(cancellation).ConfigureAwait(false);
        }

        private async Task Consume()
        {
            await foreach (var work in queue.Reader.ReadAllAsync().ConfigureAwait(false))
            {
                if (work.Cancellation.IsCancellationRequested)
                {
                    work.Completion.TrySetCanceled(work.Cancellation); continue;
                }
                try
                {
                    var result = ReadCore(work.Text, work.Locale, work.Cancellation);
                    work.Cancellation.ThrowIfCancellationRequested();
                    work.Completion.TrySetResult(result);
                }
                catch (OperationCanceledException) when (work.Cancellation.IsCancellationRequested)
                { work.Completion.TrySetCanceled(work.Cancellation); }
                catch (Exception error) { work.Completion.TrySetException(error); }
            }
        }
    }

    // Callers retain at most one outstanding request per text owner and cancel
    // it when that owner unloads. Waiting for queue space never blocks the UI.
    internal static Task<NativePathBoundaries> ReadAsync(string text, string locale, CancellationToken cancellation = default)
    {
        cancellation.ThrowIfCancellationRequested();
        return worker.Value.Enqueue(text, locale, cancellation);
    }

    internal static NativePathBoundaries Read(string text, string locale) => ReadCore(text, locale, CancellationToken.None);

    private static NativePathBoundaries ReadCore(string text, string locale, CancellationToken cancellation)
    {
        using var timing = PerformanceTrace.Measure("NativePath.ICU.boundaries");
        cancellation.ThrowIfCancellationRequested();
        var api = library.Value;
        IntPtr input = IntPtr.Zero, language = IntPtr.Zero;
        try
        {
            input = Marshal.StringToHGlobalUni(text); language = Marshal.StringToCoTaskMemUTF8(locale);
            var receipts = new JsonArray();
            int[] Boundaries(int type)
            {
                cancellation.ThrowIfCancellationRequested();
                var error = 0; var iterator = api.Open(type, language, input, text.Length, ref error);
                if (iterator == IntPtr.Zero || error > 0) throw new InvalidOperationException("System ICU ubrk_open failed: " + error);
                try
                {
                    var localeError = 0; var actualLocale = Marshal.PtrToStringUTF8(api.GetLocale(iterator, 0, ref localeError));
                    if (localeError > 0) throw new InvalidOperationException("System ICU actual locale unavailable: " + localeError);
                    var result = new List<int>();
                    for (var p = api.First(iterator); p != -1; p = api.Next(iterator))
                    {
                        cancellation.ThrowIfCancellationRequested();
                        if (p < 0 || p > text.Length || result.Count > text.Length || result.Count > 0 && p <= result[^1])
                            throw new InvalidOperationException("System ICU returned an invalid source boundary");
                        result.Add(p);
                    }
                    if (result.Count == 0 || result[0] != 0 || result[^1] != text.Length)
                        throw new InvalidOperationException("System ICU did not cover the complete source");
                    if (NativeLabelInterop.CaptureDiagnostics) receipts.Add(new JsonObject { ["type"] = type, ["open_status"] = error, ["actual_locale"] = actualLocale,
                        ["actual_locale_status"] = localeError, ["boundaries_utf16"] = new JsonArray(result.Select(n => JsonValue.Create(n)).ToArray()) });
                    return result.ToArray();
                }
                finally { api.Close(iterator); }
            }
            var lines = Boundaries(2); var characters = Boundaries(0); var words = Boundaries(1);
            if (!NativeLabelInterop.CaptureDiagnostics) return new NativePathBoundaries(lines, characters, words, new JsonObject());
            return new NativePathBoundaries(lines, characters, words, new JsonObject
            {
                ["source"] = "Actual system ICU ubrk iterators over the unchanged production source",
                ["library"] = api.Path, ["icu_version"] = api.IcuVersion, ["unicode_version"] = api.UnicodeVersion,
                ["requested_locale"] = locale, ["source_text"] = text, ["iterators"] = receipts
            });
        }
        finally
        {
            if (input != IntPtr.Zero) Marshal.FreeHGlobal(input);
            if (language != IntPtr.Zero) Marshal.FreeCoTaskMem(language);
        }
    }
}
