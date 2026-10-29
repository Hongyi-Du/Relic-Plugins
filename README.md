# Relic · macOS Apple silicon Beta

**macOS Apple silicon prerelease: v0.4.1-macos-beta.1** (plugin 0.15.1-macos-beta.1).

[简体中文](README.zh-CN.md) · [Website](https://hongyidu.ai/relic/en/plugins) · [Mac release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.4.1-macos-beta.1) · [Windows release v0.6.0-beta.1](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.6.0-beta.1)

**Persistent agent organizations for Claude Code and Codex.** Relic gives agents shared messages, documents, tasks, episodes and protocols that can survive a change of member. Start with a task; let members negotiate responsibilities and turn recurring coordination problems into shared agreements.

This branch brings the tested **v0.4.1-beta.1** baseline to **macOS on Apple silicon (arm64)**. It includes the **Relic App** and the Relic plugin for Claude Code and Codex, with English and Chinese interfaces, organization hierarchies, subgroups, a secretariat and sessions that sit in several organizations. It does not include the features added upstream in v0.5 or v0.6; the newer Windows release is a separate release line. See the [changelog](CHANGELOG.md).

The Mac package is an **unsigned source installer**, not a standalone application bundle. Intel Macs and Rosetta are unsupported. Relic runs locally using your existing Claude Code/Codex login; it does not include model access or a hosted service.

## Install

Requires **native arm64 Python 3.11+**, **native arm64 Node.js 22+ with npm**, and **Claude Code and/or Codex, installed and signed in**.

The release archives are `relic-macos-v0.4.1-macos-beta.1.zip` and `relic-macos-v0.4.1-macos-beta.1.tar.gz`, accompanied by `SHA256SUMS.txt` and `release-manifest.json`. Get the assets from the [Mac release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.4.1-macos-beta.1). Extract it to a permanent folder, open Terminal in that folder, and run:

```bash
bash install.command --host none --open
```

This installs the App launcher at **`~/Applications/Relic.app`** and opens the App. **Keep the extracted folder:** the launcher runs its source files. In Settings → Harness connections, check the detected tools and install the ACP adapters for members that run in the App. Adapter installation downloads dependencies through npm.

`--host none` uses the App alone; it does not install plugins into your host CLIs. To also install the Relic plugin into your installed Claude Code and/or Codex, replace it with `--host claude`, `--host codex`, or `--host both`. Restart the selected host or start a new session, then review and trust the plugin hooks. The installer does not call a model or trust hooks on your behalf. See the [macOS guide](docs/macos.en.md) for installation options and troubleshooting.

Create an organization and add members in the Relic App, or say in a host with the plugin installed: “Use Relic to form an organization for this task.” To join an existing organization, say “Join Relic organization org_… as member reviewer.”

**Upgrading an existing installation:** stop the App with `python3 -X utf8 scripts/open_app.py --stop`, extract the new package to its permanent location, then run its installer. Organization data is retained. Run `/reload-plugins` in open Claude Code sessions and restart Codex so it loads the updated plugin. See the [upgrade notes](docs/guide.en.md#9-storage-updates-and-removal).

For Windows, use the separate [v0.6.0-beta.1 release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.6.0-beta.1) and its matching installation instructions.

## Relic App

The **Relic App** is a desktop chat for Relic organizations and the bridge between their members, in English or Chinese (Settings → Language and names → Language):

- members that run in the App are Claude Code or Codex sessions inside it; the App brings Relic into each of these sessions itself, so they need only Claude Code or Codex, installed and signed in;
- Add member runs a member in the App, in Claude Code or Codex itself (command line or desktop app), or seats a session already on this computer: a Claude Code session, a Codex chat or a ChatGPT chat;
- the group chat with every message between members, a direct chat with each member, and the secretary; a member whose session transcript can be read shows that whole conversation, its actions folded;
- **Plain words** rewrites what members tell each other so someone outside the work can follow it, and **Digest** sums up what the group has been doing;
- organizations above and below one another (Overview → Hierarchy), subgroups, a secretariat whose leader, the secretary-general, approves changes to formal organizations, and sessions that sit in several organizations; View → Organization chart… draws them all;
- threads and quotes, a member's workspace and file preview, task reports, voice input, and settings for profile, appearance, language, notifications and harness connections.

Open **`~/Applications/Relic.app`**, ask a Claude Code or Codex session with the plugin to open the Relic App, or run this from the extracted folder:

```bash
python3 -X utf8 scripts/open_app.py
```

Use the same native arm64 Python 3.11+ interpreter selected during installation for direct Python commands.

It runs a local server on 127.0.0.1 and opens its interface in a browser. The macOS launcher is a shortcut to this local service. Plain words, Digest and automatic member names make short calls to your signed-in Claude Code (`claude -p`); see [privacy and data](docs/privacy.en.md).

App-managed Claude Code and Codex members have completed a real, signed-in organization workflow on Apple silicon, including shared documents, task reports and review between members. Native desktop delivery is conditional: Codex/ChatGPT socket bridging and Claude Desktop delivery are enabled only when their host-specific capability checks pass. This prerelease does not claim full browser or native desktop-host acceptance.

## Earlier editions

v0.2.0-beta.1 had three editions: Relic Claude 0.1.0-beta.1, Relic Codex / GPT 0.6.0-beta.1 and Relic Bridge 0.13.0-beta.1. Bridge became Relic; the others are no longer developed. All three stay downloadable from the [v0.2.0-beta.1 release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.2.0-beta.1).

- **Relic Bridge**: the plugin id stays `relic@relic-bridge` (its display name is now Relic), so the installer upgrades Bridge in place. Organizations in `~/.relic` carry over.
- **Relic Claude**: the installer disables `relic@relic-claude` in Claude Code, since it has the same tool names. Its organizations stay in `~/.claude/relic/relic.sqlite3` and are not converted.
- **Relic Codex / GPT**: the installer leaves the Codex plugin `relic-organization` alone (different tools and data); remove it in Codex if you no longer use it. Its data stays in `~/.codex/relic-organization` and is not converted. Forming organizations from native Codex subagents, text meetings (`org_call`), quiet mode and the `require_peer_review` rule format have no counterpart in Relic.

## Documentation

- [Complete user guide](docs/guide.en.md) / [完整中文指南](docs/guide.zh-CN.md)
- [Windows v0.4.1 baseline guide](docs/windows.en.md) / [Windows v0.4.1 基线说明](docs/windows.zh-CN.md)
- [macOS installation and support](docs/macos.en.md) / [macOS 安装与支持](docs/macos.zh-CN.md)
- [macOS migration steps and remaining acceptance](docs/macos-migration.md)
- [Tool reference](docs/reference.en.md) / [工具参考](docs/reference.zh-CN.md)
- [Privacy and data](docs/privacy.en.md) / [隐私与数据](docs/privacy.zh-CN.md)
- [Changelog](CHANGELOG.md), [contributing](CONTRIBUTING.md), [validation](docs/validation.md)

## Development

The runtime uses Python's standard library. `python3 scripts/check.py` runs the two isolated fixture suites, `relic` (the plugin and the App) and `packaging` (the installer and the archives); `--suite relic` or `--suite packaging` runs one. Build both Mac archive formats with:

```bash
python3 scripts/package.py --platform macos --macos-format both --output dist
```

This also writes `SHA256SUMS.txt` and `release-manifest.json`. Building archives does not publish a GitHub release. All four jobs passed in [CI run 40808895809](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40808895809): macOS 15/Python 3.11, macOS 26/Python 3.13, and Windows 2025/Python 3.11 and 3.13. The macOS jobs also verified native arm64 Python and Node 22.

Each Mac CI job recorded **417 passed, 2 skipped**; each Windows job recorded **379 passed, 40 skipped**, with platform-specific skips listed in the logs. CI tested runtime commit [`2d790de`](https://github.com/Hongyi-Du/Relic-Plugins/commit/2d790de6777454fc04013ff1ba2830c567da7108); the release adds only documentation after that commit. Local archive extraction, installation, launcher startup, restart and shutdown were also exercised on the Mac. The [validation record](docs/validation.md) separates CI from the signed-in organization test and describes the remaining coverage limits; automated tests do not certify every desktop-host integration.

The macOS installer creates `~/Applications/Relic.app`; `--no-shortcut` skips it and `--remove-launcher` removes only that managed launcher.
`python3 -X utf8 scripts/open_app.py --status`, `--stop` and `--restart` manage the server for the selected data directory.
See the macOS guide for native desktop-host requirements and limitations.

Source is under [MIT](LICENSE), matching the current public [Relic research repository](https://github.com/Hongyi-Du/Relic). This plugin release is separate from the paper's experiment code and from [Relic-Agent](https://github.com/Hongyi-Du/Relic-Agent). Please report reproducible issues at [GitHub Issues](https://github.com/Hongyi-Du/Relic-Plugins/issues) after removing private data.
