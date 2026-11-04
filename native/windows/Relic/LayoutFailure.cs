using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;

namespace Relic;

// WinUI surfaces a failing native layout (a list panel returning E_FAIL, for
// one) at the nearest managed element, as a COMException whose stack names
// neither that element nor the native origin. The elements that can be that
// nearest one add their name and state to the exception's data; the crash
// record (App.CaptureFailure) lists it.
internal static class LayoutFailure
{
    internal static void Name(Exception error, FrameworkElement element, object? state = null)
    {
        try
        {
            var text = element.GetType().Name;
            var id = AutomationProperties.GetAutomationId(element);
            if (id.Length > 0) text += " #" + id;
            if (state != null) text += " " + System.Text.Json.JsonSerializer.Serialize(state);
            error.Data["relic.layout." + error.Data.Count] = text;
        }
        catch (Exception) { /* Evidence must not replace the original failure. */ }
    }
}
