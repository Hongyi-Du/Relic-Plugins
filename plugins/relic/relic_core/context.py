"""Readable organization context for one member (injected by hooks and returned by status)."""
import json

from .store import language_name


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
    roster = ", ".join("%s%s(%s)" % (m, ("[%s]" % s["role"]) if s.get("role") else "", s.get("harness", "claude-code"))
                       for m, s in org["members"].items())
    lines.append("Governance: %s. Members (harness in parentheses): %s." % (gov, roster))
    lines.append("The person reads %s; write task titles, task reports and anything addressed to the person in that "
                 "language." % language_name())
    if org.get("auto_wake", True):
        lines.append("Auto-wake is on: a member you message gets a turn in its own session automatically when that seat "
                     "has a configured session and is idle; others read it at their next tool call.")
    if len({s.get("harness", "claude-code") for s in org["members"].values()}) > 1:
        lines.append("Members run on different harnesses (Claude Code, Codex). Protocol rules use one tool vocabulary for "
                     "everyone: Bash for shell commands, Edit/Write for file changes (Codex apply_patch counts as Edit), "
                     "Read for reads.")
    if org.get("kind") == "subgroup":
        lines.append("This is a subgroup, made for one piece of work under %s; it inherits that organization's "
                     "protocols. Its leader closes it with group op=close when the work is done."
                     % _org_name(store, org.get("parent")))
    if org.get("cabinet"):
        lines.append("This organization is the cabinet (secretariat); its leader is the secretary-general, who "
                     "approves changes to the formal organizations (group op=approve | deny). The leader of every "
                     "formal organization holds a seat here.")
        if org.get("leader") == member:
            for r in [r for r in (org.get("requests") or {}).values() if r["status"] == "pending"][:8]:
                lines.append("Approval request %s from %s: %s.%s Your call: group op=approve or op=deny, request_id=%s."
                             % (r["id"], _requester(r), store.request_text(r),
                                (" Reason: " + r["reason"][:200]) if r.get("reason") else "", r["id"]))
    seat_office = seat.get("ex_officio")
    if seat_office:
        lines.append("You hold this seat ex officio, as the leader of %s." % _org_name(store, seat_office.get("org")))
    above = store.ancestors(org)
    if above:
        lines.append("Above this organization: %s. Their members can see it, write to its members, assign its tasks "
                     "and issue protocols that take effect here directly. You report to them with message (org=<id>, "
                     "to=[member]); their work belongs to them." % ", ".join("%s (%s)" % (a["name"], a["id"]) for a in above))
    below = store.descendants(org["id"])
    if below:
        lines.append("Below this organization: %s. As a member you can act there with the org argument: status (see "
                     "it), message (write to its members), work op=task (assign or update its tasks; doc_read reads its "
                     "documents) and protocol op=propose (a protocol that takes effect there directly). protocol "
                     "inherit=true makes a protocol bind every organization below the one it belongs to."
                     % ", ".join("%s (%s)" % (b["name"], b["id"]) for b in below))
    chats = [m for m, s in org["members"].items() if s.get("harness") in ("chatgpt", "claude-chat")]
    if chats:
        lines.append("Chat members (%s) discuss and have no files or commands. A chatgpt member gets the full text of "
                     "messages written to it in its ChatGPT chat; the ChatGPT app keeps its replies from plugins, so the "
                     "person forwards each one in the Relic App and it comes back as its message. A claude-chat "
                     "member reads its messages with inbox when it is working." % ", ".join(chats))
    active = [p for p in org["protocols"].values() if p["status"] == "active"]
    if active:
        lines.append("Active protocols (organization-owned; they outlive any one member):")
        for p in active:
            source = ", issued by %s" % p["issued_by"]["name"] if p.get("issued_by") else ""
            if p["strength"] == "weak":
                lines.append("- %s v%d [weak%s] %s. When: %s. Guidance: %s" % (p["id"], p["version"], source, p["title"], p["trigger"], p["guidance"]))
            else:
                lines.append("- %s v%d [strong, enforced%s] %s: %s" % (p["id"], p["version"], source, p["title"],
                                                                      "; ".join(_rule_text(r) for r in p["rules"])))
        lines.append("When one of these shaped your work, or you chose not to follow it, record it once with protocol "
                     "op=use (followed, deviated or inapplicable). That is how the organization learns which protocols "
                     "help and which to revise or retire.")
    lineage = store.inheritance(org)
    inherited = lineage["inherited"]
    if inherited:
        lines.append("Protocols from the organizations above (they bind this organization too; record their use with "
                     "protocol op=use org=<that organization's id>; this organization can override one with "
                     "supersedes=<org id>/<P#> or stop it here with retire_target=<org id>/<P#>, by its own vote, "
                     "unless it was issued from above):")
        for above, p in inherited:
            if p["strength"] == "weak":
                lines.append("- %s/%s v%d [weak, from %s] %s. When: %s. Guidance: %s" % (
                    above["id"], p["id"], p["version"], above["name"], p["title"], p["trigger"], p["guidance"]))
            else:
                lines.append("- %s/%s v%d [strong, enforced, from %s] %s: %s" % (
                    above["id"], p["id"], p["version"], above["name"], p["title"],
                    "; ".join(_rule_text(r) for r in p["rules"])))
    for above, p, level, by, how in lineage["replaced"]:
        lines.append("- %s/%s '%s' of %s is %s by %s %s and does not bind here." % (
            above["id"], p["id"], p["title"], above["name"], how, level["name"], by))
    pending = [p for p in org["protocols"].values() if p["status"] == "proposed" and member not in p["votes"]]
    for p in pending:
        lines.append("Proposal awaiting your vote: %s '%s' by %s (%s)." % (p["id"], p["title"], p["author"], p["strength"]))
    reviews = [r for r in org["reviews"].values() if r["status"] == "pending" and r["subject"] != member]
    for r in reviews[:5]:
        lines.append("Review requested: %s by %s for %s: %s" % (r["id"], r["subject"], r["tool"], r["summary"][:120]))
    asks = [r for r in org.get("trajectory_requests", {}).values() if r["approver"] == member and r["status"] == "pending"]
    for r in asks[:5]:
        lines.append("Trajectory request %s: %s asks to read %s (reason: %s). Your call: trajectory op=answer." % (
            r["id"], r["requester"], "your session" if r["carrier"] == 0 else "carrier #%d of your seat" % r["carrier"],
            r["reason"][:120]))
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
    """One line per message: its id (what message reply_to takes), the organization of the seat it reached when that
    is not the main one ("[msg 12 · 秘书处 from chief]"), sender, episode and, for a reply, its thread."""
    text = "\n".join("[msg %d%s from %s%s%s] %s" % (
        m["id"], (" · %s" % m["org_name"]) if m.get("org_name") else "",
        m["from"] + (" of %s" % m["from_org"] if m.get("from_org") else ""),
        (" ep " + m["episode_id"]) if m.get("episode_id") else "", _thread_of(m), m["body"]) for m in messages)
    elsewhere = list(dict.fromkeys((m["org_name"], m["org_id"]) for m in messages if m.get("org_id")))
    if elsewhere:
        text += ("\n(Messages marked with an organization reached your seat there: reply with org=<its id> (%s), and "
                 "do its work with org too.)" % ", ".join("%s = %s" % pair for pair in elsewhere))
    return text


def render_seats(store, actor, current=None):
    """One line on the session's other seats (organization, member, role, unread) and how to act in them."""
    seats = store.seats_of(store.split_actor(actor)[0])
    if len(seats) < 2:
        return ""
    unread = {}
    for m in store.unread(store.split_actor(actor)[0], mark=False, limit=200):
        unread[m.get("org_id")] = unread.get(m.get("org_id"), 0) + 1
    main = seats[0][0]
    parts = []
    for org, member, is_main in seats:
        if org["id"] == current:
            continue
        role = org["members"][member].get("role")
        n = unread.get(None if is_main else org["id"], 0)
        parts.append("%s (%s) as %s%s%s%s" % (org["name"], org["id"], member, (" [%s]" % role) if role else "",
                                              ", main seat" if is_main else "", (", %d unread" % n) if n else ""))
    return ("You also hold seats in: %s. Relic tools act in your main seat (%s) unless you pass org=<id>; with org you "
            "act as that seat's member, and while you do an organization's work you follow its protocols."
            % ("; ".join(parts), main["name"]))


def _requester(r):
    who = r.get("requester") or {}
    return "%s of %s" % (who.get("member"), who.get("org_name")) if who.get("org") else "a session outside the organizations"


def _org_name(store, org_id):
    try:
        return store.get(org_id)["name"]
    except Exception:
        return str(org_id)


def render_below(store, org, viewer_org, viewer):
    """An organization below the viewer's, as a member of the organization above sees it."""
    lines = ["Organization '%s' (%s), below your organization '%s'. You see it from above: write to its members "
             "(message org=%s), assign or update its tasks (work op=task org=%s) and issue protocols that take effect "
             "here directly (protocol op=propose org=%s)." % (org["name"], org["id"], viewer_org["name"], org["id"],
                                                                 org["id"], org["id"])]
    if org.get("purpose"):
        lines.append("Purpose: " + org["purpose"])
    gov = ("leader-led (leader: %s)" % org["leader"]) if org["governance"] == "leader" else "peer (majority)"
    roster = ", ".join("%s%s(%s)" % (m, ("[%s]" % s["role"]) if s.get("role") else "", s.get("harness", "claude-code"))
                       for m, s in org["members"].items())
    lines.append("Governance: %s. Members (harness in parentheses): %s." % (gov, roster or "none yet"))
    protocols = [p for p in org["protocols"].values() if p["status"] == "active"]
    inherited = store.inherited_protocols(org)
    if org.get("kind") == "subgroup":
        lines.append("A subgroup (%s) for one piece of work." % org.get("status"))
    if protocols or inherited:
        lines.append("Protocols in effect:")
        for p in protocols:
            source = " (issued by %s)" % p["issued_by"]["name"] if p.get("issued_by") else ""
            lines.append("- %s v%d [%s] %s%s" % (p["id"], p["version"], p["strength"], p["title"], source))
        for above, p in inherited:
            lines.append("- %s/%s v%d [%s] %s (binds it from %s)" % (above["id"], p["id"], p["version"], p["strength"],
                                                                    p["title"], above["name"]))
    tasks = [t for t in org["tasks"].values() if t["status"] not in ("done", "dropped")]
    if tasks:
        lines.append("Open tasks: " + "; ".join("%s %s -> %s (%s)" % (t["id"], t["title"], t["owner"], t["status"])
                                               for t in tasks[:15]))
    done = sorted((t for t in org["tasks"].values() if t["status"] == "done"), key=lambda t: t.get("done_at") or "")
    if done:
        lines.append("Recently done: " + "; ".join("%s %s (%s)" % (t["id"], t["title"], t["owner"]) for t in done[-5:]))
    if org["documents"]:
        lines.append("Shared documents (work op=doc_read org=%s key=...): %s" % (
            org["id"], ", ".join("%s(r%d)" % (k, v["revision"]) for k, v in org["documents"].items())))
    opened = [e for e in org["episodes"].values() if e["status"] == "open" and e.get("kind") != "turn"]
    if opened:
        lines.append("Open episodes: " + "; ".join("%s %s (owner %s)" % (e["id"], e["title"], e["owner"]) for e in opened[:5]))
    recent = store.history(org["id"], 12)
    if recent:
        lines.append("Recent messages:")
        for m in recent:
            lines.append("- [msg %d %s -> %s] %s" % (m["id"], m["from"], ", ".join(m["to"]), " ".join(m["body"].split())[:160]))
    below = store.descendants(org["id"])
    if below:
        lines.append("Below it: " + ", ".join("%s (%s)" % (b["name"], b["id"]) for b in below))
    return "\n".join(lines)


def _thread_of(message):
    """', in thread #12 ("start of message 12")' for a reply (store.unread gives it the start of its thread)."""
    root = message.get("reply_to")
    if not root:
        return ""
    start = (message.get("thread") or {}).get("snippet")
    return ", in thread #%d%s" % (root, (' ("%s")' % start) if start else "")


def dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=1)
