import Foundation
import RelicCore

// These tables drive controls and state labels; wording is always fetched from /api/i18n.
enum Choices {
    static let themes = [("system", "common.theme_system"), ("light", "common.theme_light"), ("dark", "common.theme_dark")]
    static let fonts = [("small", "common.size_small"), ("medium", "common.size_medium"), ("large", "common.size_large")]
    static let densities = [("comfortable", "settings.density_comfortable"), ("compact", "settings.density_compact")]
    static let modes = [("direct", "org.mode_direct"), ("transparent", "org.mode_transparent"), ("liaison", "org.mode_liaison")]
    static let panes = [("overview", "panel.overview"), ("workspace", "panel.workspace"), ("files", "common.file")]
}

extension Model {
    func stateLabel(_ state: String) -> String {
        let keys = ["active": "state.active", "error": "state.error", "idle": "state.idle", "running": "state.running", "starting": "state.starting", "vacant": "state.vacant", "waiting": "state.waiting", "working": "state.working"]
        return keys[state].map { t($0) } ?? state
    }
    func taskLabel(_ state: String) -> String {
        let keys = ["open": "task.open", "working": "task.working", "blocked": "task.blocked", "done": "task.done", "dropped": "task.dropped"]
        return keys[state].map { t($0) } ?? state
    }
    func protocolLabel(_ state: String) -> String {
        let keys = ["active": "details.status_active", "enacted": "details.status_enacted", "proposed": "details.status_proposed", "rejected": "details.status_rejected", "retired": "details.status_retired", "superseded": "details.status_superseded"]
        return keys[state].map { t($0) } ?? state
    }
    func episodeLabel(_ episode: Node) -> String {
        if episode["status"].text == "open" { return t("task.working") }
        let keys = ["success": "org.episode_success", "failure": "common.failed", "partial": "org.episode_partial", "cancelled": "org.episode_cancelled"]
        return keys[episode["outcome"].text].map { t($0) } ?? episode["outcome"].text
    }
    func copyLabel(_ copy: Node) -> String {
        if copy["status"].text == "retired" && copy["retired_by_person"].flag { return t("cc.status_retired_person") }
        if !["", "active"].contains(copy["org_status"].text) { return t("cc.status_ended") }
        let key = ["active": "cc.status_active", "retired": "cc.status_retired", "superseded": "cc.status_superseded"][copy["status"].text]
        return key.map { t($0, ["id": copy["superseded_by"].text]) } ?? copy["status"].text
    }
    func identity(_ card: Node) -> String {
        let harness = card["harness_label"].text
        if card["state"].text == "vacant" { return t(harness.isEmpty ? "card.identity_vacant" : "card.identity_vacant_harness", ["harness": harness]) }
        if card["surface"].text == "subagent" { return t(card["parent"].text.isEmpty ? "card.identity_subagent" : "card.identity_subagent_parent", ["harness": harness, "parent": name(card["parent"].text)]) }
        if card["surface"].text == "acp" { return t("card.identity_acp", ["harness": harness]) }
        if card["surface"].text == "chat" { return t("card.identity_chat", ["harness": harness]) }
        return t("card.identity_session", ["where": [harness, card["surface_label"].text].filter { !$0.isEmpty }.joined(separator: " ")])
    }
    func banner(_ card: Node) -> String {
        if card["embedded"].flag { return t("banner.embedded", ["harness": card["harness_label"].text]) }
        if card["surface"].text == "subagent" { return t(card["parent"].text.isEmpty ? "banner.subagent" : "banner.subagent_in", ["parent": name(card["parent"].text)]) }
        let surface = card["config"]["surface"].text.isEmpty ? card["surface"].text : card["config"]["surface"].text
        if !Capabilities.automatic(platform, harness: card["harness"].text, surface: surface) { return t(card["harness"].text == "chatgpt" ? "member.chatgpt_unavailable" : "member.desktop_manual") }
        if card["state"].text == "vacant" { return t("banner.vacant") }
        return t(card["has_transcript"].flag ? "banner.transcript" : "banner.inbox")
    }
    func ago(_ node: Node, now: Date = Date()) -> String {
        guard let date = Timeline.date(node) else { return node.text }
        let seconds = max(0, now.timeIntervalSince(date))
        if seconds < 60 { return t("time.just_now") }
        if seconds < 3600 { return t("time.minutes_ago", ["n": String(Int(seconds / 60))]) }
        if seconds < 86400 { return t("time.hours_ago", ["n": String(Int(seconds / 3600))]) }
        return day(node)
    }
    func day(_ node: Node) -> String {
        guard let date = Timeline.date(node) else { return node.text }
        if Calendar.current.isDateInToday(date) { return t("time.today") }
        if Calendar.current.isDateInYesterday(date) { return t("time.yesterday") }
        let format = DateFormatter(); format.locale = Locale(identifier: words.language); format.dateStyle = .medium; return format.string(from: date)
    }
    func clock(_ node: Node) -> String {
        guard let date = Timeline.date(node) else { return node.text }
        let format = DateFormatter(); format.locale = Locale(identifier: words.language); format.timeStyle = .short; return format.string(from: date)
    }
    func ruleScope(_ rule: Node) -> String {
        let tools = rule["tools"].rows.map(\.text)
        var parts = [tools == ["Reply"] ? t("cc.scope_reply") : tools.joined(separator: " / ")]
        if !rule["path_glob"].text.isEmpty { parts.append(t("cc.scope_path", ["glob": rule["path_glob"].text])) }
        if !rule["input_contains"].rows.isEmpty { parts.append(t("cc.scope_contains", ["words": rule["input_contains"].rows.map(\.text).joined(separator: ", ")])) }
        let who = (rule["roles"].rows + rule["members"].rows).map(\.text), except = (rule["except_roles"].rows + rule["except_members"].rows).map(\.text)
        if !who.isEmpty { parts.append(t("cc.scope_who", ["names": who.joined(separator: ", ")])) }; if !except.isEmpty { parts.append(t("cc.scope_except", ["names": except.joined(separator: ", ")])) }
        return parts.joined(separator: " · ")
    }
    func protocolReference(_ reference: String) -> String {
        let parts = reference.split(separator: "/", maxSplits: 1).map(String.init)
        guard parts.count == 2 else { return reference }
        return t("org.protocol_ref", ["id": parts[1], "org": organizations.first { $0["id"].text == parts[0] }?["name"].text ?? parts[0]])
    }
    var displayMessages: [Node] {
        guard !member.isEmpty else { return messages }
        return Timeline.conversation(steps: conversation["steps"].rows, chat: messages, member: selectedMember, live: displayLiveItems, words: words)
    }
    var displayLiveItems: [Node] { Timeline.activeLive(liveItems, status: liveStatus, decisions: snapshot["decisions"].rows) }
    func unread(_ member: String = "") -> Int {
        let key = member.isEmpty ? "group" : "member:" + member, since = defaults.integer(forKey: "seen." + organization + "/" + key)
        return snapshot["chats"][key]["ids"].rows.filter { $0.rows.count > 1 && $0.rows[0].integer > since && $0.rows[1].text != "human" }.count
    }
    func lastLine(_ member: String = "") -> String {
        let last = snapshot["chats"][member.isEmpty ? "group" : "member:" + member]["last"]
        if last["body"].text.isEmpty { return member.isEmpty ? t("side.group_sub") : "" }
        return t(last["type"].text == "receipt" ? "side.last_receipt" : "side.last_line", ["name": name(last["from"].text), "text": String(last["body"].text.prefix(70))])
    }
    func decisionTitle(_ decision: Node) -> String {
        let id = decision["id"].text, who = name(decision["member"].text)
        switch decision["kind"].text {
        case "permission": return t("decision.permission", ["name": who, "what": decision["title"].text])
        case "approval":
            let requester = decision["requester_org"].text.isEmpty || decision["requester_org"].text == organization ? name(decision["requester"].text) : t("common.member_of_org", ["member": decision["requester"].text, "org": decision["requester_org_name"].text])
            return t("decision.approval", ["requester": requester, "what": decision["label"].text.isEmpty ? decision["text"].text : decision["label"].text, "id": id])
        case "trajectory":
            let whose = decision["member"].text == decision["requester"].text ? t("decision.own_seat") : t("decision.member_seat", ["name": who])
            let which = decision["carrier"].integer > 0 ? t("decision.earlier_session", ["n": decision["carrier"].text]) : t("decision.current_session")
            return t("decision.trajectory", ["requester": name(decision["requester"].text), "whose": whose, "which": which])
        case "wake": return t("decision.wake_failed", ["name": who])
        case "task": return t("decision.task_blocked", ["id": id, "title": decision["title"].text])
        default: return decision["title"].text
        }
    }
    func approvalNote(_ decision: Node) -> String {
        if decision["approver"].text == "human" { return t("decision.approval_human") }
        if decision["approver"].text == "secretary-general", let cabinet = organizations.first(where: { $0["cabinet"].flag }), !cabinet["leader"].text.isEmpty { return t("decision.approval_sg", ["name": cabinet["leader"].text]) }
        return ""
    }
}
