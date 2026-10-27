# Changelog / 更新记录

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
