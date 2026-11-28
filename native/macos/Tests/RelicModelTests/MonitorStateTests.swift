import XCTest
import Foundation
import Observation
@testable import Relic
import RelicCore

/// Answers every request from `reply(path)` and records "METHOD path?query body" for each one.
private final class MonitorTransport: URLProtocol {
    private static let lock = NSLock()
    private static var seen: [String] = []
    private static var reply: (String) -> String = { _ in "{}" }
    static var requests: [String] { lock.lock(); defer { lock.unlock() }; return seen }
    static func reset(_ answer: @escaping (String) -> String) { lock.lock(); seen = []; reply = answer; lock.unlock() }
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let path = request.url?.path ?? ""
        var entry = (request.httpMethod ?? "GET") + " " + path + (request.url?.query.map { "?" + $0 } ?? "")
        if let body = request.httpBody ?? request.httpBodyStream.map(Self.drain) { entry += " " + String(decoding: body, as: UTF8.self) }
        Self.lock.lock(); Self.seen.append(entry); let answer = Self.reply; Self.lock.unlock()
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil,
            headerFields: ["Content-Type": "application/json"])!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(answer(path).utf8)); client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
    private static func drain(_ stream: InputStream) -> Data {
        stream.open(); defer { stream.close() }
        var data = Data(), buffer = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let count = stream.read(&buffer, maxLength: buffer.count)
            if count <= 0 { break }
            data.append(contentsOf: buffer.prefix(count))
        }
        return data
    }
}

/// One working member and one stopped session: the toolbar counts one.
private let workingFixture = #"{"at": 1, "agents": [{"key": "a", "working": true, "stopped": null}], "others": [{"key": "b", "working": true, "stopped": {"at": 1, "released": false}}]}"#

@MainActor final class MonitorStateTests: XCTestCase {
    private func session() -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral; configuration.protocolClasses = [MonitorTransport.self]
        return URLSession(configuration: configuration)
    }
    private func model() throws -> Model {
        Model(client: try Client(port: 39321, token: "fixture", session: session()), defaults: UserDefaults(suiteName: "RelicTests." + UUID().uuidString)!)
    }
    private func waitUntil(_ condition: () -> Bool, file: StaticString = #filePath, line: UInt = #line) async throws {
        let deadline = Date().addingTimeInterval(5)
        while !condition() && Date() < deadline { try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertTrue(condition(), file: file, line: line)
    }

    func testToolbarCountReadsAtMostEveryFifteenSecondsAndPublishesOnlyItsChanges() async throws {
        MonitorTransport.reset { _ in workingFixture }
        let monitor = MonitorState(), client = try Client(port: 39321, token: "fixture", session: session())
        let counted = expectation(description: "The toolbar observes the first count")
        withObservationTracking { _ = monitor.working } onChange: { counted.fulfill() }
        monitor.tick(client)
        await fulfillment(of: [counted], timeout: 5)
        try await waitUntil { monitor.working == 1 }
        XCTAssertEqual(monitor.snapshot.agents.map(\.key), ["a"])
        monitor.tick(client); monitor.tick(client)
        XCTAssertEqual(MonitorTransport.requests, ["GET /api/monitor"], "Ticks within 15 s read nothing more")

        // A newer snapshot with the same count republishes the panel's data, never the toolbar.
        MonitorTransport.reset { _ in workingFixture.replacingOccurrences(of: #""at": 1,"#, with: #""at": 2,"#) }
        let unchanged = expectation(description: "The toolbar keeps its count"); unchanged.isInverted = true
        withObservationTracking { _ = monitor.working } onChange: { unchanged.fulfill() }
        let panel = expectation(description: "The open panel observes the newer snapshot")
        withObservationTracking { _ = monitor.snapshot } onChange: { panel.fulfill() }
        monitor.read(client)
        await fulfillment(of: [panel], timeout: 5)
        await fulfillment(of: [unchanged], timeout: 0.3)
        XCTAssertEqual(monitor.snapshot.at, 2)
        XCTAssertEqual(MonitorTransport.requests, ["GET /api/monitor"])
    }

    func testStopAllArmsOnTheFirstClickAndStopsEverythingOnTheSecond() async throws {
        MonitorTransport.reset { path in path == "/api/monitor/stop" ? #"{"stopped": ["a"], "orgs": ["org_a"], "paused": []}"# : workingFixture }
        let model = try model(), monitor = model.monitor
        monitor.stopAll(model: model)
        XCTAssertTrue(monitor.stopAllArmed)
        XCTAssertTrue(MonitorTransport.requests.isEmpty, "The first click only arms Stop all")
        monitor.stopAll(model: model)
        XCTAssertFalse(monitor.stopAllArmed)
        try await waitUntil { MonitorTransport.requests.count >= 2 }
        XCTAssertEqual(MonitorTransport.requests, [#"POST /api/monitor/stop {"all":true}"#, "GET /api/monitor"])
        monitor.stopAll(model: model); XCTAssertTrue(monitor.stopAllArmed)
        monitor.disarm(); XCTAssertFalse(monitor.stopAllArmed)
    }

    func testChangingAFilterReadsTheStatisticsAgainAndPreparesTheChart() async throws {
        MonitorTransport.reset { path in
            path == "/api/usage"
                ? #"{"span": "30d", "bucket": "day", "group": "org", "starts": [1793836800], "total": 5, "series": [{"key": "org_a", "label": "研发部", "values": [5], "total": {"total": 5}}]}"#
                : "{}"
        }
        let model = try model(), monitor = model.monitor
        monitor.filter(model) { monitor.span = "30d"; monitor.group = "org" }
        try await waitUntil { monitor.report.answered }
        XCTAssertEqual(monitor.report.span, "30d")
        XCTAssertEqual(monitor.chart.lines.map(\.name), ["研发部"])
        XCTAssertEqual(MonitorTransport.requests, ["GET /api/usage?span=30d&group=org"])
    }
}
