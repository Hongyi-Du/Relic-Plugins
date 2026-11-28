import XCTest
@testable import Relic

@MainActor final class MessageCaptureEvidenceTests: XCTestCase {
    func testMessageReceiptPreservesIndependentPaintAndPointerObservations() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let path = directory.appendingPathComponent("elements.json")
        let evidence: [String: Any] = [
            "native_pointer_hit": ["status": "incomplete-hit-chain", "hit": "actual-object"],
            "native_fill_draws": [["owner": "actual-fill", "current": false]],
            "native_layer_order": ["errors": ["unmeasured-native-layer"]]]
        let document: [String: Any] = ["capture_evidence": evidence,
            "elements": [["id": "actual-element"]], "extraction_errors": [["type": "prior-error"]]]
        try JSONSerialization.data(withJSONObject: document).write(to: path)
        let session = MessageCaptureSession(model: Model(), messageID: "actual-message", copying: false,
            action: ["status": "observed"], path: directory.appendingPathComponent("receipt.json"))
        try session.annotateElements(path)
        let actual = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: path)) as? [String: Any])
        let appended = try XCTUnwrap(actual["capture_evidence"] as? [String: Any])
        for (key, value) in evidence {
            XCTAssertEqual(try JSONSerialization.data(withJSONObject: XCTUnwrap(appended[key]), options: [.sortedKeys]),
                           try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]), key)
        }
        XCTAssertEqual((appended["message_action"] as? [String: Any])?["continuity_status"] as? String, "not-started")
        XCTAssertEqual((actual["elements"] as? [[String: String]])?.first?["id"], "actual-element")
        XCTAssertEqual((actual["extraction_errors"] as? [[String: String]])?.first?["type"], "prior-error")
    }
}
