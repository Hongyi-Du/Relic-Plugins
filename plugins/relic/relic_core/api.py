"""The Relic tools: their schemas and what each call does. server.py serves them over MCP stdio and reloads this module
(and the rest of relic_core) when the plugin is updated, so a session that stays open keeps up with the plugin.

The caller's identity ("actor") is filled in by the plugin's PreToolUse hook, which knows the Claude Code session and
subagent making the call. Agents never need to pass it themselves.
"""
import os
import time

from . import wake
from .context import render, render_below, render_messages, render_seats
from .store import OrgError

S = {"type": "string"}
SL = {"type": "array", "items": {"type": "string"}}
ORG = {"type": "string", "description": "Another organization, by id or exact name: one you hold a seat in (you act "
                                        "there as its member and follow its protocols), one below yours, where you "
                                        "can act, or one above it, which you report to."}
SEAT = {"type": "string", "description": "An organization you hold a seat in, by id or exact name: act there as its "
                                         "member (default: your main seat)."}
ACTOR = {"type": "string", "description": "Filled in automatically by the Relic hook. Leave it out."}
MAX_WAIT = 600  # seconds an inbox call may wait for a reply (Codex: tool_timeout_sec in codex.mcp.json is above it)


def max_wait():
    """RELIC_MAX_WAIT lowers the limit for a client that gives tools less time (the Claude desktop app's chat)."""
    try:
        return max(0, min(MAX_WAIT, int(os.getenv("RELIC_MAX_WAIT") or MAX_WAIT)))
    except ValueError:
        return MAX_WAIT


def tool(name, description, props, required=()):
    props = dict(props, actor=ACTOR)
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": props, "required": list(required)}}


RULE = {"type": "object", "description": (
    "effect: deny | require_review | require_before | check. tools: tool-name globs such as Bash, Edit, Write. "
    "Optional: input_contains [substrings of the tool input], path_glob (file path pattern), members/roles it applies to, "
    "except_members/except_roles (e.g. the owner), before {tools, input_contains} for require_before, reason. "
    "check runs a judgment program of yours on the calls the rule covers, for what the other effects cannot express: "
    "tools must name the tools it judges (not every tool); code: Python, standard library only, defining check(call) "
    "that returns {decision: allow|deny|review, reason} (review: another member approves the exact action; deny and "
    "review need a reason, which the member reads). call: tool and input (Bash for shell commands, Edit for patches), "
    "member, role, harness, org_id, org_name, protocol_id, protocol_title, recent (the member's latest 20 tool calls "
    "here, newest first: tool, kind edit|run|other, summary, failed, at, ts), last_edit_at/last_edit_ts (its latest "
    "edit, or null), now/now_ts (times are ISO UTC text and seconds; use now_ts, not the clock, so examples hold). "
    "examples: 2-12 {call, expect, note?}, calls the rule covers (fields left out get defaults), at least one allow and "
    "one deny or review; all run when you propose and must come out as expected. on_error: allow (default) or deny, "
    "for a program that fails (timeout 3 s, an exception, an answer that is not a decision) or whose code changed "
    "after it was proposed. A rule on Reply (tools [\"Reply\"], effect check or deny) judges the reply that ends a "
    "member's turn, the text the person reads, when the turn ends: call.input is {text}; a deny sends the member back "
    "once to write the reply again (a program on Reply answers allow or deny).")}

TOOLS = [
    tool("create", "Create a new Relic organization and join it as its first member. Use when the human asks for an "
         "organization or team. governance 'leader' makes you leader; 'peer' means decisions by majority.",
         {"name": S, "purpose": S, "member": S, "role": S, "governance": {"enum": ["leader", "peer"]}},
         ["name", "purpose", "member"]),
    tool("join", "Join an organization as a member (a seat). Joining an existing seat makes you its new carrier: you "
         "inherit its role, tasks and the organization's protocols, but not the previous carrier's private notes.",
         {"org_id": S, "member": S, "role": S}, ["org_id", "member"]),
    tool("status", "Your view of the organization: members and roles, active protocols, proposals to vote on, review "
         "requests, tasks, documents, reflection due, unread messages. With org (an organization below yours): "
         "that organization as seen from above.", {"org": ORG}),
    tool("message", "Send a message to members (list of names, or ['all']); write to ['human'] to reach the person, who "
         "reads and answers it in the Relic App. Messages persist and are delivered to "
         "recipients at their next tool call. With auto-wake on (the default), a recipient whose seat has a configured "
         "session gets a turn automatically to handle it (a Codex chat open in the Codex desktop app gets it there). "
         "A ChatGPT chat member gets your message's full text in its chat; the ChatGPT app keeps the reply's text "
         "from plugins, so the person forwards it in the Relic App and it comes back to you as its message. "
         "When you need the answer in this turn, call inbox with wait afterwards. A message that reached one of your "
         "other seats is answered with org=<that organization>.",
         {"to": dict(SL, description="Member names, ['all'] or ['human']. Leave it out only with reply_to."), "body": S,
          "episode_id": S,
          "reply_to": {"type": "integer", "description": "Reply inside the thread of message #id, like a Slack thread; "
                                                         "without `to`, the thread's participants receive it."},
          "org": dict(ORG, description="An organization you hold a seat in always selects that seat, even above "
                                       "your main organization. Otherwise write to one below yours, or one above "
                                       "it to report. A sender named <org id>/<member> is answered with "
                                       "to=['<org id>/<member>'] or with org=<org id>, to=[member].")},
         ["body"]),
    tool("inbox", "Read your unread messages (marks them read), in every organization you hold a seat in; one that "
         "reached another seat than your main one names its organization. wait (seconds; the longest this client "
         "allows is applied): when nothing is unread yet, wait that long for the first message to arrive; use it after "
         "messaging a member whose answer you need in this turn, and call it again if the answer has not come yet. "
         "org: only that seat's messages. message_id: read one message addressed to your seats in full, even if "
         "already read (ignores wait). When nothing is unread, lists your open assigned tasks; an empty inbox "
         "is not an empty task list: check status.",
         {"wait": {"type": "integer"}, "org": SEAT,
          "message_id": {"type": "integer", "description": "Read or reread this message id, addressed to one of "
                         "your seats (or only the seat selected by org). Returns its full text and marks it read."}}),
    tool("work", "Shared work. op=doc_write {key, body, expected_revision} | doc_read {key?} | "
         "task {task_id?, title?, owner?, status?: open|working|blocked|done|dropped, evidence?, report?} | "
         "role {member?, role} | note {body} (private to you; not inherited by a replacement). "
         "The person reads the tasks: write task titles in the person's language, and mark a task done with evidence "
         "and a short report (at most 1000 characters, Markdown) of what it achieved and how it turned out, in the "
         "person's language too.",
         {"op": {"enum": ["doc_write", "doc_read", "task", "role", "note"]}, "key": S, "body": S,
          "expected_revision": {"type": "integer"}, "task_id": S, "title": S, "owner": S, "status": S,
          "evidence": SL,
          "report": dict(S, description="Required when a task becomes done; a done task's report can also be added "
                                        "or replaced later. A short report of what the task achieved and how it "
                                        "turned out, in the person's language: Markdown, at most 1000 characters."),
          "member": S, "role": S,
          "org": dict(ORG, description="An organization below yours: read its documents (doc_read) and assign or "
                                       "update its tasks (task; a new task needs an owner, one of its members).")},
         ["op"]),
    tool("episode", "Episodes bound a piece of work so the organization can learn from it. op=open {title, participants?} | "
         "close {episode_id, outcome: success|failure|partial|cancelled, summary, evidence?} | reflect {episode_id, body}. "
         "Reflect on friction you saw: what went wrong between members, what would prevent it next time.",
         {"op": {"enum": ["open", "close", "reflect"]}, "title": S, "participants": SL, "episode_id": S,
          "outcome": S, "summary": S, "evidence": SL, "body": S, "org": SEAT}, ["op"]),
    tool("protocol", "Organization protocols. op=propose: weak {title, rationale, guidance, trigger, scope?, evidence} is "
         "shared guidance; strong {title, rationale, episode_id (closed, reflected), rules: [rule]} is enforced on tool "
         "calls by the hook. A strong protocol with a check rule (a judgment program of yours) also needs "
         "summary_for_person; it takes effect by the organization's vote alone and is then copied to the person, who "
         "can retire it at once. Revise with supersedes, retire with retire_target. A proposal becomes active when the "
         "organization's approval threshold is reached. A protocol binds its own organization only, unless inherit is "
         "true: then the organizations below inherit it, like a class, and each can override one (supersedes="
         "<org id>/<P#>) or stop it for itself and those below (retire_target=<org id>/<P#>) by its own vote; one "
         "issued from above stays as issued. Say in trigger when it applies (e.g. when reporting to the person). "
         "op=vote {protocol_id, vote: approve|reject, reason}: before voting on a check rule, read its code and "
         "examples and say what you checked. "
         "op=use {protocol_id, outcome: followed|deviated|inapplicable, note} reports actual use. op=list; with "
         "protocol_id (P3, or <org id>/P3 from above), that protocol in full: its rules' code and examples, its note "
         "for the person, votes.",
         {"op": {"enum": ["propose", "vote", "use", "list"]}, "title": S, "rationale": S,
          "strength": {"enum": ["weak", "strong"]}, "guidance": S, "trigger": S, "scope": S, "evidence": SL,
          "episode_id": S, "rules": {"type": "array", "items": RULE},
          "summary_for_person": dict(S, description="Needed with a check rule: a short note for the person, in the "
                                                    "person's language (your context names it), on what the protocol "
                                                    "is for, what its check program judges and when it blocks or sends "
                                                    "a call for review. It is copied to the person when the protocol "
                                                    "takes effect."),
          "supersedes": S, "retire_target": S,
          "protocol_id": S, "vote": {"enum": ["approve", "reject"]}, "reason": S, "outcome": S, "note": S,
          "inherit": {"type": "boolean", "description": "The organizations below this protocol's organization "
                                                        "inherit it too (default: it binds its own organization only)."},
          "downward": {"type": "boolean", "description": "Older name of inherit."},
          "org": dict(ORG, description="An organization below yours: propose there issues the protocol and it takes "
                                       "effect directly (only an organization above can revise or retire it); "
                                       "list shows its protocols. From below: op=use records your use of a "
                                       "protocol that binds you from that organization above.")},
         ["op"]),
    tool("trajectory", "Another member's trajectory (what they said and every tool call, from their Claude Code or Codex "
         "transcript) and memory (what their harness remembers about that session: Codex memory summaries of the "
         "thread, Claude Code project memory files) are theirs: reading them needs their consent. op=request {member, "
         "reason, carrier?, memory?} asks them (carrier 0 = their current session, 1 = the carrier before, ...; your own "
         "seat's earlier carriers are approved by the human; memory defaults to true). op=answer {request_id, decision: "
         "approve|deny, note?, redact?} answers a request made to you. Approval writes the files and messages the "
         "requester their paths; nothing is put into anyone's context. API keys, tokens and passwords are masked in "
         "the exported copies unless redact=false (your own transcript is never changed). op=list shows requests "
         "waiting on you and your own requests.",
         {"op": {"enum": ["request", "answer", "list"]}, "member": S, "reason": S, "carrier": {"type": "integer"},
          "memory": {"type": "boolean"}, "request_id": S, "decision": {"enum": ["approve", "deny"]}, "note": S,
          "redact": {"type": "boolean"}, "org": SEAT}, ["op"]),
    tool("group", "Subgroups and changes to formal (standing) organizations. op=create {name, purpose, leader, parent?, "
         "members?} makes a subgroup for one piece of work under parent (default: the organization you act in), which "
         "it inherits protocols from; its members (default: every member of the formal organization at or above "
         "parent) each get a seat in it with their own session and name, and leader (one of them) leads it. No "
         "approval needed. op=close {org} closes a subgroup (its leader). op=reparent {parent, org?, reason} | leader "
         "{member, org?, reason} | dissolve {org?, reason} change a formal organization (yours, or one below it): the "
         "secretary-general (the cabinet's leader) or, without a cabinet, the person approves; you get a message when "
         "it is decided. op=approve | deny {request_id, note}: the secretary-general decides a request. op=list: "
         "requests waiting on you, your own requests and the subgroups of your organization.",
         {"op": {"enum": ["create", "close", "reparent", "leader", "dissolve", "approve", "deny", "list"]},
          "name": S, "purpose": S, "leader": S, "parent": S, "members": SL, "member": S, "reason": S,
          "request_id": S, "note": S,
          "org": dict(SEAT, description="The organization to act in or on: one you hold a seat in, or (reparent, "
                                        "leader, dissolve) one below yours.")}, ["op"]),
    tool("panel", "Open the Relic App on the person's screen: the group chat and private chats with every member, where "
         "they found organizations, add members (run in the App, or in Claude Code or Codex with model, effort, folder "
         "or worktree, permission and environment variables), seat existing sessions and chats, start or replace "
         "members' sessions, answer decisions and trajectory requests and message members. Call it when the person "
         "asks for the Relic App, window, panel or UI.", {}),
    tool("review", "Peer review required by strong protocols. op=list shows pending requests; op=approve "
         "{request_id, note} approves another member's exact action after you checked it.",
         {"op": {"enum": ["list", "approve"]}, "request_id": S, "note": S, "org": SEAT}, ["op"]),
]
SEATED_ONLY = {"inbox", "episode", "review", "trajectory"}  # org names a seat of the caller, nothing else
KNOWN = {t["name"] for t in TOOLS}


def seat_actor(store):
    """The carrier of the seat this server was started for. The Relic App gives every session it runs a Relic MCP
    server of its own (app/harness.py relic_server) whose environment names the seat (RELIC_SEAT=<org id>/<member>)
    and carries the token the App stored on the seat when it started that session (RELIC_SEAT_TOKEN). Calls from that
    session then come from the seat's carrier, in any harness, with or without Relic hooks. Once the seat has moved on
    to another session (another token), this server speaks for nobody."""
    org_id, _, member = (os.getenv("RELIC_SEAT") or "").partition("/")
    if not (org_id and member and store is not None):
        return None
    try:
        seat = (store.get(org_id).get("members") or {}).get(member) or {}
    except Exception:
        return None
    token = (seat.get("config") or {}).get("seat_token")
    if not token or token != os.getenv("RELIC_SEAT_TOKEN"):
        return None
    return seat.get("carrier") or None


def actor_of(args, meta=None, store=None):
    """The hook stamps the actor on every Relic call (Claude Code and Codex both pass PreToolUse updatedInput).
    Without trusted hooks, a Codex call still names its thread in _meta; a session the Relic App runs is named by its
    seat (seat_actor); RELIC_ACTOR is the last resort."""
    stamped = args.pop("actor", None)
    if stamped:
        return stamped
    meta = meta or {}
    thread = meta.get("openai/threadId") or meta.get("openai/thread_id") or meta.get("codexThreadId") or meta.get("threadId")
    thread = thread or os.getenv("CODEX_THREAD_ID")  # Codex desktop names the thread in the server's environment
    if thread:
        return "codex:" + str(thread)
    return seat_actor(store) or os.getenv("RELIC_ACTOR") or "local"


def call(store, name, args, meta=None):
    if name not in KNOWN:
        raise OrgError("Unknown tool " + str(name))
    actor = actor_of(args, meta, store)
    result = handle_call(store, name, args, actor)
    if name in ("message", "trajectory", "group", "create"):
        try:
            wake.dispatch_for_actor(store, actor)  # recipients with an idle configured session get a turn now
            if isinstance(result, dict) and result.get("org_id"):  # written in another organization
                wake.dispatch(store, result["org_id"])
            cab = store.cabinet() if name in ("group", "create") else None
            if cab:  # a request for the secretary-general
                wake.dispatch(store, cab["id"])
        except Exception:
            pass
    return result


def inbox(store, actor, wait=0, poll=2.0, sleep=time.sleep, clock=time.time, message_id=None):
    """Unread messages, marked read; with wait, first wait up to that many seconds for one to arrive."""
    store.require(actor)
    if message_id is not None:
        messages = store.unread(actor, message_id=message_id)
        if not messages:
            raise OrgError("No message #%s is addressed to your selected seats." % message_id)
        return {"messages": messages, "text": render_messages(messages)}
    deadline = clock() + max(0, min(int(wait or 0), max_wait()))
    while not store.unread(actor, mark=False, limit=1) and clock() < deadline:
        sleep(min(poll, max(0.0, deadline - clock())))
    messages = store.unread(actor)
    if messages:
        return {"messages": messages, "text": render_messages(messages)}
    tasks = [dict(id=t["id"], title=t["title"], status=t["status"], org_id=org["id"], org_name=org["name"],
                  owner=member) for org, member, _ in store.seats_of(actor) for t in org["tasks"].values()
             if t["owner"] == member and t["status"] not in ("done", "dropped")]
    text = "No unread messages. An empty inbox is not an empty task list: check status."
    if tasks:
        text += "\nYour open assigned tasks:\n" + "\n".join(
            "- %s: %s [%s] — %s (%s)" % (t["id"], t["title"], t["status"], t["org_name"], t["org_id"]) for t in tasks)
    return {"messages": [], "tasks": tasks, "text": text}


def seated(store, name, args, actor):
    """With org naming an organization the session holds a seat in, the call acts as that seat's member
    ("<actor>#<org id>") and the session works for that organization now (its protocols bind its tool calls)."""
    if name in ("create", "join", "panel") or not args.get("org"):
        return actor
    scoped = store.scoped(actor, args["org"])
    if scoped:
        args.pop("org")
        store.set_focus(actor, store.split_actor(scoped)[1])
        return scoped
    if name in SEATED_ONLY:
        raise OrgError("You hold no seat in %s; org names an organization you are a member of." % args["org"])
    return actor


def handle_call(store, name, args, actor):
    actor = seated(store, name, args, actor)
    if name == "create":
        if store.approval_needed(actor, "create"):
            return store.file_request(actor, "create", {k: args.get(k, "") for k in
                                                        ("name", "purpose", "member", "role", "governance")},
                                      args.get("purpose", ""))
        org = store.create(actor, args["name"], args.get("purpose", ""), args["member"], args.get("role", ""),
                           args.get("governance", "leader"))
        return {"org_id": org["id"], "member": args["member"], "context": render(store, org, args["member"])}
    if name == "join":
        info = store.join(actor, args["org_id"], args["member"], args.get("role", ""))
        org = store.get(args["org_id"])
        return dict(info, context=render(store, org, args["member"]))
    if name == "status":
        if args.get("org"):
            own, member, target, way = store.reach(actor, args["org"])
            if way:
                return {"org_id": target["id"], "context": render_below(store, target, own, member)}
        org, member = store.require(actor)
        unread = len(store.unread(actor, mark=False))
        text = render(store, org, member, unread)
        others = render_seats(store, actor, org["id"])
        return {"org_id": org["id"], "member": member, "context": text + ("\n" + others if others else "")}
    if name == "group":
        return group(store, actor, args.pop("op", None), args)
    if name == "message":
        return store.send(actor, args.get("to"), args.get("body", ""), args.get("episode_id"),
                          reply_to=args.get("reply_to"), org=args.get("org"))
    if name == "inbox":
        return inbox(store, actor, args.get("wait") or 0, message_id=args.get("message_id"))
    if name == "work":
        return store.work(actor, args.pop("op"), args)
    if name == "episode":
        return store.episode(actor, args.pop("op"), args)
    if name == "protocol":
        return store.protocol(actor, args.pop("op"), args)
    if name == "review":
        return store.review(actor, args.pop("op"), args)
    if name == "panel":
        from .runner import open_window
        return {"text": "The Relic App is opening on the person's screen.", "script": open_window()}
    if name == "trajectory":
        op = args.get("op")
        if op == "request":
            return store.request_trajectory(actor, args["member"], args.get("carrier", 0), args.get("reason", ""),
                                            args.get("memory", True) is not False)
        if op == "answer":
            return store.answer_trajectory(actor, args["request_id"], args.get("decision"), args.get("note", ""),
                                           args.get("redact", True) is not False)
        if op == "list":
            return store.trajectory_requests(actor)
        raise OrgError("trajectory ops: request, answer, list.")
    raise OrgError("Unknown tool " + name)


def group(store, actor, op, a):
    if op == "create":
        g = store.create_group(actor, a.get("name", ""), a.get("purpose", ""), a.get("leader"), a.get("parent"),
                               a.get("members"))
        return {"org_id": g["id"], "name": g["name"], "parent": g["parent"], "leader": g["leader"],
                "members": list(g["members"]),
                "text": "Subgroup '%s' (%s) is open under %s; each member holds a seat in it. Work there with org=%s; "
                        "its leader closes it with group op=close when the work is done."
                        % (g["name"], g["id"], g["parent"], g["id"])}
    if op == "close":
        return store.close_group(actor, a.get("org"))
    if op in ("reparent", "leader", "dissolve"):
        return store.change_formal(actor, "parent" if op == "reparent" else op, a)
    if op in ("approve", "deny"):
        return store.decide_request(actor, a.get("request_id"), op, a.get("note", ""))
    if op == "list":
        base = store.split_actor(actor)[0]
        org, member = store.require(actor)
        mine = [r for r in store.requests() if (r.get("requester") or {}).get("actor") == base]
        waiting = [r for r in store.requests((store.cabinet() or {}).get("id")) if r["status"] == "pending"] \
            if store.is_secretary_general(actor) else []
        groups = [{"id": o["id"], "name": o["name"], "status": o.get("status"), "leader": o.get("leader")}
                  for o in store.list_orgs() if o.get("kind") == "subgroup" and o.get("parent") == org["id"]]
        return {"to_decide": waiting, "mine": mine[:10], "subgroups": groups}
    raise OrgError("group ops: create, close, reparent, leader, dissolve, approve, deny, list.")
