# Contributing / 贡献

Open an issue with the release, OS, Python and host versions (Claude Code, Codex, Node.js and the ACP adapters when the Relic App is involved) plus minimal redacted reproduction steps. The plugin and the Relic App live in `plugins/relic`; the installer, packaging and checks in `scripts`; the packaging tests in `tests`. Preserve real host identity, delivery/ack distinction, and uncertainty after an ambiguous send.

报告问题时注明发布版本、系统、Python 与宿主版本（涉及 Relic App 时再加 Claude Code、Codex、Node.js 和 ACP 适配器的版本），提供最小脱敏复现。插件和 Relic App 在 `plugins/relic`；安装器、打包与检查脚本在 `scripts`；打包测试在 `tests`。保留真实身份校验、投递/确认区分，以及不确定投递不能盲目重试的语义。

Run these commands from a clone of the full repository. The installation archives include only the scripts needed to install and use Relic (`install.py`, `doctor.py`, `open_app.py`, `macos_app.py`). `check.py` runs both suites (`--suite relic` or `--suite packaging` runs one); `package.py --platform macos --macos-format both` builds this branch's ZIP and tar.gz release assets; after changing a tool schema, `export_api.py` rewrites `docs/api/relic.json`.

以下命令在完整源码仓库的根目录执行；安装包只包含安装和使用 Relic 所需的脚本（`install.py`、`doctor.py`、`open_app.py`、`macos_app.py`）。`check.py` 运行两套测试（`--suite relic` 或 `--suite packaging` 只跑一套）；`package.py --platform macos --macos-format both` 生成本分支的 ZIP 和 tar.gz 下载包；修改工具 schema 后，用 `export_api.py` 重新生成 `docs/api/relic.json`。

```bash
python scripts/check.py
python scripts/package.py --platform macos --macos-format both --output dist
python scripts/export_api.py
```

Tests use isolated temporary data and fake hosts. Do not add test dependencies on a maintainer's logged-in application or live conversations. Include Windows/macOS checks when changing paths, subprocesses, hooks or installers. Desktop acceptance and real model behavior require separate evidence. Keep English and Chinese docs aligned.

测试使用临时隔离数据与宿主替身，不得依赖维护者已登录应用或真实对话。修改路径、子进程、hooks 和安装器时覆盖 Windows/macOS；桌面验收与真实模型表现需另外提供证据。同步更新中英文文档。

## Unified Windows/macOS candidate packages

Both platforms use `plugins/relic` and the version in `release.json`. Keep OS integration in
`relic_core/platform_support.py` or explicit OS branches; shared feature fixes must work on Windows too.
Preserve contributor commits when integrating a port. The earlier v0.4.1-macos prerelease is historical; future development uses the unified version.

```sh
python -X utf8 scripts/check.py
python -X utf8 scripts/package.py --platform all --macos-format both --output dist
```

Build from a clean committed tree. `release-manifest.json` records the source commit, dirty state, plugin version
and each archive checksum; compare it with `SHA256SUMS.txt`. ZIP/tar macOS archives carry the same logical contents,
executable `install.command`, the macOS README and `scripts/macos_app.py`. Windows keeps its launch templates and
installer. Packaging normalizes archive configuration without modifying source launch files. Do not include a live
store, installed adapters or local runtime paths. Record automated CI separately from signed-in real-Mac acceptance.
Creating a tag, GitHub Release or website deployment is a separate publication action.

Windows/macOS 使用同一源码和版本；操作系统适配放在平台层或显式系统分支中。干净提交构建后的来源清单、
校验文件和两种 macOS 归档需相符。自动化 CI 与已登录真机验收分别记录；打标签、发 Release 与网站部署另行进行。
