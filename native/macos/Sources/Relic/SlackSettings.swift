import SwiftUI
import AppKit
import RelicCore

// Settings > Slack (relic_core/slack.py), the same page as native/windows/Relic/SlackSettings.cs. The person connects
// a read-only Slack app of their own and chooses what each organization may read. The token goes from the secure
// field to the local Relic App service once and is never shown again: every answer from the service carries the
// connection only. A choice is saved as soon as it changes.
struct SlackSettings: View {
    @EnvironmentObject var m: Model
    @State private var state: Node?
    @State private var failure = ""
    @State private var conversations: [SlackText.Conversation]?
    @State private var loadingConversations = false
    /// Mode and direct messages change what the organizations below follow: an answer to such a change, like a new
    /// connection, draws every row again from it, as on Windows. A conversation ticked on a list does not.
    @State private var revision = 0
    /// Choices are saved one after another, so an earlier click never lands after a later one.
    @State private var saving: Task<Void, Never>?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ReferenceLabel(m.t("slack.intro"), size: 12.5, color: RelicStyle.muted, lineHeight: 21.25, lines: 0).padding(.bottom, 6)
            if let state {
                if state["connected"].flag {
                    SlackConnection(state: state) { redraw($0, connection: true) }
                } else {
                    SlackSetup(state: state) { redraw($0, connection: true) }
                }
                scopes(state)
                reads(state)
            } else if !failure.isEmpty {
                ReferenceLabel(m.t("slack.load_failed", ["error": failure]), size: 12.5, color: RelicStyle.muted, lines: 0)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .task { await load() }
    }

    private func load() async {
        do {
            let answer = try await m.get("/api/slack")
            redraw(answer, connection: true)
        } catch is CancellationError {
        } catch { failure = error.localizedDescription }
    }

    /// Draws the page again from an answer of the service. The conversations are read again when the page opens and
    /// after connecting or disconnecting; otherwise only when the last reading failed.
    private func redraw(_ answer: Node, connection: Bool = false) {
        if connection { conversations = nil }
        state = answer; revision += 1
        guard answer["connected"].flag, conversations == nil, !loadingConversations else { return }
        loadingConversations = true
        Task { @MainActor in
            let list = try? await m.get("/api/slack/conversations")
            loadingConversations = false
            conversations = list.map(SlackText.conversations)
        }
    }

    private func save(_ org: String, mode: String, dms: Bool, chosen: Set<String>, redraws: Bool) {
        let previous = saving
        saving = Task { @MainActor in
            await previous?.value
            do {
                let answer = try await m.post("/api/slack/scope", ["org": org, "mode": mode, "dms": dms, "conversations": chosen.sorted()])
                if redraws { redraw(answer) } else { state = answer }
            } catch is CancellationError {
            } catch { m.error = error.localizedDescription }
        }
    }

    @ViewBuilder private func scopes(_ state: Node) -> some View {
        let connected = state["connected"].flag
        ReferenceLabel(m.t("slack.scopes"), size: 15, weight: 650).padding(.top, 18).padding(.bottom, 2)
        ReferenceLabel(m.t("slack.scopes_hint"), size: 12.5, color: RelicStyle.muted, lines: 0).padding(.bottom, 4)
        ForEach(SlackText.rows(state, defaultName: m.t("slack.default"))) { row in
            SlackScopeRow(row: row, connected: connected, conversations: conversations, loading: loadingConversations) { mode, dms, chosen, redraws in
                save(row.id, mode: mode, dms: dms, chosen: chosen, redraws: redraws)
            }.id(row.id + "#" + String(revision))
        }
    }

    @ViewBuilder private func reads(_ state: Node) -> some View {
        let rows = state["reads"].rows
        ReferenceLabel(m.t("slack.reads"), size: 15, weight: 650).padding(.top, 18).padding(.bottom, 6)
        if rows.isEmpty { ReferenceLabel(m.t("slack.reads_empty"), size: 12.5, color: RelicStyle.muted, lines: 0) }
        ForEach(Array(rows.enumerated()), id: \.offset) { _, read in
            PlainLabel(SlackText.read(read, words: m.words), size: 12.5, color: RelicStyle.muted)
                .fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading).padding(.bottom, 4)
        }
    }
}

@MainActor private func slackCopy(_ text: String, model m: Model) {
    NSPasteboard.general.clearContents()
    m.notice = m.t(NSPasteboard.general.setString(text, forType: .string) ? "slack.copied" : "msg.copy_failed")
}

/// Not connected yet: create the app from the manifest, install it, paste its user token.
private struct SlackSetup: View {
    @EnvironmentObject var m: Model
    let state: Node
    let connected: (Node) -> Void
    @State private var token = ""
    @State private var problem = ""
    @State private var connecting = false
    @FocusState private var tokenFocused: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            SettingsRow(title: m.t("slack.step1"), hint: m.t("slack.step1_hint")) {
                HStack(spacing: 8) {
                    ReferenceActionButton(m.t("slack.copy_manifest"), small: true) { slackCopy(state["manifest"].text, model: m) }
                    ReferenceActionButton(m.t("slack.open_slack"), small: true) {
                        if let url = URL(string: state["create_url"].text), url.scheme == "https" { _ = NSWorkspace.shared.open(url) }
                    }
                }
            }
            SettingsRow(title: m.t("slack.step2"), hint: m.t("slack.step2_hint")) { EmptyView() }
            SettingsRow(title: m.t("slack.step3"), hint: m.t("slack.step3_hint")) {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 8) {
                        SecureField(m.t("slack.step3"), text: $token, prompt: Text(verbatim: "xoxp-…"))
                            .textFieldStyle(.plain).labelsHidden().font(Font(RelicStyle.monoFont(13)))
                            .focused($tokenFocused).onSubmit { connect() }
                            .accessibilityLabel(m.t("slack.step3"))
                            .padding(.horizontal, 10).frame(width: 260, height: 37)
                            .modifier(RecordedSurface(background: RelicStyle.background, border: RelicStyle.border, borderWidth: 1, radius: 9))
                        ReferenceActionButton(m.t("slack.connect"), primary: true, small: true) { connect() }.disabled(connecting)
                    }
                    if !problem.isEmpty {
                        ReferenceLabel(problem, size: 12.5, color: RelicStyle.red, lines: 0).frame(width: 340, alignment: .leading)
                    }
                }
            }
        }
    }
    private func connect() {
        let value = token.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { tokenFocused = true; return }
        guard !connecting else { return }
        connecting = true; problem = ""
        Task { @MainActor in
            do {
                let answer = try await m.post("/api/slack/connect", ["token": value])
                token = ""; connecting = false
                m.notice = m.t("slack.connected_note")
                connected(answer)
            } catch {
                connecting = false
                // The service answers with a word-list key or Slack's own error; neither contains the token.
                if !(error is CancellationError) { problem = SlackText.error(error.localizedDescription, words: m.words) }
            }
        }
    }
}

/// Connected: the workspace and account, permissions the app still lacks, and Disconnect.
private struct SlackConnection: View {
    @EnvironmentObject var m: Model
    let state: Node
    let disconnected: (Node) -> Void
    var body: some View {
        let missing = SlackText.missingScopes(state)
        VStack(alignment: .leading, spacing: 6) {
            SettingsRow(title: m.t("slack.workspace"), hint: SlackText.workspace(state["team"])) { OverviewChip(text: m.t("settings.connected"), tone: "ok") }
            SettingsRow(title: m.t("slack.account"), hint: state["user"]["name"].text) { EmptyView() }
            if !missing.isEmpty {
                SettingsRow(title: m.t("slack.missing"), hint: m.t("slack.missing_hint", ["scopes": missing.joined(separator: ", ")])) {
                    ReferenceActionButton(m.t("slack.copy_manifest"), small: true) { slackCopy(state["manifest"].text, model: m) }
                }
            }
            SettingsRow(title: m.t("slack.disconnect"), hint: m.t("slack.disconnect_hint")) {
                ReferenceActionButton(m.t("slack.disconnect"), small: true) {
                    m.run { disconnected(try await m.post("/api/slack/disconnect", [:])) }
                }
            }
        }
    }
}

/// The default or one organization: what it may read, and the conversations of its list.
private struct SlackScopeRow: View {
    @EnvironmentObject var m: Model
    let row: SlackText.Row
    let connected: Bool
    let conversations: [SlackText.Conversation]?
    let loading: Bool
    let save: (_ mode: String, _ dms: Bool, _ chosen: Set<String>, _ redraws: Bool) -> Void
    @State private var mode: String
    @State private var dms: Bool
    @State private var chosen: Set<String>
    @State private var filter = ""
    init(row: SlackText.Row, connected: Bool, conversations: [SlackText.Conversation]?, loading: Bool,
         save: @escaping (_ mode: String, _ dms: Bool, _ chosen: Set<String>, _ redraws: Bool) -> Void) {
        self.row = row; self.connected = connected; self.conversations = conversations; self.loading = loading; self.save = save
        _mode = State(initialValue: row.mode); _dms = State(initialValue: row.dms); _chosen = State(initialValue: row.chosen)
    }
    private var note: String {
        SlackText.note(mode: mode, dms: dms, chosen: chosen.count, effective: row.effective, source: row.source, sourceName: row.sourceName, words: m.words)
    }
    private var choice: Binding<String> {
        Binding(get: { mode }, set: { next in
            guard next != mode else { return }
            mode = next; save(next, dms, chosen, true)
        })
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .center, spacing: 16) {
                VStack(alignment: .leading, spacing: 2) {
                    ReferenceLabel(row.name, size: 13.5, weight: 600, lines: 0)
                    ReferenceLabel(note, size: 12.5, color: RelicStyle.muted, lines: 0)
                }.frame(maxWidth: .infinity, alignment: .leading)
                HStack(spacing: 10) {
                    if mode == "all" {
                        SlackCheck(title: m.t("slack.dms"), checked: dms) { value in dms = value; save(mode, value, chosen, true) }
                    }
                    ReferenceSelectField(title: row.name, selection: choice,
                                         options: SlackText.modes(isDefault: row.isDefault).map { ($0, SlackText.mode($0, words: m.words)) }, pointSize: 13)
                        .frame(width: 150)
                }.fixedSize()
            }
            .padding(.leading, CGFloat(row.indent)).padding(.vertical, 10)
            .modifier(RecordedSurface(background: .clear, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 1, trailing: 0), kind: "card"))
            if mode == "list" {
                picker.padding(.leading, CGFloat(row.indent)).padding(.top, 4).padding(.bottom, 10)
            }
        }
    }
    @ViewBuilder private var picker: some View {
        VStack(alignment: .leading, spacing: 6) {
            if !connected {
                quiet(m.t("slack.pick_needs_connection"))
            } else if let conversations {
                ReferenceInput(placeholder: m.t("slack.filter"), text: $filter, height: 36, pointSize: 13, voice: false).frame(width: 240)
                FittingScroll(maxHeight: 260) {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        ForEach(SlackText.filter(conversations, query: filter)) { item in
                            SlackCheck(title: item.label + " · " + SlackText.kind(item.kind, words: m.words), checked: chosen.contains(item.id)) { value in
                                var next = chosen
                                if value { next.insert(item.id) } else { next.remove(item.id) }
                                chosen = next; save("list", dms, next, false)
                            }
                        }
                    }
                }
            } else if loading {
                quiet(m.t("common.loading"))
            } else {
                quiet(m.t("slack.pick_failed"))
            }
        }
    }
    private func quiet(_ text: String) -> some View { ReferenceLabel(text, size: 12.5, color: RelicStyle.muted, lines: 0) }
}

/// A checkbox with its label; clicking either toggles it.
private struct SlackCheck: View {
    let title: String
    let checked: Bool
    let change: (Bool) -> Void
    var body: some View {
        Button { change(!checked) } label: {
            HStack(spacing: 8) {
                NativeCheck(checked: .constant(checked)).frame(width: 16, height: 16).allowsHitTesting(false)
                PlainLabel(title, size: 13).lineLimit(1).truncationMode(.tail)
            }.padding(.vertical, 3).contentShape(Rectangle())
        }.buttonStyle(.plain).help(title).accessibilityLabel(title).accessibilityAddTraits(checked ? .isSelected : [])
    }
}
