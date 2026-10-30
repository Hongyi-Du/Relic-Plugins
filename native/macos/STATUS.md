# macOS 原生 Relic App：逐元素验收

最新可复核诊断报告：`3934d53`，位于
`S:\Codex\Outputs\Relic-native-visual\parity-3934d53\report\`，
[CI 41050348637](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41050348637)。
报告要求全部 672 状态/平台，`passed: false`，`exceptions: []`；
`scenes_checked/scenes_passed/matched_elements` 均为 0。
macOS 实际采集 20 个诊断状态、5029 元素，与 4480 个有效参考元素配对 4404；
其中新增悬停场景在这个旧提交中错误打开 About 页，不能算完成，61e9830 已补实际交互验证。
Windows 此报告保留其实际失败结果，不代表 Windows 分支的最新验收。

| 3934d53 诊断平台 | 缺失 | 多余 | 文字 | 几何 | 样式 | 状态 | 种类 | 区域 | 顺序 | 布局 | 图标 | 提取错误 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| macOS | 76 | 625 | 12 | 1231 | 8396 | 1211 | 0 | 2 | 644 | 2325 | 0 | 30574 |
| Windows | 762 | 242 | 462 | 2008 | 11876 | 1114 | 8 | 15 | 920 | 1640 | 0 | 30259 |

`c8ea3df` [Native apps 41051300311](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41051300311)
全绿：macOS release 编译、199 项测试、打包通过，其他共享检查也通过。
后续 `8613c40` release 通过，201 项测试中 1 项失败：新按钮尺寸测试未等到
SwiftUI 发布托管 AX 节点，尚未取得尺寸；已补实际事务等待和完整视图树遍历，原尺寸断言保持不变。
新的会话间距、完整按钮点击区域、实际焦点绑定和输入框字形采集仍待最新 CI/截图验证。

最新 CI：`41ed54d` [41050111628](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41050111628)
release 编译通过，192 项测试中 1 项图标采样断言失败，其余 191 项通过。
失败原因是 24px / 1.7px 笔画交叉处并非完整覆盖像素；测试改为 48px / 3.4px
笔画的完整覆盖中心像素，保留原不透明度断言。没有更改生产绘制或门禁容差。
新矩阵包含 56 场景 × 3 尺寸 × 2 语言 × 2 主题，共 672 状态/平台。
已实现 `settings-navigation-hover` 的实际指针移动、生产 hover/selection 绑定、
原生页面内容及绘制表面稳定性记录；新增测试及完整采集均待新 CI 验证。

## Amendment 4：逐元素机器验收重新打开

此前视觉近似和烟雾截图通过均不满足新标准。当前尚无通过的逐元素报告；
原有全部 504 状态保留，新增候选菜单、实时会话、成员卡、消息交互、文本框、右栏拖拽和设置导航悬停后为 672 状态；
字体/文字/几何/颜色/状态/图标均按用户指定容差检查。
正在实现 macOS 实际 AX 控件树及渲染属性提取，再接入共享 matcher。
未知测量必须暴露并失败，不能用参考值填充。没有申请或批准任何例外；
此前列出的菜单、名片、日期、图表、Markdown、快速开始差异都恢复为待修复项。
下文保留 Amendment 3 的历史证据，不代表 Amendment 4 通过。

最新已下载的诊断正式报告来自 `749e5e8`，
[41044882055](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41044882055)，位于
`S:\Codex\Outputs\Relic-native-visual\parity-749e5e8\report\`。
macOS 19/19 捕获完成，4755 个原生元素、4263 个有效参考元素、配对 4205；
完整 660 门禁仍为 `passed: false`，检查通过场景／匹配元素均为 0，`exceptions: []`。
File 场景布局就绪后再操作，实际会话几何差异从 171 降至 24；所有差异仍保留在报告中。

| 749e5e8 诊断平台 | 缺失 | 多余 | 文字 | 几何 | 样式 | 状态 | 种类 | 区域 | 顺序 | 布局 | 图标 | 提取错误 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| macOS | 58 | 550 | 0 | 1187 | 8025 | 1200 | 0 | 2 | 599 | 2226 | 0 | 29240 |
| Windows | 544 | 237 | 455 | 2125 | 13580 | 1128 | 8 | 15 | 925 | 1630 | 0 | 33243 |

同一提交的 [构建 41044882354](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41044882354)
release 编译通过；185 项测试有 2 个断言失败，均来自一个新文字轮廓测试。
实际 AppKit 添加了子绘制层，生产提取器正确保持未知，测试却假定存在 presentation layer 就能证明轮廓不存在。
已修正此测试假定，并继续记录实际子层身份与绘制属性；生产门禁没有放宽。
原生图标也改为由实际 CoreGraphics 绘制回调保留路径／颜色／尺寸／当前窗口绑定。
新键盘滚动操作绑定会话自身 NSScrollView，方向键、翻页、Home/End 和空格只在视口获得焦点时处理，
输入和命令快捷键仍走原有响应链。其测试、AX 焦点和完整截图均待新 CI，不能先算已匹配。

此前诊断正式报告来自 `b63cd2f`，
[41042527320](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41042527320)，已下载到
`S:\Codex\Outputs\Relic-native-visual\parity-b63cd2f\report\`。
macOS 捕获 **19/19**，原生元素 4754、有效参考元素 4263、配对 4204；没有原生捕获错误。
这是诊断子集；正式报告仍要求全部 660，`scenes_checked/scenes_passed/matched_elements` 都是 0，
`passed: false`、`exceptions: []`。Windows 本次捕获有失败，不以它替代 Windows 最新分支的结果。

| b63cd2f 诊断平台 | 缺失 | 多余 | 文字 | 几何 | 样式 | 状态 | 种类 | 区域 | 顺序 | 布局 | 图标 | 提取错误 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| macOS | 59 | 550 | 0 | 1338 | 8036 | 1200 | 0 | 2 | 590 | 2225 | 0 | 29236 |
| Windows | 544 | 237 | 526 | 1713 | 13133 | 1129 | 8 | 15 | 626 | 1630 | 0 | 33641 |

本次实际滚动记录确认群聊右栏 clip y 从 7 恢复为 0；PNG 也已与参考逐项查看。
19 场景几何差异从上一诊断的 3199 降到 1338，但样式、布局和提取缺口仍须继续修复。
下拉框标题实测左移 10 px：群聊上级组织参考文字暗像素 x1194 起，原生 x1184 起，
对应文字框 x1193.03125／1183。已修正原生 popup 的标题内边距，并增加长标题原生截断测试；
没有调整参考测量、容差或坐标投影。该修正、后挂载滚动条修正仍待新 CI。

`fd93174` 包括实际 CGFloat 字体度量读取、只读文字重排时保留阅读位置、
成员名片“保存模型”按钮填满内容列，以及 CI 操作前的实际滚动布局就绪记录。
[Native apps 41043480042](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41043480042)
的 [macOS job 124021988466](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41043480042/job/124021988466)
已完成 release 编译、打包及 **183 项测试，0 失败**。实际字体度量和只读文字重排测试均通过。
此前 `63aecc0`、`b63cd2f` 的 macOS 测试在排队中被后续推送取代；本次才取得这批修复的测试证据。
该工作流整体仍因共享菜单父级 fixture 失败；Windows 已修正并合入当前分支，待新 CI。
后续新增 @ 候选项子元素／名称和只读文字自身轮廓测量，尚待各自的构建、测试与截图。

最新下载的正式报告来自 `72f5571` 的 **19 场景诊断**，
[41040938552](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41040938552)，位于
`S:\Codex\Outputs\Relic-native-visual\parity-72f5571\report\`。
macOS 捕获 19/19、4776 个原生元素、4263 个有效参考元素、配对 4205；
Windows 为 4145 个原生元素、4265 个有效参考元素、配对 3916。
两平台仍为 `scenes_checked: 0`、`scenes_passed: 0`、`matched_elements: 0`，
完整门禁要求 660，`passed: false`、`exceptions: []`。

| 72f5571 诊断平台 | 缺失 | 多余 | 文字 | 几何 | 样式 | 状态 | 种类 | 区域 | 顺序 | 布局 | 图标 | 提取错误 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| macOS | 58 | 571 | 0 | 3199 | 8038 | 1200 | 0 | 2 | 603 | 2226 | 0 | 28184 |
| Windows | 349 | 229 | 577 | 1708 | 13992 | 1201 | 8 | 16 | 625 | 1733 | 0 | 35394 |

该次原生滚动记录直接确认右栏 y=7 来自 NSTextView 在 frame 调整时自动显示休眠选区。
`ReadOnlyTextView` 只抑制 frame 调整期间的自动滚动，显式滚动和选择行为保留；
新测试已在上述 183 项中通过，截图仍待 CI，不能提前宣称几何差异消除。

此前完整通过的原生构建为 `efa7553`：
[41039878013 / macos 124009778780](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41039878013/job/124009778780)
release 编译、打包及 **180 项测试通过**，包括新增中英文秘书称呼回退测试。
`72f5571` 后续增加实际字体度量边界检查，尚待新 CI 验证。

前一版 `5d97933`：
[41038867598 / macos 124006493039](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41038867598/job/124006493039)
release 编译、打包及 **179 项测试通过**。包含原生滑块重复 AX 枚举与索引检查、
实际字体表／基线／popup 标题、Markdown 标记源文本等回归；滚动条注册递归已在 CI 验证修复。
构建工作流整体成功，不代表逐元素门禁成功；更新后的捕获尚在运行。

此前完整通过的原生构建 `711d27a`：
[41029422150 / macos 123975289918](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41029422150/job/123975289918)
release 编译及 **165 项测试通过**，含实际箭头 fallback 字体、原始工具文本边界和只读文档末尾换行高度回归。
此后的静态字体表／文字基线修改仍待验证：`3462591` release 编译成功，XCTest 在字体绘制测试退出 signal 11；
`f6c73ce` 移除排版代理递归后仍退出 signal 11。随后定位到字体表 API 返回未装箱整数标签，
错误桥接为 NSNumber 会解引用整数地址；现已改用 `CFArrayGetValueAtIndex` 读取，并保留真实绘制测试。
`ae977f2` 的 [41035024073 / macos 123993758261](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41035024073/job/123993758261)
确认实际静态字体 Regular/Bold 绘制、固定行高基线、制表位及新增 popup 标题绘制测试通过；
但测试进程在 `testThumbOnlyScrollerDoesNotExposeUnpaintedLegacyButtons` 退出 signal 11，整套测试仍失败。
`e5fe085` 只读取 role 的修改未解决滚动条崩溃：`ed5b808` 仍在同一测试退出 signal 11。
其 [诊断捕获 41035817459](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41035817459)
现已保存实际 `Relic-2026-10-30-100410.ips`，位于
`S:\Codex\Outputs\Relic-native-visual\parity-ed5b808\crash\`。
栈显示 AppKit 注册子项 UIElementSpecifier 时通过 `accessibilityIndexOfChild` 再次枚举父级，
因此即使只读 role 也会递归。`1ecee11` 增加原生注册重入保护和重复子项索引测试，
已在上述 `5d97933` CI 通过。
`5d97933` 同时修正完整中文浅色 165 状态中实测的成员选项、工作区、轨迹行的独立子元素和名称；
菜单快捷键、Markdown 标记及表格单元格名称亦已修改。新截图尚未验证这些差异已消失。
诊断样本的新增测试不替代全部 660 状态门禁。
`9aaf342` 诊断捕获已绘制群聊 PNG，但 AX 阶段退出 -11、完成数为 0/19；产物在
`S:\Codex\Outputs\Relic-native-visual\parity-9aaf342\macos\`。不把这一张 PNG 计为成功捕获。
后续源码还补齐决策按钮实际文字绘制及边框宽度、popup 原生菜单标题的实际文字绘制、
快捷键说明的次级文字色，并加入只观察真实滚动通知的几何历史；这些须继续由新 CI 验证。

最新 **19 场景诊断**正式报告已下载到
`S:\Codex\Outputs\Relic-native-visual\parity-5d97933\report\`，
[41038866965](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41038866965)。
macOS 实际捕获 19/19、4779 个原生元素、4263 个有效参考元素、配对 4208。
正式门禁仍要求 660，`scenes_checked/scenes_passed/matched_elements` 均为 0，
`passed: false`、`exceptions: []`。表中的提取错误包括缺少完整矩阵及未证明的样式测量。

| 5d97933 诊断平台 | 缺失 | 多余 | 文字 | 几何 | 样式 | 状态 | 种类 | 区域 | 顺序 | 布局 | 图标 | 提取错误 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| macOS | 55 | 571 | 0 | 3159 | 8070 | 1209 | 11 | 2 | 611 | 2226 | 0 | 28257 |
| Windows | 578 | 217 | 543 | 1613 | 13234 | 1130 | 8 | 15 | 588 | 1630 | 0 | 34272 |

最新已下载的完整矩阵失败报告是
`S:\Codex\Outputs\Relic-native-visual\parity-0a1d569\full-report\`，
来源 [41019034145](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41019034145)。
保留 `parity-report.json`、`summary.json`、1981 个 HTML 页面及全部对应图片／热图。
macOS 完成 660 原生捕获；原始／有效原生元素 153652／153566（无效 86），
原始／有效参考元素 128628／126540（无效 2088），配对 121878。
Windows 原始／有效原生元素均为 124623；参考 129000／126932（无效 2068），配对 117300。
完整门禁两平台均 `scenes_expected: 660`、`scenes_checked: 0`、`scenes_passed: 0`、`matched_elements: 0`；
`passed: false`，`exceptions: []`，没有放宽任何容差。

| 0a1d569 完整平台 | 缺失 | 多余 | 文字 | 几何 | 样式 | 状态 | 种类 | 区域 | 顺序 | 布局 | 图标 | 提取错误 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| macOS | 4662 | 31688 | 4359 | 110743 | 254162 | 17104 | 517 | 654 | 33700 | 75428 | 12 | 890660 |
| Windows | 9632 | 7323 | 18502 | 93006 | 471944 | 36638 | 336 | 412 | 24532 | 51608 | 0 | 1080297 |

较新源码 `711d27a` 的 **19 场景诊断**完整报告已在
`S:\Codex\Outputs\Relic-native-visual\parity-711d27a\report\`，
[CI 41029421500](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41029421500)。
macOS 4841 原生元素、4263 有效参考元素、4189 配对；缺失 74、多余 652、文字 4、几何 3058、
样式 8412、状态 1202、种类 11、区域 2、顺序 599、布局 2622、图标 0、提取错误 32111。
它仍不能通过完整门禁；18 个实际场景文字配对差异为 0，剩余文件行号名称已在后续源码修正。
`3462591` 后续修复工具展开时的阅读位置、8 字符制表位、设置卡片归属和色块边框／选中环；等待新捕获。

更新诊断的完整 JSON／HTML／热图位于
`S:\Codex\Outputs\Relic-native-visual\parity-05f400c\report\`，
来源 [41026206807](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41026206807)。
实际 macOS 捕获为 **19/19**，不是完整 660 场景验收。
macOS 原始／有效原生元素 4842（无效 0），参考 4331／4263（无效 68），配对 4186；
Windows 原始／有效原生元素 3892（无效 0），参考 4333／4265（无效 68），配对 3678。
两平台 `scenes_checked`、`scenes_passed`、`matched_elements` 均为 0，例外表仍为空。

| 05f400c 诊断平台 | 缺失 | 多余 | 文字 | 几何 | 样式 | 状态 | 种类 | 区域 | 顺序 | 布局 | 图标 | 提取错误 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| macOS | 77 | 656 | 32 | 3271 | 8915 | 1203 | 9 | 2 | 907 | 2633 | 0 | 32143 |
| Windows | 587 | 214 | 546 | 2111 | 14111 | 1119 | 12 | 15 | 632 | 1621 | 0 | 34979 |

群聊直接配对文字 0、区域 0、状态 2；实际重复 checkbox 已消失。
右栏顶部偏移仍在，`.defaultScrollAnchor(.top)` 没有解决实测 7px 滚动原点，继续记录真实 insets／滚动几何定位。
`0a1d569` 完整矩阵四个 macOS 分片已下载，每片 165/165、`errors: []`；
其中 en-US/light 原生捕获与上传成功，后续浏览器诊断超时，不能把整个 job 称为成功。
该次完整 compare 尚在运行，不能用分片捕获成功替代门禁通过。

`32972ca` 的 macOS [构建任务 123961577229](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41025202713/job/123961577229)
release 和 **162 个测试通过**，包含图例虚线实际像素、连线 AX、控件状态归属及重复 checkbox 回归。
`05f400c` 继续修复初始右栏滚动、拖拽条区域、实时工具文本边界和动作名称，正在等待构建与捕获。

更新的完整诊断报告／HTML／热图：
`S:\Codex\Outputs\Relic-native-visual\parity-682034a\report\`，
来源 [41022654907](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41022654907)，实际捕获为 19 个诊断场景。
macOS 原始／有效原生元素 4886（无效 0），有效参考 4259（无效 68），配对 4173；
Windows 原始／有效原生元素 4127（无效 0），有效参考 4261（无效 68），配对 3900。
完整门禁仍要求各平台 660 case，两平台 `scenes_checked`、`scenes_passed`、`matched_elements` 均为 0；例外表为空。

| 诊断平台 | 缺失 | 多余 | 文字 | 几何 | 样式 | 状态 | 种类 | 区域 | 顺序 | 布局 | 图标 | 提取错误 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| macOS | 86 | 713 | 40 | 3198 | 8767 | 1301 | 9 | 21 | 889 | 2632 | 0 | 33032 |
| Windows | 361 | 227 | 585 | 2239 | 14933 | 1182 | 9 | 16 | 765 | 1718 | 0 | 36017 |

其中群聊文字差异为 0，仍缺安装按钮／图标，且原生和参考的未测量项目仍然失败。
实际开关点击框已恢复 32×18；右栏首块向上偏移源于实测 `NSClipView.bounds.y = 7`，后续采用顶部滚动锚点，等待新截图。

`682034a` 的 [Native apps 41022652153](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41022652153)
已全部通过：macOS release 编译和 **158 个测试通过**，包括实际 SwiftUI 容器中的开关尺寸、
卡片类型转换、独立可见标签的 AX 名称、消息滚动策略和说明文字换行测试。
对应诊断捕获 `41022654907` 仍在等待 macOS runner；上述修改尚不能视为逐元素捕获通过。

诊断产物 [41019075828 / 0a1d569](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41019075828)
的 19 个 macOS 场景及完整对照报告已下载到 `S:\Codex\Outputs\Relic-native-visual\parity-0a1d569\`。
该子集 macOS 缺失 104、多余 717、文字 130、几何 4440、样式 8572、状态 1316、
种类 9、区域 21、顺序 1212、布局 2633、图标 0、提取错误 33064；完整矩阵通过数仍为 0。
其中确认了开关实际边距、卡片类型转换和群聊头像／复合名称问题；后续修复均等待新截图验证。

最新完整失败报告及全部 HTML／热图已下载到
`S:\Codex\Outputs\Relic-native-visual\parity-2cb073c\report\`，
来源为 [41011131381](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41011131381)。
报告要求每平台 660 case；两平台 `scenes_checked`、`scenes_passed`、`matched_elements` 均为 0，`exceptions: []`。
macOS 原始原生元素 152916（有效 152833，无效 83），有效参考元素 126540，配对 118753；
Windows 原始原生元素 123231（均有效），有效参考元素 69189，配对 64084。

| 平台 | 缺失 | 多余 | 文字 | 几何 | 样式 | 状态 | 种类 | 区域 | 顺序 | 布局 | 图标 | 提取错误 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| macOS | 7787 | 34080 | 12880 | 125674 | 233000 | 16778 | 528 | 898 | 65230 | 79374 | 12 | 808805 |
| Windows | 5105 | 59147 | 10437 | 53369 | 221285 | 20111 | 197 | 229 | 14189 | 26722 | 362 | 753691 |

`0a1d569` 的 [Native apps 41019034175](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41019034175)
全绿，macOS release 和 152 个测试通过；但随后 19/19 的真实诊断捕获仍发现：
SwiftUI 中开关的实际点击框为 36×22，卡片的 AXGroup 类型转换又使范围修正未生效。
这两处已在 `caaa834` 修复并补测试，尚待新截图确认。
`e5eae1d` 同时修复消息行多出的 10 px 间距及右栏宽度变化时的强制滚动；
说明文字测试的输入宽度现按参考实际 297 px 内容框计算，原宽度断言及容差保留。

此前已验证构建：[41016580612 / 1d3a643](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41016580612)
整个 Native apps 工作流通过；macOS release 编译和 **151 个测试通过**。
真实原生开关的 AX 角色、32×18 点击范围、勾选和禁用行为，以及富文本逐段 AX 读取均已通过。
后续卡片范围辅助函数曾出现主线程隔离编译错误，已在 `666b2bf` 修复；
`0a1d569` 包含该修复及右栏文字、组织徽标、图表标签归属，正在等待新 CI，尚不能算通过。

完整捕获恢复：[41011131381 / 2cb073c](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41011131381)
四个 macOS 语言／主题产物均已下载到 `S:\Codex\Outputs\Relic-native-visual\parity-2cb073c\`。
每份完成记录都是 165/165、`errors: []`，共 660 个 PNG 和 660 个元素文件。
三个窗口尺寸的进程全部完成；英文浅色任务后续的浏览器绘制诊断失败，
原生捕获及上传已成功。共享比较报告已失败，完整计数见上表。

最新诊断 [41009151448 / bbe04a3](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41009151448)
完成全部 19 个 macOS case；成员卡重命名、Copy 均有实际动作和结果回执。
群聊输入框测得 758×26，与参考相同。截图、HTML、热图和 JSON 已下载到
`S:\Codex\Outputs\Relic-native-visual\parity-bbe04a3\`。这是诊断子集，不能替代 660 case。
该报告两个平台验收通过仍为 0；macOS 缺失 219、多余 787、文字 455、几何 3674、
样式 8120、状态 1264、种类 9、区域 28、顺序 2257、布局 2887、图标 0、提取错误 31175。
当前继续修复实际原生子控件的层级顺序、阴影与批次启动；没有例外或容差放宽。
`41b68f4` 的 [Native apps 41012301431](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41012301431)
已通过 macOS release 编译和 **147 个测试**。阴影六处实际采样通过原有 ±2 通道值断言，
已下载的 `parity-27e39b3` 完整窗口也确认阴影恢复；没有放宽测试容差。
实际子控件层级和中文粗体测试已通过；中文粗体 advance 为 171.36，参考 171.375，
原英文断言也通过。富文本实际绘制区间和新原生开关仍待后续 CI。
`parity-a3ca2a3` 的 19 个原生诊断画面已完成；实际侧栏头像与状态点顺序修复已在元素文件中确认。
该报告 macOS 缺失 155、多余 723、文字 477、几何 3279、样式 7990、状态 1279、
种类 9、区域 28、顺序 1323、布局 2948、图标 0、提取错误 31240；完整矩阵通过数仍为 0。

当前构建证据：`afe7f6f` 的 [Native apps 41004901785](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41004901785)
macOS 构建和 **138 个测试通过**，包含真实外轮廓路径/虚线、生产标签的字体回退、
抗锯齿绘制、图像绘制、头像双环像素和文字归属回归测试。
侧栏圆角、结束状态透明度、组织头像/标签、菜单前景和选中背景已按生产参考修正。
静态检查仍为 52 条路由、686 个词条、214 条流程无遗漏；这些不是逐元素验收结果。
`9bfbcf5` 接入共享 `vector-image-v1` 图像格式，数据来自实际 CoreGraphics 绘制参数与当前原生视图绑定；
保留实际路径、渐变 stops、颜色空间、延伸标志和绘制顺序，不把资源身份当成最终 PNG 像素归属。
该提交新增的真实字母/圆点像素及方向测试已通过；完整截图的图像归属仍待验证。

已合入 `native-apps` 的 `6183507`，包括独立 outline 检查和实际图标内容配对。
当前 macOS 改为由生产 CoreGraphics 绘制独立 outline，同时记录实际路径、虚线长度/相位、
颜色、坐标变换、视图/窗口身份及配置版本；过期或未挂载的绘制不进入 canonical 字段。
新增真实位图的相位变化、圆角透明和旧绘制失效回归测试已通过。没有把原生路径与浏览器路径等同，
没有从零 border 推断无 outline，也没有声称绘制调用已证明最终 PNG 的像素归属。

完整采集 `56253c7` 的 en-US/dark 任务持续推进到第 148 个 case，147 对 PNG/元素文件已写出，
随后触发 1200 秒进程总超时；没有触发 90 秒单场景停滞。请求共享 harness 按三个尺寸各 55 case
分批执行，保留全部 660 case 和原有超时/容差。macOS 原始 JSON 已仅去除缩进空白，所有测量保留。

该完整采集的中文浅色组已完成全部 165 case，错误为 0；包括 1024×700 下的 Copy 提示和两种右栏手势。
原生与参考文件已下载至 `parity-56253c7/macos-zh-CN-light` 与 `reference-macos-zh-CN-light`。
共享按尺寸分批执行已经合入，并已提交新完整捕获。采集完成与逐元素匹配通过仍是不同结果。

最近逐项修复包括：字体回退不再把同一个原生标签拆成多个元素；多行截断保留独立的段落换行模式；
右栏标签使用正确的非选中颜色和真实文字/图标归属；侧栏搜索、成员区、资料栏和右栏标题区具有真实 AX 分组；
收件人 chip 使用参考的后续 CSS 圆角/间距/悬停覆盖。实际字体绘制显式使用抗锯齿并关闭 font smoothing，
没有改动用户系统字体设置。新完整窗口截图仍待核对。

成员卡阴影尚有实测差异：底边下方 1px 参考为 RGB(225,225,224)，旧原生为 (246,246,245)，
虽然声明参数相同。当前将阴影形状显式放入非线性 sRGB 合成组，并以原参考六个像素位置增加回归测试，
等待 CI；没有通过调低阴影颜色要求或改变颜色容差来接受旧画面。

新增诊断捕获 [41004201773 / 597e113](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/41004201773)
已下载至 `S:\Codex\Outputs\Relic-native-visual\parity-597e113\`，包含原生/参考文件及 `report`。
19 个诊断 case 中 18 个 captured，复制提示保持到元素提取结束；重命名仍失败，日志显示实际点击用了
资料加载前的位置。已改为等待真实成员资料的 AX 标识挂载后再测量、单次点击，并保留失败尝试证据。
该诊断输入仍按完整 660 case 门禁判断，两个平台均 0 个验收通过场景。
正文同一段的实际红色通道墨迹覆盖量为原生 2065.15 / 参考 2068.80；旧原生为 2444.42。
这验证了该段字形过重的改善，不代表全部字体、布局或场景一致。

完整捕获 [40996703093 / 56253c7](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40996703093)
已完成并按要求失败。最新完整失败报告已下载至 `S:\Codex\Outputs\Relic-native-visual\parity-56253c7\report\`，
包含 `parity-report.json`、`summary.json`、各场景 HTML 和热图，预期矩阵为每平台 660 case。
两个平台 `scenes_checked`、`scenes_passed`、`matched_elements` 均为 0；不能把失败/部分采集计为完成验收。
macOS 原始元素 152664、有效元素 152579、配对元素 94592；缺失 31426、多余 57987、文字 21172、
几何 132067、样式 156668、状态 15071、种类 982、区域 655、顺序 48207、布局 76900、图标 7000、提取错误 391545。
Windows 原始/有效元素 123878、配对元素 102066；缺失 9191、多余 21812、文字 16917、几何 88267、
样式 311229、状态 30902、种类 332、区域 52、顺序 25370、布局 46457、图标 3369、提取错误 321792。
没有例外、容差变更或场景删减。

实际字体身份新增当前绘制绑定：完整标签的字体来自生产 `showCGGlyphs` 回调，保留每次实际回退字体、
字形数和度量。视图/容器/窗口、布局、源属性变更后，旧回调失效；无法绑定到部分富文本区间时继续报未知。
独立 CoreText 重排结果仅保留为诊断，不再替代实际绘制字体。相关真实位图回归等待下一轮 CI。

**最新实际截图**：`25f57f2` 的 [40997958370](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40997958370)
已下载到 `S:\Codex\Outputs\Relic-native-visual\smoke-25f57f2\`，群聊与拖拽后的真实窗口 PNG 为 1440×900、
alpha 全部 255，最终合成的透明图回归已修复。19 个 native case 中 18 个 captured、1 个 failed-state-captured；
复制失败发生在模型产生提示条后约 6 ms，真实提示文字/表面尚未挂载，剪贴板和原计时器正确。
`f0dad28` 等待同一个实际提示条挂载，原计时器持续运行，随后才暂停并保留全部连续性断言；新 CI 待验。
两个右栏拖拽场景的真实输入和持续状态检查已完成。此轮报告在 `S:\Codex\Outputs\Relic-native-visual\parity-25f57f2\report\`，
仍然失败，不能以 19 个诊断 case 代替完整 660 case 验收。

**保留的历史透明截图回归**：`ee478c5` 的 [40993478737](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40993478737)
虽然旧 17 个动作完成、两个新增动作尚未实现，但其原生 PNG 的所有 RGBA 通道都是 0，不能作为有效截图。
文件保留在 `S:\Codex\Outputs\Relic-native-visual\smoke-ee478c5\`。`9990d4f` 修正最终画布的合成路径，
在真实 sRGB CGContext 绘制完成后才生成图像快照，测试覆盖相同的最终合成和 PNG 编解码；
新增真实源图及成图透明度检查。`9990d4f` 的 [Native apps 40996374487](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40996374487)
已构建成功且 128 个测试通过，包含生产合成路径和 PNG 编解码；完整窗口的新截图仍待采集，
不能用单控件及合成测试代替完整成图验证。

已同步共享 `c705ec7`：参考滚动条区分 gutter、thumb outer box、hit box 和 ink envelope，
未知 thumb 几何或样式仍失败。macOS 保留实际 NSScroller draw rect、AX hit bounds 和实际值域，
不从滚动比例猜测 thumb 外框。新诊断矩阵仍为 19 case，完整矩阵为 660 case。

历史构建证据：`14b78e0` 的 [Native apps 40994507899](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40994507899)
macOS 构建与 128 个测试全部通过，包含原容差下的发送按钮真实像素断言和 PNG 编解码一致性。
CI 原始通道为启用 `[27,27,26,255]`、禁用 `[175,175,175,255]`；此前失败来自
`colorAt` 生成校准色后的二次转换。现在读取位图实际 sRGB 通道，同时保留颜色空间、格式、alpha 回执。
同一运行确认侧栏混排的实际 advance 为 130.642880（参考 130.640625），而 glyph envelope 为
135.528076；两者是不同测量量。后续 `e0c98f8` 读取既有 TextKit 排版的插入点，分别保留 advance、
墨迹包络和截断未知值，待新 CI 验证。没有因这些测试通过而关闭逐元素失败项。

已合入共享 `d77f162` 的 55 场景矩阵：完整 660 case、诊断 19 case。macOS 新增
`panel-resize-hover` / `panel-resized` 的实际鼠标输入，窄窗先点击真正的 Overview 工具栏按钮；
拖拽在窗口坐标中进行八步 64 px 移动，独立检查同一面板/手柄、实际收到的 SwiftUI 手势、
宽度/位置变化，以及 PNG 和元素提取期间持续不变的指针/悬停/释放状态。实现已提交，尚待 CI。

最新采集证据：`3c652b7` 的 [40988685123](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40988685123)
已完成全部 17 个诊断 case，均为 captured、错误列表为空。群聊改用实际布局的 VStack 后，
四个文档视图的高度漂移不再出现；截图及回执在 `S:\Codex\Outputs\Relic-native-visual\smoke-3c652b7\`。
这只验证采集与交互；逐元素门禁仍未通过。实际发送按钮 PNG 像素与参考相差 1 个 sRGB 通道值，
但旧提取器把 SwiftUI 声明的 0.35 和同一次操作的原生祖先 alpha 再乘一次，误报为 0.1225。
`72592a6` 改为只记录实际原生祖先的乘积，同时保留声明值和每层原始 alpha。
`ae76905` 在绘制前将空白兼容位图配置为 sRGB，并记录实际颜色空间；其像素断言尚待 CI，容差未变。

完整失败报告 `c4b113d` 已下载到 `S:\Codex\Outputs\Relic-native-visual\parity-c4b113d\report\`，
含 summary.json、parity-report.json 和逐场景 HTML。Windows/macOS 均为 0 个已验收场景，
原始元素分别 107962 / 149839，匹配为 0；macOS 另有 2600 个结构无效元素。
该版本参考捕获不完整，不能把聚合计数解释为完整 636 case 的有效比较。
未添加例外、图标映射或放宽容差。

先前已核实的采集修复证据：共享提交 `38af737` 的
[40987219219](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40987219219) 含 macOS
17 个诊断 case，16 个 captured、1 个 failed-state-captured。成员卡悬停/重命名、实时工具展开、
消息悬停和 textarea 拖拽均完成真实动作与采集；TextKit 2 内部视图被删除的问题没有再次出现。
唯一采集失败仍为群聊四个文档视图高度变化。该提交早于 `3c652b7` 的 VStack/底部滚动修复。
原生回执位于 `S:\Codex\Outputs\Relic-native-visual\smoke-38af737\macos\`，共享 HTML 报告
位于 `S:\Codex\Outputs\Relic-native-visual\parity-38af737\`。元素匹配依旧失败，不能将
16 个采集完成解释为 16 个通过；没有已获批准的例外。

### 2026-10-30：当前修复及最新下载的完整失败报告

已合入 `native-apps` 的 `34d4c35`（共享更新 `4afb5d1`），当前矩阵为 53 个场景 × 12 个语言/主题/尺寸组合，
每个平台 636 个 case；17 个快速诊断 case 只用于定位问题。没有批准或添加任何例外，
容差和完整门禁保持原样。

`b556960` 的 [Native apps 40981767058](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40981767058)
通过构建和 114 个测试，包括实际 ImageRenderer 阴影检查。随后 `c2dc7c9` 的
[40982517205](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40982517205) 构建通过，
118 个测试中 toast 测试有两个断言失败：固定睡眠返回时，实际到期回调还未得到主线程调度。
新几何、滚动条和拖拽测试通过。`48c7ebb` 改为等待真实到期回调，保留暂停期间不失效及同一实例
的检查；[40983301213](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40983301213) 待完成。

后续 `c4b113d` 的 [Native apps 40984430219](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40984430219)
构建及 119 个测试通过，包含上述 toast 修复和真实 TextKit 字形绘制回执测试。更晚的代码仍待 CI。
`6dbdfd8` 和 `c4b113d` 的 17 场景诊断截图均已下载到
`S:\Codex\Outputs\Relic-native-visual\smoke-6dbdfd8\`、`smoke-c4b113d\`，各含 macOS 与同环境参考；
诊断采集失败不等于逐元素通过。后者 [40984430455](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40984430455)
仍暴露聊天文档高度变化及成员重命名控件被采集改变的问题。

真实 CI 回执确认显示模式从 1024×768 切换到 1600×1200，未缩放窗口/截图；textarea 的真实鼠标拖拽
使高度增加 64 px、宽度不变、居中对话框上移 32 px，与参考本次实测增量一致。实时工具输出已通过
点击展开，但旧验证器以展开前的位置校验；头像悬停也已真实绘出，但旧验证器误要求透明 SwiftUI
包装层暴露 AX 节点。`b501f03` 改为验证实际展开后的按钮位置与绘制内容，保留点击前位置和测量来源。

提取器访问 TextKit 2 控件的 `layoutManager` 会使其永久切换为 TextKit 1。`6dbdfd8` 的几何回执
记录数百个内部文字视图因此消失；`0c57b25` 阻止此切换，并保留尚不能完整测量的真实 AX 元素及
失败状态。`c4b113d` 先行换用明确的 TextKit 1 标签后多数场景已稳定，但群聊文档仍从 936 变为
916 px；后续修复是否完全消除这项漂移，须以新 CI 回执为准。成员目录的相同字体在 AppKit 和
参考中按不同单词边界换行，正在修正实际 TextKit 排版并用服务器路径的三行结果做 CI 回归检查。

当前新增修复包括：对话框阴影仅绘制于背景轮廓；成员表单并行加载必要选项；表单 textarea
实际 AppKit 拖拽；10 px 原生滚动条占位；按已下载参考测量设置表单文字和占位颜色。截图采集
增加实际 NSView/NSClipView 几何在 PNG 和 AX 提取前后的稳定性检查；现有聊天区 PNG 与部分
元素坐标不一致的剩余原因仍待新证据确定，不能用偏移补偿冒充修复。完整新矩阵及全部绘制属性
仍待 CI 截图和严格逐元素验证。

`668b1f8` 的 [40987858676](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40987858676)
已构建，但 126 个测试有 10 个断言失败。目录三行换行及长路径回归通过；失败来自独立标签
未挂载时返回 AXUnknown、两个旧测试意外创建 TextKit 2，以及 ImageRenderer 无法绘制混合
AppKit 按钮背后的探针。`8308590` 使测试使用生产 TextKit 1 标签及实际 NSHostingView 位图，
保留原断言及色差限值，等待 CI 证实修复。

完整 `c4b113d` 英文浅色分片的 159 个 case 已下载到
`S:\Codex\Outputs\Relic-native-visual\parity-c4b113d\macos-en-US-light\`，参考位于同级
`reference-macos-en-US-light\`。149 个采集完成，10 个保留失败现场，不是逐元素通过。
失败涉及群聊几何、候选输入内部文字视图、头像/实时工具验证及 1280×800 下消息悬停。
后续 `3c652b7` 将聊天底部 24 px 留白纳入真实滚动目标，使用 VStack 完整排版当前已加载的
消息页；`668b1f8` 明确消息行的悬停命中矩形。设置页英文导航原有多余 Spacer 产生第二个
10 px 间距，导致 Language and names 被截断，现已移除该间距并保留标签的完整可用宽度。
发送按钮和下拉箭头的最新实际绘制仍待新矩阵验证。

明确未解决的参考差异包括浏览器 reference 的 Install 按钮/浏览器安装说明，而原生应用已安装，
且任务禁止浏览器界面；历史源码 parity 的安装替代项不能当作 Amendment 4 批准的视觉例外。
该缺失仍计入失败。未测量的文本绘制、原生控件和装饰仍不得填充为匹配。

最新下载的完整报告来自旧提交 `f7b6bf0`，不是上述修复后的结果：
[Native visual review 40974621706](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40974621706)。
HTML、JSON、已有配对的热图和源元素文件位于
`S:\Codex\Outputs\Relic-native-visual\parity-f7b6bf0\report\`。该运行保留 564 个预期 case 的
报告，macOS 仍只捕获每分片前 15 个原生窗口，候选输入操作后停滞，绝不是完成验收。
`scenes_checked = 0` 表示没有完整且有效的可验收比较，不表示没有采集数据。

| f7b6bf0 原始报告计数 | Windows | macOS |
| --- | ---: | ---: |
| scenes_expected | 564 | 564 |
| scenes_checked / scenes_passed | 0 / 0 | 0 / 0 |
| raw_reference_elements | 105138 | 104502 |
| raw_native_elements | 99335 | 14772 |
| valid_native_elements / invalid_native_elements | 99335 / 0 | 14575 / 197 |
| paired_elements / matched_elements | 89656 / 0 | 9162 / 0 |
| missing | 15482 | 95340 |
| extra | 9679 | 5413 |
| text_mismatch | 24165 | 5998 |
| geometry_out_of_tolerance | 130161 | 15920 |
| style_out_of_tolerance | 296053 | 28294 |
| state_mismatch | 28098 | 8571 |
| kind_mismatch | 276 | 76 |
| region_mismatch | 540 | 56 |
| order_mismatch | 12006 | 756 |
| layout_mismatch | 35912 | 12326 |
| icon_mismatch | 1766 | 206 |
| extraction_errors | 224660 | 120390 |

以上属性差异计数可在同一个元素上出现多项，不能解读为独立元素总数。`passed = false`，
`exceptions = []`，`approved_icon_mappings = []`。参考滚动条环境及矩阵已变化，不能把旧报告
计数直接当成修复趋势。窗口尺寸、菜单、表单控件、所有未测量绘制和文字覆盖仍以严格报告为准。

### 102c1dc 之后：真实事件队列与当前截图修正，等待 CI

`838f96c` 的 [Native apps 40978875575](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40978875575)
已通过 Windows/macOS 构建和静态覆盖；macOS 110 个测试零失败。新用途分行测试得到
`38 / 23 / 2` 个 UTF-16 字符，匹配独立参考；三行宽度分别为 294.442630、293.25、25.5 px。
该结果只证明这些回归检查，不代表完整元素门禁通过。

[a644753 快速诊断 40978583080](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40978583080)
已保存所有 11 个 case，其中实时工具展开失败，错误状态 PNG 和元素文件保留，后续输入动画场景
仍被执行。输出位于 `S:\Codex\Outputs\Relic-native-visual\smoke-a644753\`。
工具行有悬停背景，但中心点击后真实展开状态仍为 false：其 plain Button 的空白 Spacer 未声明
命中区域。现对实际工具行/动作组标题增加整个矩形命中区域，保持同一点击断言等待新 CI。
历史动作组另补齐原先缺少的边框、时间、头像列缩进、工具计数摘要和每行输入/输出块。

`f7b6bf0` 完整运行仍在第一个候选输入框处停止，因此不能把移除 NSPopover 描述为已修复。
捕获的同步 mouseDown 分发可能进入 AppKit 跟踪循环、阻塞其后的 mouseUp；现将完整鼠标/
键盘手势排入 NSApplication 事件队列，保留真实指针移动。每个 case 出错后保存实际失败窗口、
AX/TextKit 和错误，再继续尝试剩余 case；`complete.json` 及元素提取均保留失败，进程仍返回非零。
实时输出检查要求实际展开状态及该控件下方可见的只读 TextKit 输出，不再把透明包装节点的 AX
identifier 是否存在当成输出是否绘制的依据。上述修正尚未获 CI 捕获验证。

[f7b6bf0 快速诊断 40974672159](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40974672159)
只捕获前九个 macOS case，工具输出断言失败；这不是完整矩阵的验收结果。其原生及参考原始截图
已下载并对照，位于 `S:\Codex\Outputs\Relic-native-visual\smoke-f7b6bf0\`。
具体修正包括右栏边框参与布局（正文 307 px 而非 308 px）、概况块底边占位、决策文字行高、
卡片边框内距。新增独立 DOMSnapshot 分行回归；TextKit 不再自行改变 SwiftUI 分配的高度。
当前截图仍存在差异，未获得零差异报告；异常表仍为空。

已合入 `7d0703d` 及共享 `native-layout-projection.md`。该契约要求原始绘制、交互、语义和所有权
证据，不能因 AXGroup 或空背景就删除节点。本客户端尚未据此删减任何包装节点或覆盖失败。

### edf599a：105 个测试通过；最新完整失败报告为 4f6d66b

[Native apps 40975283582](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40975283582)
Windows/macOS 构建、静态覆盖检查通过，macOS 105 个测试零失败。
粗体段落实际宽度 292.419097 px，参考 DOMRange 为 292.40625 px；实际字体
同为 PingFangSC-Semibold。普通文本的四组宽度回归也继续通过。
这些测试并不替代完整逐元素门禁。

[4f6d66b 完整视觉运行 40970311201](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40970311201)
已结束且失败。macOS 四个分片均在候选菜单处超时，各保留前 15 个 PNG；
528 个预期 case 没有全部完成。最新下载的完整 HTML/JSON/热图位于
`S:\Codex\Outputs\Relic-native-visual\parity-4f6d66b\report\`。
以下是该目录 `summary.json` 的原始计数；不是当前 HEAD 的结果。

| 4f6d66b 严格报告 | Windows | macOS |
| --- | ---: | ---: |
| scenes_expected | 528 | 528 |
| scenes_checked / passed | 0 / 0 | 0 / 0 |
| reference_elements | 97,870 | 97,302 |
| native_elements（有效） | 33,601 | 14,800 |
| invalid_native_elements | 0 | 196 |
| paired_elements / matched_elements | 29,729 / 0 | 8,558 / 0 |
| missing | 68,141 | 88,744 |
| extra | 3,872 | 6,242 |
| text_mismatch | 8,005 | 5,086 |
| geometry_out_of_tolerance | 48,880 | 18,725 |
| style_out_of_tolerance | 103,780 | 31,684 |
| state_mismatch | 8,256 | 7,006 |
| kind_mismatch | 340 | 690 |
| region_mismatch | 160 | 56 |
| order_mismatch | 4,202 | 754 |
| layout_mismatch | 11,979 | 13,560 |
| icon_mismatch | 532 | 200 |
| extraction_errors | 84,571 | 130,338 |

例外表和批准的图标映射均为空。未完成的捕获及未知测量继续计入失败，
没有将超时 case 排除，也没有把这些计数描述为通过。

### e9a0dd5 之后：实时会话、编辑态与候选菜单故障修复

已合入共享矩阵的三个实时会话场景。macOS 每个 case 都调用 fixture 的
场景重置端点，记录返回的真实状态；工具输出通过实际 AX 位置上的鼠标事件
展开。输入中圆点使用生产 NSAnimation 时钟，捕获停止并归零该时钟，保留
前后时钟值和实际 draw 记录。实时消息、工具行、权限卡均使用对应的原生布局。
构建和新测试仍待 CI 返回，不能作为已通过的元素证据。

`4f6d66b` 的 [40970311201](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40970311201)
中文深色捕获在前 15 个场景后超时；客户端日志的最后一条是打开候选菜单时
NSPopover 的 nil layout anchor 警告。没有完整回执，不能计为 528 场景完成。
相关原始日志和 PNG 已下载到
`S:\Codex\Outputs\Relic-native-visual\parity-4f6d66b\macos-zh-CN-dark\`。
候选菜单现改为窗口内生产 SwiftUI 控件，仍由输入框 Down Arrow 打开，支持
上下键、回车、Escape 和外部点击；捕获必须验证它实际出现在 AX 树中。
这项修复等待新一轮捕获验证，未取消候选菜单场景或改变共享门禁。

成员卡的改名输入框已移到标题处，模型编辑器移到模型值列；通知使用既有 toast
状态，删除了卡内多余的反馈行。已向共享负责人请求新增改名、模型编辑和头像
悬停三个场景，并实现对应原生交互捕获。它们尚未纳入已检查场景数。

### 180c161：构建通过，新增场景仍待捕获验证

[Native apps 40968278671](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40968278671)
构建及测试通过，覆盖工作区/文件读取、刷新并发与快速开始、线程布局、摘要、
原文展开及窗口内 @ 菜单的实现。该结果不证明视觉或元素一致。
已合入共享分支 `5ff6706` 的两个候选菜单场景及 `member.harness_label`。
macOS 对这两个场景通过实际 AX 输入框位置点击，再向真实窗口发送 Down Arrow；
候选弹出框未出现在实际 AX 树中会使捕获失败，不注入替代菜单。
模型/席位原生候选弹出框的外观仍待同场景比较；没有增加任何例外。

### 8fbed05：504 个 macOS 捕获完成，严格门禁仍失败

[完整视觉运行 40966815307](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40966815307)
四个 macOS 分片全部成功，各 126 张，包含三个窗口尺寸。
Windows 四个捕获分片失败，比较仍生成完整的失败报告，缺失捕获计入门禁。
已下载的 HTML、JSON 和热图位于
`S:\Codex\Outputs\Relic-native-visual\parity-8fbed05\report\`。
以下数字直接来自该报告的 `summary.json`，不是当前 HEAD 的结果。

| 8fbed05 严格报告 | Windows | macOS |
| --- | ---: | ---: |
| scenes_expected | 504 | 504 |
| scenes_checked / scenes_passed | 0 / 0 | 0 / 0 |
| raw_native_elements | 31,888 | 119,340 |
| valid_native_elements | 31,888 | 116,435 |
| invalid_native_elements | 0 | 2,905 |
| reference_elements | 93,032 | 92,536 |
| paired_elements / matched_elements | 28,255 / 0 | 59,602 / 0 |
| missing | 64,777 | 32,934 |
| extra | 3,633 | 56,833 |
| text_mismatch | 7,976 | 33,569 |
| geometry_out_of_tolerance | 40,387 | 144,984 |
| style_out_of_tolerance | 100,736 | 210,053 |
| state_mismatch | 7,820 | 35,139 |
| kind_mismatch | 340 | 5,157 |
| region_mismatch | 152 | 627 |
| order_mismatch | 4,756 | 6,997 |
| layout_mismatch | 11,708 | 88,383 |
| icon_mismatch | 532 | 1,871 |
| extraction_errors | 78,676 | 923,141 |

例外表和批准的图标映射表为空。`scenes_checked=0` 表示提取仍不完整，
不能把 504 张成功截图当作元素通过。随后已合入 `cd6c840`，新增场景矩阵为 528。
后续修复包括每场景清空客户端状态、初始画布焦点、原生裁剪、成员名片及 Markdown。
字体 CI 证明自动光学字号会改变同名 PingFangUI 字体的字形 advance：
代表段落默认 401.766 px，自动光学字号 419.406 px，参考 419.438 px。
`67dae7b` 已使用公开 CoreText 自动光学字号属性；
[Native apps 40970989476](https://github.com/Hongyi-Du/Relic-Plugins/actions/runs/40970989476)
构建与 97 个测试全部通过，包括四组字体宽度回归和原生滚动裁剪断言。
这四组 advance 与参考的差异分别约 0.031、0.048、0.079、0.037 px；
仍需完整场景的截图和元素测量验证，不能据此宣称全部字体/布局通过。

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
