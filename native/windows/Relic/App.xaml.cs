using Microsoft.UI.Xaml;

namespace Relic;
public partial class App : Application
{
    private MainWindow? window;
    public App()
    {
        // Preserve the real failure on CI rather than letting a stowed WinRT
        // exception leave only an exit code. This never handles the exception
        // or changes the app's normal crash behavior.
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
        if (Environment.GetEnvironmentVariable("GITHUB_ACTIONS") != "true") return;
        var manifest = Environment.GetEnvironmentVariable("RELIC_VISUAL_MANIFEST")
            ?? Environment.GetEnvironmentVariable("RELIC_PERF_MANIFEST");
        if (string.IsNullOrEmpty(manifest)) return;
        try
        {
            var directory = System.IO.Path.GetDirectoryName(manifest)!;
            var sceneFile = System.IO.Path.Combine(directory, "current-case.txt");
            System.IO.File.AppendAllText(System.IO.Path.Combine(directory, "app-unhandled.jsonl"), System.Text.Json.JsonSerializer.Serialize(new
            {
                source, message, exception = error?.ToString(), hresult = error?.HResult,
                // What the exception carries beyond its stack: the element whose
                // layout failed (LayoutFailure) and any WinRT error details.
                data = error?.Data.Count > 0 ? error.Data.Cast<System.Collections.DictionaryEntry>()
                    .ToDictionary(entry => entry.Key.ToString() ?? "", entry => entry.Value?.ToString()) : null,
                scene = System.IO.File.Exists(sceneFile) ? System.IO.File.ReadAllText(sceneFile) : null,
                time = DateTimeOffset.UtcNow.ToString("O")
            }) + Environment.NewLine);
        }
        catch (Exception) { /* Crash diagnostics must not replace the original exception. */ }
    }
    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        StartupFontWarmup.Start();
        StartupPrefetch.Start();
        window = new MainWindow(); window.Activate();
    }
}
