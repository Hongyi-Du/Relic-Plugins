"""Threads, like Slack's and one level deep: a reply's reply_to is the thread's root message, also when it answers a
reply; a reply without recipients goes to everyone in the thread so far (the person included when they took part).
A database from before threads gains the column when a Store opens it, and keeps working for processes that still
insert rows without it."""
import contextlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "hooks"))

from relic_core import api  # noqa: E402
from relic_core.context import render_messages  # noqa: E402
from relic_core.store import HUMAN, OrgError, Store, now  # noqa: E402
import relic_hook  # noqa: E402

LEAD, SCOUT, BUILDER, CHRONICLER = "s-lead", "s-scout", "s-builder", "s-chronicler"
QUESTION = "Can you check why test_wake times out on Windows? It fails about one run in five."
QUESTION_START = "Can you check why test_wake times out on Windows? It fail..."  # 60 characters

# The tables as earlier versions created them: hop came later, reply_to with threads.
FIRST_MESSAGES = ("CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT, sender TEXT, recipients TEXT, "
                  "body TEXT, episode_id TEXT, at TEXT)")
OLD_TABLES = """
CREATE TABLE orgs(id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE actors(actor TEXT PRIMARY KEY, org_id TEXT, member TEXT, bound_at TEXT);
CREATE TABLE reads(org_id TEXT, message_id INTEGER, member TEXT, at TEXT, PRIMARY KEY(org_id, message_id, member));
CREATE TABLE activity(id INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT, member TEXT, tool TEXT, kind TEXT, summary TEXT,
    failed INTEGER, at REAL);
CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT, member TEXT, kind TEXT, body TEXT, at TEXT);
"""


def columns(path):
    with contextlib.closing(sqlite3.connect(path)) as db:
        return [r[1] for r in db.execute("PRAGMA table_info(messages)")]


class Threads(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        self.store = Store()
        self.oid = self.store.create(LEAD, "Lab", "ship it", "lead")["id"]
        for actor, member in ((SCOUT, "scout"), (BUILDER, "builder"), (CHRONICLER, "chronicler")):
            self.store.join(actor, self.oid, member)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def last(self):
        return self.store.history(self.oid, 1)[-1]

    def last_sent(self):
        return self.store.events(self.oid, ["message.sent"])[-1]["body"]

    def test_a_reply_to_a_reply_joins_the_root_thread(self):
        root = self.store.send(LEAD, ["scout"], QUESTION)["message_id"]
        self.assertNotIn("reply_to", self.last_sent())  # a message that starts no thread is as before
        first = self.store.send(SCOUT, None, "On it.", reply_to=root)
        self.assertEqual(first["reply_to"], root)
        self.assertEqual(self.last_sent(), {"id": first["message_id"], "to": ["lead"], "reply_to": root})
        second = self.store.send(LEAD, None, "Thanks.", reply_to=first["message_id"])  # answers the reply
        self.assertEqual(second["reply_to"], root)
        self.assertEqual(self.store.send(SCOUT, None, "Found it.", reply_to="#%d" % second["message_id"])["reply_to"],
                         root)
        self.assertEqual([m["reply_to"] for m in self.store.history(self.oid)], [None, root, root, root])
        # no reply_to (or 0) is a message outside any thread
        self.assertNotIn("reply_to", self.store.send(LEAD, ["scout"], "Something else.", reply_to=0))
        self.assertIsNone(self.last()["reply_to"])

    def test_a_reply_without_recipients_goes_to_the_thread(self):
        root = self.store.send(LEAD, ["scout"], "Plan the release.")["message_id"]
        self.assertEqual(self.store.send(SCOUT, None, "Draft is in the docs.", reply_to=root)["to"], ["lead"])
        # a member joins the thread: everyone in it so far gets the reply, and later replies reach the newcomer
        self.assertEqual(self.store.send(BUILDER, [], "I can build it.", reply_to=root)["to"], ["lead", "scout"])
        self.assertEqual(self.store.send(LEAD, None, "Go ahead.", reply_to=root)["to"], ["scout", "builder"])
        self.assertEqual(self.store.unread(CHRONICLER), [])  # never in the thread
        # ['all'] and explicit lists keep their meaning; the reply stays in the thread
        everyone = self.store.send(SCOUT, ["all"], "Release at five.", reply_to=root)
        self.assertEqual((everyone["to"], everyone["reply_to"]), (["lead", "builder", "chronicler"], root))
        named = self.store.send(SCOUT, ["human"], "FYI, release at five.", reply_to=root)
        self.assertEqual((named["to"], named["reply_to"]), ([HUMAN], root))
        with self.assertRaises(OrgError):
            self.store.send(SCOUT, ["nobody"], "x", reply_to=root)
        # the person and chronicler received thread replies, so they are in it now
        self.assertEqual(self.store.send(LEAD, None, "Done.", reply_to=root)["to"],
                         ["scout", "builder", "chronicler", HUMAN])

    def test_the_person_in_a_thread(self):
        root = self.store.send_from_human(self.oid, ["lead", "scout"], "Which of you takes the docs?")
        # a member's reply goes back to the person and to the other members in the thread
        self.assertEqual(self.store.send(LEAD, None, "Scout does.", reply_to=root)["to"], [HUMAN, "scout"])
        reply = self.store.send(SCOUT, None, "Yes, today.", reply_to=root)["message_id"]
        # the person answers a reply: the same thread, to the members in it and never to the person
        mid = self.store.send_from_human(self.oid, None, "Good, thanks.", channel="group", reply_to=reply)
        last = self.last()
        self.assertEqual((last["id"], last["from"], last["to"], last["reply_to"]), (mid, HUMAN, ["lead", "scout"], root))
        self.assertEqual(self.last_sent(), {"id": mid, "to": ["lead", "scout"], "channel": "group", "reply_to": root})
        # the person joins a thread between members; explicit recipients still work
        other = self.store.send(LEAD, ["builder"], "Can you build the installer?")["message_id"]
        self.store.send_from_human(self.oid, [], "Please do.", reply_to=other)
        self.assertEqual((self.last()["to"], self.last()["reply_to"]), (["lead", "builder"], other))
        self.store.send_from_human(self.oid, ["builder"], "Only builder.", reply_to=other)
        self.assertEqual((self.last()["to"], self.last()["reply_to"]), (["builder"], other))
        self.assertEqual(self.store.send(BUILDER, None, "Building.", reply_to=other)["to"], ["lead", HUMAN])
        with self.assertRaises(OrgError):
            self.store.send_from_human(self.oid, [HUMAN], "to myself", reply_to=other)
        # without reply_to nothing changed: no reply_to on the event either
        self.store.send_from_human(self.oid, ["all"], "Thanks, all.")
        self.assertIsNone(self.last()["reply_to"])
        self.assertNotIn("reply_to", self.last_sent())

    def test_messages_the_plugin_writes_join_threads(self):
        root = self.store.send(LEAD, ["scout", "builder"], "Status?")["message_id"]
        mid = self.store.send_as(self.oid, "scout", None, "Scout's relayed answer.", relayed=True, reply_to=root)
        self.assertEqual((self.last()["id"], self.last()["to"], self.last()["reply_to"]), (mid, ["lead", "builder"], root))
        self.assertEqual(self.last_sent(), {"id": mid, "to": ["lead", "builder"], "relayed": True, "reply_to": root})
        self.store.send_as(self.oid, "builder", [HUMAN], "To the person, in the thread.", reply_to=mid)
        self.assertEqual((self.last()["to"], self.last()["reply_to"]), ([HUMAN], root))
        self.store.send_as(self.oid, "scout", [HUMAN], "A reply outside any thread.")
        self.assertIsNone(self.last()["reply_to"])
        self.assertNotIn("reply_to", self.last_sent())

    def test_unread_and_history_say_which_thread(self):
        root = self.store.send(LEAD, ["scout"], QUESTION)["message_id"]
        top, = self.store.unread(SCOUT)
        self.assertIsNone(top["reply_to"])
        self.assertNotIn("thread", top)
        reply = self.store.send(SCOUT, None, "It is the settle timer.", reply_to=root)["message_id"]
        self.assertEqual(self.store.unread_by_member(self.oid)["lead"][-1]["reply_to"], root)
        got, = self.store.unread(LEAD, mark=False)
        self.assertEqual((got["id"], got["reply_to"]), (reply, root))
        self.assertEqual(got["thread"], {"id": root, "from": "lead", "snippet": QUESTION_START})
        self.assertEqual([m["reply_to"] for m in self.store.history(self.oid)], [None, root])
        self.assertEqual([m["reply_to"] for m in self.store.history(self.oid, after=root)], [root])
        # what the member reads: the inbox and the messages the hook hands over after a tool call
        line = '[msg %d from scout, in thread #%d ("%s")] It is the settle timer.' % (reply, root, QUESTION_START)
        self.assertEqual(render_messages([got]), line)
        self.assertEqual(render_messages([top]), "[msg %d from lead] %s" % (root, QUESTION))  # as before
        self.assertIn(line, relic_hook.peer_messages(self.store, LEAD))  # marks it read
        self.store.send(SCOUT, None, "Fixed in T3.\nSee the diff.", episode_id="E7", reply_to=reply)
        out = api.inbox(self.store, LEAD)
        self.assertEqual(out["messages"][0]["reply_to"], root)
        self.assertIn('ep E7, in thread #%d ("%s")] Fixed in T3.' % (root, QUESTION_START), out["text"])

    def test_a_long_or_multiline_root_is_shown_on_one_short_line(self):
        root = self.store.send(LEAD, ["scout"], "Short\n\n  question?")["message_id"]
        self.store.send(SCOUT, None, "Short answer.", reply_to=root)
        got, = self.store.unread(LEAD)
        self.assertEqual(got["thread"]["snippet"], "Short question?")
        self.assertIn('in thread #%d ("Short question?")' % root, render_messages([got]))

    def test_a_reply_needs_a_message_of_this_organization(self):
        other = self.store.create("s-olga", "Other", "elsewhere", "olga")["id"]
        self.store.join("s-oscar", other, "oscar")
        foreign = self.store.send("s-olga", ["oscar"], "Not yours.")["message_id"]
        mine = self.store.send(LEAD, ["scout"], "Ours.")["message_id"]
        for reply_to in (foreign, 9999, "twelve"):
            with self.assertRaises(OrgError):
                self.store.send(LEAD, None, "hm", reply_to=reply_to)
            with self.assertRaises(OrgError):
                self.store.send_from_human(self.oid, None, "hm", reply_to=reply_to)
            with self.assertRaises(OrgError):
                self.store.send_as(self.oid, "lead", ["scout"], "hm", reply_to=reply_to)
        with self.assertRaisesRegex(OrgError, "no message #%d in this organization" % foreign):
            self.store.send(SCOUT, ["lead"], "hm", reply_to=foreign)
        with self.assertRaisesRegex(OrgError, "id of the message"):
            self.store.send(SCOUT, None, "hm", reply_to="twelve")
        self.assertEqual([m["id"] for m in self.store.history(self.oid)], [mine])  # nothing written
        # a thread of the other organization is its own
        self.assertEqual(self.store.send("s-oscar", None, "Mine, though.", reply_to=foreign)["to"], ["olga"])

    def test_the_message_tool_takes_reply_to(self):
        schema = next(t for t in api.TOOLS if t["name"] == "message")["inputSchema"]
        self.assertEqual(schema["properties"]["reply_to"]["type"], "integer")
        self.assertIn("thread", schema["properties"]["reply_to"]["description"])
        self.assertEqual(schema["required"], ["body"])  # `to` may be left out for a thread reply
        root = api.handle_call(self.store, "message", {"to": ["scout"], "body": "A question."}, LEAD)["message_id"]
        out = api.handle_call(self.store, "message", {"body": "An answer.", "reply_to": root}, SCOUT)
        self.assertEqual((out["to"], out["reply_to"]), (["lead"], root))
        with self.assertRaises(OrgError):
            api.handle_call(self.store, "message", {"body": "x", "reply_to": 4242}, SCOUT)


class OldDatabase(unittest.TestCase):
    """A store written by earlier versions: rows without reply_to, and processes that still write them so."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)

    def tearDown(self):
        self.tmp.cleanup()

    def old_store(self, name, messages_table, with_hop):
        path = Path(self.tmp.name) / name / "relic.sqlite3"
        path.parent.mkdir()
        org = {"id": "org_old", "name": "Old", "purpose": "", "governance": "peer", "leader": None, "status": "active",
               "members": {"lead": {"role": ""}, "ana": {"role": ""}}}
        with contextlib.closing(sqlite3.connect(path)) as db:
            db.executescript(OLD_TABLES + messages_table + ";")
            db.execute("INSERT INTO orgs VALUES(?,?)", ("org_old", json.dumps(org)))
            db.executemany("INSERT INTO actors VALUES(?,?,?,?)", [("s-old-lead", "org_old", "lead", now()),
                                                                 ("s-old-ana", "org_old", "ana", now())])
            self.insert_old(db, "Written before threads.", with_hop)
            db.commit()
        return path

    def insert_old(self, db, body, with_hop):
        if with_hop:
            db.execute("INSERT INTO messages(org_id,sender,recipients,body,episode_id,at,hop) VALUES(?,?,?,?,?,?,?)",
                       ("org_old", "lead", json.dumps(["ana"]), body, None, now(), 0))
        else:
            db.execute("INSERT INTO messages(org_id,sender,recipients,body,episode_id,at) VALUES(?,?,?,?,?,?)",
                       ("org_old", "lead", json.dumps(["ana"]), body, None, now()))

    def test_the_column_is_added_and_old_rows_are_top_level(self):
        variants = (("previous", FIRST_MESSAGES[:-1] + ", hop INTEGER DEFAULT 0)", True),
                    ("first", FIRST_MESSAGES, False))
        for name, table, with_hop in variants:
            with self.subTest(schema=name):
                path = self.old_store(name, table, with_hop)
                self.assertNotIn("reply_to", columns(path))
                store = Store(path)
                self.assertEqual([c for c in columns(path) if c in ("hop", "reply_to")], ["hop", "reply_to"])
                old, = store.history("org_old")
                self.assertIsNone(old["reply_to"])
                got, = store.unread("s-old-ana", mark=False)
                self.assertIsNone(got["reply_to"])
                self.assertEqual(render_messages([got]), "[msg %d from lead] Written before threads." % old["id"])
                self.assertEqual(store.unread_by_member("org_old")["ana"][0]["reply_to"], None)
                # a process still on the code from before writes a row without the column
                with contextlib.closing(sqlite3.connect(path)) as db:
                    self.insert_old(db, "Still written the old way.", True)
                    db.commit()
                self.assertIsNone(store.history("org_old")[-1]["reply_to"])
                # replies to the old messages work, in a thread of their own
                answer = store.send("s-old-ana", None, "Answered in its thread.", reply_to=old["id"])
                self.assertEqual((answer["to"], answer["reply_to"]), (["lead"], old["id"]))
                got, = store.unread("s-old-lead")
                self.assertEqual(got["thread"]["snippet"], "Written before threads.")
                # another process opening the store finds the column there
                Store(path)
                self.assertEqual(columns(path).count("reply_to"), 1)


if __name__ == "__main__":
    unittest.main()
