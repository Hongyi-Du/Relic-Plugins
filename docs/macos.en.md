# macOS installation and beta scope

[中文](macos.zh-CN.md) · [User guide](guide.en.md)

## Prerequisites

Use Python **3.11+** from a maintained Python distribution, with `python3` available in Terminal. The packages contain Python source, not architecture-specific binaries; Apple Silicon and Intel need a compatible Python and host installation. A native desktop session on each architecture has not been certified by this release.

Install and sign in to Claude Code and/or Codex. Ensure `claude --version` / `codex --version` works in the same Terminal. The macOS installer relies on the CLI being on PATH. For the optional Bridge/Codex panel, check `python3 -c 'import tkinter'`; if unavailable, use a Python distribution with Tk support. Core MCP tools do not need a panel.

## Install the archive

Download the selected `relic-{claude,codex,bridge}-macos-v0.1.0-beta.1.tar.gz` from the [release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.1.0-beta.1). For Bridge:

```bash
mkdir -p "$HOME/Applications/Relic"
tar -xzf relic-bridge-macos-v0.1.0-beta.1.tar.gz -C "$HOME/Applications/Relic"
cd "$HOME/Applications/Relic/relic-bridge-macos-v0.1.0-beta.1"
bash install.command
```

Use `shasum -a 256 <archive>` and compare with `SHA256SUMS.txt` to verify the download. The installer uses the actual `python3` executable for both MCP and hooks; a separate `python` alias is unnecessary. Bridge can target only one installed host with `bash install.command --host claude` or `--host codex`.

From a source checkout: `bash install.command --edition bridge`. Running `bash install.command` in Terminal does not require executable permissions on the downloaded launcher. The packages are source distributions, not signed/notarized macOS applications or `.dmg` installers.

Restart the host or open a new session, review hook trust, and enable only one Relic edition per host. Keep the extracted folder in place. Restarting an app opened from Finder may be needed after installing CLI tools or changing your environment.

## What this macOS beta provides

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

## First cross-host trial

Use two Terminal sessions with the same Bridge data directory, for example export `RELIC_HOME="$HOME/.relic"` in both before starting the hosts. In Claude Code create a Relic organization and record its ID. In Codex join that ID under a different member name. Exchange a short message and call `inbox`; verify documents and tasks from both sides before starting a larger task.

Keep CLI-owned sessions separate from chats currently held open for writing by the desktop app. Explicit inbox polling works without Bridge's desktop auto-wake. Turn auto-wake off in the panel if you want fully manual turns.

Diagnostics: `python3 scripts/doctor.py`. Panel: `python3 scripts/open_panel.py` (Bridge/Codex archive). In the repository add `--edition`. For backups, updating the marketplace path, rollback and removal, see the [user guide](guide.en.md#8-storage-updates-and-removal).
