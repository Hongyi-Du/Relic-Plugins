import Foundation

// Speech results contain the whole current transcription, including interim text.
// Keep the original selection so each update replaces it without accumulating words.
public struct DictationInsertion {
    private let before: String
    private let after: String
    public init(text: String, selection: NSRange? = nil) {
        let source = text as NSString
        let range: NSRange
        if let selection, selection.location <= source.length,
           selection.length <= source.length - selection.location,
           Range(selection, in: text) != nil { range = selection }
        else { range = NSRange(location: source.length, length: 0) }
        before = source.substring(to: range.location)
        after = source.substring(from: range.location + range.length)
    }
    public func applying(_ transcription: String) -> (text: String, caret: Int) {
        (before + transcription + after, (before + transcription).utf16.count)
    }
}

public struct NodeRow: Identifiable {
    public let id: String
    public let node: Node
    public static func identify(_ nodes: [Node]) -> [NodeRow] {
        var occurrences: [String: Int] = [:]
        return nodes.map { node in
            let key: String
            if let field = ["id", "seq", "key", "name", "path", "i"].first(where: { !node[$0].isNull && !node[$0].text.isEmpty }) { key = field + ":" + node[field].text }
            else if !node["at"].isNull { key = [node["type"].text, node["role"].text, node["member"].text, node["from"].text, node["at"].text].joined(separator: "|") }
            else { key = node.text }
            let occurrence = occurrences[key, default: 0]; occurrences[key] = occurrence + 1
            return NodeRow(id: key + "#" + String(occurrence), node: node)
        }
    }
}

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
    public var quoteAuthor: String? = nil
    public var quoteText: String? = nil
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
    private final class DateParsers {
        let fractional = ISO8601DateFormatter(), seconds = ISO8601DateFormatter()
        init() { fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]; seconds.formatOptions = [.withInternetDateTime] }
    }
    public static func date(_ node: Node) -> Date? {
        if let numeric = node.raw as? NSNumber { return Date(timeIntervalSince1970: numeric.doubleValue) }
        // Formatters are expensive to initialize and are never shared across
        // threads. Reuse one pair per worker instead of creating two per row.
        let key = "Relic.Timeline.DateParsers"
        let parsers: DateParsers
        if let existing = Thread.current.threadDictionary[key] as? DateParsers { parsers = existing }
        else { parsers = DateParsers(); Thread.current.threadDictionary[key] = parsers }
        return parsers.fractional.date(from: node.text) ?? parsers.seconds.date(from: node.text)
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
        var dated: [(index: Int, item: Node, at: Date)] = []
        dated.reserveCapacity(items.count)
        for (index, item) in items.enumerated() { dated.append((index: index, item: item, at: date(item["at"]) ?? Date.distantPast)) }
        dated.sort { left, right in left.at == right.at ? left.index < right.index : left.at < right.at }
        return dated.map { $0.item }
    }
    public static func mergeInBackground(_ current: [Node], _ incoming: [Node]) async -> [Node] { merge(current, incoming) }
    public static func merge(_ current: [Node], _ incoming: [Node]) -> [Node] {
        var result = current
        var sequences: [String: Set<Int>] = [:], ids: [String: Set<Int>] = [:]
        func index(_ node: Node, _ position: Int, remove: Bool = false) {
            if !node["seq"].isNull {
                if remove { sequences[node["seq"].text]?.remove(position) }
                else { sequences[node["seq"].text, default: []].insert(position) }
            }
            if !node["id"].isNull {
                if remove { ids[node["id"].text]?.remove(position) }
                else { ids[node["id"].text, default: []].insert(position) }
            }
        }
        for (position, node) in result.enumerated() { index(node, position) }
        for item in incoming {
            let bySequence = item["seq"].isNull ? nil : sequences[item["seq"].text]?.min()
            let byID = item["id"].isNull ? nil : ids[item["id"].text]?.min()
            if let position = [bySequence, byID].compactMap({ $0 }).min() {
                index(result[position], position, remove: true)
                result[position] = Node(result[position].object.merging(item.object) { _, new in new })
                index(result[position], position)
            } else { index(item, result.count); result.append(item) }
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
