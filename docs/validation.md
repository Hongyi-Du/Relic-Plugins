# Validation / 验证记录

## v0.4.1-beta.1

Release: **v0.4.1-beta.1**, prepared 2026-10-28. Relic plugin 0.15.1-beta.1, a front-end update to v0.4.0-beta.1: the organization chart is moved, zoomed and fitted to the window and opens from an organization's right-click menu, and the English Organization details button wraps instead of widening the Overview. No server, hook, tool or store code changed, so the real-machine run of v0.4.0-beta.1 still describes how members run.

| Check / 检查 | Result / 结果 |
| --- | --- |
| Relic fixtures (`--suite relic`) on Windows 11, Python 3.14.4 | 264 tests passed / 264 个通过 |
| Packaging (`--suite packaging`): installer and both archives | 4 tests passed / 4 个通过 |
| Organization chart in headless Edge with real mouse input, in English and in Chinese, on a store shaped like a secretariat with eight organizations under it, subgroups and shared seats, at 1400×900 and 2400×1300 | The right-click menu opens the chart; fitted, every organization is inside the window (63% at 1400 wide, 100% at 2400); the wheel zooms; dragging moves the view and a drag that starts on an organization does not open it; double-click and Fit to window fit it again; the percentage sets 100%; a plain click opens the organization; from a single organization it opens at 100%, centered; a narrow window lists them; no console errors. / 右键菜单能打开关系图；适应窗口后所有组织都在窗口里（1400 宽时 63%，2400 宽时 100%）；滚轮能缩放；拖动能移动，从组织上开始拖不会打开它；双击和「适应窗口」能重新适应；点百分比回到 100%；直接点组织能打开它；从单个组织打开时按 100% 居中；窄窗口按列表显示；控制台无报错。 |
| Windows CI, Python 3.11 | to be recorded / 待记录 |
| macOS arm64 CI, Python 3.11 | to be recorded / 待记录 |

`check.py` makes no model calls. macOS results remain development evidence only; macOS is not released.

**v0.4.1-beta.1** 于 2026-10-28 准备发布。Relic 插件 0.15.1-beta.1，是 v0.4.0-beta.1 的前端更新：组织关系图可以拖动、缩放、默认适应窗口，并能从组织的右键菜单打开；英文界面里的组织详情按钮改为换行，不再把「概况」撑宽。服务端、hooks、工具和数据库的代码都没有改，所以 v0.4.0-beta.1 的实机运行仍然说明成员怎样运行。

`check.py` 不调用模型。macOS 结果仍只作开发验证，macOS 尚未发布。

## v0.4.0-beta.1

Release: **v0.4.0-beta.1**, prepared 2026-10-27. Relic plugin 0.15.0-beta.1: the Relic App in English as well as Chinese, organizations above and below, and the organization model (one session in several seats, protocols that bind in their own organization and can be inherited downward, subgroups, a secretariat whose secretary-general approves changes to formal organizations, ex officio seats, the organization chart). The plugin has 12 tools; `group` is new.

`scripts/check.py` runs the same two suites as in v0.3.0-beta.1, each in its own process with a temporary `RELIC_HOME`, `CODEX_HOME` and temp folder and without the invoking session's `RELIC_*` and `CODEX_*` variables. The relic suite now also covers the word lists and the language choice (`test_i18n.py`), organizations above and below (`test_hierarchy.py`) and the organization model (`test_org_model.py`).

| Check / 检查 | Result / 结果 |
| --- | --- |
| Relic fixtures (`--suite relic`) on Windows 11, Python 3.14.4 | 264 tests passed / 264 个通过 |
| Packaging (`--suite packaging`): installer and both archives | 4 tests passed / 4 个通过 |
| Real-machine App run: an App server on a temporary `RELIC_HOME` started one Claude Code and one Codex member through the installed ACP adapters (claude-agent-acp 0.97.0, codex-acp 2.3.0) | Both called the Relic status tool and were answered as their own seats. The Claude Code session had one set of Relic tools, 12 including `group`, from the App's plugin folder. The Codex session used Codex's own Relic plugin and the App added no server; on this machine that plugin is the maintainer's development install, so this shows the new tools reaching a Codex member, not the packaged Codex install. / 两个成员调用 Relic status 都以自己的席位作答。Claude Code 会话只有一套 Relic 工具，共 12 个（含 `group`），来自 App 的插件目录。Codex 会话用 Codex 自己的 Relic 插件，App 没有另加服务；这台机器上的那份插件是维护者的开发安装，所以这一项说明新工具能到达 Codex 成员，不代表打包后的 Codex 安装。 |
| App page in headless Edge, in English and in Chinese, on an example store with a secretariat, departments, subgroups and requests waiting for approval | The organization chart (wide and narrow windows), the approval cards, "Also in" on a name card, the Hierarchy block and inherited protocols show as designed; no console errors; no Chinese left on the English screen. At 480 px the chat header's buttons still run past the window edge, as in v0.3.0-beta.1. / 组织关系图（宽窗口和窄窗口）、审批卡片、名片上的「也在」、「上下级」一栏和继承来的协议都按设计显示；控制台无报错；英文界面没有残留中文。480 像素宽时聊天顶栏的按钮仍会超出窗口，v0.3.0-beta.1 也是这样。 |
| Windows CI, Python 3.11 | 268 passed: packaging 4 + relic 264 / 268 个通过：packaging 4 + relic 264 |
| macOS arm64 CI, Python 3.11 | 266 passed, 2 skipped: packaging 4 + relic 262; the two skipped fixtures are Windows-only (Codex's sandbox override, finding the installed Edge app) / 266 个通过、2 个跳过：packaging 4 + relic 262；跳过的两个只在 Windows 上有意义（Codex 的沙箱覆盖、查找已安装的 Edge 应用） |

CI: both platform jobs passed in [run 40630184056](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40630184056) on source commit `81dd950e26bbb2bd40bbfcaf18fa553d86b10f31`. The published package is built from the next commit, which only records this result; the run's artifacts keep the per-suite logs. / 两个平台任务都在 [CI 40630184056](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40630184056) 通过，受测源码提交为 `81dd950e26bbb2bd40bbfcaf18fa553d86b10f31`；发布的下载包由下一个提交构建，该提交只记录这次结果；CI 附件保存逐套日志。

`check.py` makes no model calls. The real-machine run used the maintainer's signed-in Claude Code and Codex (two short turns per member) on a temporary store; no real organization was involved. macOS results remain development evidence only; macOS is not released.

**v0.4.0-beta.1** 于 2026-10-27 准备发布。Relic 插件 0.15.0-beta.1：Relic App 除中文外有了英文界面；组织可以分上下级；组织模型改版（一个会话坐多个席位，协议在本组织生效并可向下继承，子组，秘书处的秘书长审批正式组织的调整，当然席位，组织关系图）。插件有 12 个工具，`group` 是新加的。

`scripts/check.py` 运行与 v0.3.0-beta.1 相同的两套测试，每套在独立进程中运行，使用临时的 `RELIC_HOME`、`CODEX_HOME` 和临时目录，并去掉调用会话的 `RELIC_*`、`CODEX_*` 变量。relic 这套测试新增了语言包和语言选择（`test_i18n.py`）、上下级组织（`test_hierarchy.py`）和组织模型（`test_org_model.py`）。

`check.py` 不调用模型。实机运行用了维护者已登录的 Claude Code 和 Codex（每个成员两轮简短对话），数据在临时目录里，没有涉及任何真实组织。macOS 结果仍只作开发验证，macOS 尚未发布。

## v0.3.0-beta.1

Release: **v0.3.0-beta.1**, prepared 2026-10-27. One product, Relic (plugin 0.14.0-beta.1): the three editions of v0.2.0-beta.1 are merged, so the checks cover one plugin and one archive per platform.

`scripts/check.py` runs two suites, each in its own process with a temporary `RELIC_HOME`, `CODEX_HOME` and temp folder and without the invoking session's `RELIC_*` and `CODEX_*` variables:

- **relic** (`plugins/relic/tests`): the plugin's tools, MCP server, hooks, store, wake-ups, runner, desktop transport, chat members, trajectories, task reports and threads, the Relic App and its panes, and how the App brings Relic into the sessions it runs.
- **packaging** (`tests`): the installer configures a folder whose path has spaces and Chinese characters, then starts the MCP server and a hook from it; it installs into the hosts it finds, disables the earlier Claude Code editions, stops when a named host is missing, and needs no host with `--host none`. The package test builds both archives, extracts each into a path with spaces and Chinese characters and runs `install.py --configure-only` there; the App and the marketplace must be present, `scripts/open_panel.py` absent, and `install.command` must keep LF line endings and mode 755.

`scripts/package.py` builds one archive per platform, `relic-windows-v0.3.0-beta.1.zip` and `relic-macos-v0.3.0-beta.1.tar.gz`, plus `SHA256SUMS.txt` and `release-manifest.json`; only the Windows archive is published. CI runs the same two commands as before on Windows and macOS with Python 3.11.

| Check / 检查 | Result / 结果 |
| --- | --- |
| Relic fixtures (`--suite relic`) on Windows 11, Python 3.14.4 | 216 tests passed / 216 个通过 |
| Packaging (`--suite packaging`): installer and both archives | 4 tests passed / 4 个通过 |
| Real-machine App run: an App server on a temporary `RELIC_HOME` started one Claude Code and one Codex member through the installed ACP adapters | Both called the Relic status tool and were answered as their own seats. The Claude Code session had one set of Relic tools (11, from the App's plugin folder; the installed copy was switched off). The Codex session used Codex's own Relic plugin; the App added no server. / 两个成员调用 Relic status 都以自己的席位作答；Claude Code 会话只有一套 Relic 工具（11 个，来自 App 的插件目录，已装的那份在会话里关掉）；Codex 会话用 Codex 自己的 Relic 插件，App 没有另加服务。 |
| App page in headless Edge | The add-member dialog switches between its three ways, a member card shows its seat buttons, the input box is empty after sending; no console errors. / 添加成员对话框三种方式能切换，名片显示席位按钮，发送后输入框为空；控制台无报错。 |
| Windows CI, Python 3.11 | 220 passed: packaging 4 + relic 216 / 220 个通过：packaging 4 + relic 216 |
| macOS arm64 CI, Python 3.11 | 218 passed, 2 skipped: packaging 4 + relic 214; the two skipped fixtures are Windows-only (Codex's sandbox override, finding the installed Edge app) / 218 个通过、2 个跳过：packaging 4 + relic 214；跳过的两个只在 Windows 上有意义（Codex 的沙箱覆盖、查找已安装的 Edge 应用） |

CI: both platform jobs passed in [run 40553955238](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40553955238) on source commit `ddf07be188f6ec1e403a20f8e08cced01223e270`. The published package is built from the next commit, which only records this result; the run's artifacts keep the per-suite logs. / 两个平台任务都在 [CI 40553955238](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40553955238) 通过，受测源码提交为 `ddf07be188f6ec1e403a20f8e08cced01223e270`；发布的下载包由下一个提交构建，该提交只记录这次结果；CI 附件保存逐套日志。

The release checks make no model calls. macOS results remain development evidence only; macOS is not released.

**v0.3.0-beta.1** 于 2026-10-27 准备发布。一个产品 Relic（插件 0.14.0-beta.1）：v0.2.0-beta.1 的三个版本已经合并，检查覆盖一个插件和每个系统一个下载包。

`scripts/check.py` 运行两套测试，每套在独立进程中运行，使用临时的 `RELIC_HOME`、`CODEX_HOME` 和临时目录，并去掉调用会话的 `RELIC_*`、`CODEX_*` 变量：

- **relic**（`plugins/relic/tests`）：插件的工具、MCP 服务、hooks、数据库、自动唤醒、runner、桌面通信、聊天成员、轨迹、任务报告和话题，Relic App 及其面板，以及 App 怎样把 Relic 带进它运行的会话。
- **packaging**（`tests`）：安装器配置一个路径含空格和中文的目录，再从中启动 MCP 服务和一个 hook；它安装到找得到的宿主，停用较早的 Claude Code 版本，指定的宿主不存在时报错停止，`--host none` 时不需要任何宿主。打包测试构建两个下载包，分别解压到含空格和中文的路径并在那里运行 `install.py --configure-only`；App 和 marketplace 必须存在，`scripts/open_panel.py` 必须不存在，`install.command` 必须保持 LF 换行和 755 权限。

`scripts/package.py` 为每个系统生成一个下载包：`relic-windows-v0.3.0-beta.1.zip` 和 `relic-macos-v0.3.0-beta.1.tar.gz`，外加 `SHA256SUMS.txt` 和 `release-manifest.json`；只发布 Windows 包。CI 仍在 Windows 和 macOS 上用 Python 3.11 运行同样的两条命令。

发布检查不调用模型。macOS 结果仍只作开发验证，macOS 尚未发布。

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
