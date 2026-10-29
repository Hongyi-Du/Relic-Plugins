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
        UnhandledException += (_, args) => CaptureFailure("Xaml.UnhandledException", args.Exception, args.Message);
        AppDomain.CurrentDomain.UnhandledException += (_, args) => CaptureFailure("AppDomain.UnhandledException", args.ExceptionObject as Exception, args.ExceptionObject?.ToString());
        InitializeComponent();
    }
    private static void CaptureFailure(string source, Exception? error, string? message)
    {
        if (Environment.GetEnvironmentVariable("GITHUB_ACTIONS") != "true" || Environment.GetEnvironmentVariable("RELIC_VISUAL_MANIFEST") is not { Length: > 0 } manifest) return;
        try
        {
            var directory = System.IO.Path.GetDirectoryName(manifest)!;
            var sceneFile = System.IO.Path.Combine(directory, "current-case.txt");
            System.IO.File.AppendAllText(System.IO.Path.Combine(directory, "app-unhandled.jsonl"), System.Text.Json.JsonSerializer.Serialize(new
            {
                source, message, exception = error?.ToString(), hresult = error?.HResult,
                scene = System.IO.File.Exists(sceneFile) ? System.IO.File.ReadAllText(sceneFile) : null,
                time = DateTimeOffset.UtcNow.ToString("O")
            }) + Environment.NewLine);
        }
        catch (Exception) { /* Crash diagnostics must not replace the original exception. */ }
    }
    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        window = new MainWindow(); window.Activate();
    }
}
