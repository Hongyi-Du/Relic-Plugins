# macOS Apple silicon 使用指南

**v0.4.1-macos-beta.1 是 Apple silicon 预发布版，未经签名或公证。**
它基于已测试的 v0.4.1-beta.1，不包含后来上游 v0.6.0-beta.1 的变化。包内提供 Relic App 与 Claude
Code/Codex 插件源码，Python、Node.js 和已登录的宿主 CLI 需要另行准备。真实 Claude Code 写作者与
Codex 审阅者已在这台 Mac 上完成组织协作流程。已测试范围和剩余限制见 [迁移步骤](macos-migration.md)
与 [验证记录](validation.md)。

[English](macos.en.md) · [完整使用指南](guide.zh-CN.md)

## 准备

macOS 目标平台是 **Apple silicon**，需要原生 **arm64 Python 3.11+**。Intel Mac 与 Rosetta 转译运行时
不在支持范围内，安装器会拒绝 x86 Python。App 内的成员还需要原生 **arm64 Node.js 22+** 和 npm。
请安装并登录 Claude Code 和/或 Codex；适配器使用这些外部 CLI，不安装可选的内置原生依赖。

`bash install.command` 从 PATH 或 Apple-silicon Homebrew 常见位置选择原生 Python，也可用
`RELIC_PYTHON_PATH` 指定解释器。共享程序查找器还支持 `~/.local/bin`、Homebrew、Volta 和已安装的 nvm
版本。用 `CODEX_CLI_PATH`、`CLAUDE_CODE_EXECUTABLE`、`RELIC_NODE_PATH`、`RELIC_NPM_PATH` 选择程序；
显式路径无效时会报错，不会自动换用其他程序。App 的 Harness 设置也可选择其成员使用的程序。

两个内置 ACP 适配器使用已提交的 npm 锁文件，成对安装到 `RELIC_ACP_HOME/adapters/<锁文件哈希>`
（默认位于 `~/.relic/acp` 下），安装成功后写入就绪标记。旧 ACP 位置中已有的安装仍可作为回退。
更新锁文件会使用独立的适配器目录，不会就地覆盖旧版本组合。

## 安装与服务管理

将 `relic-macos-v0.4.1-macos-beta.1.zip`（或同名 `.tar.gz`）解压到准备长期保留的目录，在该目录运行：

```sh
bash install.command --host none --open
```

`--host none --open` 准备并打开 App，不向宿主注册插件。在 **设置 → Harness 连接** 安装 ACP 适配器，
然后创建组织，添加成员时选择 **在 App 里运行**，并给每位成员明确的任务。独立插件会话可用 `--host claude`、`--host codex` 或
`--host both` 安装，随后重启宿主并审阅、信任 hooks。默认 `--host auto` 向找到的 CLI 注册插件。
`--configure-only` 只配置下载包，不改宿主设置，也不创建启动器。

安装器创建 **`~/Applications/Relic.app`**，它是指向此目录和选定 Python 的 Finder 启动器，请保留源码
目录。`--no-shortcut` 跳过创建；`bash install.command --remove-launcher` 只删除 Relic 自己创建的
启动器，保留宿主注册和组织数据。从新的固定目录重新安装会更新受管理的启动器。这一本地生成的启动器
不是已经签名的发行应用。

以下命令中的 `python3` 应当是安装时选定的原生 arm64 Python 3.11+；如果 shell 选择了其他版本，
请替换为所选解释器的完整路径。上面的 `--open` 会自动使用安装器选定的解释器。

```sh
python3 -X utf8 scripts/open_app.py --status
python3 -X utf8 scripts/open_app.py --stop
python3 -X utf8 scripts/open_app.py --restart
python3 -X utf8 scripts/open_app.py --no-window
```

每个 `RELIC_HOME` 只运行一个服务。状态查询不会启动服务；停止与重启会认证保存的服务实例，并等待其
释放占用锁。重启在端口可用时沿用原端口。对旧版或无法验证的服务，不会只凭保存的 PID 杀进程。
关闭浏览器窗口不会停止后台服务。停止服务会清理它持有的会话与进程，组织数据仍保留在磁盘上。

所有宿主应共享 `~/.relic` 或显式指定的 `RELIC_HOME`。替换包前先停止服务并备份数据目录。打开旧数据库
时会在缺失的情况下补充活动路径字段，并保留已有记录；没有结构化路径的历史记录继续使用旧解析方式。
宿主插件移除、marketplace 路径和回滚见 [完整指南](guide.zh-CN.md) 第 9 节。

## 当前能力

| 功能 | 预发布行为与验证情况 |
| --- | --- |
| CLI 工具和 hooks | 组织、消息、文档、任务与治理共享本地数据库；执行约束需要宿主加载 hooks |
| App 内的 ACP 成员 | 已登录的 Claude Code 写作者与 Codex 审阅者完成了任务、双向消息和共享文档修订；启动等待指令之后需要明确的任务提示 |
| 浏览器 App | 查找 Edge/Chrome app 包或打开默认浏览器；Safari/Chromium 交互、剪贴板、输入法和触控板验收尚未完成 |
| Finder 与 Terminal | 已实现原生文件/目录打开及交互会话启动器，失败会报告；交互验收尚未完成 |
| 协议路径 | 记录绝对与解析后的路径，使用 NUL 分隔的 Git 路径，按 macOS Unicode 与目标卷的大小写行为匹配；检查符号链接别名并保留 Windows 匹配语义 |
| Codex Desktop 与 ChatGPT 席位 | 已实现 Unix socket 通信；宿主提供的私有 socket 必须通过所需工具握手，并由宿主授权请求后才可用 |
| Claude Desktop 自动回合 | 已实现，但需显式启用、通过 CLI 版本探测并观察到公共 Desktop Stop hook；每次投递还需准确对端与完成回执 |

配置为 GUI 的席位不会悄悄改由 CLI 写入。自动投递不可用时，已有 Code 会话仍可通过已加载的工具、hooks
和 `inbox` 手动参与。在「概况」关闭「自动唤醒」，可让所有成员回合保持手动推进。

## 桌面能力检查

普通诊断使用 `python3 scripts/doctor.py`。显式执行 `python3 scripts/doctor.py --probe-desktop` 可检查
桌面接口，不会发送聊天消息。App 设置里也提供能力检查。只读取状态不会自动探测宿主。

**Codex/ChatGPT：**通信只接受宿主提供的端点或其已记录副本，并验证 socket 私有且属于当前用户。
成功的所需工具握手与 socket 身份绑定，替换 socket 后原验证失效。已从安装的 macOS 宿主确认消息分帧
格式，但本次实测中真实宿主关闭了握手，因此当前测试环境仍无法投递。需要打开已加载 Relic 的聊天，
并获准使用宿主通信；app-server 连接不能替代该接口。

**Claude Desktop：**先在 Relic 设置中显式启用（尚无保存的设置时也可设
`RELIC_CLAUDE_DESKTOP_ENABLED=1`），选择 **Claude Code 2.1.224+** 并运行能力探测。在一个已有的、配置
为 GUI 的 Relic 席位中，加载公共 Stop hook 后完成手动 Desktop 回合。记录必须仍在有效期内，每个目标
席位都需要自己的记录。通过这些前置条件后，每次请求仍要检查准确对端和匹配的完成回执；不确定是否成功
的发送不会被当作新投递重试。较早的检查使用 **2.1.92**，低于要求；后来的组织测试使用 **2.1.286**，
但没有验证 Desktop 路径，其启用状态、公共 Stop 记录和回执仍未通过实测。这个 CLI 版本要求仅针对该
桌面通信路径。

## 已测试范围与已知限制

已登录组织测试完成了写作者和审阅者任务、双向消息、共享文档修订与过期修订号写入拒绝。启动等待指令
之后需要显式的人类任务提示，因此不能据此宣称完全自主启动、上下级或全部治理约束已通过验收。解压 ZIP
还单独在隔离数据目录中通过了安装、诊断、服务状态、重启和停止检查。

真实浏览器验收尚未完成：Chrome 自动化不可用，内置浏览器超时，Safari 尝试挂起后被中止。这些尝试
不计为成功的 UI 验证。Finder/Terminal 交互、剪贴板、中英文输入、触控板和拒绝权限流程尚未全部进行
交互实测。真实宿主的取消/续接/睡眠以及完整治理和上下级流程也超出本次已完成的测试范围。桌面投递须
通过上述宿主检查，当前环境尚未验证。[CI 40808895809](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40808895809)
中的四个 Windows/macOS 任务已全部通过；受测运行时代码提交、数量及平台专用跳过项见 [验证记录](validation.md)。

本版提供源码安装包和本地生成的启动器，未经签名或公证。
