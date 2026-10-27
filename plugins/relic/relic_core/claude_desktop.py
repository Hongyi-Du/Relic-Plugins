"""Native Claude Desktop delivery and opt-in public Stop receipts.

Only a fresh message router uses the CLI. It never resumes the member's carrier.
The router's local hooks gate the exact target/payload and reserve one send before
it can happen; stream-json tool records, never helper prose, establish delivery.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time
import uuid
from pathlib import Path

from . import runner
from .gui_receipt import capture, marker, payload, receipt_matches


class TransportError(RuntimeError):
    def __init__(self, outcome, message, possible=False):
        super().__init__("Claude Desktop %s: %s" % (outcome, message))
        self.outcome, self.possible = outcome, possible


def request_path(org_id, member):
    return runner.run_path(org_id, member).with_suffix(".claude-gui.json")


def _read(path, strict=False):
    try:
        return json.loads(runner._retry_locked(lambda: path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        if strict:
            raise TransportError("unknown", "pending request cannot be read; not sent again", True) from None
        return {}


def _write(path, value):
    tmp = path.with_suffix(".%s.tmp" % uuid.uuid4().hex)
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    runner._retry_locked(lambda: tmp.replace(path))






def _text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(v.get("text", "") for v in value if isinstance(v, dict) and v.get("type") == "text")
    if isinstance(value, dict):
        return _text(value.get("listing", value.get("content", "")))
    return ""


def match_peer(result, expected):
    """Fail closed on unrecognised listings. A UUID or a fuzzy title is never an address."""
    if not isinstance(result, dict) or "agents" not in result:
        try:
            structured = json.loads(_text(result))
            if isinstance(structured, dict) and "agents" in structured:
                result = structured
        except ValueError:
            pass
    if isinstance(result, dict) and isinstance(result.get("agents"), list):
        rows = []
        for peer in result["agents"]:
            if peer.get("name") == expected:
                ref = peer.get("ref", "")
                rows.append((peer.get("surface"), ref, peer.get("status")))
    else:
        rows = []
        # Native human-readable listings: the display name plus the returned short
        # ref, followed by explicit Desktop and live status in that same row.
        pattern = re.compile(r'^\s*(?:[-*]\s+)?"?' + re.escape(expected) +
                             r'"?\s+\[([0-9a-f]{6,12})\](?=\s|[|:,(·—-]|$)(.*)$')
        for line in _text(result).splitlines():
            found = pattern.match(line)
            if found:
                rest = found[2].lower()
                surface = "desktop" if re.search(r"\b(?:claude-desktop|desktop)\b", rest) else ""
                status = next((s for s in ("offline", "idle", "busy", "active")
                               if re.search(r"\b" + s + r"\b", rest)), "")
                rows.append((surface, found[1], status))
    if len(rows) != 1:
        raise TransportError("unavailable", "expected one exact live peer named %r; found %d" % (expected, len(rows)))
    surface, ref, status = rows[0]
    if surface not in ("desktop", "claude-desktop") or status not in ("idle", "busy", "active") or not re.fullmatch(r"[0-9a-f]{6,12}", ref):
        raise TransportError("unavailable", "target must have an explicit Desktop surface, live status and short ref")
    return "%s [%s]" % (expected, ref)


def exact_send_input(data, target, request):
    if not isinstance(data, dict) or data.get("to") != target or data.get("message") != payload(request):
        return False
    if set(data) - {"to", "message", "summary", "type", "recipient", "recipient_kind", "content"}:
        return False
    if data.get("type", "message") != "message" or data.get("recipient", target) != target or data.get("recipient_kind", "name") != "name":
        return False
    # Current native CLI adds a shortened display-only content alias to its
    # stream record; the complete message remains the checked message field.
    alias = data.get("content")
    return alias is None or alias == payload(request) or (isinstance(alias, str) and alias.endswith("…") and payload(request).startswith(alias[:-1]))


def router_hook(event, folder):
    """Command-local hooks, installed only in the fresh auxiliary router."""
    request = _read(folder / "request.json")
    name, tool = event.get("hook_event_name"), event.get("tool_name")
    if name == "PostToolUse" and tool == "ListAgents":
        _write(folder / "listing-hook.json", {"response": event.get("tool_response")})
        try:
            target = match_peer(event.get("tool_response"), request["expected"])
        except (TransportError, KeyError):
            target = None
        _write(folder / "target.json", {"target": target})
        return {}
    if name == "PreToolUse":
        data = event.get("tool_input") or {}
        target = _read(folder / "target.json").get("target")
        valid = (tool == "ListAgents" or
                 (tool == "SendMessage" and target and exact_send_input(data, target, request)))
        if valid and tool == "SendMessage":
            try:
                # Reserve before permission/execution: even a lost tool result cannot
                # lead this router or a later dispatcher to send a second time.
                with (folder / "attempted").open("x", encoding="utf-8") as handle:
                    handle.write(str(time.time()))
            except FileExistsError:
                valid = False
        if not valid:
            return {"hookSpecificOutput": {"hookEventName": name, "permissionDecision": "deny",
                    "permissionDecisionReason": "Relic router requires one exact Desktop peer and unchanged payload; no retry."}}
    return {}


def tool_records(stdout):
    """Keep actual matched tool-use/result blocks only; discard init/account, thinking and prose."""
    calls, records = {}, []
    sequence = 0
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get("type") not in ("assistant", "user"):
            continue
        content = (event.get("message") or {}).get("content") or []
        if not isinstance(content, list):
            continue
        for block in content:
            sequence += 1
            if block.get("type") == "tool_use" and block.get("name") in ("ListAgents", "SendMessage"):
                record = {"call": {k: block[k] for k in ("type", "id", "name", "input") if k in block}, "call_at": sequence}
                records.append(record)
                calls[block.get("id")] = record
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in calls:
                calls[block["tool_use_id"]]["result"] = {
                    k: block[k] for k in ("type", "tool_use_id", "content", "is_error") if k in block}
                calls[block["tool_use_id"]]["result_at"] = sequence
    return records


def delivery(records, request):
    target, listed_at, sends = None, 0, []
    for record in records:
        call, result = record["call"], record.get("result")
        if call["name"] == "ListAgents" and result and not result.get("is_error"):
            try:
                target = match_peer(result.get("content"), request["expected"])
                listed_at = record["result_at"]
            except TransportError:
                target = None
        if call["name"] == "SendMessage":
            sends.append((record, target if listed_at < record["call_at"] else None))
    if not sends:
        return "unavailable"
    if len(sends) != 1:
        return "unknown"
    record, target = sends[0]
    data, result = record["call"].get("input") or {}, record.get("result")
    if (not target or not exact_send_input(data, target, request) or not result):
        return "unknown"
    text = _text(result.get("content")).strip().lower()
    try:
        native = json.loads(_text(result.get("content")))
    except ValueError:
        native = None
    if isinstance(native, dict) and native.get("success") is True and isinstance(native.get("msg_id"), str):
        # Native acceptance is only queued, never proof of reading or GUI completion.
        if "in that session's inbox" in str(native.get("message", "")):
            return "queued"
    if re.search(r"\b(?:held|holding|awaiting approval)\b", text):
        return "held"
    if re.search(r"\b(?:not sent|refused|denied|rejected)\b", text):
        return "refused"
    if not result.get("is_error") and re.match(r"(?:message (?:sent|delivered)|(?:sent|delivered)(?: successfully)?\b)", text):
        return "sent"
    return "unknown"


def route(request, config, folder, execute=None):
    exe = runner.find_claude()
    if not exe:
        raise TransportError("unavailable", "Claude CLI with native ListAgents/SendMessage is required")
    model = runner.checked_model(config)
    _write(folder / "request.json", request)
    command = [Path(sys.executable).as_posix(), "-B", "-X", "utf8", "-m", "relic_core.claude_desktop", "--router-hook", folder.as_posix()]
    # Claude command hooks use Bash by default on Windows too. cmd.exe quoting
    # strips unquoted backslashes in Bash, silently disabling the local gate.
    hook_command = shlex.join(command)
    settings = {"hooks": {
        "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": hook_command}]}],
        "PostToolUse": [{"matcher": "ListAgents", "hooks": [{"type": "command", "command": hook_command}]}]}}
    args = [exe, "-p", "--output-format", "stream-json", "--verbose", "--setting-sources", "project,local",
            "--permission-mode", "dontAsk", "--tools", "ListAgents,SendMessage", "--allowedTools", "ListAgents,SendMessage",
            "--disallowedTools", "mcp__*", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--settings", json.dumps(settings), "--no-session-persistence", "--name", "Relic message router"]
    if model:
        args += ["--model", model]
    if config.get("effort"):
        args += ["--effort", config["effort"]]
    env = runner.session_env(config)
    # Use the CLI's logged-in account, never injected API/gateway credentials.
    for key in list(env):
        if (key.startswith("ANTHROPIC_") or key.startswith("CLAUDE_CODE_USE_") or
                key in ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_API_KEY_HELPER_FD", "CLAUDECODE",
                        "CLAUDE_CODE_ENTRYPOINT", "RELIC_ORG", "RELIC_MEMBER", "RELIC_ROLE", "RELIC_HARNESS")):
            env.pop(key)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    instruction = ("You are a message-only router. Do not review code or perform the member's work. "
                   "First call ListAgents. Require exactly one live Desktop peer with the EXACT name in expected. "
                   "Use its returned name plus [short ref] as SendMessage.to; never a session UUID. "
                   "If absent, ambiguous or not Desktop, stop without sending. Call SendMessage at most once, "
                   "with message EXACTLY equal to payload below. Do not paraphrase it, retry, resume, or use a fallback. "
                   "After the tool result stop.\n" + json.dumps({"expected": request["expected"], "payload": payload(request)}, ensure_ascii=False))
    execute = execute or subprocess.run
    # This is a read-only CLI status command, not a model turn; never retain its
    # account details. Refuse saved Console/API credentials before launching -p.
    try:
        auth = execute([exe, "--setting-sources", "project,local", "auth", "status"], cwd=str(folder), env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=runner.NO_WINDOW, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        raise TransportError("unavailable", "could not confirm official CLI account login; router was not started") from None
    try:
        logged_in = json.loads(auth.stdout).get("authMethod") == "claude.ai" and auth.returncode == 0
    except ValueError:
        logged_in = False
    if not logged_in:
        _write(folder / "delivery.json", {"outcome": "unavailable", "records": []})
        raise TransportError("unavailable", "an existing official claude.ai CLI login is required; API credentials are not used")
    clean_exit = False
    try:
        proc = execute(args, input=instruction, cwd=str(folder), env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", creationflags=runner.NO_WINDOW, timeout=180)
        records = tool_records(proc.stdout)
        clean_exit = proc.returncode == 0
    except subprocess.TimeoutExpired as error:
        output = error.stdout or ""
        records = tool_records(output.decode("utf-8", errors="replace") if isinstance(output, bytes) else output)
    # stderr, system init and helper result text can contain account details; never persist them.
    outcome = delivery(records, request)
    if outcome == "unavailable":
        # A missing/lost stream is not proof that no send happened. Only a clean
        # list-and-refuse path can be retried automatically without a receipt.
        absent = False
        for record in records:
            if record["call"]["name"] == "ListAgents" and record.get("result") and not record["result"].get("is_error"):
                try:
                    match_peer(record["result"].get("content"), request["expected"])
                except TransportError:
                    absent = True
                else:
                    absent = False
        if not clean_exit or not absent or (folder / "attempted").exists():
            outcome = "unknown"
    # Only the SendMessage proof and exact selected address are needed in the permanent record.
    proof = records
    _write(folder / "delivery.json", {"outcome": outcome, "records": proof})
    return outcome






def run_turn(store, org, member, config, prompt, new, cwd, route_message=None, timeout=3600, sleep=time.sleep, clock=time.monotonic):
    seat = org["members"][member]
    carrier = seat.get("carrier")
    if (config.get("harness") != "claude-code" or config.get("surface") != "gui" or new or
            seat.get("harness") != "claude-code" or not carrier or "/" in carrier):
        raise TransportError("unavailable", "an existing main Claude Desktop seat is required; GUI bootstrap is unsupported")
    path = request_path(org["id"], member)
    request = _read(path, strict=True)
    if request:
        folder = runner.runs_dir() / ("claude-gui-" + request["nonce"])
        old_receipt = _read(folder / "receipt.json")
        outcome = _read(folder / "delivery.json").get("outcome", "unknown")
        if not receipt_matches(old_receipt, request) and outcome not in ("refused", "unavailable"):
            raise TransportError(outcome, "previous request has no matching GUI Stop; not sent again (nonce %s)" % request["nonce"], True)
    request = {"org_id": org["id"], "member": member, "carrier": carrier, "nonce": uuid.uuid4().hex,
               "expected": "%s · %s" % (org["name"], member), "prompt": prompt, "created": time.time()}
    folder = runner.runs_dir() / ("claude-gui-" + request["nonce"])
    folder.mkdir()
    _write(path, request)
    try:
        outcome = (route_message or route)(request, config, folder)
    except TransportError as error:
        if not error.possible:
            _write(folder / "delivery.json", {"outcome": error.outcome, "records": []})
        raise
    except Exception:
        # The helper may have sent before failing. Leave the pending request locked.
        raise TransportError("unknown", "router failed; inspect local delivery proof before retrying", True) from None
    if outcome in ("refused", "unavailable"):
        raise TransportError(outcome, "native target/capability absent or send refused; no CLI reviewer fallback")
    deadline = clock() + timeout
    while True:
        receipt = _read(folder / "receipt.json")
        if receipt_matches(receipt, request):
            return carrier, receipt["last_assistant_message"], False, None
        if clock() >= deadline:
            raise TransportError(outcome, "no matching GUI Stop receipt; not complete and not sent again (nonce %s)" % request["nonce"], True)
        sleep(1)


if __name__ == "__main__":
    # Used only as a command-local router hook, never as a model or peer client.
    if len(sys.argv) == 3 and sys.argv[1] == "--router-hook":
        try:
            print(json.dumps(router_hook(json.load(sys.stdin), Path(sys.argv[2]))))
        except Exception:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                              "permissionDecisionReason": "Relic router validation failed"}}))
            sys.exit(2)
