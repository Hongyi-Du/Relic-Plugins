import Foundation

public struct Node {
    public let raw: Any
    public init(_ raw: Any = [String: Any]()) { self.raw = raw }
    public subscript(_ key: String) -> Node { Node((raw as? [String: Any])?[key] ?? NSNull()) }
    public var text: String { if raw is NSNull { return "" }; return (raw as? String) ?? String(describing: raw) }
    public var flag: Bool { (raw as? Bool) ?? false }
    public var rows: [Node] { (raw as? [Any] ?? []).map(Node.init) }
    public var isNull: Bool { raw is NSNull }
    public var object: [String: Any] { raw as? [String: Any] ?? [:] }
    public var integer: Int { (raw as? NSNumber)?.intValue ?? Int(text) ?? 0 }
    public var display: String { self["display"].text.isEmpty ? self["name"].text : self["display"].text }
}

public enum RelicError: LocalizedError {
    case message(String)
    public var errorDescription: String? { switch self { case .message(let message): return message } }
}

public final class Client {
    private struct Connection: Equatable {
        let base: URL
        let token: String
    }
    private var connection: Connection
    private let connectionLock = NSLock()
    private let serverRecord: (() throws -> Node)?
    let session: URLSession
    public init(port: Int, token: String, session: URLSession? = nil, serverRecord: (() throws -> Node)? = nil) throws {
        guard (1...65535).contains(port), !token.isEmpty else { throw RelicError.message("Invalid server record") }
        connection = Connection(base: URL(string: "http://127.0.0.1:\(port)")!, token: token); self.serverRecord = serverRecord
        let configuration = URLSessionConfiguration.ephemeral
        configuration.connectionProxyDictionary = [:]
        configuration.timeoutIntervalForRequest = 30
        self.session = session ?? URLSession(configuration: configuration, delegate: LoopbackDelegate(), delegateQueue: nil)
    }
    public static func segment(_ text: String) -> String {
        text.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? ""
    }
    public static func org(_ id: String, _ rest: String = "") -> String { "/api/org/" + segment(id) + rest }
    func request(_ path: String, body: [String: Any]? = nil) throws -> URLRequest {
        try request(path, body: body, using: currentConnection())
    }
    private func currentConnection() -> Connection { connectionLock.lock(); defer { connectionLock.unlock() }; return connection }
    private func adopt(_ candidate: Connection, replacing previous: Connection) {
        connectionLock.lock(); defer { connectionLock.unlock() }; if connection == previous { connection = candidate }
    }
    private func request(_ path: String, body: [String: Any]? = nil, using connection: Connection) throws -> URLRequest {
        guard path.hasPrefix("/api/"), !path.contains("#"), let url = URL(string: connection.base.absoluteString + path), url.host == "127.0.0.1", url.port == connection.base.port else { throw RelicError.message("Invalid API path") }
        var request = URLRequest(url: url)
        request.setValue(connection.token, forHTTPHeaderField: "X-Relic-Token")
        if let body {
            request.httpMethod = "POST"; request.httpBody = try JSONSerialization.data(withJSONObject: body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return request
    }
    public func get(_ path: String) async throws -> Node { try await call(path) }
    public func post(_ path: String, _ body: [String: Any]) async throws -> Node { try await call(path, body: body) }
    private func call(_ path: String, body: [String: Any]? = nil) async throws -> Node {
        do {
            let (data, response) = try await session.data(for: request(path, body: body))
            let error = Node((try? JSONSerialization.jsonObject(with: data)) ?? NSNull())["error"].text
            // A rejected token cannot have executed the write. No other failed POST is replayed.
            if (response as? HTTPURLResponse)?.statusCode == 403, error == "missing token", await refreshRecord() { return try await callOnce(path, body: body) }
            return try decode(data, response)
        } catch {
            if body == nil, !Task.isCancelled, await refreshRecord() { return try await callOnce(path, body: nil) }
            throw error
        }
    }
    private func callOnce(_ path: String, body: [String: Any]?) async throws -> Node {
        let (data, response) = try await session.data(for: request(path, body: body)); return try decode(data, response)
    }
    private func decode(_ data: Data, _ response: URLResponse) throws -> Node {
        let node = Node((try? JSONSerialization.jsonObject(with: data)) ?? NSNull())
        guard let response = response as? HTTPURLResponse, (200..<300).contains(response.statusCode) else { throw RelicError.message(node["error"].text.isEmpty ? "HTTP \((response as? HTTPURLResponse)?.statusCode ?? 0)" : node["error"].text) }
        guard !node.isNull else { throw RelicError.message("Invalid JSON response") }
        if node["status"].text == "failed" || (!node["ok"].isNull && !node["ok"].flag) { throw RelicError.message(node["error"].text) }
        return node
    }
    @discardableResult func refreshRecord() async -> Bool {
        guard let serverRecord, !Task.isCancelled else { return false }
        let previous = currentConnection()
        do {
            let info = try serverRecord(), port = info["port"].integer
            guard (1...65535).contains(port), !info["token"].text.isEmpty, info["pid"].integer > 0, !info["instance"].text.isEmpty else { return false }
            let candidate = Connection(base: URL(string: "http://127.0.0.1:\(port)")!, token: info["token"].text)
            if candidate == previous { return false }
            let (data, response) = try await session.data(for: request("/api/lifecycle", using: candidate))
            let live = try decode(data, response)
            guard live["app"].text == "relic", live["state"].text == "running", live["port"].integer == port, live["pid"].integer == info["pid"].integer, live["instance"].text == info["instance"].text else { return false }
            adopt(candidate, replacing: previous); return currentConnection() != previous
        } catch { return false }
    }
    public func data(_ path: String) async throws -> Data {
        let (data, response) = try await session.data(for: request(path))
        guard let response = response as? HTTPURLResponse, (200..<300).contains(response.statusCode) else { throw RelicError.message("Unable to load image") }
        return data
    }
    public func events(_ receive: @escaping (Node) async -> Void) async {
        while !Task.isCancelled {
            do {
                var eventRequest = try request("/api/events")
                eventRequest.timeoutInterval = 86400
                eventRequest.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                let (bytes, response) = try await session.bytes(for: eventRequest)
                guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw RelicError.message("Event stream unavailable") }
                var decoder = EventDecoder()
                for try await byte in bytes {
                    try Task.checkCancellation()
                    if let event = decoder.append(byte) { await receive(event) }
                }
            } catch { if Task.isCancelled { return } }
            do { try await Task.sleep(for: .milliseconds(1500)) } catch { return }
            await refreshRecord()
            await receive(Node(["type": "reconnect"]))
        }
    }
}

public struct Words {
    public private(set) var language = "en-US"
    private var strings = Node()
    public private(set) var languages: [Node] = []
    public init() {}
    public static func normalize(_ language: String) -> String { language.lowercased().hasPrefix("zh") ? "zh-CN" : "en-US" }
    public mutating func load(_ response: Node) { language = Self.normalize(response["lang"].text); strings = response["strings"]; languages = response["languages"].rows.filter { ["zh-CN", "en-US"].contains($0["code"].text) } }
    public func t(_ key: String, _ args: [String: String] = [:]) -> String {
        var value = strings[key]
        if value.raw is [String: Any] { value = value[language == "en-US" && args["n"] == "1" ? "one" : "other"] }
        var result = value.isNull ? key : value.text
        for (key, value) in args { result = result.replacingOccurrences(of: "{" + key + "}", with: value) }
        return result
    }
    public func list(_ values: [String]) -> String {
        guard let first = values.first else { return "" }; if values.count == 1 { return first }
        if values.count == 2 { return t("list.pair", ["a": first, "b": values[1]]) }
        return values.dropFirst().enumerated().reduce(first) { result, next in t(next.offset == values.count - 2 ? "list.end" : "list.middle", ["a": result, "b": next.element]) }
    }
}

public enum Composer {
    public static func sendsReturn(shift: Bool, composing: Bool, completing: Bool) -> Bool { !shift && !composing && !completing }
    public static func message(body: String, member: String, selected: [String], members: [Node], quote: String = "", replyTo: String = "") -> [String: Any] {
        let body = quote.isEmpty ? body : quote + "\n\n" + body
        if !replyTo.isEmpty { return ["body": body, "channel": member.isEmpty ? "group" : "private", "reply_to": Int(replyTo).map { $0 as Any } ?? replyTo] }
        var to = selected
        if !member.isEmpty { to = [member] }
        else if to.isEmpty || to.contains("all") {
            to = members.filter { body.contains("@" + $0["name"].text) || (!$0["display"].text.isEmpty && body.contains("@" + $0["display"].text)) }.map { $0["name"].text }
            if to.isEmpty { to = ["all"] }
        }
        return ["body": body, "to": to, "channel": member.isEmpty ? "group" : "private"]
    }
}

public final class ServerHost {
    private var process: Process?
    private var input: Pipe?
    private var errors = Data()
    public init() {}
    public func start(root: URL, python: String?) async throws -> Client {
        let entry = root.appendingPathComponent("plugins/relic/scripts/native_host.py")
        guard FileManager.default.fileExists(atPath: entry.path) else { throw RelicError.message("Relic engine not found: " + entry.path) }
        let process = Process(), input = Pipe(), output = Pipe(), errorPipe = Pipe()
        process.executableURL = URL(fileURLWithPath: python ?? "/usr/bin/env")
        process.arguments = (python == nil ? ["python3"] : []) + ["-X", "utf8", entry.path]
        var environment = ProcessInfo.processInfo.environment
        environment["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + (environment["PATH"] ?? "/usr/bin:/bin")
        process.environment = environment; process.currentDirectoryURL = root
        process.standardInput = input; process.standardOutput = output; process.standardError = errorPipe
        // Drain stderr so a diagnostic cannot block the readiness pipe.
        errorPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil } else { self?.errors.append(data) }
        }
        try process.run(); self.process = process; self.input = input
        do {
            var record: String?
            for try await line in output.fileHandleForReading.bytes.lines { record = line; break }
            guard let record, let data = record.data(using: .utf8) else { throw RelicError.message(String(data: errors, encoding: .utf8) ?? "Relic failed to start") }
            let info = Node(try JSONSerialization.jsonObject(with: data))
            let dataHome = environment["RELIC_HOME"] ?? NSHomeDirectory() + "/.relic"
            let recordURL = URL(fileURLWithPath: (dataHome as NSString).expandingTildeInPath, relativeTo: root).standardizedFileURL.appendingPathComponent("app.json")
            let client = try Client(port: Int(info["port"].text) ?? 0, token: info["token"].text, serverRecord: { Node(try JSONSerialization.jsonObject(with: Data(contentsOf: recordURL))) })
            let live = try await client.get("/api/lifecycle")
            guard live["app"].text == "relic", live["state"].text == "running", live["port"].integer == info["port"].integer, live["instance"].text == info["instance"].text, live["pid"].text == info["pid"].text else { throw RelicError.message("Relic instance changed during startup") }
            return client
        } catch { stop(); throw error }
    }
    public func stop() { try? input?.fileHandleForWriting.close(); input = nil }
    deinit { stop() }
}
