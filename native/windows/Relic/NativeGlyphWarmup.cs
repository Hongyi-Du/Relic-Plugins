using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Runtime.CompilerServices;
using Windows.UI.ViewManagement;

namespace Relic;

// Prepare before native TextBlock.MeasureOverride, not merely before painting.
// Opacity zero still measures real text and can synchronously build a cold font
// face. Keep the real text privately until its shape/raster preparation finishes;
// then restore it to the same native control. No replacement text is displayed.
internal static class NativeGlyphWarmup
{
    private static int pendingPreparations;
    private static readonly UISettings settings = new();
    private static readonly ConditionalWeakTable<TextBlock, Binding> bindings = new();
    internal static int PendingPreparations => Volatile.Read(ref pendingPreparations);

    internal static void Attach(TextBlock label, XamlRoot? windowRoot)
    {
        if (!bindings.TryGetValue(label, out _)) bindings.Add(label, new Binding(label, windowRoot));
    }

    // Existing action names may be assembled immediately after construction.
    // This is source data only: readiness/visual observers must read actual Text.
    internal static string SourceText(TextBlock label) =>
        bindings.TryGetValue(label, out var binding) ? binding.SourceText : label.Text;

    private sealed class Binding
    {
        private readonly TextBlock label;
        private readonly double opacity;
        private readonly XamlRoot? windowRoot;
        private XamlRoot? root;
        private CancellationTokenSource? cancellation;
        private NativeGlyphRasterPreparation.Request? current;
        private NativeGlyphRasterPreparation.Prepared? prepared;
        private double minimumHeight;
        private bool mounted, suspended, changingText, changingHeight;
        internal string SourceText { get; private set; }

        internal Binding(TextBlock label, XamlRoot? windowRoot)
        {
            this.label = label; this.windowRoot = windowRoot;
            SourceText = label.Text; opacity = label.Opacity; minimumHeight = label.MinHeight;
            label.RegisterPropertyChangedCallback(TextBlock.TextProperty, (_, _) =>
            {
                if (changingText) return;
                SourceText = label.Text;
                // A recycled, unloaded label must not expose new text to its
                // next first Measure before Loaded can restart preparation.
                if (suspended) WithholdText(); else Prepare();
            });
            foreach (var property in new[] { TextBlock.FontFamilyProperty, TextBlock.FontSizeProperty,
                TextBlock.FontWeightProperty, TextBlock.FontStyleProperty, TextBlock.FontStretchProperty,
                TextBlock.IsTextScaleFactorEnabledProperty, TextBlock.LineHeightProperty,
                FrameworkElement.LanguageProperty, FrameworkElement.FlowDirectionProperty })
                label.RegisterPropertyChangedCallback(property, (_, _) => Prepare());
            label.RegisterPropertyChangedCallback(FrameworkElement.MinHeightProperty, (_, _) =>
            {
                if (changingHeight) return;
                minimumHeight = label.MinHeight;
                if (cancellation != null || suspended) HoldHeight();
            });
            label.Loaded += Loaded;
            label.Unloaded += Unloaded;
            // The caller provides the actual window root while this control is
            // still detached. Preparation and text withholding happen now;
            // native layout is never allowed to get ahead of the worker.
            Prepare();
        }

        private void Loaded(object sender, RoutedEventArgs args)
        {
            if (mounted) return;
            mounted = true; suspended = false; root = label.XamlRoot;
            if (root != null) root.Changed += RootChanged;
            settings.TextScaleFactorChanged += TextScaleChanged;
            Prepare();
        }

        private void Unloaded(object sender, RoutedEventArgs args)
        {
            mounted = false; suspended = true;
            if (root != null) root.Changed -= RootChanged;
            root = null; settings.TextScaleFactorChanged -= TextScaleChanged;
            cancellation?.Cancel(); cancellation = null; current = null;
            prepared?.Dispose(); prepared = null; WithholdText();
        }

        private void RootChanged(XamlRoot sender, XamlRootChangedEventArgs args) => Prepare();
        private void TextScaleChanged(UISettings sender, object args) =>
            label.DispatcherQueue.TryEnqueue(Prepare);

        private void SetText(string value)
        {
            changingText = true;
            try { label.Text = value; }
            finally { changingText = false; }
        }

        private void SetHeight(double value)
        {
            changingHeight = true;
            try { label.MinHeight = value; }
            finally { changingHeight = false; }
        }

        private void HoldHeight()
        {
            var line = label.LineHeight > 0 ? label.LineHeight : label.FontSize * 1.6;
            SetHeight(SourceText.Length == 0 ? minimumHeight
                : Math.Max(minimumHeight, Math.Max(label.ActualHeight, line)));
        }

        private void WithholdText()
        {
            HoldHeight(); label.Opacity = 0; SetText("");
        }

        private void RestoreText()
        {
            SetText(SourceText); SetHeight(minimumHeight); label.Opacity = opacity;
        }

        private void Prepare()
        {
            if (suspended) return;
            var context = label.XamlRoot ?? windowRoot;
            // Inherited language/direction is not applied to a detached label
            // yet. Use the very window it is about to join, without modifying
            // the label's property values or substituting another font.
            var window = context?.Content as FrameworkElement;
            var language = !label.IsLoaded && label.ReadLocalValue(FrameworkElement.LanguageProperty) == DependencyProperty.UnsetValue
                ? window?.Language ?? label.Language : label.Language;
            var direction = !label.IsLoaded && label.ReadLocalValue(FrameworkElement.FlowDirectionProperty) == DependencyProperty.UnsetValue
                ? window?.FlowDirection ?? label.FlowDirection : label.FlowDirection;
            var scale = label.IsTextScaleFactorEnabled ? settings.TextScaleFactor : 1;
            var request = new NativeGlyphRasterPreparation.Request(SourceText, label.FontFamily.Source,
                language, (float)(label.FontSize * scale), label.FontWeight.Weight,
                (uint)label.FontStyle, (uint)label.FontStretch, (float)(context?.RasterizationScale ?? 1),
                direction == FlowDirection.RightToLeft);
            if (request == current)
            {
                // A caller can set the same real Text again while the native
                // property contains our empty placeholder. Keep it withheld
                // until the already-running preparation actually completes.
                if (cancellation != null) WithholdText();
                return;
            }
            current = request; cancellation?.Cancel(); prepared?.Dispose(); prepared = null;
            WithholdText();
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
                        if (!suspended && !source.IsCancellationRequested)
                        {
                            prepared = result; result = null;
                            // Warming is an optimization, never a reason to lose
                            // real text. Native rendering remains the fallback.
                            if (failure != null) PerformanceTrace.Count("glyph.prepare.failed", failure.HResult);
                            RestoreText();
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
