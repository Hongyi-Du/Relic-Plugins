import Foundation
import XCTest
@testable import RelicCore

final class VocabularyTests: XCTestCase {
    func testEveryNativeLiteralKeyExistsInBothServerWordLists() throws {
        let mac = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let root = mac.deletingLastPathComponent().deletingLastPathComponent()
        let languages = try ["en-US", "zh-CN"].map { language -> [String: Any] in
            let path = root.appendingPathComponent("plugins/relic/relic_core/locales/" + language + ".json")
            return try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: path)) as? [String: Any])
        }
        let prefixes = Set(languages.flatMap { $0.keys.map { String($0.split(separator: ".")[0]) } })
        // Includes choices/ternaries and data-driven menu labels, not only t("literal").
        let quoted = try NSRegularExpression(pattern: #""([a-z][a-z_]*\.[a-z][a-z0-9_.]*)""#)
        let direct = try NSRegularExpression(pattern: #"\bt\("([a-z][a-z0-9_.]*)""#)
        let files = try XCTUnwrap(FileManager.default.enumerator(at: mac.appendingPathComponent("Sources"), includingPropertiesForKeys: nil))
        var used: Set<String> = ["composer.voice_title"]
        for case let path as URL in files where path.pathExtension == "swift" {
            let raw = try String(contentsOf: path, encoding: .utf8)
            let source = raw.replacingOccurrences(of: #"(?:systemName|icon|forKey):\s*"[^"]*""#, with: "", options: .regularExpression)
            let range = NSRange(source.startIndex..., in: source)
            for regex in [quoted, direct] {
                for match in regex.matches(in: source, range: range) {
                    let key = (source as NSString).substring(with: match.range(at: 1))
                    if !key.hasSuffix("."), !key.hasSuffix("_"), regex === direct || prefixes.contains(String(key.split(separator: ".")[0])) { used.insert(key) }
                }
            }
        }
        XCTAssertGreaterThan(used.count, 400)
        for (index, words) in languages.enumerated() {
            for key in used.sorted() { XCTAssertNotNil(words[key], "Missing \(["en-US", "zh-CN"][index]) key: \(key)") }
        }
    }
    func testUnloadedOrMissingVocabularyNeverDisplaysRawKey() {
        var words = Words()
        XCTAssertEqual(words.t("composer.voice_title"), "")
        words.load(Node(["lang": "en-US", "strings": ["common.voice_input": "Voice input"]]))
        XCTAssertEqual(words.t("untranslated.key"), "")
        XCTAssertEqual(words.t("common.voice_input"), "Voice input")
    }
}
