"""Relic hook for Antigravity (Google's agent app; the person calls it 哈基米).

Antigravity runs plugin hooks with JSON of its own (camelCase fields; context goes back as injectSteps; a Stop goes on
with "decision": "continue") and offers MCP tools through one tool, call_mcp_tool {ServerName, ToolName, Arguments}.
This adapter turns each event into the one relic_hook.py handles for Claude Code and Codex, and the answer back:

  SessionStart                SessionStart: the organization's context
  PreInvocation, first call   UserPromptSubmit: the turn's context and new messages. The prompt is the step that
                              started the turn (the transcript's step before the first model call): what the person
                              typed (USER_INPUT), or a message from outside (a Relic wake-up, SYSTEM_MESSAGE)
  PreInvocation, later calls  new peer messages only, between the model calls of one turn
  PreToolUse call_mcp_tool    a Relic tool: allowed, the conversation's actor stamped into its Arguments (as on
                              Claude Code); another server's tool: "ask", Antigravity's own default for MCP tools
  PostToolUse                 the activity record (Antigravity takes no context here; messages wait for the next
                              PreInvocation, so none is taken from the inbox here)
  Stop                        Stop: due reflection, direct messages, the rules on Reply; "block" becomes "continue"

The conversation's Relic actor is "antigravity:<conversationId>". Antigravity takes a PreToolUse answer without a
decision as a denial, so the plugin registers PreToolUse for call_mcp_tool only (relic_core/antigravity.plugin_files).
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import relic_hook  # noqa: E402
from relic_core import antigravity, wake  # noqa: E402
from relic_core.store import OrgError, Store  # noqa: E402

# Antigravity's tools in the one vocabulary Relic's rules and activity use (Bash, Edit, Write, Read).
TOOLS = {"run_command": ("Bash", "CommandLine", "command"), "write_to_file": ("Write", "TargetFile", "file_path"),
         "replace_file_content": ("Edit", "TargetFile", "file_path"),
         "multi_replace_file_content": ("Edit", "TargetFile", "file_path"),
         "view_file": ("Read", "AbsolutePath", "file_path"), "read_file": ("Read", "Path", "file_path")}


def relic_tool(call):
    """(Relic tool name, input) for an Antigravity tool call: a Relic MCP tool as mcp__relic_org__<tool>, another
    server's as mcp__<server>__<tool>, the shell and file tools in Relic's vocabulary."""
    name, args = str(call.get("name") or ""), call.get("args") if isinstance(call.get("args"), dict) else {}
    if name == "call_mcp_tool":
        server, tool = str(args.get("ServerName") or ""), str(args.get("ToolName") or "")
        arguments = args.get("Arguments") if isinstance(args.get("Arguments"), dict) else {}
        prefix = "mcp__relic_org__" if antigravity.is_server(server) else "mcp__%s__" % server
        return prefix + tool, dict(arguments)
    if name in TOOLS:
        relic, field, key = TOOLS[name]
        return relic, {key: args.get(field, ""), **{k: v for k, v in args.items() if k != field}}
    return name, dict(args)


def turn_prompt(event):
    """What started the turn: the latest step before its first model call that is the person's input (USER_INPUT:
    returned as typed) or a message from outside (a SYSTEM_MESSAGE "[Message] ... content=<text>", such as a Relic
    wake-up: returned marked as not typed). Other system messages (the context hooks inject, the app's reminders)
    started nothing. None when the transcript does not show it."""
    steps = antigravity.transcript(event.get("transcriptPath"))
    first = event.get("initialNumSteps")
    before = [s for s in steps if not isinstance(first, int) or (isinstance(s.get("step_index"), int)
                                                                  and s["step_index"] < first)]
    for step in reversed(before):
        content = step.get("content") if isinstance(step.get("content"), str) else ""
        if step.get("type") == "USER_INPUT":
            start, end = content.find("<USER_REQUEST>"), content.find("</USER_REQUEST>")
            return content[start + len("<USER_REQUEST>"):end].strip() if start >= 0 and end > start else content
        if step.get("type") == "SYSTEM_MESSAGE" and "[Message]" in content:
            text = content[content.find("content=") + len("content="):] if "content=" in content else content
            text = text.rsplit("</SYSTEM_MESSAGE>", 1)[0].strip()
            return "<event source=\"antigravity\">" + text
    return None


def relic_event(event):
    """The Relic hook event for an Antigravity one, or None when Relic has nothing to do with it."""
    name = event.get("hookEventName")
    cwd = event.get("cwd") or next(iter(event.get("workspacePaths") or []), "") or None
    base = {"session_id": event.get("conversationId") or os.getenv("ANTIGRAVITY_CONVERSATION_ID") or "",
            "cwd": cwd, "transcript_path": event.get("transcriptPath")}
    if name == "SessionStart":
        return dict(base, hook_event_name="SessionStart")
    if name == "PreInvocation":
        if event.get("invocationNum"):
            return dict(base, hook_event_name="PreInvocation")  # later calls of the turn: new messages only
        prompt = turn_prompt(event)
        if prompt is None:  # no transcript to tell who started the turn: never taken for the person's words
            prompt = "<event source=\"antigravity\">" + str(event.get("lastUserInput") or "")
        return dict(base, hook_event_name="UserPromptSubmit", prompt=prompt)
    if name in ("PreToolUse", "PostToolUse"):
        call = event.get("toolCall") if isinstance(event.get("toolCall"), dict) else {}
        tool, tool_input = relic_tool(call)
        relic = dict(base, hook_event_name=name, tool_name=tool, tool_input=tool_input, tool_call=call)
        if name == "PostToolUse":
            relic["error"] = event.get("error") or ""
        return relic
    if name == "Stop":
        return dict(base, hook_event_name="Stop", stop_hook_active=bool(event.get("continuationActive")),
                    last_assistant_message=antigravity.last_reply(event.get("transcriptPath")))
    return None


def inject(text):
    return {"injectSteps": [{"systemMessage": {"systemMessage": text}}]} if text else {}


def context_of(output):
    output = output or {}
    return (output.get("hookSpecificOutput") or {}).get("additionalContext") or ""


def answer(event, relic, store):
    """Antigravity's answer to one hook event."""
    name = relic["hook_event_name"]
    actor = relic_hook.actor_key(relic)
    if name == "PreInvocation":
        org, member = store.whoami(store.focused(actor))
        text = relic_hook.peer_messages(store, actor) if org else ""
        try:
            wake.dispatch_for_actor(store, actor)
        except Exception:  # waking others must never break this member's turn
            pass
        return inject(text)
    if name == "PostToolUse":
        org, _ = store.whoami(actor)
        if org:
            store.record_activity(actor, relic["tool_name"], relic["tool_input"], failed=bool(relic.get("error")),
                                  output=str(relic.get("error") or "")[-20000:], cwd=relic.get("cwd"))
        try:
            wake.dispatch_for_actor(store, actor)
        except Exception:
            pass
        return {}
    if name == "PreToolUse":
        call = relic["tool_call"]
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        if call.get("name") != "call_mcp_tool" or not antigravity.is_server(args.get("ServerName")):
            return {"decision": "ask"}  # not Relic's: the app's own rule for MCP tools (it asks the person)
        output = relic_hook.handle(relic, store).get("hookSpecificOutput") or {}
        if output.get("permissionDecision") == "deny":
            return {"decision": "deny", "reason": output.get("permissionDecisionReason") or "Relic"}
        stamped = output.get("updatedInput") if isinstance(output.get("updatedInput"), dict) else relic["tool_input"]
        return {"decision": "allow", "reason": "Relic organization tool",
                "overwrite": {"Arguments": dict(stamped, actor=stamped.get("actor") or actor)}}
    output = relic_hook.handle(relic, store)
    if name == "Stop":
        if (output or {}).get("decision") == "block":
            return {"decision": "continue", "reason": output.get("reason") or ""}
        return {}
    return inject(context_of(output))


def main():
    os.environ["RELIC_HARNESS"] = "antigravity"  # the plugin's PLUGIN_ROOT would otherwise read as Codex
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except ValueError:
        event = {}
    tool_hook = isinstance(event, dict) and event.get("hookEventName") == "PreToolUse"
    try:
        relic = relic_event(event) if isinstance(event, dict) else None
        output = answer(event, relic, Store()) if relic and relic.get("session_id") else (
            {"decision": "ask"} if tool_hook else {})
    except OrgError as error:
        output = {"decision": "ask"} if tool_hook else inject("Relic: " + str(error))
    except Exception as error:  # never break the conversation because of the organization layer
        output = {"decision": "ask"} if tool_hook else inject("Relic hook error (%s): %s" % (type(error).__name__,
                                                                                          error))
    sys.stdout.write(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
