"""The person's Slack, read-only (relic_core/slack.py): connecting with a pasted user token that is kept encrypted and
never sent back, what each organization may read (its own choice, the nearest one above, then the default), the
members' slack tool (search, history, thread, channels), the read log that keeps no message text, and the Relic App's
settings routes. A fake Slack Web API on 127.0.0.1 answers; nothing reaches slack.com."""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from relic_core import api, slack  # noqa: E402
from relic_core.context import render  # noqa: E402
from relic_core.store import OrgError, Store  # noqa: E402
import server  # noqa: E402

TOKEN = "xoxp-1111-2222-3333-test"
LEAD = "lead-session"
CHILD = "child-session"


def user(uid, handle, display, real):
    return {"id": uid, "name": handle, "real_name": real, "profile": {"display_name": display, "real_name": real}}


class FakeSlack:
    """Just enough of the Slack Web API for these tests, with the field names Slack documents."""

    def __init__(self):
        self.calls = []
        self.scopes = ",".join(slack.USER_SCOPES)
        self.rts_error = None
        self.users = {u["id"]: u for u in (user("U1", "alice", "Alice", "Alice Liu"), user("U2", "bob", "Bob", "Bob Wu"),
                                           user("UME", "me", "Me", "Hongyi"))}
        self.convs = {"C0GEN0001": {"id": "C0GEN0001", "name": "general", "is_channel": True},
                      "C0SEC0002": {"id": "C0SEC0002", "name": "secret", "is_private": True},
                      "C0RND0003": {"id": "C0RND0003", "name": "random", "is_channel": True},
                      "D0ALC0001": {"id": "D0ALC0001", "is_im": True, "user": "U1"},
                      "G0GRP0001": {"id": "G0GRP0001", "name": "mpdm-alice--bob--me-1", "is_mpim": True}}
        self.member = ["C0GEN0001", "C0SEC0002", "D0ALC0001", "G0GRP0001"]
        self.messages = {
            "C0GEN0001": [{"ts": "1762300000.000100", "user": "U1", "text": "The deadline moved to Friday, <@U2> please check",
                    "reply_count": 2, "thread_ts": "1762300000.000100"},
                   {"ts": "1762300100.000200", "user": "U2", "text": "Draft: <https://example.org/doc|the plan> &amp; notes"},
                   {"ts": "1762300150.000250", "subtype": "channel_join", "user": "U1", "text": "<@U1> has joined"}],
            "C0SEC0002": [{"ts": "1762300200.000300", "user": "U2", "text": "secret budget numbers"}],
            "C0RND0003": [{"ts": "1762300250.000350", "user": "U1", "text": "lunch?"}],
            "D0ALC0001": [{"ts": "1762300300.000400", "user": "U1", "text": "about the deadline: can you review tonight?"}],
            "G0GRP0001": [{"ts": "1762300400.000500", "user": "U2", "text": "group deadline chat"}]}
        self.convs["C0LONG0004"] = {"id": "C0LONG0004", "name": "long", "is_channel": True}  # public, not joined
        self.messages["C0LONG0004"] = [{"ts": "17623%05d.000100" % i, "user": "U1", "text": "message %d " % i + "x" * 1400}
                                       for i in range(60)]
        self.replies = {("C0GEN0001", "1762300000.000100"): [
            self.messages["C0GEN0001"][0],
            {"ts": "1762300010.000110", "user": "U2", "text": "On it", "thread_ts": "1762300000.000100"},
            {"ts": "1762300020.000120", "user": "UME", "text": "Thanks <@U1>", "thread_ts": "1762300000.000100"}]}

    def kind(self, cid):
        c = self.convs[cid]
        return "im" if c.get("is_im") else "mpim" if c.get("is_mpim") else "private_channel" if c.get("is_private") \
            else "public_channel"

    def answer(self, method, p, auth):
        self.calls.append((method, dict(p)))
        if auth != "Bearer " + TOKEN:
            return {"ok": False, "error": "invalid_auth"}, {}
        if method == "auth.test":
            return {"ok": True, "url": "https://timan.slack.com/", "team": "TIMAN", "user": "me", "team_id": "T1",
                    "user_id": "UME"}, {"X-OAuth-Scopes": self.scopes}
        if method == "team.info":
            return {"ok": True, "team": {"id": "T1", "name": "TIMAN", "domain": "timan"}}, {}
        if method == "assistant.search.info":
            return {"ok": True, "is_ai_search_enabled": False}, {}
        if method == "users.info":
            found = self.users.get(p.get("user"))
            return ({"ok": True, "user": found} if found else {"ok": False, "error": "user_not_found"}), {}
        if method == "users.list":
            return {"ok": True, "members": list(self.users.values())}, {}
        if method == "conversations.info":
            found = self.convs.get(p.get("channel"))
            return ({"ok": True, "channel": found} if found else {"ok": False, "error": "channel_not_found"}), {}
        if method == "users.conversations":
            return {"ok": True, "channels": [self.convs[c] for c in self.member]}, {}
        if method == "conversations.list":
            return {"ok": True, "channels": [c for c in self.convs.values() if c.get("is_channel")]}, {}
        if method == "conversations.history":
            found = list(reversed(self.messages.get(p.get("channel"), [])))  # newest first, as Slack sends them
            limit = int(p.get("limit") or 100)
            return {"ok": True, "messages": found[:limit], "has_more": len(found) > limit}, {}
        if method == "conversations.replies":
            found = self.replies.get((p.get("channel"), p.get("ts")))
            return ({"ok": True, "messages": found} if found else {"ok": False, "error": "thread_not_found"}), {}
        if method == "assistant.search.context":
            if self.rts_error:
                return {"ok": False, "error": self.rts_error}, {}
            types = (p.get("channel_types") or "public_channel").split(",")
            hits = []
            for cid, items in self.messages.items():
                if self.kind(cid) not in types:
                    continue
                for m in items:
                    if p["query"].lower() in m["text"].lower():
                        hits.append({"author_name": self.users[m["user"]]["profile"]["display_name"],
                                     "author_user_id": m["user"], "team_id": "T1", "channel_id": cid,
                                     "channel_name": self.convs[cid].get("name") or "", "message_ts": m["ts"],
                                     "thread_ts": m.get("thread_ts") or "", "content": m["text"], "is_author_bot": False,
                                     "permalink": "https://timan.slack.com/archives/%s/p%s" % (cid, m["ts"].replace(".", ""))})
            return {"ok": True, "results": {"messages": hits[:int(p.get("limit") or 20)]},
                    "response_metadata": {"next_cursor": ""}}, {}
        if method == "search.messages":
            hits = [{"channel": dict(self.convs[cid]), "username": self.users[m["user"]]["name"], "user": m["user"],
                     "ts": m["ts"], "text": m["text"], "permalink": "https://timan.slack.com/x"}
                    for cid, items in self.messages.items() for m in items if p["query"].lower() in m["text"].lower()]
            return {"ok": True, "messages": {"matches": hits, "paging": {"page": 1, "pages": 1}}}, {}
        return {"ok": False, "error": "unknown_method"}, {}


def serve_fake(fake):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            size = int(self.headers.get("Content-Length") or 0)
            params = dict(urllib.parse.parse_qsl(self.rfile.read(size).decode("utf-8")))
            body, headers = fake.answer(self.path.rsplit("/", 1)[-1], params, self.headers.get("Authorization"))
            raw = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    return httpd


class SlackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        os.environ["RELIC_LANG"] = "en-US"
        os.environ["NO_PROXY"] = "127.0.0.1,localhost"
        self.fake = FakeSlack()
        self.httpd = serve_fake(self.fake)
        os.environ["RELIC_SLACK_API"] = "http://127.0.0.1:%d/api/" % self.httpd.server_address[1]
        slack.clear_cache()
        self.store = Store()
        self.oid = self.store.create(LEAD, "Lab", "run the lab", "lead", "lead")["id"]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        slack.clear_cache()
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def tool(self, actor=LEAD, **args):
        return slack.tool_call(self.store, actor, args)["text"]

    def child(self):
        child = self.store.create(CHILD, "Paper team", "write the paper", "writer", "writer")["id"]
        self.store.set_parent(child, self.oid)
        return child

    def test_organizations_are_listed_in_the_sidebars_order(self):
        """Latest event first, else the newest created, like app/views.org_list, among roots and among children."""
        with mock.patch("relic_core.store.now", return_value="2026-11-07T01:00:00Z"):
            zeta = self.store.create("zeta-session", "Zeta", "later work", "z", "z")["id"]
        with mock.patch("relic_core.store.now", return_value="2026-11-07T02:00:00Z"):
            alpha = self.store.create("alpha-session", "Alpha", "newest", "a", "a")["id"]
        def order():
            return [r["id"] for r in slack.status(self.store)["orgs"] if r["id"] in (alpha, zeta)]
        self.assertEqual(order(), [alpha, zeta])  # not by name
        with mock.patch("relic_core.store.now", return_value="2026-11-07T03:00:00Z"):
            self.store.send("zeta-session", ["z"], "a note to self")  # an event in Zeta makes it the more recent
        self.assertEqual(order(), [zeta, alpha])

    def test_connect_keeps_the_token_encrypted_and_never_sends_it_back(self):
        with self.assertRaisesRegex(ValueError, "slack.error.bot_token"):
            slack.connect(self.store, "xoxb-123")
        with self.assertRaisesRegex(ValueError, "slack.error.not_user_token"):
            slack.connect(self.store, "hello")
        with self.assertRaisesRegex(ValueError, "slack.error.invalid_token"):
            slack.connect(self.store, "xoxp-wrong")
        self.assertFalse(slack.token_path().exists())
        status = slack.connect(self.store, "  " + TOKEN + "\n")
        self.assertTrue(status["connected"])
        self.assertEqual(status["team"]["name"], "TIMAN")
        self.assertEqual(status["team"]["domain"], "timan")
        self.assertEqual(status["user"]["name"], "me")
        self.assertEqual(status["missing_scopes"], [])
        self.assertIs(status["ai_search"], False)
        self.assertNotIn(TOKEN, json.dumps(status))
        self.assertEqual(slack.load_token(), TOKEN)
        raw = slack.token_path().read_bytes()
        if os.name == "nt":
            self.assertTrue(raw.startswith(b"RELIC-DPAPI1\n"))
            self.assertNotIn(TOKEN.encode(), raw)
        else:
            self.assertEqual(slack.token_path().stat().st_mode & 0o777, 0o600)
        self.assertNotIn(TOKEN, slack.config_path().read_text(encoding="utf-8"))
        self.fake.scopes = "channels:history,channels:read"
        status = slack.connect(self.store, TOKEN)
        self.assertIn("im:history", status["missing_scopes"])

    def test_not_connected_then_disconnected(self):
        with self.assertRaisesRegex(OrgError, "not connected"):
            self.tool(op="channels")
        slack.connect(self.store, TOKEN)
        slack.set_scope(self.store, self.oid, "none")
        status = slack.disconnect(self.store)
        self.assertFalse(status["connected"])
        self.assertIsNone(status["team"])
        self.assertFalse(slack.token_path().exists())
        self.assertEqual(slack.load_config()["orgs"][self.oid]["mode"], "none")  # the person's choices stay
        with self.assertRaisesRegex(OrgError, "not connected"):
            self.tool(op="search", query="deadline")

    def test_by_default_every_organization_reads_every_channel_and_direct_message(self):
        slack.connect(self.store, TOKEN)
        text = self.tool(op="search", query="deadline")
        self.assertIn("#general", text)
        self.assertIn("direct message", text)
        self.assertIn("group deadline chat", text)
        self.assertIn("@Bob please check", text)
        searched = [p for m, p in self.fake.calls if m == "assistant.search.context"][-1]
        self.assertEqual(searched["channel_types"], "public_channel,private_channel,mpim,im")
        listing = self.tool(op="channels")
        for label in ("#general", "#secret", "@Alice", "@alice, @bob, @me"):
            self.assertIn(label, listing)
        self.assertIn("Public channels the person has not joined can be read too", listing)

    def test_an_organization_follows_the_nearest_choice_above_it(self):
        slack.connect(self.store, TOKEN)
        child = self.child()
        slack.set_scope(self.store, "", "all", dms=False)
        text = self.tool(op="search", query="deadline")
        self.assertNotIn("can you review tonight", text)
        searched = [p for m, p in self.fake.calls if m == "assistant.search.context"][-1]
        self.assertEqual(searched["channel_types"], "public_channel,private_channel")
        with self.assertRaisesRegex(OrgError, "has not let Lab read @Alice"):
            self.tool(op="history", channel="@alice")
        slack.set_scope(self.store, self.oid, "list", conversations=["C0GEN0001", "bad id"])
        self.assertEqual(slack.load_config()["orgs"][self.oid]["conversations"], ["C0GEN0001"])
        self.assertIn("Friday", self.tool(CHILD, op="history", channel="#general"))  # the child follows Lab
        with self.assertRaisesRegex(OrgError, "has not let Paper team read #secret"):
            self.tool(CHILD, op="history", channel="#secret")
        text = self.tool(CHILD, op="search", query="deadline")
        self.assertIn("#general", text)
        self.assertNotIn("group deadline chat", text)
        order = [r["id"] for r in slack.status(self.store)["orgs"]]
        self.assertLess(order.index(self.oid), order.index(child))  # a child is listed under its parent
        rows = {r["id"]: r for r in slack.status(self.store)["orgs"]}
        self.assertEqual(rows[child]["source"], self.oid)
        self.assertEqual(rows[child]["depth"], 1)
        self.assertIsNone(rows[child]["own"])
        slack.set_scope(self.store, child, "none")
        with self.assertRaisesRegex(OrgError, "has not let Paper team read Slack"):
            self.tool(CHILD, op="channels")
        self.assertEqual(slack.context_note(self.store, self.store.get(child)), "")
        slack.set_scope(self.store, child, "inherit")
        self.assertIn("Friday", self.tool(CHILD, op="history", channel="C0GEN0001"))
        with self.assertRaises(ValueError):
            slack.set_scope(self.store, "", "inherit")
        with self.assertRaises(ValueError):
            slack.set_scope(self.store, self.oid, "everything")

    def test_history_and_threads_read_as_plain_text_oldest_first(self):
        slack.connect(self.store, TOKEN)
        text = self.tool(op="history", channel="#general")
        self.assertTrue(text.startswith("#general (C0GEN0001, channel): 2 messages, oldest first."))
        self.assertLess(text.index("deadline moved"), text.index("Draft:"))
        self.assertIn("the plan (https://example.org/doc) & notes", text)
        self.assertIn("thread: 2 replies", text)
        self.assertNotIn("has joined", text)
        self.assertIn("about the deadline", self.tool(op="history", channel="@Alice Liu"))
        self.assertIn("lunch?", self.tool(op="history", channel="#random"))  # public, not joined
        with self.assertRaisesRegex(OrgError, "No channel named #nope"):
            self.tool(op="history", channel="#nope")
        thread = self.tool(op="thread", channel="C0GEN0001", ts="1762300000.000100")
        self.assertIn("Thread in #general (C0GEN0001), 3 messages.", thread)
        self.assertIn("Thanks @Alice", thread)
        with self.assertRaisesRegex(OrgError, "thread needs ts"):
            self.tool(op="thread", channel="C0GEN0001", ts="yesterday")
        with self.assertRaisesRegex(OrgError, "no such conversation"):
            self.tool(op="thread", channel="C0GEN0001", ts="1762300100.000200")
        history = [p for m, p in self.fake.calls if m == "conversations.history"]
        self.assertEqual(history[0]["limit"], "50")
        self.tool(op="history", channel="#general", oldest="2025-11-04", latest="1762300100.000200", limit=500)
        last = [p for m, p in self.fake.calls if m == "conversations.history"][-1]
        self.assertEqual(last["limit"], str(slack.HISTORY_LIMIT))
        self.assertEqual(last["latest"], "1762300100.000200")
        self.assertEqual(last["inclusive"], "true")
        self.assertRegex(last["oldest"], r"^\d{10}\.\d{6}$")
        with self.assertRaisesRegex(OrgError, "Times are a Slack ts"):
            self.tool(op="history", channel="#general", oldest="last week")

    def test_a_long_answer_keeps_the_newest_messages(self):
        slack.connect(self.store, TOKEN)
        text = self.tool(op="history", channel="#long", limit=60)
        self.assertLess(len(text), slack.OUTPUT_LIMIT + 2000)
        self.assertIn("earlier messages not shown: call history again with latest=", text)
        self.assertIn("message 59 ", text)
        self.assertNotIn("message 0 ", text)

    def test_reads_are_logged_without_what_was_read(self):
        slack.connect(self.store, TOKEN)
        self.tool(op="search", query="budget")
        self.tool(op="history", channel="#general")
        with self.assertRaises(OrgError):
            self.tool(op="history", channel="#nope")
        log = slack.reads(10)
        self.assertEqual([r["op"] for r in log], ["history", "history", "search"])
        self.assertEqual(log[1]["target"], "#general C0GEN0001")
        self.assertEqual(log[1]["count"], 2)
        self.assertEqual((log[1]["org_name"], log[1]["member"]), ("Lab", "lead"))
        self.assertIn("No channel named", log[0]["error"])
        self.assertEqual(log[2]["target"], "budget")
        raw = slack.log_path().read_bytes()
        for text in (b"secret budget numbers", b"deadline moved"):
            self.assertNotIn(text, raw)

    def test_search_falls_back_to_the_legacy_method_only_when_it_can(self):
        slack.connect(self.store, TOKEN)
        self.fake.rts_error = "missing_scope"
        with self.assertRaisesRegex(OrgError, "lacks a permission"):
            self.tool(op="search", query="deadline")
        config = slack.load_config()
        config["scopes"] = config["scopes"] + ["search:read"]
        slack.save_config(config)
        text = self.tool(op="search", query="deadline")
        self.assertIn("#general", text)
        self.assertTrue(any(m == "search.messages" for m, _ in self.fake.calls))
        self.fake.rts_error = "invalid_auth"
        with self.assertRaisesRegex(OrgError, "no longer accepts"):
            self.tool(op="search", query="deadline")

    def test_the_tool_through_the_relic_server(self):
        slack.connect(self.store, TOKEN)
        self.assertIn("slack", api.KNOWN)
        self.assertIn("slack", slack_tools())
        result = api.call(self.store, "slack", {"op": "channels", "actor": LEAD})
        reply = server.ok_result(result)
        self.assertEqual(len(reply["content"]), 1)
        self.assertTrue(reply["content"][0]["text"].startswith("Conversations this organization may read"))
        self.assertNotIn('"text_only"', reply["content"][0]["text"])
        context = render(self.store, self.store.get(self.oid), "lead")
        self.assertIn("Slack: the person's workspace TIMAN is connected", context)
        with self.assertRaisesRegex(OrgError, "slack ops"):
            api.call(self.store, "slack", {"op": "post", "actor": LEAD})


def slack_tools():
    return [t["name"] for t in api.TOOLS]


class SlackRoutes(unittest.TestCase):
    """The Relic App's settings page talks to these routes; every one needs the App's token."""

    def setUp(self):
        from app import hub as hubs, web
        from relic_core import wake
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        os.environ["CLAUDE_CONFIG_DIR"] = str(Path(self.tmp.name) / "claude")
        os.environ["NO_PROXY"] = "127.0.0.1,localhost"
        self.fake = FakeSlack()
        self.httpd = serve_fake(self.fake)
        os.environ["RELIC_SLACK_API"] = "http://127.0.0.1:%d/api/" % self.httpd.server_address[1]
        slack.clear_cache()
        self.store = Store()
        self.oid = self.store.create(LEAD, "Lab", "run the lab", "lead", "lead")["id"]
        self.retry = mock.patch.object(wake, "schedule_retry", lambda org_id, delay: None)
        self.retry.start()
        self.app, self.server = web.serve(0, store=self.store, write_info=False)
        self.app.namer.ask = lambda *args, **kwargs: {}
        self.app.explainer.ask = lambda *args, **kwargs: "{}"
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.app.port
        self.hubs = hubs

    def tearDown(self):
        self.app.stopping.set()
        self.app.hub.shutdown()
        self.server.shutdown()
        self.server.server_close()
        self.retry.stop()
        self.httpd.shutdown()
        self.httpd.server_close()
        slack.clear_cache()
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def call(self, path, body=None, token=True):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Relic-Token"] = self.app.token
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(request, timeout=20) as reply:
                return reply.status, json.loads(reply.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            with error:
                raw = error.read().decode("utf-8")
            return error.code, (json.loads(raw) if raw.startswith("{") else raw)

    def test_settings_routes(self):
        self.assertEqual(self.call("/api/slack", token=False)[0], 403)
        self.assertEqual(self.call("/api/slack/connect", {"token": TOKEN}, token=False)[0], 403)
        code, status = self.call("/api/slack")
        self.assertEqual(code, 200)
        self.assertFalse(status["connected"])
        self.assertIn("search:read.public", status["manifest"])
        self.assertNotIn("chat:write", status["manifest"])
        code, out = self.call("/api/slack/connect", {"token": "xoxb-1"})
        self.assertEqual(code, 400)
        self.assertIn("slack.error.bot_token", json.dumps(out))
        code, status = self.call("/api/slack/connect", {"token": TOKEN})
        self.assertEqual(code, 200)
        self.assertEqual(status["team"]["name"], "TIMAN")
        self.assertNotIn(TOKEN, json.dumps(status))
        code, picked = self.call("/api/slack/conversations")
        self.assertEqual(code, 200)
        self.assertEqual([c["id"] for c in picked["conversations"]], ["C0GEN0001", "C0SEC0002", "G0GRP0001", "D0ALC0001"])
        code, status = self.call("/api/slack/scope", {"org": self.oid, "mode": "list", "conversations": ["C0SEC0002"], "dms": True})
        self.assertEqual(code, 200)
        row = [r for r in status["orgs"] if r["id"] == self.oid][0]
        self.assertEqual(row["own"], {"mode": "list", "dms": True, "conversations": ["C0SEC0002"]})
        self.assertEqual(self.call("/api/slack/scope", {"org": "org_missing", "mode": "all"})[0], 400)
        code, status = self.call("/api/slack/disconnect", {})
        self.assertEqual(code, 200)
        self.assertFalse(status["connected"])
        self.assertEqual(self.call("/api/slack/conversations")[0], 400)


if __name__ == "__main__":
    unittest.main()
