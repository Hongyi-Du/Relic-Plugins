"""Relic MCP server (stdio JSON-RPC, standard library only).

The caller's identity ("actor") is filled in by the plugin's PreToolUse hook, which
knows the Claude Code session and subagent making the call. Agents never need to
pass it themselves.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from relic_core import __version__  # noqa: E402
from relic_core.context import render, render_messages  # noqa: E402
from relic_core.store import OrgError, Store  # noqa: E402

S = {"type": "string"}
SL = {"type": "array", "items": {"type": "string"}}
ACTOR = {"type": "string", "description": "Filled in automatically by the Relic hook. Leave it out."}


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
    tool("message", "Send a message to members (list of names, or ['all']). Messages persist and are delivered to "
         "recipients at their next tool call.", {"to": SL, "body": S, "episode_id": S}, ["to", "body"]),
    tool("inbox", "Read your unread messages (marks them read).", {}),
    tool("work", "Shared work. op=doc_write {key, body, expected_revision} | doc_read {key?} | "
         "task {task_id?, title?, owner?, status?: open|working|blocked|done|dropped, evidence?} | "
         "role {member?, role} | note {body} (private to you; not inherited by a replacement).",
         {"op": {"enum": ["doc_write", "doc_read", "task", "role", "note"]}, "key": S, "body": S,
          "expected_revision": {"type": "integer"}, "task_id": S, "title": S, "owner": S, "status": S,
          "evidence": SL, "member": S, "role": S}, ["op"]),
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
    tool("review", "Peer review required by strong protocols. op=list shows pending requests; op=approve "
         "{request_id, note} approves another member's exact action after you checked it.",
         {"op": {"enum": ["list", "approve"]}, "request_id": S, "note": S}, ["op"]),
]


def actor_of(args):
    return args.pop("actor", None) or os.getenv("RELIC_ACTOR") or "local"


def call(store, name, args):
    actor = actor_of(args)
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
        return store.send(actor, args.get("to"), args.get("body", ""), args.get("episode_id"))
    if name == "inbox":
        store.require(actor)
        messages = store.unread(actor)
        return {"messages": messages, "text": render_messages(messages) if messages else "No unread messages."}
    if name == "work":
        return store.work(actor, args.pop("op"), args)
    if name == "episode":
        return store.episode(actor, args.pop("op"), args)
    if name == "protocol":
        return store.protocol(actor, args.pop("op"), args)
    if name == "review":
        return store.review(actor, args.pop("op"), args)
    raise OrgError("Unknown tool " + name)


def main():
    store = Store()
    known = {t["name"] for t in TOOLS}
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        if "id" not in req:
            continue  # notifications
        method, params = req.get("method"), req.get("params") or {}
        if method == "initialize":
            result = {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                      "capabilities": {"tools": {}},
                      "serverInfo": {"name": "relic", "version": __version__},
                      "instructions": "Relic organizations: persistent members, shared work, reflection and "
                                      "organization-owned protocols. Use the relic skill for the workflow."}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "ping":
            result = {}
        elif method == "tools/call":
            name = params.get("name")
            args = dict(params.get("arguments") or {})
            try:
                if name not in known:
                    raise OrgError("Unknown tool " + str(name))
                data = call(store, name, args)
                text = data.get("context") or data.get("text") if isinstance(data, dict) else None
                body = json.dumps(data, ensure_ascii=False, indent=1)
                result = {"content": [{"type": "text", "text": text + "\n\n" + body if text else body}]}
            except (OrgError, KeyError, TypeError) as error:
                result = {"isError": True, "content": [{"type": "text", "text": "Relic: " + str(error)}]}
        else:
            print(json.dumps({"jsonrpc": "2.0", "id": req["id"],
                              "error": {"code": -32601, "message": "Method not found"}}), flush=True)
            continue
        print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": result}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
