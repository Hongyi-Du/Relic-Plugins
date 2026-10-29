# Changelog / 更新记录

## v0.7.1-beta.1 — 2026-10-29

Plugin **0.18.1-beta.1**, based on the merged Windows/macOS v0.7.0 source.

- Hook delivery fits organization context and whole messages into 9500 characters before marking messages read.
  A preview or omitted message stays unread, with its id and an inbox recovery notice.
- `inbox message_id=<id>` rereads any message addressed to the session's selected seats, including read messages.
  An empty inbox lists open assigned tasks across those seats and points to `status`.
- Waiting stdio inbox calls observe cancellation and EOF on an independent input thread, including while an
  ordinary call holds the code lock. Messages are acknowledged only after a successful response write; cancelled
  or broken-pipe replies leave them unread. Transport tests synchronize waiter lifecycle events instead of sleeps.
- Auto-wake prompts name the context/inbox and status task list. Wake turns cannot take the manual `--open` path.
- Windows subprocess creation uses one no-console flag helper, including App-owned jobs and probes. Explicit
  manual CLI opening uses Windows Terminal without a separate launcher console. Tests mock that UI action and
  hide the checker fixture's child process. Release-layout App tests skip when `scripts/open_app.py` is absent.
- An explicit held seat takes precedence over upward reporting and qualified recipients, regardless of hierarchy.
  Threaded replies remain in the receiving seat's organization and deliver a copy to cross-organization participants.
- The installer gives Codex a Windows PowerShell command with the call operator for quoted Python paths;
  Claude's shell command stays separate. Codex receives the hook's already-capped additional context without
  a second host preview truncation (`additionalContextLimit: 0`).

基于合并后的 Windows/macOS v0.7.0 源码，插件版本为 **0.18.1-beta.1**。
修复 hook 截断后误标已读；新增按消息 ID 重读和空收件箱任务提示；统一 Windows 子进程隐藏标志，
阻止自动唤醒进入人工开窗路径，修正会实际打开终端的测试夹具，并覆盖上级席位回复场景。
本次不发布、不安装、不部署；真实桌面验收另行进行。

## v0.7.0-beta.1 — 2026-10-28

One Relic version for Windows and macOS on Apple silicon, plugin **0.18.0-beta.1**. The macOS port contributed by
**HaochenGu** is merged with v0.6.0; its original commits and authorship are retained. This is a release candidate in
source, with locally buildable packages. The earlier v0.4.1-macos prerelease, published during this
integration, remains available as a historical release; future development uses the unified version.

- **Shared features.** Both systems keep check programs, Copies to the person, Stop-hook rules on `Reply`, protocols
  issued by the person, sidebar subtree folding and the draggable/zoomable organization chart. Platform differences
  are limited to runtime discovery, native launchers, paths, process ownership and desktop transports.
- **macOS Apple silicon.** Native arm64 Python 3.11+, Node.js 22+ for ACP members, Finder launcher, Command shortcuts,
  Unicode/volume-aware file matching and conditional Codex/Claude desktop connections. Intel and Rosetta are outside
  the target; the source installer is unsigned and not notarized.
- **Common runtime improvements.** Locked ACP adapters (Node.js 22+ on both systems), isolated session identity,
  authenticated App lifecycle, numeric-loopback startup and owned-child cleanup. Check-rule reviews now retain the
  same working-directory and resolved-path binding as ordinary review rules.
- **Upgrade and rollback.** Back up the data directory before upgrading. First opening an older store automatically
  adds the `paths` column to `activity`, on Windows as well as macOS. This schema migration is irreversible by Relic:
  there is no automatic downgrade, and replacing code does not remove the column. Restore a pre-upgrade backup to
  roll back. Existing rows are preserved; older writers leave `paths` null and retain the legacy interpretation.
- **Validation.** HaochenGu recorded a real Apple silicon v0.4.1-based installation/lifecycle check and signed-in
  Claude writer/Codex reviewer workflow (tasks, messages and document revision). Those observations precede this
  merge. Merged-version automated Windows/macOS results are recorded in [validation](docs/validation.md); the merged
  version has not been accepted with signed-in hosts on a real Mac. Native desktop delivery, full browser interaction,
  all governance/hook cases and cancellation/resume/sleep still need that acceptance.
- **Packages.** One source produces `relic-windows-v0.7.0-beta.1.zip` and `relic-macos-v0.7.0-beta.1.tar.gz` (optional
  macOS ZIP), with platform-specific installation instructions, executable launchers, checksums and source manifests.

Windows 与 Apple silicon macOS 统一为 **v0.7.0-beta.1**，插件 **0.18.0-beta.1**。
**HaochenGu** 贡献的 macOS 移植与 v0.6.0 合并，保留原始提交和作者。集成期间已发布的旧 v0.4.1-macos 保留为历史版本，后续使用统一版本。
当前为源码候选版，可本地构建检查包。

- **共同功能。**两端都保留检查程序、给人的抄送、Stop hook 的 `Reply` 规则、人下发协议、侧栏子树折叠及
  可拖动缩放的组织关系图。系统差异只在运行环境查找、原生启动器、路径、进程管理和桌面通信层。
- **Mac 适配。**支持原生 arm64 Python 3.11+、Finder 启动器、Command 快捷键、Unicode 与卷大小写匹配，
  桌面连接按本机能力启用。Intel/Rosetta 不在目标内；源码安装包未经签名或公证。
- **共同运行时。**锁定 ACP 适配器，两端 App 内成员均需 Node.js 22+；隔离会话身份，认证服务启停，避免
  回环 DNS 阻塞，并清理自己启动的进程。检查程序返回审核时也绑定工作目录与解析后的文件路径。
- **升级与回退。**升级前备份数据目录。两端首次打开旧库都会给 `activity` 增加 `paths` 列；这是不可逆的
  自动迁移，没有自动降级，换回旧代码不会撤销它。回退需恢复升级前备份。已有记录保留，旧写入方留下的
  空字段继续按旧方式读取。
- **验证范围。**HaochenGu 在真实 Apple silicon Mac 上记录了 v0.4.1 基础版的安装、生命周期和已登录
  Claude/Codex 成员的任务、消息与文档修订。这些是合并前证据。合并版 Windows/macOS 自动测试见
  [验证记录](docs/validation.md)；合并版尚未完成已登录真机验收，桌面投递、完整浏览器交互、全部治理与
  hooks、取消/恢复/休眠仍待验证。
- **打包。**同一源码生成 Windows ZIP 与 macOS tar.gz（可选 ZIP），提供对应系统的安装说明、启动器、
  校验文件与来源清单。

## v0.6.0-beta.1 — 2026-10-28

Sixth public beta. A strong protocol can judge the reply that ends a member's turn, and a protocol the person issues takes effect at once, with no vote. Plugin 0.17.0-beta.1; the plugin id stays `relic@relic-bridge`. Windows only, as before.

- **Rules on the reply that ends a turn.** A rule can name `Reply` instead of tools (`tools: ["Reply"]`, effect `check` or `deny`, no other tool and no `path_glob`). It judges the reply that ends a member's turn, the text the person reads, when the turn ends: the Stop hook gives the rule `{"tool": "Reply", "input": {"text": ...}}` (Claude Code and Codex both pass that reply to the hook). When the reply breaks the rule, the member is sent back once with the reason and writes the whole reply again. A program on Reply answers allow or deny; a subagent's reply is not judged. "Reports to the person in Simplified Chinese" is such a rule.
- **Protocols the person issues.** The person puts a protocol into effect in any organization at once, with no vote: what the person asks for is final. With `inherit`, every organization below is bound too. No member and no organization can revise, override or retire it; only the person retires it. The Relic App's server takes it at `POST /api/org/<org id>/protocols` with the App's token, so a session working for the person can issue what the person asked for. The group chat says that you issued it and that it is in effect, and the organization's protocols show it as issued by you.
- **Upgrading.** As before: stop the Relic App's server, extract the new package and run its installer; nothing in the store changes. Run `/reload-plugins` in Claude Code sessions that are already open, and restart Codex. Rules on Reply need 0.17.0 wherever Relic's hooks run: older versions ignore them.
- **Release and checks.** `relic-windows-v0.6.0-beta.1.zip` (published, with `SHA256SUMS.txt` and `release-manifest.json`) and the macOS `.tar.gz` (built, not released). `docs/api/relic.json` lists 12 tools; a rule takes `Reply`.

第六个公开内测版。强协议可以检查成员每轮最后给人的回复；人下发的协议立即生效，不需要表决。插件 0.17.0-beta.1，插件 id 仍是 `relic@relic-bridge`。仍然只发布 Windows。

- **检查每轮最后的回复。**规则可以写 `Reply` 代替工具名（`tools: ["Reply"]`，`effect` 是 `check` 或 `deny`，不能再写别的工具，也不能用 `path_glob`）。它管的是成员每轮结束时给人的那段回复：一轮结束时，Stop hook 把 `{"tool": "Reply", "input": {"text": ...}}` 交给规则（Claude Code 和 Codex 都会把这段回复交给 hook）。回复不合格时，成员会带着原因被打回一次，重写整段回复。Reply 上的判断程序只回答放行或拦下；子代理的回复不检查。「给人汇报一律用简体中文」就是这样一条规则。
- **人下发的协议。**人可以在任何组织直接下发协议，立即生效，不需要表决：人的要求就是最终决定。带上 `inherit`，下面所有组织一起受约束。成员和任何组织都不能修订、覆盖或废除它，只有人能废除。Relic App 的服务在 `POST /api/org/<组织 id>/protocols` 接收（要带 App 的口令），所以替人干活的会话可以按人的要求下发。群聊里写明是你下发的、已经生效，组织的协议列表里标着「由你下发」。
- **升级。**照旧先停掉 Relic App 的服务，再解压新下载包、运行其中的安装器；数据库不变。已经开着的 Claude Code 会话里运行 `/reload-plugins`，并重启 Codex。Reply 规则要求所有跑 Relic hooks 的地方都用 0.17.0，旧版本会忽略它。
- **发布与检查。**`relic-windows-v0.6.0-beta.1.zip`（发布，附 `SHA256SUMS.txt` 和 `release-manifest.json`）和 macOS 的 `.tar.gz`（构建，不发布）。`docs/api/relic.json` 列出 12 个工具；规则多了 `Reply`。

## v0.5.1-beta.1 — 2026-10-28

A small update to v0.5.0-beta.1. Plugin 0.16.1-beta.1; the plugin id stays `relic@relic-bridge`. Windows only, as before.

- **Folding in the sidebar.** Folding an organization now hides everything under it: its group chat, its members and every organization below it, at any depth. The arrow in front of an organization folds and unfolds it; its name opens it, or folds and unfolds it when it is already open. Folding is kept across a reload. Opening an organization from elsewhere (the organization chart, a link, a name card) unfolds the organizations above it so that it shows; a search shows every match, folded or not.
- **Upgrading.** As before: stop the Relic App's server, extract the new package and run its installer; nothing in the store changes. Reload the Relic App's window. Run `/reload-plugins` in Claude Code sessions that are already open, and restart Codex.
- **Release and checks.** `relic-windows-v0.5.1-beta.1.zip` (published, with `SHA256SUMS.txt` and `release-manifest.json`) and the macOS `.tar.gz` (built, not released). `docs/api/relic.json` is unchanged: 12 tools.

v0.5.0-beta.1 的小更新。插件 0.16.1-beta.1，插件 id 仍是 `relic@relic-bridge`。仍然只发布 Windows。

- **侧栏折叠。**折叠一个组织时，它下面的所有东西一起收起：群聊、成员，以及它下面各层的组织。组织前面的箭头负责折叠和展开；点组织名打开它，已经打开的组织再点名字就折叠或展开。折叠状态刷新后保留。从别处打开一个组织（组织关系图、链接、成员名片）时，它上面的组织自动展开，让它露出来；搜索时不论是否折叠，所有匹配都显示。
- **升级。**照旧先停掉 Relic App 的服务，再解压新下载包、运行其中的安装器；数据库不变。刷新 Relic App 的窗口。已经开着的 Claude Code 会话里运行 `/reload-plugins`，并重启 Codex。
- **发布与检查。**`relic-windows-v0.5.1-beta.1.zip`（发布，附 `SHA256SUMS.txt` 和 `release-manifest.json`）和 macOS 的 `.tar.gz`（构建，不发布）。`docs/api/relic.json` 没有变化，仍是 12 个工具。

## v0.5.0-beta.1 — 2026-10-28

Fifth public beta. A strong protocol can now run a check program its members wrote, and a protocol with one is copied to you when it takes effect. Plugin 0.16.0-beta.1; the plugin id stays `relic@relic-bridge`. Windows only, as before.

- **Check rules.** A strong protocol's rule can have the effect `check`: a Python program its members wrote (standard library only) that answers `allow`, `deny` or `review`, with a reason, for each tool call the rule covers. It is for problems the other rules cannot express: what a member did before, in what order, how long ago. The rule names its tools (not every tool) and carries `code`, 2 to 12 `examples` (calls the rule covers, at least one allowed and one denied or sent for review) and `on_error` (`allow`, the default, or `deny`). When the protocol is proposed, the code is compiled, its imports are checked, and every example runs and has to come out as expected; the code's sha256 is recorded and compared before every run. Members read a proposal's code and examples with `protocol op=list protocol_id=<P#>` before they vote. A program gets the call (tool, input, member, role, harness, organization, protocol), the member's latest 20 tool calls in the organization, the time of its latest edit and the current time.
- **How a program runs.** In a process of its own: the same Python with `-I -S -X utf8`, at most 3 seconds and 8 KB of answer, a temporary folder and almost no environment; on Windows a job object ends whatever the program starts and caps its memory at 512 MB. Several programs on one call run side by side. A timeout, an exception, an invalid answer or a crash follows `on_error`, is recorded, and is announced in the group chat of the protocol's organization, once a day per protocol and kind of failure; members see it in `status`. Allowed calls are only counted; blocks, reviews and failures go to the organization's event log. This is not a security sandbox: members review the code, and you can retire the protocol at once.
- **Copies to you.** A protocol with a check rule takes effect by the organization's vote (or as issued from above) without waiting for you, and a copy reaches you with `summary_for_person`, a description in your language that the proposal must include. Revisions are copied too. In the Relic App, Copies next to the notification bell shows how many are unread. Each card has the organization, the protocol, the description, who proposed it and who voted for it, when it took effect and how often its program allowed, blocked, sent for review or failed; the code and examples are folded below. Got it marks a copy read. Retire this protocol, after a confirmation, retires it at once, here and in the organizations below that inherit it, with no vote; their group chats get a notice and members see it in `status`.
- **Upgrading.** As before: stop the Relic App's server, extract the new package and run its installer. On first use the store adds the tables `cc`, `check_counts` and `check_alerts`; nothing else changes. Run `/reload-plugins` in Claude Code sessions that are already open, and restart Codex. Every place that runs Relic's hooks needs 0.16.0: older versions treat a `check` rule as `require_review` and ask for a review on every call it covers. Installed with the same Python as before, the Relic hooks keep the trust you gave them in Codex.
- **Release and checks.** `relic-windows-v0.5.0-beta.1.zip` (published, with `SHA256SUMS.txt` and `release-manifest.json`) and the macOS `.tar.gz` (built, not released). `docs/api/relic.json` lists 12 tools; `protocol` takes `summary_for_person`, and its rules take `check`.

第五个公开内测版。强协议可以运行成员自己写的判断程序；带判断程序的协议生效时抄送给你。插件 0.16.0-beta.1，插件 id 仍是 `relic@relic-bridge`。仍然只发布 Windows。

- **check 规则。**强协议的规则多了一种 `effect`：`check`，一段成员自己写的 Python 程序（只用标准库），对规则管的每次工具调用回答 `allow`、`deny` 或 `review`，并给出原因。它用来处理其他规则表达不了的问题：成员之前做过什么、先后顺序、隔了多久。规则要写明管哪些工具（不能是全部工具），并带 `code`、2 到 12 个 `examples`（这条规则管得到的调用，至少一个放行、一个拦下或送审）和 `on_error`（默认 `allow`，或 `deny`）。提交协议时编译代码、检查 import，逐个运行例子，结果必须和预期一致；同时记下代码的 sha256，每次运行前核对。成员投票前用 `protocol op=list protocol_id=<P#>` 读提案的代码和例子。程序拿到的是这次调用（工具、输入、成员、角色、宿主、组织、协议）、这个成员在本组织最近 20 次工具调用、最近一次改文件的时间和当前时间。
- **程序怎么运行。**在单独的进程里：同一个 Python 加 `-I -S -X utf8`，最多 3 秒、回答最多 8 KB，临时目录，几乎不带环境变量；Windows 上用 job object 结束程序启动的所有进程，内存上限 512 MB。同一个调用碰上几个程序时并行跑。超时、抛异常、返回不合法或崩溃都按 `on_error` 处理，记一条事件，并在协议所属组织的群聊里提示，同一协议同一类错误一天只提示一次；成员的 `status` 里也看得到。放行只计数；拦下、送审和出错记进组织的事件日志。这不是安全沙箱：靠成员互审代码，你也可以随时废除。
- **抄送给你。**带 check 规则的协议由组织投票通过（或由上级下发）即生效，不等你批，同时抄送一份给你，附 `summary_for_person`：提案必须带的、用你的语言写的说明。修订版生效时也抄送。Relic App 铃铛旁边的「抄送」显示未读数；每张卡片写明组织、协议、说明、谁提的、谁投票通过、何时生效，以及程序放行、拦下、送审、出错各多少次；代码和例子折叠在下面。「知道了」标为已读；「废除这条协议」确认后立即废除，本组织和继承它的下级组织一起失效，不需要投票；群聊里有通知，成员在 `status` 里也看得到。
- **升级。**照旧先停掉 Relic App 的服务，再解压新下载包、运行其中的安装器。第一次使用时数据库加上 `cc`、`check_counts`、`check_alerts` 三张表，别的不变。已经开着的 Claude Code 会话里运行 `/reload-plugins`，并重启 Codex。所有跑 Relic hooks 的地方都要用 0.16.0：旧版本把 `check` 规则当成 `require_review`，它管的每次调用都要求别人审核。用和上次相同的 Python 安装时，Codex 里对 Relic hooks 的信任会保留。
- **发布与检查。**`relic-windows-v0.5.0-beta.1.zip`（发布，附 `SHA256SUMS.txt` 和 `release-manifest.json`）和 macOS 的 `.tar.gz`（构建，不发布）。`docs/api/relic.json` 列出 12 个工具；`protocol` 多了 `summary_for_person`，规则多了 `check`。

## v0.4.1-macos-beta.1 — 2026-10-28

First macOS Apple silicon prerelease, based on the tested v0.4.1-beta.1 codebase. Plugin
0.15.1-macos-beta.1; the plugin id stays `relic@relic-bridge`. The newer Windows v0.6.0-beta.1
release remains separate; this release does not include its newer protocol and reply-check features.

- **Native Apple silicon installation.** arm64 Python 3.11+ and Node.js 22+ checks; PATH, Homebrew,
  nvm and Volta executable discovery; a Finder launcher at `~/Applications/Relic.app`.
- **App and member lifecycle.** One server per data directory, authenticated status/stop/restart,
  port reuse and cleanup of owned adapter processes. Locked Claude/Codex ACP dependencies.
- **macOS files and interaction.** Finder/Terminal launching, Command-key shortcuts and POSIX file
  links; volume-aware case matching, Unicode/symlink handling and structured activity paths.
- **Desktop connections.** Codex/ChatGPT Unix sockets and Claude Desktop delivery are conditional
  on local capability and host authorization checks. App-managed and CLI members work independently.
- **Distribution.** ZIP and tar.gz source installers, SHA256 checksums and a manifest recording the
  source commit. Packages and committed launch templates contain no installation-specific paths.
- **Validation.** A real signed-in Claude writer/Codex reviewer organization completed tasks,
  shared document revision and message round trips. Local Python 3.11 and 3.13 suites each passed
  406 tests with two Windows-only skips. Extracted ZIP installation and server lifecycle passed.
  See [validation](docs/validation.md) for scope and remaining interactive coverage.

首个 macOS Apple silicon 测试版，基于已验证的 v0.4.1-beta.1，插件版本为
0.15.1-macos-beta.1。Windows v0.6.0-beta.1 独立保留，本版不包含其新增的协议与回复检查功能。
新增原生 arm64 环境检测、Finder 启动器、进程与服务生命周期管理、锁定版本的 ACP 适配器、
macOS 文件路径处理及快捷键。真实 Claude/Codex 成员已完成任务、共享文档修订与消息往返；
ZIP 解压安装及启动、状态、重启、停止检查通过。桌面自动投递仍需通过本机宿主能力验证。
提供 ZIP、tar.gz、SHA256 校验及来源清单；属于未签名的源码安装包，面向 Apple silicon。

## v0.4.1-beta.1 — 2026-10-28

A small update to v0.4.0-beta.1. Plugin 0.15.1-beta.1; the plugin id stays `relic@relic-bridge`. Windows only, as before.

- **An organization chart you can move and zoom.** The chart's dialog is as wide as the window and opens with the chart fitted to it. Drag to move it (a drag that starts on an organization does not open it), scroll or pinch to zoom around the pointer, and double-click empty space to fit it again. Its title bar has Zoom out, the percentage (click it for 100%), Zoom in and Fit to window; the keys + − 0 and the arrows work too. A narrow window still lists the organizations, indented.
- **Opened from an organization.** Right-click an organization in the sidebar and choose Organization chart…: the chart opens on that organization and the ones below it (a single organization at 100%, centered). The link in the Overview's Hierarchy block opens it on the open organization; View → Organization chart… shows everything.
- **Fix.** In English, the Organization details button at the bottom of the Overview was wider than the pane, which then scrolled sideways; its label now wraps.
- **Upgrading.** As before: stop the Relic App's server, extract the new package and run its installer; nothing in the store changes. Run `/reload-plugins` in Claude Code sessions that are already open, and restart Codex. Installed with the same Python as before, the Relic hooks keep the trust you gave them in Codex.
- **Release and checks.** `relic-windows-v0.4.1-beta.1.zip` (published, with `SHA256SUMS.txt` and `release-manifest.json`) and the macOS `.tar.gz` (built, not released). `docs/api/relic.json` is unchanged: 12 tools.

v0.4.0-beta.1 的小更新。插件 0.15.1-beta.1，插件 id 仍是 `relic@relic-bridge`。仍然只发布 Windows。

- **组织关系图可以拖动和缩放。**关系图的窗口和 App 一样宽，打开时整张图缩放到放得下。拖动可以移动（从某个组织上开始拖也不会打开它），滚轮或双指捏合以指针为中心缩放，双击空白处重新适应窗口。标题栏有「缩小」、百分比（点一下回到 100%）、「放大」和「适应窗口」；键盘的 + − 0 和方向键也能用。窗口很窄时照旧按缩进列出各组织。
- **从组织上打开。**在侧栏的组织上点右键，选「组织关系图…」：关系图先显示这个组织和它下面的组织（单个组织按 100% 居中）。「概况 → 上下级」里的链接打开时对准当前组织；「视图 → 组织关系图…」显示全部。
- **修复。**英文界面里，「概况」底部的组织详情按钮比面板还宽，面板会横向滚动；现在按钮文字会换行。
- **升级。**照旧先停掉 Relic App 的服务，再解压新下载包、运行其中的安装器；数据库不变。已经开着的 Claude Code 会话里运行 `/reload-plugins`，并重启 Codex。用和上次相同的 Python 安装时，Codex 里对 Relic hooks 的信任会保留。
- **发布与检查。**`relic-windows-v0.4.1-beta.1.zip`（发布，附 `SHA256SUMS.txt` 和 `release-manifest.json`）和 macOS 的 `.tar.gz`（构建，不发布）。`docs/api/relic.json` 没有变化，仍是 12 个工具。

## v0.4.0-beta.1 — 2026-10-27

Fourth public beta. The Relic App is in English as well as Chinese, and organizations can stand above and below one another, with subgroups, a secretariat and sessions that sit in several organizations. Plugin 0.15.0-beta.1; the plugin id stays `relic@relic-bridge`. Windows only, as before; the macOS package is built in CI but not released.

- **English interface.** The Relic App's interface and the texts its server writes (group chat notices, member states, errors) are in English or Chinese: Settings → Language and names → Language, where System default follows the system's language. The same setting still sets the language of members' default names, Plain words, Digest and voice input. The words live in two word lists, `relic_core/locales/en-US.json` and `zh-CN.json`, which the page and the server both read; the code holds only their keys.
- **Organizations above and below.** You place an organization under another in the App (Overview → Hierarchy → Parent organization); members can ask for a move with `group op=reparent` (see the secretariat below). Members of an organization above, at any depth, see the ones below, write to their members (who are woken as usual), assign and update their tasks, read their documents and issue protocols there that take effect at once, without a vote; only an organization above can revise or retire such a protocol. Members below only report upward. `status`, `message`, `work` and `protocol` take `org` (an organization's id or exact name); a message from another organization names its sender `<org id>/<member>`. What is done across organizations is recorded on both sides: the group chat below shows who did it as “member (organization)”, and the organization above keeps a notice. The sidebar shows the organizations as a tree, and an organization's Overview lists the ones right below it with their decisions, blocked tasks and work in progress.
- **Which protocols bind.** A protocol binds its own organization only, unless it is proposed with `inherit: true` (`downward: true` is accepted too): then the organizations below inherit it, and its strong rules are enforced on their members' tool calls. As with classes, an organization below can override an inherited protocol (`supersedes: "<org id>/<P#>"`) or stop it (`retire_target: "<org id>/<P#>"`) for itself and those below it, by its own vote; a protocol issued from above stays as issued. A member follows the protocols of the organization whose work it is doing; acting in an organization below with `org` keeps its own organization's protocols. The Overview lists inherited protocols and strikes through those overridden or stopped.
- **One session, several seats.** A session can hold a seat in several organizations and gets the messages of each; one that reached another seat names its organization (`[msg 12 · <organization> from <sender>]`) and is answered with `org`. The main seat acts when a call names no `org`; with `org` naming an organization the session sits in, any Relic tool acts as its member there, and that organization's protocols bind the session until the turn ends. A session takes one turn at a time. `join` into another organization now adds a seat instead of moving the session; joining one it already sits in makes that its main seat. In the App, Existing session keeps the session's other seats, Leave seat leaves only that organization, and a member's card lists the others under Also in. A session the App runs (Run in the App) holds one seat only for now.
- **Formal organizations and subgroups.** Standing organizations are formal organizations; every existing organization is one. A subgroup is made for one piece of work with the new `group` tool: `group {op: "create", name, purpose, leader, parent?, members?}`. `parent` defaults to the organization the member acts in, and the subgroup inherits what passes down from it; its members default to every member of the formal organization at or above `parent`, each seated in it with the same session and name, and `leader` leads it. Any member of `parent` can make one, without approval. Its leader closes it with `group {op: "close"}`, and so can you (Close subgroup); its record stays, and the subgroups below it close too.
- **The secretariat (cabinet) and the secretary-general.** You mark one formal organization as the secretariat (Hierarchy → Make this the secretariat (cabinet)); its leader is the secretary-general. A member's request to create a formal organization (`create`), move one (`group op=reparent`), change its leader (`group op=leader`) or dissolve it (`group op=dissolve`) then waits for the secretary-general, who decides with `group op=approve|deny`; the request also appears under Needs your decision in the App, with Approve and Deny, so you can decide it too. The secretary-general's own changes take effect at once. Without a secretariat, `create` works as before and the other requests wait for you. Your own changes in the App (parent, leader, secretariat, closing a subgroup) take effect at once.
- **Ex officio seats.** The leader of every leader-led formal organization holds a seat ex officio in the formal organization right above it and in the secretariat, carried by its own session, with the role “Head of <department>”; the seats follow a change of leader or parent. A leader whose session has not sat yet, or that runs in the App, gets an empty seat. Peer organizations and subgroups have none.
- **Organization chart.** View → Organization chart… draws every organization as a tree: formal organizations in solid frames, subgroups in dashed ones, closed ones grayed, the secretariat highlighted, each with its leader, members and pending decisions. A session that sits in several organizations links them with a thin dashed line, marked Shared. Clicking an organization opens it.
- **Tools.** 12 tools: `group` is new (`create`, `close`, `reparent`, `leader`, `dissolve`, `approve`, `deny`, `list`). `inbox`, `episode`, `review` and `trajectory` take `org` too, naming an organization the session sits in.
- **Fix.** Opening another organization starts the right pane at its top instead of at the previous organization's scroll position.
- **Upgrading.** Install over v0.3.0-beta.1 as before; the plugin id is unchanged. Stop the Relic App's server first (`pid` in `~/.relic/app.json`), or the App keeps running the old version. Organizations carry over: on first use the store adds the tables `seats` and `focus` and keeps each session's seat as its main seat; existing organizations are formal organizations without a parent, and there is no secretariat, so nothing else changes until you set a parent or mark a secretariat. Marking one gives the leader of every leader-led formal organization a seat in it. In a Claude Code session that is already open, run `/reload-plugins` or start a new session to get the new tools and arguments. Codex keeps each plugin version in its own folder (`~/.codex/plugins/cache/relic-bridge/relic/<version>`) and loads the plugin when it starts: restart Codex after installing to use 0.15.0-beta.1. Until then its sessions may still use 0.14.0-beta.1, without `group` or `org` and without enforcing protocols inherited from above.
- **Release and checks.** `relic-windows-v0.4.0-beta.1.zip` (published, with `SHA256SUMS.txt` and `release-manifest.json`) and the macOS `.tar.gz` (built, not released). `docs/api/relic.json` lists 12 tools.

第四个公开内测版。Relic App 有了英文界面；组织之间可以有上下级，还有子组、秘书处，一个会话也可以坐在几个组织里。插件 0.15.0-beta.1，插件 id 仍是 `relic@relic-bridge`。仍然只发布 Windows；macOS 包在 CI 里构建，但不发布。

- **英文界面。**Relic App 的界面和服务端写出的文字（群聊里的通知、成员状态、报错）都可以是中文或英文：在「设置 → 语言与命名 → 语言」里选，默认「跟随系统」。这个设置照旧也决定成员的默认名字、「翻译成人话」「解读」和语音输入用的语言。界面文字放在两份语言包里：`relic_core/locales/zh-CN.json` 和 `en-US.json`，页面和服务端读同一份，代码里只写键。
- **上级组织和下级组织。**你在 App 里把一个组织放到另一个组织下面（「概况 → 上下级 → 上级组织」）；成员要改上级，用 `group op=reparent` 提申请（见下面的秘书处）。上级组织（隔几层也算）的成员可以查看下级组织，给下级成员发消息（照常自动唤醒），在下级派任务、改任务、读文档，并给下级下发协议：不用投票、直接生效，只有上级能修订或废止。下级成员只能向上汇报。`status`、`message`、`work`、`protocol` 多了 `org` 参数（组织 id 或准确的名字）；别的组织发来的消息，发件人写作 `<组织 id>/<成员名>`。跨组织的操作两边都留痕：下级群聊里写明是谁做的（「成员（组织名）」），上级组织里也记一条。侧栏按上下级排成树；组织的「概况」列出直属下级的待决定、受阻和进行中的数量。
- **守哪套规则。**协议默认只在本组织生效；提协议时带 `inherit: true`（也接受 `downward: true`），下面的组织才继承它，强协议的规则也对下级成员的工具调用执行。像类的继承一样，下级组织可以用自己的投票覆盖继承来的协议（`supersedes: "<组织 id>/<P#>"`）或停用它（`retire_target: "<组织 id>/<P#>"`），只影响这一层和它下面；上级下发的协议照旧不能改。成员做哪个组织的事，就守哪个组织的规则；用 `org` 到下级组织做事时，守的仍是自己组织的规则。「概况」列出继承来的协议，被覆盖或停用的划掉。
- **一个会话坐多个席位。**一个会话可以同时是几个组织的成员，几边的消息都收得到；不是主席位收到的消息写明组织（`[msg 12 · <组织> from <发件人>]`），回复时带上 `org`。调用工具不写 `org` 时用主席位；`org` 写自己坐着的组织时，任何 Relic 工具都以那里的成员身份做事，这一轮结束前守那个组织的规则。同一个会话一次只跑一个回合。`join` 另一个组织现在是多坐一个席位，不再把会话从原组织搬走；再 `join` 已经坐着的组织，就把它设为主席位。App 里，「已有会话」保留会话的其他席位，「离开席位」只离开这一个组织，成员名片在「也在」里列出其他席位。在 App 里运行的会话（「在 App 里运行」）暂时只能坐一个席位。
- **正式组织和子组。**长期的组织是正式组织，已有的组织都算。子组为一件具体的事而建，用新工具 `group`：`group {op: "create", name, purpose, leader, parent?, members?}`。`parent` 默认是成员当前所在的组织，子组继承从它往下传的协议；成员默认是 `parent`（或它上面最近的正式组织）的全体成员，各自用同一个会话、同一个名字在子组里多坐一个席位，由 `leader` 当负责人。`parent` 的任何成员都能建，不用审批。负责人用 `group {op: "close"}` 关闭子组，你也可以点「关闭子组」；记录保留，它下面的子组一起关闭。
- **秘书处（内阁）和秘书长。**你把一个正式组织标成秘书处（「上下级 → 设为秘书处（内阁）」），它的负责人就是秘书长。之后成员新建正式组织（`create`）、改上级（`group op=reparent`）、换负责人（`group op=leader`）或解散（`group op=dissolve`），都要等秘书长用 `group op=approve|deny` 决定；申请也出现在 App 的「需要你决定」里，带「同意」「拒绝」，你也可以直接批。秘书长自己的改动直接生效。没有秘书处时，`create` 照旧直接建，其他申请由你批。你在 App 里做的改动（上级、负责人、秘书处、关闭子组）都直接生效。
- **因职务席位。**每个领导制正式组织的负责人，自动在直属上级正式组织和秘书处各有一个因职务席位，由它自己的会话坐，角色是「<部门名> 负责人」；换负责人或改上级时跟着变。负责人的会话还没入座、或它在 App 里运行时，这个席位先空着。同侪制组织和子组没有因职务席位。
- **组织关系图。**「视图 → 组织关系图…」把所有组织画成一棵树：正式组织实线框，子组虚线框，关闭的变灰，秘书处高亮，每个节点写负责人、成员数和待决定数。同一个会话坐在几个组织里的，用细虚线连起来，标「兼任」。点节点就打开那个组织。
- **工具。**一共 12 个工具，新增 `group`（`create`、`close`、`reparent`、`leader`、`dissolve`、`approve`、`deny`、`list`）。`inbox`、`episode`、`review`、`trajectory` 也接受 `org`，指自己坐着的组织。
- **修复。**打开另一个组织时，右侧栏从顶部开始，不再停在上一个组织的滚动位置。
- **升级。**照旧在 v0.3.0-beta.1 上就地安装，插件 id 不变。先停掉 Relic App 的服务（`~/.relic/app.json` 里的 `pid`），否则 App 还在跑旧版本。组织照常保留：第一次使用时，数据库加上 `seats` 和 `focus` 两张表，每个会话现在的席位作为它的主席位；已有组织都是没有上级的正式组织，也没有秘书处，所以在你设上级或标秘书处之前，别的都不变。标了秘书处以后，每个领导制正式组织的负责人都会在秘书处里多一个席位。已经开着的 Claude Code 会话，在会话里运行 `/reload-plugins` 或开新会话，才有新工具和新参数。Codex 把每个插件版本放在各自的目录里（`~/.codex/plugins/cache/relic-bridge/relic/<版本>`），启动时载入，所以装好后要重启 Codex 才会用上 0.15.0-beta.1；在那之前，它的会话可能还在用 0.14.0-beta.1：没有 `group` 和 `org`，也不执行从上级继承来的协议。
- **发布与检查。**`relic-windows-v0.4.0-beta.1.zip`（发布，附 `SHA256SUMS.txt` 和 `release-manifest.json`）和 macOS 的 `.tar.gz`（构建，不发布）。`docs/api/relic.json` 列出 12 个工具。

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
