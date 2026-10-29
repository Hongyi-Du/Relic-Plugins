import Foundation

public struct Node {
    public let raw: Any
    public init(_ raw: Any = [String: Any]()) { self.raw = raw }
    public subscript(_ key: String) -> Node { Node((raw as? [String: Any])?[key] ?? NSNull()) }
    public var text: String { if raw is NSNull { return "" }; return (raw as? String) ?? String(describing: raw) }
    public var flag: Bool { (raw as? Bool) ?? false }
    public var rows: [Node] { (raw as? [Any] ?? []).map(Node.init) }
    public var isNull: Bool { raw is NSNull }
}

public enum RelicError: LocalizedError {
    case message(String)
    public var errorDescription: String? { switch self { case .message(let message): return message } }
}

public final class Client {
    let base: URL
    let token: String
    let session: URLSession
    public init(port: Int, token: String, session: URLSession? = nil) throws {
        guard (1...65535).contains(port), !token.isEmpty else { throw RelicError.message("Invalid server record") }
        self.base = URL(string: "http://127.0.0.1:\(port)")!; self.token = token
        let configuration = URLSessionConfiguration.ephemeral
        configuration.connectionProxyDictionary = [:]
        configuration.timeoutIntervalForRequest = 30
        self.session = session ?? URLSession(configuration: configuration)
    }
    public static func segment(_ text: String) -> String {
        text.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? ""
    }
    public static func org(_ id: String, _ rest: String = "") -> String { "/api/org/" + segment(id) + rest }
    func request(_ path: String, body: [String: Any]? = nil) throws -> URLRequest {
        guard path.hasPrefix("/api/"), let url = URL(string: base.absoluteString + path) else { throw RelicError.message("Invalid API path") }
        var request = URLRequest(url: url)
        request.setValue(token, forHTTPHeaderField: "X-Relic-Token")
        if let body {
            request.httpMethod = "POST"; request.httpBody = try JSONSerialization.data(withJSONObject: body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return request
    }
    public func get(_ path: String) async throws -> Node { try await call(path) }
    public func post(_ path: String, _ body: [String: Any]) async throws -> Node { try await call(path, body: body) }
    private func call(_ path: String, body: [String: Any]? = nil) async throws -> Node {
        let (data, response) = try await session.data(for: request(path, body: body))
        let node = Node(try JSONSerialization.jsonObject(with: data))
        guard let response = response as? HTTPURLResponse, (200..<300).contains(response.statusCode) else { throw RelicError.message(node["error"].text) }
        return node
    }
    public func events(_ receive: @escaping (Node) async -> Void) async {
        while !Task.isCancelled {
            do {
                let (bytes, response) = try await session.bytes(for: request("/api/events"))
                guard (response as? HTTPURLResponse)?.statusCode == 200 else { throw RelicError.message("Event stream unavailable") }
                // URLSession's lines iterator omits empty lines. Server emits one JSON data line per event.
                for try await line in bytes.lines {
                    try Task.checkCancellation()
                    if line.hasPrefix("data:"), let data = line.dropFirst(5).data(using: .utf8) {
                        await receive(Node(try JSONSerialization.jsonObject(with: data)))
                    }
                }
            } catch { if Task.isCancelled { return } }
            do { try await Task.sleep(for: .milliseconds(1500)) } catch { return }
            await receive(Node(["type": "reconnect"]))
        }
    }
}

public struct Words {
    public private(set) var language = "en-US"
    private var strings = Node()
    public init() {}
    public static func normalize(_ language: String) -> String { language.lowercased().hasPrefix("zh") ? "zh-CN" : "en-US" }
    public mutating func load(_ response: Node) { language = Self.normalize(response["lang"].text); strings = response["strings"] }
    public func t(_ key: String, _ args: [String: String] = [:]) -> String {
        var value = strings[key]
        if value.raw is [String: Any] { value = value[language == "en-US" && args["n"] == "1" ? "one" : "other"] }
        var result = value.isNull ? key : value.text
        for (key, value) in args { result = result.replacingOccurrences(of: "{" + key + "}", with: value) }
        return result
    }
}

public enum Composer {
    public static func message(body: String, member: String, selected: [String], members: [Node]) -> [String: Any] {
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
            let client = try Client(port: Int(info["port"].text) ?? 0, token: info["token"].text)
            let live = try await client.get("/api/lifecycle")
            guard live["instance"].text == info["instance"].text, live["pid"].text == info["pid"].text else { throw RelicError.message("Relic instance changed during startup") }
            return client
        } catch { stop(); throw error }
    }
    public func stop() { try? input?.fileHandleForWriting.close(); input = nil }
    deinit { stop() }
}
