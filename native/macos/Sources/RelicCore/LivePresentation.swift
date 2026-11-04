import Foundation

/// Visible portions of the latest Hub turn, after Timeline.activeLive applies
/// the real start marker and pending permission decisions.
public struct LivePresentation {
    public let prompt: Node?
    public let reply: String
    public let actions: [Node]
    public let running: Bool
    public init(items: [Node], status: Node, member: Node) {
        prompt = member["embedded"].flag && member["has_transcript"].flag ? items.first { $0["type"].text == "prompt" } : nil
        reply = items.last { $0["type"].text == "assistant" }?["text"].text ?? ""
        actions = items.filter { ["tool", "permission", "error"].contains($0["type"].text) }
        running = status["state"].text == "running"
    }
    public var showsTyping: Bool { reply.isEmpty && running }
    public static func toolState(_ state: String, words: Words) -> String {
        let keys = ["pending": "live.pending", "in_progress": "task.working", "completed": "task.done", "failed": "common.failed"]
        return keys[state].map { words.t($0) } ?? state
    }
}
