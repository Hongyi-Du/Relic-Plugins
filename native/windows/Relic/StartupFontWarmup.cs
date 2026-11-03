namespace Relic;

// A TextBlock's first measure builds cold DirectWrite font faces (including
// the fallback CJK face and the "…" trimming sign) on the UI thread; CI stacks
// caught startup there. Do that once at launch on a worker, through the shared
// DirectWrite factory WinUI also uses, so the first layout finds them loaded.
internal static class StartupFontWarmup
{
    private const string Sample = "Relic Aa 0123 … · — 组织成员群聊秘书消息任务协议需要你决定已读";

    internal static void Start()
    {
        var languages = new[] { "zh-CN", System.Globalization.CultureInfo.CurrentUICulture.Name }.Distinct().ToArray();
        _ = Task.Run(() =>
        {
            using var timing = PerformanceTrace.Measure("startup.fonts.worker");
            foreach (var language in languages)
                foreach (var weight in new uint[] { 400, 600, 650, 700 })
                    foreach (var size in new[] { 13f, 12f })
                    {
                        // Normal style (0) and stretch (5), scale 1. A failed warm-up
                        // only leaves the original cold start in place.
                        try { NativeGlyphRasterPreparation.Prepare(new(Sample, FontFamilies.UI, language, size, weight, 0, 5, 1, false), CancellationToken.None).Dispose(); }
                        catch (Exception) { }
                    }
            // Paths, commands and logs use Cascadia Code (settings, workspace,
            // trace); icons use the symbol font. Their first measure was cold too:
            // the settings dialog once spent 800 ms measuring its content.
            foreach (var (family, text) in new[] { ("Cascadia Code", "Relic aA 0123 {}()[]<>/\\:._-~ 组织"),
                ("Segoe Fluent Icons, Segoe MDL2 Assets", "\uE713\uE8BB\uE9D9\uE71A\uE77B\uE81C\uE8B7\uE73A") })
                foreach (var size in new[] { 11.5f, 13f })
                {
                    try { NativeGlyphRasterPreparation.Prepare(new(text, family, languages[0], size, 400, 0, 5, 1, false), CancellationToken.None).Dispose(); }
                    catch (Exception) { }
                }
        });
    }
}
