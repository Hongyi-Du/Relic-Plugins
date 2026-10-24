# Changelog / 更新记录

## v0.1.0-beta.1 — 2026-10-24

First public beta distribution of the current internal Relic plugin family.

- Claude 0.1.0-beta.1, Codex / GPT 0.6.0-beta.1, Bridge 0.12.0-beta.1.
- Separate Windows ZIP and macOS tar.gz packages for each edition.
- Portable installer resolves Python/MCP/hook paths on the target computer; Claude MCP wiring and command-hook packaging are normalized.
- Bilingual user guides, OS-specific installation, tool schemas, data guidance and troubleshooting.
- Isolated tests avoid borrowing the invoking Codex session's identity or live organization store.
- macOS file opening uses the native `open` command; optional benchmark paths no longer default to a developer's drive.
- Bridge macOS desktop auto-wake and ChatGPT chat relay are unavailable. Real desktop workflows, signed/notarized apps and a fully English GUI are outside this first beta's validation scope.

首次公开发布当前内部试用的 Relic 三版本插件：

- Claude 0.1.0-beta.1、Codex / GPT 0.6.0-beta.1、Bridge 0.12.0-beta.1。
- 每个版本提供 Windows ZIP 与 macOS tar.gz。
- 安装器解析使用者电脑上的 Python/MCP/hook 路径，补全 Claude MCP 注册并规范命令 hook。
- 提供完整中英文指南、两系统安装文档、工具 schema、数据说明和排错。
- 测试与当前 Codex 会话身份、真实组织数据库隔离。
- macOS 打开文件使用原生 `open`；可选基准路径不再指向开发者盘符。
- macOS Bridge 尚不支持桌面自动唤醒与 ChatGPT 聊天转发。本次未认证完整真实桌面流程，不提供已签名/公证 App，也未完成全英文 GUI。
