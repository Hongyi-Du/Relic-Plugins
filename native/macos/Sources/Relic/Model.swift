import AppKit
import SwiftUI
import UserNotifications
import RelicCore

@MainActor final class Model: ObservableObject {
    @Published var organizations: [Node] = []
    @Published var messages: [Node] = []
    @Published var copies: [Node] = []
    @Published var snapshot = Node()
    @Published var preferences = Node()
    @Published var words = Words()
    @Published var organization = ""
    @Published var member = ""
    @Published var draft = ""
    @Published var recipient = "all"
    @Published var pane = "overview"
    @Published var error = ""
    @Published var ready = false
    @Published var sheet: Sheet?
    @Published var folded: Set<String> = []
    private var drafts: [String: String] = [:]
    private var client: Client?
    private let host = ServerHost()
    private var eventTask: Task<Void, Never>?, refreshTask: Task<Void, Never>?
    private var refreshing = false, pending = false
    private var previousDecisions: [String: Set<String>] = [:]
    private var previousMessages: [String: String] = [:]
    enum Sheet: String, Identifiable { case create, member, settings, copies, chart, protocolForm; var id: String { rawValue } }
    func t(_ key: String, _ args: [String: String] = [:]) -> String { words.t(key, args) }
    func path(_ action: String = "") -> String { Client.org(organization, action) }
    func run(_ action: @escaping () async throws -> Void) { Task { do { try await action() } catch { self.error = error.localizedDescription } } }
    func get(_ path: String) async throws -> Node { guard let client else { throw RelicError.message("Relic is not connected") }; return try await client.get(path) }
    @discardableResult func post(_ path: String, _ body: [String: Any]) async throws -> Node { guard let client else { throw RelicError.message("Relic is not connected") }; return try await client.post(path, body) }
    func start() async {
        guard client == nil else { return }
        do {
            let env = ProcessInfo.processInfo.environment
            let root = env["RELIC_ENGINE_ROOT"].map { URL(fileURLWithPath: $0) } ?? Bundle.main.resourceURL!.appendingPathComponent("engine")
            client = try await host.start(root: root, python: env["RELIC_PYTHON"])
            preferences = try await get("/api/prefs")
            let language = Words.normalize(preferences["lang"].text.isEmpty ? Locale.current.identifier : preferences["lang"].text)
            _ = try await post("/api/prefs", ["lang": language])
            words.load(try await get("/api/i18n?lang=" + language)); ready = true
            try await refresh()
            eventTask = Task { [weak self] in
                guard let client = self?.client else { return }
                await client.events { [weak self] event in
                    guard let self else { return }
                    if event["type"].text == "prefs" {
                        do {
                            self.preferences = try await self.get("/api/prefs")
                            self.words.load(try await self.get("/api/i18n?lang=" + Words.normalize(self.preferences["lang"].text)))
                        } catch { self.error = error.localizedDescription }
                    }
                    self.schedule()
                }
            }
        } catch { self.error = error.localizedDescription }
    }
    func stop() { eventTask?.cancel(); refreshTask?.cancel(); host.stop() }
    func schedule() {
        pending = true
        guard refreshTask == nil else { return }
        refreshTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(350))
            guard let self, !Task.isCancelled else { return }
            self.refreshTask = nil
            do { try await self.refresh() } catch { self.error = error.localizedDescription }
        }
    }
    func refresh() async throws {
        if refreshing { pending = true; return }; refreshing = true; pending = false
        defer { refreshing = false; if pending { schedule() } }
        organizations = try await get("/api/orgs").rows
        copies = try await get("/api/cc")["items"].rows
        if organization.isEmpty { organization = organizations.first?["id"].text ?? "" }
        guard !organization.isEmpty else { return }
        let selected = organization, who = member
        let snap = try await get(path())
        var items = try await get(path("/chat?kind=" + (who.isEmpty ? "group" : "private") + "&member=" + Client.segment(who)))["items"].rows
        if !who.isEmpty { items += try await get(path("/live?member=" + Client.segment(who)))["items"].rows }
        guard selected == organization, who == member else { pending = true; return }
        snapshot = snap; messages = items
        let ids = Set(snap["decisions"].rows.map { $0["kind"].text + ":" + $0["id"].text + ":" + $0["member"].text })
        if let previous = previousDecisions[organization], !ids.subtracting(previous).isEmpty, preferences["notify"].flag, !NSApp.isActive {
            notify(t("appbar.decisions", ["n": String(ids.count)]))
        }
        previousDecisions[organization] = ids
        for (chat, raw) in snap["chats"].raw as? [String: Any] ?? [:] {
            let last = Node(raw)["last"], key = organization + "/" + chat
            if let previous = previousMessages[key], previous != last["id"].text, last["from"].text != "human", preferences["notify"].flag, !NSApp.isActive { notify(t("notify.new_messages")) }
            previousMessages[key] = last["id"].text
        }
    }
    func select(_ org: String, _ member: String = "") async throws {
        drafts[organization + "/" + self.member] = draft
        organization = org; self.member = member; draft = drafts[org + "/" + member] ?? ""
        recipient = "all"; try await refresh()
    }
    func send() async throws {
        guard !organization.isEmpty, !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        let body = draft, key = organization + "/" + member
        _ = try await post(path("/send"), Composer.message(body: body, member: member, selected: [recipient], members: snapshot["members"].rows))
        drafts[key] = ""; if key == organization + "/" + member, draft == body { draft = "" }
        try await refresh()
    }
    func saveSettings(language: String, notify: Bool) async throws {
        preferences = try await post("/api/prefs", ["lang": Words.normalize(language), "notify": notify])
        words.load(try await get("/api/i18n?lang=" + Words.normalize(language)))
        if notify { _ = try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) }
        try await refresh()
    }
    private func notify(_ message: String) {
        let content = UNMutableNotificationContent(); content.title = "Relic"; content.body = message
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil))
    }
}
