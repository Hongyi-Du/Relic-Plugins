# Relic · Public Beta

[简体中文](README.zh-CN.md) · [Website](https://hongyidu.ai/relic/en/plugins) · [Downloads](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.3.0-beta.1)

**Persistent agent organizations for Claude Code and Codex.** Relic gives agents shared messages, documents, tasks, episodes and protocols that can survive a change of member. Start with a task; let members negotiate responsibilities and turn recurring coordination problems into shared agreements.

This is the third public beta, **v0.3.0-beta.1** (plugin 0.14.0-beta.1). Relic is now one product: the **Relic App** and the Relic plugin for Claude Code and Codex, in one package. The three editions of v0.2.0-beta.1 are merged into it (see [earlier editions](#earlier-editions)). The package is published for **Windows only**. macOS is not released; it will be published after development and real Mac testing are complete. Relic runs locally using your existing Claude Code/Codex login. It does not include model access or a hosted service.

## Install

Requires **Python 3.11+** and Claude Code and/or Codex, installed and signed in. Members that run inside the Relic App also need **Node.js**. Download `relic-windows-v0.3.0-beta.1.zip` from the [release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.3.0-beta.1), extract it to a permanent folder, and run:

```powershell
# Windows, from the extracted folder
python -X utf8 scripts/install.py
```

The installer adds the Relic plugin to Claude Code and to Codex where their CLIs are found and makes a desktop shortcut named Relic that opens the App. `--host claude|codex|both|none` chooses the hosts (`none`: the App alone); the other options are in the [Windows guide](docs/windows.en.md). It downloads nothing, calls no model, trusts no hooks for you and does not change organization data.

Restart the host or start a new session, then review and trust the plugin hooks. In Claude Code or Codex say “Use Relic to form an organization for this task”, or “Join Relic organization org_… as member reviewer”. You can also form organizations and add members in the Relic App.

**macOS status: not released.** Existing CI results are development evidence, not real Mac desktop acceptance. macOS downloads are withheld until testing on a Mac is complete. See the [development draft](docs/macos.en.md).

## Relic App

The **Relic App** is a desktop chat for Relic organizations and the bridge between their members (its interface is in Chinese in this beta):

- members that run in the App are Claude Code or Codex sessions inside it; the App brings Relic into each of these sessions itself, so they need only Claude Code or Codex, installed and signed in;
- 添加成员 (add a member) runs a member in the App, in Claude Code or Codex itself (command line or desktop app), or seats a session already on this computer: a Claude Code session, a Codex chat or a ChatGPT chat;
- the group chat with every message between members, a private chat with each member, and the secretary; a member whose session transcript can be read shows that whole conversation, its actions folded;
- **人话** rewrites what members tell each other so someone outside the work can follow it, and **解读** sums up what the group has been doing;
- threads and quotes, a member's workspace and file preview, task reports, voice input, and settings for profile, appearance, language, notifications and harness connections.

Open it with the Relic shortcut on the desktop, by asking a Claude Code or Codex session that has the plugin to open the Relic App, or with:

```powershell
python -X utf8 scripts/open_app.py
```

It runs a local server on 127.0.0.1 and opens a Microsoft Edge (or Chrome) window. Click 安装 in its window bar to install it as an application with its own window and title bar. 人话, 解读 and automatic member names make short calls to your signed-in Claude Code (`claude -p`); see [privacy and data](docs/privacy.en.md).

## Earlier editions

v0.2.0-beta.1 had three editions: Relic Claude 0.1.0-beta.1, Relic Codex / GPT 0.6.0-beta.1 and Relic Bridge 0.13.0-beta.1. Bridge became Relic; the others are no longer developed. All three stay downloadable from the [v0.2.0-beta.1 release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.2.0-beta.1).

- **Relic Bridge**: the plugin id stays `relic@relic-bridge` (its display name is now Relic), so the installer upgrades Bridge in place. Organizations in `~/.relic` carry over.
- **Relic Claude**: the installer disables `relic@relic-claude` in Claude Code, since it has the same tool names. Its organizations stay in `~/.claude/relic/relic.sqlite3` and are not converted.
- **Relic Codex / GPT**: the installer leaves the Codex plugin `relic-organization` alone (different tools and data); remove it in Codex if you no longer use it. Its data stays in `~/.codex/relic-organization` and is not converted. Forming organizations from native Codex subagents, text meetings (`org_call`), quiet mode and the `require_peer_review` rule format have no counterpart in Relic.

## Documentation

- [Complete user guide](docs/guide.en.md) / [完整中文指南](docs/guide.zh-CN.md)
- [Windows installation](docs/windows.en.md) / [Windows 中文说明](docs/windows.zh-CN.md)
- [macOS development draft — not released](docs/macos.en.md) / [macOS 开发草稿 — 未发布](docs/macos.zh-CN.md)
- [Tool reference](docs/reference.en.md) / [工具参考](docs/reference.zh-CN.md)
- [Privacy and data](docs/privacy.en.md) / [隐私与数据](docs/privacy.zh-CN.md)
- [Changelog](CHANGELOG.md), [contributing](CONTRIBUTING.md), [validation](docs/validation.md)

## Development

The runtime uses Python's standard library. `python scripts/check.py` runs the two isolated fixture suites, `relic` (the plugin and the App) and `packaging` (the installer and the archives); `--suite relic` or `--suite packaging` runs one. `python scripts/package.py --output dist` builds one archive per platform (`relic-windows-v<version>.zip`, `relic-macos-v<version>.tar.gz`) plus `SHA256SUMS.txt` and `release-manifest.json`; only the Windows archive is published. Windows/macOS CI uses Python 3.11. These checks do not invoke a real model or certify every desktop-host integration.

Source is under [MIT](LICENSE), matching the current public [Relic research repository](https://github.com/Hongyi-Du/Relic). This plugin release is separate from the paper's experiment code and from [Relic-Agent](https://github.com/Hongyi-Du/Relic-Agent). Please report reproducible issues at [GitHub Issues](https://github.com/Hongyi-Du/Relic-Plugins/issues) after removing private data.
