# Native Relic App candidate / 原生 Relic App 候选版

These review builds use SwiftUI on macOS and WinUI 3 on Windows. They do not use
a browser or a web view. Both contain the same `plugins/relic` Python engine.
Build and unit-test evidence does not replace trying the actual native windows.

这些审阅构建分别使用 SwiftUI 和 WinUI 3，两端携带同一份 Python 核心。CI 构建及单元测试
与真机界面验收是不同的步骤。当前候选版的合并和安装由 Claude 在本人试用后安排。

The app's own 40 px toolbar is its title bar. Drag an empty area to move the
window, or double-click it to maximize/restore. Windows retains its system
caption buttons and macOS retains its traffic lights in the same row. Light
and dark full-window screenshots are published by the **Native window chrome**
workflow; element comparisons remain a non-blocking regression report.

应用自身的 40 px 工具行就是标题栏：空白处可拖动窗口，双击可最大化或还原；
Windows 系统窗口按钮和 macOS 红黄绿按钮都在这一行。**Native window chrome**
工作流提供亮色、暗色的整窗截图；逐元素比较保留为回归报告，不再阻塞交付。

## Requirements / 前置条件

- Windows 10 version 1809+ x64, or macOS 14+ Apple silicon.
- Python 3.11+ available as `python` on Windows or `python3` on macOS.
  `RELIC_PYTHON` may name the absolute interpreter path. The Python interpreter
  is not bundled in these unsigned candidates.
- Windows dictation uses the installed Windows desktop speech engine for en-US or zh-CN.
  Add the selected language's Speech component in Windows Settings and allow desktop
  microphone access. macOS dictation uses Apple Speech and asks for speech/microphone permission on the first click.
- Claude Code or Codex installed and signed in for members. App-managed ACP
  members also need Node.js 22+ and the corresponding adapter; retain the existing
  plugin installation. The native UI does not sign in to model providers.

需要 Python 3.11+。成员仍使用已安装、已登录的 Claude Code / Codex；App 内运行成员另需
Node.js 22+ 及相应 ACP adapter。原生候选版沿用现有插件和账号配置。

## Windows

Download `Relic-Windows-<version>-Setup.exe` from the PR's **Native apps** workflow
artifact. Run it when ready to try the candidate. It installs per user under
`%LOCALAPPDATA%\Programs\Relic`, without administrator rights, and adds Start menu
and desktop shortcuts. Open **Relic** from that shortcut. The installer does not
automatically open it. Uninstall through Windows Settings; organization data in
the Relic data directory is not an installer-owned file and is retained.

下载 CI artifact 中的 `Relic-Windows-<version>-Setup.exe`，准备试用时再安装。
从开始菜单或桌面的 **Relic** 打开；安装器不会自动启动应用。候选版未签名。
同一 artifact 的 ZIP 可解压后直接运行 `Relic.exe`，需保留整个目录。

## macOS

Download the native macOS ZIP from the PR workflow artifact, extract it, and copy
`Relic.app` to `~/Applications` for testing. Open **Relic.app** in Finder. This
contains a Mach-O SwiftUI executable, not the old shell launcher. It needs no
browser. This candidate has no Developer ID signature or notarization; use the
normal per-app macOS approval flow after the person decides to test it. Do not
disable Gatekeeper globally. A `.dmg` and distribution signing come later.

解压 macOS ZIP，将 `Relic.app` 复制到 `~/Applications` 后在 Finder 打开。
这是 SwiftUI 可执行应用，不是旧版启动器。当前没有 Developer ID 签名或公证；
首次打开的系统确认留到本人试用时处理。`.dmg`、签名及公证尚未发布。

Opening via scripts/open_app.py or plugins/relic/scripts/relic_app.py now finds the native application. It never falls back to Edge/Chrome. RELIC_NATIVE_APP can select an explicit compiled executable or .app bundle. Plugin-only packages require the native App to be installed separately; --no-window, --serve, and lifecycle commands remain available for headless engine use.

## Lifecycle / 退出行为

The App starts its local engine without a console. When it owns that engine,
closing the Windows window or choosing Quit on macOS closes it and its App-managed sessions. Closing the last macOS window keeps the Dock app and its engine running; click the Dock icon to reopen its window. If an
authenticated engine was already running, it connects to it and leaves it running
on exit. The running server is never restarted merely to open a native window.
`RELIC_HOME` still selects the data directory. Default: `~/.relic`.

应用启动自己管理的本地服务时不显示控制台。关闭 Windows 窗口或在 macOS 选择「退出」会清理自己的服务；macOS 只关闭窗口时保留 Dock 应用及其服务，点击 Dock 图标可重新打开窗口。
若连接的是原先已运行的服务，退出时保留它。现有组织数据及核心功能继续由同一引擎管理。

## Build packages / 构建包

Run on the target OS or in CI; none of these commands launches the App:

```powershell
dotnet publish native/windows/Relic/Relic.csproj -c Release -p:Platform=x64 -o native-build/windows
python scripts/package.py --platform windows --native-build native-build/windows --output dist/native
```

```sh
swift build --package-path native/macos -c release --arch arm64
python3 scripts/package.py --platform macos --native-build native/macos/.build/arm64-apple-macosx/release --output dist/native
```

Windows packaging uses the Inno Setup compiler available on the hosted Windows
runner. Packaging checks archive integrity and engine byte equality without
executing the native app. [Contract and remaining screens](native-apps.md).
