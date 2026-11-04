**Windows 实时会话：实现与待补的捕获证据**

共享 fixture 位于 `scripts/visual/serve.py`。原有场景创建组织、成员、消息和 Claude transcript 文件；成员席位配置使用 `surface: cli`。原有 `private` 场景没有嵌入式运行会话，只覆盖历史私聊／transcript，不能证明 `DrawLive` 的实时分支已经运行或通过逐元素比较。新增的 `live-busy`、`live-tool-output`、`live-typing` fixture 通过仅供 CI 的 `POST /api/visual/scene` 切换真实 Hub 内存状态；它们是新增覆盖，不能用来重新解释旧截图。

本轮只修改 Windows `DrawLive`，并增加 `LiveConversationControls.cs`。实现遵循参考 `app.js` 的 `liveItems` / `renderLive`：

- 按实际 `seq` 排序；`running`、`waiting`、`starting` 时只显示最后一个 `start` 标记开始的 turn；非忙碌状态只保留仍存在于 `decisions`、且 `kind` 为 `permission` 的权限项。
- 只有成员为 `embedded` 且 `has_transcript` 时显示当前 turn 的第一个 prompt；使用本人头像及右侧消息气泡，不添加姓名、时间或消息动作。
- 成员头像、姓名和实际状态在同一回复区域；本轮操作默认展开，工具步骤默认折叠，权限卡、错误提示及最后一条 assistant 文本按参考顺序呈现。
- 仅 `running` 且没有 assistant 文本时显示三个原生动画圆点。动画周期为 1.2 秒，依次延迟 0、0.2、0.4 秒，并响应系统减少动画设置。

该实现尚未通过带真实 live 数据的运行捕获验证。旧 fixture 的私聊场景即便通过，也不能把这里标记为已验证。共享 fixture 已增加三种状态及回归测试，但捕获接入、CI 测试结果和逐元素结果仍须分别验证；没有在本机启动 runner、成员会话、应用或测试。

建议共享 fixture 最少增加以下状态，所有数据仅在 CI 中通过真实存储／live 数据接口写入，不启动 runner 或 provider：

| 场景参数建议 | 必要数据和操作 | 要验证的行为 |
|---|---|---|
| `live-busy` | 一名 `embedded` 且有 transcript 的成员；保留上一轮记录，再写新 `start` 的 prompt；本轮工具分别为 `pending`、`in_progress`、`completed`、`failed`，其中一个有多行输出；error；两次 assistant 更新；通过真实 permission 流程产生 allow/deny options，成员进入 `waiting` | 上一轮过滤、prompt 条件、最新回复覆盖、默认展开的操作组、步骤折叠状态、权限卡和错误样式。增加真实点击展开工具步骤的子状态，验证完整输出和滚动 |
| `live-completed` | 同一成员的权限请求已解决，status 变为 `idle`；最终回复写入真实 transcript；旧 live 项及已解决 permission 记录保留 | 完成回复从历史 transcript 显示；旧 live assistant/tool/已解决 permission 不重复显示。参考在空闲状态不会继续显示旧实时 assistant，因此不能给此场景伪造一个 live 完成气泡 |
| `live-typing` | 本轮 `running`，有 start/prompt，但没有 assistant 文本 | 三个圆点及其实际动画状态；需要所有客户端采用同一已说明的减少动画设置或捕获时刻，不能仅为一个平台抹掉动画状态 |

新增 fixture 的 `live-busy` / `live-tool-output` 提供真实 `waiting` 权限状态，后者要求客户端通过真实工具控件展开输出；`live-typing` 提供没有当前 assistant 文本的 `running` 状态。`live-completed`、`starting` 和 `has_transcript=false` 仍需附加状态覆盖。权限按钮执行后还应通过 UI 验证 `/api/permission/<id>` 收到原 option id，并由真实决定状态变化触发刷新；内存权限回归测试不能替代按钮端到端证据。新增 fixture 尚未构成通过的矩阵证据。

真实数据入口在 `plugins/relic/app/hub.py`：`Live(org_id, member, harness)` 构造器只创建内存状态，`agent` 初始为 `None`；fixture 注册到当前 App 的 `hub._live`。`Hub._add` 分配真实 seq/time 并发布 live 事件，`_update` 消费实际 ACP 工具／文本回调，`_set` 发布状态；`GET /live` 读取同一个 `Hub.items/status`。`views.member_view` 的真实判断为 `embedded = bool(live) or config.get('surface') == 'acp'`，因此 Hub 状态存在就足够，不需要修改席位配置。fixture 保留原有 `surface: cli` 和 transcript，避免污染原场景；没有覆盖或伪造前端 `embedded` 字段。每个场景进入前都调用配置入口，普通场景会停止 fixture 自己的 Live、取消并回收权限等待线程，恢复原始数据。

权限可由 CI fixture 的内存线程调用真实 `Hub._request(key, 'session/request_permission', params)`：使用带已有 hooks 的 harness 和普通工具请求，避免执行外部协议检查；不调用 `create_member`、`start`、`_run` 或任何 agent/provider。该线程在真实 permission event 上等待，客户端 POST 后由 `Hub.decide` 唤醒并由 `_request` 清除请求。仅手工写 `_permissions` 而没有消费者会导致 POST 后请求不移除，不适合作为交互验收。fixture 关闭时需停止 Hub 并回收该内存等待线程。

现有参考捕获调用 `page.screenshot(..., animations='disabled')`，无限动画会在截图期间停回初始态；新增 typing 场景时应明确协调 Windows/macOS 的实际减少动画状态或真实动画暂停接口。不能忽略或填造原生圆点透明度来匹配参考。
