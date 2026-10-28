# Windows 安装说明

[English](windows.en.md) · [完整使用指南](guide.zh-CN.md)

## 准备

- Python 3.11+ 已加入 PATH，运行 `python --version` 检查。
- 已经安装并登录的 Claude Code 和/或 Codex（`claude --version`、`codex --version`）。安装器会把插件加到每个找得到 CLI 的宿主，包括 Codex 桌面应用自带的 CLI。
- 在 Relic App 里运行的成员需要 Node.js（含 npm）：它们的 ACP 适配器在 App 的「设置 → Harness 连接」里安装（约 70 MB，装在 `~/.relic/acp`）。
- App 窗口需要 Microsoft Edge（或 Chrome）。语音输入使用 Edge 的在线语音识别。
- 唤醒 Codex 桌面应用里打开的对话，要经过该应用自己的工具管道；仅安装 CLI 不会提供这条管道。ChatGPT 聊天成员需要 ChatGPT 桌面应用在运行。
- 只有克隆源码或创建成员 worktree 才需要 Git。不需要 Docker 或第三方 Python 包。

## 下载与安装

从 [Release 页面](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.5.0-beta.1) 下载 `relic-windows-v0.5.0-beta.1.zip`。可用 `Get-FileHash -Algorithm SHA256` 与 `SHA256SUMS.txt` 比较下载文件。

解压到长期保留的目录，例如 `C:\Tools\Relic`。在解压目录打开 PowerShell：

```powershell
python -X utf8 scripts/install.py
# 只装到 Codex：
python -X utf8 scripts/install.py --host codex
```

| 选项 | 作用 |
| --- | --- |
| `--host auto` | 默认：找得到 CLI 的宿主都装 |
| `--host claude`、`--host codex`、`--host both` | 只装这些宿主；指定的宿主没装时报错停止 |
| `--host none` | 不装到任何宿主：只用 Relic App |
| `--configure-only` | 只准备这个目录，不改宿主，也不建快捷方式 |
| `--no-shortcut` | 不在桌面上建 Relic 快捷方式 |
| `--open` | 安装完成后打开 Relic App |

也可使用 `./install.ps1`，选项相同，写作 `-HostTarget`、`-ConfigureOnly`、`-NoShortcut`、`-Open`。若 PowerShell 脚本策略阻止启动，直接运行上面的 Python 命令，无需修改全局执行策略。

安装器用运行它的 Python 配置这个目录（插件的 MCP 服务和 hooks 使用这个解释器），执行 `<cli> plugin marketplace add <目录>`，再执行 `claude plugin install relic@relic-bridge` / `codex plugin add relic@relic-bridge`，尽力停用较早的 Claude Code 版本 `relic@relic-claude` 和 `relic@relic-local`，并在桌面上建一个名为 Relic 的快捷方式来打开 Relic App。较早的 Codex 版本（插件 `relic-organization`）工具和数据都不同，安装器不动它；不再使用时请在 Codex 里移除。安装器不下载、不调用模型、不做全局 hook 信任，也不改数据库。

开始新宿主会话，在插件设置中审阅 hooks。若 Codex 提示 hooks 功能关闭，请通过宿主支持的设置启用；安装器保留现有选择。保留解压后的目录。

从 v0.3.0-beta.1 升级：运行新安装器之前，先停掉 Relic App 的服务（进程号是 `~/.relic/app.json` 里的 `pid`）。装好后，在还开着的 Claude Code 会话里运行 `/reload-plugins`，并重启 Codex：Codex 启动时才载入它缓存的插件版本。组织照常保留，详见 [完整指南](guide.zh-CN.md) 第 9 节。

## 验证与使用

```powershell
python scripts/doctor.py
python -X utf8 scripts/open_app.py
```

`doctor.py` 报告 Python、Claude Code 与 Codex CLI、Node.js、ACP 适配器和配置的 MCP 服务路径。Relic App 在本机 127.0.0.1 起一个服务（端口 39321 或下一个空闲端口），用 Microsoft Edge（或 Chrome）打开窗口；桌面上的 Relic 快捷方式效果相同。在窗口栏点「安装」可以装成独立应用，之后 `open_app.py` 和快捷方式会直接打开装好的应用。

要让成员在 App 里运行，先在「设置 → Harness 连接」里安装 ACP 适配器，再用「添加成员」。这些成员只需要已经安装并登录的 Claude Code 或 Codex：App 会把 Relic 带进它们的会话。

让智能体报告 Relic 状态，创建小组织并交换一条消息，确认收件人真正读到了消息。测试强协议时，使用一个无害的匹配动作和一个不匹配动作；安装成功不代表 hooks 覆盖已验证。

App 界面有中文和英文，在「设置 → 语言与命名 → 语言」里选；默认「跟随系统」。

## 常见问题

如果 `python` 打开 Microsoft Store，请安装 Python，或使用真实解释器的完整路径运行安装器。找不到 `codex` / `claude` 时，先安装并登录宿主；使用 `--host auto` 时，安装器会跳过找不到的宿主。App 提示缺少 npm 或 Node.js 时，安装 Node.js，再到「设置 → Harness 连接」重新安装适配器。宿主更新导致桌面管道失效时，重开 Codex 应用；不要为桌面持有的聊天启动第二个写入进程。

备份、升级和卸载见 [完整指南](guide.zh-CN.md)。安装器不会删除旧组织数据。
