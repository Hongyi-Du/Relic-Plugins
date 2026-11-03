using Windows.UI.ViewManagement;

namespace Relic;

internal interface ITextScaleListener
{
    // Called on a background thread when Windows' text size setting changes.
    void TextScaleChanged();
}

// Windows' text size setting, for every text control in the app. Labels and
// path text each created their own UISettings and subscribed to it: hundreds
// of native objects and event registrations per opened chat. A control whose
// Unloaded never came also stayed alive for good, because a native event
// source holding a managed handler forms a cycle the GC cannot see. One
// settings object and weak listeners do the same work and hold nothing.
internal static class TextScale
{
    private static readonly UISettings settings = new();
    private static readonly List<WeakReference<ITextScaleListener>> listeners = [];
    private static double factor = settings.TextScaleFactor;
    private static int added;

    static TextScale() => settings.TextScaleFactorChanged += Changed;

    internal static double Factor => Volatile.Read(ref factor);

    internal static void Listen(ITextScaleListener listener)
    {
        lock (listeners)
        {
            listeners.Add(new(listener));
            if (++added % 256 == 0) listeners.RemoveAll(entry => !entry.TryGetTarget(out _));
        }
    }

    private static void Changed(UISettings sender, object args)
    {
        Volatile.Write(ref factor, sender.TextScaleFactor);
        var alive = new List<ITextScaleListener>();
        lock (listeners)
        {
            listeners.RemoveAll(entry => !entry.TryGetTarget(out _));
            foreach (var entry in listeners) if (entry.TryGetTarget(out var listener)) alive.Add(listener);
        }
        foreach (var listener in alive) listener.TextScaleChanged();
    }
}
