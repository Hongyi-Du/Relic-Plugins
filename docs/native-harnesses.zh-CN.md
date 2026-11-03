# 在 Relic App 中使用 Kimi Code 和 DeepSeek Harness

[English](native-harnesses.en.md)

Relic App 可以通过程序自带的 ACP 服务运行 **Kimi Code**（`kimi-code`）和 **DeepSeek Harness**（`deepseek-harness`）成员。它们沿用现有的添加成员界面、Relic 消息、共享文档、任务、权限请求和会话管理。这两个程序无需额外安装 npm ACP 适配器。

## 连接已有安装

1. 按各程序自己的说明安装并登录，确认 `kimi acp` 或 `dsh --profile acp` 可以启动。Relic 不会安装程序、创建 profile 或改变登录。
2. 在 **设置 → Harness 连接** 中填写程序路径；已在 `PATH` 中时可以留空。Kimi 选择 `kimi` / `kimi.exe`；DSH 选择 `dsh`、CLI 包装脚本，或已安装的 Windows `DeepSeek Harness.exe`。
3. 选择 **添加成员 → 在 App 里运行**，再选 Kimi Code 或 DeepSeek Harness，设置工作目录并创建。成员的介绍回合会调用 Relic status，成员卡片显示实际会话模型。
4. 在成员卡片中选择该会话提供的模型和思考强度。支持 Kimi 的 `thinking` 选项和 DSH 按 provider 分组的模型选项。DSH 模型 ID 是完整的字符串，请直接使用列表中的完整值。

程序路径按 App 中明确填写的路径、下列环境变量、`PATH` 和系统常见 CLI 目录的顺序查找。明确填写的路径无效时会报错，不会悄悄切换到另一套安装。设置页会标明程序自带 ACP，不显示 npm 安装按钮。

| 环境变量 | 用途 |
| --- | --- |
| `RELIC_KIMI_PATH` | 未在 App 设置路径时使用的 Kimi 可执行文件或 CLI 包装脚本。 |
| `RELIC_DSH_PATH` | 未在 App 设置路径时使用的 DSH 可执行文件或 CLI 包装脚本。 |
| `RELIC_DSH_PROFILE` | 已有 DSH profile 名称，默认 `acp`。 |
| `RELIC_DSH_PATCH` | 可选的已有 DSH 配置覆盖文件，通过 `--patch` 传入。 |

在启动 Relic App 的进程中设置环境变量。例如 Windows：

```powershell
$env:RELIC_KIMI_PATH = 'C:\Tools\Kimi\kimi.exe'
$env:RELIC_DSH_PATH = 'C:\Tools\DeepSeek Harness\DeepSeek Harness.exe'
python -X utf8 scripts/open_app.py
```

请替换为实际安装路径。DSH Windows 桌面版通过旁侧的 `resources/app.asar` 和内置运行时启动，不需要重复安装 DSH，也不需要为这个成员另装系统 Node.js。不自动探测其他桌面发行版布局。CLI 查找支持 Windows、macOS 和 Linux；本次真实验收在 Windows 上进行。

## DSH 的账号和模型路由

ACP profile 需要已有可用的 provider 和模型。使用 DSH 中已配置并登录的 provider；需要覆盖文件时，在启动 App 前把 `RELIC_DSH_PATCH` 指向该文件。Relic 不强制指定 provider、不复制凭据，也不修改 DSH 的 profile 和默认模型。计费由选中的原生 provider 决定，使用 ACP 不会改变它的计费方式。

如果创建会话时失败、还没显示模型列表，先确认同一个 profile 和覆盖文件在 DSH 自身中可以运行。缺失的程序路径和覆盖文件会在 Harness 连接页提示；登录认证仍由原生程序处理。

## 会话和组织协议

每个成员都获得独立的 Relic MCP 服务，使用席位令牌绑定身份。消息和文档属于现有 Relic 组织。App 关闭空闲会话或重启后，会在程序支持时恢复同一个原生会话，并重新传入 Relic MCP 服务；恢复失败时不会悄悄新建替代对话。

这两个程序不加载 Claude Code/Codex 的 Relic hooks。沿用 App 现有的 ACP 行为：权限请求交给用户处理，Relic 协议可以拦截这些请求，已完成的工具调用记入活动记录，回合结束后可以触发 episode 反思提醒。没有发出权限请求的工具不经过这项执行前检查；本适配也没有增加依赖 hooks 的 Reply 检查。

## 验证

在仓库根目录运行 `python -X utf8 scripts/check.py`。原生启动、模型选项和 App 集成测试使用临时数据与替身程序，覆盖程序选择、带空格路径、桌面/CLI 启动、分组选项、实际设置回执、MCP 席位身份、拒绝权限、取消和恢复时重新注入 MCP。真实验收与这些测试分开，在隔离组织中使用合成文档。

参考：[Kimi ACP 命令](https://moonshotai.github.io/kimi-code/en/reference/kimi-acp)、[DSH ACP 服务接口](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/acp/acp/README.md)。
