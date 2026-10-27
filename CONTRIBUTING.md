# Contributing / 贡献

Open an issue with the release, OS, Python and host versions (Claude Code, Codex, Node.js and the ACP adapters when the Relic App is involved) plus minimal redacted reproduction steps. The plugin and the Relic App live in `plugins/relic`; the installer, packaging and checks in `scripts`; the packaging tests in `tests`. Preserve real host identity, delivery/ack distinction, and uncertainty after an ambiguous send.

报告问题时注明发布版本、系统、Python 与宿主版本（涉及 Relic App 时再加 Claude Code、Codex、Node.js 和 ACP 适配器的版本），提供最小脱敏复现。插件和 Relic App 在 `plugins/relic`；安装器、打包与检查脚本在 `scripts`；打包测试在 `tests`。保留真实身份校验、投递/确认区分，以及不确定投递不能盲目重试的语义。

Run these commands from a clone of the full repository. The installation archives include only the scripts needed to install and use Relic (`install.py`, `doctor.py`, `open_app.py`). `check.py` runs both suites (`--suite relic` or `--suite packaging` runs one); `package.py` builds one archive per platform (`--platform windows` builds only the published one); after changing a tool schema, `export_api.py` rewrites `docs/api/relic.json`.

以下命令在完整源码仓库的根目录执行；安装包只包含安装和使用 Relic 所需的脚本（`install.py`、`doctor.py`、`open_app.py`）。`check.py` 运行两套测试（`--suite relic` 或 `--suite packaging` 只跑一套）；`package.py` 为每个系统生成一个下载包（`--platform windows` 只生成要发布的那个）；修改工具 schema 后，用 `export_api.py` 重新生成 `docs/api/relic.json`。

```bash
python scripts/check.py
python scripts/package.py --output dist
python scripts/export_api.py
```

Tests use isolated temporary data and fake hosts. Do not add test dependencies on a maintainer's logged-in application or live conversations. Include Windows/macOS checks when changing paths, subprocesses, hooks or installers. Desktop acceptance and real model behavior require separate evidence. Keep English and Chinese docs aligned.

测试使用临时隔离数据与宿主替身，不得依赖维护者已登录应用或真实对话。修改路径、子进程、hooks 和安装器时覆盖 Windows/macOS；桌面验收与真实模型表现需另外提供证据。同步更新中英文文档。
