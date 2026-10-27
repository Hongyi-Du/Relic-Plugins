# Relic Plugins · Public Beta

[简体中文](README.zh-CN.md) · [Website](https://hongyidu.ai/relic/en/plugins) · [Downloads](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.2.0-beta.1)

**Persistent agent organizations for Claude Code and Codex.** Relic gives agents shared messages, documents, tasks, episodes and protocols that can survive a change of member. Start with a task; let members negotiate responsibilities and turn recurring coordination problems into shared agreements.

This is the second public beta, **v0.2.0-beta.1**. Relic Bridge now includes the **Relic App**, a desktop chat for your organizations (see below). The three editions are published for **Windows only**. macOS is not released; it will be published after development and real Mac testing are complete. The plugins run locally using your existing Claude Code/Codex login. They do not include model access or a hosted service.

| Edition | Choose it for | Component version |
| --- | --- | --- |
| **Relic Claude** | Claude Code sessions and Claude Code subagents | 0.1.0-beta.1 |
| **Relic Codex / GPT** | Codex native subagents or selected Codex desktop chats | 0.6.0-beta.1 |
| **Relic Bridge** | Claude Code and Codex members in the same local organization; the Relic App | 0.13.0-beta.1 |

For a mixed Claude + GPT team, choose **Bridge**. Enable one Relic edition per host. The standalone editions have separate storage formats; installing Bridge does not migrate their organizations.

## Install

Requires **Python 3.11+**, the CLI for the chosen host, and a signed-in host account. Tk is needed only for the optional panels. Download the Windows ZIP for your edition from the [release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.2.0-beta.1), extract it to a permanent folder, and run:

```powershell
# Windows, from the extracted package
python -X utf8 scripts/install.py
```

From a source checkout, select the edition explicitly:

```bash
python -X utf8 scripts/install.py --edition bridge
# Install Bridge into one host only: add --host claude or --host codex
```

Restart the host or start a new session, then review and trust the plugin hooks. In a Claude Code chat say “Use Relic to form an organization for this task”; in Codex with Bridge say “Join Relic organization org_… as member reviewer”. For the Codex edition use `$relic-organization`.

**macOS status: not released.** Existing CI results are development evidence, not real Mac desktop acceptance. macOS downloads are withheld until testing on a Mac is complete. See the [development draft](docs/macos.en.md).

## Relic App (Bridge)

Bridge 0.13 includes the **Relic App**, a desktop chat for Relic organizations (its interface is in Chinese in this beta):

- the group chat with every message between members, a private chat with each member, and the secretary; a member whose session transcript can be read shows that whole conversation, its actions folded;
- **人话** rewrites what members tell each other so someone outside the work can follow it, and **解读** sums up what the group has been doing;
- threads and quotes, a member's workspace and file preview, task reports, voice input, and settings for profile, appearance, language, notifications and harness connections.

After installing the Bridge package, open it with:

```powershell
python -X utf8 scripts/open_app.py
```

It runs a local server on 127.0.0.1 and opens a Microsoft Edge (or Chrome) window. Click 安装 in its window bar to install it as an application with its own window and title bar. 人话, 解读 and automatic member names make short calls to your signed-in Claude Code (`claude -p`); see [privacy and data](docs/privacy.en.md).

## Documentation

- [Complete user guide](docs/guide.en.md) / [完整中文指南](docs/guide.zh-CN.md)
- [Windows installation](docs/windows.en.md) / [Windows 中文说明](docs/windows.zh-CN.md)
- [macOS development draft — not released](docs/macos.en.md) / [macOS 开发草稿 — 未发布](docs/macos.zh-CN.md)
- [Tool reference](docs/reference.en.md) / [工具参考](docs/reference.zh-CN.md)
- [Privacy and data](docs/privacy.en.md) / [隐私与数据](docs/privacy.zh-CN.md)
- [Changelog](CHANGELOG.md), [contributing](CONTRIBUTING.md), [validation](docs/validation.md)

## Development

The runtime uses Python's standard library. Run `python scripts/check.py` to run the isolated fixture suites and MCP launch checks. `python scripts/package.py --output dist` builds development archives for both platforms plus `SHA256SUMS.txt`; only Windows archives are currently published. Windows/macOS CI uses Python 3.11. These checks do not invoke a real model or certify every desktop-host integration.

Source is under [MIT](LICENSE), matching the current public [Relic research repository](https://github.com/Hongyi-Du/Relic). This plugin release is separate from the paper's experiment code and from [Relic-Agent](https://github.com/Hongyi-Du/Relic-Agent). Please report reproducible issues at [GitHub Issues](https://github.com/Hongyi-Du/Relic-Plugins/issues) after removing private data.
