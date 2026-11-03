import SwiftUI
import RelicCore

struct Sidebar: View {
    @EnvironmentObject var m: Model
    var revealMembers = true
    @State private var focused = false
    @State private var profileImageVisible = false
    /// The organization whose members the tree shows. Another organization's
    /// member rows are admitted in their own turn after the switch publishes;
    /// the switch's transaction only collapses the previous organization.
    @State private var revealedOrganization = ""
    private let newOrganizationOwner = "relic-text-button/sidebar-new-organization"
    var body: some View {
        let _ = UIWorkTrace.count("body.sidebar")
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
            // The stack offers the tree all the height between the search
            // field and the profile; it is not measured row by row to say so.
            ScrollRegion { ScrollView {
                LazyVStack(spacing: 0) {
                    if revealMembers {
                    HStack {
                        ReferenceLabel(m.t("page.tree"), size: 12, color: RelicStyle.muted, lines: 0); Spacer()
                        if !m.organizations.isEmpty { ReferenceLabel(String(m.organizations.count), size: 12, color: RelicStyle.muted, lines: 0) }
                    }.padding(.horizontal, 10).padding(.top, 14).padding(.bottom, 6)
                    ForEach(OrganizationOutline.rows(organizations: m.organizations, selected: m.organization,
                        members: m.members, folded: m.folded, search: m.search, groupLabel: m.t("common.group_chat"),
                        secretaryLabel: m.t("common.secretary"), revealMembers: revealMembers && !m.snapshot["org"].isNull && revealedOrganization == m.organization)) { row in
                        // One sidebar row per turn: admitting several at once moved the
                        // rows below by their estimate errors together, and a click
                        // on a member row could land beside it (run 41686765993).
                        ProgressiveRow(estimatedHeight: row.kind == .organization ? 46 : 61, weight: RowMountQueue.budget) { SidebarOutlineRow(row: row).equatable() }
                    }
                    if m.organizations.isEmpty { ReferenceLabel(m.t("side.no_orgs"), size: 12.5, color: RelicStyle.muted, lines: 0).padding(.horizontal, 10).padding(.vertical, 8).frame(maxWidth: .infinity, alignment: .leading) }
                    }
                }.padding(.horizontal, 8).padding(.top, 4).padding(.bottom, 12)
                    .background {
                        if ResponsivenessCapture.enabled { NativeScrollOwner(identifier: "relic-performance-sidebar", title: "") }
                        else { ScrollAppearance() }
                    }
            }.accessibilityLabel(m.t("page.tree")) }.frame(maxHeight: .infinity)
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
            .task(id: m.organization) {
                guard revealedOrganization != m.organization else { return }
                let ticket = PerformanceRendering.beginSurface(), turn = UUID()
                defer { PerformanceRendering.endSurface(ticket) }
                guard await RowMountQueue.shared.acquire(turn, label: "sidebar-members", priority: 25) else { return }
                defer { RowMountQueue.shared.release(turn) }
                guard !Task.isCancelled else { return }
                revealedOrganization = m.organization
                try? await Task.sleep(for: .milliseconds(32))
            }
    }
}

/// Evaluating the sidebar again (a chat switch, a new snapshot) must not
/// rebuild every organization and member row: a row updates when its own
/// outline entry changes. Rows still observe the model fields they read.
private struct SidebarOutlineRow: View, Equatable {
    @EnvironmentObject var m: Model
    let row: OrganizationOutlineRow
    static func == (a: Self, b: Self) -> Bool {
        let left = a.row, right = b.row
        guard left.id == right.id, left.organization == right.organization, left.kind == right.kind, left.depth == right.depth,
              left.hasChildren == right.hasChildren, left.first == right.first, left.last == right.last else { return false }
        let leftNode = left.node.raw as AnyObject, rightNode = right.node.raw as AnyObject
        return leftNode === rightNode || (leftNode as? NSObject)?.isEqual(rightNode) == true
    }
    var body: some View {
        VStack(spacing: 0) {
            if row.kind == .organization { OrgTree(node: row.node, depth: row.depth, hasChildren: row.hasChildren) }
            else {
                Group {
                    switch row.kind {
                    case .group: SidebarChatEntry(who: nil, group: true)
                    case .secretary: SidebarChatEntry(who: row.node["name"].isNull ? nil : row.node, group: false)
                    case .member: SidebarChatEntry(who: row.node, group: false)
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
                let _ = UIWorkTrace.count("body.org-tree")
                Button {
                    PerformancePointer.observed(PerformancePointer.organization(id))
                    if active { m.toggleFold(id) } else { m.run { try await m.select(id) } }
                } label: {
                    HStack(spacing: 8) {
                        ReferenceIcon(name: "chev", size: 14, color: RelicStyle.muted, owner: owner)
                            .rotationEffect(.degrees(expanded ? 90 : 0))
                            .highPriorityGesture(TapGesture().onEnded { if active || hasChildren { m.toggleFold(id) } else { m.run { try await m.select(id) } } })
                        OrganizationAvatar(node: node)
                        PlainLabel(node["name"].text, size: 13.44, weight: 600, lineHeight: 18.144).lineLimit(2).frame(maxWidth: .infinity, alignment: .leading)
                        if !active { PlainLabel(m.shortWhen(node["last_at"]), size: 11.5, color: RelicStyle.muted).fixedSize() }
                    }.padding(.leading, CGFloat(8 + depth * 16)).padding(.trailing, 8).padding(.vertical, 6).frame(minHeight: 34)
                        .accessibilityElement(children: .contain)
                        .environment(\.nativeElementParent, owner)
                }.buttonStyle(QuietButtonStyle(selected: active, selectionApplicable: true, radius: 8, expanded: expanded)).accessibilityIdentifier(owner).accessibilityLabel(accessibilityName).help(node["name"].text + (node["purpose"].text.isEmpty ? "" : "\n" + node["purpose"].text))
                    .modifier(PerformancePointerTarget(identity: PerformancePointer.organization(id)))
                    .recordedOpacity(!node["status"].text.isEmpty && node["status"].text != "active" ? 0.55 : 1)
                    .contextMenu { Button(m.t("appmenu.org_chart")) { m.sheet = .chart } }
    }
}

struct MemberRow: View {
    let who: Node
    var body: some View { SidebarChatEntry(who: who, group: false) }
}

/// What one sidebar chat row shows, read from the model by its entry.
struct SidebarChatContent: Equatable {
    var organization = "", name = "", title = "", subtitle = "", badge = "", timestamp = ""
    var role = "", state = "", initial = "", cardTitle = "", traceTitle = ""
    var group = false, secretary = false, leader = false, hasWho = false, selected = false, hasDate = false
    var unread = 0
    @MainActor init(model m: Model, who: Node?, group: Bool) {
        let name = who?["name"].text ?? ""
        let secretary = !group && (who == nil || who?["secretary"].flag == true)
        let selected = group ? m.member.isEmpty : !name.isEmpty && m.member == name
        // One history scan and one preview/date formatting pass per entry.
        let head = m.snapshot["chats"][group ? "group" : "member:" + name]["last"]
        let date = head["at"].isNull ? who?["doing_at"] ?? Node() : head["at"]
        organization = m.organization; self.name = name; self.group = group; self.secretary = secretary
        self.selected = selected; hasWho = who != nil; leader = who?["leader"].flag == true
        title = group ? m.t("common.group_chat") : secretary ? m.t(name.isEmpty ? "side.set_secretary" : "common.secretary") : who?.display ?? ""
        subtitle = Self.subtitle(m, who: who, name: name, group: group, secretary: secretary)
        unread = selected ? 0 : m.unread(group ? "" : name)
        hasDate = !date.isNull
        timestamp = date.isNull ? "" : m.shortWhen(date)
        if secretary, let who { badge = who.display == m.t("common.secretary") ? who["name"].text : who.display }
        else if who?["leader"].flag == true { badge = m.t("common.leader") }
        role = who?["role"].text ?? ""
        state = who?["state"].text ?? ""
        initial = String(m.name(name).prefix(1)).uppercased()
        cardTitle = m.t("chat.card"); traceTitle = m.t("common.context_trace")
    }
    @MainActor private static func subtitle(_ m: Model, who: Node?, name: String, group: Bool, secretary: Bool) -> String {
        if group { let preview = m.lastLine(); return preview.isEmpty ? m.t("side.group_sub") : preview }
        if name.isEmpty { return m.t("side.secretary_hint") }
        if !secretary, let doing = who?["doing"].text, !doing.isEmpty { return m.t("side.doing", ["doing": doing]) }
        let preview = m.lastLine(name)
        if !preview.isEmpty { return preview }
        if secretary { return [who?["doing"].text ?? "", who?["detail"].text ?? ""].first { !$0.isEmpty } ?? "" }
        return (who?["role"].text).flatMap { $0.isEmpty ? nil : $0 } ?? m.stateLabel(who?["state"].text ?? "")
    }
}

/// Reads one sidebar chat row's values from the model. A chat switch or a
/// new snapshot evaluates every built entry again, which is cheap; the row
/// below is rebuilt only when its own values changed (the chat left and the
/// chat opened on a switch), not every built row's labels, avatar, badges
/// and button style, as each row did while it read the model itself.
private struct SidebarChatEntry: View {
    @EnvironmentObject var m: Model
    let who: Node?
    let group: Bool
    var body: some View {
        let _ = UIWorkTrace.count("body.sidebar-entry")
        SidebarChatRow(content: SidebarChatContent(model: m, who: who, group: group)).equatable()
    }
}

struct SidebarChatRow: View, Equatable {
    /// Actions only: the body reads nothing from the model, so the row is
    /// rebuilt only when `content` changes.
    @EnvironmentObject var m: Model
    @State private var avatarImageVisible = false
    let content: SidebarChatContent
    static func == (a: Self, b: Self) -> Bool { a.content == b.content }
    private var owner: String { "relic-list-row/" + content.organization + "/" + (content.group ? "group" : content.name) }
    private var pointerTarget: String {
        !content.group && content.name.isEmpty ? "secretary-setup:" + content.organization
            : PerformancePointer.chat(content.organization, content.group ? "" : content.name)
    }
    var body: some View {
        let _ = UIWorkTrace.count("body.sidebar-chat")
        let content = self.content, name = content.name, group = content.group, secretary = content.secretary
        let unread = content.unread, pointerTarget = self.pointerTarget
        let accessibilityName = [group || secretary || avatarImageVisible ? "" : content.initial,
            content.title, content.badge, content.subtitle, content.timestamp, unread > 0 ? unread > 99 ? "99+" : String(unread) : ""]
            .filter { !$0.isEmpty }.joined(separator: " ")
        Button {
            PerformancePointer.observed(pointerTarget)
            if secretary && name.isEmpty { m.sheet = .secretary }
            else { m.run { try await m.select(m.organization, group ? "" : name) } }
        } label: {
            HStack(spacing: 9) {
                avatar.frame(width: 30)
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 6) {
                        PlainLabel(content.title, size: 13.3, weight: 550, lineHeight: 17.955).lineLimit(1)
                        if secretary, content.hasWho { SmallBadge(text: content.badge, color: RelicStyle.violet, background: RelicStyle.violetSoft) }
                        else if content.leader { SmallBadge(text: content.badge, color: RelicStyle.accent) }
                    }.frame(height: 18, alignment: .leading)
                    if !content.subtitle.isEmpty { PlainLabel(content.subtitle, size: 12, color: RelicStyle.muted, lineHeight: 16.2).lineLimit(1).frame(height: 16.2, alignment: .leading) }
                }.frame(maxWidth: .infinity, alignment: .leading)
                VStack(alignment: .trailing, spacing: 3) {
                    if content.hasDate { PlainLabel(content.timestamp, size: 11, color: RelicStyle.muted).fixedSize() }
                    if unread > 0 { NativeCountBadge(text: unread > 99 ? "99+" : String(unread)) }
                }.padding(.top, 1).frame(maxHeight: .infinity, alignment: .topTrailing)
            }.padding(.horizontal, 8).padding(.vertical, 6).fixedSize(horizontal: false, vertical: true)
                .accessibilityElement(children: .contain)
                .environment(\.nativeElementParent, owner)
        }.buttonStyle(QuietButtonStyle(selected: content.selected, selectionApplicable: true, radius: 8, unread: unread > 0)).accessibilityIdentifier(owner).accessibilityLabel(accessibilityName).help(name + (content.hasWho && !content.role.isEmpty ? " · " + content.role : ""))
            .modifier(PerformancePointerTarget(identity: pointerTarget))
            .contextMenu { if !group && !name.isEmpty { Button(content.cardTitle) { m.openCard(name) }; Button(content.traceTitle) { m.openDetails("trace", member: name) } } }
    }
    private var avatar: some View {
        Group {
            if content.group { SidebarGroupAvatar() }
            else if content.secretary { Avatar(member: content.name, size: 28, secretaryStyle: true) }
            else { Avatar(member: content.name, size: 28, imageVisibility: { avatarImageVisible = $0 }) }
        }.overlay(alignment: .bottomTrailing) {
            if !content.state.isEmpty && content.state != "idle" {
                StateDot(state: content.state, border: RelicStyle.sidebar).offset(x: 2, y: 2)
            }
        }
    }
}
