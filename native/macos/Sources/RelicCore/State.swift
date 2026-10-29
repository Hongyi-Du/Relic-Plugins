import Foundation

// Streaming bytes preserve SSE frame boundaries, UTF-8 and multiline data.
public struct EventDecoder {
    private var line = Data()
    private var fields: [String] = []
    private var carriageReturn = false
    public init() {}
    public mutating func append(_ byte: UInt8) -> Node? {
        if byte == 10 && carriageReturn { carriageReturn = false; return nil }
        carriageReturn = byte == 13
        guard byte == 10 || byte == 13 else { line.append(byte); return nil }
        let text = String(decoding: line, as: UTF8.self); line.removeAll(keepingCapacity: true)
        if text.isEmpty {
            defer { fields.removeAll(keepingCapacity: true) }
            guard !fields.isEmpty, let value = try? JSONSerialization.jsonObject(with: Data(fields.joined(separator: "\n").utf8)) else { return nil }
            return Node(value)
        }
        if text.hasPrefix("data:") {
            let data = String(text.dropFirst(5)); fields.append(data.hasPrefix(" ") ? String(data.dropFirst()) : data)
        }
        return nil
    }
}

final class LoopbackDelegate: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
}

public struct ChatSelection: Hashable, Codable {
    public var org: String
    public var member: String
    public init(_ org: String = "", _ member: String = "") { self.org = org; self.member = member }
    public var key: String { org + "/" + member }
    public func path(_ suffix: String = "") -> String { Client.org(org, suffix) }
}

public struct ChatDraft: Codable, Equatable {
    public var text = ""
    public var quote = ""
    public var recipients = ["all"]
    public init() {}
}

public struct NavigationHistory {
    public private(set) var items: [ChatSelection] = []
    public private(set) var index = -1
    public init() {}
    public var canBack: Bool { index > 0 }
    public var canForward: Bool { index + 1 < items.count }
    public mutating func visit(_ selection: ChatSelection) {
        if items.indices.contains(index), items[index] == selection { return }
        items = Array(items.prefix(index + 1)); items.append(selection); index = items.count - 1
    }
    public mutating func move(_ delta: Int) -> ChatSelection? {
        guard items.indices.contains(index + delta) else { return nil }; index += delta; return items[index]
    }
}

public enum Tree {
    public static func descendants(_ id: String, in nodes: [Node]) -> Set<String> {
        var found: Set<String> = [id], queue = [id]
        while let next = queue.popLast() {
            for node in nodes where node["parent"].text == next {
                let key = node["id"].text
                if found.insert(key).inserted { queue.append(key) }
            }
        }
        return found
    }
    public static func toggle(_ id: String, folded: inout Set<String>) {
        if !folded.insert(id).inserted { folded.remove(id) }
    }
}

public enum Timeline {
    public static func date(_ node: Node) -> Date? {
        if let numeric = node.raw as? NSNumber { return Date(timeIntervalSince1970: numeric.doubleValue) }
        let iso = ISO8601DateFormatter(); iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = iso.date(from: node.text) { return date }
        iso.formatOptions = [.withInternetDateTime]; return iso.date(from: node.text)
    }
    public static func activeLive(_ items: [Node], status: Node, decisions: [Node]) -> [Node] {
        let sorted = items.sorted { $0["seq"].integer < $1["seq"].integer }
        if ["running", "waiting", "starting"].contains(status["state"].text) { return Array(sorted.suffix(from: sorted.lastIndex(where: { $0["start"].flag }) ?? 0)) }
        return sorted.filter { item in item["type"].text == "permission" && decisions.contains { $0["kind"].text == "permission" && $0["id"].text == item["id"].text } }
    }
    public static func conversation(steps: [Node], chat: [Node], member: Node, live: [Node], words: Words) -> [Node] {
        let name = member["name"].text, start = live.last(where: { $0["start"].flag }).flatMap { date($0["at"]) }
        var items: [Node] = [], actions: [Node] = []
        func flush() { if !actions.isEmpty { items.append(Node(["type": "acts", "steps": actions.map(\.raw), "member": name, "at": actions[0]["at"].raw])); actions = [] } }
        for step in steps {
            if let start, let at = date(step["at"]), at >= start { continue }
            let role = step["role"].text
            if ["tool_call", "tool_result"].contains(role) { actions.append(step); continue }
            flush(); var text = step["text"].text
            var from = role == "user" ? "human" : name, label = ""
            guard ["user", "assistant"].contains(role) else { continue }
            if role == "user" {
                let prefix = "[Relic App] The person (human) writes to you directly:"
                if text.hasPrefix(prefix) { text = String(text.dropFirst(prefix.count)); text = text.components(separatedBy: "\n\nReply in this conversation;")[0].trimmingCharacters(in: .whitespacesAndNewlines) }
                else if text.hasPrefix("[Relic auto-wake]") { items.append(Node(["type": "notice", "at": step["at"].raw, "text": words.t("msg.auto_woken")])); continue }
                else if text.hasPrefix("You now hold the seat") { items.append(Node(["type": "notice", "at": step["at"].raw, "text": words.t("msg.seat_briefing")])); continue }
                else if !member["agent"].text.isEmpty { from = member["parent"].text.isEmpty ? name : member["parent"].text; label = words.t("msg.task_from", ["name": member["parent"].text.isEmpty ? words.t("msg.parent_session") : member["parent"].text]) }
            }
            items.append(Node(["type": "message", "from": from, "fromLabel": label, "to": [role == "user" ? name : "human"], "body": text, "at": step["at"].raw]))
        }
        flush()
        if !member["embedded"].flag || steps.isEmpty && live.isEmpty { items += chat }
        return items.enumerated().sorted { a, b in
            let first = date(a.element["at"]) ?? .distantPast, second = date(b.element["at"]) ?? .distantPast
            return first == second ? a.offset < b.offset : first < second
        }.map(\.element)
    }
    public static func merge(_ current: [Node], _ incoming: [Node]) -> [Node] {
        var result = current
        for item in incoming {
            if let index = result.firstIndex(where: { old in
                (!item["seq"].isNull && item["seq"].text == old["seq"].text) ||
                (!item["id"].isNull && item["id"].text == old["id"].text)
            }) { result[index] = Node(result[index].object.merging(item.object) { _, new in new }) }
            else { result.append(item) }
        }
        return result
    }
}

public enum Capabilities {
    public static func automatic(_ platform: Node, harness: String, surface: String) -> Bool {
        if harness == "chatgpt" { return platform["chatgpt_delivery"].flag }
        guard ["gui", "desktop"].contains(surface) else { return true }
        return platform[harness == "codex" ? "codex_desktop_wake" : "claude_desktop_wake"].flag
    }
    public static func hostKinds(_ platform: Node) -> [String] {
        ["claude-code/cli", "claude-code/gui", "codex/cli", "codex/gui"].filter {
            let parts = $0.split(separator: "/").map(String.init)
            return automatic(platform, harness: parts[0], surface: parts[1])
        }
    }
}
