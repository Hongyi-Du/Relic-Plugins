# Validation / 验证记录

## v0.2.0-beta.1

Release: **v0.2.0-beta.1**, prepared 2026-10-27. Relic Bridge 0.13.0-beta.1 adds the Relic App; Claude and Codex are unchanged.

| Check / 检查 | Result / 结果 |
| --- | --- |
| Claude unit fixtures | 20 passed on Windows, Python 3.14 |
| Codex unit fixtures | 307 passed on Windows, Python 3.14 |
| Bridge isolated unit fixtures | 210 passed on Windows, Python 3.14 (156 in v0.1.0-beta.1; the new fixtures cover the Relic App, threads, task reports and concurrent MCP calls) |
| Installer, hook launch, MCP initialization and six extracted archives | 4 passed; Bridge archives contain `scripts/open_app.py` and the App, the others do not |
| Relic App end to end, headless Microsoft Edge | 47 checks passed, no page errors: sending, mentions, quotes, threads, private chats, renaming, workspace and file preview, task reports, menus, shortcuts, back/forward, settings, installed-app mode, 人话 and 解读 from kept results |
| Windows CI, Python 3.11 | 541 passed: packaging 4 + claude 20 + codex 307 + bridge 210 |
| macOS arm64 CI, Python 3.11 | 541 passed: packaging 4 + claude 20 + codex 307 + bridge 210 |

CI: [run 40458319380](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40458319380) on source commit `7127e06477e5cef368d9bd08d0ad25fd7ac0b1c2`.

The end-to-end run used a copy of a real organization store with auto-wake off, plus an example organization whose members have no sessions; no live member was messaged and no session was renamed. Separately, 人话 and 解读 were tried once on a real organization's messages, which called the maintainer's Claude Code (`claude -p`, Sonnet). The release checks themselves make no model calls. macOS results remain development evidence only; macOS is not released.

端到端测试使用真实组织存储的一份副本（自动唤醒关闭），外加一个成员都没有会话的示例组织；没有给真实成员发消息，也没有改任何会话的名字。另外在一个真实组织的消息上试过一次「人话」和「解读」，调用了维护者的 Claude Code（`claude -p`，Sonnet）。发布检查本身不调用模型。macOS 结果仍只作开发验证，macOS 尚未发布。

## v0.1.0-beta.1

Release: **v0.1.0-beta.1**, prepared 2026-10-24.

**Publication scope: Windows only.** macOS CI evidence below is retained as development history; macOS is not released and requires real Mac testing before publication.

**发布范围：仅 Windows。**下方 macOS CI 结果保留为开发验证历史；macOS 尚未发布，需完成真实 Mac 测试后再发布。

| Check / 检查 | Result / 结果 |
| --- | --- |
| Claude unit fixtures | 20 passed on Windows, Python 3.14 |
| Codex unit fixtures | 307 passed on Windows, Python 3.14 |
| Bridge isolated unit fixtures | 156 passed on Windows, Python 3.14 |
| Installer, hook launch, MCP initialization and six extracted archives | 4 passed, including spaces and Chinese characters in extracted paths |
| Windows CI, Python 3.11 | 487 passed: installer/archives 4 + Claude 20 + Codex 307 + Bridge 156 |
| macOS arm64 CI, Python 3.11 | 487 passed, same suite counts; no skipped tests |

Both platform jobs passed in [CI run 40135273111](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40135273111) on source commit `785d47c5b97715c0ee2962814a255f5dd4ceabef`. The release includes subsequent documentation-only updates. The run's artifacts retain per-suite logs and exit-code summaries. Earlier cancelled or failed diagnostic runs are not counted as passes.

两个平台任务均在 [CI 40135273111](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40135273111) 通过，受测源码提交为 `785d47c5b97715c0ee2962814a255f5dd4ceabef`；发行版随后仅更新文档。CI 附件保存逐套日志及退出码汇总，之前取消或失败的排查运行不计作通过。

The first Bridge suite run inherited `CODEX_THREAD_ID` from the publishing session and failed one Claude-chat identity fixture. Re-running with `scripts/check.py` isolated host identity and data roots; all 156 passed without weakening runtime identity checks. Some existing mocked runner tests emit subprocess resource warnings during cleanup; their assertions pass. This is a known test-harness cleanup limitation.

首次 Bridge 测试继承了发布会话的 `CODEX_THREAD_ID`，导致一个 Claude-chat 身份测试失败。使用 `scripts/check.py` 隔离宿主身份与数据目录后，156 项全部通过，没有放宽运行时身份校验。部分已有 runner 替身测试在退出清理时产生 subprocess resource warning；断言通过，测试进程清理仍有改进空间。

Release preparation also fixed a non-Windows Bridge panel font initialization error. Installer checks compare resolved Python paths so macOS interpreter symlinks are accepted. On the macOS CI image, repeatedly creating hidden Tk interpreters stalled the GUI event loop. `scripts/run_fixture_suite.py` therefore invokes each macOS GUI fixture in a fresh process, retaining its assertions and reporting failures or skips explicitly. Windows runs these fixtures in-process. This follows the [Python Tkinter threading guidance](https://docs.python.org/3/library/tkinter.html#threading-model) and does not certify a signed-in host desktop session.

发布准备还修复了 Bridge 面板在非 Windows 平台的字体初始化错误；安装器测试按 Python 的实际路径比较，支持 macOS 的解释器符号链接。macOS CI 中反复创建隐藏 Tk 解释器会卡住事件循环，因此 `scripts/run_fixture_suite.py` 将每项 macOS GUI 测试放进独立进程，保留断言并明确报告失败或跳过；Windows 仍在同一测试进程中执行。这遵循 [Python Tkinter 的线程与事件循环说明](https://docs.python.org/3/library/tkinter.html#threading-model)，不等于已登录宿主桌面会话的验收。

Tests establish fixture behavior, launchable MCP endpoints, and package structure. They do **not** establish scientific superiority, guaranteed protocol coverage for every host tool, live desktop delivery in all host versions, or real macOS desktop acceptance. No real organization was enrolled, no live member was messaged, and no model call was made by release checks.

这些检查证明受控测试行为、MCP 可启动与包结构，不证明研究优势、所有宿主工具均受协议约束、所有版本的真实桌面投递，或 macOS 桌面验收。发布检查没有组建真实组织、没有向实际成员发消息，也没有调用模型。
