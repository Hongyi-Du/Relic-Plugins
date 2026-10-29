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
            HStack { Spacer(); Button(m.t(labelKey)) {
                saving = true
                let sheet = m.sheet
                Task { defer { saving = false }; do { try await action(); if m.sheet == sheet { m.sheet = nil } } catch { self.error = error.localizedDescription } }
            }.disabled(saving).keyboardShortcut(.defaultAction) }
        }
    }
}

struct CreateOrgView: View {
    @EnvironmentObject var m: Model
    @State private var name = ""
    @State private var purpose = ""
    @State private var governance = "leader"
    var body: some View {
        Form {
            Text(m.t("common.new_org")).font(.title2)
            TextField(m.t("common.name"), text: $name, prompt: Text(m.t("neworg.name_placeholder")))
            TextField(m.t("neworg.purpose"), text: $purpose, prompt: Text(m.t("neworg.purpose_placeholder")), axis: .vertical)
            VoiceButton(text: $purpose)
            Picker(m.t("neworg.governance"), selection: $governance) { Text(m.t("neworg.gov_leader")).tag("leader"); Text(m.t("neworg.gov_peer")).tag("peer") }
            SaveButton(labelKey: "neworg.create") {
                guard !name.trimmingCharacters(in: .whitespaces).isEmpty else { throw RelicError.message(m.t("neworg.need_name")) }
                let result = try await m.post("/api/orgs", ["name": name.trimmingCharacters(in: .whitespacesAndNewlines), "purpose": purpose.trimmingCharacters(in: .whitespacesAndNewlines), "governance": governance])
                try await m.select(result["org_id"].text)
                m.sheet = .secretary
            }
        }.formStyle(.grouped)
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
    @State private var supersedes = ""
    var body: some View {
        Form {
            Text(m.t("org.protocols")).font(.title2)
            TextField(m.t("native.protocol_title"), text: $title)
            TextField(m.t("native.protocol_rationale"), text: $rationale, axis: .vertical)
            TextField(m.t("native.protocol_trigger"), text: $trigger)
            TextField(m.t("native.protocol_guidance"), text: $guidance, axis: .vertical)
            Picker(m.t("native.protocol_strength"), selection: $strength) { Text(m.t("common.weak")).tag("weak"); Text(m.t("common.strong")).tag("strong") }
            if strength == "strong" {
                TextField(m.t("native.protocol_rules"), text: $rules, axis: .vertical).font(.system(.body, design: .monospaced))
                Text(m.t("native.protocol_rules_hint")).font(.caption)
            }
            TextField(m.t("details.label_summary"), text: $summary, axis: .vertical)
            TextField(m.t("details.label_supersedes"), text: $supersedes)
            Toggle(m.t("org.protocol_inherits"), isOn: $inherit)
            SaveButton {
                let parsed = strength == "strong" ? try JSONSerialization.jsonObject(with: Data(rules.utf8)) : []
                try await m.post(m.path("/protocols"), ["title": title, "rationale": rationale, "trigger": trigger, "guidance": guidance, "strength": strength, "inherit": inherit, "downward": inherit, "summary_for_person": summary, "supersedes": supersedes, "rules": parsed]); try await m.refresh()
            }
        }.formStyle(.grouped)
    }
}

struct CopiesView: View {
    @EnvironmentObject var m: Model
    @State private var retire: Node?
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(m.t("cc.title")).font(.title2); Text(m.t("cc.intro"))
                if m.copies.isEmpty { Text(m.t("cc.empty")) }
                Rows(m.copies) { copy in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(copy["org_name"].text + " · " + copy["title"].text).font(.headline)
                        if !copy["read"].flag { Text(m.t("cc.unread")).font(.caption).foregroundStyle(.tint) }
                        if !copy["supersedes"].text.isEmpty { Text(m.t("cc.revision")).font(.caption) }
                        Text(copy["summary"].text).textSelection(.enabled)
                        Text(m.t("cc.proposed_by", ["name": copy["author_display"].text]))
                        Text(m.t("cc.approved_by", ["names": copy["approved_display"].rows.map(\.text).joined(separator: ", ")]))
                        Text(m.copyLabel(copy))
                        Text(m.t("cc.effective", ["when": copy["activated_at"].text])).font(.caption)
                        if !copy["supersedes"].text.isEmpty { Text(m.t("cc.replaces", ["id": copy["supersedes"].text])) }
                        if !copy["issued_by"].isNull { Text(m.t("cc.issued_by", ["name": copy["issued_by"]["name"].text])) }
                        Text(copy["stats"]["total"].text.isEmpty || copy["stats"]["total"].text == "0" ? m.t("cc.stats_none") : m.t("cc.stats", ["n": copy["stats"]["total"].text, "allow": copy["stats"]["allow"].text, "deny": copy["stats"]["deny"].text, "review": copy["stats"]["review"].text, "error": copy["stats"]["error"].text]))
                        RulesView(rules: copy["rules"].rows)
                        HStack {
                            if !copy["read"].flag { Button(m.t("cc.ack")) { m.run { try await m.post("/api/cc/" + Client.segment(copy["id"].text) + "/read", [:]); try await m.refresh() } } }
                            if copy["status"].text == "active" && ["", "active"].contains(copy["org_status"].text) { Button(m.t("cc.retire"), role: .destructive) { retire = copy } }
                        }
                    }.padding(12).background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 8))
                }
            }.frame(maxWidth: .infinity, alignment: .leading)
        }.frame(maxHeight: 600)
        .confirmationDialog(m.t("cc.retire"), isPresented: Binding(get: { retire != nil }, set: { if !$0 { retire = nil } }), presenting: retire) { copy in
            Button(m.t("cc.retire"), role: .destructive) { m.run { do { try await m.post("/api/cc/" + Client.segment(copy["id"].text) + "/retire", [:]); m.notice = m.t("cc.retired", ["id": copy["protocol_id"].text, "title": copy["title"].text]); try await m.refresh() } catch { throw RelicError.message(m.t("cc.retire_failed", ["error": error.localizedDescription])) } } }
        } message: { copy in Text(m.t("cc.retire_confirm", ["id": copy["protocol_id"].text, "title": copy["title"].text, "org": copy["org_name"].text])) }
    }
}
