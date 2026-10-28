# macOS development draft — not released

**No macOS download is currently published.** The current public beta is Windows-only. CI builds the macOS package (`relic-macos-v<version>.tar.gz`), but it is not released. macOS development and documentation are retained for future testing on a real Mac; CI passes do not replace signed-in desktop acceptance.

[中文](macos.zh-CN.md) · [User guide](guide.en.md)

## Prerequisites

Use Python **3.11+** from a maintained Python distribution, with `python3` available in Terminal. The package contains Python source, not architecture-specific binaries; Apple Silicon and Intel need a compatible Python and host installation. A native desktop session on each architecture has not been certified by this release.

Install and sign in to Claude Code and/or Codex. Ensure `claude --version` / `codex --version` works in the same Terminal. The macOS installer, `bash install.command`, runs `scripts/install.py` with `python3` and takes the same options; it relies on the CLIs being on PATH. Members that run inside the Relic App also need Node.js for their ACP adapters.

## Release status

Installation instructions and downloadable packages will be finalized after real Mac validation. No public installation is requested at this stage.

## Development state (unreleased)

| Feature | Availability |
| --- | --- |
| Relic tools and hooks in Claude Code and Codex CLI sessions: organizations, messages, documents, tasks, governance | Included; host hooks must be loaded; members share local `RELIC_HOME` |
| Relic App | Source included; opens in the default browser unless `msedge` or `chrome` is on PATH; not tested on a Mac |
| Members that run inside the App (ACP adapters) | Source included; needs Node.js; not tested on a Mac |
| Desktop shortcut | Windows only; open the App with `python3 -X utf8 scripts/open_app.py` |
| Wake-up of a Codex desktop-owned chat | Unavailable: current transport validates Windows named pipes |
| ChatGPT chat members | Unavailable on macOS |
| Open session on a member's card | Not certified; resume the member in Terminal yourself |

There is no claim of Windows/macOS desktop feature parity. Automated tests verify portable code and fixtures, not a signed-in commercial desktop app. The exact run evidence is in [validation](validation.md).

## Future real-Mac validation

Use two Terminal sessions with the same Relic data directory, for example export `RELIC_HOME="$HOME/.relic"` in both before starting the hosts. In Claude Code create a Relic organization and record its ID. In Codex join that ID under a different member name. Exchange a short message and call `inbox`; verify documents and tasks from both sides before starting a larger task.

Keep CLI-owned sessions separate from chats currently held open for writing by the desktop app. Explicit inbox polling works without desktop auto-wake. Turn auto-wake off with the Auto-wake switch in the App's Overview pane if you want fully manual turns.

Diagnostics: `python3 scripts/doctor.py`. The App: `python3 -X utf8 scripts/open_app.py`. For backups, updating the marketplace path, rollback and removal, see the [user guide](guide.en.md#9-storage-updates-and-removal).
