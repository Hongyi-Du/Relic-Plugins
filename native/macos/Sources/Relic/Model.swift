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
        set {
            guard newValue != presentedAppMenu else { return }
            if newValue != nil {
                mentionEditor?.closeMentions()
                if recipientPicker { recipientPicker = false }
            }
            presentedAppMenu = newValue
        }
    }
    let dialogPresentation = DialogPresentation()
    // The toolbar reads only the monitor's working count; the panel reads the rest while it is open.
    let monitor = MonitorState()
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
    var threadData = Node() { didSet { if threadData["root"].isNull { threadRows = [] } } }
    var threadRows: [ConversationRow] = []
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
    @ObservationIgnored private var conversationTaskID: UUID?
    var isPreparingConversation: Bool { conversationTask != nil }
    @ObservationIgnored private var conversationGeneration = 0
    @ObservationIgnored private var preparationSuspended = 0
    @ObservationIgnored private var navigationGeneration = 0
    @ObservationIgnored private var navigationTask: Task<Void, Error>?
    @ObservationIgnored private var pendingNavigation: ChatSelection?
    var isLoadingSelectedChat: Bool { navigationTask != nil }
    @ObservationIgnored private(set) var selectedChatLoadVersion = 0
    @ObservationIgnored private var refreshAfterNavigation = false
    @ObservationIgnored private var messageGeneration = 0
    @ObservationIgnored private var liveGeneration = 0
    @ObservationIgnored private var fileRequest = UUID()
    @ObservationIgnored private var previousDecisions: [String: Set<String>] = [:]
    @ObservationIgnored private var previousMessages: [String: String] = [:]
    @ObservationIgnored private var previousCopies: Int?
    enum Sheet: String, Identifiable {
        case create, member, settings, copies, chart, protocolForm, card, secretary, forward, details, shortcuts, monitor
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
            monitor.tick(client)
            eventTask = Task { [weak self] in
                guard let client = self?.client else { return }
                await client.events { [weak self] event in await self?.receive(event) }
            }
        } catch { self.error = error.localizedDescription; ready = false; client = nil; host.stop() }
    }
    func receive(_ event: Node) async {
        let type = event["type"].text
        if type == "shutdown" { ready = false; error = t("state.idle"); eventTask?.cancel(); client = nil; host.stop(); return }
        // Members' work announces itself here; the monitor's toolbar count follows it at most every 15 s.
        if type != "install" { monitor.tick(client) }
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
        if let next = pendingNavigation, next != selection, event["org"].text == next.org,
           ["org", "decision"].contains(type) || type == "live" && event["member"].text == next.member {
            // The old chat remains selected until the new document is ready.
            // Fetch any target events that arrived after its in-flight reply.
            refreshAfterNavigation = true
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
    func stop() { inputSuggestions = nil; toasts = []; activeSpeech?.stop(); persistDraft(); eventTask?.cancel(); refreshTask?.cancel(); plainTask?.cancel(); conversationTask?.cancel(); navigationTask?.cancel(); host.stop() }
    private func prepareConversation() {
        conversationGeneration += 1
        guard preparationSuspended == 0, conversationTask == nil else { return }
        let taskID = UUID(); conversationTaskID = taskID
        conversationTask = Task { [weak self] in
            guard let self else { return }
            defer {
                if self.conversationTaskID == taskID { self.conversationTask = nil; self.conversationTaskID = nil }
            }
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
        // A click owns its own current-chat request. Background global refresh
        // must not put it behind the previous chat or publish an older snapshot.
        guard navigationTask == nil else { refreshAfterNavigation = true; return }
        let selected = selection
        let navigation = navigationGeneration
        startupStage?("snapshot")
        let snap = try await get(selected.path("?lang=" + words.language))
        let chatQuery = selected.member.isEmpty ? "/chat?kind=group&limit=200"
            : "/chat?kind=private&member=" + Client.segment(selected.member) + "&limit=200"
        let chat = try await get(selected.path(chatQuery))
        startupStage?("history")
        let who = snap["members"].rows.first { $0["name"].text == selected.member } ?? Node()
        let liveRevision = liveGeneration
        var live = Node(), convo = Node()
        if who["embedded"].flag { live = try await get(selected.path("/live?member=" + Client.segment(selected.member))) }
        if who["has_transcript"].flag { convo = try await get(selected.path("/convo?member=" + Client.segment(selected.member))) }
        guard selected == selection, navigation == navigationGeneration else { return }
        let hadHistory = !messages.isEmpty
        guard await mergeMessages(chat["items"].rows, selected: selected, navigation: navigation) else { return }
        startupStage?("publish")
        let snapshotChanged = !(await Node.sameContent(snapshot, snap))
        guard selected == selection, navigation == navigationGeneration else { return }
        if snapshotChanged { snapshot = snap; revision += 1 }
        if !hadHistory { moreChat = chat["more"].flag }
        let chatKey = member.isEmpty ? "group" : "member:" + member
        if !snap["chats"][chatKey]["last"]["id"].isNull { defaults.set(snap["chats"][chatKey]["last"]["id"].integer, forKey: "seen." + organization + "/" + chatKey) }
        let updatedLive = live["items"].rows
        let itemsChanged = !(await Node.sameRows(liveItems, updatedLive))
        let statusChanged = !(await Node.sameContent(liveStatus, live["status"]))
        let conversationChanged = !(await Node.sameContent(conversation, convo))
        guard selected == selection, navigation == navigationGeneration else { return }
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
        navigationGeneration += 1; navigationTask?.cancel(); navigationTask = nil; pendingNavigation = nil
        changeSelection(next, record: record, clearContent: true)
    }
    private func changeSelection(_ next: ChatSelection, record: Bool, clearContent: Bool) {
        let sameOrganization = organization == next.org && !next.org.isEmpty
        // Every Observation write invalidates each view that read the field,
        // even when the value is unchanged: all mounted messages read the
        // plain-language state, the inspector its mode, the sidebar the folds.
        // A chat switch writes only the fields whose values actually change.
        if inputSuggestions != nil { inputSuggestions = nil }
        mentionEditor?.closeMentions()
        activeSpeech?.stop()
        plainTask?.cancel(); plainTask = nil; plainQueue = []
        persistDraft()
        if organization != next.org { organization = next.org }
        if member != next.member { member = next.member }
        let saved = drafts[next.key] ?? ChatDraft()
        if draft != saved.text { draft = saved.text }
        if quote != saved.quote { quote = saved.quote }
        if recipients != saved.recipients { recipients = saved.recipients }
        if quoteAuthor != (saved.quoteAuthor ?? "") { quoteAuthor = saved.quoteAuthor ?? "" }
        if quoteText != (saved.quoteText ?? "") { quoteText = saved.quoteText ?? "" }
        if clearContent {
            messages = []; streamRows = []
            // Direct resets still discard the old chat. Network navigation
            // replaces these fields with prepared data in one publication.
            if !sameOrganization { snapshot = Node() }
            liveItems = []; liveStatus = Node(); conversation = Node()
        }
        if moreChat { moreChat = false }
        if historyPagesLoaded != 0 { historyPagesLoaded = 0 }
        if !selectedText.isEmpty { selectedText = "" }
        if !selectedAuthor.isEmpty { selectedAuthor = "" }
        selectedTextView = nil
        if !threadID.isEmpty { threadID = "" }
        if !threadData.object.isEmpty { threadData = Node() }
        if pane == "thread" { pane = "overview" }
        if !file.object.isEmpty { file = Node() }
        if fileImage != nil { fileImage = nil }
        if !plain.isEmpty { plain = [:] }
        if !plainOne.isEmpty { plainOne = [] }
        if !plainPending.isEmpty { plainPending = [] }
        if !plainFailed.isEmpty { plainFailed = [] }
        if !digest.object.isEmpty { digest = Node() }
        if digestPending { digestPending = false }
        let nextPlain = defaults.bool(forKey: "plain." + next.org), nextDigest = defaults.bool(forKey: "digest." + next.org)
        if plainMode != nextPlain { plainMode = nextPlain }
        if digestOpen != nextDigest { digestOpen = nextDigest }
        let nextOverview = defaults.string(forKey: "overview.mode") ?? "direct"
        if overviewMode != nextOverview { overviewMode = nextOverview }
        if record { history.visit(next) }
        if let data = try? JSONEncoder().encode(next) { defaults.set(data, forKey: "selection") }
        var updatedRecent = recent
        updatedRecent.removeAll { $0 == next }; updatedRecent.insert(next, at: 0); updatedRecent = Array(updatedRecent.prefix(12))
        if updatedRecent != recent {
            recent = updatedRecent
            if let data = try? JSONEncoder().encode(recent) { defaults.set(data, forKey: "recent") }
        }
        var updatedFolds = folded, ancestor = next.org, seen: Set<String> = []
        while !ancestor.isEmpty, seen.insert(ancestor).inserted { updatedFolds.remove(ancestor); ancestor = organizations.first { $0["id"].text == ancestor }?["parent"].text ?? "" }
        if updatedFolds != folded { folded = updatedFolds; defaults.set(Array(folded), forKey: "folded") }
    }
    func select(_ org: String, _ member: String = "", record: Bool = true) async throws {
        let next = ChatSelection(org, member)
        if next.org.isEmpty { setSelection(next, record: record); return }
        // Keep the actual selection and native document intact while fetching
        // and preparing the replacement. Clearing a 1,000-row lazy document
        // first makes SwiftUI tear it down, lay out an empty chat and recreate
        // it in another transaction; a failed request also loses the old chat.
        navigationGeneration += 1
        let generation = navigationGeneration
        navigationTask?.cancel()
        pendingNavigation = next
        let task = Task { try await self.loadSelectedChat(next, generation: generation, record: record) }
        navigationTask = task
        defer {
            if generation == navigationGeneration {
                navigationTask = nil; pendingNavigation = nil
                if refreshAfterNavigation { refreshAfterNavigation = false; schedule() }
            }
        }
        do { try await task.value }
        catch {
            if task.isCancelled || generation != navigationGeneration { return }
            throw error
        }
        guard generation == navigationGeneration else { return }
        if digestOpen { try await loadDigest(false) }
    }

    private func loadSelectedChat(_ selected: ChatSelection, generation: Int, record: Bool) async throws {
        guard !selected.org.isEmpty else { return }
        let query = selected.member.isEmpty ? "/chat?kind=group&limit=200"
            : "/chat?kind=private&member=" + Client.segment(selected.member) + "&limit=200"
        // Like the reference, a chat switch inside the open organization only
        // loads that chat. Event-driven refreshes keep this snapshot current;
        // re-reading the whole organization doubled the server work per click.
        let current: Node? = selected.org == organization && snapshot["org"]["id"].text == selected.org ? snapshot : nil
        async let snapshotRequest = organizationSnapshot(current, path: selected.path("?lang=" + words.language))
        async let chatRequest = get(selected.path(query))
        let snap = try await snapshotRequest
        let who = snap["members"].rows.first { $0["name"].text == selected.member } ?? Node()
        let requestedLiveRevision = liveGeneration
        async let liveRequest = optionalChatResource(who["embedded"].flag, path: selected.path("/live?member=" + Client.segment(selected.member)))
        async let transcriptRequest = optionalChatResource(who["has_transcript"].flag, path: selected.path("/convo?member=" + Client.segment(selected.member)))
        let (chat, live, transcript) = try await (chatRequest, liveRequest, transcriptRequest)
        while !Task.isCancelled, generation == navigationGeneration {
            let sameChat = selected == selection
            let messageRevision = messageGeneration, liveRevision = liveGeneration, presentationRevision = conversationGeneration
            let current = sameChat ? messages : []
            // A live event for the still-visible chat can arrive while its
            // refresh request is in flight. Preserve that newer native turn.
            let useLiveReply = !sameChat || requestedLiveRevision == liveRevision
            let nextLive = useLiveReply ? live["items"].rows : liveItems
            let nextStatus = useLiveReply ? live["status"] : liveStatus
            let merged = await Timeline.mergeInBackground(current, chat["items"].rows)
            let sameMessages = await Node.sameRows(current, merged)
            let sameSnapshot = await Node.sameContent(snapshot, snap)
            let sameLive = await Node.sameRows(liveItems, nextLive)
            let sameStatus = await Node.sameContent(liveStatus, nextStatus)
            let sameTranscript = await Node.sameContent(conversation, transcript)
            let changed = !sameChat || !sameSnapshot || !sameMessages || !sameLive || !sameStatus || !sameTranscript
            let rows = changed ? await ConversationRow.prepare(messages: merged, steps: transcript["steps"].rows,
                member: who, live: nextLive, status: nextStatus, decisions: snap["decisions"].rows,
                words: words, now: displayNow, privateChat: !selected.member.isEmpty) : streamRows
            guard !Task.isCancelled, generation == navigationGeneration else { return }
            // Rebase a current-chat refresh if history or SSE advanced while
            // the background projection was running. New-chat replies never
            // merge the old displayed chat's messages into the requested chat.
            guard messageRevision == messageGeneration, liveRevision == liveGeneration,
                  presentationRevision == conversationGeneration else { continue }
            if changed {
                // A canceled projection can finish later. Its identity-guarded
                // defer must not clear a worker for a subsequent live update.
                conversationTask?.cancel(); conversationTask = nil; conversationTaskID = nil
                conversationGeneration += 1
                preparationSuspended += 1
                if !sameChat { changeSelection(selected, record: record, clearContent: false) }
                if !sameSnapshot { snapshot = snap; revision += 1 }
                if !sameMessages || !sameChat { messages = merged }
                if !sameChat || current.isEmpty { moreChat = chat["more"].flag }
                if !sameLive { liveItems = nextLive }
                if !sameStatus { liveStatus = nextStatus }
                if !sameTranscript { conversation = transcript }
                preparationSuspended -= 1
                streamRows = rows; streamVersion += 1
            }
            let key = selected.member.isEmpty ? "group" : "member:" + selected.member
            if !snap["chats"][key]["last"]["id"].isNull {
                defaults.set(snap["chats"][key]["last"]["id"].integer, forKey: "seen." + selected.org + "/" + key)
            }
            selectedChatLoadVersion += 1
            return
        }
    }
    private func optionalChatResource(_ enabled: Bool, path: String) async throws -> Node {
        if enabled { return try await get(path) }
        return Node()
    }
    private func organizationSnapshot(_ current: Node?, path: String) async throws -> Node {
        if let current { return current }
        return try await get(path)
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
    private func mergeMessages(_ incoming: [Node], selected: ChatSelection, prepend: Bool = false, navigation: Int? = nil) async -> Bool {
        while selected == selection && !Task.isCancelled && (navigation == nil || navigation == navigationGeneration) {
            let generation = messageGeneration, current = messages
            let merged = await Timeline.mergeInBackground(prepend ? incoming : current, prepend ? current : incoming)
            let changed = !(await Node.sameRows(current, merged))
            guard selected == selection, navigation == nil || navigation == navigationGeneration else { return false }
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
    func openThread(_ id: String) async throws {
        if pane != "thread" { threadPreviousPane = pane }
        if threadID != id { threadData = Node() }
        threadID = id; threadDraft = defaults.string(forKey: "thread." + organization + "/" + id) ?? ""
        setPane("thread"); try await loadThread()
    }
    func closeThread() { threadID = ""; threadData = Node(); setPane(threadPreviousPane) }
    func loadThread() async throws {
        let selected = selection, id = threadID; guard !id.isEmpty else { return }
        let result = try await get(selected.path("/thread?root=" + Client.segment(id)))
        guard selected == selection, id == threadID else { return }
        let rows = await ConversationRow.prepareReplies(result["replies"].rows, words: words, now: displayNow)
        if selected == selection, id == threadID { threadRows = rows; threadData = result }
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
