namespace Relic;

// A real completion can be a canceled/offscreen request and cause no XAML
// layout. Consumers schedule their own UI work and recheck all pending counts;
// this notification is not permission to paint unfinished content.
internal static class PresentationPreparation
{
    internal static event Action? Completed;
    internal static void NotifyCompletion() => Completed?.Invoke();
}
