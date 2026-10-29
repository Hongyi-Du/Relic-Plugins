import Foundation

public struct ToolActivity {
    public let call: Node?
    public var result: Node?
    public var failed: Bool { result?["error"].flag == true }
    public var title: String { Self.toolName(call?["tool"].text ?? "") }
    public var argument: String {
        var text = call?["text"].text ?? result?["text"].text ?? ""
        if let data = text.data(using: .utf8), let raw = try? JSONSerialization.jsonObject(with: data) {
            let args = Node(raw)
            if let key = ["command", "cmd", "file_path", "pattern", "url", "query", "description", "prompt", "path", "body"].first(where: { !args[$0].text.isEmpty }) { text = args[key].text }
        }
        return String(text.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression).prefix(120))
    }
    public static func toolName(_ name: String) -> String {
        for prefix in ["mcp__plugin_relic_org__", "mcp__relic_org__"] { if name.hasPrefix(prefix) { return "Relic " + name.dropFirst(prefix.count) } }
        return name.hasPrefix("mcp__") ? String(name.dropFirst(5)) : name
    }
    public static func pair(_ steps: [Node]) -> [ToolActivity] {
        var rows: [ToolActivity] = [], waiting: [Int] = []
        for step in steps {
            if step["role"].text == "tool_call" { waiting.append(rows.count); rows.append(ToolActivity(call: step, result: nil)) }
            else if !waiting.isEmpty { rows[waiting.removeFirst()].result = step }
            else { rows.append(ToolActivity(call: nil, result: step)) }
        }
        return rows
    }
}
