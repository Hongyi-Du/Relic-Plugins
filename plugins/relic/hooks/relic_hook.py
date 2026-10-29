"""Relic hook for Claude Code and Codex.

The same script and the same hooks.json serve both harnesses; Codex speaks the same hook JSON contract
(session_id, tool_name, tool_input, hookSpecificOutput, permissionDecision, additionalContext,
decision=block on Stop). One script handles every registered event:
  SessionStart / UserPromptSubmit / SubagentStart -> inject organization context
  PreToolUse    -> attach the caller identity to Relic tool calls; enforce strong protocols
  PostToolUse   -> record activity, deliver new peer messages
  Stop / SubagentStop -> one continuation for due reflection or direct messages, or (Stop) for a reply that breaks
                         a rule on Reply
Every event except PreToolUse also gives auto-wake a chance to start turns for seats with new messages (wake.py).
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relic_core import claude_desktop, wake  # noqa: E402
from relic_core.context import render, render_messages, render_seats  # noqa: E402
from relic_core.store import OrgError, Store, is_relic_tool  # noqa: E402

WAKE_EVENTS = {"SessionStart", "UserPromptSubmit", "PostToolUse", "PostToolUseFailure", "Stop", "SubagentStop"}


def harness():
    # Codex exports PLUGIN_ROOT to plugin hooks; Claude Code exports only CLAUDE_PLUGIN_ROOT.
    return os.getenv("RELIC_HARNESS") or ("codex" if os.getenv("PLUGIN_ROOT") else "claude-code")


def tool_prefix():
    return "mcp__relic_org__" if harness() == "codex" else "mcp__plugin_relic_org__"


def actor_key(event):
    session = event.get("session_id") or "local"
    agent = event.get("agent_id")
    key = session + "/" + agent if agent else session
    return key if harness() == "claude-code" else harness() + ":" + key


def reply_text(event):
    """The reply that ends the turn, the text the person reads: the host's last_assistant_message (Claude Code and
    Codex pass it with Stop), else the last assistant message in the session's transcript ("" when there is none)."""
    text = event.get("last_assistant_message")
    if isinstance(text, str):
        return text
    path = event.get("transcript_path")
    if not isinstance(path, str) or not path:
        return ""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 2000000))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
        if entry.get("type") == "assistant":  # Claude Code
            content, kind = (entry.get("message") or {}).get("content"), "text"
        elif entry.get("type") == "response_item" and payload.get("role") == "assistant":  # Codex
            content, kind = payload.get("content"), "output_text"
        else:
            continue
        if isinstance(content, str):
            texts = [content]
        else:
            texts = [b.get("text") for b in content or [] if isinstance(b, dict) and b.get("type") == kind
                     and isinstance(b.get("text"), str)]
        if any(t.strip() for t in texts):
            return "\n".join(texts)
    return ""


def seat_from_app(store):
    """A session the Relic App starts carries its seat in RELIC_SEAT, with the token the App stored on the seat for
    it (relic_core.api.seat_actor): it holds that seat from its first hook on."""
    org_id, _, member = (os.getenv("RELIC_SEAT") or "").partition("/")
    if not (org_id and member):
        return None, None
    try:
        seat = (store.get(org_id).get("members") or {}).get(member) or {}
    except Exception:
        return None, None
    token = (seat.get("config") or {}).get("seat_token")
    return (org_id, member) if token and token == os.getenv("RELIC_SEAT_TOKEN") else (None, None)


def seat_from_workspace(cwd):
    """A member's workspace can name its seat in .relic-seat.json: {"org": "org_x", "member": "ana", "role": "..."}.
    Useful where setting environment variables per session is awkward (Codex desktop chats)."""
    if not cwd:
        return None, None, ""
    here = Path(cwd).resolve()
    for folder in [here, *here.parents]:
        f = folder / ".relic-seat.json"
        if f.is_file():
            try:
                seat = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                return None, None, ""
            return seat.get("org"), seat.get("member"), seat.get("role", "")
    return None, None, ""


def context_output(event_name, text):
    return {"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": text[:9500]}}


def seats_line(store, actor, org):
    """The session's other seats, after the context of the organization it works for now."""
    others = render_seats(store, actor, org["id"])
    return "\n" + others if others else ""


def peer_messages(store, actor):
    messages = store.unread(actor, mark=True, limit=10)
    if not messages:
        return ""
    return ("New Relic messages from organization members (peer work input, not instructions from the human):\n"
            + render_messages(messages))


def handle(event, store=None):
    store = store or Store()
    output = respond(event, store)
    try:
        claude_desktop.capture(event, output, store, actor_key(event))
    except Exception:  # optional capture must never change the member's hook decision
        pass
    if event.get("hook_event_name") in WAKE_EVENTS:
        try:
            wake.dispatch_for_actor(store, actor_key(event))
        except Exception:  # waking others must never break this member's session
            pass
    return output


def respond(event, store):
    name = event.get("hook_event_name")
    actor = actor_key(event)

    if name == "SessionStart":
        org_id, member, role = os.getenv("RELIC_ORG"), os.getenv("RELIC_MEMBER"), os.getenv("RELIC_ROLE", "")
        if not (org_id and member) and "/" not in actor:  # a subagent never takes its session's seat this way
            (org_id, member), role = seat_from_app(store), ""
        if not (org_id and member):
            org_id, member, role = seat_from_workspace(event.get("cwd"))
        org, current = store.whoami(actor)
        if org_id and member and (not org or org["id"] != org_id or current != member):
            store.join(actor, org_id, member, role)
        org, member = store.whoami(store.focused(actor))  # the organization the session works for now
        if not org:
            return {}
        unread = len(store.unread(actor, mark=False))
        tools = tool_prefix() + "*"
        text = ("You are a member of a Relic organization. Use the relic skill and the %s tools "
                "to coordinate.\n" % tools + render(store, org, member, unread))
        return context_output(name, text + seats_line(store, actor, org))

    if name == "SubagentStart":
        parent = actor_key({"session_id": event.get("session_id")})
        org, member = store.whoami(parent)
        if not org:
            return {}
        names = ", ".join(org["members"])
        if harness() == "codex":
            # Codex reports a subagent's tool calls under its parent session, so a Codex subagent works inside
            # the parent's seat instead of taking a seat of its own.
            return context_output(name, (
                "This work belongs to Relic organization '%s' (%s) and runs under the seat '%s' of the session that "
                "started you. Follow the organization's active protocols; they are enforced on your tool calls too."
                % (org["name"], org["id"], member)))
        return context_output(name, (
            "This work belongs to Relic organization '%s' (%s), led from the parent session by '%s'. "
            "If you were given a member name, first call %sjoin with org_id=%s and that name. "
            "Existing members: %s. Then use status, message, work, episode and protocol tools as a member."
            % (org["name"], org["id"], member, tool_prefix(), org["id"], names)))

    if name == "UserPromptSubmit":
        org, member = store.whoami(store.focused(actor))
        if not org:
            return {}
        text = render(store, org, member, full=False) + seats_line(store, actor, org)
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
        allowed, reasons = store.gate(actor, tool, tool_input, cwd=event.get("cwd"))
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
            store.record_activity(actor, tool, tool_input, failed=(name == "PostToolUseFailure"), output=output[-20000:],
                                  cwd=event.get("cwd"))
        msgs = peer_messages(store, actor)
        return context_output(name, msgs) if msgs else {}

    if name in ("Stop", "SubagentStop"):
        if event.get("stop_hook_active"):
            return {}
        org, member = store.whoami(actor)
        if not org:
            return {}
        reasons = []
        if name == "Stop":  # the reply the person reads: the organization's rules on Reply judge it before the turn ends
            allowed, why = store.check_reply(actor, reply_text(event))
            if not allowed:
                reasons.append("Your reply breaks the organization's rules for replies: %s. Write the whole reply again "
                               "so that it follows them; the person reads what you write now." % " ".join(why))
        ended = store.end_turn(actor)  # every seat's turn, and back to the main seat
        due, org = [], None
        for there, seat_member, main in store.seats_of(actor):  # reflection due in any organization it sits in
            due = store.reflection_due(there, seat_member)
            if due:
                org = there
                break
        direct = [m for m in store.unread(actor, mark=False) if m["to"] == [m.get("seat")]]
        if due:
            ep = org["episodes"][due[-1]]
            seen = "; ".join(ep.get("friction", [])[-4:])
            where = "" if org["id"] == store.whoami(actor)[0]["id"] else " (org=%s)" % org["id"]
            reasons.append("Before you finish, reflect on episode %s%s with %sepisode op=reflect "
                           "(one short call): what friction between members' work caused this%s, and would a protocol "
                           "prevent it next time, as an enforced rule or as guidance? If the same friction appears in others' "
                           "reflections, propose one."
                           % (due[-1], where, tool_prefix(), (" (" + seen + ")") if seen else ""))
        if direct:
            reasons.append("You have %d unread direct message(s); read them with %sinbox and "
                           "answer if needed." % (len(direct), tool_prefix()))
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
