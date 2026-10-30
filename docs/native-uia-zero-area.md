# Windows 省略预览的零面积 UIA 范围

本记录是只读诊断与下一步实现边界，不是将零面积范围判为隐藏的豁免。
没有修改 Capture、projector、阈值或失败规则；没有在本机运行应用或测试。

## 已读到的实际证据

证据目录：`S:\Codex\Outputs\Relic-native-visual\smoke-b89f80b-windows-zh-light`。
该目录实际有 19 个 PNG、19 个 `native-label-frame.json`、76 个 surface readback
记录，`surface_readback_errors` 总数为 0。这些是实际 `NativeLabel` 的绘制回读，
不能当作仍由 `TextBlock` 绘制的侧栏预览的字形证据。

以下均来自 `zh-CN-light-1440x900-group.uia.json` 及同名 `xaml.json`。
UIA 实际窗口原点是屏幕 `(8,31)`；表中的原始 COM 数组未减窗口原点。

| 对象 | 原始文本/范围 | 实际 COM 矩形 | 其他证据 |
|---|---|---|---|
| `uia-55` / `xaml-276` | `设计师：三个窗口尺寸都会检查，长标题会换行或显示省略提示。`，UTF-16 `[0,29)` | 文档范围依次为 `[88,294,132,16]`、`[220,294,8,16]`、`[8,31,0,0]` | XAML `TextBlock`；`NoWrap`、`CharacterEllipsis`；实际 `IsTextTrimmed=true` |
| `uia-55` 第一个 visible range | `设计师：三个窗口尺寸都`，`[0,11)` | `[88,294,132,16]` | 实际 `IsHidden=false` |
| `uia-55` 第二个 visible range | `。`，`[28,29)` | `[8,31,0,0]` | 实际 `IsHidden=false`；非 degenerate range |
| `uia-61` / `xaml-297` | `秘书处负责人：目前有两项：确认权限设置，以及本轮集成负责人。任务和相关协议都在右侧概况中。`，`[0,45)` | 文档范围依次为 `[88,344,132,16]`、`[220,344,8,16]`、`[8,31,0,0]` | 同样是实际被截断的单行 `TextBlock` |
| `uia-61` 两个 visible ranges | 前缀 `秘书处负责人：目前有两`，`[0,11)`；末尾 `。`，`[44,45)` | 前缀 `[88,344,132,16]`；句号 `[8,31,0,0]` | 两者 `IsHidden=false` |

`xaml-276` 实际 bounds 为 `(80,263.1549987792969,140.794921875,16.20001220703125)`，
`xaml-297` 为 `(80,313.05499267578125,140.794921875,16.20001220703125)`。
两者 `visible_bounds` 等于 bounds，自己的 `Clip=null`，共同的祖先裁剪框为
`(33,239.1999969482422,234,288.375)`。因此这不是现有证据所显示的整个控件被祖先裁出窗口。
`actual_trimming.ellipsis_bounds` 仍为 `null`。

实际 PNG 可见两个预览都在右端省略。文档中的 8×16 矩形是候选省略符命中区域，
但 UIA 记录没有给出“这个矩形由省略号字形绘制”的关联；不能把它直接改名为省略号 ink box。
XAML 的 character rectangle 是约 140.795×15.240 的文本范围框，也不是独立省略符盒。

生产入口是 `SidebarCopies.cs` 的 `Chat` 预览：`SidebarText(subtitle,12,...)`，
行高 16.2、不可选、`TextWrapping.NoWrap`、`TextTrimming.CharacterEllipsis`。
没有为这两个末尾句号设置隐藏、透明或独立裁剪状态。

## 微软源码能解释什么

已核对微软公开源码提交 `0a03f68d586d1c100f753ca3221597c3ee550f4a`：

- [`CTextAdapter::GetVisibleRanges`](https://github.com/microsoft/microsoft-ui-xaml/blob/0a03f68d586d1c100f753ca3221597c3ee550f4a/dxaml/xcp/core/text/common/textadapter.cpp#L102)
  先取得整个文档的 text bounds，跳过原始零宽/零高矩形，再对每个剩余矩形左右内侧点
  调用 `PixelPositionToTextPosition` 生成文字范围。它并未保证新生成范围再次查 bounds 后仍有面积。
- [`TextBlockView::PixelPositionToTextPosition`](https://github.com/microsoft/microsoft-ui-xaml/blob/0a03f68d586d1c100f753ca3221597c3ee550f4a/dxaml/xcp/core/text/TextBlock/TextBlockView.cpp#L269)
  的 DirectWrite 分支使用实际 `HitTestPoint`，再以 `textPosition + length - 1 + trailingHit`
  等信息形成文本端点。因此替代区域可能映射到原文后部位置；本次“8px 区域→末尾句号”的形态与此机制吻合。
  这是结合源码的解释，当前 receipt 还没有保存这些内部 hit-test metrics，不能把它写成已测绘制结论。
- [`TextBlockView::TextRangeToTextBounds`](https://github.com/microsoft/microsoft-ui-xaml/blob/0a03f68d586d1c100f753ca3221597c3ee550f4a/dxaml/xcp/core/text/TextBlock/TextBlockView.cpp#L28)
  将 DirectWrite hit-test metrics 的 left/top/width/height 交给上层，
  没有同时向 UIA 传递 `isText`、`isTrimmed` 与替代对象身份。
  [`CTextRangeAdapter::GetBoundingRectangles`](https://github.com/microsoft/microsoft-ui-xaml/blob/0a03f68d586d1c100f753ca3221597c3ee550f4a/dxaml/xcp/core/text/common/textrangeadapter.cpp#L599)
  变换和扁平化这些矩形，并不删除零面积条目。
- [`IsHiddenAttribute`](https://github.com/microsoft/microsoft-ui-xaml/blob/0a03f68d586d1c100f753ca3221597c3ee550f4a/dxaml/xcp/core/text/common/textrangeadapter.cpp#L2027)
  在该实现中直接返回 false。它不是逐范围栅格可见性证明。
- [`UpdateIsTextTrimmedFastPath`](https://github.com/microsoft/microsoft-ui-xaml/blob/0a03f68d586d1c100f753ca3221597c3ee550f4a/dxaml/xcp/core/text/TextBlock/TextBlock.cpp#L1935)
  使用 DirectWrite 的 line metrics 判断整个 TextBlock 已截断。该属性能支持“发生过截断”，
  不能定位哪个 UTF-16 区间被替代，也不能返回省略符的 glyph 或 ink box。

源码版本边界必须保留：本机当前构建输出的 `Microsoft.UI.Xaml.dll` 文件版本是
`3.1.6.2506`，产品版本 `1.6`，文件版本中的源码标记为
`08ec1de0f82d16742618784569dcfb69a2c1c99f`。该标记在微软公开仓库查询返回未找到。
项目包版本是 `Microsoft.WindowsAppSDK 1.6.250602001`。以上公开源码是可审计的机制证据，
不是对 CI 中 DLL 每条内部指令的二进制证明。

## 有限的下一步

现有 UIA 加 `IsTextTrimmed` 足以发现 provider 的几何/文本归属不完整，
**不足以严格证明末尾句号没有被绘制，也不足以取得实际省略号字形的边界**。
不能将这些零矩形改为 hidden、丢弃它们或把 8px 文档矩形直接标成省略号而清除 gate。

可以在 CI 添加一次有限诊断：对实际文档里这个 8px 正面积矩形的左右内侧与中心调用
真实 `TextPattern.RangeFromPoint`，保存前后文档文本、runtime ID、端点、再查询的原始矩形。
这不需要移动鼠标，也不修改控件。若再次落在 `[28,29)` / `[44,45)`，可以加强
“替代区域回映到句号”的证据；仍不能单独解除字形覆盖失败。

要取得完整证据，建议下一项生产实现只替换侧栏单行预览的绘制，沿用已有真正绘制的
`NativeLabel`，增加 character-ellipsis 选项，不改四个菜单标签的默认行为：

1. 在**用于实际绘制的同一 layout** 上设置 character trimming，使用
   [`CreateEllipsisTrimmingSign`](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritefactory-createellipsistrimmingsign)
   创建真正绘制的 omission object；记录它与 `GetTrimming` 返回对象的真实 COM 身份。
2. 同一个 layout 的
   [`DWRITE_HIT_TEST_METRICS`](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/ns-dwrite-dwrite_hit_test_metrics)
   保存 `textPosition/length/isText/isTrimmed`，同时保存实际 line metrics。
   当前 `NativeLabel.ReadHitTestBounds` 已有这些字段；不可用旁建 layout 替现有 TextBlock 测量。
3. 在实际
   [`DrawInlineObject`](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritetextrenderer-drawinlineobject)
   回调记录 omission object 的身份、原点与实际返回结果，并继续让该对象画入同一 SurfaceImageSource。
   现有 renderer 已转发 inline draw 并标记 `from_inline_object`，还需增加确切对象身份和所属绘制记录。
4. 将省略对象真正提交的 glyph run、face、D2D ink bounds、实际 surface 回读与最终截屏对应。
   命中区域框、ink box、layout box 必须分别保留，不能拿其中一种冒充另一种。
5. 只有测得某个实际 `isTrimmed` 区间被同一 omission object 的绘制替代，并完成同帧关联后，
   才能将该区间作为“被省略替代的原文”保留在 raw evidence，而不要求它的每个原字符有独立可见 glyph。
   缺少任一关联继续失败。UIA 的 `IsHidden=false` 原值仍保留，不能改写。

回归必须包括完整未截断文字、截断后正面积省略符、原文末尾句号、零面积但未证实截断、
以及未知 inline object / 绘制失败。几何与颜色容差、场景数量和矩阵均不变。

## 已实现、等待 CI 的有限生产改动

侧栏 `Chat` 的同一个 subtitle 入口现在使用实际 `NativeLabel`，覆盖群聊和私聊预览。
名称、组织名称、页脚及 logo 未迁移。默认四个菜单标签仍不启用省略选项。
预览的显式 foreground 仍为原先 `Muted`，完整原文由真正的 Text automation peer 提供；
其唯一 Image 子对象仍是实际文字绘图 surface，不成为独立可访问图片。
父行的名称拼接也读取完整 `NativeLabel.Text`，原有行工具提示和点击行为保留。

`ApplyCharacterEllipsis` 在实际生产 layout 上调用 `CreateEllipsisTrimmingSign` 和
`SetTrimming(CHARACTER)`；没有创建替代测量 layout。每次真实 Draw 的 receipt 增加：

- `trimming`：同一个 layout 的 `GetTrimming` 返回值、配置及实际返回省略对象的 COM 身份、
  `same_sign_com_identity`，以及真正 `IDWriteInlineObject.GetMetrics` 的布局尺寸。
- `inline_object_draws`：实际 `DrawInlineObject` 回调、对象身份、是否是配置的省略对象、
  父 inline 调用、绘制原点、真实转发 `IDWriteInlineObject.Draw` 的 HRESULT、对应 glyph-run ordinal。
- 每个真实 glyph run 保留原始 `DrawGlyphRun`/font-face/ink bounds，并增加实际 inline 调用 ordinal。
  原有 line metrics、`HitTestTextRange.isTrimmed`、EndDraw、SIS readback 及 frame 关联机制继续使用。

新增 ABI 已按本机 Windows SDK `10.0.26100.0/um/dwrite.h` 核对：
factory slot 20、TextFormat/Layout slots 9/17、InlineObject slots 3/4；
`GetTrimming` 与 `GetMetrics` 都是 HRESULT 加显式输出指针，结构分别为 12 与 16 字节，
没有使用 COM 的结构返回值 ABI。相关声明和调用有 CI 专用回归；真实 DirectWrite 测试验证
同一 layout 在宽度缩小/恢复后改变实际 trim state，原文长度和省略对象身份保留。
测试不会启动 WinUI 应用或窗口，本机未执行。

这批代码**尚不声称省略符匹配通过**。没有修改 projector，也没有把 UIA 零面积范围分类为隐藏。
新的 receipt 提供可进一步验证的实际绘制来源；省略对象与 trim interval 的严格对应、
最终截图可见字形的规范化几何、未知或失败 inline 绘制的完整覆盖仍需在 CI 实际证据中验证。
`coverage_complete=false` 保留，因此相关未知不会被这批生产替换自动清除。
