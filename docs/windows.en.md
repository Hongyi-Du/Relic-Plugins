# Windows installation

[中文](windows.zh-CN.md) · [User guide](guide.en.md)

## Prerequisites

- Windows with Python 3.11+ on PATH. Check `python --version`.
- Claude Code and/or Codex, installed and signed in (`claude --version`, `codex --version`). The installer adds the plugin to each host whose CLI it finds, including the CLI bundled with the Codex desktop app.
- Node.js (with npm) for members that run inside the Relic App: their ACP adapters are installed from the App's 设置 → Harness 连接 (about 70 MB under `~/.relic/acp`).
- Microsoft Edge (or Chrome) for the App window. Voice input uses Edge's online speech recognition.
- Waking a Codex chat that is open in the Codex desktop app goes through that app's tool pipe; a CLI-only installation does not provide one. ChatGPT chat members need the ChatGPT desktop app running.
- Git is only needed for cloning sources or member worktrees. No Docker or third-party Python package is needed.

## Download and install

Download `relic-windows-v0.3.0-beta.1.zip` from the [release page](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.3.0-beta.1). Compare the archive's `Get-FileHash -Algorithm SHA256` value with `SHA256SUMS.txt` if you want to verify the download.

Extract into a permanent folder such as `C:\Tools\Relic`. Open PowerShell in the extracted folder:

```powershell
python -X utf8 scripts/install.py
# Only into Codex:
python -X utf8 scripts/install.py --host codex
```

| Option | Effect |
| --- | --- |
| `--host auto` | The default: every host whose CLI is found |
| `--host claude`, `--host codex`, `--host both` | Only these hosts; stops with an error if a named host is not installed |
| `--host none` | No host: the Relic App alone |
| `--configure-only` | Prepare this folder without changing any host or making a shortcut |
| `--no-shortcut` | Do not make the Relic shortcut on the desktop |
| `--open` | Open the Relic App when the installation is done |

The optional PowerShell wrapper is `./install.ps1`, with the same options as `-HostTarget`, `-ConfigureOnly`, `-NoShortcut` and `-Open`. If PowerShell's script policy rejects it, use the Python command above; changing global execution policy is unnecessary.

The installer configures the folder for the Python that runs it (the plugin's MCP server and hooks use that interpreter), runs `<cli> plugin marketplace add <folder>` and then `claude plugin install relic@relic-bridge` / `codex plugin add relic@relic-bridge`, disables the earlier Claude Code editions `relic@relic-claude` and `relic@relic-local` (best effort), and makes a desktop shortcut named Relic that opens the Relic App. It leaves the earlier Codex edition (plugin `relic-organization`) alone, because its tools and data are different; remove it in Codex if you no longer use it. It makes no downloads, model calls, global hook trust or database changes.

Start a new host session and review hooks in plugin settings. If Codex reports its hooks feature disabled, enable hooks through the host's supported settings; the installer preserves that choice. Keep the extracted folder.

## Verify and use

```powershell
python scripts/doctor.py
python -X utf8 scripts/open_app.py
```

`doctor.py` reports Python, the Claude Code and Codex CLIs, Node.js, the ACP adapters and the configured MCP server paths. The Relic App runs a local server on 127.0.0.1 (port 39321 or the next free one) and opens a Microsoft Edge (or Chrome) window; the Relic shortcut on the desktop does the same. Click 安装 in its window bar to install it as an application; afterwards `open_app.py` and the shortcut open the installed application.

To run members inside the App, install the ACP adapters under 设置 → Harness 连接 first, then use 添加成员. Those members need only Claude Code or Codex, installed and signed in: the App brings Relic into their sessions.

Ask the agent to report the current Relic state, create a small organization and exchange one message. Confirm the receiver actually reads it. For a strong rule, check one harmless matching and one nonmatching action; installation success alone does not prove hook coverage.

The App's interface currently contains Chinese labels. English and Chinese user documentation is complete; a fully translated English GUI is not included in this beta.

## Common Windows issues

If `python` opens the Microsoft Store, install Python or choose its real executable and use it to run the installer. If `codex` / `claude` is missing, install and sign in to that host first; with `--host auto` the installer skips a host it does not find. If the App reports that npm or Node.js is missing, install Node.js and install the adapters again from 设置 → Harness 连接. If a host update invalidates the desktop pipe, reopen the Codex app. Do not start a second app-server writer against a desktop-owned chat.

See the [user guide](guide.en.md#8-storage-updates-and-removal) for backups, updates and uninstall. The installer does not delete older organization data.
