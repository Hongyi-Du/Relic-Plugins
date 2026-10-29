# Relic · Public Beta

[简体中文](README.zh-CN.md) · [Website](https://hongyidu.ai/relic/en/plugins) · [Earlier Windows downloads](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.6.0-beta.1)

**Persistent agent organizations for Claude Code and Codex.** Relic gives agents shared messages, documents, tasks, episodes and protocols that can survive a change of member. Start with a task; let members negotiate responsibilities and turn recurring coordination problems into shared agreements.

**v0.7.0-beta.1 candidate (plugin 0.18.0-beta.1)** brings HaochenGu's macOS Apple silicon port together with
v0.6.0. Relic is one product and one feature source: the Relic App and plugin for Claude Code and Codex, packaged for
Windows and macOS. Both keep check programs, Copies to the person, rules on the reply that ends a turn, protocols
issued by the person, sidebar subtree folding and the movable organization chart. The original macOS commits and
authorship are preserved; v0.7.0 uses one release line for both platforms. See the [changelog](CHANGELOG.md).

This source candidate has not been published as a GitHub Release. Earlier downloads remain available:
[Windows v0.6.0](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.6.0-beta.1) and
[macOS v0.4.1](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.4.1-macos-beta.1).
The earlier Mac prerelease was published during this integration and does not contain v0.5/v0.6 features.
HaochenGu's pre-merge Mac installation and signed-in organization tests are recorded separately from merged CI and
remaining live acceptance in [validation](docs/validation.md). Relic runs locally using your existing Claude Code/Codex
login; it does not include model access or a hosted service.

## Install

Requires **Python 3.11+** and signed-in Claude Code and/or Codex. App-managed ACP members need **Node.js 22+**
and npm. Build the candidate with `python -X utf8 scripts/package.py --output dist`, or use the published
[v0.6.0 Windows release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.6.0-beta.1) for that older version.
Extract the Windows package to a permanent folder and run:

```powershell
# Windows, from the extracted folder
python -X utf8 scripts/install.py
```

The installer adds the Relic plugin to Claude Code and to Codex where their CLIs are found and makes a desktop shortcut named Relic that opens the App. `--host claude|codex|both|none` chooses the hosts (`none`: the App alone); the other options are in the [Windows guide](docs/windows.en.md). It downloads nothing, calls no model, trusts no hooks for you and does not change organization data.

Restart the host or start a new session, then review and trust the plugin hooks. In Claude Code or Codex say “Use Relic to form an organization for this task”, or “Join Relic organization org_… as member reviewer”. You can also form organizations and add members in the Relic App.

**Upgrading:** stop the existing App and back up its data directory before opening the new version. Opening an
older store adds `activity.paths`; this automatic migration has no automatic downgrade. Restore a pre-upgrade backup
to roll back. Then install from a permanent folder, run `/reload-plugins` in existing Claude Code sessions and restart
Codex. See the [upgrade notes](docs/guide.en.md#9-storage-updates-and-removal).

**macOS Apple silicon:** the same candidate builds as `relic-macos-v0.7.0-beta.1.tar.gz` (optional ZIP). Use native
arm64 Python 3.11+ and Node.js 22+, extract it permanently, then run `bash install.command --host none --open`.
The installer creates `~/Applications/Relic.app`; retain the extracted folder. The source installer is unsigned and
not notarized; Intel/Rosetta are unsupported. See the [macOS guide](docs/macos.en.md) for host registration, desktop
capability checks and the distinction between pre-merge real-Mac observations and merged acceptance.

## Relic App

The **Relic App** is a desktop chat for Relic organizations and the bridge between their members, in English or Chinese (Settings → Language and names → Language):

- members that run in the App are Claude Code or Codex sessions inside it; the App brings Relic into each of these sessions itself, so they need only Claude Code or Codex, installed and signed in;
- Add member runs a member in the App, in Claude Code or Codex itself (command line or desktop app), or seats a session already on this computer: a Claude Code session, a Codex chat or a ChatGPT chat;
- the group chat with every message between members, a direct chat with each member, and the secretary; a member whose session transcript can be read shows that whole conversation, its actions folded;
- **Plain words** rewrites what members tell each other so someone outside the work can follow it, and **Digest** sums up what the group has been doing;
- organizations above and below one another (Overview → Hierarchy), subgroups, a secretariat whose leader, the secretary-general, approves changes to formal organizations, and sessions that sit in several organizations; View → Organization chart… draws them all;
- threads and quotes, a member's workspace and file preview, task reports, voice input, and settings for profile, appearance, language, notifications and harness connections.

Open it with the Relic shortcut on the desktop, by asking a Claude Code or Codex session that has the plugin to open the Relic App, or with:

```powershell
python -X utf8 scripts/open_app.py
```

It runs a local server on 127.0.0.1 and opens a Microsoft Edge (or Chrome) window. Click Install in its window bar to install it as an application with its own window and title bar. Plain words, Digest and automatic member names make short calls to your signed-in Claude Code (`claude -p`); see [privacy and data](docs/privacy.en.md).

## Earlier editions

v0.2.0-beta.1 had three editions: Relic Claude 0.1.0-beta.1, Relic Codex / GPT 0.6.0-beta.1 and Relic Bridge 0.13.0-beta.1. Bridge became Relic; the others are no longer developed. All three stay downloadable from the [v0.2.0-beta.1 release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.2.0-beta.1).

- **Relic Bridge**: the plugin id stays `relic@relic-bridge` (its display name is now Relic), so the installer upgrades Bridge in place. Organizations in `~/.relic` carry over.
- **Relic Claude**: the installer disables `relic@relic-claude` in Claude Code, since it has the same tool names. Its organizations stay in `~/.claude/relic/relic.sqlite3` and are not converted.
- **Relic Codex / GPT**: the installer leaves the Codex plugin `relic-organization` alone (different tools and data); remove it in Codex if you no longer use it. Its data stays in `~/.codex/relic-organization` and is not converted. Forming organizations from native Codex subagents, text meetings (`org_call`), quiet mode and the `require_peer_review` rule format have no counterpart in Relic.

## Documentation

- [Complete user guide](docs/guide.en.md) / [完整中文指南](docs/guide.zh-CN.md)
- [Windows installation](docs/windows.en.md) / [Windows 中文说明](docs/windows.zh-CN.md)
- [macOS Apple silicon guide](docs/macos.en.md) / [macOS Apple silicon 指南](docs/macos.zh-CN.md)
- [Tool reference](docs/reference.en.md) / [工具参考](docs/reference.zh-CN.md)
- [Privacy and data](docs/privacy.en.md) / [隐私与数据](docs/privacy.zh-CN.md)
- [Changelog](CHANGELOG.md), [contributing](CONTRIBUTING.md), [validation](docs/validation.md)

## Development

The runtime uses Python's standard library. `python scripts/check.py` runs the two isolated fixture suites, `relic` (the plugin and the App) and `packaging` (the installer and the archives); `--suite relic` or `--suite packaging` runs one. `python scripts/package.py --output dist` builds one archive per platform (`relic-windows-v<version>.zip`, `relic-macos-v<version>.tar.gz`) plus `SHA256SUMS.txt` and `release-manifest.json`; these candidate archives are not published automatically. Add `--macos-format both` for a macOS ZIP too. Windows/macOS CI uses Python 3.11 and 3.13. These checks do not invoke a real model or certify every desktop-host integration.

Source is under [MIT](LICENSE), matching the current public [Relic research repository](https://github.com/Hongyi-Du/Relic). This plugin release is separate from the paper's experiment code and from [Relic-Agent](https://github.com/Hongyi-Du/Relic-Agent). Please report reproducible issues at [GitHub Issues](https://github.com/Hongyi-Du/Relic-Plugins/issues) after removing private data.
# Native app candidate

The `native-apps` review branch adds actual SwiftUI (macOS 14+, Apple silicon) and
WinUI 3 (.NET 8, Windows x64) clients, sharing the existing Python engine. Native
installers and `.app` bundles are produced by the **Native apps** workflow; they
are unsigned review candidates, separate from the existing released packages.
See [native installation](docs/native-install.md) and the [screen/API contract](docs/native-apps.md).

