# macOS 开发草稿 — 未发布

**目前不提供 macOS 公开下载。**本次内测仅发布 Windows。CI 会构建 macOS 包（`relic-macos-v<版本>.tar.gz`），但不发布。macOS 代码与说明保留供后续真实 Mac 测试，CI 通过不能代替已登录宿主的桌面实机验收。

[English](macos.en.md) · [完整使用指南](guide.zh-CN.md)

## 准备

使用仍受维护的 Python 发行版，版本 **3.11+**，确保 Terminal 中有 `python3`。下载包包含 Python 源码，没有绑定 CPU 架构的二进制；Apple Silicon 和 Intel 都需要各自兼容的 Python 与宿主。本次发布没有认证两种架构上的真实桌面会话。

安装并登录 Claude Code 和/或 Codex，确认同一个 Terminal 中 `claude --version` / `codex --version` 可用。macOS 安装器 `bash install.command` 用 `python3` 运行 `scripts/install.py`，选项相同；它依赖 CLI 位于 PATH。在 Relic App 里运行的成员还需要 Node.js 来运行 ACP 适配器。

## 发布状态

待真实 Mac 验证完成后，再定稿安装说明并提供下载包。当前阶段不提供公开安装入口。

## 当前开发状态（未发布）

| 功能 | 可用范围 |
| --- | --- |
| Claude Code 与 Codex CLI 会话里的 Relic 工具和 hooks：组织、消息、文档、任务、治理 | 已包含，宿主需要加载 hooks；成员共享本机 `RELIC_HOME` |
| Relic App | 已包含源码；除非 PATH 上有 `msedge` 或 `chrome`，否则在默认浏览器中打开；未在 Mac 上测试 |
| 在 App 里运行的成员（ACP 适配器） | 已包含源码，需要 Node.js；未在 Mac 上测试 |
| 桌面快捷方式 | 仅 Windows；用 `python3 -X utf8 scripts/open_app.py` 打开 App |
| 唤醒被 Codex 桌面持有的聊天 | 不可用：当前通信实现只接受 Windows 命名管道 |
| ChatGPT 聊天成员 | macOS 不可用 |
| 成员卡片上的「打开会话」 | 未认证，请自行在 Terminal 恢复会话 |

本版不声称 Windows/macOS 桌面功能完全一致。自动测试检验可移植代码和受控测试替身，不等于测试过已登录的商业桌面应用。准确运行记录见 [验证记录](validation.md)。

## 后续 Mac 实机验证

在两个 Terminal 中使用相同的 Relic 数据目录，例如先分别执行 `export RELIC_HOME="$HOME/.relic"`，再启动宿主。Claude Code 创建 Relic 组织并记下 ID；Codex 用另一个成员名加入相同 ID。互发一条短消息并调用 `inbox`，从两边检查文档与任务后再开始更大任务。

CLI 持有的会话应与桌面应用正在持有写锁的聊天分开。显式读取 inbox 不需要桌面自动唤醒。希望完全手动推进时，在 App「概况」面板关掉「自动唤醒」开关。

诊断：`python3 scripts/doctor.py`。App：`python3 -X utf8 scripts/open_app.py`。备份、marketplace 路径更新、回滚和卸载见 [完整指南](guide.zh-CN.md)。
