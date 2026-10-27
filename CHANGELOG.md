# Changelog / 更新记录

## v0.3.0-beta.1 — 2026-10-27

Third public beta. The three editions of v0.2.0-beta.1 are merged into one product, **Relic**: the Relic App and the Relic plugin for Claude Code and Codex, in one package. Plugin 0.14.0-beta.1. Windows only, as before; the macOS package is built in CI but not released.

- **One product.** Relic Bridge became Relic. Relic Claude 0.1.0-beta.1 and Relic Codex / GPT 0.6.0-beta.1 are no longer developed; all three editions stay downloadable from the [v0.2.0-beta.1 release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.2.0-beta.1). The plugin id stays `relic@relic-bridge`, so Bridge installs upgrade in place; its display name is now Relic.
- **The App is the bridge.** Members that run in the App are Claude Code or Codex sessions (ACP) inside it, started through the official adapters `@agentclientprotocol/claude-agent-acp@0.97.0` and `@agentclientprotocol/codex-acp@2.3.0`, installed from 设置 → Harness 连接 (npm, about 70 MB under `~/.relic/acp`, Node.js required). The App brings Relic into each session itself: a Claude Code session loads the plugin from the App's own folder, and a Relic plugin installed in Claude Code is switched off in that session, so tools and hooks run once; a Codex session uses Codex's own Relic plugin when it is enabled there, otherwise the App gives it the Relic MCP server. Each session is named by its seat: the App stores a token on the seat, and the server it starts carries the seat and the token (`RELIC_SEAT`, `RELIC_SEAT_TOKEN`). These members need only Claude Code or Codex itself, installed and signed in.
- **Other coding agents.** Adding one that speaks ACP is one entry in `plugins/relic/app/harness.py`; 设置 lists agents of the ACP registry under 以后接入 (CodeBuddy / WorkBuddy, GLM, Kimi, Qwen Code, Gemini CLI, OpenCode). For a session without Relic hooks the App does the hooks' work: it allows Relic's own tool calls, checks strong protocols when the session asks for permission (an action the session takes without asking cannot be stopped), records finished tool calls as activity, closes the turn and gives one short turn for a reflection that is due.
- **Adding members.** 添加成员 has three ways: 在 App 里运行 (a session the App hosts); 命令行或桌面版 (Claude Code or Codex itself, on the command line or in the desktop app, with model, reasoning effort, folder or a git worktree per member, permission and environment variables; Relic starts its sessions and wakes it); 已有会话 (a Claude Code session, Codex chat or ChatGPT chat already on this computer takes a seat). 文件 → 把已有会话放进组织… opens the last one directly.
- **Member card.** 开新会话 (a fresh session; role, tasks and protocols stay, private notes do not), 打开会话 (its terminal or desktop app), 改配置, 离开席位 (the session leaves, the seat stays), and for ChatGPT chat members 转发回复 (paste the reply copied from the ChatGPT window).
- **The Relic window is gone.** Everything the Tk Relic (Bridge) window did is in the App. The `panel` tool opens the App; `scripts/open_panel.py` is removed. Tk is no longer needed.
- **Installer.** `scripts/install.py` (or `install.ps1`; `bash install.command` on macOS) takes `--host auto|claude|codex|both|none` (default `auto`: every host whose CLI is found; `none`: the App alone; a named host that is not installed stops it with an error), `--configure-only`, `--no-shortcut` and `--open`. It configures the folder with the installing Python, removes an earlier registration of the `relic-bridge` marketplace (an older folder), runs `<cli> plugin marketplace add <folder>` and then `claude plugin install relic@relic-bridge` / `codex plugin add relic@relic-bridge`, disables the earlier Claude Code editions `relic@relic-claude` and `relic@relic-local` (best effort), and on Windows makes a desktop shortcut named Relic that opens the App. No downloads, model calls, global hook trust or database changes. `--edition` is gone.
- **Coming from the earlier editions.** Relic Bridge: organizations in `~/.relic` carry over. Relic Claude: the installer disables `relic@relic-claude`; its organizations in `~/.claude/relic/relic.sqlite3` are not converted. Relic Codex / GPT: the installer leaves the Codex plugin `relic-organization` alone (different tools and data); remove it in Codex if you no longer use it. Its data in `~/.codex/relic-organization` is not converted, and forming organizations from native Codex subagents, text meetings (`org_call`), quiet mode and the `require_peer_review` rule format have no counterpart in Relic.
- **Fixes.** A sent message no longer stays in the input box (group chat, private chats and threads); an organization founded outside the App while it shows none now opens in the App with its input box.
- **Release and checks.** One archive per platform: `relic-windows-v0.3.0-beta.1.zip` (published, with `SHA256SUMS.txt` and `release-manifest.json`) and the macOS `.tar.gz` (built, not released). `scripts/check.py --suite all|relic|packaging` replaces `--edition`; the CI commands are unchanged. `docs/api/relic.json` (11 tools) replaces `claude.json`, `codex.json` and `bridge.json`.

第三个公开内测版。v0.2.0-beta.1 的三个版本合并成一个产品 **Relic**：Relic App 加上给 Claude Code 和 Codex 用的 Relic 插件，放在同一个下载包里。插件 0.14.0-beta.1。仍然只发布 Windows；macOS 包在 CI 里构建，但不发布。

- **一个产品。**Relic Bridge 变成了 Relic。Relic Claude 0.1.0-beta.1 与 Relic Codex / GPT 0.6.0-beta.1 不再开发；三个版本仍可从 [v0.2.0-beta.1 Release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.2.0-beta.1) 下载。插件 id 仍是 `relic@relic-bridge`，Bridge 可以就地升级；显示名现在是 Relic。
- **App 就是桥。**在 App 里运行的成员是 App 里的 Claude Code 或 Codex 会话（ACP），通过官方适配器 `@agentclientprotocol/claude-agent-acp@0.97.0` 和 `@agentclientprotocol/codex-acp@2.3.0` 启动；适配器在「设置 → Harness 连接」里安装（npm，约 70 MB，装在 `~/.relic/acp`，需要 Node.js）。App 自己把 Relic 带进每个会话：Claude Code 会话从 App 自己的目录加载插件，并在这个会话里关掉 Claude Code 中已安装的 Relic 插件，工具和 hooks 只运行一份；Codex 会话在 Codex 里启用了 Relic 插件时用 Codex 自己的插件，否则由 App 给它 Relic MCP 服务。每个会话以它的席位命名：App 在席位上存一个令牌，它启动的服务带着席位和令牌（`RELIC_SEAT`、`RELIC_SEAT_TOKEN`）。这些成员只需要已经安装并登录的 Claude Code 或 Codex。
- **其他编程智能体。**接入一个支持 ACP 的智能体，只需在 `plugins/relic/app/harness.py` 里加一条；「设置」在「以后接入」下列出 ACP 注册表里的智能体（CodeBuddy / WorkBuddy、GLM、Kimi、Qwen Code、Gemini CLI、OpenCode）。对没有 Relic hooks 的会话，App 代做 hooks 的工作：放行 Relic 自己的工具调用，在会话请求权限时检查强协议（会话不请求权限就做的动作拦不住），把完成的工具调用记为活动，结束这一轮，并在该写反思时多给一轮简短回合。
- **添加成员。**「添加成员」有三种方式：「在 App 里运行」（由 App 托管的会话）；「命令行或桌面版」（在 Claude Code 或 Codex 本身里运行，命令行或桌面版，可设模型、推理强度、文件夹或每个成员一份的 git worktree、权限和环境变量；Relic 启动它的会话并唤醒它）；「已有会话」（把这台电脑上已有的 Claude Code 会话、Codex 对话或 ChatGPT 聊天放进席位）。「文件 → 把已有会话放进组织…」直接打开最后这一种。
- **成员卡片。**「开新会话」（换一个新会话；职责、任务和协议留下，私人笔记不带过去）、「打开会话」（在终端或桌面版里打开）、「改配置」、「离开席位」（会话离开，席位留着），ChatGPT 聊天成员还有「转发回复」（粘贴从 ChatGPT 窗口复制的回复）。
- **Relic 窗口去掉了。**原来 Tk 的 Relic（Bridge）窗口能做的事都在 App 里。`panel` 工具打开 App；`scripts/open_panel.py` 已删除。不再需要 Tk。
- **安装器。**`scripts/install.py`（或 `install.ps1`；macOS 用 `bash install.command`）接受 `--host auto|claude|codex|both|none`（默认 `auto`：找得到 CLI 的宿主都装；`none`：只用 App；指定的宿主没装时报错停止）、`--configure-only`、`--no-shortcut` 和 `--open`。它用运行安装器的 Python 配置目录，先移除指向旧目录的 `relic-bridge` marketplace 注册，再执行 `<cli> plugin marketplace add <目录>`，再执行 `claude plugin install relic@relic-bridge` / `codex plugin add relic@relic-bridge`，尽力停用较早的 Claude Code 版本 `relic@relic-claude` 和 `relic@relic-local`，并在 Windows 上建一个名为 Relic 的桌面快捷方式来打开 App。不下载、不调用模型、不做全局 hook 信任，也不改数据库。`--edition` 已取消。
- **从以前的版本过来。**Relic Bridge：`~/.relic` 里的组织照常保留。Relic Claude：安装器停用 `relic@relic-claude`；它在 `~/.claude/relic/relic.sqlite3` 里的组织不会被转换。Relic Codex / GPT：安装器不动 Codex 插件 `relic-organization`（工具和数据都不同），不再使用时请在 Codex 里移除；它在 `~/.codex/relic-organization` 里的数据不会被转换。用 Codex 原生子智能体组建组织、文字会议（`org_call`）、静默模式和 `require_peer_review` 规则格式，在 Relic 里没有对应功能。
- **修复。**发出的消息不再留在输入框里（群聊、私聊和话题都是）；App 里还没有组织时，在外面建的组织会直接在 App 里打开，输入框也会出现。
- **发布与检查。**每个系统一个下载包：`relic-windows-v0.3.0-beta.1.zip`（发布，附 `SHA256SUMS.txt` 和 `release-manifest.json`）和 macOS 的 `.tar.gz`（构建，不发布）。`scripts/check.py --suite all|relic|packaging` 取代 `--edition`；CI 命令不变。`docs/api/relic.json`（11 个工具）取代 `claude.json`、`codex.json` 和 `bridge.json`。

## v0.2.0-beta.1 — 2026-10-27

Second public beta. Relic Bridge 0.13.0-beta.1 adds the Relic App; Claude 0.1.0-beta.1 and Codex / GPT 0.6.0-beta.1 are unchanged. Windows only, as before.

- **Relic App** (Bridge): a desktop chat for Relic organizations. Group chat, secretary and private chats; a member's own session with its actions folded; threads and quotes; 人话 (plain-language versions of what members tell each other) and 解读 (a short digest of the group); a member's workspace and file preview; task reports; profile, appearance, language, voice input, notifications and harness connections in Settings; installable as an application with its own title bar. Open it with `python scripts/open_app.py`.
- Embedded members: members created in the App run Claude Code or Codex sessions inside it through the Agent Client Protocol (ACP); the adapters are installed from Settings.
- Threads: `message` takes `reply_to` to answer inside a message's thread.
- Task reports: marking a task done requires evidence and a short report (Markdown, at most 1000 characters); members write task titles and reports in the person's language.
- The MCP server serves several members' calls at once: one member's long `inbox` wait no longer holds up the others in the same session.
- Packaging builds Windows-only release assets with `scripts/package.py --platform windows`; CI gives each isolated suite more time.

第二个公开内测版。Relic Bridge 0.13.0-beta.1 加入 Relic App；Claude 0.1.0-beta.1 与 Codex / GPT 0.6.0-beta.1 不变。仍然只发布 Windows。

- **Relic App**（Bridge）：给 Relic 组织用的桌面聊天应用。群聊、秘书和成员私聊；成员自己会话里的全部对话，动作折叠；话题与引用；「人话」（把成员之间的话改写成看得懂的话）与「解读」（几句话讲清群里在干什么）；成员工作区与文件预览；任务完成报告；设置里有个人资料、外观、语言、语音输入、通知和 Harness 连接；可以装成有自己标题栏的独立应用。用 `python scripts/open_app.py` 打开。
- 内嵌成员：在 App 里新建的成员通过 Agent Client Protocol（ACP）在 App 里运行 Claude Code 或 Codex 会话；适配器在设置里安装。
- 话题：`message` 支持 `reply_to`，在某条消息的话题里回复。
- 任务报告：把任务标为完成必须附证据和一份简短报告（Markdown，最多 1000 字）；成员按人类的语言写任务标题和报告。
- MCP 服务可以同时处理多个成员的调用：同一会话里一个成员长时间等待 `inbox`，不再挡住其他成员。
- 打包可用 `scripts/package.py --platform windows` 只生成 Windows 发布文件；CI 给每套隔离测试更多时间。

## v0.1.0-beta.1 — 2026-10-24

First public beta distribution of the current internal Relic plugin family.

- Claude 0.1.0-beta.1, Codex / GPT 0.6.0-beta.1, Bridge 0.12.0-beta.1.
- Windows ZIP packages are published for all three editions. macOS downloads are withdrawn pending development completion and real Mac validation.
- Portable installer resolves Python/MCP/hook paths on the target computer; Claude MCP wiring and command-hook packaging are normalized.
- Bilingual user guides, OS-specific installation, tool schemas, data guidance and troubleshooting.
- Isolated tests avoid borrowing the invoking Codex session's identity or live organization store.
- macOS file opening uses the native `open` command; optional benchmark paths no longer default to a developer's drive.
- Fixed Bridge panel font initialization on macOS; GUI fixtures run in separate macOS processes to avoid Tk lifecycle hangs.
- Bridge macOS desktop auto-wake and ChatGPT chat relay are unavailable. Real desktop workflows, signed/notarized apps and a fully English GUI are outside this first beta's validation scope.

首次公开发布当前内部试用的 Relic 三版本插件：

- Claude 0.1.0-beta.1、Codex / GPT 0.6.0-beta.1、Bridge 0.12.0-beta.1。
- 三个版本仅公开发布 Windows ZIP；macOS 下载已撤下，待开发完善与真实 Mac 验证后再发布。
- 安装器解析使用者电脑上的 Python/MCP/hook 路径，补全 Claude MCP 注册并规范命令 hook。
- 提供完整中英文指南、两系统安装文档、工具 schema、数据说明和排错。
- 测试与当前 Codex 会话身份、真实组织数据库隔离。
- macOS 打开文件使用原生 `open`；可选基准路径不再指向开发者盘符。
- 修复 Bridge 面板在 macOS 的字体初始化；macOS GUI 测试使用独立进程，避免 Tk 生命周期造成阻塞。
- macOS Bridge 尚不支持桌面自动唤醒与 ChatGPT 聊天转发。本次未认证完整真实桌面流程，不提供已签名/公证 App，也未完成全英文 GUI。
