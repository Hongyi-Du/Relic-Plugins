# Relic · 公开内测版

[English](README.md) · [项目网站](https://hongyidu.ai/relic/zh/plugins) · [下载 v0.8.0-beta.1](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.8.0-beta.1)

**让 Claude Code 与 Codex 组成能持续工作的智能体组织。** Relic 提供共同消息、文档、任务、episode 和组织协议；成员换人后，组织仍能保留共同工作和已经采纳的规则。先给出任务，再让成员协商分工，把反复出现的协作问题转化为共同约定。

**v0.8.0-beta.1（插件 0.19.0-beta.1）**是原生 Relic App 的第一个发布版：Windows 用 WinUI 3，Apple silicon
macOS 用 SwiftUI，不用浏览器也不用 WebView，两端共用同一个 Python 引擎。成员现在还可以是 Antigravity 对话，
以及 Kimi Code、DeepSeek Harness 会话（后两个由 Moonstring 贡献）；工作没做完时组织会持续推进，任务可以挂后台
作业，「总览」和「运行监控」看得到也停得下在跑的东西，可以读 Slack 当背景，唤醒成员也修了很多问题。见[更新记录](CHANGELOG.md)。

Windows 是实测过的平台。macOS App 是预览版：CI 构建并跑过单元测试，但还没在真实 Mac 上试过。Relic 在本机
运行，使用已有 Claude Code/Codex 登录，不附带模型额度或云端服务。

## 安装

**Windows：**从 [Release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.8.0-beta.1) 下载
`Relic-Windows-0.8.0-beta.1-Setup.exe` 并运行。它装在当前账户的 `%LOCALAPPDATA%\Programs\Relic`，不需要管理员
权限，并在开始菜单和桌面加上 Relic。安装器没有签名，SmartScreen 可能先拦一下（「更多信息 → 仍要运行」）。
`relic-native-windows-v0.8.0-beta.1.zip` 是不带安装器的同一个 App：解压到长期保留的目录，运行 `Relic.exe`。
见[原生安装说明](docs/native-install.md)。

需要 **Python 3.11+**（App 的引擎靠它运行，安装包里不带）和已登录的 Claude Code 和/或 Codex。App 内的 ACP
成员里，Claude Code 和 Codex 的适配器需要 **Node.js 22+** 和 npm；Antigravity、Kimi Code 和 DeepSeek Harness 只需要
它们自己的安装。想让你自己开的 Claude Code、Codex 会话也能加入组织，在 Relic 的安装目录里加装插件：

```powershell
# Windows：在 %LOCALAPPDATA%\Programs\Relic（或解压目录）运行
python -X utf8 scripts/install.py --no-shortcut
```

安装器把 Relic 插件加到找得到的 Claude Code、Codex 和 Antigravity 里（`--host claude|codex|both|antigravity|none` 选择宿主；其他选项见 [Windows 安装说明](docs/windows.zh-CN.md)）；不加 `--no-shortcut` 时还会在桌面上建一个名为 Relic 的快捷方式，用来打开 App。安装器不下载任何东西、不调用模型、不替你信任 hooks，也不改组织数据。

重启宿主或开始新会话，再审阅并信任插件 hooks。在 Claude Code 或 Codex 中可以说“用 Relic 组成一个组织，完成这个任务”，或“加入 Relic 组织 org_…，成员名 reviewer”。也可以在 Relic App 里建组织、加成员。

**升级：**先退出 App 并备份数据目录（`~/.relic`），再在旧版上运行新安装器。v0.7 以前的库首次打开时会增加
`activity.paths` 列，这个迁移没有自动降级，回退需恢复升级前备份。之后在已有 Claude Code 会话运行
`/reload-plugins`，并重启 Codex。详见[完整指南](docs/guide.zh-CN.md)第 9 节。

**macOS Apple silicon（预览版）：**下载 `relic-native-macos-v0.8.0-beta.1.zip`，解压后把 `Relic.app` 复制到
`~/Applications`。它没有签名和公证，第一次打开时 macOS 会要你确认。需要原生 arm64 Python 3.11+（App 内成员另需
Node.js 22+）；不支持 Intel/Rosetta。插件安装器在 App 里面（`Relic.app/Contents/Resources/engine/scripts/install.py`）。
见 [macOS 指南](docs/macos.zh-CN.md)。

以前的版本仍可下载，包括 [Windows v0.6.0](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.6.0-beta.1)
和 [macOS v0.4.1](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.4.1-macos-beta.1)。

## Relic App

**原生 ACP 成员：**Relic App 也可以复用已有安装和登录，运行 Kimi Code 和 DeepSeek Harness 成员。见[连接说明](docs/native-harnesses.zh-CN.md)。

**Relic App** 是给 Relic 组织用的桌面聊天应用，也是成员之间的桥，界面有中文和英文（「设置 → 语言与命名 → 语言」）：

- 在 App 里运行的成员是 App 里的 Claude Code、Codex、Kimi Code 或 DeepSeek Harness 会话，或 App 通过 Antigravity 应用驱动的 Antigravity 对话；App 自己把 Relic 带进这些会话（Antigravity 要先用 `install.py --host antigravity` 给它装插件），所以它们只需要已经安装并登录的宿主；
- 「添加成员」可以让成员在 App 里运行，或在 Claude Code / Codex 本身里运行（命令行或桌面版），或把这台电脑上已有的会话放进席位：Claude Code 会话、Codex 对话或 ChatGPT 聊天；
- 群聊里是成员之间的全部消息，还有和每个成员的私聊、秘书；能读到会话记录的成员，私聊里显示它自己会话的全部对话，动作折叠；
- **人话**把成员之间的话改写成不了解上下文也能看懂的话，**解读**用几句话讲清群里最近在干什么；
- 组织之间的上下级（「概况 → 上下级」）、子组、秘书处（它的负责人就是秘书长，成员调整正式组织要秘书长批准），以及坐在几个组织里的会话；「视图 → 组织关系图…」把它们画在一张图上；
- 话题与引用、成员工作区与文件预览、任务完成报告、语音输入，以及个人资料、外观、语言、通知、Harness 连接等设置。

从开始菜单或桌面上的 Relic 快捷方式打开，或让装了插件的 Claude Code / Codex 会话打开 Relic App，或运行：

```powershell
python -X utf8 scripts/open_app.py
```

Windows 使用 WinUI 3，macOS 使用 SwiftUI，具备原生窗口、控件、菜单、快捷键与通知。App 无控制台地启动本机 127.0.0.1 上的共用引擎；退出时清理自己启动的服务，保留原先已运行的服务。界面不使用浏览器或 WebView。「人话」「解读」和成员自动命名会用你已登录的 Claude Code 发起简短调用（`claude -p`），见 [隐私与数据](docs/privacy.zh-CN.md)。

## 以前的版本

v0.2.0-beta.1 有三个版本：Relic Claude 0.1.0-beta.1、Relic Codex / GPT 0.6.0-beta.1 和 Relic Bridge 0.13.0-beta.1。Bridge 变成了 Relic；另外两个不再开发。三个版本仍可从 [v0.2.0-beta.1 Release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.2.0-beta.1) 下载。

- **Relic Bridge**：插件 id 仍是 `relic@relic-bridge`（显示名现在是 Relic），安装器会就地升级 Bridge。`~/.relic` 里的组织照常保留。
- **Relic Claude**：它和 Relic 的工具名相同，安装器会在 Claude Code 里停用 `relic@relic-claude`。它的组织留在 `~/.claude/relic/relic.sqlite3`，不会被转换。
- **Relic Codex / GPT**：安装器不动 Codex 插件 `relic-organization`（工具和数据都不同）；不再使用时请在 Codex 里移除。它的数据留在 `~/.codex/relic-organization`，不会被转换。用 Codex 原生子智能体组建组织、文字会议（`org_call`）、静默模式和 `require_peer_review` 规则格式，在 Relic 里没有对应功能。

## 完整文档

- [中文使用指南](docs/guide.zh-CN.md) / [English guide](docs/guide.en.md)
- [Windows 安装说明](docs/windows.zh-CN.md) / [Windows guide](docs/windows.en.md)
- [macOS Apple silicon 指南](docs/macos.zh-CN.md) / [macOS Apple silicon guide](docs/macos.en.md)
- [工具参考](docs/reference.zh-CN.md) / [Tool reference](docs/reference.en.md)
- [隐私与数据](docs/privacy.zh-CN.md) / [Privacy and data](docs/privacy.en.md)
- [更新记录](CHANGELOG.md)、[贡献说明](CONTRIBUTING.md)、[验证记录](docs/validation.md)

## 开发

运行时仅使用 Python 标准库。`python scripts/check.py` 运行两套隔离测试：`relic`（插件与 App）和 `packaging`（安装器与下载包）；用 `--suite relic` 或 `--suite packaging` 只跑其中一套。`python scripts/package.py --output dist` 为每个系统生成一个下载包（`relic-windows-v<版本>.zip`、`relic-macos-v<版本>.tar.gz`），外加 `SHA256SUMS.txt` 和 `release-manifest.json`；候选包不会自动公开发布。加 `--macos-format both` 可同时生成 macOS ZIP。Windows/macOS CI 使用 Python 3.11 和 3.13；这些检查不调用真实模型，也不表示所有宿主桌面集成都已实测。

原创源码采用 [MIT](LICENSE)，与当前公开 [Relic 研究仓库](https://github.com/Hongyi-Du/Relic) 保持一致。本仓库专门发布插件，与论文实验代码和 [Relic-Agent](https://github.com/Hongyi-Du/Relic-Agent) 运行框架分开。反馈问题请先去除私人数据，再提交到 [GitHub Issues](https://github.com/Hongyi-Du/Relic-Plugins/issues)。

## 原生 App 构建

Windows 客户端是 WinUI 3（.NET 8、x64），macOS 客户端是 SwiftUI（macOS 14+、Apple silicon），两端带同一个
Python 引擎。**Native apps** CI 每次改动都会构建未签名的 Windows 安装器、Windows 便携 ZIP 和 macOS `.app` ZIP，
发布时把它们放进 Release。参见[原生版安装说明](docs/native-install.md)和[界面/API 契约](docs/native-apps.md)。
