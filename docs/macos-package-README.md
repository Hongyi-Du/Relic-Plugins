# Relic for macOS · Apple silicon

v0.8.0-beta.1（插件 0.19.0-beta.1）：这个源码包只装插件与引擎；原生 SwiftUI 的 `Relic.app` 在
`relic-native-macos-v0.8.0-beta.1.zip` 里，是预览版，还没在真实 Mac 上试过。
v0.8.0-beta.1 (plugin 0.19.0-beta.1): this source package installs the plugin and engine; the native SwiftUI
`Relic.app` is in `relic-native-macos-v0.8.0-beta.1.zip`, a preview not yet tried on a real Mac.
Windows 和 macOS 共用一个引擎和同一套功能。Both systems share one engine and feature set.
macOS 移植由 HaochenGu 贡献。The macOS port was contributed by HaochenGu.
见 [验证记录](docs/validation.md) / See [validation](docs/validation.md).
Requires native arm64 Python 3.11+, Node.js 22+ with npm, and a signed-in Claude Code and/or Codex CLI.

## 安装 / Install

解压到固定目录，在 Terminal 进入该目录：
Extract into a permanent folder, then run from Terminal:

```sh
bash install.command --host none --open
```

这是插件与引擎源码包。请另按 [原生安装说明](docs/native-install.md) 安装 SwiftUI Relic.app，再从 Finder 打开；请保留插件解压目录。
This is the plugin/engine source package. Install the SwiftUI Relic.app separately using [native installation](docs/native-install.md), then open it in Finder. The plugin installer does not create the former shell launcher.

进入 Settings → Harness connections，安装 ACP adapters，再选择 New organization → Add member → Run in the App。
Install the ACP adapters under Settings → Harness connections, then add members with Run in the App.
The adapters use your existing Claude/Codex login. Blank executable fields mean automatic discovery.

若需要让独立 CLI 会话加载插件，运行 `bash install.command --host both`，重启宿主并确认 hooks。
For independent CLI sessions, run `bash install.command --host both`, restart the hosts and review the hooks.

## 管理 / Manage

以下 python3 应为安装时使用的 arm64 Python 3.11+；也可以使用该解释器的完整路径。
Use the same native arm64 Python 3.11+ interpreter selected during installation for these commands.

```sh
python3 scripts/doctor.py
python3 scripts/open_app.py --status
python3 scripts/open_app.py --restart
python3 scripts/open_app.py --stop
```

原生 App 退出会停止自己启动的服务，保留原先已运行的服务。组织数据默认保存在 ~/.relic；也可通过 RELIC_HOME 指定目录。
The native App stops its own engine on exit and leaves a borrowed engine running. Organization data defaults to ~/.relic or RELIC_HOME.

此包不含个人聊天、账号凭据、本机 Python 绝对路径或已安装的依赖。桌面投递由本机能力检查控制。
This source package contains no personal chats, credentials, machine-specific launch paths or installed dependencies.
Desktop delivery is enabled only after local capability checks. This is an unsigned source installer prerelease.
Intel Macs and Rosetta runtimes are outside this release's support target.

[macOS 中文指南](docs/macos.zh-CN.md) · [macOS English guide](docs/macos.en.md)

## 升级 / Upgrade

升级前备份数据目录：首次打开旧库会给 `activity` 增加 `paths` 列。这是不可逆的自动迁移，没有自动降级；回退时恢复升级前备份。
Back up the data directory before upgrading: the first open adds `activity.paths`. Relic cannot reverse this migration automatically; restore a pre-upgrade backup to roll back.
