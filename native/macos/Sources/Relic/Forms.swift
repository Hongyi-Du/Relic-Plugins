import SwiftUI
import RelicCore

struct SaveButton: View {
    @EnvironmentObject var m: Model
    @State private var saving = false
    @State private var error = ""
    var labelKey = "common.save"
    let action: () async throws -> Void
    var body: some View {
        VStack(alignment: .leading) {
            if !error.isEmpty { Text(error).foregroundStyle(.red).textSelection(.enabled) }
            HStack(spacing: 8) { Spacer(); TextButton(m.t("common.cancel"), size: 13) { m.sheet = nil }.buttonStyle(ReferenceButtonStyle()); TextButton(m.t(labelKey), size: 13, color: RelicStyle.background) {
                saving = true
                let sheet = m.sheet
                Task { defer { saving = false }; do { try await action(); if m.sheet == sheet { m.sheet = nil } } catch { self.error = error.localizedDescription } }
            }.buttonStyle(ReferenceButtonStyle(primary: true)).disabled(saving).keyboardShortcut(.defaultAction) }
        }
    }
}

struct CreateOrgView: View {
    @EnvironmentObject var m: Model
    @State private var name = ""
    @State private var purpose = ""
    @State private var governance = "leader"
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(m.t("common.new_org")).font(RelicStyle.font(17, weight: 600))
            VStack(alignment: .leading, spacing: 6) {
                Text(m.t("common.name")).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.secondary)
                HStack { TextField(m.t("neworg.name_placeholder"), text: $name).textFieldStyle(.plain); VoiceButton(text: $name).labelStyle(.iconOnly) }.padding(9).background(RelicStyle.card, in: RoundedRectangle(cornerRadius: 8)).overlay(RoundedRectangle(cornerRadius: 8).stroke(RelicStyle.border))
            }
            VStack(alignment: .leading, spacing: 6) {
                Text(m.t("neworg.purpose")).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.secondary)
                ZStack(alignment: .topLeading) {
                    if purpose.isEmpty { Text(m.t("neworg.purpose_placeholder")).foregroundStyle(RelicStyle.muted).padding(6).allowsHitTesting(false) }
                    TextEditor(text: $purpose).font(RelicStyle.font(13, weight: 400)).scrollContentBackground(.hidden).padding(3).accessibilityLabel(m.t("neworg.purpose"))
                }.frame(height: 80).background(RelicStyle.card, in: RoundedRectangle(cornerRadius: 8)).overlay(RoundedRectangle(cornerRadius: 8).stroke(RelicStyle.border)).overlay(alignment: .bottomTrailing) { VoiceButton(text: $purpose).labelStyle(.iconOnly).padding(8) }
            }
            VStack(alignment: .leading, spacing: 6) {
                Text(m.t("neworg.governance")).font(RelicStyle.font(12, weight: 400)).foregroundStyle(RelicStyle.secondary)
                Picker(m.t("neworg.governance"), selection: $governance) { Text(m.t("neworg.gov_leader")).tag("leader"); Text(m.t("neworg.gov_peer")).tag("peer") }.labelsHidden().frame(maxWidth: .infinity)
            }
            SaveButton(labelKey: "neworg.create") {
                guard !name.trimmingCharacters(in: .whitespaces).isEmpty else { throw RelicError.message(m.t("neworg.need_name")) }
                let result = try await m.post("/api/orgs", ["name": name.trimmingCharacters(in: .whitespacesAndNewlines), "purpose": purpose.trimmingCharacters(in: .whitespacesAndNewlines), "governance": governance])
                try await m.select(result["org_id"].text)
                m.sheet = .secretary
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}


struct ProtocolForm: View {
    @EnvironmentObject var m: Model
    @State private var title = ""
    @State private var guidance = ""
    @State private var rationale = ""
    @State private var trigger = ""
    @State private var inherit = false
    @State private var strength = "weak"
    @State private var rules = "[]"
    @State private var summary = ""
    var body: some View {
        Form {
            Text(m.t("org.protocols")).font(.title2)
            TextField(m.t("native.protocol_title"), text: $title)
            TextField(m.t("native.protocol_rationale"), text: $rationale, axis: .vertical)
            TextField(m.t("native.protocol_trigger"), text: $trigger).disabled(strength == "strong")
            TextField(m.t("native.protocol_guidance"), text: $guidance, axis: .vertical).disabled(strength == "strong")
            Picker(m.t("native.protocol_strength"), selection: $strength) { Text(m.t("common.weak")).tag("weak"); Text(m.t("common.strong")).tag("strong") }
            if strength == "strong" {
                TextField(m.t("native.protocol_rules"), text: $rules, axis: .vertical).font(.system(.body, design: .monospaced))
                Text(m.t("native.protocol_rules_hint")).font(RelicStyle.font(12, weight: 400))
                TextField(m.t("details.label_summary"), text: $summary, axis: .vertical)
            }
            Toggle(m.t("org.protocol_inherits"), isOn: $inherit)
            SaveButton {
                let parsed = strength == "strong" ? try JSONSerialization.jsonObject(with: Data(rules.utf8)) : []
                try await m.post(m.path("/protocols"), ["title": title, "rationale": rationale, "trigger": trigger, "guidance": guidance, "strength": strength, "inherit": inherit, "summary_for_person": summary, "rules": parsed]); try await m.refresh()
            }
        }.formStyle(.grouped)
    }
}

struct CopiesView: View {
    @EnvironmentObject var m: Model
    @State private var retire: Node?
    private var unread: Int { m.copies.filter { !$0["read"].flag }.count }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                ReferenceIcon(name: "cc", size: 18).foregroundStyle(RelicStyle.secondary)
                ReferenceLabel(m.t("cc.title"), size: 17, weight: 650)
                if unread > 0 { ReferenceLabel(String(unread), size: 11, weight: 700, color: .white, alignment: .center).padding(.horizontal, 5).frame(minWidth: 18).frame(height: 18).modifier(RecordedSurface(background: RelicStyle.accent, radius: 9, kind: "badge")) }
                Spacer(minLength: 0)
                IconButton(title: m.t("common.close"), icon: "x") { m.sheet = nil }
            }
            ReferenceLabel(m.t("cc.intro"), size: 13, color: RelicStyle.secondary, lineHeight: 22.1, lines: 0)
            VStack(alignment: .leading, spacing: 10) {
                if m.copies.isEmpty { ReferenceLabel(m.t("cc.empty"), size: 13, color: RelicStyle.muted).padding(22).frame(maxWidth: .infinity) }
                Rows(m.copies) { copy in CopyCard(copy: copy, retire: { retire = copy }) }
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
        .confirmationDialog(m.t("cc.retire"), isPresented: Binding(get: { retire != nil }, set: { if !$0 { retire = nil } }), presenting: retire) { copy in
            Button(m.t("cc.retire"), role: .destructive) { m.run { do { try await m.post("/api/cc/" + Client.segment(copy["id"].text) + "/retire", [:]); m.notice = m.t("cc.retired", ["id": copy["protocol_id"].text, "title": copy["title"].text]); try await m.refresh() } catch { throw RelicError.message(m.t("cc.retire_failed", ["error": error.localizedDescription])) } } }
        } message: { copy in Text(m.t("cc.retire_confirm", ["id": copy["protocol_id"].text, "title": copy["title"].text, "org": copy["org_name"].text])) }
    }
}

struct CopyCard: View {
    @EnvironmentObject var m: Model
    let copy: Node
    let retire: () -> Void
    @State private var acknowledging = false
    private var live: Bool { copy["status"].text == "active" && ["", "active"].contains(copy["org_status"].text) }
    private var organization: Node { m.organizations.first { $0["id"].text == copy["org"].text } ?? Node(["id": copy["org"].text, "name": copy["org_name"].text]) }
    private var tone: String { !["", "active"].contains(copy["org_status"].text) ? "" : copy["status"].text == "active" ? "ok" : copy["status"].text == "retired" && copy["retired_by"].text == "human" ? "bad" : "" }
    private var metadata: String {
        var parts = [m.t(copy["issued_by"]["member"].text.isEmpty ? "cc.proposed_by" : "cc.issued_by", ["name": copy["author_display"].text])]
        if !copy["approved_display"].rows.isEmpty { parts.append(m.t("cc.approved_by", ["names": m.list(copy["approved_display"].rows.map(\.text))])) }
        if !copy["activated_at"].text.isEmpty { parts.append(m.t("cc.effective", ["when": m.day(copy["activated_at"]) + " " + m.clock(copy["activated_at"])])) }
        if !copy["supersedes"].text.isEmpty { parts.append(m.t("cc.replaces", ["id": copy["supersedes"].text])) }
        return parts.joined(separator: " · ")
    }
    private var stats: String {
        let stats = copy["stats"]
        return stats["total"].integer == 0 ? m.t("cc.stats_none") : m.t("cc.stats", ["n": stats["total"].text, "allow": String(stats["allow"].integer), "deny": String(stats["deny"].integer), "review": String(stats["review"].integer), "error": String(stats["error"].integer)])
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 10) {
                OrganizationBadge(node: organization).padding(.top, 2)
                VStack(alignment: .leading, spacing: 0) {
                    ReferenceLabel(copy["org_name"].text, size: 12, color: RelicStyle.muted, lineHeight: 16.8).help(copy["org_name"].text)
                    (Text(copy["protocol_id"].text).font(Font(RelicStyle.monoFont(14))).foregroundColor(RelicStyle.secondary) + Text(" " + copy["title"].text).font(RelicStyle.font(14, weight: 650))).lineSpacing(0).fixedSize(horizontal: false, vertical: true)
                }.frame(maxWidth: .infinity, alignment: .leading)
                FlowLayout(spacing: 4) {
                    if !copy["read"].flag { OverviewChip(text: m.t("cc.unread"), tone: "accent") }
                    if !copy["supersedes"].text.isEmpty { OverviewChip(text: m.t("cc.revision")) }
                    OverviewChip(text: m.copyLabel(copy), tone: tone)
                }.frame(maxWidth: 300, alignment: .trailing)
            }
            RichText(copy["summary"].text).frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 12).padding(.vertical, 8)
                .modifier(RecordedSurface(background: live ? RelicStyle.sidebar : RelicStyle.background, border: RelicStyle.line, borderWidth: 1, radius: 10, kind: "region")).recordedOpacity(live ? 1 : 0.8)
            ReferenceLabel(metadata, size: 12, color: RelicStyle.muted, lines: 0)
            ReferenceLabel(stats, size: 12, color: RelicStyle.muted, lines: 0)
            RulesView(rules: copy["rules"].rows)
            if !copy["read"].flag || live {
                FlowLayout(spacing: 6) {
                    if !copy["read"].flag {
                        Button { acknowledging = true; m.run { defer { acknowledging = false }; try await m.post("/api/cc/" + Client.segment(copy["id"].text) + "/read", [:]); try await m.refresh() } } label: {
                            HStack(spacing: 6) { ReferenceIcon(name: "check", size: 14); ReferenceLabel(m.t("cc.ack"), size: 12, weight: 600) }
                        }.buttonStyle(ReferenceButtonStyle(small: true)).disabled(acknowledging)
                    }
                    if live { TextButton(m.t("cc.retire"), size: 12, color: RelicStyle.red, action: retire).buttonStyle(ReferenceButtonStyle(small: true, danger: true)) }
                }
            }
        }.padding(.horizontal, 14).padding(.vertical, 12).frame(maxWidth: .infinity, alignment: .leading)
            .modifier(RecordedSurface(background: live ? RelicStyle.card : RelicStyle.sidebar, border: copy["read"].flag ? RelicStyle.line : RelicStyle.mix(RelicStyle.accent, RelicStyle.line, fraction: 0.45), borderWidth: 1, radius: 12, kind: "card", insetLeadingWidth: copy["read"].flag ? 0 : 3, insetLeadingColor: RelicStyle.accent))
    }
}
