"""The Relic App: what it shows (group chat, private chats, the secretary, decisions, transcripts), its local HTTP API
and guards, and the sessions it embeds through ACP (introduction, the person's messages, permission requests, cancel,
automatic wake-ups handed over by the runner). Embedded sessions run tests/fake_acp_agent.py, a small ACP agent."""
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import acp, views, web  # noqa: E402
from app import harness as harnesses  # noqa: E402
from relic_core import runner, wake  # noqa: E402
from relic_core.store import HUMAN, OrgError, Store  # noqa: E402

FAKE = Path(__file__).resolve().parent / "fake_acp_agent.py"
LEAD = "lead-session"


def wait_for(check, timeout=30, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        value = check()
        if value:
            return value
        time.sleep(step)
    raise AssertionError("timed out waiting")


def fake_launch(harness, extra_env=None):
    if harness not in harnesses.HARNESSES:
        raise RuntimeError("Unknown harness %s." % harness)
    return [sys.executable, "-X", "utf8", str(FAKE)], dict(os.environ, **(extra_env or {}))


class Isolated(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        os.environ["RELIC_LANG"] = "zh-CN"  # these tests read the Chinese texts, whatever the computer's language
        os.environ["CLAUDE_CONFIG_DIR"] = str(Path(self.tmp.name) / "claude")
        views._LOCATE.clear()
        views._META.clear()
        self.store = Store()
        self.oid = self.store.create(LEAD, "Demo", "build a demo", "lead", "lead role")["id"]

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()


class Views(Isolated):
    def setUp(self):
        super().setUp()
        self.store.join("ana-session", self.oid, "ana", "frontend")
        self.store.join(LEAD + "/agent123", self.oid, "sub", "checker")

    def test_the_person_is_a_message_recipient(self):
        self.store.send("ana-session", [HUMAN], "a question for the person")
        self.assertEqual(self.store.history(self.oid, 1)[0]["to"], [HUMAN])
        self.assertTrue(self.store.send_as(self.oid, "ana", [HUMAN], "a reply"))
        with self.assertRaises(OrgError):
            self.store.send("ana-session", ["nobody"], "unknown names are still refused")

    def test_group_chat_and_private_chats_split_the_messages(self):
        self.store.send(LEAD, ["ana"], "between members")
        to_ana = self.store.send_from_human(self.oid, ["ana"], "private to ana")
        self.store.send("ana-session", [HUMAN], "ana answers the person")
        self.store.send_from_human(self.oid, ["lead", "ana"], "the person writes to two members")
        self.store.send("ana-session", [HUMAN, "lead"], "ana to the person and lead")
        self.store.mark_read(self.oid, "ana", [to_ana])
        # in the group chat the person asks ana alone; ana's answer to the person stays in the group
        self.store.send_from_human(self.oid, ["ana"], "asked in the group", channel="group")
        self.store.send("ana-session", [HUMAN], "answered in the group")
        self.store.send_from_human(self.oid, ["ana"], "back in private", channel="private")
        self.store.send("ana-session", [HUMAN], "private again")

        group = views.chat(self.store, self.oid, "group")["items"]
        bodies = [i.get("body") for i in group if i["type"] != "notice"]
        self.assertEqual(bodies, ["between members", "the person writes to two members", "ana to the person and lead",
                                  "asked in the group", "answered in the group"])
        self.assertTrue(any(i["type"] == "notice" and "创建了组织" in i["text"] for i in group))

        private = views.chat(self.store, self.oid, "private", "ana")["items"]
        self.assertEqual([i["body"] for i in private], ["private to ana", "ana answers the person", "back in private",
                                                        "private again"])
        self.assertEqual(private[0]["read_by"], ["ana"])

        heads = views.chat_heads(self.store, self.oid)
        self.assertEqual(set(heads), {"group", "member:ana"})
        self.assertEqual(heads["member:ana"]["last"]["body"], "private again")
        self.assertEqual(len(heads["group"]["ids"]), 5)

    def test_secretary_is_the_marked_seat_else_the_leaders_main_session(self):
        self.assertEqual(views.secretary_of(self.store.get(self.oid)), "lead")
        self.store.set_seat_fields(self.oid, "ana", secretary=True)
        self.assertEqual(views.secretary_of(self.store.get(self.oid)), "ana")

    def test_an_organization_founded_in_the_app_has_a_secretary_only_when_one_is_set(self):
        # the person founds it and declines the secretary; the first seat leads, as a member, not as the secretary
        oid = self.store.found("App org", "built in the App")["id"]
        self.store.add_seat(oid, "lead", "负责人", {"harness": "claude-code", "surface": "acp"})
        self.store.join("claude-code-session", oid, "lead")
        org = self.store.get(oid)
        self.assertEqual((org["leader"], views.secretary_of(org)), ("lead", None))
        snap = views.snapshot(self.store, oid)
        self.assertEqual((snap["org"]["secretary"], snap["members"][0]["secretary"], snap["members"][0]["leader"]),
                         (None, False, True))
        self.store.add_seat(oid, "sec", "秘书", {"harness": "claude-code", "surface": "acp"})
        self.store.set_seat_fields(oid, "sec", secretary=True)
        self.assertEqual(views.secretary_of(self.store.get(oid)), "sec")

    def test_a_subagent_card_names_its_parent_session(self):
        snap = views.snapshot(self.store, self.oid)
        sub = next(m for m in snap["members"] if m["name"] == "sub")
        self.assertEqual((sub["surface"], sub["parent"], sub["agent"], sub["session"]), ("subagent", "lead", "agent123", LEAD))
        lead = next(m for m in snap["members"] if m["name"] == "lead")
        self.assertTrue(lead["secretary"] and lead["leader"])
        self.assertEqual(snap["org"]["secretary"], "lead")

    def test_decisions_list_what_waits_on_the_person(self):
        self.store.join("ana-session-2", self.oid, "ana")  # a new carrier: the earlier one is the person's to share
        self.store.request_trajectory("ana-session-2", "ana", carrier=1, reason="pick up where the last session stopped")
        self.store.work("ana-session-2", "task", {"title": "wire the API", "status": "blocked"})
        kinds = {d["kind"]: d for d in views.decisions(self.store, self.store.get(self.oid))}
        self.assertEqual((kinds["trajectory"]["member"], kinds["trajectory"]["carrier"]), ("ana", 1))
        self.assertEqual(kinds["task"]["title"], "wire the API")

    def test_transcripts_read_the_seat_s_own_file_and_never_the_parent_s(self):
        project = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / "X--work"
        (project / LEAD / "subagents").mkdir(parents=True)
        lines = [
            {"type": "user", "timestamp": "2026-10-26T10:00:00Z", "message": {"content": "build it"}},
            {"type": "assistant", "timestamp": "2026-10-26T10:00:01Z", "message": {"model": "claude-x", "content": [
                {"type": "text", "text": "on it"}, {"type": "tool_use", "id": "u1", "name": "Bash", "input": {"command": "ls"}}]}},
            {"type": "user", "timestamp": "2026-10-26T10:00:02Z", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "u1", "content": "a.txt"}]}},
        ]
        (project / (LEAD + ".jsonl")).write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
        side = [dict(x, isSidechain=True) for x in lines[:2]]
        (project / LEAD / "subagents" / "agent-agent123.jsonl").write_text("\n".join(json.dumps(x) for x in side), encoding="utf-8")

        main = views.transcript(LEAD)
        self.assertEqual([s["role"] for s in main["steps"]], ["user", "assistant", "tool_call", "tool_result"])
        self.assertEqual(views.session_meta(LEAD)["model"], "claude-x")
        sub = views.transcript(LEAD + "/agent123")
        self.assertEqual([s["role"] for s in sub["steps"]], ["user", "assistant", "tool_call"])
        missing = views.transcript(LEAD + "/agent999")
        self.assertIsNone(missing["path"])
        page = views.transcript(LEAD, limit=2)
        self.assertEqual((page["start"], [s["i"] for s in page["steps"]]), (2, [2, 3]))


class AcpClient(unittest.TestCase):
    def test_a_prompt_streams_updates_and_ends_the_turn(self):
        updates = []
        agent = acp.AcpAgent([sys.executable, "-X", "utf8", str(FAKE)], on_update=lambda m, p: updates.append(p["update"]))
        try:
            agent.start(timeout=20)
            self.assertIn("resume", agent.capabilities()["sessionCapabilities"])
            sid = agent.new_session(os.getcwd())["sessionId"]
            result = agent.prompt(sid, "hello there")
            self.assertEqual(result["stopReason"], "end_turn")
            text = "".join(acp.text_of(u["content"]) for u in updates if u["sessionUpdate"] == "agent_message_chunk")
            self.assertEqual(text, "echo: hello there")
            done = [u for u in updates if u["sessionUpdate"] == "tool_call_update"][0]
            self.assertEqual(acp.tool_text(done["content"]), "notes ok")
            with self.assertRaises(acp.AcpError):
                agent.request("no/such_method", {}, timeout=10)
        finally:
            agent.close()
        self.assertFalse(agent.alive)


class AppServer(Isolated):
    def setUp(self):
        super().setUp()
        self.launch = mock.patch.object(harnesses, "launch", fake_launch)
        self.launch.start()
        self.retries = []  # auto-wake's delayed re-check runs as a background process; record it instead
        self.retry = mock.patch.object(wake, "schedule_retry", lambda org_id, delay: self.retries.append(delay))
        self.retry.start()
        self.app, self.server = web.serve(0, store=self.store, write_info=True)
        self.app.namer.ask = lambda *args, **kwargs: {}  # no model calls in tests
        self.app.explainer.ask = lambda *args, **kwargs: "{}"
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.app.port

    def tearDown(self):
        self.app.stopping.set()
        self.app.hub.shutdown()
        self.server.shutdown()
        self.server.server_close()
        self.launch.stop()
        self.retry.stop()
        super().tearDown()

    def call(self, path, body=None, token=True, host=None):
        headers = {"Content-Type": "application/json"}
        if token and body is not None:
            headers["X-Relic-Token"] = self.app.token
        if host:
            headers["Host"] = host
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(request, timeout=20) as reply:
                raw = reply.read().decode("utf-8")
                return reply.status, (json.loads(raw) if raw.startswith(("{", "[")) else raw)
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read().decode("utf-8"))

    def messages(self, sender, to=None):
        return [m for m in self.store.history(self.oid, 200) if m["from"] == sender and (to is None or m["to"] == to)]

    def add_helper(self, **extra):
        code, out = self.call("/api/org/%s/members" % self.oid, dict({"name": "helper", "role": "assistant", "harness": "claude-code"}, **extra))
        self.assertEqual(code, 200, out)
        intro = wait_for(lambda: self.messages("helper", [HUMAN]))
        self.assertIn("echo:", intro[0]["body"])
        self.idle()  # the turn also dispatches waiting wake-ups after posting its reply
        return intro

    def idle(self, member="helper"):
        wait_for(lambda: (self.app.hub.status(self.oid, member) or {}).get("state") == "idle")

    def test_reads_and_guards(self):
        code, page = self.call("/")
        self.assertEqual(code, 200)
        self.assertIn(self.app.token, page)
        self.assertEqual(self.call("/api/orgs")[1][0]["id"], self.oid)
        code, snap = self.call("/api/org/" + self.oid)
        self.assertEqual((code, snap["org"]["secretary"], [m["name"] for m in snap["members"]]), (200, "lead", ["lead"]))
        self.assertEqual(self.call("/api/org/%s/send" % self.oid, {"to": ["lead"], "body": "x"}, token=False)[0], 403)
        self.assertEqual(self.call("/api/orgs", host="evil.example:%d" % self.app.port)[0], 403)
        self.assertEqual(self.call("/api/org/%s/send" % self.oid, {"to": ["lead"], "body": "hello lead"})[0], 200)
        self.assertEqual(self.messages(HUMAN)[-1]["body"], "hello lead")
        info = json.loads((Path(os.environ["RELIC_HOME"]) / "app.json").read_text(encoding="utf-8"))
        self.assertEqual((info["port"], info["token"]), (self.app.port, self.app.token))

    def test_the_page_reads_its_word_list(self):
        code, words = self.call("/api/i18n?lang=en-GB")
        self.assertEqual((code, words["lang"], [l["code"] for l in words["languages"]]), (200, "en-US", ["en-US", "zh-CN"]))
        self.assertEqual(words["strings"]["common.add_member"], "Add member")
        code, words = self.call("/api/i18n?lang=zh-CN")
        self.assertEqual((words["lang"], words["strings"]["common.add_member"]), ("zh-CN", "添加成员"))
        self.assertIn("English", [l["name"] for l in words["languages"]])
        # the server's own words follow the person's choice in Settings
        self.assertEqual(self.call("/api/prefs", {"lang": "en-US"})[0], 200)
        code, out = self.call("/api/org/%s/seat" % self.oid, {"name": ""})
        self.assertEqual((code, out), (400, {"error": "Enter a name."}))
        self.assertIn("created the organization", " ".join(i["text"] for i in self.call("/api/org/%s/chat?kind=group" % self.oid)[1]["items"] if i["type"] == "notice"))
        manifest = self.call("/manifest.webmanifest")[1]
        self.assertEqual(json.loads(manifest)["lang"] if isinstance(manifest, str) else manifest["lang"], "en-US")

    def test_a_refused_write_leaves_the_connection_usable(self):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.app.port, timeout=10)
        try:
            conn.request("POST", "/api/org/%s/send" % self.oid, body=json.dumps({"to": ["lead"], "body": "x" * 500}),
                         headers={"Content-Type": "application/json"})
            refused = conn.getresponse()
            refused.read()
            self.assertEqual(refused.status, 403)
            conn.request("GET", "/api/ping")  # same connection: the refused body must not leak into this request
            reply = conn.getresponse()
            self.assertEqual((reply.status, json.loads(reply.read())["app"]), (200, "relic"))
        finally:
            conn.close()

    def test_an_embedded_member_introduces_itself_and_answers_the_person(self):
        self.add_helper()
        seat = self.store.get(self.oid)["members"]["helper"]
        self.assertEqual((seat["config"]["surface"], seat["carrier"]), ("acp", seat["config"]["session"]))
        self.assertTrue(seat["carrier"].startswith("fake-"))
        self.assertEqual(self.call("/api/org/%s/send" % self.oid, {"to": ["helper"], "body": "ping 42"})[0], 200)
        reply = wait_for(lambda: [m for m in self.messages("helper", [HUMAN]) if "ping 42" in m["body"]])
        self.assertIn("[Relic App] The person (human) writes to you directly", reply[0]["body"])
        self.idle()
        mine = [m for m in self.messages(HUMAN) if m["body"] == "ping 42"][0]
        private = views.chat(self.store, self.oid, "private", "helper")["items"]
        self.assertEqual([m["read_by"] for m in private if m["id"] == mine["id"]], [["helper"]])
        live = self.call("/api/org/%s/live?member=helper" % self.oid)[1]
        self.assertTrue({"prompt", "tool", "assistant"} <= {i["type"] for i in live["items"]})
        self.assertEqual(live["status"]["state"], "idle")
        card = self.call("/api/org/%s/member/helper" % self.oid)[1]
        self.assertEqual((card["surface"], card["embedded"]), ("acp", True))

    def test_permission_requests_wait_for_the_person(self):
        self.add_helper()
        self.call("/api/org/%s/send" % self.oid, {"to": ["helper"], "body": "write it; needs permission"})
        pending = wait_for(lambda: self.app.hub.permissions(self.oid))
        snap = self.call("/api/org/" + self.oid)[1]
        decision = [d for d in snap["decisions"] if d["kind"] == "permission"][0]
        self.assertEqual((decision["title"], [o["id"] for o in decision["options"]]), ("Write notes.txt", ["allow", "reject"]))
        self.assertEqual(self.call("/api/permission/" + pending[0]["id"], {"option": "allow"})[0], 200)
        wait_for(lambda: [m for m in self.messages("helper", [HUMAN]) if "[permission: allow]" in m["body"]])
        self.assertEqual(self.app.hub.permissions(self.oid), [])

    def test_cancel_stops_the_running_turn(self):
        self.add_helper()
        self.call("/api/org/%s/send" % self.oid, {"to": ["helper"], "body": "a slow one"})
        wait_for(lambda: (self.app.hub.status(self.oid, "helper") or {}).get("state") == "running")
        self.assertEqual(self.call("/api/org/%s/cancel" % self.oid, {"member": "helper"})[0], 200)
        self.idle()
        self.assertEqual(runner.run_state(self.oid, "helper")["stop"], "cancelled")

    def test_idle_sessions_close_and_resume_on_the_next_message(self):
        self.add_helper()
        session = self.store.get(self.oid)["members"]["helper"]["config"]["session"]
        self.app.hub.reap(idle=60, now=time.time() + 30)  # not idle long enough
        self.assertIsNotNone(self.app.hub.status(self.oid, "helper"))
        self.app.hub.reap(idle=60, now=time.time() + 120)
        self.assertIsNone(self.app.hub.status(self.oid, "helper"))
        self.call("/api/org/%s/send" % self.oid, {"to": ["helper"], "body": "still there?"})
        wait_for(lambda: [m for m in self.messages("helper", [HUMAN]) if "still there?" in m["body"]])
        self.assertEqual(self.app.hub.status(self.oid, "helper")["session"], session)  # the same conversation

    def test_wake_ups_of_embedded_seats_go_through_the_app(self):
        self.add_helper()
        mid = self.store.send(LEAD, ["helper"], "please check the build")["message_id"]
        self.assertTrue(runner.start_turn(self.oid, "helper", "[Relic auto-wake] read your inbox", wake_from=["lead"],
                                          wake_hop=1, wake_message_ids=[mid]))
        receipt = wait_for(lambda: self.messages("helper", ["lead"]))
        self.assertTrue(receipt[0]["body"].startswith(wake.RECEIPT_MARK))
        state = wait_for(lambda: (runner.run_state(self.oid, "helper") or {}).get("status") == "done" and runner.run_state(self.oid, "helper"))
        self.assertEqual((state["via"], state["wake_from"]), ("relic-app", ["lead"]))
        self.assertEqual(state["wake_message_ids"], [mid])
        self.assertIn("ids %s" % mid, receipt[0]["body"])

    def test_wake_ups_fail_cleanly_when_the_app_is_closed(self):
        self.add_helper()
        (Path(os.environ["RELIC_HOME"]) / "app.json").write_text(json.dumps({"port": free_port(), "token": "x"}), encoding="utf-8")
        with self.assertRaises(RuntimeError) as caught:
            runner.start_turn(self.oid, "helper", "wake", wake_from=["lead"])
        self.assertIn("Relic App, which is not open", str(caught.exception))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class CodexSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.env = mock.patch.dict(os.environ, {"CODEX_HOME": self.tmp.name, "RELIC_ACP_HOME": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_an_embedded_codex_member_gets_the_person_s_own_sandbox_mode(self):
        config = Path(self.tmp.name) / "config.toml"
        config.write_text('model = "gpt-x"\nsandbox_mode = "danger-full-access"\napproval_policy = "never"\n', encoding="utf-8")
        self.assertEqual(harnesses.default_mode("codex"), "agent-full-access")
        config.write_text('sandbox_mode = "workspace-write"\n', encoding="utf-8")
        self.assertEqual(harnesses.default_mode("codex"), "workspace-write")
        config.unlink()
        self.assertEqual(harnesses.default_mode("codex"), "")  # the adapter's own default
        self.assertEqual(harnesses.default_mode("claude-code"), "auto")

    @unittest.skipUnless(os.name == "nt", "the sandbox override is for Windows")
    def test_on_windows_codex_starts_with_the_runner_s_sandbox_override(self):
        program = harnesses._codex_program(r"C:\Program Files\Codex\codex.exe")
        text = Path(program).read_text(encoding="utf-8")
        self.assertTrue(program.endswith("codex-app-server.cmd"))
        self.assertIn('"C:\\Program Files\\Codex\\codex.exe" %* -c windows.sandbox=\\"unelevated\\"', text)
        with mock.patch.dict(os.environ, {"RELIC_CODEX_WINDOWS_SANDBOX": ""}):
            self.assertEqual(harnesses._codex_program("codex.exe"), "codex.exe")


class Ports(unittest.TestCase):
    def test_a_taken_port_moves_the_server_to_another(self):
        with socket.socket() as taken:
            taken.bind(("127.0.0.1", 0))
            taken.listen()
            port = taken.getsockname()[1]
            server = web.bind(port)
            try:
                self.assertNotEqual(server.server_address[1], port)
            finally:
                server.server_close()


if __name__ == "__main__":
    unittest.main()
