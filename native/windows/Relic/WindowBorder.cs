using System.Runtime.InteropServices;

namespace Relic;

// Windows 11 draws a 1 px window border in the accent colour when "Show accent colour on title bars and window
// borders" is on (Settings > Personalisation > Colours). Relic draws its own title bar, so that border is the only
// accent-coloured line around the window, and the person's other apps show none. DWMWA_BORDER_COLOR set to
// DWMWA_COLOR_NONE removes it; the window keeps its shadow and rounded corners. Windows 10 does not know the
// attribute and leaves the window as it was.
public sealed partial class MainWindow
{
    private const int DwmBorderColor = 34;  // DWMWA_BORDER_COLOR, Windows 11 (build 22000) and later
    private const uint DwmColorNone = 0xFFFFFFFE;  // DWMWA_COLOR_NONE

    [DllImport("dwmapi.dll", EntryPoint = "DwmSetWindowAttribute")]
    private static extern int WindowBorderSetAttribute(nint window, int attribute, ref uint value, int size);

    private void RemoveAccentBorder()
    {
        var none = DwmColorNone;
        _ = WindowBorderSetAttribute(WinRT.Interop.WindowNative.GetWindowHandle(this), DwmBorderColor, ref none, sizeof(uint));
    }
}
