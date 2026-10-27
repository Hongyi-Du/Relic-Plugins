"""The Relic tools: their schemas and what each call does. server.py serves them over MCP stdio and reloads this module
(and the rest of relic_core) when the plugin is updated, so a session that stays open keeps up with the plugin.

The caller's identity ("actor") is filled in by the plugin's PreToolUse hook, which knows the Claude Code session and
subagent making the call. Agents never need to pass it themselves.
"""
import os
import time

from . import wake
from .context import render, render_messages
from .store import OrgError

S = {"type": "string"}
SL = {"type": "array", "items": {"type": "string"}}
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
    "effect: deny | require_review | require_before. tools: tool-name globs such as Bash, Edit, Write. "
    "Optional: input_contains [substrings of the tool input], path_glob (file path pattern), members/roles it applies to, "
    "except_members/except_roles (e.g. the owner), before {tools, input_contains} for require_before, reason.")}

TOOLS = [
    tool("create", "Create a new Relic organization and join it as its first member. Use when the human asks for an "
         "organization or team. governance 'leader' makes you leader; 'peer' means decisions by majority.",
         {"name": S, "purpose": S, "member": S, "role": S, "governance": {"enum": ["leader", "peer"]}},
         ["name", "purpose", "member"]),
    tool("join", "Join an organization as a member (a seat). Joining an existing seat makes you its new carrier: you "
         "inherit its role, tasks and the organization's protocols, but not the previous carrier's private notes.",
         {"org_id": S, "member": S, "role": S}, ["org_id", "member"]),
    tool("status", "Your view of the organization: members and roles, active protocols, proposals to vote on, review "
         "requests, tasks, documents, reflection due, unread messages.", {}),
    tool("message", "Send a message to members (list of names, or ['all']); write to ['human'] to reach the person, who "
         "reads and answers it in the Relic App. Messages persist and are delivered to "
         "recipients at their next tool call. With auto-wake on (the default), a recipient whose seat has a configured "
         "session gets a turn automatically to handle it (a Codex chat open in the Codex desktop app gets it there). "
         "A ChatGPT chat member gets your message's full text in its chat; the ChatGPT app keeps the reply's text "
         "from plugins, so the person forwards it in the Relic App and it comes back to you as its message. "
         "When you need the answer in this turn, call inbox with wait afterwards.",
         {"to": dict(SL, description="Member names, ['all'] or ['human']. Leave it out only with reply_to."), "body": S,
          "episode_id": S,
          "reply_to": {"type": "integer", "description": "Reply inside the thread of message #id, like a Slack thread; "
                                                         "without `to`, the thread's participants receive it."}},
         ["body"]),
    tool("inbox", "Read your unread messages (marks them read). wait (seconds; the longest this client allows is "
         "applied): when nothing is unread yet, wait that long for the first message to arrive; use it after messaging "
         "a member whose answer you need in this turn, and call it again if the answer has not come yet.",
         {"wait": {"type": "integer"}}),
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
          "member": S, "role": S}, ["op"]),
    tool("episode", "Episodes bound a piece of work so the organization can learn from it. op=open {title, participants?} | "
         "close {episode_id, outcome: success|failure|partial|cancelled, summary, evidence?} | reflect {episode_id, body}. "
         "Reflect on friction you saw: what went wrong between members, what would prevent it next time.",
         {"op": {"enum": ["open", "close", "reflect"]}, "title": S, "participants": SL, "episode_id": S,
          "outcome": S, "summary": S, "evidence": SL, "body": S}, ["op"]),
    tool("protocol", "Organization protocols. op=propose: weak {title, rationale, guidance, trigger, scope?, evidence} is "
         "shared guidance; strong {title, rationale, episode_id (closed, reflected), rules: [rule]} is enforced on tool "
         "calls by the hook. Revise with supersedes, retire with retire_target. A proposal becomes active when the "
         "organization's approval threshold is reached. op=vote {protocol_id, vote: approve|reject, reason}. "
         "op=use {protocol_id, outcome: followed|deviated|inapplicable, note} reports actual use. op=list.",
         {"op": {"enum": ["propose", "vote", "use", "list"]}, "title": S, "rationale": S,
          "strength": {"enum": ["weak", "strong"]}, "guidance": S, "trigger": S, "scope": S, "evidence": SL,
          "episode_id": S, "rules": {"type": "array", "items": RULE}, "supersedes": S, "retire_target": S,
          "protocol_id": S, "vote": {"enum": ["approve", "reject"]}, "reason": S, "outcome": S, "note": S}, ["op"]),
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
          "redact": {"type": "boolean"}}, ["op"]),
    tool("panel", "Open the Relic App on the person's screen: the group chat and private chats with every member, where "
         "they found organizations, add members (run in the App, or in Claude Code or Codex with model, effort, folder "
         "or worktree, permission and environment variables), seat existing sessions and chats, start or replace "
         "members' sessions, answer decisions and trajectory requests and message members. Call it when the person "
         "asks for the Relic App, window, panel or UI.", {}),
    tool("review", "Peer review required by strong protocols. op=list shows pending requests; op=approve "
         "{request_id, note} approves another member's exact action after you checked it.",
         {"op": {"enum": ["list", "approve"]}, "request_id": S, "note": S}, ["op"]),
]
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
    if name in ("message", "trajectory"):
        try:
            wake.dispatch_for_actor(store, actor)  # recipients with an idle configured session get a turn now
        except Exception:
            pass
    return result


def inbox(store, actor, wait=0, poll=2.0, sleep=time.sleep, clock=time.time):
    """Unread messages, marked read; with wait, first wait up to that many seconds for one to arrive."""
    store.require(actor)
    deadline = clock() + max(0, min(int(wait or 0), max_wait()))
    while not store.unread(actor, mark=False, limit=1) and clock() < deadline:
        sleep(min(poll, max(0.0, deadline - clock())))
    messages = store.unread(actor)
    return {"messages": messages, "text": render_messages(messages) if messages else "No unread messages."}


def handle_call(store, name, args, actor):
    if name == "create":
        org = store.create(actor, args["name"], args.get("purpose", ""), args["member"], args.get("role", ""),
                           args.get("governance", "leader"))
        return {"org_id": org["id"], "member": args["member"], "context": render(store, org, args["member"])}
    if name == "join":
        info = store.join(actor, args["org_id"], args["member"], args.get("role", ""))
        org = store.get(args["org_id"])
        return dict(info, context=render(store, org, args["member"]))
    if name == "status":
        org, member = store.require(actor)
        unread = len(store.unread(actor, mark=False))
        return {"org_id": org["id"], "member": member, "context": render(store, org, member, unread)}
    if name == "message":
        return store.send(actor, args.get("to"), args.get("body", ""), args.get("episode_id"),
                          reply_to=args.get("reply_to"))
    if name == "inbox":
        return inbox(store, actor, args.get("wait") or 0)
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
