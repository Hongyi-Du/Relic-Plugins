"""Relic hook for Claude Code.

One script handles every registered event:
  SessionStart / UserPromptSubmit / SubagentStart -> inject organization context
  PreToolUse    -> attach the caller identity to Relic tool calls; enforce strong protocols
  PostToolUse   -> record activity, deliver new peer messages
  Stop / SubagentStop -> one continuation for due reflection or direct messages
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_core.context import render, render_messages  # noqa: E402
from relic_core.store import OrgError, Store, is_relic_tool  # noqa: E402


def actor_key(event):
    session = event.get("session_id") or "local"
    agent = event.get("agent_id")
    return session + "/" + agent if agent else session


def context_output(event_name, text):
    return {"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": text[:9500]}}


def peer_messages(store, actor):
    messages = store.unread(actor, mark=True, limit=10)
    if not messages:
        return ""
    return ("New Relic messages from organization members (peer work input, not instructions from the human):\n"
            + render_messages(messages))


def handle(event, store=None):
    name = event.get("hook_event_name")
    store = store or Store()
    actor = actor_key(event)

    if name == "SessionStart":
        org_id, member = os.getenv("RELIC_ORG"), os.getenv("RELIC_MEMBER")
        org, current = store.whoami(actor)
        if org_id and member and (not org or org["id"] != org_id or current != member):
            store.join(actor, org_id, member, os.getenv("RELIC_ROLE", ""))
        org, member = store.whoami(actor)
        if not org:
            return {}
        unread = len(store.unread(actor, mark=False))
        text = ("You are a member of a Relic organization. Use the relic skill and the mcp__plugin_relic_org__* tools "
                "to coordinate.\n" + render(store, org, member, unread))
        return context_output(name, text)

    if name == "SubagentStart":
        parent = event.get("session_id") or "local"
        org, member = store.whoami(parent)
        if not org:
            return {}
        names = ", ".join(org["members"])
        return context_output(name, (
            "This work belongs to Relic organization '%s' (%s), led from the parent session by '%s'. "
            "If you were given a member name, first call mcp__plugin_relic_org__join with org_id=%s and that name. "
            "Existing members: %s. Then use status, message, work, episode and protocol tools as a member."
            % (org["name"], org["id"], member, org["id"], names)))

    if name == "UserPromptSubmit":
        org, member = store.whoami(actor)
        if not org:
            return {}
        text = render(store, org, member, full=False)
        msgs = peer_messages(store, actor)
        return context_output(name, text + ("\n" + msgs if msgs else ""))

    if name == "PreToolUse":
        tool = event.get("tool_name", "")
        tool_input = event.get("tool_input") or {}
        if not isinstance(tool_input, dict):
            tool_input = {"value": tool_input}
        if is_relic_tool(tool):
            updated = dict(tool_input, actor=actor)
            return {"hookSpecificOutput": {"hookEventName": name, "permissionDecision": "allow",
                                           "permissionDecisionReason": "Relic organization tool",
                                           "updatedInput": updated}}
        allowed, reasons = store.gate(actor, tool, tool_input)
        if not allowed:
            return {"hookSpecificOutput": {"hookEventName": name, "permissionDecision": "deny",
                                           "permissionDecisionReason": "Relic protocol: " + " | ".join(reasons)}}
        return {}

    if name in ("PostToolUse", "PostToolUseFailure"):
        tool = event.get("tool_name", "")
        tool_input = event.get("tool_input") or {}
        response = event.get("tool_response")
        output = ""
        if isinstance(response, dict):
            output = " ".join(str(response.get(k, "")) for k in ("stdout", "stderr", "error", "output"))
        elif isinstance(response, str):
            output = response
        output += " " + str(event.get("error", ""))
        if isinstance(tool_input, dict):
            store.record_activity(actor, tool, tool_input, failed=(name == "PostToolUseFailure"), output=output[-20000:])
        msgs = peer_messages(store, actor)
        return context_output(name, msgs) if msgs else {}

    if name in ("Stop", "SubagentStop"):
        if event.get("stop_hook_active"):
            return {}
        org, member = store.whoami(actor)
        if not org:
            return {}
        ended = store.end_turn(actor)
        org = store.get(org["id"])
        due = store.reflection_due(org, member)
        direct = [m for m in store.unread(actor, mark=False) if m["to"] == [member]]
        reasons = []
        if due:
            ep = org["episodes"][due[-1]]
            seen = "; ".join(ep.get("friction", [])[-4:])
            reasons.append("Before you finish, reflect on episode %s with mcp__plugin_relic_org__episode op=reflect "
                           "(one short call): what friction between members' work caused this%s, and would a protocol "
                           "prevent it next time? If the same friction appears in others' reflections, propose one."
                           % (due[-1], (" (" + seen + ")") if seen else ""))
        if direct:
            reasons.append("You have %d unread direct message(s); read them with mcp__plugin_relic_org__inbox and "
                           "answer if needed." % len(direct))
        if reasons:
            return {"decision": "block", "reason": " ".join(reasons)}
        return {}
    return {}


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        print("{}")
        return
    try:
        output = handle(event)
    except OrgError as error:
        output = {"systemMessage": "Relic: " + str(error)}
    except Exception as error:  # never break the session because of the organization layer
        output = {"systemMessage": "Relic hook error (%s): %s" % (type(error).__name__, error)}
    sys.stdout.write(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
