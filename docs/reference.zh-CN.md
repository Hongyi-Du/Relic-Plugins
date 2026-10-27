# 工具与配置参考

[English](reference.en.md) · [完整指南](guide.zh-CN.md)

随包源码导出的准确 MCP schema 见 [Claude](api/claude.json)、[Codex](api/codex.json)、[Bridge](api/bridge.json)。必填字段、枚举和参数说明以这些文件为准。会话身份由宿主提供，不要通过 actor 参数冒充其他成员。

## Claude 与 Bridge

| 工具 | 操作与主要字段 |
| --- | --- |
| `create` | `name`、`purpose`、`member`，可选 `role`、`governance: leader|peer` |
| `join` | `org_id`、`member`、可选 `role`；重新加入同名席位表示替换载体 |
| `status` | 当前成员的组织、共同工作、协议与待办 |
| `inbox` | 读取未读消息；Bridge 增加最长 600 秒的 `wait` |
| `message` | `to: [成员名]` 或 `["all"]`、`body`、可选 `episode_id`；Bridge 可用 `reply_to` 在某条消息的话题里回复（不写 `to` 时发给话题里的人） |
| `work` | `doc_read`、`doc_write`、`task`、`role`、`note`；Bridge 的 `task` 标记 `done` 时要带 `evidence` 和 `report`（Markdown，最多 1000 字） |
| `episode` | `open`、`close`、`reflect` |
| `protocol` | `propose`、`vote`、`use`、`list`；用 `supersedes` / `retire_target` 修订/废止 |
| `review` | `list`、`approve`；批准具体待审核的 `request_id` |
| `panel` | 仅 Bridge：打开 Tk 组织窗口 |
| `trajectory` | 仅 Bridge：`request`、`answer`、`list`，经过批准的导出 |

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

此规则只是可选示例，不会被预装。Bridge 将支持的 Codex shell 调用映射为 `Bash`，补丁映射为 `Edit`，并检查补丁涉及的各个路径。实际 hook 覆盖取决于宿主。

## 独立 Codex / GPT 版

| 工具 | 用途 |
| --- | --- |
| `org_discover`、`org_panel` | 发现本机会话、打开成员选择面板 |
| `org_organize` | `start` / `status`、`request_id`、`data`；原生或桌面组建 |
| `org_context` | 当前真实执行者有权访问的状态、原生 inbox/outbox、协议活动 |
| `org_message` | `send`、`ack`、`dispatch`、`list`，使用本版本的 `data` 格式 |
| `org_work` | 版本化文档、任务、episode、反思与成员私人笔记 |
| `org_call` | 有界文字会议，议题、参与者与 1–6 轮贡献 |
| `org_protocol` | 提案、同意/讨论/投票/采纳、使用记录、修订、废止 |
| `org_review` | 预检动作或记录其他成员对准确动作的审查 |
| `org_benchmark` | 可选开发接口，需要另外的基准资源 |
| `org_scope_evolution` | 实验性开发接口，管理经治理的 patch/scope 注册与部署 |

多数操作采用 `{org_id,operation,data}`。嵌套字段和回执语义见随源码提供的 [operations](https://github.com/Hongyi-Du/Relic-Plugins/blob/main/editions/codex/plugins/relic-organization/skills/relic-organization/references/operations.md) 与 [native-subagents](https://github.com/Hongyi-Du/Relic-Plugins/blob/main/editions/codex/plugins/relic-organization/skills/relic-organization/references/native-subagents.md)。

```json
{"operation":"start","request_id":"a-fresh-request-id","data":{"runtime":"native_subagents","execution_mode":"native","name":"文档组","task":"审查文档","new_members":2}}
```

这只是登记组建，随后还要实际调用宿主创建成员。结果未知时复用原请求与键，不要换一个请求来隐藏不确定性。原生消息在实际收件人确认前保持 pending。

Codex 强规则支持 `deny`、`require_peer_review`，字段包括 `tools`、可选 `members`、`input_contains`、`argument_equals`。审核回执绑定准确参数和协议版本，一小时后过期，不能自审。弱协议保存 guidance、trigger、scope，不包含阻断规则。达到当前组织要求的负责人及同伴同意条件后生效，不要假定固定阈值。

## 环境变量

| 变量 | 范围 |
| --- | --- |
| `RELIC_HOME` | Claude / Bridge 数据目录；不要混用独立 Claude 与 Bridge 数据 |
| `RELIC_ORG_HOME` | 独立 Codex 数据目录 |
| `RELIC_ORG`、`RELIC_MEMBER`、`RELIC_ROLE` | Claude/Bridge 平级会话启动席位 |
| `CODEX_THREAD_ID`、`CODEX_APP_TOOLS_PIPE_PATH` | 宿主提供，不可从其他会话复制身份 |
| `CODEX_HOME` | Codex 配置根目录，在支持处继承 |
| `CODEX_CLI_PATH` | 可选显式 Codex CLI 路径 |
| `RELIC_MAX_WAIT` | Bridge inbox 最大等待；Claude Chat 使用 50 |
| `RELIC_ACTOR` | 专门配置独立聊天 MCP 时使用，不能用于冒充同伴 |
| `RELIC_CODEX_WINDOWS_SANDBOX` | Bridge runner 的 Windows 沙箱选项，仍受宿主权限约束 |
| `RELIC_CODEX_APP_SERVER`、`CODEX_MCP_NODE_PATH` | 独立 Codex 桌面适配器高级配置 |
| `RELIC_ORGANIZATIONBENCH_PATH` | 可选外部开发基准仓库 |

插件本身不要求模型密钥。成员环境配置可能包含密钥，因此本地数据库与备份应当私下保管。

## 包结构与宿主文档

每个版本各有一个本地 marketplace。发行安装器先配置本机 MCP 与 hook 路径，再注册；不要把未配置的整个源码仓库根目录当成单个 marketplace 安装。

- [OpenAI 插件打包](https://developers.openai.com/plugins/build/plugins)：本地 marketplace 与 manifest。
- [OpenAI 发布边界](https://developers.openai.com/plugins/deploy/submission)：依赖 hooks 的插件采用手动桌面分发；本版不声称已进入官方通用插件目录。
- [Claude manifest](https://code.claude.com/docs/en/plugins-reference)：插件组件与路径变量。
- [Claude hooks](https://code.claude.com/docs/en/hooks)：命令 hook 生命周期与输入输出。

本次发布于 2026-10-24 核对这些说明，宿主能力可独立于 Relic 更新。
