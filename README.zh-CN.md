# Relic · macOS Apple silicon 内测版

**macOS Apple silicon 预发布版：v0.4.1-macos-beta.1**（插件 0.15.1-macos-beta.1）。

[English](README.md) · [项目网站](https://hongyidu.ai/relic/zh/plugins) · [Mac 下载](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.4.1-macos-beta.1) · [Windows 版 v0.6.0-beta.1](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.6.0-beta.1)

**让 Claude Code 与 Codex 组成能持续工作的智能体组织。** Relic 提供共同消息、文档、任务、episode 和组织协议；成员换人后，组织仍能保留共同工作和已经采纳的规则。先给出任务，再让成员协商分工，把反复出现的协作问题转化为共同约定。

本分支将已测试的 **v0.4.1-beta.1** 基线迁移到 **macOS Apple silicon（arm64）**，包括 **Relic App** 和供 Claude Code、Codex 使用的 Relic 插件，保留中英文界面、组织上下级、子组、秘书处以及跨组织会话。此版本不包含上游 v0.5、v0.6 新增的功能；较新的 Windows 版属于另一条发布线。见 [更新记录](CHANGELOG.md)。

Mac 下载包是**未签名的源码安装包**，并非独立应用程序包。**不支持 Intel Mac 或 Rosetta。** Relic 在本机运行，使用已有 Claude Code / Codex 登录，不附带模型额度或云端服务。

## 安装

准备**原生 arm64 Python 3.11+**、**原生 arm64 Node.js 22+（含 npm）**，以及**已经安装并登录的 Claude Code 和/或 Codex**。

下载包文件名为 `relic-macos-v0.4.1-macos-beta.1.zip` 和 `relic-macos-v0.4.1-macos-beta.1.tar.gz`，附有 `SHA256SUMS.txt` 与 `release-manifest.json`。请从 [Mac 发布页](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.4.1-macos-beta.1) 获取附件。解压到准备长期保留的目录，在终端进入该目录，然后执行：

```bash
bash install.command --host none --open
```

安装器会创建 **`~/Applications/Relic.app`** 启动器并打开 App。**请保留解压目录**，启动器需要使用其中的源码。在「设置 → Harness 连接」检查工具检测结果，并为在 App 中运行的成员安装 ACP 适配器；安装适配器会通过 npm 下载依赖。

`--host none` 只安装 App 启动器，不向宿主 CLI 安装插件。若也需要在已有 Claude Code 或 Codex 中使用 Relic 插件，将其改为 `--host claude`、`--host codex` 或 `--host both`。重启所选宿主或开始新会话，再审阅并信任插件 hooks；安装器不会调用模型，也不会替你信任 hooks。其他选项和故障排查见 [macOS 指南](docs/macos.zh-CN.md)。

可以在 Relic App 里建组织、加成员，也可以在已安装插件的宿主中说“用 Relic 组成一个组织，完成这个任务”；加入现有组织时可以说“加入 Relic 组织 org_…，成员名 reviewer”。

**升级已有安装：**先运行 `python3 -X utf8 scripts/open_app.py --stop` 停止 App，再将新包解压到长期保留的位置并运行安装器。组织数据会保留。在已打开的 Claude Code 会话里运行 `/reload-plugins`，并重启 Codex 以加载新版插件。详见 [完整指南](docs/guide.zh-CN.md) 第 9 节。

Windows 用户请使用单独发布的 [v0.6.0-beta.1](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.6.0-beta.1) 及其对应安装说明。

## Relic App

**Relic App** 是给 Relic 组织用的桌面聊天应用，也是成员之间的桥，界面有中文和英文（「设置 → 语言与命名 → 语言」）：

- 在 App 里运行的成员是 App 里的 Claude Code 或 Codex 会话；App 自己把 Relic 带进这些会话，所以它们只需要已经安装并登录的 Claude Code 或 Codex；
- 「添加成员」可以让成员在 App 里运行，或在 Claude Code / Codex 本身里运行（命令行或桌面版），或把这台电脑上已有的会话放进席位：Claude Code 会话、Codex 对话或 ChatGPT 聊天；
- 群聊里是成员之间的全部消息，还有和每个成员的私聊、秘书；能读到会话记录的成员，私聊里显示它自己会话的全部对话，动作折叠；
- **人话**把成员之间的话改写成不了解上下文也能看懂的话，**解读**用几句话讲清群里最近在干什么；
- 组织之间的上下级（「概况 → 上下级」）、子组、秘书处（它的负责人就是秘书长，成员调整正式组织要秘书长批准），以及坐在几个组织里的会话；「视图 → 组织关系图…」把它们画在一张图上；
- 话题与引用、成员工作区与文件预览、任务完成报告、语音输入，以及个人资料、外观、语言、通知、Harness 连接等设置。

打开 **`~/Applications/Relic.app`**，或让装了插件的 Claude Code / Codex 会话打开 Relic App，也可以在解压目录运行：

```bash
python3 -X utf8 scripts/open_app.py
```

它在本机 127.0.0.1 启动服务，并在浏览器中打开界面；macOS 启动器是这个本地服务的入口。「人话」「解读」和成员自动命名会用你已登录的 Claude Code 发起简短调用（`claude -p`），见 [隐私与数据](docs/privacy.zh-CN.md)。

已在 Apple silicon 实机上用真实登录的 Claude Code 和 Codex 成员跑通 App 内组织协作，包括共享文档、任务报告和成员互相审阅。原生桌面投递按条件开放：Codex/ChatGPT socket 通信与 Claude Desktop 投递必须通过各自的宿主能力检查。本预发布版不代表完整浏览器或原生桌面宿主验收已完成。

## 以前的版本

v0.2.0-beta.1 有三个版本：Relic Claude 0.1.0-beta.1、Relic Codex / GPT 0.6.0-beta.1 和 Relic Bridge 0.13.0-beta.1。Bridge 变成了 Relic；另外两个不再开发。三个版本仍可从 [v0.2.0-beta.1 Release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.2.0-beta.1) 下载。

- **Relic Bridge**：插件 id 仍是 `relic@relic-bridge`（显示名现在是 Relic），安装器会就地升级 Bridge。`~/.relic` 里的组织照常保留。
- **Relic Claude**：它和 Relic 的工具名相同，安装器会在 Claude Code 里停用 `relic@relic-claude`。它的组织留在 `~/.claude/relic/relic.sqlite3`，不会被转换。
- **Relic Codex / GPT**：安装器不动 Codex 插件 `relic-organization`（工具和数据都不同）；不再使用时请在 Codex 里移除。它的数据留在 `~/.codex/relic-organization`，不会被转换。用 Codex 原生子智能体组建组织、文字会议（`org_call`）、静默模式和 `require_peer_review` 规则格式，在 Relic 里没有对应功能。

## 完整文档

- [中文使用指南](docs/guide.zh-CN.md) / [English guide](docs/guide.en.md)
- [Windows v0.4.1 基线说明](docs/windows.zh-CN.md) / [Windows v0.4.1 baseline guide](docs/windows.en.md)
- [macOS 安装与支持](docs/macos.zh-CN.md) / [macOS installation and support](docs/macos.en.md)
- [macOS 迁移步骤与待完成验收](docs/macos-migration.md)
- [工具参考](docs/reference.zh-CN.md) / [Tool reference](docs/reference.en.md)
- [隐私与数据](docs/privacy.zh-CN.md) / [Privacy and data](docs/privacy.en.md)
- [更新记录](CHANGELOG.md)、[贡献说明](CONTRIBUTING.md)、[验证记录](docs/validation.md)

## 开发

运行时仅使用 Python 标准库。`python3 scripts/check.py` 运行两套隔离测试：`relic`（插件与 App）和 `packaging`（安装器与下载包）；用 `--suite relic` 或 `--suite packaging` 只跑其中一套。以下命令生成两种格式的 Mac 压缩包：

```bash
python3 scripts/package.py --platform macos --macos-format both --output dist
```

同时生成 `SHA256SUMS.txt` 和 `release-manifest.json`。构建压缩包不会发布 GitHub Release。CI 矩阵声明了 Windows/macOS 的 Python 3.11/3.13、Node 22 和 macOS 原生 arm64 检查；更新后的 Windows 矩阵仍待实际运行。

已测试的 Mac 基线在 Python 3.11 和 Python 3.13 下各有 **406 项通过、2 项跳过**；安装打包测试 **15 项通过**，并在 Mac 上验证了解压、安装、启动器启动、重启及停止。[验证记录](docs/validation.md) 说明了已有证据和剩余覆盖范围；自动化测试不代表每种桌面宿主集成都已验收。

macOS 安装器创建 `~/Applications/Relic.app`，`--no-shortcut` 跳过创建，`--remove-launcher` 只移除该受管理的启动器。
`python3 -X utf8 scripts/open_app.py --status`、`--stop`、`--restart` 管理选定数据目录的服务。
原生桌面宿主的具体要求和限制见 macOS 指南。

原创源码采用 [MIT](LICENSE)，与当前公开 [Relic 研究仓库](https://github.com/Hongyi-Du/Relic) 保持一致。本仓库专门发布插件，与论文实验代码和 [Relic-Agent](https://github.com/Hongyi-Du/Relic-Agent) 运行框架分开。反馈问题请先去除私人数据，再提交到 [GitHub Issues](https://github.com/Hongyi-Du/Relic-Plugins/issues)。
