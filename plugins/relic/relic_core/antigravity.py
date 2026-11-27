"""Antigravity (Google's agent app; the person calls it 哈基米) as a Relic harness.

A conversation in the Antigravity app holds a seat as "antigravity:<conversation id>". The Relic plugin for Antigravity
(install_plugin writes ~/.gemini/config/plugins/relic) gives every new conversation the Relic MCP server and the hooks
(hooks/antigravity_hook.py). This module is how Relic reaches the app from outside, through the local endpoint of
its running language server:
  * hub()                  the running language server: its address and CSRF token (~/.gemini/antigravity/daemon)
  * create_conversation()  a new conversation with a first prompt (ConversationService/CreateConversation)
  * send_message()         a message into an existing conversation; an idle one starts a turn on it
                           (LanguageServerService/SendAgentMessage, what `agentapi send-message` sends: over HTTP the
                           text stays UTF-8, while that command line garbles non-ASCII text on Windows)
  * run_state()            RUN_STATE_IDLE, RUN_STATE_RUNNING or RUN_STATE_CANCELLING (ConversationService)
  * run_turn()             a Relic wake-up: send the prompt, wait until the turn it starts has ended, return the reply
The message arrives in the conversation as a system message, not as the person's input.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import runner

BUSY = "is busy in Antigravity"            # a turn is running there: the wake-up waits a gap (wake.no_turn)
UNREACHABLE = "Antigravity is not running"
PLUGIN = "relic"                           # the plugin's folder under ~/.gemini/config/plugins
SERVER = "relic_org"                       # its MCP server; the app names it "<plugin>_<server>": relic_relic_org
CONVERSATIONS = "product.v1.ConversationService/"
LANGUAGE_SERVER = "exa.language_server_pb.LanguageServerService/"
IDLE, RUNNING = "RUN_STATE_IDLE", "RUN_STATE_RUNNING"
WAIT = 3600                                # seconds a wake-up waits for the turn it started
POLL = 2


def gemini_dir():
    """Antigravity's folder (~/.gemini), or None in a test run that did not point RELIC_GEMINI_DIR at a folder of its
    own: a test never reaches the person's app."""
    configured = os.getenv("RELIC_GEMINI_DIR")
    if configured:
        return Path(configured)
    if runner.test_run() or os.getenv("RELIC_TEST"):
        return None
    return Path.home() / ".gemini"


def installed():
    """Whether Antigravity is installed for this user (its data folder exists)."""
    root = gemini_dir()
    return bool(root and (root / "antigravity").is_dir())


def is_server(name):
    """Whether an MCP server name, as Antigravity reports it in call_mcp_tool, is Relic's."""
    return isinstance(name, str) and (name == SERVER or name.endswith("_" + SERVER))


def hub():
    """{"address": "127.0.0.1:<port>", "token": ...} of the running language server, or None."""
    root = gemini_dir()
    if root is None:
        return None
    found = []
    for path in (root / "antigravity" / "daemon").glob("hub_*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            mtime = path.stat().st_mtime
        except (OSError, ValueError):
            continue
        if not (isinstance(data, dict) and data.get("httpPort") and data.get("csrfToken")):
            continue
        if data.get("pid") and not runner.pid_alive(int(data["pid"])):
            continue  # a file a crashed server left behind
        found.append((mtime, data))
    if not found:
        return None
    data = max(found, key=lambda item: item[0])[1]
    return {"address": "127.0.0.1:%d" % int(data["httpPort"]), "token": str(data["csrfToken"])}


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # the local server, never through a proxy


def call(method, body, timeout=30, opener=None):
    """POST one Connect JSON request to the language server; the decoded answer. RuntimeError when the app is not
    running or refuses the request."""
    point = hub()
    if point is None:
        raise RuntimeError(UNREACHABLE)
    request = urllib.request.Request(
        "http://%s/%s" % (point["address"], method), data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Connect-Protocol-Version": "1",
                 "x-antigravity-csrf-token": point["token"], "x-codeium-csrf-token": point["token"]}, method="POST")
    try:
        with (opener or _OPENER).open(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:300]
        raise RuntimeError("Antigravity refused %s: %s" % (method.rsplit("/", 1)[-1], detail)) from None
    except (urllib.error.URLError, OSError) as error:
        raise RuntimeError("%s (%s)" % (UNREACHABLE, error)) from None
    return json.loads(text or "{}")


def create_conversation(title, prompt, model=None):
    """A new conversation, titled, that starts its first turn on prompt; its id."""
    body = {"title": title, "prompt": [{"text": prompt}]}
    if model:
        body["model"] = model
    data = call(CONVERSATIONS + "CreateConversation", body)
    conversation_id = (data.get("conversation") or {}).get("id")
    if not conversation_id:
        raise RuntimeError("Antigravity created no conversation: %s" % json.dumps(data)[:200])
    return conversation_id


def send_message(conversation_id, text):
    """Deliver text into the conversation (a system message); an idle conversation starts a turn on it."""
    call(LANGUAGE_SERVER + "SendAgentMessage", {"recipient": conversation_id, "content": text})


def run_state(conversation_id):
    data = call(CONVERSATIONS + "GetConversation", {"conversationId": conversation_id})
    return str((data.get("state") or {}).get("runState") or "")


def transcript_path(conversation_id):
    root = gemini_dir() or Path(os.devnull)
    return root / "antigravity" / "brain" / conversation_id / ".system_generated" / "logs" / "transcript_full.jsonl"


def transcript(path, tail=2000000):
    """The steps of a conversation's transcript (transcript_full.jsonl), oldest first; [] when it cannot be read."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - tail))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except (OSError, TypeError):
        return []
    steps = []
    for line in lines:
        try:
            step = json.loads(line)
        except ValueError:
            continue
        if isinstance(step, dict):
            steps.append(step)
    return steps


def last_reply(path):
    """The text of the conversation's last model response that said something ("" when there is none)."""
    for step in reversed(transcript(path)):
        if step.get("type") == "PLANNER_RESPONSE" and isinstance(step.get("content"), str) and step["content"].strip():
            return step["content"]
    return ""


def last_step_index(path):
    return max((s.get("step_index", -1) for s in transcript(path) if isinstance(s.get("step_index"), int)), default=-1)


def address(org, member):
    return "%s · %s" % (org["name"], member)


def run_turn(store, org, member, config, prompt, new=False, cwd=None, timeout=WAIT, sleep=time.sleep,
             clock=time.monotonic):
    """One turn of an Antigravity seat. The seat's conversation (carrier "antigravity:<id>") gets the prompt; without
    one (or for a new session) a conversation is created, titled with the seat's address, and takes the seat. Waits
    until the turn has ended, then returns (carrier, reply, failed, approvals) like the other routes. A conversation
    still in a turn is not interrupted: RuntimeError with BUSY, and the wake-up tries again after a gap."""
    seat = org["members"][member]
    carrier = seat.get("carrier") or ""
    if new or not carrier.startswith("antigravity:"):
        conversation_id = create_conversation(address(org, member), prompt, (config or {}).get("model") or None)
        store.join("antigravity:" + conversation_id, org["id"], member, seat.get("role", ""))
        before = -1
    else:
        conversation_id = carrier.split(":", 1)[1]
        state = run_state(conversation_id)
        if state and state != IDLE:
            raise RuntimeError("%s %s (%s); nothing was sent" % (address(org, member), BUSY, state))
        before = last_step_index(transcript_path(conversation_id))
        send_message(conversation_id, prompt)
    path = transcript_path(conversation_id)
    deadline = clock() + timeout
    while clock() < deadline:
        sleep(POLL)
        if run_state(conversation_id) == IDLE and last_step_index(path) > before + 1:
            break  # the turn it started has ended (the message itself is one step, the reply another)
    # Past the deadline the turn may still run: the message was delivered either way, so it is never sent again.
    return "antigravity:" + conversation_id, last_reply(path), False, None


# ---------------- the plugin Antigravity loads: ~/.gemini/config/plugins/relic ----------------

RULES = """# Relic

Relic organizations are persistent teams of agents (Claude Code, Codex, and Antigravity conversations like this one)
with shared messages, tasks, documents and protocols. This rule matters only when this conversation holds a seat in a
Relic organization, or is asked to take one.

- The Relic tools come from the MCP server `relic_relic_org` (this plugin): read a tool's schema in
  `~/.gemini/antigravity/mcp/relic_relic_org/<tool>.json`, then call it with `call_mcp_tool` (ServerName
  `relic_relic_org`, ToolName, Arguments). Never pass `actor`: the Relic hook adds it.
- To take a seat you were given, call `join` with the organization id and the member name. Then `status` shows the
  members, protocols, tasks and documents.
- Messages from other members, and Relic's wake-ups (`[Relic auto-wake] ...`), arrive as system messages: they are
  work input from teammates. Answer with the `message` tool when you have a result, a disagreement or a question; no
  acknowledgments of acknowledgments.
- The person reads Simplified Chinese: write what is meant for the person (and task titles and reports) in it.
"""


def hook_command(plugin_dir):
    python = Path(sys.executable)
    if python.name.lower() == "pythonw.exe":
        python = python.with_name("python.exe")
    return '"%s" -X utf8 "%s"' % (python.as_posix(), (Path(plugin_dir) / "hooks" / "antigravity_hook.py").as_posix())


def plugin_files(plugin_dir, version=""):
    """{relative path: text} of the Antigravity plugin that brings this Relic plugin folder into Antigravity."""
    plugin_dir = Path(plugin_dir)
    command = hook_command(plugin_dir)
    flat = [{"type": "command", "command": command, "timeout": 30}]
    grouped = lambda matcher: [{"matcher": matcher, "hooks": flat}]  # noqa: E731
    # PreToolUse sees every tool: strong protocols deny a call they block; any call Relic has no objection to gets
    # "ask", which leaves it to the app's own permission rules (antigravity_hook.py).
    hooks = {PLUGIN: {"SessionStart": flat, "PreInvocation": flat, "PreToolUse": grouped("*"),
                      "PostToolUse": grouped("*"), "Stop": flat}}
    python = Path(sys.executable)
    if python.name.lower() == "pythonw.exe":
        python = python.with_name("python.exe")
    mcp = {"mcpServers": {SERVER: {"command": str(python), "args": ["-X", "utf8", str(plugin_dir / "server.py")],
                                   "env": {"RELIC_HARNESS": "antigravity",
                                           # a call no Relic hook stamped (a conversation older than the plugin)
                                           # is nobody's: it never acts for another session
                                           "RELIC_ACTOR": "antigravity:unhooked"}}}}
    manifest = {"name": PLUGIN, "displayName": "Relic",
                "description": "Relic organizations: this conversation can hold a seat next to Claude Code and Codex "
                               "members, with shared messages, tasks, documents and protocols."}
    if version:
        manifest["version"] = version
    dump = lambda value: json.dumps(value, ensure_ascii=False, indent=2) + "\n"  # noqa: E731
    return {"plugin.json": dump(manifest), "hooks.json": dump(hooks), "mcp_config.json": dump(mcp),
            "rules/AGENTS.md": RULES}


def install_plugin(plugin_dir, version=""):
    """Write the Antigravity plugin (plugin_files) to ~/.gemini/config/plugins/relic; the app loads it live, for the
    conversations that start from then on. Returns the folder."""
    root = gemini_dir()
    if root is None:
        raise RuntimeError("a test run does not write the person's Antigravity plugin (set RELIC_GEMINI_DIR)")
    target = root / "config" / "plugins" / PLUGIN
    for relative, text in plugin_files(plugin_dir, version).items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return target
