namespace Relic;

// Where the window keeps its own view state: native-ui.json (the open chat, read marks, folds, drafts) and
// window.json (size and position). It lives with Relic's data, in RELIC_HOME (default %USERPROFILE%\.relic)\native.
//
// It used to live in %LOCALAPPDATA%\Relic. Windows redirects %LOCALAPPDATA% for a program started from a packaged
// app (MSIX, such as the Claude desktop app and every agent session it runs) into that package's own folder,
// Packages\<package>\LocalCache\Local. So the same person had one view state when an agent opened Relic and another,
// empty one when they opened it from the desktop: every chat looked unread, and the window and folds were reset
// (found on Hongyi's machine on 2026-11-07). RELIC_HOME is not redirected, which is why the organizations always
// matched. The first start of this version copies the most recently written earlier view state it can find, from
// either place, and leaves the earlier files where they were.
internal static class ViewStateHome
{
    private static readonly string[] Files = { "native-ui.json", "window.json" };
    private static readonly Lazy<string> folder = new(Prepare);

    internal static string Folder => folder.Value;

    private static string Prepare()
    {
        var home = Environment.GetEnvironmentVariable("RELIC_HOME") is { Length: > 0 } relicHome
            ? relicHome
            : System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".relic");
        var target = System.IO.Path.Combine(home, "native");
        try
        {
            System.IO.Directory.CreateDirectory(target);
            if (!System.IO.File.Exists(System.IO.Path.Combine(target, Files[0])) && Earlier() is { } source)
                foreach (var name in Files)
                {
                    var from = System.IO.Path.Combine(source, name);
                    var to = System.IO.Path.Combine(target, name);
                    if (System.IO.File.Exists(from) && !System.IO.File.Exists(to)) System.IO.File.Copy(from, to);
                }
        }
        catch (Exception ex) when (ex is System.IO.IOException or UnauthorizedAccessException) { }
        return target;
    }

    // The earlier folder whose native-ui.json was written last: %LOCALAPPDATA%\Relic as this program sees it, or a
    // packaged app's redirected copy of it.
    private static string? Earlier()
    {
        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var candidates = new List<string> { System.IO.Path.Combine(local, "Relic") };
        try
        {
            var packages = System.IO.Path.Combine(local, "Packages");
            if (System.IO.Directory.Exists(packages))
                foreach (var package in System.IO.Directory.EnumerateDirectories(packages))
                    candidates.Add(System.IO.Path.Combine(package, "LocalCache", "Local", "Relic"));
        }
        catch (Exception ex) when (ex is System.IO.IOException or UnauthorizedAccessException) { }
        string? newest = null;
        var newestWrite = DateTime.MinValue;
        foreach (var candidate in candidates)
        {
            try
            {
                var file = System.IO.Path.Combine(candidate, Files[0]);
                if (!System.IO.File.Exists(file)) continue;
                var written = System.IO.File.GetLastWriteTimeUtc(file);
                if (written > newestWrite) { newestWrite = written; newest = candidate; }
            }
            catch (Exception ex) when (ex is System.IO.IOException or UnauthorizedAccessException) { }
        }
        return newest;
    }
}
