using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    // The main XAML walk can attach this raw evidence to a real NativeLabel node.
    // It is intentionally not a canonical font/geometry conversion: presentation
    // synchronization, source text ownership and equal-quantity browser evidence
    // still have to be established by the capture/matcher work.
    private static JsonObject CaptureNativeLabel(NativeLabel label) => label.CaptureProductionReceipt();
}
