using Microsoft.UI.Xaml.Controls;
using Relic.Core;

namespace Relic;

// Codex pins its approval of a plugin's hooks to a fingerprint of the plugin's whole folder, so after every Relic
// upgrade it skips Relic's hooks, silently, until the person approves them again with /hooks in Codex. Until then
// Codex members get no messages between their own Relic calls and strict protocols are not enforced on them. The
// engine compares Codex's approvals with the installed plugin (relic_core/codex_trust.py) and reports the result in
// /api/platform as codex_hooks.state; this bar says what to do. Relic never approves the hooks itself.
public sealed partial class MainWindow
{
    private readonly InfoBar codexHooksNotice = new() { Severity = InfoBarSeverity.Warning, IsClosable = true, IsOpen = false };

    private void ShowCodexHooksNotice()
    {
        var hooks = platform["codex_hooks"];
        var state = hooks.Text("state");
        if (state is not ("changed" or "untrusted")) { codexHooksNotice.IsOpen = false; return; }
        (string, object) plugin = ("plugin", hooks.Text("plugin"));
        codexHooksNotice.Title = T("health.codex_hooks.title");
        codexHooksNotice.Message = state == "changed" ? T("health.codex_hooks.changed", plugin) : T("health.codex_hooks.untrusted", plugin);
        codexHooksNotice.IsOpen = true;
    }
}
