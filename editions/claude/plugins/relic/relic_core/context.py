"""Readable organization context for one member (injected by hooks and returned by status)."""
import json


def _rule_text(rule):
    who = ""
    if rule.get("roles"):
        who += " for roles " + "/".join(rule["roles"])
    if rule.get("members"):
        who += " for " + "/".join(rule["members"])
    if rule.get("except_roles") or rule.get("except_members"):
        who += " except " + "/".join(rule.get("except_roles", []) + rule.get("except_members", []))
    what = "/".join(rule["tools"])
    if rule.get("path_glob"):
        what += " on " + rule["path_glob"]
    if rule.get("input_contains"):
        what += " containing " + ", ".join(rule["input_contains"])
    if rule["effect"] == "require_before":
        need = "/".join(rule["before"]["tools"])
        if rule["before"].get("input_contains"):
            need += " containing " + ", ".join(rule["before"]["input_contains"])
        return "%s requires %s after your latest edit%s" % (what, need, who)
    if rule["effect"] == "require_review":
        return "%s needs another member's approval%s" % (what, who)
    return "%s is blocked%s" % (what, who)


def render(store, org, member, unread_count=None, full=True):
    seat = org["members"][member]
    lines = ["Relic organization '%s' (%s). You are member '%s'%s." % (
        org["name"], org["id"], member, (" with role '%s'" % seat["role"]) if seat.get("role") else "")]
    if org.get("purpose"):
        lines.append("Purpose: " + org["purpose"])
    gov = ("leader-led (leader: %s)" % org["leader"]) if org["governance"] == "leader" else "peer (majority)"
    roster = ", ".join("%s%s" % (m, ("[%s]" % s["role"]) if s.get("role") else "") for m, s in org["members"].items())
    lines.append("Governance: %s. Members: %s." % (gov, roster))
    active = [p for p in org["protocols"].values() if p["status"] == "active"]
    if active:
        lines.append("Active protocols (organization-owned; they outlive any one member):")
        for p in active:
            if p["strength"] == "weak":
                lines.append("- %s v%d [weak] %s. When: %s. Guidance: %s" % (p["id"], p["version"], p["title"], p["trigger"], p["guidance"]))
            else:
                lines.append("- %s v%d [strong, enforced] %s: %s" % (p["id"], p["version"], p["title"],
                                                                      "; ".join(_rule_text(r) for r in p["rules"])))
    pending = [p for p in org["protocols"].values() if p["status"] == "proposed" and member not in p["votes"]]
    for p in pending:
        lines.append("Proposal awaiting your vote: %s '%s' by %s (%s)." % (p["id"], p["title"], p["author"], p["strength"]))
    reviews = [r for r in org["reviews"].values() if r["status"] == "pending" and r["subject"] != member]
    for r in reviews[:5]:
        lines.append("Review requested: %s by %s for %s: %s" % (r["id"], r["subject"], r["tool"], r["summary"][:120]))
    mine = [t for t in org["tasks"].values() if t["owner"] == member and t["status"] not in ("done", "dropped")]
    if mine:
        lines.append("Your open tasks: " + "; ".join("%s %s (%s)" % (t["id"], t["title"], t["status"]) for t in mine[:8]))
    others = [t for t in org["tasks"].values() if t["owner"] != member and t["status"] not in ("done", "dropped")]
    if others and full:
        lines.append("Others' open tasks: " + "; ".join("%s %s -> %s (%s)" % (t["id"], t["title"], t["owner"], t["status"]) for t in others[:10]))
    if org["documents"] and full:
        lines.append("Shared documents: " + ", ".join("%s(r%d)" % (k, v["revision"]) for k, v in org["documents"].items()))
    opened = [e for e in org["episodes"].values() if e["status"] == "open" and member in e["participants"]]
    if opened:
        lines.append("Open episodes you take part in: " + "; ".join("%s %s (owner %s)" % (e["id"], e["title"], e["owner"]) for e in opened[:5]))
    due = store.reflection_due(org, member)
    if due:
        lines.append("Reflection due on closed episodes: " + ", ".join(due))
    if seat.get("notes") and full:
        lines.append("Your private notes: " + " | ".join(seat["notes"][-5:]))
    if unread_count:
        lines.append("You have %d unread message(s); call the inbox tool." % unread_count)
    return "\n".join(lines)


def render_messages(messages):
    return "\n".join("[msg %d from %s%s] %s" % (m["id"], m["from"], (" ep " + m["episode_id"]) if m.get("episode_id") else "",
                                               m["body"]) for m in messages)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=1)
