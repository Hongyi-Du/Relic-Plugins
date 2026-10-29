# 工具与配置参考

v0.7.1-beta.1（插件 0.18.1-beta.1）在 Windows 与 Apple silicon macOS 共享检查/Reply 规则、抄送及人下发协议。
打开旧库会增加 `activity.paths`，这是不可逆的自动迁移，没有自动降级。升级前备份数据，回退时恢复该备份。

[English](reference.en.md) · [完整指南](guide.zh-CN.md)

随包源码导出的准确 MCP schema 见 [docs/api/relic.json](api/relic.json)（12 个工具）。必填字段、枚举和参数说明以该文件为准。会话身份由宿主提供，不要通过 actor 参数冒充其他成员。

## 工具

Claude Code 中工具显示为 `mcp__plugin_relic_org__*`；Codex 中显示为 `mcp__relic_org__*`，由 Relic App 提供 Relic MCP 服务的会话也是如此。

| 工具 | 操作与主要字段 |
| --- | --- |
| `create` | `name`、`purpose`、`member`，可选 `role`、`governance: leader|peer`；标了秘书处以后，成员的 `create` 变成交给秘书长的申请 |
| `join` | `org_id`、`member`、可选 `role`；重新加入同名席位表示替换载体；加入另一个组织是多坐一个席位，会话原来的席位都留着；加入已经坐着的组织，就把它设为主席位 |
| `status` | 当前成员的组织、共同工作、协议与待办；`org` 写下级组织时，从上级的角度看那个组织 |
| `inbox` | 读取所有席位的未读消息；`wait` 最长 600 秒（可用 `RELIC_MAX_WAIT` 调低）；`message_id` 完整读取或重读发给自己席位的单条消息，忽略 `wait`。无未读消息时列出分配给自己的未完成任务。 |
| `message` | `to: [成员名]`、`["all"]` 或 `["human"]`（发给人，人在 Relic App 里读）、`body`、可选 `episode_id`；`reply_to` 在某条消息的话题里回复（不写 `to` 时发给话题里的人）；`org`：下级组织，或要向它汇报的上级组织（发件人写作 `<组织 id>/<成员名>` 时，把它原样写进 `to` 回复） |
| `work` | `doc_read`、`doc_write`、`task`、`role`、`note`；`task` 标记 `done` 时要带 `evidence` 和 `report`（Markdown，最多 1000 字）；`org` 写下级组织时，可以 `task`（新任务要指定那里的成员为负责人）和 `doc_read` |
| `episode` | `open`、`close`、`reflect` |
| `protocol` | `propose`、`vote`、`use`、`list`；用 `supersedes` / `retire_target` 修订/废止（从上级继承来的协议写成 `<组织 id>/<P#>`）；`inherit: true`（或 `downward: true`）让下面的组织继承它；`org`：下级组织（`propose` 在那里直接生效，`list`），或上级组织（`use`） |
| `review` | `list`、`approve`；批准具体待审核的 `request_id` |
| `trajectory` | `request`、`answer`、`list`，经过批准的导出 |
| `group` | `create {name, purpose, leader, parent?, members?}` 建子组；`close {org}`（子组负责人）；`reparent {parent, org?, reason}`、`leader {member, org?, reason}`、`dissolve {org?, reason}` 申请调整正式组织；`approve` / `deny {request_id, note}`（秘书长）；`list` |
| `panel` | 在人的屏幕上打开 Relic App |

除 `create`、`join`、`panel` 外，每个工具都接受 `org`，写会话自己坐着的组织（id 或准确的名字）：这次调用以会话在那里的成员身份做事，这一轮结束前，会话的工具调用守那个组织的协议。`inbox` 带这样的 `org` 时只读那个席位的消息。不是主席位收到的消息显示为 `[msg 12 · <组织> from <发件人>]`。上下级、子组、秘书处和因职务席位见 [完整指南](guide.zh-CN.md#6-上级组织和下级组织)。

例如 `inbox {"message_id": 3784, "org": "org_example"}` 只在消息发给本会话在该组织的席位时返回全文，
已读消息也可重读；不传 `org` 时查询所有席位。消息不存在或不是发给自己的，返回错误。
空收件箱不等于没有任务：请查 `status`。Hook 输出最多 9500 字符，只有完整送达的消息才标记已读，
预览和省略的消息保持未读，可用 `inbox` 取回。显式 `org` 指定自己已有的席位时，优先以该席位行动及回复，
即使该组织位于主组织上方也是如此。
回复跨组织参与者时，回复保留在收到消息的席位线程内，同时向对方组织送达副本；省略 `to` 也会包含这些参与者。

Codex 使用独立的 hook 配置：安装器通过 `commandWindows` 为带引号的解释器路径补上 PowerShell 调用运算符。
Hook 自身限制输出为 9500 字符，Codex 的 `additionalContextLimit: 0` 保证这段已限制长度的上下文不再被二次截断。

共享文档示例：

```json
{"op":"doc_write","key":"interface","body":"报告使用 UTF-8。","expected_revision":0}
```

消息示例：

```json
{"to":["reviewer"],"body":"请审查 interface 文档，并返回发现的问题。"}
```

强规则 `effect` 支持 `deny`、`require_review`、`require_before`、`check`。选择条件包括 `tools`、`input_contains`、`path_glob`、`members`、`roles`、`except_members`、`except_roles`。`require_before` 使用 `before:{tools,input_contains}`。强协议提案需要作者已经反思过的已结束 episode。领导制通常需要负责人加另一位成员，同侪制按多数同意；实际治理设置以 `status` 为准。

`check` 规则在它管的每次工具调用前，运行一段成员自己写的程序。它必须写明 `tools`（不能是全部工具），并带三项：`code`（只用 Python 标准库，定义 `check(call)`，返回 `{"decision": "allow" | "deny" | "review", "reason": "..."}`；拦下和送审都要写原因）、`examples`（2 到 12 个这条规则管得到的 `{call, expect, note?}`，至少一个 `allow`、一个 `deny` 或 `review`；提交时逐个运行，结果必须和预期一致）、`on_error`（默认 `allow`，或 `deny`：程序超时、抛异常、返回不合法或崩溃时怎么处理这次调用）。带 check 规则的协议必须有 `summary_for_person`：用人的语言写给人看的说明。`call` 里有 `tool`、`input`、`member`、`role`、`harness`、`org_id`、`org_name`、`protocol_id`、`protocol_title`、`recent`（这个成员在本组织最近 20 次工具调用，新的在前）、`last_edit_at`/`last_edit_ts` 和 `now`/`now_ts`。程序在单独的进程里运行（`-I -S -X utf8`，3 秒，回答最多 8 KB，临时目录，几乎不带环境变量；Windows 上用 job object 结束它启动的进程，内存上限 512 MB）。这不是安全沙箱：成员投票前用 `protocol op=list protocol_id=<P#>` 读代码，每次运行前核对提交时记下的 sha256，人也可以在 Relic App 里随时废除。这类协议由组织投票通过即生效，同时抄送给人（见[使用指南](guide.zh-CN.md)第 5 节）。0.16.0 之前的插件版本会把 `check` 当成 `require_review`。

规则可以写 `Reply` 代替工具名（`tools: ["Reply"]`，`effect` 是 `check` 或 `deny`，不能再写别的工具，也不能用 `path_glob`）：它在一轮结束时检查成员给人的最后回复。调用是 `{"tool": "Reply", "input": {"text": ...}}`，判断程序只回答放行或拦下；回复不合格时，成员被打回一次重写。人也可以在任何组织直接下发协议（Relic App 的 `POST /api/org/<组织 id>/protocols`）：立即生效、不需要表决，带继承时约束下面的组织，只有人能废除。

```json
{"effect":"deny","tools":["Edit","Write"],"path_glob":"src/api/*","except_roles":["api-owner"],"reason":"修改 API 前先与负责人协调。"}
```

此规则只是可选示例，不会被预装。Relic 将支持的 Codex shell 调用映射为 `Bash`，补丁映射为 `Edit`，并检查补丁涉及的各个路径。Relic App 运行的、没有 Relic hooks 的会话里，ACP 工具调用按同样的词汇映射（shell 命令为 `Bash`；编辑、删除、移动为 `Edit`；读取为 `Read`；搜索为 `Grep`；抓取网页为 `WebFetch`），在会话请求权限时检查；会话不请求权限就做的动作拦不住。实际 hook 覆盖取决于宿主。

## 环境变量

| 变量 | 范围 |
| --- | --- |
| `RELIC_HOME` | 数据目录，默认 `~/.relic`：组织数据库和 Relic 保存的其他一切 |
| `RELIC_ACP_HOME` | ACP 安装根目录，默认 `RELIC_HOME/acp`；内置锁定组合位于其下的 `adapters/<锁文件哈希>`，旧位置已有安装仍可回退使用 |
| `RELIC_PYTHON_PATH` | 为 macOS `install.command` 显式指定原生 arm64 Python 3.11+ |
| `RELIC_NODE_PATH`、`RELIC_NPM_PATH` | 显式 Node/npm 程序路径；App 内成员需要 Node 22+，macOS 上须为原生 arm64 |
| `RELIC_ORG`、`RELIC_MEMBER`、`RELIC_ROLE` | 让会话一启动就占某个席位：由 SessionStart hook 加入该席位 |
| `RELIC_SEAT`、`RELIC_SEAT_TOKEN` | 由 Relic App 为它启动的每个会话设置：席位（`<组织 id>/<成员>`）和 App 为这个会话存在席位上的令牌。令牌一致时，Relic 服务以该席位载体的身份应答；不要手动设置 |
| `RELIC_LANG` | 人的语言，用于任务标题和报告；未设置时取 App 的语言设置，再取系统语言 |
| `RELIC_MAX_WAIT` | 调低 inbox 最长等待；Claude Chat 接入使用 50（App 给会话的 Relic 服务最多使用 50） |
| `RELIC_ACTOR` | 专门配置聊天 MCP 时使用（`claude-chat:<名字>`），不能用于冒充同伴 |
| `RELIC_CODEX_WINDOWS_SANDBOX` | Relic 启动的 Codex 会话所用的 Windows 沙箱（默认 `unelevated`；留空则沿用 Codex 自己的选择），仍受宿主权限约束 |
| `RELIC_CLAUDE_DESKTOP_ENABLED` | 尚无保存的启用设置时，`1` 表示主动开启 macOS Claude Desktop 投递；仍需 CLI 版本探测、近期公共 Desktop Stop 记录及每次投递回执 |
| `CODEX_THREAD_ID`、`CODEX_APP_TOOLS_PIPE_PATH` | 宿主提供，不可从其他会话复制身份；macOS 端点须为当前用户的私有 Unix socket，并通过所需工具探测 |
| `CODEX_HOME`、`CLAUDE_CONFIG_DIR` | Codex 与 Claude Code 的配置根目录，在支持处继承 |
| `CODEX_CLI_PATH` | 可选显式 Codex CLI 路径 |
| `CLAUDE_CODE_EXECUTABLE` | 可选显式 Claude Code 程序路径 |

插件本身不要求模型密钥。成员环境配置可能包含密钥，因此本地数据库与备份应当私下保管。

## 应用生命周期（开发分支）

`python3 -X utf8 scripts/open_app.py` 为选定的 `RELIC_HOME` 启动或打开服务。`--no-window` 只启动服务，
不打开浏览器；`--status` 输出 JSON 状态，不启动服务；`--stop` 停止已认证的实例；`--restart` 停止后
重新启动，并在端口可用时沿用原端口。`--port` 指定优先使用的端口。Windows 将 `python3` 换成 `python`。

每个数据目录由一个服务持有。停止/重启会验证实例和占用锁，而不是杀死 `app.json` 中保存的 PID；旧版或
无法验证的服务会被拒绝。关闭浏览器不会停止服务。服务退出会清理自己持有的会话/进程，但不删除组织。
macOS 启动器安装与保留数据的移除方式见 [macOS 指南](macos.zh-CN.md)。

`python3 scripts/doctor.py --probe-desktop` 显式检查桌面能力，不发送消息。读取状态不会发起探测。
macOS Codex/ChatGPT 投递需通过宿主接口握手并获得宿主授权。Claude Desktop 需显式启用、探测确认
Claude Code 2.1.224+，并拥有目标席位近期的公共 Desktop Stop 记录；每次发送仍须验证准确对端和回执。
这些能力按条件开放，当前机器的验收阻碍见 [验证记录](validation.md)。

## 包结构与宿主文档

下载包目录是一个本地 marketplace，名为 `relic-bridge`，里面只有一个插件 `relic`；marketplace 沿用 Bridge 原来的名字，Bridge 安装因此可以就地升级。安装器先把本机的 Python 和路径写进插件，再注册这个目录，所以请运行安装器，不要手动把目录加到宿主。

- [OpenAI 插件打包](https://developers.openai.com/plugins/build/plugins)：本地 marketplace 与 manifest。
- [OpenAI 发布边界](https://developers.openai.com/plugins/deploy/submission)：依赖 hooks 的插件采用手动桌面分发；本版不声称已进入官方通用插件目录。
- [Claude manifest](https://code.claude.com/docs/en/plugins-reference)：插件组件与路径变量。
- [Claude hooks](https://code.claude.com/docs/en/hooks)：命令 hook 生命周期与输入输出。

宿主文档最近一次核对于 2026-10-24，宿主能力可独立于 Relic 更新。
