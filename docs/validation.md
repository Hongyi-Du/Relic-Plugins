# Validation / 验证记录

Release: **v0.1.0-beta.1**, prepared 2026-10-24.

| Check / 检查 | Result / 结果 |
| --- | --- |
| Claude unit fixtures | 20 passed on Windows, Python 3.14 |
| Codex unit fixtures | 307 passed on Windows, Python 3.14 |
| Bridge isolated unit fixtures | 156 passed on Windows, Python 3.14 |
| Installer, hook launch, MCP initialization and six extracted archives | 4 passed, including spaces and Chinese characters in extracted paths |
| Windows/macOS CI | See the actual run linked from [Actions](https://github.com/Hongyi-Du/Relic-Plugins/actions); no uncompleted run is counted as passed |

The first Bridge suite run inherited `CODEX_THREAD_ID` from the publishing session and failed one Claude-chat identity fixture. Re-running with `scripts/check.py` isolated host identity and data roots; all 156 passed without weakening runtime identity checks. Some existing mocked runner tests emit subprocess resource warnings during cleanup; their assertions pass. This is a known test-harness cleanup limitation.

首次 Bridge 测试继承了发布会话的 `CODEX_THREAD_ID`，导致一个 Claude-chat 身份测试失败。使用 `scripts/check.py` 隔离宿主身份与数据目录后，156 项全部通过，没有放宽运行时身份校验。部分已有 runner 替身测试在退出清理时产生 subprocess resource warning；断言通过，测试进程清理仍有改进空间。

Tests establish fixture behavior, launchable MCP endpoints, and package structure. They do **not** establish scientific superiority, guaranteed protocol coverage for every host tool, live desktop delivery in all host versions, or real macOS desktop acceptance. No real organization was enrolled, no live member was messaged, and no model call was made by release checks.

这些检查证明受控测试行为、MCP 可启动与包结构，不证明研究优势、所有宿主工具均受协议约束、所有版本的真实桌面投递，或 macOS 桌面验收。发布检查没有组建真实组织、没有向实际成员发消息，也没有调用模型。
