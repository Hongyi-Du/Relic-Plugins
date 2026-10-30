import SwiftUI
import RelicCore

struct Sidebar: View {
    @EnvironmentObject var m: Model
    @FocusState private var focused: Bool
    var body: some View {
        VStack(spacing: 0) {
            VStack(spacing: 2) {
                Button { m.sheet = .create } label: {
                    HStack(spacing: 10) { ReferenceIcon(name: "neworg"); ReferenceLabel(m.t("common.new_org"), lines: 0); Spacer(minLength: 0) }.padding(.horizontal, 10).frame(height: 34)
                }.buttonStyle(QuietButtonStyle())
                HStack(spacing: 8) {
                    ReferenceIcon(name: "search", size: 16, color: RelicStyle.muted)
                    TextField(m.t("page.search"), text: $m.search).textFieldStyle(.plain).focused($focused)
                    VoiceButton(text: $m.search).labelStyle(.iconOnly)
                }.padding(.horizontal, 10).frame(height: 34).modifier(RecordedSurface(background: RelicStyle.hover, radius: 8, kind: "card"))
            }.padding(.horizontal, 8).padding(.top, 10).padding(.bottom, 6)
            ScrollView {
                VStack(spacing: 0) {
                    HStack {
                        ReferenceLabel(m.t("page.tree"), size: 12, color: RelicStyle.muted, lines: 0); Spacer()
                        if !m.organizations.isEmpty { ReferenceLabel(String(m.organizations.count), size: 12, color: RelicStyle.muted, lines: 0) }
                    }.padding(.horizontal, 10).padding(.top, 14).padding(.bottom, 6)
                    Rows(m.organizations.filter { node in node["parent"].text.isEmpty || !m.organizations.contains { $0["id"].text == node["parent"].text } }) { OrgTree(node: $0, ancestors: []) }
                    if m.organizations.isEmpty { Text(m.t("side.no_orgs")).foregroundStyle(RelicStyle.muted).padding(.horizontal, 10).padding(.vertical, 8).frame(maxWidth: .infinity, alignment: .leading) }
                }.padding(.horizontal, 8).padding(.top, 4).padding(.bottom, 12)
            }.frame(maxHeight: .infinity)
            RelicStyle.line.frame(height: 1)
            HStack(spacing: 4) {
                Button { m.sheet = .settings } label: {
                    HStack(spacing: 10) {
                        Avatar(member: "human", size: 28)
                        VStack(alignment: .leading, spacing: 0) {
                            ReferenceLabel(m.name("human"), size: 13.3, weight: 600)
                            ReferenceLabel(m.t("side.profile"), size: 11.5, color: RelicStyle.muted)
                        }
                        Spacer(minLength: 0)
                    }.padding(.vertical, 6).padding(.horizontal, 8)
                }.buttonStyle(QuietButtonStyle()).help(m.t("page.me"))
                IconButton(title: m.t("common.settings"), icon: "gear") { m.sheet = .settings }
            }.padding(8)
        }.padding(.trailing, 1).modifier(RecordedSurface(background: RelicStyle.sidebar, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 0, trailing: 1), kind: "region"))
            .accessibilityElement(children: .contain).accessibilityLabel(m.t("page.side"))
            .onChange(of: m.focusSearch) { if m.focusSearch { focused = true; m.focusSearch = false } }
    }
}

struct OrgTree: View {
    @EnvironmentObject var m: Model
    @Environment(\.colorScheme) private var scheme
    let node: Node
    let ancestors: Set<String>
    var depth = 0
    private var id: String { node["id"].text }
    private var active: Bool { m.organization == id }
    private var owner: String { "relic-org/" + id }
    private var folded: Bool { m.search.isEmpty && m.folded.contains(id) }
    private var children: [Node] { m.organizations.filter { $0["parent"].text == id && !ancestors.union([id]).contains($0["id"].text) } }
    private var query: String { m.search.trimmingCharacters(in: .whitespacesAndNewlines) }
    private var orgHit: Bool { query.isEmpty || [node["name"].text, node["purpose"].text].contains { $0.localizedCaseInsensitiveContains(query) } }
    private var memberHits: [Node] { active ? m.members.filter { query.isEmpty || [$0.display, $0["name"].text, $0["role"].text].contains { $0.localizedCaseInsensitiveContains(query) } } : [] }
    var body: some View {
        VStack(spacing: 0) {
            if orgHit || !memberHits.isEmpty {
                Button {
                    if active { m.toggleFold(id) } else { m.run { try await m.select(id) } }
                } label: {
                    HStack(spacing: 8) {
                        ReferenceIcon(name: "chev", size: 14, color: RelicStyle.muted)
                            .rotationEffect(.degrees((active || !children.isEmpty) && !folded ? 90 : 0))
                            .highPriorityGesture(TapGesture().onEnded { if active || !children.isEmpty { m.toggleFold(id) } else { m.run { try await m.select(id) } } })
                        Text(String(node["name"].text.trimmingCharacters(in: .whitespaces).prefix(1)).uppercased())
                            .font(RelicStyle.font(11, weight: 700)).frame(width: 22, height: 22)
                            .foregroundStyle(RelicStyle.avatar(id, background: false, dark: false))
                            .background(RelicStyle.avatar(id, background: true, dark: false), in: RoundedRectangle(cornerRadius: 6))
                            .overlay { if node["kind"].text == "subgroup" { RoundedRectangle(cornerRadius: 6).strokeBorder(RelicStyle.muted, style: StrokeStyle(lineWidth: 1, dash: [2, 2])) } }
                        ReferenceLabel(node["name"].text, size: 13.44, weight: 600, lineHeight: 18.144, lines: 2, owner: owner).frame(maxWidth: .infinity, alignment: .leading)
                        if !active { ReferenceLabel(m.shortWhen(node["last_at"]), size: 11.5, color: RelicStyle.muted, owner: owner) }
                    }.padding(.leading, CGFloat(8 + depth * 16)).padding(.trailing, 8).padding(.vertical, 6).frame(minHeight: 34)
                        .accessibilityElement(children: .contain)
                }.buttonStyle(QuietButtonStyle(selected: active, selectionApplicable: true)).accessibilityIdentifier(owner).accessibilityLabel(node["name"].text).help(node["name"].text + (node["purpose"].text.isEmpty ? "" : "\n" + node["purpose"].text))
                    .recordedOpacity(!node["status"].text.isEmpty && node["status"].text != "active" ? 0.6 : 1)
                    .contextMenu { Button(m.t("appmenu.org_chart")) { m.sheet = .chart } }
                if active && !folded {
                    VStack(spacing: 1) {
                        if query.isEmpty || orgHit || m.t("common.group_chat").localizedCaseInsensitiveContains(query) {
                            SidebarChatRow(who: nil, group: true)
                        }
                        let secretary = m.members.first { $0["secretary"].flag }
                        if query.isEmpty || m.t("common.secretary").localizedCaseInsensitiveContains(query) || secretary.map({ member in memberHits.contains { $0["name"].text == member["name"].text } }) == true {
                            SidebarChatRow(who: secretary, group: false)
                        }
                        Rows(memberHits.filter { !$0["secretary"].flag }) { MemberRow(who: $0) }
                        Button { m.openMemberForm() } label: {
                            HStack(spacing: 8) { ReferenceIcon(name: "plus", size: 14, color: RelicStyle.muted); ReferenceLabel(m.t("common.add_member"), size: 12.5, color: RelicStyle.muted, lines: 0); Spacer(minLength: 0) }.padding(.horizontal, 8).padding(.vertical, 6)
                        }.buttonStyle(QuietButtonStyle())
                    }.padding(.leading, 15).padding(.top, 2).padding(.bottom, 8)
                        .overlay(alignment: .leading) { RelicStyle.border.frame(width: 1) }.padding(.leading, 10)
                }
            }
            if !folded { Rows(children) { child in AnyView(OrgTree(node: child, ancestors: ancestors.union([id]), depth: depth + 1)) } }
        }
    }
}

struct MemberRow: View {
    let who: Node
    var body: some View { SidebarChatRow(who: who, group: false) }
}

struct SidebarChatRow: View {
    @EnvironmentObject var m: Model
    let who: Node?
    let group: Bool
    private var owner: String { "relic-list-row/" + m.organization + "/" + (group ? "group" : name) }
    private var secretary: Bool { !group && (who == nil || who?["secretary"].flag == true) }
    private var name: String { who?["name"].text ?? "" }
    private var selected: Bool { group ? m.member.isEmpty : !name.isEmpty && m.member == name }
    private var head: Node { m.snapshot["chats"][group ? "group" : "member:" + name]["last"] }
    private var title: String { group ? m.t("common.group_chat") : secretary ? m.t(name.isEmpty ? "side.set_secretary" : "common.secretary") : who?.display ?? "" }
    private var subtitle: String {
        if group { return m.lastLine().isEmpty ? m.t("side.group_sub") : m.lastLine() }
        if name.isEmpty { return m.t("side.secretary_hint") }
        if !secretary, let doing = who?["doing"].text, !doing.isEmpty { return m.t("side.doing", ["doing": doing]) }
        if !m.lastLine(name).isEmpty { return m.lastLine(name) }
        if secretary { return [who?["doing"].text ?? "", who?["detail"].text ?? ""].first { !$0.isEmpty } ?? "" }
        return (who?["role"].text).flatMap { $0.isEmpty ? nil : $0 } ?? m.stateLabel(who?["state"].text ?? "")
    }
    private var unread: Int { selected ? 0 : m.unread(group ? "" : name) }
    var body: some View {
        Button {
            if secretary && name.isEmpty { m.sheet = .secretary }
            else { m.run { try await m.select(m.organization, group ? "" : name) } }
        } label: {
            HStack(spacing: 9) {
                avatar.frame(width: 30)
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 6) {
                        ReferenceLabel(title, size: 13.3, weight: 550, lineHeight: 17.955, owner: owner)
                        if secretary, let who { Text(who.display == m.t("common.secretary") ? who["name"].text : who.display).font(RelicStyle.font(10.5, weight: 600)).lineLimit(1).padding(.horizontal, 6).frame(height: 18).foregroundStyle(RelicStyle.violet).background(RelicStyle.violetSoft, in: RoundedRectangle(cornerRadius: 5)) }
                        else if who?["leader"].flag == true { SmallBadge(text: m.t("common.leader"), color: RelicStyle.accent) }
                    }.frame(height: 18, alignment: .leading)
                    if !subtitle.isEmpty { ReferenceLabel(subtitle, size: 12, color: RelicStyle.muted, lineHeight: 16.2, owner: owner).frame(height: 16.2, alignment: .leading) }
                }.frame(maxWidth: .infinity, alignment: .leading)
                VStack(alignment: .trailing, spacing: 3) {
                    let date = head["at"].isNull ? who?["doing_at"] ?? Node() : head["at"]
                    if !date.isNull { ReferenceLabel(m.shortWhen(date), size: 11, color: RelicStyle.muted, owner: owner) }
                    if unread > 0 { NativeCountBadge(text: unread > 99 ? "99+" : String(unread)) }
                }.padding(.top, 1).frame(maxHeight: .infinity, alignment: .topTrailing)
            }.padding(.horizontal, 8).padding(.vertical, 6).fixedSize(horizontal: false, vertical: true)
                .accessibilityElement(children: .contain)
        }.buttonStyle(QuietButtonStyle(selected: selected, selectionApplicable: true)).accessibilityIdentifier(owner).accessibilityLabel(title + ", " + subtitle).help(name + (who?["role"].text.isEmpty == false ? " · " + who!["role"].text : ""))
            .contextMenu { if !group && !name.isEmpty { Button(m.t("chat.card")) { m.openCard(name) }; Button(m.t("common.context_trace")) { m.openDetails("trace", member: name) } } }
    }
    private var avatar: some View {
        Group {
            if group { ReferenceIcon(name: "hash", size: 14).frame(width: 28, height: 28).background(RelicStyle.hover, in: RoundedRectangle(cornerRadius: 8)) }
            else if secretary { Avatar(member: name, size: 28, secretaryStyle: true) }
            else { Avatar(member: name, size: 28) }
        }.overlay(alignment: .bottomTrailing) {
            if let state = who?["state"].text, !state.isEmpty && state != "idle" {
                StateDot(state: state, border: RelicStyle.sidebar).offset(x: 2, y: 2)
            }
        }
    }
}
