import AppKit
import SwiftUI
import UserNotifications
import RelicCore
import Observation
import Combine

@Observable @MainActor final class WindowMetrics {
    var size = CGSize(width: 1440, height: 900)
}

@Observable @MainActor final class ConversationData {
    var messages: [Node] = []
    var rows: [ConversationRow] = []
    var version = 0
    var more = false
    var loadingOlder = false
}

@Observable @MainActor final class Model: ObservableObject {
    // EnvironmentObject remains the injection API; Observation tracks each field.
    // No change is broadcast to every view through this compatibility publisher.
    let objectWillChange = ObservableObjectPublisher()
    var organizations: [Node] = []
    private let conversationData = ConversationData()
    // History paging changes the conversation, not the organization tree,
    // toolbar, inspector and every already-mounted message's environment.
    var messages: [Node] {
        get { conversationData.messages }
        set { conversationData.messages = newValue; messageGeneration += 1; prepareConversation() }
    }
    var liveItems: [Node] = [] { didSet { liveGeneration += 1; prepareConversation() } }
    var liveStatus = Node() { didSet { liveGeneration += 1; prepareConversation() } }
    var streamRows: [ConversationRow] {
        get { conversationData.rows }
        set { conversationData.rows = newValue; UIWorkTrace.gauge("conversation_rows", newValue.count) }
    }
    var streamVersion: Int {
        get { conversationData.version }
        set { conversationData.version = newValue }
    }
    var inputSuggestions: InputSuggestionsState?
    var conversation = Node() { didSet { prepareConversation() } }
    var copies: [Node] = []
    var unreadCopies = 0
    var snapshot = Node() { didSet { members = snapshot["members"].rows; prepareConversation() } }
    var preferences = Node()
    var platform = Node()
    var words = Words() { didSet { prepareConversation() } }
    var organization = ""
    var member = ""
    var draft = ""
    var recipients = ["all"]
    var quote = "" {
        didSet { if quote != oldValue { quoteAuthor = ""; quoteText = "" } }
    }
    var quoteAuthor = ""
    var quoteText = ""
    var quotePreviewText: String { quoteText.isEmpty ? quote.replacingOccurrences(of: #"(?m)^>\s?"#, with: "", options: .regularExpression) : quoteText }
    var selectedText = ""
    var selectedAuthor = ""
    @ObservationIgnored weak var selectedTextView: NSTextView?
    var pane = "overview"
    var toasts: [NativeToastMessage] = [] { didSet { for item in oldValue where !toasts.contains(where: { $0 === item }) { item.cancelTimer() } } }
    var noticeSeconds: Double = 3.6
    var error = "" { didSet { if ready && !error.isEmpty { appendToast(error, seconds: 3.6) } } }
    var notice = "" {
        didSet {
            if notice.isEmpty { toasts = [] }
            else { appendToast(notice, seconds: noticeSeconds) }
        }
    }
    var ready = false
    var sending = false
    var threadSending = false
    @ObservationIgnored weak var activeSpeech: SpeechInput?
    var moreChat: Bool {
        get { conversationData.more }
        set { conversationData.more = newValue }
    }
    var loadingOlder: Bool {
        get { conversationData.loadingOlder }
        set { conversationData.loadingOlder = newValue }
    }
    private(set) var historyPagesLoaded = 0
    private let windowMetrics = WindowMetrics()
    // SwiftUI tracks this nested observable only in bodies that read geometry.
    // A window resize must not republish every message, avatar and protocol.
    var windowSize: CGSize {
        get { windowMetrics.size }
        set { if windowMetrics.size != newValue { windowMetrics.size = newValue } }
    }
    func updateWindowGeometry(_ size: CGSize) {
        windowSize = size
        mentionEditor?.closeMentions()
        if inputSuggestions != nil { inputSuggestions = nil }
        if recipientPicker { recipientPicker = false }
        if appMenu != nil { appMenu = nil }
    }
    var expandRules = false
    var recipientPicker = false
    var mentionItems: [Node] = []
    var mentionIndex = 0
    var mentionAnchor = CGRect.zero
    var mentionMenuBounds = CGRect.zero
    var mentionVisible = false
    @ObservationIgnored weak var mentionEditor: ComposerTextView?
    var recipientAnchor = CGRect.zero
    private var presentedAppMenu: String?
    var appMenu: String? {
        get { presentedAppMenu }
        set { if newValue != presentedAppMenu { presentedAppMenu = newValue } }
    }
    let dialogPresentation = DialogPresentation()
    var sheet: Sheet? {
        get { dialogPresentation.sheet }
        set {
            guard newValue != dialogPresentation.sheet else { return }
            activeSpeech?.stop()
            if newValue != nil {
                if recipientPicker { recipientPicker = false }
                mentionEditor?.closeMentions()
            }
            dialogPresentation.sheet = newValue
        }
    }
    var folded: Set<String> = []
    var history = NavigationHistory()
    var recent: [ChatSelection] = []
    var sidebarOpen = true
    var panelOpen = true
    var focusSearch = false
    var search = ""
    var overviewMode = "direct"
    var detailTab = "trace"
    var detailMember = ""
    var detailDocument = ""
    var detailTask = ""
    var detailFilter = "open"
    var cardMember = ""
    var cardAnchor = CGRect.zero
    var memberMode = "app"
    var editMember = ""
    var newSecretary = false
    var settingsSection = "profile"
    var threadID = ""
    var threadData = Node()
    var threadDraft = ""
    @ObservationIgnored private var threadPreviousPane = "overview"
    var file = Node()
    var workspaceMember = ""
    var fileImage: NSImage?
    var fileLine = 0
    var plainMode = false
    var plainOne: Set<String> = []
    var plain: [String: Node] = [:]
    var plainPending: Set<String> = []
    var plainFailed: Set<String> = []
    var digestOpen = false
    var digest = Node()
    var digestPending = false
    var installLogs: [String: [String]] = [:]
    var revision = 0
    let defaults: UserDefaults
    var drafts: [String: ChatDraft] = [:]
    var client: Client?
    var startupStage: ((String) -> Void)?
    private let host = ServerHost()
    @ObservationIgnored private var eventTask: Task<Void, Never>?
    @ObservationIgnored private var refreshTask: Task<Void, Never>?
    @ObservationIgnored private var plainTask: Task<Void, Never>?
    @ObservationIgnored private var plainQueue: Set<String> = []
    @ObservationIgnored private var refreshing = false
    @ObservationIgnored private var pending = false
    @ObservationIgnored private var starting = false
    @ObservationIgnored private var refreshWaiters: [CheckedContinuation<Void, Error>] = []
    @ObservationIgnored private var conversationTask: Task<Void, Never>?
    var isPreparingConversation: Bool { conversationTask != nil }
    @ObservationIgnored private var conversationGeneration = 0
    @ObservationIgnored private var messageGeneration = 0
    @ObservationIgnored private var liveGeneration = 0
    @ObservationIgnored private var fileRequest = UUID()
    @ObservationIgnored private var previousDecisions: [String: Set<String>] = [:]
    @ObservationIgnored private var previousMessages: [String: String] = [:]
    @ObservationIgnored private var previousCopies: Int?
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
    private(set) var members: [Node] = []
    var selectedMember: Node { members.first { $0["name"].text == member } ?? Node() }
    var secretary: String { snapshot["org"]["secretary"].text }
    func name(_ who: String) -> String { who == "human" ? (preferences["name"].text.isEmpty ? t("common.you") : preferences["name"].text) : members.first { $0["name"].text == who }?.display ?? who }
    func roleName(_ who: String, _ titleKey: String) -> String { name(who) == t(titleKey) ? who : name(who) }
    func t(_ key: String, _ args: [String: String] = [:]) -> String { words.t(key, args) }
    func list(_ values: [String]) -> String { words.list(values) }
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
            startupStage?("preferences")
            preferences = try await get("/api/prefs")
            startupStage?("platform")
            platform = try await get("/api/platform")
            let language = Words.normalize(preferences["lang"].text.isEmpty ? Locale.current.identifier : preferences["lang"].text)
            _ = try await post("/api/prefs", ["lang": language])
            startupStage?("language")
            words.load(try await get("/api/i18n?lang=" + language))
            try await refresh()
            startupStage?("fonts")
            let labels = [t("common.new_org"), t("common.group_chat"), t("common.secretary"),
                t("page.tree"), t("org.heading"), t("common.settings"), snapshot["org"]["name"].text]
                + members.prefix(8).map(\.display)
            _ = await NativeTextPreparation.shared.prepare(String(labels.joined(separator: " ").prefix(512)))
            startupStage?("publish")
            ready = true
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
            schedule(); return
        }
        if type == "prefs" {
            do { preferences = try await get("/api/prefs"); words.load(try await get("/api/i18n?lang=" + Words.normalize(preferences["lang"].text))) }
            catch { self.error = error.localizedDescription }
            return
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
        if ["orgs", "cc"].contains(type) || ["org", "decision"].contains(type) && event["org"].text == organization { schedule() }
    }
    func persistDraft() {
        guard !organization.isEmpty else { return }
        var value = ChatDraft(); value.text = draft; value.quote = quote; value.recipients = recipients
        value.quoteAuthor = quoteAuthor.isEmpty ? nil : quoteAuthor
        value.quoteText = quoteText.isEmpty ? nil : quoteText
        drafts[selection.key] = value
        if let data = try? JSONEncoder().encode(drafts) { defaults.set(data, forKey: "drafts") }
    }
    func stop() { inputSuggestions = nil; toasts = []; activeSpeech?.stop(); persistDraft(); eventTask?.cancel(); refreshTask?.cancel(); plainTask?.cancel(); conversationTask?.cancel(); host.stop() }
    private func prepareConversation() {
        conversationGeneration += 1
        guard conversationTask == nil else { return }
        conversationTask = Task { [weak self] in
            guard let self else { return }
            defer { self.conversationTask = nil }
            while !Task.isCancelled {
                // Coalesce the fields of one response and bursts of live events.
                await Task.yield()
                let generation = self.conversationGeneration
                let rows = await ConversationRow.prepare(messages: self.messages, steps: self.conversation["steps"].rows,
                    member: self.selectedMember, live: self.liveItems, status: self.liveStatus,
                    decisions: self.snapshot["decisions"].rows, words: self.words, now: self.displayNow, privateChat: !self.member.isEmpty)
                guard !Task.isCancelled else { return }
                if generation == self.conversationGeneration {
                    self.streamRows = rows; self.streamVersion += 1; return
                }
            }
        }
    }
    func schedule() {
        pending = true
        // An active refresh already consumes the pending bit. Do not enqueue
        // another waiting task for every SSE burst while the request is slow.
        guard !refreshing, refreshTask == nil else { return }
        refreshTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(350))
            guard let self, !Task.isCancelled else { return }
            self.refreshTask = nil
            do { try await self.refresh() } catch { self.error = error.localizedDescription }
        }
    }
    func refresh() async throws {
        if refreshing {
            pending = true
            return try await withCheckedThrowingContinuation { refreshWaiters.append($0) }
        }
        refreshTask?.cancel(); refreshTask = nil; refreshing = true
        do {
            repeat { pending = false; try await refreshOnce() } while pending
            refreshing = false
            let waiting = refreshWaiters; refreshWaiters = []
            for waiter in waiting { waiter.resume() }
        } catch {
            refreshing = false; pending = false
            let waiting = refreshWaiters; refreshWaiters = []
            for waiter in waiting { waiter.resume(throwing: error) }
            throw error
        }
    }
    private func refreshOnce() async throws {
        startupStage?("organizations")
        do {
            let updated = try await get("/api/orgs").rows
            if !(await Node.sameRows(organizations, updated)) { organizations = updated }
        } catch { throw RelicError.message(t("boot.load_orgs_failed", ["error": error.localizedDescription])) }
        startupStage?("copies")
        let copyResponse = try await get("/api/cc")
        let updatedCopies = copyResponse["items"].rows
        if !(await Node.sameRows(copies, updatedCopies)) { copies = updatedCopies }
        if unreadCopies != copyResponse["unread"].integer { unreadCopies = copyResponse["unread"].integer }
        if let previousCopies, unreadCopies > previousCopies, let copy = copies.first(where: { !$0["read"].flag }) { backgroundNotify(t("cc.notify", ["org": copy["org_name"].text, "id": copy["protocol_id"].text, "title": copy["title"].text]), org: copy["org"].text, member: "") }
        previousCopies = unreadCopies
        if !organization.isEmpty && !organizations.contains(where: { $0["id"].text == organization }) { setSelection(ChatSelection()) }
        if organization.isEmpty, let first = organizations.first { setSelection(ChatSelection(first["id"].text)) }
        guard !organization.isEmpty else { return }
        let selected = selection
        startupStage?("snapshot")
        let snap = try await get(selected.path("?lang=" + words.language))
        let chatQuery = selected.member.isEmpty ? "/chat?kind=group&limit=1000"
            : "/chat?kind=private&member=" + Client.segment(selected.member) + "&limit=1000"
        let chat = try await get(selected.path(chatQuery))
        startupStage?("history")
        let who = snap["members"].rows.first { $0["name"].text == selected.member } ?? Node()
        let liveRevision = liveGeneration
        var live = Node(), convo = Node()
        if who["embedded"].flag { live = try await get(selected.path("/live?member=" + Client.segment(selected.member))) }
        if who["has_transcript"].flag { convo = try await get(selected.path("/convo?member=" + Client.segment(selected.member))) }
        guard selected == selection else { return }
        let hadHistory = !messages.isEmpty
        guard await mergeMessages(chat["items"].rows, selected: selected) else { return }
        startupStage?("publish")
        let snapshotChanged = !(await Node.sameContent(snapshot, snap))
        guard selected == selection else { return }
        if snapshotChanged { snapshot = snap; revision += 1 }
        if !hadHistory { moreChat = chat["more"].flag }
        let chatKey = member.isEmpty ? "group" : "member:" + member
        if !snap["chats"][chatKey]["last"]["id"].isNull { defaults.set(snap["chats"][chatKey]["last"]["id"].integer, forKey: "seen." + organization + "/" + chatKey) }
        let updatedLive = live["items"].rows
        let itemsChanged = !(await Node.sameRows(liveItems, updatedLive))
        let statusChanged = !(await Node.sameContent(liveStatus, live["status"]))
        let conversationChanged = !(await Node.sameContent(conversation, convo))
        guard selected == selection else { return }
        // A streamed item can arrive during the request or background diff.
        // Do not replace that newer turn with the earlier HTTP snapshot.
        if liveRevision == liveGeneration {
            if itemsChanged { liveItems = updatedLive }
            if statusChanged { liveStatus = live["status"] }
        }
        if conversationChanged { conversation = convo }
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
        let sameOrganization = organization == next.org && !next.org.isEmpty
        inputSuggestions = nil
        mentionEditor?.closeMentions()
        activeSpeech?.stop()
        plainTask?.cancel(); plainTask = nil; plainQueue = []
        persistDraft(); organization = next.org; member = next.member
        let saved = drafts[next.key] ?? ChatDraft(); draft = saved.text; quote = saved.quote; recipients = saved.recipients
        quoteAuthor = saved.quoteAuthor ?? ""; quoteText = saved.quoteText ?? ""
        messages = []; streamRows = []
        // Changing chats within an organization must not tear down its member
        // tree and inspector, then build them again after the same snapshot.
        if !sameOrganization { snapshot = Node() }
        liveItems = []; liveStatus = Node(); conversation = Node(); moreChat = false; historyPagesLoaded = 0
        selectedText = ""; selectedAuthor = ""; selectedTextView = nil
        threadID = ""; threadData = Node(); if pane == "thread" { pane = "overview" }
        file = Node(); fileImage = nil; plain = [:]; plainOne = []; plainPending = []; plainFailed = []; digest = Node(); digestPending = false
        plainMode = defaults.bool(forKey: "plain." + next.org); digestOpen = defaults.bool(forKey: "digest." + next.org)
        overviewMode = defaults.string(forKey: "overview.mode") ?? "direct"
        if record { history.visit(next) }
        if let data = try? JSONEncoder().encode(next) { defaults.set(data, forKey: "selection") }
        recent.removeAll { $0 == next }; recent.insert(next, at: 0); recent = Array(recent.prefix(12))
        if let data = try? JSONEncoder().encode(recent) { defaults.set(data, forKey: "recent") }
        var ancestor = next.org, seen: Set<String> = []
        while !ancestor.isEmpty, seen.insert(ancestor).inserted { folded.remove(ancestor); ancestor = organizations.first { $0["id"].text == ancestor }?["parent"].text ?? "" }
        defaults.set(Array(folded), forKey: "folded")
    }
    func select(_ org: String, _ member: String = "", record: Bool = true) async throws {
        let next = ChatSelection(org, member)
        // Clicking the active chat refreshes it without throwing away loaded
        // history, its view identities, the draft, or the current scroll offset.
        if next != selection { setSelection(next, record: record) }
        try await refresh()
        if digestOpen { try await loadDigest(false) }
    }
    func navigate(_ delta: Int) { guard let next = history.move(delta) else { return }; run { try await self.select(next.org, next.member, record: false) } }
    func loadOlder() async throws {
        guard !loadingOlder else { return }
        loadingOlder = true; defer { loadingOlder = false }
        let selected = selection, before = messages.first(where: { Int($0["id"].text) != nil })?["id"].text ?? ""
        guard !before.isEmpty else { moreChat = false; return }
        let result = try await get(selected.path("/chat?kind=" + (member.isEmpty ? "group" : "private") + "&member=" + Client.segment(member) + "&limit=200&before=" + Client.segment(before)))
        guard selected == selection else { return }
        guard await mergeMessages(result["items"].rows, selected: selected, prepend: true) else { return }
        historyPagesLoaded += 1
        UIWorkTrace.gauge("history_pages_loaded", historyPagesLoaded)
        moreChat = result["more"].flag
    }
    private func mergeMessages(_ incoming: [Node], selected: ChatSelection, prepend: Bool = false) async -> Bool {
        while selected == selection && !Task.isCancelled {
            let generation = messageGeneration, current = messages
            let merged = await Timeline.mergeInBackground(prepend ? incoming : current, prepend ? current : incoming)
            let changed = !(await Node.sameRows(current, merged))
            guard selected == selection else { return false }
            // A refresh and an older page can finish together. Rebase onto the
            // latest immutable array instead of overwriting the other response.
            if generation == messageGeneration { if changed { messages = merged }; return true }
        }
        return false
    }
    func send() async throws {
        guard !sending, !organization.isEmpty, !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !quote.isEmpty else { return }
        activeSpeech?.stop()
        sending = true; defer { sending = false }
        let selected = selection, original = draft, body = draft.trimmingCharacters(in: .whitespacesAndNewlines), quoted = quote, to = recipients
        do { _ = try await post(selected.path("/send"), Composer.message(body: body, member: selected.member, selected: to, members: members, quote: quoted)) }
        catch { throw RelicError.message(t("composer.send_failed", ["error": error.localizedDescription])) }
        if selected == selection {
            if draft == original { draft = "" }; if quote == quoted { quote = "" }; if recipients == to { recipients = ["all"] }; persistDraft()
        } else if drafts[selected.key]?.text == original {
            drafts[selected.key] = ChatDraft()
            if let data = try? JSONEncoder().encode(drafts) { defaults.set(data, forKey: "drafts") }
        }
        try await refresh()
    }
    func savePreferences(_ changes: [String: Any]) async throws {
        do { let saved = try await post("/api/prefs", changes); preferences = Node(preferences.object.merging(saved.object) { _, new in new }) } catch { throw RelicError.message(t("prefs.save_failed", ["error": error.localizedDescription])) }
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
    func openCard(_ name: String, anchor: CGRect? = nil) {
        cardMember = name
        let sidebarWidth = sidebarOpen ? InspectorGeometry.sidebarWidth(window: windowSize.width) : 0
        cardAnchor = anchor ?? CGRect(x: sidebarWidth, y: 40, width: max(0, windowSize.width - sidebarWidth - (panelOpen ? 340 : 0)), height: 56)
        sheet = .card
    }
    func openDetails(_ tab: String, member: String = "", task: String = "", filter: String = "open") { detailTab = tab; detailDocument = ""; detailMember = member.isEmpty ? self.member : member; detailTask = task; detailFilter = task.isEmpty ? filter : "all"; sheet = .details }
    func setPane(_ value: String) { pane = value; panelOpen = true; if value != "thread" { defaults.set(value, forKey: "pane") } }
    func togglePane(_ value: String) { if pane == value && panelOpen { panelOpen = false } else { setPane(value) } }
    func quoteSelection() {
        if let view = NSApp.keyWindow?.firstResponder as? NSTextView, view.selectedRange().length > 0 {
            setQuote((view.string as NSString).substring(with: view.selectedRange()), from: view === selectedTextView && !selectedAuthor.isEmpty ? selectedAuthor : t("common.quote"))
            view.setSelectedRange(NSRange(location: view.selectedRange().location, length: 0))
        } else if !selectedText.isEmpty { setQuote(selectedText, from: selectedAuthor.isEmpty ? t("common.quote") : selectedAuthor) }
        else { notice = t("appmenu.quote_need_selection") }
        selectedText = ""; selectedAuthor = ""; selectedTextView = nil
    }
    func toggleFold(_ id: String) { Tree.toggle(id, folded: &folded); defaults.set(Array(folded), forKey: "folded") }
    func setQuote(_ body: String, from: String, stripExisting: Bool = false) {
        let trimmed = body.trimmingCharacters(in: .whitespacesAndNewlines)
        var lines = trimmed.components(separatedBy: "\n"); if stripExisting { while lines.first?.hasPrefix(">") == true { lines.removeFirst() } }
        while lines.first?.isEmpty == true { lines.removeFirst() }; guard !lines.isEmpty else { return }
        let text = lines.joined(separator: "\n"); let preview = text.count > 1200 ? String(text.prefix(1200)) + "…" : text
        lines = preview.components(separatedBy: "\n")
        lines[0] = t("sel.quote_line", ["who": name(from), "text": lines[0]])
        quote = lines.map { "> " + $0 }.joined(separator: "\n")
        quoteAuthor = name(from); quoteText = preview; persistDraft()
    }
    func openThread(_ id: String) async throws { if pane != "thread" { threadPreviousPane = pane }; threadID = id; threadDraft = defaults.string(forKey: "thread." + organization + "/" + id) ?? ""; setPane("thread"); try await loadThread() }
    func closeThread() { threadID = ""; threadData = Node(); setPane(threadPreviousPane) }
    func loadThread() async throws {
        let selected = selection, id = threadID; guard !id.isEmpty else { return }
        let result = try await get(selected.path("/thread?root=" + Client.segment(id)))
        if selected == selection, id == threadID { threadData = result }
    }
    func sendThread() async throws {
        guard !threadSending, !threadID.isEmpty else { return }
        let selected = selection, id = threadID, original = threadDraft, body = threadDraft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !body.isEmpty || !quote.isEmpty else { return }
        threadSending = true; defer { threadSending = false }; activeSpeech?.stop()
        let quoted = quote
        _ = try await post(selected.path("/send"), Composer.message(body: body, member: selected.member, selected: [], members: [], quote: quoted, replyTo: id))
        let key = "thread." + selected.org + "/" + id
        if defaults.string(forKey: key) == original { defaults.removeObject(forKey: key) }
        if selected == selection, id == threadID, threadDraft == original { threadDraft = ""; if quote == quoted { quote = "" } }
        try await loadThread(); schedule()
    }
    func openFile(_ path: String, line: Int = 0) async throws {
        let selected = selection, request = UUID(); fileRequest = request
        file = Node(["path": path]); fileImage = nil; fileLine = line; setPane("files")
        do {
            let result = try await get("/api/fs/read?path=" + Client.segment(path))
            var image: NSImage?
            if result["kind"].text == "image" { image = NSImage(data: try await bytes("/api/fs/raw?path=" + Client.segment(path))) }
            guard selection == selected, fileRequest == request else { return }
            file = result; fileImage = image
        } catch {
            guard selection == selected, fileRequest == request else { return }
            file = Node(["path": path, "error": error.localizedDescription])
        }
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
