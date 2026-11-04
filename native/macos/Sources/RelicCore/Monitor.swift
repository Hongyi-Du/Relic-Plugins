import Foundation

// The monitor and token statistics as the native panel draws them: who is working on this computer and what it
// costs (GET /api/monitor), and tokens per period by session, agent or organization (GET /api/usage). The Client
// extensions below fetch and decode on the request's own executor, so the main actor only receives finished values.

extension Node {
    /// A JSON number, or numeric text, as a Double; 0 when absent (the Windows client's Num).
    var number: Double {
        if let value = raw as? NSNumber { return value.doubleValue }
        return Double(text) ?? 0
    }
    var isObject: Bool { raw is NSDictionary || raw is [String: Any] }
}

/// Token counts as the monitor writes them: 亿/万 in Chinese, B/M/K otherwise, like the Windows client.
public enum TokenFormat {
    public static func text(_ value: Double, words: Words) -> String {
        let n = value.isFinite ? max(0, value).rounded(.toNearestOrEven) : 0
        if words.language.hasPrefix("zh") {
            if n >= 1e8 { return (n >= 1e10 ? whole(n / 1e8) : tenths(n / 1e8)) + words.t("mon.unit_1e8") }
            if n >= 1e4 { return (n >= 1e6 ? whole(n / 1e4) : tenths(n / 1e4)) + words.t("mon.unit_1e4") }
            return whole(n)
        }
        if n >= 1e9 { return tenths(n / 1e9) + "B" }
        if n >= 1e6 { return tenths(n / 1e6) + "M" }
        if n >= 1e3 { return tenths(n / 1e3) + "K" }
        return whole(n)
    }
    /// .NET's "0" format: the nearest whole number, halves away from zero.
    static func whole(_ value: Double) -> String {
        String(Int64(min(9e18, max(0, value).rounded(.toNearestOrAwayFromZero))))
    }
    /// .NET's "0.#" format: at most one decimal and no trailing zero.
    static func tenths(_ value: Double) -> String {
        let tenths = Int64(min(9e18, max(0, value * 10).rounded(.toNearestOrAwayFromZero)))
        return tenths % 10 == 0 ? String(tenths / 10) : String(tenths / 10) + "." + String(tenths % 10)
    }
}

public struct MonitorSeat: Equatable, Sendable {
    public let organization: String
    public let organizationName: String
    public let member: String
    public let autoWake: Bool
    public let organizationAutoWake: Bool
    init(_ node: Node) {
        organization = node["org"].text; organizationName = node["org_name"].text; member = node["member"].text
        autoWake = node["auto_wake"].flag; organizationAutoWake = node["org_auto_wake"].flag
    }
}

/// One Claude Code or Codex session: a Relic member's carrier, or a session without a seat.
public struct MonitorAgent: Equatable, Sendable, Identifiable {
    public enum State: String, Sendable { case working, idle, stopped, released }
    public let key: String
    public let harness: String
    public let title: String
    public let seats: [MonitorSeat]
    public let working: Bool
    /// A Stop brake is on; released: the person typed to the session since, so only its wake-ups stay off.
    public let stopped: Bool
    public let released: Bool
    public let canInterrupt: Bool
    public let lastActive: Double
    public let rate: Double
    public let subagents: Int
    public let automations: Int
    public let hour: Double
    public let fiveHours: Double
    public let day: Double
    public var id: String { key }
    public init(_ node: Node) {
        key = node["key"].text; harness = node["harness"].text; title = node["title"].text
        seats = node["seats"].rows.map(MonitorSeat.init)
        working = node["working"].flag
        let brake = node["stopped"]
        stopped = brake.isObject; released = brake["released"].flag
        canInterrupt = node["can_interrupt"].flag
        lastActive = node["last_active"].number; rate = node["rate"].number
        subagents = node["subagents"].integer; automations = node["automations"].rows.count
        let tokens = node["tokens"]
        hour = tokens["hour"]["total"].number; fiveHours = tokens["five_hours"]["total"].number; day = tokens["day"]["total"].number
    }
    public var state: State { stopped ? (released ? .released : .stopped) : working ? .working : .idle }
    /// Counted on the toolbar: working, unless a Stop brake still holds it.
    public var busy: Bool { working && !(stopped && !released) }
    public var wakeOff: Bool { seats.contains { !$0.autoWake || !$0.organizationAutoWake } }
    public var codex: Bool { harness == "codex" }
}

public struct MonitorTotals: Equatable, Sendable {
    public var hour = 0.0
    public var fiveHours = 0.0
    public var day = 0.0
    public var rate = 0.0
    public var working = 0
    public init() {}
    init(_ node: Node) {
        hour = node["hour"].number; fiveHours = node["five_hours"].number; day = node["day"].number
        rate = node["rate"].number; working = node["working"].integer
    }
}

/// A rate-limit window of the Codex plan, as Codex last reported it.
public struct MonitorPlanWindow: Equatable, Sendable {
    public let minutes: Double
    public let usedPercent: Double
    public let resetsAt: Double
}

public struct MonitorAutomation: Equatable, Sendable {
    public let id: String
    public let name: String
    public let status: String
    public let rrule: String
    public var paused: Bool { status == "PAUSED" }
}

public struct MonitorOrganization: Equatable, Sendable {
    public let id: String
    public let name: String
    public let autoWake: Bool
}

public struct MonitorSnapshot: Equatable, Sendable {
    public var at = 0.0
    public var agents: [MonitorAgent] = []
    public var others: [MonitorAgent] = []
    public var claude = MonitorTotals()
    public var codex = MonitorTotals()
    /// nil until Codex has reported its plan.
    public var codexPlan: [MonitorPlanWindow]?
    public var automations: [MonitorAutomation] = []
    public var organizations: [MonitorOrganization] = []
    public var claudeTasks = 0
    public var stoppedAll = false
    public var loaded = false
    public init() {}
    public init(_ node: Node) {
        at = node["at"].number
        agents = node["agents"].rows.map(MonitorAgent.init)
        others = node["others"].rows.map(MonitorAgent.init)
        claude = MonitorTotals(node["totals"]["claude"]); codex = MonitorTotals(node["totals"]["codex"])
        let plan = node["plans"]["codex"]
        if plan.isObject {
            codexPlan = [plan["primary"], plan["secondary"]].filter(\.isObject).map {
                MonitorPlanWindow(minutes: $0["window_minutes"].number, usedPercent: $0["used_percent"].number, resetsAt: $0["resets_at"].number)
            }
        }
        automations = node["automations"].rows.map {
            MonitorAutomation(id: $0["id"].text, name: $0["name"].text, status: $0["status"].text, rrule: $0["rrule"].text)
        }
        organizations = node["orgs"].rows.map { MonitorOrganization(id: $0["id"].text, name: $0["name"].text, autoWake: $0["auto_wake"].flag) }
        claudeTasks = node["claude_tasks"].rows.count
        stoppedAll = node["stopped_all"].isObject
        loaded = true
    }
    /// The toolbar count: sessions working now, Relic members and other sessions alike.
    public var working: Int { agents.filter(\.busy).count + others.filter(\.busy).count }
    public var anyStopped: Bool { stoppedAll || agents.contains(where: \.stopped) || others.contains(where: \.stopped) }
    public var automationsOn: Int { automations.filter { !$0.paused }.count }
}

/// The texts of the monitor's rows and cards, shared with the tests.
public enum MonitorText {
    public static func ago(_ epoch: Double, now: Double, words: Words) -> String {
        let seconds = max(0, now - epoch)
        if seconds < 60 { return words.t("time.just_now") }
        if seconds < 3600 { return words.t("time.minutes_ago", ["n": String(Int(seconds / 60))]) }
        return words.t("time.hours_ago", ["n": String(Int(seconds / 3600))])
    }
    public static func plan(_ windows: [MonitorPlanWindow], words: Words, timeZone: TimeZone = .current) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.timeZone = timeZone; formatter.dateFormat = "M/d HH:mm"
        return windows.map { window -> String in
            let name = window.minutes == 300 ? words.t("mon.window_5h") : window.minutes == 10080 ? words.t("mon.window_week")
                : words.t("mon.window_hours", ["n": String(Int((window.minutes / 60).rounded(.toNearestOrEven)))])
            let reset = window.resetsAt > 0 ? formatter.string(from: Date(timeIntervalSince1970: window.resetsAt)) : ""
            return words.t("mon.plan_used", ["window": name, "pct": String(Int(window.usedPercent.rounded(.toNearestOrEven))), "reset": reset])
        }.joined(separator: " · ")
    }
    public static func seats(_ agent: MonitorAgent) -> String {
        agent.seats.map { $0.organizationName + " · " + $0.member }.joined(separator: "   ")
    }
    public static func meta(_ agent: MonitorAgent, now: Double, words: Words) -> String {
        var parts: [String] = []
        if agent.lastActive > 0 { parts.append(words.t("mon.last_active", ["when": ago(agent.lastActive, now: now, words: words)])) }
        if agent.rate > 0 { parts.append(words.t("mon.rate", ["n": TokenFormat.text(agent.rate, words: words)])) }
        if agent.subagents > 0 { parts.append(words.t("mon.subagents", ["n": String(agent.subagents)])) }
        if agent.automations > 0 { parts.append(words.t("mon.automations", ["n": String(agent.automations)])) }
        if agent.wakeOff { parts.append(words.t("mon.wake_off")) }
        return parts.joined(separator: " · ")
    }
}

public struct UsageSeries: Equatable, Sendable {
    public let key: String
    public let label: String
    public let organization: String
    public let values: [Double]
    public let total: Double
    /// For the summed rest ("*"): how many series it holds.
    public let count: Int
    init(_ node: Node) {
        key = node["key"].text; label = node["label"].text; organization = node["org"].text
        values = node["values"].rows.map(\.number); total = node["total"]["total"].number; count = node["count"].integer
    }
}

public struct UsageChoice: Equatable, Sendable {
    public let value: String
    public let label: String
    /// An agent's organization; empty for organizations themselves.
    public let organization: String
}

public struct UsageReport: Equatable, Sendable {
    public var span = ""
    public var bucket = ""
    public var group = ""
    public var starts: [Double] = []
    public var series: [UsageSeries] = []
    public var total = 0.0
    public var organizations: [UsageChoice] = []
    public var agents: [UsageChoice] = []
    public var failed = false
    public init() {}
    public init(_ node: Node) {
        span = node["span"].text; bucket = node["bucket"].text; group = node["group"].text
        starts = node["starts"].rows.map(\.number)
        series = node["series"].rows.map(UsageSeries.init)
        total = node["total"].number
        organizations = node["filters"]["orgs"].rows.map { UsageChoice(value: $0["id"].text, label: $0["name"].text, organization: "") }
        agents = node["filters"]["agents"].rows.map { UsageChoice(value: $0["key"].text, label: $0["label"].text, organization: $0["org"].text) }
    }
    public static var failure: UsageReport { var report = UsageReport(); report.failed = true; return report }
    /// The server answered (with or without usage) or the request failed: no longer loading.
    public var answered: Bool { failed || !span.isEmpty }
    /// org "-" asks for the sessions without a seat.
    public static func path(span: String, group: String, organization: String, agent: String) -> String {
        "/api/usage?span=" + span + "&group=" + group
            + (organization.isEmpty ? "" : "&org=" + Client.segment(organization))
            + (agent.isEmpty ? "" : "&agent=" + Client.segment(agent))
    }
    /// The agents the agent filter offers under an organization filter.
    public func agents(in organization: String) -> [UsageChoice] {
        organization.isEmpty || organization == "-" ? agents : agents.filter { $0.organization == organization }
    }
}

/// The two charts: per-period stacked bars and cumulative lines for the 7 largest series plus the summed rest.
public struct UsageChart: Equatable, Sendable {
    public struct Line: Equatable, Sendable {
        public let name: String
        public let values: [Double]
        public let total: Double
        /// One of the eight series colors; the last is the gray of the summed rest.
        public let palette: Int
    }
    public static let named = 7
    public static let height: CGFloat = 210
    public static let left: CGFloat = 64
    public static let bottom: CGFloat = 22
    public static let top: CGFloat = 8
    public private(set) var labels: [String] = []
    public private(set) var lines: [Line] = []
    public private(set) var cumulative: [[Double]] = []
    public init() {}
    public init(report: UsageReport, words: Words, timeZone: TimeZone = .current) {
        guard !report.starts.isEmpty else { return }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.timeZone = timeZone
        formatter.dateFormat = report.bucket == "hour" ? "HH" : "M/d"
        labels = report.starts.map { formatter.string(from: Date(timeIntervalSince1970: $0)) }
        let count = labels.count
        func fit(_ values: [Double]) -> [Double] { (0..<count).map { $0 < values.count ? values[$0] : 0 } }
        for series in report.series.prefix(Self.named) {
            lines.append(Line(name: Self.name(series, words: words), values: fit(series.values), total: series.total, palette: lines.count))
        }
        let rest = report.series.dropFirst(Self.named)
        if !rest.isEmpty {
            var sum = [Double](repeating: 0, count: count)
            var total = 0.0, held = 0
            for series in rest {
                let values = fit(series.values)
                for index in 0..<count { sum[index] += values[index] }
                total += series.total
                held += series.key == "*" ? series.count : 1
            }
            lines.append(Line(name: words.t("mon.other_series", ["n": String(held)]), values: sum, total: total, palette: Self.named))
        }
        cumulative = lines.map { line -> [Double] in
            var running = 0.0
            return line.values.map { value -> Double in running += value; return running }
        }
    }
    /// Prepared on the caller's executor rather than the main actor.
    public static func prepare(_ report: UsageReport, words: Words) async -> UsageChart { UsageChart(report: report, words: words) }
    static func name(_ series: UsageSeries, words: Words) -> String {
        if series.key == "*" { return words.t("mon.other_series", ["n": String(series.count)]) }
        return series.label.isEmpty ? words.t("mon.unseated") : series.label
    }
    public var stackMaximum: Double {
        let sums = (0..<labels.count).map { index in lines.reduce(0.0) { $0 + $1.values[index] } }
        return max(1, sums.max() ?? 0)
    }
    public var cumulativeMaximum: Double { max(1, cumulative.map { $0.last ?? 0 }.max() ?? 0) }
    public static func plot(width: CGFloat) -> CGRect {
        CGRect(x: left, y: top, width: max(10, width - left - 6), height: height - bottom - top)
    }
    public func slot(width: CGFloat) -> CGFloat { labels.isEmpty ? 0 : Self.plot(width: width).width / CGFloat(labels.count) }
    /// Every n-th period is labeled, at most about eight labels.
    public var labelStep: Int { max(1, Int((Double(labels.count) / 8).rounded(.up))) }
    public var labeled: [Int] { Array(stride(from: 0, to: labels.count, by: labelStep)) }
    /// Each line's bars, stacked from the bottom in line order.
    public func bars(width: CGFloat) -> [[CGRect]] {
        var result = lines.map { _ in [CGRect]() }
        guard !labels.isEmpty, width > 0 else { return result }
        let plot = Self.plot(width: width), period = slot(width: width)
        let bar = max(2, min(24, period * 0.6)), maximum = CGFloat(stackMaximum)
        for index in 0..<labels.count {
            let x = plot.minX + period * CGFloat(index) + (period - bar) / 2
            var y = plot.maxY
            for (series, line) in lines.enumerated() where line.values[index] > 0 {
                let height = plot.height * CGFloat(line.values[index]) / maximum
                result[series].append(CGRect(x: x, y: y - height, width: bar, height: max(0.5, height)))
                y -= height
            }
        }
        return result
    }
    /// Each line's running total, one point at the middle of each period.
    public func points(width: CGFloat) -> [[CGPoint]] {
        guard !labels.isEmpty, width > 0 else { return lines.map { _ in [] } }
        let plot = Self.plot(width: width), period = slot(width: width), maximum = CGFloat(cumulativeMaximum)
        return cumulative.map { running -> [CGPoint] in
            running.indices.map { index -> CGPoint in
                CGPoint(x: plot.minX + period * CGFloat(index) + period / 2, y: plot.minY + plot.height * (1 - CGFloat(running[index]) / maximum))
            }
        }
    }
}

extension Client {
    /// GET /api/monitor, decoded here rather than on the caller's actor.
    public func monitorSnapshot() async throws -> MonitorSnapshot { MonitorSnapshot(try await get("/api/monitor")) }
    public func usageReport(span: String, group: String, organization: String, agent: String) async throws -> UsageReport {
        UsageReport(try await get(UsageReport.path(span: span, group: group, organization: organization, agent: agent)))
    }
}
