using System.Runtime.InteropServices;

namespace Relic;

// Observe only the Precision Touchpad HID collection. XAML's independent input
// processing can consume a touchpad pan without a routed PointerWheelChanged.
// This observer neither handles input nor reads/stores the HID report content.
internal sealed class NativeTouchpadInput : IDisposable
{
    private const ushort Digitizer = 0x0d, Touchpad = 0x05;
    private const uint RawInput = 0x00ff, Destroy = 0x0082, ReadHeader = 0x10000005;
    private const uint DeviceInfo = 0x2000000b, Remove = 1, PageOnly = 0x20;
    private const nuint SubclassId = 0x524c5450;
    private readonly nint window;
    private readonly Action input;
    private readonly Action observationLost;
    private readonly Subclass callback;
    private readonly Dictionary<nint, bool> devices = [];
    private bool attached, registered, disposed, available;
    internal bool IsAvailable
    {
        get
        {
            if (!available) return false;
            // Do not infer absence of input after another component takes over
            // this process-wide registration while the window remains open.
            if (!Registrations(out var existing) || !existing.Any(device =>
                device.Page == Digitizer && device.Usage == Touchpad && device.Window == window))
                available = false;
            return available;
        }
    }

    internal NativeTouchpadInput(nint window, Action input, Action observationLost)
    {
        this.window = window; this.input = input; this.observationLost = observationLost; callback = OnMessage;
        // Registration is process-wide per collection. Never displace another
        // consumer (including a page-wide registration owned by the platform).
        if (!Registrations(out var existing) || existing.Any(CoversTouchpad)) return;
        if (!SetWindowSubclass(window, callback, SubclassId, 0)) return;
        attached = true;
        var device = new RawDevice { Page = Digitizer, Usage = Touchpad, Window = window };
        if (!RegisterRawInputDevices([device], 1, (uint)Marshal.SizeOf<RawDevice>()))
        { RemoveWindowSubclass(window, callback, SubclassId); attached = false; return; }
        registered = true; available = true;
    }

    private static bool CoversTouchpad(RawDevice device) => device.Page == Digitizer
        && (device.Usage == Touchpad || device.Usage == 0 && (device.Flags & PageOnly) != 0);

    private static bool Registrations(out RawDevice[] devices)
    {
        devices = []; uint count = 0;
        var size = (uint)Marshal.SizeOf<RawDevice>();
        if (GetRegisteredRawInputDevices(null, ref count, size) == uint.MaxValue) return false;
        if (count == 0) return true;
        devices = new RawDevice[count];
        var read = GetRegisteredRawInputDevices(devices, ref count, size);
        if (read == uint.MaxValue) { devices = []; return false; }
        if (read != devices.Length) Array.Resize(ref devices, (int)read);
        return true;
    }

    private nint OnMessage(nint handle, uint message, nuint wparam, nint lparam, nuint id, nuint data)
    {
        if (message == RawInput && available)
        {
            try
            {
                var size = (uint)Marshal.SizeOf<RawHeader>();
                if (GetRawInputData(lparam, ReadHeader, out var header, ref size,
                    (uint)Marshal.SizeOf<RawHeader>()) != Marshal.SizeOf<RawHeader>()) LoseObservation();
                else if (IsTouchpad(header)) input();
            }
            catch
            {
                // Never let an unmanaged callback unwind, or treat an input
                // we could not observe as evidence that no user input exists.
                LoseObservation();
            }
        }
        if (message == Destroy) Dispose();
        return DefSubclassProc(handle, message, wparam, lparam);
    }

    private bool IsTouchpad(RawHeader header)
    {
        // Windows documents that a Precision Touchpad's raw input can carry a
        // null device handle. It must not be discarded as an invalid device.
        if (header.Device == 0) return true;
        if (header.Type != 2) return false; // Other registered mouse/key inputs.
        if (devices.TryGetValue(header.Device, out var touchpad)) return touchpad;
        var info = new RawDeviceInfo { Size = (uint)Marshal.SizeOf<RawDeviceInfo>() };
        var size = info.Size;
        var read = GetRawInputDeviceInfo(header.Device, DeviceInfo, ref info, ref size);
        if (read == uint.MaxValue || read < 24)
        { LoseObservation(); return false; }
        touchpad = info.Type == 2 && info.Page == Digitizer && info.Usage == Touchpad;
        if (devices.Count >= 32) devices.Clear();
        devices[header.Device] = touchpad;
        return touchpad;
    }

    private void LoseObservation()
    {
        if (!available) return;
        available = false;
        observationLost();
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true; available = false;
        // Another component may have since registered this collection. Remove
        // only our own still-current registration, never the new consumer's.
        if (registered && Registrations(out var existing) && existing.Any(device =>
            device.Page == Digitizer && device.Usage == Touchpad && device.Window == window))
        {
            RegisterRawInputDevices([new RawDevice { Page = Digitizer, Usage = Touchpad, Flags = Remove }],
                1, (uint)Marshal.SizeOf<RawDevice>());
        }
        registered = false;
        if (attached) RemoveWindowSubclass(window, callback, SubclassId);
        attached = false;
    }

    internal Windows.Foundation.Point? PointerClientPosition()
    {
        if (!GetCursorPos(out var point) || !ScreenToClient(window, ref point)) return null;
        return new(point.X, point.Y);
    }

    [StructLayout(LayoutKind.Sequential)] private struct RawDevice
    { internal ushort Page, Usage; internal uint Flags; internal nint Window; }
    [StructLayout(LayoutKind.Sequential)] private struct RawHeader
    { internal uint Type, Size; internal nint Device; internal nuint Wparam; }
    [StructLayout(LayoutKind.Sequential)] private struct CursorPoint { internal int X, Y; }
    [StructLayout(LayoutKind.Explicit, Size = 32)] private struct RawDeviceInfo
    {
        [FieldOffset(0)] internal uint Size;
        [FieldOffset(4)] internal uint Type;
        [FieldOffset(20)] internal ushort Page;
        [FieldOffset(22)] internal ushort Usage;
    }
    private delegate nint Subclass(nint window, uint message, nuint wparam, nint lparam, nuint id, nuint data);
    [DllImport("comctl32.dll")] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetWindowSubclass(nint window, Subclass callback, nuint id, nuint data);
    [DllImport("comctl32.dll")] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool RemoveWindowSubclass(nint window, Subclass callback, nuint id);
    [DllImport("comctl32.dll")] private static extern nint DefSubclassProc(nint window, uint message, nuint wparam, nint lparam);
    [DllImport("user32.dll")] private static extern uint GetRegisteredRawInputDevices([Out] RawDevice[]? devices, ref uint count, uint size);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool RegisterRawInputDevices([In] RawDevice[] devices, uint count, uint size);
    [DllImport("user32.dll")] private static extern uint GetRawInputData(nint raw, uint command, out RawHeader header, ref uint size, uint headerSize);
    [DllImport("user32.dll", EntryPoint = "GetRawInputDeviceInfoW")]
    private static extern uint GetRawInputDeviceInfo(nint device, uint command, ref RawDeviceInfo info, ref uint size);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetCursorPos(out CursorPoint point);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ScreenToClient(nint window, ref CursorPoint point);
}
