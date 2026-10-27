# Windows 安装说明

[English](windows.en.md) · [完整使用指南](guide.zh-CN.md)

## 准备

- Python 3.11+ 已加入 PATH，运行 `python --version` 检查。标准 Python 安装通常包含 Tk；需要面板时用 `python -c "import tkinter"` 检查。
- Claude 版需要已登录的 Claude Code CLI（`claude --version`）；Codex 版需要支持插件命令且已登录的 Codex CLI（`codex --version`）。Bridge 默认安装到两边，也可选择单个宿主。
- Codex 桌面通信需要桌面应用及其自带 `codex-app-tools`；仅安装 CLI 不会提供桌面管道。Windows 安装器能发现桌面应用自带的 Codex CLI。
- 只有克隆源码或创建成员 worktree 才需要 Git。核心组织无需 Docker 或第三方 Python 包。

## 下载与安装

从 [Release 页面](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.2.0-beta.1) 下载 `relic-claude-windows-v0.2.0-beta.1.zip`、`relic-codex-windows-v0.2.0-beta.1.zip` 或 `relic-bridge-windows-v0.2.0-beta.1.zip`。可用 `Get-FileHash -Algorithm SHA256` 与 `SHA256SUMS.txt` 比较下载文件。

解压到长期保留的目录，例如 `C:\Tools\Relic\bridge`。在解压目录打开 PowerShell：

```powershell
python -X utf8 scripts/install.py
# Bridge：如果只准备好了 Codex
python -X utf8 scripts/install.py --host codex
```

也可使用 `./install.ps1`。若 PowerShell 脚本策略阻止启动，直接运行上面的 Python 命令，无需修改全局执行策略。源码仓库使用 `python scripts/install.py --edition bridge`，也可选 `claude` / `codex`。

开始新宿主会话，在插件设置中审阅 hooks。若 Codex 提示 hooks 功能关闭，请通过宿主支持的设置启用；安装器保留现有选择。同一个宿主应停用另一套 Relic，避免重复注入。保留解压后的源码目录。

## 验证与使用

```powershell
python scripts/doctor.py
# 仅 Bridge 下载包：Relic App（桌面聊天）
python scripts/open_app.py
# 仅 Bridge 或 Codex 下载包支持面板
python scripts/open_panel.py
```

Relic App 在本机 127.0.0.1 起一个服务，用 Microsoft Edge（或 Chrome）打开窗口。在窗口栏点「安装」可以装成独立应用，之后 `open_app.py` 会直接打开装好的应用。界面是中文。

源码仓库里的命令还需加 `--edition bridge` 或 `--edition codex`。Codex 面板请先在真实桌面聊天中调用一次 `org_panel`，保存当前宿主通信上下文。Claude 独立版没有独立面板，在 Claude Code 中用 `/relic:relic` 或自然语言发起。

让智能体报告 Relic 状态，创建小组织并交换一条消息，确认收件人真正读到了消息。测试强协议时，使用一个无害的匹配动作和一个不匹配动作；安装成功不代表 hooks 覆盖已验证。

当前窗口仍含中文界面标签。中英文使用文档均已提供，本内测版没有完成整个 GUI 的英文翻译。

## 常见问题

如果 `python` 打开 Microsoft Store，请安装 Python，或使用真实解释器的完整路径运行安装器。找不到 `codex` / `claude` 时，先安装并登录宿主。宿主更新导致桌面管道失效时，重开应用并从实际 Codex 聊天再次打开面板；不要为桌面持有的聊天启动第二个写入进程。

备份、升级和卸载见 [完整指南](guide.zh-CN.md)。安装器不会删除旧组织数据。
