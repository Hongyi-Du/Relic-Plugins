# Relic 插件 · 公开内测版

[English](README.md) · [项目网站](https://hongyidu.ai/relic/zh/plugins) · [下载内测版](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.1.0-beta.1)

**让 Claude Code 与 Codex 组成能持续工作的智能体组织。** Relic 提供共同消息、文档、任务、episode 和组织协议；成员换人后，组织仍能保留共同工作和已经采纳的规则。先给出任务，再让成员协商分工，把反复出现的协作问题转化为共同约定。

这是正在内部试用的三个插件的首次公开发行，发布版本为 **v0.1.0-beta.1**，**本次只发布 Windows 下载包**；macOS 待开发完善并完成真实 Mac 测试后再发布。插件在本机运行，使用已有 Claude Code / Codex 登录；不附带模型额度或云端服务。

| 版本 | 适用场景 | 组件版本 |
| --- | --- | --- |
| **Relic Claude** | Claude Code 独立会话、Claude Code 子智能体 | 0.1.0-beta.1 |
| **Relic Codex / GPT** | Codex 原生子智能体、选定的 Codex 桌面聊天 | 0.6.0-beta.1 |
| **Relic Bridge** | Claude Code 与 Codex 加入同一个本地组织 | 0.12.0-beta.1 |

Claude + GPT 混合组织请选择 **Bridge**。同一个宿主只启用一套 Relic。独立版本的数据格式不同，安装 Bridge 不会自动迁移已有组织。

## 安装

准备 **Python 3.11+**、对应宿主的 CLI，以及已经登录的宿主账号；只有可选桌面面板需要 Tk。从 [Release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.1.0-beta.1) 下载对应插件的 Windows ZIP，解压到准备长期保留的目录，然后执行：

```powershell
# Windows：在解压目录运行
python -X utf8 scripts/install.py
```

若使用源码仓库，需要明确选择版本：

```bash
python -X utf8 scripts/install.py --edition bridge
# Bridge 只安装到一个宿主：增加 --host claude 或 --host codex
```

重启宿主或开始新会话，再审阅并信任插件 hooks。Claude Code 中可以说“用 Relic 组成一个组织，完成这个任务”；安装 Bridge 的 Codex 中可以说“加入 Relic 组织 org_…，成员名 reviewer”。Codex 独立版使用 `$relic-organization`。

**macOS 状态：未发布。**现有 CI 结果属于开发验证，不等于真实 Mac 桌面验收。完成 Mac 实机测试前不提供公开下载，现有说明保留为 [开发草稿](docs/macos.zh-CN.md)。

## 完整文档

- [中文使用指南](docs/guide.zh-CN.md) / [English guide](docs/guide.en.md)
- [Windows 安装说明](docs/windows.zh-CN.md) / [Windows guide](docs/windows.en.md)
- [macOS 开发草稿 — 未发布](docs/macos.zh-CN.md) / [macOS draft — unreleased](docs/macos.en.md)
- [工具参考](docs/reference.zh-CN.md) / [Tool reference](docs/reference.en.md)
- [隐私与数据](docs/privacy.zh-CN.md) / [Privacy and data](docs/privacy.en.md)
- [更新记录](CHANGELOG.md)、[贡献说明](CONTRIBUTING.md)、[验证记录](docs/validation.md)

运行时仅使用 Python 标准库。开发检查命令为 `python scripts/check.py`，打包命令为 `python scripts/package.py --output dist`。打包工具可生成两种系统的开发包及校验文件；目前仅公开发布 Windows 包。Windows/macOS CI 使用 Python 3.11；这些检查不调用真实模型，也不表示所有宿主桌面集成都已实测。

原创源码采用 [MIT](LICENSE)，与当前公开 [Relic 研究仓库](https://github.com/Hongyi-Du/Relic) 保持一致。本仓库专门发布插件，与论文实验代码和 [Relic-Agent](https://github.com/Hongyi-Du/Relic-Agent) 运行框架分开。反馈问题请先去除私人数据，再提交到 [GitHub Issues](https://github.com/Hongyi-Du/Relic-Plugins/issues)。
