import SwiftUI
import RelicCore

struct Sidebar: View {
    @EnvironmentObject var m: Model
    var revealMembers = true
    @State private var focused = false
    @State private var profileImageVisible = false
    private let newOrganizationOwner = "relic-text-button/sidebar-new-organization"
    var body: some View {
        VStack(spacing: 0) {
            VStack(spacing: 2) {
                Button { m.sheet = .create } label: {
                    HStack(spacing: 10) { ReferenceIcon(name: "neworg", size: 17, owner: newOrganizationOwner); ReferenceLabel(m.t("common.new_org"), lines: 0, owner: newOrganizationOwner); Spacer(minLength: 0) }.padding(.horizontal, 10).frame(height: 34)
                }.buttonStyle(QuietButtonStyle(radius: 8)).accessibilityIdentifier(newOrganizationOwner)
                HStack(spacing: 8) {
                    ReferenceIcon(name: "search", size: 15, color: RelicStyle.muted, owner: "relic-card/sidebar-search")
                    ObservedSearchField(placeholder: m.t("page.search"),
                        accessibleName: m.preferences["voice"].text == "off" ? "" : m.t("common.voice_input"),
                        text: $m.search, focused: $focused)
                    VoiceButton(text: $m.search, size: 32).labelStyle(.iconOnly)
                }.padding(.horizontal, 10).frame(height: 34).modifier(RecordedSurface(background: RelicStyle.hover, radius: 8, kind: "card", owner: "relic-card/sidebar-search"))
                    .accessibilityElement(children: .contain).accessibilityIdentifier("relic-card/sidebar-search").accessibilityLabel("")
            }.padding(.horizontal, 8).padding(.top, 10).padding(.bottom, 6)
            ScrollView {
                LazyVStack(spacing: 0) {
                    HStack {
                        ReferenceLabel(m.t("page.tree"), size: 12, color: RelicStyle.muted, lines: 0); Spacer()
                        if !m.organizations.isEmpty { ReferenceLabel(String(m.organizations.count), size: 12, color: RelicStyle.muted, lines: 0) }
                    }.padding(.horizontal, 10).padding(.top, 14).padding(.bottom, 6)
                    ForEach(OrganizationOutline.rows(organizations: m.organizations, selected: m.organization,
                        members: m.members, folded: m.folded, search: m.search, groupLabel: m.t("common.group_chat"),
                        secretaryLabel: m.t("common.secretary"), revealMembers: revealMembers && !m.snapshot["org"].isNull)) { row in
                        SidebarOutlineRow(row: row)
                    }
                    if m.organizations.isEmpty { ReferenceLabel(m.t("side.no_orgs"), size: 12.5, color: RelicStyle.muted, lines: 0).padding(.horizontal, 10).padding(.vertical, 8).frame(maxWidth: .infinity, alignment: .leading) }
                }.padding(.horizontal, 8).padding(.top, 4).padding(.bottom, 12)
            }.frame(maxHeight: .infinity).accessibilityLabel(m.t("page.tree"))
                .modifier(RecordedSurface(background: .clear, kind: "region"))
            HStack(spacing: 4) {
                Button { m.sheet = .settings } label: {
                    HStack(spacing: 10) {
                        Avatar(member: "human", size: 28, imageVisibility: { profileImageVisible = $0 })
                        VStack(alignment: .leading, spacing: 0) {
                            ReferenceLabel(m.name("human"), size: 13.3, weight: 600)
                            ReferenceLabel(m.t("side.profile"), size: 11.5, color: RelicStyle.muted)
                        }
                        Spacer(minLength: 0)
                    }.padding(.vertical, 6).padding(.horizontal, 8)
                        .environment(\.nativeElementParent, "relic-profile-button")
                }.buttonStyle(QuietButtonStyle(radius: 8)).accessibilityIdentifier("relic-profile-button")
                    .accessibilityLabel([profileImageVisible ? "" : String(m.name("human").prefix(1)).uppercased(), m.name("human"), m.t("side.profile")].filter { !$0.isEmpty }.joined(separator: " "))
                    .help(m.t("page.me"))
                IconButton(title: m.t("common.settings"), icon: "gear") { m.sheet = .settings }
            }.padding(8).padding(.top, 1)
                .modifier(RecordedSurface(background: .clear, border: RelicStyle.line, edges: EdgeInsets(top: 1, leading: 0, bottom: 0, trailing: 0), kind: "card", owner: "relic-card/sidebar-profile"))
                .accessibilityElement(children: .contain).accessibilityIdentifier("relic-card/sidebar-profile").accessibilityLabel("")
        }.padding(.trailing, 1).modifier(RecordedSurface(background: RelicStyle.sidebar, border: RelicStyle.line, edges: EdgeInsets(top: 0, leading: 0, bottom: 0, trailing: 1), kind: "region"))
            .accessibilityElement(children: .contain).accessibilityLabel(m.t("page.side"))
            .accessibilityIdentifier("relic-region/sidebar")
            .onChange(of: m.focusSearch) { if m.focusSearch { focused = true; m.focusSearch = false } }
    }
}

private struct SidebarOutlineRow: View {
    @EnvironmentObject var m: Model
    let row: OrganizationOutlineRow
    var body: some View {
        VStack(spacing: 0) {
            if row.kind == .organization { OrgTree(node: row.node, depth: row.depth, hasChildren: row.hasChildren) }
            else {
                Group {
                    switch row.kind {
                    case .group: SidebarChatRow(who: nil, group: true)
                    case .secretary: SidebarChatRow(who: row.node["name"].isNull ? nil : row.node, group: false)
                    case .member: SidebarChatRow(who: row.node, group: false)
                    case .addMember:
                        Button { m.openMemberForm() } label: {
                            HStack(spacing: 8) {
                                ReferenceIcon(name: "plus", size: 14, color: RelicStyle.muted, owner: "relic-text-button/add-member/" + row.organization)
                                ReferenceLabel(m.t("common.add_member"), size: 12.5, color: RelicStyle.muted, lines: 0, owner: "relic-text-button/add-member/" + row.organization)
                                Spacer(minLength: 0)
                            }.padding(.horizontal, 8).padding(.vertical, 6)
                        }.buttonStyle(QuietButtonStyle(radius: 8)).accessibilityIdentifier("relic-text-button/add-member/" + row.organization)
                    case .organization: EmptyView()
                    }
                }.padding(.leading, 15).padding(.top, row.first ? 2 : 1).padding(.bottom, row.last ? 8 : 0)
                    .overlay(alignment: .leading) { Rectangle().fill(RelicStyle.border).frame(width: 1).allowsHitTesting(false).accessibilityHidden(true) }
                    .padding(.leading, 10)
            }
        }.onAppear { PerformanceRendering.rowAppeared("sidebar") }
            .onDisappear { PerformanceRendering.rowDisappeared("sidebar") }
    }
}

private struct OrgTree: View {
    @EnvironmentObject var m: Model
    @Environment(\.colorScheme) private var scheme
    let node: Node
    let depth: Int
    let hasChildren: Bool
    private var id: String { node["id"].text }
    private var active: Bool { m.organization == id }
    private var owner: String { "relic-org/" + id }
    private var folded: Bool { m.search.isEmpty && m.folded.contains(id) }
    private var expanded: Bool { (active || hasChildren) && !folded }
    private var accessibilityName: String {
        [OrganizationAvatar.initial(for: node), node["name"].text, active ? "" : m.shortWhen(node["last_at"])].filter { !$0.isEmpty }.joined(separator: " ")
    }
    var body: some View {
                Button {
                    if active { m.toggleFold(id) } else { m.run { try await m.select(id) } }
                } label: {
                    HStack(spacing: 8) {
                        ReferenceIcon(name: "chev", size: 14, color: RelicStyle.muted, owner: owner)
                            .rotationEffect(.degrees(expanded ? 90 : 0))
                            .highPriorityGesture(TapGesture().onEnded { if active || hasChildren { m.toggleFold(id) } else { m.run { try await m.select(id) } } })
                        OrganizationAvatar(node: node)
                        ReferenceLabel(node["name"].text, size: 13.44, weight: 600, lineHeight: 18.144, lines: 2, owner: owner).frame(maxWidth: .infinity, alignment: .leading)
                        if !active { ReferenceLabel(m.shortWhen(node["last_at"]), size: 11.5, color: RelicStyle.muted, lines: 0, owner: owner).fixedSize() }
                    }.padding(.leading, CGFloat(8 + depth * 16)).padding(.trailing, 8).padding(.vertical, 6).frame(minHeight: 34)
                        .accessibilityElement(children: .contain)
                        .environment(\.nativeElementParent, owner)
                }.buttonStyle(QuietButtonStyle(selected: active, selectionApplicable: true, radius: 8, expanded: expanded)).accessibilityIdentifier(owner).accessibilityLabel(accessibilityName).help(node["name"].text + (node["purpose"].text.isEmpty ? "" : "\n" + node["purpose"].text))
                    .recordedOpacity(!node["status"].text.isEmpty && node["status"].text != "active" ? 0.55 : 1)
                    .contextMenu { Button(m.t("appmenu.org_chart")) { m.sheet = .chart } }
    }
}

struct MemberRow: View {
    let who: Node
    var body: some View { SidebarChatRow(who: who, group: false) }
}

struct SidebarChatRow: View {
    @EnvironmentObject var m: Model
    @State private var avatarImageVisible = false
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
    private var date: Node { head["at"].isNull ? who?["doing_at"] ?? Node() : head["at"] }
    private var badgeText: String {
        if secretary, let who { return who.display == m.t("common.secretary") ? who["name"].text : who.display }
        return who?["leader"].flag == true ? m.t("common.leader") : ""
    }
    private var accessibilityName: String {
        [group || secretary || avatarImageVisible ? "" : String(m.name(name).prefix(1)).uppercased(),
         title, badgeText, subtitle, date.isNull ? "" : m.shortWhen(date), unread > 0 ? unread > 99 ? "99+" : String(unread) : ""]
            .filter { !$0.isEmpty }.joined(separator: " ")
    }
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
                        if secretary, who != nil { SmallBadge(text: badgeText, color: RelicStyle.violet, background: RelicStyle.violetSoft) }
                        else if who?["leader"].flag == true { SmallBadge(text: badgeText, color: RelicStyle.accent) }
                    }.frame(height: 18, alignment: .leading)
                    if !subtitle.isEmpty { ReferenceLabel(subtitle, size: 12, color: RelicStyle.muted, lineHeight: 16.2, owner: owner).frame(height: 16.2, alignment: .leading) }
                }.frame(maxWidth: .infinity, alignment: .leading)
                VStack(alignment: .trailing, spacing: 3) {
                    if !date.isNull { ReferenceLabel(m.shortWhen(date), size: 11, color: RelicStyle.muted, lines: 0, owner: owner).fixedSize() }
                    if unread > 0 { NativeCountBadge(text: unread > 99 ? "99+" : String(unread)) }
                }.padding(.top, 1).frame(maxHeight: .infinity, alignment: .topTrailing)
            }.padding(.horizontal, 8).padding(.vertical, 6).fixedSize(horizontal: false, vertical: true)
                .accessibilityElement(children: .contain)
                .environment(\.nativeElementParent, owner)
        }.buttonStyle(QuietButtonStyle(selected: selected, selectionApplicable: true, radius: 8, unread: unread > 0)).accessibilityIdentifier(owner).accessibilityLabel(accessibilityName).help(name + (who?["role"].text.isEmpty == false ? " · " + who!["role"].text : ""))
            .contextMenu { if !group && !name.isEmpty { Button(m.t("chat.card")) { m.openCard(name) }; Button(m.t("common.context_trace")) { m.openDetails("trace", member: name) } } }
    }
    private var avatar: some View {
        Group {
            if group { SidebarGroupAvatar() }
            else if secretary { Avatar(member: name, size: 28, secretaryStyle: true) }
            else { Avatar(member: name, size: 28, imageVisibility: { avatarImageVisible = $0 }) }
        }.overlay(alignment: .bottomTrailing) {
            if let state = who?["state"].text, !state.isEmpty && state != "idle" {
                StateDot(state: state, border: RelicStyle.sidebar).offset(x: 2, y: 2)
            }
        }
    }
}
