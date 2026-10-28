# 工具与配置参考

[English](reference.en.md) · [完整指南](guide.zh-CN.md)

随包源码导出的准确 MCP schema 见 [docs/api/relic.json](api/relic.json)（12 个工具）。必填字段、枚举和参数说明以该文件为准。会话身份由宿主提供，不要通过 actor 参数冒充其他成员。

## 工具

Claude Code 中工具显示为 `mcp__plugin_relic_org__*`；Codex 中显示为 `mcp__relic_org__*`，由 Relic App 提供 Relic MCP 服务的会话也是如此。

| 工具 | 操作与主要字段 |
| --- | --- |
| `create` | `name`、`purpose`、`member`，可选 `role`、`governance: leader|peer`；标了秘书处以后，成员的 `create` 变成交给秘书长的申请 |
| `join` | `org_id`、`member`、可选 `role`；重新加入同名席位表示替换载体；加入另一个组织是多坐一个席位，会话原来的席位都留着；加入已经坐着的组织，就把它设为主席位 |
| `status` | 当前成员的组织、共同工作、协议与待办；`org` 写下级组织时，从上级的角度看那个组织 |
| `inbox` | 读取所有席位的未读消息；有上限的 `wait`（秒，最长 600，可用 `RELIC_MAX_WAIT` 调低） |
| `message` | `to: [成员名]`、`["all"]` 或 `["human"]`（发给人，人在 Relic App 里读）、`body`、可选 `episode_id`；`reply_to` 在某条消息的话题里回复（不写 `to` 时发给话题里的人）；`org`：下级组织，或要向它汇报的上级组织（发件人写作 `<组织 id>/<成员名>` 时，把它原样写进 `to` 回复） |
| `work` | `doc_read`、`doc_write`、`task`、`role`、`note`；`task` 标记 `done` 时要带 `evidence` 和 `report`（Markdown，最多 1000 字）；`org` 写下级组织时，可以 `task`（新任务要指定那里的成员为负责人）和 `doc_read` |
| `episode` | `open`、`close`、`reflect` |
| `protocol` | `propose`、`vote`、`use`、`list`；用 `supersedes` / `retire_target` 修订/废止（从上级继承来的协议写成 `<组织 id>/<P#>`）；`inherit: true`（或 `downward: true`）让下面的组织继承它；`org`：下级组织（`propose` 在那里直接生效，`list`），或上级组织（`use`） |
| `review` | `list`、`approve`；批准具体待审核的 `request_id` |
| `trajectory` | `request`、`answer`、`list`，经过批准的导出 |
| `group` | `create {name, purpose, leader, parent?, members?}` 建子组；`close {org}`（子组负责人）；`reparent {parent, org?, reason}`、`leader {member, org?, reason}`、`dissolve {org?, reason}` 申请调整正式组织；`approve` / `deny {request_id, note}`（秘书长）；`list` |
| `panel` | 在人的屏幕上打开 Relic App |

除 `create`、`join`、`panel` 外，每个工具都接受 `org`，写会话自己坐着的组织（id 或准确的名字）：这次调用以会话在那里的成员身份做事，这一轮结束前，会话的工具调用守那个组织的协议。`inbox` 带这样的 `org` 时只读那个席位的消息。不是主席位收到的消息显示为 `[msg 12 · <组织> from <发件人>]`。上下级、子组、秘书处和因职务席位见 [完整指南](guide.zh-CN.md#6-上级组织和下级组织)。

共享文档示例：

```json
{"op":"doc_write","key":"interface","body":"报告使用 UTF-8。","expected_revision":0}
```

消息示例：

```json
{"to":["reviewer"],"body":"请审查 interface 文档，并返回发现的问题。"}
```

强规则 `effect` 支持 `deny`、`require_review`、`require_before`。选择条件包括 `tools`、`input_contains`、`path_glob`、`members`、`roles`、`except_members`、`except_roles`。`require_before` 使用 `before:{tools,input_contains}`。强协议提案需要作者已经反思过的已结束 episode。领导制通常需要负责人加另一位成员，同侪制按多数同意；实际治理设置以 `status` 为准。

```json
{"effect":"deny","tools":["Edit","Write"],"path_glob":"src/api/*","except_roles":["api-owner"],"reason":"修改 API 前先与负责人协调。"}
```

此规则只是可选示例，不会被预装。Relic 将支持的 Codex shell 调用映射为 `Bash`，补丁映射为 `Edit`，并检查补丁涉及的各个路径。Relic App 运行的、没有 Relic hooks 的会话里，ACP 工具调用按同样的词汇映射（shell 命令为 `Bash`；编辑、删除、移动为 `Edit`；读取为 `Read`；搜索为 `Grep`；抓取网页为 `WebFetch`），在会话请求权限时检查；会话不请求权限就做的动作拦不住。实际 hook 覆盖取决于宿主。

## 环境变量

| 变量 | 范围 |
| --- | --- |
| `RELIC_HOME` | 数据目录，默认 `~/.relic`：组织数据库和 Relic 保存的其他一切 |
| `RELIC_ACP_HOME` | Relic App 安装 ACP 适配器的位置；默认 `RELIC_HOME/acp` |
| `RELIC_ORG`、`RELIC_MEMBER`、`RELIC_ROLE` | 让会话一启动就占某个席位：由 SessionStart hook 加入该席位 |
| `RELIC_SEAT`、`RELIC_SEAT_TOKEN` | 由 Relic App 为它启动的每个会话设置：席位（`<组织 id>/<成员>`）和 App 为这个会话存在席位上的令牌。令牌一致时，Relic 服务以该席位载体的身份应答；不要手动设置 |
| `RELIC_LANG` | 人的语言，用于任务标题和报告；未设置时取 App 的语言设置，再取系统语言 |
| `RELIC_MAX_WAIT` | 调低 inbox 最长等待；Claude Chat 接入使用 50（App 给会话的 Relic 服务最多使用 50） |
| `RELIC_ACTOR` | 专门配置聊天 MCP 时使用（`claude-chat:<名字>`），不能用于冒充同伴 |
| `RELIC_CODEX_WINDOWS_SANDBOX` | Relic 启动的 Codex 会话所用的 Windows 沙箱（默认 `unelevated`；留空则沿用 Codex 自己的选择），仍受宿主权限约束 |
| `CODEX_THREAD_ID`、`CODEX_APP_TOOLS_PIPE_PATH` | 宿主提供，不可从其他会话复制身份 |
| `CODEX_HOME`、`CLAUDE_CONFIG_DIR` | Codex 与 Claude Code 的配置根目录，在支持处继承 |
| `CODEX_CLI_PATH` | 可选显式 Codex CLI 路径 |

插件本身不要求模型密钥。成员环境配置可能包含密钥，因此本地数据库与备份应当私下保管。

## 包结构与宿主文档

下载包目录是一个本地 marketplace，名为 `relic-bridge`，里面只有一个插件 `relic`；marketplace 沿用 Bridge 原来的名字，Bridge 安装因此可以就地升级。安装器先把本机的 Python 和路径写进插件，再注册这个目录，所以请运行安装器，不要手动把目录加到宿主。

- [OpenAI 插件打包](https://developers.openai.com/plugins/build/plugins)：本地 marketplace 与 manifest。
- [OpenAI 发布边界](https://developers.openai.com/plugins/deploy/submission)：依赖 hooks 的插件采用手动桌面分发；本版不声称已进入官方通用插件目录。
- [Claude manifest](https://code.claude.com/docs/en/plugins-reference)：插件组件与路径变量。
- [Claude hooks](https://code.claude.com/docs/en/hooks)：命令 hook 生命周期与输入输出。

宿主文档最近一次核对于 2026-10-24，宿主能力可独立于 Relic 更新。
