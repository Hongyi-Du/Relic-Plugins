# Contributing / 贡献

Open an issue with edition, release, OS, Python and host versions plus minimal redacted reproduction steps. Keep changes in the edition that owns the behavior; the standalone Codex store and Bridge store are different implementations. Preserve real host identity, delivery/ack distinction, and uncertainty after an ambiguous send.

报告问题时注明版本、系统、Python/宿主版本，提供最小脱敏复现。只改拥有相关行为的版本；独立 Codex 与 Bridge 数据库是不同实现。保留真实身份校验、投递/确认区分，以及不确定投递不能盲目重试的语义。

```bash
python scripts/check.py
python scripts/package.py --output dist
```

Tests use isolated temporary data and fake hosts. Do not add test dependencies on a maintainer's logged-in application or live conversations. Include Windows/macOS checks when changing paths, subprocesses, hooks or installers. Desktop acceptance and real model behavior require separate evidence. Keep English and Chinese docs aligned.

测试使用临时隔离数据与宿主替身，不得依赖维护者已登录应用或真实对话。修改路径、子进程、hooks 和安装器时覆盖 Windows/macOS；桌面验收与真实模型表现需另外提供证据。同步更新中英文文档。
