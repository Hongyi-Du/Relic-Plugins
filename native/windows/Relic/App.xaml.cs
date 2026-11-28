using Microsoft.UI.Xaml;

namespace Relic;
public partial class App : Application
{
    private MainWindow? window;
    public App()
    {
        // Preserve the real failure rather than letting a stowed WinRT exception
        // leave only an exit code. This never handles the exception or changes
        // the app's normal crash behavior.
        // A refresh starts several reads at once and parses each off the UI
        // thread. Above the pool's minimum, extra workers start only after a delay
        // and retire after 20 s idle, so bursts waited and the thread count kept
        // rising and falling. Keep enough workers for those bursts.
        ThreadPool.GetMinThreads(out var workers, out var completion);
        ThreadPool.SetMinThreads(Math.Max(workers, 12), completion);
        UnhandledException += (_, args) => CaptureFailure("Xaml.UnhandledException", args.Exception, args.Message);
        AppDomain.CurrentDomain.UnhandledException += (_, args) => CaptureFailure("AppDomain.UnhandledException", args.ExceptionObject as Exception, args.ExceptionObject?.ToString());
        InitializeComponent();
    }
    private static void CaptureFailure(string source, Exception? error, string? message)
    {
        try
        {
            var ci = Environment.GetEnvironmentVariable("GITHUB_ACTIONS") == "true";
            var manifest = Environment.GetEnvironmentVariable("RELIC_VISUAL_MANIFEST")
                ?? Environment.GetEnvironmentVariable("RELIC_PERF_MANIFEST");
            if (ci && string.IsNullOrEmpty(manifest)) return;
            var directory = ci ? System.IO.Path.GetDirectoryName(manifest)! : null;
            var sceneFile = directory == null ? null : System.IO.Path.Combine(directory, "current-case.txt");
            var record = System.Text.Json.JsonSerializer.Serialize(new
            {
                source, message, exception = error?.ToString(), hresult = error?.HResult,
                // What the exception carries beyond its stack: the element whose
                // layout failed (LayoutFailure) and any WinRT error details.
                data = error?.Data.Count > 0 ? error.Data.Cast<System.Collections.DictionaryEntry>()
                    .ToDictionary(entry => entry.Key.ToString() ?? "", entry => entry.Value?.ToString()) : null,
                scene = sceneFile != null && System.IO.File.Exists(sceneFile) ? System.IO.File.ReadAllText(sceneFile) : null,
                // A layout cycle ends the app right after this event, even when
                // handled, and its stack does not say which code kept changing
                // layout. This names what did, most recent last.
                layout_feedback = LayoutFeedback.Snapshot(),
                time = DateTimeOffset.UtcNow.ToString("O")
            }) + Environment.NewLine;
            if (directory != null)
            {
                System.IO.File.AppendAllText(System.IO.Path.Combine(directory, "app-unhandled.jsonl"), record);
                return;
            }
            // On the person's computer: one small file per failure, the newest
            // twenty kept. Numbers and code roles, no message text.
            var folder = System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Relic", "crashes");
            System.IO.Directory.CreateDirectory(folder);
            System.IO.File.WriteAllText(System.IO.Path.Combine(folder, $"crash-{DateTime.Now:yyyyMMdd-HHmmss-fff}.json"), record);
            foreach (var old in new System.IO.DirectoryInfo(folder).GetFiles("crash-*.json").OrderByDescending(file => file.Name).Skip(20))
                old.Delete();
        }
        catch (Exception) { /* Crash diagnostics must not replace the original exception. */ }
    }
    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        // Diagnosis of a layout that never settles: WinUI then writes each pass
        // and every element whose size kept changing to the debug output.
        if (Environment.GetEnvironmentVariable("RELIC_LAYOUT_CYCLE_TRACING") == "1")
            DebugSettings.LayoutCycleTracingLevel = LayoutCycleTracingLevel.High;
        StartupFontWarmup.Start();
        StartupPrefetch.Start();
        window = new MainWindow(); window.Activate();
    }
}
