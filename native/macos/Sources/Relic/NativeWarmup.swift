import SwiftUI
import RelicCore

/// Shown, invisibly, only while the first organization loads. Creating one
/// native List row with a label and a selectable passage moves AppKit's
/// one-time table, TextKit and font setup into launch, instead of blocking
/// the first chat that appears after the data arrives.
///
/// The next rows are a notice, an activity group and one message of every
/// block kind (heading, emphasis, inline code and a link, a list, a quote,
/// a code block and a table) with its Markdown already parsed, so all are
/// built in the same launch transaction. The first chat's first rows were
/// otherwise the first such views the process ever created: CI runners
/// spent 170-530 ms in one such row's display turn at startup, against
/// under 50 ms for the same rows once warm.
struct NativeWarmup: View {
    private static let sample: (item: Node, body: PreparedMarkdown) = {
        let text = """
        # 原生界面准备 Preparing the native interface
        启动时先建一条示例消息，含**强调**、`inline code` 和[链接](https://example.invalid/relic)。 Rows, text and tables warm up here.

        - 列表第一项 First item
        - 列表第二项 Second item

        > 引用的说明 A quoted note.

        ```swift
        let ready = true
        ```

        | 项目 | 结果 |
        | --- | --- |
        | 窗口 | 准备中 |
        """
        let item = Node(["id": "relic-warmup", "type": "message", "from": "relic-warmup", "to": ["human"],
                         "at": "2026-01-01T09:30:00Z", "body": text] as [String: Any])
        return (item, PreparedMarkdown(parsing: text))
    }()
    private static let notice = Node(["id": "relic-warmup-notice", "type": "notice", "at": "2026-01-01T09:30:00Z",
                                      "text": "示例提示 Preparing a notice"] as [String: Any])
    private static let activity = Node(["id": "relic-warmup-acts", "type": "acts", "at": "2026-01-01T09:30:00Z",
                                        "member": "relic-warmup", "steps": [Any]()] as [String: Any])
    var body: some View {
        List {
            ReferenceLabel("Relic 组织 Organization", size: 13.3, weight: 600)
            SelectableText(value: AttributedString("原生界面准备中。 Preparing native text."), pointSize: 14, lineHeight: 23.1)
            MessageView(item: Self.notice)
            MessageView(item: Self.activity)
            MessageView(item: Self.sample.item, preparedBody: Self.sample.body)
        }
        .listStyle(.plain)
        // Tall enough that the table creates every row, the message's too.
        .frame(width: 360, height: 640)
        .opacity(0)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}
