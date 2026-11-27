"""Tests for the Relic App Antigravity ACP adapter, harness catalog, session binding, views, and live Hub E2E.

All tests run completely isolated from the person's live Antigravity app and Relic store (RELIC_HOME + RELIC_GEMINI_DIR).
"""
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import antigravity_acp, naming, views, web  # noqa: E402
from app import harness as harnesses  # noqa: E402
from app import hub as hubs  # noqa: E402
from relic_core import antigravity, wake  # noqa: E402
from relic_core.store import HUMAN, OrgError, Store  # noqa: E402


def wait_for(check, timeout=30, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        value = check()
        if value:
            return value
        time.sleep(step)
    raise AssertionError("timed out waiting")


class FakeAntigravityBackend:
    """In-memory double matching relic_core.antigravity's public contract."""

    CONVERSATIONS = "product.v1.ConversationService/"
    LANGUAGE_SERVER = "exa.language_server_pb.LanguageServerService/"
    IDLE = "RUN_STATE_IDLE"
    RUNNING = "RUN_STATE_RUNNING"
    BUSY = "is busy in Antigravity"
    PLUGIN = "relic"
    SERVER = "relic_org"

    def __init__(self, root):
        self.root = Path(root)
        self.created = []
        self.sent = []
        self.renamed = []
        self.listed = []
        self.states = {}       # sid -> list of states to pop (last sticks)
        self.transcripts = {}  # sid -> list of step dicts
        self.on_send = None
        self._seq = 0

    def gemini_dir(self):
        return self.root

    def installed(self):
        return (self.root / "antigravity").is_dir()

    def hub(self):
        return {"address": "127.0.0.1:55555", "token": "tok"}

    def is_server(self, name):
        return isinstance(name, str) and (name == self.SERVER or name.endswith("_" + self.SERVER))

    def create_conversation(self, title, prompt, model=None):
        self._seq += 1
        sid = "ag-conv-%d" % self._seq
        body = {"title": title, "prompt": [{"text": prompt}]}
        if model:
            body["model"] = model
        self.created.append((sid, body))
        self.states[sid] = [self.IDLE]
        self.transcripts[sid] = [
            {"step_index": 0, "type": "USER_INPUT", "content": prompt},
            {"step_index": 1, "type": "PLANNER_RESPONSE", "content": "OK"},
        ]
        return sid

    def call(self, method, body, timeout=30):
        if method == self.CONVERSATIONS + "UpdateConversation":
            self.renamed.append(dict(body))
            return {"conversation": {"id": body["conversationId"]}}
        if method == self.CONVERSATIONS + "ListConversations":
            return {"conversations": list(self.listed)}
        raise RuntimeError("unexpected RPC: " + method)

    def send_message(self, conversation_id, text):
        self.sent.append((conversation_id, text))
        if self.on_send:
            self.on_send(conversation_id, text)

    def run_state(self, conversation_id):
        queue = self.states.get(conversation_id)
        if not queue:
            return self.IDLE
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def transcript_path(self, conversation_id):
        return self.root / "antigravity" / "brain" / conversation_id / ".system_generated" / "logs" / "transcript_full.jsonl"

    def transcript(self, path):
        for sid, steps in self.transcripts.items():
            if self.transcript_path(sid) == Path(path):
                return list(steps)
        return []

    def last_step_index(self, path):
        return max((s.get("step_index", -1) for s in self.transcript(path) if isinstance(s.get("step_index"), int)),
                   default=-1)

    def last_reply(self, path):
        for step in reversed(self.transcript(path)):
            if step.get("type") == "PLANNER_RESPONSE" and isinstance(step.get("content"), str) and step["content"].strip():
                return step["content"]
        return ""


class AntigravityAcpProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.backend = FakeAntigravityBackend(self.tmp.name)
        self.messages = []
        self.server = antigravity_acp.AntigravityAcpServer(
            backend=self.backend,
            send=self.messages.append,
            poll=0.01,
            start_grace=0.05,
            busy_wait=0.2,
            bootstrap_timeout=2.0,
            turn_timeout=5.0,
            sleep=lambda s: time.sleep(min(s, 0.01)),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def reply_for(self, rid):
        return next(m for m in self.messages if m.get("id") == rid)

    def updates(self):
        return [m["params"]["update"] for m in self.messages if m.get("method") == "session/update"]

    def test_initialize_new_resume_and_set_model(self):
        self.server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": 1}})
        init = self.reply_for(1)["result"]
        self.assertEqual(init["protocolVersion"], 1)
        self.assertIn("resume", init["agentCapabilities"]["sessionCapabilities"])

        self.server.handle({"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"cwd": self.tmp.name}})
        created = self.reply_for(2)["result"]
        sid = created["sessionId"]
        self.assertEqual(sid, "ag-conv-1")
        # Bootstrap prompt initializes the conversation so subsequent SendAgentMessage calls wake it.
        self.assertTrue(self.backend.created[0][1]["prompt"][0]["text"].startswith(antigravity_acp.BOOTSTRAP_PROMPT))
        self.assertIn(self.tmp.name, self.backend.created[0][1]["prompt"][0]["text"])
        self.assertIn("flash", [m["modelId"] for m in created["models"]["availableModels"]])

        self.server.handle({"jsonrpc": "2.0", "id": 3, "method": "session/set_model",
                            "params": {"sessionId": sid, "modelId": "pro"}})
        self.assertEqual(self.reply_for(3)["result"], {})

        self.server.handle({"jsonrpc": "2.0", "id": 4, "method": "session/resume",
                            "params": {"sessionId": sid, "cwd": self.tmp.name}})
        self.assertEqual(self.reply_for(4)["result"]["models"]["currentModelId"], "pro")

    def test_prompt_streams_tools_relic_mcp_and_assistant_reply(self):
        self.server.handle({"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": self.tmp.name}})
        sid = self.reply_for(1)["result"]["sessionId"]

        def on_send(conv_id, text):
            self.backend.states[conv_id] = [self.backend.RUNNING, self.backend.IDLE]
            self.backend.transcripts[conv_id] = list(self.backend.transcripts[conv_id]) + [
                {"step_index": 2, "type": "SYSTEM_MESSAGE", "content": text},
                {"step_index": 3, "type": "PLANNER_RESPONSE", "tool_calls": [
                    {"name": "call_mcp_tool", "args": {"ServerName": '"relic_relic_org"', "ToolName": '"status"', "Arguments": "{}"}},
                    {"name": "run_command", "args": {"CommandLine": '"pytest -q"'}},
                ]},
                {"step_index": 4, "type": "GENERIC", "status": "DONE", "content": "status ok"},
                {"step_index": 5, "type": "GENERIC", "status": "DONE", "content": "10 passed"},
                {"step_index": 6, "type": "PLANNER_RESPONSE", "content": "All checks passed."},
            ]

        self.backend.on_send = on_send
        self.server.handle({"jsonrpc": "2.0", "id": 2, "method": "session/prompt",
                            "params": {"sessionId": sid, "prompt": [{"type": "text", "text": "check status"}]}})
        self.assertEqual(self.reply_for(2)["result"], {"stopReason": "end_turn"})
        self.assertEqual(self.backend.sent, [(sid, "check status")])

        ups = self.updates()
        tool_starts = [u for u in ups if u["sessionUpdate"] == "tool_call"]
        self.assertEqual(len(tool_starts), 2)
        self.assertEqual(tool_starts[0]["title"], "mcp__relic_org__status")
        self.assertTrue(hubs.relic_call(tool_starts[0]))
        self.assertEqual(tool_starts[1]["kind"], "execute")
        self.assertEqual(tool_starts[1]["rawInput"]["command"], "pytest -q")

        tool_done = [u for u in ups if u["sessionUpdate"] == "tool_call_update"]
        self.assertEqual([u["status"] for u in tool_done], ["completed", "completed"])

        chunks = [u["content"]["text"] for u in ups if u["sessionUpdate"] == "agent_message_chunk"]
        self.assertEqual("".join(chunks), "All checks passed.")

    def test_tool_only_turn_never_replays_previous_turn_text(self):
        self.server.handle({"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": self.tmp.name}})
        sid = self.reply_for(1)["result"]["sessionId"]

        def on_send(conv_id, text):
            self.backend.states[conv_id] = [self.backend.RUNNING, self.backend.IDLE]
            self.backend.transcripts[conv_id] = list(self.backend.transcripts[conv_id]) + [
                {"step_index": 2, "type": "SYSTEM_MESSAGE", "content": text},
                {"step_index": 3, "type": "PLANNER_RESPONSE", "tool_calls": [
                    {"name": "call_mcp_tool", "args": {"ServerName": '"relic_relic_org"', "ToolName": '"message"', "Arguments": "{}"}},
                ]},
                {"step_index": 4, "type": "GENERIC", "status": "DONE", "content": "sent"},
            ]

        self.backend.on_send = on_send
        self.server.handle({"jsonrpc": "2.0", "id": 2, "method": "session/prompt",
                            "params": {"sessionId": sid, "prompt": [{"type": "text", "text": "send silently"}]}})
        self.assertEqual(self.reply_for(2)["result"], {"stopReason": "end_turn"})
        chunks = [u["content"]["text"] for u in self.updates() if u["sessionUpdate"] == "agent_message_chunk"]
        self.assertEqual(chunks, [])

    def test_cancel_interrupts_waiting_prompt(self):
        self.server.handle({"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": self.tmp.name}})
        sid = self.reply_for(1)["result"]["sessionId"]
        started = threading.Event()

        def on_send(conv_id, _text):
            self.backend.states[conv_id] = [self.backend.RUNNING]
            started.set()

        self.backend.on_send = on_send
        worker = threading.Thread(
            target=self.server.handle,
            args=({"jsonrpc": "2.0", "id": 2, "method": "session/prompt",
                   "params": {"sessionId": sid, "prompt": [{"type": "text", "text": "long task"}]}},),
        )
        worker.start()
        self.assertTrue(started.wait(5))
        self.server.handle({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": sid}})
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.reply_for(2)["result"], {"stopReason": "cancelled"})

    def test_serve_exits_cleanly_on_eof(self):
        stream = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n")
        self.server.serve(stream)
        wait_for(lambda: self.messages)
        self.assertEqual(self.reply_for(1)["result"]["protocolVersion"], 1)


class AppIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        self.home = Path(self.tmp.name)
        os.environ["RELIC_HOME"] = str(self.home / "relic")
        os.environ["RELIC_GEMINI_DIR"] = str(self.home / "gemini")
        os.environ["RELIC_LANG"] = "zh-CN"
        views._LOCATE.clear()
        views._META.clear()
        views._STEPS.clear()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def test_harness_entry_catalog_and_plugin_detection(self):
        self.assertIn("antigravity", harnesses.HARNESSES)
        self.assertEqual(harnesses.actor_for("antigravity", "c-1"), "antigravity:c-1")
        self.assertTrue(harnesses.installed("antigravity"))
        self.assertEqual(harnesses.install_command("antigravity"), [])
        logs = []
        self.assertEqual(harnesses.install("antigravity", logs.append), 0)
        self.assertTrue(logs)

        backend = FakeAntigravityBackend(self.home / "gemini")
        (self.home / "gemini" / "antigravity").mkdir(parents=True)
        with mock.patch.object(harnesses, "_antigravity_module", return_value=backend):
            self.assertEqual(harnesses.antigravity_relic_plugin(), (False, False))
            self.assertFalse(harnesses.has_hooks("antigravity"))
            plugin = self.home / "gemini" / "config" / "plugins" / "relic"
            plugin.mkdir(parents=True)
            (plugin / "plugin.json").write_text('{"name":"relic"}\n', encoding="utf-8")
            (plugin / "hooks.json").write_text('{}\n', encoding="utf-8")
            self.assertEqual(harnesses.antigravity_relic_plugin(), (True, True))
            self.assertTrue(harnesses.has_hooks("antigravity"))
            self.assertEqual(harnesses.relic_for("antigravity", "org_1", "hajimi", "tok"), ([], None))
            entry = next(item for item in harnesses.catalog() if item["id"] == "antigravity")
            self.assertTrue(entry["available"])
            self.assertEqual(entry["title"], "Antigravity")
            self.assertEqual(entry["adapter"], "built-in")
            self.assertEqual(entry["install"], "")

        backend.hub = lambda: None
        with mock.patch.object(harnesses, "_antigravity_module", return_value=backend):
            entry = next(item for item in harnesses.catalog() if item["id"] == "antigravity")
            self.assertFalse(entry["available"])
            self.assertIn("Antigravity", entry["problem"])

    def test_views_transcript_surface_and_rename_for_antigravity(self):
        conv = "11111111-2222-3333-4444-555555555555"
        actor = "antigravity:" + conv
        tpath = self.home / "gemini" / "antigravity" / "brain" / conv / ".system_generated" / "logs" / "transcript_full.jsonl"
        tpath.parent.mkdir(parents=True)
        lines = [
            {"step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-27T05:00:00Z",
             "content": "<USER_REQUEST>\nHello team\n</USER_REQUEST>"},
            {"step_index": 1, "type": "PLANNER_RESPONSE", "created_at": "2026-11-27T05:00:01Z",
             "model": "gemini-4-hydrogen-tiered-high", "thinking": "checking",
             "tool_calls": [{"name": "read_file", "args": {"Path": "README.md"}}]},
            {"step_index": 2, "type": "GENERIC", "status": "DONE", "created_at": "2026-11-27T05:00:02Z",
             "content": "readme body"},
            {"step_index": 3, "type": "PLANNER_RESPONSE", "created_at": "2026-11-27T05:00:03Z",
             "model": "gemini-4-hydrogen-tiered-high", "content": "Ready to help."},
        ]
        tpath.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")

        self.assertEqual(views.harness_label("antigravity"), "Antigravity")
        meta = views.session_meta(actor)
        self.assertEqual((meta["harness"], meta["model"]), ("antigravity", "gemini-4-hydrogen-tiered-high"))
        tr = views.transcript(actor)
        self.assertEqual([s["role"] for s in tr["steps"]], ["user", "tool_call", "tool_result", "assistant"])
        self.assertEqual(tr["steps"][0]["text"], "Hello team")
        self.assertEqual(tr["steps"][-1]["text"], "Ready to help.")
        full = views.transcript(actor, full=True)
        self.assertIn("thinking", [s["role"] for s in full["steps"]])

        backend = FakeAntigravityBackend(self.home / "gemini")
        with mock.patch.object(antigravity, "call", backend.call):
            ok, note = naming.rename_session({"carrier": actor, "harness": "antigravity"}, "哈基米助手", lambda _: None, "zh-CN")
        self.assertTrue(ok)
        self.assertIn("Antigravity", note)
        self.assertEqual(backend.renamed, [{"conversationId": conv, "annotations": {"title": "哈基米助手"}}])

        store = Store()
        oid = store.create("lead-1", "Team", "ship", "lead")["id"]
        store.join(actor, oid, "hajimi", "research")
        store.add_seat(oid, "acp-ag", "assistant", {"harness": "antigravity", "surface": "acp"})
        snap = views.snapshot(store, oid, lang="en-US")
        mem = next(m for m in snap["members"] if m["name"] == "hajimi")
        self.assertEqual((mem["harness"], mem["harness_label"], mem["surface"], mem["has_transcript"]),
                         ("antigravity", "Antigravity", "desktop", True))
        self.assertIn("Antigravity", mem["model_note"])
        acp_mem = next(m for m in snap["members"] if m["name"] == "acp-ag")
        self.assertEqual((acp_mem["surface"], acp_mem["model_editable"]), ("acp", True))

    def test_sessions_picker_bind_and_open_session_for_antigravity(self):
        backend = FakeAntigravityBackend(self.home / "gemini")
        backend.listed = [
            {"id": "ag-live-1", "annotations": {"title": "哈基米主对话"},
             "state": {"updateTime": "2026-11-27T05:30:00Z"}},
        ]
        store = Store()
        oid = store.create("lead-1", "Team", "ship", "lead")["id"]
        app_inst = web.App(store=store)
        with mock.patch.object(antigravity, "hub", backend.hub), mock.patch.object(antigravity, "call", backend.call):
            listed = app_inst.sessions()["sessions"]
        picked = next(s for s in listed if s["harness"] == "antigravity")
        self.assertEqual((picked["id"], picked["title"], picked["surface"]), ("ag-live-1", "哈基米主对话", "app"))
        self.assertGreater(picked["updated"], 0)

        app_inst.bind(oid, {"session": picked, "member": "hajimi", "role": "research"})
        seat = store.get(oid)["members"]["hajimi"]
        self.assertEqual((seat["carrier"], seat["harness"]), ("antigravity:ag-live-1", "antigravity"))
        self.assertEqual(seat["config"], {"harness": "antigravity", "surface": "app", "model": ""})
        self.assertTrue(wake.wakeable(seat, seat["config"]))

        with self.assertRaises(OrgError) as caught:
            app_inst.open_session(oid, {"member": "hajimi"})
        self.assertIn("Antigravity", str(caught.exception))


class _MockAntigravityServer:
    """Real loopback Connect-HTTP mock server matching Antigravity's ConversationService & SendAgentMessage."""

    def __init__(self, gemini_dir):
        self.gemini = Path(gemini_dir)
        self.token = "test-csrf-token"
        self.lock = threading.Lock()
        self.seq = 0
        self.created = []
        self.sent = []
        self.convs = {}  # sid -> {"title": str, "model": str, "state": str, "step": int}

        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads((self.rfile.read(length) if length else b"{}").decode("utf-8"))
                if self.headers.get("x-antigravity-csrf-token") != parent.token:
                    self.send_response(403)
                    self.end_headers()
                    return
                out = parent._dispatch(self.path, body)
                data = json.dumps(out, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        daemon = self.gemini / "antigravity" / "daemon"
        daemon.mkdir(parents=True, exist_ok=True)
        (daemon / "hub_1.json").write_text(
            json.dumps({"pid": os.getpid(), "httpPort": self.port, "csrfToken": self.token}),
            encoding="utf-8",
        )
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()

    def _transcript_path(self, sid):
        path = self.gemini / "antigravity" / "brain" / sid / ".system_generated" / "logs" / "transcript_full.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _append(self, sid, steps):
        with self._transcript_path(sid).open("a", encoding="utf-8") as handle:
            for step in steps:
                handle.write(json.dumps(step, ensure_ascii=False) + "\n")

    def _dispatch(self, path, body):
        with self.lock:
            if path == "/" + antigravity.CONVERSATIONS + "CreateConversation":
                self.seq += 1
                sid = "mock-ag-%d" % self.seq
                self.created.append((sid, dict(body)))
                prompt_text = ((body.get("prompt") or [{}])[0]).get("text", "")
                self.convs[sid] = {"title": body.get("title", ""), "model": body.get("model", ""),
                                   "state": antigravity.IDLE, "step": 1}
                self._append(sid, [
                    {"step_index": 0, "type": "USER_INPUT", "content": prompt_text},
                    {"step_index": 1, "type": "PLANNER_RESPONSE", "model": body.get("model") or "flash", "content": "OK"},
                ])
                return {"conversation": {"id": sid}}
            if path == "/" + antigravity.CONVERSATIONS + "GetConversation":
                sid = body.get("conversationId", "")
                conv = self.convs.get(sid)
                if not conv:
                    raise RuntimeError("unknown conversation " + sid)
                return {"id": sid, "state": {"runState": conv["state"]}}
            if path == "/" + antigravity.LANGUAGE_SERVER + "SendAgentMessage":
                sid = body.get("recipient", "")
                text = body.get("content", "")
                self.sent.append((sid, text))
                conv = self.convs[sid]
                base = conv["step"] + 1
                self._append(sid, [
                    {"step_index": base, "type": "SYSTEM_MESSAGE", "content": text},
                    {"step_index": base + 1, "type": "PLANNER_RESPONSE", "tool_calls": [
                        {"name": "call_mcp_tool", "args": {"ServerName": "relic_relic_org", "ToolName": "status", "Arguments": {}}},
                    ]},
                    {"step_index": base + 2, "type": "GENERIC", "status": "DONE", "content": "org status ok"},
                    {"step_index": base + 3, "type": "PLANNER_RESPONSE", "model": conv["model"] or "flash",
                     "content": "回复：" + text.splitlines()[0][:60]},
                ])
                conv["step"] = base + 3
                return {}
            raise RuntimeError("unexpected path: " + path)

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class SubprocessHubEndToEndTests(unittest.TestCase):
    """Real Hub -> AcpAgent -> subprocess antigravity_acp.py -> real relic_core.antigravity -> loopback HTTP server."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        self.home = Path(self.tmp.name)
        os.environ["RELIC_HOME"] = str(self.home / "relic")
        os.environ["RELIC_GEMINI_DIR"] = str(self.home / "gemini")
        os.environ["RELIC_LANG"] = "zh-CN"
        self.mock_ag = _MockAntigravityServer(self.home / "gemini")
        self.retries = []
        self.retry = mock.patch.object(wake, "schedule_retry", lambda org_id, delay: self.retries.append(delay))
        self.retry.start()
        self.store = Store()
        self.oid = self.store.create("lead-session", "Demo", "ship it", "lead", "lead role")["id"]
        self.hub = hubs.Hub(store=self.store)

    def tearDown(self):
        self.hub.shutdown()
        self.retry.stop()
        self.mock_ag.close()
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def messages(self, sender, to=None):
        return [m for m in self.store.history(self.oid, 200) if m["from"] == sender and (to is None or m["to"] == to)]

    def test_hub_runs_antigravity_acp_subprocess_for_intro_human_and_resumed_wake(self):
        self.hub.create_member(self.oid, "hajimi", "research", "antigravity", model="flash")
        intro = wait_for(lambda: self.messages("hajimi", [HUMAN]), timeout=30)
        wait_for(lambda: (self.hub.status(self.oid, "hajimi") or {}).get("state") == "idle", timeout=30)

        self.assertEqual(len(self.mock_ag.created), 1)
        sid, created_body = self.mock_ag.created[0]
        self.assertEqual(created_body["title"], "Demo · hajimi")
        self.assertEqual(created_body["model"], "flash")
        seat = self.store.get(self.oid)["members"]["hajimi"]
        self.assertEqual((seat["carrier"], seat["harness"]), ("antigravity:" + sid, "antigravity"))
        self.assertEqual((seat["config"]["surface"], seat["config"]["session"]), ("acp", sid))
        self.assertIn("回复：", intro[0]["body"])

        # Human sends a UTF-8 Chinese message -> delivered through ACP subprocess and reply stored for HUMAN.
        mid = self.store.send_from_human(self.oid, ["hajimi"], "哈基米你好")
        self.hub.deliver_human(self.oid, "hajimi", "哈基米你好", message_id=mid)
        wait_for(lambda: len(self.messages("hajimi", [HUMAN])) >= 2, timeout=30)
        wait_for(lambda: (self.hub.status(self.oid, "hajimi") or {}).get("state") == "idle", timeout=30)
        self.assertTrue(any("哈基米你好" in text for _, text in self.mock_ag.sent))
        items = self.hub.items(self.oid, "hajimi")
        self.assertTrue({"prompt", "tool", "assistant"} <= {item["type"] for item in items})

        # Idle reap closes the adapter subprocess; a wake-up resumes the SAME Antigravity conversation (no new create).
        self.hub.reap(idle=-1)
        self.assertIsNone(self.hub.status(self.oid, "hajimi"))
        self.hub.prompt(self.oid, "hajimi", "[Relic auto-wake] 请汇报进度", {"kind": "wake", "wake_from": ["lead"], "hop": 1})
        wait_for(lambda: any("请汇报进度" in text for _, text in self.mock_ag.sent), timeout=30)
        wait_for(lambda: (self.hub.status(self.oid, "hajimi") or {}).get("state") == "idle", timeout=30)
        self.assertEqual(len(self.mock_ag.created), 1)
        receipts = wait_for(lambda: self.messages("hajimi", ["lead"]), timeout=30)
        self.assertTrue(receipts[0]["body"].startswith(views.RECEIPT))


if __name__ == "__main__":
    unittest.main()
