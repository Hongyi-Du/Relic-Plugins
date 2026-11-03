import XCTest
import Foundation
@testable import RelicCore

final class MonitorTests: XCTestCase {
    private let utc = TimeZone(identifier: "UTC")!

    /// The shipped word lists, so the 亿/万 units and plural forms are the real ones.
    private func words(_ language: String) throws -> Words {
        let mac = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let root = mac.deletingLastPathComponent().deletingLastPathComponent()
        let path = root.appendingPathComponent("plugins/relic/relic_core/locales/" + language + ".json")
        var words = Words()
        words.load(Node(["lang": language, "strings": try JSONSerialization.jsonObject(with: Data(contentsOf: path))]))
        return words
    }
    private func node(_ json: String) throws -> Node { Node(try JSONSerialization.jsonObject(with: Data(json.utf8))) }
    private func assertClose(_ actual: [CGPoint], _ expected: [CGPoint], file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertEqual(actual.count, expected.count, file: file, line: line)
        for (a, e) in zip(actual, expected) {
            XCTAssertEqual(a.x, e.x, accuracy: 0.001, file: file, line: line); XCTAssertEqual(a.y, e.y, accuracy: 0.001, file: file, line: line)
        }
    }
    private func assertClose(_ actual: [CGRect], _ expected: [CGRect], file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertEqual(actual.count, expected.count, file: file, line: line)
        for (a, e) in zip(actual, expected) {
            for (x, y) in [(a.minX, e.minX), (a.minY, e.minY), (a.width, e.width), (a.height, e.height)] {
                XCTAssertEqual(x, y, accuracy: 0.001, file: file, line: line)
            }
        }
    }

    func testSnapshotDecodesSessionsTotalsPlanAndWhatStartsAgents() throws {
        let snapshot = MonitorSnapshot(try node(#"""
        {"at": 1793900000.5,
         "agents": [
          {"key": "c1", "harness": "claude-code", "title": "研发部 · lead", "working": true, "reason": "active",
           "seats": [{"org": "org_a", "org_name": "研发部", "member": "lead", "auto_wake": true, "org_auto_wake": false, "running": false}],
           "last_active": 1793899880, "rate": 1250, "subagents": 2,
           "tokens": {"hour": {"total": 12000, "fresh": 1}, "five_hours": {"total": 56000}, "day": {"total": 340000}},
           "stopped": null, "can_stop": true, "can_interrupt": true, "automations": []},
          {"key": "codex:t1", "harness": "codex", "title": "Codex 定时", "working": true, "seats": [],
           "last_active": null, "rate": 0, "subagents": 0,
           "tokens": {"hour": {"total": 0}, "five_hours": {"total": 0}, "day": {"total": 0}},
           "stopped": {"at": 1793899000, "released": false}, "can_stop": true, "can_interrupt": false, "automations": ["a1", "a2"]}],
         "others": [
          {"key": "s9", "harness": "claude-code", "title": "my session", "working": true, "seats": [],
           "last_active": 1793899990, "rate": 0, "subagents": 0,
           "tokens": {"hour": {"total": 5}, "five_hours": {"total": 5}, "day": {"total": 5}},
           "stopped": {"at": 1793899000, "released": true}, "can_stop": true, "can_interrupt": true, "automations": []}],
         "totals": {"claude": {"hour": 12005, "five_hours": 56005, "day": 340005, "rate": 1250, "working": 2},
                    "codex": {"hour": 0, "five_hours": 0, "day": 0, "rate": 0, "working": 1}},
         "scanning": false,
         "plans": {"codex": {"primary": {"used_percent": 38.4, "window_minutes": 300, "resets_at": 1794199750},
                             "secondary": {"used_percent": 12.6, "window_minutes": 10080, "resets_at": 0}, "observed_at": 1}},
         "automations": [{"id": "a1", "name": "Nightly", "kind": "cron", "status": "ACTIVE", "rrule": "FREQ=DAILY", "target": "t1"},
                         {"id": "a2", "name": "Weekly", "kind": "cron", "status": "PAUSED", "rrule": "FREQ=WEEKLY", "target": "t1"}],
         "claude_tasks": [{"id": "x", "description": "d"}],
         "orgs": [{"id": "org_a", "name": "研发部", "auto_wake": false}, {"id": "org_b", "name": "学业部", "auto_wake": true}],
         "stopped_all": null}
        """#))
        XCTAssertTrue(snapshot.loaded)
        XCTAssertEqual(snapshot.at, 1793900000.5)
        XCTAssertEqual(snapshot.agents.map(\.key), ["c1", "codex:t1"])
        let lead = snapshot.agents[0]
        XCTAssertEqual(lead.state, .working); XCTAssertTrue(lead.busy); XCTAssertTrue(lead.wakeOff); XCTAssertFalse(lead.codex)
        XCTAssertEqual(lead.hour, 12000); XCTAssertEqual(lead.fiveHours, 56000); XCTAssertEqual(lead.day, 340000)
        XCTAssertEqual(lead.rate, 1250); XCTAssertEqual(lead.subagents, 2); XCTAssertEqual(lead.lastActive, 1793899880)
        XCTAssertEqual(lead.seats.map(\.organizationName), ["研发部"]); XCTAssertEqual(lead.seats.first?.member, "lead")
        let codex = snapshot.agents[1]
        XCTAssertEqual(codex.state, .stopped); XCTAssertFalse(codex.busy); XCTAssertTrue(codex.codex); XCTAssertFalse(codex.canInterrupt)
        XCTAssertEqual(codex.automations, 2); XCTAssertEqual(codex.lastActive, 0); XCTAssertFalse(codex.wakeOff)
        // A released brake no longer holds the session: it counts as working again, like the Windows toolbar.
        XCTAssertEqual(snapshot.others.first?.state, .released); XCTAssertEqual(snapshot.others.first?.busy, true)
        XCTAssertEqual(snapshot.working, 2)
        XCTAssertTrue(snapshot.anyStopped); XCTAssertFalse(snapshot.stoppedAll)
        XCTAssertEqual(snapshot.claude.fiveHours, 56005); XCTAssertEqual(snapshot.claude.rate, 1250)
        XCTAssertEqual(snapshot.claude.working, 2); XCTAssertEqual(snapshot.codex.working, 1)
        XCTAssertEqual(snapshot.codexPlan, [MonitorPlanWindow(minutes: 300, usedPercent: 38.4, resetsAt: 1794199750),
                                           MonitorPlanWindow(minutes: 10080, usedPercent: 12.6, resetsAt: 0)])
        XCTAssertEqual(snapshot.automations.map(\.name), ["Nightly", "Weekly"]); XCTAssertTrue(snapshot.automations[1].paused)
        XCTAssertEqual(snapshot.automationsOn, 1)
        XCTAssertEqual(snapshot.claudeTasks, 1)
        XCTAssertEqual(snapshot.organizations.map(\.autoWake), [false, true])
    }

    func testStopAllRecordAndMissingFieldsDecodeQuietly() throws {
        let stopped = MonitorSnapshot(try node(#"{"agents": [], "others": [], "plans": {"codex": null}, "stopped_all": {"orgs": ["org_a"], "paused": {}, "at": 1}}"#))
        XCTAssertTrue(stopped.stoppedAll); XCTAssertTrue(stopped.anyStopped); XCTAssertNil(stopped.codexPlan); XCTAssertEqual(stopped.working, 0)
        let older = MonitorSnapshot(try node("{}"))
        XCTAssertTrue(older.loaded); XCTAssertFalse(older.anyStopped); XCTAssertNil(older.codexPlan)
        XCTAssertEqual(older.claude, MonitorTotals()); XCTAssertTrue(older.agents.isEmpty)
        XCTAssertFalse(MonitorSnapshot().loaded)
    }

    func testTokensUseWanAndYiInChineseAndKMBOtherwise() throws {
        let en = try words("en-US"), zh = try words("zh-CN")
        let english: [(Double, String)] = [(-5, "0"), (0, "0"), (999, "999"), (999.4, "999"), (1000, "1K"), (1500, "1.5K"),
            (12_345, "12.3K"), (999_949, "999.9K"), (1_000_000, "1M"), (2_345_678, "2.3M"), (1_000_000_000, "1B"), (12_340_000_000, "12.3B")]
        for (value, text) in english { XCTAssertEqual(TokenFormat.text(value, words: en), text, "\(value)") }
        let chinese: [(Double, String)] = [(9_999, "9999"), (10_000, "1万"), (15_000, "1.5万"), (123_456, "12.3万"),
            (1_234_567, "123万"), (123_456_789, "1.2亿"), (20_000_000_000, "200亿")]
        for (value, text) in chinese { XCTAssertEqual(TokenFormat.text(value, words: zh), text, "\(value)") }
        XCTAssertEqual(TokenFormat.text(.infinity, words: en), "0")
    }

    func testRowsAndCardsReadLikeTheWindowsMonitor() throws {
        let en = try words("en-US"), zh = try words("zh-CN")
        let windows = [MonitorPlanWindow(minutes: 300, usedPercent: 38.4, resetsAt: 1794199750), MonitorPlanWindow(minutes: 120, usedPercent: 12.6, resetsAt: 0)]
        XCTAssertEqual(MonitorText.plan(windows, words: en, timeZone: utc),
                       "5-hour limit: 38% used, resets 11/9 04:49 · 2-hour limit: 13% used, resets ")
        XCTAssertEqual(MonitorText.plan([windows[0]], words: zh, timeZone: utc), "5 小时额度已用 38%，11/9 04:49 重置")
        XCTAssertEqual(MonitorText.ago(1000, now: 1030, words: en), "just now")
        XCTAssertEqual(MonitorText.ago(1000, now: 1125, words: en), "2 minutes ago")
        XCTAssertEqual(MonitorText.ago(1000, now: 4700, words: en), "1 hour ago")
        XCTAssertEqual(MonitorText.ago(1000, now: 4700, words: zh), "1 小时前")
        let agent = MonitorAgent(try node(#"""
        {"key": "c1", "harness": "claude-code", "title": "lead", "working": true,
         "seats": [{"org": "org_a", "org_name": "研发部", "member": "lead", "auto_wake": false, "org_auto_wake": true},
                   {"org": "org_b", "org_name": "学业部", "member": "lead", "auto_wake": true, "org_auto_wake": true}],
         "last_active": 10000, "rate": 1250, "subagents": 1, "automations": ["a1", "a2"], "stopped": null}
        """#))
        XCTAssertEqual(MonitorText.meta(agent, now: 10_150, words: en),
                       "last active 2 minutes ago · about 1.3K/min · 1 subagent working · 2 Codex automations start it · Wake-ups off")
        XCTAssertEqual(MonitorText.meta(agent, now: 10_150, words: zh),
                       "最后活动：2 分钟前 · 约 1250/分钟 · 1 个子代理在工作 · 2 个 Codex 定时任务会唤醒它 · 自动唤醒已关")
        XCTAssertEqual(MonitorText.seats(agent), "研发部 · lead   学业部 · lead")
    }

    func testUsageKeepsSevenNamedSeriesAndSumsTheRestIntoOne() throws {
        let en = try words("en-US"), zh = try words("zh-CN")
        var series: [String] = []
        for index in 0..<8 {
            let label = index == 1 ? "" : "研发部 · m\(index)"
            series.append("{\"key\": \"org_a/m\(index)\", \"label\": \"\(label)\", \"org\": \"org_a\", \"kinds\": [\"claude\"], \"values\": [\(index), 1, 0], \"total\": {\"total\": \(100 - index), \"fresh\": 0}, \"cumulative\": []}")
        }
        series.append(#"{"key": "*", "label": null, "org": null, "kinds": [], "values": [10, 0], "total": {"total": 7}, "count": 3}"#)
        let json = [#"{"span": "7d", "bucket": "day", "group": "agent", "from": 1793836800, "to": 1794009700, "#,
                    #""starts": [1793836800, 1793923200, 1794009600], "series": ["#, series.joined(separator: ", "), #"], "#,
                    #""totals": [], "cumulative": [], "total": 820, "scanning": false, "plans": {"codex": null}, "#,
                    #""filters": {"orgs": [{"id": "org_a", "name": "研发部"}, {"id": "org_b", "name": "学业部"}], "#,
                    #""agents": [{"key": "org_a/m0", "label": "研发部 · m0", "org": "org_a"}, {"key": "org_b/x", "label": "学业部 · x", "org": "org_b"}]}}"#].joined()
        let report = UsageReport(try node(json))
        XCTAssertTrue(report.answered); XCTAssertEqual(report.series.count, 9); XCTAssertEqual(report.total, 820)
        XCTAssertEqual(report.series[8].count, 3); XCTAssertEqual(report.series[2].total, 98)
        XCTAssertEqual(report.organizations.map(\.value), ["org_a", "org_b"])
        XCTAssertEqual(report.agents(in: "org_b").map(\.value), ["org_b/x"])
        XCTAssertEqual(report.agents(in: "-").count, 2); XCTAssertEqual(report.agents(in: "").count, 2)

        let chart = UsageChart(report: report, words: en, timeZone: utc)
        XCTAssertEqual(chart.labels, ["11/5", "11/6", "11/7"])
        XCTAssertEqual(chart.lines.count, 8)
        XCTAssertEqual(chart.lines[0].name, "研发部 · m0")
        XCTAssertEqual(chart.lines[1].name, "Sessions without a seat")
        XCTAssertEqual(chart.lines.map(\.palette), Array(0...7))
        XCTAssertEqual(chart.lines[2].values, [2, 1, 0]); XCTAssertEqual(chart.cumulative[2], [2, 3, 3])
        // The eighth series and the three the server already summed share one gray series.
        let rest = chart.lines[7]
        XCTAssertEqual(rest.name, "4 others"); XCTAssertEqual(rest.values, [17, 1, 0]); XCTAssertEqual(rest.total, 100)
        XCTAssertEqual(chart.stackMaximum, 38)
        XCTAssertEqual(chart.cumulativeMaximum, 18)
        XCTAssertEqual(UsageChart(report: report, words: zh, timeZone: utc).lines[7].name, "其他 4 个")

        var hourly = report; hourly.bucket = "hour"; hourly.starts = [1793836800, 1793840400]
        XCTAssertEqual(UsageChart(report: hourly, words: en, timeZone: utc).labels, ["00", "01"])
        XCTAssertTrue(UsageChart(report: UsageReport(), words: en).lines.isEmpty)
    }

    func testChartGeometryStacksBarsFromTheBottomAndPlacesRunningTotals() throws {
        let report = UsageReport(try node(#"""
        {"span": "24h", "bucket": "hour", "starts": [1793836800, 1793840400], "total": 60,
         "series": [{"key": "a", "label": "A", "values": [10, 0], "total": {"total": 10}},
                    {"key": "b", "label": "B", "values": [30, 20], "total": {"total": 50}}]}
        """#))
        let chart = UsageChart(report: report, words: try words("en-US"), timeZone: utc)
        XCTAssertEqual(UsageChart.plot(width: 470), CGRect(x: 64, y: 8, width: 400, height: 180))
        XCTAssertEqual(chart.slot(width: 470), 200)
        let bars = chart.bars(width: 470)
        assertClose(bars[0], [CGRect(x: 152, y: 143, width: 24, height: 45)])
        assertClose(bars[1], [CGRect(x: 152, y: 8, width: 24, height: 135), CGRect(x: 352, y: 98, width: 24, height: 90)])
        let points = chart.points(width: 470)
        assertClose(points[0], [CGPoint(x: 164, y: 152), CGPoint(x: 364, y: 152)])
        assertClose(points[1], [CGPoint(x: 164, y: 80), CGPoint(x: 364, y: 8)])
        XCTAssertEqual(chart.labeled, [0, 1])
        XCTAssertTrue(UsageChart().bars(width: 470).isEmpty)
        XCTAssertEqual(chart.bars(width: 0).map(\.count), [0, 0])
    }

    func testUsagePathCarriesTheFiltersAndAsksForSessionsWithoutASeat() {
        XCTAssertEqual(UsageReport.path(span: "7d", group: "agent", organization: "", agent: ""), "/api/usage?span=7d&group=agent")
        XCTAssertEqual(UsageReport.path(span: "24h", group: "session", organization: "-", agent: "org_a/lead"),
                       "/api/usage?span=24h&group=session&org=%2D&agent=org%5Fa%2Flead")
        XCTAssertFalse(UsageReport().answered); XCTAssertTrue(UsageReport.failure.answered)
        XCTAssertTrue(UsageChart(report: .failure, words: Words()).labels.isEmpty)
    }

    func testMonitorDialogIsWideEnoughForTheTokenColumns() {
        let layout = DialogGeometry(kind: "monitor", window: CGSize(width: 1280, height: 800))
        XCTAssertEqual(layout.width, 900); XCTAssertNil(layout.height)
        XCTAssertEqual(DialogGeometry(kind: "monitor", window: CGSize(width: 700, height: 500)).width, 668)
    }
}
