# macOS development draft — not released

**No macOS download is currently published.** The current public beta is Windows-only. macOS development and documentation are retained for future testing on a real Mac; CI passes do not replace signed-in desktop acceptance.

[中文](macos.zh-CN.md) · [User guide](guide.en.md)

## Prerequisites

Use Python **3.11+** from a maintained Python distribution, with `python3` available in Terminal. The packages contain Python source, not architecture-specific binaries; Apple Silicon and Intel need a compatible Python and host installation. A native desktop session on each architecture has not been certified by this release.

Install and sign in to Claude Code and/or Codex. Ensure `claude --version` / `codex --version` works in the same Terminal. The macOS installer relies on the CLI being on PATH. For the optional Bridge/Codex panel, check `python3 -c 'import tkinter'`; if unavailable, use a Python distribution with Tk support. Core MCP tools do not need a panel.

## Release status

Installation instructions and downloadable packages will be finalized after real Mac validation. No public installation is requested at this stage.

## Development state (unreleased)

| Feature | Availability |
| --- | --- |
| Claude Code core organization, messages, documents, tasks, governance | Included; host hooks must be loaded |
| Bridge shared store and Claude Code + Codex CLI members | Included; members share local `RELIC_HOME` |
| Codex native subagent organizations | Included when the host exposes native collaboration and identity metadata |
| Optional Tk panels | Source included; requires Tk/display; complete real-host GUI workflow not certified |
| Codex edition's direct desktop transport | Uses installed host app-tools; real macOS desktop integration not certified |
| Bridge wake-up of a Codex desktop-owned chat | Unavailable: current transport validates Windows named pipes |
| Bridge ChatGPT chat relay | Unavailable on macOS |
| Bridge “open CLI session” convenience button | Not certified; resume the member in Terminal yourself |

There is no claim of Windows/macOS desktop feature parity. Automated tests verify portable code and fixtures, not a signed-in commercial desktop app. The exact run evidence is in [validation](validation.md).

## Future real-Mac validation

Use two Terminal sessions with the same Bridge data directory, for example export `RELIC_HOME="$HOME/.relic"` in both before starting the hosts. In Claude Code create a Relic organization and record its ID. In Codex join that ID under a different member name. Exchange a short message and call `inbox`; verify documents and tasks from both sides before starting a larger task.

Keep CLI-owned sessions separate from chats currently held open for writing by the desktop app. Explicit inbox polling works without Bridge's desktop auto-wake. Turn auto-wake off in the panel if you want fully manual turns.

Diagnostics: `python3 scripts/doctor.py`. Panel: `python3 scripts/open_panel.py` (Bridge/Codex archive). In the repository add `--edition`. For backups, updating the marketplace path, rollback and removal, see the [user guide](guide.en.md#8-storage-updates-and-removal).
