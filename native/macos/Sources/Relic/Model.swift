import AppKit
import SwiftUI
import UserNotifications
import RelicCore

@MainActor final class Model: ObservableObject {
    @Published var organizations: [Node] = []
    @Published var messages: [Node] = []
    @Published var liveItems: [Node] = []
    @Published var liveStatus = Node()
    @Published var conversation = Node()
    @Published var copies: [Node] = []
    @Published var snapshot = Node()
    @Published var preferences = Node()
    @Published var platform = Node()
    @Published var words = Words()
    @Published var organization = ""
    @Published var member = ""
    @Published var draft = ""
    @Published var recipients = ["all"]
    @Published var quote = ""
    var selectedText = ""
    var selectedAuthor = ""
    @Published var pane = "overview"
    @Published var error = ""
    @Published var notice = ""
    @Published var ready = false
    @Published var sending = false
    @Published var moreChat = false
    @Published var sheet: Sheet?
    @Published var folded: Set<String> = []
    @Published var history = NavigationHistory()
    @Published var recent: [ChatSelection] = []
    @Published var sidebarOpen = true
    @Published var panelOpen = true
    @Published var focusSearch = false
    @Published var search = ""
    @Published var overviewMode = "transparent"
    @Published var detailTab = "trace"
    @Published var detailMember = ""
    @Published var detailTask = ""
    @Published var detailFilter = "open"
    @Published var cardMember = ""
    @Published var memberMode = "app"
    @Published var editMember = ""
    @Published var newSecretary = false
    @Published var settingsSection = "profile"
    @Published var threadID = ""
    @Published var threadData = Node()
    @Published var threadDraft = ""
    @Published var file = Node()
    @Published var fileImage: NSImage?
    @Published var fileLine = 0
    @Published var plainMode = false
    @Published var plainOne: Set<String> = []
    @Published var plain: [String: Node] = [:]
    @Published var plainPending: Set<String> = []
    @Published var plainFailed: Set<String> = []
    @Published var digestOpen = false
    @Published var digest = Node()
    @Published var digestPending = false
    @Published var installLogs: [String: [String]] = [:]
    @Published var revision = 0
    let defaults: UserDefaults
    var drafts: [String: ChatDraft] = [:]
    var client: Client?
    private let host = ServerHost()
    private var eventTask: Task<Void, Never>?, refreshTask: Task<Void, Never>?
    private var plainTask: Task<Void, Never>?
    private var plainQueue: Set<String> = []
    private var refreshing = false, pending = false, starting = false
    private var fileRequest = UUID()
    private var previousDecisions: [String: Set<String>] = [:]
    private var previousMessages: [String: String] = [:]
    private var previousCopies: Int?
    enum Sheet: String, Identifiable {
        case create, member, settings, copies, chart, protocolForm, card, secretary, forward, details, shortcuts
        var id: String { rawValue }
    }
    init(client: Client? = nil, defaults: UserDefaults = .standard) {
        self.client = client; self.defaults = defaults
        folded = Set(defaults.stringArray(forKey: "folded") ?? [])
        if let data = defaults.data(forKey: "drafts") { drafts = (try? JSONDecoder().decode([String: ChatDraft].self, from: data)) ?? [:] }
        if let data = defaults.data(forKey: "recent") { recent = (try? JSONDecoder().decode([ChatSelection].self, from: data)) ?? [] }
        sidebarOpen = defaults.object(forKey: "sidebar") as? Bool ?? true
        panelOpen = defaults.object(forKey: "panel") as? Bool ?? true
        pane = defaults.string(forKey: "pane") ?? "overview"
        if let data = defaults.data(forKey: "selection"), let saved = try? JSONDecoder().decode(ChatSelection.self, from: data) { setSelection(saved) }
    }
    var selection: ChatSelection { ChatSelection(organization, member) }
    var members: [Node] { snapshot["members"].rows }
    var selectedMember: Node { members.first { $0["name"].text == member } ?? Node() }
    var secretary: String { snapshot["org"]["secretary"].text }
    func name(_ who: String) -> String { who == "human" ? (preferences["name"].text.isEmpty ? t("common.you") : preferences["name"].text) : members.first { $0["name"].text == who }?.display ?? who }
    func t(_ key: String, _ args: [String: String] = [:]) -> String { words.t(key, args) }
    func path(_ action: String = "") -> String { selection.path(action) }
    func run(_ action: @escaping () async throws -> Void) { Task { do { try await action() } catch is CancellationError {} catch { self.error = error.localizedDescription } } }
    func get(_ path: String) async throws -> Node { guard let client else { throw RelicError.message(t("common.loading")) }; return try await client.get(path) }
    @discardableResult func post(_ path: String, _ body: [String: Any]) async throws -> Node { guard let client else { throw RelicError.message(t("common.loading")) }; return try await client.post(path, body) }
    func bytes(_ path: String) async throws -> Data { guard let client else { return Data() }; return try await client.data(path) }
    func start() async {
        guard !starting, !ready else { return }; starting = true
        defer { starting = false }
        do {
            if client == nil {
                let env = ProcessInfo.processInfo.environment
                let root = env["RELIC_ENGINE_ROOT"].map { URL(fileURLWithPath: $0) } ?? Bundle.main.resourceURL!.appendingPathComponent("engine")
                client = try await host.start(root: root, python: env["RELIC_PYTHON"])
            }
            preferences = try await get("/api/prefs"); platform = try await get("/api/platform")
            let language = Words.normalize(preferences["lang"].text.isEmpty ? Locale.current.identifier : preferences["lang"].text)
            _ = try await post("/api/prefs", ["lang": language])
            words.load(try await get("/api/i18n?lang=" + language)); ready = true
            try await refresh()
            eventTask = Task { [weak self] in
                guard let client = self?.client else { return }
                await client.events { [weak self] event in await self?.receive(event) }
            }
        } catch { self.error = error.localizedDescription; ready = false; client = nil; host.stop() }
    }
    func receive(_ event: Node) async {
        let type = event["type"].text
        if type == "shutdown" { ready = false; error = t("state.idle"); eventTask?.cancel(); client = nil; host.stop(); return }
        if type == "reconnect" {
            let retry = Array(plainPending); plainPending = []
            for id in retry { enqueuePlain(id) }
            if digestOpen { run { try await self.loadDigest(false) } }
        }
        if type == "prefs" {
            do { preferences = try await get("/api/prefs"); words.load(try await get("/api/i18n?lang=" + Words.normalize(preferences["lang"].text))) }
            catch { self.error = error.localizedDescription }
        }
        if type == "install" {
            let id = event["id"].text
            if !event["line"].text.isEmpty { installLogs[id, default: []].append(event["line"].text) }
            if !event["done"].isNull { installLogs[id, default: []].append(event["done"].integer == 0 ? t("settings.install_done") : t("settings.install_failed", ["code": event["done"].text])); notice = t(event["done"].integer == 0 ? "settings.adapter_installed" : "settings.adapter_install_failed"); revision += 1 }
            installLogs[id] = Array((installLogs[id] ?? []).suffix(200)); return
        }
        if event["org"].text == organization {
            if type == "plain" { acceptPlain(event["items"], ids: event["ids"].rows.map(\.text)); if !event["error"].text.isEmpty { error = t("plain.failed", ["error": event["error"].text]) }; return }
            if type == "digest" { digestPending = false; digest = event["digest"]; if !event["error"].text.isEmpty { error = t("digest.failed", ["error": event["error"].text]) }; return }
            if type == "live", event["member"].text == member {
                if !event["item"].isNull { liveItems = Timeline.merge(liveItems, [event["item"]]) }
                if !event["status"].isNull { liveStatus = event["status"] }
            }
        }
        schedule()
    }
    func persistDraft() {
        guard !organization.isEmpty else { return }
        var value = ChatDraft(); value.text = draft; value.quote = quote; value.recipients = recipients
        drafts[selection.key] = value
        if let data = try? JSONEncoder().encode(drafts) { defaults.set(data, forKey: "drafts") }
    }
    func stop() { persistDraft(); eventTask?.cancel(); refreshTask?.cancel(); plainTask?.cancel(); host.stop() }
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
        do { organizations = try await get("/api/orgs").rows } catch { throw RelicError.message(t("boot.load_orgs_failed", ["error": error.localizedDescription])) }
        copies = try await get("/api/cc")["items"].rows
        let unreadCopies = copies.filter { !$0["read"].flag }.count
        if let previousCopies, unreadCopies > previousCopies, let copy = copies.first(where: { !$0["read"].flag }) { backgroundNotify(t("cc.notify", ["org": copy["org_name"].text, "id": copy["protocol_id"].text, "title": copy["title"].text]), org: copy["org"].text, member: "") }
        previousCopies = unreadCopies
        if !organization.isEmpty && !organizations.contains(where: { $0["id"].text == organization }) { setSelection(ChatSelection()) }
        if organization.isEmpty, let first = organizations.first { setSelection(ChatSelection(first["id"].text)) }
        guard !organization.isEmpty else { return }
        let selected = selection
        let snap = try await get(selected.path("?lang=" + words.language))
        let chat = try await get(selected.path("/chat?kind=" + (selected.member.isEmpty ? "group" : "private") + "&member=" + Client.segment(selected.member) + "&limit=200"))
        let who = snap["members"].rows.first { $0["name"].text == selected.member } ?? Node()
        var live = Node(), convo = Node()
        if who["embedded"].flag { live = try await get(selected.path("/live?member=" + Client.segment(selected.member))) }
        if who["has_transcript"].flag { convo = try await get(selected.path("/convo?member=" + Client.segment(selected.member))) }
        guard selected == selection else { pending = true; return }
        snapshot = snap; messages = Timeline.merge(messages, chat["items"].rows); moreChat = chat["more"].flag
        let chatKey = member.isEmpty ? "group" : "member:" + member
        if !snap["chats"][chatKey]["last"]["id"].isNull { defaults.set(snap["chats"][chatKey]["last"]["id"].integer, forKey: "seen." + organization + "/" + chatKey) }
        liveItems = live["items"].rows; liveStatus = live["status"]; conversation = convo; revision += 1
        let ids = Set(snap["decisions"].rows.map { $0["kind"].text + ":" + $0["id"].text + ":" + $0["member"].text })
        if let previous = previousDecisions[organization], !ids.subtracting(previous).isEmpty { backgroundNotify(t("notify.decisions", ["n": String(ids.count), "org": snap["org"]["name"].text])) }
        previousDecisions[organization] = ids
        for (chatKey, raw) in snap["chats"].object {
            let last = Node(raw)["last"], key = organization + "/" + chatKey
            if let previous = previousMessages[key], previous != last["id"].text, last["from"].text != "human" { backgroundNotify(t("notify.new_messages"), org: organization, member: chatKey.hasPrefix("member:") ? String(chatKey.dropFirst(7)) : "") }
            previousMessages[key] = last["id"].text
        }
        if !threadID.isEmpty { try await loadThread() }
    }
    func setSelection(_ next: ChatSelection, record: Bool = true) {
        plainTask?.cancel(); plainTask = nil; plainQueue = []
        persistDraft(); organization = next.org; member = next.member
        let saved = drafts[next.key] ?? ChatDraft(); draft = saved.text; quote = saved.quote; recipients = saved.recipients
        messages = []; snapshot = Node(); liveItems = []; liveStatus = Node(); conversation = Node(); moreChat = false
        selectedText = ""; selectedAuthor = ""
        threadID = ""; threadData = Node(); if pane == "thread" { pane = "overview" }
        file = Node(); fileImage = nil; plain = [:]; plainOne = []; plainPending = []; plainFailed = []; digest = Node(); digestPending = false
        plainMode = defaults.bool(forKey: "plain." + next.org); digestOpen = defaults.bool(forKey: "digest." + next.org)
        overviewMode = defaults.string(forKey: "mode." + next.org) ?? "transparent"
        if record { history.visit(next) }
        if let data = try? JSONEncoder().encode(next) { defaults.set(data, forKey: "selection") }
        recent.removeAll { $0 == next }; recent.insert(next, at: 0); recent = Array(recent.prefix(12))
        if let data = try? JSONEncoder().encode(recent) { defaults.set(data, forKey: "recent") }
        var ancestor = next.org, seen: Set<String> = []
        while !ancestor.isEmpty, seen.insert(ancestor).inserted { folded.remove(ancestor); ancestor = organizations.first { $0["id"].text == ancestor }?["parent"].text ?? "" }
        defaults.set(Array(folded), forKey: "folded")
    }
    func select(_ org: String, _ member: String = "", record: Bool = true) async throws {
        setSelection(ChatSelection(org, member), record: record); try await refresh()
        if digestOpen { try await loadDigest(false) }
    }
    func navigate(_ delta: Int) { guard let next = history.move(delta) else { return }; run { try await self.select(next.org, next.member, record: false) } }
    func loadOlder() async throws {
        let selected = selection, before = messages.first?["id"].text ?? ""
        let result = try await get(selected.path("/chat?kind=" + (member.isEmpty ? "group" : "private") + "&member=" + Client.segment(member) + "&limit=200&before=" + Client.segment(before)))
        guard selected == selection else { return }; messages = Timeline.merge(result["items"].rows, messages); moreChat = result["more"].flag
    }
    func send() async throws {
        guard !sending, !organization.isEmpty, !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        sending = true; defer { sending = false }
        let selected = selection, body = draft, quoted = quote, to = recipients
        do { _ = try await post(selected.path("/send"), Composer.message(body: body, member: selected.member, selected: to, members: members, quote: quoted)) }
        catch { throw RelicError.message(t("composer.send_failed", ["error": error.localizedDescription])) }
        if selected == selection {
            if draft == body { draft = "" }; if quote == quoted { quote = "" }; recipients = ["all"]; persistDraft()
        } else if drafts[selected.key]?.text == body {
            drafts[selected.key] = ChatDraft()
            if let data = try? JSONEncoder().encode(drafts) { defaults.set(data, forKey: "drafts") }
        }
        try await refresh()
    }
    func savePreferences(_ changes: [String: Any]) async throws {
        do { preferences = try await post("/api/prefs", changes) } catch { throw RelicError.message(t("prefs.save_failed", ["error": error.localizedDescription])) }
        if changes["lang"] != nil { words.load(try await get("/api/i18n?lang=" + Words.normalize(preferences["lang"].text))) }
    }
    func saveSettings(language: String, notify: Bool) async throws {
        try await savePreferences(["lang": Words.normalize(language), "notify": notify])
        if notify { try await authorizeNotifications() }
        try await refresh()
    }
    func authorizeNotifications() async throws {
        let allowed: Bool
        do { allowed = try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) }
        catch { throw RelicError.message(t("settings.notify_unsupported") + " " + error.localizedDescription) }
        guard allowed else { throw RelicError.message(t("settings.notify_denied")) }
    }
    func notify(_ message: String, org: String? = nil, member: String? = nil) {
        let content = UNMutableNotificationContent(); content.title = "Relic"; content.body = message; content.userInfo = ["org": org ?? organization, "member": member ?? self.member]
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil))
    }
    private func backgroundNotify(_ message: String, org: String? = nil, member: String? = nil) { if preferences["notify"].flag, NSApp != nil, !NSApp.isActive { notify(message, org: org, member: member) } }
    func openMemberForm(mode: String = "app", edit: String = "", secretary: Bool = false) { memberMode = mode; editMember = edit; newSecretary = secretary; sheet = .member }
    func openCard(_ name: String) { cardMember = name; sheet = .card }
    func openDetails(_ tab: String, member: String = "", task: String = "", filter: String = "open") { detailTab = tab; detailMember = member.isEmpty ? self.member : member; detailTask = task; detailFilter = task.isEmpty ? filter : "all"; sheet = .details }
    func setPane(_ value: String) { pane = value; panelOpen = true; if value != "thread" { defaults.set(value, forKey: "pane") } }
    func toggleFold(_ id: String) { Tree.toggle(id, folded: &folded); defaults.set(Array(folded), forKey: "folded") }
    func setQuote(_ body: String, from: String, stripExisting: Bool = false) {
        let trimmed = body.trimmingCharacters(in: .whitespacesAndNewlines)
        var lines = trimmed.components(separatedBy: "\n"); if stripExisting { while lines.first?.hasPrefix(">") == true { lines.removeFirst() } }
        while lines.first?.isEmpty == true { lines.removeFirst() }; guard !lines.isEmpty else { return }
        let text = lines.joined(separator: "\n"); lines = (text.count > 1200 ? String(text.prefix(1200)) + "…" : text).components(separatedBy: "\n")
        lines[0] = t("sel.quote_line", ["who": name(from), "text": lines[0]])
        quote = lines.map { "> " + $0 }.joined(separator: "\n"); persistDraft()
    }
    func openThread(_ id: String) async throws { threadID = id; threadDraft = defaults.string(forKey: "thread." + organization + "/" + id) ?? ""; setPane("thread"); try await loadThread() }
    func loadThread() async throws {
        let selected = selection, id = threadID; guard !id.isEmpty else { return }
        let result = try await get(selected.path("/thread?root=" + Client.segment(id)))
        if selected == selection, id == threadID { threadData = result }
    }
    func sendThread() async throws {
        let selected = selection, id = threadID, body = threadDraft
        guard !body.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        let quoted = quote
        _ = try await post(selected.path("/send"), Composer.message(body: body, member: selected.member, selected: [], members: [], quote: quoted, replyTo: id))
        defaults.removeObject(forKey: "thread." + selected.org + "/" + id)
        if selected == selection, id == threadID, threadDraft == body { threadDraft = ""; if quote == quoted { quote = "" } }
        try await loadThread(); schedule()
    }
    func openFile(_ path: String, line: Int = 0) async throws {
        let selected = selection, request = UUID(); fileRequest = request
        let result: Node
        do { result = try await get("/api/fs/read?path=" + Client.segment(path)) } catch { throw RelicError.message(t("file.open_failed", ["error": error.localizedDescription])) }
        var image: NSImage?; if result["kind"].text == "image" { image = NSImage(data: try await bytes("/api/fs/raw?path=" + Client.segment(path))) }
        guard selection == selected, fileRequest == request else { return }; file = result; fileImage = image; fileLine = line; setPane("files")
    }
    func acceptPlain(_ items: Node, ids: [String]) {
        for (id, value) in items.object { plain[id] = Node(value) }
        for id in ids { plainPending.remove(id); if plain[id] == nil { plainFailed.insert(id) } }
    }
    func enqueuePlain(_ id: String) {
        guard Int(id) != nil, plain[id] == nil, !plainPending.contains(id) else { return }; plainQueue.insert(id)
        guard plainTask == nil else { return }
        let selected = selection
        plainTask = Task { [weak self] in
            do { try await Task.sleep(for: .milliseconds(400)) } catch { return }
            guard let self, !Task.isCancelled, self.selection == selected else { return }
            let ids = Array(self.plainQueue).sorted { (Int($0) ?? 0) < (Int($1) ?? 0) }; self.plainQueue = []; self.plainTask = nil
            do { try await self.requestPlain(ids) } catch { self.error = self.t("plain.failed", ["error": error.localizedDescription]) }
        }
    }
    func requestPlain(_ ids: [String]) async throws {
        let ids = Array(ids.filter { Int($0) != nil && plain[$0] == nil && !plainPending.contains($0) }.prefix(200))
        guard !ids.isEmpty else { return }; let selected = selection; plainPending.formUnion(ids); plainFailed.subtract(ids)
        do { let result = try await post(selected.path("/plain"), ["ids": ids.compactMap(Int.init)]); guard selected == selection else { return }; acceptPlain(result["items"], ids: Array(result["items"].object.keys)) }
        catch { if selected == selection { plainPending.subtract(ids); plainFailed.formUnion(ids) }; throw error }
    }
    func togglePlain() { plainMode.toggle(); defaults.set(plainMode, forKey: "plain." + organization); if plainMode { notice = t("plain.on_hint") } }
    func loadDigest(_ refresh: Bool) async throws {
        let selected = selection; digestPending = true
        do { let result = try await post(selected.path("/digest"), ["refresh": refresh]); guard selection == selected else { return }; if !result["digest"].isNull { digest = result["digest"] }; digestPending = result["pending"].flag; if refresh && !digestPending { notice = t("digest.up_to_date") } }
        catch { if selection == selected { digestPending = false }; throw error }
    }
    func toggleDigest() { digestOpen.toggle(); defaults.set(digestOpen, forKey: "digest." + organization); if digestOpen { run { try await self.loadDigest(false) } } }
    func askSecretary() async throws {
        let selected = selection, sec = secretary; guard !sec.isEmpty else { return }
        try await post(selected.path("/send"), ["to": [sec], "channel": "private", "body": t("digest.ask_message")]); try await select(selected.org, sec)
    }
}
