# CI desktop only. Never change the person's display or launch a settings window.
# -Scale sets the display scale the person may use (150% is common on laptops):
# layout rounding at a fractional scale differs from 100%.
param([ValidateSet(100, 125, 150)][int]$Scale = 100)
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

  // The display scale, as Settings > Display sets it: the per-source DPI
  // scale of DisplayConfig (device info types -3 get and -4 set, relative to
  // the recommended step of 100, 125, 150, ...). Windows started afterwards
  // get the new DPI; no sign-out needed.
  [StructLayout(LayoutKind.Sequential)] struct Luid { public uint Low; public int High; }
  [StructLayout(LayoutKind.Sequential)] struct Header { public int Type; public uint Size; public Luid Adapter; public uint Id; }
  [StructLayout(LayoutKind.Sequential)] struct ScaleGet { public Header Header; public int Min, Current, Max; }
  [StructLayout(LayoutKind.Sequential)] struct ScaleSet { public Header Header; public int Scale; }
  [DllImport("user32.dll")] static extern int GetDisplayConfigBufferSizes(uint flags, out uint paths, out uint modes);
  [DllImport("user32.dll")] static extern int QueryDisplayConfig(uint flags, ref uint paths, byte[] pathArray, ref uint modes, byte[] modeArray, IntPtr topology);
  [DllImport("user32.dll")] static extern int DisplayConfigGetDeviceInfo(ref ScaleGet packet);
  [DllImport("user32.dll")] static extern int DisplayConfigSetDeviceInfo(ref ScaleSet packet);
  static readonly int[] Steps = { 100, 125, 150, 175, 200, 225, 250, 300, 350, 400, 450, 500 };
  public static string Scale(int percent) {
    const uint ActivePaths = 2; const int PathBytes = 72, ModeBytes = 64;
    uint pathCount, modeCount;
    if (GetDisplayConfigBufferSizes(ActivePaths, out pathCount, out modeCount) != 0) throw new Exception("Cannot size the display configuration");
    var paths = new byte[pathCount * PathBytes]; var modes = new byte[modeCount * ModeBytes];
    if (QueryDisplayConfig(ActivePaths, ref pathCount, paths, ref modeCount, modes, IntPtr.Zero) != 0) throw new Exception("Cannot query the display configuration");
    var report = "";
    for (int i = 0; i < pathCount; i++) {
      var adapter = new Luid { Low = BitConverter.ToUInt32(paths, i * PathBytes), High = BitConverter.ToInt32(paths, i * PathBytes + 4) };
      uint source = BitConverter.ToUInt32(paths, i * PathBytes + 8);
      var get = new ScaleGet { Header = new Header { Type = -3, Size = (uint)Marshal.SizeOf<ScaleGet>(), Adapter = adapter, Id = source } };
      if (DisplayConfigGetDeviceInfo(ref get) != 0) throw new Exception("Cannot read the display scale");
      int recommended = -get.Min, target = Array.IndexOf(Steps, percent) - recommended;
      if (target < get.Min || target > get.Max)
        throw new Exception(string.Format("{0}% is outside this display's {1}%..{2}%", percent, Steps[recommended + get.Min], Steps[recommended + get.Max]));
      var set = new ScaleSet { Header = new Header { Type = -4, Size = (uint)Marshal.SizeOf<ScaleSet>(), Adapter = adapter, Id = source }, Scale = target };
      if (DisplayConfigSetDeviceInfo(ref set) != 0) throw new Exception("Cannot set the display scale to " + percent + "%");
      if (DisplayConfigGetDeviceInfo(ref get) != 0 || get.Current != target) throw new Exception("The display scale did not change to " + percent + "%");
      report += string.Format("source {0}: {1}% (recommended {2}%)", source, percent, Steps[recommended]);
    }
    return report;
  }
}
'@
[VisualDisplay]::Prepare()
if ($Scale -ne 100) { "CI display scale: " + [VisualDisplay]::Scale($Scale) }
