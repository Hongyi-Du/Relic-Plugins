import SwiftUI
import RelicCore
import Observation

// The monitor (toolbar): who is working on this computer and what it costs, from the Relic App's /api/monitor; Stop
// and Resume for one session or all of them; and the token statistics by session, agent or organization from
// /api/usage, drawn as per-period stacked bars and cumulative lines with plain SwiftUI paths.

/// The toolbar observes only `working`. The panel's data is read while the panel is open; requests and their JSON
/// decoding run on the request's executor, and only the finished values are applied on the main actor.
@Observable @MainActor final class MonitorState {
    private(set) var working = 0
    private(set) var snapshot = MonitorSnapshot()
    private(set) var report = UsageReport()
    private(set) var chart = UsageChart()
    private(set) var stopAllArmed = false
    var span = "7d"
    var group = "agent"
    var organization = ""
    var agent = ""
    @ObservationIgnored private var readAt: ContinuousClock.Instant?
    @ObservationIgnored private var reading = false
    @ObservationIgnored private var readAgain = false
    @ObservationIgnored private var usageRequest = 0
    @ObservationIgnored private var disarmTask: Task<Void, Never>?

    /// The toolbar count follows the refreshes that already run while members work, at most every 15 s. An idle
    /// app reads nothing; an older Relic App without the monitor leaves the button quiet.
    func tick(_ client: Client?) {
        guard let client else { return }
        if let readAt, readAt.duration(to: ContinuousClock.now) < .seconds(15) { return }
        read(client)
    }
    func read(_ client: Client) {
        if reading { readAgain = true; return }
        reading = true; readAt = ContinuousClock.now
        Task { [weak self] in
            let result = try? await client.monitorSnapshot()
            guard let self else { return }
            self.reading = false
            if let result {
                if self.working != result.working { self.working = result.working }
                if self.snapshot != result { self.snapshot = result }
            }
            if self.readAgain { self.readAgain = false; self.read(client) }
        }
    }
    func readUsage(_ client: Client, words: Words) {
        usageRequest += 1
        let request = usageRequest, span = self.span, group = self.group, organization = self.organization, agent = self.agent
        Task { [weak self] in
            let report = (try? await client.usageReport(span: span, group: group, organization: organization, agent: agent)) ?? .failure
            let chart = await UsageChart.prepare(report, words: words)
            guard let self, request == self.usageRequest else { return }
            self.report = report; self.chart = chart
        }
    }
    func filter(_ model: Model, _ change: () -> Void) {
        change()
        if let client = model.client { readUsage(client, words: model.words) }
    }

    func stop(_ key: String, model: Model) {
        model.run {
            let result = try await model.post("/api/monitor/stop", ["key": key])
            model.notice = model.t("mon.stopped_one", ["killed": String(result["killed"].rows.count),
                "wake": String(result["wake_off"].rows.count), "autos": String(result["paused"].object.count)])
            if let client = model.client { self.read(client) }
        }
    }
    func resume(_ key: String, model: Model) {
        model.run {
            try await model.post("/api/monitor/resume", ["key": key])
            model.notice = model.t("mon.resumed")
            if let client = model.client { self.read(client) }
        }
    }
    /// The first click arms Stop all for four seconds; the second one stops everything.
    func stopAll(model: Model) {
        guard stopAllArmed else {
            stopAllArmed = true
            disarmTask?.cancel()
            disarmTask = Task { [weak self] in
                try? await Task.sleep(for: .seconds(4))
                guard !Task.isCancelled else { return }
                self?.stopAllArmed = false
            }
            return
        }
        disarm()
        model.run {
            let result = try await model.post("/api/monitor/stop", ["all": true])
            model.notice = model.t("mon.stopped_all", ["n": String(result["stopped"].rows.count),
                "orgs": String(result["orgs"].rows.count), "autos": String(result["paused"].rows.count)])
            if let client = model.client { self.read(client) }
        }
    }
    func resumeAll(model: Model) {
        model.run {
            try await model.post("/api/monitor/resume", ["all": true])
            model.notice = model.t("mon.resumed_all")
            if let client = model.client { self.read(client) }
        }
    }
    func disarm() {
        disarmTask?.cancel(); disarmTask = nil
        if stopAllArmed { stopAllArmed = false }
    }
}

enum MonitorPalette {
    static let series: [Color] = [
        RelicStyle.color(0x2A78D6, 0x3987E5), RelicStyle.color(0xEB6834, 0xD95926), RelicStyle.color(0x1BAF7A, 0x199E70),
        RelicStyle.color(0xEDA100, 0xC98500), RelicStyle.color(0xE87BA4, 0xD55181), RelicStyle.color(0x008300, 0x008300),
        RelicStyle.color(0x6250D6, 0x9085E9), RelicStyle.color(0x8F8C86, 0x8A877F)
    ]
    static let working = RelicStyle.color(0x1E8E3E, 0x4CC26A)
    static let stopped = RelicStyle.color(0xC9372C, 0xE66767)
    static let released = RelicStyle.color(0xB26A00, 0xE0A030)
    static let idle = RelicStyle.color(0xB4B2A9, 0x5F5E5A)
    static func color(_ index: Int) -> Color { series[max(0, min(series.count - 1, index))] }
}

private struct MonitorQuiet: View {
    let text: String
    var size: CGFloat = 12
    init(_ text: String, size: CGFloat = 12) { self.text = text; self.size = size }
    var body: some View {
        PlainLabel(text, size: size, color: RelicStyle.muted).fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct MonitorHeading: View {
    let text: String
    var size: CGFloat = 14
    init(_ text: String, size: CGFloat = 14) { self.text = text; self.size = size }
    var body: some View {
        PlainLabel(text, size: size, weight: 600).fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct MonitorPanel: View {
    @EnvironmentObject var m: Model
    var body: some View {
        let monitor = m.monitor
        VStack(alignment: .leading, spacing: 18) {
            HStack(spacing: 8) {
                PlainLabel(m.t("mon.title"), size: 18, weight: 600).lineLimit(1)
                Spacer(minLength: 0)
                IconButton(title: m.t("common.close"), icon: "x") { m.sheet = nil }
            }
            MonitorLive(monitor: monitor)
            MonitorUsage(monitor: monitor)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .task {
            // Reads every 5 s while the panel is open; the task ends with the panel.
            guard let client = m.client else { return }
            monitor.read(client)
            monitor.readUsage(client, words: m.words)
            while !Task.isCancelled {
                do { try await Task.sleep(for: .seconds(5)) } catch { return }
                if let client = m.client { monitor.read(client) }
            }
        }
        .onDisappear { monitor.disarm() }
    }
}

// ---------------- who is working ----------------
private struct MonitorLive: View {
    @EnvironmentObject var m: Model
    let monitor: MonitorState
    var body: some View {
        let snapshot = monitor.snapshot
        VStack(alignment: .leading, spacing: 10) {
            MonitorQuiet(m.t("mon.intro"), size: 12.5)
            HStack(alignment: .top, spacing: 12) {
                MonitorTotalCard(name: "Claude", totals: snapshot.claude, plan: nil, claude: true)
                MonitorTotalCard(name: "Codex", totals: snapshot.codex, plan: snapshot.codexPlan, claude: false)
            }
            HStack(spacing: 8) {
                ReferenceActionButton(m.t(monitor.stopAllArmed ? "mon.stop_all_sure" : "mon.stop_all"), small: true) { monitor.stopAll(model: m) }
                if snapshot.anyStopped {
                    ReferenceActionButton(m.t("mon.resume_all"), small: true) { monitor.resumeAll(model: m) }
                }
            }
            MonitorHeading(m.t("mon.relic_agents"))
            if !snapshot.loaded { MonitorQuiet(m.t("common.loading")) }
            else if snapshot.agents.isEmpty { MonitorQuiet(m.t("mon.no_agents")) }
            ForEach(snapshot.agents) { agent in MonitorRow(agent: agent, now: snapshot.at, monitor: monitor) }
            if !snapshot.others.isEmpty {
                MonitorHeading(m.t("mon.other_sessions"))
                MonitorQuiet(m.t("mon.other_hint"))
                ForEach(snapshot.others) { agent in MonitorRow(agent: agent, now: snapshot.at, monitor: monitor) }
            }
            MonitorSchedules(snapshot: snapshot)
        }
    }
}

private struct MonitorTotalCard: View {
    @EnvironmentObject var m: Model
    let name: String
    let totals: MonitorTotals
    let plan: [MonitorPlanWindow]?
    let claude: Bool
    private func tokens(_ value: Double) -> String { TokenFormat.text(value, words: m.words) }
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                PlainLabel(name, size: 14, weight: 600)
                Spacer(minLength: 0)
                PlainLabel(totals.working > 0 ? m.t("mon.n_working", ["n": String(totals.working)]) : m.t("mon.none_working"), size: 12, color: RelicStyle.muted).lineLimit(1)
            }
            PlainLabel(tokens(totals.fiveHours), size: 22, weight: 600).lineLimit(1)
            MonitorQuiet(m.t("mon.in_five_hours"))
            MonitorQuiet(m.t("mon.hour_day", ["hour": tokens(totals.hour), "day": tokens(totals.day)])
                + (totals.rate > 0 ? " · " + m.t("mon.rate", ["n": tokens(totals.rate)]) : ""))
            if let plan {
                let line = MonitorText.plan(plan, words: m.words)
                if !line.isEmpty { MonitorQuiet(line) }
            } else if claude {
                MonitorQuiet(m.t("mon.claude_plan_hint"))
            }
        }
        .padding(12).frame(maxWidth: .infinity, alignment: .topLeading)
        .background(RoundedRectangle(cornerRadius: 10).fill(RelicStyle.card))
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(RelicStyle.line, lineWidth: 1))
    }
}

private struct MonitorRow: View {
    @EnvironmentObject var m: Model
    let agent: MonitorAgent
    let now: Double
    let monitor: MonitorState
    private var stateText: String {
        switch agent.state {
        case .working: return m.t("mon.state_working")
        case .stopped: return m.t("mon.state_stopped")
        case .released: return m.t("mon.state_released")
        case .idle: return m.t("mon.state_idle")
        }
    }
    private var dot: Color {
        switch agent.state {
        case .working: return MonitorPalette.working
        case .stopped: return MonitorPalette.stopped
        case .released: return MonitorPalette.released
        case .idle: return MonitorPalette.idle
        }
    }
    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 8) {
                    PlainLabel(agent.title, size: 13.5, weight: 600).lineLimit(1).truncationMode(.tail).help(agent.title)
                    PlainLabel(agent.codex ? "Codex" : "Claude", size: 11, color: RelicStyle.secondary, lineHeight: 15).lineLimit(1).fixedSize()
                        .padding(.horizontal, 6).padding(.vertical, 2).background(RoundedRectangle(cornerRadius: 5).fill(RelicStyle.bubble))
                    PlainLabel(stateText, size: 12, color: RelicStyle.muted).lineLimit(1).fixedSize()
                }
                if !agent.seats.isEmpty { MonitorQuiet(MonitorText.seats(agent)) }
                let meta = MonitorText.meta(agent, now: now, words: m.words)
                if !meta.isEmpty { MonitorQuiet(meta) }
                if agent.state == .working && !agent.canInterrupt { MonitorQuiet(m.t("mon.codex_note")) }
                if agent.state == .stopped { MonitorQuiet(m.t("mon.stopped_note")) }
            }
            .padding(.leading, 21)
            .overlay(alignment: .topLeading) { Circle().fill(dot).frame(width: 9, height: 9).padding(.top, 7) }
            .frame(maxWidth: .infinity, alignment: .leading)
            HStack(spacing: 14) {
                MonitorTokenCell(caption: m.t("mon.span_hour"), value: TokenFormat.text(agent.hour, words: m.words))
                MonitorTokenCell(caption: m.t("mon.span_five_hours"), value: TokenFormat.text(agent.fiveHours, words: m.words))
                MonitorTokenCell(caption: m.t("mon.span_day"), value: TokenFormat.text(agent.day, words: m.words))
            }.fixedSize()
            if agent.stopped {
                ReferenceActionButton(m.t("mon.resume"), small: true) { monitor.resume(agent.key, model: m) }.fixedSize()
            } else {
                ReferenceActionButton(m.t("mon.stop"), small: true) { monitor.stop(agent.key, model: m) }.fixedSize()
            }
        }
        .padding(.horizontal, 10).padding(.vertical, 8)
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(agent.state == .working ? RelicStyle.accent : RelicStyle.line, lineWidth: 1))
    }
}

private struct MonitorTokenCell: View {
    let caption: String
    let value: String
    var body: some View {
        VStack(alignment: .trailing, spacing: 0) {
            PlainLabel(caption, size: 11, color: RelicStyle.muted).lineLimit(1)
            PlainLabel(value, size: 13, weight: 600).lineLimit(1)
        }
    }
}

private struct MonitorSchedules: View {
    @EnvironmentObject var m: Model
    let snapshot: MonitorSnapshot
    var body: some View {
        let awake = snapshot.organizations.filter(\.autoWake).map(\.name)
        let asleep = snapshot.organizations.filter { !$0.autoWake }.map(\.name)
        VStack(alignment: .leading, spacing: 10) {
            MonitorHeading(m.t("mon.schedules"))
            MonitorQuiet(m.t("mon.schedules_hint"))
            PlainLabel(m.t("mon.codex_automations", ["on": String(snapshot.automationsOn), "n": String(snapshot.automations.count)]), size: 13)
                .fixedSize(horizontal: false, vertical: true)
            ForEach(Array(snapshot.automations.enumerated()), id: \.offset) { _, automation in
                MonitorQuiet((automation.paused ? m.t("mon.paused") : m.t("mon.active")) + " · " + automation.name + " · " + automation.rrule)
            }
            if !awake.isEmpty { MonitorQuiet(m.t("mon.org_wake_on", ["names": m.list(awake)])) }
            if !asleep.isEmpty { MonitorQuiet(m.t("mon.org_wake_off", ["names": m.list(asleep)])) }
            if snapshot.claudeTasks > 0 { MonitorQuiet(m.t("mon.claude_tasks", ["n": String(snapshot.claudeTasks)])) }
        }
    }
}

// ---------------- token statistics ----------------
private struct MonitorUsage: View {
    @EnvironmentObject var m: Model
    let monitor: MonitorState
    private func tokens(_ value: Double) -> String { TokenFormat.text(value, words: m.words) }
    private func choice(_ title: String, _ value: String, _ options: [(String, String)], set: @escaping (String) -> Void) -> some View {
        let selection = Binding<String>(get: { value }, set: { next in
            if next != value { monitor.filter(m) { set(next) } }
        })
        return ReferenceSelectField(title: title, selection: selection, options: options, pointSize: 12.5)
    }
    private var spans: [(String, String)] {
        [("today", m.t("mon.span_today")), ("24h", m.t("mon.span_24h")), ("7d", m.t("mon.span_7d")),
         ("30d", m.t("mon.span_30d")), ("90d", m.t("mon.span_90d"))]
    }
    private var groups: [(String, String)] {
        [("session", m.t("mon.by_session")), ("agent", m.t("mon.by_agent")), ("org", m.t("mon.by_org"))]
    }
    private func organizations(_ report: UsageReport) -> [(String, String)] {
        var options: [(String, String)] = [("", m.t("mon.all_orgs"))]
        for choice in report.organizations { options.append((choice.value, choice.label)) }
        options.append(("-", m.t("mon.unseated")))
        return options
    }
    private func agents(_ report: UsageReport) -> [(String, String)] {
        var options: [(String, String)] = [("", m.t("mon.all_agents"))]
        for choice in report.agents(in: monitor.organization) { options.append((choice.value, choice.label)) }
        return options
    }
    var body: some View {
        let report = monitor.report, chart = monitor.chart
        VStack(alignment: .leading, spacing: 10) {
            MonitorHeading(m.t("mon.usage"), size: 16)
            HStack(spacing: 8) {
                choice(m.t("mon.filter_span"), monitor.span, spans) { monitor.span = $0 }.frame(width: 130)
                choice(m.t("mon.filter_group"), monitor.group, groups) { monitor.group = $0 }.frame(width: 150)
                choice(m.t("mon.filter_org"), monitor.organization, organizations(report)) { monitor.organization = $0; monitor.agent = "" }
                    .frame(minWidth: 120, maxWidth: 240)
                choice(m.t("mon.filter_agent"), monitor.agent, agents(report)) { monitor.agent = $0 }
                    .frame(minWidth: 120, maxWidth: 240)
            }
            if chart.labels.isEmpty {
                MonitorQuiet(report.answered ? m.t("mon.usage_none") : m.t("common.loading"))
            } else {
                PlainLabel(m.t("mon.usage_total", ["n": tokens(report.total)]), size: 13).fixedSize(horizontal: false, vertical: true)
                MonitorQuiet(m.t("mon.chart_bars"))
                UsageChartView(chart: chart, cumulative: false, format: tokens).accessibilityLabel(m.t("mon.chart_bars"))
                MonitorQuiet(m.t("mon.chart_lines"))
                UsageChartView(chart: chart, cumulative: true, format: tokens).accessibilityLabel(m.t("mon.chart_lines"))
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(Array(chart.lines.enumerated()), id: \.offset) { _, line in
                        HStack(spacing: 8) {
                            RoundedRectangle(cornerRadius: 2).fill(MonitorPalette.color(line.palette)).frame(width: 10, height: 10)
                            PlainLabel(line.name + "  " + tokens(line.total), size: 12.5).lineLimit(1)
                        }
                    }
                }
            }
        }
    }
}

/// Plain SwiftUI paths: one filled path per series for the stacked bars, one stroked path per series for the
/// cumulative lines (every other one dashed), three grid lines and at most about eight period labels.
private struct UsageChartView: View {
    let chart: UsageChart
    let cumulative: Bool
    let format: (Double) -> String
    private func axisText(_ text: String) -> some View {
        Text(verbatim: text).font(RelicStyle.font(11, weight: 400)).foregroundStyle(RelicStyle.muted).lineLimit(1)
    }
    var body: some View {
        GeometryReader { proxy in
            let width = proxy.size.width
            let plot = UsageChart.plot(width: width)
            let maximum = cumulative ? chart.cumulativeMaximum : chart.stackMaximum
            let period = chart.slot(width: width)
            let fractions: [CGFloat] = [0, 0.5, 1]
            ZStack(alignment: .topLeading) {
                Path { path in
                    for fraction in fractions {
                        let y = plot.minY + plot.height * (1 - fraction)
                        path.move(to: CGPoint(x: plot.minX, y: y)); path.addLine(to: CGPoint(x: plot.maxX, y: y))
                    }
                }.stroke(RelicStyle.line, lineWidth: 1)
                ForEach(fractions, id: \.self) { fraction in
                    axisText(format(maximum * Double(fraction))).frame(width: UsageChart.left - 8, alignment: .trailing)
                        .position(x: (UsageChart.left - 8) / 2, y: plot.minY + plot.height * (1 - fraction))
                }
                if cumulative {
                    let points = chart.points(width: width)
                    ForEach(points.indices, id: \.self) { series in
                        Path { path in path.addLines(points[series]) }
                            .stroke(MonitorPalette.color(chart.lines[series].palette),
                                    style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round, dash: series % 2 == 1 ? [5, 3] : []))
                    }
                } else {
                    let bars = chart.bars(width: width)
                    ForEach(bars.indices, id: \.self) { series in
                        Path { path in path.addRects(bars[series]) }.fill(MonitorPalette.color(chart.lines[series].palette))
                    }
                }
                ForEach(chart.labeled, id: \.self) { index in
                    axisText(chart.labels[index]).frame(width: max(period * CGFloat(chart.labelStep), 32))
                        .position(x: plot.minX + period * CGFloat(index) + period / 2, y: plot.maxY + 11)
                }
            }
        }
        .frame(height: UsageChart.height)
        .accessibilityElement(children: .ignore)
    }
}
