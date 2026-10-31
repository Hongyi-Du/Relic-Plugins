using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using System.Threading.Channels;
using static Relic.NativeLabelInterop;

namespace Relic;

internal sealed record NativeLabelLayoutRequest(string Text, string Families, string Locale,
    float FontSize, uint Weight, float LineHeight, float Width, float Height,
    bool WholeWords, bool PrimaryLineSpacing, bool CharacterEllipsis);

// Native resource ownership moves once from the worker to the UI label. No
// worker accesses a layout after completion, and canceled results are released.
internal sealed class NativeLabelPreparedLayout : IDisposable
{
    internal IntPtr Format, Layout, TrimmingSign;
    internal float Width, Height, ResolvedLineHeight;
    internal JsonObject? Fallback, LineSpacing;
    internal TextMetrics Metrics;
    internal LineMetrics[] Lines = [];
    public void Dispose()
    { Release(ref Layout); Release(ref TrimmingSign); Release(ref Format); }
}

internal static class NativeLabelPreparation
{
    private sealed class LayoutWorker
    {
        private readonly Channel<Action> queue = Channel.CreateBounded<Action>(new BoundedChannelOptions(128)
        {
            SingleReader = true, SingleWriter = false, FullMode = BoundedChannelFullMode.Wait,
            AllowSynchronousContinuations = false
        });
        private readonly Task consumer;
        internal LayoutWorker() => consumer = Task.Run(Consume);
        internal async Task<T> Enqueue<T>(Func<CancellationToken, T> prepare, CancellationToken cancellation)
        {
            cancellation.ThrowIfCancellationRequested();
            var completion = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
            await queue.Writer.WriteAsync(() =>
            {
                T? result = default;
                var ownsResult = false;
                try
                {
                    cancellation.ThrowIfCancellationRequested();
                    result = prepare(cancellation); ownsResult = true;
                    cancellation.ThrowIfCancellationRequested();
                    if (completion.TrySetResult(result)) ownsResult = false;
                }
                catch (OperationCanceledException) when (cancellation.IsCancellationRequested)
                {
                    if (ownsResult && result is IDisposable canceled) canceled.Dispose();
                    ownsResult = false; completion.TrySetCanceled(cancellation);
                }
                catch (Exception error)
                {
                    if (ownsResult && result is IDisposable failed) failed.Dispose();
                    ownsResult = false; completion.TrySetException(error);
                }
                finally { if (ownsResult && result is IDisposable disposable) disposable.Dispose(); }
            }, cancellation).ConfigureAwait(false);
            // The consumer owns disposal until ownership is transferred by this
            // completion. Do not abandon a native result with WaitAsync(token).
            return await completion.Task.ConfigureAwait(false);
        }
        private async Task Consume()
        {
            await foreach (var work in queue.Reader.ReadAllAsync().ConfigureAwait(false)) work();
        }
    }
    private static readonly Lazy<LayoutWorker> worker = new(() => new(), LazyThreadSafetyMode.ExecutionAndPublication);
    internal static Task<NativeLabelPreparedLayout> PrepareAsync(NativeLabelLayoutRequest request, CancellationToken cancellation)
        => RunAsync(token => Prepare(request, token), cancellation);
    internal static Task<T> RunAsync<T>(Func<CancellationToken, T> prepare, CancellationToken cancellation)
        => worker.Value.Enqueue(prepare, cancellation);

    // Only DirectWrite objects and managed immutable inputs enter this method.
    // No UISettings, XAML object, renderer, SurfaceImageSource or graphics device
    // is created or touched here. This is the real layout subsequently drawn.
    internal static NativeLabelPreparedLayout Prepare(NativeLabelLayoutRequest request, CancellationToken cancellation)
    {
        using var timing = PerformanceTrace.Measure("NativeLabel.prepare.worker");
        var result = new NativeLabelPreparedLayout();
        try
        {
            cancellation.ThrowIfCancellationRequested();
            var family = request.Families.Split(',')[0].Trim().Trim('"');
            if (family.Length == 0) throw new InvalidOperationException("NativeLabel requires an explicit primary font family");
            var factory = NativeWriteFactory.Shared;
            Check(Method<CreateFormat>(factory, 15)(factory, family, IntPtr.Zero, request.Weight, 0, 5,
                request.FontSize, request.Locale, out result.Format));
            Check(Method<SetUInt>(result.Format, 5)(result.Format, request.WholeWords ? 3u : 1u));
            using (PerformanceTrace.Measure("NativeLabel.DirectWrite.CreateTextLayout.worker"))
                Check(Method<CreateLayout>(factory, 18)(factory, request.Text, checked((uint)request.Text.Length),
                    result.Format, request.Width, Math.Max(request.Height, 1000), out result.Layout));
            using (PerformanceTrace.Measure("NativeLabel.fallback.apply.worker"))
                result.Fallback = NativeLabelFallback.Apply(factory, result.Layout, request.Families);
            cancellation.ThrowIfCancellationRequested();
            LineMetrics[] natural;
            using (PerformanceTrace.Measure("NativeLabel.DirectWrite.GetLineMetrics.worker")) natural = ReadLines(result.Layout);
            result.ResolvedLineHeight = request.LineHeight;
            if (natural.Length > 0)
            {
                var baseline = natural[0].Baseline + (request.LineHeight - natural[0].Height) / 2;
                var effectiveHeight = request.LineHeight;
                result.LineSpacing = CaptureDiagnostics ? new JsonObject
                {
                    ["source"] = "Actual production IDWriteTextLayout natural line metrics and subsequent SetLineSpacing",
                    ["policy"] = request.PrimaryLineSpacing ? "primary-font-integer-metrics-floor-half-leading" : "natural-line-symmetric-half-leading",
                    ["layout_com_identity"] = ComIdentity(result.Layout),
                    ["natural_first_line_height"] = natural[0].Height, ["natural_first_line_baseline"] = natural[0].Baseline,
                    ["requested_line_height"] = request.LineHeight
                } : null;
                if (request.PrimaryLineSpacing)
                {
                    var primary = NativeListMarkerFont.ReadForLine(request.Families, request.FontSize, request.Locale, request.Weight);
                    var spacing = NativePrimaryLineMetrics.FromPrimary(primary.Metrics, request.LineHeight);
                    effectiveHeight = (float)spacing.Height; baseline = (float)spacing.Baseline;
                    if (result.LineSpacing != null)
                    {
                        result.LineSpacing["primary_font"] = primary.Evidence;
                        result.LineSpacing["leading_before"] = spacing.LeadingBefore;
                        result.LineSpacing["leading_after"] = spacing.LeadingAfter;
                    }
                }
                var spacingResult = Method<SetLineSpacing>(result.Layout, 10)(result.Layout, 1, effectiveHeight, baseline);
                if (result.LineSpacing != null)
                {
                    result.LineSpacing["set_line_spacing_hresult"] = spacingResult;
                    result.LineSpacing["applied_height"] = effectiveHeight;
                    result.LineSpacing["applied_baseline"] = baseline;
                }
                Check(spacingResult); result.ResolvedLineHeight = effectiveHeight;
            }
            if (request.CharacterEllipsis) result.TrimmingSign = ApplyCharacterEllipsis(factory, result.Layout);
            Check(Method<SetFloat>(result.Layout, 29)(result.Layout, request.Height));
            result.Width = request.Width; result.Height = request.Height;
            // Force the requested line policy and ellipsis to resolve before
            // handoff too; lazy first shaping must not return to the UI thread.
            using (PerformanceTrace.Measure("NativeLabel.DirectWrite.GetMetrics.worker"))
                Check(Method<GetTextMetrics>(result.Layout, 60)(result.Layout, out result.Metrics));
            result.Lines = ReadLines(result.Layout);
            cancellation.ThrowIfCancellationRequested();
            return result;
        }
        catch { result.Dispose(); throw; }
    }

    internal static LineMetrics[] ReadLines(IntPtr layout)
    {
        var first = Method<GetArray>(layout, 59)(layout, IntPtr.Zero, 0, out var count);
        if (first < 0 && first != unchecked((int)0x8007007A)) Check(first);
        if (count == 0) return [];
        var pointer = Marshal.AllocHGlobal(checked((int)count * Marshal.SizeOf<LineMetrics>()));
        try
        {
            Check(Method<GetArray>(layout, 59)(layout, pointer, count, out var actual));
            var result = new LineMetrics[actual];
            for (var i = 0; i < result.Length; i++)
                result[i] = Marshal.PtrToStructure<LineMetrics>(pointer + i * Marshal.SizeOf<LineMetrics>());
            return result;
        }
        finally { Marshal.FreeHGlobal(pointer); }
    }
}
