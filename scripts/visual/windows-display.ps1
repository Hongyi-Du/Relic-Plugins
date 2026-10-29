# CI desktop only. Never change the person's display or launch a settings window.
if ($env:GITHUB_ACTIONS -ne 'true') { throw 'Display setup is restricted to GitHub Actions.' }
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class VisualDisplay {
  [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
  public struct Mode {
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)] public string device;
    public ushort spec, driver, size, extra; public uint fields;
    public int x,y; public uint orientation, fixedOutput;
    public short color, duplex, yResolution, tt, collate;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)] public string form;
    public ushort logPixels; public uint bits, width, height, flags, frequency, icmMethod, icmIntent, media, dither, reserved1, reserved2, panningWidth, panningHeight;
  }
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern bool EnumDisplaySettings(string name, int mode, ref Mode result);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int ChangeDisplaySettingsEx(string name, ref Mode mode, IntPtr window, uint flags, IntPtr parameters);
  public static string Prepare() {
    var mode = new Mode { size=(ushort)Marshal.SizeOf<Mode>() };
    if (!EnumDisplaySettings(null, -1, ref mode)) throw new Exception("Cannot query CI display mode");
    mode.width=1920; mode.height=1080; mode.fields=0x180000;
    int result=ChangeDisplaySettingsEx(null, ref mode, IntPtr.Zero, 0, IntPtr.Zero);
    if (result!=0) throw new Exception("Cannot set CI desktop to 1920x1080: " + result);
    return "CI desktop: 1920x1080";
  }
}
'@
[VisualDisplay]::Prepare()
