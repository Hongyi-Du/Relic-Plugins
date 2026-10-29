import Foundation
import RelicCore

extension Model {
    func clippedDecisionError(_ value: String) -> String {
        let normalized = value.replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression).trimmingCharacters(in: .whitespacesAndNewlines)
        return normalized.utf16.count > 140 ? String(decoding: Array(normalized.utf16.prefix(139)), as: UTF16.self) + "…" : normalized
    }
    func taskReportPreview(_ value: String) -> String {
        let stripped = value.replacingOccurrences(of: "[#*`>|_-]+", with: " ", options: .regularExpression)
        let normalized = stripped.replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression).trimmingCharacters(in: .whitespacesAndNewlines)
        return normalized.utf16.count > 80 ? String(decoding: Array(normalized.utf16.prefix(79)), as: UTF16.self) + "…" : normalized
    }
    func overviewMemberDetail(_ member: Node) -> String {
        var parts: [String] = []
        if !member["ex_officio"].isNull { parts.append(t("card.ex_officio", ["org": member["ex_officio"]["org_name"].text])) }
        parts.append([member["doing"].text, member["detail"].text].first { !$0.isEmpty } ?? stateLabel(member["state"].text))
        return parts.filter { !$0.isEmpty }.joined(separator: " · ")
    }
    func overviewProtocolDetail(_ p: Node, source: String) -> String {
        func issuer() -> String { t(p["issued_by"]["person"].flag ? "org.issued_by_person" : "org.issued_by", ["name": p["issued_by"]["name"].text]) }
        if source == "replaced_protocols" { return t(p["how"].text == "retired" ? "org.protocol_retired" : "org.protocol_overridden", ["from": p["from"].text, "at": p["at"].text, "by": p["by"].text]) }
        var parts: [String] = []
        if source == "inherited_protocols" {
            parts.append(t("org.inherited_from", ["name": p["from"].text]))
            if !p["issued_by"]["name"].text.isEmpty { parts.append(issuer()) }
        } else {
            if !p["issued_by"].isNull { parts.append(issuer()) }
            else { parts.append(t(p["status"].text == "proposed" ? "org.protocol_voting" : "org.protocol_used", ["n": p[p["status"].text == "proposed" ? "votes" : "uses"].text])) }
            if p["replaces_above"].flag && !p["supersedes"].text.isEmpty { parts.append(t("org.protocol_overrides", ["ref": protocolReference(p["supersedes"].text)])) }
            if p["inherit"].flag { parts.append(t("org.protocol_inherits")) }
        }
        if p["check"].flag { parts.append(t("org.protocol_check")) }
        return parts.filter { !$0.isEmpty }.joined(separator: " · ")
    }
}
