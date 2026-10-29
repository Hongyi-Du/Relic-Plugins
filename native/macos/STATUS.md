# macOS 原生 Relic App：逐元素验收

## Amendment 4：逐元素机器验收重新打开

此前视觉近似和烟雾截图通过均不满足新标准。当前尚无通过的逐元素报告；
原有全部 504 状态保留，新增模型/席位候选菜单后为 528 状态；
字体/文字/几何/颜色/状态/图标均按用户指定容差检查。
正在实现 macOS 实际 AX 控件树及渲染属性提取，再接入共享 matcher。
未知测量必须暴露并失败，不能用参考值填充。没有申请或批准任何例外；
此前列出的菜单、名片、日期、图表、Markdown、快速开始差异都恢复为待修复项。
下文保留 Amendment 3 的历史证据，不代表 Amendment 4 通过。

### 180c161：构建通过，新增场景仍待捕获验证

[Native apps 40968278671](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40968278671)
构建及测试通过，覆盖工作区/文件读取、刷新并发与快速开始、线程布局、摘要、
原文展开及窗口内 @ 菜单的实现。该结果不证明视觉或元素一致。
已合入共享分支 `5ff6706` 的两个候选菜单场景及 `member.harness_label`。
macOS 对这两个场景通过实际 AX 输入框位置点击，再向真实窗口发送 Down Arrow；
候选弹出框未出现在实际 AX 树中会使捕获失败，不注入替代菜单。
模型/席位原生候选弹出框的外观仍待同场景比较；没有增加任何例外。

### 38526b3：最新完整矩阵失败报告及后续捕获回归

[完整视觉运行 40958568166](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40958568166)
两端各 504 个截图已捕获，严格门禁失败。报告已下载至
`S:\Codex\Outputs\Relic-native-visual\parity-38526b3\report\`，
三端对照图在同级 `comparisons\`。以下数字直接读取该报告的 `summary.json`。

| 38526b3 严格报告 | Windows | macOS |
| --- | ---: | ---: |
| scenes_expected | 504 | 504 |
| scenes_checked / scenes_passed | 0 / 0 | 0 / 0 |
| raw_native_elements | 96,028 | 104,962 |
| valid_native_elements | 96,028 | 100,542 |
| invalid_native_elements | 0 | 4,420 |
| reference_elements | 93,032 | 92,536 |
| paired_elements / matched_elements | 80,974 / 0 | 50,855 / 0 |
| missing | 12,058 | 41,681 |
| extra | 15,054 | 49,687 |
| text_mismatch | 34,167 | 29,786 |
| geometry_out_of_tolerance | 133,666 | 130,574 |
| style_out_of_tolerance | 252,960 | 201,332 |
| state_mismatch | 23,199 | 32,389 |
| kind_mismatch | 2,398 | 5,179 |
| region_mismatch | 552 | 1,423 |
| order_mismatch | 6,430 | 3,948 |
| layout_mismatch | 34,413 | 85,161 |
| icon_mismatch | 2,740 | 2,345 |
| extraction_errors | 131,144 | 1,026,354 |

例外表和批准的图标映射表仍为空；`scenes_checked=0` 仍表示提取尚不完整。
这不是当前 HEAD 的视觉结果。后续详情、抄送、区域归属、头像、输入区、气泡、
新建组织及成员表单修改已通过
[f3a95a6 构建与单元测试](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40964128226)。

[4e18fc3 捕获运行](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40962975136)
的四个 macOS 作业各完成首个尺寸 42 场景后，在切换至 1280×800 时失败：
实际 view 保留 1440×872。布局回调在设置 NSWindow 后覆盖了可变 model.windowSize；
捕获代码改为使用不可变目标尺寸，并在布局完成后分配位图，保留原尺寸断言。
已下载并查看首个尺寸的实际截图，未宣称矩阵通过，也未缩小矩阵或改变容差。

### 119f04c：完整矩阵的实际失败报告

[完整视觉运行 40952663814](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40952663814)
已结束，两端各 504 场景均已捕获，严格门禁失败。完整报告、逐场景 HTML、热图在
`S:\Codex\Outputs\Relic-native-visual\parity-119f04c\report\`；三端对照图在
同级 `comparisons\`。以下来自实际下载的 `summary.json`，不是构建结果推断。

| 119f04c 严格报告 | Windows | macOS |
| --- | ---: | ---: |
| scenes_expected | 504 | 504 |
| scenes_checked / scenes_passed | 0 / 0 | 0 / 0 |
| raw_native_elements | 92,746 | 100,794 |
| valid_native_elements | 84,268 | 96,559 |
| invalid_native_elements | 8,478 | 4,235 |
| reference_elements | 93,032 | 92,536 |
| paired_elements / matched_elements | 62,842 / 0 | 52,694 / 0 |
| missing | 30,190 | 39,842 |
| extra | 21,426 | 43,865 |
| text_mismatch | 30,936 | 33,595 |
| geometry_out_of_tolerance | 299,614 | 170,563 |
| style_out_of_tolerance | 252,661 | 317,608 |
| state_mismatch | 60,864 | 36,585 |
| kind_mismatch | 6,804 | 6,737 |
| region_mismatch | 742 | 76 |
| order_mismatch | 12,576 | 4,263 |
| layout_mismatch | 40,012 | 109,952 |
| icon_mismatch | 4,846 | 1,700 |
| extraction_errors | 487,960 | 1,371,276 |

例外表和批准的图标映射表均为空。`scenes_checked=0` 表示仍有未完成的提取，
不能把截图齐全称为完整逐元素验证。此提交早于弹层、分栏、消息、设置、名片、
组织图、组织详情的后续修正；后续修改已经通过构建/单元测试，仍须新完整矩阵验证。
[2749a17 Native apps](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40959230686)
通过；[38526b3 全矩阵](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40958568166)
运行中。完整绘制覆盖、遮挡、菜单、Markdown、快速开始及所有非零项仍未完成。

### 重启后继续：d4a4e44 的完整失败报告

已核对重启后的干净工作区及远端提交。`d4a4e44` 的
[Native apps 40938288562](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40938288562)
通过，**70 个 XCTest，0 失败**；
[完整视觉运行 40938288684](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40938288684)
的四个 macOS 作业成功，504 个实际窗口 PNG、AX、elements 文件齐全，
包含 1024×700 及真实 App 内的复合标签检查。严格 compare 作业失败。

报告已实际下载到 `S:\Codex\Outputs\Relic-native-visual\parity-d4a4e44\report\`，
入口为 `index.html`，完整数据为 `parity-report.json`，轻量汇总为 `summary.json`。
macOS 基线来自同一 macOS runner、同一个 fixture/server。

| d4a4e44 严格报告 | Windows | macOS |
| --- | ---: | ---: |
| scenes_expected | 504 | 504 |
| scenes_checked / scenes_passed | 0 / 0 | 0 / 0 |
| raw_native_elements | 92,564 | 100,670 |
| valid_native_elements | 84,107 | 95,036 |
| invalid_native_elements | 8,457 | 5,634 |
| reference_elements | 93,032 | 92,536 |
| paired_elements / matched_elements | 62,719 / 0 | 52,646 / 0 |
| missing | 30,313 | 39,890 |
| extra | 21,388 | 42,390 |
| text_mismatch | 30,883 | 33,912 |
| geometry_out_of_tolerance | 299,025 | 165,264 |
| style_out_of_tolerance | 252,193 | 313,765 |
| state_mismatch | 60,742 | 35,682 |
| kind_mismatch | 6,787 | 6,166 |
| region_mismatch | 741 | 77 |
| order_mismatch | 12,560 | 4,401 |
| layout_mismatch | 39,955 | 119,497 |
| icon_mismatch | 4,830 | 1,675 |
| extraction_errors | 486,448 | 1,363,074 |

`scenes_checked=0` 是提取尚不完整的结果；504 个成功截图不等于 504 个场景
已完整验证。例外表及批准的图标替代表均为空。Windows 英文浅色中断在
1280×800 的通知设置，COM E_FAIL 已写入 REQUESTS.md 交由 Windows 会话修复。

已根据这版真实截图继续修复：macOS 字体跟随参考实际使用的 PingFang SC；
原生 CoreText 字体运行及 TextKit 每行边界进入报告；概况页的分区、紧凑行、
决策卡与原生选择器按参考调整；分栏宽度恢复增加后续布局校正。
`119f04c` 已推送，新的 CI 尚待返回。余下菜单、名片、图表、Markdown、
快速开始、完整绘制覆盖、遮挡和顺序仍须按机器结果修复，不能归为原生差异豁免。

首轮严格报告来自 [CI 40926888945](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40926888945)，
提交 61b2740，结果失败；已下载到
S:\Codex\Outputs\Relic-native-visual\parity-61b2740\report，
包含 parity-report.json、index.html 和全部 504 场景的分平台/合并 HTML。
两平台 scenes_expected 均为 504；scenes_checked 和 scenes_passed 均为 0，
原因包含提取缺失，不能声称已完整核对了 504 个场景。
参考元素 93,048；Windows 提取 90,675，macOS 提取 706（AX 子树缺失）。

| 首轮诊断类别 | Windows | macOS |
| --- | ---: | ---: |
| missing | 27,458 | 92,352 |
| extra | 25,085 | 10 |
| text_mismatch | 19,534 | 553 |
| geometry_out_of_tolerance | 285,234 | 4,362 |
| style_out_of_tolerance | 195,109 | 2,784 |
| state_mismatch | 78,208 | 1,392 |
| kind_mismatch | 7,136 | 0 |
| region_mismatch | 548 | 0 |
| order_mismatch | 10,112 | 0 |
| layout_mismatch | 156,655 | 2,088 |
| icon_mismatch | 10,553 | 0 |
| extraction_errors | 251,293 | 16,140 |

这些数字是修复前的失败基线；不能把低提取覆盖导致的零计数解释为通过。
异常表为空，无已批准例外。后续 b7e6962 已修正窗口内菜单、工具栏/分页、
群聊标题操作、参考路径图标、日期和快速开始的部分差异，并加入原生绘制测量；
[新完整矩阵](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40930279724)
仍待返回。功能静态检查当前为 52 路由、686 词条、214 参考流程，缺失均为 0；
这与逐元素验收分开记录。

## Amendment 3：macOS 已验证，完整三方验收被共享问题阻塞

更新：2026-10-29。分支 `native-macos`；本会话只修改 `native/macos/**`。
已包含本次核验时本地及 origin 最新的 `native-apps`（`5e02738`）。应用使用共享
Python 引擎、HTTP/SSE 契约与 `/api/i18n` 词库。没有浏览器或 WebView 界面。
**不能宣布 Amendment 3 全部完成：完整三方视觉工作流仍失败，真 Mac 交互尚待验收。**

已按实际截图重做：紧凑组织树及参考头像色板/状态点、图标工具栏、消息气泡/事件行、
收件人标签/引用/@ 候选、三栏及原生分页、决策/协议/抄送卡片、文件与轨迹、
成员表单/已有会话列表/秘书选择、全部七节设置。长说明换行，长名称/路径提供
省略或完整 tooltip。输入框的麦克风、发送和收件人保持紧凑；空输入框没有滚动条。
任务筛选和抄送显示数量。修复了长摘要越界、短代码居中、聊天缩放后丢失末尾、
成员配置空选项、协议代码重复显示及 @ 候选偏离光标。原始词条键不作为显示回退。

本次代码证据：

- 代码 `f7a6bfd` 的 [Native apps CI](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40882519547)
  三个作业全部通过：macOS、Windows、parity。macOS 为 **57 个 XCTest，0 失败**，
  包含双词库完整性、真实 payload/SSE、输入/草稿/导航以及 @ 锚点与 UTF-16 测试。
- 同代码的 [共享 Python/package CI](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40882519557)
  全部通过。parity 覆盖 **52 条路由、686 个词条、214 个参考函数**，缺失项为 0。
- 同代码的 [完整视觉运行](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40882519398)
  macOS 四个作业全部通过：**42 场景 × 3 尺寸 × 2 语言 × 2 主题 = 504 PNG**。
  Reference 也有 504 张；Windows 仅中文浅色 126 张完成，其他三个变体启动失败，
  compare 作业被跳过。**504 组三方合成 gate 没有通过。**
- 已逐页查看 42 场景中文浅色、42 场景英文深色的三方诊断对照；另外复核了
  七节新设置、各尺寸文件/摘要/群聊、明暗主题与最新 @ 弹出位置、数量徽标。
  没有把“自动生成 504 张”写成“人工逐像素验收了全部 504 张”。

下载与审阅入口（均未在本机打开窗口）：

- `S:\Codex\Outputs\Relic-native-visual\review-40882519398\index.html`：同一完整 CI 的
  **504 场景诊断图**，由下载的原图本地合成。126 组有三列实际图片；另外 378 组
  Windows 空位明确写出捕获失败。没有混入旧版本填补缺失，不是最终验收通过集。
  `coverage.json` 记录全部缺失文件及来源。
- `S:\Codex\Outputs\Relic-native-visual\smoke-40881418693\index.html`：下载的
  [已通过七场景三方 CI artifact](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40881418693)。
  该轮代码 `b0dbc3d`，早于最后的数量徽标和 @ 锚点修复，不能代替完整矩阵。
- `S:\Codex\Outputs\Relic-native-visual\macos-app-f7a6bfd\relic-native-macos-v0.7.1-beta.1.zip`：
  CI 产出的 unsigned arm64 应用包，未在这台电脑安装或启动。
- 原始图片和各轮审阅图在 `iteration-10` 至 `iteration-13`；旧轮次仅作问题诊断证据。

共享阻塞与剩余差别：

1. Windows 启动连续三轮出现 `Received an invalid status line: '<!DOCTYPE HTML>'`。
   `REQUESTS.md` 已记录调用栈及静态诊断：`PostAsJsonAsync` 的 chunked 请求体与
   仅读取 Content-Length 的服务端不匹配；请求改用缓冲 JSON 请求体并加 CI 回归。
   该修复在 Windows/共享代码所有权范围内，本分支没有越界修改。
2. `documents` 场景中参考与 Windows 未选择文档正文，macOS 已加载首篇文档；
   已请求共享捕获脚本通过真实控件选中文档后截图，API 不变。
3. macOS 使用系统菜单/SF Symbols、原生分页和控件。应用内 File/Edit/View/Help
   收进紧凑菜单；成员名片是居中 sheet。组织图图标、任务元数据位置、部分行高
   和日期格式仍与网页不同，未宣称逐像素一致。
4. CI 捕获真实 NSHostingView/AppKit 内容及 sheet/popover，一像素/点；不包含
   Dock、系统菜单栏和标题栏，也不能验证真实权限提示、麦克风、通知、输入法、
   VoiceOver 或提供方会话。本人或 HaochenGu 的 Mac 仍须按文末清单验收。

本机没有启动应用、浏览器、编辑器、可见终端、权限弹窗或本地 Python/native 测试。
未创建/合并 PR；Windows 会话仍负责合入本分支、共享修复和唯一 PR #4。

## 先前功能/契约验证记录

更新：2026-10-29。分支：`native-macos`。本会话仅修改 `native/macos/**`。
参考基线：`2007a83` 的完整界面与行为，包含用户要求的 v0.6 全部功能。
打包版本沿用共享引擎的 `v0.7.1-beta.1`，没有另建核心或词库。

## 完成范围与验证

- 共享契约的 **23 个界面条目 + 11 个回调/流程条目 = 34 个条目**全部实现，
  **214 个命名参考函数**均有原生映射，并经共享维护会话标记为 `done`。
- parity 覆盖参考的 **52 条路由、686 个词条**；应用共享维护的逐项原生替代说明后，
  缺失路由、缺失词条、未完成流程、浏览器 UI 调用均为 **0**。
- 最终代码提交 `fe5c5a35d75ffb67fa20ea86a6b619589d93c627` 的
  [Native apps 完整 CI](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40837118720)
  已通过 parity、macOS、Windows 三个作业。
- [macOS 作业](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40837118720/job/123324399176)
  完成 arm64 Release 构建、**49 个 XCTest（0 失败）**和 unsigned `.app` 打包；
  测试为 34 个核心契约、2 个语音选区及 13 个异步模型测试。
- 同一代码提交的 [共享 Python/package 验证](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40837118681)
  四个作业全部通过：Windows Python 3.11/3.13、macOS 15 Python 3.11、macOS 26 Python 3.13。
- 已合入共享分支 `native-apps` 的 `4c26286`。`REQUESTS.md` 的所有共享请求均已解决。
- 全程没有在这台 Windows 电脑打开 App、浏览器、编辑器、可见终端或权限弹窗，
  没有本地运行 Relic Python 测试。构建、测试和打包均由 GitHub Actions 执行。

## 逐项完成清单

“完成”表示实现和契约映射完成；窗口观感与 macOS 系统交互仍须最后一节的真机验收。

| # | 参考功能 | macOS 实现位置及行为 | 状态 |
| --- | --- | --- | --- |
| 1 | App 菜单、快捷键、主题/字体/布局 | `RelicApp.swift`、`MainView.swift`：Commands、标准编辑菜单、历史与侧栏/面板切换 | 完成 |
| 2 | 组织树、搜索、最近会话、未读 | `MainView.swift`、`Model.swift`、`State.swift`：递归折叠、预览、状态与祖先展开 | 完成 |
| 3 | 会话选择、标题、权限/等待横幅 | `Model.swift`、`Conversation.swift`：统一组织/成员选择，丢弃旧选择的延迟响应 | 完成 |
| 4 | 消息、历史、已读、工具及实时过程 | `Conversation.swift`、`Activity.swift`：稳定行标识、历史游标、工具配对、完整步骤加载 | 完成 |
| 5 | 输入框、收件人、@、引用、草稿 | `NativeInput.swift`、`Model.swift`、`Client.swift`：按会话保存、引用单独发送、重复提交锁 | 完成 |
| 6 | 权限和结构性审批 | `Overview.swift`：精确 option ID、批准/拒绝、成员/任务导航及失败状态 | 完成 |
| 7 | Overview、层级、工作、协议与 Episode | `Overview.swift`：父组织/领导/秘书处/自动唤醒/子组织、继承与替代协议 | 完成 |
| 8 | Copies、规则和确认 | `Forms.swift`：统计、规则代码/示例、Got it、确认后 Retire | 完成 |
| 9 | 创建组织 | `Forms.swift`：名称→目的→治理→创建→秘书设置 | 完成 |
| 10 | 创建 App 成员 | `MemberForm.swift`：名称、角色、可用适配器、模型、目录、秘书及创建 | 完成 |
| 11 | 创建 host 成员 | `MemberForm.swift`：Claude Code/Codex、支持的载体、模型/effort、环境/权限与启动方式 | 完成 |
| 12 | 绑定已有会话 | `MemberForm.swift`：标题/目录/ID 搜索，明确选择，保留完整 session 对象 | 完成 |
| 13 | 成员卡片、席位和手动转发 | `MemberCard.swift`：改名、头像、配置、新会话/解绑/打开、其他成员身份及转发 | 完成 |
| 14 | 秘书设置与空状态引导 | `MemberCard.swift`、`MainView.swift`：组织→秘书/成员→会话 | 完成 |
| 15 | 组织图 | `ChartView.swift`、`OrganizationLayout.swift`：层级/共享席位、筛选、平移/缩放/适配及定位 | 完成 |
| 16 | 线程 | `Conversation.swift`、`Model.swift`：根消息、回复、reply_to、草稿、返回原面板及重复发送锁 | 完成 |
| 17 | Workspace 与文件树 | `Workspace.swift`：成员目录、Git 分支/变更、最近编辑、嵌套文件及系统目录打开 | 完成 |
| 18 | 文件预览与路径导航 | `Workspace.swift`、`NativeLinks.swift`：文本/Markdown/JSON/图片、截断/二进制、行号及默认 App | 完成 |
| 19 | 白话、摘要、询问秘书 | `Conversation.swift`、`Model.swift`：批量异步白话、切换、摘要和后续消息数量 | 完成 |
| 20 | 语音输入 | `NativeInput.swift`、`State.swift`：Apple Speech、显式授权、选区插入、临时/最终结果 | 完成 |
| 21 | 任务/报告、文档/修订、协议、轨迹 | `Details.swift`：筛选、证据、修订内容、搜索与完整分页 | 完成 |
| 22 | Settings 全部七节 | `Settings.swift`：个人、外观、语言、语音、通知、适配器、关于/诊断/路径与能力检查 | 完成 |
| 23 | 原生安装替代浏览器安装 | `RelicApp.swift`、`Resources/Relic.icns` 和共享打包：arm64 Mach-O `.app`、图标、中英文元数据 | 完成 |
| 24 | 选择文字后复制/引用 | `SelectableText.swift`、`Model.swift`：原生上下文菜单、Edit 引用、选区与作者 | 完成 |
| 25 | Voice 支持、切换、停止 | `NativeInput.swift`：可用性/权限/偏好、单一录音器、发送/导航/退出时停止 | 完成 |
| 26 | Voice result/error/end | `NativeInput.swift`、`DictationInsertion`：保留前后文、UTF-16 光标、结果替换、错误及焦点恢复 | 完成 |
| 27 | Enter / Shift-Enter / IME / @ 补全 | `ComposerTextView`：仅在非输入法组合、非补全时发送，Shift 换行，Cmd-Enter 别名 | 完成 |
| 28 | SSE 重连与 token 更换 | `Client.swift`、`State.swift`：读取 app.json、验证 lifecycle、刷新凭据，只有明确 token 拒绝才重试写入 | 完成 |
| 29 | 拖动分栏与尺寸记忆 | `SplitPersistence.swift`：原生 NSSplitView、侧栏/面板宽度、单独 File 宽度及可见性 | 完成 |
| 30 | 导航与前进/后退 | `Model.swift`、`NavigationHistory`：组织/成员历史、展开所选组织祖先 | 完成 |
| 31 | 安装与 service worker 的原生替代 | 原生 `.app` 及共享 native launcher；旧浏览器安装路由返回 410 | 完成 |
| 32 | 人发布弱/强协议、继承规则 | `Forms.swift`：rationale、trigger、inherit、summary_for_person、强规则 JSON 和服务端校验 | 完成 |
| 33 | 生命周期、关闭与退出 | `RelicApp.swift`、`ServerHost`：关闭窗口保留 Dock、重开、Quit 释放自身 lease，借用引擎不关闭 | 完成 |
| 34 | 原生通知及点击 | `Model.swift`、`RelicApp.swift`：显式通知授权、Copies/审批偏好、激活并导航到对应会话 | 完成 |

## 自动化测试边界

核心测试覆盖真实形状的嵌套 JSON、loopback/token/重定向、业务错误、凭据更换与拒绝、
禁止重放不确定的 POST、SSE UTF-8/多行/CRLF、两种语言/复数/列表模板、收件人/线程负载、
草稿/折叠/导航、时间线和实时过程、并行工具配对、组织图层级/环、Markdown/文件链接、稳定行标识、
语音选区/临时替换/Unicode 光标。
13 个异步模型测试覆盖选择与草稿持久化、成功/失败发送保留更新内容、旧响应隔离、
白话批处理取消、摘要/实时合并、未读、引用、线程重复发送锁和历史游标等。
这些测试不打开原生窗口，不替代真 Mac 的 GUI 和系统权限验收。

## 214 个参考函数映射

浏览器 DOM/HTML/SVG/存储/安装脚手架对应 SwiftUI、AppKit、UserDefaults 和 Finder 安装。
下表是实现导航资料；词条和路由检查只扫描实际原生源代码，不使用本表充当覆盖证据。

| Reference function | Native implementation |
| --- | --- |
| `platformInfo@9` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `automaticDelivery@17` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `hostSurfaces@22` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `shortcutLabel@26` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `shortcutAction@29` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `absolutePath@46` | NativeLinks.swift: POSIX/Windows paths, Unicode, line/column parsing and native preview links |
| `inlineTokens@51` | Markdown.swift / NativeLinks.swift / SelectableText.swift: native attributed text and preserved Markdown links |
| `append@86` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `h@93` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `icon@148` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `hue@166` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `initial@172` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `dayLabel@179` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `clock@185` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `shortWhen@186` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `ago@191` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `stateLabel@200` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `taskLabel@204` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `pathLink@207` | NativeLinks.swift / Workspace.swift / SelectableText.swift: local-path previews and line navigation |
| `inline@211` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `rich@220` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `mdRun@245` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `quoteBlock@271` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `load@277` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `save@278` | Client.swift / State.swift / Markdown.swift / Conversation.swift / Presentation.swift: native platform, Markdown, links, time, storage |
| `get@281` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `loadPlatform@287` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `freshToken@291` | Client.swift: refreshRecord verifies replacement app/port/pid/instance with its token before adopting credentials |
| `post@297` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `toast@305` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `lang@313` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `applyPrefs@314` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `loadPrefs@325` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `setPrefs@329` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `tget@343` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `targ@355` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `t@365` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `tn@369` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `loadLang@381` | Client.swift: request, call, events, Words; Model.swift: start, savePreferences |
| `dname@417` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `roleName@429` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `avatar@432` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `secAvatar@446` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `groupAvatar@452` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `orgBadge@454` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `loadOrgs@460` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `readHash@470` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `writeHash@476` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `openOrg@482` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `refreshSnap@506` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `loadChat@513` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `markSeen@543` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `unreadOf@547` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `scheduleRefresh@554` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `notifyChanges@562` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `liveSlot@576` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `connect@577` | Client.swift: events / refreshRecord; State.swift: EventDecoder; Model.swift: receive / refresh after reconnect |
| `lastLine@623` | Model.swift: selection, refresh, receive, history, persisted drafts; Presentation.swift: unread, lastLine; Avatar |
| `chatRow@629` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `orgTree@636` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `setFolded@652` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `unfoldTo@656` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `renderSide@662` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `renderMe@729` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `pushHist@736` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `goHist@744` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `toggleSide@753` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `go@759` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `renderAll@769` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `renderHead@772` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `renderBanner@802` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `nearBottom@821` | MainView.swift: Sidebar, OrgTree; Conversation.swift: ChatView; Model.swift: select, navigate, toggleFold |
| `renderStream@822` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `watchPlain@853` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `plainState@863` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `requestPlain@868` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `gotPlain@883` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `updatePlain@888` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `togglePlain@896` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `togglePlainOne@904` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `toggleDigest@910` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `loadDigest@916` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `digestCard@927` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `askSecretary@940` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `placeholder@950` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `renderItem@954` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `stripQuote@1013` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `copyText@1014` | Conversation.swift: MessageView, RichText, DigestCard; Model.swift: requestPlain, acceptPlain, loadDigest, askSecretary |
| `memberItems@1018` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `toolName@1050` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `stepArg@1051` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `actsBlock@1059` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `stepRow@1081` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `liveTurnStart@1102` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `liveItems@1109` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `renderLive@1120` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `permissionCard@1156` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `decide@1161` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `setQuote@1166` | State.swift: Timeline.conversation/activeLive/merge; Conversation.swift: StepView, LiveItem; Overview.swift: DecisionView |
| `quotedBody@1174` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `closeSelBar@1181` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `micButton@1236` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `field@1242` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `composerBox@1249` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `doSend@1264` | Model.swift: send, per-chat drafts and quote-only dispatch; Client.swift: Composer; NativeInput.swift: IME/mention-aware Return |
| `renderComposer@1290` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `toPicker@1312` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `mentionCheck@1331` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `pickMention@1347` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `mentionKey@1357` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `closeMention@1369` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `closeMenu@1373` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `openMenu@1374` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `openContextMenu@1381` | NativeInput.swift: MentionEditor, ComposerTextView, SpeechInput; Conversation.swift: ComposerView; Model.swift: drafts, send, setQuote; native Menu/contextMenu |
| `openThread@1400` | Conversation.swift: ThreadView; Model.swift: openThread/loadThread/sendThread; MainView.swift: RightPane/HSplitView |
| `loadThread@1405` | Conversation.swift: ThreadView; Model.swift: openThread/loadThread/sendThread; MainView.swift: RightPane/HSplitView |
| `closeThread@1416` | Conversation.swift: ThreadView; Model.swift: openThread/loadThread/sendThread; MainView.swift: RightPane/HSplitView |
| `renderThread@1417` | Conversation.swift: ThreadView; Model.swift: openThread/loadThread/sendThread; MainView.swift: RightPane/HSplitView |
| `panes@1436` | Conversation.swift: ThreadView; Model.swift: openThread/loadThread/sendThread; MainView.swift: RightPane/HSplitView |
| `setPane@1437` | Conversation.swift: ThreadView; Model.swift: openThread/loadThread/sendThread; MainView.swift: RightPane/HSplitView |
| `togglePanel@1444` | Conversation.swift: ThreadView; Model.swift: openThread/loadThread/sendThread; MainView.swift: RightPane/HSplitView |
| `applyPanelWidth@1450` | SplitPersistence.swift: NSSplitView geometry, sidebar/panel/File widths; Model.swift preferences |
| `startResize@1454` | SplitPersistence.swift: native divider tracking and persisted dimensions, no pointer simulation |
| `renderPanel@1465` | Workspace.swift: WorkspaceView, FileTree, FilePreview; Model.swift: openFile; RichText local links |
| `renderWork@1493` | Workspace.swift: WorkspaceView, FileTree, FilePreview; Model.swift: openFile; RichText local links |
| `fileTree@1540` | Workspace.swift: WorkspaceView, FileTree, FilePreview; Model.swift: openFile; RichText local links |
| `fill@1543` | Workspace.swift: WorkspaceView, FileTree, FilePreview; Model.swift: openFile; RichText local links |
| `openFile@1569` | Workspace.swift: WorkspaceView, FileTree, FilePreview; Model.swift: openFile; RichText local links |
| `sizeLabel@1578` | Workspace.swift: WorkspaceView, FileTree, FilePreview; Model.swift: openFile; RichText local links |
| `renderFile@1579` | Workspace.swift: WorkspaceView, FileTree, FilePreview; Model.swift: openFile; RichText local links |
| `codeView@1602` | Workspace.swift: WorkspaceView, FileTree, FilePreview; Model.swift: openFile; RichText local links |
| `renderOrgPane@1612` | Overview.swift: Overview, HierarchyView, TaskCard, ProtocolList, DecisionView |
| `hierarchyBlock@1717` | Overview.swift: Overview, HierarchyView, TaskCard, ProtocolList, DecisionView |
| `walk@1720` | Overview.swift: Overview, HierarchyView, TaskCard, ProtocolList, DecisionView |
| `decisionCard@1784` | Overview.swift: Overview, HierarchyView, TaskCard, ProtocolList, DecisionView |
| `scheduleCc@1838` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `loadCc@1839` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `openCopies@1852` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `drawCopies@1859` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `copyState@1874` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `copyCard@1881` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `checkRulesView@1905` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `issuedBy@1922` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `ruleScope@1923` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `exampleText@1933` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `plainRules@1939` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `ackCopy@1942` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `retireCopy@1951` | Forms.swift: CopiesView; Overview.swift: RulesView; Model.swift: refresh/notifications; Presentation.swift: copyLabel/ruleScope |
| `closeCard@1964` | MemberCard.swift: MemberCard; NativeInput.swift: pickAvatar; Presentation.swift: identity |
| `identity@1965` | MemberCard.swift: MemberCard; NativeInput.swift: pickAvatar; Presentation.swift: identity |
| `pickImage@1972` | MemberCard.swift: MemberCard; NativeInput.swift: pickAvatar; Presentation.swift: identity |
| `openCard@1986` | MemberCard.swift: MemberCard; NativeInput.swift: pickAvatar; Presentation.swift: identity |
| `closeLayer@2081` | Forms.swift: CreateOrgView; MemberForm.swift: MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `scrim@2082` | Forms.swift: CreateOrgView; MemberForm.swift: MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `harnessList@2088` | Forms.swift: CreateOrgView; MemberForm.swift: MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `runModes@2094` | Forms.swift: CreateOrgView; MemberForm.swift: MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `runNotes@2095` | Forms.swift: CreateOrgView; MemberForm.swift: MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `hostKinds@2102` | Forms.swift: CreateOrgView; MemberForm.swift: MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `seatOptions@2105` | Forms.swift: CreateOrgView; MemberForm.swift: MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `memberDialog@2109` | Forms.swift: CreateOrgView; MemberForm.swift: MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `forwardDialog@2247` | Forms.swift: CreateOrgView; MemberForm.swift: MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `seatAction@2271` | Forms.swift: CreateOrgView; MemberForm.swift: MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `openSecretarySetup@2279` | Forms.swift: CreateOrgView; MemberForm.swift: MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `orgDialog@2288` | Forms.swift: CreateOrgView; MemberForm.swift: MemberForm; MemberCard.swift: SecretarySetup/ForwardForm/seatAction |
| `openDetails@2310` | Details.swift: DetailsView, TraceView, DocumentsView; Overview.swift: TaskCard, ProtocolList, RulesView |
| `render@2323` | Details.swift: DetailsView, TraceView, DocumentsView; Overview.swift: TaskCard, ProtocolList, RulesView |
| `countTasks@2402` | Details.swift: DetailsView, TraceView, DocumentsView; Overview.swift: TaskCard, ProtocolList, RulesView |
| `reportBlock@2405` | Details.swift: DetailsView, TraceView, DocumentsView; Overview.swift: TaskCard, ProtocolList, RulesView |
| `traceView@2410` | Details.swift: DetailsView, TraceView, DocumentsView; Overview.swift: TaskCard, ProtocolList, RulesView |
| `fetchMore@2427` | Details.swift: DetailsView, TraceView, DocumentsView; Overview.swift: TaskCard, ProtocolList, RulesView |
| `draw@2434` | Details.swift: DetailsView, TraceView, DocumentsView; Overview.swift: TaskCard, ProtocolList, RulesView |
| `sections@2454` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `openSettings@2458` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `draw@2464` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `setRow@2474` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `segControl@2477` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `toggleControl@2480` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `redraw@2485` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `drawProfile@2486` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `drawAppearance@2501` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `drawLanguage@2510` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `drawVoice@2525` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `drawNotify@2533` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `drawHarness@2545` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `onInstall@2595` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `drawAbout@2603` | Settings.swift: SettingsView/HarnessSettings; Model.swift: prefs/install events; NativeInput.swift: Apple Speech |
| `svgEl@2621` | ChartView.swift / OrganizationLayout.swift: native edges/cards, hierarchy, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `protoName@2627` | ChartView.swift / OrganizationLayout.swift: native edges/cards, hierarchy, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `openChart@2635` | ChartView.swift / OrganizationLayout.swift: native edges/cards, hierarchy, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `applyView@2665` | ChartView.swift / OrganizationLayout.swift: native edges/cards, hierarchy, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `clampView@2672` | ChartView.swift / OrganizationLayout.swift: native edges/cards, hierarchy, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `fitChart@2677` | ChartView.swift / OrganizationLayout.swift: native edges/cards, hierarchy, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `zoomAt@2687` | ChartView.swift / OrganizationLayout.swift: native edges/cards, hierarchy, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `zoomBy@2695` | ChartView.swift / OrganizationLayout.swift: native edges/cards, hierarchy, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `panBy@2696` | ChartView.swift / OrganizationLayout.swift: native edges/cards, hierarchy, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `wireChart@2702` | ChartView.swift / OrganizationLayout.swift: native edges/cards, hierarchy, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `loadChart@2772` | ChartView.swift / OrganizationLayout.swift: native edges/cards, hierarchy, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `reloadChart@2781` | ChartView.swift / OrganizationLayout.swift: native edges/cards, hierarchy, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `redrawChart@2786` | ChartView.swift / OrganizationLayout.swift: native edges/cards, hierarchy, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `drawChart@2791` | ChartView.swift / OrganizationLayout.swift: native edges/cards, hierarchy, shared seats, filters, zoom/fit/pan; Presentation.swift: protocolReference |
| `menus@2965` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `abBtn@2966` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `renderAppbar@2970` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `openAppMenu@2995` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `menuItem@3003` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `appMenu@3011` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `focusSearch@3060` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `pasteText@3061` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `quoteSelection@3066` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `shortcutsDialog@3075` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `shortcut@3082` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `installApp@3096` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `installPage@3115` | RelicApp.swift: Commands/ShortcutsView; MainView.swift: toolbar; AppKit standard Edit; shared Finder app packaging replaces PWA |
| `wire@3130` | RelicApp.swift: RelicApp/Delegate; Client.swift: ServerHost; Model.swift: start/stop; CreateOrgView/SecretarySetup |

## 真 Mac 验收与交付条件

最低系统：**macOS 14+、Apple silicon**。CI 产物为 **unsigned / 未 notarize** 的 `.app` ZIP。
包内含同源 Python 引擎源码，不捆绑解释器；运行需要 **Python 3.11+**。
使用 ACP 适配器时还需要 **Node.js 22+** 和已安装/登录的对应提供方工具；
可用能力与缺失原因在 Settings/成员表单显示。实际版本号以共享包元数据为准。

本人或 HaochenGu 可在 Mac 上按以下顺序验收：

1. 从 Finder 启动，确认 Dock 图标、菜单栏、三栏窗口；关闭窗口后重开，再用 Quit 退出。
   分别验证自启引擎随退出清理，以及借用已有引擎时原引擎继续运行。
2. 对照参考检查三栏布局、动作顺序、缩放/分栏记忆、浅色/深色/字体、简体中文与英语；
   用 VoiceOver/键盘检查焦点、Tab、快捷键、中文输入法、@ 补全、选区引用与线程发送。
3. 新建组织和三种成员、配置秘书/层级、权限和审批、强/弱协议、Copies、组织图；
   使用真实提供方测试会话打开/绑定/新建/解绑/手动转发和实时工具更新。
4. 检查 Workspace、真实文件/图片/Markdown、路径行号、系统默认 App 打开，
   白话/摘要、任务报告/证据、文档修订和轨迹分页。
5. 在显式点击后测试麦克风/语音许可、拒绝与恢复、中文/英语识别、选区和临时结果；
   测试通知许可、后台通知点击后的正确会话导航，以及服务端重启后的重连。

本记录不宣称以上真机步骤已经通过。没有创建或合并 PR；由 Windows 会话将
`native-macos` 合入 `native-apps`，维护唯一 PR 和最终共享发布。
