"""Readable organization context for one member (injected by hooks and returned by status)."""
import json
import time

from .store import REPLY, WAY_PAST, away_note, has_check, language_name

RECENT_TROUBLE = 24 * 3600  # a check program's failures are mentioned for a day after the latest one
DOCUMENTS_ABOVE = 15  # document names of each organization above in a member's context, the most recently written first


def _pause_text(what, pause):
    end = ("Relic asks %s every 2 hours whether the reason is still there; to end it at a set time, switch it off again "
           "with until" % (pause.get("by") or "whoever paused it")) if pause.get("review") else (
        "it ends %s%s" % (pause.get("until"), {"quota:codex": " once the Codex limit has really reset",
                                                "idle": " once the person has left the computer"}.get(
                                                    pause.get("wait_for"), "")))
    return "%s is paused by %s since %s (%s): %s." % (what, pause.get("by") or "?", pause.get("at"),
                                                     (pause.get("reason") or "no reason given")[:200], end)


def pause_lines(store, org, member):
    """Pauses that touch this member, and the member's questions to the person that are running."""
    lines = []
    if org.get("pause") and not org.get("auto_wake", True):
        lines.append(_pause_text("Auto-wake in this organization", org["pause"]))
    seat = org["members"].get(member) or {}
    if seat.get("pause") and not seat.get("auto_wake", True):
        lines.append(_pause_text("Your seat's auto-wake", seat["pause"]))
    drive = org.get("drive") or {}
    if drive.get("pause") and not drive.get("on"):
        lines.append(_pause_text("Keep-going here", drive["pause"]))
    for ask in sorted((org.get("asks") or {}).values(), key=lambda a: a.get("due") or ""):
        if ask.get("status") == "open" and member in (ask.get("asker"), ask.get("executor")):
            lines.append("Question to the person (message #%s by %s): if the person has not written to %s by %s, %s goes "
                         "ahead with: %s" % (ask["message_id"], ask["asker"], ask["asker"], ask["due"],
                                             ask.get("executor") or ask["asker"], ask["recommend"][:300]))
    return lines


def _stops_calls(protocol):
    """Whether a protocol has a strong rule on tool calls (a rule on Reply judges the reply instead)."""
    return protocol.get("strength") == "strong" and any(r.get("tools") != [REPLY] for r in protocol.get("rules") or [])


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
    if rule["effect"] == "check":
        return "%s is judged by its check program%s (if the program fails: %s)" % (what, who,
                                                                                  rule.get("on_error") or "allow")
    return "%s is blocked%s" % (what, who)


def _drive_line(org, member, above):
    """Keep-going (wake.drive_check) on here or above: what the person wants, and who decides the next step."""
    for place in [org] + list(above):
        drive = place.get("drive") or {}
        if not drive.get("on"):
            continue
        from .wake import DRIVE_QUIET
        mine = place["id"] == org["id"] and drive.get("driver") == member
        goal = drive.get("goal") or ""
        goal = goal if len(goal) <= 400 else goal[:400] + "..."
        return ("Keep-going (持续推进) is on for %s and the organizations below it; the driver is %s. The person wants "
                "the work to go on without waiting for them: when you finish a step, send the result and the next step "
                "you propose to whoever gave you the work. When nobody there has worked for %d minutes and work is "
                "unfinished, %s a keep-going notice to decide the next step and start it. The person's standing "
                "instruction: %s" % (place["name"], "you" if mine else drive.get("driver"), DRIVE_QUIET // 60,
                                     "you get" if mine else "the driver gets", goal))
    return None


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
    try:
        away = away_note(store.person_away()).strip()
    except Exception:  # not knowing whether the person is around never breaks the context
        away = ""
    if away:
        lines.append(away)
    above = store.ancestors(org)
    documents_above = _documents_above(above) if full else ""
    if org.get("auto_wake", True):
        lines.append("Auto-wake is on: a member you message gets a turn in its own session automatically when that seat "
                     "has a configured session and is idle; others read it at their next tool call.")
    keep = _drive_line(org, member, above)
    if keep:
        lines.append(keep)
    slack_line = _slack_note(store, org)
    if slack_line:
        lines.append(slack_line)
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
    if above:
        lines.append("Above this organization: %s. Their members can see it, write to its members, assign its tasks "
                     "and issue protocols that take effect here directly. You report to them with message (org=<id>, "
                     "to=[member]) and can read them: status (org=<id>) shows one read-only and work op=doc_read "
                     "(org=<id>, key=...) reads its documents; the rest of their work belongs to them."
                     % ", ".join("%s (%s)" % (a["name"], a["id"]) for a in above))
    below = store.descendants(org["id"])
    if below:
        lines.append("Below this organization: %s. As a member you can act there with the org argument: status (see "
                     "it), message (write to its members), work op=task (assign or update its tasks; doc_read reads its "
                     "documents) and protocol op=propose (a protocol that takes effect there directly). protocol "
                     "inherit=true makes a protocol bind every organization below the one it belongs to. Their members "
                     "read this organization's documents and status too (read-only), so what they should keep knowing "
                     "(run settings, working practices) can be a document instead of a protocol."
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
    if any(_stops_calls(p) for p in active) or any(_stops_calls(p) for _, p in inherited):
        lines.append(WAY_PAST)
    lines += pause_lines(store, org, member)
    for ref, title, kinds, latest in store.check_trouble(org):
        if time.time() - latest < RECENT_TROUBLE:
            lines.append("The check program of %s '%s' has failed (%s; latest %s UTC): calls it covers are allowed or "
                         "blocked as its on_error says. Propose a revision (supersedes) that fixes it." % (
                             ref, title, ", ".join("%s x%d" % (k, n) for k, n in sorted(kinds.items())),
                             time.strftime("%Y-%m-%d %H:%M", time.gmtime(latest))))
    gone = store.retired_by_person(org)
    if gone:
        lines.append("Retired by the person (they no longer bind anyone here; do not propose them again as they were): "
                     + "; ".join("%s '%s' (%s)" % (ref, title, when[:10]) for ref, title, when in gone))
    pending = [p for p in org["protocols"].values() if p["status"] == "proposed" and member not in p["votes"]]
    for p in pending:
        lines.append("Proposal awaiting your vote: %s '%s' by %s (%s)." % (p["id"], p["title"], p["author"], p["strength"])
                     + (" It runs a check program: read its code and examples with protocol op=list protocol_id=%s "
                        "before you vote, and say in your vote what you checked." % p["id"] if has_check(p) else ""))
    reviews = [r for r in org["reviews"].values()
               if r["status"] == "pending" and r["subject"] != member and r.get("kind", "review") == "review"]
    for r in reviews[:5]:
        lines.append("Review requested: %s by %s for %s: %s%s" % (r["id"], r["subject"], r["tool"], r["summary"][:120],
                                                                 (" (why: %s)" % r["why"][:160]) if r.get("why") else ""))
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
    if documents_above:
        lines.append(documents_above)
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


def _slack_note(store, org):
    """While the person's Slack is connected and this organization may read it, say so (relic_core/slack.py)."""
    try:
        from . import slack
        return slack.context_note(store, org)
    except Exception:  # a broken Slack setting never breaks a member's context
        return ""


def _outline(store, org):
    """What both views of an organization from outside show (render_below, render_above): its purpose, governance and
    members, the titles of the protocols in effect there and its open tasks."""
    lines = []
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
    return lines


def _documents_index(org):
    """The index of an organization's documents, as both views from outside show it."""
    if not org["documents"]:
        return []
    return ["Shared documents (work op=doc_read org=%s key=...): %s" % (
        org["id"], ", ".join("%s(r%d)" % (k, v["revision"]) for k, v in org["documents"].items()))]


def _documents_above(above):
    """One line naming the documents of each organization above (nearest first), for a member's context: members below
    read them (work op=doc_read org=<id>), so an organization above can keep what they should know in a document
    instead of a protocol. At most DOCUMENTS_ABOVE names an organization, the most recently written first."""
    parts = []
    for place in above:
        names = [k for k, _ in sorted((place.get("documents") or {}).items(), key=lambda kv: kv[1].get("at") or "",
                                      reverse=True)]
        if names:
            more = len(names) - DOCUMENTS_ABOVE
            parts.append("%s (%s): %s%s" % (place["name"], place["id"], ", ".join(names[:DOCUMENTS_ABOVE]),
                                            (", +%d more" % more) if more > 0 else ""))
    if not parts:
        return ""
    return "Documents of the organizations above (work op=doc_read org=<id> key=...): " + "; ".join(parts)


def render_above(store, org, viewer_org, viewer):
    """An organization above the viewer's, as a member of the organization below sees it (status org=<it>): read-only,
    and what render_below shows of an organization except its messages, episodes, finished tasks and the
    organizations below it. Nothing that belongs to its members alone: no reviews, proposals or votes, trajectory
    requests, unread messages or notes (render_below leaves those out too)."""
    lines = ["Organization '%s' (%s), above your organization '%s'. You see it from below, read-only: read its "
             "documents (work op=doc_read org=%s key=...) and report to its members (message org=%s, to=[member]); "
             "the rest of its work belongs to them." % (org["name"], org["id"], viewer_org["name"], org["id"],
                                                         org["id"])]
    return "\n".join(lines + _outline(store, org) + _documents_index(org))


def render_below(store, org, viewer_org, viewer):
    """An organization below the viewer's, as a member of the organization above sees it."""
    lines = ["Organization '%s' (%s), below your organization '%s'. You see it from above: write to its members "
             "(message org=%s), assign or update its tasks (work op=task org=%s) and issue protocols that take effect "
             "here directly (protocol op=propose org=%s)." % (org["name"], org["id"], viewer_org["name"], org["id"],
                                                                 org["id"], org["id"])]
    lines += _outline(store, org)
    done = sorted((t for t in org["tasks"].values() if t["status"] == "done"), key=lambda t: t.get("done_at") or "")
    if done:
        lines.append("Recently done: " + "; ".join("%s %s (%s)" % (t["id"], t["title"], t["owner"]) for t in done[-5:]))
    lines += _documents_index(org)
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
