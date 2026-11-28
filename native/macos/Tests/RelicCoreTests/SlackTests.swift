import XCTest
import Foundation
@testable import RelicCore

/// Settings > Slack: the words the page shows, from the shipped word lists and answers shaped like relic_core/slack.py's.
final class SlackTests: XCTestCase {
    private let utc = TimeZone(identifier: "UTC")!

    private func words(_ language: String) throws -> Words {
        let mac = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let root = mac.deletingLastPathComponent().deletingLastPathComponent()
        let path = root.appendingPathComponent("plugins/relic/relic_core/locales/" + language + ".json")
        var words = Words()
        words.load(Node(["lang": language, "strings": try JSONSerialization.jsonObject(with: Data(contentsOf: path))]))
        return words
    }
    private func node(_ json: String) throws -> Node { Node(try JSONSerialization.jsonObject(with: Data(json.utf8))) }

    func testErrorsFromTheServiceAreTranslatedAndSlacksOwnTextIsKept() throws {
        let en = try words("en-US"), zh = try words("zh-CN")
        for key in SlackText.errorKeys {
            XCTAssertFalse(SlackText.error(key, words: en).isEmpty, key)
            XCTAssertNotEqual(SlackText.error(key, words: en), key)
            XCTAssertNotEqual(SlackText.error(key, words: zh), SlackText.error(key, words: en), key)
        }
        XCTAssertEqual(SlackText.error("slack.error.bot_token", words: en), "That is a bot token (xoxb-). Paste the User OAuth Token; it starts with xoxp-.")
        XCTAssertEqual(SlackText.error("Slack: ratelimited", words: en), "Slack: ratelimited")
        XCTAssertEqual(SlackText.error("HTTP 500", words: zh), "HTTP 500")
    }

    func testModesKindsAndReadsUseTheWordListsAndShowUnknownValuesAsThemselves() throws {
        let en = try words("en-US"), zh = try words("zh-CN")
        XCTAssertEqual(SlackText.modes(isDefault: true), ["all", "list", "none"])
        XCTAssertEqual(SlackText.modes(isDefault: false), ["inherit", "all", "list", "none"])
        XCTAssertEqual(SlackText.modes(isDefault: false).map { SlackText.mode($0, words: en) }, ["Follow above", "Everything", "Chosen conversations", "Nothing"])
        XCTAssertEqual(SlackText.modes(isDefault: false).map { SlackText.mode($0, words: zh) }, ["跟上级", "全部", "选定的会话", "不能读"])
        XCTAssertEqual(["public", "private", "mpim", "im"].map { SlackText.kind($0, words: zh) }, ["频道", "私有频道", "群私信", "私信"])
        XCTAssertEqual(["search", "history", "thread", "channels"].map { SlackText.op($0, words: en) },
                       ["searched", "read", "read a thread in", "listed conversations"])
        XCTAssertEqual(SlackText.mode("later", words: en), "later")
        XCTAssertEqual(SlackText.kind("huddle", words: en), "huddle")
        XCTAssertEqual(SlackText.op("files", words: en), "files")
    }

    func testRowNotesSayWhatARowMayReadOrWhatItFollows() throws {
        let en = try words("en-US"), zh = try words("zh-CN")
        let list = try node(#"{"mode": "list", "dms": false, "conversations": ["C1", "C2", "D3"]}"#)
        XCTAssertEqual(SlackText.describe(list, words: en), "3 chosen conversations")
        XCTAssertEqual(SlackText.describe(list, counted: false, words: en), "chosen conversations")
        XCTAssertEqual(SlackText.describe(try node(#"{"mode": "all", "dms": true}"#), words: en), "Every channel and DM")
        XCTAssertEqual(SlackText.describe(try node(#"{"mode": "all", "dms": false}"#), words: zh), "全部频道，不含私信")
        XCTAssertEqual(SlackText.describe(try node(#"{"mode": "none", "dms": true}"#), words: en), "Nothing")
        XCTAssertEqual(SlackText.describe(Node(NSNull()), words: en), "Every channel, no DMs")

        let all = try node(#"{"mode": "all", "dms": true}"#)
        XCTAssertEqual(SlackText.note(mode: "inherit", dms: false, chosen: 0, effective: all, source: "default", sourceName: "", words: en),
                       "From the default: Every channel and DM")
        XCTAssertEqual(SlackText.note(mode: "inherit", dms: false, chosen: 0, effective: list, source: "org_a", sourceName: "研发部", words: en),
                       "From 研发部: chosen conversations")
        XCTAssertEqual(SlackText.note(mode: "inherit", dms: false, chosen: 0, effective: list, source: "org_a", sourceName: "研发部", words: zh),
                       "跟 研发部：选定的会话")
        // A row's own choice is said from what the page shows now, not from the last answer.
        XCTAssertEqual(SlackText.note(mode: "list", dms: true, chosen: 1, effective: all, source: "", sourceName: "", words: en), "1 chosen conversation")
        XCTAssertEqual(SlackText.note(mode: "list", dms: true, chosen: 2, effective: all, source: "", sourceName: "", words: zh), "2 个选定的会话")
        XCTAssertEqual(SlackText.note(mode: "all", dms: false, chosen: 0, effective: all, source: "", sourceName: "", words: en), "Every channel, no DMs")
        XCTAssertEqual(SlackText.note(mode: "all", dms: true, chosen: 0, effective: all, source: "", sourceName: "", words: en), "Every channel and DM")
        XCTAssertEqual(SlackText.note(mode: "none", dms: true, chosen: 3, effective: all, source: "", sourceName: "", words: zh), "不能读")
    }

    func testRowsAreTheDefaultThenEachOrganizationIndentedByDepth() throws {
        let state = try node(#"""
        {"connected": false, "default": {"mode": "all", "dms": true},
         "orgs": [
          {"id": "org_a", "name": "总办", "depth": 0, "own": null, "effective": {"mode": "all", "dms": true}, "source": "default", "source_name": ""},
          {"id": "org_b", "name": "研发部", "depth": 1, "own": {"mode": "list", "dms": false, "conversations": ["C1", "C2", ""]},
           "effective": {"mode": "list", "dms": false, "conversations": ["C1", "C2"]}, "source": "org_b", "source_name": "研发部"},
          {"id": "org_c", "name": "深处", "depth": 9, "own": null, "effective": {"mode": "list", "dms": false, "conversations": ["C1", "C2"]},
           "source": "org_b", "source_name": "研发部"},
          {"id": "", "name": "broken"}
         ]}
        """#)
        let rows = SlackText.rows(state, defaultName: "Default")
        XCTAssertEqual(rows.map(\.id), ["", "org_a", "org_b", "org_c"])
        XCTAssertEqual(rows.map(\.name), ["Default", "总办", "研发部", "深处"])
        XCTAssertEqual(rows.map(\.depth), [0, 1, 2, 10])
        XCTAssertEqual(rows.map(\.indent), [0, 18, 36, 108])
        XCTAssertEqual(rows.map(\.isDefault), [true, false, false, false])
        XCTAssertEqual(rows.map(\.mode), ["all", "inherit", "list", "inherit"])
        XCTAssertEqual(rows.map(\.dms), [true, false, false, false])
        XCTAssertEqual(rows[2].chosen, ["C1", "C2"])
        XCTAssertEqual(rows[3].source, "org_b")
        XCTAssertEqual(rows[3].sourceName, "研发部")
        XCTAssertEqual(rows[3].effective["mode"].text, "list")
    }

    func testConversationsFilterIgnoresALeadingHashOrAtAndShowsAtMostThreeHundred() throws {
        let answer = try node(##"""
        {"conversations": [{"id": "C1", "kind": "public", "label": "#general"}, {"id": "G2", "kind": "private", "label": "#Design-Review"},
                           {"id": "D3", "kind": "im", "label": "@alice"}, {"id": "", "kind": "public", "label": "#nothing"}]}
        """##)
        let all = SlackText.conversations(answer)
        XCTAssertEqual(all.map(\.id), ["C1", "G2", "D3"])
        XCTAssertEqual(all[1], SlackText.Conversation(id: "G2", label: "#Design-Review", kind: "private"))
        XCTAssertEqual(SlackText.filter(all, query: "").map(\.id), ["C1", "G2", "D3"])
        XCTAssertEqual(SlackText.filter(all, query: "  #design ").map(\.id), ["G2"])
        XCTAssertEqual(SlackText.filter(all, query: "@ALI").map(\.id), ["D3"])
        XCTAssertEqual(SlackText.filter(all, query: "#").map(\.id), ["C1", "G2", "D3"])
        XCTAssertTrue(SlackText.filter(all, query: "random").isEmpty)
        let many = (0..<450).map { SlackText.Conversation(id: "C\($0)", label: "#room-\($0)", kind: "public") }
        XCTAssertEqual(SlackText.filter(many, query: "room").count, 300)
        XCTAssertEqual(SlackText.filter(many, query: "room-44").map(\.id), ["C44"] + (440..<450).map { "C\($0)" })
    }

    func testReadsSayWhenWhereWhoWhatAndHowMuch() throws {
        let en = try words("en-US"), zh = try words("zh-CN")
        let read = try node(##"{"at": 1793900000.5, "org": "org_b", "org_name": "研发部", "member": "lead", "op": "history", "target": "#general", "count": 12, "error": ""}"##)
        XCTAssertEqual(SlackText.read(read, words: en, timeZone: utc), "11-05 17:33 · 研发部 · lead · read #general · 12 messages")
        XCTAssertEqual(SlackText.read(read, words: zh, timeZone: utc), "11-05 17:33 · 研发部 · lead · 读了 #general · 12 条")
        let one = try node(#"{"at": 1793900000, "org_name": "总办", "member": "chief", "op": "search", "target": "release", "count": 1}"#)
        XCTAssertEqual(SlackText.read(one, words: en, timeZone: utc), "11-05 17:33 · 总办 · chief · searched release · 1 message")
        let failed = try node(#"{"at": 1793900000, "org_name": "", "member": "chief", "op": "channels", "target": "", "count": null, "error": "ratelimited"}"#)
        XCTAssertEqual(SlackText.read(failed, words: en, timeZone: utc), "11-05 17:33 · chief · listed conversations · error: ratelimited")
        XCTAssertEqual(SlackText.read(failed, words: zh, timeZone: utc), "11-05 17:33 · chief · 列出会话 · 出错：ratelimited")
        let undated = try node(##"{"member": "chief", "op": "thread", "target": "#general", "count": 3}"##)
        XCTAssertEqual(SlackText.read(undated, words: en, timeZone: utc), "chief · read a thread in #general · 3 messages")
    }

    func testTheConnectionShowsTheWorkspaceAndTheMissingPermissions() throws {
        XCTAssertEqual(SlackText.workspace(try node(#"{"name": "Acme", "domain": "acme"}"#)), "Acme · acme.slack.com")
        XCTAssertEqual(SlackText.workspace(try node(#"{"name": "Acme", "domain": ""}"#)), "Acme")
        XCTAssertEqual(SlackText.missingScopes(try node(#"{"missing_scopes": ["search:read.im", "", "users:read"]}"#)), ["search:read.im", "users:read"])
        XCTAssertEqual(SlackText.missingScopes(try node(#"{"missing_scopes": []}"#)), [])
    }
}
