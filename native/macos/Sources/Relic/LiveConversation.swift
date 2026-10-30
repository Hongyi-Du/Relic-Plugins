import SwiftUI
import RelicCore

struct LiveTurnView: View {
    @EnvironmentObject var m: Model
    private var turn: LivePresentation { LivePresentation(items: m.displayLiveItems, status: m.liveStatus, member: m.selectedMember) }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let prompt = turn.prompt {
                HStack(alignment: .top, spacing: 10) {
                    liveBubble(prompt["text"].text, mine: true).frame(maxWidth: .infinity, alignment: .trailing)
                    Avatar(member: "human", size: 36)
                }.padding(.top, messageGap).environment(\.selectedAuthor, "human")
            }
            HStack(alignment: .top, spacing: 10) {
                MemberCardButton(member: m.member) { Avatar(member: m.member, size: 36) }.buttonStyle(.plain).accessibilityLabel("")
                VStack(alignment: .leading, spacing: 4) {
                    FlowLayout(spacing: 6) {
                        ReferenceLabel(m.name(m.member), size: 12.5, weight: 600, color: RelicStyle.secondary, lineHeight: 16.25)
                        ReferenceLabel(turn.running ? m.t("live.replying") : m.stateLabel(m.liveStatus["state"].text), size: 12, color: RelicStyle.muted, lineHeight: 15.6)
                    }
                    if !turn.actions.isEmpty { LiveActions(items: turn.actions) }
                    if !turn.reply.isEmpty { liveBubble(turn.reply) }
                    else if turn.showsTyping { TypingIndicator().frame(width: 30, height: 18) }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }.padding(.top, messageGap).environment(\.selectedAuthor, m.member)
        }
    }
    private var messageGap: CGFloat { m.preferences["density"].text == "compact" ? 7 : 14 }
    private func liveBubble(_ text: String, mine: Bool = false) -> some View {
        RichText(text).padding(.horizontal, 13).padding(.vertical, 9)
            .modifier(RecordedSurface(background: mine ? RelicStyle.mine : RelicStyle.bubble, radius: 14, kind: "card", cornerRadii: mine ? [14,4,14,14] : [4,14,14,14]))
            .frame(maxWidth: 720, alignment: mine ? .trailing : .leading)
    }
}

private struct LiveActions: View {
    @EnvironmentObject var m: Model
    @Environment(\.conversationDisclosure) private var preserveScroll
    let items: [Node]
    @State private var expanded = true
    @State private var identity = "relic-text-button/live-actions/" + UUID().uuidString
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { if !items.isEmpty { preserveScroll() }; expanded.toggle() } label: {
                HStack(spacing: 8) {
                    ReferenceIcon(name: "chev", size: 13, color: RelicStyle.muted, owner: identity).rotationEffect(.degrees(expanded ? 90 : 0))
                    ReferenceLabel(m.t("live.turn_actions"), size: 12.5, weight: 600, color: RelicStyle.secondary, lineHeight: 20, owner: identity)
                    Spacer(minLength: 0)
                }.padding(.horizontal, 10).padding(.vertical, 6).contentShape(Rectangle())
                    .modifier(RecordedSurface(background: .clear, owner: identity, expanded: expanded))
            }.buttonStyle(.plain).accessibilityIdentifier(identity)
            if expanded {
                VStack(alignment: .leading, spacing: 0) { Rows(items) { LiveItem(item: $0) } }
                    .padding(.vertical, 4).padding(.top, 1)
                    .modifier(RecordedSurface(background: .clear, border: RelicStyle.line, edges: EdgeInsets(top: 1, leading: 0, bottom: 0, trailing: 0), kind: "card"))
            }
        }.padding(1).frame(maxWidth: 720, alignment: .leading)
            .modifier(RecordedSurface(background: RelicStyle.background, border: RelicStyle.line, borderWidth: 1, radius: 10, kind: "card"))
    }
}

struct LiveItem: View {
    let item: Node
    var body: some View {
        switch item["type"].text {
        case "permission": PermissionCard(item: item)
        case "tool": LiveToolRow(item: item)
        case "error":
            NoticeLayout {
                ReferenceLabel(item["text"].text, size: 12, color: RelicStyle.red, lines: 0, alignment: .center)
                    .padding(.horizontal, 10).padding(.vertical, 2).modifier(RecordedSurface(background: RelicStyle.sidebar, radius: 10, kind: "card"))
            }.padding(.vertical, 8)
        default: EmptyView()
        }
    }
}

private struct LiveToolRow: View {
    @EnvironmentObject var m: Model
    @Environment(\.conversationDisclosure) private var preserveScroll
    let item: Node
    @State private var expanded = false
    @State private var hovering = false
    private var identity: String { "relic-row/live-tool/" + item["id"].text }
    private var dot: Color { item["status"].text == "completed" ? RelicStyle.green : item["status"].text == "failed" ? RelicStyle.red : RelicStyle.faint }
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { if !item["text"].text.isEmpty { preserveScroll() }; expanded.toggle() } label: {
                HStack(spacing: 8) {
                    Color.clear.frame(width: 7, height: 7).modifier(RecordedSurface(background: dot, radius: 3.5, kind: "card"))
                    ReferenceLabel(ReferenceText.clip(item["title"].text, to: 60), size: 12.5, weight: 600, lineHeight: 20, owner: identity).fixedSize()
                    Spacer(minLength: 0)
                    ReferenceLabel(LivePresentation.toolState(item["status"].text, words: m.words), size: 11, color: RelicStyle.muted, lineHeight: 17.6, owner: identity).fixedSize()
                }.environment(\.nativeElementParent, identity)
                    .padding(.leading, 12).padding(.trailing, 10).padding(.vertical, 3).contentShape(Rectangle())
                    .modifier(RecordedSurface(background: hovering ? RelicStyle.sidebar : .clear, owner: identity, hovered: hovering, expanded: expanded))
            }.buttonStyle(.plain).accessibilityIdentifier(identity)
                .accessibilityLabel(ReferenceText.clip(item["title"].text, to: 60) + " " + LivePresentation.toolState(item["status"].text, words: m.words))
                .onHover { hovering = $0 }
            if expanded && !item["text"].text.isEmpty {
                LiveToolOutput(text: item["text"].text).padding(.leading, 27).padding(.trailing, 10).padding(.top, 2).padding(.bottom, 8)
                    .accessibilityIdentifier("relic-live-output/" + item["id"].text)
            }
        }
    }
}

private struct LiveToolOutput: View {
    let text: String
    var body: some View {
        ViewThatFits(in: .vertical) {
            output
            ScrollView { output }
        }.frame(maxHeight: 360, alignment: .topLeading)
    }
    private var output: some View {
        SelectableText(value: AttributedString(text), pointSize: 11.5, lineHeight: 17.825, monospaced: true, uniformSource: true)
            .padding(.horizontal, 10).padding(.vertical, 8).frame(maxWidth: .infinity, alignment: .leading)
            .modifier(RecordedSurface(background: RelicStyle.code, border: RelicStyle.line, borderWidth: 1, radius: 7, kind: "code"))
    }
}
