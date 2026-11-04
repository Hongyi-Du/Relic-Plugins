import Foundation
import XCTest
@testable import Relic
import RelicCore

@MainActor final class ConversationTimestampTests: XCTestCase {
    private func model(_ language: String) -> Model {
        let defaults = UserDefaults(suiteName: "ConversationTimestampTests." + UUID().uuidString)!
        let model = Model(defaults: defaults)
        model.words.load(Node(["lang": language, "strings": [
            "time.today": language == "zh-CN" ? "今天" : "Today",
            "time.yesterday": language == "zh-CN" ? "昨天" : "Yesterday"
        ]]))
        return model
    }

    private func message(_ at: String, id: Int = 1) -> Node {
        Node(["id": id, "type": "message", "from": "analyst", "body": "A message", "at": at])
    }

    func testPreparedTimestampMatchesExistingPresentationInBothLanguagesAndTimeZones() throws {
        let now = try XCTUnwrap(Timeline.date(Node("2026-11-02T00:30:00Z")))
        let timestamps = ["2026-11-02T00:10:00Z", "2026-11-01T06:30:00Z",
                          "2026-11-01T07:30:00Z", "2026-10-20T12:00:00Z",
                          "2025-10-20T12:00:00Z", "invalid"]
        for language in ["en-US", "zh-CN"] {
            let model = model(language)
            for zone in ["UTC", "America/Chicago", "Asia/Shanghai"] {
                var calendar = Calendar(identifier: .gregorian)
                calendar.timeZone = try XCTUnwrap(TimeZone(identifier: zone))
                let rows = ConversationRow.build(timestamps.enumerated().map { message($0.element, id: $0.offset) },
                    words: model.words, now: now, calendar: calendar)
                for (row, at) in zip(rows, timestamps) {
                    let clock = model.clock(Node(at), calendar: calendar)
                    let tooltip = model.day(Node(at), now: now, calendar: calendar) + " " + clock
                    XCTAssertEqual(row.clockLabel, clock, "\(language), \(zone), \(at)")
                    XCTAssertEqual(row.dayTooltip, tooltip, "\(language), \(zone), \(at)")
                }
            }
        }
    }

    func testPreparedDateChangesAtLocalMidnightAndOnLanguageChange() throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "America/Chicago"))
        let at = "2026-10-29T04:59:00Z" // October 28, 23:59 in Chicago.
        let before = try XCTUnwrap(Timeline.date(Node("2026-10-29T04:59:30Z")))
        let after = try XCTUnwrap(Timeline.date(Node("2026-10-29T05:00:00Z")))
        for language in ["en-US", "zh-CN"] {
            let model = model(language)
            let initial = try XCTUnwrap(ConversationRow.build([message(at)], words: model.words,
                now: before, calendar: calendar).first)
            let nextDay = try XCTUnwrap(ConversationRow.build([message(at)], words: model.words,
                now: after, calendar: calendar).first)
            XCTAssertEqual(initial.clockLabel, "23:59")
            XCTAssertEqual(initial.dayTooltip, model.t("time.today") + " 23:59")
            XCTAssertEqual(nextDay.clockLabel, initial.clockLabel)
            XCTAssertEqual(nextDay.dayTooltip, model.t("time.yesterday") + " 23:59")
            XCTAssertNotEqual(initial.dayTooltip, nextDay.dayTooltip)
        }
    }

    func testRepeatedSidebarDatesKeepLocaleTimeZoneAndRelativeDayChanges() throws {
        let at = try XCTUnwrap(Timeline.date(Node("2026-10-29T00:30:00Z")))
        let node = Node("2026-10-29T00:30:00Z")
        for _ in 0..<2 {
            for language in ["zh-CN", "en-US"] {
                let model = model(language)
                for zone in ["UTC", "America/Chicago", "Asia/Shanghai"] {
                    var calendar = Calendar(identifier: .gregorian)
                    calendar.timeZone = try XCTUnwrap(TimeZone(identifier: zone))
                    let clock = DateFormatter(); clock.locale = Locale(identifier: "en_US_POSIX")
                    clock.timeZone = calendar.timeZone; clock.dateFormat = "HH:mm"
                    XCTAssertEqual(model.shortWhen(node, now: at, calendar: calendar), clock.string(from: at))
                    XCTAssertEqual(model.shortWhen(node, now: calendar.date(byAdding: .day, value: 1, to: at), calendar: calendar), model.t("time.yesterday"))
                    let short = DateFormatter(); short.locale = Locale(identifier: model.words.language)
                    short.timeZone = calendar.timeZone; short.setLocalizedDateFormatFromTemplate("Md")
                    XCTAssertEqual(model.shortWhen(node, now: calendar.date(byAdding: .day, value: 10, to: at), calendar: calendar), short.string(from: at))
                }
            }
        }
    }

    func testSameMessageIdentityRecomputesChangedTimestampAndTimeZone() throws {
        let model = model("en-US")
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "UTC"))
        let now = try XCTUnwrap(Timeline.date(Node("2026-10-29T12:00:00Z")))
        let initial = try XCTUnwrap(ConversationRow.build([message("2026-10-29T00:15:00Z")],
            words: model.words, now: now, calendar: calendar).first)
        let edited = try XCTUnwrap(ConversationRow.build([message("2026-10-28T23:45:00Z")],
            words: model.words, now: now, calendar: calendar).first)
        XCTAssertEqual(initial.id, edited.id)
        XCTAssertEqual(initial.dayTooltip, "Today 00:15")
        XCTAssertEqual(edited.dayTooltip, "Yesterday 23:45")
        calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "Asia/Shanghai"))
        let moved = try XCTUnwrap(ConversationRow.build([edited.item], words: model.words,
            now: now, calendar: calendar).first)
        XCTAssertEqual(moved.id, edited.id)
        XCTAssertEqual(moved.dayTooltip, "Today 07:45")
    }

    func testInvalidTimestampsKeepExistingEmptyClockAndTooltipSpacing() throws {
        let model = model("en-US")
        let rows = ConversationRow.build([message("invalid"), Node(["id": 2, "type": "message"])],
            words: model.words, now: Date())
        for row in rows {
            XCTAssertEqual(row.clockLabel, "")
            XCTAssertEqual(row.dayTooltip, " ")
            XCTAssertNil(row.separator)
        }
        let manual = ConversationRow(id: "manual", item: message("2026-10-29T00:15:00Z"),
            separator: nil, continued: false)
        XCTAssertNil(manual.clockLabel, "Direct callers retain MessageView's formatting fallback")
        XCTAssertNil(manual.dayTooltip)
        XCTAssertNil(manual.timestampContext)
    }

    func testPreparedContextExpiresOnLocalDayLanguageAndSystemTimeZoneChanges() throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "America/Chicago"))
        let now = try XCTUnwrap(Timeline.date(Node("2026-11-01T05:30:00Z")))
        let context = ConversationTimestampContext(language: "en-US", now: now, calendar: calendar)
        XCTAssertEqual(context.dayEnd.timeIntervalSince(context.dayStart), 25 * 3600,
            "The DST transition day must expire at the next local midnight, not after 24 hours")
        XCTAssertTrue(context.isCurrent(language: "en-US", now: now, calendar: calendar))
        XCTAssertTrue(context.isCurrent(language: "en-US", now: context.dayEnd.addingTimeInterval(-1), calendar: calendar))
        XCTAssertFalse(context.isCurrent(language: "en-US", now: context.dayEnd, calendar: calendar))
        XCTAssertFalse(context.isCurrent(language: "en-US", now: context.dayStart.addingTimeInterval(-1), calendar: calendar))
        XCTAssertFalse(context.isCurrent(language: "zh-CN", now: now, calendar: calendar))
        calendar.timeZone = try XCTUnwrap(TimeZone(identifier: "Asia/Shanghai"))
        XCTAssertFalse(context.isCurrent(language: "en-US", now: now, calendar: calendar))
    }

    func testAsyncConversationAndThreadPreparationCarryTimestampLabels() async throws {
        let model = model("zh-CN")
        let now = try XCTUnwrap(Timeline.date(Node("2026-10-29T12:00:00Z")))
        let items = [message("2026-10-29T10:15:00Z"), message("2025-10-20T12:00:00Z", id: 2)]
        let chat = await ConversationRow.prepare(messages: items, steps: [], member: Node(), live: [],
            status: Node(), decisions: [], words: model.words, now: now, privateChat: false)
        let replies = await ConversationRow.prepareReplies(items, words: model.words, now: now)
        for rows in [chat, replies] {
            XCTAssertEqual(rows.count, items.count)
            for row in rows {
                let clock = model.clock(row.item["at"])
                XCTAssertEqual(row.clockLabel, clock)
                XCTAssertEqual(row.dayTooltip, model.day(row.item["at"], now: now) + " " + clock)
                XCTAssertTrue(row.timestampContext?.isCurrent(language: model.words.language, now: now) ?? false)
            }
        }
        XCTAssertTrue(replies.allSatisfy { $0.separator == nil })
    }
}
