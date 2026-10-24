# macOS 安装与内测范围

[English](macos.en.md) · [完整使用指南](guide.zh-CN.md)

## 准备

使用仍受维护的 Python 发行版，版本 **3.11+**，确保 Terminal 中有 `python3`。下载包包含 Python 源码，没有绑定 CPU 架构的二进制；Apple Silicon 和 Intel 都需要各自兼容的 Python 与宿主。本次发布没有认证两种架构上的真实桌面会话。

安装并登录 Claude Code 和/或 Codex，确认同一个 Terminal 中 `claude --version` / `codex --version` 可用。macOS 安装器依赖 CLI 位于 PATH。可选 Bridge/Codex 面板需要 Tk，用 `python3 -c 'import tkinter'` 检查；缺失时选用包含 Tk 的 Python 发行版。核心 MCP 工具不依赖面板。

## 安装下载包

从 [Release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.1.0-beta.1) 下载对应的 `relic-{claude,codex,bridge}-macos-v0.1.0-beta.1.tar.gz`。Bridge 示例：

```bash
mkdir -p "$HOME/Applications/Relic"
tar -xzf relic-bridge-macos-v0.1.0-beta.1.tar.gz -C "$HOME/Applications/Relic"
cd "$HOME/Applications/Relic/relic-bridge-macos-v0.1.0-beta.1"
bash install.command
```

用 `shasum -a 256 <压缩包>` 可与 `SHA256SUMS.txt` 比较下载内容。安装器会让 MCP 与 hooks 使用当前真实 `python3` 路径，不要求额外建立 `python` 别名。Bridge 只安装到一个宿主时使用 `bash install.command --host claude` 或 `--host codex`。

源码仓库运行 `bash install.command --edition bridge`。在 Terminal 中通过 `bash` 执行无需给下载的启动文件添加可执行权限。这是源码发行包，不是经过签名/公证的 macOS App 或 `.dmg` 安装镜像。

重开宿主或开始新会话，审阅 hook 信任，并确保同一宿主只启用一个 Relic 版本。保留解压目录。安装 CLI 或修改环境后，从 Finder 启动的桌面应用可能需要重新启动。

## macOS 内测版包含什么

| 功能 | 可用范围 |
| --- | --- |
| Claude Code 核心组织、消息、文档、任务、治理 | 已包含，宿主需要加载 hooks |
| Bridge 共享数据库与 Claude Code + Codex CLI 成员 | 已包含，两边共享本机 `RELIC_HOME` |
| Codex 原生子智能体组织 | 已包含，需宿主提供真实协作工具与身份元数据 |
| 可选 Tk 面板 | 已包含源码，需 Tk 和图形显示；完整真实宿主 GUI 流程未认证 |
| Codex 独立版直接桌面通信 | 使用宿主已有 app-tools；macOS 真实桌面集成未认证 |
| Bridge 唤醒被 Codex 桌面持有的聊天 | 不可用：当前通信实现只接受 Windows 命名管道 |
| Bridge ChatGPT 聊天转发 | macOS 不可用 |
| Bridge“打开 CLI 会话”便捷按钮 | 未认证，请自行在 Terminal 恢复会话 |

本版不声称 Windows/macOS 桌面功能完全一致。自动测试检验可移植代码和受控测试替身，不等于测试过已登录的商业桌面应用。准确运行记录见 [验证记录](validation.md)。

## 第一次跨宿主试用

在两个 Terminal 中使用相同的 Bridge 数据目录，例如先分别执行 `export RELIC_HOME="$HOME/.relic"`，再启动宿主。Claude Code 创建 Relic 组织并记下 ID；Codex 用另一个成员名加入相同 ID。互发一条短消息并调用 `inbox`，从两边检查文档与任务后再开始更大任务。

CLI 持有的会话应与桌面应用正在持有写锁的聊天分开。显式读取 inbox 不需要 Bridge 桌面自动唤醒。希望完全手动推进时，在面板关闭自动唤醒。

诊断：`python3 scripts/doctor.py`。Bridge/Codex 包面板：`python3 scripts/open_panel.py`。源码仓库需增加 `--edition`。备份、marketplace 路径更新、回滚和卸载见 [完整指南](guide.zh-CN.md)。
