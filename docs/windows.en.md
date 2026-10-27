# Windows installation

[中文](windows.zh-CN.md) · [User guide](guide.en.md)

## Prerequisites

- Windows with Python 3.11+ on PATH. Check `python --version`. A standard Python installation includes Tk; check `python -c "import tkinter"` if you want the panel.
- Claude edition: a signed-in Claude Code CLI (`claude --version`). Codex edition: a signed-in Codex CLI (`codex --version`) with plugin commands. Bridge uses both unless you choose one host.
- The Codex desktop transport requires the desktop app and its bundled `codex-app-tools`; a CLI-only installation does not provide a desktop pipe. The desktop app's bundled CLI is discovered by the installer on Windows.
- Git is only needed for cloning sources or member worktrees. No Docker or third-party Python package is needed for the core organization.

## Download and install

Download `relic-claude-windows-v0.2.0-beta.1.zip`, `relic-codex-windows-v0.2.0-beta.1.zip`, or `relic-bridge-windows-v0.2.0-beta.1.zip` from the [release page](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.2.0-beta.1). Compare the archive's `Get-FileHash -Algorithm SHA256` value with `SHA256SUMS.txt` if you want to verify the download.

Extract into a permanent folder such as `C:\Tools\Relic\bridge`. Open PowerShell in the extracted folder:

```powershell
python -X utf8 scripts/install.py
# Bridge, when only Codex is installed:
python -X utf8 scripts/install.py --host codex
```

The optional PowerShell wrapper is `./install.ps1`. If PowerShell's script policy rejects it, use the Python command above; changing global execution policy is unnecessary. From a source checkout use `python scripts/install.py --edition bridge` (or `claude` / `codex`).

Start a new host session and review hooks in plugin settings. If Codex reports its hooks feature disabled, enable hooks through the host's supported settings; the installer preserves that choice. Disable another Relic edition in the same host to avoid duplicate hooks. Keep the extracted source directory.

## Verify and use

```powershell
python scripts/doctor.py
# Bridge archive only: the Relic App (desktop chat)
python scripts/open_app.py
# Bridge or Codex archive only: the Tk panel
python scripts/open_panel.py
```

The Relic App runs a local server on 127.0.0.1 and opens a Microsoft Edge (or Chrome) window. Click 安装 in its window bar to install it as an application; afterwards `open_app.py` opens the installed application. Its interface is in Chinese.

In a source checkout those commands also need `--edition bridge` or `--edition codex`. For the Codex panel, invoke `org_panel` from a real desktop chat first to capture its current host context. Claude-only has no standalone panel; use `/relic:relic` or a natural-language request in Claude Code.

Ask the agent to report the current Relic state, create a small organization and exchange one message. Confirm the receiver actually reads it. For a strong rule, check one harmless matching and one nonmatching action; installation success alone does not prove hook coverage.

The window interface currently contains Chinese labels. English and Chinese user documentation is complete; a fully translated English GUI is not included in this beta.

## Common Windows issues

If `python` opens the Microsoft Store, install Python or choose its real executable and use it to run the installer. If `codex` / `claude` is missing, install and sign in to that host first. If a host update invalidates the desktop pipe, reopen the app and call the panel from a live Codex chat. Do not start a second app-server writer against a desktop-owned chat.

See the [user guide](guide.en.md#8-storage-updates-and-removal) for backups, updates and uninstall. The installer does not delete older organization data.
