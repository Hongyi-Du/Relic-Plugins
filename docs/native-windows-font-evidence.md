**Windows 实际字体证据：可实施的生产绘制路径**

调研日期：2026-10-29。本文是实现方案，不是已经完成的渲染器或验收证据。本轮只读取了项目、本机 SDK 文档和微软公开文档／源码，没有安装工具、运行应用或修改生产文本控件。

结论是：现有 WinUI `TextBlock` / `RichTextBlock` 的公开 API 没有找到可以取出其实际 `IDWriteTextLayout`、`IDWriteFontFace` 或 glyph-run 回调的方法。要让字体证据最终摆脱 `null`，可实施的路线是让应用自己的原生文本控件通过 DirectWrite 的实际绘制回调画字，并在同一个回调中记录真正送到 Direct2D 的 glyph run。不能保留原控件画字，再另建一份 layout 来声称测得了原控件。

当前项目引用 `Microsoft.WindowsAppSDK 1.6.250602001`，目标 `net8.0-windows10.0.19041.0`，最低版本 `10.0.17763.0`，见 [Relic.csproj](../native/windows/Relic/Relic.csproj)。本机已读的 API 清单为 `S:\Codex\Caches\nuget\microsoft.windowsappsdk\1.6.250602001\lib\uap10.0\Microsoft.UI.Xaml.xml`；它列出了文本属性、`TextPointer`、`GetAlphaMask` 和自定义 UIA provider 接口，没有上述内部 layout / face getter。本机缓存没有 Win2D；本文没有因此下载包。这里的“没有找到”限定为这套公开 API 和下述已核实源码，不能推导为所有私有实现都不可访问。

UIA 字体目前为什么不能充当实际字体：微软 WinUI 源码 `CTextRangeAdapter::GetAttributeValueFromTextElement` 的 `FontNameAttribute` 分支读取的是 `TextElement_FontFamily`，再返回 `CFontFamily::Source`；字号和字重分支也读取声明属性。源码已经钉住提交 `0a03f68d586d1c100f753ca3221597c3ee550f4a`，可以直接审计 [textrangeadapter.cpp 的相关分支](https://github.com/microsoft/microsoft-ui-xaml/blob/0a03f68d586d1c100f753ca3221597c3ee550f4a/dxaml/xcp/core/text/common/textrangeadapter.cpp#L1987)。因此现有提取器将 UIA 名称留在 `evidence.provider_fonts`，而 `style.rendered_fonts` 保持未知，是对现有证据的正确处理。

| 途径 | 能证明什么 | 对已有 WinUI 文本的结论 |
|---|---|---|
| UIA `FontName`、XAML `FontFamily.Source` | 控件／文本范围声明的字体 | 不能证明 fallback face |
| cmap / `HasCharacter` | 某个字体是否可能覆盖字符 | 可以排除不可能的声明，不能确认实际绘制字体 |
| `IDWriteFontFallback::MapCharacters` | 给定输入和回退条件下应选的字体 | 是字体选择运算，不是读取已有控件的绘制记录；[官方接口](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_2/nf-dwrite_2-idwritefontfallback-mapcharacters)没有控件或已绘制 glyph-run 参数 |
| 另建 `CanvasTextLayout` / `IDWriteTextLayout` 后收集回调 | 那一份新 layout 的字体选择 | 不能冒充原来 `TextBlock` 的结果 |
| 截图、`GetAlphaMask`、GPU 字形纹理 | 已绘制像素／覆盖范围 | 不能唯一反推字体文件、face index 和变体轴 |
| 自有控件在真正 `Draw` 中记录并绘制同一 glyph run | 该控件这一绘制版本使用的实际 face 和字形 | 可实施；替换范围内可产生真实证据 |

**建议采用的最小生产结构**

保留原生 `Button`、菜单、列表、滚动容器、对话框及其动作逻辑；替换它们真正绘制文字的内容。增加一个 `RelicTextView : Control`，模板中放原生 Win2D `CanvasControl`，由小型 C++/WinRT 组件持有唯一的 DirectWrite layout。控件的 Measure、Arrange、绘制、命中检测和 UIA 范围都使用这一份 layout。名称是建议的新生产类型，尚未创建。

Win2D 在这里只负责原生 XAML 绘制表面和设备生命周期。`CanvasControl.Draw` 把实际 `CanvasDrawingSession` 交给组件；组件通过公开 interop 取得当前 `ID2D1DeviceContext1`。微软的 [Win2D interop 表](https://learn.microsoft.com/en-us/windows/apps/develop/win2d/interop)明确列出这组对应，C++/WinRT 可经 `ICanvasResourceWrapperNative::GetNativeResource` 使用。组件随后调用它自己持有、同时用于布局的 `IDWriteTextLayout::Draw`，把记录器作为真正 renderer。该接口本来就通过 renderer 回调执行文字、装饰和 inline object 的绘制：[DirectWrite Draw](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritetextlayout-draw)。

实际调用链应为：

```text
RelicTextView / CanvasControl.Draw
  -> NativeTextSurface.Draw(currentDrawingSession, layoutRevision, ownerId)
     -> IDWriteTextLayout::Draw(actualFrameContext, RelicTextRenderer, origin)
        -> RelicTextRenderer::DrawGlyphRun(actual DWRITE_GLYPH_RUN)
           -> copy actual face / glyph / description / draw-state evidence
           -> ID2D1DeviceContext::DrawGlyphRun(the SAME run, actual brush)
     -> finish the drawing session successfully
     -> publish records for that presented surface revision
```

这是同一生产绘制路径上的观测，不是额外排版。`IDWriteTextRenderer::DrawGlyphRun` 收到的 face 就是该次绘制应使用的物理字体；回调的职责是把它交给真实图形 API 绘制，见 [DrawGlyphRun 文档](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritetextrenderer-drawglyphrun)。记录器不能替换字体、重新 shape、重算 advances，或只记录后让另一条路径负责画字。

实现应使用 `IDWriteTextRenderer1`，并实现真实像素吸附、DPI、变换、underline、strikethrough、inline object 回调。彩色 emoji / 字体不能退化为单色：应调用 `IDWriteFactory4::TranslateColorGlyphRun`，保留 base run 与真正绘制的 color layer 记录，并根据实际 glyph image format 使用相应 Direct2D 绘制入口。微软说明了 [base run 到 color runs 的转换](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nf-dwrite_3-idwritefactory4-translatecolorglyphrun)。遇到未实现的格式必须产生覆盖失败，不能静默改画。

| 实测内容 | 直接来源 | 记录要求 |
|---|---|---|
| 实际 face | 回调的 `DWRITE_GLYPH_RUN.fontFace` | 持有 COM 引用，不能从 family name 重新创建后替代 |
| family、face、PostScript 名称 | 对同一 face 查询 `IDWriteFontFace3` | `GetFamilyNames` / `GetFaceNames` / `GetInformationalStrings`；缺失字符串记录缺失，不能用声明名填空；[字符串 API](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nf-dwrite_3-idwritefontface3-getinformationalstrings) |
| 文件来源、集合中的 face index、模拟样式 | 同一 `IDWriteFontFace` 的 `GetFiles`、`GetIndex`、`GetSimulations` | 保存实际 loader/reference key 和 index；不要求字体一定来自本地路径；[GetFiles](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritefontface-getfiles)、[GetIndex](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritefontface-getindex) |
| 变体轴 | 对回调同一 face 查询 `IDWriteFontFace5` | `GetFontAxisValueCount` / `GetFontAxisValues` 返回实际实例的 tag/value；不要把用户请求的 `wght` 等值当实测；[轴 API](https://learn.microsoft.com/en-us/windows/win32/api/dwrite_3/nf-dwrite_3-idwritefontface5-getfontaxisvalues) |
| 字形、位置 | glyph indices、advances、offsets、em size、baseline、bidi level、sideways / orientation | 这些值来自实际 run，坐标按实际 DPI / 变换换算；[glyph-run 结构](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/ns-dwrite-dwrite_glyph_run) |
| 源文字归属 | `DWRITE_GLYPH_RUN_DESCRIPTION` 的 UTF-16 字符串、text position、cluster map | 字符数和 glyph 数不一定相等，不能按一个字符一个 glyph 分配；[description 结构](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/ns-dwrite-dwrite_glyph_run_description) |
| 绘制范围 | 同一 context 的 `GetGlyphRunWorldBounds`，再结合实际 clip 和可见性 | world bounds 只是包围框，不能把跨行／双向字形中的空隙当成实心覆盖；[实际 context bounds](https://learn.microsoft.com/en-us/windows/win32/api/d2d1_1/nf-d2d1_1-id2d1devicecontext-getglyphrunworldbounds) |

每条记录还需携带生产 owner id、layout revision、surface revision、draw ordinal、实际 brush / opacity、clip 和坐标变换。只有成功完成的绘制版本能用于对应截图；device lost、未完成的 session、过期 layout、被裁掉的文字都不能借另一帧补齐。回调证明的是被提交绘制的 run，单独一次回调并不证明它已经出现在最终屏幕。CI 必须等待对应 surface 的绘制完成，再沿现有截图帧流程捕获；这部分需要用实际 CI 验证，本文不宣称已有现成的帧同步实现。

普通文字、字重、字号、超链接、Markdown run 的源文字都由控件自己的生产文档模型建立稳定归属。省略号和 inline object 的回调若没有原文字范围，须以其实际装饰／对象身份记录，不能硬分配给某个原字符。提取器仍独立从 UIA 读取语义和状态，再使用生产控件实际渲染记录补充 face、字形和几何；它不读取参考页面来生成节点。

**为什么不直接推荐纯 C# `ICanvasTextRenderer` 包装作为最终轴证据**

Win2D 的 `ICanvasTextRenderer` 确实提供实际 fallback 回调，并可把参数交给 `CanvasDrawingSession.DrawGlyphRun`。但已核实的微软源码提交 `25680382dd2136779e10ea6084f0c5ba437ae288` 中，[InternalDWriteTextRenderer](https://github.com/microsoft/Win2D/blob/25680382dd2136779e10ea6084f0c5ba437ae288/winrt/lib/text/InternalDWriteTextRenderer.cpp#L9)把原始 face 转成 `CanvasFontFace`；[CanvasFontFace::GetContainer](https://github.com/microsoft/Win2D/blob/25680382dd2136779e10ea6084f0c5ba437ae288/winrt/lib/text/CanvasFontFace.cpp#L97)又通过字体集合和 `GetFontFromFontFace` 建立 reference。公开 interop 对应的是 `IDWriteFontFaceReference`，不是直接暴露 callback 的原始 `IDWriteFontFace`。

因此，纯 Win2D 路径可以做可工作的生产绘制原型，但不能未经验证便声称它保留了所有 variable-font axis 实例身份。本文建议在原始 DirectWrite callback 处记录，再绘制同一个原始 run，直接避开该不确定性。所选 Win2D 包版本与 Windows App SDK 1.6 的兼容性仍须在 CI 编译／运行确认并锁定；上游源码阅读不是包兼容性测试。

**原生交互怎样保留**

自绘文字不会自动获得 `TextBlock` / `RichTextBlock` / `TextBox` 的交互和 UIA。不能把隐藏 `TextBox` 当作替身，将其独立排版所得的 caret、选择框或 UIA 范围充当新渲染表面的几何。必须明确实现以下三类真实控件：

| 范围 | 最小生产路径 | 必须保留的行为 |
|---|---|---|
| 按钮、菜单项、树行、徽章的非编辑文字 | 原来的原生交互控件 + `RelicTextView` 内容 | 保留原按钮／列表／菜单 peer、Invoke / Toggle / Selection、焦点和键盘加速器；复合行的头像、状态点、主副文字仍独立，Canvas 本身不额外暴露伪控件 |
| 聊天、文件预览、Markdown 的可选文字 | `RelicRichTextView : Control`，同一个 layout 与文档模型 | 指针拖选、双击词选择、键盘移动和 Shift 扩选、复制、上下文菜单、链接激活、代码块、引用当前选择；选择高亮和 caret 依据真实 layout 的 hit-test 结果 |
| 输入框、composer、搜索、设置字段 | `RelicTextEditor : Control` + 同一文档模型／layout + 桌面 TSF text store | 原有单／多行、换行／发送、IME composition、撤销／重做、剪切／复制／粘贴、选择、placeholder、只读／禁用、滚动、焦点、菜单和语音写入 |

可选文字需使用 `IDWriteTextLayout::HitTestPoint`、`HitTestTextPosition` 和 `HitTestTextRange` 做指针／caret／选择几何，而不是猜字宽；后者明确可返回一个范围的多个选择区域，见 [HitTestTextRange](https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritetextlayout-hittesttextrange)。移动单位必须尊重文档边界、UTF-16 cluster 和词／行规则，不能直接逐 code unit 移动导致拆开 emoji 或代理对。

UIA 通过 `OnCreateAutomationPeer` 返回真实 `FrameworkElementAutomationPeer` 子类；文本控件实现 `ITextProvider` / `ITextRangeProvider`，编辑控件还要提供恰当的 `IValueProvider`、selection、caret 和 text-edit 事件。`DocumentRange`、`RangeFromPoint`、`GetVisibleRanges`、`GetSelection`、range bounds 和文字属性都来自实际文档及当前 layout。API 适用于自定义控件，而不是把旧内置控件的 provider 转嫁过来：[WinUI 自定义 peer](https://learn.microsoft.com/en-us/windows/apps/design/accessibility/custom-automation-peers)、[ITextProvider](https://learn.microsoft.com/en-us/windows/windows-app-sdk/api/winrt/microsoft.ui.xaml.automation.provider.itextprovider?view=windows-app-sdk-1.6)。本机 1.6 XML 确有这些接口声明，但完整 peer 行为尚待实现和 CI 验证。

编辑器的桌面输入法路线应是原生 TSF，而不能直接照搬 UWP `CoreTextServicesManager.GetForCurrentView` 示例。微软当前桌面 API 支持表把 `CoreTextServicesManager` 的桌面支持限定为 Insider Preview，因此它不满足本项目的普通 Windows 桌面基线：[支持表](https://learn.microsoft.com/en-us/windows/apps/desktop/modernize/desktop-to-uwp-supported-api)。

可实施的 TSF 组件持有 `ITfThreadMgr` / `ITfDocumentMgr` / context，让实际编辑文档实现 `ITextStoreACP`。必须处理文档锁和 sink、Get/SetText、Get/SetSelection、InsertTextAtSelection、GetTextExt / GetACPFromPoint / GetScreenExt / GetWnd，焦点切换和文本／选择／布局变更通知。用 `ITfContextOwnerCompositionSink` 跟踪 composition，把候选窗口位置和 composition underline 关联到同一实际 layout；composition 期间 Enter 不能误发聊天消息。[Text store 初始化及锁协议](https://learn.microsoft.com/en-us/windows/win32/tsf/text-stores)、[ITextStoreACP 方法](https://learn.microsoft.com/en-us/windows/win32/api/textstor/nn-textstor-itextstoreacp)、[composition 生命周期](https://learn.microsoft.com/en-us/windows/win32/tsf/compositions)给出了这些接口，但它们不会替应用实现编辑器。

现有仓库确实依赖上述行为：`ContentViews.cs` 使用 `RichTextBlock.IsTextSelectionEnabled` 和 `SelectionChanged`；`Conversation.cs` 和 `MainWindow.cs` 有原生多行 `TextBox`；`DesktopSettings.cs` 中语音输入直接修改目标 `TextBox`。因此“只换画字然后保留输入功能”不是一处模板修改，需要把这些调用接到共同的真实编辑／选择接口。装饰字体、dialog 默认标签、ComboBox 弹出项和原生模板内文字也必须全部计入，否则仍会存在未测量字体。

**另一个可行但目前未验证的方向：给 WinUI 框架本身加记录**

公开 WinUI 源码确实已经持有真实 runs：[DWriteTextRenderer::DrawGlyphRun](https://github.com/microsoft/microsoft-ui-xaml/blob/0a03f68d586d1c100f753ca3221597c3ee550f4a/dxaml/xcp/core/text/TextBlock/DWriteTextRenderer.cpp#L16)复制字形数据，并直接包装传入的 face；[D2DTextDrawingContext](https://github.com/microsoft/microsoft-ui-xaml/blob/0a03f68d586d1c100f753ca3221597c3ee550f4a/dxaml/xcp/core/native/text/Common/D2DTextDrawingContext.cpp)保存并绘制这些记录。若构建并实际交付带观测的框架，理论上可以保留原生控件和其完整编辑行为。

但这不是当前 NuGet 的公开插件接口，源码 `main` 也没有被证明与项目锁定的 1.6 二进制完全对应。需要先证明可重现构建、包替换和部署，覆盖 TextBlock 快慢路径、RichTextBlock、TextBox / RichEdit、模板文字、缓存字形和颜色字体，并把缓存记录归属到实际屏幕帧。只给 `DWriteTextRenderer.cpp` 加日志不能证明所有文本都覆盖。微软自己的 [框架构建说明](https://github.com/microsoft/microsoft-ui-xaml/blob/0a03f68d586d1c100f753ca3221597c3ee550f4a/docs/building/developer-guide.md)要求完整工具链并指出单一构建约需 80 GB 空间。本轮没有克隆、构建或替换框架，也不建议未经这一步验证就采用 DLL hook、私有偏移或修改本机安装版。

**进入生产前可以明确检查的完成条件**

先在 CI 让一个真正可见的 `RelicTextView` 画混合中英文、粗细变体、emoji、组合字符、换行和省略文字；必须从实际 Draw 路径得到 face、axes、glyph positions 和截图。此原型只证明新控件可观测，不改变整套矩阵的未完成状态。随后替换所有显示／模板文本，再完成可选文字和 TSF 编辑器，最后覆盖全部 42 × 3 × 2 × 2 场景及交互状态；中途不豁免未迁移控件。

CI 应分别证明：字体回退真正发生时 callback face 改变；记录与实际绘制消费的是同一 run；layout revision 改变后旧记录失效；裁剪／省略不会把不可见源文字算作画出的文字；UIA 文本、范围、选择与截图对应；中文 IME composition 不误发送；复制／引用／超链接／语音修改仍走同一文档。字体证据缺失、未知 axes、未支持 color layer 或尚未迁移的文字都继续导致覆盖失败。还要单独检查原有 `InputBox`／`Button` 等语义和键盘操作，不能靠视觉相似代替。

这条路线能够最终产生实际 face 证据，但不保证字体、几何或像素已经与网页参考相同；实现后仍须按现有容差和全部矩阵比较。当前最可靠的决策是采用原始 DirectWrite callback 的生产渲染组件作为可验证原型，并把完整编辑器保留列为交付的必要工作。若希望尽量少改原生文本行为，则先在 CI 验证框架观测构建；两种路线都不能用独立 layout、声明字体或回退预测提前填平 `rendered_fonts`。

**生产原型进展（2026-10-30）**

`NativeLabel` 已接到四个真实菜单入口的 Button.Content，并通过无窗口的本机 Release 编译。它的同一个 `IDWriteTextLayout` 用于 Measure、Arrange 和 Draw；SurfaceImageSource 成功 EndDraw 后才保留实际 glyph callback 记录。完整 UI 字体回退顺序应用于该生产 layout，并通过 GetFontFallback 核对对象身份。原 Button 的 Name、peer、Invoke、键盘和焦点行为保留。

当前捕获只把这些原始记录放在 `native_label_evidence`。CI 尚需确认真实显示、字形数据及截图对应；`coverage_complete` 仍为 false，最终呈现帧仍未知，canonical 字体不能提前填入。全应用其余 TextBlock、RichTextBlock、输入编辑器及复杂彩色文字没有因为四个菜单入口的原型而算作完成。

现有 TextBlock 另记录实际 [IsTextTrimmed](https://learn.microsoft.com/en-us/windows/windows-app-sdk/api/winrt/microsoft.ui.xaml.controls.textblock.istexttrimmed?view=windows-app-sdk-1.6)。它能说明控件发生了截断，不能给出省略号的绘制边界；UIA 原始零面积范围、文本配置和截断状态分别保留，未知边界仍失败。
