# Windows 文本范围：27e39b3 的实际浮点与 UIA 零高度证据

本记录只解释 CI 原始证据，不改变任何提取错误、匹配字段、容差或可见性判据。
两个被调查的实际 TextBlock 在 WinRT 文本提供程序层都返回了**正的亚像素高度**。
独立进程 UIA 中同文案的范围返回零高度，与后续整数化一致；目前还没有完整
opaque RuntimeId 与 XAML owner 的实际关联，因此不能把这种数值对应直接当作
同对象、同次原生范围的转换证明，也不能据此解除门禁失败。

## 证据位置与范围

原始产物目录：

```text
S:\Codex\Outputs\Relic-native-visual\smoke-27e39b3-windows-zh-light\
```

两个 case basename：

- `zh-CN-light-1440x900-file-code`
- `zh-CN-light-1440x900-live-tool-output`

本记录读取各 case 的：

- `.text-range-provider-probe.json`：实际 TextBlock → FromElement → GetPattern(Text)
  → DocumentRange / GetVisibleRanges 的 WinRT 查询。
- `.text-range-provider-probe.progress.jsonl`：逐调用原始结果、异常和 QPC。
- `.provider-probe.json`：独立 UIA 遍历前后保留的同一个生产 peer 及其实际 COM 出口。
- `.uia.json`：独立 UIA 元素、原生 COM SAFEARRAY 原值、范围身份和错误。
- `.uia.json.progress.jsonl`：独立 UIA 捕获过程。
- `.xaml.json`：实际 owner 的布局、裁切及尚未完成的 automation identity 记录。

这些是 commit `27e39b3` 的实测，不是正在排队的 `a3ca2a3` held-observer
捕获结果。本轮分析不运行本地应用、服务器、测试或安装。

## WinRT 查询的实际 owner 与时间

TextRangeProviderProbe 的 phase 均为
`after-independent-uia-and-provider-probe`，查询在 UI 线程 1 执行。
它按原 renderIds 查询全部实际 TextBlock，不按名字或位置选择候选；下面按源文案
检索既有记录只是为了定位审阅条目，不建立 UIA 与 XAML 的身份关联。

| case | 实际 owner | TextBlock 数 | 完成 | API 异常 | 全 case contract issues | 探针耗时 |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| file-code | `xaml-517` | 80 | true | 0 | 5 | 221.0373 ms |
| live-tool-output | `xaml-970` | 165 | true | 0 | 5 | 285.6555 ms |

两个目标 owner 自己的 `error_count` 和 `contract_issue_count` 均为 0。
全 case 的 5 个问题分别是其他 TextBlock 的 GetVisibleRanges 返回 null；
它们仍保留为独立问题，不能把目标 owner 成功概括为全捕获无缺口。

两个 owner 均有以下实际观察：

- `peer_type = Microsoft.UI.Xaml.Automation.Peers.TextBlockAutomationPeer`。
- `peer_owner_same_object`、`peer_same_object_after`、
  `peer_owner_same_object_after`、`events_source_same_object_after` 均为 true。
- EventsSource 前后均为 null；没有另一个事件 owner 被替换进来。
- owner.Text 和 DocumentRange.GetText(-1) 的前后 UTF-16 字节完全一致。
- 前后 `IsLoaded=true`、`Visibility=Visible`、`Opacity=1`、
  `IsTextTrimmed=false`、`TextTrimming=None`，实际尺寸与根坐标保持不变。
- 所有目标范围的 clone 端点对齐比较返回 0，前缀 UTF-16 长度在文档范围内，
  范围原文与对应文档片段一致。

成功调用只记录 `returned_normally=true`，`hresult=null`：
C# WinRT 投影没有提供原始成功 HRESULT。不得将其补写为原生 S_OK。

## file-code：reviewer 加入事件

原文：

```text
reviewer 加入了组织，角色「验收与回归检查」
```

长度为 26 个 UTF-16 code units。实际 owner `xaml-517` 前后：

```json
{
  "actual_width": 251.783203125,
  "actual_height": 19.200000762939453,
  "root_origin_x": 467.1083984375,
  "root_origin_y": 77.64999389648438,
  "content_start_offset": 0,
  "content_end_offset": 30,
  "line_height": 19.200000762939453
}
```

WinRT DocumentRange 与 visible-0 的原始数组完全相同：

```json
[467.1083984375, 96, 251.783203125, 0.8499908447265625]
```

对应 IEEE754 位模式：

```json
["407D31BC00000000", "4058000000000000", "406F791000000000", "3FEB332000000000"]
```

| 范围 | 经实际 clone 前缀测得的 UTF-16 span | start 对 document start | end 对 document end | start 对自身 end |
| --- | --- | ---: | ---: | ---: |
| document | [0, 26) | 0 | 0 | -30 |
| visible-0 | [0, 26) | 2 | -2 | -26 |

CompareEndpoints 的返回值仅作为实际相对位置/相等性证据；它包含内部结构位置，
**不是 UTF-16 字符偏移**。文档和 visible range 的内部端点并不完全相同，
但二者实际原文均覆盖完整 26 个 UTF-16 code units，且返回相同浮点矩形。
不能把 doc 的 -30 直接解释为 30 个可见字符。

独立 UIA 条目 `uia-117`：

```json
{
  "runtime_id": [42, 851990, 4, 114],
  "window_origin": [8, 31],
  "native_bounds_raw": [475, 127, 251, 0],
  "bounds_after_origin_subtraction": [467, 96, 251, 0],
  "native_span_utf16": [0, 26],
  "native_is_hidden": false
}
```

UIA document、visible range 及其 format run 均返回同一个零高度数组，
产生 3 条错误，属于同一段文本的 3 次测量，不能算作 3 个不同的 UI 元素。
UIA 的 managed Rect.Empty 只是此有限零高数组的投影；真实 COM 原值已经保存，
不是 JSON 序列化非有限值导致零高度。

## live-tool-output：秘书处说明末行

原文：

```text
全库只有一个秘书处，它的负责人就是秘书长：成员新建或调整正式组织，要秘书长批准；各正式组织的负责人也会自动在秘书处有一个席位。
```

长度为 63 个 UTF-16 code units。实际 owner `xaml-970` 前后：

```json
{
  "actual_width": 288,
  "actual_height": 55.80000305175781,
  "root_origin_x": 1117,
  "root_origin_y": 862.4000244140625,
  "content_start_offset": 0,
  "content_end_offset": 67,
  "line_height": 18.600000381469727
}
```

WinRT DocumentRange 原始数组：

```json
[
  1117, 862.4000244140625, 288, 18.5999755859375,
  1117, 881, 288, 18.5999755859375,
  1117, 899.5999755859375, 180, 0.4000244140625
]
```

三个 GetVisibleRanges 范围分别返回对应四元组：

| 范围 | 经 clone 前缀测得的 UTF-16 span | 实际原文 |
| --- | --- | --- |
| visible-0 | [0, 24) | 全库只有一个秘书处，它的负责人就是秘书长：成员新 |
| visible-1 | [24, 48) | 建或调整正式组织，要秘书长批准；各正式组织的负责 |
| visible-2 | [48, 63) | 人也会自动在秘书处有一个席位。 |

末行原始位模式为
`["4091740000000000","408C1CCCC0000000","4066800000000000","3FD99A0000000000"]`。
DocumentRange 与 visible-2 的末行几何一致，前后原文稳定，没有丢弃末行或生成替代范围。

独立 UIA 条目 `uia-233`：

```json
{
  "runtime_id": [42, 655720, 4, 230],
  "window_origin": [8, 31],
  "native_document_bounds_raw": [
    1125, 893, 288, 18,
    1125, 912, 288, 18,
    1125, 930, 180, 0
  ],
  "last_range_bounds_after_origin_subtraction": [1117, 899, 180, 0],
  "last_range_span_utf16": [48, 63],
  "native_is_hidden": false
}
```

UIA document 的第三个矩形、visible-2 及其 format run 各产生一条零面积错误，
合计 3 条。前两行是正面积。不能因为第三行的 glyph/font metric 几何可能在窗口外，
就把提供程序的正高 line allocation 当作完全不可见；它们是不同的测量量。

## 两阶段 peer 证据与仍未成立的跨层绑定

既有 AutomationProviderProbe 在独立 UIA 遍历前保留实际 peer，在遍历后查询原实例。
下面的 IUnknown 地址在各自进程内前后相同；它们只证明本地实际 COM 对象观察，
不能与另一个进程的指针或 UIA RuntimeId 按数值拼接。

| case | retained peer 的 IUnknown | before QPC 起止 | after QPC 起止 | TextRangeProbe 目标 owner QPC 起止 |
| --- | --- | --- | --- | --- |
| file-code | `0x1E6AB73FD98` | 4220945712–4220948338 | 4291795046–4291797714 | 4294061492–4294080002 |
| live-tool-output | `0x1D891E0F638` | 4350909876–4350912447 | 4455173875–4455175002 | 4457399606–4457423564 |

QPC frequency 为 10000000。TextRangeProbe owner 的精确起止以 JSON 为准；
独立 UIA 进程自己的进度日志记录 elapsed time，不能把它的 elapsed 值冒充 QPC。
这些记录支持前后观察一致；当前两个独立 API 层的查询仍不是原子测量。

两个 peer 的 `MarshalInspectable<object>.FromManaged` 和
`IWinRTObject.NativeObject.GetRef` 出口，在 before 与 after 阶段查询
`IRawElementProviderFragment` 均返回实际 `E_NOINTERFACE (0x80004002)`。
因此 XAML `automation_identity_evidence.status` 仍为 `unknown`，
其 `native` 值为 null，尚无完整 opaque RuntimeId。

另一方面，独立 UIA 内部的 managed 与 native COM range 关联已成功：

| case | 原生 HWND 索引节点数 | RuntimeId 唯一候选 | traversal errors | matched_range_count |
| --- | ---: | ---: | ---: | ---: |
| file-code | 200 | 1 | 0 | 3 |
| live-tool-output | 319 | 1 | 0 | 7 |

这证明独立 UIA 捕获不是在多个 native RuntimeId 候选中随意挑选，
但**不证明** `uia-117 == xaml-517` 或 `uia-233 == xaml-970`。
相同文案、相同 UTF-16 span、相近坐标和整数化形态都不能替代缺失的对象身份绑定。

## 固定 SDK 能支持的解释

项目固定使用 Windows App SDK `1.6.250602001`。已审阅的官方 WinUI 固定源码
`da699b040bddc2a6adf660512a7c6db8a96bfbe3` 中：

- GetVisibleRanges 按 TextRangeToTextBounds 的行矩形创建范围，跳过当地零宽/零高；
  不能仅凭一个范围出现在该数组就断言其最终 viewport 可见。
  [CTextAdapter::GetVisibleRanges](https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/core/text/common/textadapter.cpp)
- GetBoundingRectangles 对实际文本范围调用 TransformToWorldSpace，并启用祖先及
  ScrollContentPresenter 裁切，再将实际浮点矩形各分量写入 double 数组。
  [CTextRangeAdapter::GetBoundingRectangles](https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/core/text/common/textrangeadapter.cpp)
- WinRT TextRangeAdapter 的 GetBoundingRectanglesImpl 将 CoreImports 返回的
  DOUBLE 值逐项复制到输出，没有在这个已审阅函数里将宽高强转为整数。
  [TextRangeAdapter::GetBoundingRectanglesImpl](https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/dxaml/lib/TextRangeAdapter_partial.cpp)

本轮没有定位到该固定 SDK 构建中负责**宽高**整数化的确切桥接函数或 cast。
当前主分支的其他实现不能冒充此固定二进制的源码。准确表述是：
“已绑定 owner 的 WinRT 查询保留正的分数高度；独立 UIA 同文案记录呈现整数化迹象”。
不能表述为“已经证明某个指定桥接函数把同一个范围的高度截断为 0”。

## 下一最小步骤

1. 先审阅 held-observer CI 的实际结果，确认独立原生 UIA 对象仍存活时取得的实际
   provider 出口和完整 opaque RuntimeId。若仍失败，继续保留 identity unknown，
   不按文字、box 或 RuntimeId 后缀猜关联。
2. 只有完整 RuntimeId、真实 owner/peer/EventsSource 和原生对象连续性成立后，
   再用同源文档及实际 endpoint 证明两侧测的是同一段范围，并验证查询期间布局、
   裁切、root scale、window origin 与源文案没有变化。
3. 上述证据齐全后，才评估将同 owner 的实际 WinRT 浮点范围作为额外精度证据。
   它仍需声明实际坐标空间及 line allocation 的测量含义；原 COM 数组、异常和
   精度损失记录必须保留。不能直接复制一个 TextPointer/font-metric box 当作 UIA box。
4. 当前不改 gate，不清除这 6 条零面积错误，不把它们降级为非可见诊断，
   不通过调整滚动、padding、字体或布局使错误“消失”。

本记录没有提供 production 修复成功、最终像素贡献或逐元素 parity 已完成的证明。
