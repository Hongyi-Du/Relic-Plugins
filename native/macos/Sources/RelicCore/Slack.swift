import Foundation

// Settings > Slack (relic_core/slack.py), as on Windows (native/windows/Relic/SlackSettings.cs): what the page says
// about the connection, each organization's choice and the members' latest reads. Everything here comes from the
// Relic App's /api/slack answers, which carry the connection only; the token never passes through this file.
public enum SlackText {
    /// Errors the service answers with as word-list keys; anything else is Slack's own text.
    public static let errorKeys: Set<String> =
        ["slack.error.bot_token", "slack.error.not_user_token", "slack.error.invalid_token", "slack.error.unreachable", "slack.error.not_connected"]
    private static let modeKeys = ["inherit": "slack.mode.inherit", "all": "slack.mode.all", "list": "slack.mode.list", "none": "slack.mode.none"]
    private static let kindKeys = ["public": "slack.kind.public", "private": "slack.kind.private", "mpim": "slack.kind.mpim", "im": "slack.kind.im"]
    private static let opKeys = ["search": "slack.op.search", "history": "slack.op.history", "thread": "slack.op.thread", "channels": "slack.op.channels"]

    public static func error(_ message: String, words: Words) -> String { errorKeys.contains(message) ? words.t(message) : message }
    // An unknown value from a newer service shows as itself rather than disappearing.
    public static func mode(_ value: String, words: Words) -> String { modeKeys[value].map { words.t($0) } ?? value }
    public static func kind(_ value: String, words: Words) -> String { kindKeys[value].map { words.t($0) } ?? value }
    public static func op(_ value: String, words: Words) -> String { opKeys[value].map { words.t($0) } ?? value }
    /// The default has nothing above it to follow.
    public static func modes(isDefault: Bool) -> [String] { isDefault ? ["all", "list", "none"] : ["inherit", "all", "list", "none"] }

    /// "Workspace · domain.slack.com", or the name alone.
    public static func workspace(_ team: Node) -> String {
        let domain = team["domain"].text
        return team["name"].text + (domain.isEmpty ? "" : " · " + domain + ".slack.com")
    }
    public static func missingScopes(_ state: Node) -> [String] { state["missing_scopes"].rows.map(\.text).filter { !$0.isEmpty } }

    /// One scope in words. A followed list is not counted: the row above shows its own count.
    public static func describe(_ scope: Node, counted: Bool = true, words: Words) -> String {
        switch scope["mode"].text {
        case "list": return counted ? words.t("slack.scope_list", ["n": String(scope["conversations"].rows.count)]) : words.t("slack.scope_list_any")
        case "none": return words.t("slack.scope_none")
        default: return scope["dms"].flag ? words.t("slack.scope_all_dms") : words.t("slack.scope_all")
        }
    }

    /// The note under a row: its own choice as the page shows it now, or what it follows and from where.
    public static func note(mode: String, dms: Bool, chosen: Int, effective: Node, source: String, sourceName: String, words: Words) -> String {
        switch mode {
        case "inherit":
            let what = describe(effective, counted: false, words: words)
            return source == "default" || sourceName.isEmpty ? words.t("slack.from_default", ["what": what])
                : words.t("slack.from_org", ["name": sourceName, "what": what])
        case "list": return words.t("slack.scope_list", ["n": String(chosen)])
        case "none": return words.t("slack.scope_none")
        default: return dms ? words.t("slack.scope_all_dms") : words.t("slack.scope_all")
        }
    }

    /// The default row (empty id) and one row per organization, in the service's order: each one after the
    /// organization above it, `depth` 0 for the default and 1 for an organization at the top.
    public struct Row: Identifiable {
        public let id: String
        public let name: String
        public let depth: Int
        public let own: Node
        public let effective: Node
        public let source: String
        public let sourceName: String
        public var isDefault: Bool { id.isEmpty }
        /// An organization without its own choice follows the one above it.
        public var mode: String { own["mode"].text.isEmpty ? "inherit" : own["mode"].text }
        public var dms: Bool { own["dms"].flag }
        public var chosen: Set<String> { Set(own["conversations"].rows.map(\.text).filter { !$0.isEmpty }) }
        /// Points the row is indented: 18 a level, at most six levels.
        public var indent: Int { min(max(depth, 0), 6) * 18 }
    }
    public static func rows(_ state: Node, defaultName: String) -> [Row] {
        var rows = [Row(id: "", name: defaultName, depth: 0, own: state["default"], effective: state["default"], source: "", sourceName: "")]
        for org in state["orgs"].rows where !org.isNull && !org["id"].text.isEmpty {
            rows.append(Row(id: org["id"].text, name: org["name"].text, depth: org["depth"].integer + 1, own: org["own"],
                            effective: org["effective"], source: org["source"].text, sourceName: org["source_name"].text))
        }
        return rows
    }

    /// A conversation the person can put on an organization's list.
    public struct Conversation: Identifiable, Equatable {
        public let id: String
        public let label: String
        public let kind: String
    }
    public static func conversations(_ answer: Node) -> [Conversation] {
        answer["conversations"].rows.filter { !$0.isNull && !$0["id"].text.isEmpty }
            .map { Conversation(id: $0["id"].text, label: $0["label"].text, kind: $0["kind"].text) }
    }
    /// The conversations whose name contains the filter (a leading # or @ is ignored), at most `limit` of them.
    public static func filter(_ conversations: [Conversation], query: String, limit: Int = 300) -> [Conversation] {
        var needle = Substring(query.trimmingCharacters(in: .whitespacesAndNewlines))
        while let first = needle.first, first == "#" || first == "@" { needle = needle.dropFirst() }
        let lowered = needle.lowercased()
        var shown: [Conversation] = []
        for item in conversations where lowered.isEmpty || item.label.lowercased().contains(lowered) {
            shown.append(item)
            if shown.count >= limit { break }
        }
        return shown
    }

    /// One of the latest reads: when, where, who, what and how much (or the error), joined with " · ".
    public static func read(_ read: Node, words: Words, timeZone: TimeZone = .current) -> String {
        var at = ""
        if let seconds = (read["at"].raw as? NSNumber)?.doubleValue ?? Double(read["at"].text) {
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.timeZone = timeZone; formatter.dateFormat = "MM-dd HH:mm"
            at = formatter.string(from: Date(timeIntervalSince1970: seconds))
        }
        let target = read["target"].text, error = read["error"].text
        let what = op(read["op"].text, words: words) + (target.isEmpty ? "" : " " + target)
        let tail = error.isEmpty ? words.t("slack.read_count", ["n": read["count"].text]) : words.t("slack.read_error", ["error": error])
        return [at, read["org_name"].text, read["member"].text, what, tail].filter { !$0.isEmpty }.joined(separator: " · ")
    }
}
