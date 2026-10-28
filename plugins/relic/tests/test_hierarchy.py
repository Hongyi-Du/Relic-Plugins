"""Organizations above and below: the person places an organization under another in the Relic App; members of an
organization above see one below, write to its members, assign its tasks and issue protocols that take effect there
directly; a protocol marked downward binds every organization below its own; members below only report upward."""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import views, web  # noqa: E402
from relic_core import api, wake  # noqa: E402
from relic_core.context import render, render_messages  # noqa: E402
from relic_core.store import HUMAN, OrgError, Store  # noqa: E402

CHIEF, HELPER, LEAD, DEV, SUB, OTHER = "chief-s", "helper-s", "lead-s", "dev-s", "sub-s", "other-s"
DENY_PUSH = {"effect": "deny", "tools": ["Bash"], "input_contains": ["git push"], "reason": "the secretariat pushes"}


class Hierarchy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        os.environ["RELIC_LANG"] = "zh-CN"
        self.store = Store()
        s = self.store
        self.sec = s.create(CHIEF, "秘书处", "the person's secretariat", "chief", "chief of staff")["id"]
        s.join(HELPER, self.sec, "helper", "assistant")
        self.team = s.create(LEAD, "Team", "build the site", "lead", "lead")["id"]
        s.join(DEV, self.team, "dev", "frontend")
        self.sub = s.create(SUB, "Sub", "a part of the site", "s1", "worker")["id"]
        self.other = s.create(OTHER, "Other", "unrelated", "o1", "")["id"]
        s.set_parent(self.team, self.sec)
        s.set_parent(self.sub, self.team)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    # ---------------- the links
    def test_the_person_places_organizations_in_a_tree(self):
        s = self.store
        self.assertEqual([o["id"] for o in s.ancestors(s.get(self.sub))], [self.team, self.sec])
        self.assertEqual({o["id"] for o in s.descendants(self.sec)}, {self.team, self.sub})
        with self.assertRaises(OrgError):
            s.set_parent(self.sec, self.sub)  # a circle
        with self.assertRaises(OrgError):
            s.set_parent(self.sec, self.sec)
        s.set_parent(self.sub, None)
        self.assertEqual(s.descendants(self.team), [])
        kinds = [e["kind"] for e in s.events(self.team)]
        self.assertIn("organization.parent_set", kinds)
        self.assertIn("organization.child_added", kinds)
        self.assertIn("organization.child_removed", kinds)

    def test_a_member_acts_only_below_and_reports_only_above(self):
        s = self.store
        self.assertEqual(s.reach(CHIEF, "Sub")[3], "down")  # any depth, by name or id
        self.assertEqual(s.reach(DEV, self.sec, up=True)[3], "up")
        with self.assertRaises(OrgError):
            s.reach(DEV, self.sec)  # above: report only
        with self.assertRaises(OrgError):
            s.reach(CHIEF, self.other)  # unrelated
        with self.assertRaises(OrgError):
            s.work(DEV, "task", {"org": self.sec, "title": "x", "owner": "chief"})
        with self.assertRaises(OrgError):
            s.protocol(DEV, "propose", {"org": self.sec, "title": "x", "rationale": "y", "guidance": "g",
                                        "trigger": "t", "evidence": ["msg 1"]})
        with self.assertRaises(OrgError):
            s.send(OTHER, ["lead"], "hello", org=self.team)

    # ---------------- messages
    def test_writing_down_and_reporting_up(self):
        s = self.store
        sent = s.send(CHIEF, ["dev"], "Ship the landing page first.", org="Team")
        self.assertEqual(sent["org_id"], self.team)
        got = s.unread(DEV)
        self.assertEqual((got[0]["from"], got[0]["from_org"], got[0]["body"]),
                         (self.sec + "/chief", "秘书处", "Ship the landing page first."))
        self.assertIn("from %s/chief of 秘书处" % self.sec, render_messages(got))
        # the answer goes back by the sender's name, or by the organization
        back = s.send(DEV, [self.sec + "/chief"], "On it.")
        self.assertEqual(back["org_id"], self.sec)
        self.assertEqual(s.unread(CHIEF)[0]["from"], self.team + "/dev")
        s.send(LEAD, ["all"], "Weekly report: on track.", org=self.sec)
        self.assertEqual({m["body"] for m in s.unread(HELPER)}, {"Weekly report: on track."})
        reached = [e for e in s.events(self.sec) if e["kind"] == "organization.reached"]
        self.assertEqual(reached[0]["body"]["to"], ["dev"])
        for wrong in ([HUMAN], ["nobody"]):
            with self.assertRaises(OrgError):
                s.send(CHIEF, wrong, "x", org=self.team)
        with self.assertRaises(OrgError):
            s.send(CHIEF, ["dev"], "x", episode_id="E1", org=self.team)
        with self.assertRaises(OrgError):
            s.send(CHIEF, ["helper", self.team + "/dev"], "mixed")

    def test_a_receipt_goes_back_to_the_organization_that_woke_the_member(self):
        s = self.store
        s.send(CHIEF, ["dev"], "Please check the build.", org=self.team)
        s.send_as(self.team, "dev", [self.sec + "/chief"], "[Relic auto-receipt] dev was woken by your message(s)")
        got = s.unread(CHIEF)
        self.assertEqual((got[0]["from"], got[0]["body"][:20]), (self.team + "/dev", "[Relic auto-receipt]"))

    def test_a_message_down_wakes_the_organization_below(self):
        woken = []
        with mock.patch.object(wake, "dispatch", lambda store, org_id, **kw: woken.append(org_id) or []), \
                mock.patch.object(wake, "dispatch_for_actor", lambda store, actor: []):
            api.call(self.store, "message", {"actor": CHIEF, "to": ["dev"], "body": "hi", "org": self.team})
        self.assertEqual(woken, [self.team])

    # ---------------- tasks
    def test_assigning_tasks_below(self):
        s = self.store
        with self.assertRaises(OrgError):
            s.work(CHIEF, "task", {"org": self.team, "title": "No owner"})
        with self.assertRaises(OrgError):
            s.work(CHIEF, "doc_write", {"org": self.team, "key": "k", "body": "b"})
        task = s.work(CHIEF, "task", {"org": self.team, "title": "Landing page", "owner": "dev"})
        self.assertEqual((task["id"], task["owner"], task["created_by"]), ("T1", "dev", self.sec + "/chief"))
        s.work(CHIEF, "task", {"org": self.team, "task_id": "T1", "status": "working"})
        self.assertEqual(s.get(self.team)["tasks"]["T1"]["status"], "working")
        self.assertIn("Your open tasks: T1 Landing page (working)", render(s, s.get(self.team), "dev"))
        s.work(LEAD, "doc_write", {"key": "spec", "body": "# Spec"})
        self.assertEqual(s.work(CHIEF, "doc_read", {"org": self.team, "key": "spec"})["body"], "# Spec")

    # ---------------- protocols
    def test_a_protocol_issued_from_above_takes_effect_and_stays(self):
        s = self.store
        p = s.protocol(CHIEF, "propose", {"org": self.team, "title": "Report every Friday", "rationale": "the person asked",
                                          "guidance": "Send the week's progress to chief.", "trigger": "Friday",
                                          "evidence": ["msg 1"]})
        self.assertEqual((p["status"], p["issued_by"]["name"], p["votes"]), ("active", "秘书处", {}))
        self.assertIn("[weak, issued by 秘书处] Report every Friday", render(s, s.get(self.team), "dev"))
        for change in ({"retire_target": p["id"]}, {"supersedes": p["id"]}):
            with self.assertRaises(OrgError):
                s.protocol(LEAD, "propose", dict({"title": "drop it", "rationale": "r", "guidance": "g", "trigger": "t",
                                                  "evidence": ["x"]}, **change))
        gone = s.protocol(CHIEF, "propose", {"org": self.team, "title": "No more Friday reports", "rationale": "done",
                                             "retire_target": p["id"]})
        self.assertEqual((gone["status"], s.get(self.team)["protocols"][p["id"]]["status"]), ("enacted", "retired"))

    def test_a_downward_protocol_binds_every_organization_below(self):
        s = self.store
        ep = s.episode(CHIEF, "open", {"title": "Pushes", "participants": ["chief", "helper"]})
        s.episode(CHIEF, "close", {"episode_id": ep["id"], "outcome": "partial", "summary": "a push broke the site"})
        s.episode(CHIEF, "reflect", {"episode_id": ep["id"], "body": "only the secretariat should push"})
        p = s.protocol(CHIEF, "propose", {"title": "The secretariat pushes", "rationale": "a push broke the site",
                                          "strength": "strong", "episode_id": ep["id"], "rules": [DENY_PUSH],
                                          "downward": True})
        s.protocol(HELPER, "vote", {"protocol_id": p["id"], "vote": "approve", "reason": "agreed"})
        self.assertEqual(s.get(self.sec)["protocols"][p["id"]]["status"], "active")
        for actor in (LEAD, DEV, SUB):  # below, at any depth
            allowed, reasons = s.gate(actor, "Bash", {"command": "git push origin main"})
            self.assertFalse(allowed)
            self.assertIn("The secretariat pushes", reasons[0])
        self.assertTrue(s.gate(OTHER, "Bash", {"command": "git push origin main"})[0])
        self.assertIn("[strong, enforced, from 秘书处] The secretariat pushes", render(s, s.get(self.sub), "s1"))
        used = s.protocol(SUB, "use", {"org": self.sec, "protocol_id": p["id"], "outcome": "followed",
                                       "note": "asked chief to push"})
        self.assertEqual(used["uses"], 1)
        listed = s.protocol(DEV, "list", {})
        self.assertEqual(listed["%s/%s" % (self.sec, p["id"])]["from"], "秘书处")

    def test_status_of_an_organization_below(self):
        s = self.store
        s.send(LEAD, ["dev"], "start with the header")
        out = api.handle_call(s, "status", {"org": "Team"}, CHIEF)
        self.assertEqual(out["org_id"], self.team)
        self.assertIn("below your organization '秘书处'", out["context"])
        self.assertIn("start with the header", out["context"])
        with self.assertRaises(OrgError):
            api.handle_call(s, "status", {"org": self.sec}, DEV)
        self.assertIn("Below this organization: Team", render(s, s.get(self.sec), "chief"))
        self.assertIn("Above this organization: 秘书处", render(s, s.get(self.team), "dev"))

    # ---------------- what the person sees
    def test_the_app_shows_the_tree_and_the_notices(self):
        s = self.store
        s.work(CHIEF, "task", {"org": self.team, "title": "Landing page", "owner": "dev"})
        s.work(LEAD, "task", {"title": "Blocked one", "owner": "dev", "status": "blocked"})
        s.protocol(CHIEF, "propose", {"org": self.team, "title": "Report", "rationale": "r", "guidance": "g",
                                      "trigger": "t", "evidence": ["x"], "downward": True})
        snap = views.snapshot(s, self.sec, lang="en-US")
        self.assertEqual(snap["org"]["parent"], None)
        self.assertEqual([(c["name"], c["blocked"], c["working"]) for c in snap["org"]["children"]], [("Team", 1, 1)])
        team = views.snapshot(s, self.team, lang="en-US")
        self.assertEqual(team["org"]["parent"]["name"], "秘书处")
        self.assertEqual(team["protocols"][0]["issued_by"]["name"], "秘书处")
        self.assertEqual([p["from"] for p in views.snapshot(s, self.sub)["inherited_protocols"]], ["Team"])
        self.assertEqual({o["id"]: o["parent"] for o in views.org_list(s)}[self.sub], self.team)
        notices = [i["text"] for i in views.chat(s, self.team, "group", lang="en-US")["items"] if i["type"] == "notice"]
        self.assertIn("This organization is now under “秘书处”", notices)
        self.assertIn("chief (秘书处) set task T1 “Landing page” for dev (To do)", notices)
        self.assertIn("chief (秘书处) issued protocol P1 “Report”; it is in effect now", notices)
        mine = [i["text"] for i in views.chat(s, self.sec, "group")["items"] if i["type"] == "notice"]
        self.assertIn("「Team」成为本组织的下级组织", mine)
        self.assertIn("chief 在「Team」把任务 T1「Landing page」交给 dev（待办）", mine)
        self.assertIn("chief 给「Team」下发了协议 P1「Report」", mine)


class Endpoint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = dict(os.environ)
        os.environ["RELIC_HOME"] = str(Path(self.tmp.name) / "relic")
        self.store = Store()
        self.a = self.store.create("a-s", "A", "", "a", "")["id"]
        self.b = self.store.create("b-s", "B", "", "b", "")["id"]
        self.app, self.server = web.serve(0, store=self.store, write_info=True)
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True).start()

    def tearDown(self):
        self.app.stopping.set()
        self.app.hub.shutdown()
        self.server.shutdown()
        self.server.server_close()
        os.environ.clear()
        os.environ.update(self.saved)
        self.tmp.cleanup()

    def post(self, path, body, token=True):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Relic-Token"] = self.app.token
        request = urllib.request.Request("http://127.0.0.1:%d%s" % (self.app.port, path), method="POST",
                                         data=json.dumps(body).encode("utf-8"), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=20) as reply:
                return reply.status, json.loads(reply.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.loads(error.read().decode("utf-8"))

    def test_only_the_person_sets_the_parent_in_the_app(self):
        self.assertEqual(self.post("/api/org/%s/parent" % self.b, {"parent": self.a}, token=False)[0], 403)
        self.assertEqual(self.post("/api/org/%s/parent" % self.b, {"parent": self.a}), (200, {"org_id": self.b, "parent": self.a}))
        self.assertEqual(self.store.get(self.b)["parent"], self.a)
        self.assertEqual(self.post("/api/org/%s/parent" % self.a, {"parent": self.b})[0], 400)  # a circle
        self.assertEqual(self.post("/api/org/%s/parent" % self.b, {"parent": None})[1]["parent"], None)


if __name__ == "__main__":
    unittest.main()
