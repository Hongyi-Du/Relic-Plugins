using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.UI.ViewManagement;

namespace Relic;

// Prepare the actual mounted label's glyphs before WinUI first rasterizes it.
// Opacity zero retains measure/arrange but WinUI's HW render walk culls the
// text (hwwalk.cpp, skipRenderWhileTransparent). The original TextBlock, font,
// selection and automation remain the production presentation.
internal static class NativeGlyphWarmup
{
    private static int pendingPreparations;
    private static readonly UISettings settings = new();
    internal static int PendingPreparations => Volatile.Read(ref pendingPreparations);

    internal static void Attach(TextBlock label) => _ = new Binding(label);

    private sealed class Binding
    {
        private readonly TextBlock label;
        private readonly double opacity;
        private readonly List<(DependencyProperty Property, long Token)> callbacks = [];
        private XamlRoot? root;
        private CancellationTokenSource? cancellation;
        private NativeGlyphRasterPreparation.Request? current;
        private NativeGlyphRasterPreparation.Prepared? prepared;
        private bool mounted;

        internal Binding(TextBlock label)
        {
            this.label = label; opacity = label.Opacity; label.Opacity = 0;
            label.Loaded += Loaded;
            label.Unloaded += Unloaded;
        }

        private void Loaded(object sender, RoutedEventArgs args)
        {
            if (mounted) return;
            mounted = true; root = label.XamlRoot;
            if (root != null) root.Changed += RootChanged;
            settings.TextScaleFactorChanged += TextScaleChanged;
            foreach (var property in new[] { TextBlock.TextProperty, TextBlock.FontFamilyProperty,
                TextBlock.FontSizeProperty, TextBlock.FontWeightProperty, TextBlock.FontStyleProperty,
                TextBlock.FontStretchProperty, TextBlock.IsTextScaleFactorEnabledProperty,
                FrameworkElement.LanguageProperty, FrameworkElement.FlowDirectionProperty })
                callbacks.Add((property, label.RegisterPropertyChangedCallback(property, (_, _) => Prepare())));
            Prepare();
        }

        private void Unloaded(object sender, RoutedEventArgs args)
        {
            mounted = false;
            if (root != null) root.Changed -= RootChanged;
            root = null; settings.TextScaleFactorChanged -= TextScaleChanged;
            foreach (var (property, token) in callbacks) label.UnregisterPropertyChangedCallback(property, token);
            callbacks.Clear(); cancellation?.Cancel(); cancellation = null; current = null;
            prepared?.Dispose(); prepared = null; label.Opacity = 0;
        }

        private void RootChanged(XamlRoot sender, XamlRootChangedEventArgs args) => Prepare();
        private void TextScaleChanged(UISettings sender, object args) =>
            label.DispatcherQueue.TryEnqueue(Prepare);

        private void Prepare()
        {
            if (!mounted || !label.IsLoaded || label.XamlRoot == null) return;
            var scale = label.IsTextScaleFactorEnabled ? settings.TextScaleFactor : 1;
            var request = new NativeGlyphRasterPreparation.Request(label.Text, label.FontFamily.Source,
                label.Language, (float)(label.FontSize * scale), label.FontWeight.Weight,
                (uint)label.FontStyle, (uint)label.FontStretch, (float)label.XamlRoot.RasterizationScale,
                label.FlowDirection == FlowDirection.RightToLeft);
            if (request == current) return;
            current = request; cancellation?.Cancel(); prepared?.Dispose(); prepared = null;
            label.Opacity = 0;
            var source = cancellation = new CancellationTokenSource();
            Interlocked.Increment(ref pendingPreparations);
            _ = Complete(request, source);
        }

        private async Task Complete(NativeGlyphRasterPreparation.Request request, CancellationTokenSource source)
        {
            NativeGlyphRasterPreparation.Prepared? result = null;
            Exception? failure = null;
            try
            {
                // The existing bounded, single-consumer worker owns every
                // mutable layout/analysis. No XAML or D2D device crosses over.
                result = await NativeLabelPreparation.RunAsync(token =>
                    NativeGlyphRasterPreparation.Prepare(request, token), source.Token).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (source.IsCancellationRequested) { }
            catch (Exception error) { failure = error; }
            void Finish()
            {
                try
                {
                    if (ReferenceEquals(cancellation, source))
                    {
                        cancellation = null;
                        if (mounted && !source.IsCancellationRequested)
                        {
                            prepared = result; result = null;
                            // Warming is an optimization, never a reason to lose
                            // real text. Native rendering remains the fallback.
                            if (failure != null) PerformanceTrace.Count("glyph.prepare.failed", failure.HResult);
                            label.Opacity = opacity;
                        }
                    }
                }
                finally
                {
                    result?.Dispose(); source.Dispose();
                    Interlocked.Decrement(ref pendingPreparations);
                    PresentationPreparation.NotifyCompletion();
                }
            }
            if (!label.DispatcherQueue.TryEnqueue(Finish))
            {
                result?.Dispose(); source.Dispose();
                Interlocked.Decrement(ref pendingPreparations);
                PresentationPreparation.NotifyCompletion();
            }
        }
    }
}
