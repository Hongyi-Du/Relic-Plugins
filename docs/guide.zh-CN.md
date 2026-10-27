# Relic 完整使用指南

**当前公开版本仅支持 Windows；macOS 尚未发布，等待真实 Mac 测试。**

[English](guide.en.md) · [Windows](windows.zh-CN.md) · [macOS](macos.zh-CN.md) · [工具参考](reference.zh-CN.md)

## 1. Relic 是什么

Relic 是一个产品、一个下载包：给 Claude Code 和 Codex 用的 **Relic 插件**，加上 **Relic App**。插件给 Claude Code 或 Codex 会话提供 Relic 工具和 hooks，让会话能建立或加入组织。App 是给你的组织用的桌面聊天应用，也是成员之间的桥：成员可以作为 Claude Code 或 Codex 会话在 App 里运行，由 App 自己把 Relic 带进这些会话。一个组织的所有成员，不论在哪个宿主上运行，都使用同一个本地数据库。

这里的“GPT”成员指 **Codex 编程会话**。普通 ChatGPT 对话不会因为安装本包而获得 Relic 工具；桌面应用里的 ChatGPT 聊天可以占一个席位，但回复需要人工转发（见第 7 节）。

v0.2.0-beta.1 有三个版本：Relic Claude、Relic Codex / GPT 和 Relic Bridge。它们已经合并：Bridge 变成了 Relic。用过其中某个版本，请看 [第 9 节](#9-从以前的版本过来)。

## 2. 安装与检查

按 [Windows 安装指南](windows.zh-CN.md) 安装；[macOS 文档](macos.zh-CN.md) 暂为未发布的开发草稿。安装器会在使用者电脑上解析 Python 和服务器路径，让插件的 MCP 服务和 shell hooks 使用同一个解释器，然后对每个宿主调用官方插件 CLI：先 `<cli> plugin marketplace add <目录>`，再 `claude plugin install relic@relic-bridge` 或 `codex plugin add relic@relic-bridge`。在 Claude Code 里，它会先尽力停用注册了相同工具名的旧版本（`relic@relic-claude`、`relic@relic-local`）。在 Windows 上，它会在桌面建一个名为 Relic 的快捷方式来打开 App。安装器不会替你登录、购买额度、下载任何东西、调用模型、批准 hooks 或修改组织数据。

解压目录需要长期保留：插件的 MCP 配置和快捷方式都指向其中的文件。移动后要从新位置重新运行安装器。`--host` 选择宿主：`auto`（默认）安装到所有找得到 CLI 的宿主；`claude`、`codex` 或 `both` 指定宿主，指定的宿主没装时安装器报错停止；`none` 不改任何宿主，只用 App。`--configure-only` 只准备目录，不改宿主，也不建快捷方式；`--no-shortcut` 不建快捷方式；`--open` 在安装完成后打开 App。

在 Relic App 里运行的成员由 App 提供 Relic，它们的宿主不需要装插件。其他 Claude Code 和 Codex 会话（包括你自己的），安装后要开始新会话，在宿主插件设置中审阅并信任 hooks。hooks 不可用或未被信任时，共享工具可能仍能工作，但不能假定自动上下文注入和工具阻断已生效。先检查宿主实际加载的 MCP 工具列表，再用一个无害的小任务试用。

## 3. 创建第一个组织

在已启用插件的 Claude Code 或 Codex 会话中说：

> 用 Relic 建立一个两人组织，完成小型文档任务。我会给出任务和工作区边界。先创建组织，告诉我组织 ID，等另一名成员加入。

负责人调用 `create`，提供 `name`、`purpose`、`member`，可选 `role` 和治理方式 `governance`（`leader` 或 `peer`）。记下返回的 `org_id`。在第二个会话（Claude Code 或 Codex）中说：

> 加入 Relic 组织 org_…，成员名 reviewer。读取当前组织状态，并与负责人协调。

两边必须在同一台电脑上使用同一个 `RELIC_HOME`。Claude Code 工具通常以 `mcp__plugin_relic_org__*` 开头；Codex 工具通常为 `mcp__relic_org__*`。具体显示前缀以宿主加载的工具列表为准。

在 Relic App 里，「新建组织」创建组织，「添加成员」给它加成员（见第 4 节）。

Claude Code 的负责人加子智能体模式可以使用包内的 `relic:member` 定义。每个子成员需要实际组织 ID、成员名、任务和边界。不要伪造其他会话的 actor；身份由 hooks 或宿主元数据提供。Codex 子智能体在父会话的席位里工作。

已有独立会话直接 `join` 最简单。启动时环境里带 `RELIC_ORG` 和 `RELIC_MEMBER`（可选 `RELIC_ROLE`）的会话，一启动就占这个席位；工作区里有 `.relic-seat.json` 的会话也一样：

```json
{"org":"org_actual_id","member":"reviewer","role":"review"}
```

填写真实返回的组织 ID。不要将席位文件复制到无关工作区。不同会话以同一个成员名加入表示更换该席位的载体，并不是新增两位成员。

## 4. 在 Relic App 里添加成员

「添加成员」（在侧栏、「概况」面板或「文件 → 添加成员…」）有三种运行方式：

- **在 App 里运行**：由 App 托管成员的会话。选择 Claude Code 或 Codex、模型和文件夹（默认 `~/.relic/workspaces/<组织>/<成员>`），也可以把它设为这个组织的秘书。它坐进席位、读一遍组织，然后等任务。
- **命令行或桌面版**：成员的会话在 Claude Code 或 Codex 本身里运行。可以选择模型、推理强度、文件夹或它自己的 git worktree、权限和环境变量。Relic 启动它的会话，并在有消息时唤醒它。
- **已有会话**：把这台电脑上已有的会话放进席位：Claude Code 会话、Codex 对话或 ChatGPT 聊天。它带着自己的上下文加入。「文件 → 把已有会话放进组织…」直接打开这一种。

后两种成员是 Claude Code 或 Codex 本身的会话，使用那里安装的 Relic 插件；ChatGPT 聊天不需要插件，由 Relic 代它收发。模型留空时使用宿主默认值。插件本身不直接调用模型 API；成员的回合消耗宿主账号额度或其配置的 API 计费。

成员卡片（点它的头像）管理席位：「开新会话」换一个新会话（职责、任务和协议留下，旧会话的私人笔记不带过去）；「打开会话」在终端或桌面版里打开它的会话；「改配置」修改它的配置；「离开席位」让会话离开、席位留着；ChatGPT 聊天还有「转发回复」，用来提交你从 ChatGPT 窗口复制的回复（见第 7 节）。

在 App 里运行的成员是 Agent Client Protocol（ACP）会话，通过官方适配器 `@agentclientprotocol/claude-agent-acp@0.97.0` 和 `@agentclientprotocol/codex-acp@2.3.0` 启动。在「设置 → Harness 连接」里安装它们：npm 把它们装在 `~/.relic/acp`（约 70 MB），所以需要 Node.js。适配器驱动这台电脑上已有的 Claude Code 和 Codex。App 这样把 Relic 带进它运行的每个会话：

- Claude Code 会话从 App 自己的目录加载插件。Claude Code 里已安装的 Relic 插件在这个会话里被关掉，工具和 hooks 只运行一份。
- Codex 会话在 Codex 里启用了 Relic 插件时用 Codex 自己的插件；否则由 App 给这个会话 Relic MCP 服务。
- 每个会话以它的席位命名。App 启动会话时在席位上存一个令牌，它启动的 Relic 服务带着席位和这个令牌（`RELIC_SEAT`、`RELIC_SEAT_TOKEN`）。令牌一致时，服务就代表这个席位。

所以在 App 里运行的成员只需要已经安装并登录的 Claude Code 或 Codex。App 运行的 Claude Code 会话以 `auto` 权限模式开始；App 运行的 Codex 会话使用与你 Codex `config.toml` 中 `sandbox_mode` 对应的模式。Relic 不替你决定的权限请求，在 App 里等你回答。App 运行的成员只在 App 的服务运行时才会被唤醒；服务重启后，它们的会话接着恢复。

其他支持 ACP 的编程智能体，在 `plugins/relic/app/harness.py` 里加一条就能接入。「设置 → Harness 连接」在「以后接入」下列出 ACP 注册表里的智能体：CodeBuddy / WorkBuddy、GLM、Kimi、Qwen Code、Gemini CLI 和 OpenCode。对没有 Relic hooks 的会话（这类智能体的会话，或 Codex 里没启用 Relic 插件、或其 hooks 未被信任时的 Codex 会话），由 App 代做 hooks 的工作：放行 Relic 自己的工具调用，在会话请求权限时检查强协议（会话不请求权限就做的动作拦不住），把完成的工具调用记为活动，结束这一轮，并在该写反思时多给一轮简短回合。

## 5. 共同工作、episode 与持久协议

Relic 区分三类状态：

| 状态 | 示例 | 席位换人后保留？ |
| --- | --- | --- |
| 成员私有笔记 | 私人临时观察 | 不保留 |
| 共同工作 | 消息、版本化文档、任务、episode | 保留 |
| 组织协议 | 已采纳的共同约定与可执行规则 | 保留 |

需要多人依赖的接口和决定写入共享文档。更新时提供预期 revision，避免覆盖同伴刚完成的修改。任务应有负责人，标记完成时附提交、审阅文件或测试结果等具体证据。消息是持久通信记录，投递回执不是任务验收。

为一个有意义的协作单元打开 episode，以真实结果结束，再由每位参与者反思实际遇到的协调问题。同类问题反复出现时可以提议组织协议。插件不会预置业务协议，也不要求组织达到某个协议数量。

**弱协议**是共享指导。**强协议**额外提供明确可执行条件，作用于支持的工具调用：`deny`、`require_review`、`require_before`。详见 [工具参考](reference.zh-CN.md)。

协议例子包括按职责限制目录写入、对准确的发布命令要求同伴审核、要求最后一次修改后先通过测试。成员用 `protocol` 工具提案、讨论和批准。提案不等于已生效的强制规则。修订和废止保留历史；使用记录应区分遵循、偏离和不适用。

hooks 只约束实际经过它的动作，不能当作操作系统隔离或对所有托管工具的全面控制。宿主沙箱和正常权限仍然适用。遇到不合理规则时，通过保持可达的治理工具缩小范围、修订或废止。

成员把任务标为完成时必须带上证据和一份简短的完成报告（Markdown，最多 1000 字），说清做成了什么、结果怎样；成员按你的语言写任务标题和报告（取自 `RELIC_LANG`、Relic App 的语言设置或系统语言）。回复某条消息时可以用 `message` 的 `reply_to` 在它的话题里回复。

## 6. Relic App 与自动回合

用桌面上的 Relic 快捷方式打开 App，或让装了插件的 Claude Code / Codex 会话打开 Relic App（`panel` 工具），或运行 `python -X utf8 scripts/open_app.py`（`--no-window` 只启动服务并打印地址）。它在本机 127.0.0.1 起一个服务，端口 39321 或下一个空闲端口，并用 Microsoft Edge 或 Chrome 打开应用窗口。在窗口栏点「安装」，可以装成有自己窗口、标题栏和任务栏图标的应用；装好的应用只连 39321 端口上的服务。关掉窗口后，服务仍在后台运行。本内测版界面为中文。

左侧是组织和成员；中间是群聊、秘书和每个成员的私聊，能读到会话记录的成员显示它自己会话里的全部对话，动作折叠；右侧可切换「概况」「工作区」「文件」「话题」。群聊里的「翻译成人话」把成员之间的话改写成不了解上下文也能看懂的话，原文折叠在下面；「解读」用几句话讲清群里最近在干什么。这两项和成员的自动命名会用你已登录的 Claude Code 发起简短调用（`claude -p`，不保存会话），按你的 Claude 账号正常计费。

配置过的席位，在组织启用自动唤醒后可因新消息启动额外回合。当前限制包括最多六跳自动消息链、编程席位两分钟间隔、每组织每小时最多三十次唤醒。回执不会递归唤醒发送者。在「概况」面板关掉「自动唤醒」开关即可停止这种行为。未配置的席位通过显式工具、hooks 或 `inbox` 接收消息。

在 Windows 上，Codex 桌面应用里打开的 Codex 对话通过应用自己的工具管道唤醒。请求可能已经送达但未确认时保留 uncertain，不盲目重发。macOS 上没有这条通路：使用 CLI 持有的会话和显式 `inbox`；不要通过另一个写入者恢复已被桌面锁住的会话。成员卡片上的「打开会话」在 macOS 上尚未认证，请自行在 Terminal 打开会话。

## 7. 聊天席位与轨迹访问

Relic 的 Claude Chat 接入需要在 Claude Desktop 单独配置本地 MCP，安装 Code 插件不等于配置 Chat 页。该连接使用 `claude-chat:` actor 和最长 50 秒 inbox 等待；聊天需自己发起回合。

在 Windows 上，ChatGPT 聊天可以占一个席位：在 ChatGPT 桌面应用运行时，用「添加成员 → 已有会话」把它放进席位。Relic 把发给它的每条消息的全文放进这个聊天。应用不把 ChatGPT 回复的文字交给插件，所以需要本人在 ChatGPT 窗口复制每条回复，再用成员卡片上的「转发回复」转进组织；它以这个聊天成员的消息送到各成员。这不是 ChatGPT 网页版的全自动集成，也不在 macOS 内测可用范围内。

成员请求另一位成员的轨迹时必须说明理由，并得到对方批准。读取自己席位前任的轨迹由人类决定。导出可能包含完整对话、工具记录和可归属该会话的记忆；默认脱敏不能保证去掉所有私人细节。不需要记忆时传 `memory:false`，共享前检查文件，并阅读 [隐私与数据](privacy.zh-CN.md)。

## 8. 数据、升级与卸载

Relic 的数据都在 `~/.relic`（`~` 是当前系统账号的主目录）；`RELIC_HOME` 可以把它们整体移到别处。

| `~/.relic` 下的路径 | 内容 |
| --- | --- |
| `relic.sqlite3` | 组织：成员、消息、文档、任务、episode、协议 |
| `app/` | App 偏好、头像、保存的「人话」和「解读」结果 |
| `acp/` | ACP 适配器，以及它们报告过的模型 |
| `runs/` | 自动唤醒、成员回合和 App 服务的日志 |
| `workspaces/<组织>/<成员>` | 在 App 里添加的成员的默认文件夹 |
| `trajectories/` | 经过批准的轨迹导出 |

一个组织的所有成员必须使用同一台电脑上的同一个数据目录；不支持依靠网盘同步在多台电脑上并发共享数据库。

升级前先关闭自动唤醒，关掉 Relic 会话，并停止 App 的服务（进程号是 `~/.relic/app.json` 里的 `pid`）。再私下备份完整数据目录，包括可能存在的 SQLite WAL/SHM 文件，并保留旧下载包。将新版解压到准备长期保留的路径并运行其中的安装器：它会先移除指向旧目录的 `relic-bridge` marketplace 注册，再把新目录注册上。重启宿主，按提示重新审阅 hooks。不要为了修安装错误而删除组织数据库。

回滚时，在进程已停止的条件下恢复旧下载包与匹配的数据备份。卸载时在宿主插件管理器中移除插件，并删除 Relic 快捷方式；数据和解压目录会保留，只有明确不再需要记录时才另行删除。

## 9. 从以前的版本过来

v0.2.0-beta.1 的各个版本仍可从 [v0.2.0-beta.1 Release](https://github.com/Hongyi-Du/Relic-Plugins/releases/tag/v0.2.0-beta.1) 下载，不再开发。

- **Relic Bridge** 变成了 Relic。marketplace 沿用原来的名字，所以插件 id 仍是 `relic@relic-bridge`，安装器会就地升级 Bridge；显示名现在是 Relic。`~/.relic` 里的组织照常保留。Tk 的 Relic 窗口去掉了：它能做的事都在 App 里，`panel` 工具会打开 App。
- **Relic Claude** 注册了相同的工具名，所以安装器会在 Claude Code 里停用 `relic@relic-claude`（以及 `relic@relic-local`）。它的组织在 `~/.claude/relic/relic.sqlite3`，不会被转换。
- **Relic Codex / GPT**（Codex 插件 `relic-organization`）的工具和数据都不同，所以安装器不动它。不再使用时请在 Codex 里移除。它的数据留在 `~/.codex/relic-organization`，不会被转换。Codex 版的这些功能在 Relic 里没有对应：用 Codex 原生子智能体组建组织、文字会议（`org_call`）、静默模式，以及 `require_peer_review` 规则格式（Relic 里最接近的是 `require_review`）。

## 10. 排错与反馈

在解压目录运行 `python scripts/doctor.py`。它报告 Python、Claude Code 与 Codex CLI、Node.js、ACP 适配器，以及配置的 MCP 服务路径是否存在；不读取聊天内容，不启动模型回合。

| 现象 | 检查方向 |
| --- | --- |
| 找不到 Relic 工具 | 插件是否已安装并启用、是否新会话、解释器和脚本路径、宿主 MCP 日志 |
| Claude Code 里的 Relic 工具出现两份 | 旧版本仍在启用：停用 `relic@relic-claude` 或 `relic@relic-local` |
| 强规则从不阻断 | hooks 是否被信任和启用、规则是否 active、该工具是否经过 hook |
| 尚未加入组织 | 使用当前会话加入真实组织 ID，不覆盖其他成员身份 |
| 文档 revision 冲突 | 读取最新版，合并修改，再使用其 revision 写入 |
| 消息 pending | 收件人配置/空闲状态、自动唤醒是否打开、显式 inbox；App 运行的成员只在 App 服务运行时被唤醒 |
| 消息 uncertain | 先查收件人回执，再决定是否重试，可能已送达 |
| App 打不开 | 在终端运行 `python -X utf8 scripts/open_app.py` 查看错误；服务日志在 `~/.relic/runs/relic-app.log` |
| 装好的 App 连不上 Relic | 39321 端口被占用，服务换了端口；释放端口，停止服务（`~/.relic/app.json` 里的 `pid`），再打开 App |
| 成员无法在 App 里运行 | 「设置 → Harness 连接」：适配器是否已装、是否找到 Node.js、Claude Code 或 Codex 是否找到并已登录 |
| Codex 桌面对话没被唤醒 | Windows 上 Codex 桌面应用是否打开；被终端里 Codex CLI 会话持有的对话无法触达，消息等它调用 `inbox` |
| macOS 上 Relic 无法唤醒桌面聊天 | 当前平台限制，使用 CLI 同伴或显式 inbox |

报告问题时附发布版本、系统、Python 和宿主版本、失败步骤、预期行为及最小脱敏日志。不要默认上传真实组织数据库或完整轨迹。
